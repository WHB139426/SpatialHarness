#!/usr/bin/env python3
"""Reconstruct a video and ask a Qwen agent to explore its Blender scene."""

"""
## Qwen-3.8-Flash-Next (vLLM 0.31.0)

Uses the native 262,144-token context window without RoPE scaling overrides.

```bash
CUDA_VISIBLE_DEVICES=2,3 \
VLLM_ENGINE_READY_TIMEOUT_S=3600 \
VLLM_PLE_CPU_OFFLOAD=1 \
vllm serve /data4/haibo/weights/Qwen3.8-Flash-Next-FP8 \
  --served-model-name qwen3.8-flash-next \
  --host 127.0.0.1 \
  --port 8000 \
  --tensor-parallel-size 2 \
  --max-model-len 262144 \
  --max-num-seqs 16 \
  --gpu-memory-utilization 0.95 \
  --enable-prefix-caching \
  --enable-prompt-tokens-details \
  --no-enable-flashinfer-autotune \
  --allowed-local-media-path /data4/haibo \
  --limit-mm-per-prompt '{"image":100,"video":100}'
```

## Qwen3.8-27B-FP8 (vLLM 0.31.0)

Requires `transformers>=5.8.0`. Uses the native 262,144-token context window
without RoPE scaling overrides.

```bash
CUDA_VISIBLE_DEVICES=2 \
VLLM_ENGINE_READY_TIMEOUT_S=3600 \
vllm serve /data4/haibo/weights/Qwen3.8-27B-FP8 \
  --served-model-name qwen3.8-27b \
  --host 127.0.0.1 \
  --port 8000 \
  --tensor-parallel-size 1 \
  --max-model-len 262144 \
  --kv-cache-dtype fp8 \
  --reasoning-parser qwen3 \
  --mm-encoder-tp-mode data \
  --max-num-seqs 16 \
  --max-num-batched-tokens 8192 \
  --gpu-memory-utilization 0.95 \
  --enable-prefix-caching \
  --enable-prompt-tokens-details \
  --no-enable-flashinfer-autotune \
  --allowed-local-media-path /data4/haibo \
  --limit-mm-per-prompt '{"image":100,"video":100}'
```
"""
from multiprocessing import Process
from pathlib import Path
import sys

import main_env as environment
from agent import Agent
from agent.backend import VLLMBackend
from agent.protocols.qwen import QwenProtocol
from agent.tools import create_tools
from scene.camera_control.bridge import CameraClient


MODEL = 'qwen3.8-27b' # 'qwen3.8-flash-next'  'qwen3.8-27b'
BASE_URL = 'http://127.0.0.1:8000/v1'
MAX_TOKENS = 8192
TEMPERATURE = 1
TOP_P = 0.95
TOP_K = 20
ENABLE_THINKING = True
REASONING_EFFORT = 'medium'
PRESERVE_THINKING = True
MAX_STEPS = 100
MAX_CONVERSATION_IMAGES = 4*3  # 4 complete three-image camera observations.
MODEL_TIMEOUT = 180

SYSTEM_PROMPT = '''Role
You are a camera-navigation agent exploring a reconstructed 3D point-cloud scene.
Use the camera tools to understand its layout and answer the user's spatial questions.

Visual observations
camera_observe, camera_action, and camera_reset automatically attach three separate images
in one observation message. Each image is enclosed by its view's opening and closing text tags.
Inspect all three together as one observation.

First-person view (<first_person_view>)
This is the current camera's rendered view, with a crosshair.
Use it to inspect visible geometry, occlusion, and object positions relative to the current
viewing direction. Point-cloud gaps may be reconstruction artifacts, not proof of free space.

Top-down view (<top_down_view>)
This is an overhead map showing the current camera position and horizontal heading.
Use it to understand the scene layout, track movement, and plan navigation.
It does not show camera pitch. Its axes and the camera yaw are scene references, not geographic
directions; do not infer compass directions.

Nearest video frame (<nearest_video_frame>)
This is a captured video frame matched to the current camera pose.
Use it to identify objects, textures, and appearance details that are unclear in the point cloud.
It may differ in position and viewing direction, so do not treat it as evidence of exact current
visibility or relative position. Its matching distance and angle are included in the tool result.

Combining the views
For navigation, combine the first-person view with the top-down map.
Use the reference frame to clarify appearance, and camera state metadata to verify movement
and rotation. When the views disagree, state the uncertainty and obtain another observation
if needed. A camera turn angle alone does not measure an object's bearing.

Tool workflow
Start with camera_observe when you have no current observation.
Call at most one camera tool per response, inspect its result, and base the next action on the
latest observation. Do not call view_media again for automatically attached observation images.
Use view_media for other local images or videos.
camera_status returns position, yaw, pitch, and point radius without rendering.
camera_reset restores the initial pose and radius; use it when requested or restarting exploration.

Camera actions and units
camera_action executes one key: w/s forward/backward, a/d left/right, q/e down/up,
j/l turn left/right, i/k look up/down, +/- increase/decrease point radius.
WASD magnitudes use {distance_units}; IJKL magnitudes use degrees.
Defaults are {move_step} distance units and {look_step} degrees.
q/e use the fixed movement step and +/- use {point_step}; these four keys do not accept a magnitude.
Explicit magnitudes must be positive and finite. Pitch is limited to -89.9 through 89.9 degrees.

Navigation and answers
There is no collision detection. Use small movements near objects.
Answer once you have enough evidence, and clearly state uncertainty.'''


def main():
    args, _ = environment.parse_args()
    output = environment.create_session_dir(Path(args.output_dir).expanduser().resolve())
    folder = output / 'reconstruction'
    print(f'Reconstructing video: {args.video}', flush=True)
    reconstruction = Process(target=environment.reconstruct, args=(
        args, folder / 'vggt_reconstruction.ply', folder / 'vggt_cameras.json', environment.METRIC_FRAMES,
    ))
    reconstruction.start()
    try:
        reconstruction.join()
    except BaseException:
        reconstruction.terminate()
        reconstruction.join()
        raise
    if reconstruction.exitcode != 0:
        return reconstruction.exitcode

    command = [str(Path(args.blender).expanduser().resolve()), '--background', '--factory-startup',
               '--python-exit-code', '1', '--python', str(environment.ROOT / 'main_env.py'),
               '--', '--worker', '--session-dir', str(output), *sys.argv[1:]]
    backend = VLLMBackend(MODEL, base_url=BASE_URL, max_tokens=MAX_TOKENS,
                          temperature=TEMPERATURE, top_p=TOP_P, top_k=TOP_K)
    try:
        backend.client = backend.client.with_options(timeout=MODEL_TIMEOUT, max_retries=0)
        with CameraClient(command, log_path=output / 'render.log', timeout=environment.CAMERA_TIMEOUT) as camera:
            distance_units = ('scene units, approximately meters' if args.metric_weights.lower() != 'none'
                              else 'VGGT relative scene units, not meters')
            agent = Agent(
                backend, QwenProtocol(enable_thinking=ENABLE_THINKING, reasoning_effort=REASONING_EFFORT,
                                      preserve_thinking=PRESERVE_THINKING), create_tools(camera),
                system_prompt=SYSTEM_PROMPT.format(distance_units=distance_units, move_step=environment.MOVE_STEP,
                                                   look_step=environment.LOOK_STEP, point_step=environment.POINT_STEP),
                max_steps=MAX_STEPS, max_conversation_images=MAX_CONVERSATION_IMAGES,
                conversation_path=output / 'conversation.json',
            )
            print(f'Agent model: {MODEL}\nSession: {output}\nAsk a question; /exit to quit.', flush=True)
            while True:
                try:
                    prompt = input('agent> ').strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if prompt.lower() in ('/exit', 'quit', 'exit'):
                    break
                if prompt:
                    print('Agent:', agent.run(prompt), flush=True)
    finally:
        backend.client.close()
    print('Done. Session saved in:', output, flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
