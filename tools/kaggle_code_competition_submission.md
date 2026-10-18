# Kaggle Code Competition 提出フロー（汎用ガイド）

`kaggle` CLI だけで **Dataset 作成 → Notebook push → 提出** までを再現可能な手順にまとめる。
任意の Kaggle Code Competition プロジェクトで使い回せる構成。

## 0. Code Competition と CSV Competition の違い

| 種別 | 提出方法 | CLI で完結するか |
|---|---|---|
| **CSV Competition** (Submission) | `submission.csv` を直接 upload | `kaggle competitions submit -c <comp> -f sub.csv -m "..."` で完結 |
| **Code Competition** (Notebook) | Kaggle 上で Notebook を実行 → そこから "Submit to Competition" | push〜提出まで CLI 可（`submit -k -f -v`・§8.0）。ただし**提出前に人間の OK を挟む**運用（§3.5） |

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
       ↓ kaggle kernels push の時点で実行開始（UI の Save & Run All は不要・§8.2）
       ↓ Notebook が /kaggle/working/submission.csv 生成
       ↓ 検証 → 人間の OK → 提出（UI の "Submit to Competition" か CLI・§3.5）
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
- ★**GPU 種別は `"machine_shape"` で明示する**（例: `"machine_shape": "NvidiaTeslaT4"`）。書かないと **P100 が割り当たることがあり**、
  コンペによっては Submit 自体が拒否される（`Your Notebook cannot use P100 GPUs in this competition.`）
  - 有効値は `NvidiaTeslaT4` / `NvidiaTeslaP100` / `Tpu1VmV38` など。キー名は **snake_case**（`machineShape` や `GpuT4x2` のような UI 表記は**エラーにならず黙って無視される**）
    → push 後に `kaggle kernels pull <user>/<slug> -p <dir> -m` で実際の値を必ず確認する
  - P100（sm_60）は Kaggle 既定イメージの新しい torch に対応カーネルが無いことがあり、`torch.cuda.is_available()` が True でも最初の CUDA 演算で落ちる
  - UI 側で GPU を切り替えても、次の `kernels push` でメタデータの値に戻される。**ファイル側に持たせること**
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
# ★push した時点で Kaggle 上の run が始まる（§8.2）。版番号は push 出力にしか出ないので控える（§8 参照）
kaggle kernels push -p . | tee push.log
grep -o 'Kernel version [0-9]* successfully pushed' push.log || { echo "push 失敗" >&2; exit 1; }

cat <<EOF
NEXT STEPS:
  1. tools/kaggle_submit_watch.sh で完走待ち + submission.csv 検証（提出はしない）
  2. 人間の OK
  3. tools/kaggle_submit_now.sh で提出（または UI の Submit to Competition）
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

# 3. push の時点で run 開始（UI の Save & Run All は不要・§8.2）。
#    push 出力 "Kernel version N successfully pushed." の N を控える（提出に必須・§8）

# 4. 見張り＋検証（自動・提出しない）→ 人間の OK → 提出（§3.5）
bash tools/kaggle_submit_watch.sh <user>/<kernel-slug> <comp-slug> "<message>"        # 報告して止まる
bash tools/kaggle_submit_now.sh  <user>/<kernel-slug> <comp-slug> "<message>" <N>    # OK が出てから

# 5. LB が出たら記録
# submit/SUBMISSIONS.md に行を追加
```

## 3.5 提出の操作境界 — **確認してから提出**

**方針: 検証までは自動、提出は人間の OK の後。** 全自動（完走を検知して即提出）と全手動の間を取る。

| 段階 | 誰が / 何が | 中身 |
|---|---|---|
| 1. 準備 | エージェント | Dataset upload・Notebook push（= run 開始）・版番号の控え |
| 2. 見張り＋検証 | `tools/kaggle_submit_watch.sh` | kernel 完走を待ち、出力 `submission.csv` を下の項目で形式検証して**報告。提出はしない** |
| 3. OK 出し | **人間** | 報告を見て「出してよい」と一言。**人間の手が要るのはここだけ**（Save & Run All は不要・§8.2） |
| 4. 提出＋確認 | `tools/kaggle_submit_now.sh` | `-k -f -v` で提出し、**自分の提出 ref** を特定して採点確定まで見張る |

- 報告・結果の通知は、`XANGI_CMD` と `NOTIFY_CHANNEL` の**両方が設定されているときだけ** xangi 経由でチャットへ送る（任意モジュール `tools/xangi/`・共通関数 `tools/notify.sh`）。
  未設定なら標準出力とログ（`/tmp/kaggle_submit_watch/<slug>/`）に出すだけで、スクリプトはそのまま動く
- `kaggle_submit_now.sh` は**冪等ではない**。失敗しても再実行の前に `kaggle competitions submissions <comp>` で入っていないことを確認する（多重提出防止）

### なぜ全自動にしなかったか
**大会の日次提出上限は API から取得できない**（提出コマンドの出力にしか出ない・§8.3）。
全自動だと、notebook が「完走したが中身が壊れている」ケースで**枠を 1 つ黙って溶かす**経路が残る。
提出直前に人間の目を 1 回入れることで、ここだけを塞ぐ。**それ以外に全自動を避ける理由はない**（検証自体は機械に任せる）。

### 🔴 実例: 見張りが「自分の提出」を見ていなかった
旧実装は提出後に `competition_submissions(comp)[0]` = **表の一番上（最新の提出）**を読んでいた。
提出前の先頭 ref と比較する gate はあったが、**自分より後に出た提出は除外できない**。

- **実害**: 2 本を約 10 秒差で続けて提出したら、1 本目の見張りが 2 本目の提出を掴み、**1 本目の LB として 2 本目のスコアを報告**した。
  片方の LB を他方の値で置き換え、どれが一番良いかの判定を誤らせる種類のバグ。**続けて出すと必ず起きる**
- **対策（`kaggle_submit_now.sh` に実装済み）**: 提出直後に **`description`（提出メッセージ）完全一致**で自分の ref を 1 回だけ特定して固定し、
  以後はその ref だけを読む。特定できなければ非 0 で止めて人に投げる（推測で別の ref を掴まない）。
  → **提出メッセージは毎回一意にする**（版番号・日時を入れる）
- 🔴 教訓: 「表の一番上」「status」のような**当てにならない指標を正本にしない**。提出の同一性は **ref** でしか担保できない

### 検証項目（`kaggle_submit_watch.sh` が自動で見る）
報告に必ず載せる。**1 つでも落ちたら提出せず、赤で報告する。** 項目はコンペの提出形式に合わせて調整する（以下は「ID 列 + 確率列」の例）。

| # | 項目 | 落ちる例 |
|---|---|---|
| 1 | kernel が `COMPLETE`（`ERROR` / `CANCEL` で即停止） | OOM・timeout |
| 2 | `submission.csv` が存在する | 出力パス違い |
| 3 | ヘッダが期待どおり（ID 列 + 予測列） | 列名の typo・順序違い |
| 4 | 行数 ≥ 1 かつ ID 重複なし | 空出力・取りこぼし |
| 5 | 全数値が値域内（確率なら `[0, 1]`）・NaN / Inf なし | sigmoid 忘れ・欠損補完漏れ |
| 6 | **定数列がない**（全行同じ値の列） | 重みが載っていない・Dataset 未 mount |
| 7 | 各列の mean / min / max | 分布が潰れていないか目視用 |

> ⚠️ **6 は「Dataset 未 mount のまま実行」を検知するための項目。** このとき notebook は**落ちずに完走してしまう**
> （フォールバックの既定値で埋まる等）ので、status だけ見ていると気付けない。

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
| ユーザー名 | - | `python -c "import json,os;print(json.load(open(os.path.join(os.environ.get('KAGGLE_CONFIG_DIR',os.path.expanduser('~/.kaggle')),'kaggle.json')))['username'])"`（**`cat kaggle.json` は鍵まで出るので使わない**） |

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

### 6.1 `HOME` がずれる環境では `KAGGLE_CONFIG_DIR` を明示する

コンテナ・常駐 bot・cron・`setsid` で切り離したプロセスなど、**実行時の `HOME` が対話シェルと違う**環境では、
`~/.kaggle/kaggle.json` が「無い」ように見える。**credential は在るのに、`HOME` がズレて見えていないだけ**のことが多い。

```bash
export KAGGLE_CONFIG_DIR=<kaggle.json を置いたディレクトリ>   # HOME がどこでも通る
export PATH="<kaggle CLI の bin ディレクトリ>:$PATH"            # CLI も HOME 配下にあるなら同様にずれる
```

- 典型: 認証ディレクトリを別パスへ read-only マウントしている / 常駐プロセスだけ別ユーザーの `HOME` で動いている
- 読み取り専用マウントでも、認証に書き込みは不要なので問題ない
- 切り離して走らせるスクリプトには、この設定を**スクリプト内に**持たせる（親シェルの env を当てにしない）。
  `tools/kaggle_submit_now.sh` は `KAGGLE_CONFIG_DIR` / `KAGGLE_EXTRA_PATH` / `KAGGLE_EXTRA_PYTHONPATH` を env で受ける
- 「この環境では Kaggle 経路は使えない」と結論する前に、`KAGGLE_CONFIG_DIR` を明示して再確認する

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

# 提出（CSV Competition）: ローカルの CSV を直接送る
kaggle competitions submit <slug> -f <csv> -m "..."

# 提出（Code Competition）: -k と -f と -v の 3 つが要る（-v は任意ではない・§8）
kaggle competitions submit <slug> -k <username>/<kernel-slug> -f submission.csv -v <N> -m "..."

kaggle competitions leaderboard -c <slug> --show
```

## 8. CLI 提出の落とし穴（実地で踏んだ）

### 8.0 Code Competition も CLI から提出できる。ただし `-v` は必須
`-k / --kernel` を付ければ Code Competition も CLI から提出できる（`-f` は「kernel が出力したファイル名」）。
ただし `--help` 上は任意に見える **`-v / --version` が実際には必須**で、`-k` と `-f` だけだと必ずこう落ちる:

```
Code competition submissions require both the output file name and the version number
```

**版番号はどこからも取得できない**（`kaggle kernels status` にも `kernels list` にも出ない）。
**唯一の一次情報は `kaggle kernels push` の出力 `Kernel version N successfully pushed.`** なので、push した時点で控える。
`tools/kaggle_submit_now.sh` は版番号を必須引数にして、忘れたら実行前に止まる。

> 🔴 教訓: `--help` を読んだだけで「できる」と書かない。**実際に 1 回打って確認してから**手順書に載せる。
> この種の誤記で、自動化できる提出を人間に手で押させたことがある。

### 8.1 kernel の実 slug は `id` ではなく **title** から決まる
`kernel-metadata.json` に `id` を書いても、**title のスラグ化が優先される**。push は成功し、警告が 1 行出るだけ:

```
Your kernel title does not resolve to the specified id. This may result in surprising behavior.
```

例: `id` に `<user>/my-comp-infer` と書き、title を `My Comp Ens5 CV0.9123 Infer` にすると、実 slug は `my-comp-ens5-cv0-9123-infer` になる。
**`id` の値を `kaggle kernels status` に渡すと "Permission denied / wrong kernel slug" で落ちる**ので、watch / submit スクリプトが動かない。
実 slug は `kaggle kernels list -m -s <keyword>` で引く。

> **「title に CV スコアを埋める」（§5.1）と「`id` で kernel を管理する」は両立しない。** どちらかを選ぶ:
> ① title を変えるなら `id` を title 由来の slug に合わせる
> ② title を `id` と同形にして、CV は dataset 側の title / description に書く

### 8.2 `kaggle kernels push` は **push した時点で run が始まる**
UI で Save & Run All を押す必要は**ない**。push のたびに 1 run 走る（GPU 枠も消費する）ので、メタデータだけ直したい時も push = 実行になることに注意。
**人間の手が要るのは提出の OK 出しだけ**（§3.5）。

### 8.3 日次提出上限は **UTC 日**単位。上限値は提出して初めて分かる
上限は API からは取得できない（`competitions list -v` の全フィールドに無い）が、**提出コマンドの標準出力に出る**:

```
2 submissions remaining today.
```

上限値はコンペごとに違う（コンペ例: 5 回 / 日）。Rules と、この出力で確認する。

> ⚠️ **境界は UTC 日**。JST 00:00〜09:00 の提出は UTC では前日に入る。
> **日本時間の午前中に出す提出は前日の枠を食う。** 枠を数えるときは UTC で数えること。

## 9. 提出フォルダの構成例（プレースホルダ）

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
