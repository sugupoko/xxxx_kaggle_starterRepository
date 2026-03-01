"""
Loss functions for segmentation.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class DiceLoss(nn.Module):
    def __init__(self, smooth=1.0):
        super().__init__()
        self.smooth = smooth

    def forward(self, pred, target):
        pred = torch.sigmoid(pred)
        pred_flat = pred.view(-1)
        target_flat = target.view(-1)
        intersection = (pred_flat * target_flat).sum()
        return 1 - (2.0 * intersection + self.smooth) / (
            pred_flat.sum() + target_flat.sum() + self.smooth
        )


class BCEDiceLoss(nn.Module):
    def __init__(self, bce_weight=0.5):
        super().__init__()
        self.bce = nn.BCEWithLogitsLoss()
        self.dice = DiceLoss()
        self.bce_weight = bce_weight

    def forward(self, pred, target):
        return self.bce_weight * self.bce(pred, target) + (1 - self.bce_weight) * self.dice(pred, target)


class FocalLoss(nn.Module):
    def __init__(self, alpha=0.25, gamma=2.0):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma

    def forward(self, pred, target):
        bce = F.binary_cross_entropy_with_logits(pred, target, reduction="none")
        pt = torch.exp(-bce)
        focal = self.alpha * (1 - pt) ** self.gamma * bce
        return focal.mean()


class FocalDiceLoss(nn.Module):
    def __init__(self, focal_weight=0.5):
        super().__init__()
        self.focal = FocalLoss()
        self.dice = DiceLoss()
        self.focal_weight = focal_weight

    def forward(self, pred, target):
        return self.focal_weight * self.focal(pred, target) + (1 - self.focal_weight) * self.dice(pred, target)


class WeightedMSELoss(nn.Module):
    """MSE loss with position weighting (from yu4u/kaggle-czii-4th)."""

    def __init__(self, neg_weight=0.1):
        super().__init__()
        self.neg_weight = neg_weight

    def forward(self, pred, target):
        loss = F.mse_loss(pred, target, reduction="none")
        weight = target + self.neg_weight
        return (loss * weight).mean()


def get_loss(cfg):
    name = cfg.loss.name
    if name == "bce_dice":
        return BCEDiceLoss()
    elif name == "mse":
        return WeightedMSELoss()
    elif name == "focal_dice":
        return FocalDiceLoss()
    else:
        raise ValueError(f"Unknown loss: {name}")
