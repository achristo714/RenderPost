# Changelog

## 1.8.5
- Fix: running spend could undercount when several images finished at the same moment. The project settings file is now written under a lock.

## 1.8.4
- GPT Image 2 replaced by GPT Image 2.5 Flare (default) and Sunburst. Saved configs on GPT Image 2 move to Flare. Quality gains Extra high and Max. Spend estimate for GPT models now uses fal's per-quality, per-size price table instead of a flat $0.25.

## 1.8.3
- Character activation moved from a global batch switch to a per-image checkbox, with an optional
  per-image placement/pose note that combines with the existing project-wide note. Seedance
  character warning dialog on first activation per session. Fixed the project-wide character note
  field not being persisted. (Filip Filyov)

## 1.8.2
- Internal restructure: prompt briefs moved to `prompts.py`, page HTML/CSS/JS moved to `web/` and bundled into the exe. Dependencies listed in `requirements.txt`. No behavior change. (Filip Filyov)

## 1.8.1
- Update check and model catalog point at this repository.

## 1.8.0
- Enhance selected, Grid view, running spend, More fold, delete version, in-app dialogs, folder watching, drag and drop, angle auto-After.

## 1.7.x
- Character (generate or upload) for enhancements, angles and takes. Tick-order reels with badges, music folder button, catalog dialog, Picks gallery, image prompt export, draft-loss fix, reel sizes to largest clip.

## 1.6.x
- New project switcher with recents. Favicon. H3 Max parameter fixes, H3 Max Turbo, show-all visibility, Picks tab, Camera energy, prompt export.

## 1.5.x
- Angles: new camera positions from a finished version.

## 1.4.0
- Model catalog with recommended flag and show all; H3 Max as default video model.

## 1.3.x
- Kling 3.0 Pro; briefs aligned with vendor prompting docs; Kling multi-shot storyboard; video range serving fix; watchdog fix; reel toggle, music start, real resolutions.

## 1.2.x
- Video rebuilt as Images / Video sections with Frames, Make clips, Reel; multi-shot prompts.

## 1.1.x
- Video: clips, reels, single takes on Seedance 2.5.

## 1.0.x
- Image enhancement with reviewable prompts, versions, picks, before/after, Nano Banana models, GPT Image 2.
