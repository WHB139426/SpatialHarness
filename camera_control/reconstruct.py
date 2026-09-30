#!/usr/bin/env python3
"""Sample a video and reconstruct a colored PLY plus camera parameters."""

import argparse
import json
import math
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

# Support direct execution as well as python -m camera_control.reconstruct.
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# Both model packages use absolute imports of their own top-level names.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'models'))

from main import (
    REC_WEIGHTS,
    DEVICE,
    FPS,
    MAX_NUM_FRAMES,
    METRIC_FRAMES,
    METRIC_WEIGHTS,
    VIDEO,
    OUTPUTDIR,
)


def sample_video(video_path, target_fps, max_num_frames, frames_dir):
    import cv2

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f'Cannot open video: {video_path}')
    try:
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        source_fps = capture.get(cv2.CAP_PROP_FPS)
        if not math.isfinite(source_fps) or source_fps <= 0:
            raise ValueError(f'Cannot read video frame rate: {video_path}')
        if target_fps > source_fps:
            raise ValueError(f'Requested {target_fps:g} fps exceeds video frame rate {source_fps:g} fps')
        indices = []
        for sample in range(max_num_frames):
            index = round(sample * source_fps / target_fps)
            if index >= total:
                break
            indices.append(index)
        if len(indices) < 2:
            raise ValueError('Video is too short to sample at least two frames at the requested fps')
        paths = []
        for index in indices:
            if not capture.set(cv2.CAP_PROP_POS_FRAMES, index):
                raise RuntimeError(f'Cannot seek to video frame {index}')
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError(f'Cannot decode video frame {index}')
            path = frames_dir / f'frame_{index:06d}.jpg'
            if not cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95]):
                raise RuntimeError(f'Cannot write sampled frame {index}')
            paths.append(path)
    finally:
        capture.release()
    return paths, indices, source_fps


def reconstruct(args):
    import numpy as np
    import open3d as o3d
    import torch

    video = Path(args.video).expanduser().resolve(strict=True)
    checkpoint = Path(args.checkpoint).expanduser().resolve(strict=True)
    metric_weights = (None if args.metric_weights.lower() == 'none' else
                      Path(args.metric_weights).expanduser().resolve(strict=True))
    output_ply = Path(args.output_ply).expanduser().resolve()
    output_cameras = Path(args.output_cameras).expanduser().resolve()
    if metric_weights is not None and not (metric_weights / 'config.json').is_file():
        raise ValueError(f'DA3 Metric checkpoint directory is invalid: {metric_weights}')
    if not video.is_file() or not checkpoint.is_file():
        raise ValueError('Video and checkpoint must be files')
    model_dir = Path(__file__).resolve().parent.parent / 'models'
    if not (model_dir / 'vggt_omega').is_dir():
        raise ValueError('Local models/vggt_omega package is missing')
    if metric_weights is not None and not (model_dir / 'depth_anything_3').is_dir():
        raise ValueError('Local models/depth_anything_3 package is missing')
    if output_ply == output_cameras or output_ply.parent != output_cameras.parent:
        raise ValueError('PLY and camera JSON must be distinct files in one directory')
    if args.device.startswith('cuda') and not torch.cuda.is_available():
        raise RuntimeError('CUDA is unavailable; choose an available device')

    from vggt_omega.models import VGGTOmega
    from vggt_omega.utils.load_fn import load_and_preprocess_images
    from vggt_omega.utils.pose_enc import pose_encoding_to_extri_intri

    output_ply.parent.mkdir(parents=True, exist_ok=True)
    frames_dir = output_ply.parent / 'frames'
    frames_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.reconstruction_work_', dir=output_ply.parent) as temp:
        temp_dir = Path(temp)
        frame_paths, indices, source_fps = sample_video(video, args.fps, args.max_num_frames, frames_dir)
        print(f'Sampled {len(frame_paths)} frames at {args.fps:g} fps '
              f'(video {source_fps:.3f} fps; indices {indices[0]}..{indices[-1]})', flush=True)

        model = VGGTOmega().to(args.device).eval()
        state = torch.load(checkpoint, map_location='cpu', weights_only=True)
        model.load_state_dict(state)
        del state
        images = load_and_preprocess_images([str(p) for p in frame_paths], image_resolution=512).to(args.device)
        with torch.inference_mode():
            predictions = model(images)

        if metric_weights is None:
            scale = 1.0
            print('Metric scaling disabled; coordinates use VGGT relative units', flush=True)
        else:
            from camera_control.metric_scale import estimate_metric_scale
            scale = estimate_metric_scale(predictions, metric_weights, args.device, METRIC_FRAMES)

        images = predictions['images']
        _, sequence, _, height, width = images.shape
        extrinsics, intrinsics = pose_encoding_to_extri_intri(predictions['pose_enc'], (height, width))
        point_cloud = o3d.geometry.PointCloud()
        camera_data = []
        for i in range(sequence):
            rgb = (images[0, i].permute(1, 2, 0).contiguous().cpu().numpy() * 255).astype(np.uint8)
            depth = (predictions['depth'][0, i, :, :, 0].float() * scale).contiguous().cpu().numpy()
            confidence = predictions['depth_conf'][0, i].float().cpu().numpy()
            depth[confidence < np.percentile(confidence, 40)] = 0.0
            extrinsic = np.eye(4, dtype=np.float64)
            extrinsic[:3, :] = extrinsics[0, i].float().cpu().numpy()
            extrinsic[:3, 3] *= scale
            intrinsic = intrinsics[0, i].float().cpu().numpy().astype(np.float64)
            rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
                o3d.geometry.Image(rgb), o3d.geometry.Image(depth),
                depth_scale=1.0, depth_trunc=15.0, convert_rgb_to_intensity=False,
            )
            pinhole = o3d.camera.PinholeCameraIntrinsic(
                width=width, height=height,
                fx=intrinsic[0, 0], fy=intrinsic[1, 1],
                cx=intrinsic[0, 2], cy=intrinsic[1, 2],
            )
            point_cloud += o3d.geometry.PointCloud.create_from_rgbd_image(rgbd, pinhole, extrinsic)
            camera_data.append({
                'id': i, 'extrinsic': extrinsic.tolist(), 'intrinsic': intrinsic.tolist(),
                'W': width, 'H': height, 'video_frame_index': indices[i],
                'image_path': str(Path('frames') / frame_paths[i].name),
                'time_seconds': indices[i] / source_fps,
                'source_video': str(video),
                'metric_scale': scale, 'metric_weights': str(metric_weights) if metric_weights else None,
            })
            if (i + 1) % 16 == 0 or i + 1 == sequence:
                print(f'Converted {i + 1}/{sequence} frames', flush=True)

        point_cloud = point_cloud.voxel_down_sample(voxel_size=0.01)
        if not point_cloud.has_points():
            raise RuntimeError('Reconstruction produced an empty point cloud')
        temp_ply = temp_dir / output_ply.name
        temp_cameras = temp_dir / output_cameras.name
        if not o3d.io.write_point_cloud(str(temp_ply), point_cloud):
            raise RuntimeError(f'Failed to write PLY: {temp_ply}')
        temp_cameras.write_text(json.dumps(camera_data, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temp_ply, output_ply)
        os.replace(temp_cameras, output_cameras)
        print(f'PLY: {output_ply} ({len(point_cloud.points):,} points)', flush=True)
        print(f'Cameras: {output_cameras} ({len(camera_data)} frames)', flush=True)
        print(f'Sampled frames: {frames_dir} ({len(frame_paths)} JPGs)', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', default=VIDEO)
    parser.add_argument('--fps', type=float, default=FPS)
    parser.add_argument('--max-num-frames', type=int, default=MAX_NUM_FRAMES)
    parser.add_argument('--checkpoint', default=REC_WEIGHTS)
    parser.add_argument('--device', default=DEVICE)
    parser.add_argument('--metric-weights', default=METRIC_WEIGHTS,
                        help='DA3 Metric checkpoint directory; use none for VGGT relative scale')
    parser.add_argument('--output-dir', default=OUTPUTDIR, help='Parent directory for reconstructions')
    parser.add_argument('--output-ply', help='Output PLY; default: <output-dir>/reconstructions/<video name>/vggt_reconstruction.ply')
    parser.add_argument('--output-cameras', help='Output camera JSON; default: <output-dir>/reconstructions/<video name>/vggt_cameras.json')
    args = parser.parse_args()
    if not math.isfinite(args.fps) or args.fps <= 0:
        parser.error('--fps must be finite and positive')
    if args.max_num_frames < 2:
        parser.error('--max-num-frames must be at least 2')
    folder = Path(args.output_dir).expanduser().resolve() / 'reconstructions' / Path(args.video).stem
    args.output_ply = args.output_ply or str(folder / 'vggt_reconstruction.ply')
    args.output_cameras = args.output_cameras or str(folder / 'vggt_cameras.json')
    reconstruct(args)


if __name__ == '__main__':
    main()
