## Render Post v1.13.0

**Nano Banana 2.1** (Google's newest model, released this week) is now available as a
recommended model on all three providers:

- **Nano Banana 2.1 · Google** — direct via fal
- **Nano Banana 2.1 · Google** (Higgsfield-tagged) — via your Higgsfield subscription
- **Nano Banana 2.1 · Google** (Nim-tagged) — via your Nim.video credits

All three keep the output's aspect ratio matching your source image automatically.

**Fix:** toggling the per-image Character checkbox right before Rewrite/Enhance/Angles could
occasionally be dropped — the generation could start before the checkbox's own save had landed.
That race is gone; the checkbox state now travels with the same request.

**New:** a scroll-to-top button for long image grids, and a lightbox for the character reference
thumbnail — click it to view the reference image full-size, or click the empty placeholder to
jump straight to the upload dialog.

Also fixed: GPT Image 2.5 Flare/Sunburst via Nim.video had a working Quality setting that never
actually showed up in the dropdown — it's visible now.
