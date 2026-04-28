# 🎬 GitHub Video Generator

**English** | [简体中文](README.zh-CN.md)

One-command tool to auto-generate stunning intro videos for any GitHub repository.

**给任意 GitHub 仓库一键生成介绍视频** — 自动截图、AI 旁白、字幕同步、Remotion 渲染。

## Web UI

Left: repo URL, language, transitions, narration, **Load & Parse Repo**, **Export MP4**. Right: Remotion preview with subtitles (`http://localhost:5173`).

![Reposhow Web UI — editor and preview](docs/webui/webui-overview.png)

## ✨ Features

- **One-command generation** — just pass a GitHub URL
- **Auto screenshot** — captures repo page, star count, README via Playwright
- **AI narration script** — GPT (`gpt-4o-mini`) generates engaging voiceover scripts
- **Multi-provider TTS** — Gemini Flash TTS (multi-speaker); Chinese falls back to DashScope; English falls back to OpenAI TTS
- **Smart subtitles** — Whisper transcription + reference-text alignment for precise timing
- **Scene transitions** — chromatic aberration, blur, zoom, dissolve, slide, and more
- **Chinese & English** — full bilingual support for narration and subtitles
- **Remotion rendering** — high-quality MP4 output with zoom animations and sound effects

## 📋 Prerequisites

- **Python** 3.11+
- **Node.js** 18+
- **ffmpeg** (must be on `PATH`; used for PCM→MP3 and subtitle timing)
- **Playwright browsers** — after `pip install -r requirements.txt`, run `playwright install chromium` (or `playwright install` for all browsers)

### API keys (what you actually need)

| Goal | Recommended keys |
|---|---|
| **Web UI + narration + subtitles** | `GEMINI_API_KEY`, `OPENAI_API_KEY` |
| **CLI-only, minimal** | At least one TTS-capable key — typically `GEMINI_API_KEY`; Chinese can use `DASHSCOPE_API_KEY` as fallback when Gemini fails |

See **API Keys** (section below) for the full breakdown.

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/YOUR_USERNAME/reposhow.git
cd reposhow

# Python dependencies
pip install -r requirements.txt
python -m playwright install chromium

# Node.js dependencies (Remotion + Vite web UI)
npm install
```

### 2. Configure environment variables

The FastAPI server (`server.py`) loads **`./.env.local`** (not `.env`). Easiest path:

```bash
cp .env.example .env.local
# Edit .env.local and paste your keys
```

Alternatively, export variables in your shell before starting Python:

```bash
export GEMINI_API_KEY="your-gemini-api-key"
export OPENAI_API_KEY="your-openai-api-key"
export DASHSCOPE_API_KEY="your-dashscope-api-key"
```

### 3A. Web UI (browser preview)

You need **two terminals** — Vite proxies `/api` and `/out` to the backend (`vite.config.ts` → `http://localhost:8000`).

**Terminal 1 — backend**

```bash
python server.py
```

Listen address: `http://127.0.0.1:8000` (OpenAPI docs: `/docs`).

**Terminal 2 — frontend**

```bash
npm run web
```

Open **`http://localhost:5173`**, paste a GitHub repo URL, choose language, then **Load & Parse Repo**. Use **Export MP4** when ready. The preview starts empty until you generate (no default repo baked into the UI).

If the browser shows `http proxy error` / `ECONNREFUSED` on `/api/generate`, the backend on port **8000** is not running — start Terminal 1 first.

### 3B. CLI — generate a video file

```bash
python reposhow.py https://github.com/facebook/react
```

Output: `out/react.mp4`

## 📖 Usage

### CLI — Basic

```bash
# Generate video with default settings (Chinese narration)
python reposhow.py https://github.com/user/repo

# English narration
python reposhow.py https://github.com/user/repo --lang en

# Custom output path
python reposhow.py https://github.com/user/repo --output my_video.mp4

# Dry run (detect params only, skip rendering)
python reposhow.py https://github.com/user/repo --dry-run
```

### CLI — Advanced Options

```bash
# Custom narration text
python reposhow.py https://github.com/user/repo \
  --narration-text "This amazing project..."

# Custom scroll settings
python reposhow.py https://github.com/user/repo \
  --scroll-distance 3000 --scroll-duration 30

# Change transition style
python reposhow.py https://github.com/user/repo \
  --transition blur

# No audio mode
python reposhow.py https://github.com/user/repo --no-audio
```

### Multi-Speaker Narration

Include `Speaker N:` tags in your narration text to enable multi-speaker TTS (Gemini only):

```bash
python reposhow.py https://github.com/user/repo \
  --narration-text "Speaker 1: Welcome to this project!\nSpeaker 2: Let's dive into the details."
```

## ⚙️ CLI Reference

| Argument | Default | Description |
|---|---|---|
| `url` | (required) | GitHub repository URL |
| `--output` | `out/{slug}.mp4` | Output video path |
| `--lang` | `zh` | Language: `zh` or `en` |
| `--dry-run` | — | Print params, skip rendering |
| `--scroll-distance` | `2500` | Pixels to scroll in Scene 3 |
| `--scroll-duration` | `25` | Scene 3 duration in seconds |
| `--bgm` | `/bgm/lofi.mp3` | Background music path |
| `--zoom-sfx` | `/sfx/1.wav` | Zoom sound effect |
| `--sfx` | `/sfx/2.wav` | Underline sound effect |
| `--no-audio` | — | Disable all audio |
| `--no-narration` | — | Skip TTS narration |
| `--narration-text` | (auto) | Custom narration script |
| `--subtitle-text` | (auto) | Custom subtitle text |
| `--transition` | `chromatic` | Transition style |

**Transition styles:** `none`, `black`, `white`, `chromatic`, `blur`, `zoom`, `dissolve`, `slide`

## 🎬 Video Structure

| Time | Scene | Effect |
|---|---|---|
| 0–4s | Repo homepage | Slow zoom + red underline on repo name |
| 4–8s | Star/Fork data | Zoom focus + red underline on star count |
| 8s+ | Full page scroll | Smooth scroll through README with narration |

## 🔑 API Keys

| Provider | Env Variable | Used For |
|---|---|---|
| **Gemini** | `GEMINI_API_KEY` | TTS (primary for both `zh` and `en`; multi-speaker when narration uses `Speaker N:` lines) |
| **OpenAI** | `OPENAI_API_KEY` | GPT narration script, Whisper subtitle alignment, **and English TTS fallback** when Gemini fails |
| **DashScope** | `DASHSCOPE_API_KEY` | **Chinese** TTS fallback when Gemini fails |

**TTS order (current behavior)**

1. Try **Gemini** if `GEMINI_API_KEY` is set.
2. If Gemini fails: **`en`** → OpenAI TTS (needs `OPENAI_API_KEY`); **`zh`** → DashScope (needs `DASHSCOPE_API_KEY`).
3. If no usable TTS succeeds, narration audio is skipped (UI may still show script/subtitles depending on pipeline).

**Script generation:** without `OPENAI_API_KEY`, narration falls back to a built-in template instead of GPT.

## ❓ Troubleshooting

| Symptom | What to do |
|---|---|
| `BrowserType.launch: Executable doesn't exist` / Playwright asks to run `playwright install` | Run `python -m playwright install chromium` (same Python env you use for `server.py` / `reposhow.py`). Restart the backend after installing. |
| Vite logs `http proxy error` / `ECONNREFUSED` for `/api/generate` | Start **`python server.py`** first; Vite only proxies to `localhost:8000`. |
| `pip install requirements.txt` fails | Use **`pip install -r requirements.txt`** (`-r` reads the file). |

## 🏗️ Tech Stack

- **[Remotion](https://remotion.dev/)** — React-based video rendering
- **[Playwright](https://playwright.dev/)** — Browser automation for screenshots
- **Gemini Flash TTS** — Google's multi-speaker text-to-speech
- **DashScope CosyVoice** — Alibaba's multilingual TTS
- **OpenAI Whisper** — Audio transcription for subtitle alignment

## 📄 License

[MIT](LICENSE)
