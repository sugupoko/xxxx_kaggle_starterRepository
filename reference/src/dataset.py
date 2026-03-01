"""
2.5D Segmentation Dataset.

Handles 3D volumes by extracting 2D slices with neighboring depth context.
Each sample: (n_slices, H, W) image + (num_classes, H, W) mask.
"""

import numpy as np
import torch
from torch.utils.data import Dataset
import albumentations as A
from albumentations.pytorch import ToTensorV2


def get_train_transforms(img_size):
    return A.Compose([
        A.RandomCrop(img_size, img_size),
        A.HorizontalFlip(p=0.5),
        A.VerticalFlip(p=0.5),
        A.RandomRotate90(p=0.5),
        A.ShiftScaleRotate(
            shift_limit=0.05, scale_limit=0.1, rotate_limit=30,
            border_mode=0, p=0.5,
        ),
        A.RandomBrightnessContrast(brightness_limit=0.2, contrast_limit=0.2, p=0.3),
        A.GaussNoise(p=0.2),
        ToTensorV2(),
    ])


def get_val_transforms(img_size):
    return A.Compose([
        A.CenterCrop(img_size, img_size),
        ToTensorV2(),
    ])


class Seg25DDataset(Dataset):
    """
    2.5D segmentation dataset.

    Loads 3D volume slices with neighboring depth context.
    Each item returns:
        image: (n_slices, H, W) float32 - center slice + neighbors
        mask:  (num_classes, H, W) float32 - segmentation target for center slice

    Args:
        images: list of 3D arrays, each (D, H, W) or (H, W, D)
        masks: list of 3D arrays, each (D, H, W, C) or (H, W, D, C)
        n_slices: number of neighboring slices (e.g., 5 = center + 2 above + 2 below)
        transform: albumentations transform
        depth_indices: optional pre-computed list of (volume_idx, slice_idx) tuples
    """

    def __init__(self, images, masks, n_slices=5, transform=None, depth_indices=None):
        self.images = images
        self.masks = masks
        self.n_slices = n_slices
        self.half = n_slices // 2
        self.transform = transform

        if depth_indices is not None:
            self.indices = depth_indices
        else:
            self.indices = []
            for vol_idx, img in enumerate(images):
                depth = img.shape[0]
                for d in range(depth):
                    self.indices.append((vol_idx, d))

    def __len__(self):
        return len(self.indices)

    def _get_slice_stack(self, volume, center_d):
        """Extract n_slices around center_d with reflection padding."""
        depth = volume.shape[0]
        slices = []
        for offset in range(-self.half, self.half + 1):
            d = center_d + offset
            d = max(0, min(d, depth - 1))  # clamp
            slices.append(volume[d])
        return np.stack(slices, axis=-1)  # (H, W, n_slices)

    def __getitem__(self, idx):
        vol_idx, slice_idx = self.indices[idx]

        # image: (H, W, n_slices) for albumentations
        image = self._get_slice_stack(self.images[vol_idx], slice_idx)
        image = image.astype(np.float32)

        # mask: (H, W, C) for albumentations
        mask = self.masks[vol_idx][slice_idx].astype(np.float32)
        if mask.ndim == 2:
            mask = mask[..., np.newaxis]

        if self.transform:
            augmented = self.transform(image=image, mask=mask)
            image = augmented["image"]  # (n_slices, H, W)
            mask = augmented["mask"]    # (H, W, C)

        # mask: (H, W, C) -> (C, H, W)
        if isinstance(mask, np.ndarray):
            mask = torch.from_numpy(mask).permute(2, 0, 1).float()
        else:
            mask = mask.permute(2, 0, 1).float()

        return image.float(), mask
