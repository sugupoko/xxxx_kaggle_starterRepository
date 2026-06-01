# Competition Experiment Template

**v2.4.1**

> Supports **Kaggle** and **non-Kaggle** competitions (grand-challenge.org, CodaBench, custom platforms).
> Designed for **Claude Opus (1M context)**.

[日本語 (default)](#日本語) | [English](#english)
　
---

## English

This repository is an **experiment management template for data science competitions**.
Built for Claude Code, it provides rules and workflows for the full pipeline: **data acquisition → EDA → research (papers/similar competitions) → experiments (exp management) → submission**, with high reproducibility.

Supports **Kaggle** and **non-Kaggle** platforms (grand-challenge.org, CodaBench, custom sites). Submission pipelines cover CSV, prediction-file (zip), and Docker container formats.

### Quick Start

```bash
# 1. Fork this repository

# 2. Set language to English
./setup.sh en

# 3. Set target competition URL in KAGGLE_DIRECTION.md

# 4. Start working with Claude Code
```

### Language Setup

This template supports **Japanese** and **English**. Run the setup script to switch:

```bash
./setup.sh en   # English
./setup.sh ja   # Japanese (default)
```

This updates: `CLAUDE.md`, `KAGGLE_DIRECTION.md`, agent definitions, skill definitions, and templates.

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
├── setup.sh                          # Language setup script
├── locales/                          # Language files
│   ├── ja/                           # Japanese
│   └── en/                           # English
├── .claude/
│   ├── agents/                       # Custom Agents (5 types)
│   └── skills/                       # Skills (7 commands)
├── reference/                        # Reference code (2.5D Seg)
├── tools/
│   ├── kaggle_elapsed_time.py        # Submission monitoring
│   ├── kaggle_upload.sh              # Dataset upload
│   └── runpod/                       # External-GPU (RunPod) ops guide + scripts
├── submit/
│   └── SUBMISSIONS.md                # Submission history
├── datasets/                         # Competition data
├── competition/                      # EDA & competition overview
├── survey/                           # Paper & discussion research
│   ├── discussion/
│   └── papers/
├── knowledge/                        # Knowledge wiki (stock layer)
│   ├── INDEX.md                      #   retrieval index (load this first)
│   ├── technique/ data/ error/ decision/
│   └── _template.md
├── daily_reports/                    # Daily reports (flow layer)
└── workspace/                        # Experiment folders
    └── expXXX... / expA00...
```

---

## 日本語

このリポジトリは **データ分析コンペ用の実験管理テンプレート**です。
Claude Code を前提に、**データ取得 → EDA → 調査（論文/類似コンペ） → 実験（exp管理） → 提出**までを、再現性高く回すためのルールと作業手順をまとめています。

**Kaggle だけでなく、grand-challenge.org / CodaBench / 独自プラットフォームなど Kaggle 以外のコンペにも対応**。提出形式は CSV / 予測ファイル zip / Docker コンテナの 3 タイプをカバーします。

詳細はこの記事に記載してあります。[リンク](https://zenn.dev/sugupoko/articles/1c985219823589)

### クイックスタート
1. このリポジトリをfork
2. KAGGLE_DIRECTION.md に対象コンペURLを記入
3. Claude Code で作業開始

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
├── setup.sh                          # 言語設定スクリプト
├── locales/                          # 言語ファイル
│   ├── ja/                           # 日本語
│   └── en/                           # English
├── .claude/
│   ├── agents/                       # Custom Agents (5種)
│   └── skills/                       # Skills (7コマンド)
├── reference/                        # リファレンスコード (2.5D Seg)
├── tools/
│   ├── kaggle_elapsed_time.py        # 提出監視
│   ├── kaggle_upload.sh              # Dataset アップロード
│   └── runpod/                       # 外部GPU(RunPod)運用ガイド + スクリプト
├── submit/
│   └── SUBMISSIONS.md                # 提出履歴
├── datasets/                         # コンペデータ
├── competition/                      # EDA・コンペ概要
├── survey/                           # 論文・ディスカッション調査
│   ├── discussion/
│   └── papers/
├── knowledge/                        # ナレッジWiki（ストック層）
│   ├── INDEX.md                      #   検索用目次（まずこれを見る）
│   ├── technique/ data/ error/ decision/
│   └── _template.md
├── daily_reports/                    # 日報（フロー層）
└── workspace/                        # 実験フォルダ
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
| v2.4.1 | 2026-06-01 | Add **external-GPU (RunPod) ops tooling** at `tools/runpod/` (verified on runpodctl 2.3.0): connect / Secrets-based key handling / cost auto-stop / storage 3-tier (Kaggle = source of truth, Network Volume = scratch), plus `runpod_ops.py` / `smoke_test.sh` / `startup.sh` / `.runpod.env.example`. `.gitignore` protects `*.env` while keeping `*.env.example`. CLAUDE.md notes external GPU under background execution |
| v2.4.0 | 2026-05-31 | Add **knowledge wiki (stock layer)**: `knowledge/` with `INDEX.md` retrieval index + atomic pages (`technique/` `data/` `error/` `decision/`), new `/wiki` skill (add / find / promote / consolidate), SessionStart auto-injects `INDEX.md`. Separates flow (`daily_reports/`) from stock (distilled, reusable knowledge). Make the Opus version label version-agnostic ("Opus (1M context)"); agents keep the `model: opus` alias |
| v2.3.2 | 2026-05-13 | Add **Kaggle Code Competition** support: full submission flow guide at `tools/kaggle_code_competition_submission.md`. CLAUDE.md distinguishes CSV vs Code Competition. `submission-validator` agent gains (A') Code Competition checks. `submit/` naming convention bumped: include source exp folder (e.g., `v001_expA02_super_clone`) |
| v2.3.1 | 2026-05-03 | Add **hybrid phase guard (early / mid / late)** to prevent "premature ensemble". Time-based + milestone-based detection in `competition-strategist`. Compact phase table in CLAUDE.md (always loaded), detailed do/don't lists in KAGGLE_DIRECTION.md |
| v2.3.0 | 2026-05-02 | Designed for **Claude Opus 4.7 (1M context)**: `code-reviewer` and new `competition-strategist` agents upgraded to opus; add `submission-validator` agent; add 5 new skills (`/onboard`, `/exp-new`, `/daily-report`, `/submit-check`, `/strategy`); CLAUDE.md gets explicit "parallel-load for synthesis" guidance |
| v2.2.0 | 2026-04-11 | Support non-Kaggle platforms (grand-challenge.org / CodaBench / custom): add competition onboarding checklist (7 items) and split submission pipeline into Kaggle / prediction-file / Docker formats |
| v2.1.1 | 2026-03-20 | Change kaggle-researcher agent from haiku to sonnet |
| v2.1.0 | 2026-03-20 | Add English language support (`locales/`, `setup.sh`), bilingual README |
| v2.0.1 | - | Initial public release with full experiment management template |
