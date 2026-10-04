"""Estimate one metric scale for a VGGT-Omega reconstruction using DA3 Metric."""

import math


def estimate_metric_scale(predictions, metric_weights, device, max_frames):
    import torch
    import torch.nn.functional as F

    from depth_anything_3.api import DepthAnything3
    from vggt_omega.utils.pose_enc import pose_encoding_to_extri_intri

    images = predictions['images']
    depth = predictions['depth'][..., 0]
    confidence = predictions['depth_conf']
    _, frames, _, height, width = images.shape
    # DA3 uses 14-pixel patches; VGGT-Omega uses 16-pixel patches.
    metric_height = round(height / 14) * 14
    metric_width = round(width / 14) * 14
    _, intrinsics = pose_encoding_to_extri_intri(
        predictions['pose_enc'], (metric_height, metric_width))
    model = DepthAnything3.from_pretrained(str(metric_weights)).to(device).eval()
    sampled = torch.linspace(0, frames - 1, min(frames, max_frames)).round().long().tolist()
    scales = []
    with torch.inference_mode():
        for index in sampled:
            image = F.interpolate(images[:, index], (metric_height, metric_width),
                                  mode='bilinear', align_corners=False)
            vggt_depth = F.interpolate(depth[:, index:index + 1],
                                       (metric_height, metric_width), mode='bilinear',
                                       align_corners=False)[:, 0].float()
            vggt_conf = F.interpolate(confidence[:, index:index + 1],
                                      (metric_height, metric_width), mode='bilinear',
                                      align_corners=False)[:, 0].float()
            metric = model(image[:, None], export_feat_layers=[0])
            metric_depth = metric.depth[:, 0].float()
            non_sky = metric.sky[:, 0].float() < .3
            # Match GeoVR's focal-length correction and confidence mask.
            focal = (intrinsics[:, index, 0, 0] + intrinsics[:, index, 1, 1]) / 2
            metric_depth = metric_depth * (focal[:, None, None] / 300.0)
            if non_sky.sum() < 10:
                continue
            threshold = vggt_conf[non_sky].median()
            valid = (non_sky & (vggt_conf >= threshold)
                     & (vggt_depth > 1e-3) & (metric_depth > 1e-2)
                     & torch.isfinite(vggt_depth) & torch.isfinite(metric_depth))
            if valid.sum() < 10:
                continue
            source, target = vggt_depth[valid], metric_depth[valid]
            scale = (target * source).sum() / source.square().sum()
            value = float(scale)
            if math.isfinite(value) and value > 0:
                scales.append(value)
    del model
    if not scales:
        raise RuntimeError('DA3 Metric could not estimate a valid scene scale')
    values = torch.tensor(scales, dtype=torch.float64)
    q25, scale, q75 = (float(v) for v in torch.quantile(
        values, torch.tensor([.25, .50, .75], dtype=torch.float64)))
    spread = (q75 - q25) / scale * 100
    print(f'Metric scale: {scale:.6g} from {len(scales)}/{len(sampled)} sampled frames; '
          f'frame-scale IQR: {spread:.1f}%', flush=True)
    if spread > 25:
        print('Warning: frame scales vary substantially; metric scale may be unreliable', flush=True)
    return scale
