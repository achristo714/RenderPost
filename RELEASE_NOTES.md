## Render Post v1.12.0

Fixed a real bug in last release's Nim.video integration: enhancing through a Nim image model
could report "fal refused this request (403)" even though the generation had actually succeeded
(visible in Nim's own web UI) — the download step itself was failing, not the generation. Nim's
CDN rejects a request with no browser-style User-Agent header; now fixed.

GPT Image 2.5 Flare and Sunburst via Nim.video get a real Quality selector (Low/Medium/High —
previously fixed to Medium, since Nim bills each tier as its own underlying model rather than one
adjustable parameter). Four more Nim-routed models join the lineup: Nano Banana 2, Kling 3.0,
MiniMax H3 and Veo 3.1 — every parameter and price verified against Nim's own live model catalog.
Seedance 2.5 · Nim also gains its full 480p/720p/1080p resolution range (was fixed to 720p only).

A reminder from testing this release: a clip card stays locked to whichever video model it had
when you last wrote its motion prompt — picking a different model in the dropdown doesn't change
an existing card's model until you write its prompt again. This isn't new in this release, just
easy to trip over.

Nothing else changed since 1.11.0.
