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
    pip install pyinstaller fal-client pillow imageio-ffmpeg
    pyinstaller --onefile --noconsole --name RenderPost --collect-all fal_client --collect-all httpx --collect-all imageio_ffmpeg --icon RenderPost.ico RenderPost.py
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

APP_NAME = "RenderPost"
APP_VERSION = "1.8.1"
# Optional: where the exe checks for a newer release. Point this at your GitHub repo's
# latest-release API and the header shows an "Update available" link when a newer tag exists.
# e.g. "https://api.github.com/repos/YOURNAME/renderpost/releases/latest"   ("" = don't check)
UPDATE_URL = "https://api.github.com/repos/achristo714/RenderPost/releases/latest"
DEMO = "--demo" in sys.argv

MODELS = {
    "gpt-image-2":     {"label": "GPT Image 2 · OpenAI", "endpoint": "openai/gpt-image-2/edit", "kind": "gpt", "recommended": True,
                        "hint": "strongest at photoreal materials and people · token priced, roughly $0.10 to $0.40 per image"},
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

MOTION_BRIEF = """You write prompts for video models (Seedance, Kling) to animate a single
architectural visualization still. The still is frame one of the clip and must stay exactly
as it is: same architecture, materials, furniture, camera lens, and time of day. Motion
comes from the camera and from the world, never from redesigning the scene.

Structure the prompt the way these models are documented to want it, as short sentences
in this order, describing how the shot evolves over its full length:
1. What moves in the scene and how (subject and action): people walking or talking,
   leaves and curtains stirring, water, distant traffic, candle or lamp flicker, cloud
   drift. Only things already present or plausible. Natural speed.
2. The scene held constant: say explicitly that the architecture, materials, layout and
   lighting stay exactly as in the still.
3. ONE specific named camera move, slow and steady: slow push-in, slow pull-back, gentle
   dolly left or right, subtle orbit, or a slow crane. Never a vague word like "cinematic".
   Then state what the camera is NOT doing: no cuts, no zoom, no shake.
4. One short line of ambient sound that fits the space.
No text or captions in the video. Output ONLY the prompt. No preamble, no bullet points,
no quotes. Under 90 words."""

CHARACTER_BRIEF = """A SECOND input image is provided: a reference photo of one specific person. Include this
exact person in the scene, once, placed where a real person would be in this space and doing
something natural for it (seated at a table, standing at the counter, walking through, looking
at the view). Keep their face, hair, build and clothing consistent with the reference. Refer to
them in the prompt as "the person shown in the second input image". This overrides the rule
about not adding people, for this one person only; add nobody else unless the notes say so.
{note}"""

CHARACTER_T2I = ("Full-length reference photograph of one person for use as a consistent character in "
                 "architectural visualisation: {desc}. Plain light grey studio background, soft even "
                 "light, relaxed natural pose, facing the camera, photoreal, no text, no logos.")

TAKE_CHARACTER = """The LAST image is a reference of one specific person (@Image {n}). They appear in the take,
walking through the spaces at a natural pace, seen from behind or in three-quarter view more
than head-on, with consistent face, hair, build and clothing. Say so explicitly in the prompt."""

MOTION_CHARACTER = """The still contains a specific person. Keep their appearance exactly as in the still and give
them one small natural action across the clip (turn, take a few steps, sip, look up)."""

ENERGY = {
    "calm":     "Camera energy: CALM. One slow, steady move; the viewer should barely notice the camera. Suits stills for print and quiet interiors.",
    "moderate": "Camera energy: MODERATE. A clear, confident camera move that travels a noticeable distance over the clip (a dolly that crosses the room, an orbit of 20 to 30 degrees, a crane that rises past a balcony), plus visible life in the scene. Still smooth, never handheld.",
    "dynamic":  "Camera energy: DYNAMIC. A bold cinematic move with real parallax: a fast dolly or tracking shot, a sweeping orbit, a crane from ground to roofline, a drone-style reveal. Foreground elements should slide past the lens. The architecture still does not change; only the camera is brave.",
}

ANGLES_BRIEF = """You are an art director for architectural visualization. You are shown one finished
image of a space. Write {n} prompts for an image model that will produce {n} NEW stills of
this SAME space, each from a different camera position, as if a photographer had walked the
room. Every angle must be consistent with what the image shows: same architecture, materials,
furniture, fixtures, lighting and time of day. Nothing is redesigned; the camera moves, the
space does not.

Choose {n} genuinely different, useful angles for this space, for example: a wide
establishing view from the entrance, the reverse angle looking back, a low three-quarter view
across furniture, an elevated view, a tight detail vignette of the best material moment, a
view through an opening into the next space. Only propose angles this image gives enough
information to support. Name what the camera sees in each, using details visible in the image.

Format: EXACTLY {n} lines, one prompt per line, no numbering, no preamble, no quotes. Each
line starts with "Same space as the reference image, identical architecture, materials,
furniture, lighting and time of day." followed by the new camera position and what is in
frame. Under 60 words per line."""

MULTISHOT_BRIEF = """You write prompts for Seedance, a video model that supports multi-shot prompts:
several shots in one clip, cut together. You are given one architectural visualization still.
Write a prompt for a short sequence of {shots} shots of THIS space.

Rules:
- Shot 1 starts exactly on the still: same framing, same everything. Later shots are new
  camera setups of the same space (a closer detail, a reverse angle, a wider establishing
  view) that stay consistent with what the still shows: same architecture, materials,
  furniture, lighting and time of day. Never invent rooms or elements not implied by the still.
- Write EXACTLY one line per shot, each starting "Shot N:" in order. Within each line,
  follow the documented order: camera move first, then what moves in the scene, then a
  short sound cue. One slow camera move per shot. Do not use timestamps.
- No text, captions or logos.
- Output ONLY the shot lines, nothing else. Under 140 words total."""

TAKE_BRIEF = """You write prompts for Seedance reference-to-video. You are given several
architectural visualization stills of the same project, in order. ByteDance's documented
convention is to reference them as @Image 1, @Image 2, and so on. Write ONE prompt for a
single continuous cinematic take that tours the project, visiting the spaces in that
order, treating each image as the exact look of that space.
Rules:
- Reference each image explicitly by its @Image N tag, in order, and describe the camera
  move that carries the viewer from one to the next (walk through a doorway, glide along
  a facade, rise over the roofline). Say what the camera is NOT doing: no cuts.
- End with one short line of ambient sound that evolves with the spaces.
- Keep the architecture, materials and lighting of each reference exactly as shown. No
  redesign, no new rooms, no text.
- Slow, steady, steadicam feel. Natural life: people at walking pace, foliage, light.
- Output ONLY the prompt. No preamble, no lists, no quotes. Under 160 words."""
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
QUALITY_OPTIONS = {"low": "Low (fast, cheap)", "medium": "Medium", "high": "High"}

DEFAULT_CONFIG = {"fal_key": "", "model": "gpt-image-2", "quality": "medium", "long_edge": "3072",
                  "resolution": "2K", "variations": "1", "angles": "6", "style_notes": "", "review_first": True,
                  "video_model": "h3max", "video_res": "480p", "show_all_models": False, "video_duration": "5", "take_duration": "15", "video_audio": True,
                  "crossfade": "0.6", "motion_notes": "", "shots": "1", "video_frames": "[]", "energy": "calm",
                  "character_on": False, "character_note": "", "character_desc": "", "take_character": False}

BASE_BRIEF = """You are an art director for architectural visualization marketing imagery.
You will be shown one raw render from D5 Render. Write a single image-editing prompt
that turns it into a marketing-grade image a top-tier archviz studio would publish.

Hard rules for the prompt you write:
- The building's geometry, massing, facade design, materials, window layout, camera
  position, lens, and composition must remain EXACTLY as rendered. Say this explicitly
  at the start of the prompt. Nothing about the architecture may be redesigned.
- Nothing may be added, removed, or swapped: no new fixtures, furniture, shelving,
  bars, artwork, panelling, or people that are not already there, and no window,
  opening, or wall treatment replaced with a different feature. Existing elements
  become more real; they do not become different elements.
- Keep the render's own white balance and colour temperature. Do not warm, tint,
  or push the image toward orange or yellow. Lighting can gain depth, contrast,
  falloff, and realism without changing its colour.
- Only improve: lighting quality and depth, sky and atmosphere where present,
  material realism (reflections, roughness, weathering, fabric and wood texture),
  vegetation quality, existing people made photoreal and naturally posed, contrast,
  depth of field realism, edge realism, and removal of obvious CG artifacts.
- Be specific to THIS image. Name what is actually weak in it and what to do about it.
- Choose one coherent mood that suits the project type and view.
- No text, logos, watermarks, or captions.
- Output ONLY the prompt. No preamble, no bullet points, no quotes, no markdown.
  Under 180 words."""


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


FOLDER_KEYS = ("style_notes", "motion_notes", "video_frames", "character_on", "character_note", "character_desc", "take_character", "spend")
GPT_IMAGE_EST = 0.25            # GPT Image 2 is token priced; this is the working average used for the running total          # these live with the render folder, not the user


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
            brief += "\n\n" + CHARACTER_BRIEF.format(note=("Notes about the person: " + character_note.strip()) if character_note.strip() else "")
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
            if take and cfg.get("take_character") and cfg.get("character_on") and self.character_path():
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
            char = self.character_url() if cfg.get("character_on") else None
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
            data = {n: {"draft": it["prompt"], "notes_used": it.get("notes_used", ""), "versions": it["versions"]} for n, it in self.items.items()}
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
        return GPT_IMAGE_EST * n

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
            char = self.character_url() if cfg.get("character_on") else None
            if stage in ("prompt", "full", "revise", "revise_full") and not forced_prompt:
                revising = stage.startswith("revise") and bool(it["prompt"])
                self.set(name, step="updating prompt" if revising else "writing prompt")
                prompt = self.fal.write_prompt(url, cfg["style_notes"], it["prompt"] if revising else None, char, cfg.get("character_note", ""))
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
            return self._send(200, PAGE, "text/html; charset=utf-8")
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
            cfg["character_desc"] = ""; cfg["character_on"] = True; save_config(cfg)
            return self._send(200, {"ok": True})
        if path == "/api/character/clear":
            p = STATE.out_dir / "character.png"
            if p.exists():
                p.unlink()
            cfg["character_on"] = False; cfg["character_desc"] = ""; save_config(cfg)
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
                      "video_model", "video_res", "video_duration", "take_duration", "crossfade", "motion_notes", "shots", "video_frames", "energy"):
                if k in body:
                    cfg[k] = str(body[k])
            if "video_audio" in body:
                cfg["video_audio"] = bool(body["video_audio"])
            if "show_all_models" in body:
                cfg["show_all_models"] = bool(body["show_all_models"])
            if "catalog_url" in body:
                cfg["catalog_url"] = str(body["catalog_url"]).strip()
                save_config(cfg); load_catalog()
            for k in ("character_on", "take_character"):
                if k in body:
                    cfg[k] = bool(body[k])
            if cfg["model"] not in MODELS:
                cfg["model"] = "gpt-image-2"
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
            cfg["character_desc"] = desc; cfg["character_on"] = True; save_config(cfg)
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


# ---------------------------------------------------------------- page
PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Render Post</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%23131211'/%3E%3Cg stroke='%23FF5A1E' stroke-width='2.4' stroke-linecap='round' fill='none'%3E%3Cpath d='M26 9h-6M14 9H6M26 16h-8M12 16H6M26 23h-4M16 23H6M17 6.5v5M10 13.5v5M19 20.5v5'/%3E%3C/g%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap">
<style>
  :root{
    --em-bg-0:#131211; --em-bg-1:#1B1918; --em-bg-2:#1C1A19; --em-bg-inset:#141312; --em-bg-raised:#33302C;
    --em-panel:rgba(28,26,25,.92); --em-dot:#26231F; --em-scrim:rgba(10,9,8,.5);
    --em-line:rgba(255,255,255,.07); --em-line-strong:rgba(255,255,255,.10); --em-line-bright:rgba(255,255,255,.18);
    --em-hover:rgba(255,255,255,.06); --em-chip:rgba(255,255,255,.08);
    --em-ink:#ECE8E3; --em-ink-dim:#97918A; --em-ink-faint:#6E6862;
    --em-accent:#FF5A1E; --em-on-accent:#131211; --em-ok:#5FB870; --em-warn:#E8B04B; --em-danger:#E05A4E;
    --em-font-ui:'Instrument Sans',system-ui,sans-serif; --em-font-mono:'JetBrains Mono',ui-monospace,monospace;
    --em-r-sm:7px; --em-r:8px; --em-r-md:9px; --em-r-lg:12px; --em-r-xl:16px;
    --em-blur:blur(14px); --em-shadow-panel:0 14px 40px rgba(0,0,0,.4); --em-shadow-modal:0 30px 80px rgba(0,0,0,.6);
    --em-ease:cubic-bezier(.2,.7,.3,1); --em-t-fast:120ms; --em-t-pop:140ms;
  }
  @keyframes em-pop{from{opacity:0;transform:translateY(6px) scale(.985)}to{opacity:1;transform:none}}
  @keyframes pulse{0%,100%{opacity:.35}50%{opacity:1}}
  *{box-sizing:border-box}
  [hidden]{display:none !important}
  html,body{margin:0}
  body{background:var(--em-bg-0);color:var(--em-ink);font-family:var(--em-font-ui);font-size:13px;-webkit-font-smoothing:antialiased;
    background-image:radial-gradient(circle,var(--em-dot) 1px,transparent 1px);background-size:28px 28px}
  ::selection{background:rgba(255,90,30,.35)}
  ::-webkit-scrollbar{width:8px;height:8px}::-webkit-scrollbar-thumb{background:#2E2B28;border-radius:4px}::-webkit-scrollbar-track{background:transparent}
  .label{font-family:var(--em-font-mono);font-size:9px;font-weight:500;letter-spacing:.12em;text-transform:uppercase;color:var(--em-ink-dim)}
  .dot{width:5px;height:5px;border-radius:50%;display:inline-block;background:var(--em-ink-faint);flex:none}
  .dot.ok{background:var(--em-ok)}.dot.bad{background:var(--em-danger)}.dot.warn{background:var(--em-warn)}.dot.live{background:var(--em-accent);animation:pulse 1.2s infinite}

  header{position:sticky;top:0;z-index:5;height:52px;display:flex;align-items:center;gap:20px;padding:0 16px;
    background:rgba(19,18,17,.82);backdrop-filter:var(--em-blur);border-bottom:1px solid var(--em-line)}
  header h1{margin:0;font-size:14px;font-weight:600;display:flex;align-items:center;gap:10px}
  header h1 i{width:8px;height:8px;border-radius:50%;background:var(--em-accent);display:inline-block}
  header .ver{font-family:var(--em-font-mono);font-size:10px;font-weight:500;color:var(--em-ink-faint);letter-spacing:.04em}
  header .update{font-family:var(--em-font-mono);font-size:11px;color:var(--em-accent);text-decoration:none;display:inline-flex;align-items:center;gap:6px}
  header .update::before{content:"";width:5px;height:5px;border-radius:50%;background:var(--em-accent)}
  .meta{font-family:var(--em-font-mono);font-size:11px;color:var(--em-ink-dim);display:flex;gap:6px;flex-wrap:wrap;min-width:0;overflow:hidden;white-space:nowrap}
  .meta b{color:var(--em-ink);font-weight:500}.meta s{text-decoration:none;color:var(--em-ink-faint)}
  .seg.views{margin-left:auto} .seg.wipeseg{margin-left:0} body[data-view="video"] .wipeseg,body[data-view="video"] .hints{display:none}
  body[data-view="video"] #setup,body[data-view="video"] #cards{display:none !important}
  body[data-view="picks"] #setup{display:none !important} body[data-view="picks"] article:not(.haspick){display:none !important}
  .pickbar{display:none;padding:12px 16px 0;font-size:13px;color:var(--em-ink-dim)} body[data-view="picks"] .pickbar{display:block}
  .pickbar b{color:var(--em-ink);font-weight:500}
  .viewbar{display:flex;align-items:center;gap:12px;padding:0 0 2px} body[data-view="video"] .viewbar,body[data-view="picks"] .viewbar{display:none}
  .viewbar .hint{font-size:12px;color:var(--em-ink-faint)} body[data-imgmode="detail"] .viewbar .hint{display:none}
  .imggrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
  .imggrid .gi{position:relative;border-radius:var(--em-r-md);overflow:hidden;border:1px solid var(--em-line);cursor:pointer;background:var(--em-bg-inset)}
  .imggrid .gi:hover{border-color:var(--em-line-bright)} .imggrid .gi.sel{border-color:rgba(255,90,30,.45)}
  .imggrid .gi img{width:100%;aspect-ratio:16/10;object-fit:cover;display:block}
  .imggrid .gi .cap{display:flex;justify-content:space-between;align-items:center;gap:6px;padding:7px 9px;font-family:var(--em-font-mono);font-size:11px;color:var(--em-ink)}
  .imggrid .gi .cap span{color:var(--em-ink-dim);display:flex;align-items:center;gap:5px}
  .imggrid .gi .st{position:absolute;top:8px;left:8px}
  body[data-imgmode="grid"][data-view="images"] #cards{display:none !important}
  .pickgrid{display:none;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;padding:10px 16px 0}
  body[data-view="picks"] .pickgrid{display:grid}
  .pickgrid .pg{position:relative;border-radius:var(--em-r-sm);overflow:hidden;border:1px solid var(--em-line);cursor:pointer;background:var(--em-bg-inset)}
  .pickgrid .pg img{width:100%;aspect-ratio:16/9;object-fit:cover;display:block} .pickgrid .pg:hover{border-color:var(--em-line-bright)}
  .pickgrid .pg span{position:absolute;left:6px;bottom:6px;padding:2px 6px;font-family:var(--em-font-mono);font-size:10px;background:var(--em-panel);border:1px solid var(--em-line-strong);border-radius:4px;color:var(--em-ink)}
  .seg{margin-left:auto;display:inline-flex;gap:2px;background:var(--em-bg-2);border:1px solid var(--em-line);border-radius:var(--em-r-md);padding:3px;flex:none}
  .seg button{border:none;cursor:pointer;font-family:var(--em-font-ui);font-size:12px;font-weight:500;padding:5px 12px;border-radius:var(--em-r-sm);
    background:transparent;color:var(--em-ink-dim);transition:background var(--em-t-fast),color var(--em-t-fast)}
  .seg button:hover{color:var(--em-ink)} .seg button[aria-pressed="true"]{background:var(--em-bg-raised);color:var(--em-ink)} .seg button:active{transform:translateY(1px)}
  .status{display:flex;align-items:center;gap:6px;font-family:var(--em-font-mono);font-size:11px;color:var(--em-ink-dim);flex:none}

  .btn{display:inline-flex;align-items:center;gap:6px;cursor:pointer;font-family:var(--em-font-ui);font-size:12px;font-weight:500;color:var(--em-ink);
    background:transparent;border:1px solid var(--em-line-strong);padding:5px 11px;border-radius:var(--em-r);transition:background var(--em-t-fast),border-color var(--em-t-fast),color var(--em-t-fast);white-space:nowrap}
  .btn:hover{background:var(--em-hover);border-color:var(--em-line-bright)} .btn:active{transform:translateY(1px)}
  .btn:disabled{opacity:.45;cursor:default;transform:none}
  .btn.solid{background:var(--em-accent);border-color:var(--em-accent);color:var(--em-on-accent);font-weight:600;padding:6px 14px}
  .btn.solid:hover{background:#FF6B35}
  .btn.quiet{border-color:transparent;color:var(--em-ink-dim)} .btn.quiet:hover{color:var(--em-ink)}
  .btn:focus-visible,.field:focus-visible,textarea:focus-visible,select:focus-visible{outline:2px solid var(--em-accent);outline-offset:2px}
  .btn svg{width:14px;height:14px;stroke:currentColor;fill:none;stroke-width:1.4;stroke-linecap:round;stroke-linejoin:round}
  .field,textarea,select{width:100%;background:var(--em-bg-inset);border:1px solid var(--em-line);border-radius:var(--em-r-md);padding:8px 12px;
    font-family:var(--em-font-ui);font-size:13px;color:var(--em-ink);outline:none;transition:border-color var(--em-t-fast)}
  .field:focus,textarea:focus,select:focus{border-color:var(--em-accent)}
  textarea{resize:vertical;line-height:1.55;min-height:64px}
  select{appearance:none;cursor:pointer;padding-right:28px;background-image:linear-gradient(45deg,transparent 50%,var(--em-ink-dim) 50%),linear-gradient(135deg,var(--em-ink-dim) 50%,transparent 50%);
    background-position:calc(100% - 16px) 15px,calc(100% - 11px) 15px;background-size:5px 5px;background-repeat:no-repeat}
  .field::placeholder,textarea::placeholder{color:var(--em-ink-faint)}

  main{padding:16px 16px 72px;display:grid;gap:16px;max-width:1800px;margin:0 auto}

  .setup{background:var(--em-bg-1);border:1px solid var(--em-line);border-radius:var(--em-r-lg);padding:14px;display:grid;gap:12px;animation:em-pop var(--em-t-pop) var(--em-ease) both}
  .setup .f{display:grid;gap:6px}
  .setup .controls{display:flex;gap:12px;align-items:end;flex-wrap:wrap}
  .setup .controls{align-items:start}
  .setup .controls .f{width:200px}
  .setup .controls .f.wide{width:300px}
  .setup .controls .hint{font-size:11px;color:var(--em-ink-faint);line-height:1.4}
  body:not(.more) .charblock,body:not(.more) .f.more{display:none !important}
  .charblock{display:grid;grid-template-columns:96px 1fr;gap:12px;align-items:start;padding:10px;border:1px solid var(--em-line);border-radius:var(--em-r-md);background:var(--em-bg-inset)}
  .charthumb{width:96px;aspect-ratio:3/4;border-radius:var(--em-r-sm);background:var(--em-bg-2);border:1px solid var(--em-line);display:grid;place-items:center;overflow:hidden;text-align:center;padding:4px}
  .charthumb img{width:100%;height:100%;object-fit:cover}
  .charbody{display:grid;gap:8px;min-width:0}
  .charbody .hint{font-size:11px;color:var(--em-ink-faint);line-height:1.4}
  .charrow{display:flex;gap:8px;align-items:center} .charrow .field{flex:1}
  .charblock.on{border-color:rgba(255,90,30,.4)}
  .linkbtn{float:right;margin-right:10px;border:none;background:transparent;color:var(--em-ink-faint);font-family:var(--em-font-mono);font-size:10px;letter-spacing:.06em;text-transform:none;cursor:pointer;padding:0} .linkbtn:hover{color:var(--em-accent)}
  .showall{float:right;display:inline-flex;align-items:center;gap:5px;text-transform:none;letter-spacing:0;font-size:10px;color:var(--em-ink-faint);cursor:pointer}
  .showall input{width:11px;height:11px;margin:0;accent-color:var(--em-accent)}
  .setup[data-kind="gpt"] .f.nano,.setup[data-kind="nano"] .f.gpt{display:none}
  .vstep .vhead{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
  .vstep .vhead .hint{font-size:12px;color:var(--em-ink-dim);margin-top:3px}
  .vstep[data-vmode="clips"] .takeonly,.vstep[data-vmode="take"] .clipsonly{display:none}
  .vstep[data-nores="1"][data-vmode="clips"] .resonly{display:none}
  .framegrid{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(320px,1fr))}
  .frame{background:var(--em-bg-inset);border:1px solid var(--em-line);border-radius:var(--em-r-md);overflow:hidden}
  .frame .name{font-family:var(--em-font-mono);font-size:11px;color:var(--em-ink);padding:8px 10px 0;display:flex;justify-content:space-between;gap:8px}
  .frame .name span{color:var(--em-ink-faint)}
  .frame .stack{display:grid;gap:6px;padding:8px 10px 10px}
  .ver{position:relative;border-radius:var(--em-r-sm);overflow:hidden;cursor:pointer;border:1px solid transparent;transition:border-color var(--em-t-fast)}
  .ver img{width:100%;aspect-ratio:16/9;object-fit:cover;display:block;opacity:.75;transition:opacity var(--em-t-fast)}
  .ver:hover img,.ver.on img{opacity:1} .ver.on{border-color:var(--em-accent)}
  .ver .tag{position:absolute;left:6px;bottom:6px;padding:2px 6px;font-family:var(--em-font-mono);font-size:9px;letter-spacing:.08em;background:var(--em-panel);border:1px solid var(--em-line-strong);border-radius:4px;color:var(--em-ink-dim)}
  .ver .ord{position:absolute;top:6px;right:6px;font-family:var(--em-font-mono);font-size:10px;background:var(--em-accent);color:var(--em-on-accent);border-radius:4px;padding:1px 6px;font-weight:600}
  .ver .star{position:absolute;top:6px;left:6px;color:var(--em-accent);font-size:11px}
  .frame .raw{opacity:.4;filter:grayscale(1)} .frame .raw.on{opacity:1;filter:none}
  .stitch .r{display:flex;align-items:center;gap:10px}
  .seg.small{margin-left:0} .seg.small button{padding:4px 10px;font-size:12px}
  .pickstrip{display:flex;gap:8px;flex-wrap:wrap}
  .pk{position:relative;width:240px;background:var(--em-bg-inset);border:1px solid var(--em-line);border-radius:var(--em-r);overflow:hidden;cursor:pointer;user-select:none}
  .pk img{width:100%;aspect-ratio:16/9;object-fit:cover;display:block;opacity:.55;transition:opacity var(--em-t-fast)}
  .pk.on img{opacity:1} .pk.on{border-color:var(--em-line-bright)}
  .pk .cap{font-family:var(--em-font-mono);font-size:11px;color:var(--em-ink-dim);padding:5px 7px;display:flex;justify-content:space-between;align-items:center;gap:4px}
  .pk .cap b{color:var(--em-ink);font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .pk .ord{position:absolute;top:6px;left:6px;font-family:var(--em-font-mono);font-size:10px;background:var(--em-accent);color:var(--em-on-accent);border-radius:4px;padding:1px 5px;font-weight:600}
  .pk .mv{display:none;gap:2px} .vstep[data-vmode="take"] .pk .mv{display:inline-flex}
  .pk .mv button{border:none;background:transparent;color:var(--em-ink-dim);cursor:pointer;font-size:11px;padding:0 3px} .pk .mv button:hover{color:var(--em-ink)}
  .clips{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(420px,1fr))}
  .clip{background:var(--em-bg-inset);border:1px solid var(--em-line);border-radius:var(--em-r-md);overflow:hidden;display:flex;flex-direction:column}
  .clip .media{position:relative;aspect-ratio:16/9;background:#0e0d0c}
  .clip .media video,.clip .media img{width:100%;height:100%;object-fit:contain;display:block}
  .clip .media img{opacity:.5}
  .clip .media .working{position:absolute;inset:0;display:grid;place-items:center}
  .clip .body{padding:10px 10px 10px;display:flex;flex-direction:column;gap:8px}
  .clip .top{display:flex;align-items:center;justify-content:space-between;gap:8px;font-family:var(--em-font-mono);font-size:11px;color:var(--em-ink-dim)}
  .clip .top label{display:flex;align-items:center;gap:6px;color:var(--em-ink)}
  .inreel{position:absolute;top:10px;left:10px;display:inline-flex;align-items:center;gap:8px;padding:6px 10px 6px 8px;border-radius:var(--em-r);cursor:pointer;
    background:var(--em-panel);backdrop-filter:var(--em-blur);border:1px solid var(--em-line-strong);font-family:var(--em-font-mono);font-size:11px;color:var(--em-ink);user-select:none}
  .inreel input{width:14px;height:14px;margin:0;accent-color:var(--em-accent);cursor:pointer}
  .inreel.on{border-color:rgba(255,90,30,.5);color:var(--em-accent)}
  .inreel .ord{display:inline-block;min-width:16px;text-align:center;background:var(--em-accent);color:var(--em-on-accent);border-radius:4px;padding:0 4px;margin-right:6px;font-weight:600}
  .clip textarea{min-height:64px;font-size:12px}
  .clip .actions{justify-content:space-between}
  .clip .actions .r{display:flex;gap:6px}
  .bar.stitch{border-top:1px solid var(--em-line);padding-top:12px}
  .f.inline{display:flex;align-items:center;gap:8px;width:auto} .f.inline select{width:auto;padding-right:26px}
  .video .bar .l .hint{font-size:11px;color:var(--em-ink-faint)}
  .setup .hint{font-size:12px;color:var(--em-ink-dim);line-height:1.5}
  .setup .hint b{color:var(--em-ink);font-weight:500}
  .setup .bar{display:flex;align-items:center;gap:10px;justify-content:space-between;flex-wrap:wrap}
  .setup .bar .l,.setup .bar .r{display:flex;align-items:center;gap:8px;min-width:0}
  .setup .bar .l .hint{margin-right:6px}
  .btn.icon{padding:5px 10px 5px 8px;color:var(--em-ink-dim)} .btn.icon:hover{color:var(--em-ink)}
  .saved a{color:var(--em-accent);text-decoration:none}
  .saved{font-family:var(--em-font-mono);font-size:11px;color:var(--em-ink-dim);display:inline-flex;align-items:center;gap:6px;min-width:70px}

  article{background:var(--em-bg-1);border:1px solid var(--em-line);border-radius:var(--em-r-lg);overflow:hidden;
    display:grid;grid-template-columns:minmax(0,1fr) 400px;animation:em-pop var(--em-t-pop) var(--em-ease) both}
  article:hover,article:focus-within{border-color:var(--em-line-strong)}
  @media (max-width:1000px){article{grid-template-columns:1fr}}
  .stage{position:relative;background:var(--em-bg-inset);aspect-ratio:var(--ar,16/9);max-height:80vh;overflow:hidden;border-right:1px solid var(--em-line)}
  @media (max-width:1000px){.stage{border-right:0;border-bottom:1px solid var(--em-line)}}
  .stage img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;display:block;user-select:none;-webkit-user-drag:none}
  .stage img.after{clip-path:inset(0 0 0 var(--cut,50%))}
  .stage[data-mode="before"] img.after{display:none}
  .stage[data-mode="after"] img.before{display:none}
  .stage[data-mode="after"] img.after{clip-path:none}
  .stage[data-mode="before"] .wipe,.stage[data-mode="after"] .wipe,.stage.noafter .wipe,.stage.noafter .tag.r{display:none}
  .wipe{position:absolute;inset:0}
  .wipe input{position:absolute;inset:0;width:100%;height:100%;margin:0;opacity:0;cursor:ew-resize}
  .wipe .handle{position:absolute;top:0;bottom:0;left:var(--cut,50%);width:1px;background:var(--em-accent);pointer-events:none}
  .wipe .handle::after{content:"";position:absolute;top:50%;left:50%;width:22px;height:22px;transform:translate(-50%,-50%);border-radius:50%;background:var(--em-accent);box-shadow:0 6px 18px rgba(0,0,0,.5)}
  .tag{position:absolute;bottom:10px;padding:4px 8px;border-radius:var(--em-r-sm);background:var(--em-panel);backdrop-filter:var(--em-blur);border:1px solid var(--em-line-strong);pointer-events:none}
  .tag.l{left:10px}.tag.r{right:10px}
  .stage[data-mode="after"] .tag.l,.stage[data-mode="before"] .tag.r{display:none}
  .working{position:absolute;inset:0;display:grid;place-items:center;background:rgba(19,18,17,.55);backdrop-filter:blur(2px)}
  .working .cancel{margin-left:6px;padding:3px 8px;font-size:11px}
  .working span{display:flex;align-items:center;gap:8px;padding:6px 6px 6px 12px;border-radius:var(--em-r);background:var(--em-panel);border:1px solid var(--em-line-strong);font-family:var(--em-font-mono);font-size:11px;color:var(--em-ink)}

  aside{padding:14px;display:flex;flex-direction:column;gap:10px;min-width:0}
  aside h2{margin:0;font-size:15px;font-weight:600;word-break:break-all;line-height:1.3;display:flex;align-items:center;gap:8px}
  .selbox input{width:14px;height:14px;margin:0;accent-color:var(--em-accent);cursor:pointer}
  article.sel{border-color:rgba(255,90,30,.45)}
  .vseg{display:inline-flex;gap:2px;background:var(--em-bg-2);border:1px solid var(--em-line);border-radius:var(--em-r-sm);padding:2px;flex:none}
  .vseg button{border:none;cursor:pointer;font-family:var(--em-font-mono);font-size:10px;font-weight:500;padding:3px 8px;border-radius:5px;background:transparent;color:var(--em-ink-dim)}
  .vseg button:hover{color:var(--em-ink)} .vseg button[aria-pressed="true"]{background:var(--em-bg-raised);color:var(--em-ink)}
  .facts{display:grid;grid-template-columns:auto 1fr;gap:4px 14px;align-items:center;font-family:var(--em-font-mono);font-size:11px;color:var(--em-ink-dim)}
  .facts b{color:var(--em-ink);font-weight:500;display:flex;align-items:center;gap:6px}
  .row{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:2px}
  aside textarea{min-height:150px;max-height:none;font-size:12.5px;field-sizing:content;overflow:hidden}
  .err[hidden]{display:none}
  .err{font-family:var(--em-font-mono);font-size:11px;line-height:1.5;color:var(--em-danger);background:var(--em-bg-inset);border:1px solid var(--em-line);border-radius:var(--em-r-md);padding:10px 12px;word-break:break-word}
  .actions{display:flex;gap:8px;align-items:center;justify-content:flex-end;flex-wrap:wrap}
  .btn.pick.on{color:var(--em-accent);border-color:rgba(255,90,30,.4)} .btn.pick.on svg{fill:currentColor}
  @keyframes flash{0%{border-color:var(--em-accent);box-shadow:0 0 0 3px rgba(255,90,30,.25)}100%{border-color:var(--em-line);box-shadow:none}}
  .video.flash{animation:flash 1.4s var(--em-ease)}
  .btn.tovideo{width:100%;justify-content:center;margin-top:4px}
  .empty{padding:80px 0;text-align:center;display:grid;gap:12px;justify-items:center;color:var(--em-ink-dim)}

  .scrim[hidden]{display:none}
  .scrim{position:fixed;inset:0;background:var(--em-scrim);backdrop-filter:blur(2px);display:grid;place-items:center;z-index:20}
  .modal{width:420px;max-width:calc(100vw - 24px);background:rgba(24,22,21,.98);backdrop-filter:blur(20px);border:1px solid var(--em-line-strong);border-radius:var(--em-r-xl);
    box-shadow:var(--em-shadow-modal);padding:20px;display:grid;gap:12px;animation:em-pop var(--em-t-pop) var(--em-ease)}
  .modal h2{margin:0;font-size:16px;font-weight:600}
  .modal p{margin:0;color:var(--em-ink-dim);line-height:1.5}
  .modal a{color:var(--em-accent);text-decoration:none}
  .modal .actions{margin-top:4px}
  .recent{display:grid;gap:4px;max-height:40vh;overflow:auto}
  .recent button{text-align:left;font-family:var(--em-font-mono);font-size:11px;color:var(--em-ink);background:var(--em-bg-inset);border:1px solid var(--em-line);border-radius:var(--em-r-sm);padding:8px 10px;cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .recent button:hover{border-color:var(--em-line-bright);background:var(--em-hover)}
  .recent .none{font-size:12px;color:var(--em-ink-faint)}
  body.dropping::after{content:"Drop renders to add them to this project";position:fixed;inset:12px;border:2px dashed var(--em-accent);border-radius:var(--em-r-xl);background:rgba(19,18,17,.75);display:grid;place-items:center;font-size:16px;color:var(--em-ink);z-index:25;pointer-events:none}
  .toasts{position:fixed;right:14px;bottom:14px;display:grid;gap:8px;z-index:30;max-width:380px}
  .toast{padding:10px 14px;border-radius:var(--em-r-md);background:var(--em-panel);backdrop-filter:var(--em-blur);border:1px solid var(--em-line-strong);box-shadow:var(--em-shadow-panel);font-size:13px;color:var(--em-ink);display:flex;gap:10px;align-items:flex-start;animation:em-pop var(--em-t-pop) var(--em-ease)}
  .toast.bad{border-color:rgba(224,90,78,.5)} .toast.ok{border-color:rgba(95,184,112,.4)}
  .toast .dot{margin-top:6px}
  .hints{position:fixed;left:14px;bottom:12px;display:flex;gap:14px;font-family:var(--em-font-mono);font-size:10px;color:var(--em-ink-faint);pointer-events:none}
  .hints b{color:var(--em-ink-dim);font-weight:500;margin-right:4px}
  .hints{transition:opacity .3s} body.scrolled .hints{opacity:0}
  @media (prefers-reduced-motion:reduce){article,.setup,.modal{animation:none}.dot.live{animation:none}}
</style>
</head>
<body>
<header>
  <h1><i></i>Render Post <span class="ver" id="ver"></span></h1>
  <a class="update" id="update" href="#" target="_blank" rel="noopener" hidden></a>
  <div class="meta" id="meta"></div>
  <div class="seg views" role="group" aria-label="Section">
    <button data-view="images" aria-pressed="true">Images</button>
    <button data-view="picks" id="pickstab">Picks</button>
    <button data-view="video" id="videotab">Video</button>
  </div>
  <div class="seg wipeseg" role="group" aria-label="View">
    <button data-mode="before">Before</button>
    <button data-mode="wipe" aria-pressed="true">Wipe</button>
    <button data-mode="after">After</button>
  </div>
  <div class="status" id="spend" title="Estimated spend on this project, from fal's published rates. GPT Image 2 counts as $0.25 per image."></div>
  <div class="status" id="status"></div>
  <button class="btn" id="stop" type="button" hidden title="Cancel everything queued or in progress">Stop</button>
  <button class="btn quiet" id="quit" type="button" title="Stops Render Post">Quit</button>
</header>

<main id="main">
  <section class="setup" id="setup">
    <div class="f">
      <span class="label">Style notes · used whenever a prompt is written</span>
      <textarea id="notes" rows="2" placeholder="Optional, in plain English. e.g. cooler white balance, dusk lighting, no people, autumn trees. Prompts already written keep their text; press New batch or Rewrite to apply notes to them."></textarea>
    </div>
    <div class="morewrap" id="morewrap">
    <div class="charblock" id="charblock">
      <div class="charthumb" id="charthumb"><span class="label">No character</span></div>
      <div class="charbody">
        <div class="row"><span class="label">Character · off by default</span>
          <label class="showall" style="float:none"><input type="checkbox" id="charon"> use in enhancements and angles</label></div>
        <div class="hint">One consistent person across the whole set. Generate one from a description, or upload a person you have the rights to use. Real photos of strangers are a rights problem and trip model filters; generated people are safest.</div>
        <div class="charrow">
          <input class="field" id="chardesc" placeholder="Describe a person to generate, e.g. woman in her 30s, dark hair tied back, linen shirt, tailored trousers">
          <button class="btn" id="chargen" type="button">Generate</button>
          <button class="btn quiet" id="charupload" type="button">Upload</button>
          <button class="btn quiet" id="charclear" type="button" hidden>Remove</button>
          <input type="file" id="charfile" accept="image/*" hidden>
        </div>
        <input class="field" id="charnote" placeholder="Optional notes about how they appear: seated, reading, carrying a bag, never facing camera…">
      </div>
    </div>
    <div class="controls">
      <div class="f wide"><span class="label">Model <label class="showall"><input type="checkbox" id="showall"> show all</label><button class="linkbtn" id="catalogbtn" type="button" title="Where extra models come from">catalog</button></span><select id="model"></select><span class="hint" id="modelhint"></span></div>
      <div class="f gpt"><span class="label">Quality</span><select id="quality"></select></div>
      <div class="f gpt"><span class="label">Output size · long edge</span><select id="size"></select></div>
      <div class="f nano"><span class="label">Resolution</span><select id="resolution"></select></div>
      <div class="f wide"><span class="label">Before spending credits</span><select id="review"><option value="1">Write prompts first, let me review</option><option value="0">Enhance straight away</option></select></div>
      <div class="f more"><span class="label">Variations</span><select id="variations"></select></div>
      <div class="f more"><span class="label">Angles per run</span><select id="angles"></select></div>
      <div class="f more"><span class="label">Spend warning at</span><div class="f inline"><span class="label">$</span><input class="field" id="spendalert" type="number" min="1" step="1" style="width:90px"></div></div>
    </div>
    </div>
    <div class="bar">
      <div class="l">
        <button class="btn quiet" id="moretoggle" type="button">More</button>
        <div class="hint" id="folderhint"></div>
        <button class="btn icon" id="switchfolder" type="button" title="Work on a different folder of renders"><svg viewBox="0 0 16 16"><path d="M2 4.5A1.5 1.5 0 0 1 3.5 3h3l1.5 1.5h4.5A1.5 1.5 0 0 1 14 6v5.5a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 11.5z"/><path d="M8 7v4M6 9h4"/></svg>New project</button>
        <button class="btn icon" id="openfolder" type="button" title="Open the enhanced folder"><svg viewBox="0 0 16 16"><path d="M2 4.5A1.5 1.5 0 0 1 3.5 3h3l1.5 1.5h4.5A1.5 1.5 0 0 1 14 6v5.5a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 11.5z"/></svg>Open folder</button>
        <button class="btn icon" id="rescan" type="button" title="Look for renders added since launch"><svg viewBox="0 0 16 16"><path d="M13 8a5 5 0 1 1-1.5-3.6"/><path d="M13 2.5v3h-3"/></svg>Rescan</button>
      </div>
      <div class="r">
        <span class="saved" id="selinfo" hidden></span>
        <span class="saved" id="estimate"></span>
        <span class="saved" id="stale" hidden></span>
        <span class="saved" id="saved"></span>
        <button class="btn quiet" id="exportimg" type="button" hidden title="Save every image prompt with its version file and the fal-hosted raw URL to enhanced/prompts-export.json">Export prompts</button>
        <button class="btn quiet" id="keybtn" type="button">Change key</button>
        <button class="btn" id="run" type="button">Write prompts</button>
        <button class="btn" id="newbatch" type="button" title="Write a fresh prompt for every image using the current style notes">New batch</button>
        <button class="btn solid" id="enhance" type="button">Enhance all</button>
      </div>
    </div>
  </section>
  <div class="viewbar" id="viewbar"><div class="seg small" role="group" aria-label="Layout"><button data-imgmode="grid">Grid</button><button data-imgmode="detail" aria-pressed="true">Detail</button></div><span class="hint" id="gridhint">Grid shows the latest version of each image; click one to open it.</span></div>
  <div class="imggrid" id="imggrid" hidden></div>
  <div class="pickbar" id="pickbar"></div>
  <div class="pickgrid" id="pickgrid"></div>
  <div id="cards"></div>

  <div id="videoview" hidden>
    <section class="setup vstep" id="vframes">
      <div class="vhead"><div><span class="label">Step 1 · Frames</span><div class="hint">Click a version to add it to the video set. Click again to remove. Order is the order you add them.</div></div>
        <span class="saved" id="framecount"></span></div>
      <div class="framegrid" id="framegrid"></div>
    </section>

    <section class="setup vstep" id="vmakepanel">
      <div class="vhead"><div><span class="label">Step 2 · Make clips</span><div class="hint" id="vexplain"></div></div>
        <div class="seg small" role="group" aria-label="Video mode">
          <button data-vmode="clips" aria-pressed="true" title="Each frame becomes its own separate video">Separate videos</button>
          <button data-vmode="take" title="One video that travels through all frames in order · always Seedance · experimental">One video through all frames</button>
        </div></div>
      <div class="f"><span class="label">Motion notes · used whenever a motion prompt is written</span>
        <textarea id="mnotes" rows="2" placeholder="Optional. e.g. slow push-ins only, no people, evening ambience, keep it still and calm."></textarea></div>
      <div class="controls">
        <div class="f wide clipsonly"><span class="label">Video model <label class="showall"><input type="checkbox" id="vshowall"> show all</label></span><select id="vmodel"></select><span class="hint" id="vmodelhint"></span></div>
        <div class="f clipsonly"><span class="label">Shots per clip</span><select id="shots"><option value="1">1 · one continuous camera move</option><option value="2">2 · cuts to a second angle</option><option value="3">3 · cuts through three angles</option></select></div>
        <div class="f resonly"><span class="label">Resolution</span><select id="vres"></select></div>
        <div class="f clipsonly"><span class="label">Clip length</span><select id="vdur"></select></div>
        <div class="f takeonly"><span class="label">Take length</span><select id="tdur"></select></div>
        <div class="f takeonly wide"><span class="label">Character in the take</span><label class="showall" style="float:none;font-size:12px;color:var(--em-ink)"><input type="checkbox" id="takechar"> add the project character as a reference</label><span class="hint">Seedance reference-to-video with the character as the last @Image. Its filter may refuse realistic people; a generated character passes more often.</span></div>
        <div class="f"><span class="label">Sound</span><select id="vaudio"><option value="1">Ambient audio</option><option value="0">Silent</option></select></div>
        <div class="f"><span class="label">Camera energy</span><select id="energy"><option value="calm">Calm · barely moves</option><option value="moderate">Moderate · clear move</option><option value="dynamic">Dynamic · bold, real parallax</option></select></div>
      </div>
      <div class="f"><span class="label">Video set<span class="takeonly"> · order matters, use the arrows</span></span><div class="pickstrip" id="pickstrip"></div></div>
      <div class="bar">
        <div class="l"><span class="saved" id="vestimate"></span></div>
        <div class="r">
          <button class="btn quiet" id="vexport" type="button" hidden title="Save every motion prompt with its hosted frame URL to enhanced/video/prompts-export.json, for use in other video tools">Export prompts</button>
          <button class="btn quiet" id="vclear" type="button" hidden title="Remove prompts that haven't been sent">Clear unsent</button>
          <button class="btn" id="vprompts" type="button">Write motion prompts</button>
          <button class="btn solid" id="vmake" type="button">Make clips</button>
        </div>
      </div>
      <div class="clips" id="clips"></div>
    </section>

    <section class="setup vstep" id="vreel">
      <div class="vhead"><div><span class="label">Step 3 · Reel</span><div class="hint">Press "Add to reel" on finished clips in the order you want them; the badge shows each clip's place. Crossfade and optional music. Made on this computer, free.</div></div>
        <button class="btn icon" id="openvideo" type="button" title="Open the video folder"><svg viewBox="0 0 16 16"><path d="M2 4.5A1.5 1.5 0 0 1 3.5 3h3l1.5 1.5h4.5A1.5 1.5 0 0 1 14 6v5.5a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 11.5z"/></svg>Open video folder</button></div>
      <div class="bar stitch" id="stitchbar">
        <div class="l">
          <div class="f inline"><span class="label">Crossfade</span><select id="crossfade"><option value="0">Cut</option><option value="0.4">0.4 s</option><option value="0.6">0.6 s</option><option value="1">1 s</option></select></div>
          <div class="f inline"><span class="label">Music</span><select id="music"><option value="">None</option></select><button class="btn icon" id="openmusic" type="button" title="Open the render folder. Drop an mp3 or wav there and it appears in this list."><svg viewBox="0 0 16 16"><path d="M2 4.5A1.5 1.5 0 0 1 3.5 3h3l1.5 1.5h4.5A1.5 1.5 0 0 1 14 6v5.5a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 11.5z"/></svg></button></div>
          <div class="f inline" id="mstartwrap" hidden><span class="label">Start at</span><input class="field" id="mstart" type="number" min="0" step="1" value="0" style="width:74px" title="Seconds into the track to start from"> <span class="label">s</span></div>
          <span class="hint" id="musichint">No tracks yet: press the folder button, drop an mp3 or wav in, then Rescan.</span>
        </div>
        <div class="r"><span class="saved" id="stitchhint"></span><button class="btn solid" id="stitch" type="button">Stitch</button></div>
      </div>
      <div class="clips" id="reels"></div>
    </section>
  </div>
</main>

<div class="scrim" id="keymodal" hidden>
  <div class="modal">
    <h2>Add your fal key</h2>
    <p>This tool runs on your own fal.ai account. Create a key at <a href="https://fal.ai/dashboard/keys" target="_blank" rel="noopener">fal.ai/dashboard/keys</a> and paste it here. It's stored on this computer only, never inside your render folder.</p>
    <input class="field" id="keyinput" type="password" placeholder="Paste key" autocomplete="off" spellcheck="false">
    <div class="err" id="keyerr" hidden></div>
    <div class="actions"><button class="btn quiet" id="keycancel" type="button" hidden>Cancel</button><button class="btn solid" id="keysave" type="button">Save key</button></div>
  </div>
</div>

<div class="scrim" id="catalogmodal" hidden>
  <div class="modal" style="width:560px">
    <h2>Model catalog</h2>
    <p>Extra models come from a JSON file at a URL you host (GitHub raw file, your site, anywhere public). Render Post reads it on launch and merges it over the built-in models, so new models can be added or re-priced without a new build. Models marked <span class="mono">recommended</span> show by default; the rest sit behind "show all".</p>
    <input class="field" id="catalogurl" placeholder="https://…/renderpost-models.json" spellcheck="false">
    <div class="hint" id="catalogstatus" style="font-family:var(--em-font-mono);font-size:11px;color:var(--em-ink-dim)"></div>
    <details><summary class="label" style="cursor:pointer">File format</summary>
<pre class="mono" style="font-size:10.5px;line-height:1.5;color:var(--em-ink-dim);background:var(--em-bg-inset);border:1px solid var(--em-line);border-radius:var(--em-r-sm);padding:10px;overflow:auto;max-height:36vh">{
  "image": {
    "my-model": {
      "label": "My Model · Vendor",
      "endpoint": "vendor/my-model/edit",
      "kind": "nano",                  // "nano": image_urls + resolution; "gpt": image_urls + quality + image_size
      "recommended": false,
      "hint": "what it's good at · price",
      "price": 0.10, "mult": {"1K": 1, "2K": 1, "4K": 2}
    }
  },
  "video": {
    "my-video": {
      "label": "My Video · Vendor",
      "i2v": "vendor/my-video/image-to-video",   // must accept prompt, image_url, duration, resolution
      "recommended": false,
      "hint": "what it's good at · price",
      "res": {"480p": "480p", "720p": "720p"},   // omit if the model has no resolution setting
      "min_duration": 5,
      "price": {"480p": 0.05, "720p": 0.08}      // per second, keyed by resolution, or {"audio": x, "silent": y}
    }
  }
}</pre></details>
    <div class="actions"><button class="btn quiet" id="catalogcancel" type="button">Cancel</button><button class="btn solid" id="catalogsave" type="button">Save and reload</button></div>
  </div>
</div>
<div class="scrim" id="foldermodal" hidden>
  <div class="modal">
    <h2>Open a folder of renders</h2>
    <p>Each folder is its own project: its own versions, notes and video set. Nothing here is lost when you switch.</p>
    <div id="recentlist" class="recent"></div>
    <div class="actions"><button class="btn quiet" id="foldercancel" type="button">Cancel</button><button class="btn solid" id="folderbrowse" type="button">Browse…</button></div>
  </div>
</div>
<div class="scrim" id="askmodal" hidden>
  <div class="modal" style="width:420px"><h2 id="asktitle">Confirm</h2><p id="askbody"></p>
    <div class="actions"><button class="btn quiet" id="askno" type="button">Cancel</button><button class="btn solid" id="askyes" type="button">Continue</button></div></div>
</div>
<div class="toasts" id="toasts"></div>
<div class="hints"><span><b>1 2 3</b>view</span><span><b>J K</b>next · prev</span><span><b>drag</b>wipe</span></div>

<script>
const $ = (s, el=document) => el.querySelector(s);
function toast(msg, kind="bad", ms=5000){ const t = document.createElement("div"); t.className = "toast " + kind; t.innerHTML = `<i class="dot ${kind}"></i><span>${esc(msg)}</span>`; $("#toasts").appendChild(t); setTimeout(() => t.remove(), ms); }
function ask(body, title="Confirm", yes="Continue"){ return new Promise(res => { $("#asktitle").textContent = title; $("#askbody").textContent = body; $("#askyes").textContent = yes; const m = $("#askmodal"); m.hidden = false;
  const done = v => { m.hidden = false; m.hidden = true; $("#askyes").onclick = $("#askno").onclick = null; res(v); }; $("#askyes").onclick = () => done(true); $("#askno").onclick = () => done(false); $("#askyes").focus(); }); }
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const api = (p, body) => fetch(p, body ? {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)} : {}).then(r => r.json());
let S = null, mode = "wipe", cards = {}, dirtyNotes = false, saveTimer = null, selected = new Set(), imgmode = "detail";
let vmode = "clips", frames = [], clipEls = {}, reelEls = {}, stitchSel = new Set(), view = "images";

function setSaved(t){ $("#saved").innerHTML = t ? `<i class="dot ok"></i>${t}` : ""; }
async function saveNow(extra={}){
  clearTimeout(saveTimer);
  await api("/api/config", {model:$("#model").value, quality:$("#quality").value, long_edge:$("#size").value, resolution:$("#resolution").value,
    variations:$("#variations").value, angles:$("#angles").value, style_notes:$("#notes").value, review_first:$("#review").value === "1",
    character_on:$("#charon").checked, character_note:$("#charnote").value, take_character:!!($("#takechar") && $("#takechar").checked),
    video_res:$("#vres").value, video_duration:$("#vdur").value, take_duration:$("#tdur").value, video_audio:$("#vaudio").value === "1",
    crossfade:$("#crossfade").value, motion_notes:$("#mnotes").value, shots:$("#shots").value, video_frames: JSON.stringify(frames), video_model:$("#vmodel").value, show_all_models:$("#showall").checked, energy:$("#energy").value, ...extra});
  Object.assign(S.config, {style_notes:$("#notes").value, model:$("#model").value, quality:$("#quality").value, long_edge:$("#size").value, resolution:$("#resolution").value, variations:$("#variations").value, angles:$("#angles").value,
    video_model:$("#vmodel").value, video_res:$("#vres").value, video_duration:$("#vdur").value, take_duration:$("#tdur").value, video_audio:$("#vaudio").value === "1", crossfade:$("#crossfade").value, motion_notes:$("#mnotes").value, shots:$("#shots").value, video_frames: JSON.stringify(frames)});
  setSaved("Saved"); setTimeout(() => setSaved(""), 1500);
}
function saveConfig(extra={}){
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => saveNow(extra).then(render), 250);
}

function modelOpts(table, all){ return Object.fromEntries(Object.entries(table).filter(([k,v]) => all || v.recommended).map(([k,v]) => [k, v.label])); }
function syncModel(){ const m = S.models[$("#model").value]; if (!m) return; $("#setup").dataset.kind = m.kind; $("#modelhint").textContent = m.hint + (m.price ? " · fal rates as of Aug 2026" : ""); }
function fillModels(){
  const extra = Object.values(S.models).some(v => !v.recommended) || Object.values(S.video.models).some(v => !v.recommended);
  for (const el of document.querySelectorAll(".showall")) el.hidden = !extra;
  const all = $("#showall").checked;
  const cur = $("#model").value || S.config.model; fill($("#model"), modelOpts(S.models, all || !(S.models[cur] || {}).recommended), cur); if (!$("#model").value) $("#model").selectedIndex = 0;
  const vcur = $("#vmodel").value || S.config.video_model; fill($("#vmodel"), modelOpts(S.video.models, all || !(S.video.models[vcur] || {}).recommended), vcur); if (!$("#vmodel").value) $("#vmodel").selectedIndex = 0;
  syncModel(); syncVideoModel();
}
function syncVideoModel(){
  const m = S.video.models[$("#vmodel").value]; if (!m) return;
  const panel = $("#vmakepanel"); panel.dataset.nores = m.res ? "0" : "1";
  if (m.res) { const cur = $("#vres").value; fill($("#vres"), m.res, m.res[cur] ? cur : Object.keys(m.res)[0]); }
  const minD = m.min_duration || 1, cur = $("#vdur").value;
  fill($("#vdur"), Object.fromEntries(Object.entries(S.video.durations).filter(([k]) => Number(k) >= minD)), Number(cur) >= minD ? cur : String(minD));
  $("#vmodelhint").textContent = m.hint || "";
}
function estimate(count){
  const m = S.models[$("#model").value], n = Number($("#variations").value);
  if (!m.price) return `${count * n} generation${count*n===1?"":"s"} · token priced`;
  const cost = m.price * (m.mult[$("#resolution").value] || 1) * n * count;
  return `${count * n} generation${count*n===1?"":"s"} · about $${cost.toFixed(2)}`;
}
function fill(sel, opts, val){ sel.innerHTML = Object.entries(opts).map(([k,v]) => `<option value="${k}"${k===val?" selected":""}>${v}</option>`).join(""); }

async function boot(){
  S = await api("/api/state");
  fill($("#quality"), S.quality_options, S.config.quality);
  fill($("#size"), S.size_options, S.config.long_edge);
  fill($("#resolution"), S.res_options, S.config.resolution);
  fill($("#variations"), S.variation_options, S.config.variations);
  fill($("#angles"), S.angle_options, S.config.angles || "6");
  fill($("#vres"), S.video.res, S.config.video_res); fill($("#vdur"), S.video.durations, S.config.video_duration); fill($("#tdur"), S.video.take_durations, S.config.take_duration);
  $("#vaudio").value = S.config.video_audio === false ? "0" : "1"; $("#crossfade").value = S.config.crossfade || "0.6"; $("#mnotes").value = S.config.motion_notes || ""; $("#shots").value = S.config.shots || "1"; $("#energy").value = S.config.energy || "calm";
  try { frames = JSON.parse(S.config.video_frames || "[]"); } catch { frames = []; }
  $("#showall").checked = $("#vshowall").checked = !!S.config.show_all_models;
  $("#model").value = S.config.model; $("#vmodel").value = S.config.video_model || "h3max";
  fillModels(); $("#vres").value = S.config.video_res; syncVideoModel();
  for (const id of ["showall","vshowall"]) $("#"+id).addEventListener("change", e => { $("#showall").checked = $("#vshowall").checked = e.target.checked; fillModels(); saveConfig(); renderVideo(); });
  $("#vmodel").addEventListener("change", () => { syncVideoModel(); saveConfig(); renderVideo(); });
  for (const id of ["vres","vdur","tdur","vaudio","crossfade","shots","energy","takechar"]) $("#"+id).addEventListener("change", () => { saveConfig(); renderVideo(); });
  $("#takechar").checked = !!S.config.take_character;
  for (const b of document.querySelectorAll("[data-view]")) b.addEventListener("click", () => setView(b.dataset.view));
  document.body.dataset.view = "images"; imgmode = S.config.img_mode || "detail"; document.body.dataset.imgmode = imgmode;
  for (const b of document.querySelectorAll("[data-imgmode]")) { b.setAttribute("aria-pressed", b.dataset.imgmode === imgmode); b.addEventListener("click", () => { imgmode = b.dataset.imgmode; document.body.dataset.imgmode = imgmode; for (const o of document.querySelectorAll("[data-imgmode]")) o.setAttribute("aria-pressed", o === b); api("/api/config", {img_mode: imgmode}); render(); }); }
  $("#mnotes").addEventListener("input", () => saveConfig());
  for (const b of document.querySelectorAll("[data-vmode]")) b.addEventListener("click", () => { vmode = b.dataset.vmode; for (const o of document.querySelectorAll("[data-vmode]")) o.setAttribute("aria-pressed", o === b); renderVideo(); });
  $("#vprompts").addEventListener("click", () => videoPrompts());
  $("#vclear").addEventListener("click", async () => { await api("/api/video/clear_drafts", {}); poll(); });
  $("#vexport").addEventListener("click", async () => { const b = $("#vexport"); const r = await api("/api/video/export", {}); b.textContent = r.error ? "Failed" : `Saved ${r.count} to video folder`; setTimeout(() => b.textContent = "Export prompts", 2200); });
  $("#vmake").addEventListener("click", () => videoMake());
  $("#stitch").addEventListener("click", () => stitch());
  $("#openvideo").addEventListener("click", () => api("/api/open", {which: "video"}));
  $("#openmusic").addEventListener("click", () => api("/api/open", {which: "root"}));
  S.clips = S.clips || [];
  $("#notes").value = S.config.style_notes || "";
  $("#review").value = S.config.review_first === false ? "0" : "1";
  $("#ver").textContent = "v" + S.version;
  $("#folderhint").innerHTML = `<b>${S.items.length}</b> render${S.items.length===1?"":"s"} in <b>${esc(S.folder)}</b>${S.demo ? " · demo mode, nothing is sent to fal" : ""}`;
  S.recent = S.recent || []; S.catalog = S.catalog || {}; S.spend = S.spend || 0;
  for (const id of ["quality","size","resolution","variations","review"]) $("#"+id).addEventListener("change", () => saveConfig());
  $("#angles").addEventListener("change", () => { saveConfig(); for (const a of Object.values(cards)) a.dataset.sig = ""; render(); });
  $("#model").addEventListener("change", () => { syncModel(); saveConfig(); });
  $("#openfolder").addEventListener("click", () => api("/api/open", {which: "enhanced"}));
  $("#switchfolder").addEventListener("click", openFolderModal);
  document.body.classList.toggle("more", !!S.config.more_open); $("#moretoggle").textContent = S.config.more_open ? "Less" : "More";
  $("#moretoggle").addEventListener("click", () => { const on = !document.body.classList.contains("more"); document.body.classList.toggle("more", on); $("#moretoggle").textContent = on ? "Less" : "More"; api("/api/config", {more_open: on}); });
  $("#spendalert").value = S.spend_alert || 10; $("#spendalert").addEventListener("change", () => { api("/api/config", {spend_alert: Number($("#spendalert").value) || 10}); S.spend_alert = Number($("#spendalert").value) || 10; render(); });
  $("#catalogbtn").addEventListener("click", () => { $("#catalogurl").value = (S.catalog && S.catalog.url) || ""; $("#catalogstatus").innerHTML = catalogLine(); $("#catalogmodal").hidden = false; });
  $("#catalogcancel").addEventListener("click", () => $("#catalogmodal").hidden = true);
  $("#catalogsave").addEventListener("click", async () => { await api("/api/config", {catalog_url: $("#catalogurl").value}); setTimeout(() => location.reload(), 600); });
  $("#charon").checked = !!S.config.character_on; $("#charnote").value = S.config.character_note || ""; $("#chardesc").value = S.character.desc || "";
  $("#charon").addEventListener("change", () => { saveConfig(); renderChar(); });
  $("#charnote").addEventListener("input", () => saveConfig());
  $("#chargen").addEventListener("click", async () => { const b = $("#chargen"); b.disabled = true; b.textContent = "Generating"; const r = await api("/api/character/generate", {description: $("#chardesc").value}); b.disabled = false; b.textContent = "Generate"; if (r.need_key) { openKey(false); return; } if (r.error) { toast(r.error); return; } await poll(); $("#charon").checked = true; renderChar(); });
  $("#charupload").addEventListener("click", () => $("#charfile").click());
  $("#charfile").addEventListener("change", () => { const f = $("#charfile").files[0]; if (!f) return; const rd = new FileReader(); rd.onload = async () => { const r = await api("/api/character/upload", {data: rd.result}); if (r.error) { toast(r.error); return; } await poll(); $("#charon").checked = true; renderChar(); }; rd.readAsDataURL(f); $("#charfile").value = ""; });
  $("#charclear").addEventListener("click", async () => { if (!await ask("Remove the character from this project?", "Remove character", "Remove")) return; await api("/api/character/clear", {}); await poll(); $("#charon").checked = false; renderChar(); });
  renderChar();
  $("#foldercancel").addEventListener("click", () => $("#foldermodal").hidden = true);
  $("#folderbrowse").addEventListener("click", async () => { const r = await api("/api/folder", {browse: true}); if (r.error) { toast(r.error); return; } $("#foldermodal").hidden = true; waitForFolder(); });
  $("#rescan").addEventListener("click", async () => {
    const b = $("#rescan"), label = b.lastChild; label.textContent = "Scanning";
    const r = await api("/api/rescan", {}); await poll();
    label.textContent = r.pending ? `${r.pending} new` : "Nothing new"; setTimeout(() => label.textContent = "Rescan", 1800);
    $("#folderhint").innerHTML = `<b>${S.items.length}</b> render${S.items.length===1?"":"s"} in <b>${esc(S.folder)}</b>${S.demo ? " · demo mode, nothing is sent to fal" : ""}`;
    if (r.pending && S.has_key && $("#review").value !== "1") runAll(false);
  });
  $("#notes").addEventListener("input", () => { saveConfig(); render(); });
  $("#run").addEventListener("click", () => runAll(false));
  $("#newbatch").addEventListener("click", async () => { if (await ask("Write a fresh prompt for every image? Nothing is enhanced until you press Enhance.", "New batch", "Write prompts")) runAll(true); });
  $("#keybtn").addEventListener("click", () => openKey(true));
  $("#exportimg").addEventListener("click", async () => { const b = $("#exportimg"); const r = await api("/api/export_images", {}); b.textContent = r.error ? "Failed" : `Saved ${r.count} to enhanced`; setTimeout(() => b.textContent = "Export prompts", 2200); });
  $("#keysave").addEventListener("click", saveKey);
  $("#keycancel").addEventListener("click", () => $("#keymodal").hidden = true);
  $("#stop").addEventListener("click", async () => { await api("/api/cancel", {}); poll(); });
  $("#quit").addEventListener("click", async () => { if (S.active) { if (!await ask("Jobs are still running. Quit anyway?", "Quit", "Quit")) return; } await api("/api/quit", {}); document.body.innerHTML = '<div class="empty"><span class="label">Render Post stopped</span><span>You can close this tab.</span></div>'; });
  $("#keyinput").addEventListener("keydown", e => { if (e.key === "Enter") saveKey(); });
  if (!S.has_key) openKey(false);
  else if (S.items.some(i => i.status === "pending") && S.config.review_first === false) runAll(false);
  render(); setInterval(poll, 1500);
}
function catalogLine(){ const c = S.catalog || {}; if (!c.url) return "No catalog set. Built-in models only."; if (c.ok === true) return `<i class="dot ok"></i> ${c.note}`; if (c.ok === false) return `<i class="dot bad"></i> couldn't load: ${esc(c.note)}`; return "Loading…"; }
function renderChar(){
  const has = !!(S.character && S.character.file);
  $("#charthumb").innerHTML = has ? `<img src="/img/out/${S.character.file}" alt="character">` : `<span class="label">No character</span>`;
  $("#charclear").hidden = !has; $("#charon").disabled = !has; if (!has) $("#charon").checked = false;
  $("#charblock").classList.toggle("on", has && $("#charon").checked);
  const tc = $("#takechar"); if (tc) { tc.disabled = !has; if (!has) tc.checked = false; }
}
function openFolderModal(){
  const list = $("#recentlist"); list.innerHTML = (S.recent && S.recent.length) ? S.recent.map(r => `<button type="button" data-path="${esc(r)}" title="${esc(r)}">${esc(r)}</button>`).join("") : `<span class="none">No other projects yet. Browse to a folder of renders.</span>`;
  for (const b of list.querySelectorAll("button[data-path]")) b.addEventListener("click", async () => { const r = await api("/api/folder", {path: b.dataset.path}); if (r.error) { toast(r.error); return; } $("#foldermodal").hidden = true; reloadProject(); });
  $("#foldermodal").hidden = false;
}
async function waitForFolder(){
  // the picker runs on the desktop; poll until the folder changes or the user cancels (~2 min)
  const before = S.folder; const t0 = Date.now();
  while (Date.now() - t0 < 120000) { await new Promise(r => setTimeout(r, 800)); const st = await api("/api/state"); if (st.folder !== before) { reloadProject(); return; } }
}
function reloadProject(){ location.reload(); }
function openKey(cancelable){ $("#keycancel").hidden = !cancelable; $("#keyinput").value = ""; $("#keyerr").hidden = true; $("#keymodal").hidden = false; setTimeout(() => $("#keyinput").focus(), 50); }
async function saveKey(){
  const k = $("#keyinput").value.trim(); if (!k) return;
  const btn = $("#keysave"); btn.disabled = true; btn.textContent = "Checking"; $("#keyerr").hidden = true;
  const r = await api("/api/config", {fal_key:k});
  btn.disabled = false; btn.textContent = "Save key";
  if (r.error) { $("#keyerr").textContent = r.error; $("#keyerr").hidden = false; return; }
  $("#keymodal").hidden = true; S.has_key = true;
  if (S.items.some(i => i.status === "pending") && $("#review").value !== "1") runAll(false);
}
async function reviseAll(){ await saveNow(); const r = await api("/api/revise", {}); if (r.need_key) { openKey(false); $("#keyerr").textContent = r.error; $("#keyerr").hidden = false; return; } if (r.error) toast(r.error); poll(); }
async function enhanceAll(names){
  await saveNow();
  const prompts = {}; for (const [n, el] of Object.entries(cards)) { const ta = el.querySelector("textarea"); if (ta) prompts[n] = ta.value; }
  const r = await api("/api/enhance_all", {prompts, names: names || null, revise_stale: $("#review").value !== "1"});
  if (r.need_key) { openKey(false); $("#keyerr").textContent = r.error; $("#keyerr").hidden = false; return; }
  if (r.error) toast(r.error); poll();
}
async function runAll(all){ const r = await api("/api/run", {all: !!all}); if (r.need_key) { openKey(false); $("#keyerr").textContent = r.error; $("#keyerr").hidden = false; return; } if (r.error) toast(r.error); poll(); }
async function regen(name, rewrite){
  const ta = cards[name].querySelector("textarea");
  const r = await api("/api/regenerate", rewrite ? {name, rewrite:true} : {name, prompt: ta.value});
  if (r.need_key) { openKey(false); $("#keyerr").textContent = r.error; $("#keyerr").hidden = false; return; }
  if (r.error) toast(r.error); poll();
}
let lastCount = null;
async function poll(){ const s = await api("/api/state"); if (lastCount !== null && s.items.length > lastCount) toast(`${s.items.length - lastCount} new render${s.items.length - lastCount === 1 ? "" : "s"} found in the folder`, "ok", 4000); lastCount = s.items.length; S.items = s.items; S.active = s.active; S.picks = s.picks; S.clips = s.clips || []; S.video = s.video || S.video; S.recent = s.recent || []; S.character = s.character || {}; S.catalog = s.catalog || S.catalog; S.spend = s.spend; S.spend_alert = s.spend_alert;
  if (s.latest && s.latest.version) { const u = $("#update"); u.textContent = `v${s.latest.version} available`; u.href = s.latest.url || "#"; u.hidden = false; }
  render(); }

function stateLine(it){
  if (it.status === "working" || it.status === "queued") return `<i class="dot live"></i>${it.step}`;
  if (it.status === "failed") return `<i class="dot bad"></i>failed`;
  if (it.status === "done") { const v = it.versions[it.versions.length-1]; return `<i class="dot ok"></i>${it.versions.length} version${it.versions.length===1?"":"s"}${v && v.seconds != null ? " · last " + v.seconds + "s" : ""}`; }
  if (it.status === "ready") return `<i class="dot warn"></i>prompt ready · not sent`;
  return `<i class="dot"></i>waiting`;
}

function render(){
  const items = S.items, busy = items.filter(i => i.status === "working" || i.status === "queued").length;
  const done = items.filter(i => i.status === "done").length, failed = items.filter(i => i.status === "failed").length;
  const mdl = S.models[S.config.model] || {}; const setting = mdl.kind === "nano" ? S.config.resolution : `${S.config.quality} · ${S.config.long_edge}px`;
  $("#meta").innerHTML = [`<b>${items.length}</b> images`, "<s>·</s>", `<b>${done}</b> done`, failed ? `<s>·</s> <b>${failed}</b> failed` : "", S.picks ? `<s>·</s> <b>${S.picks}</b> picked` : "", "<s>·</s>", `${(mdl.label || "").split(" ·")[0]} · ${setting}`].join(" ");
  $("#status").innerHTML = busy ? `<i class="dot live"></i>${busy} in progress` : `<i class="dot ok"></i>idle`;
  const sp = Number(S.spend || 0), lim = Number(S.spend_alert || 10); $("#spend").innerHTML = sp > 0 ? `<i class="dot ${sp >= lim ? "warn" : ""}"></i>≈ $${sp.toFixed(2)} this project` : "";
  $("#stop").hidden = busy === 0;
  const pending = items.filter(i => i.status === "pending").length;
  const ready = items.filter(i => i.status === "ready").length;
  const anyPrompt = items.filter(i => i.prompt && i.status !== "pending").length;
  const reviewMode = $("#review").value === "1";
  const notesNow = $("#notes").value.trim();
  const stale = items.filter(i => i.prompt && ["ready","failed","done"].includes(i.status) && (i.notes_used || "") !== notesNow).length;
  $("#stale").hidden = stale === 0; $("#stale").innerHTML = `<i class="dot warn"></i>${stale} prompt${stale===1?"":"s"} written with old notes`;
  $("#run").hidden = !reviewMode || pending === 0; $("#run").disabled = busy > 0;
  $("#exportimg").hidden = !items.some(i => i.prompt || i.versions.length);
  $("#run").textContent = `Write ${pending} prompt${pending===1?"":"s"}`;
  $("#run").classList.toggle("solid", reviewMode && pending > 0 && anyPrompt === 0);
  $("#enhance").hidden = reviewMode && pending > 0 && anyPrompt === 0;
  $("#newbatch").hidden = pending > 0 || !items.length; $("#newbatch").disabled = busy > 0;
  $("#enhance").disabled = busy > 0 || (anyPrompt === 0 && !(pending && !reviewMode));
  const toSend = selected.size ? [...selected].filter(nm => items.some(i => i.name === nm && i.prompt)).length : (ready || anyPrompt || pending); $("#estimate").textContent = toSend ? estimate(toSend) : "";
  if (pending && !reviewMode) { $("#enhance").textContent = `Enhance ${pending} image${pending===1?"":"s"}`; $("#enhance").onclick = () => runAll(false); }
  else if (reviewMode && stale) { $("#enhance").textContent = `Update ${stale} prompt${stale===1?"":"s"}`; $("#enhance").onclick = reviseAll; }
  else if (selected.size) { const n = [...selected].filter(nm => items.some(i => i.name === nm && ["ready","failed","done"].includes(i.status) && i.prompt)).length; $("#enhance").textContent = `Enhance ${n} selected`; $("#enhance").disabled = busy > 0 || n === 0; $("#enhance").onclick = () => enhanceAll([...selected]); }
  else { $("#enhance").textContent = ready ? `Enhance ${ready} reviewed` : (stale ? "Update prompts and enhance" : "Enhance all again"); $("#enhance").onclick = () => enhanceAll(null); }
  $("#selinfo").hidden = selected.size === 0; $("#selinfo").innerHTML = `<i class="dot warn"></i>${selected.size} selected · <a href="#" id="selclear">clear</a>`; const sc = $("#selclear"); if (sc) sc.onclick = e => { e.preventDefault(); selected.clear(); for (const a of Object.values(cards)) a.dataset.sig = ""; render(); };

  renderVideo();
  const npick = items.reduce((n, i) => n + i.versions.filter(v => v.pick).length, 0);
  $("#pickstab").textContent = npick ? `Picks · ${npick}` : "Picks";
  $("#pickbar").innerHTML = npick ? `<b>${npick}</b> picked version${npick===1?"":"s"}, also copied to enhanced/picks. Click a thumbnail to jump to its card; unpick from the card to remove it.` : `Nothing picked yet. Press the star on a version to pick it.`;
  const gg = $("#imggrid"); gg.hidden = !(view === "images" && imgmode === "grid");
  if (!gg.hidden) { gg.innerHTML = ""; for (const it of items) { const v = it.versions[it.versions.length - 1]; const el = document.createElement("div"); el.className = "gi" + (selected.has(it.name) ? " sel" : "");
      const st = it.status === "working" || it.status === "queued" ? `<i class="dot live st"></i>` : it.status === "failed" ? `<i class="dot bad st"></i>` : it.status === "ready" ? `<i class="dot warn st"></i>` : "";
      el.innerHTML = `${st}<img src="${v ? `/img/out/${encodeURIComponent(v.file)}` : `/img/raw/${encodeURIComponent(it.source_file)}`}" loading="lazy" alt=""><div class="cap"><b>${esc(it.name)}</b><span>${it.versions.some(x => x.pick) ? "★ " : ""}${it.versions.length ? it.versions.length + " v" : (it.prompt ? "prompt ready" : "raw")}</span></div>`;
      el.addEventListener("click", e => { if (e.shiftKey) { selected.has(it.name) ? selected.delete(it.name) : selected.add(it.name); for (const a of Object.values(cards)) a.dataset.sig = ""; render(); return; }
        imgmode = "detail"; document.body.dataset.imgmode = "detail"; for (const o of document.querySelectorAll("[data-imgmode]")) o.setAttribute("aria-pressed", o.dataset.imgmode === "detail"); api("/api/config", {img_mode: "detail"}); render(); const art = cards[it.name]; if (art) art.scrollIntoView({behavior:"smooth", block:"start"}); });
      gg.appendChild(el); } $("#gridhint").textContent = "Grid shows the latest version of each image. Click to open, shift-click to select."; }
  if (view === "picks") { const g = $("#pickgrid"); g.innerHTML = ""; for (const it of items) it.versions.forEach((v, i) => { if (!v.pick) return; const el = document.createElement("div"); el.className = "pg"; el.innerHTML = `<img src="/img/out/${encodeURIComponent(v.file)}" loading="lazy" alt=""><span>${esc(it.name)} · ${v.angle ? "a" : "v"}${it.versions.slice(0, i+1).filter(y => !!y.angle === !!v.angle).length}</span>`; el.addEventListener("click", () => { const art = cards[it.name]; if (art) { art.dataset.sel = i; art.dataset.sig = ""; render(); art.scrollIntoView({behavior:"smooth", block:"start"}); } }); g.appendChild(el); }); }
  const wrap = $("#cards");
  if (!items.length) { wrap.innerHTML = `<div class="empty"><span class="label">No renders found</span><span>Put PNG or JPG renders in this folder and restart.</span></div>`; return; }
  wrap.style.display = "grid"; wrap.style.gap = "16px";
  items.forEach((it, i) => {
    let art = cards[it.name];
    if (!art) { art = document.createElement("article"); art.tabIndex = -1; art.style.animationDelay = `${Math.min(i,8)*30}ms`; cards[it.name] = art; wrap.appendChild(art); art.dataset.sig = ""; }
    art.classList.toggle("haspick", it.versions.some(v => v.pick)); art.classList.toggle("sel", selected.has(it.name));
    const sig = JSON.stringify([it.status, it.step, it.versions.map(v => v.file + (v.pick ? "*" : "")), it.error, it.prompt, it.notes_used, selected.has(it.name)]);
    if (art.dataset.sig === sig) return;           // only rebuild when something changed
    const ta0 = art.querySelector("textarea");
    const editing = ta0 && document.activeElement === ta0;
    // "shown" is whatever the box was last filled with (a version's prompt or the next-run draft);
    // only a difference from that counts as the user's edit, and edits belong to the next-run draft
    const edited = ta0 && ta0.value !== (art.dataset.shown || "");
    const prevCount = Number(art.dataset.count || 0);
    let sel = Number(art.dataset.sel ?? -1);
    if (it.versions.length !== prevCount || sel < 0 || sel >= it.versions.length) sel = it.versions.length - 1;  // new version: jump to it
    const wasLatest = art.dataset.wasLatest === "1";
    if (edited && wasLatest) art.dataset.draft = ta0.value;           // remember the edit while browsing older versions
    if (it.prompt !== (art.dataset.prompt || "")) delete art.dataset.draft;   // server changed the draft (rewrite, run): drop the stale local edit
    const isLatest = sel === it.versions.length - 1;
    const draft = isLatest && art.dataset.draft != null ? art.dataset.draft : null;
    art.dataset.sig = sig; art.dataset.prompt = it.prompt || ""; art.dataset.count = it.versions.length; art.dataset.sel = sel; art.dataset.wasLatest = isLatest ? "1" : "0";
    const v = it.versions[sel];
    const ar = it.src_size ? `${it.src_size[0]}/${it.src_size[1]}` : "16/9";
    const busyItem = it.status === "working" || it.status === "queued";
    const vlabel = (x, i) => x.angle ? "a" + (it.versions.slice(0, i+1).filter(y => y.angle).length) : "v" + (it.versions.slice(0, i+1).filter(y => !y.angle).length);
    const tabs = it.versions.length > 1 ? `<div class="vseg" role="group" aria-label="Version">${it.versions.map((x,i) => `<button type="button" data-i="${i}" aria-pressed="${i===sel}" title="${esc((x.angle ? "angle · " : "") + (x.character ? "with character · " : "") + (x.made || "") + (x.model ? " · " + x.model : ""))}">${vlabel(x, i)}${x.character ? "·" : ""}${x.pick ? "★" : ""}</button>`).join("")}</div>` : "";
    art.innerHTML = `
      <div class="stage ${v ? "" : "noafter"}" data-mode="${v ? (v.angle ? "after" : mode) : "before"}" style="--ar:${ar}">
        <img class="before" src="/img/raw/${encodeURIComponent(it.source_file)}" alt="" loading="lazy">
        ${v ? `<img class="after" src="/img/out/${encodeURIComponent(v.file)}" alt="" loading="lazy">` : ""}
        <div class="wipe"><input type="range" min="0" max="100" value="50" aria-label="Wipe"><div class="handle"></div></div>
        <span class="tag l label">Raw</span><span class="tag r label">${v ? vlabel(v, sel) : "Enhanced"}</span>
        ${busyItem ? `<div class="working"><span><i class="dot live"></i>${it.step}<button class="btn quiet cancel" type="button">Cancel</button></span></div>` : ""}
      </div>
      <aside>
        <div class="row"><h2><label class="selbox" title="Select for Enhance selected"><input type="checkbox" class="selimg" ${selected.has(it.name) ? "checked" : ""}></label>${esc(it.name)}</h2>${tabs}</div>
        <div class="facts">
          <span>raw</span><b>${it.src_size ? it.src_size.join(" × ") : "–"}</b>
          <span>out</span><b>${v && v.out_size ? v.out_size.join(" × ") + (v.model ? " · " + ((S.models[v.model]||{}).label||v.model).split(" ·")[0] : "") + (v.quality ? " · " + v.quality : "") : "–"}</b>
          <span>run</span><b>${stateLine(it)}</b>
        </div>
        ${it.error ? `<div class="err">${esc(it.error)}</div>` : ""}
        <div class="row"><span class="label">${v && sel < it.versions.length-1 ? "Prompt · " + vlabel(v, sel) : "Prompt · next"}</span>
          <span><button class="btn quiet rewrite" type="button" title="Ask for a fresh prompt using the current style notes">Rewrite</button><button class="btn quiet copy" type="button">Copy</button></span></div>
        <textarea spellcheck="false" placeholder="Prompt appears here once written. Edit it, then Enhance.">${esc(draft ?? (v && !isLatest ? v.prompt : it.prompt))}</textarea>
        <div class="actions">
          ${v ? `<button class="btn quiet compare" type="button" title="Save a side-by-side JPG to enhanced/compare">Before / after</button>
          <button class="btn quiet delver" type="button" title="Move this version to enhanced/trash">Delete</button>
          <button class="btn quiet pick ${v.pick ? "on" : ""}" type="button" title="${v.pick ? "Picked: this version is in enhanced/picks and eligible for video" : "Mark this version as a pick: copies it to enhanced/picks"}"><svg viewBox="0 0 16 16"><path d="M8 1.8l1.9 3.9 4.3.6-3.1 3 .7 4.3L8 11.6l-3.8 2 .7-4.3-3.1-3 4.3-.6z"/></svg>${v.pick ? "Picked" : "Pick"}</button>` : ""}
          <button class="btn regen ${it.status === "ready" ? "solid" : ""}" type="button" ${busyItem ? "disabled" : ""}>${it.versions.length ? "Enhance again" : "Enhance this one"}</button>
          ${v && it.status === "done" ? `<button class="btn angles" type="button" title="New stills of this space from other camera positions, with the current image model. Best from a wide, well-lit view that shows the whole space; partial or steep views invent more. Count is set under Angles per run.">${$("#angles").value} angles</button>
          <button class="btn solid tovideo" type="button" title="Add this version to the video set and open Video">Add to video</button>` : ""}</div>
      </aside>`;
    for (const b of art.querySelectorAll(".vseg button")) b.addEventListener("click", () => { art.dataset.sel = b.dataset.i; art.dataset.sig = ""; render(); });
    $(".rewrite", art).addEventListener("click", () => regen(it.name, true));
    const pk = $(".pick", art); if (pk) pk.addEventListener("click", async () => { await api("/api/pick", {name: it.name, file: v.file}); poll(); });
    const dv = $(".delver", art); if (dv) dv.addEventListener("click", async () => { if (!await ask(`Delete ${it.name} ${vlabel(v, sel)}? It moves to enhanced/trash, not the bin.`, "Delete version", "Delete")) return; const r = await api("/api/delete_version", {name: it.name, file: v.file}); if (r.error) { toast(r.error); return; } frames = frames.filter(f => !(f.name === it.name && f.file === v.file)); saveConfig(); art.dataset.sel = Math.max(0, sel - 1); art.dataset.sig = ""; poll(); });
    const ag = $(".angles", art); if (ag) ag.addEventListener("click", async () => {
      await saveNow();
      const n = Number($("#angles").value), m = S.models[$("#model").value];
      const cost = m.price ? ` · about $${(m.price * (m.mult[$("#resolution").value] || 1) * n).toFixed(2)}` : " · token priced";
      if (!await ask(`Make ${n} new angles of ${it.name} ${vlabel(v, sel)} with ${m.label.split(" ·")[0]}${cost}?`, "Angles", "Make angles")) return;
      const r = await api("/api/angles", {name: it.name, file: v.file}); if (r.need_key) { openKey(false); $("#keyerr").textContent = r.error; $("#keyerr").hidden = false; return; } if (r.error) toast(r.error); poll();
    });
    const tv = $(".tovideo", art); if (tv) tv.addEventListener("click", () => {
      const k = it.name + "|" + v.file; if (!frames.some(f => frameKey(f) === k)) { frames.push({name: it.name, file: v.file}); saveConfig(); }
      setView("video");
    });
    const cp = $(".compare", art); if (cp) cp.addEventListener("click", async () => { cp.textContent = "Saving"; const r = await api("/api/compare", {name: it.name, file: v.file}); cp.textContent = r.error ? "Failed" : "Saved to compare"; setTimeout(() => cp.textContent = "Before / after", 1800); });
    const c = $(".cancel", art); if (c) c.addEventListener("click", async () => { c.disabled = true; c.textContent = "Cancelling"; await api("/api/cancel", {name: it.name}); poll(); });
    const sb = $(".selimg", art); if (sb) sb.addEventListener("change", () => { sb.checked ? selected.add(it.name) : selected.delete(it.name); render(); });
    const ta = $("textarea", art); art.dataset.shown = ta.value; const fit = () => { ta.style.height = "auto"; ta.style.height = Math.max(150, ta.scrollHeight + 2) + "px"; };
    ta.addEventListener("input", () => { fit(); if (art.dataset.wasLatest === "1") art.dataset.draft = ta.value; }); requestAnimationFrame(fit);
    const stage = $(".stage", art), range = $("input[type=range]", art);
    range.addEventListener("input", () => stage.style.setProperty("--cut", range.value + "%"));
    $(".copy", art).addEventListener("click", async e => { try { await navigator.clipboard.writeText($("textarea", art).value); e.target.textContent = "Copied"; setTimeout(() => e.target.textContent = "Copy", 1400); } catch {} });
    $(".regen", art).addEventListener("click", () => regen(it.name, false));
    if (editing) $("textarea", art).focus();
  });
}

// ---------------- video
function setView(v){
  view = v; document.body.dataset.view = v;
  for (const b of document.querySelectorAll("[data-view]")) b.setAttribute("aria-pressed", b.dataset.view === v);
  $("#videoview").hidden = v !== "video";
  if (v === "picks") { for (const [name, art] of Object.entries(cards)) { const it = S.items.find(i => i.name === name); const i = it ? it.versions.findIndex(x => x.pick) : -1; if (i >= 0) { art.dataset.sel = i; art.dataset.sig = ""; } } render(); }
  if (v === "video") renderVideo();
  window.scrollTo({top:0, behavior:"smooth"});
}
function frameKey(f){ return f.name + "|" + f.file; }
function frameLabel(f){ const it = S.items.find(i => i.name === f.name); if (!it) return f.name; if (f.file === it.source_file) return `${f.name} · raw`; const i = it.versions.findIndex(v => v.file === f.file); if (i < 0) return f.name; const x = it.versions[i]; const k = it.versions.slice(0, i+1).filter(y => !!y.angle === !!x.angle).length; return `${f.name} · ${x.angle ? "a" : "v"}${k}`; }
function frameSrc(f){ const it = S.items.find(i => i.name === f.name); return (it && f.file === it.source_file) ? `/img/raw/${encodeURIComponent(f.file)}` : `/img/out/${encodeURIComponent(f.file)}`; }
function toggleFrame(f){ const k = frameKey(f); const i = frames.findIndex(x => frameKey(x) === k); if (i >= 0) frames.splice(i,1); else frames.push({name: f.name, file: f.file}); saveConfig(); renderVideo(); }
function moveFrame(k, d){ const i = frames.findIndex(x => frameKey(x) === k); const j = i + d; if (i < 0 || j < 0 || j >= frames.length) return; const [f] = frames.splice(i,1); frames.splice(j,0,f); saveConfig(); renderVideo(); }
function vprice(){
  if (vmode === "take") return S.video.models.seedance.price[$("#vres").value] || 0;
  const m = S.video.models[$("#vmodel").value]; if (!m) return 0;
  return m.price[$("#vres").value] ?? m.price[$("#vaudio").value === "1" ? "audio" : "silent"] ?? Object.values(m.price)[0] ?? 0;
}
function vestimate(){
  const price = vprice(), n = frames.length;
  if (!n) return "";
  if (vmode === "take") { const d = Number($("#tdur").value); return `1 take · ${n} frames · ${d}s · about $${(price*d).toFixed(2)}`; }
  const d = Number($("#vdur").value); return `${n} clip${n===1?"":"s"} · ${d}s each · about $${(price*d*n).toFixed(2)}`;
}
function renderVideo(){
  if (!S || !S.video) return;
  const valid = new Set(); for (const it of S.items) { valid.add(it.name + "|" + it.source_file); for (const v of it.versions) valid.add(it.name + "|" + v.file); }
  frames = frames.filter(f => valid.has(frameKey(f)));
  const done = S.items.filter(i => i.versions.length).length;
  $("#videotab").textContent = frames.length ? `Video · ${frames.length}` : "Video";
  if (view !== "video") return;
  $("#vmakepanel").dataset.vmode = vmode; $("#vmakepanel").dataset.vmodel = $("#vmodel").value;
  if (vmode === "take") { $("#vmakepanel").dataset.nores = "0"; if (!S.video.res[$("#vres").value]) fill($("#vres"), S.video.res, "480p"); }
  else syncVideoModel();
  const n = frames.length, sh = Number($("#shots").value);
  $("#vexplain").textContent = !n ? "Add frames in Step 1 first."
    : vmode === "take" ? `You'll get 1 video, ${$("#tdur").value}s long, that travels through all ${n} frame${n===1?"":"s"} in the order shown. Experimental: the model recreates the spaces rather than reproducing them.`
    : sh === 1 ? `You'll get ${n} separate video${n===1?"":"s"}, ${$("#vdur").value}s each. Each one starts exactly on its frame and holds one slow camera move.`
    : `You'll get ${n} separate video${n===1?"":"s"}, ${$("#vdur").value}s each. Each starts exactly on its frame, then cuts to ${sh-1} more angle${sh===2?"":"s"} of the same space, like a mini edit.`;
  // ---- step 1: frames grid, versions stacked per image
  const grid = $("#framegrid"); grid.innerHTML = "";
  for (const it of S.items) {
    const fr = document.createElement("div"); fr.className = "frame";
    let nv = 0, na = 0; const vers = it.versions.map(v => ({file: v.file, label: v.angle ? `a${++na}` : `v${++nv}`, pick: v.pick, raw: false}));
    vers.push({file: it.source_file, label: "raw", pick: false, raw: true});
    fr.innerHTML = `<div class="name">${esc(it.name)}<span>${it.versions.length} version${it.versions.length===1?"":"s"}</span></div><div class="stack"></div>`;
    const st = $(".stack", fr);
    for (const v of vers) {
      const k = it.name + "|" + v.file, ord = frames.findIndex(f => frameKey(f) === k);
      const el = document.createElement("div"); el.className = "ver" + (ord >= 0 ? " on" : "") + (v.raw ? " raw" : ""); el.title = ord >= 0 ? "Remove from video set" : "Add to video set";
      el.innerHTML = `<img src="${v.raw ? `/img/raw/${encodeURIComponent(v.file)}` : `/img/out/${encodeURIComponent(v.file)}`}" alt="" loading="lazy"><span class="tag">${v.label}</span>${v.pick ? `<span class="star">★</span>` : ""}${ord >= 0 ? `<span class="ord">${ord+1}</span>` : ""}`;
      el.addEventListener("click", () => toggleFrame({name: it.name, file: v.file}));
      st.appendChild(el);
    }
    grid.appendChild(fr);
  }
  if (!S.items.length) grid.innerHTML = `<span class="hint">No renders in this folder.</span>`;
  $("#framecount").innerHTML = frames.length ? `<i class="dot ok"></i>${frames.length} in the set` : `<i class="dot"></i>nothing selected`;
  // ---- step 2: set strip + controls
  const strip = $("#pickstrip"); strip.innerHTML = "";
  frames.forEach((f, i) => {
    const el = document.createElement("div"); el.className = "pk on";
    el.innerHTML = `${vmode === "take" ? `<span class="ord">${i+1}</span>` : ""}<img src="${frameSrc(f)}" alt=""><div class="cap"><b>${esc(frameLabel(f))}</b><span class="mv"><button type="button" title="Earlier">◀</button><button type="button" title="Later">▶</button></span></div>`;
    el.title = "Remove from set"; el.addEventListener("click", e => { if (e.target.tagName === "BUTTON") return; toggleFrame(f); });
    const [bl, br] = el.querySelectorAll(".mv button"); bl.addEventListener("click", () => moveFrame(frameKey(f), -1)); br.addEventListener("click", () => moveFrame(frameKey(f), 1));
    strip.appendChild(el);
  });
  if (!frames.length) strip.innerHTML = `<span class="hint" style="color:var(--em-ink-dim)">Empty. Add frames in Step 1.</span>`;
  $("#vestimate").textContent = vestimate();
  const clips = (S.clips || []).filter(c => c.kind !== "reel"), reels = (S.clips || []).filter(c => c.kind === "reel");
  const busy = (S.clips || []).filter(c => c.status === "queued" || c.status === "working").length;
  const ready = clips.filter(c => c.status === "ready" || c.status === "failed").length;
  const readyTake = clips.some(c => (c.status === "ready" || c.status === "failed") && c.kind === "take");
  const reviewMode = $("#review").value === "1";
  $("#vprompts").hidden = !reviewMode; $("#vprompts").disabled = busy > 0 || frames.length === 0;
  $("#vclear").hidden = ready === 0 || busy > 0;
  $("#vexport").hidden = !clips.some(c => c.prompt);
  $("#vprompts").textContent = vmode === "take" ? "Write take prompt" : `Write ${frames.length} motion prompt${frames.length===1?"":"s"}`;
  $("#vprompts").classList.toggle("solid", reviewMode && ready === 0 && frames.length > 0);
  if (reviewMode) { $("#vmake").hidden = ready === 0; $("#vmake").textContent = readyTake && ready === 1 ? "Make the take" : `Make ${ready} ${ready===1?"clip":"clips"}`; $("#vmake").disabled = busy > 0; }
  else { $("#vmake").hidden = false; $("#vmake").textContent = vmode === "take" ? "Make the take" : `Make ${frames.length} clip${frames.length===1?"":"s"}`; $("#vmake").disabled = busy > 0 || frames.length === 0; }
  renderClipCards(clips, $("#clips"), clipEls, true);
  // ---- step 3: reel
  renderClipCards(reels, $("#reels"), reelEls, false);
  updateStitch();
}
function renderClipCards(list, wrap, els, withStitchBox){
  const seen = new Set();
  for (const c of list) {
    seen.add(c.id); let el = els[c.id];
    if (!el) { el = document.createElement("div"); el.className = "clip"; els[c.id] = el; wrap.appendChild(el); el.dataset.sig = ""; }
    const sig = JSON.stringify([c.status, c.step, c.file, c.error, c.prompt, [...stitchSel].indexOf(c.id)]); if (el.dataset.sig === sig) continue;
    const ta0 = el.querySelector("textarea"); const draft = ta0 && ta0.value !== (el.dataset.prompt || "") ? ta0.value : null;
    el.dataset.sig = sig; el.dataset.prompt = c.prompt || "";
    const busyItem = c.status === "queued" || c.status === "working";
    const src = c.kind === "reel" ? null : c.sources[0];
    const title = c.kind === "reel" ? "Reel" : c.kind === "take" ? `Take · ${c.sources.length} frames` : (src ? esc(frameLabel(src)) : "Clip");
    const shots = (c.kind === "clip" && Number(c.shots || 1) > 1 ? ` · ${c.shots} shots` : "") + (c.vmodel && c.kind === "clip" ? " · " + (((S.video.models[c.vmodel] || {}).label || c.vmodel).split(" ·")[0]) : "");
    const dims = c.out_size ? ` · ${c.out_size[0]}×${c.out_size[1]}` : (c.resolution ? ` · ${c.resolution}` : "");
    const state = busyItem ? `<i class="dot live"></i>${esc(c.step)}` : c.status === "done" ? `<i class="dot ok"></i>${c.duration}s${dims}${shots}` : c.status === "failed" ? `<i class="dot bad"></i>failed` : `<i class="dot warn"></i>prompt ready · not sent`;
    el.innerHTML = `
      <div class="media">${c.file ? `<video src="/vid/${encodeURIComponent(c.file)}" ${src ? `poster="${frameSrc(src)}"` : ""} controls preload="metadata" loop muted></video>` : src ? `<img src="${frameSrc(src)}" alt="">` : ""}
        ${withStitchBox && c.status === "done" ? `<label class="inreel ${stitchSel.has(c.id) ? "on" : ""}" title="Include this clip in the reel. Order is the order you tick."><input type="checkbox" class="stitchsel" ${stitchSel.has(c.id) ? "checked" : ""}><span>${stitchSel.has(c.id) ? `<b class="ord">${[...stitchSel].indexOf(c.id) + 1}</b> In reel` : "Add to reel"}</span></label>` : ""}
        ${busyItem ? `<div class="working"><span><i class="dot live"></i>${esc(c.step)}<button class="btn quiet vcancel" type="button">Cancel</button></span></div>` : ""}</div>
      <div class="body">
        <div class="top"><label>${title}</label><span>${state}</span></div>
        ${c.error ? `<div class="err">${esc(c.error)}</div>` : ""}
        ${c.kind === "reel" ? `<div class="hint" style="font-family:var(--em-font-mono);font-size:11px;color:var(--em-ink-dim)">${esc(c.prompt)}</div>` : `<textarea spellcheck="false" placeholder="Motion prompt appears here once written.">${esc(draft ?? c.prompt)}</textarea>`}
        <div class="actions"><span class="r">${c.file ? `<a class="btn quiet" href="/vid/${encodeURIComponent(c.file)}" target="_blank" rel="noopener">Open</a><a class="btn quiet" href="/vid/${encodeURIComponent(c.file)}" download="${esc(c.file)}">Download</a>` : ""}${!busyItem ? `<button class="btn quiet vremove" type="button" title="Remove from this list (keeps the file)">Remove</button>` : ""}</span>
          <span class="r">${c.kind !== "reel" && !busyItem ? `<button class="btn vmake1 ${c.status === "ready" ? "solid" : ""}" type="button">${c.status === "done" ? "Make again" : "Make clip"}</button>` : ""}</span></div>
      </div>`;
    const ta = el.querySelector("textarea"); if (ta) { const fit = () => { ta.style.height = "auto"; ta.style.height = Math.max(64, ta.scrollHeight + 2) + "px"; }; ta.addEventListener("input", fit); requestAnimationFrame(fit); }
    const cb = el.querySelector(".stitchsel"); if (cb) cb.addEventListener("change", () => { cb.checked ? stitchSel.add(c.id) : stitchSel.delete(c.id); el.dataset.sig = ""; renderVideo(); });
    const vc = el.querySelector(".vcancel"); if (vc) vc.addEventListener("click", async () => { vc.disabled = true; await api("/api/video/cancel", {id: c.id}); poll(); });
    const rm = el.querySelector(".vremove"); if (rm) rm.addEventListener("click", async () => { await api("/api/video/remove", {id: c.id}); el.remove(); delete els[c.id]; stitchSel.delete(c.id); poll(); });
    const mk = el.querySelector(".vmake1"); if (mk) mk.addEventListener("click", async () => { await saveNow(); const r = await api("/api/video/make", {ids: [c.id], prompts: {[c.id]: el.querySelector("textarea").value}}); if (r.error) toast(r.error); poll(); });
  }
  for (const id of Object.keys(els)) if (!seen.has(id)) { els[id].remove(); delete els[id]; }
}
function updateStitch(){
  const done = (S.clips || []).filter(c => c.status === "done" && c.kind !== "reel");
  const m = $("#music"); if (!m.dataset.wired) { m.dataset.wired = "1"; m.addEventListener("change", updateStitch); } const cur = m.value; m.innerHTML = `<option value="">None</option>` + (S.video.music || []).map(f => `<option value="${esc(f)}">${esc(f)}</option>`).join(""); m.value = cur;
  $("#musichint").hidden = (S.video.music || []).length > 0;
  $("#mstartwrap").hidden = !m.value;
  const ok = S.video.ffmpeg && stitchSel.size >= 2;
  $("#stitch").disabled = !ok;
  $("#stitchhint").innerHTML = !S.video.ffmpeg ? `<i class="dot bad"></i>ffmpeg missing in this build` : done.length < 2 ? `<i class="dot"></i>needs two finished clips` : stitchSel.size < 2 ? `<i class="dot warn"></i>add ${2 - stitchSel.size} more clip${stitchSel.size === 1 ? "" : "s"} to the reel` : `<i class="dot ok"></i>${stitchSel.size} clips, in the order ticked`;
  $("#stitch").textContent = ok ? `Stitch ${stitchSel.size} clips` : "Stitch";
}
async function videoPrompts(){
  await saveNow();
  if (!frames.length) return;
  const r = await api("/api/video/prompts", {mode: vmode, picks: frames});
  if (r.need_key) { openKey(false); $("#keyerr").textContent = r.error; $("#keyerr").hidden = false; return; }
  if (r.error) toast(r.error); poll();
}
async function videoMake(){
  await saveNow();
  const reviewMode = $("#review").value === "1";
  if (!reviewMode) { const est = vestimate(); if (!await ask(`This will generate video now: ${est}.`, "Make video", "Generate")) return; return videoPrompts(); }
  const prompts = {}; for (const [id, el] of Object.entries(clipEls)) { const ta = el.querySelector("textarea"); if (ta) prompts[id] = ta.value; }
  const ids = (S.clips || []).filter(c => c.status === "ready" || c.status === "failed").map(c => c.id);
  const price = vprice(); const secs = ids.reduce((n, id) => n + Number((S.clips.find(c => c.id === id) || {}).duration || 0), 0);
  if (!await ask(`Generate ${ids.length} clip${ids.length===1?"":"s"}: ${secs}s of video, about $${(price*secs).toFixed(2)}.`, "Make clips", "Generate")) return;
  const r = await api("/api/video/make", {ids, prompts}); if (r.error) toast(r.error); poll();
}
function reelOrder(){ return [...stitchSel].filter(id => (S.clips || []).some(c => c.id === id && c.status === "done")); }   // tick order, as shown on the badges
async function stitch(){
  await saveNow();
  const order = reelOrder();
  const r = await api("/api/video/stitch", {ids: order, music: $("#music").value || null, music_start: Number($("#mstart").value || 0)}); if (r.error) toast(r.error); poll();
}

for (const b of document.querySelectorAll(".seg button[data-mode]")) b.addEventListener("click", () => {
  mode = b.dataset.mode;
  for (const o of document.querySelectorAll(".seg button")) o.setAttribute("aria-pressed", o === b);
  for (const s of document.querySelectorAll(".stage:not(.noafter)")) { const art = s.closest("article"); const it = art && S.items.find(i => i.name === Object.keys(cards).find(k => cards[k] === art)); const v = it && it.versions[Number(art.dataset.sel)]; s.dataset.mode = v && v.angle && mode === "wipe" ? "after" : mode; }
});
let cur = -1;
function jump(d){ const c = [...document.querySelectorAll("article")]; if (!c.length) return; cur = Math.max(0, Math.min(c.length-1, cur+d)); c[cur].scrollIntoView({behavior:"smooth",block:"start"}); c[cur].focus({preventScroll:true}); }
window.addEventListener("scroll", () => document.body.classList.toggle("scrolled", window.scrollY > 200), {passive:true});
["dragenter","dragover"].forEach(ev => window.addEventListener(ev, e => { if ([...e.dataTransfer.types].includes("Files")) { e.preventDefault(); document.body.classList.add("dropping"); } }));
["dragleave","drop"].forEach(ev => window.addEventListener(ev, e => { if (ev === "dragleave" && e.relatedTarget) return; document.body.classList.remove("dropping"); }));
window.addEventListener("drop", async e => {
  const files = [...(e.dataTransfer.files || [])].filter(f => /\.(png|jpe?g|webp)$/i.test(f.name)); if (!files.length) return; e.preventDefault();
  const payload = await Promise.all(files.map(f => new Promise(res => { const rd = new FileReader(); rd.onload = () => res({name: f.name, data: rd.result}); rd.readAsDataURL(f); })));
  const r = await api("/api/add_images", {files: payload}); if (r.error) { toast(r.error); return; } toast(`Added ${r.added} render${r.added === 1 ? "" : "s"} to the folder`, "ok", 4000); poll();
});
window.addEventListener("pagehide", () => { try { navigator.sendBeacon("/api/bye", "{}"); } catch {} });
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") poll(); });
document.addEventListener("keydown", e => {
  if (e.metaKey || e.ctrlKey || ["INPUT","TEXTAREA","SELECT"].includes(e.target.tagName)) return;
  const m = {"1":"before","2":"wipe","3":"after"};
  if (m[e.key]) $(`.seg button[data-mode=${m[e.key]}]`).click();
  else if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); jump(1); }
  else if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); jump(-1); }
});
boot();
</script>
</body>
</html>
"""


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
