# How Higgsfield connectivity was built — a blueprint for the next aggregator

Written as a handoff document before implementing Nim.video as the second aggregator provider.
Everything below describes the real, current, working state of the Higgsfield integration in
`RenderPost.py` as of branch `filip-aggregator-providers` (commit `170e6df`). Read this before
touching `PROVIDERS`/`MODELS`/`VIDEO_MODELS` for a new provider — the engine is deliberately
generic; a new aggregator should almost never need a new mechanism, only a new declarative entry.

## 1. The non-negotiable scope boundary

**fal.ai does every vision-model call and every prompt-writing call, always, for every project,
regardless of which provider ends up generating the image or video.** This was the first and most
important design decision and it has not moved once across the whole Higgsfield build:

- `Fal.upload()` uploads every source image and reference image (the render itself, angle sources,
  the character portrait) — an aggregator-routed generation still gets its input image hosted by
  fal first; the aggregator only ever receives a URL (or imports it from one), never does its own
  upload of RenderPost's original source file.
- `Fal.write_prompt()`, `Fal.write_angles()`, `Fal.write_motion()`, `Fal.generate_character()` are
  the *only* code paths that call a vision/reasoning model. `AggregatorProvider` (the universal
  client every non-fal provider uses) implements exactly three methods — `edit()`, `video()`,
  `download()` — and nothing else. It has no way to write a prompt even if you wanted it to.
- Consequence for a new provider: however it's implemented, it is wired in at exactly two
  dispatch points (image edit, video generation) and nowhere else. If you find yourself routing a
  vision or prompt call through the new provider, stop — that's out of scope by design, not an
  oversight.

## 2. The declarative `PROVIDERS` catalog — one generic engine, N providers

`PROVIDERS` (a module-level dict in `RenderPost.py`, ~line 191) holds one entry per aggregator.
Nothing provider-specific lives in Python code; a new provider is *data*, not a new class. The one
entry that exists today:

```python
PROVIDERS = {"higgsfield": {
    "label": "Higgsfield", "transport": "mcp_http", "mcp_url": "https://mcp.higgsfield.ai/mcp",
    "auth": {"type": "oauth2", "authorize_url": ..., "token_url": ..., "registration_endpoint": ...,
             "scope": "openid email offline_access", "fields": ["access_token", "refresh_token"]},
    "operations": {
        "image": {"steps": [...]},
        "video": {"steps": [...]},
    }
}}
```

`transport` picks which of three generic call paths `AggregatorProvider._call()` uses:
`rest_async` (submit → poll → done — built for this, never actually needed since Higgsfield turned
out to be MCP), `rest_sync` (a plain synchronous REST call), or `mcp_http` (the one Higgsfield
actually uses — a remote MCP server over Streamable HTTP). All three are implemented and tested at
the engine level; only `mcp_http` has a real provider behind it so far. **If Nim.video turns out to
offer a plain REST API instead of MCP, `rest_async`/`rest_sync` already work — verify which one
Nim's connector actually implies and use that, don't assume MCP just because Higgsfield happened
to be MCP.**

### Auth

`auth.type` is `"header_template"` (a fixed API-key format string), `"bearer"`/`"oauth2"` (a
stored access token, `Authorization: Bearer ...`), with OAuth2 further supporting Dynamic Client
Registration (RFC 7591, `registration_endpoint`) so RenderPost never needs a hardcoded
`client_id` — it registers itself fresh on every "Connect" click, since the local OAuth
redirect's port changes every launch (`free_port()`). `_oauth_register()`/`_oauth_exchange()`
implement this generically; a provider only needs to declare its real `authorize_url`/`token_url`
(and `registration_endpoint` if it supports DCR — if not, a fixed `client_id` in `auth` works
instead). **Don't assume Nim uses OAuth2 — check what its actual connector/MCP setup implies.**

### The declarative `steps` template engine

Each operation (`image`, `video`) is an ordered list of `steps`. Each step names an MCP `tool` and
an `arguments` template. `_fill_template()` (RenderPost.py) fills placeholders like `"{prompt}"`
from a plain `args` dict that steps can read from and write to:

- A string that is *exactly* one placeholder (`"{x}"`) is replaced with the raw arg value,
  preserving its type (a list, a bool, a number) — not stringified.
- A dict can carry `"_when": "<arg>"` — if that arg is falsy, the *whole dict* is dropped from its
  parent list (used for an optional reference image in a `medias` array).
- A step can carry `"when": "<arg>"` — if that arg is falsy, the *whole step* is skipped (used for
  an optional character-reference import step).
- **A key whose filled value resolves to exactly `None` is dropped from its parent dict entirely**
  (not sent as a literal null). This is what lets *one* shared template serve several underlying
  models with different parameter schemas — a model's catalog entry either doesn't declare a given
  template variable (reads back as `None` via `args.get(...)`) or explicitly sets it to `None` to
  suppress a value a shared default would otherwise supply. This mechanism single-handedly avoids
  needing a separate template per model.
- `step.output_as` + `step.output_field` extract a value (via `_dig()`, supporting dotted paths and
  numeric list indices, e.g. `"jobs.0.job_id"`) from a step's result and store it back into `args`
  under a new name, so later steps can reference it.
- A step can carry `"poll": true` plus `poll_done_field`/`poll_done_value`/`poll_delay_field` — the
  same tool call repeats until the done-condition is met, sleeping for whatever the response's own
  delay field says (falling back to a fixed default), up to `poll_max_attempts`.

Higgsfield's real `image`/`video` operations (verbatim from the current code):

```python
"image": {"steps": [
    {"tool": "media_import_url", "arguments": {"url": "{image_url}", "type": "image"},
     "output_as": "media_id", "output_field": "media_id"},
    {"tool": "media_import_url", "when": "character_url", "arguments": {"url": "{character_url}", "type": "image"},
     "output_as": "character_media_id", "output_field": "media_id"},
    {"tool": "generate_image_batch", "arguments": {"requests": [{"index": 0, "params": {
        "model": "{higgsfield_model}", "variant": "{variant}", "quality": "{quality}",
        "resolution": "{resolution}", "aspect_ratio": "{aspect_ratio}", "prompt": "{prompt}",
        "declined_preset_id": "{declined_preset_id}",
        "medias": [{"value": "{media_id}", "role": "image_references"},
                    {"value": "{character_media_id}", "role": "image_references", "_when": "character_media_id"}],
        "use_unlim": False}}]},
     "output_as": "job_id", "output_field": "jobs.0.job_id"},
    {"tool": "jobs_wait", "poll": True, "poll_done_field": "all_terminal",
     "poll_delay_field": "poll_after_seconds", "poll_delay": 5,
     "arguments": {"jobs": [{"index": 0, "job_id": "{job_id}"}], "timeout_seconds": 15},
     "output_field": "jobs.0.result_url"}]},
"video": {"steps": [
    {"tool": "media_import_url", "arguments": {"url": "{image_url}", "type": "image"},
     "output_as": "media_id", "output_field": "media_id"},
    {"tool": "media_import_url", "when": "character_url", "arguments": {"url": "{character_url}", "type": "image"},
     "output_as": "character_media_id", "output_field": "media_id"},
    {"tool": "generate_video_batch", "arguments": {"requests": [{"index": 0, "params": {
        "model": "{higgsfield_model}", "mode": "{mode}", "sound": "{sound}", "quality": "{quality}",
        "duration": "{duration}", "resolution": "{resolution}", "aspect_ratio": "16:9",
        "generate_audio": "{generate_audio}", "prompt": "{prompt}",
        "declined_preset_id": "{declined_preset_id}",
        "medias": [{"value": "{media_id}", "role": "{frame_role}"},
                    {"value": "{character_media_id}", "role": "image_references", "_when": "character_media_id"}],
        "use_unlim": False}}]},
     "output_as": "job_id", "output_field": "jobs.0.job_id"},
    {"tool": "jobs_wait", "poll": True, "poll_done_field": "all_terminal",
     "poll_delay_field": "poll_after_seconds", "poll_delay": 5,
     "arguments": {"jobs": [{"index": 0, "job_id": "{job_id}"}], "timeout_seconds": 15},
     "output_field": "jobs.0.result_url"}]},
```

Both operations use Higgsfield's own *batch* submission tools (`generate_image_batch`,
`generate_video_batch`) — not the singular, interactive-widget tools (`generate_image`,
`generate_video`), which are meant for a chat UI, not headless use — followed by `jobs_wait`, a
long-poll (~15s per call) status tool, repeated until `all_terminal`. **Check whether Nim's MCP
exposes an equivalent batch-vs-widget distinction; if it only has one generation tool, that's fine,
just confirm which one is meant for headless/background use before wiring it in.**

## 3. `AggregatorProvider` — the one class every provider shares

`AggregatorProvider.__init__(provider_id, defn, creds)` is constructed from a `PROVIDERS` entry
plus stored credentials. It implements only what `State` needs for the two production calls:

- `edit(image_url, prompt, cfg, src_dims, cancelled, extra_urls=())` — image generation.
  `extra_urls[0]`, if present, becomes `character_url` in the template args (an optional second
  reference image). `aspect_ratio` is computed from `src_dims` via `math.gcd`.
- `video(prompt, image_urls, cfg, take, cancelled, extra_urls=())` — video generation. Same
  `character_url` convention. `duration` comes from `cfg["take_duration"]` or
  `cfg["video_duration"]` depending on `take`.
- `download(url, out_path)` — plain `urllib` fetch, used for both.

Both `edit()`/`video()` build an `args` dict with cfg-derived defaults, then spread the model's own
`_model_extra` dict **last** (so a catalog entry's own declared value — including an explicit
`None` — wins over a live UI default). This is what lets a model override something the UI
currently shows without touching the UI: e.g. a model with only one resolution value hides the
Resolution control (`"res": None` in its catalog entry) but still needs *some* fixed value sent
(`"resolution": "2K"` as a template-var override); a model with no resolution parameter at all
needs the opposite — the key suppressed entirely (`"resolution": None`, dropped by the template
engine's None-filtering).

Two further per-model escape hatches exist, both discovered by hitting a real API constraint, not
designed in advance:

- **`res_param`**: redirects the UI's Resolution control into whatever field the model actually
  calls its tier, when it isn't literally named `"resolution"` (Kling's `"mode"`: std/pro/4k; Veo's
  `"quality"`: basic/high/ultra). `AggregatorProvider.video()` reads `extra.get("res_param")`, and
  if set, uses the UI's live resolution value under that key instead.
- **`char_ref_exclusive`**: some models (MiniMax H3, confirmed live) reject their normal start-frame
  role (`start_image`) when *any* reference image is also present — the two are mutually exclusive
  at the API level, not combinable the way Seedance 2.5 combines them. The template's first media
  entry uses role `"{frame_role}"` (a template var, not a hardcoded string); `video()` computes it
  as `"start_image"` normally, or `"image_references"` when a character reference is active *and*
  the model's catalog entry sets `"char_ref_exclusive": True`.

**Lesson for Nim**: don't assume any model combines a start frame with a reference image the same
way another model does. If Nim's generation models accept multiple reference images, verify via
its own MCP tools exactly how a "this is the one to animate" image is distinguished from "this is
who/what should look consistent" images — test it live before writing the catalog entry, the same
way `char_ref_exclusive` was discovered (a real 422 from the real API, not a guess).

## 4. The model catalog — `MODELS`/`VIDEO_MODELS`, `provider` field

Every image model lives in `MODELS`, every video model in `VIDEO_MODELS` — both plain dicts keyed
by an internal id RenderPost invented (not necessarily the provider's own model id). A model entry
defaults to `"provider": "fal"` if the key is absent (today's behavior, unchanged); setting
`"provider": "higgsfield"` routes it through `AggregatorProvider` instead. Fields split into two
groups:

- **Structural** (`_MODEL_CATALOG_STRUCTURAL_KEYS`): `label`, `kind`, `endpoint`, `i2v`, `provider`,
  `price`, `mult`, `hint`, `recommended`, `res`, `min_duration`, `price_table`, `durations`. These
  drive the UI (dropdown label, which controls to show, the price estimate) and are never sent to
  the provider.
- **Everything else** becomes a template variable via `_model_extra_args()` — e.g. `higgsfield_model`
  (the provider's own real model id), `variant`, `mode`, `sound`, `quality`, `res_param`,
  `char_ref_exclusive`. A new field name just works the moment a template references
  `"{that_name}"` — no engine change needed to add a new per-model knob.

Today's Higgsfield lineup (8 models, all verified live against real `models_explore`/cost-preflight
calls before being added, never guessed from documentation):

| Catalog id | Underlying Higgsfield model | Kind | Notes |
| --- | --- | --- | --- |
| `gpt-image-2.5-flare-higgsfield` / `-sunburst-higgsfield` | `gpt_image_2_5` | image, `"gptres"` | Quality + Resolution both selectable; `price_table` (quality×resolution), not a flat rate |
| `nano-banana-pro-higgsfield` | `nano_banana_pro` | image, `"nano"` | No quality param — explicitly suppressed (`"quality": None`) |
| `nano-banana-2-higgsfield` | `nano_banana_2` | image, `"nano"` | Same |
| `seedance-higgsfield` | `seedance_2_5` | video | `mode: "omni_reference"` fixed, audio off for predictable pricing; combines start_image + a character reference fine |
| `kling3-higgsfield` | `kling3_0` | video | `res_param: "mode"` (std/pro/4k); sound off |
| `minimax-h3-higgsfield` | `minimax_h3` | video | Fixed 2K (no real alternative); `char_ref_exclusive: True` |
| `veo3-1-higgsfield` | `veo3_1` | video | `res_param: "quality"` (basic/high/ultra); discrete duration set (4/6/8s only, via `durations` override) |

Five more models (Gemini Omni Flash 1.1, Grok Imagine 1.5, Happy Horse Video, MiniMax Hailuo 2.3,
FLUX.3 Video) were added, verified working, then **removed again** at Filip's request after direct
MCP testing showed two of them intermittently failing (confirmed via Higgsfield's own credit
refunds — a real backend reliability issue, not a RenderPost bug, not an account/plan gap). The
full investigation trail is git history on this branch; don't re-add them without checking whether
Higgsfield's backend for those specific models has stabilized.

### `gptres` — a third UI "kind"

The image controls originally supported exactly two mutually exclusive `"kind"`s: `"gpt"`
(Quality + pixel-size) and `"nano"` (Resolution only). GPT Image 2.5 via Higgsfield needed Quality
*and* Resolution together (real parameters on the Higgsfield side, unlike pixel-size which is
fal-only) — solved by splitting the Quality/Output-size CSS classes apart and adding a third kind,
`"gptres"`, that shows Quality + Resolution while hiding Output-size. **If Nim's image models need
some other combination the current UI can't express, this is the precedent for how to extend it —
split classes, add a kind, don't hack around the existing two.**

## 5. Dispatch — `State.generator_for()`

```python
def generator_for(self, model_entry):
    pid = (model_entry or {}).get("provider", "fal")
    if pid == "fal":
        return self.fal
    if pid in self.providers:
        return self.providers[pid]
    ...
    client = DemoAggregator(pid) if DEMO else AggregatorProvider(pid, PROVIDERS[pid], creds)
    self.providers[pid] = client
    return client
```

One cached client per connected provider id (not per model) — every Higgsfield-routed model shares
the same `AggregatorProvider("higgsfield", ...)` instance for the life of the running app. The three
call sites (`_job` for image edit, `_angles_job`, `_clip_job` for video) all go through this; none
of them care which provider they got back.

`DemoAggregator` delegates straight to a `DemoFal()` instance so `--demo` mode can exercise a
provider-backed model without credentials — required by CLAUDE.md's verification checklist.

## 6. Credentials and the Connect/Disconnect UI

`config.json` gained a `"providers"` dict (per-provider creds: API-key fields, or
`access_token`/`refresh_token`) and `"custom_providers"` (a pasted-in provider definition, for
anyone who wants to add one without a rebuild — the "Add a custom provider" panel). A new local
HTTP route, `/oauth/{provider_id}/callback`, exists only while a connect flow is in progress, to
receive the OAuth redirect and exchange the code server-side.

**The money this cost to learn, now fixed for any future provider**: `config.json` writes must be
atomic (`_atomic_write_json()` — write to a temp file, `os.replace()` into place) and both writers
(`save_config()`, `update_providers_config()`) must share one lock (`CONFIG_FILE_LOCK`). Without
this, a concurrent read during a provider connect/disconnect could catch a half-written file,
silently fall back to all-defaults, and the next save would write a blank `fal_key` straight back
to disk — this happened twice before being root-caused and fixed. **Nothing about adding Nim should
require touching this again** — it's already fixed generically, not per-provider.

## 7. Money — `price`/`price_table`, verified not assumed

Every model entry carries its own `price` (flat, or a dict keyed by resolution/tier) or
`price_table` (quality×resolution, for models where both independently affect cost). `image_cost()`/
`video_cost()` already key off whichever shape is present — adding Nim models needs no change here,
just real verified numbers in the same shape. **Every single price in the Higgsfield lineup came
from that provider's own cost-preflight tool** (`models_explore` + a `get_cost: true` preflight call
that doesn't spend anything), called with the exact resolution/duration/quality combinations the
catalog entry actually offers — never estimated, never copied from a pricing page. Do the same for
Nim: find its cost-preflight equivalent (or, if none exists, its real per-generation credit cost via
a cheap real call) before writing a single price number into the catalog.

## 8. The verify-live, never-guess discipline

This is the single biggest lesson from the whole Higgsfield build, and the explicit instruction for
Nim too. Every real bug fixed on this branch was found by *reproducing it live* — against the real
API, through the real MCP connector, not by reading documentation or reasoning about what "should"
happen:

- Model ids, parameter names, option values, aspect ratios, media roles — all pulled from
  `models_explore`, never assumed from a provider's marketing copy.
- The opaque `"unhandled errors in a TaskGroup"` crash turned out to be Higgsfield's own preset-
  recommendation system intercepting a literal prompt — found by unwrapping the real exception and
  reading its actual text, then reproducing the exact failing request through the MCP connector
  directly (bypassing RenderPost) to isolate whether it was a RenderPost bug or a provider-side one.
- The MiniMax H3 `char_ref_exclusive` constraint was found the same way: reproduce the exact failing
  request via the MCP connector first, try fixes against the *live API* until one is accepted
  cleanly, then and only then write the code change — confirmed working before being called "fixed."
- Five models were added, found flaky via direct independent MCP testing (not RenderPost), and
  removed — the MCP connector was the source of truth for "does this actually work," not assumption
  from either direction (not "it must work, Higgsfield lists it" and not "RenderPost failed, so it
  must be RenderPost's bug").

**Apply the identical discipline to Nim**: every model id, parameter, media/reference convention,
and price in the Nim catalog entries should trace back to a real call through
`mcp__claude_ai_Nim__*` made during this implementation, not to anything assumed from how Higgsfield
or any other aggregator happens to work. Different providers *will* differ in real, surprising ways
— that was true of Higgsfield's own eight models relative to each other (mode vs quality vs no
selector at all, combinable vs exclusive reference images, wildly different per-unit pricing) and
there's no reason to expect Nim to match any of those patterns by default.
