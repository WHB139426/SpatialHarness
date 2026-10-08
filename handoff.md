# SpatialHarness 交接说明

更新日期：2026-10-08。项目根目录：`/data4/haibo/code/SpatialHarness`。

这份文件记录项目目的、当前实现和前一轮工作的决定。新 session 先读本文，再看 `main_env.py`、`README.md` 和需要修改的模块；用户后续指令优先于本文。

## 1. 项目目的与当前阶段

项目要提供一个由视频重建得到、可供 agent 自由探索的三维空间环境。目标交互是：agent 获得观察，选择移动或转头动作，环境执行动作并返回新观察，agent 根据结果继续探索和回答空间问题。

目前已实现环境底座：视频重建、米制尺度估计、点云渲染、相机移动、独立三图观察与三栏预览、状态记录和重置。`main_env.py` 提供终端 `camera>` 手动交互，`main_agent.py` 提供 `agent>` 自然语言空间问答。agent 接收三张独立图片，人工预览仍使用拼接图。`CameraSession` 在 Blender 进程中使用，普通 Python 的 agent 通过 `CameraClient` 控制它。

**已迁入最小 agent 核心、打通 Blender 通信、包装相机工具，并新增正式 agent 入口。** 用户先授权新增独立 agent 入口，随后指定两个入口命名为 `main_agent.py` 和 `main_env.py`，覆盖此前只保留一个入口的约束。`main_agent.py` 已组装重建子进程、Qwen backend/protocol、相机工具和连续提问循环，改名只同步调整文件引用与帮助文字，业务逻辑保持不变。实际工具以 `create_tools(camera)` 为准，提示词在新入口顶部，README 中旧逐按键接口草案已移除。新入口的连续提问和退出已通过重建 fixture + 真实 Qwen/Blender 检查；完整视频的 GPU 重建本轮未重跑。

**碰撞检测暂不做。** 用户刚讨论过难度，随后明确说“算了先不管碰撞检测的事情”。当前相机可以穿墙、离开点云范围，也没有物体交互、物理模拟或任务奖励机制。

## 2. 用户的明确约束与代码偏好

- **不要修改 `models/` 下任何文件。** 前一轮没有改模型源码，并用整个目录的文件哈希核对过。运行检查时使用 `PYTHONDONTWRITEBYTECODE=1`，避免向模型目录写入字节码；如果自己误改，应仅撤销自己的修改，不能覆盖用户的其他变更。
- 用户要求优化和简化代码，删除冗余、重复和过度防御。倾向于直接清楚的实现，不喜欢为了复用一点点代码而加函数、配置层或多层封装。
- **入口当前为 `main_env.py` 和 `main_agent.py`。** 用户最新指定这两个入口名称，覆盖之前的唯一入口要求；不保留旧名称的转发文件。新入口复用 `main_env.parse_args()` 与 Blender worker，不新增独立重建 CLI、第二套参数定义或 `add_reconstruction_args()`。
- **配置直接写在入口顶部。** 环境配置沿用 `main_env.py`，agent 配置在 `main_agent.py`；不恢复 `config.py` 或其他配置文件。底层配置仍由调用方传入，不导入入口；新 agent 入口为了复用环境入口的解析与启动常量而导入 `main_env`。
- `positive_float()` 和 `frame_count()` 已按用户要求删除；CLI 使用原生 `float`、`int`。不要恢复这些数值验证包装函数。
- 用户曾自行删除 `tests/` 和 `docs/`，随后已清理 README 中的失效引用。不要擅自恢复这些目录。历史验证脚本在 `/tmp/`，不是正式测试套件。
- 删防御代码时保留有实际意义的算法条件、资源释放和失败回滚，不要为了缩短代码改变结果。

## 3. 当前代码结构与职责

```text
main_env.py                     环境配置、共享参数解析、手动交互和 Blender worker
main_agent.py                   Agent 配置、重建启动、相机工具组装、连续提问
agent/
  loop.py                       独立 agent 循环、消息历史、工具执行与可选 JSON 记录
  types.py                      Model/ChatProtocol 类型约定与少量共享数据类型
  backend.py                    vLLM 请求，保留原始工具文本供 protocol 解析
  protocols/qwen.py             Qwen thinking 与 XML 工具调用解析
  tools.py                      view_media 与 create_tools(camera) 相机工具包装
scene/
  reconstruction/
    reconstruct.py              会话目录、视频抽帧、VGGT 推理、PLY/相机 JSON 写出
    metric_scale.py             DA3 Metric 全场景尺度估计
  camera_control/
    actions.py                  紧凑动作字符串解析
    navigation.py               相机位置、yaw/pitch、点半径计算与应用
    session.py                  动作执行、观察、状态提交、重置、失败回滚
    bridge.py                   CameraClient、Blender JSON 命令服务与进程清理
  rendering/
    scene.py                    点云导入、材质、渲染配置、地面/上轴、内参、初始位姿
    views.py                    俯瞰相机、位置朝向标记、准星、标签
    renderer.py                 场景组装、视图切换、渲染与观察记录保存
    reference_frame.py          最近原视频帧匹配
    stitch.py                   三栏图片拼接
models/                         本地 VGGT-Omega、Depth Anything 3 源码；禁止修改
assets/                         字体与标签资源
outputs/                        每次运行的新会话与输出
README.md                       环境、agent 与相机通信的使用说明
requirements.txt                Python 依赖
```

目录中还保留必要的 `__init__.py`。旧根目录 `camera_control/` 的实现已整理到 `scene/` 的三个职责目录。

前一轮合并了 `overhead.py`、`crosshair.py`、`view_label.py` 到 `views.py`，把 `estimate_up.py`、`intrinsics.py` 的场景初始化逻辑收进 `rendering/scene.py`。`views.py` 与 `stitch.py` 目前分开：前者操作 Blender 场景和视图元素，后者处理渲染后的图片拼接；这份结构已沿用。

## 4. 启动与进程边界

运行 `main_env.py` 后：

1. 解析参数，创建 `OUTPUTDIR/camera_<时间戳>/`。
2. 用 `multiprocessing.Process` 调用普通函数 `reconstruct(args, output_ply, output_cameras, metric_frames)`。
3. 重建进程使用启动脚本的 Python 环境；进程结束后释放模型资源。若重建失败，不启动 Blender。
4. 调用 Blender 后台运行同一份 `main_env.py`，用内部 `--worker` 模式加载本次重建结果。
5. `SceneRenderer` 初始化场景并计算初始位姿；`main_env.py` 将位置、方向及动作默认值传给 `CameraSession`。
6. 普通 worker 先输出 `initial` 观察，再进入终端循环；通信 worker 使用隐藏 `--response-fd` 进入 JSON 循环，先返回初始状态，收到观察请求时才渲染。Blender 在整个交互期间持续运行。

`--worker`、隐藏参数 `--session-dir` 和 `--response-fd` 是内部启动机制，不是第二个用户入口。当前普通启动每次都重建，没有公开的“直接打开已有重建”CLI 模式。Python 调用方可以给新会话复用已有重建，再通过 `CameraClient` 启动 worker。`state.json` 保存最近观察，但重新启动不会自动恢复该状态。

`main_agent.py` 复用同一个参数解析器，新建会话并在子进程调用同一重建函数。重建成功后，通过 `CameraClient` 启动 `main_env.py` 的通信 worker，再组装 Qwen agent 与五个工具，进入 `agent>` 连续提问。模型按需调用观察工具，启动时不预先渲染。退出时释放 worker 与模型客户端；重建失败不启动服务，重建中断会终止并回收子进程。

## 5. 重建、坐标与观察数据

重建从首帧起按 `FPS` 抽帧，达到视频末尾或 `MAX_NUM_FRAMES` 停止。VGGT-Omega 预测深度和相机参数，每帧过滤低于第 40 百分位的深度置信度，生成彩色点云，最后使用 0.01 体素下采样。

默认 DA3 Metric 从最多 `METRIC_FRAMES` 个均匀选择的帧估计尺度：每帧在有效区域拟合比例，取有效帧尺度中位数，同时缩放深度和相机外参平移。输出近似米制坐标；`--metric-weights none` 则保留 VGGT 相对单位。尺度失败会报错，不静默使用相对尺度。`metric_scale.py` 中 DA3 调用的 `export_feat_layers=[0]` 已对实际 checkpoint 验证过，不能仅凭表面上“多余”就删掉。

相机 JSON 的 `extrinsic` 是 world-to-camera。相机中心为 `-R.T @ t`，原视频相机的前向是相机坐标 `+Z`。Blender 相机看向本地 `-Z`，相应转换已在位姿与导航中处理。

场景上方向优先从点云地板候选平面估计；无可靠平面时使用第一帧相机上方向和低处 5% 点近似地面。真正的算法异常直接报错，不用宽泛异常捕获吞掉。初始位置参考第一帧相机，投影到地面后沿上方向升高 `EYE_HEIGHT`；初始朝向参考第一帧，pitch 为 0。`--up X Y Z` 可以覆盖导航参考上轴。

每次观察保存三栏 PNG：

- 左：带准星的第一人称点云视图。
- 中：正交俯瞰图，标记相机投影位置与水平朝向。
- 右：位置与朝向最接近的原视频抽帧，保持原始宽高比并留黑边。

最近帧匹配分数为 `(位置距离 / 0.5)^2 + (朝向夹角 / 20°)^2`，仅比较位姿；右栏不是当前视角的精确实拍图，匹配距离与角度会记录下来。第一人称使用归一化 VGGT 内参的中位数，保持固定视野，输出方形画面；向上下扩展视野而不是拉伸视频投影。

默认每栏 960×960，合成 PNG 为 2880×960。Blender 使用 Cycles CPU 渲染，8 线程、16 samples；模型推理与渲染使用不同环境。

`RESOLUTION = 960` 已移到 `main_env.py` 顶部，`--resolution` 复用它作为默认值。第一人称与俯视图按这个边长分别保存；agent 使用这两张独立 PNG 和原始参考帧，不使用拼接预览。当前默认视频的参考帧为 640×480，保持原尺寸。一条观察消息含三个英文视图标签及图片，明确前两图是当前状态、第三图是匹配参考帧。实际视觉编码尺寸仍取决于服务端预处理。

```text
outputs/camera_<时间戳>/
  reconstruction/
    vggt_reconstruction.ply
    vggt_cameras.json
    frames/frame_<原视频帧号>.jpg
  0001_initial.png
  0001_initial_first_person.png
  0001_initial_top_down.png
  0001_initial.json
  0002_<动作>.png / .json
  state.json
  render.log
```

观察 record 包含 `command`、`views`、`layout`、`state`、`camera_position`、`camera_forward`、`lens_mm`、`intrinsics`、`nearest_frame`、`image`、`images` 和 `input`。`nearest_frame.image_path` 是原视频帧路径，`image` 是三栏 PNG 预览路径；`images` 按 `first_person`、`top_down`、`nearest_video_frame` 提供独立图片路径。历史观察保留，`state.json` 通过临时文件替换随最近成功观察更新；失败时清理本次新文件，不删除参考帧。

## 6. 已有动作接口

`CameraSession` 提供：

```python
session.observe()                         # 当前位姿渲染，返回观察 record
session.execute('w', magnitude=0.5)       # 一步动作，返回观察 record
session.status()                         # 状态副本，不渲染
session.reset()                          # 恢复初始状态并渲染，返回 record
```

状态字段为 `position`、`yaw`、`pitch`、`point_radius`。执行动作时先应用候选状态并渲染，成功后提交；失败则恢复原相机状态。初始位姿属于场景初始化逻辑，不由 session 再计算地面。

| 输入 | 行为 |
| --- | --- |
| `w/s`、`a/d` | 水平前后、左右移动，可附距离，例如 `w0.5` |
| `q/e` | 沿场景上轴下降/上升，固定使用 `MOVE_STEP` |
| `j/l`、`i/k` | 左右、上下转头，可附角度，例如 `j30` |
| `+/-` | 调节点半径，固定使用 `POINT_STEP` |
| `reset` | 恢复初始位置、朝向与点半径，并渲染 |
| `status` | 输出状态，不渲染 |
| `help`、`quit/exit` | 帮助、退出 |

`parse_actions()` 支持 `w0.5a0.2j30` 等组合，返回 `(key, magnitude, label)` 列表，逐步执行并且每步都有一张观察。`reset/status/help/quit` 在终端循环中单独处理，不由该解析器处理。pitch 限制在 -89.9° 到 89.9°，点半径必须大于 0；显式动作幅度必须为有限正数。这些仍存在的条件有实际几何或动作语义用途。

## 7. 本机配置和运行方法

当前 `main_env.py` 默认值：

```python
DEVICE = 'cuda:1'
BLENDER = '/data4/haibo/software/blender/blender-4.5.13-linux-x64/blender'
VIDEO = '/data4/haibo/data/VSI-Bench/scannet/scene0246_00.mp4'
REC_WEIGHTS = '/data4/haibo/weights/VGGT-Omega/vggt_omega_1b_512.pt'
METRIC_WEIGHTS = '/data4/haibo/weights/DA3METRIC-LARGE'
OUTPUTDIR = 'outputs'
FPS = 2.0
MAX_NUM_FRAMES = 500
METRIC_FRAMES = 32
EYE_HEIGHT = 1.0
RADIUS = 0.015
RESOLUTION = 960
MOVE_STEP = 0.3
LOOK_STEP = 15
POINT_STEP = 0.005
CAMERA_TIMEOUT = 300
```

已发现完整依赖环境的 Python：`/home/hw139426/workspace/miniconda3/envs/spatial_agent/bin/python`。本次交接检查得到 Python 3.12.1、PyTorch 2.7.0+cu126，**`torch.cuda.is_available()` 为 False**。默认 `cuda:1` 在当前检查环境不可用；新 session 运行真实重建前重新确认 GPU。不要因此擅自改默认设备或大改模型。

普通默认 Python 之前没有完整重建依赖；不要把它的 import 失败当成项目逻辑错误。Blender 自带 `bpy` 和 `mathutils`，不需要在普通 Python 里安装 `bpy`。

```bash
cd /data4/haibo/code/SpatialHarness
PYTHONDONTWRITEBYTECODE=1 /home/hw139426/workspace/miniconda3/envs/spatial_agent/bin/python main_env.py --help
# GPU 可用后，下面的命令会实际重建并进入交互：
PYTHONDONTWRITEBYTECODE=1 /home/hw139426/workspace/miniconda3/envs/spatial_agent/bin/python main_env.py
```

CLI 还支持 `--video`、`--fps`、`--max-num-frames`、`--checkpoint`、`--device`、`--metric-weights`、`--output-dir`、`--blender`、`--resolution`、`--samples`、`--up`、`--point-radius`。`METRIC_FRAMES`、眼高和默认动作步长直接在入口顶部设置。

## 8. 已完成的整理与验证边界

前一轮已完成目录整理、渲染小文件合并、重复材质与图片处理逻辑复用、初始位姿职责调整，删除重复的路径/数值前置检查及静默异常兜底；随后统一为一个启动入口，最后把所有 config 常量原值移进 `main_env.py`，删除 `config.py` 并更新 README。没有修改 `models/`。

历史验证包括：

- 语法、导入、CLI 参数与配置默认值一致性检查。
- 合并前后导航状态、拼接像素、真实 Blender 渲染及内参的一致性检查；验证重置、失败回滚和临时图片清理。
- Metric 尺度计算与采样/掩码行为一致性，以及实际 DA3 Metric checkpoint 的 CPU 推理。
- 用 **fixture 替代重建**、使用真实 Blender 的完整启动和 `status → w.5 → reset → quit` 检查，`fork` 和 `spawn` 两种子进程方式均通过，并确认 `METRIC_FRAMES` 从入口传入。
- 模型目录全部文件的哈希一致性检查。

**这些检查不等于已验证完整视频的 GPU 重建。** 前一轮受 GPU 环境限制，没有完成真实 VGGT + DA3 的全视频 GPU 端到端验证。本次仅写交接文档和检查当前环境，没有重跑这些历史测试。

本机临时检查材料在 `/tmp/spatialharness-checks/`，可能被清理，不能当成持久仓库依赖。较有用的文件：

- `check_single_entry_pipeline.py`：重建 fixture + 真实 Blender；参数 `fork` 或 `spawn`。
- `config-inline-fork.log`、`config-inline-spawn.log`：最新配置内联后的通过记录。
- `blender-structure-comparison.log`：渲染与状态一致性通过记录。
- `check_metric.py`、`metric-structure.log`：Metric 与实际 checkpoint 检查。

例如临时材料仍存在时可运行：

```bash
printf 'status\nw.5\nreset\nquit\n' | PYTHONDONTWRITEBYTECODE=1 /home/hw139426/workspace/miniconda3/envs/spatial_agent/bin/python /tmp/spatialharness-checks/check_single_entry_pipeline.py fork
```

部分旧脚本引用 `/tmp/` 中的历史源码备份，复用前先看内容。不要直接运行全部历史脚本，更不要为了文档任务重新进行昂贵推理。

## 9. 接手时的重点

写本文前，仓库 HEAD 为 `1582fa3`（提交标题 `update`），`git status --short` 为空。前一轮曾有大量未提交结构调整，但当前已进入提交历史；新 session 应以接手时实际 Git 状态为准。本次新增此文档，没有修改业务代码，也没有执行提交。

环境底座已经支持“观察—动作—再观察”。本机管道 JSON 通信、相机工具包装与新入口组装均已完成，普通 Python 的 Qwen agent 可以通过 `CameraClient` 控制持续运行的 Blender session。遵守用户最新指定的两个入口结构，保持直接实现，不引入框架或恢复配置抽象。

继续工作时优先确认用户下一步具体目标；碰撞检测保持搁置。不要把整理代码的历史任务无限扩大，也不要将“agent 可用的环境底座”描述成“agent 已经自主运行”。

## 10. 最小 agent 核心迁入范围

用户允许当前环境必要的相机工具，但禁止源仓库的 coding、搜索等通用工具；已分步授权核心迁入、现有 vLLM 服务验证、Blender 通信、工具包装和临时脚本联合验证。随后授权新增 agent 入口并统一改名为 `main_agent.py` 和 `main_env.py`，环境业务逻辑保持不变。

迁入保留 backend/protocol/循环边界，便于以后替换模型；当前仅实现 Qwen。没有迁入 SessionManager、workspace 模板、其他模型实现、统计日志或独立 conversation store 类。配置显式由调用方传入，没有新增入口或默认配置文件。`requirements.txt` 已有 `openai`，无需增加依赖。

`Agent.run()` 支持文本或多模态内容，执行工具并回传结果；同一响应中的所有工具结果先回传，再附加视觉消息。`conversation_path` 可选，记录写入使用临时文件替换，新建 agent 不自动恢复旧记录。`Agent.reset()` 只重置消息，不涉及相机。图片历史限制沿用源仓库语义，不裁剪视频。

Qwen protocol 沿用源仓库 Qwen3.8 的 XML 工具调用格式。backend 保留 `skip_special_tokens=False` 与 `tool_choice='none'` 的原始文本解析方式；不要自行启用服务端自动工具调用解析。`view_media` 通过本地文件 URI 附加图片/视频，要求模型服务可访问并允许读取相应路径。

迁入阶段通过 11 项本地检查，覆盖 Qwen thinking/参数解析、工具与多模态消息回传、多工具消息顺序、错误反馈、图片历史限制、步骤上限、对话记录与重置、替换 protocol，以及使用真实 SDK 加模拟 HTTP 的 backend 请求与失败处理。7 个新增 Python 文件通过语法/导入检查，模型目录全部 155 个文件哈希未变。检查脚本在 `/tmp/spatialharness-agent-core/check_core.py`，不属于正式测试目录。迁入阶段没有调用真实模型、启动 Blender 或运行重建；随后获用户授权完成下面的真实服务验证。

## 11. 真实 Qwen 服务验证

用户确认后台已有 vLLM 并授权验证。服务地址 `http://127.0.0.1:8000/v1`，`/models` 返回 `qwen3.8-27b`，权重为 `/data4/haibo/weights/Qwen3.8-27B-FP8`，上下文上限 1,000,000。服务和 agent 核心配合工作，无需修改核心代码。

使用现有 `Agent`、`VLLMBackend`、`QwenProtocol` 完成三项真实验证：

- 文本：`17 + 25` 返回 `42`。
- 图片：agent 先调用 `view_media`，工具成功附加 `image_url`，随后正确识别已有观察图的三个英文标题、红色窗帘及椅子/桌子。
- 视频：从默认原视频截取前 4 秒，保存为 32 帧、8 FPS 的短片；agent 先调用 `view_media`，工具成功附加 `video_url`，随后描述卧室家具与镜头向右移动。视频请求以 `media_io_kwargs={'video': {'num_frames': 8}}` 采样。已查看短片首尾帧，场景与移动描述基本一致；这不等于全长视频或复杂时序推理验证。

验证启用 thinking，`reasoning_effort='medium'`，`preserve_thinking=True`，`max_tokens=4096`；三项分别用时约 0.47、3.05、2.14 秒，仅是这次小样本的耗时。图片/视频均完成“模型工具调用 → 工具结果 → 媒体消息 → 模型回答”的两次请求闭环。

报告及完整对话记录在 `outputs/agent_check_t0hsnr74/`，报告为 `report.json`，三份对话为 `text.json`、`image.json`、`video.json`；短片和首尾参考帧也在该目录。临时执行脚本为 `/tmp/spatialharness-agent-core/check_live_vllm.py`，未新增正式入口。本次仅验证服务并更新文档，没有重建、启动 Blender 或接相机工具。

## 12. Python 与 Blender 通信

用户随后授权实施通信步骤。仅新增业务文件 `scene/camera_control/bridge.py`，并在 `main.py` 增加 `CAMERA_TIMEOUT = 300`、隐藏参数 `--response-fd` 和 worker 的 `serve_camera` 分支；没有改导航、渲染或 agent 核心，也没有新增启动入口。

`CameraClient(command, log_path=..., timeout=...)` 启动 Blender 并等待初始化状态；客户端自动给命令追加 `--response-fd`。启动命令由调用方提供，需包含 `main.py`、`--worker` 和 `--session-dir`。初始化不渲染，状态保存在 `initial_state`。随后提供 `observe()`、`execute(key, magnitude=None)`、`status()`、`reset()`、`close()`，并支持 `with` 自动清理。新会话可通过 `reconstruction` 符号链接复用已有重建，输出记录写入新会话。

请求是标准输入上的逐行 JSON，格式为 `{'op': ..., 'params': {...}}`。响应在独立的继承管道中发送，格式为 `{'ok': True, 'result': ...}` 或 `{'ok': False, 'error': ...}`；Blender 标准输出与错误输出写入调用方指定的日志，因此启动信息与原生渲染日志不会干扰协议。服务端只映射观察、动作、状态、重置、关闭五项操作，复用现有 `CameraSession`。请求为同步串行，不支持并发。

初始化成功后返回状态；动作或渲染错误反馈给调用方，worker 可继续使用。请求超时、管道断开或非法响应时关闭 worker，避免后续响应错配；清理会回收管道并等待子进程，必要时终止/强制结束。正常 `close()` 等待 worker 自然退出，可重复调用。外部进程退出造成的缓冲写入 BrokenPipe 也已验证并处理。

验证结果：

- 11 项临时通信检查全部通过：大响应与日志分离、错误请求恢复、非法 JSON/参数、非有限幅度、初始化失败/超时、缺失程序、worker 崩溃与外部退出、请求超时、终止不响应时强制结束、上下文异常清理。
- 使用 `outputs/camera_20261005_100405_131445/reconstruction` 的真实约 202 万点点云和 Blender，生成 5 张 384×128 三栏图：观察、前进 0.5、左转 30°、失败后重观察、重置。状态查询不渲染，移动距离与转角正确，输出 PNG/JSON/state.json 一致，临时图清理正确，关闭后退出码为 0。
- 注入一次渲染失败，验证相机状态、历史记录和 state.json 不变；失败后重新观察的相机位姿及 PNG 字节与失败前一致。重置后的状态和 PNG 字节也与初始观察一致。
- 现有手动入口通过重建 fixture + 真实 Blender 的 `status → w.5 → reset → quit` 回归检查（fork）。未运行真实重建。
- `main.py --help` 保持原有公开参数，桥接参数隐藏。语法及普通 Python 导入通过；最终核对模型目录全部 155 个文件哈希未变。

真实 Blender 验证报告与图片在 `outputs/bridge_check_559qfnmc/`，报告为 `report.json`，完整日志为 `render.log`。临时检查材料在 `/tmp/spatialharness-bridge-checks/`；不属于正式仓库测试目录。本轮没有调用 Qwen，也未包装 agent 相机工具；下一步需等待用户指示。

## 13. 相机 agent 工具包装

用户授权“先添加 tools.py”。修改现有 `agent/tools.py`，新增 `create_tools(camera)` 工厂，返回 `view_media`、`camera_action`、`camera_observe`、`camera_status`、`camera_reset` 五个工具。没有新增业务文件或修改入口、循环、backend、protocol、通信、导航、渲染实现。

`camera_action(key, magnitude=None)` 直接映射 `CameraClient.execute()`；动作键支持 `wasdqeijkl+-`，可选幅度只适用于 WASD/IJKL，语义和校验复用环境。观察、动作、重置将完整 record 作为工具结果，并通过 `view_media(record['image']).messages` 自动附加三栏图片；状态只返回状态字典，不渲染或附加媒体。工厂只绑定传入的客户端，不启动/关闭 worker，没有给模型暴露 close/quit 或通用工具。原 `TOOLS = [VIEW_MEDIA_TOOL]` 保留，支持不依赖相机的独立媒体 agent。

通过 8 项本地模拟检查：工厂无启动副作用和工具范围、动作/可选幅度转发、完整记录与图片 URI、状态不渲染、不同客户端绑定独立、agent 循环连续收到每步观察、错误反馈不附加伪观察、多工具结果先于图片消息。临时脚本在 `/tmp/spatialharness-camera-tools-checks/check_tools.py`。包装阶段没有调用真实 Qwen、启动 Blender 或执行重建；随后获授权完成下述临时脚本联合验证。

## 14. 临时脚本 Qwen + Blender 联合验证

用户要求“先用临时脚本验证，别接着接到 main 里”。临时脚本为 `/tmp/spatialharness-live-camera-checks/check_live_camera.py`，使用已有 `Agent`、`VLLMBackend`、`QwenProtocol`、`create_tools(camera)` 和 `CameraClient`，调用现有 `qwen3.8-27b` 服务及真实 Blender。复用 `outputs/camera_20261005_100405_131445/reconstruction`，没有执行重建。

两项真实验证均通过：

1. 指定序列：Qwen 依次调用 `camera_observe`、`camera_action(w, 0.3)`、`camera_action(j, 30)`、`camera_status`、`camera_reset`、`camera_status`，最终根据观察回答。独立核对移动距离约 0.3、yaw 增加 30°、重置状态与初始一致，重置 PNG 字节也与初始观察一致。
2. 模型选择确认动作：沿用同一 agent 和 worker，询问床相对初始朝向的位置。Qwen 重新观察，自行选择 `camera_action(l, 20)`，接收新图后回答床在初始朝向右侧。独立核对原地右转 20°、位置不变，并查看初始及动作后图片确认这一空间判断。

验证中相机工具的所有结果均成功，6 张 1440×480 三栏图片均已保存，并进入后续模型请求；没有额外调用 `view_media` 来重复附加观察。共 10 次模型请求，耗时约 36.26 秒，关闭后 Blender 退出码为 0。图片、JSON、状态和对话记录保留。这个样例说明工具闭环可用，不代表已实现正式 agent 启动模式或全面验证空间理解准确率。

最终报告在 `outputs/agent_camera_check_eoq59n1v/report.json`，完整对话为同目录 `conversation.json`，模型请求的图片 URI 摘要为 `requests.json`，Blender 日志为 `render.log`。首次验证的临时断言严格禁止额外观察，而模型合法追加了一次 `camera_observe`，导致脚本断言失败；调整临时断言后重跑通过，没有修改业务代码。首次材料在 `outputs/agent_camera_check_t6k48jch/`，以最终通过报告为准。

运行前后核对 178 个现有业务源码/模型文件哈希，全部一致，包含 `main.py` 和 `models/`。本轮仅新增临时脚本与验证输出，并更新 README/交接说明；没有正式入口接线、模型/工具/渲染代码修改或提交。下一步必须等用户指示。

## 15. 新增 agent_main.py

用户随后指定新增 `agent_main.py`，并保留 `main.py` 原样。本轮只新增这一个业务文件，没有修改既有入口或底层模块；模型、服务、生成参数、thinking、步骤上限、图片保留数量、服务超时和系统提示词写在新入口顶部，环境默认值继续复用 `main.py`。CLI 直接使用 `main.parse_args()`，没有复制参数定义。

流程为新会话 → 子进程重建 → 释放重建进程 → 启动 Blender 通信 worker → 组装 `Agent` → 连续自然语言提问。五个工具仍由 `create_tools(camera)` 提供；不注册通用工具。对话保存为当前会话的 `conversation.json`。`/exit`、`quit`、`exit` 或 EOF 结束交互；同一 agent/worker 在连续提问期间保持运行。新建 agent 不恢复旧会话。

系统提示词使用真实工具名，说明三栏视图与参考帧局限、动作与单位、自动附图、逐步观察、无碰撞检测和不确定区域。Metric 禁用时明确距离为 VGGT 相对单位；转角为度。场景 yaw 不代表地理方向，转头角度本身也不等于物体方位角。

新增默认值为 `MODEL='qwen3.8-27b'`、`BASE_URL='http://127.0.0.1:8000/v1'`、`MAX_TOKENS=8192`、`TEMPERATURE=0.1`、`TOP_P=0.95`、`TOP_K=20`、thinking 开启、`REASONING_EFFORT='medium'`、preserve thinking 开启、`MAX_STEPS=100`、`MAX_CONVERSATION_IMAGES=4`、`MODEL_TIMEOUT=180`。CLI 重建/渲染参数与手动入口一致，`python agent_main.py --help` 可查看。

验证包括语法/导入/帮助检查、7 项本地生命周期检查，以及 spawn 重建 fixture + 真实 Qwen/Blender 的连续两次提问与正常退出。fixture 在真正的子进程中复用已有重建，验证了模型观察、右转 20°、新图回传、连续对话、重置、状态确认及 PNG 一致性。新入口的网络/推理失败、worker 初始化失败、EOF/Ctrl-C 和重建中断路径也通过本地清理检查。本轮未运行完整 GPU 视频重建。

临时检查脚本在 `/tmp/spatialharness-agent-entry-checks/`。最终真实验证报告为 `outputs/agent_entry_check_29adu93o/report.json`，其中记录实际会话目录；对话、图片、状态与 Blender 日志在该会话目录。一次中间检查中模型认为 reset 返回的状态已足够，省略额外状态查询；临时提问改为明确要求依次调用 `camera_reset` 与 `camera_status` 后通过，业务代码无需因此修改。样例仍把相机右转 20° 推断为床的方位角，不能据此证明数值空间推理准确；本轮验证目标是工具闭环与生命周期。运行前后核对本轮之前 178 个源码/模型文件哈希全部相同，包含 `main.py` 与全部模型文件；新增 `agent_main.py` 不在旧文件快照内。README 已更新两个入口的用法，并删除过时的逐按键工具 schema 草案。

## 16. 两个入口统一命名

用户随后指定使用 `main_agent.py` 与 `main_env.py`。已将 `agent_main.py` 和 `main.py` 分别改名，同步更新 agent 导入、两个入口的 Blender worker 路径、相机帮助文字及 README/本文当前用法。不保留旧名称的转发文件。第 11–15 节保留当时文件名作为历史记录，历史临时脚本可能需要相应调整才能复用。

核对改名前后源码：两个入口内容只有上述名称与引用变化，其他 177 个业务源码和模型文件哈希全部一致。两个入口的 `--help`、导入和 7 项生命周期检查通过。手动入口通过 spawn 重建 fixture + 真实 Blender 的 `status → w.5 → reset → quit` 检查；agent 入口通过 spawn 重建 fixture + 真实 Qwen/Blender 的两次提问、观察、右转 20°、重置、状态查询和退出检查。没有重跑 GPU 重建。

改名检查脚本在 `/tmp/spatialharness-rename-checks/`，agent 真实报告为 `outputs/agent_rename_check_ge26g_9y/report.json`；报告记录会话、工具调用、正常 worker 退出与改名后源码哈希核对结果。没有修改模型或提交代码。

## 17. 三张独立图片与 RESOLUTION 默认值

用户批准将观察拆成独立三图，要求框架生成的视图消息全部使用英文，并把分辨率加入 `main_env.py` 顶部配置。改动限于 `main_env.py`、`main_agent.py`、`scene/rendering/renderer.py`、`agent/tools.py` 和 `agent/loop.py` 五个业务文件，以及 README/本文。用户自行选择的 `MODEL='qwen3.8-flash-next'` 保留。

渲染器持久保存 `<编号>_<动作>_first_person.png` 与 `_top_down.png`，在 record 的 `images` 中返回它们及原始参考帧路径；原 `image` 与 `layout` 继续描述人工用三栏预览。`RESOLUTION = 960` 是两个入口共同使用的渲染边长默认值，可由 `--resolution` 覆盖。默认视频参考帧为 640×480，直接发送原图，不从拼接图裁切或缩放。记录写入失败、渲染失败或中断会清理本次新输出，状态通过临时文件替换提交，参考帧保留。

工具观察消息按英文 `first_person_view`、`top_down_view`、`nearest_video_frame` 开闭标签交替附加三个原生图片内容项，再附英文当前视图/参考帧说明。没有手动生成 image token，也没有修改 backend、protocol 或通信桥接。图片历史预算为 12，裁剪以消息内全部图片为单位，保留文字；只含三图相机观察时可容纳最近四组。视频附件仍不受这个图片预算管理。

验证通过：5 项三图本地检查、7 项入口生命周期检查；真实 Blender 默认 960×960 双渲染图与 640×480 参考帧、移动与重置、第二视图渲染失败和状态提交失败清理/回滚；真实 Flash-Next + Blender 三次问答、右转 20°、重置、状态查询及第五组三图进入后的 12 张预算完整组裁剪。服务 `/models` 确认 `qwen3.8-flash-next` 使用 262,144 上下文。图像重置比较解码后像素，独立 PNG 的文件元数据可能不同。本轮没有重跑 GPU 视频重建，fixture 采用 221 点合成场景搭配默认视频首帧，不用于证明空间推理精度提升。

最终 Blender 报告为 `outputs/three_image_check_of8rnicj/report.json`，真实 Flash-Next 报告为 `outputs/three_image_live_d286ldmy/report.json`，对话与每次请求的图片数量在同目录 `conversation.json`、`requests.json`。临时检查脚本在 `/tmp/spatialharness-three-images-checks/`。中间临时检查先修正了未生效的 Blender operator 故障注入，再将 PNG 字节相等断言改为解码像素相等；业务实现无需因这两处检查问题调整。最终语法/帮助/差异检查通过，其他业务源码和模型文件哈希保持不变；未提交代码。
