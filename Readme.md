# Competition Experiment Template

**v2.7.1**

> Supports **Kaggle** and **non-Kaggle** competitions (grand-challenge.org, CodaBench, custom platforms).
> Designed for **Claude Opus (1M context)**.

[日本語 (default)](#日本語) | [English](#english)
　
---

## English

This repository is an **experiment management template for data science competitions**.
Built for Claude Code, it provides rules and workflows for the full pipeline: **data acquisition → EDA → research (papers/similar competitions) → experiments (exp management) → submission**, with high reproducibility.

Supports **Kaggle** and **non-Kaggle** platforms (grand-challenge.org, CodaBench, custom sites). Submission pipelines cover CSV, prediction-file (zip), and Docker container formats.

### Requirements

- Linux / WSL2
- Python 3.10+
- [Claude Code](https://claude.com/claude-code) CLI
- Docker (optional — only for the closed-env workflow below)

### Known Limitations

- **Final submission is manual** — Claude prepares and validates artifacts, but the actual upload / "Submit to Competition" click (Kaggle Dataset, Code Competition Notebook, grand-challenge, etc.) is always done by the user
- **Discussion monitoring relies on scraping** — the official Kaggle API has no discussion endpoint, so `survey/discussion/` uses Playwright-based scraping (keep 2-3 s between requests)
- **Model files are not tracked by git** — `model/`, `*.ckpt`, `*.pth` etc. are gitignored for size; move weights via Kaggle Dataset / external storage
- **Some docs are Japanese-only** — guides under `tools/` and `reference/README.md` (see Language Setup below)

### Quick Start

```bash
# 1. Fork this repository

# 2. Set language to English
bash setup.sh en

# 3. Set target competition URL in KAGGLE_DIRECTION.md

# 4. Start working with Claude Code
```

### First Session Flow

```text
/onboard <competition URL>     # fill the 7-item checklist → survey/competition/overview.md
/daily-report                  # create today's daily report
# design folds: workspace/fold/generate_folds.py → workspace/fold/{version}/folds.csv
/exp-new baseline              # scaffold workspace/expA00_baseline from reference/
bash workspace/expA00_baseline/run.sh       # train
/submit-check submit/v001_expA00_baseline   # validate before submitting
```

### Language Setup

This template supports **Japanese** and **English**. Run the setup script to switch:

```bash
bash setup.sh en   # English
bash setup.sh ja   # Japanese (default)
```

This updates: `CLAUDE.md`, `KAGGLE_DIRECTION.md`, agent definitions, skill definitions, and templates. It also enables the secret-blocking git pre-commit hook (`core.hooksPath=tools/git-hooks`) — or enable it manually with `bash tools/git-hooks/install.sh`. The hook is local config, so run this once per clone.

**Localization scope** — files switched by `setup.sh` (root is the Japanese original; `locales/ja` is a byte-identical copy, `locales/en` is the translation; CI enforces the sync): `CLAUDE.md`, `KAGGLE_DIRECTION.md`, `.claude/agents/`, `.claude/skills/`, `knowledge/` scaffolding (`README.md` / `_template.md` / `INDEX.md`), and `submit/SUBMISSIONS.md`. Of these, `knowledge/INDEX.md` and `submit/SUBMISSIONS.md` are user-editable seeds — `setup.sh` refreshes them only while pristine, and the CI byte-identity check excludes them. **Japanese only (not localized)**: guides under `tools/` (`runpod/README.md`, `kaggle_code_competition_submission.md`, …), `reference/README.md`, and `claudeSummary.md` (user content — seeded once, never overwritten by `setup.sh`).

The sync-check CI (`.github/workflows/locale-sync.yml`) exists to maintain this template repo itself: the byte-identity check auto-skips on forks (only the shell/Python syntax checks run), so competition forks can keep the workflow as-is — or simply delete the file after running `setup.sh`.

#### Run in a closed Docker environment (optional)

```bash
bash docker/build.sh    # build the "claude" image (PyTorch + ML stack + Claude Code CLI)
bash rundocker.sh       # launch a container with the repo mounted
```

`build.sh` inherits the host `UID`/`GID`; `rundocker.sh` is portable (GPU only when `nvidia-smi` exists, GUI/drives mounted only when present, extra mounts via `EXTRA_MOUNTS`).

### Features

#### Instructions & Rules
- **CLAUDE.md** — Instructions for Claude Code: Opus (1M context) meta-rules (parallel-load for cross-experiment synthesis), competition onboarding checklist (7 items), training code rules, fold design, error analysis, submission workflow (Kaggle / prediction-file / Docker)
- **KAGGLE_DIRECTION.md** — Competition-specific settings + design intent (safe + bold, fold design, preprocessing, metric guidelines). Filename is historical; content applies to any platform

#### Custom Agents (`.claude/agents/`)
| Agent | Model | Purpose |
|---|---|---|
| competition-strategist | opus | Cross-experiment synthesis (loads all daily reports + SESSION_NOTES + claudeSummary). Maximizes 1M context |
| code-reviewer | opus | ML/DL code quality review. Catches cross-file leakage, metric bugs, broken checkpoints |
| submission-validator | sonnet | Pre-submission validation (Kaggle CSV / prediction zip / Docker) |
| kaggle-researcher | sonnet | Paper, similar competition, and discussion research (Kaggle and non-Kaggle platforms) |
| data-analyst | sonnet | EDA, visualization, feature analysis |

**Model selection policy**: `opus` for tasks that require deep reading (leakage, synthesis); `sonnet` for procedural breadth (research, EDA, format checks).

#### Skills (`.claude/skills/`)
| Skill | Description |
|---|---|
| `/onboard [URL]` | Walk through the 7-item competition onboarding checklist; save to `survey/competition/overview.md` |
| `/exp-new <name> [--human]` | Scaffold a new experiment folder from `reference/` with `SESSION_NOTES.md` and `run.sh` |
| `/daily-report` | Create today's daily report carrying over from yesterday's |
| `/submit-check <path>` | Pre-submission validation; delegates to submission-validator agent |
| `/strategy [focus]` | Cross-experiment synthesis via competition-strategist agent. Use weekly or at inflection points |
| `/survey-papers [keyword]` | Paper/solution research (`context: fork` keeps main context clean) |
| `/wiki [add\|find\|promote\|consolidate]` | Accumulate/search/consolidate competition knowledge in the `knowledge/` stock layer (atomic pages + INDEX). Distill from the daily-report flow |

#### Tools (`tools/`)
| File | Description |
|---|---|
| `kaggle_elapsed_time.py` | Submission status monitoring & elapsed time |
| `kaggle_upload.sh` | Folder upload to Kaggle Dataset with versioning |
| `kaggle_code_competition_submission.md` | End-to-end flow for Kaggle Code Competitions (Dataset + Notebook + manual submit). Templates for `kernel-metadata.json`, `dataset-metadata.json`, `upload.sh`, common pitfalls |
| `runpod/` | External-GPU (RunPod) ops guide, verified on real hardware (runpodctl 2.3.0): connect / key handling via Secrets / cost guards / storage 3-tier (Kaggle = source of truth, Network Volume = scratch). Scripts: `runpod_ops.py`, `smoke_test.sh`, `startup.sh`, `.runpod.env.example`. Copy the folder into any repo to port it |

#### Reference Code (`reference/`)
- **2.5D segmentation template** based on PyTorch Lightning + timm + smp
- Based on [yu4u/kaggle-czii-4th](https://github.com/yu4u/kaggle-czii-4th)

#### Experiment Management
- **Folder naming**: Claude `expA00_xxx`, Human `exp200_xxx`
- **SESSION_NOTES.md**: Required in each experiment folder
- **Daily reports** (`daily_reports/YYYYMMDD.md`): Central record; append insights as they emerge
- **Submission history** (`submit/SUBMISSIONS.md`): CV/LB scores and parameters for all submissions
- **claudeSummary.md**: Cross-experiment insights and best score history

#### Training Code Rules
- AMP (Mixed Precision) always ON
- Checkpoint resume mandatory
- Seed fixed
- Hyperparameters in config (no hardcoding)
- `logging` module for output (`print` prohibited)
- All outputs to `results/{experiment_name}/foldN/`

### Repository Structure

```
./
├── CLAUDE.md                         # Claude Code instructions
├── KAGGLE_DIRECTION.md               # Competition settings + design intent
├── claudeSummary.md                  # Cross-experiment insights
├── myMemo.md                         # Personal notes
├── LICENSE                           # MIT License
├── setup.sh                          # Language setup script
├── rundocker.sh                      # Launch the closed Docker env (portable)
├── docker/                           # Closed-env image (Dockerfile + build.sh)
├── locales/                          # Language files
│   ├── ja/                           # Japanese
│   └── en/                           # English
├── .claude/
│   ├── agents/                       # Custom Agents (5 types)
│   └── skills/                       # Skills (7 commands)
├── .github/
│   └── workflows/                    # CI (locale sync check)
├── reference/                        # Reference code (2.5D Seg)
├── tools/
│   ├── kaggle_elapsed_time.py        # Submission monitoring
│   ├── kaggle_upload.sh              # Dataset upload
│   ├── kaggle_code_competition_submission.md  # Code Competition submission guide
│   ├── git-hooks/                    # Secret-blocking pre-commit hook (+ install.sh)
│   └── runpod/                       # External-GPU (RunPod) ops guide + scripts
├── submit/
│   └── SUBMISSIONS.md                # Submission history
├── datasets/                         # Competition data
├── survey/                           # Research (competition overview / discussions / papers)
│   ├── competition/                  # Competition overview (/onboard → overview.md)
│   ├── discussion/
│   └── papers/
├── knowledge/                        # Knowledge wiki (stock layer)
│   ├── INDEX.md                      #   retrieval index (load this first)
│   ├── technique/ data/ error/ decision/
│   └── _template.md
├── daily_reports/                    # Daily reports (flow layer)
└── workspace/                        # Experiment folders
    ├── fold/                         # Shared fold assignments (generate_folds.py + {version}/folds.csv)
    └── expXXX... / expA00...
```

---

## 日本語

このリポジトリは **データ分析コンペ用の実験管理テンプレート**です。
Claude Code を前提に、**データ取得 → EDA → 調査（論文/類似コンペ） → 実験（exp管理） → 提出**までを、再現性高く回すためのルールと作業手順をまとめています。

**Kaggle だけでなく、grand-challenge.org / CodaBench / 独自プラットフォームなど Kaggle 以外のコンペにも対応**。提出形式は CSV / 予測ファイル zip / Docker コンテナの 3 タイプをカバーします。

詳細はこの記事に記載してあります。[リンク](https://zenn.dev/sugupoko/articles/1c985219823589)

### 前提環境

- Linux / WSL2
- Python 3.10+
- [Claude Code](https://claude.com/claude-code) CLI
- Docker（任意。閉じた Docker 環境で動かす場合のみ）

### 既知の制約

- **最終提出は手動** — 提出物の生成・検証までは Claude が行うが、実際のアップロードや "Submit to Competition" の操作は必ずユーザーが行う
- **ディスカッション取得はスクレイピング依存** — 公式 Kaggle API にディスカッション取得機能がないため、`survey/discussion/` は Playwright によるスクレイピングで運用する（リクエスト間 2-3 秒のマナー厳守）
- **モデルファイルは git 管理外** — `model/` や `*.ckpt` / `*.pth` はサイズの都合で gitignore 済み。重みの移動は Kaggle Dataset や外部ストレージで行う
- **一部ドキュメントは日本語のみ** — `tools/` 配下のガイドと `reference/README.md`（ローカライズ対象の境界は English 節の Language Setup を参照）

### クイックスタート
1. このリポジトリをfork
2. `bash setup.sh ja` で日本語セットアップ（pre-commit フックも自動有効化）。英語に切り替える場合は `bash setup.sh en`
3. KAGGLE_DIRECTION.md に対象コンペURLを記入
4. Claude Code で作業開始

### 最初のセッションの流れ

```text
/onboard <コンペURL>           # 7項目チェックリスト → survey/competition/overview.md
/daily-report                  # 今日の日報を作成
# fold 設計: workspace/fold/generate_folds.py → workspace/fold/{version}/folds.csv
/exp-new baseline              # reference/ から workspace/expA00_baseline を作成
bash workspace/expA00_baseline/run.sh       # 学習
/submit-check submit/v001_expA00_baseline   # 提出前検証
```

#### 閉じた Docker 環境で動かす（任意）

```bash
bash docker/build.sh    # "claude" イメージをビルド（PyTorch + ML スタック + Claude Code CLI）
bash rundocker.sh       # リポジトリをマウントしてコンテナ起動
```

### 機能一覧

#### 指示書・ルール
- **CLAUDE.md** — Claude Code への指示書。Opus (1M context) 用のメタルール（横断分析時に並列ロードしていい指針）、コンペ開始時の把握フェーズ（7項目）、学習コードの鉄則、Fold設計、エラー分析、提出ワークフロー（Kaggle / 予測ファイル / Docker）
- **KAGGLE_DIRECTION.md** — コンペ固有の設定 + 設計意図（堅実＋爆発、Fold設計、前処理、評価指標の判断指針）。ファイル名は歴史的経緯で Kaggle のままだが、中身は汎用の設計原則

#### Custom Agents（`.claude/agents/`）
| エージェント | モデル | 用途 |
|---|---|---|
| competition-strategist | opus | 横断 synthesis（全 daily_report + SESSION_NOTES + claudeSummary を一括ロード）。1M ctx を最大活用 |
| code-reviewer | opus | ML/DLコード品質レビュー。リーク・指標バグ・チェックポイント破綻を横断検出 |
| submission-validator | sonnet | 提出物の事前検証（Kaggle CSV / 予測 zip / Docker） |
| kaggle-researcher | sonnet | 論文・類似コンペ解法・ディスカッション調査（Kaggle・非Kaggle両対応） |
| data-analyst | sonnet | EDA・可視化・特徴量分析 |

**モデル選定方針**: 「深く読まないと気付けない」系は `opus`（リーク検出・横断 synthesis）。「広く浅く回す」系は `sonnet`（調査・EDA・形式チェック）。

#### Skills（`.claude/skills/`）
| スキル | 説明 |
|---|---|
| `/onboard [URL]` | コンペ開始時の7項目チェックリストを対話的に埋め、`survey/competition/overview.md` に保存 |
| `/exp-new <name> [--human]` | `reference/` から雛形コピーで新しい実験フォルダ + `SESSION_NOTES.md` + `run.sh` を生成 |
| `/daily-report` | 今日の日報を前日から引き継いで作成 |
| `/submit-check <path>` | 提出物の事前検証（submission-validator agent に委譲） |
| `/strategy [追加観点]` | competition-strategist agent で横断 synthesis。週1回や局面の変わり目で |
| `/survey-papers [キーワード]` | 論文・解法調査（`context: fork` でメインコンテキストを汚さない） |
| `/wiki [add\|find\|promote\|consolidate]` | コンペ知識を `knowledge/` ストック層（原子ページ + INDEX）に蓄積・検索・整理。daily_report のフローから蒸留して昇格 |

#### ツール（`tools/`）
| ファイル | 説明 |
|---|---|
| `kaggle_elapsed_time.py` | 提出状況の監視・経過時間計測 |
| `kaggle_upload.sh` | フォルダを Kaggle Dataset にアップロード・バージョン管理 |
| `kaggle_code_competition_submission.md` | Kaggle Code Competition 用の提出フロー全文（Dataset 作成 → Notebook push → 手動 submit）。`kernel-metadata.json` / `dataset-metadata.json` / `upload.sh` の雛形とハマりどころ集 |
| `runpod/` | 外部GPU（RunPod）の運用ガイド（実機 runpodctl 2.3.0 で検証）。接続 / Secrets による鍵運用 / コスト自動停止 / ストレージ3層（Kaggle=真実・Volume=scratch）。スクリプト: `runpod_ops.py` / `smoke_test.sh` / `startup.sh` / `.runpod.env.example`。フォルダごとコピーで他リポジトリへ移植可 |

#### リファレンスコード（`reference/`）
- PyTorch Lightning + timm + smp ベースの **2.5Dセグメンテーションテンプレート**
- [yu4u/kaggle-czii-4th](https://github.com/yu4u/kaggle-czii-4th) ベース

#### 実験管理
- **実験フォルダ命名規則**: Claude用 `expA00_xxx`、人間用 `exp200_xxx`
- **SESSION_NOTES.md**: 各実験フォルダに必須。仮説・結果・次アクションを記録
- **日報** (`daily_reports/YYYYMMDD.md`): 全記録の中心。知見が出たら都度追記
- **提出履歴** (`submit/SUBMISSIONS.md`): 全提出のCV/LBスコア・パラメータを記録
- **claudeSummary.md**: 実験横断の知見・ベストスコア履歴を集約

#### 学習コードの鉄則
- AMP (Mixed Precision) 常にON
- チェックポイント再開必須
- シード固定
- ハイパーパラメータは config 管理（ハードコーディング禁止）
- `logging` モジュールで出力（`print` 禁止）
- 全出力は `results/{experiment_name}/foldN/` に集約

### リポジトリ構造

```
./
├── CLAUDE.md                         # Claude Code 指示書
├── KAGGLE_DIRECTION.md               # コンペ固有設定 + 設計意図
├── claudeSummary.md                  # 実験横断の知見集約
├── myMemo.md                         # 個人メモ
├── LICENSE                           # MIT License
├── setup.sh                          # 言語設定スクリプト
├── rundocker.sh                      # 閉じた Docker 環境を起動（配布対応）
├── docker/                           # 閉じた環境イメージ (Dockerfile + build.sh)
├── locales/                          # 言語ファイル
│   ├── ja/                           # 日本語
│   └── en/                           # English
├── .claude/
│   ├── agents/                       # Custom Agents (5種)
│   └── skills/                       # Skills (7コマンド)
├── .github/
│   └── workflows/                    # CI（ロケール同期チェック）
├── reference/                        # リファレンスコード (2.5D Seg)
├── tools/
│   ├── kaggle_elapsed_time.py        # 提出監視
│   ├── kaggle_upload.sh              # Dataset アップロード
│   ├── kaggle_code_competition_submission.md  # Code Competition 提出ガイド
│   ├── git-hooks/                    # 秘密混入を止める pre-commit フック (+ install.sh)
│   └── runpod/                       # 外部GPU(RunPod)運用ガイド + スクリプト
├── submit/
│   └── SUBMISSIONS.md                # 提出履歴
├── datasets/                         # コンペデータ
├── survey/                           # 調査（コンペ概要・ディスカッション・論文）
│   ├── competition/                  # コンペ概要（/onboard の出力 overview.md）
│   ├── discussion/
│   └── papers/
├── knowledge/                        # ナレッジWiki（ストック層）
│   ├── INDEX.md                      #   検索用目次（まずこれを見る）
│   ├── technique/ data/ error/ decision/
│   └── _template.md
├── daily_reports/                    # 日報（フロー層）
└── workspace/                        # 実験フォルダ
    ├── fold/                         # fold割り当ての共有（generate_folds.py + {version}/folds.csv）
    └── expXXX... / expA00...
```

### 実験フォルダ命名規則

* **Claude用**: `workspace/exp(アルファベット)(数字2桁)_(実験名)`
  * 例: `workspace/expA00_baseline`
  * 大きく方針が変わる時だけ番号を増やす（微調整は同じexp内）
* **人間用**: `workspace/exp(数字3桁)_(実験名)`
  * 例: `workspace/exp200_try_unet`

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v2.7.1 | 2026-06-18 | **Common rule: don't swallow errors.** Add an "Error-Handling Principles (Don't Swallow Errors)" section to CLAUDE.md — a careless `try/except` makes code "look like it works but is actually broken," hiding bugs; default to fail-fast, and catch only when recoverable + specific exception type + logged. `code-reviewer` agent gains a swallowed-exception check so the rule is enforced, not just stated. Synced across ja/en |
| v2.7.0 | 2026-06-17 | **Simulation-competition support** (agent-vs-agent: Lux AI / ConnectX / Halite …). Add `reference_sim/` — a runnable reference (heuristic + alpha-beta search agents, a local match-evaluation harness with opponent-pool versioning as the "fold" analogue, a self-contained `submit_agent.py`, and a cwd-safe `run_local.sh` that auto-installs deps), worked on ConnectX via `kaggle_environments`. Extend the docs/skills/agents: onboarding gains simulation items (engine/observation/action/episode/rating/agent-I/F), a simulation phase guard (heuristic → search/RL → policy-ensemble), the fold section notes the opponent-pool analogue, a 4th submission track **(D) Simulation agent**, and `/submit-check` + `submission-validator` gain agent checks (self-contained / full-episode completion / timeout / illegal-move / stray-print). Synced across ja/en |
| v2.6.1 | 2026-06-13 | **RunPod multi-pod / detached-run ops lessons** (from real practice): README §11 (1 pod = 1 launch — re-launching stacks processes → GPU contention SIGKILL; full detach via `setsid CMD >log 2>&1 </dev/null &`; verify startup with a separate ssh call; `while-read` loops eat ssh stdin; `pkill -f` self-matches its own cmdline), reconcile the Kaggle-zip trap in §9.5 (extract behavior is inconsistent → auto-detect the data root; add real-username owner-id, post-create 404 polling, and `HF_TOKEN` stall traps), add a generic `tools/runpod/pod_run.sh` per-job training entry (Kaggle fetch → auto-detected extraction → train → `/workspace/out_<TAG>`) |
| v2.6.0 | 2026-06-10 | **Review-based overhaul**: restore the missing `reference/` config, add missing executable bits on scripts, harden the secret-blocking pre-commit hook, safer RunPod ops defaults, migrate the session hook from Stop to **SessionEnd** (`$CLAUDE_PROJECT_DIR`-based paths), add locale-sync CI under `.github/workflows/`, unify the competition overview under `survey/competition/`, document `workspace/fold/generate_folds.py`, and refresh the README (structure / requirements / first-session flow / License) |
| v2.5.1 | 2026-06-07 | Add **secret-blocking git pre-commit hook** (idiot-proofing) at `tools/git-hooks/`: blocks commits touching credential paths (`.kaggle/`, `kaggle.json`, `.credentials.json`, SSH keys, `*.env`, …) or containing token patterns (PRIVATE KEY / AWS / GitHub PAT / Hugging Face / Google API / Slack); `*.example` is exempt, binary/>1MB skipped, NUL-safe for spaced/non-ASCII filenames; bypass via `ALLOW_SECRETS=1` / `--no-verify`. Distributed via `core.hooksPath` (tracked `install.sh`; `setup.sh` auto-enables; per-clone activation required). Also extend `rundocker.sh`: pass `HF_TOKEN` from `~/.hf_token`, and selectable `KAGGLE_INSTALL=skip/always/no` |
| v2.5.0 | 2026-06-06 | Add **`docker/` closed-environment image**: `Dockerfile` (PyTorch 2.7.1 / CUDA 12.8 base + ML stack + Claude Code CLI, baked into one distributable image; `UID`/`GID` parametrized via build args) and beginner-friendly `build.sh` (inherits host `UID`/`GID` to avoid bind-mount ownership mismatches). Make `rundocker.sh` portable for distribution: `--gpus all` only when `nvidia-smi` exists (CPU-only hosts still launch), GUI (X11/WSLg) mounts only when present, drives auto-detected from `/mnt/<letter>` or `EXTRA_MOUNTS` (drops hardcoded `/mnt/d,e,j`). Preventively harden `.gitignore` for the HOME-mount workflow (no secrets were ever tracked; this guards credential files that *would* be created once you authenticate inside the container): whitelist `.claude/` (track only `agents/` `skills/` `settings.json`, auto-ignore credentials/history Claude Code writes), and block `.kaggle/` / `kaggle.json` / SSH keys (`id_rsa`, `*.pem`, `*.key`) / `.npm/` / `.bash_history` |
| v2.4.1 | 2026-06-01 | Add **external-GPU (RunPod) ops tooling** at `tools/runpod/` (verified on runpodctl 2.3.0): connect / Secrets-based key handling / cost auto-stop / storage 3-tier (Kaggle = source of truth, Network Volume = scratch), plus `runpod_ops.py` / `smoke_test.sh` / `startup.sh` / `.runpod.env.example`. `.gitignore` protects `*.env` while keeping `*.env.example`. CLAUDE.md notes external GPU under background execution. Includes a real-hardware-verified recipe (§9.5: Kaggle dataset → RunPod model training) and confirms `{{ RUNPOD_SECRET_x }}` is NOT resolved via CLI/SDK (inject keys via scp) |
| v2.4.0 | 2026-05-31 | Add **knowledge wiki (stock layer)**: `knowledge/` with `INDEX.md` retrieval index + atomic pages (`technique/` `data/` `error/` `decision/`), new `/wiki` skill (add / find / promote / consolidate), SessionStart auto-injects `INDEX.md`. Separates flow (`daily_reports/`) from stock (distilled, reusable knowledge). Make the Opus version label version-agnostic ("Opus (1M context)"); agents keep the `model: opus` alias |
| v2.3.2 | 2026-05-13 | Add **Kaggle Code Competition** support: full submission flow guide at `tools/kaggle_code_competition_submission.md`. CLAUDE.md distinguishes CSV vs Code Competition. `submission-validator` agent gains (A') Code Competition checks. `submit/` naming convention bumped: include source exp folder (e.g., `v001_expA02_super_clone`) |
| v2.3.1 | 2026-05-03 | Add **hybrid phase guard (early / mid / late)** to prevent "premature ensemble". Time-based + milestone-based detection in `competition-strategist`. Compact phase table in CLAUDE.md (always loaded), detailed do/don't lists in KAGGLE_DIRECTION.md |
| v2.3.0 | 2026-05-02 | Designed for **Claude Opus 4.7 (1M context)**: `code-reviewer` and new `competition-strategist` agents upgraded to opus; add `submission-validator` agent; add 5 new skills (`/onboard`, `/exp-new`, `/daily-report`, `/submit-check`, `/strategy`); CLAUDE.md gets explicit "parallel-load for synthesis" guidance |
| v2.2.0 | 2026-04-11 | Support non-Kaggle platforms (grand-challenge.org / CodaBench / custom): add competition onboarding checklist (7 items) and split submission pipeline into Kaggle / prediction-file / Docker formats |
| v2.1.1 | 2026-03-20 | Change kaggle-researcher agent from haiku to sonnet |
| v2.1.0 | 2026-03-20 | Add English language support (`locales/`, `setup.sh`), bilingual README |
| v2.0.1 | 2025-12-13 | Initial public release with full experiment management template |

---

## License

[MIT License](LICENSE) © 2025 sugupoko
（MIT ライセンスです。詳細は [LICENSE](LICENSE) を参照）
