## Render Post v1.11.0

Nim.video joins Higgsfield as a second built-in aggregator provider — same "pick it from the Model
/ Video model dropdown" mechanism, no separate switch. Once connected (Connect providers →
Nim.video, one-time browser sign-in), you get "Nano Banana Pro Edit" and "GPT Image 2.5 Flare" in
the image picker and "Hailuo 2.3 Fast" and "Seedance 2.5" in the video picker, billed on your own
Nim.video credits instead of a separate fal balance. Every parameter, price and upload mechanic
was checked live against Nim's own tools rather than assumed from Higgsfield's shape — Nim turned
out to need a genuinely different upload step (no import-by-URL; a short-lived upload slot plus a
direct file POST) and a different reference-image shape (a flat list, not role-tagged), both now
general engine features any future provider can also use. "Seedance 2.5 · Nim" ships with its
resolution fixed to 720p for now (its pricing at other tiers isn't confirmed yet) and hasn't been
run through an actual generation — try a short clip yourself before relying on it.

Also in this release: the MiniMax H3 character-reference fix from 1.10.0 was re-confirmed working
end-to-end this session (no code change needed).

Artlist is next, once its own connection details are worked out.

Nothing else changed since 1.10.0.
