# Reference: Simulation Competition Template (ConnectX)

A runnable reference for **simulation / agent-vs-agent competitions** — the kind
where you **submit an agent** that is **scored by playing matches** (Lux AI,
ConnectX, Halite, Kore, …). This sits alongside `reference/` (the 2.5D
segmentation template) as the second starting point in this repo.

The concrete engine here is **ConnectX** via `kaggle_environments`, but the
structure (agent I/F + opponent pool + evaluation harness) ports to other
engines by swapping the move function and the environment name.

## 0. Environment setup (環境構築)

The heuristic/search baselines are **pure Python + CPU only** — no GPU, no heavy
ML stack. Setup is one `pip` install (Python 3.10+):

```bash
# from this folder
pip install -r requirements.txt          # kaggle-environments, numpy

# verify in one line (should print W/D/L and win-rate, then exit 0)
bash run_local.sh --policy heuristic --opponents random --games 4 --seed 0
```

`run_local.sh` is the **foolproof entry**: it `cd`s into this folder (so output
never lands in the wrong place regardless of your cwd) and **auto-installs
`requirements.txt` if `kaggle_environments` is missing**, so you never hit a
"module not found" mid-run. Run `evaluate.py` directly only if you prefer.

- **No GPU needed** for stages 1–2 (heuristic / alpha-beta search).
- **RL self-play (stage 3, §5)** is the only part that wants a GPU. Reuse the
  repo's existing environment-construction assets — the closed Docker image
  (`docker/`, `rundocker.sh`) and external GPU (`tools/runpod/`) — exactly as
  the supervised side does. Nothing simulation-specific is required there.
- `results/` is git-ignored (eval logs/JSON are run artifacts), so repeated
  evaluation never pollutes commits.

## 1. How this differs from supervised learning

| | Supervised comp (`reference/`) | Simulation comp (this) |
|---|---|---|
| What you submit | predictions (CSV) or weights | **an agent** (a `agent(obs, cfg)` function) |
| Ground truth | labels | **none** — only game outcomes |
| Local metric | **CV** over fixed folds | **win-rate** vs a **frozen opponent pool** |
| Leaderboard | metric on hidden test | **skill rating** from live matches (TrueSkill-like) |
| Overfitting risk | to the train labels | to a **single opponent** (beats X, loses to everyone else) |

There is **no cross-validation score**. The yardstick is "how often do I beat a
fixed set of opponents", which is why the opponent pool is frozen and
versioned (`opponents/`) — it is the simulation analogue of `workspace/fold/`.

## 2. Agent interface

Kaggle ConnectX calls a single function:

```python
def agent(observation, configuration) -> int:
    # observation.board : list[int], length rows*columns, row-major
    #                     (0 empty, 1 player1, 2 player2)
    # observation.mark  : int, our piece (1 or 2)
    # configuration     : .rows (6), .columns (7), .inarow (4)
    # return            : the column index to drop a piece into
    ...
```

Rules implemented exactly: a move is legal iff the **top cell** of the column is
empty (`board[c] == 0`); the piece falls to the **lowest empty cell**; a win is
`inarow` consecutive pieces horizontally, vertically, or on either diagonal.

**Hard rule (from `CLAUDE.md`): never `print`/`logging` inside `agent()`.** The
scoring environment captures stdout/stderr and stray output can break an
episode. All logging lives in `evaluate.py` only.

### Files

```
reference_sim/
├── agent.py            # dev entrypoint: picks a POLICY, exposes agent(obs, cfg)
├── agents/
│   ├── heuristic.py    # rule-based baseline (win / block / centre)
│   └── search.py       # alpha-beta negamax, depth-limited, deterministic
├── evaluate.py         # CLI: play vs an opponent pool, report win-rate + Wilson LB
├── run_local.sh        # cwd-safe wrapper for evaluate.py (auto-installs deps)
├── opponents/
│   ├── README.md       # opponent-pool versioning (the "fold" of sim comps)
│   └── v1/frozen_heuristic.py   # frozen, self-contained pool member
├── submit_agent.py     # SELF-CONTAINED negamax — submit this file to Kaggle
├── requirements.txt    # kaggle-environments, numpy (range-pinned)
└── README.md
```

`agent.py` imports from `agents/` (good for dev). `submit_agent.py` inlines
everything into one file (good for submission). Keep them in sync.

## 3. Evaluation harness

Install deps, then play your policy against an opponent pool:

```bash
pip install -r requirements.txt

# Heuristic baseline vs the built-in random agent (quick smoke test)
python evaluate.py --policy heuristic --opponents random --games 4 --seed 0

# Search policy vs random + the built-in negamax, 50 games each
python evaluate.py --policy search --opponents random,negamax --games 50

# Full pool, deeper search, fixed seed
python evaluate.py --policy search \
    --opponents random,negamax,heuristic,frozen_v1 \
    --games 100 --seed 0 --depth 6
```

Each opponent plays `--games` games with **first move alternating** (half as
player 1, half as player 2) so you are not flattered by a first-move advantage.
The harness reports W/D/L, win-rate (draws count as half a win), and the
**Wilson 95% lower bound** — a conservative "is this really better?" number.

- Allowed `--opponents`: `random`, `negamax` (both `kaggle_environments`
  built-ins), `heuristic`, `frozen_v1`.
- **Reproducibility:** the harness seeds Python's RNG and passes `--seed` into
  the environment `configuration` per game, so the built-in `random` opponent
  and any environment stochasticity are fixed. Our own agents are deterministic
  by construction. (If a future engine has stochasticity that ignores the
  configuration seed, note it in code where it cannot be controlled.)
- Output: a timestamped log (`results/{run}/eval_*.log`) and a machine-readable
  `results/{run}/summary_*.json`. Logging follows `CLAUDE.md`: console=INFO,
  file=DEBUG, format `%(asctime)s | %(levelname)s | %(message)s`.

## 4. Opponent pool = the "fold" of simulation comps

Because there is no CV, the **frozen opponent pool** (`opponents/`) is your
stable yardstick. Build a stronger agent → freeze it as a new version
(`v2/`, …), never delete old versions, always measure against the fixed pool.
Full rationale and the "how to add a version" recipe are in
`opponents/README.md`.

## 5. Progression: heuristic → search → RL (self-play)

Apply the repo's **phase guard** (`CLAUDE.md`): don't start with the heavy thing.

| Stage | What | Status here |
|-------|------|-------------|
| 1. Heuristic | win/block/centre rules. Zero training, instant baseline, sanity-checks the harness | ✅ `agents/heuristic.py` |
| 2. Search | alpha-beta negamax with a windowed eval. Strong, deterministic, no training | ✅ `agents/search.py`, `submit_agent.py` |
| 3. RL (self-play) | learn a policy/value net by playing itself (AlphaZero-style / PPO league). Competition-specific and compute-heavy | ⏳ future skeleton |

RL self-play is deliberately **not** implemented: it is engine-specific and
expensive, and per the phase guard it belongs in the mid/late game after a
strong search baseline exists. When you add it, train under `workspace/` (use
RunPod for GPU per `CLAUDE.md`), then **freeze the trained policy into a
self-contained `submit_agent.py`** and into the opponent pool so future agents
are measured against it.

## 6. Submitting to Kaggle

ConnectX is a **Kaggle simulation competition**: you submit a **single Python
file** that defines `agent(observation, configuration)`.

1. Verify locally:
   ```bash
   python evaluate.py --policy search --opponents random,negamax,frozen_v1 --games 100
   ```
2. Make sure `submit_agent.py` matches the search logic you just measured, and
   fill in the local win-rates in its top docstring (so you know which agent a
   submission was).
3. Upload **`submit_agent.py`** as the agent on the competition's *Submit
   Agent* page (Claude does **not** upload — the human does, per `CLAUDE.md`).

`submit_agent.py` is **self-contained** (no local imports), uses only the Python
standard library, and never prints/logs inside `agent()` — so it runs as-is in
the scoring sandbox. Record every submission in `submit/SUBMISSIONS.md` per the
repo rules (which agent, depth, local win-rates vs each pool member).

## 7. Porting to other engines (Lux AI, Halite, Kore, …)

The architecture is engine-agnostic. To move to another `kaggle_environments`
game (or another simulator):

1. **Agent I/F** — reimplement the board helpers and `agent(obs, cfg)` for the
   new observation/action format in `agents/` (keep them pure + deterministic;
   still never print/log inside the move function).
2. **Evaluate** — change the environment name in `evaluate.py`
   (`make("connectx")` → `make("<engine>")`); the match loop, alternating
   sides, win-rate, Wilson bound, and logging are reusable.
3. **Opponent pool** — keep the frozen/versioned `opponents/` discipline.
4. **Submit** — keep `submit_agent.py` self-contained for the new engine.

Stages 1–3 (heuristic → search → RL) and the phase guard apply to any
simulation competition; only the per-engine rules and observation shape change.
