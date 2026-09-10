## Render Post v1.8.3

Character is no longer an all-or-nothing switch for the whole batch. Each image now has its own
"Character" checkbox, visible once you've generated or uploaded a character in the character
panel. Turn it on for just the images that need it, and optionally tell it where to place the
person for that image ("seated at the counter", "walking through the doorway") — leave it blank
and the model places them naturally on its own. Your existing project-wide character note still
applies everywhere the character is used; a per-image note is folded in alongside it.

Checking the box the first time in a session shows a reminder that Seedance's video models
refuse frames with realistic people in them, with a "don't show this again" option for the rest
of the session.

Fixed: the project-wide character note field wasn't actually being saved — it now persists like
every other setting. Contributed by Filip Filyov.
