# Higgsfield MCP: Connection Check and Video Generation Test Log

- **Date:** Thu 2026-10-01 (Europe/Sofia, UTC+03:00)
- **Run from:** Claude chat session using the Higgsfield MCP connector (`mcp__Higgsfield__*`)
- **Purpose:** Prove MCP connection and functionality for an ongoing Claude Code project

---

## 1. Account and connection state

| Item | Result |
|---|---|
| Connection | OK, all read-only tools responded |
| Plan | ultimate |
| Credits at check time | 706.71 |
| Workspaces | 1 (private, role: owner) |
| Workspace ID | `0be0b6a8-4fb2-4b26-9c66-87e0d914549a` |
| `is_selected` | `false`, and the workspace name is `null`. Calls still work when `workspace_id` is passed explicitly. Likely cosmetic; `select_workspace` would set it. |
| TikTok | No account connected |

## 2. Read-only tool check

| Tool | Result |
|---|---|
| `balance` | OK, 706.71 credits |
| `list_workspaces` | OK, 1 workspace |
| `transactions` | OK (recent entries: Happy Horse Video spend and refund) |
| `list_projects` (needs `workspace_id`) | OK, 5 projects (incl. "Catherina-Logan-UGC", "Nine Angle Scene") |
| `list_folders` | OK (empty for the project tested) |
| `list_project_assets` | OK (3 Marketing Studio videos in the project tested) |
| `models_explore` (list) | OK, but the output was truncated at 25k tokens, so the tail of the catalog was not seen. Use `limit`/`after` pagination or `type` filter next time. |
| `show_medias` | OK |
| `show_generations` | OK |
| `show_marketing_studio_generations` | OK |
| `show_characters` | OK, 1 trained character ("Logan", soul_cinematic) |
| `show_reference_elements` | OK, 5 elements |
| `get_presets` | OK, 736 presets (87 viral, 649 marketing studio) |
| `get_explainer_presets` | OK, 22 styles |
| `shorts_studio_list_presets` | OK, 8 returned, more available |
| `shorts_studio_list_sessions` | OK, none |
| `video_analysis_jobs` | OK, none |
| `list_voices` | OK |
| `list_websites` / `list_website_categories` | OK, no websites; 8 categories |
| `scene_builder_3d_list_projects` | OK, none |
| `animation_actions` | OK, 678 rig animations |
| `apps_search` / `apps_describe` | OK, 1 app: Match Cut + Tracelab (28 actions, manifest v3) |
| `get_workflow_instructions` | OK, 16 workflows |
| `tiktok_accounts` | OK, none connected |

Not called (spend credits or change state): all `generate_*`, `execute_preset`, upscale, background removal, outpaint, reframe, motion control, dubbing, voice change, `apps_invoke`, uploads, project/folder/voice creation, website create/deploy/publish, TikTok connect/publish, `sandbox_exec`, 3D scene edit tools.

## 3. Video generation test

### 3.1 Input

- **Source URL:** `https://d8j0ntlcm91z4.cloudfront.net/user_33FuofGQTA9bj60MG0zeB6Tn79G/hf_20261001_100408_db0d89ac-81b6-49f9-96d1-3fcffef40d98.png`
- **Import:** `media_import_url` (type `image`) returned media_id `f46f56b8-35af-4d04-82f2-ecb3ae3ef879`
- **Prompt (identical for all):** `Subtle slow camera push-in, gentle natural motion`
- **Media role:** `start_image`
- **Submission:** one `generate_video_batch` call (indices 0-4), then `jobs_wait` polling (15 s long-poll) until terminal, then `show_generation_by_ids`

### 3.2 Results

| # | Model ID | Model | Settings (lowest available) | Job ID | Status |
|---|---|---|---|---|---|
| 0 | `gemini_omni_flash_1_1` | Gemini Omni Flash 1.1 | `mode: image-to-video`, `duration: 3`, `resolution: 360p` | `edb8288a-f6ba-4276-a578-e68785ed82ff` | completed |
| 1 | `flux_3_video` | FLUX 3 Video | `duration: 5` (min), `resolution: 720p` (min), `generate_audio: false` | `2d8b5550-2f76-4d61-a9ca-079915d122b4` | completed |
| 2 | `grok_video_v15` | Grok Video 1.5 | `duration: 2` (min), `resolution: 480p` | `0e60b07e-7a7c-4ecb-83a3-f53dfff1e2da` | completed |
| 3 | `happy_horse_video` | Happy Horse | `duration: 3` (min), `resolution: 720p` (min) | `3486a102-3445-490e-b606-319262a7fcdd` | completed |
| 4 | `minimax_hailuo` | Minimax Hailuo 2.3 **Fast** | `variant: minimax-2.3-fast`, `duration: 6` (min), `resolution: 768` (min for 2.3 variants) | `12d1baad-1f2c-4f08-bc1e-d1ca67a61448` | completed |

### 3.3 Result URLs

- Gemini Omni 1.1: https://d8j0ntlcm91z4.cloudfront.net/user_33FuofGQTA9bj60MG0zeB6Tn79G/hf_20261001_122701_edb8288a-f6ba-4276-a578-e68785ed82ff.mp4
- FLUX 3 Video: https://d8j0ntlcm91z4.cloudfront.net/user_33FuofGQTA9bj60MG0zeB6Tn79G/hf_20261001_122701_2d8b5550-2f76-4d61-a9ca-079915d122b4.mp4
- Grok Video 1.5: https://d8j0ntlcm91z4.cloudfront.net/user_33FuofGQTA9bj60MG0zeB6Tn79G/hf_20261001_122701_0e60b07e-7a7c-4ecb-83a3-f53dfff1e2da.mp4
- Happy Horse: https://d8j0ntlcm91z4.cloudfront.net/user_33FuofGQTA9bj60MG0zeB6Tn79G/hf_20261001_122701_3486a102-3445-490e-b606-319262a7fcdd.mp4
- Minimax Hailuo 2.3 Fast: https://d8j0ntlcm91z4.cloudfront.net/user_33FuofGQTA9bj60MG0zeB6Tn79G/hf_20261001_122826_12d1baad-1f2c-4f08-bc1e-d1ca67a61448.mp4

### 3.4 Event timeline (UTC)

1. ~12:27: batch submitted. Indices 0-3 accepted and pending; index 4 (`minimax_hailuo`, `variant: minimax-2.3`) rejected with `429 rate_limit_reached` (no job created).
2. Retry of index 4 with `variant: minimax-2.3`: rejected again with the same 429.
3. Indices 0-3 polled with `jobs_wait` until completed; Gemini Omni and Grok first, then FLUX 3, then Happy Horse.
4. Third attempt at index 4 with `variant: minimax-2.3-fast`: accepted (`12d1baad-...`), completed ~12:28 after several polls.
5. `show_generation_by_ids` rendered all 5 jobs (`all_found: true`).

## 4. Notes and caveats

- **Variant substitution:** Minimax ran as `minimax-2.3-fast`, not `minimax-2.3`. The `minimax-2.3` variant was rate-limited twice. Re-run with `minimax-2.3` if the exact variant matters.
- **Rate limits:** a 429 on submission means no job and no charge was created. Retry later rather than immediately.
- **Aspect ratio:** not passed; models used their default or `auto`, so output framing follows each model's default.
- **Cost:** no `get_cost` preflight was run and the balance was not re-read after generation. Check `balance` and `transactions` to confirm the spend.
- **Media references:** pass `media_id` or job ID in `medias[].value`, never raw URLs. Import web images first with `media_import_url`.
- **Large catalog output:** `models_explore` with `action: list` and `limit: 100` exceeds the output limit. Filter by `type` or paginate.
- **Result URLs:** hosted on CloudFront; they may not be permanent. Download anything you need to keep.

## 5. Reproduce in Claude Code

Once the Higgsfield MCP server is connected in Claude Code, the sequence is:

1. `media_import_url` with `type: image` and the source URL, to get a `media_id`.
2. `generate_video_batch` with one request per model (`medias: [{role: "start_image", value: <media_id>}]` plus the per-model settings from section 3.2).
3. `jobs_wait` on the returned job IDs until `all_terminal: true`.
4. Optionally `show_generation_by_ids` for the gallery view (a UI widget; in Claude Code the `result_url` values from `jobs_wait` are enough).
