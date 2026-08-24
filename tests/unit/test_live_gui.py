"""The live match GUI: board construction, banner state, belief rendering,
agent markers and trail dots.

Split out of the original `test_gui.py`."""


from police_thief.domain.board import Position
from police_thief.domain.live_view_model import TurnState, build_live_view_model
from police_thief.gui.live_gui import LiveGUI

# tk_root/root fixtures live in tests/unit/conftest.py, shared across every
# GUI test file -- Tkinter does not reliably support creating more than one
# session-scoped Tk() root within a single process.
from tests.unit.gui_helpers import (
    _belief_peaked_at,
)


def test_live_gui_constructs_one_cell_rect_per_board_position(root):
    gui = LiveGUI(root, grid_size=7)
    assert len(gui._rects) == 49


def test_live_gui_render_updates_the_banner_text_and_color(root):
    board, belief = _belief_peaked_at(7, Position(5, 5))
    vm = build_live_view_model(Position(0, 0), belief, board, TurnState.YOUR_TURN)
    gui = LiveGUI(root, grid_size=7)
    gui.render(vm)
    assert gui.banner.cget("text") == "YOUR TURN"
    assert gui.banner.cget("fg") == "#2e7d32"


def test_live_gui_render_colors_the_belief_peak_cell(root):
    board, belief = _belief_peaked_at(7, Position(5, 5))
    vm = build_live_view_model(Position(0, 0), belief, board, TurnState.YOUR_TURN)
    gui = LiveGUI(root, grid_size=7)
    gui.render(vm)
    rect_id = gui._rects[(5, 5)]
    assert gui.canvas.itemcget(rect_id, "fill") == "#c80000"


def test_live_gui_render_outlines_only_the_own_position_cell(root):
    board, belief = _belief_peaked_at(7, Position(5, 5))
    vm = build_live_view_model(Position(2, 2), belief, board, TurnState.YOUR_TURN)
    gui = LiveGUI(root, grid_size=7)
    gui.render(vm)
    own_rect = gui._rects[(2, 2)]
    other_rect = gui._rects[(0, 0)]
    assert gui.canvas.itemcget(own_rect, "outline") == "#000000"
    assert gui.canvas.itemcget(other_rect, "outline") == "#cccccc"


def test_live_gui_locked_banner_renders_gray(root):
    board, belief = _belief_peaked_at(7, Position(5, 5))
    vm = build_live_view_model(Position(0, 0), belief, board, TurnState.LOCKED)
    gui = LiveGUI(root, grid_size=7)
    gui.render(vm)
    assert gui.banner.cget("text") == "LOCKED"
    assert gui.banner.cget("fg") == "#616161"


def test_live_gui_render_shows_a_barrier_cell_in_its_distinct_color(root):
    board, belief = _belief_peaked_at(7, Position(5, 5))
    board.place_barrier(Position(5, 4), Position(5, 5))
    vm = build_live_view_model(Position(0, 0), belief, board, TurnState.YOUR_TURN)
    gui = LiveGUI(root, grid_size=7)
    gui.render(vm)
    rect_id = gui._rects[(5, 5)]
    assert gui.canvas.itemcget(rect_id, "fill") == "#2b2b2b"


def test_live_gui_step_label_increments_on_every_render(root):
    board, belief = _belief_peaked_at(7, Position(5, 5))
    vm = build_live_view_model(Position(0, 0), belief, board, TurnState.YOUR_TURN)
    gui = LiveGUI(root, grid_size=7)
    assert gui.step_label.cget("text") == "Step 0"
    gui.render(vm)
    assert gui.step_label.cget("text") == "Step 1"
    gui.render(vm)
    assert gui.step_label.cget("text") == "Step 2"


def test_live_gui_draws_an_agent_marker_with_the_role_label(root):
    board, belief = _belief_peaked_at(7, Position(5, 5))
    vm = build_live_view_model(Position(2, 2), belief, board, TurnState.YOUR_TURN, role_label="C")
    gui = LiveGUI(root, grid_size=7)
    gui.render(vm)
    texts = [gui.canvas.itemcget(item, "text") for item in gui.canvas.find_all() if gui.canvas.type(item) == "text"]
    assert "C" in texts


def test_live_gui_draws_a_trail_dot_for_each_visited_cell_except_the_current_one(root):
    board, belief = _belief_peaked_at(7, Position(5, 5))
    visited = frozenset({Position(0, 0), Position(1, 1), Position(2, 2)})  # includes own position
    vm = build_live_view_model(Position(2, 2), belief, board, TurnState.YOUR_TURN, visited=visited)
    gui = LiveGUI(root, grid_size=7)
    gui.render(vm)
    # 2 trail dots (own position excluded) + 1 agent marker (oval + text) = 4 marker ids
    assert len(gui.canvas._marker_ids) == 4


def test_live_gui_clears_previous_markers_on_re_render_rather_than_accumulating(root):
    board, belief = _belief_peaked_at(7, Position(5, 5))
    vm = build_live_view_model(Position(2, 2), belief, board, TurnState.YOUR_TURN, visited=frozenset({Position(0, 0)}))
    gui = LiveGUI(root, grid_size=7)
    gui.render(vm)
    first_count = len(gui.canvas._marker_ids)
    gui.render(vm)
    assert len(gui.canvas._marker_ids) == first_count
