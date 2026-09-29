## Render Post v1.10.0

Image and video **generation** (not prompt-writing, not vision analysis — those always stay on
fal) can now be sent to a third-party aggregator instead of fal.ai, chosen per model in the
existing Model / Video model dropdowns, exactly like switching between GPT Image and Nano Banana
today.

Higgsfield ships connected-and-ready: "GPT Image 2.5 Flare/Sunburst · Higgsfield" and "Seedance
2.5 · Higgsfield" sit next to their fal counterparts once you connect it (same underlying models,
different billing path — Higgsfield draws on your existing subscription credits instead of a
separate paid balance). New "Connect providers" button next to Change key handles that: an
API-key form, or a one-time "Connect" for anything using OAuth — after that one click, every
actual generation job runs headless, same as fal. A provider's models only show up in the
dropdowns once it's connected, and disconnecting reverts to fal-only immediately. Artlist and
Nim.video aren't wired up yet; the same mechanism is ready for them once their connection details
are worked out. Anyone can add their own provider too — "Add a custom provider" now explains how.

Nothing else changed since 1.9.0.
