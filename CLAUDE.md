# Kaggle Competition Workspace

このリポジトリはKaggleコンペ用の実験管理テンプレートです。
**判断に迷ったら `KAGGLE_DIRECTION.md` の設計意図を確認すること。**

## アイデア提案の原則（堅実＋爆発）

**アプローチやアイデアを提案するときは、必ず「堅実案」と「爆発案」の両方を出すこと。**

- **堅実案**: 既知の手法、定石、段階的改善。確実にスコアが上がる見込みがあるもの
- **爆発案**: 常識外れ、異分野からの転用、誰もやらなそうなアプローチ。失敗リスクは高いが当たれば大きいもの

例:
```
堅実: encoder を efficientnet_b0 → b4 に変更（+0.5%程度の改善見込み）
爆発: セグメンテーションを捨てて物体検出で解く / 全く別のモダリティの事前学習済みモデルを転用
```

局所解に陥らないために、爆発案は「それは普通やらないだろう」くらいがちょうどいい。

## 基本ルール

- 実験は `workspace/` 以下で行う
- Claude用: `expA00_baseline` (アルファベット+数字2桁)、人間用: `exp200_name` (数字3桁)
- 各実験フォルダには必ず `SESSION_NOTES.md` を作成する
- 大きく方針が変わる時だけ新しいexp番号にする。微調整は同じフォルダ内で
- 結果・知見は `claudeSummary.md` に集約する

## 学習コードの鉄則

- **AMP (Mixed Precision) は常にON** (`precision: 16-mixed`)
- **チェックポイント再開は必須** (`save_last=True` + `ckpt_path`)
- **シード固定** (`pl.seed_everything(seed, workers=True)`)
- ハイパーパラメータはすべてconfigで管理（ハードコーディング禁止）

## Fold設計（最重要）

**安易にランダムKFoldにしない。データの性質を先に確認する。**

- 時系列 → TimeSeriesSplit
- グループ構造あり → GroupKFold
- クラス不均衡 → StratifiedKFold
- グループ+不均衡 → StratifiedGroupKFold
- fold設計の理由と各foldの分布はSESSION_NOTES.mdに記録する
- CV/LBの相関を確認し、相関が弱ければfold設計を見直す

## 前処理・評価・提出

- 正規化はtrainデータの統計量で計算する（testの情報を使わない）
- コンペの評価指標を正確に再現する（既存実装のパラメータも確認）
- Augmentationはまず弱めで、過学習が確認されてから強める
- single modelのCV/LBを記録してからアンサンブルする
- 提出前に行数・カラム名・欠損値・値の範囲を確認する

## 利用可能なSkills

- `/new-exp [実験名]` - 新規実験フォルダ作成
- `/eda [データパス]` - EDA実行 → competition/overview.md
- `/submit [ファイル] [メッセージ]` - Kaggle提出 + 監視開始
- `/survey-discussion` - ディスカッション定点観測
- `/survey-papers [キーワード]` - 論文・解法調査
- `/exp-summary` - 全実験の結果をclaudeSummary.mdに集約
- `/upload [フォルダ]` - Kaggle Datasetにアップロード

## Custom Agents

状況に応じて自動的にサブエージェントに委譲される。並列実行も可能。

- **kaggle-researcher** (haiku) - 論文・類似コンペ解法・ディスカッション調査。コスト節約のためhaiku使用
- **data-analyst** (sonnet) - EDA・可視化・特徴量分析。データの全体像把握に
- **code-reviewer** (sonnet) - ML/DLコード品質レビュー。読み取り専用で安全
- **experiment-runner** (inherit) - 実験実行＋SESSION_NOTES記録。学習の実行から結果整理まで

## リファレンスコード

- `reference/` に2.5Dセグメンテーションのテンプレートコード（PyTorch Lightning + timm + smp）がある
- 新しい実験のベースとして活用すること
