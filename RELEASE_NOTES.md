## Render Post v1.10.0

Image and video **generation** (not prompt-writing, not vision analysis — those always stay on
fal) can now be sent to a third-party aggregator instead of fal.ai, chosen per model in the
existing Model / Video model dropdowns, exactly like switching between GPT Image and Nano Banana
today.

New "Connect providers" button next to Change key opens a settings panel listing any aggregators
in the model catalog, with a Connect action for each (an API-key form, or a one-time "Connect"
button for anything using OAuth — after that one click, every actual generation job runs
headless, same as fal). A provider's models only show up in the dropdowns once it's connected.

Nothing is built in by default — Render Post doesn't favor one aggregator. Providers arrive the
same way extra models already do: a JSON file at your catalog URL, no rebuild needed, or pasted
directly into Connect providers as a one-off "custom provider" for testing.

Nothing else changed since 1.9.0.
