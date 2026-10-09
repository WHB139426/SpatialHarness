#!/usr/bin/env python3
"""Reconstruct a video and ask a Qwen agent to explore its Blender scene."""

"""
## Qwen3.8-Flash-Next-FP8 (vLLM 0.31.0)

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


MODEL = 'qwen3.8-flash-next' # 'qwen3.8-flash-next'  'qwen3.8-27b'
BASE_URL = 'http://127.0.0.1:8000/v1'
MAX_TOKENS = 8*1024
TEMPERATURE = 1
TOP_P = 0.95
TOP_K = 20
ENABLE_THINKING = True
REASONING_EFFORT = 'medium' # "low", "medium", "xhigh"
PRESERVE_THINKING = True
MAX_STEPS = 100
MAX_CONVERSATION_IMAGES = 4*3  # Keep 4 complete three-image observations.

# 你现在走到卫生间的位置，要求第一视角必须对着马桶

SYSTEM_PROMPT = '''Role
You are a camera-navigation agent exploring a reconstructed 3D point-cloud scene.
Use the camera tools to understand its layout and answer the user's spatial questions.

Visual observations
camera_observe, camera_action, and camera_reset automatically attach three separate images
in one observation message. Each image is enclosed by its view's opening and closing text tags.
Their order is first-person view, top-down map with movement history, and nearest video frame.
Inspect all three together as one observation.

First-person view (<first_person_view>)
This is the current camera's rendered view, with a crosshair.
Use it to inspect visible geometry, occlusion, and object positions relative to the current
viewing direction. Point-cloud gaps may be reconstruction artifacts, not proof of free space.

Top-down view (<top_down_view>)
This is an overhead map showing the current camera position, horizontal heading, and movement history.
The orange dot marks the camera position. A cross labeled w/a/s/d shows the current horizontal
movement directions: the long blue w arrow points forward, a left, s backward, and d right.
Green curved arrows show camera turns: j turns left (counterclockwise on this map),
and l turns right (clockwise). These labels are the keys accepted by camera_action:
w moves forward, a strafes left, s moves backward, d strafes right, j turns left, and l turns right.
The cross shows movement directions; the curved arrows show turns without changing position.
The cross and curved arrows rotate with the camera's heading while all letters stay upright.
The marker indicates directions, not movement distances or turn angles.
Use it to understand the scene layout, track movement, and plan navigation.
It does not show camera pitch. Its axes and the camera yaw are scene references, not geographic
directions; do not infer compass directions.

The path is drawn directly on this top-down map. Use it to review visited locations,
recognize repeated routes, and plan further exploration.
Magenta lines and arrows show past horizontal movement and travel direction, not camera heading.
Yellow dots mark path starts. Only successful position changes add path points; turns do not.
camera_reset retains old paths and starts a disconnected segment at the initial position.
The map is a horizontal projection: vertical movement overlaps the same map position.
The path includes the latest successful move or reset. Map framing includes all historical
positions and may change between observations; do not compare pixel coordinates across images.

Nearest video frame (<nearest_video_frame>)
This is a captured video frame matched to the current camera pose.
Use it to identify objects, textures, and appearance details that are unclear in the point cloud.
It may differ in position and viewing direction, so do not treat it as evidence of exact current
visibility or relative position. Its matching distance and angle are included in the tool result.

Evidence from the views
Use the top-down map to plan routes and locate the current camera relative to the target.
Use the first-person view to check nearby geometry, occlusion, and target visibility.
Use the reference video frame to identify objects and appearance.
Verify any passage seen in the reference frame against the current rendered views before following it.
Use camera state metadata to verify movement and rotation. When the views disagree, state
the uncertainty and obtain another observation if needed.
A camera turn angle alone does not measure an object's bearing.

Tool workflow
Start with camera_observe when you have no current observation.
Call at most one camera tool per response, inspect its result, and base the next action on the
latest observation. Observation images are attached automatically; inspect them directly.
camera_status returns position, yaw, pitch, and point radius without rendering.
camera_reset restores the initial pose and radius; use it when requested or restarting exploration.

Camera actions and units
All actions apply to the current first-person camera or its rendered point cloud.
Interpret directional keys from that camera's perspective, not the top-down image
axes or the reference video frame.
camera_action takes one key and an optional magnitude:
w: move forward; s: move backward; a: strafe left; d: strafe right.
q: move down; e: move up.
j: turn toward the camera's own left; l: turn toward its own right.
i: tilt the view up; k: tilt the view down.
+: increase rendered point radius; -: decrease rendered point radius.
Pass a single key and provide magnitude separately; do not use key sequences or combined
commands such as w0.3.
Horizontal movement is relative to the current first-person camera's horizontal heading,
so movement directions change after turning. Horizontal movement preserves height, regardless of pitch.
q/e move along the scene's vertical axis, independently of camera pitch.
w/s/a/d magnitudes use {distance_units}.
j/l/i/k magnitudes use degrees.
Defaults are {move_step} distance units and {look_step} degrees.
q/e use the fixed movement step; +/- use {point_step}.
These four keys do not accept a magnitude.
Explicit magnitudes must be positive and finite. Pitch is limited to -89.9 through 89.9 degrees.

Navigation planning
Identify the target region and choose a short route with intermediate waypoints.
Keep one current waypoint until it is reached or new evidence requires a route change.
Treat uncertain entrances and passages as hypotheses to verify.
Update the existing plan after each observation instead of reconstructing the entire layout.

Action and verification
Before each action, briefly state the current waypoint, the next action, and its expected result in English.
After the action, check whether the expected change occurred before choosing another action.
Use small movement steps near furniture, walls, and uncertain passages.
Use the current w/a/s/d marker to interpret movement directions.
Do not invent world coordinates or estimate distances from uncalibrated map pixels.
The j/l arcs indicate rotation, not movement directions or target bearings.

Recovery
If three consecutive actions neither advance the current waypoint nor provide useful new information,
stop the current approach and revise the route.
If a nearby surface fully obscures the first-person view, first retreat toward the last clear viewpoint.
Avoid repeated opposite turns or revisiting a failed approach without new evidence.
Changing point radius does not resolve occlusion caused by being inside or against a surface.
Prefer visible passages around obstacles; absence of collision detection does not prove walkability.

Completion
For navigation tasks, finish when the camera is in the requested region and the requested object
is clearly visible in the current first-person view with the required viewing direction.
Once this condition is satisfied, stop making unnecessary adjustments.
For spatial questions, answer once you have enough evidence, and clearly state uncertainty.'''


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
        backend.client = backend.client.with_options(timeout=180, max_retries=0)
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
