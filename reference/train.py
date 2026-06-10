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
import sys
import time
import logging
from pathlib import Path
import pytorch_lightning as pl
from pytorch_lightning.callbacks import (
    ModelCheckpoint,
    LearningRateMonitor,
    RichProgressBar,
)
from pytorch_lightning.loggers import CSVLogger
from omegaconf import OmegaConf

from src.pl_module import SegModule
from src.datamodule import SegDataModule

log = logging.getLogger(__name__)


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


def setup_logging(log_dir: str, prefix: str = "train") -> None:
    """Configure logging to both console and file."""
    os.makedirs(log_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"{prefix}_{timestamp}.log")

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(fh)
    root_logger.addHandler(ch)

    log.info(f"Log file: {log_file}")


def resolve_fold_dir(results_root: Path, exp_name: str, fold: int, resume: bool) -> Path:
    """Resolve fold directory with auto-numbering to avoid overwrite.

    Existence is checked per-fold (not per-experiment) so that running
    fold1 after fold0 lands in the same experiment directory.
    When resuming from a checkpoint, keep writing to the existing directory.
    """
    base = results_root / exp_name / f"fold{fold}"
    if resume or not base.exists():
        return base
    n = 1
    while True:
        candidate = results_root / f"{exp_name}_{n:03d}" / f"fold{fold}"
        if not candidate.exists():
            return candidate
        n += 1


def train(cfg):
    pl.seed_everything(cfg.seed, workers=True)

    # Resolve experiment directory: results/{exp_name}/foldN/
    # Relative output_dir is resolved against this file's directory (cwd-independent)
    exp_name = cfg.get("experiment", {}).get("name", "default")
    results_root = Path(cfg.get("paths", {}).get("output_dir", "results"))
    if not results_root.is_absolute():
        results_root = Path(__file__).resolve().parent / results_root

    ckpt_path = cfg.trainer.get("ckpt_path", None)
    fold_dir = resolve_fold_dir(
        results_root, exp_name, cfg.data.fold, resume=ckpt_path is not None
    )
    fold_dir.mkdir(parents=True, exist_ok=True)

    # Setup logging in fold directory (before any log output)
    setup_logging(str(fold_dir))
    if fold_dir.parent.name != exp_name:
        log.info(f"Fold dir for '{exp_name}' exists, using '{fold_dir.parent.name}'")
    log.info(f"Experiment: {fold_dir.parent.name}, Fold: {cfg.data.fold}")
    log.info(f"Config:\n{OmegaConf.to_yaml(cfg)}")

    # Save merged config (CLI overrides included) for reproducibility
    OmegaConf.save(cfg, fold_dir / "config.yaml")

    datamodule = SegDataModule(cfg)
    model = SegModule(cfg)

    callbacks = [
        ModelCheckpoint(
            dirpath=str(fold_dir),
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

    csv_logger = CSVLogger(
        save_dir=str(fold_dir),
        name="csv_logs",
    )

    trainer = pl.Trainer(
        max_epochs=cfg.trainer.max_epochs,
        accelerator=cfg.trainer.accelerator,
        devices=cfg.trainer.devices,
        precision=cfg.trainer.precision,
        accumulate_grad_batches=cfg.trainer.accumulate_grad_batches,
        gradient_clip_val=cfg.trainer.gradient_clip_val,
        deterministic=cfg.trainer.deterministic,
        callbacks=callbacks,
        logger=csv_logger,
        log_every_n_steps=10,
    )

    log.info(f"Starting training: fold={cfg.data.fold}, epochs={cfg.trainer.max_epochs}")
    trainer.fit(model, datamodule=datamodule, ckpt_path=ckpt_path)
    log.info("Training complete")


if __name__ == "__main__":
    # Load base config and merge CLI overrides
    base_cfg = OmegaConf.load(os.path.join(os.path.dirname(__file__), "config.yaml"))
    cli_cfg = OmegaConf.from_cli()
    cfg = OmegaConf.merge(base_cfg, cli_cfg)
    train(cfg)
