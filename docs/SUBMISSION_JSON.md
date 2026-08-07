# Email submission JSON contract

This contract is derived from project PDF section 9.3.3 (physical pages 94-95) and Appendix table 20. The final report is machine-readable JSON, not free text. Both teams independently email their agreed report.

## Required attachments

For a six-sub-game series, attach 14 JSON files:

1. `declaration_<game_id>.json`
2. `config_<game_id>_g01.json` through `config_<game_id>_g06.json`
3. `log_<game_id>_g01.json` through `log_<game_id>_g06.json`
4. `result_<game_id>.json`

`result_<game_id>_gNN.json`, validation reports, GIFs, quota files, credentials, OAuth tokens, and private configuration are not submission attachments.

All mandatory files share one `game_id` and one UUID `game_uid`. Per-sub-game filenames use a two-digit number matching `sub_game_number`.

## Declaration schema

Mandatory top-level fields:

| Field | Type / allowed value |
|---|---|
| `schema_version` | string, `"1.1"` |
| `report_type` | string, `"declaration"` |
| `declaration_type` | string, `"pre_game_declaration"` |
| `game_id` | non-empty string |
| `game_uid` | UUID string |
| `links` | object containing declaration/config/log/result names and both teams' GitHub links |
| `timezone` | string, `"Asia/Jerusalem"` |
| `game_started_at` | timezone-aware ISO-8601 string |
| `num_sub_games` | positive integer; official series value is `6` |
| `max_tokens_per_game` | non-negative integer |
| `groups` | object containing exactly `group_1` and `group_2` |

Each group object requires `group_id` and `group_name` strings; a non-empty string array `members`; `repos` with `cop` and `thief` GitHub URLs; public `mcp_servers`; `llm_model`; public `hardware_spec`; 40-character `github_commit`; `code_version`; and `signature` in `sha256:<digest>` form.

Optional: `_schema` explanatory text and `league` classification metadata. Private prompts, credentials, tokens, email/OAuth data, API keys, private strategy settings, and reasoning are forbidden.

## Config schema

Mandatory: `schema_version`, `game_id`, `game_uid`, `links`, integer `sub_game_number`, 14-key `terms`, and `config_sha256`. The checksum is lowercase SHA-256 over canonical UTF-8 JSON for `terms`.

The 14 signed terms are: `board_size`, `smell_grid_size`, `decay_per_step`, `emit_intensity`, `min_center_intensity`, `max_steps`, `barriers_max`, `setting`, `hint_max_words`, `axis_origin_corner`, `axis_start_index`, `thief_start`, `cop_start`, and `num_games`.

Optional: `_schema` and `league`.

## Log schema

Mandatory: `schema_version`, `game_id`, `game_uid`, `links`, integer `sub_game_number`, `summary`, and `records`.

`summary` contains the sub-game number, both role assignments, result, winner or `null`, ISO start/end timestamps, step count, and audit result. Every record contains exactly `payload`, `nonce`, and `commit`. `commit` must equal SHA-256 of `canonical_json(payload) + "|" + nonce`. Moves are limited to `N`, `S`, `E`, `W`, and `STAY`; roles are `police` or `thief`.

Optional: `_schema`, `league`, and additional public audit details. Private Gemini rationale or prompts are forbidden.

## Final result schema

Mandatory: `schema_version`, `report_type = "final_game_result"`, `game_id`, `game_uid`, `links`, `timezone`, the two group IDs, `num_sub_games`, one row per sub-game, `final_result`, and `mutual_agreement`.

Every sub-game row requires: number, roles, ISO start/end timestamps, result (`capture`, `survival`, or `technical_loss`), winner or `null`, tie boolean, steps, both commit hashes, per-group token counts, per-group score, log filenames, and audit status.

`final_result` contains derived total scores, games won, tie count, winner or `null`, series-tie boolean, and total tokens per group. `mutual_agreement` requires `confirmed = true` and a lowercase SHA-256 digest.

Optional: `_schema`, `league`, and league-standing fields when they are known and legitimately claimed.

## Validation

```powershell
uv run python scripts/validate_submission_json.py `
  --directory "results/network" `
  --game-id "<game_id>"
```

Exit code `0` means the complete attachment set passed. Exit code `1` prints the affected filename, field, expected format/value, received value, and error code.
