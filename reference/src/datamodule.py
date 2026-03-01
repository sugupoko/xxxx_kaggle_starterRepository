"""
PyTorch Lightning DataModule for 2.5D segmentation.

This is a template - adapt load_data() to your competition's data format.
"""

import numpy as np
from pathlib import Path
from sklearn.model_selection import KFold
import pytorch_lightning as pl
from torch.utils.data import DataLoader

from .dataset import Seg25DDataset, get_train_transforms, get_val_transforms


class SegDataModule(pl.LightningDataModule):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.train_dataset = None
        self.val_dataset = None

    def load_data(self):
        """
        Load 3D volumes and masks.
        Adapt this method to your competition's data format.

        Returns:
            images: list of np.ndarray, each (D, H, W)
            masks:  list of np.ndarray, each (D, H, W, C)
        """
        img_dir = Path(self.cfg.data.img_dir)
        mask_dir = Path(self.cfg.data.mask_dir)

        img_paths = sorted(img_dir.glob("*.npy"))
        mask_paths = sorted(mask_dir.glob("*.npy"))

        images = [np.load(p) for p in img_paths]
        masks = [np.load(p) for p in mask_paths]

        return images, masks, img_paths

    def setup(self, stage=None):
        images, masks, img_paths = self.load_data()
        n_volumes = len(images)

        # K-Fold split on volume level
        kf = KFold(n_splits=self.cfg.data.num_folds, shuffle=True, random_state=self.cfg.seed)
        splits = list(kf.split(range(n_volumes)))
        train_idx, val_idx = splits[self.cfg.data.fold]

        train_images = [images[i] for i in train_idx]
        train_masks = [masks[i] for i in train_idx]
        val_images = [images[i] for i in val_idx]
        val_masks = [masks[i] for i in val_idx]

        img_size = self.cfg.data.img_size
        n_slices = self.cfg.data.n_slices

        self.train_dataset = Seg25DDataset(
            train_images, train_masks,
            n_slices=n_slices,
            transform=get_train_transforms(img_size),
        )
        self.val_dataset = Seg25DDataset(
            val_images, val_masks,
            n_slices=n_slices,
            transform=get_val_transforms(img_size),
        )

    def train_dataloader(self):
        return DataLoader(
            self.train_dataset,
            batch_size=self.cfg.trainer.batch_size,
            shuffle=True,
            num_workers=self.cfg.data.num_workers,
            pin_memory=True,
            drop_last=True,
        )

    def val_dataloader(self):
        return DataLoader(
            self.val_dataset,
            batch_size=self.cfg.trainer.batch_size,
            shuffle=False,
            num_workers=self.cfg.data.num_workers,
            pin_memory=True,
        )
