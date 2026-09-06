# Render Post: notes for Claude Code sessions

Two people work on this repo with Claude Code (Andy, the owner, and Filip, a collaborator).
Read this whole file before changing anything. It is short on purpose.

## What this is

A single-file Python app that becomes one Windows exe. `RenderPost.py` starts a local HTTP
server, opens a browser page, and runs AI enhancement, angles, characters and video on a folder
of architectural renders through the user's own fal.ai key. There is no framework, no database
and no test suite. The product is `dist\RenderPost.exe`, built by PyInstaller.

## Repo layout

| Path | What belongs there |
| --- | --- |
| `RenderPost.py` | The whole app: constants, prompt briefs, `Fal` client, `DemoFal`, `State`, `Handler` (all `/api/*` routes), the inline `PAGE` HTML/CSS/JS, `main()`. |
| `models.json` | Model catalog the app fetches on launch from `main`. Editing it changes every user's model list without a rebuild. |
| `build.bat` | Local Windows build. Its `pyinstaller` line must stay identical to the one in the workflow. |
| `.github/workflows/build-exe.yml` | Builds the exe on every push to `main` and on `v*` tags. A tag also creates the GitHub Release with `RELEASE_NOTES.md` as the body. |
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
- Releases are part of the job, not a separate ask. When a PR that changes app behavior is
  merged, the session that did the work cuts the release (see Release below). Users only see
  the change once a release exists; a merged PR with no release is unfinished work.

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

- Constants and prompt briefs live at the top of the file as module-level names in
  `UPPER_SNAKE`. Prompt text is a plain triple-quoted string; edit wording there, not inline in
  handlers.
- All fal calls go through the `Fal` class. `DemoFal` mirrors its interface with fake results so
  `--demo` mode works without a key. Any new `Fal` method needs a `DemoFal` twin.
- Network calls are wrapped in `with_retry()` (3 attempts, exponential backoff, no retry on 401
  or 402). User-facing error text comes from `friendly(e)`; add new mappings there rather than
  building messages in handlers.
- Routes are `if path == "/api/...":` blocks in `Handler`. JSON in, JSON out. Long work runs on
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

## Release (do this after every merged PR that changes the app)

Tags are not covered by the `main` ruleset, so a collaborator session can and should do this.

1. In the PR itself: bump `APP_VERSION` in `RenderPost.py`, rewrite `RELEASE_NOTES.md` for
   this version, and add a `CHANGELOG.md` entry. Patch bump (`1.8.2`) for fixes, minor bump
   (`1.9.0`) for features. A PR that changes app behavior without a version bump is incomplete.
2. After the PR is merged, tag the merge commit on `main`:
   ```
   git fetch origin main
   git tag -a vX.Y.Z -m "Render Post vX.Y.Z" origin/main
   git push origin vX.Y.Z
   ```
3. Watch the "Build RenderPost.exe" run for the tag. When it is green, confirm the Release at
   `https://github.com/achristo714/RenderPost/releases/latest` shows `RenderPost.exe` as an
   asset. Post that URL in the PR or to Andy. The app's header shows the update link to every
   user once the release exists.
4. If the run fails, fix forward on a new branch and PR. Do not delete or move a published
   tag. Do not hand-upload an exe built locally; the release asset always comes from the
   workflow so every user gets the same build.

Refactor-only or docs-only PRs (no behavior change) merge without a release.
