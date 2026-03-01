# Kaggle Competition Experiment Template

このリポジトリは **Kaggle コンペ用の実験管理テンプレート**です。
Claude Code を前提に、**データ取得 → EDA → 調査（論文/類似コンペ） → 実験（exp管理） → 提出**までを、再現性高く回すためのルールと作業手順をまとめています。

**Claude Code の Skills / Custom Agents を活用**し、コンペのワークフローを自動化・効率化しています。

詳細はこの記事に記載してあります。[リンク](https://zenn.dev/sugupoko/articles/1c985219823589)

---

# 使い方

## Quickstart

### 1) 対象コンペを確定する

* `KAGGLE_DIRECTION.md` に **対象コンペ名とURL** を記入

### 2) Claude Code を起動する

* リポジトリ直下で Claude Code を起動すれば `CLAUDE.md` が自動読み込みされる
* `/init` は不要

### 3) データを揃える

* プロンプト:「データセットをダウンロードしてきて。`datasets/` に保存、展開まで。」
* 注意：kaggle APIのセットアップは済ませておくこと

### 4) まず全体像を掴む（EDA）

* `/eda` を実行、または「EDAして」と指示
* 結果は `competition/overview.md` にまとめられる

### 5) 先行知見を集める（調査）

* `/survey-papers` で論文検索
* `/survey-discussion` でディスカッション定点観測

### 6) 実験を開始する

* `/new-exp baseline` で実験フォルダ + SESSION_NOTES.md が自動生成
* `reference/` のコードをベースに実装

---

# 基本ルール（必ず守ること）

## 学習の設定

1. **AMP (Automatic Mixed Precision) は常にON**
   - `precision: 16-mixed` または `torch.cuda.amp` を必ず使用する
   - AMP非対応の処理がある場合のみ例外的にOFFにし、その理由をSESSION_NOTES.mdに明記する

2. **チェックポイント再開は必須**
   - PCが途中で止まることがある。学習は必ず途中から再開できるようにする
   - `ModelCheckpoint(save_last=True)` + `trainer.fit(ckpt_path=...)` を使う
   - optimizer、scheduler、epoch数すべて復元されること

3. **シード固定**
   - `pl.seed_everything(seed, workers=True)` で再現性を確保する
   - シード値はconfigに記載し、SESSION_NOTES.mdにも記録する

4. **ハードコーディング禁止**
   - パス、ハイパーパラメータはすべてconfigファイルで管理する
   - マジックナンバーを使わない

5. **再現性の担保**
   - 使用したコマンドをSESSION_NOTES.mdに記録する
   - configファイルも結果と一緒に保存する

## Cross Validation（Fold設計）

**Foldの切り方は最重要事項の一つ。安易にランダムKFoldにしない。**

1. **データの性質を必ず先に確認する**
   - 時系列データ → TimeSeriesSplit / Purged KFold（リークを防ぐ）
   - グループ構造がある（患者ID、画像ID等） → GroupKFold（同じグループがtrain/valに分かれないように）
   - クラス不均衡 → StratifiedKFold（各foldのクラス比率を揃える）
   - グループ + 不均衡 → StratifiedGroupKFold
   - 独立なデータで上記の懸念がない場合のみ → KFold

2. **CV設計時に確認すること**
   - train/valの分布が一致しているか（特徴量、ターゲット両方）
   - リークがないか（時間的リーク、グループリーク）
   - fold間でスコアのばらつきが大きすぎないか（大きい場合はfold設計を見直す）
   - CV と LB の相関があるか（なければfold設計を疑う）

3. **fold数の目安**
   - データ量が十分 → 5-fold
   - データ量が少ない → 10-fold（各foldのval数を確保）
   - 学習コストが高い → 3-fold or 代表1-2foldで実験、最終は全fold

4. **fold設計の決定はSESSION_NOTES.mdに記録する**
   - なぜそのfold戦略を選んだか
   - 各foldのデータ数・分布
   - CV/LB相関の確認結果

## 評価指標

1. **コンペの評価指標を正確に実装する**
   - コンペページの Evaluation を必ず確認し、指標を正確に再現する
   - sklearn等の既存実装がある場合でもパラメータが一致するか確認する

2. **最適化対象の一貫性**
   - Loss関数と評価指標が異なる場合、その影響を意識する
   - 閾値最適化が必要な指標（F1等）は、CV内で閾値チューニングする

## データ前処理

1. **正規化・標準化はtrainデータの統計量で計算する**
   - testデータの情報を使わない（リーク防止）
   - fold毎にtrain splitから統計量を計算するのが理想

2. **Augmentationの方針**
   - まず弱いAugmentationでベースラインを確立する
   - 強いAugmentationは過学習が確認されてから導入する
   - Augmentationの効果はCV値で判断する（感覚でやらない）

## 提出・アンサンブル

1. **single model のスコアを必ず記録してからアンサンブルする**
   - 各モデルのCV/LBスコアを把握しておく
   - アンサンブルの寄与を把握できるようにする

2. **提出前のチェック**
   - submission.csv の行数がsample_submissionと一致するか
   - カラム名がsample_submissionと一致するか
   - 欠損値がないか
   - 値の範囲が妥当か

---

# 実験のルール

## 実験フォルダ命名規則

Claude と人間で実験フォルダを分けます。

* **Claude用**: `workspace/exp(アルファベット)(数字2桁)_(実験名)`
  * 例: `workspace/expA00_baseline`
  * 大きく方針が変わる時だけ番号を増やす（微調整は同じexp内）
* **人間用**: `workspace/exp(数字3桁)_(実験名)`
  * 例: `workspace/exp200_try_unet`

## SESSION_NOTES.md（必須）

**各実験フォルダには必ず `SESSION_NOTES.md` を作成**します。
途中で中断しても、未来の自分/他人が復帰できる状態を作ります。

含めるべき内容：

1. **セッション情報** - 日付、作業フォルダ、目標
2. **試したアプローチと結果** - 詳細説明、ファイル名、メトリクス、問題点
3. **ファイル構成** - スクリプト、可視化結果、データファイルのリスト
4. **重要な知見** - 発見、避けるべきアプローチ、有効だったテクニック
5. **次のステップ** - TODO、優先度付き
6. **性能変化の記録** - 何をしてどうなったかを俯瞰できるように
7. **コマンド履歴** - 再現性のための記録

## 実験フォルダ構成

```
workspace/expA00_baseline/
├── SESSION_NOTES.md          # 必須
├── src/                      # ソースコード
├── results/                  # 実験結果
│   └── exp001_xxxx/
└── dataset/                  # データセット
    └── v001_xxxx/
```

---

# Skills（スラッシュコマンド）

`.claude/skills/` に定義。`/コマンド名` で手動実行、または Claude が状況に応じて自動起動。

| コマンド | 用途 | 自動起動 |
|---------|------|---------|
| `/new-exp [実験名]` | 命名規則に従って実験フォルダ + SESSION_NOTES.md を自動生成 | OK |
| `/eda [データパス]` | EDA実行 → `competition/overview.md` に保存 | OK |
| `/submit [ファイル] [msg]` | Kaggle提出 + `kaggle_elapsed_time.py` で監視開始 | 手動のみ |
| `/survey-discussion` | ディスカッション定点観測（Playwright） | OK |
| `/survey-papers [キーワード]` | 論文・類似コンペ解法の検索・まとめ | OK |
| `/exp-summary` | 全実験の結果を `claudeSummary.md` に集約 | OK |
| `/upload [フォルダ]` | Kaggle Datasetにアップロード | 手動のみ |

> `submit` と `upload` は外部APIへの送信を伴うため、手動起動のみ。

---

# Custom Agents（サブエージェント）

`.claude/agents/` に定義。Claude が状況に応じて自動的に委譲。並列実行も可能。

| Agent | モデル | ツール | 用途 |
|-------|--------|--------|------|
| **kaggle-researcher** | haiku | Read, Grep, Glob, WebSearch, WebFetch, Bash | 論文・類似コンペ解法・ディスカッション調査 |
| **data-analyst** | sonnet | Read, Write, Edit, Bash, Grep, Glob | EDA・可視化・特徴量分析 |
| **code-reviewer** | sonnet | Read, Grep, Glob（読み取り専用） | ML/DLコード品質レビュー |
| **experiment-runner** | inherit | Read, Write, Edit, Bash, Grep, Glob | 実験実行 + SESSION_NOTES記録 |

---

# リポジトリ構造

```
./
├── CLAUDE.md                     # Claude Code 自動読み込みルール（要約）
├── KAGGLE_DIRECTION.md           # コンペ固有設定 + 設計意図（WHY）
├── claudeSummary.md              # 全実験の知見集約
├── myMemo.md                     # 自分のメモ
├── .claude/
│   ├── skills/                   # カスタムスキル（7個）
│   └── agents/                   # カスタムエージェント（4個）
├── reference/                    # リファレンスコード
│   ├── config.yaml
│   ├── train.py
│   └── src/                      # 2.5Dセグメンテーション (PL + timm + smp)
├── datasets/                     # データセット
├── competition/                  # コンペ情報（EDA/類似コンペ）
├── tools/
│   ├── kaggle_elapsed_time.py    # 提出状況監視
│   └── kaggle_upload.sh          # Dataset アップロード
├── survey/
│   ├── discussion/               # ディスカッション定点観測
│   └── papers/                   # 論文まとめ
└── workspace/                    # 実験フォルダ
```

---

# リファレンスコード

`reference/` に **2.5Dセグメンテーション**のテンプレートコード。

* [yu4u/kaggle-czii-4th](https://github.com/yu4u/kaggle-czii-4th) をベースに設計
* **PyTorch Lightning** + **timm** (encoder) + **segmentation_models_pytorch** (decoder)
* 2.5Dアプローチ：隣接スライスをチャンネルスタックして2Dモデルで処理
* EMA、Mixup、Freeze encoder、AMP、チェックポイント再開 対応

```bash
python reference/train.py                              # 基本実行
python reference/train.py model.encoder=efficientnet_b0 # encoder変更
python reference/train.py data.fold=0 trainer.max_epochs=100  # 設定オーバーライド
```

---

# tools の使い方

## 提出の監視・経過時間の計測

`tools/kaggle_elapsed_time.py` - 提出状況の監視。`/submit` スキルから自動呼び出しも可能。

## Kaggle Dataset へのアップロード

`tools/kaggle_upload.sh` - フォルダを Kaggle Dataset としてアップロード。`/upload` スキルから呼び出しも可能。

> kaggle APIのセットアップが前提です。
