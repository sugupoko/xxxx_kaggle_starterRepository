# Reference: 2.5D Segmentation Template (PyTorch Lightning)

[yu4u/kaggle-czii-4th](https://github.com/yu4u/kaggle-czii-4th) をベースにした汎用2.5Dセグメンテーションテンプレート。

## 構成

```
reference/
├── config.yaml          # OmegaConf設定ファイル
├── train.py             # 学習エントリポイント
├── requirements.txt     # 依存パッケージ（メジャーバージョン範囲ピン）
├── README.md
└── src/
    ├── pl_module.py     # LightningModule (EMA, mixup, optimizer)
    ├── datamodule.py    # LightningDataModule (K-Fold)
    ├── dataset.py       # 2.5D Dataset + augmentations
    ├── model.py         # timm encoder + smp decoder
    └── loss.py          # BCEDice / WeightedMSE / FocalDice
```

## 2.5Dアプローチ

3Dボリュームを直接扱う代わりに、注目するスライスの前後N枚を入力チャンネルとしてスタック。
2Dの事前学習済みEncoder（ImageNet）をそのまま活用できる。
ボリューム端では存在しないスライスを端のスライスで埋める（clamp = replicate padding）。

```
n_slices=5 の場合:
  入力: [slice_d-2, slice_d-1, slice_d, slice_d+1, slice_d+2] → (5, H, W)
  出力: center sliceのセグメンテーション → (C, H, W)
```

## 使い方

```bash
# 依存パッケージのインストール
pip install -r requirements.txt

# 基本実行
python train.py

# 設定オーバーライド（OmegaConf dotlist 形式。--config フラグは無い）
python train.py data.fold=0 trainer.max_epochs=100 model.encoder=efficientnet_b0

# チェックポイントから再開（ナンバリングされず既存ディレクトリに書き続ける）
python train.py trainer.ckpt_path=results/exp_baseline/fold0/last.ckpt

# 全fold実行（各foldは同じ results/{experiment.name}/ 配下の foldN/ に出力される）
for i in 0 1 2 3 4; do python train.py data.fold=$i; done
```

## 出力

全出力は `results/{experiment.name}/foldN/` に集約される（`paths.output_dir` が相対パスの場合は
train.py のあるディレクトリ基準で解決されるため、どこから実行しても同じ場所に出る）。

```
results/exp_baseline/fold0/
├── config.yaml              # CLIオーバーライドをマージ済みのconfig（再現性のため自動保存）
├── last.ckpt                # 再開用（save_last=True）
├── epochXXX-diceY.YYYY.ckpt # val/dice 上位3つ
├── train_YYYYMMDD_HHMMSS.log
└── csv_logs/
```

- 同名 fold ディレクトリが既に存在する場合は `exp_baseline_001/fold0` のように実験名をナンバリングして上書きを防ぐ
- `trainer.ckpt_path` を指定した再開時はナンバリングせず既存ディレクトリを使う

## EMA有効時の推論

`model.ema: true` の場合、checkpoint には生のモデル（`model.*`）と EMA モデル（`ema_model.module.*`）の
両方の重みが保存される。**推論には EMA 側の重みを使うこと**（validation も EMA で評価している）。

```python
import torch
from omegaconf import OmegaConf
from src.model import get_model

cfg = OmegaConf.load("results/exp_baseline/fold0/config.yaml")
ckpt = torch.load("results/exp_baseline/fold0/last.ckpt", map_location="cpu")

prefix = "ema_model.module."
state = {k[len(prefix):]: v for k, v in ckpt["state_dict"].items() if k.startswith(prefix)}

model = get_model(cfg)
model.load_state_dict(state)
model.eval()
```

## 依存パッケージ

`requirements.txt` を参照（torch / pytorch-lightning / timm / segmentation-models-pytorch /
albumentations / omegaconf / scikit-learn / pandas / numpy / rich）。
timm は `ModelEmaV3` を使うため 1.0 以上が必要。

## カスタマイズのポイント

- **データ読み込み**: `src/datamodule.py` の `load_data()` をコンペのデータ形式に合わせて変更（画像とマスクは stem 名でマッチングされる）
- **fold割り当て**: `data.folds_csv` に `workspace/fold/{version}/folds.csv` を指定すると事前計算foldを使用（null なら on-the-fly KFold）
- **モデル**: `config.yaml` の `model.encoder` で timm の任意のモデルを指定可能
- **Loss**: `src/loss.py` に追加して `config.yaml` で切り替え
- **Augmentation**: `src/dataset.py` の `get_train_transforms()` を編集
