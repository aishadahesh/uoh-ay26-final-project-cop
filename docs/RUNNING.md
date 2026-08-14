# Running the uoh-ay26 Cop Agent

This tutorial covers installation, local checks, replay, and a real six-sub-game peer series. The Cop and Thief remain independent repositories and processes; neither repository reads the other role's private configuration.

## 1. Prerequisites

- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/)
- Git
- Tcl/Tk only for GUI modes
- A Gemini API key for model-assisted play
- `cloudflared` for public peer matches
- Google OAuth files only when automatic Gmail reporting is enabled

## 2. Install both role repositories

Keep the repositories as sibling directories so the six-game coordinator can alternate roles:

```powershell
git clone https://github.com/aishadahesh/uoh-ay26-final-project-cop.git
git clone https://github.com/aishadahesh/uoh-ay26-final-project-thief.git
cd uoh-ay26-final-project-cop
uv sync
cd ..\uoh-ay26-final-project-thief
uv sync
```

Create a local environment file in each repository:

```powershell
Copy-Item .env-example .env
```

Set `GEMINI_API_KEY` in `.env`. Never commit `.env`, `credentials.json`, or `token.json`.

## 3. Try safe local modes

From the Cop repository:

```powershell
uv run python -m police_thief simulate
uv run python -m police_thief demo
uv run python -m police_thief play
```

Run tests and static checks:

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## 4. Configure a peer series

Edit these local files:

- `config/game.json`: shared rules; both teams must use the agreed canonical content.
- `config/network_match.json`: series label, teams, repositories, output directory, and email switch.
- `config/cop/game.toml`: Cop port and the opponent Thief URL.
- The sibling Thief repository's `config/network_match.json` and `config/thief/game.toml` for its role.

The Cop listens on local port `8801`. Our stable public endpoint is:

```text
https://cop.uohay26game.com/mcp
```

The sibling Thief listens on local port `8802` at:

```text
https://theif.uohay26game.com/mcp
```

`theif` is the deployed hostname spelling. Do not silently change it to `thief`.

Before a counted series, exchange the information in [`OPPONENT_MATCH_GUIDE.md`](OPPONENT_MATCH_GUIDE.md). Do not reuse a previous series label or `game_uid` for a new opponent.

## 5. Run the Cloudflare routes

For quick tunnels, explicitly target IPv4 loopback:

```powershell
cloudflared tunnel --url http://127.0.0.1:8801
cloudflared tunnel --url http://127.0.0.1:8802
```

A named tunnel may route both stable hostnames through one connector:

```yaml
ingress:
  - hostname: cop.uohay26game.com
    service: http://127.0.0.1:8801
  - hostname: theif.uohay26game.com
    service: http://127.0.0.1:8802
  - service: http_status:404
```

Keep the connector running for the entire series. HTTP `502` while an agent process is stopped means the route exists but the local origin is idle. HTTP `530`/Cloudflare `1033` means no connected tunnel currently serves that hostname.

## 6. Start a full six-game series

If this team is Cop in sub-games 1, 3, and 5, launch from this repository:

```powershell
cd C:\path\to\uoh-ay26-final-project-cop
uv run python -m police_thief peer --role police
```

The coordinator launches a fresh fixed-role child for every sub-game:

| Sub-games | Local role | Opponent URL used |
|---|---|---|
| 1, 3, 5 | Cop | Opponent Thief endpoint |
| 2, 4, 6 | Thief, from the sibling repository | Opponent Cop endpoint |

Use `--sibling-repo` if the repositories are not siblings:

```powershell
uv run python -m police_thief peer --role police `
  --sibling-repo "C:\path\to\uoh-ay26-final-project-thief"
```

Leave the parent terminal running until final consensus completes. The coordinator preserves verified completed sub-games and refuses to fabricate later results after a failed child process.

## 7. Expected artifacts

A completed series named `G009` illustrates the naming pattern:

```text
results/network/
├── declaration_G009.json
├── config_G009_g01.json ... config_G009_g06.json
├── log_G009_g01.json ... log_G009_g06.json
├── result_G009_g01.json ... result_G009_g06.json
└── result_G009.json
```

Each sub-game must finish with a verified audit for mutual sign-off. The aggregate is confirmed only after both peers explicitly exchange the same canonical series SHA.

## 8. Replay and GIF export

Open a signed log in the replay viewer:

```powershell
uv run python -m police_thief replay --log results/network/log_G009_g01.json
```

### Generate a replay GIF

Generate a README-ready animation:

```powershell
uv run python scripts/visualize_game_log.py `
  --input results/network/log_G009_g01.json `
  --output docs/replays/my-replay.gif `
  --format gif --duration 350 --resolution 960x540
```

## 9. Automatic reporting

For live Gmail reporting:

1. Install the configured email dependencies.
2. Place the OAuth client in `credentials.json`.
3. Complete consent once to create `token.json`.
4. Set `email.automatic` and verify the recipient in `config/network_match.json`.
5. Verify the series is counted before launch.

The implementation is fail-closed: an invalid bundle or failed final consensus is saved locally but is not automatically presented as mutually confirmed.

## 10. Troubleshooting

- **Negotiation timeout:** both peers must send a signed offer; confirm both public origins are live simultaneously.
- **HTTP 502:** start the local process behind the already-connected tunnel.
- **HTTP 530/1033:** restore the Cloudflare connector/hostname route.
- **Step 0 rejected:** require a sealed `step: 0`, `type: "system_spec"` audit record and a 40-character `identity.git_commit_hash`.
- **Audit timeout after game 6:** both peers must emit a reciprocal empty-record `series_consensus` envelope.
- **Result exists but email failed:** preserve the signed evidence and repair only the reporting boundary; do not replay merely to resend email.
