"""Policy agents for ConnectX (simulation-competition reference).

Each agent exposes a pure function ``*_agent(obs, config) -> int`` that returns
a column index to play. The agents are deterministic so that a given board
state always yields the same move (reproducibility).

NOTE: nothing in this package may ``print`` or ``logging`` inside the move
function — the scoring environment captures stdout/stderr and any noise there
can break an episode. Logging belongs in ``evaluate.py`` only.
"""

from .heuristic import heuristic_agent
from .search import search_agent

__all__ = ["heuristic_agent", "search_agent"]
