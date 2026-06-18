"""Evaluate a ConnectX policy against an opponent pool (CLI).

For simulation competitions there is no cross-validation score: an agent is
judged by playing matches. This harness plays N games against each opponent,
alternating who moves first, and reports win/draw/loss, win-rate, and a Wilson
lower confidence bound on the win-rate (a conservative "is this really better?"
estimate).

Usage
-----
    python evaluate.py --policy search \
        --opponents random,negamax,heuristic,frozen_v1 \
        --games 50 --seed 0 --depth 4

Opponents
---------
    random      : kaggle_environments built-in random agent
    negamax     : kaggle_environments built-in negamax agent
    heuristic   : agents/heuristic.py (this repo)
    frozen_v1   : opponents/v1/frozen_heuristic.py (frozen pool member)

Reproducibility
---------------
We seed Python's ``random`` and pass ``seed`` into the environment
``configuration`` so kaggle_environments seeds its own RNG. The built-in
``random`` opponent and any environment-level stochasticity are then
deterministic for a given ``--seed``. (Our own agents are already deterministic,
so against deterministic opponents the seed mainly fixes the built-in random
agent's choices.)

Logging follows CLAUDE.md: console=INFO, file=DEBUG, format
``%(asctime)s | %(levelname)s | %(message)s``. Logs + a summary JSON are written
to ``reference_sim/results/{run_name}/``. Logging happens ONLY here, never
inside an agent's move function.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Tuple

HERE = Path(__file__).resolve().parent

# --- Defaults (override via CLI) -------------------------------------------
DEFAULT_GAMES = 20
DEFAULT_SEED = 0
DEFAULT_DEPTH = 4
ALLOWED_OPPONENTS = ("random", "negamax", "heuristic", "frozen_v1")

logger = logging.getLogger("reference_sim.evaluate")


# ---------------------------------------------------------------------------
# Logging (CLAUDE.md-compliant)
# ---------------------------------------------------------------------------
def setup_logging(run_dir: Path, timestamp: str) -> Path:
    """Console=INFO, file=DEBUG. Returns the log file path."""
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / f"eval_{timestamp}.log"

    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return log_path


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------
def wilson_lower_bound(wins: float, n: int, z: float = 1.96) -> float:
    """Lower bound of the Wilson score interval for a binomial proportion.

    Draws are counted as half a win (``wins`` may be fractional). Returns 0.0
    for n == 0. This is the conservative win-rate estimate.
    """
    if n == 0:
        return 0.0
    p = wins / n
    denom = 1.0 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return max(0.0, (centre - margin) / denom)


# ---------------------------------------------------------------------------
# Opponent / policy resolution
# ---------------------------------------------------------------------------
def build_my_agent(policy: str, depth: int) -> Callable:
    """Build the agent under test (imported from this repo)."""
    from agents.heuristic import heuristic_agent
    from agents.search import search_agent

    if policy == "heuristic":
        return heuristic_agent
    if policy == "search":
        return lambda obs, cfg: search_agent(obs, cfg, depth=depth)
    raise ValueError(f"unknown --policy {policy!r} (heuristic|search)")


def build_opponent(name: str):
    """Resolve an opponent name to something kaggle_environments accepts.

    Built-ins ("random"/"negamax") are passed through as strings; our own
    agents are returned as callables.
    """
    if name in ("random", "negamax"):
        return name  # kaggle_environments built-in by name
    if name == "heuristic":
        from agents.heuristic import heuristic_agent
        return heuristic_agent
    if name == "frozen_v1":
        from opponents.v1.frozen_heuristic import agent as frozen_v1
        return frozen_v1
    raise ValueError(
        f"unknown opponent {name!r}; allowed: {', '.join(ALLOWED_OPPONENTS)}"
    )


# ---------------------------------------------------------------------------
# Match play
# ---------------------------------------------------------------------------
def play_pair(env, me, opp, seed: int) -> Tuple[int, int]:
    """Play two games (me first, then opp first). Return (my_result1, my_result2).

    Each result is +1 win / 0 draw / -1 loss from *my* perspective. Uses the
    env's ``run`` so we can pass a per-game configuration seed.
    """
    # Game A: I move first.
    env.reset()
    env.configuration.seed = seed
    env.run([me, opp])
    r_a = _my_result(env, my_position=0)

    # Game B: opponent moves first.
    env.reset()
    env.configuration.seed = seed + 1
    env.run([opp, me])
    r_b = _my_result(env, my_position=1)
    return r_a, r_b


def _my_result(env, my_position: int) -> int:
    """+1/0/-1 for the agent at ``my_position`` from the finished env state."""
    rewards = [s.reward for s in env.state]
    mine = rewards[my_position]
    other = rewards[1 - my_position]
    if mine is None:
        mine = -1  # our agent errored/timed out => treat as loss
    if other is None:
        other = -1
    if mine > other:
        return 1
    if mine < other:
        return -1
    return 0


def evaluate_against(
    env, me, opp_name: str, opp, games: int, base_seed: int
) -> Dict:
    """Play ``games`` games (alternating first move) vs one opponent."""
    wins = draws = losses = 0
    # Each "pair" is 2 games; play ceil(games/2) pairs, then trim to `games`.
    results: List[int] = []
    pair_idx = 0
    while len(results) < games:
        seed = base_seed + 2 * pair_idx
        r_a, r_b = play_pair(env, me, opp, seed)
        results.extend([r_a, r_b])
        pair_idx += 1
    results = results[:games]

    for r in results:
        if r > 0:
            wins += 1
        elif r < 0:
            losses += 1
        else:
            draws += 1

    n = len(results)
    win_points = wins + 0.5 * draws  # draws as half-wins for the rate
    win_rate = win_points / n if n else 0.0
    wlb = wilson_lower_bound(win_points, n)

    summary = {
        "opponent": opp_name,
        "games": n,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "win_rate": round(win_rate, 4),
        "wilson_lower_95": round(wlb, 4),
    }
    logger.info(
        "vs %-10s | W %3d  D %3d  L %3d | win_rate %.3f  wilson_lb %.3f",
        opp_name, wins, draws, losses, win_rate, wlb,
    )
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate a ConnectX policy vs an opponent pool.")
    p.add_argument("--policy", choices=("heuristic", "search"), default="search")
    p.add_argument(
        "--opponents",
        default="random,negamax",
        help="comma-separated; allowed: " + ",".join(ALLOWED_OPPONENTS),
    )
    p.add_argument("--games", type=int, default=DEFAULT_GAMES)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--depth", type=int, default=DEFAULT_DEPTH)
    p.add_argument("--run-name", default=None, help="results subdir name (default: auto)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    opponents = [o.strip() for o in args.opponents.split(",") if o.strip()]
    bad = [o for o in opponents if o not in ALLOWED_OPPONENTS]
    if bad:
        raise SystemExit(
            f"unknown opponent(s): {bad}; allowed: {', '.join(ALLOWED_OPPONENTS)}"
        )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_name = args.run_name or f"{args.policy}_d{args.depth}_{timestamp}"
    run_dir = HERE / "results" / run_name
    log_path = setup_logging(run_dir, timestamp)

    # Reproducibility: seed Python RNG; env seed is set per game in play_pair.
    random.seed(args.seed)

    logger.info("=== ConnectX evaluation ===")
    logger.info(
        "policy=%s depth=%d games=%d seed=%d opponents=%s",
        args.policy, args.depth, args.games, args.seed, ",".join(opponents),
    )
    logger.debug("run_dir=%s log=%s", run_dir, log_path)

    try:
        from kaggle_environments import make
    except ImportError as exc:  # pragma: no cover - depends on env
        logger.error("kaggle_environments not installed: %s", exc)
        logger.error("install with: pip install -r requirements.txt")
        return 2

    me = build_my_agent(args.policy, args.depth)
    env = make("connectx", debug=True)

    all_summaries = []
    for opp_name in opponents:
        opp = build_opponent(opp_name)
        all_summaries.append(
            evaluate_against(env, me, opp_name, opp, args.games, args.seed)
        )

    # Aggregate
    total_w = sum(s["wins"] for s in all_summaries)
    total_d = sum(s["draws"] for s in all_summaries)
    total_l = sum(s["losses"] for s in all_summaries)
    total_n = sum(s["games"] for s in all_summaries)
    overall_rate = (total_w + 0.5 * total_d) / total_n if total_n else 0.0
    logger.info(
        "OVERALL    | W %3d  D %3d  L %3d | win_rate %.3f over %d games",
        total_w, total_d, total_l, overall_rate, total_n,
    )

    summary = {
        "policy": args.policy,
        "depth": args.depth,
        "games_per_opponent": args.games,
        "seed": args.seed,
        "timestamp": timestamp,
        "opponents": all_summaries,
        "overall": {
            "wins": total_w,
            "draws": total_d,
            "losses": total_l,
            "games": total_n,
            "win_rate": round(overall_rate, 4),
        },
    }
    json_path = run_dir / f"summary_{timestamp}.json"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info("wrote summary: %s", json_path)
    return 0


if __name__ == "__main__":
    # Ensure imports resolve when run from any cwd (agent threads reset cwd).
    sys.path.insert(0, str(HERE))
    raise SystemExit(main())
