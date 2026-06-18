"""Self-contained Kaggle ConnectX submission agent (alpha-beta negamax).

Source: reference_sim/agents/search.py (depth=DEPTH below)
Local win-rate (fill in before submitting, from evaluate.py):
    vs random   : ____ / ____   (____%)
    vs negamax  : ____ / ____   (____%)
    vs frozen_v1: ____ / ____   (____%)

This file inlines EVERYTHING (board helpers + search) so it has no local
imports and can be submitted to Kaggle ConnectX as-is (a single-file agent).
Keep it in sync with agents/search.py + agents/heuristic.py when you change
the search logic.

HARD RULE: never print() or use logging inside agent() — the scoring
environment captures stdout/stderr and any output there can break the episode.
"""

from __future__ import annotations

# --- Hyperparameters --------------------------------------------------------
DEPTH = 4                  # plies of look-ahead
LARGE = 1_000_000          # magnitude for a terminal win/loss
WINDOW_WEIGHTS = {2: 10, 3: 50}
OPP_THREE_PENALTY = 80

# Cache of index-windows keyed by (rows, columns, inarow).
_WINDOWS_CACHE: dict = {}


def _legal_moves(board, columns):
    return [c for c in range(columns) if board[c] == 0]


def _ordered_moves(board, columns):
    centre = (columns - 1) / 2.0
    return sorted(_legal_moves(board, columns), key=lambda c: (abs(c - centre), c))


def _drop(board, col, piece, rows, columns):
    new_board = list(board)
    for r in range(rows - 1, -1, -1):
        idx = r * columns + col
        if new_board[idx] == 0:
            new_board[idx] = piece
            break
    return new_board


def _is_win(board, piece, rows, columns, inarow):
    def cell(r, c):
        return board[r * columns + c]

    for r in range(rows):
        for c in range(columns - inarow + 1):
            if all(cell(r, c + i) == piece for i in range(inarow)):
                return True
    for r in range(rows - inarow + 1):
        for c in range(columns):
            if all(cell(r + i, c) == piece for i in range(inarow)):
                return True
    for r in range(inarow - 1, rows):
        for c in range(columns - inarow + 1):
            if all(cell(r - i, c + i) == piece for i in range(inarow)):
                return True
    for r in range(rows - inarow + 1):
        for c in range(columns - inarow + 1):
            if all(cell(r + i, c + i) == piece for i in range(inarow)):
                return True
    return False


def _windows(rows, columns, inarow):
    key = (rows, columns, inarow)
    cached = _WINDOWS_CACHE.get(key)
    if cached is not None:
        return cached

    def idx(r, c):
        return r * columns + c

    wins = []
    for r in range(rows):
        for c in range(columns - inarow + 1):
            wins.append([idx(r, c + i) for i in range(inarow)])
    for r in range(rows - inarow + 1):
        for c in range(columns):
            wins.append([idx(r + i, c) for i in range(inarow)])
    for r in range(inarow - 1, rows):
        for c in range(columns - inarow + 1):
            wins.append([idx(r - i, c + i) for i in range(inarow)])
    for r in range(rows - inarow + 1):
        for c in range(columns - inarow + 1):
            wins.append([idx(r + i, c + i) for i in range(inarow)])
    _WINDOWS_CACHE[key] = wins
    return wins


def _evaluate(board, me, opp, rows, columns, inarow):
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
            continue
        if mine:
            score += WINDOW_WEIGHTS.get(mine, 0)
        elif theirs:
            score -= WINDOW_WEIGHTS.get(theirs, 0)
            if theirs == inarow - 1:
                score -= OPP_THREE_PENALTY
    return score


def _negamax(board, piece, me, opp, depth, alpha, beta, rows, columns, inarow):
    prev = opp if piece == me else me
    if _is_win(board, prev, rows, columns, inarow):
        return -(LARGE + depth)

    legal = _ordered_moves(board, columns)
    if not legal:
        return 0

    if depth == 0:
        ev = _evaluate(board, me, opp, rows, columns, inarow)
        return ev if piece == me else -ev

    next_piece = opp if piece == me else me
    value = -(LARGE * 2)
    for col in legal:
        child = _drop(board, col, piece, rows, columns)
        score = -_negamax(
            child, next_piece, me, opp, depth - 1, -beta, -alpha,
            rows, columns, inarow,
        )
        if score > value:
            value = score
        if value > alpha:
            alpha = value
        if alpha >= beta:
            break
    return value


def agent(observation, configuration):
    """Return the column index to play (Kaggle ConnectX entrypoint)."""
    rows = configuration.rows
    columns = configuration.columns
    inarow = configuration.inarow
    me = observation.mark
    opp = 2 if me == 1 else 1
    board = list(observation.board)

    legal = _ordered_moves(board, columns)
    if not legal:
        return 0

    best_col = legal[0]
    best_val = -(LARGE * 2)
    alpha, beta = -(LARGE * 2), LARGE * 2

    for col in legal:
        child = _drop(board, col, me, rows, columns)
        val = -_negamax(
            child, opp, me, opp, DEPTH - 1, -beta, -alpha,
            rows, columns, inarow,
        )
        if val > best_val:
            best_val = val
            best_col = col
        if best_val > alpha:
            alpha = best_val
    return best_col
