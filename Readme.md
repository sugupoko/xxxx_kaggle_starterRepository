# Kaggle Competition Experiment Template

このリポジトリは **Kaggle コンペ用の実験管理テンプレートレポジトリ**です。
Claude Code を前提に、**データ取得 → EDA → 調査（論文/類似コンペ） → 実験（exp管理） → 提出**までを、再現性高く回すためのルールと作業手順をまとめています。

---

## 0. このテンプレの使い方（最初にやること）

### 0-1. テンプレをクローンする

```bash
git clone <このリポジトリURL>
cd <repo>
```

### 0-2. 指示書の冒頭に「対象コンペURL」を記入する（重要）

このテンプレは、**対象コンペが毎回変わる**前提です。
作業開始前に、方針md（指示書）の最初に **対象コンペのURL** を記入してください。

例：

```md
# Competition URL
https://www.kaggle.com/competitions/<competition-slug>

# はじめに
これはKaggleのコンペティション用のレポジトリです。
/initをしたらここを読み込んでルールを確認してください。
...
```

> これにより「このレポがどのコンペの作業場か」が常に明確になります。

### 0-3. `/init` で初期化（Claude Code）

Claude Code 上でリポジトリ直下から `/init` を実行し、
**指示書（方針md）を読み込ませてルールを確定**させます。

以降は **指示書のルールが最優先**です。

---

## 1. リポジトリ構造（テンプレ標準）

```
./
├── datasets/
│   └── distributed/              # Competition data download scripts
├── tools/                        # Utility scripts
│   ├── kaggle_elapsed_time.py    # Submission status monitoring
│   └── kaggle_upload.sh          # Dataset upload/versioning script
├── survey/                       # 調査した内容を格納
│   ├── discussion/               # kaggleのディスカッション定点観測
│   └── papers/                   # 論文の内容をまとめておく
└── workspace/                    # Main development workspace
    └── expXXX... / expA00...     # 実験フォルダ（命名規則は後述）
```

---

## 2. 実験のルール（テンプレの核）

### 2-1. 実験フォルダ命名規則

Claude と人間で実験フォルダを分けます。

* **Claude用**: `workspace/exp(アルファベット)(数字2桁)_(実験名)`

  * 例: `workspace/expA00_baseline`
  * 大きく方針が変わる時だけ番号を増やす（微調整は同じexp内）
* **人間用**: `workspace/exp(数字3桁)_(実験名)`

  * 例: `workspace/exp200_try_unet`

### 2-2. SESSION_NOTES.md（必須）

**各実験フォルダには必ず `SESSION_NOTES.md` を作成**します。
途中で中断しても、未来の自分/他人が復帰できる状態を作ります。

（テンプレの詳細は指示書の「セッション記録のルール」に従ってください）

---

## 3. 典型ワークフロー（このテンプレの標準手順）

このテンプレは「毎回同じ手順で調査→実験に入れる」ことが価値です。
以下を順番に実施します。

### 3-1. データのダウンロードを指示する

Claude への指示例：

* 「データセットをダウンロードしてきて。`datasets/` 配下に保存して、zipなら展開まで。」
* 「再現性のために、実行コマンドと取得先（Kaggle API等）も残して。」

期待成果物：

* `datasets/` にデータが揃う
* 取得手順が `datasets/distributed/` かドキュメントに残る

### 3-2. コンペデータのEDAをしてまとめる

Claude への指示例：

* 「コンペデータをEDAして、データ構造・サイズ感・欠損・ラベル分布・注意点を markdown にまとめて」
* 「train/test/sample_submission、評価指標、提出形式、ローカル検証の観点も書いて」

保存先（推奨）：

* `survey/competition/overview.md`（※無ければ作成する）

### 3-3. コンペ内容に近い論文を探してまとめる

Claude への指示例：

* 「このコンペに近い論文を探して `survey/papers/maybe_related_research.md` にまとめて」
* 「手法・データ・評価・再現リンク・転用アイデア・注意点を入れて」

### 3-4. コンペ内容に近いタスクのコンペを探してまとめる

Claude への指示例：

* 「近いタスクのKaggle/他コンペを探して `survey/competition/related_competitions.md` にまとめて」
* 「タスク概要、評価指標、定番手法、上位解法の共通パターン、参考ノート/解法のリンクも」

### 3-5. 実験に入る（最初のベースライン）

1つ目の実験フォルダを切って、最小ベースラインを作ります。

```bash
mkdir -p workspace/expA00_baseline
touch workspace/expA00_baseline/SESSION_NOTES.md
```

Claude への指示例：

* 「`workspace/expA00_baseline` を作り、最小ベースライン（学習→推論→submission生成）を実装して。`SESSION_NOTES.md` も必ず埋めて。」

---

## 4. チェックリスト（迷ったらここ）

* [ ] 指示書冒頭に対象コンペURLを書いた
* [ ] `/init` で初期化してルールを読み込んだ
* [ ] データを `datasets/` に配置し、手順が残っている
* [ ] EDAが `survey/competition/overview.md` にまとまっている
* [ ] 論文まとめが `survey/papers/` にある
* [ ] 類似コンペまとめが `survey/competition/related_competitions.md` にある
* [ ] `workspace/expA00_*` を作り `SESSION_NOTES.md` を作った
* [ ] 最小ベースラインが一気通貫で動く

---

## 付録：Claudeに投げる指示（コピペ用）

1. 「データセットをダウンロードしてきて。`datasets/` に保存、展開まで。再現コマンドも残して。」
2. 「EDAして `survey/competition/overview.md` にまとめて。データ構造、サイズ、指標、提出形式、注意点込み。」
3. 「関連論文を探して `survey/papers/maybe_related_research.md` にまとめて。転用アイデアも。」
4. 「類似コンペを探して `survey/competition/related_competitions.md` にまとめて。流用点/差分も。」
5. 「`workspace/expA00_baseline` を作って最小ベースライン。`SESSION_NOTES.md` を必ず作成して記録。」
