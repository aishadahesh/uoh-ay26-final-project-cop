# Opponent Integration Guide for uoh-ay26

Send this document to an opposing team before a friendly or counted series. It records public identity, endpoints, and interoperability conventions. It does not expose strategy, hidden state, prompts, keys, tokens, or private configuration.

## Public team details

| Item | Value |
|---|---|
| Group ID/name | `uoh-ay26` |
| Members | Aisha Abu Dahesh; Yousef Asadi |
| Cop repository | <https://github.com/aishadahesh/uoh-ay26-final-project-cop> |
| Thief repository | <https://github.com/aishadahesh/uoh-ay26-final-project-thief> |
| Cop endpoint | `https://cop.uohay26game.com/mcp` |
| Thief endpoint | `https://theif.uohay26game.com/mcp` |
| Automatic-report sender | `aishadahesh11@gmail.com` |

The spelling `theif.uohay26game.com` is deliberate and matches the deployed hostname.

## Information required from the opponent

Before play, send us:

1. Exact group ID and group name.
2. Member names.
3. Public Cop and Thief repository URLs.
4. Full 40-character playing commit SHA for each role.
5. Public Cop and Thief MCP URLs, each ending in `/mcp`.
6. Automatic-report sender address.
7. Counted-game history including the proposed series, when applicable.
8. Proposed unique series label such as `G010`.
9. Explicit role schedule for sub-games 1/3/5 and 2/4/6.
10. The exact shared `game.json`, its file SHA-256, canonical terms SHA-256, and derived `game_uid`.

Do not start until the group order, series label, role schedule, configuration hashes, and `game_uid` match on both sides.

## MCP wire contract

Our server exposes exactly these tools and argument names:

```text
negotiate(message: dict)
receive_turn(message: dict)
submit_audit(payload: dict)
receive_control(message: dict)
```

`submit_audit` uses `payload`; the other three use `message`. An HTTP 200 containing a tool-level error is not a successful protocol exchange and must not be treated as an accepted offer.

Wire roles are `police` and `thief`. Final game results are `capture`, `survival`, or `technical_loss`; `timeout` describes a transport condition, not our canonical result vocabulary.

## Step-0 compatibility convention

The PDF requires a pre-game fairness declaration but leaves some record-envelope details implementation-specific. For interoperability, uoh-ay26 requires both representations below:

1. Negotiation identity contains a top-level `git_commit_hash` with exactly 40 lowercase hexadecimal characters.
2. The final revealed audit begins with a sealed Step-0 record whose payload contains at least:

```json
{
  "step": 0,
  "type": "system_spec"
}
```

The complete payload also carries the signed identity/system evidence used during negotiation. Step 0 is part of the audit record set; building it without attaching it to `AuditPayload.records` causes verification failure at step `0`.

## Capture and boxed-in conventions

- After every Police action, including `STAY` and barrier placement, Police sends `capture_claim` for its post-action Police cell.
- A barrier is independently published as `barrier_placed`. The Thief truthfully checks every public claim cell and returns the matching cell (or the first checked cell when none match) with Boolean `caught` in `claim_response`.
- `caught=true` is terminal and the Thief sends the signed acknowledgement without executing an escape move.
- Coordinate equality alone is never retroactively converted into capture during final audit.
- A fully enclosed Thief may send signed `win_claim: {"type":"boxed_in"}`; a 35-step survival uses `win_claim: {"type":"survival"}`.
- Completed gameplay outcomes are preserved if a later envelope cannot be parsed; verification/sign-off becomes false rather than silently inventing a different outcome.

## Final series consensus extension

`AuditPayload` supports:

```text
consensus_sha: str | None = None
```

- Omit the field from serialized payloads when it is `None`.
- When present, require exactly 64 lowercase hexadecimal characters.
- After all six sub-games, both sides must send a reciprocal `series_consensus` audit envelope with `records: []`.
- A consensus envelope containing game records is malformed.
- Consensus never changes an already completed sub-game result.

The shared digest preimage is exactly:

```json
{
  "game_id": "G010",
  "game_uid": "<shared UUID>",
  "sub_games": [
    {
      "sub_game_number": 1,
      "result": "survival",
      "roles": {
        "opponent": "thief",
        "uoh-ay26": "police"
      },
      "score": {
        "opponent": 10,
        "uoh-ay26": 5
      },
      "winner_group": "opponent"
    }
  ]
}
```

The six rows are ordered g01 through g06 and contain exactly `sub_game_number`, `result`, `roles`, `score`, and `winner_group`. Use:

```python
json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
```

Then compute SHA-256 over those bytes. Exclude timestamps, steps, filenames, tokens, commits, audit metadata, log wrappers/hashes, final totals, and final winner.

Mutual agreement is confirmed only when every log verifies, no tampering is reported, all six result claims agree, and the peer explicitly sends the same consensus SHA.

## Endpoint readiness

- HTTP `502` while an agent is stopped: tunnel route is connected; local origin is idle.
- HTTP `530`/Cloudflare `1033`: no connected tunnel serves the hostname.
- A successful MCP session requires the real match process, not a placeholder health server. Never replace the process after accepting a signed offer; an acknowledged offer held only in memory would be lost.

## Shared failure policy

- If either public endpoint is unavailable before play, delay or reschedule; do
  not manufacture a technical result for a game that never negotiated.
- If a tunnel drops mid-game, preserve both signed journals, identify whether
  the failure is transport, origin, or gameplay, and agree in writing whether
  the specification requires a technical loss or a fresh non-counted replay.
- If our own code causes a technical failure, fix and regression-test it before
  arranging another series. Never edit an already signed log to improve the
  result.
- If a counted-game-history declaration appears false, preserve the declaration
  and supporting evidence, ask the opponent to reconcile it, and escalate under
  course policy when unresolved. Do not retaliate or silently change scoring.

## Pre-start checklist

- [ ] Both repositories/commits are public or shared and resolve.
- [ ] Both role endpoints and both local origins are ready.
- [ ] Shared configuration bytes/hash and `game_uid` match.
- [ ] Unique series label and role schedule match.
- [ ] Both teams declare counted history and reporting mode.
- [ ] Step-0 shape, tool arguments, capture fields, and consensus extension are accepted.
- [ ] Both teams agree whether the run is friendly or counted before sub-game 1.
