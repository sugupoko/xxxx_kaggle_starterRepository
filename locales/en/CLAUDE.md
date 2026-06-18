# Competition Workspace

This repository is an experiment management template for data science competitions.
It supports **Kaggle and non-Kaggle platforms** (grand-challenge.org, CodaBench, custom sites).
**When in doubt, check the design intent in `KAGGLE_DIRECTION.md`.** (The filename is historical — the content is a general-purpose design guide.)

## Meta-rule: Designed for Opus (1M context)

This template is designed to run on **Claude Opus (1M context)**. To leverage that, **don't hold back** on the following:

- **Cross-experiment analysis**: Load `daily_reports/*.md` + all `workspace/exp*/SESSION_NOTES.md` + `claudeSummary.md` + `submit/SUBMISSIONS.md` **in parallel** before judging. Don't try to conserve context by reading sequentially
- **Code review**: Parallel-load `src/`, `config.yaml`, fold generation scripts, and `KAGGLE_DIRECTION.md` **simultaneously** before checking consistency (trace the leakage path end-to-end: training → inference → submission)
- **Strategy**: See the "line," not the "points." The `competition-strategist` agent / `/strategy` skill is optimized for cross-experiment synthesis
- **Background execution**: Run training jobs, scraping, long validations with `run_in_background` or via `/loop` / `/schedule`
- **External GPU**: When local GPU is not enough, run training on RunPod (`tools/runpod/` — README currently Japanese only) — connection / key handling / cost control verified on real hardware. Keys live in `.runpod.env` (gitignored); never expose raw values
- **Plan mode**: Use Plan mode before major direction changes (moving to a new exp number, switching submission format, etc.)

Parallel reading is OK for **your own competition files**. You don't need to load all of `reference/` or every byte of `datasets/*`.

## Competition Onboarding Phase (Do this before writing any training code)

When starting a new competition, don't jump into training code. First fill in the following under **`survey/competition/`** before any implementation:

1. **Platform**: Kaggle / grand-challenge.org / CodaBench / custom site
2. **Task definition**: inputs, outputs, number of classes, evaluation unit (per-image / per-pixel / per-patient)
3. **Data location**: download URLs, size, format, license, local paths where it will live
4. **Metric**: exact definition (per-class / macro / micro, treatment of background class — eliminate implementation ambiguity)
5. **Submission format**: CSV / prediction-file zip (images, JSON) / Docker container
6. **Timeline**: validation phase / test phase / final deadline, submission quota
7. **Rules**: team size, external data allowed?, pretrained models allowed?, commercial license

Do not start implementation until all 7 items are filled in.

**For Simulation competitions (submit an agent that plays matches — Lux AI / ConnectX / Halite etc.), also confirm the following** (with no fixed train/test, grasping the environment and the I/F contract is essential):
- **Engine / environment**: `kaggle_environments` or a custom engine, game name (connectx / lux_ai_s3 etc.), whether `make(...)` reproduces it
- **Observation / action space**: what is in `observation`, the contents of `configuration`, the set of legal moves and the penalty for illegal moves
- **Episode / turn structure**: turns per episode, simultaneous vs alternating turns, number of players
- **Rating system**: TrueSkill / ELO-like scoring, matchmaking, matches per day
- **Agent submission I/F**: the return (action) format of `def agent(observation, configuration)`, per-move timeout, memory limit, agent file-size cap

## Phase Guard (Don't Jump to Ensemble)

**Competitions have phases. If you don't separate "do/don't" per phase, you'll waste resources by bringing late-stage optimization into early stages.**

| Phase | Progress | Do | **Never Do** |
|-------|----------|-----|--------------|
| Early | ~30% | EDA / fold design / **one strong baseline** / working submission pipeline / research | Ensemble, TTA, heavy aug, complex post-processing, hyperparameter tuning |
| Mid | 30-70% | **3-5 single models** with diversity / error analysis / data additions / aug validation | **Serious ensemble work**, excessive hyperparameter search |
| Late | 70%- | **Ensemble** / TTA / post-processing / final submission selection / LB shake evaluation | New architecture, large preprocessing changes, new external data |

Phase detection is **hybrid: time-based + milestone-based**. The `competition-strategist` agent (invoked via `/strategy`) auto-detects the phase and warns on divergence (e.g., "Entered mid phase but only 1 baseline exists").

**Simulation-competition phase guard** (re-read CV/ensemble as "matches / opponent pool / policies"):

| Phase | Progress | Do | **Never Do** |
|-------|----------|-----|--------------|
| Early | ~30% | a working submission pipeline (an agent that completes one episode) / a **heuristic baseline** / understanding the environment and I/F / a local evaluation harness + the first opponent pool | spin up heavy RL early, expensive search implementations, overfitting to a single opponent |
| Mid | 30-70% | strengthen search (minimax/MCTS) / RL (self-play/PPO) / **diversify the opponent pool** / analyze losses from replays | evaluating against only one opponent, tuning by feel without an evaluation harness |
| Late | 70%- | **policy ensembling** (opponent-specific counters, situation-specific switching) / track meta shifts / LB shake evaluation / select the final agent | starting a new algorithm, large observation/action redesigns |

Since simulation has no fixed CV, judge each phase's progress with **the trend of win-rate against the opponent pool + the trend of submission rating**.

**Session start checklist**: Before proposing any action:
1. What phase are we in? (days remaining + milestone status)
2. Is the proposed action in the current phase's "do" list?
3. If not, explicitly state it's a phase violation before deferring to the user

See `KAGGLE_DIRECTION.md` "Phase Guidance" for details and per-phase completion criteria.

## Idea Proposal Principles (Safe + Bold)

**When proposing approaches or ideas, always present both a "safe" and a "bold" option.**

- **Safe**: Known methods, established practices, incremental improvements. Expected to reliably improve scores
- **Bold**: Unconventional, cross-domain transfers, approaches nobody would normally try. High failure risk, but huge upside if successful

Example:
```
Safe: Switch encoder from efficientnet_b0 to b4 (expected ~+0.5% improvement)
Bold: Drop segmentation entirely and solve with object detection / Transfer a pretrained model from a completely different modality
```

To avoid local optima, bold ideas should be "nobody would normally do that" level.

## Basic Rules

- Experiments go under `workspace/`
- Claude: `expA00_baseline` (letter + 2-digit number), Human: `exp200_name` (3-digit number)
- Every experiment folder must have a `SESSION_NOTES.md`
- Only increment exp numbers for major direction changes. Minor tweaks stay in the same folder
- All results, insights, and strategy go in daily reports `daily_reports/YYYYMMDD.md` (no separate plan files)

## Training Code Rules

- **AMP (Mixed Precision) always ON** (`precision: 16-mixed`)
- **Checkpoint resume is mandatory** (`save_last=True` + `ckpt_path`)
- **Seed fixed** (`pl.seed_everything(seed, workers=True)`)
- All hyperparameters managed via config (no hardcoding)
- **Use Python `logging` module for output** (`print` is prohibited)
  - Output to both console (INFO) and file (DEBUG)
  - Log files saved to `results/{experiment_name}/foldN/` with timestamps
  - Format: `%(asctime)s | %(levelname)s | %(message)s`
- **All outputs go to `workspace/expXXX_xxx/results/{experiment_name}/foldN/`**
  - **Always write to `results/` directly under the experiment folder.** Never create it at the repo root or under `workspace/results/`
  - In `train.py`, build the path **relative to the experiment folder** with absolute resolution: `output_dir = Path(__file__).resolve().parent / 'results' / experiment_name / f'fold{fold}'` (one `parent` because `train.py` lives directly in the experiment folder). Do NOT use `Path('results/...')` — relative paths depend on cwd and cause accidents
  - Specify `output_dir` in config.yaml as a path relative to the experiment folder (or absolute)
  - In `run.sh`, `cd "$(dirname "$0")"` before calling `python train.py "$@"` (also prevents cwd-dependent accidents). Arguments override config.yaml in OmegaConf dotlist format (e.g., `data.fold=0`). There is no `--config` flag
  - Example output: `workspace/expA00_baseline/results/expA00_baseline/fold0/best_model.ckpt`
  - Save best_model, checkpoint, log, training_log.json, **config.yaml** all in the same directory
  - **config.yaml is auto-copied at training start** (for reproducibility)
  - Define `experiment.name` in config; change the name when parameters change
  - If an experiment directory with the same name exists, append `_001`, `_002` numbering (never overwrite)
- Run via `run.sh` (create `run.sh` in each experiment folder; all training/inference goes through this script)
- **Daily reports `daily_reports/YYYYMMDD.md` are the central record**
  - One file per day. Strategy, roadmap, insights, experiment results all go here
  - **Append as insights emerge** (training complete, error found, score change — write immediately, don't wait)
  - Record experiment results (CV scores etc.) with exact numbers
  - Don't edit past reports; keep them as history
  - **Read the latest daily report at session start to understand current status**
  - Template:
    ```markdown
    # Daily Report YYYY-MM-DD

    ## Competition Info
    - **Competition**: Competition name
    - **Deadline**: YYYY-MM-DD (N days remaining)
    - **Metric**:
    - **LB Status**:

    ## What was done today
    ### 1. ...

    ## Numerical Summary
    | Experiment | Data Size | CV | LB | Status |
    |------------|-----------|-----|-----|--------|

    ## Strategy & Roadmap

    ## Decisions & Insights
    <!-- Important decisions and insights from today -->

    ## Data Inventory
    <!-- Organize available data sources -->

    ## Next Steps
    - [ ] TODO
    ```

## Knowledge Accumulation (Flow → Stock)

**As work grows, insights pile up. Separate the time-ordered log (flow) from distilled knowledge (stock).**

| Layer | Location | Nature |
|-------|----------|--------|
| **Flow** | `daily_reports/YYYYMMDD.md` | Time-ordered log. Append-only, never edited. "What happened" |
| **Stock** | `knowledge/**.md` | Distilled knowledge. Atomic pages + `INDEX.md`. "What we currently know" |

- `knowledge/` is **explicit in-repo .md files** (a visible asset, committed and shared). Distinct from `memory/` (Claude Code's cross-session private notes)
- **Principle: write to the daily report first → distill and promote into `knowledge/`.** Never write straight to stock, skipping flow (provenance would be lost)
- One topic per file (`technique/` `data/` `error/` `decision/`). Frontmatter + short distilled body. Conventions in `knowledge/README.md`, template in `knowledge/_template.md`
- **Retrieve via `INDEX.md` first, then load only the relevant page.** Don't scan all pages (saves context)
- Accumulate / search / consolidate with `/wiki` (`add` / `find` / `promote` / `consolidate`). `INDEX.md` is auto-injected at SessionStart
- Keep rejected insights too, as `status: rejected` (so the same mistake isn't repeated)

## Fold Design (Critical)

**Do not default to random KFold. Check data characteristics first.**

- Time series → TimeSeriesSplit
- Group structure → GroupKFold
- Class imbalance → StratifiedKFold
- Group + imbalance → StratifiedGroupKFold
- Record fold design rationale and per-fold distributions in SESSION_NOTES.md
- Check CV/LB correlation; if weak, revisit fold design

**Fold assignment persistence (`workspace/fold/`):**
- Save fold assignments in `workspace/fold/{version}/folds.csv`, shared across all experiments
- Generate with `workspace/fold/generate_folds.py`. Version controlled
- Create new version when preprocessing or data changes. Never delete old versions
- Specify version in config.yaml via `data.folds_csv`
- Document design intent and split details in `workspace/fold/README.md`

**Simulation competitions have no folds:**
- There is no fixed train/test and no CV. Instead, design an "**opponent pool (versioned) + local evaluation harness**"
- Use **win-rate against the fixed opponent pool as a proxy CV** (measure with the same opponent set and the same seed; keep old versions when you bump the pool)
- Diversify the opponent pool from weak to strong (random / simple heuristic / your past agents / strong public agents) to prevent overfitting
- See `reference_sim/README.md` / `reference_sim/opponents/README.md` for details

## Submission Pipeline (`submit/`)

Submission code and models are managed under `submit/`. Submission formats differ by platform, so follow one of the layouts below.

### Common Rules (Platform-Agnostic)

- **Naming**: Sequential format `v00X_<source-exp-folder>` or `v00X_<source-exp-folder>_<extra-tag>`
  - Examples: `submit/v001_expA02_super_clone` / `submit/v002_expA03_anchor_calib_ens5fold`
  - **Always include the source experiment folder name** — prevents the "which exp's weights is this?" problem later
  - For ensembles, use representative exp name + `_ens` (e.g., `v005_expA04_ens3model`)
  - Extra tag for inference param variations (e.g., `_tta8`, `_thresh07`)
- **Self-contained**: Submission scripts include preprocessing/postprocessing internally and don't depend on `workspace/` training code
- **Environment detection**: Auto-detect execution environment (Kaggle / grand-challenge / local) and switch paths
- **Inference parameters**: Managed as constants at the top of the file (avoid scattered hardcoding)
- **Source tracking**: Include `Source: workspace/expXXX/.../best_model/` and CV score in the script docstring
- **Model handling**: Copy `best_model/` from `workspace/`. `model/` is git-ignored due to size
- **Local test is mandatory**: Verify the submission artifact (CSV / prediction files / Docker image) locally before submitting
- **Artifact validation**: Always check platform requirements (file count, naming rules, value ranges, missing values) before submission
- **Uploads are manual**: Actual uploads to Kaggle Dataset / grand-challenge submission page / etc. are done by the user (Claude does not execute them)
- **Submission history**: Record all submissions in `submit/SUBMISSIONS.md`. Include experiment folder, model source path, fold definition, training data, training/inference parameters, preprocessing, CV/LB scores

### Kaggle

Kaggle has **two competition types**: **CSV Competition** vs **Code Competition**. Submission flows differ completely — identify the type first:

| Type | How to detect | Submission |
|---|---|---|
| **CSV Competition** | Rules say "Submit CSV directly" / `kaggle competitions submit` succeeds | Upload `submission.csv` directly. CLI one-liner |
| **Code Competition** | Rules say "Submissions are made from Kaggle Notebooks" / `kaggle competitions submit` returns "Code Competition" error | Run Notebook on Kaggle → "Submit to Competition". **Final Submit is manual** |

#### (a) CSV Competition

```
submit/v001_baseline/
├── notebook.py          # Inference script (run locally)
└── model/               # Trained model files
```

- Entry point is `notebook.py`
- Output is `submission.csv`. Always validate **row count, column names, missing values, value ranges** before submission
- Only commit `notebook.py` to git

#### (b) Code Competition

```
submit/v001_baseline/
├── inference_notebook.py     # jupytext source synced with .ipynb (commit)
├── inference_notebook.ipynb  # generated from .py (do not commit)
├── kernel-metadata.json      # Notebook Kaggle metadata (commit)
├── dataset-metadata.json     # Dataset Kaggle metadata (commit)
├── upload.sh                 # One-command Dataset create + Notebook push (commit)
└── kaggle_dataset/           # Dataset upload target (.gitignore)
    ├── models/
    └── (trained model files)
```

- **For the full flow, templates, and gotchas, see `tools/kaggle_code_competition_submission.md`** (currently Japanese only)
- Flow: `upload.sh` uploads Dataset + pushes Notebook → Save & Run All on Kaggle UI → "Submit to Competition" (manual)
- Required: `enable_internet: false` (no pip install), self-contained (no `kernel_sources` imports)
- Validation: assert format at notebook end (`assert len(sub) == EXPECTED_ROWS` etc.)
- Embed CV score in `kernel-metadata.json` / `dataset-metadata.json` title (so the weight version is identifiable at a glance)

### Non-Kaggle (grand-challenge.org / CodaBench / custom sites)

Typically one of two submission types. Choose based on the competition spec.

**(A) Prediction-file type** (upload a zip of images / masks / JSON)

```
submit/v001_baseline/
├── predict.py           # Script that reads input files and writes predictions
├── run.sh               # predict.py → validate outputs → zip in one go
├── requirements.txt     # Pinned for reproducibility
├── model/               # Trained model files (.gitignore)
└── output/              # Generated submission artifacts (.gitignore)
```

- Input/output directories specified as constants at the top of `predict.py` (`INPUT_DIR` / `OUTPUT_DIR`)
- Output must **strictly match the official spec** in filename, size, dtype, and value range
- Before submission, assert "input file count == output file count" and "stem name match"

**(B) Docker container type** (submit as an algorithm container)

```
submit/v001_baseline/
├── Dockerfile
├── process.py           # Implements the grand-challenge algorithm interface
├── requirements.txt
├── test/                # Local validation samples
│   ├── input/
│   └── expected_output/
├── build.sh             # docker build
├── test.sh              # Run the container locally and validate outputs
├── export.sh            # docker save → tar.gz (submission artifact)
└── model/               # .gitignore
```

- Respect the platform's I/O contract (input path / output path / file format) above all
- Always run `test.sh` after building to regression-test locally with the same I/O paths as production
- Know the image size / GPU requirements / inference time limits in advance; consider model lightening or ONNX conversion if needed
- Only commit `Dockerfile` / `process.py` / scripts to git (exclude large data in `model/` and `test/`)

### For Simulation competitions (agent-submission type)

**(D) Simulation agent type** (submit a single file implementing `def agent(observation, configuration)` that plays against other agents on the server)

```
submit/v001_expA00_heuristic/
├── agent.py             # the submitted agent (a self-contained single file)
├── run_local.sh         # run one full episode locally + check win-rate vs the opponent pool
├── requirements.txt     # for local evaluation (match the submission env's preinstalled libraries)
└── model/               # policy weights etc. (.gitignore; only if used)
```

- The entry point is `def agent(observation, configuration)` in `agent.py`. **Self-contained** (complete in one file without depending on `workspace/` or external modules; if weights are used, resolve the load path via environment detection)
- **Confirm one full episode completes locally** before submitting (run `kaggle_environments` `make(...)` / `env.run([agent, "random"])` via `reference_sim/evaluate.py`)
- **Verify it does not die from timeout / memory / illegal moves**: measure per-move response time and keep it within the limit / return only legal moves / never `print` stray output to stdout inside the agent function (it pollutes the scoring log)
- Follow the existing naming convention (`v00X_<source-exp-folder>[_extra-id]`). Commit only `agent.py` / scripts to git (exclude `model/`)

## Error Analysis Principles (Look at Outputs Before Scores)

**Before trying to improve scores, first observe outputs to identify "what's wrong."**

- After each experiment, visually inspect prediction vs ground truth (at least 20 samples)
- Classify error types and identify patterns (categories are task-dependent; discover inductively from outputs, don't predefine lists)
- Apply targeted fixes based on error types (preprocessing, postprocessing, inference strategy, training data, model changes)
- Don't blindly search by tweaking parameters based on score numbers alone

Order: Read outputs → Identify what's wrong → Address the cause → Verify with scores

## Preprocessing & Evaluation

- Normalization uses statistics from train data only (never use test data info)
- Accurately reproduce the competition metric (check parameters of existing implementations)
- Start with weak augmentation; strengthen only after overfitting is confirmed
- Record single model CV/LB before ensembling
- Validate submissions depending on the platform:
  - Kaggle (CSV): row count, column names, missing values, value ranges
  - Prediction files (image/JSON): file count, naming rules, dtype, value range, size
  - Docker: local regression test, I/O paths, GPU/time limits

## Reference Code

- `reference/` contains a template for 2.5D segmentation (PyTorch Lightning + timm + smp)
- Use as a base for new experiments
- See `reference/README.md` for details (currently Japanese only)
- `reference_sim/` contains a **reference for simulation competitions** (agent I/F + match-evaluation harness, with ConnectX as the worked example). Use it as the base for agent-submission competitions. See `reference_sim/README.md`

## Automation (Hooks)

`.claude/settings.json` ships with these hooks. Inspect/edit via `/hooks`:

- **SessionStart**: Auto-inject the latest daily report (newest match of `daily_reports/[0-9]*.md`) and `knowledge/INDEX.md` (the knowledge index) into context. Ensures you never skip status check or lose track of where stock knowledge lives
- **SessionEnd**: When the session ends, append a `<!-- session ended: ... -->` marker to today's daily report (if it exists). Keeps a daily activity log (uses SessionEnd, not Stop — Stop fires on every completed response)

## Available Skills

- `/onboard [URL]` - Walk through the 7-item competition onboarding checklist and save to `survey/competition/overview.md`. **Use first when starting a new competition** (also covers the extra items for simulation competitions)
- `/exp-new <name> [--human]` - Scaffold a new experiment folder from `reference/` with auto-generated `SESSION_NOTES.md` and `run.sh`
- `/daily-report` - Create today's `daily_reports/YYYYMMDD.md` carrying over from yesterday's (use at session start)
- `/submit-check <path>` - Pre-submission validation (Kaggle CSV / prediction zip / Docker / Simulation agent). Use right before any submission
- `/strategy [focus]` - Cross-experiment synthesis. The `competition-strategist` agent loads all daily reports + SESSION_NOTES + claudeSummary in parallel and proposes next moves. Use weekly or when CV plateaus
- `/survey-papers [keyword]` - Paper/solution survey (runs in `context: fork` without polluting main context)
- `/wiki [add|find|promote|consolidate]` - Accumulate / search / consolidate competition knowledge in the `knowledge/` stock layer (atomic pages + INDEX). Distill and promote from the daily-report flow. Use when an insight emerges, for weekly cleanup, or to recall past knowledge

## Custom Agents

Automatically delegates to subagents as needed. Parallel execution supported.

| Agent | Model | Purpose |
|-------|-------|---------|
| **competition-strategist** | opus | Cross-experiment synthesis (loads all daily reports + SESSION_NOTES + claudeSummary + SUBMISSIONS in parallel). Maximum use of 1M context |
| **code-reviewer** | opus | ML/DL code quality review. Catches issues only visible across multiple files: leakage, metric bugs, broken checkpoints |
| **submission-validator** | sonnet | Pre-submission validation (CSV / prediction zip / Docker / Simulation agent). Eliminates submission errors |
| **kaggle-researcher** | sonnet | Paper, similar competition solution, and discussion research. Covers non-Kaggle platforms (grand-challenge.org / CodaBench) too |
| **data-analyst** | sonnet | EDA, visualization, feature analysis. For understanding overall data picture |

**Model selection policy**:
- **opus**: "Can't notice without reading deeply" tasks (leakage detection, cross-experiment synthesis). Premised on using 1M context
- **sonnet**: "Wide and shallow" tasks (research, EDA, format checks). Procedural work that benefits from speed
