"""Development entrypoint for the ConnectX reference agent.

Selects a policy at import time and exposes ``agent(observation, configuration)``
which Kaggle ConnectX (and ``kaggle_environments``) call to obtain a move.

This module imports from the ``agents`` package, so it is NOT self-contained —
use it for local development / evaluation. For an actual Kaggle submission use
``submit_agent.py`` instead, which inlines everything into one file.

Switch the policy with the ``POLICY`` constant below, or by overriding the
``SIM_POLICY`` / ``SIM_DEPTH`` environment variables (handy for evaluate.py).

NOTE: ``agent()`` must never print/log — see agents/__init__.py.
"""

from __future__ import annotations

import os

from agents.heuristic import heuristic_agent
from agents.search import DEFAULT_DEPTH, search_agent

# --- Policy selection (edit here) ------------------------------------------
POLICY = "search"   # "heuristic" | "search"
DEPTH = DEFAULT_DEPTH

# Allow evaluate.py (or a shell) to override without editing the file.
POLICY = os.environ.get("SIM_POLICY", POLICY)
DEPTH = int(os.environ.get("SIM_DEPTH", DEPTH))


def agent(observation, configuration) -> int:
    """Return a column index to play for the current observation."""
    if POLICY == "heuristic":
        return heuristic_agent(observation, configuration)
    if POLICY == "search":
        return search_agent(observation, configuration, depth=DEPTH)
    raise ValueError(f"unknown POLICY: {POLICY!r} (expected 'heuristic' or 'search')")
