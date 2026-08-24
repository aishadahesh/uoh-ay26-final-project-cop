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
import tkinter as tk

from police_thief.cli.args import (
    parse_args,
)
from police_thief.cli.demo import _demo
from police_thief.cli.peer import _peer
from police_thief.cli.play import _play
from police_thief.domain.replay import ReplaySession, load_log
from police_thief.domain.simulation import run_local_match
from police_thief.gui.replay_gui import ReplayGUI
from police_thief.shared.game_config import load_match_parameters

__all__ = ["main", "parse_args"]




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
