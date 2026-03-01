"""
2.5D Segmentation Model using timm encoder + smp decoder.

2.5D approach: neighboring depth slices are stacked as input channels
to a 2D segmentation model, providing local 3D context without full 3D convolutions.
"""

import segmentation_models_pytorch as smp


ARCH_MAP = {
    "unet": smp.Unet,
    "unetplusplus": smp.UnetPlusPlus,
    "manet": smp.MAnet,
    "deeplabv3plus": smp.DeepLabV3Plus,
}


def get_model(cfg):
    arch_cls = ARCH_MAP[cfg.model.arch]
    model = arch_cls(
        encoder_name=cfg.model.encoder,
        encoder_weights="imagenet" if cfg.model.pretrained else None,
        in_channels=cfg.data.n_slices,
        classes=cfg.data.num_classes,
    )
    return model
