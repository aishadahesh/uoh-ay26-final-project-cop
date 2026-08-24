"""Argument parsing for the CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_CONFIG_ROOT = Path(__file__).resolve().parents[3] / "config"
DEFAULT_GAME_CONFIG = DEFAULT_CONFIG_ROOT / "game.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the `peer`/`simulate`/`replay` subcommands and their options."""
    parser = argparse.ArgumentParser(prog="police_thief")
    subparsers = parser.add_subparsers(dest="command", required=True)

    peer = subparsers.add_parser(
        "peer", help="Start this peer's FastMCP server, as the cop (wire role \"police\")",
    )
    peer.add_argument(
        "--role", required=True, choices=["police"],
        help="Only 'police' is supported -- this repo has no thief config to run as 'thief' with",
    )
    peer.add_argument("--config-root", type=Path, default=DEFAULT_CONFIG_ROOT)
    peer.add_argument("--single-subgame", action="store_true", help=argparse.SUPPRESS)
    peer.add_argument("--sub-game-number", type=int, help=argparse.SUPPRESS)
    peer.add_argument("--output-directory", type=Path, help=argparse.SUPPRESS)
    peer.add_argument("--series-state", type=Path, help=argparse.SUPPRESS)
    peer.add_argument("--finalize-series", action="store_true", help=argparse.SUPPRESS)
    peer.add_argument(
        "--series-first-role", choices=["police", "thief"], default="police",
        help=argparse.SUPPRESS,
    )
    peer.add_argument(
        "--sibling-repo", type=Path,
        default=DEFAULT_CONFIG_ROOT.parent.parent / "uoh-ay26-final-project-thief",
        help="Path to this team's independent Thief repository.",
    )

    simulate = subparsers.add_parser("simulate", help="Run a local placeholder-policy match")
    simulate.add_argument("--game-config", type=Path, default=DEFAULT_GAME_CONFIG)

    replay = subparsers.add_parser("replay", help="Launch the Replay Viewer on a saved match log")
    replay.add_argument("--log", required=True, type=Path, dest="log_file")

    demo = subparsers.add_parser("demo", help="Open a standalone Live GUI demo (no networking)")
    demo.add_argument("--turns", type=int, default=25)
    demo.add_argument("--delay-ms", type=int, default=500)

    subparsers.add_parser("play", help="Open the interactive, mode-selectable play window")

    return parser.parse_args(argv)
