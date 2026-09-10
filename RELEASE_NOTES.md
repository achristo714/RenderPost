## Render Post v1.8.2

Internal restructure, no user-facing changes. Same features and behavior as 1.8.1.

The app is now split into separate files under the hood: the art-director prompt briefs live in `prompts.py`, and the page's HTML, CSS and JavaScript live in a `web/` folder that is bundled into the exe. This makes the code easier for two people to work on and review. Contributed by Filip Filyov.

If anything looks different from 1.8.1 in day-to-day use, that is a bug: report it.
