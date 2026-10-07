## Render Post v1.13.0

**Nano Banana 2.1** (Google's newest model, released this week) is now available as a
recommended model on all three providers:

- **Nano Banana 2.1 · Google** — direct via fal
- **Nano Banana 2.1 · Google** (Higgsfield-tagged) — via your Higgsfield subscription
- **Nano Banana 2.1 · Google** (Nim-tagged) — via your Nim.video credits

All three keep the output's aspect ratio matching your source image automatically. Being brand
new, all three can still be inconsistent — a content-filter refusal or an off-prompt result is
worth a retry or a reworded prompt; a short note to that effect now shows under the Model
selector for each.

**New:** a scroll-to-top button for long image grids, and a lightbox for the character reference
thumbnail — click it to view the reference image full-size, or click the empty placeholder to
jump straight to the upload dialog.

**Fix:** an image card's version/angle tabs (v1, v2, a1...) used to crowd the image name on a
long version history, wrapping the name letter-by-letter and eventually pushing tabs out of
view. They now get their own row right under the name and wrap onto further rows themselves as
they build up.

**Fix:** changing Model/Quality/Resolution and immediately clicking Enhance/Angles on a card
could silently run against the *previous* model — the dropdowns save a moment after you change
them, and a fast click could beat that save. Fixed by flushing the save first, the same way
"Enhance all" already did.

**Fix:** toggling the per-image Character checkbox right before Rewrite/Enhance/Angles could
occasionally be dropped — the generation could start before the checkbox's own save had landed.
That race is gone; the checkbox state now travels with the same request.

**Fix:** a content-filter refusal on any model used to say "Seedance refused the input images:
its content filter flags realistic people" even when the model wasn't Seedance at all — that
specific explanation is now shown only for an actual Seedance refusal; every other model gets an
honest, model-agnostic message.

**Fix:** Higgsfield could fail with an opaque "Server returned an error response" even on a
healthy request — the real cause, a plain expired access token, was getting masked by a generic
fallback before this app ever saw it. A silent token refresh now also covers this case; if it
still fails, the error now says to reconnect the provider instead of leaving you guessing.

Also fixed: GPT Image 2.5 Flare/Sunburst via Nim.video had a working Quality setting that never
actually showed up in the dropdown — it's visible now.
