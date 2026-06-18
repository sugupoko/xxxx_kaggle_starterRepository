"""Depth-limited alpha-beta negamax agent for ConnectX.

The search is deterministic: the same board always produces the same move.
Determinism comes from (a) a fixed move ordering (centre-first) and (b) strict
``>`` comparisons when updating the best move, so ties resolve to the
earlier-explored (more central) column.

Evaluation function: weighted count of "windows" of length ``inarow``. For each
such window we add a positive score for our pieces and a negative score for the
opponent's, weighted super-linearly so that "3 in a window with an empty 4th"
dominates "2 in a window". A window containing both colours is dead (0).

Terminal scores: win = +LARGE, loss = -LARGE, draw = 0. Wins/losses found
shallower in the tree are preferred over the same outcome found deeper (we
fold the remaining depth into the magnitude) so the agent finishes games.

IMPORTANT: never print/log inside the agent — see package docstring.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from .heuristic import drop, is_win, legal_moves

# --- Hyperparameters (edit here, not scattered through the code) -----------
DEFAULT_DEPTH = 4          # plies of look-ahead
LARGE = 1_000_000          # magnitude for a terminal win/loss
# Window weights by number of own pieces (index = count, rest empty).
WINDOW_WEIGHTS = {2: 10, 3: 50}
# Penalty applied to an opponent "3 with empty 4th" window (defensive bias).
OPP_THREE_PENALTY = 80


def _windows(rows: int, columns: int, inarow: int) -> List[List[int]]:
    """Pre-compute all index-windows of length ``inarow`` (cached per board geom)."""
    key = (rows, columns, inarow)
    cached = _windows_cache.get(key)
    if cached is not None:
        return cached

    def idx(r: int, c: int) -> int:
        return r * columns + c

    wins: List[List[int]] = []
    # Horizontal
    for r in range(rows):
        for c in range(columns - inarow + 1):
            wins.append([idx(r, c + i) for i in range(inarow)])
    # Vertical
    for r in range(rows - inarow + 1):
        for c in range(columns):
            wins.append([idx(r + i, c) for i in range(inarow)])
    # Diagonal "/"
    for r in range(inarow - 1, rows):
        for c in range(columns - inarow + 1):
            wins.append([idx(r - i, c + i) for i in range(inarow)])
    # Diagonal "\"
    for r in range(rows - inarow + 1):
        for c in range(columns - inarow + 1):
            wins.append([idx(r + i, c + i) for i in range(inarow)])
    _windows_cache[key] = wins
    return wins


_windows_cache: dict = {}


def evaluate_board(
    board: Sequence[int], me: int, opp: int, rows: int, columns: int, inarow: int
) -> int:
    """Heuristic score of a non-terminal board from ``me``'s perspective."""
    score = 0
    for win in _windows(rows, columns, inarow):
        mine = 0
        theirs = 0
        for i in win:
            v = board[i]
            if v == me:
                mine += 1
            elif v == opp:
                theirs += 1
        if mine and theirs:
            continue  # mixed window: cannot be completed by either side
        if mine:
            score += WINDOW_WEIGHTS.get(mine, 0)
        elif theirs:
            score -= WINDOW_WEIGHTS.get(theirs, 0)
            if theirs == inarow - 1:
                score -= OPP_THREE_PENALTY
    return score


def _negamax(
    board: List[int],
    piece: int,
    me: int,
    opp: int,
    depth: int,
    alpha: int,
    beta: int,
    rows: int,
    columns: int,
    inarow: int,
) -> int:
    """Return the negamax value of ``board`` with ``piece`` to move.

    Value is from the perspective of the side to move (``piece``).
    """
    prev = opp if piece == me else me  # the side that just moved
    if is_win(board, prev, rows, columns, inarow):
        # The mover-to-act has already lost. Prefer losing later (small depth
        # bonus) so the agent does not give up early.
        return -(LARGE + depth)

    legal = _ordered_moves(board, columns)
    if not legal:
        return 0  # draw (board full, no winner)

    if depth == 0:
        # Static eval is always from ``me``'s view; flip if it's opp's turn.
        ev = evaluate_board(board, me, opp, rows, columns, inarow)
        return ev if piece == me else -ev

    next_piece = opp if piece == me else me
    value = -(LARGE * 2)
    for col in legal:
        child = drop(board, col, piece, rows, columns)
        score = -_negamax(
            child, next_piece, me, opp, depth - 1, -beta, -alpha,
            rows, columns, inarow,
        )
        if score > value:
            value = score
        if value > alpha:
            alpha = value
        if alpha >= beta:
            break  # alpha-beta cutoff
    return value


def _ordered_moves(board: Sequence[int], columns: int) -> List[int]:
    """Legal moves ordered centre-first (improves pruning, fixes tie-breaks)."""
    centre = (columns - 1) / 2.0
    return sorted(legal_moves(board, columns), key=lambda c: (abs(c - centre), c))


def search_agent(obs, config, depth: int = DEFAULT_DEPTH) -> int:
    """Return the best column via depth-limited alpha-beta negamax."""
    rows = config.rows
    columns = config.columns
    inarow = config.inarow
    me = obs.mark
    opp = 2 if me == 1 else 1
    board = list(obs.board)

    legal = _ordered_moves(board, columns)
    if not legal:
        return 0

    best_col = legal[0]
    best_val = -(LARGE * 2)
    alpha, beta = -(LARGE * 2), LARGE * 2

    for col in legal:
        child = drop(board, col, me, rows, columns)
        # After our move it is the opponent's turn; negate their value.
        val = -_negamax(
            child, opp, me, opp, depth - 1, -beta, -alpha,
            rows, columns, inarow,
        )
        if val > best_val:  # strict > keeps the more central / earlier column
            best_val = val
            best_col = col
        if best_val > alpha:
            alpha = best_val
    return best_col
