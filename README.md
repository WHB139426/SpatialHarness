# SpatialHarness

在远程 Linux 服务器上，通过 Blender 后台渲染交互查看由视频重建的点云。使用 CPU 渲染，无需桌面环境；每次相机操作后生成 PNG。

`main_env.py` 提供手动相机交互并承载 Blender worker；`main_agent.py` 提供 Qwen agent 的空间问答。两个入口复用同一套重建、渲染、相机控制和参数解析。底层环境模块统一放在 `scene/` 下。

## 代码结构

```text
main_env.py              # 默认配置、启动流程、组装相机会话与终端交互
main_agent.py            # Qwen 配置、重建启动、相机工具组装与 agent 提问循环
scene/
  reconstruction/
    reconstruct.py       # 视频抽帧、VGGT 推理、保存点云和相机参数
    metric_scale.py      # DA3 米制尺度估计
  camera_control/
    actions.py           # 解析相机命令
    navigation.py        # 计算并应用相机位姿和点半径
    session.py           # 相机状态、动作执行、重置与失败回滚
    bridge.py            # 普通 Python 与 Blender 的 JSON 通信
  rendering/
    renderer.py          # 场景初始化、三栏渲染与观察结果保存
    scene.py             # 点云导入、材质、地面估计、内参和初始相机位姿
    views.py             # 俯瞰视图、位置朝向标记、准星和文字标签
    reference_frame.py   # 最近原视频帧匹配
    stitch.py            # 三栏图片拼接
models/                  # 本地模型源码
assets/                  # 字体与标签图片
```

修改动作解析或移动方式看 `scene/camera_control/`，修改图片显示看 `scene/rendering/`，修改抽帧和重建看 `scene/reconstruction/`。调用关系为 `main_env.py` → `CameraSession` → `SceneRenderer`：相机会话执行动作并维护状态，渲染器根据当前位姿生成观察结果，终端交互调用会话方法。重建结果通过 PLY、相机 JSON 和抽帧文件传给查看器。

`CameraSession` 提供 `observe()`、`execute(key, magnitude=None)`、`status()` 和 `reset()`。观察、动作和重置返回包含图片路径与相机状态的记录；状态查询只返回相机状态。动作成功生成观察结果后才提交状态，失败时恢复之前的相机位姿。

环境默认配置在 `main_env.py` 顶部，agent 默认配置在 `main_agent.py` 顶部。初始相机位姿由场景初始化计算，并作为位置和方向传给 `CameraSession`；会话负责动作和状态，不计算地面或眼高。

## Agent 核心

从 `AgentHarness` 迁入的最小核心位于 `agent/`，不依赖重建模型或 Blender：

```text
agent/
  loop.py                # 模型调用、工具执行、消息历史和可选 JSON 记录
  types.py               # Model/ChatProtocol 类型约定、ModelInput、Tool、ToolOutput
  backend.py             # vLLM 服务请求，不加载本地模型权重
  protocols/qwen.py      # Qwen 模板参数、thinking 和 XML 工具调用解析
  tools.py               # view_media 和绑定 CameraClient 的相机工具
```

`Agent` 接收 backend、protocol、工具列表及显式配置，`run(prompt)` 持续执行模型与工具调用直至返回回答；`prompt` 可以是文本或多模态内容列表。工具可以通过 `ToolOutput.messages` 附加视觉观察。独立的 `TOOLS` 仅含 `view_media`；`create_tools(camera)` 返回绑定一个运行中 `CameraClient` 的五个工具：

| 工具 | 参数与行为 |
| --- | --- |
| `view_media` | `path`：附加本地图片或视频 |
| `camera_action` | `key` 和可选 `magnitude`：执行一步动作，返回完整观察记录并自动附加三张独立图片 |
| `camera_observe` | 无参数：渲染当前位姿，返回观察记录与三张独立图片 |
| `camera_status` | 无参数：只返回相机状态，不渲染 |
| `camera_reset` | 无参数：恢复初始位姿和点半径，返回观察记录与三张独立图片 |

`key` 支持 `wasdqeijkl+-`。`magnitude` 只用于 WASD 移动距离和 IJKL 转角，单位沿用环境，省略时使用配置步长。动作结果已经附加图片，无需再调用 `view_media` 查看同一张观察图。`create_tools(camera)` 不启动或关闭 worker，生命周期由调用方管理；工具列表没有 coding、shell、搜索或关闭相机工具。向 `Agent` 传入 `tools=create_tools(camera)` 即可使用这一组工具。

构造时由调用方传入系统提示词、最大步骤数和图片保留数量（`-1` 表示不限制）；默认不写文件。提供 `conversation_path` 时保存当前对话 JSON，新建 agent 从新对话开始，不自动恢复旧记录。`reset()` 仅重置 agent 消息历史，与相机重置无关。图片历史限制不处理视频附件。

相机观察在一条消息中按 `first_person_view`、`top_down_view`、`nearest_video_frame` 的顺序附加三张图片，使用英文开闭标签和说明。图片由模型服务分别预处理，三栏拼接 PNG 只供人工查看，不自动附加给模型。历史裁剪按整条消息中的图片一起处理，保留其他文字，不会拆散一组三图观察。

三图输入已通过真实 `qwen3.8-flash-next` + Blender 检查：使用合成点云 fixture 和默认视频的原始帧，两张渲染图为 960×960，参考帧为 640×480；三次问答覆盖转向、重置、状态查询及超过四组观察后的完整组裁剪。记录在 [report.json](outputs/three_image_live_d286ldmy/report.json)。渲染和状态保存失败时的文件清理、状态回滚另通过 [Blender 检查](outputs/three_image_check_of8rnicj/report.json)。本轮没有重跑 GPU 重建，也未评估拆图后的空间推理精度提升。

`VLLMBackend` 的模型名称、服务地址和生成参数由调用方传入。它沿用原仓库的原始工具调用文本方式：服务端不要启用自动工具调用解析，工具文本由 protocol 解析。Qwen protocol 目前支持原仓库 Qwen3.8 使用的 `<tool_call><function=...><parameter=...>` 格式，不代表所有 Qwen 模型都使用同一格式。本地媒体通过 `file://` URI 传递，推理服务需要能访问这些文件并允许读取相应目录。

backend 负责服务接口，protocol 负责模型消息与输出格式。以后添加模型时可以替换这两个实现，复用循环和工具。`main_agent.py` 已组装 agent 与相机工具，原 `main_env.py` 保留手动相机交互。

已用本机 vLLM 的 `qwen3.8-27b` 完成真实文本问答、三栏观察图与 4 秒视频验证；图片和视频均通过 `view_media` 调用后进入模型请求，再返回回答。验证记录在 [report.json](outputs/agent_check_t0hsnr74/report.json)。这项验证不包含相机控制或 Blender 通信。

## 启动 agent 空间问答

先保持 Qwen vLLM 服务运行，再从项目目录启动：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/hw139426/workspace/miniconda3/envs/spatial_agent/bin/python main_agent.py
```

入口先在子进程中从视频重建，成功后释放重建进程，再启动 Blender worker 和 agent。在 `agent>` 后输入空间问题，例如“床在当前朝向的哪一侧？请转头确认”。模型按需观察和移动；每步观察自动回传图片。同一个 agent 和 worker 连续处理提问，输入 `/exit`、`quit`、`exit` 或终端 EOF 可退出；会话关闭时释放 Blender 和模型客户端。

模型当前使用用户选定的 `qwen3.8-flash-next`、`http://127.0.0.1:8000/v1`，生成上限 8192 tokens，最多 100 次模型调用/提问，图片预算为 12 张，可容纳最近四组三图相机观察。模型参数、thinking 设置、服务超时和 system prompt 直接在 `main_agent.py` 顶部修改。环境参数复用 `main_env.py` 的解析器，例如：

```bash
python main_agent.py --video /path/to/video.mp4 --resolution 480 --samples 4
python main_agent.py --help
```

每次运行创建新的 `outputs/camera_<时间戳>/`，保存重建、观察 PNG/JSON、`state.json`、`render.log` 和 `conversation.json`。会话顶层的 PNG 只保留拼接预览；agent 使用的独立第一人称图和俯视图放在 `.views/` 子目录，参考帧仍在 `reconstruction/` 中。不自动恢复旧会话。默认 Metric 开启时移动距离近似为米；使用 `--metric-weights none` 时提示词会说明距离是 VGGT 相对单位。转角单位为度，yaw 使用场景参考轴，不代表地理方位。agent 只获得相机与媒体工具。

新入口已通过子进程重建 fixture + 真实 Qwen/Blender 的连续两次提问、移动、重置和退出检查，也通过失败及中断清理检查，记录在 [report.json](outputs/agent_entry_check_29adu93o/report.json)。验证覆盖工具闭环和资源清理，不代表空间推理精度验证。完整视频的 GPU 重建沿用原实现，本轮没有重跑。入口最初新增时保留了原环境入口；现在两个入口已统一命名为 `main_env.py` 和 `main_agent.py`。

## Python 与 Blender 通信

`scene.camera_control.bridge.CameraClient` 可以在普通 Python 中启动并控制持续运行的 Blender worker，不需要导入 `bpy`。它接收完整的 worker 启动命令、日志路径和超时时间；场景初始化完成后，`initial_state` 保存初始状态，此时尚未渲染。

客户端提供 `observe()`、`execute(key, magnitude=None)`、`status()`、`reset()` 和 `close()`。前四项对应现有 `CameraSession` 方法；观察、动作和重置返回含 PNG 路径的完整记录，状态查询不渲染。使用 `with` 会在结束时关闭子进程。相机动作仍是一项按键动作，例如 `execute('w', 0.5)`，不接收组合命令字符串。

Blender worker 仍运行 `main_env.py`。客户端自动追加隐藏参数 `--response-fd`，让内部 `--worker` 分支进入 JSON 循环；请求通过标准输入发送，响应走独立的继承管道，Blender 标准输出与错误输出写入日志。协议为同步串行的逐行 JSON，请求形如 `{"op": "execute", "params": {"key": "w", "magnitude": 0.5}}`；响应包含 `ok`，成功时有 `result`，失败时有 `error`。动作错误可继续请求；通信超时或管道断开会关闭 worker，避免错配后续响应。超时默认配置 `CAMERA_TIMEOUT = 300` 放在 `main_env.py` 顶部，由调用方传入客户端。

下面的普通 Python 调用示例创建新输出会话，并复用已有重建。按需替换 `existing`，新会话保存本次观察和状态：

```python
from pathlib import Path
import main_env
from scene.camera_control.bridge import CameraClient

existing = Path('outputs/camera_20261005_100405_131445/reconstruction').resolve()
session_dir = main_env.create_session_dir(Path(main_env.OUTPUTDIR).resolve())
(session_dir / 'reconstruction').symlink_to(existing, target_is_directory=True)
command = [main_env.BLENDER, '--background', '--factory-startup', '--python-exit-code', '1',
           '--python', str(main_env.ROOT / 'main_env.py'), '--', '--worker',
           '--session-dir', str(session_dir)]
with CameraClient(command, log_path=session_dir / 'render.log', timeout=main_env.CAMERA_TIMEOUT) as camera:
    record = camera.observe()
    print(record['image'])
    record = camera.execute('w', 0.5)
    record = camera.execute('j', 30)
    record = camera.reset()
```

已用已有真实点云和 Blender 验证观察、移动、转头、重置、失败回滚及退出，结果在 [report.json](outputs/bridge_check_559qfnmc/report.json)。原来的 `camera>` 手动交互也通过回归检查。

另用临时脚本完成真实 `qwen3.8-27b` + Blender 联合验证：模型通过工具观察、前进 0.3 米、左转 30°、查询状态并重置；每张新观察均进入后续模型请求，重置状态及图片与初始一致。随后模型根据观察自行选择右转 20°，接收新图并回答床位于初始朝向右侧。两项通过，共 10 次模型请求、6 张 1440×480 观察图，worker 正常退出。记录在 [report.json](outputs/agent_camera_check_eoq59n1v/report.json)，完整消息在同目录 `conversation.json`。本次仅作样例联合验证，没有修改业务代码或将 agent 接入 `main_env.py`。

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

`main_env.py` 顶部设置输入视频 `VIDEO`、抽帧速率 `FPS`、最多抽取的帧数 `MAX_NUM_FRAMES`、米制尺度采样帧数 `METRIC_FRAMES`、VGGT 权重 `REC_WEIGHTS` 和 DA3 Metric 权重目录 `METRIC_WEIGHTS`。每次运行都会从视频重建，再打开查看器；运行时先创建带时间戳的相机会话目录，PLY、相机 JSON 和抽帧都保存在该会话的 `reconstruction/` 子目录中。从首帧开始按 `FPS` 指定的时间间隔抽帧，到视频结束或达到 `MAX_NUM_FRAMES` 为止；例如 `FPS = 2.0` 表示每秒抽取约两帧。目标 FPS 不能高于视频原始帧率，且至少要能抽到两帧。之后使用 VGGT 推理、40% 深度置信度过滤和 0.01 体素下采样。相机条目保留内外参及原视频帧号。

在 `SpatialHarness` 目录执行重建并打开交互查看器：

```bash
python main_env.py
```

每次运行都新建 `OUTPUTDIR/camera_<时间戳>/`；其中 `reconstruction/vggt_reconstruction.ply`、`reconstruction/vggt_cameras.json` 和 `reconstruction/frames/` 保存本次重建结果，相机渲染 PNG 和状态 JSON 放在会话目录顶层。重建使用 `models/vggt_omega/` 和 `models/depth_anything_3/` 中的本地模型源码；模型权重路径由配置中的 `REC_WEIGHTS` 和 `METRIC_WEIGHTS` 指定。运行环境需要 PyTorch、OpenCV、Open3D 以及 DA3 的依赖。相机 JSON 的 `image_path` 指向同一 `reconstruction/` 目录下的 `frames/`；重复运行会新建会话，不覆盖之前的重建和图片。可用 `--fps`、`--max-num-frames`、`--video`、`--checkpoint`、`--metric-weights` 覆盖重建配置。`main_env.py` 和 `main_agent.py` 都在子进程中调用同一重建函数，使用启动脚本的 Python 环境，重建进程结束后再启动 Blender。

默认运行时，DA3 Metric 从最多 `METRIC_FRAMES = 32` 个均匀选取的帧估计一个全场景尺度，再同时缩放 VGGT 深度与相机外参平移；PLY 和相机 JSON 因而使用近似米制尺度。终端同时打印各帧尺度的四分位距（IQR），用于观察估计是否稳定；JSON 中的 `metric_scale` 记录乘数。尺度估计失败会报错；如需保持原来的 VGGT 相对尺度，使用 `--metric-weights none`。启用 Metric 时，查看器的移动距离可近似按米理解；尺度精度仍取决于 DA3 预测。

## 启动交互脚本

用普通 Python 启动，脚本会自动调用 Blender，无需在当前 Python 环境安装 `bpy`。

运行以下命令，会从 `VIDEO` 重建点云并进入相机交互：

```bash
python main_env.py
```

脚本自动识别无面的点云，并将其显示为带原始顶点颜色的可渲染点。启动后从视频第一帧相机所在位置附近、地面上方约 1 米处水平向前看，然后显示 `camera>` 提示符。Blender 在交互期间保持运行。

如果 Blender 安装在其他位置，添加 `--blender /实际路径/blender`。

初始高度由 `main_env.py` 顶部的 `EYE_HEIGHT = 1.0` 控制。起点参考第一帧相机，投影到估计地面后沿上方向升高；初始朝向参考该帧，俯仰角为 0。没有可靠地板平面时使用低处点近似地面，日志会注明。米制尺度和地板估计都有误差，因此高度是近似值。

## 第一人称相机操作

在 `camera>` 后输入一个或连续多个按键并回车。按键从左到右依次执行，每个按键都生成一张 PNG；`reset`、`status`、`help` 和 `quit` 单独输入。相机像第一人称视角一样移动；不写数字时，`wasd` 的默认移动距离由 `main_env.py` 顶部的 `MOVE_STEP` 指定，`ijkl` 的默认转动角度由 `LOOK_STEP` 指定。也可以在每个按键后紧接一个正数，单独指定该步的幅度，例如 `w0.5` 或 `j30`，无需输入单位字符。`w0.5` 和 `MOVE_STEP` 使用同一个场景距离单位；默认启用 Metric 时约为米，使用 `--metric-weights none` 时是 VGGT 的相对单位。`ijkl` 的幅度单位是度；`q/e` 和点大小仍使用 `main_env.py` 顶部的固定步长。

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

每次操作都会渲染第一人称和俯瞰视角，并把匹配的原视频帧拼成一张三栏 PNG：左侧 “FIRST PERSON” 是带准星的第一人称画面；中间 “TOP DOWN” 是正交俯瞰图；右侧 “NEAREST VIDEO FRAME” 是位置和朝向最接近的原视频抽帧，保持原始宽高比并留黑边，不裁切。英文标签使用项目自带的 [DejaVu Sans 字体](assets/fonts/DejaVuSans-Bold.ttf)（[许可证](assets/fonts/LICENSE.txt)），不依赖系统字体路径。俯瞰图中的橙色圆点标示当前相机位置，三短一长的十字标示 WASD 水平移动方向：蓝色长臂 `w` 带箭头指向前方，短臂 `a/s/d` 分别向左、后、右。绿色弧形箭头表示 `j` 向左转（俯视图逆时针）、`l` 向右转（顺时针）。十字和弧线随相机转向，六个字母保持正立并带深色底，低分辨率时设置最小显示尺寸。标记只表达方向，不代表移动距离或转角大小。所有按键控制同一台第一人称相机，左侧和中间画面同步更新，右侧根据当前相机姿态重新匹配。俯瞰图只显示水平朝向；`i/k` 改变的俯仰角可从左侧画面看到。

每次渲染后还会从本次重建的 `vggt_cameras.json` 中查找位置和镜头朝向最接近的原视频抽帧。终端打印该 JPG 路径、位置距离和朝向夹角；同名渲染 JSON 的 `nearest_frame` 字段也记录这些信息。匹配分数为 `(位置距离 / 0.5)^2 + (朝向夹角 / 20°)^2`；只比较位置与镜头朝向，不使用内参或画面内容。最近帧可能仍与当前视角相差很大，因此请同时查看距离和夹角。

`j/l` 围绕估计出的场景上方向转动，`i/k` 控制俯仰角，限制在 -89.9° 到 89.9°。第一人称镜头根据本次 `vggt_cameras.json` 中各帧的归一化内参取中位数，设置固定的透视视野；这样最近原视频帧切换时不会突然变焦。第一人称图直接渲染为方形：保留原视频对应的水平视野和中央区域投影，向上下扩展可见范围，不拉伸画面。同名渲染 JSON 的 `intrinsics` 字段记录实际使用的像素内参。镜头不做碰撞检测；启用 Metric 时，输入的移动距离按米解释，其准确度取决于尺度估计。

## 点云大小

初始点半径默认为 0.015 个场景单位。可在启动时指定绝对半径：

```bash
python main_env.py --point-radius 0.003
```

交互时输入 `+` 或 `-`，每次分别增加或减少 `POINT_STEP = 0.005`；半径不能降到 0 或以下。`reset` 会恢复启动时的点半径。

## 场景上方向

不传 `--up` 时，脚本使用本次重建的 PLY 和相机参数临时估计上方向，不额外保存方向配置。

脚本用点云寻找地板候选平面，再利用相机位置和第一帧画面上方向判断地板正反面。启动时会打印最终 `Scene up` 和来源。如果没有可靠的地板，会退回第一帧相机的画面上方向；地面估计发生异常时直接报错。第一帧相机方向只是近似方向，不保证与地板垂直。

重新生成当前视频的 VGGT 重建：

```bash
python main_env.py
```

如果自动估计不合适，可用 `--up X Y Z` 显式指定，手动值优先：

```bash
python main_env.py --up 0 -1 0
```

`--up` 只决定镜头转头时的参考上方向，不修改点坐标。`j/l` 围绕该方向转动，`i/k` 控制抬头或低头；`w/s` 沿当前视线在水平面上的投影移动。点云缺少清晰地板时，估计可能退回到相机方向。

## 查看渲染结果

在 `SpatialHarness` 目录启动时，每次都会在 `outputs/` 下新建一个 `camera_时间戳/` 目录。该目录同时包含 `reconstruction/` 和本次渲染的 PNG、状态 JSON；每次渲染打印完整 PNG 路径，历史会话不会被覆盖。

- `0001_initial.png`、`0002_w.png` 等：渲染图片。
- 同名 `.json`：生成该图片的命令、相机参数及最近原视频抽帧的路径和匹配误差。
- `state.json`：最近一次成功渲染的第一人称相机位置与朝向；重新启动时仍从场景内的初始视点开始。
- `render.log`：Blender 导入和渲染日志。

拼接图的左侧中央显示小型白色十字准星（黑色描边），中间俯瞰图显示相机的地图位置与水平朝向。两张 Blender 临时渲染图仅用于拼接，完成后会自动删除；原视频抽帧仍保存在 `reconstruction/frames/`。

在 VS Code Remote SSH 中打开对应 PNG 即可查看；普通 SSH 终端不会自动显示图片，也可以下载到本地查看。

## 渲染参数

`main_env.py` 顶部的 `RESOLUTION = 960` 控制第一人称图和俯视图的默认边长，均直接渲染为 960×960；`--resolution` 可以覆盖它，两个入口共用此默认值。agent 收到两张独立渲染图和未经缩放的原视频帧，当前默认视频帧为 640×480。它们的实际编码尺寸由模型服务的预处理配置决定。人工预览仍将原视频帧保持宽高比、居中放入第三栏并可能留黑边，最终 PNG 为 2880×960；Blender 每个视角的采样数为 16。VGGT 内参来自预处理后的图像，是模型估计值，和原视频帧的像素对齐只可视为近似。快速预览示例：

```bash
python main_env.py --resolution 480 --samples 4
```

用 `--output-dir /输出目录` 同时指定重建结果和相机会话的父目录；用 `python main_env.py --help` 查看所有启动参数。
