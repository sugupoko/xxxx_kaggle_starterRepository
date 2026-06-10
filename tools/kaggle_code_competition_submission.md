# Kaggle Code Competition 提出フロー（汎用ガイド）

`kaggle` CLI だけで **Dataset 作成 → Notebook push → 提出** までを再現可能な手順にまとめる。
任意の Kaggle Code Competition プロジェクトで使い回せる構成。

## 0. Code Competition と CSV Competition の違い

| 種別 | 提出方法 | CLI で完結するか |
|---|---|---|
| **CSV Competition** (Submission) | `submission.csv` を直接 upload | `kaggle competitions submit -c <comp> -f sub.csv -m "..."` で完結 |
| **Code Competition** (Notebook) | Kaggle 上で Notebook を実行 → そこから "Submit to Competition" | **手動ステップが残る**（最後の "Submit" ボタン）。upload までは CLI 可 |

このガイドは **Code Competition** 向け。CSV Competition なら `kaggle competitions submit` 一発で済むのでこのガイドは不要。

判定方法:
- Rules ページに "Submissions are made from Kaggle Notebooks" 等の記述
- 公開上位 Notebook が `/kaggle/input/competitions/<comp>/` を読み `/kaggle/working/submission.csv` を出力するパターン
- `kaggle competitions submit` を実行して "Code Competition" エラーが返る

## 1. アーキテクチャ（全体像）

```
ローカル
├── workspace/<exp>/                  ← 学習スクリプト & 出力
│   └── results/<exp>/
│       ├── models/*.txt              ← 学習済みモデル (LightGBM Booster, PyTorch ckpt, etc.)
│       ├── postproc.json             ← 後処理ハイパーパラメータ
│       └── cv_summary.json           ← CV スコア記録
└── submit/v00X_<name>/
    ├── inference_notebook.ipynb      ← Kaggle で実行する notebook
    ├── inference_notebook.py         ← jupytext で .ipynb と同期する Python 表現
    ├── kernel-metadata.json          ← Notebook の Kaggle メタ
    ├── dataset-metadata.json         ← Dataset の Kaggle メタ
    ├── upload.sh                     ← 1コマンドで Dataset 作成 + Notebook push
    └── kaggle_dataset/               ← Dataset アップロード対象（.gitignore）
        ├── models/*.txt
        ├── postproc.json
        └── dataset-metadata.json (コピー)
                ↓ kaggle datasets create / version
                ↓
Kaggle 上
├── Dataset (private)                  ← /kaggle/input/<dataset-slug>/
└── Notebook (private)                 ← attach: dataset + competition data
       ↓ ユーザーが Save & Run All（手動）
       ↓ Notebook が /kaggle/working/submission.csv 生成
       ↓ ユーザーが "Submit to Competition"（手動）
LB
```

## 2. ファイルテンプレート

### 2.1 `dataset-metadata.json`

```json
{
  "title": "<COMP> v001 <exp名> (single model)",
  "id": "<kaggle-username>/<slug>",
  "subtitle": "CV=X.XX (5-fold)",
  "description": "v001 <exp名> (single model, no ensemble). 5-fold CV = X.XX. fold v1, N train samples. Source: workspace/<exp名>/results/<experiment_name>.",
  "isPrivate": true,
  "licenses": [{"name": "CC0-1.0"}],
  "keywords": ["<task-keyword>"],
  "collaborators": [],
  "data": []
}
```

注意:
- `id` のスラッグは小文字英数とハイフンのみ
- 一部のキーワード（コンペ名そのもの等）は Kaggle 側で reject されるが、Dataset 自体は問題なく作成される
- `isPrivate: true` 推奨。public にすると他チームに物理的にコピーされる

### 2.2 `kernel-metadata.json`

```json
{
  "id": "<kaggle-username>/<notebook-slug>",
  "title": "v001 <exp名> inference",
  "code_file": "inference_notebook.ipynb",
  "language": "python",
  "kernel_type": "notebook",
  "is_private": true,
  "enable_gpu": false,
  "enable_internet": false,
  "dataset_sources": ["<kaggle-username>/<dataset-slug>"],
  "competition_sources": ["<competition-slug>"],
  "kernel_sources": []
}
```

注意:
- `dataset_sources` に Dataset を列挙すると、Kaggle 側で自動 attach される。これが本ワークフローの肝
- `competition_sources` に競技スラッグを書くと、`/kaggle/input/<competition-slug>/` に競技データが自動マウントされる
- `enable_internet: false` は Code Competition 必須（`pip install` 不可）
- `enable_gpu: true` にすると T4×2（時間切れリスクあり）。`false` なら CPU のみ
- タイトル変更時は slug が変わる: タイトルに CV スコアを入れたい場合は、初回 push 後にタイトル更新 → 2 回目の push で slug が変わる **ことに注意**

### 2.3 `inference_notebook.py` の骨格

```python
"""
Source: workspace/<exp>/
CV: X.XX (5-fold OOF)
"""
from pathlib import Path

# ── 1. パス解決（Kaggle 環境を自動検出）
def _find_competition_dir() -> Path:
    for p in [Path("/kaggle/input/<comp-slug>"),
              Path("/kaggle/input/competitions/<comp-slug>")]:
        if (p / "train").exists():
            return p
    raise FileNotFoundError("competition data not found")

def _find_model_dir() -> Path:
    candidates = [Path("/kaggle/input/<dataset-slug>")]
    for p in candidates:
        if (p / "models").exists():
            return p
    raise FileNotFoundError("model dataset not found")

DATA = _find_competition_dir()
MODEL_DIR = _find_model_dir()
OUT = Path("/kaggle/working/submission.csv")

# ── 2. 特徴量構築 (training と完全に同じコード) ...
# ── 3. fold モデル読み込み + 推論 ...
# ── 4. 後処理 + submission.csv 出力 ...

# 最後に assert で形式検証
assert len(sub) == EXPECTED_ROWS
assert sub["target_col"].notna().all()
sub.to_csv(OUT, index=False)
```

#### jupytext で .py ↔ .ipynb 同期

```bash
pip install jupytext
jupytext --to ipynb inference_notebook.py    # .py → .ipynb 生成
jupytext --sync inference_notebook.py        # 両方向同期
```

`# %% [markdown]` / `# %%` で cell 分割。`.py` の方を Git 管理して `.ipynb` は派生扱いするのが綺麗。

### 2.4 `upload.sh`（1 コマンド全自動）

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

EXP_RESULTS_DIR="../../workspace/<exp>/results/<exp_subdir>"

# 1) ローカル artifact → kaggle_dataset/ にコピー
mkdir -p kaggle_dataset/models
cp "$EXP_RESULTS_DIR/models/"*.txt kaggle_dataset/models/
cp "$EXP_RESULTS_DIR/postproc.json" kaggle_dataset/
cp "$EXP_RESULTS_DIR/cv_summary.json" kaggle_dataset/

# 2) CV スコアを抽出して description に埋め込む（どのウェイトか分かるように）
OOF=$(python -c "import json; print(round(json.load(open('$EXP_RESULTS_DIR/cv_summary.json'))['best_abs_oof_rmse'], 4))")
echo "  CV: ABS_OOF=$OOF"

# 3) dataset-metadata.json を kaggle_dataset/ にコピーしつつ description を上書き
python - <<PY
import json
m = json.load(open("dataset-metadata.json"))
m["description"] = f"CV abs OOF={$OOF}ft. <experiment description>"
m["subtitle"] = f"OOF={$OOF}ft"
json.dump(m, open("kaggle_dataset/dataset-metadata.json", "w"), ensure_ascii=False, indent=2)
PY

# 4) Dataset 作成 or バージョン更新
DATASET_SLUG="<username>/<dataset-slug>"
if kaggle datasets status "$DATASET_SLUG" 2>/dev/null | grep -q "ready"; then
  kaggle datasets version -p kaggle_dataset -m "v00X OOF=$OOF"
else
  kaggle datasets create -p kaggle_dataset --dir-mode zip
fi

# 5) Notebook の title に CV スコアを反映 → push
python - <<PY
import json
m = json.load(open("kernel-metadata.json"))
m["title"] = f"v00X <name> (OOF=$OOFft)"
json.dump(m, open("kernel-metadata.json", "w"), ensure_ascii=False, indent=2)
PY
kaggle kernels push -p .

cat <<EOF
NEXT STEPS (manual):
  1. Open notebook URL
  2. Save & Run All  → submission.csv が生成
  3. Submit to Competition
EOF
```

## 3. 提出手順（毎回のループ）

```bash
# 0. 学習（既存）
bash workspace/<exp>/run.sh

# 1. submit フォルダを v00X 用に作成（前回 v 番から複製）
cp -r submit/v001_<prev> submit/v002_<new>
# slug を v002 系に書き換え（kernel-metadata.json / dataset-metadata.json 内）

# 2. アップロード
bash submit/v002_<new>/upload.sh

# 3. （手動）Kaggle UI で Run All → Submit to Competition

# 4. LB が出たら記録
# submit/SUBMISSIONS.md に行を追加
```

## 4. ハマりやすい注意点

| 罠 | 症状 | 対策 |
|---|---|---|
| Dataset processing 待ち | Notebook 実行時に `/kaggle/input/<slug>/` が空 | upload 後 **1〜2 分** 待ってから Run。`kaggle datasets status` で `ready` 確認 |
| タイトル変更で slug 変わる | URL が変わる、過去版を再利用不可 | 初回 push 時に最終形のタイトルにする。CV スコア入れたいなら `upload.sh` が自動で行うのが楽 |
| `enable_internet: false` で pip install できない | `ModuleNotFoundError` | Kaggle に最初から入っている library のみ使う（numpy/pandas/scipy/sklearn/lightgbm/numba/torch 等） |
| `kernel_sources` 経由の import が解決しない | `ImportError` | コードを 1 notebook に inline する（self-contained） |
| `competition_sources` に書いた competition で auth エラー | `403 Forbidden` | Kaggle UI から競技に参加（Rules accept）してから push |
| Dataset が `dir-mode zip` だと中身がアーカイブ化されて読みにくい | path が `/kaggle/input/<slug>/<file>.zip` | `--dir-mode tar` or 省略（推奨）で平置きに |
| competition slug が分からない | - | URL の `/competitions/<slug>` 部分。または `kaggle competitions list -s <keyword>` |
| ユーザー名 | - | `cat ~/.kaggle/kaggle.json` |

## 5. ベストプラクティス

### 5.1 dataset/kernel の title に CV スコアを埋める

複数バージョンを upload したとき、Kaggle UI 上で**どのウェイトか一目で分かる**ようにする。

```
"title": "v003 <exp名> (CV=X.XX)"
```

`upload.sh` 内で CV スコアを cv_summary.json から抽出して title に流す。

### 5.2 提出履歴を `submit/SUBMISSIONS.md` に必ず追記

```markdown
| 日付 | バージョン | 実験フォルダ | モデル元パス | Fold定義 | 学習データ | パラメータ | 前処理 | CV | Public LB | Private LB | 備考 |
```

LB の数字は手動で埋める。これがないと「どのモデルで何のスコア」が分からなくなる。

### 5.3 inference notebook の最後に必ず形式検証

```python
assert len(sub) == EXPECTED_ROWS, f"row count mismatch: {len(sub)}"
assert sub["target_col"].notna().all(), "NaN in submission"
assert sub["target_col"].between(LOW, HIGH).all(), "value out of range"
```

Kaggle 上で実行時、これらが落ちれば即気付く。

### 5.4 git に commit するもの / しないもの

| commit する | commit しない |
|---|---|
| `inference_notebook.py` (jupytext source) | `inference_notebook.ipynb` (派生) |
| `kernel-metadata.json` | `kaggle_dataset/` |
| `dataset-metadata.json` | `models/`, `*.txt`, `*.ckpt`, `*.pkl` |
| `upload.sh` | `submission.csv` |
| `README.md` | |

`.gitignore` に以下を入れる:
```
kaggle_dataset/
model/
*.ckpt
*.pkl
*.txt
submission.csv
```

ただし `*.txt` は要件次第（lightgbm の booster は .txt 拡張子なので、コード `.py` の .txt 等と混同しないように `submit/v00X/kaggle_dataset/**/*.txt` のような限定 ignore が安全）。

## 6. 認証セットアップ（初回のみ）

```bash
# 1. https://www.kaggle.com/<username>/account から API Token を取得 → kaggle.json
mkdir -p ~/.kaggle
mv ~/Downloads/kaggle.json ~/.kaggle/
chmod 600 ~/.kaggle/kaggle.json

# 2. CLI 動作確認
pip install -U kaggle
kaggle competitions list      # 何か返ってくれば OK
```

## 7. 関連 CLI コマンド早見表

```bash
# Datasets
kaggle datasets create -p <folder> --dir-mode zip|tar|skip
kaggle datasets version -p <folder> -m "<message>"
kaggle datasets status <username>/<slug>
kaggle datasets list -s <keyword>

# Kernels (Notebooks)
kaggle kernels push -p <folder>
kaggle kernels pull <username>/<slug> -p <folder>
kaggle kernels status <username>/<slug>
kaggle kernels output <username>/<slug> -p <folder>     # 実行後の出力を取得
kaggle kernels list -s <keyword>

# Competitions
kaggle competitions list -s <keyword>
kaggle competitions files -c <slug>
kaggle competitions download -c <slug> -p <folder>
kaggle competitions submissions <slug>
# kaggle competitions submit <slug> -f <csv> -m "..."   ← CSV Competition のみ
kaggle competitions leaderboard -c <slug> --show
```

## 8. 提出フォルダの構成例（プレースホルダ）

新しく提出フォルダを作るときの雛形イメージ（`<exp名>` は元実験フォルダ名に置き換える）:

```
submit/v001_<exp名>_clone/
├── inference_notebook.py     # §2.3 の骨格をベースに、前処理〜推論〜後処理を 1 ファイルに inline（all-in-one）
├── kernel-metadata.json      # §2.2 のテンプレートを slug だけ書き換え
├── dataset-metadata.json     # §2.1 のテンプレートを slug だけ書き換え
└── upload.sh                 # §2.4 のテンプレートをパスだけ書き換え
```

- 命名は CLAUDE.md の `submit/` 規約（`v00X_<元実験フォルダ名>`）に従う
- `inference_notebook.py` は `kernel_sources` に依存せず self-contained にする（§4 参照）
