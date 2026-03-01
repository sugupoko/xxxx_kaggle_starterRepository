"""
PyTorch Lightning Module for 2.5D segmentation.

Features:
- EMA (Exponential Moving Average) support via timm
- Mixup augmentation
- Configurable optimizer/scheduler via timm
- Checkpoint resume support (built-in to Lightning)
"""

import torch
import pytorch_lightning as pl
from timm.utils import ModelEmaV3
from timm.optim import create_optimizer_v2
from timm.scheduler import create_scheduler_v2

from .model import get_model
from .loss import get_loss


class SegModule(pl.LightningModule):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.save_hyperparameters()

        self.model = get_model(cfg)
        self.loss_fn = get_loss(cfg)

        # EMA
        self.use_ema = cfg.model.ema
        self.ema_model = None
        if self.use_ema:
            self.ema_model = ModelEmaV3(self.model, decay=cfg.model.ema_decay)

        self.mixup_prob = cfg.loss.mixup

    def forward(self, x):
        return self.model(x)

    def _forward_with_ema(self, x):
        if self.use_ema and self.ema_model is not None and not self.training:
            return self.ema_model.module(x)
        return self.model(x)

    def _mixup(self, x, y):
        """Apply mixup augmentation."""
        if self.training and self.mixup_prob > 0 and torch.rand(1).item() < self.mixup_prob:
            lam = torch.distributions.Beta(0.4, 0.4).sample().item()
            idx = torch.randperm(x.size(0), device=x.device)
            x_mixed = lam * x + (1 - lam) * x[idx]
            return x_mixed, y, y[idx], lam
        return x, y, None, 1.0

    def training_step(self, batch, batch_idx):
        x, y = batch
        x, y1, y2, lam = self._mixup(x, y)

        pred = self.model(x)
        loss = lam * self.loss_fn(pred, y1)
        if y2 is not None:
            loss += (1 - lam) * self.loss_fn(pred, y2)

        self.log("train/loss", loss, prog_bar=True)
        return loss

    def on_train_batch_end(self, outputs, batch, batch_idx):
        if self.use_ema and self.ema_model is not None:
            self.ema_model.update(self.model)

    def validation_step(self, batch, batch_idx):
        x, y = batch
        pred = self._forward_with_ema(x)
        loss = self.loss_fn(pred, y)

        # Dice score
        pred_bin = (torch.sigmoid(pred) > 0.5).float()
        intersection = (pred_bin * y).sum()
        dice = (2.0 * intersection + 1) / (pred_bin.sum() + y.sum() + 1)

        self.log("val/loss", loss, prog_bar=True, sync_dist=True)
        self.log("val/dice", dice, prog_bar=True, sync_dist=True)
        return loss

    def configure_optimizers(self):
        optimizer = create_optimizer_v2(
            self.model,
            opt=self.cfg.optimizer.name,
            lr=self.cfg.optimizer.lr,
            weight_decay=self.cfg.optimizer.weight_decay,
        )

        scheduler, num_epochs = create_scheduler_v2(
            optimizer,
            sched=self.cfg.scheduler.name,
            num_epochs=self.cfg.trainer.max_epochs,
            warmup_epochs=self.cfg.scheduler.warmup_epochs,
            min_lr=self.cfg.scheduler.min_lr,
        )

        return {
            "optimizer": optimizer,
            "lr_scheduler": {
                "scheduler": scheduler,
                "interval": "epoch",
            },
        }
