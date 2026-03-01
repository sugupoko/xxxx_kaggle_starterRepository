"""
Training script for 2.5D segmentation.

Usage:
    python train.py
    python train.py data.fold=0 trainer.max_epochs=100
    python train.py model.encoder=efficientnet_b0 trainer.batch_size=32

Resume training:
    python train.py trainer.ckpt_path=path/to/checkpoint.ckpt
"""

import os
import pytorch_lightning as pl
from pytorch_lightning.callbacks import (
    ModelCheckpoint,
    LearningRateMonitor,
    EarlyStopping,
    RichProgressBar,
)
from pytorch_lightning.loggers import CSVLogger
from omegaconf import OmegaConf

from src.pl_module import SegModule
from src.datamodule import SegDataModule


class FreezeEncoderCallback(pl.Callback):
    """Freeze encoder for the first N epochs, then unfreeze."""

    def __init__(self, freeze_epochs=0):
        self.freeze_epochs = freeze_epochs

    def on_train_epoch_start(self, trainer, pl_module):
        if trainer.current_epoch < self.freeze_epochs:
            for param in pl_module.model.encoder.parameters():
                param.requires_grad = False
        elif trainer.current_epoch == self.freeze_epochs and self.freeze_epochs > 0:
            for param in pl_module.model.encoder.parameters():
                param.requires_grad = True


def train(cfg):
    pl.seed_everything(cfg.seed, workers=True)

    datamodule = SegDataModule(cfg)
    model = SegModule(cfg)

    callbacks = [
        ModelCheckpoint(
            dirpath=f"results/fold{cfg.data.fold}/checkpoints",
            filename="epoch{epoch:03d}-dice{val/dice:.4f}",
            monitor="val/dice",
            mode="max",
            save_top_k=3,
            save_last=True,
            auto_insert_metric_name=False,
        ),
        LearningRateMonitor(logging_interval="epoch"),
        RichProgressBar(),
    ]

    if cfg.trainer.freeze_epochs > 0:
        callbacks.append(FreezeEncoderCallback(cfg.trainer.freeze_epochs))

    logger = CSVLogger(
        save_dir=f"results/fold{cfg.data.fold}",
        name="logs",
    )

    ckpt_path = cfg.trainer.get("ckpt_path", None)

    trainer = pl.Trainer(
        max_epochs=cfg.trainer.max_epochs,
        accelerator=cfg.trainer.accelerator,
        devices=cfg.trainer.devices,
        precision=cfg.trainer.precision,
        accumulate_grad_batches=cfg.trainer.accumulate_grad_batches,
        gradient_clip_val=cfg.trainer.gradient_clip_val,
        deterministic=cfg.trainer.deterministic,
        callbacks=callbacks,
        logger=logger,
        log_every_n_steps=10,
    )

    trainer.fit(model, datamodule=datamodule, ckpt_path=ckpt_path)


if __name__ == "__main__":
    # Load base config and merge CLI overrides
    base_cfg = OmegaConf.load(os.path.join(os.path.dirname(__file__), "config.yaml"))
    cli_cfg = OmegaConf.from_cli()
    cfg = OmegaConf.merge(base_cfg, cli_cfg)
    train(cfg)
