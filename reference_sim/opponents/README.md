# Opponent pool (the "fold" of simulation competitions)

In a supervised competition you measure progress with **cross-validation folds**:
a fixed, frozen partition of the data that lets you compare experiments on the
same yardstick. Simulation competitions have **no labels and no CV** — an agent
is only as good as the games it wins. The analogue of a frozen fold is a
**frozen opponent pool**.

## The rule

- A new, stronger opponent gets a **new version directory** (`v1/`, `v2/`, …).
- **Past versions are never deleted or edited.** Once `v1/frozen_heuristic.py`
  exists, its behaviour is fixed forever, exactly like a committed fold split.
- Evaluation = play your current agent against the **fixed pool** and measure
  win-rate / Wilson lower bound (see `../evaluate.py`).

## Why frozen

If the opponent changes whenever you improve your agent, win-rates from
different days are not comparable and you cannot tell whether you actually got
better. Freezing the pool gives you a stable measuring stick across the whole
competition — the same role a fixed `folds.csv` plays in `workspace/fold/`.

## Self-contained members

Each frozen opponent has **no imports from the `reference_sim` package**
(everything is inlined). This guarantees that a frozen agent keeps behaving
identically even if the live `agents/` code is refactored later. It also lets
`evaluate.py` load it without dragging in the rest of the repo.

## Adding a new version

1. When you build a meaningfully stronger agent (e.g. a deeper search or an RL
   policy), copy it self-contained into a new folder:
   ```
   opponents/v2/frozen_search_d6.py   # def agent(observation, configuration)
   ```
2. Add a loader branch in `evaluate.py::build_opponent` (e.g. `"frozen_v2"`)
   and to `ALLOWED_OPPONENTS`.
3. Keep older versions so historical win-rates stay reproducible.
4. Record what each version is and why it was frozen in this README.

## Current pool

| Version | File | Agent | Notes |
|---------|------|-------|-------|
| v1 | `v1/frozen_heuristic.py` | win/block/centre heuristic | Baseline opponent. Frozen from `agents/heuristic.py`. Loaded by `evaluate.py` as `frozen_v1`. |

Built-in opponents from `kaggle_environments` (`random`, `negamax`) are also
available to `evaluate.py` without living in this pool — they are stable by
virtue of being shipped with the library.
