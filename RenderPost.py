"""
Render Post — one file, one double-click.

Drop RenderPost.exe (or this .py) into a folder of raw D5 renders and run it.
A browser page opens. Renders are enhanced as you watch. Every prompt is
editable in the page; edit it and press Regenerate. Style notes at the top
shape every prompt. The fal key is asked for once and stored in the user's
AppData folder, never in the render folder.

Run with Python for testing:      python RenderPost.py
Demo mode (no API calls, fakes the enhancement so you can test the UI):
                                  python RenderPost.py --demo

Build the single .exe (once, on Windows, or via the GitHub Actions workflow):
    pip install -r requirements.txt
    python -m PyInstaller --onefile --noconsole --name RenderPost --collect-all fal_client --collect-all httpx --collect-all imageio_ffmpeg --add-data "web;web" --icon RenderPost.ico RenderPost.py
    -> dist\\RenderPost.exe   (no Python, no command window; log in %APPDATA%\\RenderPost\\log.txt)
"""

import io
import os
import sys
import json
import time
import shutil
import socket
import threading
import webbrowser
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from prompts import (
    BASE_BRIEF, MOTION_BRIEF, CHARACTER_BRIEF, CHARACTER_T2I, TAKE_CHARACTER,
    MOTION_CHARACTER, ENERGY, ANGLES_BRIEF, MULTISHOT_BRIEF, TAKE_BRIEF,
    CHARACTER_AUTO_PLACEMENT, CHARACTER_NOTE_BOTH, CHARACTER_NOTE_CARD_ONLY,
)

APP_NAME = "RenderPost"
APP_VERSION = "1.8.5"
# Optional: where the exe checks for a newer release. Point this at your GitHub repo's
# latest-release API and the header shows an "Update available" link when a newer tag exists.
# e.g. "https://api.github.com/repos/YOURNAME/renderpost/releases/latest"   ("" = don't check)
UPDATE_URL = "https://api.github.com/repos/achristo714/RenderPost/releases/latest"
DEMO = "--demo" in sys.argv

MODELS = {
    "gpt-image-2.5-flare":    {"label": "GPT Image 2.5 Flare · OpenAI", "endpoint": "openai/gpt-image-2.5/flare/edit", "kind": "gpt", "recommended": True,
                               "hint": "fast tier · strongest at photoreal materials and people · token priced, about $0.01 to $0.40 per image by quality and size"},
    "gpt-image-2.5-sunburst": {"label": "GPT Image 2.5 Sunburst · OpenAI", "endpoint": "openai/gpt-image-2.5/sunburst/edit", "kind": "gpt", "recommended": True,
                               "hint": "precision tier · slower, same price as Flare · for demanding edits where detail must hold"},
    "nano-banana-pro": {"label": "Nano Banana Pro · Google", "endpoint": "fal-ai/nano-banana-pro/edit", "kind": "nano", "recommended": True,
                        "price": 0.15, "mult": {"1K": 1, "2K": 1, "4K": 2},
                        "hint": "deeper reasoning, tends to preserve geometry better · $0.15 per image, 4K double"},
    "nano-banana-2":   {"label": "Nano Banana 2 · Google, fast", "endpoint": "fal-ai/nano-banana-2/edit", "kind": "nano", "recommended": True,
                        "price": 0.08, "mult": {"1K": 1, "2K": 1.5, "4K": 2},
                        "hint": "fastest and cheapest, good for quick passes · $0.08 per image, 2K x1.5, 4K x2"},
}
RES_OPTIONS = {"1K": "1K (about 1024px)", "2K": "2K (about 2048px)", "4K": "4K (about 4096px)"}

VIDEO_R2V = "bytedance/seedance-2.5/reference-to-video"
VIDEO_MODELS = {
    "h3max":    {"label": "H3 Max · fal / MiniMax", "i2v": "minimax/h3-max/image-to-video", "recommended": True,
                 "hint": "top-ranked image-to-video, very fast, cheapest · 480p or 768p, native audio · clips are 5s or longer",
                 "res": {"480p": "480p · iterate here", "768p": "768p · final"}, "min_duration": 5,
                 "price": {"480p": 0.05, "768p": 0.08}},            # per second, fal Sep 2026 (regular rate)
    "h3turbo":  {"label": "H3 Max Turbo · fal / MiniMax", "i2v": "minimax/h3-max-turbo/image-to-video", "recommended": False,
                 "hint": "faster, lighter H3 · same controls · pricing not verified, check fal before a big batch",
                 "res": {"480p": "480p · iterate here", "768p": "768p · final"}, "min_duration": 5,
                 "price": {"480p": 0.05, "768p": 0.08}},
    "kling":    {"label": "Kling 3.0 Pro · Kuaishou", "i2v": "fal-ai/kling-video/o3/pro/image-to-video", "recommended": True,
                 "hint": "cinematic, ~1080p output, native audio, filter is generally tolerant of people in frame",
                 "res": None,
                 "price": {"audio": 0.14, "silent": 0.112}},        # per second, fal Aug 2026
    "seedance": {"label": "Seedance 2.5 · ByteDance", "i2v": "bytedance/seedance-2.5/image-to-video", "recommended": True,
                 "hint": "strong motion and the only model for single takes · strict filter: refuses frames with realistic people",
                 "res": {"480p": "480p · iterate here", "720p": "720p · final"},
                 "price": {"480p": 0.2205, "720p": 0.4730}},        # per second, fal Aug 2026
}
VIDEO_RES = {"480p": "480p · iterate here", "720p": "720p · final"}   # take mode (Seedance)
# Optional: a JSON at this URL can add or update models without rebuilding the exe.
# Shape: {"image": {<key>: {...same fields as MODELS...}}, "video": {<key>: {...same fields as VIDEO_MODELS...}}}
MODEL_CATALOG_URL = "https://raw.githubusercontent.com/achristo714/RenderPost/main/models.json"   # the app setting "catalog_url" overrides it
VIDEO_DURATIONS = {"4": "4 s", "5": "5 s", "6": "6 s", "8": "8 s", "10": "10 s", "12": "12 s", "15": "15 s"}
TAKE_DURATIONS = {"8": "8 s", "10": "10 s", "15": "15 s", "20": "20 s", "30": "30 s"}
MUSIC_EXT = {".mp3", ".wav", ".m4a", ".aac"}

VARIATION_OPTIONS = {"1": "1 per image", "2": "2 per image", "4": "4 per image"}
ANGLE_OPTIONS = {"4": "4 angles", "6": "6 angles", "9": "9 angles"}
VISION_ENDPOINT = "openrouter/router/vision"
VISION_MODELS = ["openai/gpt-5.4", "google/gemini-2.5-flash"]
EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
OUTPUT_DIRNAME = "enhanced"
MAX_WORKERS = 3
MAX_UPLOAD_EDGE = 3840
FAL_MAX_EDGE, FAL_MIN_PIXELS, FAL_MAX_PIXELS = 3840, 655_360, 8_294_400

SIZE_OPTIONS = {"1536": "Standard (1.5K)", "2048": "2K", "3072": "3K", "3840": "4K"}
QUALITY_OPTIONS = {"low": "Low (fast, cheap)", "medium": "Medium", "high": "High", "xhigh": "Extra high", "max": "Max (slow, costly)"}

DEFAULT_CONFIG = {"fal_key": "", "model": "gpt-image-2.5-flare", "quality": "medium", "long_edge": "3072",
                  "resolution": "2K", "variations": "1", "angles": "6", "style_notes": "", "review_first": True,
                  "video_model": "h3max", "video_res": "480p", "show_all_models": False, "video_duration": "5", "take_duration": "15", "video_audio": True,
                  "crossfade": "0.6", "motion_notes": "", "shots": "1", "video_frames": "[]", "energy": "calm",
                  "character_note": "", "character_desc": "", "take_character": False}


# ---------------------------------------------------------------- config
def config_dir():
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


FOLDER_FILE_LOCK = threading.Lock()   # renderpost.json is read-modify-written from worker threads and the UI; serialize it
FOLDER_KEYS = ("style_notes", "motion_notes", "video_frames", "character_note", "character_desc", "take_character", "spend")
LEGACY_MODELS = {"gpt-image-2": "gpt-image-2.5-flare"}     # saved config ids from older builds -> current id
# GPT Image 2.5 is token priced. Estimate per image by quality and output long edge, from fal's published
# 16:9 price rows (Sep 2026): 1920x1080, 2560x1440, midpoint to 3840x2160, 3840x2160. Flare and Sunburst cost the same.
GPT_IMAGE_EST = {
    "low":    {"1536": 0.0044, "2048": 0.0062, "3072": 0.0086, "3840": 0.0111},
    "medium": {"1536": 0.0103, "2048": 0.0143, "3072": 0.0201, "3840": 0.0260},
    "high":   {"1536": 0.0396, "2048": 0.0553, "3072": 0.0777, "3840": 0.1001},
    "xhigh":  {"1536": 0.0704, "2048": 0.0983, "3072": 0.1381, "3840": 0.1779},
    "max":    {"1536": 0.1584, "2048": 0.2211, "3072": 0.3107, "3840": 0.4003},
}


def folder_settings_path():
    return STATE.out_dir / "renderpost.json" if STATE.out_dir else None


def load_config():
    p = config_dir() / "config.json"
    cfg = dict(DEFAULT_CONFIG)
    if p.exists():
        try:
            cfg.update(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    cfg["model"] = LEGACY_MODELS.get(cfg.get("model"), cfg.get("model"))
    for k in FOLDER_KEYS:
        cfg[k] = "" if k != "spend" else 0
    fp = folder_settings_path()
    if fp and fp.exists():
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
            for k in FOLDER_KEYS:
                cfg[k] = d.get(k, 0) if k == "spend" else str(d.get(k, ""))
        except Exception:
            pass
    return cfg


def save_config(cfg):
    user = {k: v for k, v in cfg.items() if k not in FOLDER_KEYS}
    (config_dir() / "config.json").write_text(json.dumps(user, indent=2), encoding="utf-8")
    fp = folder_settings_path()
    if fp:
        with FOLDER_FILE_LOCK:
            keep = {}
            if fp.exists():
                try:
                    keep = json.loads(fp.read_text(encoding="utf-8"))
                except Exception:
                    pass
            keep.update({k: cfg.get(k, "") for k in FOLDER_KEYS if k != "spend"})
            fp.write_text(json.dumps(keep, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- folder
def app_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_path(*parts):
    """Locate a bundled resource (the web/ folder) whether run from source or frozen by PyInstaller."""
    base = Path(getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent)
    return base.joinpath(*parts)


def find_images(folder):
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in EXTENSIONS and not p.name.startswith(".")
    )


def pick_folder():
    here = app_dir()
    if find_images(here):
        return here
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        chosen = filedialog.askdirectory(title="Choose the folder with your renders")
        root.destroy()
        if chosen:
            return Path(chosen)
    except Exception:
        pass
    return here


# ---------------------------------------------------------------- image helpers
def prep_image(path):
    from PIL import Image
    img = Image.open(path)
    orig = img.size
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")
    w, h = img.size
    s = MAX_UPLOAD_EDGE / max(w, h)
    if s < 1:
        img = img.resize((int(w * s), int(h * s)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), orig


def output_size(src_w, src_h, long_edge):
    long_edge = min(int(long_edge), FAL_MAX_EDGE)
    if src_w >= src_h:
        w, h = long_edge, long_edge * src_h / src_w
    else:
        h, w = long_edge, long_edge * src_w / src_h
    px = w * h
    if px > FAL_MAX_PIXELS:
        s = (FAL_MAX_PIXELS / px) ** 0.5; w, h = w * s, h * s
    elif px < FAL_MIN_PIXELS:
        s = (FAL_MIN_PIXELS / px) ** 0.5; w, h = w * s, h * s
    snap = lambda v: max(16, int(v // 16) * 16)
    return {"width": snap(w), "height": snap(h)}


def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def run_ffmpeg(args):
    import subprocess
    exe = ffmpeg_exe()
    if not exe:
        raise RuntimeError("ffmpeg is not available in this build, so clips can't be stitched.")
    r = subprocess.run([exe, "-y", "-hide_banner", "-loglevel", "error", *args],
                       capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg: " + (r.stderr.strip().splitlines() or ["failed"])[-1])


def make_demo_video(src, out_path, seconds=3):
    """Demo mode only: a slow push-in on the still, so the stitching path gets exercised."""
    if not src:
        raise RuntimeError("demo source missing")
    run_ffmpeg(["-loop", "1", "-i", str(src), "-t", str(seconds),
                "-vf", f"scale=1280:-2,zoompan=z='min(zoom+0.0015,1.15)':d={seconds*24}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1280x720:fps=24,format=yuv420p",
                "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-an", str(out_path)])


def probe_video(path):
    """(width, height, duration_seconds, has_audio) via ffmpeg's own output; None if unreadable."""
    import subprocess, re
    exe = ffmpeg_exe()
    if not exe:
        return None
    r = subprocess.run([exe, "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    d = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else None
    wh = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", r.stderr)
    w, h = (int(wh.group(1)), int(wh.group(2))) if wh else (None, None)
    return (w, h, d, "Audio:" in r.stderr)


def stitch_clips(files, out_path, crossfade=0.6, music=None, music_start=0.0):
    """Concatenate clips with crossfades (video and audio), optional music bed.
    Output size follows the largest clip (capped at 1920 wide) so mixed batches don't downsample the good ones."""
    exe = ffmpeg_exe()
    durs, has_audio, dims = [], [], []
    for f in files:
        pr = probe_video(f) or (None, None, None, False)
        w, h, d, a = pr
        durs.append(d or 5.0); has_audio.append(a); dims.append((w, h))
    best = max((d for d in dims if d[0]), key=lambda d: d[0] * d[1], default=(1280, 720))
    W, H = best
    if W > 1920:
        H = int(H * 1920 / W); W = 1920
    W, H = W - W % 2, H - H % 2
    n = len(files)
    cf = max(0.0, min(float(crossfade), min(durs) / 2 - 0.05)) if n > 1 else 0.0
    args = []
    for f in files:
        args += ["-i", str(f)]
    filt = []
    # normalise every input so xfade accepts them
    for i in range(n):
        filt.append(f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24,format=yuv420p[v{i}]")
        filt.append((f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo[a{i}]") if has_audio[i]
                    else f"anullsrc=r=48000:cl=stereo,atrim=0:{durs[i]},asetpts=PTS-STARTPTS[a{i}]")
    vprev, aprev, offset = "v0", "a0", 0.0
    for i in range(1, n):
        offset += durs[i - 1] - cf
        filt.append(f"[{vprev}][v{i}]xfade=transition=fade:duration={cf}:offset={offset:.3f}[vx{i}]")
        filt.append(f"[{aprev}][a{i}]acrossfade=d={max(cf, 0.01)}:c1=tri:c2=tri[ax{i}]")
        vprev, aprev = f"vx{i}", f"ax{i}"
    total = sum(durs) - cf * (n - 1)
    amap = f"[{aprev}]"
    if music:
        args += ["-ss", f"{max(0.0, float(music_start)):.3f}", "-i", str(music)]
        filt.append(f"[{n}:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:{total:.3f},afade=t=out:st={max(0, total-1.5):.3f}:d=1.5,volume=0.8[m]")
        filt.append(f"[{aprev}]volume=0.5[ad];[ad][m]amix=inputs=2:duration=first:dropout_transition=0[amix]")
        amap = "[amix]"
    run_ffmpeg([*args, "-filter_complex", ";".join(filt), "-map", f"[{vprev}]", "-map", amap,
                "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", f"{total:.3f}", str(out_path)])
    return total


def make_compare(raw_path, out_path, folder):
    """Side-by-side before/after JPG for sharing. Raw is scaled to the output's height."""
    from PIL import Image
    folder.mkdir(exist_ok=True)
    a = Image.open(raw_path).convert("RGB"); b = Image.open(out_path).convert("RGB")
    h = b.height
    a = a.resize((int(a.width * h / a.height), h), Image.LANCZOS)
    gap = max(4, h // 200)
    sheet = Image.new("RGB", (a.width + gap + b.width, h), (19, 18, 17))
    sheet.paste(a, (0, 0)); sheet.paste(b, (a.width + gap, 0))
    if sheet.width > 4096:
        sheet = sheet.resize((4096, int(sheet.height * 4096 / sheet.width)), Image.LANCZOS)
    out = folder / (Path(out_path).stem + "_before-after.jpg")
    sheet.save(out, "JPEG", quality=92)
    return out


def image_dims(path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            return list(im.size)
    except Exception:
        return None


# ---------------------------------------------------------------- fal calls
def split_shots(prompt):
    """Split a 'Shot 1: ... / Shot 2: ...' prompt into per-shot prompts. Freeform text returns itself."""
    import re
    parts = re.split(r"(?:^|\n|\s)(?=Shot\s*\d+\s*:)", prompt.strip())
    shots = [re.sub(r"^Shot\s*\d+\s*:\s*", "", x).strip() for x in parts if x.strip()]
    return shots if len(shots) > 1 else [prompt.strip()]


def friendly(e):
    m = str(e)
    if "content_policy_violation" in m or "likenesses of real people" in m:
        return ("Seedance refused the input images: its content filter flags realistic people. "
                "Use versions without people (add 'no people' to style notes and re-enhance), "
                "or keep people small and distant.")
    if "content_policy" in m or "policy_violation" in m:
        return "The model's content filter refused this request. Reword the prompt or use different images."
    if len(m) > 400:
        m = m[:400] + " …"
    if "401" in m:
        return "fal rejected your key. Open Change key and paste a current one."
    if "402" in m or "insufficient" in m.lower() or "balance" in m.lower():
        return "fal says your account is out of credit."
    if "429" in m:
        return "fal is rate limiting this account. Wait a minute and retry."
    if "403" in m:
        return "fal refused this request (403). The model may need to be enabled on your account."
    if "timed out" in m.lower() or "timeout" in m.lower():
        return "The request timed out. Retry; large images can take a few minutes."
    return m


def with_retry(fn, attempts=3):
    delay = 4
    for i in range(attempts):
        try:
            return fn()
        except Cancelled:
            raise
        except Exception as e:
            if i == attempts - 1 or "401" in str(e) or "402" in str(e):
                raise
            time.sleep(delay); delay *= 2


def character_guidance(global_note, card_note):
    """Combine the project-wide character note with a card's own placement/pose text."""
    g, c = (global_note or "").strip(), (card_note or "").strip()
    if g and c:
        return CHARACTER_NOTE_BOTH.format(**{"global": g, "card": c})
    if g:
        return g
    if c:
        return CHARACTER_NOTE_CARD_ONLY.format(card=c)
    return CHARACTER_AUTO_PLACEMENT


class Fal:
    def __init__(self, key):
        import fal_client
        self.mod = fal_client
        self.c = fal_client.SyncClient(key=key.strip(), default_timeout=300)

    def check(self):
        """Cheapest possible call that needs auth: a 2-byte upload."""
        self.c.upload(b"ok", "text/plain", file_name="check.txt")

    def upload(self, png_bytes, name):
        return with_retry(lambda: self.c.upload(png_bytes, "image/png", file_name=name))

    def write_angles(self, image_url, n, notes="", character_url=None):
        brief = ANGLES_BRIEF.format(n=n)
        if character_url:
            brief += "\n\nA SECOND input image shows one specific person. In roughly half of the angles, include that exact person once, naturally placed, as 'the person shown in the second input image'."
        if notes.strip():
            brief += "\n\nThe client also wants:\n" + notes.strip()
        last = None
        for model in VISION_MODELS:
            try:
                def call():
                    r = self.c.subscribe(VISION_ENDPOINT, arguments={
                        "image_urls": [image_url] + ([character_url] if character_url else []), "system_prompt": brief,
                        "prompt": f"Write the {n} angle prompts for this image.",
                        "model": model, "temperature": 0.8, "max_tokens": 900})
                    lines = [l.strip().lstrip("-•0123456789. ").strip() for l in (r.get("output") or "").splitlines()]
                    lines = [l for l in lines if len(l) > 20]
                    if not lines:
                        raise RuntimeError("empty")
                    return lines[:n]
                return with_retry(call, attempts=2)
            except Exception as e:
                last = e
        raise RuntimeError(f"Could not write angle prompts ({last})")

    def write_motion(self, image_urls, notes, take=False, shots=1, energy="calm", character=False):
        brief = TAKE_BRIEF if take else (MULTISHOT_BRIEF.format(shots=shots) if int(shots) > 1 else MOTION_BRIEF)
        brief += "\n\n" + ENERGY.get(energy, ENERGY["calm"])
        if character:
            brief += "\n\n" + (TAKE_CHARACTER.format(n=len(image_urls)) if take else MOTION_CHARACTER)
        if notes.strip():
            brief += "\n\nThe client also wants:\n" + notes.strip() + "\nFold these in."
        ask = ("Write the take prompt for these stills, in order." if take else
               "Write the motion prompt for this still.")
        last = None
        for model in VISION_MODELS:
            try:
                def call():
                    r = self.c.subscribe(VISION_ENDPOINT, arguments={
                        "image_urls": image_urls, "system_prompt": brief, "prompt": ask,
                        "model": model, "temperature": 0.7, "max_tokens": 400})
                    t = (r.get("output") or "").strip().strip('"')
                    if not t:
                        raise RuntimeError("empty prompt")
                    return t
                return with_retry(call, attempts=2)
            except Exception as e:
                last = e
        raise RuntimeError(f"Could not write a motion prompt ({last})")

    def video(self, prompt, image_urls, cfg, take, cancelled=lambda: False):
        audio = bool(cfg.get("video_audio", True))
        if take:
            args = {"prompt": prompt, "image_urls": image_urls, "resolution": cfg["video_res"],
                    "duration": str(cfg["take_duration"]), "aspect_ratio": "auto",
                    "generate_audio": audio}
            endpoint = VIDEO_R2V
        elif cfg.get("video_model") not in ("kling", "seedance") and cfg.get("video_model") in VIDEO_MODELS:
            # H3 family: integer duration with a 5s floor, resolution spelled 480P / 768P
            m = VIDEO_MODELS[cfg["video_model"]]
            res = cfg["video_res"] if (m.get("res") and cfg["video_res"] in m["res"]) else (list(m["res"])[-1] if m.get("res") else None)
            dur = max(int(m.get("min_duration", 1)), int(cfg["video_duration"]))
            args = {"prompt": prompt, "image_url": image_urls[0], "duration": dur}
            if res:
                args["resolution"] = res.upper()
            endpoint = m["i2v"]
        elif cfg.get("video_model") == "kling":
            args = {"image_url": image_urls[0], "duration": str(cfg["video_duration"]),
                    "generate_audio": audio}
            shots = split_shots(prompt)
            if len(shots) > 1:
                # Kling's documented multi-shot storyboard: one prompt+duration per shot, total <= 15s
                total = int(cfg["video_duration"])
                per = max(3, total // len(shots))
                durs = [per] * len(shots)
                durs[-1] = max(3, total - per * (len(shots) - 1))
                args["multi_prompt"] = [{"prompt": sp, "duration": str(d)} for sp, d in zip(shots, durs)]
                args["shot_type"] = "customize"
                args["duration"] = str(sum(durs))
            else:
                args["prompt"] = prompt
            endpoint = VIDEO_MODELS["kling"]["i2v"]
        else:
            args = {"prompt": prompt, "image_url": image_urls[0], "resolution": cfg["video_res"],
                    "duration": str(cfg["video_duration"]), "aspect_ratio": "auto",
                    "generate_audio": audio}
            endpoint = VIDEO_MODELS["seedance"]["i2v"]

        def call():
            handle = self.c.submit(endpoint, arguments=args)
            while True:
                if cancelled():
                    try:
                        handle.cancel()
                    except Exception:
                        pass
                    raise Cancelled()
                if isinstance(handle.status(), self.mod.Completed):
                    break
                time.sleep(2.0)
            r = handle.get()
            url = (r.get("video") or {}).get("url")
            if not url:
                raise RuntimeError("The model returned no video. It may have refused the prompt; try rewording it.")
            return url
        return with_retry(call, attempts=2)

    def generate_character(self, desc):
        args = {"prompt": CHARACTER_T2I.format(desc=desc.strip()), "aspect_ratio": "3:4",
                "resolution": "1K", "num_images": 1, "output_format": "png"}
        def call():
            r = self.c.subscribe("fal-ai/nano-banana-pro", arguments=args)
            urls = [im["url"] for im in r.get("images", [])]
            if not urls:
                raise RuntimeError("No image came back. Try a plainer description.")
            return urls[0]
        return with_retry(call, attempts=2)

    def write_prompt(self, image_url, style_notes, previous=None, character_url=None, character_note=""):
        brief = BASE_BRIEF
        if character_url:
            brief += "\n\n" + CHARACTER_BRIEF.format(note=character_note)
        if style_notes.strip():
            brief += ("\n\nThe client also wants, for every image in this set:\n" + style_notes.strip()
                      + "\nFold these into the prompt. They override the mood choice above.")
        ask = "Write the enhancement prompt for this render."
        if previous:
            ask = ("Here is the prompt used last time for this render:\n\n" + previous.strip() +
                   "\n\nRevise it so it follows the client's current notes. Keep the parts that are still "
                   "consistent with the notes and with the image. Output only the revised prompt.")
        last = None
        for model in VISION_MODELS:
            try:
                def call():
                    r = self.c.subscribe(VISION_ENDPOINT, arguments={
                        "image_urls": [image_url] + ([character_url] if character_url else []), "system_prompt": brief,
                        "prompt": ask,
                        "model": model, "temperature": 0.7, "max_tokens": 500})
                    t = (r.get("output") or "").strip().strip('"')
                    if not t:
                        raise RuntimeError("empty prompt")
                    return t
                return with_retry(call, attempts=2)
            except Exception as e:
                last = e
        raise RuntimeError(f"Could not write a prompt ({last})")

    def edit(self, image_url, prompt, cfg, src_dims, cancelled=lambda: False, extra_urls=()):
        m = MODELS[cfg["model"]]
        n = int(cfg.get("variations", "1"))
        urls = [image_url] + list(extra_urls)
        if m["kind"] == "gpt":
            args = {"prompt": prompt, "image_urls": urls, "image_size": output_size(*src_dims, cfg["long_edge"]),
                    "quality": cfg["quality"], "num_images": n, "output_format": "png"}
        else:
            args = {"prompt": prompt, "image_urls": urls, "aspect_ratio": "auto",
                    "resolution": cfg["resolution"], "num_images": n, "output_format": "png"}

        def call():
            handle = self.c.submit(m["endpoint"], arguments=args)
            while True:
                if cancelled():
                    try:
                        handle.cancel()
                    except Exception:
                        pass
                    raise Cancelled()
                st = handle.status()
                if isinstance(st, self.mod.Completed):
                    break
                time.sleep(1.0)
            r = handle.get()
            urls = [im["url"] for im in r.get("images", [])]
            if not urls:
                raise RuntimeError("The model returned no image. It may have refused the prompt; try rewording it.")
            return urls
        return with_retry(call)

    @staticmethod
    def download(url, out_path):
        with urllib.request.urlopen(url, timeout=300) as resp:
            out_path.write_bytes(resp.read())


class Cancelled(Exception):
    pass


class DemoFal:
    """Fakes the API so the UI can be tested without spending credits."""
    def upload(self, png_bytes, name=None, **kw):
        time.sleep(0.4); return "demo://" + str(name or kw.get("file_name") or "x")

    def write_angles(self, image_url, n, notes="", character_url=None):
        time.sleep(1.0)
        views = ["wide from the entrance", "reverse angle looking back", "low three-quarter across the furniture",
                 "elevated corner view", "tight detail of the best material", "through the opening into the next space",
                 "from the far wall", "centred symmetrical", "close on the window"]
        return [f"Same space as the reference image, identical architecture, materials, furniture, lighting and time of day. Camera {v}." for v in views[:int(n)]]

    def write_motion(self, image_urls, notes, take=False, shots=1, energy="calm", character=False):
        time.sleep(1.0)
        if int(shots) > 1 and not take:
            return "\n".join(f"Shot {i+1}: slow {'push-in' if i%2==0 else 'dolly'} on the space, architecture unchanged." for i in range(int(shots)))
        if take:
            return " ".join(f"Glide through the space in [Image{i+1}]," for i in range(len(image_urls))) + " one continuous steadicam take, architecture unchanged." + (f" Client notes: {notes.strip()}" if notes.strip() else "")
        return "Slow push-in toward the far wall, curtains stirring, two people talking at a table, warm lamps flicker softly. Architecture, materials and lighting stay exactly as in the still." + (f" Client notes: {notes.strip()}" if notes.strip() else "")

    def video(self, prompt, image_urls, cfg, take, cancelled=lambda: False):
        for _ in range(30):
            if cancelled():
                raise Cancelled()
            time.sleep(0.1)
        return "demo-video://" + image_urls[0]

    def generate_character(self, desc):
        time.sleep(0.8); return "demo-char://" + desc[:20]

    def write_prompt(self, image_url, style_notes, previous=None, character_url=None, character_note=""):
        time.sleep(1.2)
        if character_url:
            return "Keep the geometry exactly as rendered. The person shown in the second input image sits at the window table, relaxed, looking out. Warm late light, deeper contrast." + (f" Client notes: {style_notes.strip()}" if style_notes.strip() else "")
        if previous:
            return previous.split(" Client notes:")[0] + (f" Client notes: {style_notes.strip()}" if style_notes.strip() else "")
        return ("Keep the geometry, facade, materials, camera and composition exactly as rendered. "
                "Warm late-afternoon light from camera left, long soft shadows, light atmospheric haze "
                "in the distance, photoreal vegetation, natural pedestrians, deeper contrast in the glazing."
                + (f" Client notes: {style_notes.strip()}" if style_notes.strip() else ""))

    def edit(self, image_url, prompt, cfg, src_dims, cancelled=lambda: False, extra_urls=()):
        for _ in range(20):
            if cancelled():
                raise Cancelled()
            time.sleep(0.15)
        return [f"{image_url}#{i}" for i in range(int(cfg.get("variations", "1")))]

    def download(self, url, out_path):
        if url.startswith("demo-char://"):
            from PIL import Image, ImageDraw
            im = Image.new("RGB", (768, 1024), (200, 198, 194)); d = ImageDraw.Draw(im)
            d.ellipse((284, 180, 484, 380), fill=(120, 90, 70)); d.rounded_rectangle((250, 400, 520, 900), 60, fill=(60, 70, 90))
            im.save(out_path, "PNG"); return
        if url.startswith("demo-video://"):
            src = STATE.demo_sources.get(url[len("demo-video://"):])
            make_demo_video(src, out_path)
            return
        from PIL import Image, ImageEnhance
        src = STATE.demo_sources.get(url.split("#")[0])
        i = int(url.split("#")[-1])
        img = Image.open(src).convert("RGB") if src else Image.new("RGB", (1536, 864), (60, 55, 50))
        img.thumbnail((1536, 1536))
        img = ImageEnhance.Contrast(ImageEnhance.Color(img).enhance(1.2 + 0.3 * i)).enhance(1.15)
        img.save(out_path, "PNG")


# ---------------------------------------------------------------- state + jobs
class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.last_seen = time.time()
        self.seen_browser = False
        self.bye_at = None          # set when the page says it's closing; cleared by the next poll
        self.music_dirty = False
        self.folder = None
        self.out_dir = None
        self.items = {}          # name -> dict
        self.order = []
        self.pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        self.active = 0
        self.demo_sources = {}
        self.fal = None
        self.video_dir = None
        self.clips = []            # list of dicts, see new_clip()
        self.clip_urls = {}        # (name,file) -> fal url of the uploaded enhanced image

    def scan(self):
        meta = {}
        pj = self.out_dir / "prompts.json"
        if pj.exists():
            try:
                meta = json.loads(pj.read_text(encoding="utf-8"))
            except Exception:
                pass
        with self.lock:
            for p in find_images(self.folder):
                name = p.stem
                if name in self.items:
                    continue
                m = meta.get(name)
                if isinstance(m, str):            # old format: just a prompt
                    m = {"draft": m, "versions": []}
                m = m or {"draft": "", "versions": []}
                # versions on disk win over the json (files may have been deleted by hand)
                versions = []
                legacy = self.out_dir / f"{name}_enhanced.png"
                files = sorted(self.out_dir.glob(f"{name}_v[0-9][0-9].png")) + sorted(self.out_dir.glob(f"{name}_a[0-9][0-9].png"))
                if legacy.exists() and not files:
                    legacy.rename(self.out_dir / f"{name}_v01.png")
                    files = [self.out_dir / f"{name}_v01.png"]
                known = {v["file"]: v for v in m.get("versions", []) if isinstance(v, dict)}
                for f in files:
                    v = known.get(f.name, {})
                    versions.append({"file": f.name, "prompt": v.get("prompt", ""), "out_size": image_dims(f),
                                     "seconds": v.get("seconds"), "quality": v.get("quality"), "model": v.get("model"),
                                     "made": v.get("made"), "pick": bool(v.get("pick")),
                                     "angle": v.get("angle") or ("_a" in f.stem and f.stem.rsplit("_a", 1)[1].isdigit())})
                draft = m.get("draft", "") or (versions[-1]["prompt"] if versions else "")
                self.items[name] = {
                    "name": name, "source_file": p.name, "versions": versions,
                    "prompt": draft, "notes_used": m.get("notes_used", ""), "src_size": image_dims(p),
                    "status": "done" if versions else "pending", "step": "", "error": None, "url": None,
                    "character_on": bool(m.get("character_on", False)), "character_note": m.get("character_note", "") or "",
                }
                self.order.append(name)

    # ---- video
    def load_clips(self):
        cj = self.video_dir / "clips.json"
        if cj.exists():
            try:
                self.clips = [c for c in json.loads(cj.read_text(encoding="utf-8"))
                              if c.get("status") != "done" or (self.video_dir / c["file"]).exists()]
            except Exception:
                self.clips = []
        for c in self.clips:
            if c.get("status") in ("queued", "working"):
                c["status"] = "ready" if c.get("prompt") else "failed"

    def save_clips(self):
        with self.lock:
            data = [{k: v for k, v in c.items() if not k.startswith("_")} for c in self.clips]
        self.video_dir.mkdir(exist_ok=True)
        (self.video_dir / "clips.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    def new_clip(self, kind, sources, cfg):
        cid = f"{int(time.time()*1000)}{len(self.clips):02d}"
        c = {"id": cid, "kind": kind, "sources": sources, "prompt": "", "file": None,
             "status": "queued", "step": "waiting", "error": None, "seconds": None, "made": None,
             "resolution": ("1080p" if cfg.get("video_model") == "kling" else cfg["video_res"]) if kind == "clip" else cfg["video_res"],
             "vmodel": None if kind == "reel" else ("seedance" if kind == "take" else cfg.get("video_model", "seedance")),
             "duration": cfg["take_duration"] if kind == "take" else cfg["video_duration"],
             "shots": cfg.get("shots", "1") if kind == "clip" else None}
        with self.lock:
            self.clips.append(c)
        return c

    def clip(self, cid):
        return next((c for c in self.clips if c["id"] == cid), None)

    def clip_set(self, cid, **kw):
        with self.lock:
            c = self.clip(cid)
            if c:
                c.update(kw)

    def character_path(self):
        p = self.out_dir / "character.png"
        return p if p.exists() else None

    def character_url(self):
        p = self.character_path()
        if not p:
            return None
        key = ("__character__", p.name + str(p.stat().st_mtime))
        if key not in self.clip_urls:
            self.clip_urls[key] = self.fal.upload(p.read_bytes(), "character.png")
            if DEMO:
                self.demo_sources[self.clip_urls[key]] = p
        return self.clip_urls[key]

    def upload_source(self, src):
        key = (src["name"], src["file"])
        if key in self.clip_urls:
            return self.clip_urls[key]
        it = self.items.get(src["name"], {})
        path = (self.folder if src["file"] == it.get("source_file") else self.out_dir) / src["file"]
        url = self.fal.upload(path.read_bytes(), src["file"])
        if DEMO:
            self.demo_sources[url] = path
        self.clip_urls[key] = url
        return url

    def _clip_job(self, cid, stage, forced_prompt, cfg):
        c = self.clip(cid)
        cancelled = lambda: bool(c.get("_cancel"))
        t0 = time.time()
        try:
            with self.lock:
                self.active += 1
            self.clip_set(cid, status="working", step="uploading")
            urls = [self.upload_source(src) for src in c["sources"]]
            take = c["kind"] == "take"
            with_char = False
            if take and cfg.get("take_character") and self.character_path():
                urls = urls + [self.character_url()]; with_char = True
            elif not take:
                src0 = c["sources"][0]; it0 = self.items.get(src0["name"], {})
                with_char = any(v.get("character") for v in it0.get("versions", []) if v["file"] == src0["file"])
            if cancelled():
                raise Cancelled()
            if stage in ("prompt", "full") and not forced_prompt:
                self.clip_set(cid, step="writing motion prompt")
                prompt = self.fal.write_motion(urls, cfg.get("motion_notes", ""), take, cfg.get("shots", "1"), cfg.get("energy", "calm"), with_char)
                self.clip_set(cid, prompt=prompt)
                self.save_clips()
            else:
                prompt = forced_prompt or c["prompt"]
            if stage == "prompt":
                self.clip_set(cid, status="ready", step="")
                return
            if cancelled():
                raise Cancelled()
            self.clip_set(cid, prompt=prompt, step=f"generating {c['duration']}s" + ("" if c.get("vmodel") == "kling" else f" at {c['resolution']}"),
                          duration=cfg["take_duration"] if take else cfg["video_duration"])
            url = self.fal.video(prompt, urls, cfg, take, cancelled)
            self.clip_set(cid, step="downloading")
            self.video_dir.mkdir(exist_ok=True)
            base = "take" if take else Path(c["sources"][0]["file"]).stem
            n = 1
            while (self.video_dir / f"{base}_clip{n:02d}.mp4").exists():
                n += 1
            out = self.video_dir / f"{base}_clip{n:02d}.mp4"
            self.fal.download(url, out)
            pr = probe_video(out)
            extra = {}
            if pr and pr[1]:
                extra = {"out_size": [pr[0], pr[1]], "resolution": f"{pr[1]}p", "duration": str(round(pr[2] or float(c["duration"]), 1))}
            self.clip_set(cid, status="done", step="", file=out.name, seconds=round(time.time() - t0),
                          made=time.strftime("%Y-%m-%d %H:%M"), **extra)
            self.save_clips()
            self.add_spend(self.video_cost(self.clip(cid), cfg))
        except Cancelled:
            self.clip_set(cid, status="ready" if c.get("prompt") else "failed", step="", error=None, _cancel=False)
        except Exception as e:
            self.clip_set(cid, status="failed", step="", error=friendly(e))
            self.save_clips()
        finally:
            with self.lock:
                self.active -= 1

    def _angles_job(self, name, file, cfg):
        """From one finished version, make N new stills of the same space from new camera positions."""
        it = self.items[name]
        n = int(cfg.get("angles", "6"))
        cancelled = lambda: bool(it.get("_cancel"))
        t0 = time.time()
        try:
            with self.lock:
                self.active += 1
            self.set(name, status="working", step="uploading")
            src_path = self.out_dir / file
            url = self.upload_source({"name": name, "file": file})
            if cancelled():
                raise Cancelled()
            char = self.character_url() if it.get("character_on") else None
            self.set(name, step=f"planning {n} angles")
            prompts = self.fal.write_angles(url, n, cfg.get("style_notes", ""), char)
            dims = image_dims(src_path) or it["src_size"] or [1920, 1080]
            one = dict(cfg, variations="1")
            made = []
            for i, ptxt in enumerate(prompts, 1):
                if cancelled():
                    raise Cancelled()
                self.set(name, step=f"angle {i} of {len(prompts)}")
                urls = self.fal.edit(url, ptxt, one, tuple(dims), cancelled, [char] if char else [])
                k = 1
                while (self.out_dir / f"{name}_a{k:02d}.png").exists():
                    k += 1
                out = self.out_dir / f"{name}_a{k:02d}.png"
                tmp = out.with_suffix(".tmp.png")
                self.fal.download(urls[0], tmp)
                shutil.move(str(tmp), str(out))
                made.append({"file": out.name, "prompt": ptxt, "out_size": image_dims(out), "seconds": round(time.time() - t0),
                             "model": cfg["model"], "quality": cfg["quality"] if MODELS[cfg["model"]]["kind"] == "gpt" else cfg["resolution"],
                             "made": time.strftime("%Y-%m-%d %H:%M"), "pick": False, "angle": True, "from": file})
                with self.lock:
                    it["versions"] = it["versions"] + [made[-1]]
                self.save_prompts()
                self.add_spend(self.image_cost(cfg, 1))
            self.set(name, status="done", step="")
        except Cancelled:
            with self.lock:
                it.update(status=self._resting_status(it), step="", error=None, _cancel=False)
        except Exception as e:
            with self.lock:
                it.update(status="done" if it["versions"] else "failed", step="", error=friendly(e))
        finally:
            with self.lock:
                self.active -= 1

    def _stitch_job(self, cid, files, crossfade, music, music_start=0.0):
        t0 = time.time()
        try:
            with self.lock:
                self.active += 1
            self.clip_set(cid, status="working", step="stitching")
            n = 1
            while (self.video_dir / f"reel_{n:02d}.mp4").exists():
                n += 1
            out = self.video_dir / f"reel_{n:02d}.mp4"
            total = stitch_clips(files, out, crossfade, music, music_start)
            pr = probe_video(out)
            self.clip_set(cid, status="done", step="", file=out.name, duration=str(round(total, 1)),
                          resolution=(f"{pr[1]}p" if pr and pr[1] else "720p"), out_size=([pr[0], pr[1]] if pr and pr[1] else None),
                          seconds=round(time.time() - t0), made=time.strftime("%Y-%m-%d %H:%M"))
            self.save_clips()
        except Exception as e:
            self.clip_set(cid, status="failed", step="", error=friendly(e))
            self.save_clips()
        finally:
            with self.lock:
                self.active -= 1

    def clips_snapshot(self):
        with self.lock:
            return [{k: v for k, v in c.items() if not k.startswith("_")} for c in self.clips]

    def save_prompts(self):
        with self.lock:
            data = {n: {"draft": it["prompt"], "notes_used": it.get("notes_used", ""), "versions": it["versions"],
                        "character_on": it.get("character_on", False), "character_note": it.get("character_note", "")} for n, it in self.items.items()}
        (self.out_dir / "prompts.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    def snapshot(self):
        with self.lock:
            return [{k: v for k, v in self.items[n].items() if not k.startswith("_")} for n in self.order]

    def set(self, name, **kw):
        with self.lock:
            self.items[name].update(kw)

    def queue(self, name, stage, prompt=None, cfg=None):
        """stage: 'prompt' (write prompt only), 'enhance' (use given prompt), 'full' (both)."""
        with self.lock:
            it = self.items[name]
            if it["status"] in ("queued", "working"):
                return
            it.update(status="queued", step="waiting", error=None, _stage=stage, _cancel=False)
        self.pool.submit(self._job, name, stage, prompt, cfg)

    def cancel(self, name=None):
        with self.lock:
            names = [name] if name else list(self.items)
            for n in names:
                it = self.items.get(n)
                if it and it["status"] in ("queued", "working"):
                    it["_cancel"] = True

    def add_spend(self, amount):
        """Estimated dollars, accumulated per project in renderpost.json."""
        try:
            with FOLDER_FILE_LOCK:
                fp = folder_settings_path()
                d = json.loads(fp.read_text(encoding="utf-8")) if fp and fp.exists() else {}
                d["spend"] = round(float(d.get("spend") or 0) + float(amount), 4)
                fp.write_text(json.dumps(d, indent=2), encoding="utf-8")
        except Exception:
            pass

    def image_cost(self, cfg, n=1):
        m = MODELS.get(cfg["model"], {})
        if m.get("price"):
            return m["price"] * (m.get("mult", {}).get(cfg.get("resolution"), 1)) * n
        q = GPT_IMAGE_EST.get(cfg.get("quality"), GPT_IMAGE_EST["high"])
        return q.get(str(cfg.get("long_edge")), q["3072"]) * n

    def video_cost(self, c, cfg):
        m = VIDEO_MODELS.get(c.get("vmodel") or "seedance", {})
        price = m.get("price", {})
        per = price.get(c.get("resolution")) or price.get("audio" if cfg.get("video_audio", True) else "silent") or (list(price.values())[0] if price else 0)
        try:
            return float(per) * float(c.get("duration") or 0)
        except (TypeError, ValueError):
            return 0.0

    def _resting_status(self, it):
        return "done" if it["versions"] else ("ready" if it["prompt"] else "pending")

    def _job(self, name, stage, forced_prompt, cfg):
        it = self.items[name]
        src = self.folder / it["source_file"]
        t0 = time.time()
        cancelled = lambda: bool(it.get("_cancel"))
        try:
            with self.lock:
                self.active += 1
            if cancelled():
                raise Cancelled()
            png, (w, h) = prep_image(src)
            self.set(name, status="working", src_size=[w, h])
            url = it.get("url")
            if not url:
                self.set(name, step="uploading")
                url = self.fal.upload(png, it["source_file"])
                self.set(name, url=url)
                if DEMO:
                    self.demo_sources[url] = src
            if cancelled():
                raise Cancelled()
            char = self.character_url() if it.get("character_on") else None
            note = character_guidance(cfg.get("character_note", ""), it.get("character_note", "")) if char else ""
            if stage in ("prompt", "full", "revise", "revise_full") and not forced_prompt:
                revising = stage.startswith("revise") and bool(it["prompt"])
                self.set(name, step="updating prompt" if revising else "writing prompt")
                prompt = self.fal.write_prompt(url, cfg["style_notes"], it["prompt"] if revising else None, char, note)
                self.set(name, prompt=prompt, notes_used=cfg["style_notes"].strip())
                self.save_prompts()
            else:
                prompt = forced_prompt or it["prompt"]
                self.set(name, notes_used=cfg["style_notes"].strip())
            if stage in ("prompt", "revise"):
                self.set(name, status="ready", step="")
                return
            if not prompt:
                raise RuntimeError("No prompt to send. Write one in the box first.")
            if cancelled():
                raise Cancelled()
            self.set(name, prompt=prompt, step="enhancing")
            urls = self.fal.edit(url, prompt, cfg, (w, h), cancelled, [char] if char else [])
            self.set(name, step="downloading")
            made = []
            for u in urls:
                n = len(it["versions"]) + len(made) + 1
                while (self.out_dir / f"{name}_v{n:02d}.png").exists():
                    n += 1
                out = self.out_dir / f"{name}_v{n:02d}.png"
                tmp = out.with_suffix(".tmp.png")
                self.fal.download(u, tmp)
                shutil.move(str(tmp), str(out))
                made.append({"file": out.name, "prompt": prompt, "out_size": image_dims(out),
                             "seconds": round(time.time() - t0), "model": cfg["model"],
                             "quality": cfg["quality"] if MODELS[cfg["model"]]["kind"] == "gpt" else cfg["resolution"],
                             "made": time.strftime("%Y-%m-%d %H:%M"), "pick": False, "character": bool(char)})
            with self.lock:
                it["versions"] = it["versions"] + made
                it.update(status="done", step="")
            self.save_prompts()
            self.add_spend(self.image_cost(cfg, len(made)))
        except Cancelled:
            with self.lock:
                it.update(status=self._resting_status(it), step="", error=None, _cancel=False)
        except Exception as e:
            with self.lock:
                it.update(status="failed" if not it["versions"] else "done", step="", error=friendly(e))
        finally:
            with self.lock:
                self.active -= 1


STATE = State()
FOLDER_REQUESTS = []           # main thread services these (tk dialogs want the main thread)


def open_folder(folder):
    """Point the app at another render folder. Safe only when nothing is running."""
    folder = Path(folder)
    if not folder.is_dir():
        raise RuntimeError("That folder no longer exists.")
    with STATE.lock:
        STATE.items = {}; STATE.order = []; STATE.clips = []; STATE.clip_urls = {}
        STATE.folder = folder
        STATE.out_dir = folder / OUTPUT_DIRNAME
        STATE.video_dir = STATE.out_dir / "video"
    STATE.out_dir.mkdir(exist_ok=True)
    STATE.scan(); STATE.load_clips()
    cfg = load_config()
    recent = [str(folder)] + [r for r in cfg.get("recent_folders", []) if r != str(folder)]
    cfg["recent_folders"] = recent[:8]
    save_config(cfg)


# ---------------------------------------------------------------- http
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"          # keep-alive; video seeking needs it to behave

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            html = resource_path("web", "templates", "index.html").read_text(encoding="utf-8")
            return self._send(200, html, "text/html; charset=utf-8")
        if path.startswith("/static/"):
            root = resource_path("web", "static").resolve()
            f = (root / urllib.parse.unquote(path[len("/static/"):])).resolve()
            if os.path.normcase(str(f.parent)) != os.path.normcase(str(root)) or not f.exists():
                return self._send(404, "not found", "text/plain")
            ctype = {".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8"}.get(f.suffix.lower(), "application/octet-stream")
            return self._send(200, f.read_bytes(), ctype)
        if path == "/api/state":
            STATE.last_seen = time.time(); STATE.seen_browser = True; STATE.bye_at = None
            cfg = load_config()
            return self._send(200, {
                "folder": str(STATE.folder), "has_key": bool(cfg["fal_key"]) or DEMO, "demo": DEMO,
                "recent": [r for r in cfg.get("recent_folders", []) if r != str(STATE.folder)],
                "character": {"file": "character.png?v=" + str(int(STATE.character_path().stat().st_mtime)) if STATE.character_path() else None,
                              "desc": cfg.get("character_desc", "")},
                "version": APP_VERSION, "latest": LATEST, "catalog": {**CATALOG_STATUS, "url": cfg.get("catalog_url", "") or MODEL_CATALOG_URL},
                "config": {k: v for k, v in cfg.items() if k != "fal_key"},
                "size_options": SIZE_OPTIONS, "quality_options": QUALITY_OPTIONS,
                "models": {k: {"label": v["label"], "kind": v["kind"], "hint": v["hint"], "price": v.get("price"), "mult": v.get("mult"), "recommended": v.get("recommended", False)} for k, v in MODELS.items()},
                "res_options": RES_OPTIONS, "variation_options": VARIATION_OPTIONS, "angle_options": ANGLE_OPTIONS,
                "picks": sum(1 for it in STATE.snapshot() for v in it["versions"] if v.get("pick")),
                "spend": float(cfg.get("spend") or 0), "spend_alert": float(cfg.get("spend_alert") or 10),
                "clips": STATE.clips_snapshot(),
                "video": {"res": VIDEO_RES, "models": {k: {"label": v["label"], "hint": v["hint"], "price": v["price"], "res": v.get("res"), "recommended": v.get("recommended", False), "min_duration": v.get("min_duration", 1)} for k, v in VIDEO_MODELS.items()},
                          "durations": VIDEO_DURATIONS,
                          "take_durations": TAKE_DURATIONS, "ffmpeg": bool(ffmpeg_exe()),
                          "music": sorted(p.name for p in STATE.folder.iterdir() if p.is_file() and p.suffix.lower() in MUSIC_EXT)},
                "active": STATE.active, "items": STATE.snapshot()})
        if path.startswith("/vid/"):
            f = (STATE.video_dir / urllib.parse.unquote(path[5:])).resolve()
            root = STATE.video_dir.resolve()
            if os.path.normcase(str(f.parent)) != os.path.normcase(str(root)) or not f.exists():
                return self._send(404, "not found", "text/plain")
            size = f.stat().st_size
            rng = self.headers.get("Range")
            start, end = 0, size - 1
            if rng and rng.startswith("bytes="):
                a, _, b = rng[6:].partition("-")
                try:
                    start = int(a) if a else max(0, size - int(b))
                    end = int(b) if (a and b) else end
                except ValueError:
                    start, end = 0, size - 1
                start = max(0, min(start, size - 1)); end = max(start, min(end, size - 1))
            self.send_response(206 if rng else 200)
            self.send_header("Content-Type", "video/webm" if f.suffix.lower() == ".webm" else "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if rng:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            try:
                with open(f, "rb") as fh:
                    fh.seek(start); left = end - start + 1
                    while left > 0:
                        chunk = fh.read(min(1 << 20, left))
                        if not chunk:
                            break
                        self.wfile.write(chunk); left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        if path.startswith("/img/"):
            kind, _, name = path[5:].partition("/")
            name = urllib.parse.unquote(name)
            base = STATE.folder if kind == "raw" else STATE.out_dir
            f = (base / name).resolve()
            if os.path.normcase(str(f.parent)) != os.path.normcase(str(base.resolve())) or not f.exists():
                return self._send(404, "not found", "text/plain")
            ct = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}
            data = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ct.get(f.suffix[1:].lower(), "application/octet-stream"))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return self.wfile.write(data)
        self._send(404, "not found", "text/plain")

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        body = self._json()
        cfg = load_config()
        if path == "/api/video/stitch":
            ids = body.get("ids") or []
            files = []
            for cid in ids:
                c = STATE.clip(cid)
                if c and c["status"] == "done" and c["file"]:
                    files.append(STATE.video_dir / c["file"])
            if len(files) < 2:
                return self._send(400, {"error": "Pick at least two finished clips to stitch."})
            music = body.get("music")
            music = STATE.folder / music if music and (STATE.folder / music).exists() else None
            mstart = max(0.0, float(body.get("music_start") or 0))
            c = STATE.new_clip("reel", [{"clip": cid} for cid in ids], cfg)
            c.update(resolution="", prompt=f"{len(files)} clips, {cfg['crossfade']}s crossfade" + (f", music: {music.name}" + (f" from {mstart:g}s" if mstart else "") if music else ""))
            STATE.pool.submit(STATE._stitch_job, c["id"], files, float(cfg.get("crossfade", "0.6")), music, mstart)
            return self._send(200, {"ok": True, "id": c["id"]})
        if path == "/api/video/cancel":
            cid = body.get("id")
            with STATE.lock:
                for c in STATE.clips:
                    if (cid is None or c["id"] == cid) and c["status"] in ("queued", "working"):
                        c["_cancel"] = True
            return self._send(200, {"ok": True})
        if path == "/api/export_images":
            rows = []
            for it in STATE.snapshot():
                rows.append({"image": it["source_file"], "raw_image_url": it.get("url"), "next_prompt": it.get("prompt"),
                             "versions": [{"file": v["file"], "prompt": v.get("prompt"), "model": v.get("model"), "angle": bool(v.get("angle")), "pick": bool(v.get("pick"))} for v in it["versions"]]})
            out = STATE.out_dir / "prompts-export.json"
            out.write_text(json.dumps({"exported": time.strftime("%Y-%m-%d %H:%M"), "style_notes": cfg.get("style_notes", ""),
                                       "note": "raw_image_url is a fal-hosted copy of the raw render, valid for a limited time; null means it hasn't been uploaded this session.",
                                       "images": rows}, indent=2), encoding="utf-8")
            return self._send(200, {"ok": True, "file": out.name, "count": len(rows)})
        if path == "/api/video/export":
            # prompt + hosted image URL per clip draft, for people who run other video tools
            rows = []
            for c in STATE.clips_snapshot():
                if c["kind"] == "reel" or not c.get("prompt"):
                    continue
                srcs = []
                for src in c["sources"]:
                    key = (src["name"], src["file"])
                    srcs.append({"frame": src["file"], "image_url": STATE.clip_urls.get(key)})
                rows.append({"kind": c["kind"], "frames": srcs, "prompt": c["prompt"], "shots": c.get("shots"),
                             "duration": c.get("duration"), "status": c["status"]})
            STATE.video_dir.mkdir(exist_ok=True)
            out = STATE.video_dir / "prompts-export.json"
            out.write_text(json.dumps({"exported": time.strftime("%Y-%m-%d %H:%M"), "note": "image_url is a fal-hosted copy of the frame, valid for a limited time; null means it was never uploaded this session (press Write motion prompts once).", "clips": rows}, indent=2), encoding="utf-8")
            return self._send(200, {"ok": True, "file": out.name, "count": len(rows)})
        if path == "/api/video/clear_drafts":
            with STATE.lock:
                STATE.clips = [c for c in STATE.clips if not (c["kind"] != "reel" and c["status"] in ("ready", "failed"))]
            STATE.save_clips()
            return self._send(200, {"ok": True})
        if path == "/api/video/remove":
            cid = body.get("id")
            with STATE.lock:
                c = STATE.clip(cid)
                if c and c["status"] not in ("queued", "working"):
                    STATE.clips.remove(c)
                    if c.get("file") and body.get("delete_file"):
                        try:
                            (STATE.video_dir / c["file"]).unlink()
                        except Exception:
                            pass
            STATE.save_clips()
            return self._send(200, {"ok": True})
        if path == "/api/open":
            which = body.get("which")
            target = {"picks": STATE.out_dir / "picks", "video": STATE.video_dir, "root": STATE.folder}.get(which, STATE.out_dir)
            target.mkdir(exist_ok=True)
            try:
                if os.name == "nt":
                    os.startfile(str(target))
                else:
                    import subprocess
                    subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(target)])
            except Exception as e:
                return self._send(500, {"error": str(e)})
            return self._send(200, {"ok": True})
        if path == "/api/rescan":
            STATE.scan()
            STATE.music_dirty = True
            return self._send(200, {"ok": True, "pending": sum(1 for it in STATE.snapshot() if it["status"] == "pending")})
        if path == "/api/pick":
            name, file = body.get("name"), body.get("file")
            it = STATE.items.get(name)
            if not it:
                return self._send(404, {"error": "unknown image"})
            picks = STATE.out_dir / "picks"; picks.mkdir(exist_ok=True)
            with STATE.lock:
                for v in it["versions"]:
                    if v["file"] == file:
                        v["pick"] = not v.get("pick")
                        dst = picks / v["file"]
                        if v["pick"]:
                            shutil.copy2(STATE.out_dir / v["file"], dst)
                        elif dst.exists():
                            dst.unlink()
            STATE.save_prompts()
            return self._send(200, {"ok": True})
        if path == "/api/delete_version":
            name, file = body.get("name"), body.get("file")
            it = STATE.items.get(name)
            if not it or not any(v["file"] == file for v in it["versions"]):
                return self._send(404, {"error": "unknown version"})
            if it["status"] in ("queued", "working"):
                return self._send(400, {"error": "That image is busy."})
            trash = STATE.out_dir / "trash"; trash.mkdir(exist_ok=True)
            try:
                src = STATE.out_dir / file
                if src.exists():
                    shutil.move(str(src), str(trash / file))
                pk = STATE.out_dir / "picks" / file
                if pk.exists():
                    pk.unlink()
            except Exception as e:
                return self._send(500, {"error": str(e)})
            with STATE.lock:
                it["versions"] = [v for v in it["versions"] if v["file"] != file]
                if not it["versions"]:
                    it["status"] = "ready" if it["prompt"] else "pending"
            STATE.save_prompts()
            return self._send(200, {"ok": True})
        if path == "/api/compare":
            name, file = body.get("name"), body.get("file")
            it = STATE.items.get(name)
            if not it or not file:
                return self._send(404, {"error": "unknown image"})
            try:
                out = make_compare(STATE.folder / it["source_file"], STATE.out_dir / file, STATE.out_dir / "compare")
            except Exception as e:
                return self._send(500, {"error": friendly(e)})
            return self._send(200, {"ok": True, "file": out.name})
        if path == "/api/cancel":
            STATE.cancel(body.get("name"))
            return self._send(200, {"ok": True})
        if path == "/api/add_images":
            import base64
            added = 0
            for f in body.get("files") or []:
                name = Path(str(f.get("name") or "")).name
                if not name or Path(name).suffix.lower() not in EXTENSIONS:
                    continue
                data = str(f.get("data") or "")
                if "," in data:
                    data = data.split(",", 1)[1]
                try:
                    raw = base64.b64decode(data)
                except Exception:
                    continue
                dest = STATE.folder / name; k = 2
                while dest.exists():
                    dest = STATE.folder / f"{Path(name).stem}-{k}{Path(name).suffix}"; k += 1
                dest.write_bytes(raw); added += 1
            STATE.scan()
            return self._send(200, {"ok": True, "added": added})
        if path == "/api/character/upload":
            import base64
            data = body.get("data") or ""
            if "," in data:
                data = data.split(",", 1)[1]
            try:
                raw = base64.b64decode(data)
                from PIL import Image
                im = Image.open(io.BytesIO(raw)).convert("RGB")
                im.thumbnail((2048, 2048))
                im.save(STATE.out_dir / "character.png", "PNG")
            except Exception as e:
                return self._send(400, {"error": f"Couldn't read that image ({e})."})
            cfg["character_desc"] = ""; save_config(cfg)
            return self._send(200, {"ok": True})
        if path == "/api/character/clear":
            p = STATE.out_dir / "character.png"
            if p.exists():
                p.unlink()
            cfg["character_desc"] = ""; save_config(cfg)
            return self._send(200, {"ok": True})
        if path == "/api/folder":
            if STATE.active:
                return self._send(400, {"error": "Wait for the current jobs to finish before switching folders."})
            target = body.get("path")
            if body.get("browse"):
                FOLDER_REQUESTS.append(True)
                return self._send(200, {"ok": True, "browsing": True})
            try:
                open_folder(target)
            except Exception as e:
                return self._send(400, {"error": str(e)})
            return self._send(200, {"ok": True})
        if path == "/api/bye":
            STATE.bye_at = time.time()
            return self._send(200, {"ok": True})
        if path == "/api/quit":
            self._send(200, {"ok": True})
            threading.Timer(0.3, lambda: os._exit(0)).start()
            return
        if path == "/api/config":
            if "img_mode" in body:
                cfg["img_mode"] = "grid" if body["img_mode"] == "grid" else "detail"
            if "more_open" in body:
                cfg["more_open"] = bool(body["more_open"])
            if "spend_alert" in body:
                try:
                    cfg["spend_alert"] = float(body["spend_alert"])
                except (TypeError, ValueError):
                    pass
            for k in ("model", "quality", "long_edge", "resolution", "variations", "angles", "style_notes",
                      "video_model", "video_res", "video_duration", "take_duration", "crossfade", "motion_notes", "shots", "video_frames", "energy",
                      "character_note"):
                if k in body:
                    cfg[k] = str(body[k])
            if "video_audio" in body:
                cfg["video_audio"] = bool(body["video_audio"])
            if "show_all_models" in body:
                cfg["show_all_models"] = bool(body["show_all_models"])
            if "catalog_url" in body:
                cfg["catalog_url"] = str(body["catalog_url"]).strip()
                save_config(cfg); load_catalog()
            if "take_character" in body:
                cfg["take_character"] = bool(body["take_character"])
            if cfg["model"] not in MODELS:
                cfg["model"] = DEFAULT_CONFIG["model"]
            if "review_first" in body:
                cfg["review_first"] = bool(body["review_first"])
            if body.get("fal_key"):
                key = body["fal_key"].strip()
                if not DEMO:
                    try:
                        Fal(key).check()
                    except Exception as e:
                        msg = "fal rejected that key. Check it's copied in full and still active." if "401" in str(e) \
                            else f"Could not reach fal: {e}"
                        return self._send(400, {"error": msg})
                cfg["fal_key"] = key
                STATE.fal = None
            save_config(cfg)
            return self._send(200, {"ok": True})
        if path == "/api/item_config":
            name = body.get("name")
            if name not in STATE.items:
                return self._send(404, {"error": "unknown image"})
            STATE.set(name, character_on=bool(body.get("character_on")), character_note=str(body.get("character_note") or ""))
            STATE.save_prompts()
            return self._send(200, {"ok": True})
        if not cfg["fal_key"] and not DEMO:
            return self._send(400, {"error": "Add your fal key first."})
        if STATE.fal is None:
            try:
                fal = DemoFal() if DEMO else Fal(cfg["fal_key"])
                if not DEMO:
                    fal.check()
                STATE.fal = fal
            except Exception as e:
                if "401" in str(e):
                    return self._send(401, {"error": "fal rejected the saved key.", "need_key": True})
                return self._send(500, {"error": friendly(e)})
        if path == "/api/character/generate":
            desc = (body.get("description") or "").strip()
            if len(desc) < 8:
                return self._send(400, {"error": "Describe the person in a sentence or two."})
            try:
                url = STATE.fal.generate_character(desc)
                tmp = STATE.out_dir / "character.tmp.png"
                STATE.fal.download(url, tmp)
                shutil.move(str(tmp), str(STATE.out_dir / "character.png"))
            except Exception as e:
                return self._send(500, {"error": friendly(e)})
            cfg["character_desc"] = desc; save_config(cfg)
            STATE.add_spend(0.15)
            return self._send(200, {"ok": True})
        if path == "/api/angles":
            name, file = body.get("name"), body.get("file")
            it = STATE.items.get(name)
            if not it or not any(v["file"] == file for v in it["versions"]):
                return self._send(404, {"error": "unknown version"})
            if it["status"] in ("queued", "working"):
                return self._send(400, {"error": "That image is busy."})
            with STATE.lock:
                it.update(status="queued", step="waiting", error=None, _cancel=False)
            STATE.pool.submit(STATE._angles_job, name, file, cfg)
            return self._send(200, {"ok": True})
        if path == "/api/video/prompts":
            # Create clip drafts from picks and write a motion prompt for each (or one take prompt).
            picks = body.get("picks") or []
            picks = [p for p in picks if p.get("name") in STATE.items and
                     (p.get("file") == STATE.items[p["name"]]["source_file"] or any(v["file"] == p.get("file") for v in STATE.items[p["name"]]["versions"]))]
            if not picks:
                return self._send(400, {"error": "Pick at least one version first."})
            stage = "prompt" if cfg.get("review_first", True) else "full"
            made = []
            def draft_for(kind, sources):
                # an unsent draft for the same frame(s) gets rewritten, not duplicated
                key = [(x["name"], x["file"]) for x in sources]
                for c in STATE.clips:
                    if c["kind"] == kind and c["status"] in ("ready", "failed") and [(x["name"], x["file"]) for x in c["sources"]] == key:
                        return c
                return None
            if body.get("mode") == "take":
                c = draft_for("take", picks) or STATE.new_clip("take", picks, cfg)
                with STATE.lock:
                    c.update(status="queued", step="waiting", error=None, _cancel=False, sources=picks)
                made.append(c["id"]); STATE.pool.submit(STATE._clip_job, c["id"], stage, None, cfg)
            else:
                for pk in picks:
                    c = draft_for("clip", [pk]) or STATE.new_clip("clip", [pk], cfg)
                    with STATE.lock:
                        c.update(status="queued", step="waiting", error=None, _cancel=False)
                    made.append(c["id"]); STATE.pool.submit(STATE._clip_job, c["id"], stage, None, cfg)
            STATE.save_clips()
            return self._send(200, {"ok": True, "ids": made})
        if path == "/api/video/make":
            prompts = body.get("prompts") or {}
            ids = body.get("ids") or [c["id"] for c in STATE.clips_snapshot() if c["status"] in ("ready", "failed")]
            for cid in ids:
                c = STATE.clip(cid)
                if not c or c["kind"] == "reel" or c["status"] in ("queued", "working"):
                    continue
                p = (prompts.get(cid) or c["prompt"] or "").strip()
                if c["status"] == "done":                      # remake: new draft, keep the old clip
                    c = STATE.new_clip(c["kind"], c["sources"], cfg)
                with STATE.lock:
                    c.update(status="queued", step="waiting", error=None, _cancel=False, prompt=p)
                STATE.pool.submit(STATE._clip_job, c["id"], "enhance" if p else "full", p or None, cfg)
            STATE.save_clips()
            return self._send(200, {"ok": True})
        if path == "/api/run":
            # Stage 1: write prompts for anything new. In review mode, stop there.
            STATE.scan()
            stage = "prompt" if cfg.get("review_first", True) else "full"
            everything = bool(body.get("all"))       # new batch: fresh prompts for every image
            for it in STATE.snapshot():
                if everything or it["status"] == "pending" or (it["status"] == "failed" and not it["prompt"]):
                    STATE.queue(it["name"], stage, None, cfg)
            return self._send(200, {"ok": True})
        notes_now = cfg["style_notes"].strip()
        def stale(it):
            return bool(it["prompt"]) and (it.get("notes_used") or "") != notes_now
        if path == "/api/revise":
            # Style notes changed: update every prompt that was written under the old notes.
            for it in STATE.snapshot():
                if it["status"] in ("ready", "failed", "done") and stale(it):
                    STATE.queue(it["name"], "revise", None, cfg)
            return self._send(200, {"ok": True})
        if path == "/api/enhance_all":
            # Stage 2: send every reviewed prompt. Prompts arrive from the page so edits count.
            prompts = body.get("prompts") or {}
            auto_revise = bool(body.get("revise_stale"))
            only = set(body.get("names") or [])
            for it in STATE.snapshot():
                if it["status"] not in ("ready", "failed", "done"):
                    continue
                if only and it["name"] not in only:
                    continue
                p = (prompts.get(it["name"]) or it["prompt"] or "").strip()
                if not p:
                    continue
                hand_edited = p != (it["prompt"] or "").strip()
                if auto_revise and stale(it) and not hand_edited:
                    STATE.queue(it["name"], "revise_full", None, cfg)   # update prompt, then enhance
                else:
                    STATE.set(it["name"], prompt=p)
                    STATE.queue(it["name"], "enhance", p, cfg)
            STATE.save_prompts()
            return self._send(200, {"ok": True})
        if path == "/api/regenerate":
            # One image, with exactly the prompt in its box. Empty box = write a fresh prompt first.
            name = body.get("name")
            if name not in STATE.items:
                return self._send(404, {"error": "unknown image"})
            prompt = (body.get("prompt") or "").strip() or None
            if body.get("rewrite"):
                STATE.queue(name, "prompt", None, cfg)          # fresh prompt for this image only
            elif prompt:
                STATE.set(name, prompt=prompt)
                STATE.save_prompts()
                STATE.queue(name, "enhance", prompt, cfg)
            else:
                STATE.queue(name, "full", None, cfg)
            return self._send(200, {"ok": True})
        self._send(404, {"error": "not found"})


# ---------------------------------------------------------------- main
def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def ensure_packages():
    """First run on a fresh machine: install what's missing, then continue."""
    if getattr(sys, "frozen", False):
        return True   # everything is bundled in the exe
    missing = []
    try:
        import PIL  # noqa
    except ImportError:
        missing.append("pillow")
    if not DEMO:
        try:
            import fal_client  # noqa
        except ImportError:
            missing.append("fal-client")
    try:
        import imageio_ffmpeg  # noqa
    except ImportError:
        missing.append("imageio-ffmpeg")      # bundled ffmpeg, used for stitching reels
    if not missing:
        return True
    print(f"First run: installing {', '.join(missing)} (one time, needs internet)...")
    import subprocess
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", *missing])
    except Exception as e:
        print(f"\nCould not install automatically ({e}).")
        print(f"Open a terminal and run:  {sys.executable} -m pip install {' '.join(missing)}")
        return False
    print("Installed.\n")
    return True


LATEST = {"version": None, "url": None}


CATALOG_STATUS = {"url": "", "ok": None, "note": ""}


def load_catalog():
    """Merge a remote model catalog over the built-in tables, if configured."""
    url = (load_config().get("catalog_url") or MODEL_CATALOG_URL or "").strip()
    CATALOG_STATUS.update(url=url, ok=None, note="")
    if not url:
        return
    try:
        req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read().decode("utf-8"))
        for k, v in (d.get("image") or {}).items():
            if isinstance(v, dict) and v.get("endpoint") and v.get("kind") in ("gpt", "nano"):
                MODELS[k] = {**MODELS.get(k, {}), **v}
        n = 0
        for k, v in (d.get("video") or {}).items():
            if isinstance(v, dict) and v.get("i2v"):
                VIDEO_MODELS[k] = {**VIDEO_MODELS.get(k, {}), **v}; n += 1
        n += sum(1 for v in (d.get("image") or {}).values() if isinstance(v, dict) and v.get("endpoint"))
        CATALOG_STATUS.update(ok=True, note=f"{n} model entr{'y' if n == 1 else 'ies'} loaded")
    except Exception as e:
        CATALOG_STATUS.update(ok=False, note=str(e)[:120])


def check_updates():
    if not UPDATE_URL:
        return
    try:
        req = urllib.request.Request(UPDATE_URL, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read().decode("utf-8"))
        tag = str(d.get("tag_name") or d.get("version") or "").lstrip("v")
        url = d.get("html_url") or d.get("url")
        def key(v):
            return tuple(int(x) if x.isdigit() else 0 for x in v.split("."))
        if tag and key(tag) > key(APP_VERSION):
            LATEST.update(version=tag, url=url)
    except Exception:
        pass


def folder_watch():
    """Pick up renders dropped into the folder while the app is open."""
    last = None
    while True:
        time.sleep(6)
        try:
            if not STATE.folder or STATE.active:
                continue
            names = tuple(p.name for p in find_images(STATE.folder))
            if last is not None and names != last:
                STATE.scan(); STATE.music_dirty = True
            last = names
        except Exception:
            pass


def watchdog():
    """Exit when the page says goodbye and doesn't come back, or after a long silence.
    Background tabs poll slowly (browsers throttle them), so silence alone must be long."""
    while True:
        time.sleep(5)
        now = time.time()
        idle = now - STATE.last_seen
        if STATE.active:
            continue
        if STATE.bye_at and now - STATE.bye_at > 60 and STATE.last_seen < STATE.bye_at:
            os._exit(0)
        if (STATE.seen_browser and idle > 30 * 60) or (not STATE.seen_browser and idle > 10 * 60):
            os._exit(0)


def main():
    if sys.stdout is None or sys.stderr is None:       # built with --noconsole
        logf = open(config_dir() / "log.txt", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = logf
        print(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} start")
    if not ensure_packages():
        return 1

    STATE.folder = pick_folder()
    STATE.out_dir = STATE.folder / OUTPUT_DIRNAME
    open_folder(STATE.folder)

    port = free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    print(f"{APP_NAME} {APP_VERSION}{' (demo)' if DEMO else ''}")
    print(f"Folder:  {STATE.folder}")
    print(f"Renders: {len(STATE.order)}")
    print(f"Open:    {url}")
    print("\nKeep this window open while you work. Close it when you're done.")
    if not webbrowser.open(url):
        print("Your browser did not open on its own. Copy the address above into it.")
    threading.Thread(target=watchdog, daemon=True).start()
    threading.Thread(target=folder_watch, daemon=True).start()
    threading.Thread(target=check_updates, daemon=True).start()
    threading.Thread(target=load_catalog, daemon=True).start()
    try:
        while True:
            time.sleep(0.5)
            if FOLDER_REQUESTS:
                FOLDER_REQUESTS.pop()
                try:
                    import tkinter as tk
                    from tkinter import filedialog
                    root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
                    chosen = filedialog.askdirectory(title="Choose a folder of renders", initialdir=str(STATE.folder))
                    root.destroy()
                    if chosen:
                        open_folder(chosen)
                except Exception as e:
                    print(f"folder picker: {e}")
    except KeyboardInterrupt:
        pass
    server.shutdown()
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except SystemExit:
        raise
    except Exception:
        import traceback
        print("\nSomething went wrong:\n")
        traceback.print_exc()
        code = 1
    if code != 0 and os.name == "nt":
        input("\nPress Enter to close.")
    sys.exit(code)
