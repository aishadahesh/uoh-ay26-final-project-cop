"""CLI entry point: `uv run python -m police_thief <command> ...`.

This repository is the **cop** side only (docs/tasks.md's mandatory
two-separate-repos submission split): it ships and reads only
`config/cop/game.toml`, never a thief config directory, and `peer` below
always runs this process as the cop (wire role "police" -- see
services/network_protocol.py::WIRE_ROLES). The sibling thief repo (see
README.md) mirrors this same package restricted the other way.

`peer --role police` / `replay --log` match the naming used by
docs/tasks.md Appendix D's illustrative (non-mandatory) example runner --
purely a local invocation convenience. It has no effect on cross-team
compatibility: the wire protocol two teams actually speak over the network
(negotiate/receive_turn/submit_audit/receive_control, and the "police"
wire-role string) is unrelated to what you type in your own terminal, and
is unchanged by this naming.

Commands:
  peer --role police       Coordinate the complete real six-game series:
                           launches fresh fixed-role Cop and Thief child
                           processes and drives each negotiate/turn/audit
                           match against whatever
                           opponent config/network_match.json names --
                           e.g. your own group's thief repo, run the same
                           way on its own machine/port. Connection details
                           (port, opponent URL) come from config/cop/
                           game.toml's [network] section (Chapter 2's
                           private per-peer file); team/session details
                           come from config/network_match.json (edit it
                           before running). Only "police" is accepted --
                           this repo has no thief config to run as the
                           thief with. Multi-game series alternate the live
                           role. Run the sibling Thief repository as a
                           separate process for this team's Thief games.
  simulate                 Run a single-process local match with placeholder
                           policies and print the result (Chapter 3). No
                           live opponent config is read -- both sides are
                           simulated in-process from the public heuristic.
  replay --log PATH        Launch the Replay Viewer against a saved match
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
                           scope -- see domain/interactive_match.py. Every
                           mode here is a local, single-process practice
                           sandbox using the same public heuristic for
                           whichever side isn't human-controlled -- it never
                           reads a live opponent's private config and never
                           represents this repo actually playing a real,
                           graded match as the thief.

`peer` is the concrete realization of Chapter 2's "Total Separation of
Working Environments" rule: this process reads only its own (cop) config,
sharing no memory and no config file with the thief's own, separately-run
process. `simulate` has no networking or live-opponent concept at all -- it
exercises board/movement/barrier/capture/scoring end-to-end against the
single shared config/game.json.
"""

from __future__ import annotations

import argparse
import threading
import tkinter as tk
from dataclasses import replace
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
from police_thief.services.mcp_server import PeerInboxes, build_peer_server, run_peer_server
from police_thief.services.network_match import NetworkMatchRunner, NetworkMatchSettings
from police_thief.services.network_match_config import load_network_defaults, validate_peer_defaults
from police_thief.services.series_coordinator import mark_subgame_finished, run_series
from police_thief.shared.config import load_network_config
from police_thief.shared.constants import AgentRole
from police_thief.shared.game_config import load_match_parameters

DEFAULT_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "config"
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


def _peer(args: argparse.Namespace) -> None:
    """Plays a complete, real match as the cop (wire role "police") --
    not just an idle listener; `--role` accepts only "police" since this
    repo has no thief config to run as "thief" with.

    Connection details (port, opponent URL) come from config/cop/
    game.toml's [network] section (Chapter 2's private per-peer file);
    match/team/session details come from config/network_match.json, the
    same file the `play` GUI's two-computer setup screen reads
    (services/network_match_config.py::load_network_defaults) -- edit it
    before running to point at a real opponent, e.g. your own group's
    thief repo run the same way on its own machine/port.
    """
    project_root = args.config_root.parent
    defaults = load_network_defaults(args.config_root / "network_match.json", project_root)
    if not args.single_subgame:
        first_role = (
            AgentRole.COP if args.series_first_role == "police" else AgentRole.THIEF
        )
        try:
            run_series(
                current_role=AgentRole.COP,
                first_role=first_role,
                current_repo=project_root,
                sibling_repo=args.sibling_repo,
                config_root=args.config_root,
                output_dir=Path(defaults["output"]),
                game_id=defaults["game"],
                first_sub_game=int(defaults["subgame"]),
            )
        except RuntimeError as exc:
            raise SystemExit(f"Series stopped: {exc}") from None
        return
    network = load_network_config(AgentRole.COP, args.config_root)
    try:
        validate_peer_defaults(defaults, network.opponent_url)
    except ValueError as exc:
        raise SystemExit(f"Cannot start the network agent: {exc}") from exc
    from dotenv import load_dotenv

    from police_thief.services.gemini_agent import GeminiAgentAdvisor, GeminiConfigurationError

    load_dotenv(project_root / ".env")
    try:
        gemini_advisor = GeminiAgentAdvisor()
    except GeminiConfigurationError as exc:
        raise SystemExit(f"Cannot start the network agent: {exc}") from exc
    settings = NetworkMatchSettings(
        role=AgentRole.COP, local_port=network.my_port, opponent_url=network.opponent_url,
        public_url=defaults["public"], game_id=defaults["game"],
        sub_game_number=args.sub_game_number or int(defaults["subgame"]),
        shared_config=args.config_root / "game.json",
        output_dir=args.output_directory or Path(defaults["output"]),
        team_name=defaults["team1_name"],
        members=(defaults["team1_member1"], defaults["team1_member2"]),
        opponent_team_name=defaults["team2_name"],
        opponent_members=(defaults["team2_member1"], defaults["team2_member2"]),
        own_cop_repo=defaults["own_cop"], own_thief_repo=defaults["own_thief"],
        opponent_cop_repo=defaults["opponent_cop"], opponent_thief_repo=defaults["opponent_thief"],
        shared_key=defaults["secret"].encode(),
        email_mode="real" if defaults["email"] else "dry_run",
        email_recipient=defaults["email_recipient"],
        credentials_path=project_root / "credentials.json",
        token_path=project_root / "token.json",
        llm_model=gemini_advisor.model,
        counted=defaults["counted"],
        counted_games_played=defaults["counted_games_played"],
        prior_counted_opponents=defaults["prior_counted_opponents"],
    )
    inboxes = PeerInboxes()
    server = build_peer_server(AgentRole.COP.value, inboxes)
    server_thread = threading.Thread(
        target=run_peer_server, args=(server, "0.0.0.0", network.my_port),
        daemon=True, name="mcp-peer-server",
    )
    server_thread.start()
    print(f"MCP server listening on 0.0.0.0:{network.my_port}/mcp")
    # Keep the submitted Cop and Thief as independent live processes.  This
    # Cop entry point runs exactly one configured sub-game and never changes
    # its role in-process; the sibling Thief repository owns thief-role games.
    child_settings = replace(settings, email_mode="series_deferred")
    result_path = NetworkMatchRunner(
        child_settings, inboxes, gemini_advisor=gemini_advisor,
    ).run(threading.Event(), emit=print)
    if args.series_state is not None:
        mark_subgame_finished(
            args.series_state, settings.game_id, settings.sub_game_number,
        )
    print(f"Cop sub-game complete -- result saved to {result_path}")
    if args.finalize_series:
        if args.series_state is None:
            raise RuntimeError("--finalize-series requires --series-state")
        from police_thief.services.network_match import finalize_completed_series

        first_role = (
            AgentRole.COP if args.series_first_role == "police" else AgentRole.THIEF
        )
        final_path = finalize_completed_series(
            settings, inboxes, args.series_state, first_role, emit=print,
        )
        print(f"Final series result saved to {final_path}")


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
    """Dispatch to `peer`, `simulate`, `replay`, `demo`, or `play` based on the parsed subcommand."""
    args = parse_args(argv)
    if args.command == "peer":
        _peer(args)
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
