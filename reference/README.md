# Reference: 2.5D Segmentation Template (PyTorch Lightning)

[yu4u/kaggle-czii-4th](https://github.com/yu4u/kaggle-czii-4th) をベースにした汎用2.5Dセグメンテーションテンプレート。

## 構成

```
reference/
├── config.yaml          # OmegaConf設定ファイル
├── train.py             # 学習エントリポイント
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

```
n_slices=5 の場合:
  入力: [slice_d-2, slice_d-1, slice_d, slice_d+1, slice_d+2] → (5, H, W)
  出力: center sliceのセグメンテーション → (C, H, W)
```

## 使い方

```bash
# 基本実行
python train.py

# 設定オーバーライド
python train.py data.fold=0 trainer.max_epochs=100 model.encoder=efficientnet_b0

# チェックポイントから再開
python train.py trainer.ckpt_path=results/fold0/checkpoints/last.ckpt

# 全fold実行
for i in 0 1 2 3 4; do python train.py data.fold=$i; done
```

## 依存パッケージ

```
pytorch-lightning
segmentation-models-pytorch
timm
albumentations
omegaconf
scikit-learn
rich
```

## カスタマイズのポイント

- **データ読み込み**: `src/datamodule.py` の `load_data()` をコンペのデータ形式に合わせて変更
- **モデル**: `config.yaml` の `model.encoder` で timm の任意のモデルを指定可能
- **Loss**: `src/loss.py` に追加して `config.yaml` で切り替え
- **Augmentation**: `src/dataset.py` の `get_train_transforms()` を編集
