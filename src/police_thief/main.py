"""CLI entry point: `uv run python -m police_thief <command> ...`.

Commands:
  serve --role cop|thief   Start this peer's FastMCP server (Chapter 2).
  simulate                 Run a single-process local match with placeholder
                           policies and print the result (Chapter 3).
  replay --log-file PATH   Launch the Replay Viewer against a saved match
                           log (Chapter 7) -- runs standalone, independent
                           of any live match code (docs/tasks.md T0437).
  demo                     Open a standalone Live GUI window: the cop chases
                           a fleeing thief using scent + belief-map inference
                           (Chapter 4/6/7), rendered live. Single-process, no
                           networking or crypto layer -- just a quick way to
                           see the Live GUI in action.
  play                     Open the interactive, mode-selectable play window:
                           choose Agent vs Agent, Human (either side) vs
                           Agent, or Human vs Human, then play with a move
                           pad / board clicks / barrier placement. A
                           deliberate addition beyond the rulebook's own
                           scope -- see domain/interactive_match.py.

`serve` is the concrete realization of Chapter 2's "Total Separation of
Working Environments" rule: one shared codebase (docs/PLAN.md ADR-011), but
each invocation is its own OS process reading only its own role's config,
sharing no memory with the other role's process. `simulate` has no
networking or role concept at all -- it exercises board/movement/barrier/
capture/scoring end-to-end against the single shared config/game.json.
"""

from __future__ import annotations

import argparse
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board, BoardConfig, Position
from police_thief.domain.heuristics import greedy_manhattan_move
from police_thief.domain.live_view_model import TurnState, build_live_view_model
from police_thief.domain.replay import ReplaySession, load_log
from police_thief.domain.scent import ScentConfig, ScentField
from police_thief.domain.simulation import run_local_match
from police_thief.gui.live_gui import LiveGUI
from police_thief.gui.replay_gui import ReplayGUI
from police_thief.services.mcp_server import build_peer_server, run_peer_server
from police_thief.shared.config import load_network_config
from police_thief.shared.constants import AgentRole
from police_thief.shared.game_config import load_match_parameters

DEFAULT_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "config"
DEFAULT_GAME_CONFIG = DEFAULT_CONFIG_ROOT / "game.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the `serve`/`simulate`/`replay` subcommands and their options."""
    parser = argparse.ArgumentParser(prog="police_thief")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Start this peer's FastMCP server")
    serve.add_argument("--role", required=True, choices=[role.value for role in AgentRole])
    serve.add_argument("--config-root", type=Path, default=DEFAULT_CONFIG_ROOT)

    simulate = subparsers.add_parser("simulate", help="Run a local placeholder-policy match")
    simulate.add_argument("--game-config", type=Path, default=DEFAULT_GAME_CONFIG)

    replay = subparsers.add_parser("replay", help="Launch the Replay Viewer on a saved match log")
    replay.add_argument("--log-file", required=True, type=Path)

    demo = subparsers.add_parser("demo", help="Open a standalone Live GUI demo (no networking)")
    demo.add_argument("--turns", type=int, default=25)
    demo.add_argument("--delay-ms", type=int, default=500)

    subparsers.add_parser("play", help="Open the interactive, mode-selectable play window")

    return parser.parse_args(argv)


def _serve(args: argparse.Namespace) -> None:
    role = AgentRole(args.role)
    network = load_network_config(role, args.config_root)
    mcp = build_peer_server(peer_name=f"{role.value}_peer")
    run_peer_server(mcp, host="0.0.0.0", port=network.my_port)


def _simulate(args: argparse.Namespace) -> None:
    params = load_match_parameters(args.game_config)
    result = run_local_match(params)
    print(
        f"outcome={result.outcome.value} cop_score={result.cop_score} "
        f"thief_score={result.thief_score} turns_played={result.turns_played}"
    )


def _replay(args: argparse.Namespace) -> None:
    session = ReplaySession(load_log(args.log_file))
    root = tk.Tk()
    root.title(f"Replay Viewer - {args.log_file.name}")
    ReplayGUI(root, session)
    root.mainloop()


def _demo(args: argparse.Namespace) -> None:
    """A standalone Live GUI demo: cop vs. fleeing thief, single-process.

    Not a real match -- no networking, no commit-reveal, no strategy module
    (Chapter 6's ManhattanHeuristicBrain isn't even used here). This is just
    the Chapter 4 scent field + Chapter 6 belief map + Chapter 3 greedy
    Manhattan search, wired to the real Chapter 7 LiveGUI so it's runnable
    without first building a full live match loop (Chapter 8's still-open
    gap -- see docs/PRD_reliability_layer.md).
    """
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    cop_pos = Position(0, 0)
    thief_pos = Position(3, 4)  # off-center: avoids the thief camping in a
    # corner for several turns maximizing distance from the cop, which would
    # otherwise build up one dominant scent blob and make the belief's guess
    # look artificially "stuck" instead of visibly tracking the chase
    scent = ScentField(grid_size=board.config.grid_size, config=ScentConfig())
    belief = BeliefMap(board)
    visited: set[Position] = {cop_pos}

    root = tk.Tk()
    root.title("Live GUI Demo - Cop's View")
    gui = LiveGUI(root, grid_size=board.config.grid_size)

    def step(turn: int) -> None:
        nonlocal cop_pos, thief_pos
        if turn >= args.turns or cop_pos == thief_pos:
            return
        thief_pos = board.apply_move(
            thief_pos, greedy_manhattan_move(board, thief_pos, cop_pos, chase=False)
        )
        scent.decay()
        scent.emit(thief_pos)
        belief.update_from_scent(scent)
        guess = belief.arg_max()
        cop_pos = board.apply_move(cop_pos, greedy_manhattan_move(board, cop_pos, guess, chase=True))
        visited.add(cop_pos)

        turn_state = TurnState.YOUR_TURN if turn % 2 == 0 else TurnState.LOCKED
        view_model = build_live_view_model(
            cop_pos, belief, board, turn_state, role_label="C", visited=frozenset(visited)
        )
        gui.render(view_model)
        root.after(args.delay_ms, step, turn + 1)

    step(0)
    root.mainloop()


def _play(args: argparse.Namespace) -> None:
    """The interactive, mode-selectable play window (see main.py's own
    module docstring and domain/interactive_match.py for scope/rationale).

    `args` is unused today (no CLI flags yet) but kept for a consistent
    handler signature alongside `_serve`/`_simulate`/`_replay`/`_demo`.
    """
    from dotenv import load_dotenv

    from police_thief.domain.interactive_match import (
        InteractiveMatch,
        PlayerType,
        controller_for,
    )
    from police_thief.gui.mode_select import ModeSelectDialog
    from police_thief.gui.network_match_app import NetworkMatchApp
    from police_thief.gui.network_setup import NetworkSetupDialog
    from police_thief.gui.play_app import PlayApp
    from police_thief.services.gemini_agent import GeminiAgentAdvisor, GeminiConfigurationError

    root = tk.Tk()
    root.withdraw()
    load_dotenv()
    current_app: PlayApp | NetworkMatchApp | None = None

    def select_and_start() -> bool:
        nonlocal current_app
        mode = ModeSelectDialog(root).show()
        if mode is None:
            return False

        if mode.value == "network_agent_vs_agent":
            try:
                gemini_advisor = GeminiAgentAdvisor()
            except GeminiConfigurationError as exc:
                root.deiconify()
                messagebox.showerror(
                    "Gemini API key required",
                    f"{exc}\n\nCopy .env-example to .env and set GEMINI_API_KEY, then launch again.",
                    parent=root,
                )
                return False
            settings = NetworkSetupDialog(root, DEFAULT_CONFIG_ROOT.parent).show()
            if settings is None:
                return False
            if current_app is not None:
                current_app.close()
            root.deiconify()
            current_app = NetworkMatchApp(
                root, settings, gemini_advisor, on_new_game=select_and_start,
            )
            current_app.start()
            return True

        has_agent = any(
            controller_for(mode, role) is PlayerType.AGENT for role in AgentRole
        )
        gemini_advisor = None
        if has_agent:
            try:
                gemini_advisor = GeminiAgentAdvisor()
            except GeminiConfigurationError as exc:
                root.deiconify()
                messagebox.showerror(
                    "Gemini API key required",
                    f"{exc}\n\nCopy .env-example to .env and set GEMINI_API_KEY, then launch again.",
                    parent=root,
                )
                return False

        if current_app is not None:
            current_app.close()
        board = Board(BoardConfig(grid_size=7, max_barriers=14))
        match = InteractiveMatch(board, Position(0, 0), Position(3, 3), mode, max_moves=35)
        root.deiconify()
        root.title("Police-Thief - Interactive Play")
        current_app = PlayApp(
            root, match, gemini_advisor=gemini_advisor, on_new_game=select_and_start
        )
        current_app.start()
        return True

    if not select_and_start():
        root.destroy()
        return
    root.mainloop()


def main(argv: list[str] | None = None) -> None:
    """Dispatch to `serve`, `simulate`, `replay`, `demo`, or `play` based on the parsed subcommand."""
    args = parse_args(argv)
    if args.command == "serve":
        _serve(args)
    elif args.command == "simulate":
        _simulate(args)
    elif args.command == "replay":
        _replay(args)
    elif args.command == "demo":
        _demo(args)
    elif args.command == "play":
        _play(args)


if __name__ == "__main__":
    main()
