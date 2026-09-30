# SpatialHarness

在远程 Linux 服务器上，通过 Blender 后台渲染交互查看由视频重建的点云。使用 CPU 渲染，无需桌面环境；每次相机操作后生成 PNG。

入口为 `main.py`；准星、俯瞰视角、上方向估计、视频重建和场景渲染模块放在 `camera_control/` 中。

## 安装 Blender

下载并解压 Blender 4.5.13 LTS 的 Linux x64 便携版，无需 sudo：

```bash
wget -c https://download.blender.org/release/Blender4.5/blender-4.5.13-linux-x64.tar.xz
tar -xf blender-4.5.13-linux-x64.tar.xz
```

验证版本和后台 Python 环境：

```bash
./blender-4.5.13-linux-x64/blender --version

./blender-4.5.13-linux-x64/blender \
  --background --factory-startup --python-exit-code 1 \
  --python-expr "import bpy; print('Blender background OK:', bpy.app.version_string)"
```

## 从视频生成点云与相机参数

`main.py` 顶部设置输入视频 `VIDEO`、抽帧速率 `FPS`、最多抽取的帧数 `MAX_NUM_FRAMES`、米制尺度采样帧数 `METRIC_FRAMES`、VGGT 权重 `REC_WEIGHTS` 和 DA3 Metric 权重目录 `METRIC_WEIGHTS`。每次运行都会从视频重建，再打开查看器；PLY 和相机 JSON 的路径在运行时由视频文件名生成。从首帧开始按 `FPS` 指定的时间间隔抽帧，到视频结束或达到 `MAX_NUM_FRAMES` 为止；例如 `FPS = 2.0` 表示每秒抽取约两帧。目标 FPS 不能高于视频原始帧率，且至少要能抽到两帧。之后使用 VGGT 推理、40% 深度置信度过滤和 0.01 体素下采样。相机条目保留内外参及原视频帧号。

在 `SpatialHarness` 目录执行重建并打开交互查看器：

```bash
python main.py
```

只运行重建、暂不打开 Blender：

```bash
python -m camera_control.reconstruct
```

输出在 `OUTPUTDIR/reconstructions/<视频文件名>/`；例如 `VIDEO` 指向 `scene0651_02.mp4` 时，输出目录为 `outputs/reconstructions/scene0651_02/`。重建使用 `models/vggt_omega/` 和 `models/depth_anything_3/` 中的本地模型源码；模型权重路径由顶部的 `REC_WEIGHTS` 和 `METRIC_WEIGHTS` 指定。运行环境需要 PyTorch、OpenCV、Open3D 以及 DA3 的依赖。抽出的 JPG 保存在同一重建目录下的 `frames/`，相机 JSON 的 `image_path` 记录相对路径；重复运行会更新同名图片。可用 `--fps`、`--max-num-frames`、`--video`、`--checkpoint`、`--metric-weights` 覆盖重建配置。运行重建时使用启动脚本的 Python 环境。

默认运行时，DA3 Metric 从最多 `METRIC_FRAMES = 32` 个均匀选取的帧估计一个全场景尺度，再同时缩放 VGGT 深度与相机外参平移；PLY 和相机 JSON 因而使用近似米制尺度。终端同时打印各帧尺度的四分位距（IQR），用于观察估计是否稳定；JSON 中的 `metric_scale` 记录乘数。尺度估计失败会报错；如需保持原来的 VGGT 相对尺度，使用 `--metric-weights none`。启用 Metric 时，查看器的移动距离可近似按米理解；尺度精度仍取决于 DA3 预测。

重复运行会更新该视频对应目录中的 PLY、JSON 和同名抽帧图片。

## 启动交互脚本

用普通 Python 启动，脚本会自动调用 Blender，无需在当前 Python 环境安装 `bpy`。

运行以下命令，会从 `VIDEO` 重建点云并进入相机交互：

```bash
python main.py
```

脚本自动识别无面的点云，并将其显示为带原始顶点颜色的可渲染点。启动后从视频第一帧相机所在位置附近、地面上方约 1 米处水平向前看，然后显示 `camera>` 提示符。Blender 在交互期间保持运行。

如果 Blender 安装在其他位置，添加 `--blender /实际路径/blender`。

初始高度由 `main.py` 顶部的 `EYE_HEIGHT = 1.0` 控制。起点参考第一帧相机，投影到估计地面后沿上方向升高；初始朝向参考该帧，俯仰角为 0。没有可靠地板平面时使用低处点近似地面，日志会注明。米制尺度和地板估计都有误差，因此高度是近似值。

## 第一人称相机操作

在 `camera>` 后输入一个或连续多个按键并回车。按键从左到右依次执行，每个按键都生成一张 PNG；`reset`、`status`、`help` 和 `quit` 单独输入。相机像第一人称视角一样移动；不写数字时，`wasd` 的默认移动距离由 `main.py` 顶部的 `MOVE_STEP` 指定，`ijkl` 的默认转动角度由 `LOOK_STEP` 指定。也可以在每个按键后紧接一个正数，单独指定该步的幅度，例如 `w0.5` 或 `j30`，无需输入单位字符。`w0.5` 和 `MOVE_STEP` 使用同一个场景距离单位；默认启用 Metric 时约为米，使用 `--metric-weights none` 时是 VGGT 的相对单位。`ijkl` 的幅度单位是度；`q/e` 和点大小仍使用脚本顶部的固定步长。

| 按键 | 镜头动作 |
| --- | --- |
| `w` / `s` | 沿当前朝向水平前进 / 后退；例如 `w0.5` 前进 0.5 个场景单位（米制重建时约 0.5 米） |
| `a` / `d` | 沿当前镜头的左右方向平移；例如 `a0.2` 左移 0.2 个场景单位（米制重建时约 0.2 米） |
| `q` / `e` | 沿场景上轴下降 / 上升，每次移动 `MOVE_STEP` 个场景单位 |
| `j` / `l` | 原地向左 / 向右转头；例如 `j30` 左转 30 度 |
| `i` / `k` | 原地向上 / 向下看；例如 `i10` 抬头 10 度 |
| `+` / `-` | 点云半径增加 / 减少 0.005 个场景单位 |
| `reset` | 恢复初始相机位置、朝向和点半径 |
| `status` | 打印相机位置、yaw、pitch 和点半径，不渲染 |
| `help` | 显示按键说明 |
| `quit` 或 `exit` | 退出 |

例如输入 `wwww` 会按默认距离连续前进四次；输入 `w0.5a0.2j30` 会依次前进 0.5 个场景单位、左移 0.2 个场景单位、左转 30 度。原来的 `waij` 仍可用，也可以连续调整点大小：

```text
waij
++
reset
quit
```

每次操作都会渲染第一人称和俯瞰视角，再左右拼接为一张 PNG：左侧标注 “FIRST PERSON”，是带准星的第一人称画面；右侧标注 “TOP DOWN”，是从场景上方向观察的正交俯瞰图。英文标签使用项目自带的 [DejaVu Sans 字体](assets/fonts/DejaVuSans-Bold.ttf)（[许可证](assets/fonts/LICENSE.txt)），不依赖系统字体路径。俯瞰图中的橙色圆点标示当前相机在地图上的投影位置，蓝色箭头表示水平朝向。所有按键控制同一台第一人称相机，两侧画面同步更新。俯瞰图只显示水平朝向；`i/k` 改变的俯仰角可从左侧画面看到。

`j/l` 围绕估计出的场景上方向转动，`i/k` 控制俯仰角，限制在 -89.9° 到 89.9°。第一人称镜头使用 12 mm 固定焦距的透视投影，不做碰撞检测；启用 Metric 时，输入的移动距离按米解释，其准确度取决于尺度估计。

## 点云大小

初始点半径默认为 0.015 个场景单位。可在启动时指定绝对半径：

```bash
python main.py --point-radius 0.003
```

交互时输入 `+` 或 `-`，每次分别增加或减少 `POINT_STEP = 0.005`；半径不能降到 0 或以下。`reset` 会恢复启动时的点半径。

## 场景上方向

不传 `--up` 时，脚本使用本次重建的 PLY 和相机参数临时估计上方向，不额外保存方向配置。

脚本用点云寻找地板候选平面，再利用相机位置和第一帧画面上方向判断地板正反面。启动时会打印最终 `Scene up` 和来源。如果没有可靠的地板，会退回第一帧相机的画面上方向；估计异常时会退回脚本顶部的 `UP = [0, -1, 0]`。回退值只是近似方向，不保证与地板垂直。

重新生成当前视频的 VGGT 重建：

```bash
python main.py
```

如果自动估计不合适，可用 `--up X Y Z` 显式指定，手动值优先：

```bash
python main.py --up 0 -1 0
```

`--up` 只决定镜头转头时的参考上方向，不修改点坐标。`j/l` 围绕该方向转动，`i/k` 控制抬头或低头；`w/s` 沿当前视线在水平面上的投影移动。点云缺少清晰地板时，估计可能退回到相机方向。

## 查看渲染结果

在 `SpatialHarness` 目录启动时，每次都会在 `outputs/` 下新建一个 `camera_时间戳/` 目录。每次渲染打印完整 PNG 路径，历史图片不会被覆盖。

- `0001_initial.png`、`0002_w.png` 等：渲染图片。
- 同名 `.json`：生成该图片的命令和相机参数。
- `state.json`：最近一次成功渲染的第一人称相机位置与朝向；重新启动时仍从场景内的初始视点开始。
- `render.log`：Blender 导入和渲染日志。

拼接图的左侧中央显示小型白色十字准星（黑色描边），右侧显示相机的地图位置与水平朝向。中间的两张原始渲染图仅用于拼接，完成后会自动删除。

在 VS Code Remote SSH 中打开对应 PNG 即可查看；普通 SSH 终端不会自动显示图片，也可以下载到本地查看。

## 渲染参数

默认每个视角分辨率为 960×960，拼接后的 PNG 为 1920×960；每个视角的采样数为 16。快速预览示例：

```bash
python main.py --resolution 480 --samples 4
```

用 `--output-dir /输出目录` 同时指定重建结果和相机会话的父目录；用 `python main.py --help` 查看所有启动参数。

## TODO: Agent camera-control interface (draft)

This is a proposed interface for a future agent. The repository does not yet expose these functions to an agent. A tool adapter will need to send the corresponding command to the running camera session and return its output.

### Draft system prompt

```text
You are a camera-navigation agent exploring a reconstructed 3D point-cloud scene. Use the camera tools to understand the scene layout and answer the user's spatial questions.

Every camera-changing tool returns one combined image: FIRST PERSON on the left and TOP DOWN on the right. The left image shows the camera's view and a center crosshair. The right image shows the whole scene, an orange dot for the camera's projected position, and a cyan arrow for its horizontal heading. Both views reflect the same camera state.

Use the top-down view to plan movement and the first-person view to inspect objects and openings. Treat gaps and irregular surfaces in the point cloud as uncertain reconstruction, not automatically as free space. There is no collision detection. Use small movements near objects, inspect each returned image, and use status when the camera state is unclear.

The w, s, a, and d tools accept an optional positive distance in meters. Omitting it uses MOVE_STEP. The i, j, k, and l tools accept an optional positive angle in degrees. Omitting it uses LOOK_STEP. Distances share the same scene units as MOVE_STEP; they are approximately meters only when metric scaling is enabled. The q and e tools use the fixed MOVE_STEP. Point-size tools use the fixed POINT_STEP. Pitch is limited to -89.9 through 89.9 degrees.

Call tools in the order you want actions to happen. Base each next action on the latest image or status. When you have enough evidence, answer with the observed layout and clearly identify uncertain areas. Call quit only when the user asks to end the interactive session.
```

### Draft tool schema

The schema below is provider-neutral. An omitted `meters` or `degrees` property means the current `MOVE_STEP` or `LOOK_STEP` default. All supplied magnitudes must be positive and finite. The adapter maps `w({"meters": 0.5})` to `w0.5`, `j({"degrees": 30})` to `j30`, and calls with `{}` to the bare key. `increase_point_size` and `decrease_point_size` map to `+` and `-`.

```json
{
  "tools": [
    {
      "type": "function",
      "name": "w",
      "description": "Move forward horizontally in the current facing direction.",
      "parameters": {
        "type": "object",
        "properties": {
          "meters": {
            "type": "number",
            "exclusiveMinimum": 0,
            "description": "Distance in scene units (approximately meters with metric scaling)."
          }
        },
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "type": "function",
      "name": "s",
      "description": "Move backward horizontally from the current facing direction.",
      "parameters": {
        "type": "object",
        "properties": {
          "meters": {
            "type": "number",
            "exclusiveMinimum": 0,
            "description": "Distance in scene units (approximately meters with metric scaling)."
          }
        },
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "type": "function",
      "name": "a",
      "description": "Strafe left without changing heading.",
      "parameters": {
        "type": "object",
        "properties": {
          "meters": {
            "type": "number",
            "exclusiveMinimum": 0,
            "description": "Distance in scene units (approximately meters with metric scaling)."
          }
        },
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "type": "function",
      "name": "d",
      "description": "Strafe right without changing heading.",
      "parameters": {
        "type": "object",
        "properties": {
          "meters": {
            "type": "number",
            "exclusiveMinimum": 0,
            "description": "Distance in scene units (approximately meters with metric scaling)."
          }
        },
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "type": "function",
      "name": "j",
      "description": "Turn left around the scene up axis.",
      "parameters": {
        "type": "object",
        "properties": {
          "degrees": {
            "type": "number",
            "exclusiveMinimum": 0,
            "description": "Angle in degrees."
          }
        },
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "type": "function",
      "name": "l",
      "description": "Turn right around the scene up axis.",
      "parameters": {
        "type": "object",
        "properties": {
          "degrees": {
            "type": "number",
            "exclusiveMinimum": 0,
            "description": "Angle in degrees."
          }
        },
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "type": "function",
      "name": "i",
      "description": "Look up without changing position.",
      "parameters": {
        "type": "object",
        "properties": {
          "degrees": {
            "type": "number",
            "exclusiveMinimum": 0,
            "description": "Angle in degrees."
          }
        },
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "type": "function",
      "name": "k",
      "description": "Look down without changing position.",
      "parameters": {
        "type": "object",
        "properties": {
          "degrees": {
            "type": "number",
            "exclusiveMinimum": 0,
            "description": "Angle in degrees."
          }
        },
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "type": "function",
      "name": "q",
      "description": "Descend by the fixed MOVE_STEP.",
      "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "type": "function",
      "name": "e",
      "description": "Ascend by the fixed MOVE_STEP.",
      "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "type": "function",
      "name": "increase_point_size",
      "description": "Increase the point radius by the fixed POINT_STEP; maps to +.",
      "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "type": "function",
      "name": "decrease_point_size",
      "description": "Decrease the point radius by the fixed POINT_STEP; maps to -.",
      "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "type": "function",
      "name": "reset",
      "description": "Restore the initial camera pose and point radius.",
      "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "type": "function",
      "name": "status",
      "description": "Return the camera position, yaw, pitch, and point radius without rendering.",
      "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "type": "function",
      "name": "help",
      "description": "Return the available camera commands without rendering.",
      "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "type": "function",
      "name": "quit",
      "description": "End the interactive camera session.",
      "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": false
      }
    }
  ]
}
```

Camera-changing tools, including `reset`, should return the combined PNG and the updated camera-state JSON. `status` and `help` return text without rendering; `quit` ends the session. The adapter and agent integration remain TODO.
