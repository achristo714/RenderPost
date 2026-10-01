# Changelog

## 1.10.0
- Image/video generation (never prompt-writing or vision analysis, which stay on fal) can be routed to a third-party aggregator instead of fal.ai, chosen per model in the existing Model/Video model dropdowns. New "Connect providers" settings panel handles per-provider API-key or one-time OAuth connect (Dynamic Client Registration where a provider supports it — no manual app registration needed); headless afterward, with silent token refresh. Providers are declarative catalog entries, added via the model catalog JSON or pasted as a custom provider (now with setup instructions in that panel); Higgsfield ships as a built-in entry (Flare/Sunburst/Seedance, paired against their fal counterparts, billed on your Higgsfield subscription instead of a separate balance) — Artlist/Nim.video to follow the same way. Fixed a race in config.json's own save path (unrelated autosaves could clobber a just-connected/disconnected provider) and a gap where a character reference was never passed through to an aggregator. (Filip Filyov)
- Added Nano Banana Pro and Nano Banana 2 as Higgsfield-routed image models, paired against their fal counterparts. GPT Image 2.5 via Higgsfield gains its own Quality selector (previously fixed to Medium); a new "gptres" model kind drives Quality + Resolution together, and the per-image spend estimate now uses a verified quality-by-resolution price table instead of a flat rate. Added Kling 3.0 Pro, MiniMax H3 and Veo 3.1 as new Higgsfield-only video models (no fal equivalent shipped for these), each fixed to a predictable, verified parameter set (mode/sound/quality tier) so spend stays a flat rate per second; Veo 3.1's duration selector is limited to the 4s/6s/8s values it actually accepts. All new model parameter names, options and per-model pricing were verified live against Higgsfield's model catalog and cost-preflight tool, not assumed. (Filip Filyov)
- Fix: a Higgsfield video/image generation could fail with an opaque "unhandled errors in a TaskGroup" error that hid the real cause. Found live with Kling 3.0 Pro: Higgsfield's batch tools can intercept a literal submission with "a preset was recommended instead" rather than submitting it — now auto-declined and resubmitted once, transparently. Also unwrapped the TaskGroup wrapper itself so any other underlying error (a real 401, a timeout, ...) shows its actual message instead of the generic wrapper text. (Filip Filyov)
- Fix: Kling 3.0 and Veo 3.1 via Higgsfield shipped with no Resolution control — both were fixed to a single hardcoded tier (Kling always "Pro", Veo always "Basic") even though each has a real, cost-varying quality tier at the API level (Kling's "mode": std/pro/4k; Veo's "quality": basic/high/ultra). Renamed "Kling 3.0 Pro" to "Kling 3.0" and gave both models a proper Resolution dropdown driving their real tier parameter, each verified against its real per-tier cost. MiniMax H3 still has no Resolution control — verified it genuinely only offers one resolution ("2K") at the API level, so there is nothing to select. (Filip Filyov)
- Added Gemini Omni Flash 1.1, Grok Imagine 1.5, Happy Horse Video and MiniMax Hailuo 2.3 as new Higgsfield-only video models, with resolution/duration options verified against each model's real schema and per-tier pricing verified live. ("Flux.3" was also requested but does not exist in Higgsfield's current catalog — not added.) Hardened the MCP call path generally: a failing call now retries up to 3 times with backoff before giving up (matching the retry pattern already used for REST calls elsewhere), and failures are now logged with their real underlying cause for diagnosis. Known issue: these four new models currently fail consistently when generated through the app (reproduced across multiple source images and both AI-written and hand-written prompts), while an identical request against Higgsfield's API directly succeeds — most likely an account/plan entitlement gap rather than a bug in these settings, but not fully isolated. Kling 3.0, Veo 3.1, MiniMax H3 and Seedance 2.5 are unaffected and continue to work normally. (Filip Filyov)

## 1.9.0
- Style notes and Motion notes gain saved phrases: select text and "Add phrase" to save it, then reopen it from a "Saved phrases" button or Shift+Tab in either box and click to insert it at your cursor. Both boxes share one phrase library. Phrases can be deleted from the same list. Stored in a new `%APPDATA%\RenderPost\phrases.json`, separate from other settings and shared across every project. (Filip Filyov)

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
