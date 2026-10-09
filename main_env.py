#!/usr/bin/env python3
"""Reconstruct a video and explore its point cloud with Blender."""
import argparse
import json
from multiprocessing import Process
from pathlib import Path
import subprocess
import sys

# Blender does not add the script directory to sys.path in background mode.
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from scene.reconstruction.reconstruct import create_session_dir, reconstruct

DEVICE = 'cuda:1'
BLENDER = '/data4/haibo/software/blender/blender-4.5.13-linux-x64/blender'
VIDEO = '/data4/haibo/data/VSI-Bench/scannet/scene0246_00.mp4'
REC_WEIGHTS = '/data4/haibo/weights/VGGT-Omega/vggt_omega_1b_512.pt'
METRIC_WEIGHTS = '/data4/haibo/weights/DA3METRIC-LARGE'
OUTPUTDIR = 'outputs'
FPS = 2.0  # 每秒从视频中抽取的帧数
MAX_NUM_FRAMES = 500  # 最多用于重建的帧数
METRIC_FRAMES = 32  # 均匀选取多少帧用于估计米制尺度
EYE_HEIGHT = 1.0  # 初始视点距估计地面的高度；米制重建中约为米
RADIUS = 0.015
RESOLUTION = 960  # 第一人称图和俯视图的边长（像素）；参考帧保持原始尺寸
MOVE_STEP = 0.3  # 默认移动距离；启用 Metric 时近似为米
LOOK_STEP = 15  # 每次 IJKL 转动的角度
POINT_STEP = 0.005  # 每次 +/- 调整的点半径
CAMERA_TIMEOUT = 300  # 相机 worker 初始化或单次响应的等待秒数

HELP = f'''
Camera controls (one or more keys per line; three-panel PNG after each key):
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
Edit MOVE_STEP, LOOK_STEP, or POINT_STEP at the top of main_env.py to change these fixed amounts.
Positive magnitudes can follow each WASD/IJKL key: w0.5a0.2j30.
Keys run left to right: wwww moves four default steps; waij still works.
Each key saves a three-panel PNG preview, separate first-person and top-down-with-trajectory PNGs, and a JSON record.
'''


def parse_args():
    worker = '--worker' in sys.argv
    argv = sys.argv[sys.argv.index('--worker') + 1:] if worker else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', default=VIDEO, help='Source video for reconstruction.')
    parser.add_argument('--fps', type=float, default=FPS, help='Frames sampled per second of video.')
    parser.add_argument('--max-num-frames', type=int, default=MAX_NUM_FRAMES, help='Maximum sampled frames.')
    parser.add_argument('--checkpoint', default=REC_WEIGHTS, help='VGGT-Omega checkpoint for reconstruction.')
    parser.add_argument('--device', default=DEVICE, help='Reconstruction inference device.')
    parser.add_argument('--metric-weights', default=METRIC_WEIGHTS, help='DA3 Metric checkpoint directory; use none to keep VGGT relative scale.')
    parser.add_argument('--output-dir', default=OUTPUTDIR, help='Parent directory for new camera sessions')
    parser.add_argument('--blender', default=BLENDER)
    parser.add_argument('--resolution', type=int, default=RESOLUTION,
                        help='First-person and top-down image size in pixels; default: %(default)s')
    parser.add_argument('--samples', type=int, default=16)
    parser.add_argument('--up', nargs=3, type=float, default=None,
                        metavar=('X', 'Y', 'Z'), help='Override the scene up vector; otherwise estimate from the PLY and camera JSON.')
    parser.add_argument('--point-radius', default=RADIUS, type=float, help='Point cloud radius in scene units; default: %(default)s')
    parser.add_argument('--session-dir', help=argparse.SUPPRESS)
    parser.add_argument('--response-fd', type=int, help=argparse.SUPPRESS)
    return parser.parse_args(argv), worker


def launch(args, session_dir, source, cameras_path):
    blender = Path(args.blender).expanduser().resolve()
    print(f'Reconstructing video: {args.video}', flush=True)
    reconstruction = Process(target=reconstruct, args=(args, source, cameras_path, METRIC_FRAMES))
    reconstruction.start()
    reconstruction.join()
    if reconstruction.exitcode != 0:
        return reconstruction.exitcode
    command = [str(blender), '--background', '--factory-startup', '--python-exit-code', '1',
               '--python', str(ROOT / 'main_env.py'), '--', '--worker',
               '--session-dir', str(session_dir), *sys.argv[1:]]
    return subprocess.call(command)


def run_viewer(session, output):
    """Read terminal commands and dispatch them to the camera session."""
    from scene.camera_control.actions import parse_actions

    print(HELP, flush=True)
    session.observe('initial')
    while True:
        try:
            command = input('camera> ').strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if command in ('quit', 'exit'):
            break
        if not command:
            continue
        try:
            if command == 'help':
                print(HELP, flush=True)
                continue
            if command == 'status':
                print(json.dumps(session.status(), indent=2), flush=True)
                continue
            if command == 'reset':
                session.reset()
                continue
            actions = parse_actions(command)
            if len(actions) > 1:
                print('Sequence:', ' '.join(label for _, _, label in actions), flush=True)
            for key, magnitude, label in actions:
                session.execute(key, magnitude, label)
        except (ValueError, RuntimeError, OSError) as exc:
            print(f'Error: {exc}\nRender log: {output / "render.log"}', flush=True)
    print('Done. Images saved in:', output, flush=True)
    return 0


def main():
    args, worker = parse_args()
    if worker:
        session_dir = Path(args.session_dir).expanduser().resolve()
    else:
        session_dir = create_session_dir(Path(args.output_dir).expanduser().resolve())
    folder = session_dir / 'reconstruction'
    source = folder / 'vggt_reconstruction.ply'
    cameras_path = folder / 'vggt_cameras.json'
    if not worker:
        return launch(args, session_dir, source, cameras_path)
    from scene.camera_control.session import CameraSession
    from scene.rendering.renderer import SceneRenderer
    renderer = SceneRenderer(args, source, cameras_path, session_dir, eye_height=EYE_HEIGHT)
    position, direction = renderer.initial_pose
    session = CameraSession(
        renderer, position=position, direction=direction,
        point_radius=args.point_radius, move_step=MOVE_STEP,
        look_step=LOOK_STEP, point_step=POINT_STEP,
    )
    if args.response_fd is not None:
        from scene.camera_control.bridge import serve_camera
        return serve_camera(session, args.response_fd)
    return run_viewer(session, session_dir)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
