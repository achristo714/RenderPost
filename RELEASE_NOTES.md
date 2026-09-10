## Render Post v1.8.4

GPT Image 2 is gone. In its place: **GPT Image 2.5 Flare** (the new default) and **GPT Image 2.5 Sunburst**.

- **Flare** is the fast tier: the same photoreal strengths as before, up to half the latency.
- **Sunburst** is the precision tier: slower, priced the same, for edits where fine detail has to hold.
- If your saved model was GPT Image 2, you are moved to Flare automatically.
- Quality gets two new steps above High: **Extra high** and **Max**. Cost climbs steeply with them, so the running spend estimate now follows fal's published price table by quality and output size instead of a flat $0.25 an image. At Medium and 3K a Flare image is about 2 cents; at Max and 4K about 40 cents.

Nano Banana Pro and Nano Banana 2 are unchanged.

Not yet verified against live fal: the first real Flare and Sunburst runs. The request format is identical to GPT Image 2 per fal's published schema, so no change is expected, but if an enhance fails on either, report it.
