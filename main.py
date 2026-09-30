#!/usr/bin/env python3
"""Reconstruct a video and explore its point cloud with Blender."""
import argparse
from datetime import datetime
import math

from pathlib import Path
import subprocess
import sys

DEVICE = 'cuda:0'
BLENDER = '/data4/haibo/software/blender/blender-4.5.13-linux-x64/blender'
VIDEO = '/data4/haibo/data/VSI-Bench/scannet/scene0246_00.mp4'
REC_WEIGHTS = '/data4/haibo/weights/VGGT-Omega/vggt_omega_1b_512.pt'
METRIC_WEIGHTS = '/data4/haibo/weights/DA3METRIC-LARGE'
OUTPUTDIR = 'outputs'
FPS = 2.0  # 每秒从视频中抽取的帧数
MAX_NUM_FRAMES = 300  # 最多用于重建的帧数
METRIC_FRAMES = 32  # 均匀选取多少帧用于估计米制尺度
UP = [0.0, -1.0, 0.0]  # 相机参考方向；估计失败时的回退值
EYE_HEIGHT = 1.0  # 初始视点距估计地面的高度；米制重建中约为米
RADIUS = 0.015
MOVE_STEP = 0.3  # 默认移动距离；启用 Metric 时近似为米
LOOK_STEP = 15  # 每次 IJKL 转动的角度
POINT_STEP = 0.005  # 每次 +/- 调整的点半径
HELP = f'''
Camera controls (one or more keys per line; both views render after each key):
  w / s    Walk forward / backward horizontally; add meters, e.g. w0.5.
  a / d    Strafe left / right; add meters, e.g. a0.2.
  q / e    Descend / ascend along the scene up axis.
  j / l    Look left / right; add degrees, e.g. j30.
  i / k    Look up / down; add degrees, e.g. i10.
  + / -    Increase / decrease point radius (point clouds only).
  reset    Restore the initial camera pose and point radius.
  status   Print current camera position, angles, and point radius without rendering.
  help     Show this help.
  quit     Exit (also: exit).
WASD defaults to {MOVE_STEP:g} meters; IJKL defaults to {LOOK_STEP:g} degrees.
Point radius changes by {POINT_STEP:g} scene units per +/- key.
Edit MOVE_STEP, LOOK_STEP, or POINT_STEP at the top to change these fixed amounts.
Positive magnitudes can follow each WASD/IJKL key: w0.5a0.2j30.
Keys run left to right: wwww moves four default steps; waij still works.
Each key renders one PNG with first-person on the left and overhead on the right, plus a JSON record.
'''


def create_session_dir(parent):
    session_dir = parent / datetime.now().strftime('camera_%Y%m%d_%H%M%S_%f')
    session_dir.mkdir(parents=True, exist_ok=False)
    return session_dir


def parse_args():
    worker = '--worker' in sys.argv
    argv = sys.argv[sys.argv.index('--worker') + 1:] if worker else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blender', default=BLENDER)
    parser.add_argument('--output-dir', default=OUTPUTDIR, help='Parent directory for new camera sessions')
    parser.add_argument('--resolution', type=int, default=960)
    parser.add_argument('--samples', type=int, default=16)
    parser.add_argument('--up', nargs=3, type=float, default=None,
                        metavar=('X', 'Y', 'Z'), help='Override the scene up vector; otherwise estimate from the PLY and camera JSON.')
    parser.add_argument('--video', default=VIDEO, help='Source video for reconstruction.')
    parser.add_argument('--fps', type=float, default=FPS, help='Frames sampled per second of video.')
    parser.add_argument('--max-num-frames', type=int, default=MAX_NUM_FRAMES, help='Maximum sampled frames.')
    parser.add_argument('--checkpoint', default=REC_WEIGHTS, help='VGGT-Omega checkpoint for reconstruction.')
    parser.add_argument('--device', default=DEVICE, help='Reconstruction inference device.')
    parser.add_argument('--metric-weights', default=METRIC_WEIGHTS, help='DA3 Metric checkpoint directory; use none to keep VGGT relative scale.')
    parser.add_argument('--point-radius', default=RADIUS, type=float, help='Point cloud radius in scene units; default: %(default)s')
    parser.add_argument('--session-dir', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.resolution < 64 or args.samples < 1:
        parser.error('resolution must be >=64 and samples must be >=1')
    if not math.isfinite(args.fps) or args.fps <= 0:
        parser.error('fps must be finite and positive')
    if args.max_num_frames < 2:
        parser.error('max-num-frames must be at least 2')
    if not math.isfinite(args.point_radius) or args.point_radius <= 0:
        parser.error('point-radius must be finite and positive')
    if args.up is not None:
        up_length = math.hypot(*args.up)
        if not all(math.isfinite(v) for v in args.up) or not math.isfinite(up_length) or up_length <= 1e-12:
            parser.error('up must be a finite, nonzero vector')
        args.up = [v / up_length for v in args.up]
    return parser, args, worker


def launch(args, session_dir, source, cameras_path, parser):
    print(f'Reconstructing video: {args.video}', flush=True)
    reconstruction = [sys.executable, str(Path(__file__).resolve().parent / 'camera_control' / 'reconstruct.py'),
                      '--video', args.video, '--fps', str(args.fps),
                      '--max-num-frames', str(args.max_num_frames),
                      '--checkpoint', args.checkpoint, '--device', args.device,
                      '--metric-weights', args.metric_weights,
                      '--output-ply', str(source), '--output-cameras', str(cameras_path)]
    try:
        result = subprocess.call(reconstruction)
    except KeyboardInterrupt:
        return 130
    if result != 0:
        return result
    blender = Path(args.blender).expanduser().resolve()
    if not blender.is_file():
        parser.error(f'Blender not found: {blender}')
    command = [str(blender), '--background', '--factory-startup', '--python-exit-code', '1',
               '--python', str(Path(__file__).resolve()), '--', '--worker',
               '--session-dir', str(session_dir), *sys.argv[1:]]
    try:
        return subprocess.call(command)
    except KeyboardInterrupt:
        return 130


def main():
    parser, args, worker = parse_args()
    parent = Path(args.output_dir).expanduser().resolve()
    if worker:
        if args.session_dir is None:
            parser.error('Blender worker requires --session-dir')
        session_dir = Path(args.session_dir).expanduser().resolve()
        if not session_dir.is_dir():
            parser.error(f'Session directory missing: {session_dir}')
    else:
        session_dir = create_session_dir(parent)
    folder = session_dir / 'reconstruction'
    source = folder / 'vggt_reconstruction.ply'
    cameras_path = folder / 'vggt_cameras.json'
    if not worker:
        return launch(args, session_dir, source, cameras_path, parser)
    if not source.is_file() or not cameras_path.is_file():
        parser.error(f'Reconstruction output missing: {source} or {cameras_path}')

    # Blender does not add the script directory to sys.path in background mode.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from camera_control.session import run_session
    return run_session(args, source, cameras_path, session_dir, HELP, UP,
                       MOVE_STEP, LOOK_STEP, POINT_STEP, EYE_HEIGHT)


if __name__ == '__main__':
    raise SystemExit(main())
