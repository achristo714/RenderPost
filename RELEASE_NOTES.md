## Render Post v1.10.0

Image and video **generation** (not prompt-writing, not vision analysis — those always stay on
fal) can now be sent to a third-party aggregator instead of fal.ai, chosen per model in the
existing Model / Video model dropdowns, exactly like switching between GPT Image and Nano Banana
today.

Higgsfield ships connected-and-ready, with twelve models next to their fal counterparts once you
connect it (same underlying models, different billing path — Higgsfield draws on your existing
subscription credits instead of a separate paid balance): "GPT Image 2.5 Flare/Sunburst",
"Nano Banana Pro", "Nano Banana 2" and "Seedance 2.5 · Higgsfield" in the image/video pickers, plus
"Kling 3.0", "MiniMax H3", "Veo 3.1", "Gemini Omni Flash 1.1", "Grok Imagine 1.5", "Happy Horse
Video" and "MiniMax Hailuo 2.3 · Higgsfield" as video-only additions. GPT Image 2.5 via Higgsfield
now has its own Quality selector alongside Resolution (previously fixed to Medium); Kling 3.0 and
Veo 3.1 likewise gained a Resolution control for their real quality tiers (previously fixed to one
tier each). New "Connect providers" button next to Change key handles the one-time setup: an
API-key form, or a one-time "Connect" for anything using OAuth — after that one click, every actual
generation job runs headless, same as fal. A provider's models only show up in the dropdowns once
it's connected, and disconnecting reverts to fal-only immediately. Artlist and Nim.video aren't
wired up yet; the same mechanism is ready for them once their connection details are worked out.
Anyone can add their own provider too — "Add a custom provider" now explains how.

Known issue: Gemini Omni Flash 1.1, Grok Imagine 1.5, Happy Horse Video and MiniMax Hailuo 2.3
currently fail to generate through the app even though their settings are verified correct against
Higgsfield's own API — likely an account/plan access gap, under investigation. Every other model,
including the rest of the Higgsfield lineup, is unaffected.

Nothing else changed since 1.9.0.
