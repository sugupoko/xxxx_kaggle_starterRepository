# Kaggle Competition Experiment Template

このリポジトリは **Kaggle コンペ用の実験管理テンプレート**です。
Claude Code を前提に、**データ取得 → EDA → 調査（論文/類似コンペ） → 実験（exp管理） → 提出**までを、再現性高く回すためのルールと作業手順をまとめています。

`tools/` 以下には、時間測定（提出監視など）スクリプトと、フォルダを Kaggle Dataset にアップロードしてバージョン管理するシェルが入っています。必要に応じて使ってください。

詳細はこの記事に記載してあります。[リンク](https://zenn.dev/sugupoko/articles/1c985219823589)

---

# 使い方

## Quickstart

最短で「このレポでコンペを回し始める」ための手順です。迷ったらここだけ順に潰してください。

### 1) 対象コンペを確定する

* `KAGGLE_DIRECTION.md` の冒頭に **対象コンペURL** を記入

### 2) Claude Code を初期化する

* リポジトリ直下で `/init` を実行し、指示書を読み込ませる
  （以降は **指示書のルールが最優先**）

### 3) データを揃える
* プロンプト:「データセットをダウンロードしてきて。`datasets/` に保存、展開まで。再現コマンドも残して。」
* 注意：kaggle APIのセットアップは済ませておくこと。

### 4) まず全体像を掴む（EDA）
* プロンプト：「EDAして `competition/overview.md` にまとめて。データ構造、サイズ、指標、提出形式、注意点込み。」

### 5) 先行知見を集める（調査）
* プロンプト：「関連論文を探して `survey/papers/maybe_related_research.md` にまとめて。転用アイデアも。」
* プロンプト：「類似コンペを探して `competition/related_competitions.md` にまとめて。流用点/差分も。」
 
### 6) 実験を開始する（最初のベースライン）
* プロンプト：「`workspace/expA00_baseline` を作って最小ベースライン。`SESSION_NOTES.md` を必ず作成して記録。」



---

# 詳細説明

## リポジトリ構造（テンプレ標準）

```
./
├── datasets/
│   └── distributed/              # Competition data download scripts
├── competition/                  # コンペティションの内容について（EDA/類似コンペなど）
├── tools/                        # Utility scripts
│   ├── kaggle_elapsed_time.py    # Submission status monitoring
│   └── kaggle_upload.sh          # Dataset upload/versioning script
├── survey/                       # 調査した内容を格納
│   ├── discussion/               # kaggleのディスカッション定点観測
│   └── papers/                   # 論文の内容をまとめておく
└── workspace/                    # Main development workspace
    └── expXXX... / expA00...     # 実験フォルダ（命名規則は後述）
```

推奨ドキュメント配置：

* `competition/overview.md`：EDAまとめ（データ構造・指標・提出形式など）
* `competition/related_competitions.md`：類似コンペまとめ
* `survey/papers/xxxx.md`：論文メモ
* `survey/discussion/xxxx.md`：ディスカッション観測メモ
* `workspace/exp*/SESSION_NOTES.md`：実験ログ（必須）

---

## 実験のルール（テンプレの核）

### 実験フォルダ命名規則

Claude と人間で実験フォルダを分けます。

* **Claude用**: `workspace/exp(アルファベット)(数字2桁)_(実験名)`

  * 例: `workspace/expA00_baseline`
  * 大きく方針が変わる時だけ番号を増やす（微調整は同じexp内）
* **人間用**: `workspace/exp(数字3桁)_(実験名)`

  * 例: `workspace/exp200_try_unet`

### SESSION_NOTES.md（必須）

**各実験フォルダには必ず `SESSION_NOTES.md` を作成**します。
途中で中断しても、未来の自分/他人が復帰できる状態を作ります。

最低限書くこと（例）：

* 仮説（何を良くしたいのか）
* 変更点（どのファイル/どの設定を変えたか）
* 実験条件（CV、seed、データ分割、特徴量、モデル設定）
* 結果（メトリクス、提出結果、ログへのリンク）
* 次アクション（TODO、やる/やらない）

※詳細は指示書（`KAGGLE_DIRECTION.md`）の「セッション記録のルール」に従ってください。

---

## tools の使い方

### 提出の監視・経過時間の計測

`tools/kaggle_elapsed_time.py` は提出状況の監視や、経過時間を見たい時に使います。
（具体的な使い方はスクリプト内のヘルプやコメントを参照）

### Kaggle Dataset へのアップロード（フォルダをバージョン管理）

`tools/kaggle_upload.sh` は、フォルダを Kaggle Dataset としてアップロードしてバージョンを作る用途です。
（実験成果物や特徴量、推論結果などを再現性のために残す）

> 使い方・前提（Kaggle API 設定など）はスクリプト内のコメントに従ってください。

