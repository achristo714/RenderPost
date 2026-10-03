## Render Post v1.12.1

Fixed another real bug from testing the last release: GPT Image 2.5 Flare and Sunburst via
Nim.video always produced a 16:9 output, no matter what aspect ratio the source render actually
was. Nim quietly defaults to 16:9 whenever the aspect ratio isn't explicitly specified — now it is,
matched to the source image (or the closest ratio Nim supports, when an exact match isn't
available). Nano Banana Pro Edit and Nano Banana 2 via Nim were adjusted too, using Nim's own
"match the input automatically" option. Higgsfield and fal were never affected by this.

Nothing else changed since 1.12.0.
