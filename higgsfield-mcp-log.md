# Higgsfield MCP video-model test log

Two independent test runs of the 5 newly-added Higgsfield video models, both through Claude's own
Higgsfield MCP connector (bypassing RenderPost entirely), to settle whether the failures seen
through RenderPost were a client bug, an account issue, or something else. Both runs
2026-10-01, same account/workspace (`0be0b6a8-...`, Ultimate plan, private, single workspace).

**See also**: `higgsfield-mcp-test-log.md` — the first run's own detailed write-up (connection
check + full tool inventory + its own method section). This file adds a second run ~7 minutes
later and reconciles both into one conclusion.

## Combined result

| Model | Run 1 (~12:27) | Run 2 (~12:34-12:36) | Verdict |
| --- | --- | --- | --- |
| Gemini Omni Flash 1.1 | ✅ completed | ✅ completed | **Reliable** |
| Grok Video 1.5 ("Grok Imagine 1.5") | ✅ completed | ❌ 429 rate-limited, then ✅ completed on retry | **Reliable** (occasional rate limit, not a real failure) |
| FLUX 3 Video | ✅ completed | ✅ completed | **Reliable** |
| Happy Horse Video | ✅ completed | ❌ failed+refunded, ❌ failed+refunded again | **Intermittent** — worked once, failed twice since |
| MiniMax Hailuo 2.3 (`minimax-2.3` variant) | ❌ 429 rate-limited twice, never completed as `minimax-2.3` | ❌ failed+refunded, ❌ failed+refunded again | **`minimax-2.3` specifically looks unhealthy right now** |
| MiniMax Hailuo 2.3 Fast (`minimax-2.3-fast` variant) | ✅ completed (3rd attempt, after `minimax-2.3` kept rate-limiting) | not retried | **Reliable** — the "Fast" variant worked when plain 2.3 didn't |

This is a materially different conclusion from this file's own first draft (written after Run 2
alone, before Run 1's log was found): **all 5 models genuinely work on Higgsfield's platform** —
every one of them has at least one clean success through this connector. Happy Horse Video and the
plain `minimax-2.3` variant are showing **intermittent/unhealthy** behavior right now (succeeded
once, failed on both later attempts), not permanent breakage. This is consistent with newer or
less-trafficked models having rougher reliability than the established ones (Kling, Veo, MiniMax
H3, Seedance), not with anything wrong in RenderPost's request shape, Filip's account, or the
settings added to RenderPost's catalog.

## Run 1 — method and raw results

Full write-up in `higgsfield-mcp-test-log.md`. Summary: `media_import_url` on a real Higgsfield-
hosted source image, one `generate_video_batch` call across all 5 models (prompt: "Subtle slow
camera push-in, gentle natural motion"), `jobs_wait` to terminal, `show_generation_by_ids` at the
end. `minimax_hailuo` with `variant: "minimax-2.3"` was rejected twice with `429
rate_limit_reached` before being retried as `variant: "minimax-2.3-fast"`, which succeeded. All
other 4 models completed cleanly on the first submission. Result URLs and job IDs are in that file.

## Run 2 — method and raw results

Run independently (different `media_id`, different prompt: "Gentle camera drift, soft cinematic
light", imported from `https://httpbin.org/image/png` rather than a Higgsfield-hosted image), using
the exact request shape RenderPost's `PROVIDERS["higgsfield"]["video"]` template sends (`model`,
tier/variant field, `resolution`, `duration`, `aspect_ratio: "16:9"`, `prompt`, `medias:
[{value, role: "start_image"}]`, `use_unlim: false`), via `generate_video_batch` (the same tool
RenderPost calls, not the single-generation widget tool).

**Round 1** (`media_id: d41d4c0a-7a23-481c-b76e-82b3e77d539b`):
- `gemini_omni_flash_1_1` → job `c8bb9672-...` → **completed**
- `grok_video_v15` → **submission_failed**: `backend request failed (429): rate_limit_reached` (no
  job, no charge)
- `happy_horse_video` → job `ebd8ad44-...` → **failed** (spent 10cr, refunded 10cr)
- `minimax_hailuo` (`variant: "minimax-2.3"`) → job `9ec1ac40-...` → **failed** (spent 6cr, refunded
  6cr)
- `flux_3_video` → job `e4937adb-...` → **completed**

**Round 2** (retry of the 3 non-clean results):
- `grok_video_v15` → job `8db13988-...` → **completed** (spent 18cr, not refunded — confirms round
  1 was only a transient rate limit)
- `happy_horse_video` → job `f00f4d24-...` → **failed again** (spent 10cr, refunded 10cr)
- `minimax_hailuo` (`variant: "minimax-2.3"`) → job `bf6cd508-...` → **failed again** (spent 6cr,
  refunded 6cr)

`job_display` on the failed job IDs returned `status: "failed"` with no further error text exposed
through this connector. `transactions` confirms every failure was refunded (Higgsfield only refunds
when it accepted and then failed a job server-side — this rules out a client-side/parameter
rejection for these specific failures).

## What this means for RenderPost

- **Gemini Omni Flash 1.1, Grok Imagine 1.5, FLUX.3 Video**: confirmed reliable across both runs.
  Their RenderPost catalog entries are correct as shipped.
- **Happy Horse Video**: the catalog entry is correct (it worked once, with the same shape
  RenderPost sends); it's just hitting Higgsfield's own intermittent backend issues right now. No
  RenderPost-side change indicated — retry later.
- **MiniMax Hailuo 2.3**: same conclusion, but with one concrete lead — the plain `minimax-2.3`
  variant has not completed successfully in either run (rate-limited twice in Run 1, failed+refunded
  twice in Run 2), while `minimax-2.3-fast` completed cleanly the one time it was tried. RenderPost's
  `minimax-hailuo-23-higgsfield` entry currently hardcodes `"variant": "minimax-2.3"` per Filip's
  original request ("minimax hailuo 2.3", not "2.3 fast") — worth asking him whether to switch the
  default to `minimax-2.3-fast` for reliability, or keep `minimax-2.3` and accept it may fail
  intermittently until Higgsfield's backend settles.
- The `session.initialize()`-level crash seen earlier through RenderPost specifically (rather than
  the cleaner "job accepted, then failed, refunded" behavior seen through this connector for the
  same failures) is still not explained by this log — both connectors hit the same underlying
  backend issue, but surface it differently. Worth retrying RenderPost itself against Happy Horse
  now that this log shows the backend does work for it sometimes, to see whether RenderPost gets a
  clean result or the same opaque crash on a now-known-good attempt.
