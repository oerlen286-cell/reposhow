"""
One-command GitHub intro video generator.

Usage:
    python reposhow.py https://github.com/user/repo
    python reposhow.py https://github.com/user/repo --output out/my_video.mp4
    python reposhow.py https://github.com/user/repo --dry-run   # skip render, just print params
    python reposhow.py https://github.com/user/repo --lang en   # English narration & subtitles

Requirements:
    pip install playwright dashscope openai google-genai && playwright install chromium
    npm install
    Set environment variables: GEMINI_API_KEY, DASHSCOPE_API_KEY, OPENAI_API_KEY
    Install ffmpeg for PCM→MP3 conversion.
"""

import argparse
import base64
import copy
import hashlib
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import dashscope
from dashscope.audio.tts_v2 import SpeechSynthesizer
from playwright.sync_api import sync_playwright, Page

GITHUB_VIDEO_DIR = Path(__file__).parent
VIEWPORT_W = 1920
VIEWPORT_H = 1080
COMPOSITION_ID = "Auto"

# DashScope TTS config (set via environment variable DASHSCOPE_API_KEY)
DASHSCOPE_API_KEY_ZH = os.environ.get("DASHSCOPE_API_KEY", "")
DASHSCOPE_API_KEY_EN = os.environ.get("DASHSCOPE_API_KEY", "")
dashscope.api_key = DASHSCOPE_API_KEY_ZH
dashscope.base_websocket_api_url = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
TTS_MODEL = "cosyvoice-v3-flash"
EN_TTS_MODEL = "cosyvoice-v3-flash"
TTS_VOICE_ZH = "longanhuan"   # Chinese voice
TTS_VOICE_EN = "donna"  # Native English voice for DashScope/CosyVoice
TTS_VOICE = TTS_VOICE_ZH      # default
# OpenAI API key (for narration script generation + Whisper transcription)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_TTS_MODEL = "gpt-4o-mini-tts"
OPENAI_TTS_VOICE = "alloy"
# Gemini TTS (zh/en): set env GEMINI_API_KEY. Requires ffmpeg for PCM→MP3.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# Gemini TTS endpoint / voice
GEMINI_TTS_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-3.1-flash-tts-preview:generateContent"
)
GEMINI_TTS_STREAM_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-3.1-flash-tts-preview:streamGenerateContent"
)
GEMINI_TTS_VOICE_ZH = "Callirrhoe"
GEMINI_TTS_VOICE_EN = "Puck"
GEMINI_TTS_VOICE = GEMINI_TTS_VOICE_ZH  # default

# Default multi-speaker voice mapping
DEFAULT_MULTI_SPEAKER_CONFIGS_ZH: list[dict] = [
    {"speaker": "Speaker 1", "voice_name": "Puck"},
    {"speaker": "Speaker 2", "voice_name": "Callirrhoe"},
]
DEFAULT_MULTI_SPEAKER_CONFIGS_EN: list[dict] = [
    {"speaker": "Speaker 1", "voice_name": "Puck"},
    {"speaker": "Speaker 2", "voice_name": "Charon"},
]
DEFAULT_MULTI_SPEAKER_CONFIGS = DEFAULT_MULTI_SPEAKER_CONFIGS_ZH


def _resolve_gemini_api_key() -> str:
    """Env GEMINI_API_KEY overrides in-file GEMINI_API_KEY."""
    env = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if env:
        return env
    return (GEMINI_API_KEY or "").strip()


# ── Helpers ───────────────────────────────────────────────────────────────────

def slugify(url: str) -> str:
    """Extract repo name from URL as filesystem-safe slug."""
    return re.sub(r"[^a-z0-9_-]", "-", url.rstrip("/").split("/")[-1].lower())


def format_star_count(raw: str) -> str:
    """Normalize raw star text to display string, e.g. '16400' → '16.4k'."""
    raw = raw.strip().replace(",", "")
    if re.match(r"^\d+(\.\d+)?[kKmM]$", raw):
        return raw
    try:
        n = int(raw)
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}m"
        if n >= 1_000:
            return f"{n / 1_000:.1f}k"
        return str(n)
    except ValueError:
        return raw or "0"


def hide_cookie_banners(page: Page) -> None:
    page.add_style_tag(content="""
        .js-cookie-consent, .cookie-banner, [data-testid="cookie-banner"],
        .signup-prompt, .js-notice { display: none !important; }
    """)


# ── Detection ─────────────────────────────────────────────────────────────────

def detect_params(url: str, screenshot_dir: Path, scroll_distance: int = 2500, scroll_duration: int = 25) -> dict:
    """
    Open the GitHub repo page, capture three screenshots, and auto-detect
    all layout parameters needed by GithubIntro.
    """
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    rel_dir = "/" + screenshot_dir.relative_to(GITHUB_VIDEO_DIR / "public").as_posix()

    params: dict = {
        "screenshotDir": rel_dir,
        "repoDescription": "",
        "starCount": "0",
        "fullPageHeight": 4000,
        "scrollFromY": 0,
        "scrollToY": None,          # None → ScrollScene scrolls to page bottom
        "scene1Origin": {"x": 200, "y": 180},
        "scene1Annotation": {"left": 135, "top": 115, "width": 180, "height": 5},
        "scene2Origin": {"x": 1800, "y": 57},
        "scene2Annotation": {"left": 1765, "top": 118, "width": 120, "height": 6},
        "scrollSubtitle": "",
        "scrollPauseFrames": 90,
        "scrollPauseScale": 1.6,
        "scaleFrom": 1.0,
        "scaleTo": 1.9,
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # DPR=2 context: viewport screenshots only (zoom scenes need retina quality)
        ctx_2x = browser.new_context(
            viewport={"width": VIEWPORT_W, "height": VIEWPORT_H},
            device_scale_factor=2,
        )
        page = ctx_2x.new_page()

        print(f"  Loading {url} ...")
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(2000)
        hide_cookie_banners(page)

        # ── Repo description (og:description is usually clean) ──
        desc = page.evaluate(
            'document.querySelector(\'meta[property="og:description"]\')?.content ?? ""'
        )
        if desc:
            params["repoDescription"] = desc.strip()[:80]
            params["scrollSubtitle"] = desc.strip()[:50]

        # ── Star count ──
        star_text = page.evaluate("""() => {
            const selectors = [
                '#repo-stars-counter-star',
                '.starring-container .social-count',
                '[href$="/stargazers"] .Counter',
                '[data-view-component] [href$="/stargazers"]',
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el?.textContent?.trim()) return el.textContent.trim();
            }
            return null;
        }""")
        if star_text:
            params["starCount"] = format_star_count(star_text)

        # ── Scene 1: repo name bounding box ──
        try:
            box = page.locator("strong[itemprop='name'] a").first.bounding_box()
            if box:
                params["scene1Annotation"] = {
                    "left": int(box["x"]),
                    "top": int(box["y"] + box["height"]),
                    "width": int(box["width"]),
                    "height": 5,
                }
                origin_x = 10
                try:
                    user_box = page.locator(
                        "nav[aria-label='Breadcrumbs'] ol li:first-child a, "
                        "a[data-hovercard-type='user'], "
                        "span[itemprop='author'] a"
                    ).first.bounding_box()
                    if user_box:
                        origin_x = max(10, int(user_box["x"]) - 10)
                except Exception:
                    pass
                params["scene1Origin"] = {
                    "x": origin_x,
                    "y": int(box["y"] + box["height"] / 2),
                }
        except Exception:
            pass

        # ── Scene 2: star button bounding box ──
        try:
            box = page.evaluate("""() => {
                const selectors = [
                    'button[data-aria-prefix*="Star this"]',
                    'form[action$="/star"] button[type="submit"]',
                    'form[action$="/unstar"] button[type="submit"]',
                    '#repo-stars-counter-star',
                ];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (!el) continue;
                    const btn = el.closest('button') ?? el;
                    const group = btn.closest('.BtnGroup')
                                ?? btn.closest('.js-social-form')?.parentElement
                                ?? btn;
                    const r = group.getBoundingClientRect();
                    if (r.width > 0) return { x: r.x, y: r.y, width: r.width, height: r.height };
                }
                return null;
            }""")
            if not box:
                print("  [!] scene2: star button not found, using defaults")
            else:
                print(f"  [✓] scene2: star button at x={box['x']:.0f}, width={box['width']:.0f}")
                params["scene2Annotation"] = {
                    "left": int(box["x"]),
                    "top": int(box["y"] + box["height"]),
                    "width": int(box["width"]),
                    "height": 5,
                }
                params["scene2Origin"] = {
                    "x": min(VIEWPORT_W - 10, int(box["x"] + box["width"]) + 10),
                    "y": int(box["y"] + box["height"] / 2),
                }
        except Exception:
            pass

        # Viewport screenshots at 2x DPR (zoom scenes: repo-home, star-count)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(300)
        page.screenshot(path=str(screenshot_dir / "repo-home.png"), full_page=False)
        page.screenshot(path=str(screenshot_dir / "star-count.png"), full_page=False)
        print("  [✓] repo-home.png + star-count.png  (2x DPR)")
        ctx_2x.close()

        # Full-page screenshot
        ctx_1x = browser.new_context(
            viewport={"width": VIEWPORT_W, "height": VIEWPORT_H},
            device_scale_factor=1,
        )
        page = ctx_1x.new_page()
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(2000)
        hide_cookie_banners(page)

        page_height = page.evaluate("document.body.scrollHeight")

        readme_y = page.evaluate("""() => {
            const el = document.getElementById('readme')
                     ?? document.querySelector('article.markdown-body')
                     ?? document.querySelector('[data-target="readme-toc.content"]');
            if (!el) return 0;
            return Math.round(el.getBoundingClientRect().top + window.scrollY);
        }""")
        scroll_from = int(readme_y) - 20
        scroll_to   = min(int(readme_y) + scroll_distance, page_height - VIEWPORT_H)
        params["scrollFromY"]      = scroll_from
        params["scrollToY"]        = scroll_to
        params["scrollDurationSec"] = scroll_duration
        print(f"  [✓] README position detected at y={readme_y}px")
        ctx_1x.close()

        clip_h = scroll_to + VIEWPORT_H + 200
        full_page_dpr = round(min(2.0, 6000 / clip_h), 2)
        ctx_fp = browser.new_context(
            viewport={"width": VIEWPORT_W, "height": clip_h},
            device_scale_factor=full_page_dpr,
        )
        page = ctx_fp.new_page()
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(2000)
        hide_cookie_banners(page)
        page.evaluate("window.scrollTo(0, 0)")
        page.screenshot(path=str(screenshot_dir / "full-page.png"), full_page=False)
        params["fullPageHeight"] = clip_h
        print(f"  [✓] full-page.png  ({VIEWPORT_W}x{clip_h}px, {full_page_dpr}x DPR)")
        
        # ── Readme Text ──
        readme_text = page.evaluate("() => document.querySelector('article.markdown-body')?.innerText || ''")
        if readme_text:
            params["readmeText"] = readme_text.strip()[:1500]
            print(f"  [✓] README text extracted ({len(params['readmeText'])} chars)")
            
        ctx_fp.close()
        browser.close()

    return {k: v for k, v in params.items() if v is not None}


# ── TTS ───────────────────────────────────────────────────────────────────────

def build_narration_script(slug: str, description: str, star_count: str, lang: str = "zh", readme_text: str = "") -> str:
    repo_name = slug.replace("-", " ")
    try:
        import openai
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        
        prompt_ctx = f"Project name: {repo_name}\nDescription: {description or 'No description'}\nGitHub Stars: {star_count}\n"
        if readme_text:
            prompt_ctx += f"README Snippet:\n\"\"\"{readme_text}\"\"\"\n"

        if lang == "en":
            prompt = (
                f"You are a tech video blogger creating a 15-second narration for a GitHub open-source project.\n\n"
                f"{prompt_ctx}\n"
                "Based on the context above, write a natural, engaging English narration (4-5 sentences, ~60-80 words). "
                "Highlight the project's actual features and value. End with a call-to-action to check it out. "
                "Output only the narration text, no explanations."
            )
        else:
            prompt = (
                f"你是一位科技视频博主，正在为一个 GitHub 开源项目制作 15 秒介绍视频的旁白。\n\n"
                f"{prompt_ctx}\n"
                "请结合上述摘要，生成一段自然流畅的中文旁白（4～5句话，约100字），"
                "语气活泼，准确指出该项目的核心功能、卖点和价值，"
                "结尾引导观众查看项目详情。只输出旁白正文，不加任何说明或标点以外的内容。"
            )
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.7,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"  [!] LLM narration failed: {e}, falling back to template")
        if lang == "en":
            lines = [
                f"This is an open-source GitHub project called {repo_name}.",
                description.strip() if description else "",
                f"It has already earned {star_count} stars on GitHub.",
                "Let's take a closer look at what it can do.",
            ]
        else:
            lines = [
                f"这是一个名为 {repo_name} 的 GitHub 开源项目。",
                description.strip() if description else "",
                f"在 GitHub 上已经收获了 {star_count} 颗星。",
                "我们一起来看看项目的详细内容。",
            ]
        return "\n".join(line for line in lines if line)


def _has_speaker_tags(text: str) -> bool:
    if not text or not text.strip():
        return False
    # Only enable multi-speaker features if we explicitly detect Speaker markers
    if re.search(r"(?m)^\s*Speaker\s*\d*\s*:", text, flags=re.I):
        return True
    return False


def strip_all_metadata_for_subtitles(text: str) -> str:
    """Strip metadata (## headers, [...] tags, Speaker marks) for pure subtitles."""
    if not text:
        return ""
    
    # 1. Remove paragraphs starting with ## (Markdown meta blocks)
    paragraphs = re.split(r'\n\s*\n', text)
    kept_paragraphs = []
    for p in paragraphs:
        if not p.strip():
            continue
        if p.strip().startswith("##"):
            continue
        kept_paragraphs.append(p)
    out = "\n\n".join(kept_paragraphs)
    
    # 2. Remove Speaker N: tags
    out = re.sub(r"(?m)^\s*Speaker\s*\d*\s*:\s*", "", out, flags=re.I)
    
    # 3. Remove stage brackets [...]
    prev = None
    while prev != out:
        prev = out
        out = re.sub(r"\[[^\]]*\]", "", out)
        
    # 4. Remove bold/italic markup
    out = re.sub(r"\*\*(.+?)\*\*", r"\1", out, flags=re.DOTALL)
    out = re.sub(r"__(.+?)__", r"\1", out, flags=re.DOTALL)
    
    # Clean up excess whitespace
    out = re.sub(r"[ \t]+", " ", out)
    out = re.sub(r"\s*\n\s*", "\n", out)
    return out.strip()


def _ffprobe_duration_seconds(path: Path) -> float | None:
    """Return audio file duration in seconds, or None if ffprobe is missing or fails."""
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        s = proc.stdout.strip()
        if not s:
            return None
        return float(s)
    except (FileNotFoundError, ValueError, subprocess.CalledProcessError):
        return None


# Minimum on-screen duration at 30fps
MIN_SUBTITLE_FRAMES = 36  # ~1.2s @ 30fps


def stretch_subtitle_lines_to_narration_audio(
    lines: list[dict], audio_path: Path, fps: int = 30,
) -> None:
    """
    Scale subtitle startFrame/endFrame so the cue track spans the real narration length.
    Only ever EXPANDS timing — never compresses. This prevents subtitles from running
    ahead of the audio.
    """
    if not lines:
        return
    duration_sec = _ffprobe_duration_seconds(audio_path)
    if duration_sec is None or duration_sec <= 0:
        return
    last_sec = max(line["endFrame"] for line in lines) / fps
    if last_sec < 0.2:
        return
    ratio = duration_sec / last_sec

    # FIX: never compress — only expand. Compressing causes subtitles to run ahead of audio.
    if ratio <= 1.0:
        print(
            f"  [i] Subtitle span ({last_sec:.1f}s) >= audio ({duration_sec:.1f}s); "
            f"skipping stretch (never compress)."
        )
        return
    if 0.97 <= ratio <= 1.03:
        return
    for line in lines:
        line["startFrame"] = int(round(line["startFrame"] * ratio))
        line["endFrame"] = int(round(line["endFrame"] * ratio))
    print(
        f"  [✓] Subtitle timing stretched to narration length: "
        f"{last_sec:.1f}s → {duration_sec:.1f}s (×{ratio:.3f})"
    )


def redistribute_subtitle_timing(
    lines: list[dict],
    audio_path: Path,
    fps: int = 30,
    lang: str = "zh",
    min_cue_frames: int | None = None,
) -> None:
    """
    Recompute subtitle timing proportionally based on text length and actual
    audio duration. Uses a dynamic floor so total floor time never exceeds
    audio duration, preventing subtitles from running ahead of speech.
    """
    if not lines:
        return
    duration_sec = _ffprobe_duration_seconds(audio_path)
    if duration_sec is None or duration_sec <= 0:
        return

    # Remove trivial punctuation-only cues
    _PUNCT_ONLY = re.compile(r'^[\s\u3000。！？；!?;，,、：:…—–\-·.]+$')
    i = len(lines) - 1
    while i >= 0:
        if _PUNCT_ONLY.match(lines[i]["text"]):
            if i > 0:
                lines[i - 1]["text"] += lines[i]["text"]
            lines.pop(i)
        i -= 1

    if not lines:
        return

    total_frames = int(duration_sec * fps)
    gap_frames = 3
    total_gaps = gap_frames * max(0, len(lines) - 1)
    available = max(total_frames - total_gaps, len(lines))

    # FIX: dynamic floor — cap so total floor time never exceeds 60% of audio duration.
    # This prevents the scale-back compression that caused subtitles to run ahead.
    requested_floor = min_cue_frames if min_cue_frames is not None else MIN_SUBTITLE_FRAMES
    max_floor = max(1, int(available * 0.6 / len(lines)))
    floor_frames = min(requested_floor, max_floor)
    floor_frames = max(1, floor_frames)

    def _text_weight(text: str) -> float:
        if lang == "en":
            return max(len(text.split()), 1)
        return max(sum(1.0 if not c.isascii() else 0.5 for c in text if not c.isspace()), 1.0)

    weights = [_text_weight(line["text"]) for line in lines]
    total_weight = sum(weights)

    cursor = 0
    for i, line in enumerate(lines):
        dur = max(floor_frames, int(round(available * weights[i] / total_weight)))
        line["startFrame"] = cursor
        line["endFrame"] = cursor + dur
        cursor += dur + gap_frames

    # FIX: if total span exceeds audio, scale back — but log it clearly.
    last_end = max(l["endFrame"] for l in lines)
    if last_end > total_frames and last_end > 0:
        ratio = total_frames / last_end
        print(
            f"  [i] Subtitle span ({last_end/fps:.1f}s) slightly > audio ({duration_sec:.1f}s); "
            f"scaling back by {ratio:.3f} to fit."
        )
        for line in lines:
            line["startFrame"] = int(round(line["startFrame"] * ratio))
            line["endFrame"] = int(round(line["endFrame"] * ratio))
        # Re-enforce minimum gap after scaling
        for i in range(1, len(lines)):
            if lines[i]["startFrame"] <= lines[i - 1]["endFrame"]:
                lines[i]["startFrame"] = lines[i - 1]["endFrame"] + 1

    orig_last = max(l["endFrame"] for l in lines) / fps if lines else 0
    print(
        f"  [✓] Subtitle timing redistributed proportionally: "
        f"{len(lines)} cues over {duration_sec:.1f}s audio "
        f"(last cue ends at {orig_last:.1f}s)"
    )


def finalize_subtitle_timeline(lines: list[dict]) -> None:
    """
    Sort cues by startFrame and remove overlaps so only one line is active at a time.
    """
    if not lines:
        return
    gap = 1
    lines.sort(key=lambda x: (x["startFrame"], x["endFrame"]))
    for i in range(1, len(lines)):
        cur = lines[i]
        prev = lines[i - 1]
        min_start = prev["endFrame"] + gap
        if cur["startFrame"] < min_start:
            delta = min_start - cur["startFrame"]
            cur["startFrame"] += delta
            cur["endFrame"] += delta
        if cur["endFrame"] < cur["startFrame"]:
            cur["endFrame"] = cur["startFrame"]


def enforce_min_subtitle_duration(
    lines: list[dict], min_frames: int = MIN_SUBTITLE_FRAMES, gap: int = 1
) -> None:
    """Ensure each cue is visible at least min_frames; ripple later cues to the right."""
    if not lines or min_frames < 1:
        return
    lines.sort(key=lambda x: (x["startFrame"], x["endFrame"]))
    for _ in range(len(lines) + 3):
        changed = False
        for row in lines:
            s, e = row["startFrame"], row["endFrame"]
            need_end = s + min_frames - 1
            if e < need_end:
                row["endFrame"] = need_end
                changed = True
        for i in range(1, len(lines)):
            prev_end = lines[i - 1]["endFrame"]
            min_start = prev_end + gap
            if lines[i]["startFrame"] < min_start:
                delta = min_start - lines[i]["startFrame"]
                lines[i]["startFrame"] += delta
                lines[i]["endFrame"] += delta
                changed = True
        if not changed:
            break


def build_subtitle_lines(
    narration_text: str,
    fps: int = 30,
    chars_per_sec: float = 4.5,
    gap_frames: int = 6,
    lang: str = "zh",
) -> list[dict]:
    """
    Fallback: split narration into per-line subtitle entries with estimated frame timing.
    """
    narration_text = strip_all_metadata_for_subtitles(narration_text)
    if lang == "en":
        chars_per_sec = 14.0

    raw_lines = [l.strip() for l in narration_text.split("\n") if l.strip()]
    chunks: list[str] = []
    for line in raw_lines:
        chunks.extend(_split_chunks(line, lang=lang))

    result = []
    current = 0
    for chunk in chunks:
        duration = max(fps * 2, int(len(chunk) / chars_per_sec * fps))
        result.append({
            "text": chunk,
            "startFrame": current,
            "endFrame": current + duration,
        })
        current += duration + gap_frames
    return result


# ── Subtitle helpers ──────────────────────────────────────────────────────────

_SUB_MAX      = 14
_SUB_MAX_HARD = 22
_HARD_BREAK   = set("。！？；!?;")
_SOFT_BREAK   = set("，、：,:")

_EN_MAX_WORDS = 7
_EN_HARD_BREAK = set(".!?;")
_EN_SOFT_BREAK = set(",:")


def _visual_len(s: str) -> float:
    return sum(0.5 if c.isascii() else 1 for c in s)


def _split_chunks_en(text: str) -> list[str]:
    """Split English text into subtitle chunks by word count and punctuation."""
    text = re.sub(r"\s+", " ", text).strip()
    words = text.split(" ")
    chunks, current = [], []
    for word in words:
        current.append(word)
        last_char = word[-1] if word else ""
        if last_char in _EN_HARD_BREAK or len(current) >= _EN_MAX_WORDS:
            chunks.append(" ".join(current).strip())
            current = []
        elif last_char in _EN_SOFT_BREAK and len(current) >= 4:
            chunks.append(" ".join(current).strip())
            current = []
    if current:
        chunks.append(" ".join(current).strip())
    return [c for c in chunks if c]


def _split_chunks(text: str, lang: str = "zh") -> list[str]:
    """Split text into display-safe subtitle chunks respecting punctuation boundaries."""
    if lang == "en":
        return _split_chunks_en(text)
    text = re.sub(r"\s+", " ", text).strip()
    chunks, current, cur_len = [], [], 0.0
    for ch in text:
        current.append(ch)
        cur_len += _visual_len(ch)
        if ch in _HARD_BREAK or (cur_len >= _SUB_MAX and ch in _SOFT_BREAK) or cur_len >= _SUB_MAX_HARD:
            chunk = "".join(current).strip()
            if chunk:
                chunks.append(chunk)
            current, cur_len = [], 0.0
    tail = "".join(current).strip()
    if tail:
        chunks.append(tail)
    return chunks


# ── Subtitle correction helpers ───────────────────────────────────────────────

class _Word:
    def __init__(self, word: str, start: float, end: float):
        self.word = word
        self.start = start
        self.end = end


def _normalize_for_compare(text: str) -> str:
    t = re.sub(r"\s+", "", text or "")
    t = re.sub(r"[^\w\u4e00-\u9fff]", "", t)
    return t.lower()


def _group_whisper_words_en(words: list[_Word]) -> list[tuple[float, float, str]]:
    """Group raw English Whisper words into chunks, bypassing difflib alignment."""
    chunks = []
    current_words = []
    start = 0.0
    for w in words:
        word = w.word.strip()
        if not word:
            continue
        if not current_words:
            start = w.start
        current_words.append(word)
        last_char = word[-1] if word else ""
        if last_char in ('.', '!', '?', ';', ',', ':') or len(current_words) >= 7:
            end = max(float(w.end), float(start) + 0.5)
            chunks.append([float(start), end, " ".join(current_words)])
            current_words = []

    if current_words:
        end = max(float(words[-1].end), float(start) + 0.5)
        chunks.append([float(start), end, " ".join(current_words)])

    # Prevent overlap
    for i in range(len(chunks) - 1):
        if chunks[i+1][0] < chunks[i][1] + 0.05:
            delta = chunks[i][1] + 0.05 - chunks[i+1][0]
            chunks[i+1][0] += delta
            chunks[i+1][1] += delta

    return [(c[0], c[1], c[2]) for c in chunks]


def _token_to_chars(word: _Word) -> list[tuple[str, float, float]]:
    chars = [c for c in word.word.strip() if not c.isspace()]
    if not chars:
        return []
    duration = max(word.end - word.start, 0.02)
    step = duration / len(chars)
    return [(ch, word.start + i * step, word.start + (i + 1) * step) for i, ch in enumerate(chars)]


def _words_to_char_timeline(words: list[_Word]) -> list[tuple[str, float, float]]:
    timeline = []
    for w in words:
        timeline.extend(_token_to_chars(w))
    return timeline


def _interpolate_times(start: float, end: float, count: int) -> list[tuple[float, float]]:
    if count <= 0:
        return []
    end = max(end, start)
    step = (end - start) / count if count else 0.0
    return [(start + i * step, start + (i + 1) * step) for i in range(count)]


def _map_reference_times(
    reference_text: str, words: list[_Word]
) -> tuple[str, list[tuple[float, float]]]:
    """Align reference text chars to Whisper word timeline using difflib."""
    ref_norm = "".join(c for c in reference_text if not c.isspace())
    timeline = _words_to_char_timeline(words)
    rec_norm = "".join(ch for ch, _, _ in timeline)
    if not ref_norm or not rec_norm:
        return ref_norm, []

    score = difflib.SequenceMatcher(
        None, _normalize_for_compare(rec_norm), _normalize_for_compare(ref_norm)
    ).ratio()
    print(f"  [Whisper↔reference similarity: {score:.1%}]")

    mapped: list[tuple[float, float] | None] = [None] * len(ref_norm)
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, rec_norm, ref_norm).get_opcodes():
        if tag == "equal":
            for ri, rj in zip(range(i1, i2), range(j1, j2)):
                mapped[rj] = (timeline[ri][1], timeline[ri][2])
        elif tag == "replace":
            st = timeline[i1][1] if i1 < i2 else (timeline[i1 - 1][2] if i1 > 0 else 0.0)
            et = timeline[i2 - 1][2] if i1 < i2 else st
            for rj, pair in zip(range(j1, j2), _interpolate_times(st, et, j2 - j1)):
                mapped[rj] = pair
        elif tag == "insert":
            prev = timeline[i1 - 1][2] if i1 > 0 else 0.0
            nxt  = timeline[i1][1] if i1 < len(timeline) else prev
            for rj, pair in zip(range(j1, j2), _interpolate_times(prev, nxt, j2 - j1)):
                mapped[rj] = pair

    for idx, pair in enumerate(mapped):
        if pair is not None:
            continue
        prev = next((mapped[p] for p in range(idx - 1, -1, -1) if mapped[p] is not None), None)
        nxt  = next((mapped[p] for p in range(idx + 1, len(mapped)) if mapped[p] is not None), None)
        if prev and nxt:
            mapped[idx] = (prev[1], nxt[0])
        elif prev:
            mapped[idx] = (prev[1], prev[1] + 0.08)
        elif nxt:
            mapped[idx] = (max(0.0, nxt[0] - 0.08), nxt[0])
        else:
            mapped[idx] = (0.0, 0.08)

    return ref_norm, mapped  # type: ignore[return-value]


def _reference_to_cues(reference_text: str, words: list[_Word], lang: str = "zh") -> list[tuple[float, float, str]]:
    """Build subtitle cues from reference text with Whisper-derived timing."""
    ref_norm, mapped = _map_reference_times(reference_text, words)
    if not ref_norm or not mapped:
        return []
    chunks = _split_chunks(reference_text, lang=lang)
    cues = []
    cursor = 0
    for chunk in chunks:
        norm_chunk = "".join(c for c in chunk if not c.isspace())
        if not norm_chunk:
            continue
        end_idx = min(len(ref_norm), cursor + len(norm_chunk))
        if end_idx <= cursor:
            continue
        start = mapped[cursor][0]
        end   = mapped[end_idx - 1][1]
        if end <= start + 0.1:
            end = start + 0.5
        cues.append((start, end, chunk))
        cursor = end_idx

    _CUE_GAP = 0.04
    adjusted: list[list[float | str]] = []
    for s, e, t in cues:
        adjusted.append([float(s), float(e), t])
    for i in range(len(adjusted) - 1):
        s, e, t = adjusted[i]
        ns, ne, nt = adjusted[i + 1]
        if ns < e + _CUE_GAP:
            delta = e + _CUE_GAP - ns
            adjusted[i + 1][0] = ns + delta
            adjusted[i + 1][1] = ne + delta
    return [(float(a[0]), float(a[1]), str(a[2])) for a in adjusted]


# ── Main transcription entry point ────────────────────────────────────────────

def transcribe_to_subtitles(
    audio_path: Path,
    reference_text: str = "",
    fps: int = 30,
    lang: str = "zh",
) -> list[dict]:
    """
    Use OpenAI Whisper (word-level) to transcribe TTS audio.
    Falls back to [] on any error so the caller can use the estimator fallback.
    """
    try:
        import openai
    except ImportError:
        print("  [!] openai package not installed. Run: pip install openai")
        return []

    print(f"  Transcribing audio with Whisper → {audio_path.name} ...")
    reference_text = strip_all_metadata_for_subtitles(reference_text)
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        whisper_lang = "en" if lang == "en" else "zh"
        whisper_prompt = (
            "Transcribe every word accurately, preserve technical terms and numbers."
            if lang == "en" else
            "请逐字转写音频内容，不要省略任何字词，保留英文术语与数字。"
        )
        with audio_path.open("rb") as f:
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="verbose_json",
                timestamp_granularities=["word", "segment"],
                language=whisper_lang,
                prompt=whisper_prompt,
            )

        raw_words = getattr(response, "words", None) or []
        segments  = getattr(response, "segments", None) or []

        words = [
            _Word(
                w["word"] if isinstance(w, dict) else w.word,
                float(w["start"] if isinstance(w, dict) else w.start),
                float(w["end"]   if isinstance(w, dict) else w.end),
            )
            for w in raw_words
        ]

        if words:
            span = max(w.end for w in words) - min(w.start for w in words)
            if span < 2.0:
                print(f"  [WARN] Word timestamps span only {span:.2f}s — using segment mode")
                words = []

        if not words and segments:
            words = [
                _Word(
                    seg["text"].strip() if isinstance(seg, dict) else seg.text.strip(),
                    float(seg["start"] if isinstance(seg, dict) else seg.start),
                    float(seg["end"]   if isinstance(seg, dict) else seg.end),
                )
                for seg in segments
            ]

        if not words:
            print("  [!] Whisper returned no usable timestamps")
            return []

        if lang == "en":
            if reference_text.strip():
                cues = _reference_to_cues(reference_text, words, lang="en")
                if not cues:
                    cues = _group_whisper_words_en(words)
            else:
                cues = _group_whisper_words_en(words)
        else:
            cues = _reference_to_cues(reference_text, words, lang=lang) if reference_text.strip() else [
                (w.start, w.end, w.word) for w in words if w.word.strip()
            ]

        result = [
            {"text": text, "startFrame": int(start * fps), "endFrame": int(end * fps)}
            for start, end, text in cues
            if text.strip()
        ]
        print(f"  [✓] {len(result)} subtitle segments (reference-corrected)")
        return result

    except Exception as e:
        print(f"  [!] Whisper transcription failed: {e}")
        return []


def _pcm_to_mp3_via_ffmpeg(pcm_bytes: bytes, mp3_path: Path) -> bool:
    """Convert raw s16le mono 24kHz PCM to MP3 using ffmpeg."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".pcm", delete=False) as tmp:
            tmp.write(pcm_bytes)
            pcm_file = tmp.name
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "s16le",
                    "-ar", "24000",
                    "-ac", "1",
                    "-i", pcm_file,
                    "-c:a", "libmp3lame",
                    "-q:a", "2",
                    str(mp3_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            return True
        finally:
            Path(pcm_file).unlink(missing_ok=True)
    except FileNotFoundError:
        print("  [!] ffmpeg not found — install ffmpeg to use Gemini TTS")
        return False
    except subprocess.CalledProcessError as e:
        print(f"  [!] ffmpeg PCM→MP3 failed: {e.stderr or e}")
        return False


def _generate_tts_gemini(text: str, output_path: Path, voice: str = GEMINI_TTS_VOICE_ZH) -> bool:
    """TTS via Gemini generateContent (AUDIO modality)."""
    api_key = _resolve_gemini_api_key()
    if not api_key:
        return False

    line = re.sub(r"\s+", " ", text.strip())
    if not line:
        print("  [!] Gemini TTS: empty text")
        return False

    payload = {
        "contents": [{"parts": [{"text": line}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": voice}
                }
            },
        },
        "model": "gemini-3.1-flash-tts-preview",
    }

    print(
        f"  Generating TTS (Gemini flash-tts, voice={voice}) → {output_path.name} ..."
    )
    print(f"  [DEBUG] TTS Text Snippet: {line[:50]}...")
    req = urllib.request.Request(
        GEMINI_TTS_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"  [!] Gemini TTS HTTP {e.code}: {err_body[:500]}")
        return False
    except OSError as e:
        print(f"  [!] Gemini TTS request failed: {e}")
        return False

    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        print("  [!] Gemini TTS: invalid JSON response")
        return False

    if data.get("error"):
        print(f"  [!] Gemini API error: {data['error']}")
        return False

    parts = (
        (data.get("candidates") or [{}])[0]
        .get("content", {})
        .get("parts") or []
    )
    b64 = None
    for part in parts:
        inline = part.get("inlineData") or part.get("inline_data")
        if inline and inline.get("data"):
            b64 = inline["data"]
            break
    if not b64:
        print("  [!] Gemini TTS: no inline audio in response")
        return False

    try:
        pcm_bytes = base64.b64decode(b64)
    except Exception as e:
        print(f"  [!] Gemini TTS: base64 decode failed: {e}")
        return False

    if not pcm_bytes:
        print("  [!] Gemini TTS: empty PCM")
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not _pcm_to_mp3_via_ffmpeg(pcm_bytes, output_path):
        return False
    print(f"  [✓] Narration saved ({output_path.stat().st_size:,} bytes)")
    return True


def _generate_tts_gemini_multi_speaker(
    text: str,
    output_path: Path,
    speaker_configs: list[dict],
) -> bool:
    """
    Multi-speaker TTS via Gemini streamGenerateContent REST API.

    speaker_configs example:
        [
            {"speaker": "Speaker 1", "voice_name": "Puck"},
            {"speaker": "Speaker 2", "voice_name": "Zephyr"},
        ]
    """
    api_key = _resolve_gemini_api_key()
    if not api_key:
        print("  [!] Gemini multi-speaker TTS: no API key")
        return False

    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        print("  [!] Gemini multi-speaker TTS: empty text")
        return False

    speaker_voice_configs = [
        {
            "speaker": cfg["speaker"],
            "voice_config": {
                "prebuilt_voice_config": {"voice_name": cfg["voice_name"]}
            },
        }
        for cfg in speaker_configs
    ]

    payload = {
        "contents": [{"role": "user", "parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["audio"],
            "temperature": 1,
            "speech_config": {
                "multi_speaker_voice_config": {
                    "speaker_voice_configs": speaker_voice_configs
                }
            },
        },
    }

    voices_str = ", ".join(f"{c['speaker']}={c['voice_name']}" for c in speaker_configs)
    print(
        f"  Generating TTS (Gemini multi-speaker: {voices_str}) → {output_path.name} ..."
    )

    url = f"{GEMINI_TTS_STREAM_URL}?key={api_key}&alt=sse"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    pcm_chunks: list[bytes] = []
    mime_type_found: str = ""
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                # SSE data lines start with "data: "
                if line.startswith("data:"):
                    line = line[len("data:"):].strip()
                if not line or line == "[DONE]":
                    continue
                try:
                    chunk_data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                parts = (
                    (chunk_data.get("candidates") or [{}])[0]
                    .get("content", {})
                    .get("parts") or []
                )
                for part in parts:
                    inline = part.get("inlineData") or part.get("inline_data")
                    if inline and inline.get("data"):
                        try:
                            audio_bytes = base64.b64decode(inline["data"])
                            pcm_chunks.append(audio_bytes)
                            if not mime_type_found:
                                mime_type_found = inline.get("mimeType") or inline.get("mime_type") or ""
                        except Exception:
                            pass
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"  [!] Gemini multi-speaker TTS HTTP {e.code}: {err_body[:500]}")
        return False
    except OSError as e:
        print(f"  [!] Gemini multi-speaker TTS request failed: {e}")
        return False

    if not pcm_chunks:
        print("  [!] Gemini multi-speaker TTS: no audio received")
        return False

    pcm_bytes = b"".join(pcm_chunks)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Parse sample rate from mime type (e.g. "audio/L16;rate=24000")
    rate = 24000
    if mime_type_found:
        for param in mime_type_found.split(";"):
            param = param.strip()
            if param.lower().startswith("rate="):
                try:
                    rate = int(param.split("=", 1)[1])
                except (ValueError, IndexError):
                    pass

    # Convert PCM → MP3 via ffmpeg
    try:
        with tempfile.NamedTemporaryFile(suffix=".pcm", delete=False) as tmp:
            tmp.write(pcm_bytes)
            pcm_file = tmp.name
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "s16le",
                    "-ar", str(rate),
                    "-ac", "1",
                    "-i", pcm_file,
                    "-c:a", "libmp3lame",
                    "-q:a", "2",
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        finally:
            Path(pcm_file).unlink(missing_ok=True)
    except FileNotFoundError:
        print("  [!] ffmpeg not found — install ffmpeg to convert PCM to MP3")
        return False
    except subprocess.CalledProcessError as e:
        print(f"  [!] ffmpeg PCM→MP3 failed: {e.stderr or e}")
        return False

    print(f"  [✓] Multi-speaker narration saved ({output_path.stat().st_size:,} bytes)")
    return True


def generate_tts(gemini_text: str, dashscope_text: str, output_path: Path, lang: str = "zh", speaker_configs: list[dict] | None = None) -> bool:
    """
    Generate TTS narration.
    English uses Gemini first and OpenAI fallback. Chinese uses Gemini first
    and DashScope fallback.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    is_en = (lang == "en")
    print(f"  [DEBUG] generate_tts: lang='{lang}', is_en={is_en}")
    
    if _resolve_gemini_api_key():
        print(f"  [DEBUG] Using Gemini TTS... (is_en={is_en})")
        if speaker_configs:
            if _generate_tts_gemini_multi_speaker(gemini_text, output_path, speaker_configs):
                return True
            print("  [!] Gemini multi-speaker TTS failed, falling back to single-voice")
        
        gemini_voice = GEMINI_TTS_VOICE_EN if is_en else GEMINI_TTS_VOICE_ZH
        if _generate_tts_gemini(gemini_text, output_path, voice=gemini_voice):
            return True
        fallback_name = "OpenAI" if is_en else "DashScope"
        print(f"  [!] Gemini TTS failed, falling back to {fallback_name}")

    if is_en:
        return _generate_tts_openai(dashscope_text, output_path)

    voice = TTS_VOICE_EN if is_en else TTS_VOICE_ZH
    model = EN_TTS_MODEL if is_en else TTS_MODEL
    try:
        return _generate_tts_dashscope(dashscope_text, output_path, model=model, voice=voice, is_en=is_en)
    finally:
        dashscope.api_key = DASHSCOPE_API_KEY_ZH


def _generate_tts_openai(text: str, output_path: Path) -> bool:
    line = re.sub(r"\s+", " ", text.strip())
    if not line:
        print("  [!] OpenAI TTS: empty text")
        return False
    if not OPENAI_API_KEY:
        print("  [!] OpenAI TTS skipped: OPENAI_API_KEY missing")
        return False

    print(
        f"  Generating TTS (OpenAI, model={OPENAI_TTS_MODEL}, voice={OPENAI_TTS_VOICE}) → {output_path.name} ..."
    )
    try:
        import openai

        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.audio.speech.create(
            model=OPENAI_TTS_MODEL,
            voice=OPENAI_TTS_VOICE,
            input=line,
        )
        response.write_to_file(output_path)
        print(f"  [✓] Narration saved ({output_path.stat().st_size:,} bytes)")
        return True
    except Exception as e:
        print(f"  [!] OpenAI TTS failed: {e}")
        return False


def _generate_tts_dashscope(text: str, output_path: Path, model: str = TTS_MODEL, voice: str = TTS_VOICE_ZH, is_en: bool = False) -> bool:
    print(f"  Generating TTS (DashScope, model={model}, voice={voice}) → {output_path.name} ...")
    try:
        synthesizer = SpeechSynthesizer(
            model=model,
            voice=voice,
            speech_rate=1.3,
            volume=70,
            language_hints=["en"] if is_en else ["zh"]
        )
        audio = synthesizer.call(text)
        if not audio:
            print("  [!] DashScope TTS returned empty audio")
            return False
        output_path.write_bytes(audio)
        print(f"  [✓] Narration saved ({len(audio):,} bytes)")
        return True
    except Exception as e:
        print(f"  [!] DashScope TTS failed: {e}")
        return False


# ── Render ────────────────────────────────────────────────────────────────────

def _normalize_props_for_render_cache(props: dict) -> dict:
    """Strip volatile fields so unchanged compositions hit export cache (e.g. ?t= on narration URL)."""
    p = copy.deepcopy(props)
    nav = p.get("narration")
    if isinstance(nav, str) and "?" in nav:
        p["narration"] = nav.split("?", 1)[0]
    return p


def render_props_fingerprint(params: dict) -> str:
    """Stable SHA-256 over normalized JSON for export cache keyed by output slug."""
    normalized = _normalize_props_for_render_cache(params)
    payload = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def render_video(params: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fp = render_props_fingerprint(params)
    fp_path = output.with_suffix(".fp")

    if output.exists() and fp_path.exists():
        try:
            if fp_path.read_text(encoding="utf-8").strip() == fp:
                print(
                    f"\n  [cache hit] {output.name} matches props — skipping remotion render."
                )
                return
        except OSError:
            pass

    props_file = GITHUB_VIDEO_DIR / "auto_props.json"
    props_file.write_text(json.dumps(params, ensure_ascii=False, indent=2))

    print(f"\n  Rendering {COMPOSITION_ID} → {output} ...")

    subprocess.run(
        [
            "npx", "remotion", "render",
            COMPOSITION_ID,
            str(output.resolve()),
            "--props", str(props_file.resolve()),
        ],
        cwd=GITHUB_VIDEO_DIR,
        check=True,
    )
    fp_path.write_text(fp, encoding="utf-8")
    print(f"\n[Done] {output}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-generate GitHub intro video")
    parser.add_argument("url", help="GitHub repo URL")
    parser.add_argument("--output", default=None, help="Output mp4 path")
    parser.add_argument("--dry-run", action="store_true",
                        help="Detect params and print, skip rendering")
    parser.add_argument("--scroll-distance", type=int, default=2500,
                        help="Pixels to scroll in Scene 3 (default 2500)")
    parser.add_argument("--scroll-duration", type=int, default=25,
                        help="Scene 3 duration in seconds (longer = slower, default 25)")
    parser.add_argument("--bgm", default="/bgm/lofi.mp3",
                        help="Background music under public/ (default /bgm/lofi.mp3)")
    parser.add_argument("--zoom-sfx", default="/sfx/1.wav",
                        help="Zoom sound effect under public/ (default /sfx/1.wav)")
    parser.add_argument("--sfx", default="/sfx/2.wav",
                        help="Underline sound effect under public/ (default /sfx/2.wav)")
    parser.add_argument("--no-audio", action="store_true",
                        help="Disable all audio (BGM + SFX + narration)")
    parser.add_argument("--no-narration", action="store_true",
                        help="Skip TTS narration generation")
    parser.add_argument("--narration-text", default=None,
                        help="Custom narration script (overrides auto-generated)")
    parser.add_argument("--subtitle-text", default=None,
                        help="Custom subtitle text (overrides Whisper transcription)")
    parser.add_argument("--lang", default="zh", choices=["zh", "en"],
                        help="Narration language: zh (Chinese, default) or en (English)")
    parser.add_argument("--transition", default="chromatic",
                        choices=["none", "black", "white", "chromatic", "blur", "zoom", "dissolve", "slide"],
                        help="Scene transition style (default: chromatic)")
    args = parser.parse_args()

    slug = slugify(args.url)
    screenshot_dir = GITHUB_VIDEO_DIR / "public" / "screenshots" / slug
    output = Path(args.output) if args.output else GITHUB_VIDEO_DIR / "out" / f"{slug}.mp4"

    print(f"\n=== Auto Video: {slug} ===")
    print(f"  Screenshots → {screenshot_dir}")

    params = detect_params(args.url, screenshot_dir, args.scroll_distance, args.scroll_duration)
    params["transitionStyle"] = args.transition
    if not args.no_audio:
        params["bgMusic"] = args.bgm
        params["zoomSfx"] = args.zoom_sfx
        params["annotationSfx"] = args.sfx

        if not args.no_narration:
            narration_raw = args.narration_text or build_narration_script(
                slug,
                params.get("repoDescription", ""),
                params.get("starCount", "0"),
                lang=args.lang,
            )
            print(f"\n  Narration script (raw):\n  {narration_raw!r}")
            narration_text = strip_all_metadata_for_subtitles(narration_raw)
            if narration_text != narration_raw:
                print(f"\n  Subtitles reference (metadata stripped):\n  {narration_text!r}")

            narration_path = GITHUB_VIDEO_DIR / "public" / "narration" / f"{slug}.mp3"
            # Auto-enable multi-speaker when the raw script has "Speaker N:" lines
            tts_speaker_configs = (
                DEFAULT_MULTI_SPEAKER_CONFIGS
                if _has_speaker_tags(narration_raw)
                else None
            )
            if tts_speaker_configs:
                print(f"  [i] Multi-speaker mode: {[c['speaker']+'='+c['voice_name'] for c in tts_speaker_configs]}")
            if generate_tts(narration_raw, narration_text, narration_path, lang=args.lang, speaker_configs=tts_speaker_configs):
                params["narration"] = f"/narration/{slug}.mp3"
                subtitle_source = (
                    strip_all_metadata_for_subtitles(args.subtitle_text)
                    if args.subtitle_text
                    else narration_text
                )
                if args.subtitle_text:
                    subtitles = build_subtitle_lines(subtitle_source, lang=args.lang)
                else:
                    subtitles = transcribe_to_subtitles(
                        narration_path, reference_text=narration_text, lang=args.lang
                    )
                params["subtitleLines"] = subtitles or build_subtitle_lines(
                    subtitle_source, lang=args.lang
                )

                if params["subtitleLines"]:
                    if args.lang == "en":
                        # FIX: single stretch only, never compress.
                        # Compressing subtitle cues causes them to run ahead of audio.
                        stretch_subtitle_lines_to_narration_audio(
                            params["subtitleLines"], narration_path, fps=30,
                        )
                    else:
                        # Chinese: redistribute proportionally with dynamic floor
                        # to prevent scale-back compression.
                        redistribute_subtitle_timing(
                            params["subtitleLines"], narration_path,
                            fps=30, lang=args.lang,
                        )

                # FIX: extend scene3 based on actual audio duration, not subtitle lastFrame.
                # subtitle lastFrame may be shorter than audio if cues were compressed.
                audio_duration_sec = _ffprobe_duration_seconds(narration_path) or 0
                if audio_duration_sec > 0:
                    scene1_scene2_secs = 8  # 4s + 4s fixed
                    needed_scene3_secs = max(
                        audio_duration_sec - scene1_scene2_secs + 1,  # +1s buffer
                        args.scroll_duration,
                    )
                    current_scroll_secs = params.get("scrollDurationSec", args.scroll_duration)
                    if needed_scene3_secs > current_scroll_secs:
                        params["scrollDurationSec"] = int(needed_scene3_secs) + 1
                        print(
                            f"  [✓] scrollDurationSec extended to {params['scrollDurationSec']}s "
                            f"to cover narration audio ({audio_duration_sec:.1f}s)"
                        )

    print("\nDetected params:")
    print(json.dumps(params, ensure_ascii=False, indent=2))

    if args.dry_run:
        print("\n[dry-run] Skipped rendering.")
        return

    render_video(params, output)


if __name__ == "__main__":
    main()
