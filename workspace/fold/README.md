# workspace/fold/ — fold 割り当ての永続化

## 設計意図

- **fold 割り当ては 1 箇所で生成・固定し、全実験で同じ `folds.csv` を共有する**
  - 実験ごとに fold を切り直すと CV スコアが比較不能になり、リークの温床にもなる
  - 学習コードは `folds.csv` をキー列で join して train/val を分けるだけにする
- 切り方の選定基準は `CLAUDE.md` の「Fold設計（最重要）」を参照（安易にランダム KFold にしない）
  - 時系列 → TimeSeriesSplit（`generate_folds.py` の対象外。必要なら専用スクリプトを同階層に追加する）
  - グループ構造あり → GroupKFold
  - クラス不均衡 → StratifiedKFold
  - グループ + 不均衡 → StratifiedGroupKFold
- fold 設計の理由と各 fold の分布は実験の `SESSION_NOTES.md` に記録する（`generate_folds.py` のログをそのまま転記してよい）

## 使い方

```bash
cd workspace/fold

# 例: グループ + 不均衡 → StratifiedGroupKFold
python generate_folds.py --input ../../datasets/train.csv \
    --version v1_sgkf_patient_label --strategy stratified_group \
    --id-col image_id --target-col label --group-col patient_id
```

- 引数の詳細は `python generate_folds.py --help` / `generate_folds.py` 冒頭の docstring を参照
- シードはデフォルト 42 で固定（`--seed` で変更可。変えたら別バージョンにする）
- 学習側は config.yaml の `data.folds_csv` で使用バージョンを指定する:

```yaml
data:
  folds_csv: workspace/fold/v1_sgkf_patient_label/folds.csv
```

## バージョニング規約

- バージョン名は `v1_xxx` 形式（連番 + 切り方が分かる短い識別子）
  - 例: `v1_random_kfold5` / `v2_group_patient` / `v3_sgkf_patient_label`
- **前処理やデータを変更したら新バージョンを作る。古いバージョンは削除しない**（過去実験の再現性のため）
  - `generate_folds.py` も既存バージョンへの上書きを拒否する
- ディレクトリ構成:

```
workspace/fold/
├── README.md
├── generate_folds.py
├── v1_xxx/
│   ├── folds.csv                          # キー列 + (target/group 列) + fold
│   └── generate_folds_YYYYMMDD_HHMMSS.log # 生成時の引数・分布ログ
└── v2_yyy/
    └── ...
```

## 検証

- 生成ログで各 fold の件数・ターゲット分布・グループ非重複（リーク検査）を確認する
- CV/LB の相関を確認し、相関が弱ければ fold 設計を見直して**新バージョン**を作る
