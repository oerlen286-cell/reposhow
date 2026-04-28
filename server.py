import sys
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Force Python's standard output to be line-buffered so prints show up immediately in Uvicorn
sys.stdout.reconfigure(line_buffering=True)

from dotenv import load_dotenv

# Load API keys from .env.local
load_dotenv(dotenv_path=".env.local")

# Import logic from reposhow
import reposhow
import importlib
importlib.reload(reposhow)

print(f"--- Environment Status ---")
print(f"OPENAI_API_KEY: {'[LOADED]' if os.environ.get('OPENAI_API_KEY') else '[MISSING]'}")
print(f"GEMINI_API_KEY: {'[LOADED]' if os.environ.get('GEMINI_API_KEY') else '[MISSING]'}")
print(f"DASHSCOPE_API_KEY: {'[LOADED]' if os.environ.get('DASHSCOPE_API_KEY') else '[MISSING]'}")
print(f"DEBUG: reposhow.GEMINI_TTS_VOICE_EN = {getattr(reposhow, 'GEMINI_TTS_VOICE_EN', 'Not Found')}")
print(f"--------------------------")

# Manually propagate keys to reposhow module in case it was imported before dotenv
reposhow.OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
reposhow.GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
reposhow.DASHSCOPE_API_KEY_ZH = os.environ.get("DASHSCOPE_API_KEY", "")
reposhow.dashscope.api_key = reposhow.DASHSCOPE_API_KEY_ZH

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Path("out").mkdir(exist_ok=True)
app.mount("/out", StaticFiles(directory="out"), name="out")

class LoggerWriter:
    def __init__(self, filename):
        self.file = open(filename, "w", encoding="utf-8")
        self.terminal = sys.stdout
    def write(self, message):
        self.terminal.write(message)
        self.file.write(message)
        self.file.flush()
    def flush(self):
        self.terminal.flush()
        self.file.flush()
    def close(self):
        self.file.close()

class GenerateRequest(BaseModel):
    url: str
    lang: str = "zh"
    scrollDistance: int = 2500
    scrollDuration: int = 25

@app.post("/api/generate")
def generate_metadata(req: GenerateRequest):
    logger = LoggerWriter("out/status.log")
    old_stdout = sys.stdout
    sys.stdout = logger
    try:
        print(f"\n--- NEW GENERATION REQUEST: {req.url} (lang={req.lang}) ---")
        slug = reposhow.slugify(req.url)
        # We will save screenshots to public/screenshots/slug
        # so Vite can serve them directly via /screenshots/slug
        screenshot_dir = Path(reposhow.GITHUB_VIDEO_DIR) / "public" / "screenshots" / slug
        
        # 1. Detect layout params
        params = reposhow.detect_params(req.url, screenshot_dir, req.scrollDistance, req.scrollDuration)
        
        # 2. Add some defaults for the frontend if missing
        if "repoDescription" not in params:
            params["repoDescription"] = "No description provided."
            
        # 3. Generate initial narration script using reposhow
        narration_raw = reposhow.build_narration_script(
            slug, 
            params.get("repoDescription", ""), 
            params.get("starCount", "0"), 
            req.lang,
            params.get("readmeText", "")
        )
        params["scrollSubtitle"] = narration_raw  # Preview the full script in the UI
        
        narration_text = reposhow.strip_all_metadata_for_subtitles(narration_raw)
        # Unique filename per language to avoid overwrites and cache issues
        narration_filename = f"{slug}-{req.lang}.mp3"
        narration_path = Path(reposhow.GITHUB_VIDEO_DIR) / "public" / "narration" / narration_filename
        narration_path.parent.mkdir(parents=True, exist_ok=True)
        
        if req.lang == "en":
            default_speakers = reposhow.DEFAULT_MULTI_SPEAKER_CONFIGS_EN
        else:
            default_speakers = reposhow.DEFAULT_MULTI_SPEAKER_CONFIGS_ZH

        tts_speaker_configs = default_speakers if reposhow._has_speaker_tags(narration_raw) else None
        
        print(f"\n  Generating TTS audio for {req.lang}...")
        if reposhow.generate_tts(narration_raw, narration_text, narration_path, lang=req.lang, speaker_configs=tts_speaker_configs):
            params["narration"] = f"/narration/{narration_filename}"
            subtitle_lines = reposhow.transcribe_to_subtitles(narration_path, narration_text, lang=req.lang)
            if subtitle_lines:
                params["subtitleLines"] = subtitle_lines
            else:
                params["subtitleLines"] = []
                print("  [!] Whisper subtitles failed, using empty subtitles.")
        if "narration" in params and params["narration"]:
            import time
            params["narration"] = f"{params['narration']}?t={int(time.time())}"
            
        params["screenshotDir"] = f"/screenshots/{slug}"

        return {
            "success": True,
            "slug": slug,
            "props": params,
            "narrationScript": narration_raw
        }
    except Exception as e:
        print(f"  [ERROR] /api/generate failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        sys.stdout = old_stdout
        logger.close()

class ExportRequest(BaseModel):
    slug: str
    props: dict

@app.post("/api/export")
def export_video(req: ExportRequest):
    print(f"Export requested for {req.slug}")
    try:
        output_path = Path(reposhow.GITHUB_VIDEO_DIR) / "out" / f"{req.slug}.mp4"
        reposhow.render_video(req.props, output_path)
        return {
            "success": True,
            "videoUrl": f"/out/{req.slug}.mp4",
            "message": "Render completed successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
