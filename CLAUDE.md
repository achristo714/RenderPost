# Render Post: notes for Claude Code sessions

Two people work on this repo with Claude Code (Andy, the owner, and Filip, a collaborator).
Read this whole file before changing anything. It is short on purpose.

## What this is

A small Python app that becomes one Windows exe. `RenderPost.py` starts a local HTTP server,
opens a browser page, and runs AI enhancement, angles, characters and video on a folder of
architectural renders through the user's own fal.ai key. There is no framework, no database and
no test suite. The product is `dist\RenderPost.exe`, built by PyInstaller.

## Repo layout

| Path | What belongs there |
| --- | --- |
| `RenderPost.py` | The app: constants, `Fal` client, `DemoFal`, `State`, `Handler` (all `/api/*` and `/static/*` routes), `main()`. Entry point for the exe. |
| `prompts.py` | The art-director prompt briefs (`BASE_BRIEF`, `ANGLES_BRIEF`, `TAKE_BRIEF`, `ENERGY`, and so on). Edit prompt wording here. |
| `web/templates/index.html`, `web/static/app.css`, `web/static/app.js` | The single-page UI. Plain HTML, CSS and JS, served by the app and bundled into the exe with `--add-data "web;web"`. |
| `requirements.txt` | Python dependencies. `build.bat` and the workflow both install from it. |
| `models.json` | Model catalog the app fetches on launch from `main`. Editing it changes every user's model list without a rebuild. |
| `build.bat` | Local Windows build. Its PyInstaller line must stay identical to the one in the workflow. |
| `.github/workflows/build-exe.yml` | Builds the exe on every push to `main`. If `APP_VERSION` has no tag yet, it also creates the tag and the GitHub Release with `RELEASE_NOTES.md` as the body. |
| `RELEASE_NOTES.md` | Body of the next release. Rewritten each release. |
| `CHANGELOG.md` | Running history. Append, do not rewrite. |
| `docs/` | User guide PDF and README screenshots. |
| `RenderPost.ico`, `RenderPost-orange.ico` | App icons. |

Ignored and never committed: `build/`, `dist/`, `*.spec`, `__pycache__/`, `enhanced/`, loose `*.png`.

## Branch rules (enforced by a GitHub ruleset on `main`)

- `main` is protected. Direct pushes are rejected for collaborators. Every change goes through a
  pull request that needs one approving review. Andy (repository admin) can bypass this for
  version bumps, release notes and tags.
- Force pushes and branch deletion on `main` are blocked.
- Workflow: branch from `main` (for example `dev/filip`, `fix/reel-order`), commit, push the
  branch, open a PR against `main`. Do not push to `main` and do not try to work around the
  ruleset.
- One topic per PR. A refactor PR contains no behavior changes. A feature PR contains no
  unrelated refactoring. Reviewers cannot verify a mixed PR.
- If the exe changes, it ships. Any PR that touches `RenderPost.py`, `prompts.py`, `web/`,
  `requirements.txt`, `build.bat` or the workflow bumps `APP_VERSION` and updates the release
  notes in the same PR, refactors included; the workflow publishes the release when the merge
  lands on `main` (see Release below). Only docs-only changes (README, CLAUDE.md, CHANGELOG,
  docs/) skip the bump. Everyone runs the exe, so an unreleased merge is invisible.

## Working rules

- Do not refactor, rename, reorder or reformat code outside the scope of the current task.
  Diffs on a 2,700-line file are reviewed by eye; noise hides real changes.
- No formatter is configured. Do not run black, ruff format or an IDE reformat over existing
  code. Adopting a formatter is its own PR, agreed first, and applied in one commit with
  nothing else in it.
- Keep `RenderPost.py` as the entry point name. `build.bat`, the workflow, the README and the
  docstring all reference it.
- These must survive any change unchanged unless the task is specifically about them:
  `APP_NAME`, `APP_VERSION`, `UPDATE_URL`, `MODEL_CATALOG_URL`, `OUTPUT_DIRNAME`, the
  `enhanced/` folder layout (`name_v01.png`, `name_a01.png`, `picks/`, `compare/`, `video/`,
  `trash/`) and the config location `%APPDATA%\RenderPost`. Users have existing folders that
  depend on them.
- If a change adds a Python dependency or a data file the exe needs (for example a `web/`
  folder), update the `pyinstaller` line in both `build.bat` and the workflow in the same PR,
  and say so in the PR description. A missing `--collect-all` or `--add-data` builds green and
  breaks at runtime.
- Do not add a license file. Do not add third-party frontend frameworks or build steps; the
  page is plain HTML, CSS and JS served by the app.
- Never commit a fal key, a log file or anything from a render folder.

## Code conventions (match what is there)

- Constants live at the top of `RenderPost.py` as module-level `UPPER_SNAKE` names. Prompt briefs
  live in `prompts.py` as plain triple-quoted strings; edit wording there, not inline in handlers.
- All fal calls go through the `Fal` class. `DemoFal` mirrors its interface with fake results so
  `--demo` mode works without a key. Any new `Fal` method needs a `DemoFal` twin.
- Network calls are wrapped in `with_retry()` (3 attempts, exponential backoff, no retry on 401
  or 402). User-facing error text comes from `friendly(e)`; add new mappings there rather than
  building messages in handlers.
- Routes are `if path == "/api/...":` blocks in `Handler`. JSON in, JSON out. The UI is served
  from `web/` via `resource_path()`, which resolves to the PyInstaller bundle when frozen. Long work runs on
  the `ThreadPoolExecutor`; the handler returns immediately and the page polls `/api/state`.
- App state is the single `State` instance. Per-folder settings persist in the render folder,
  user settings in `%APPDATA%\RenderPost\config.json`.
- Logging is `print()`. In the exe, stdout is redirected to `%APPDATA%\RenderPost\log.txt`.
  Do not add a logging framework.
- Money: every spend path shows an estimate first. If you add a paid call, add its price to the
  running-spend estimate.

## Verify before opening a PR

1. `python -m py_compile RenderPost.py` (and any new modules).
2. `python RenderPost.py --demo` on a folder with a few images. Click through the part you
   changed. Confirm the page loads, prompts generate, an enhancement saves a version.
3. If you touched the build line, imports, or file layout: run `build.bat`, launch
   `dist\RenderPost.exe`, and repeat step 2 inside the exe. The exe is what users run.
4. In the PR description state what you ran. "Compiles" is not verification.

## Release (automatic once a version bump reaches `main`)

The workflow does the release. On every push to `main` it builds the exe, reads `APP_VERSION`
from `RenderPost.py`, and if no tag exists for that version it creates the tag and the GitHub
Release with `RELEASE_NOTES.md` as the body and the exe attached. Nobody pushes tags by hand.

So any PR that changes what goes into the exe must carry its own release:

1. Bump `APP_VERSION` in `RenderPost.py`. Patch bump (`1.8.3`) for fixes and refactors, minor
   bump (`1.9.0`) for features. Two open PRs must not claim the same version; the second one rebases and
   bumps again.
2. Rewrite `RELEASE_NOTES.md` for this version. It becomes the release body verbatim.
3. Add a `CHANGELOG.md` entry.
4. After the merge, watch the "Build RenderPost.exe" run on `main`. When it is green, confirm
   `https://github.com/achristo714/RenderPost/releases/latest` shows the new version with
   `RenderPost.exe` as an asset. Post that URL in the PR. The app's header shows the update
   link to every user once the release exists.

A code change merged without a version bump is a bug: users never see it, and the exe they run
no longer matches `main`. If the release
run fails, fix forward on a new branch and PR with another bump. Do not delete or move a
published tag. Do not hand-upload a locally built exe; the asset always comes from the
workflow so every user gets the same build.

Docs-only PRs leave `APP_VERSION` alone and produce no release. A refactor is not docs-only:
it changes the exe, so it bumps and ships, with release notes that say "internal restructure,
no user-facing changes".
