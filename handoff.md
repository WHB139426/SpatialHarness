# SpatialHarness 交接说明

更新日期：2026-10-08。项目根目录：`/data4/haibo/code/SpatialHarness`。

这份文件记录项目目的、当前实现和前一轮工作的决定。新 session 先读本文，再看 `main_env.py`、`README.md` 和需要修改的模块；用户后续指令优先于本文。

## 1. 项目目的与当前阶段

项目要提供一个由视频重建得到、可供 agent 自由探索的三维空间环境。目标交互是：agent 获得观察，选择移动或转头动作，环境执行动作并返回新观察，agent 根据结果继续探索和回答空间问题。

目前已实现环境底座：视频重建、米制尺度估计、点云渲染、相机移动、独立三图观察与三栏预览、状态记录和重置。`main_env.py` 提供终端 `camera>` 手动交互，`main_agent.py` 提供 `agent>` 自然语言空间问答。agent 接收三张独立图片（第一视角、含轨迹俯视图、参考帧），人工预览也显示三栏。`CameraSession` 在 Blender 进程中使用，普通 Python 的 agent 通过 `CameraClient` 控制它。

**已迁入最小 agent 核心、打通 Blender 通信、包装相机工具，并新增正式 agent 入口。** 用户先授权新增独立 agent 入口，随后指定两个入口命名为 `main_agent.py` 和 `main_env.py`，覆盖此前只保留一个入口的约束。`main_agent.py` 已组装重建子进程、Qwen backend/protocol、相机工具和连续提问循环，改名只同步调整文件引用与帮助文字，业务逻辑保持不变。实际工具以 `create_tools(camera)` 为准，`camera_action` 使用英文 `action` 名称并在工具层映射到环境按键；提示词在新入口顶部，README 中旧逐按键接口草案已移除。新入口的连续提问和退出已通过重建 fixture + 真实 Qwen/Blender 检查；完整视频的 GPU 重建本轮未重跑。

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
  tools.py                      create_tools(camera) 相机工具包装与内部媒体附件
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

`main_agent.py` 复用同一个参数解析器，新建会话并在子进程调用同一重建函数。重建成功后，通过 `CameraClient` 启动 `main_env.py` 的通信 worker，再组装 Qwen agent 与四个相机工具（轨迹自动叠加到俯视图），进入 `agent>` 连续提问。模型按需调用观察工具，启动时不预先渲染。退出时释放 worker 与模型客户端；重建失败不启动服务，重建中断会终止并回收子进程。

## 5. 重建、坐标与观察数据

重建从首帧起按 `FPS` 抽帧，达到视频末尾或 `MAX_NUM_FRAMES` 停止。VGGT-Omega 预测深度和相机参数，每帧过滤低于第 40 百分位的深度置信度，生成彩色点云，最后使用 0.01 体素下采样。

默认 DA3 Metric 从最多 `METRIC_FRAMES` 个均匀选择的帧估计尺度：每帧在有效区域拟合比例，取有效帧尺度中位数，同时缩放深度和相机外参平移。输出近似米制坐标；`--metric-weights none` 则保留 VGGT 相对单位。尺度失败会报错，不静默使用相对尺度。`metric_scale.py` 中 DA3 调用的 `export_feat_layers=[0]` 已对实际 checkpoint 验证过，不能仅凭表面上“多余”就删掉。

相机 JSON 的 `extrinsic` 是 world-to-camera。相机中心为 `-R.T @ t`，原视频相机的前向是相机坐标 `+Z`。Blender 相机看向本地 `-Z`，相应转换已在位姿与导航中处理。

场景上方向优先从点云地板候选平面估计；无可靠平面时使用第一帧相机上方向和低处 5% 点近似地面。真正的算法异常直接报错，不用宽泛异常捕获吞掉。初始位置参考第一帧相机，投影到地面后沿上方向升高 `EYE_HEIGHT`；初始朝向参考第一帧，pitch 为 0。`--up X Y Z` 可以覆盖导航参考上轴。

每次观察保存三栏 PNG：

- 左：带准星的第一人称点云视图。
- 第二栏：叠加历史路径的正交俯瞰图，用橙色圆点标记位置，带 WASD 字母的三短一长十字标记水平移动方向；蓝色长 `w` 臂带前进箭头，绿色 `j/l` 弧形箭头标记向左/右转，六个字母始终正立。
- 第三栏：位置与朝向最接近的原视频抽帧，保持原始宽高比并留黑边。
俯视图内以黄色点表示轨迹起点、紫红色路线和箭头表示历史移动与行进方向。

最近帧匹配分数为 `(位置距离 / 0.5)^2 + (朝向夹角 / 20°)^2`，仅比较位姿；右栏不是当前视角的精确实拍图，匹配距离与角度会记录下来。第一人称使用归一化 VGGT 内参的中位数，保持固定视野，输出方形画面；向上下扩展视野而不是拉伸视频投影。

默认每栏 960×960，合成 PNG 为 2880×960。Blender 使用 Cycles CPU 渲染，8 线程、16 samples；模型推理与渲染使用不同环境。

`RESOLUTION = 960` 已移到 `main_env.py` 顶部，`--resolution` 复用它作为默认值。第一人称和含轨迹的俯视图按这个边长分别保存到 `.views/`；agent 使用这两张独立 PNG 和原始参考帧，不使用拼接预览。当前默认视频的参考帧为 640×480，保持原尺寸。一条观察消息含三个英文视图标签及图片，顺序为第一视角、包含最新成功动作的俯视轨迹图、匹配参考帧。实际视觉编码尺寸仍取决于服务端预处理。

```text
outputs/camera_<时间戳>/
  reconstruction/
    vggt_reconstruction.ply
    vggt_cameras.json
    frames/frame_<原视频帧号>.jpg
  0001_initial.png
  .views/
    0001_initial_first_person.png
    0001_initial_top_down.png
  0001_initial.json
  0002_<动作>.png / .json
  state.json
  render.log
```

观察 record 包含 `command`、`views`、`layout`、`state`、`camera_position`、`camera_forward`、`lens_mm`、`intrinsics`、`nearest_frame`、`image`、`images` 和 `input`。`nearest_frame.image_path` 是原视频帧路径，`image` 是三栏 PNG 预览路径；`images` 按 `first_person`、`top_down`、`nearest_video_frame` 提供独立图片路径，top_down 已包含轨迹。历史观察保留，`state.json` 通过临时文件替换随最近成功观察更新；失败时清理本次新文件，不删除参考帧。

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

## 18. 输出目录只展示拼接预览

用户要求输出里只展示拼接后的图片。渲染器将新观察的独立第一人称图和俯视图保存到会话的 `.views/` 子目录，顶层 PNG 只保留三栏预览；record 与 agent 附件直接使用新路径，参考帧继续使用 `reconstruction/` 原图。已有会话及其对话路径没有迁移。真实 Blender 检查通过：顶层仅有每次观察的拼接图、独立图均在 `.views/`、三图附件路径有效、移动/重置正常、失败时子目录文件也清理且状态回滚。报告为 `outputs/view_storage_check_ggoouz6o/report.json`，临时脚本为 `/tmp/spatialharness-three-images-checks/check_view_storage.py`。本轮业务改动仅在 `scene/rendering/renderer.py`，未调用模型或重建。

## 19. 俯视图 WASD 十字标记

用户授权将蓝色箭头改为三短一长的十字，并在各方向附小写 WASD 字母。`OverheadView` 保留橙色位置圆点，`w` 长臂与字母用蓝色突出，其余 `a/s/d` 为等长短臂和白色字母；字母有深色底并抵消父标记的旋转，保持地图中正立。低分辨率使用最小屏幕显示尺寸。`main_agent.py` 的英文 top-down 说明同步描述标记，明确其表示方向而非移动距离。没有改导航或工具接口。

使用合成点云 fixture 完成真实 Blender 渲染：960、480 各五个 yaw（0/45/90/180/270），十字四臂世界方向均与 `Navigator.step()` 的 WASD 位移方向一致，字母保持正立，俯仰 60° 不改变十字朝向，标记不显示在第一人称图中；已查看两种分辨率的实际图像。最终报告与拼接预览在 `outputs/map_marker_check_rdgm7g63/`，报告为 `report.json`，例如 `960/0003_yaw45.png`、`480/0003_yaw45.png`。临时脚本为 `/tmp/spatialharness-map-marker/check_blender.py`。首次检查的角度断言遇到 +π/-π 环绕，改为比较归一化角差后通过；视觉检查后提高小分辨率标记的最小尺寸并重跑检查。未运行重建或模型推理。


## 20. 转向弧线和 w 箭头

用户先查看独立图标预览，再授权按预览加入 `j/l` 弧形箭头，并要求 `w` 方向也带箭头。`scene/rendering/views.py` 在蓝色长臂末端增加三角箭头，绿色弧线表示 `j` 逆时针左转、`l` 顺时针右转；弧线随相机朝向旋转，六个字母共享正立和深色底处理。`main_agent.py` 英文提示词同步解释平移与转向、方向标记不表示距离或转角大小，README 同步说明。未修改导航或工具接口。

真实 Blender 合成点云检查通过：960、480 各五个 yaw（0/45/90/180/270），WASD 与实际位移一致，`w` 箭头与前进方向一致，弧形箭头与实际 `j/l` 转向一致，六个字母始终正立、俯仰不改变水平标记、第一人称视图隐藏全部标记。已查看两种分辨率的渲染图。报告为 `outputs/rotation_marker_check_a0aiyb8f/report.json`，示例拼接图为 `960/0001_yaw90.png`、`480/0003_yaw45.png`。临时检查脚本为 `/tmp/spatialharness-rotation-marker-check.py`。未调用模型或重跑 GPU 重建。

用户随后要求放大字母：六个字母的字号从 `0.95` 调至 `1.2`（约增大 26%），深色底框半宽/半高从 `0.52/0.45` 同步调至 `0.66/0.57`；十字、箭头和弧线尺寸保持原值。真实 Blender 检查 480/960、yaw 45/90 通过，并查看渲染确认可读性与排布。报告为 `outputs/marker_letters_check_n7yhpcp6/report.json`，示例为 `960/0001_yaw90.png`；临时脚本为 `/tmp/spatialharness-marker-letters-check.py`。


## 21. camera_action 使用英文动作名

用户授权将 agent 相机工具的参数从 `key` 改为 `action`：`move_forward/move_backward`、`move_left/move_right`、`move_down/move_up`、`turn_left/turn_right`、`look_up/look_down`、`increase_point_radius/decrease_point_radius`。`agent/tools.py` 的工厂内只增加一张名称到按键的映射，schema 与函数签名同步修改，没有保留旧参数或按键别名。可选 `magnitude` 的单位、默认值和适用范围继续由环境处理。`CameraClient.execute(key, magnitude)`、桥接协议、导航、手动键盘和地图标记保持原接口。

`main_agent.py` 的英文提示词同步使用动作名，地图段明确 w/a/s/d/j/l 与动作名的对应关系；README 更新参数说明、映射表和调用示例。真实 Blender 合成点云 + 脚本模型经过 Qwen XML 解析与 Agent 循环的检查通过：十二种动作的位移、角度和点半径变化正确，观察仍附三张图片，状态/重置可用；七类无效参数（旧按键、未知动作、旧 key 参数、不允许的 magnitude、非正幅度）返回错误且不改变状态，不附虚假观察。报告为 `outputs/named_actions_check_e1d7jfcb/report.json`，对话为同目录 `conversation.json`，临时脚本为 `/tmp/spatialharness-named-actions-check.py`。已检查提示词格式化和英文文本。本轮未调用真实 Qwen 服务或重跑 GPU 重建。

用户追加要求在 system prompt 和 camera_action description 中说明所有动作的第一视角参照。两处现已明确动作作用于当前第一视角相机或其渲染点云，方向按当前相机视角理解；turn_left/right 是相机自身左右，look_up/down 是抬头/低头，水平移动沿当前水平朝向，垂直移动仍沿场景竖直轴。点半径动作说明为渲染点大小调整。仅修改英文说明，未改动作逻辑；语法和 diff 检查通过。


## 22. 移除独立 view_media 工具

用户授权删除 `view_media`。`agent/tools.py` 删除 `VIEW_MEDIA_TOOL`、独立 `TOOLS` 注册和相机工具列表中的媒体工具，原附件函数改为内部 `_view_media()`，仍用于三张观察图片的文件校验与 URI 构造。`create_tools(camera)` 目前只返回 `camera_action`、`camera_observe`、`camera_status`、`camera_reset` 四个工具。英文 system prompt 与 README 的当前接口说明同步更新；历史媒体验证记录保留并注明工具已移除。

本地附件 fixture 经 Qwen XML 解析和 Agent 循环检查通过：每次模型请求只提供四个相机工具，观察/动作/重置各自动附加三图，状态仅返回元数据，尝试调用已删除工具返回 unknown tool 错误且不影响相机。报告为 `/tmp/spatialharness-camera-only-dw4iwgx2/report.json`。语法和 diff 检查通过，未调用真实模型或 Blender。本轮没有实现此前讨论的 camera_trajectory 工具。


## 23. camera_trajectory 轨迹工具

用户授权实现此前讨论的轨迹工具。修改六个代码文件：`CameraSession` 在成功提交动作后记录位置变化，初始位置构成第一段，成功 reset 保留旧段并新开一段；失败动作与 reset 不写历史。`CameraClient` 与 worker 分发新增 `trajectory` 请求。`OverheadView` 复用一个 mesh 绘制紫红色路线与行进箭头、黄色段起点，继续显示当前相机的橙点及方向十字；按全体历史位置取景，垂直移动投影重合，不画零长箭头。`SceneRenderer.render_trajectory()` 单独保存 `<序号>_trajectory.png/json`，不覆盖 `state.json`，失败时清理输出，结束后隐藏叠加层并恢复第一视角。反复查看复用 mesh 和材质，不累积 Blender 对象。

`create_tools(camera)` 现返回五个工具：camera_action、camera_observe、camera_status、camera_reset、camera_trajectory，无独立 view_media。新工具无参数，返回当前状态、轨迹段数/点数、图片路径及尺寸，并通过一条自动 user 消息附加一张 top_down_view 图片和英文说明。英文 system prompt 新增轨迹段落，说明颜色、路径箭头、reset 断线、水平投影和跨图像素坐标不可直接比较。图片预算仍为 12 张，普通观察占 3 张、轨迹图占 1 张。README 同步接口及输出说明；没有新增业务模块、改 main_env.py、导航或模型 backend/protocol。

真实 Blender 进程通信 + Qwen XML 协议/Agent 循环的脚本模型检查通过，使用 221 点合成点云：初始轨迹、成功位置记录、转头/俯仰/点半径不增点、reset 分段、垂直投影、单张附件、历史越界位置取景、重复查询复用对象、查询不改状态及 state.json、普通观察像素不变、新 worker 历史独立、960/480 渲染、正常退出。注入移动和 reset 第二视角失败及轨迹记录写入失败后，状态/历史保持原值、输出清理并可继续调用。已查看两种分辨率实际轨迹图。报告为 `outputs/trajectory_check_fh7rt4cz/report.json`，示例 `0017_trajectory.png`（两段）、`480/0003_trajectory.png`；临时脚本为 `/tmp/spatialharness-trajectory-check.py` 与 `/tmp/spatialharness-trajectory-inject.py`。本轮未调用真实模型服务或 GPU 重建。


## 24. 轨迹自动作为第四张观察图片

用户选择保留干净的当前地图和独立历史轨迹地图，每次观察自动附加第四张图，取代额外 camera_trajectory 工具。`CameraSession._commit()` 先生成待提交的轨迹副本（含本次移动或 reset），传给渲染器；全部渲染与保存成功后同时提交状态和轨迹，失败保留原历史。删除 CameraSession/CameraClient 的独立 trajectory 方法、worker 分发和 camera_trajectory 工具。`SceneRenderer.render()` 统一渲染第一视角、干净俯视图、轨迹图，三张 PNG 均在 `.views/`，参考帧保持原尺寸；顶层只有原三栏拼接图。失败时四图相关新增输出全部清理。record 的 images 新增 trajectory，views/布局描述独立四图，并提供轨迹段数与点数。旧会话不迁移。

每条自动 user 观察消息按 first_person_view、top_down_view、nearest_video_frame、trajectory_view 顺序包含四张图片，tool description 和英文 system prompt 已同步。普通俯视图不叠加轨迹；轨迹图包含当前最新成功动作，保留 reset 断线、黄色起点与紫红色行进箭头。无需模型主动调用轨迹工具。用户已自行将图片预算设为 4*4，本轮保留该值并更新注释，按完整消息保留最近四组四图观察，未改裁剪逻辑。main_env.py 仅更新 HELP 的文件说明。

真实 Blender + CameraClient + Qwen XML 协议的脚本模型检查通过：每次观察四张附件、工具列表仅四项、轨迹及时包含新移动和 reset、纯转向不加点、垂直投影、干净/轨迹图分别保存、历史越界取景、reset 不连线、16 张预算完整组裁剪、旧 camera_trajectory 调用被拒绝、状态与历史原子回滚、第二视角/第四视角/状态写入/reset 失败后的文件清理与恢复、960/480 渲染及 worker 正常退出。模型请求图片数为 [0,4,8,12,16,16,16,16,16,16,16,16]。已查看默认尺寸的干净地图与轨迹地图。报告为 `outputs/four_views_check__y3g7yvo/report.json`，示例为 `.views/0010_w0.8_top_down.png`、`.views/0010_w0.8_trajectory.png`，三栏预览为 `0010_w0.8.png`。临时脚本为 `/tmp/spatialharness-four-views-check.py` 与 `/tmp/spatialharness-four-views-inject.py`。没有调用真实模型服务或 GPU 重建。


## 25. 四栏人工预览与最新会话修复

用户反馈看不到第四张图。检查最新真实会话 `camera_20261008_190813_940511/conversation.json`，最后一条观察消息已有四个 image_url，四个文件均存在，轨迹为 `.views/0013_j55_trajectory.png`；原因是上一轮只升级模型输入，人工拼接预览仍保留三栏。现 `stitch_views()` 拼接顺序也改为第一视角、干净俯视图、参考帧、轨迹，默认宽度 3840×960；渲染器给新的第四张图单独使用 TRAJECTORY 标题，main_env HELP 与 README 同步四栏说明。

已用现有独立图片重建上述最新会话的全部 13 张拼接预览，输入图片哈希保持不变，没有改对话、状态和参考帧。示例为 `outputs/camera_20261008_190813_940511/0013_j55.png`。既有独立轨迹图片保留旧 TOP DOWN 标题，新生成的轨迹图片使用 TRAJECTORY。重建脚本为 `/tmp/spatialharness-rebuild-four-panel-previews.py`，报告 `/tmp/spatialharness-four-panel-rebuild-report.json`。真实 Blender 桥接/四图附件/完整组裁剪/失败回滚检查在 960/480 重跑通过，预览尺寸分别为 3840×960 和 1920×480；报告为 `outputs/four_panel_check_vu2b_1oe/report.json`，脚本为 `/tmp/spatialharness-four-panel-check.py`。已查看用户实际四栏预览和新轨迹标题。模型仍接收四张独立图，不接收拼接预览。


## 26. 轨迹合入俯视图，恢复三图设置

用户最终选择将 top-down 与 trajectory 合并。渲染器每次只渲染第一视角和含历史路径的俯视图，再附匹配原视频帧；删除单独 trajectory PNG、第四张附件标签和 TRAJECTORY 标题对象，人工预览恢复三栏（2880×960，480 时为 1440×480）。模型观察消息按 first_person_view、top_down_view、nearest_video_frame 附加三张独立图片，图片预算恢复 4*3=12，保留最近四组完整观察。仍只有 camera_action、camera_observe、camera_status、camera_reset 四个工具。轨迹记录、最新动作、reset 断线、失败原子回滚均保留，路径直接显示在 TOP DOWN 图中。英文提示词、工具说明、HELP 和 README 同步三图设置。

真实 Blender 进程通信与脚本模型检查通过：俯视图实际含紫红色路径、三图附件/标签、12 张整组预算、最新动作和 reset 包含在地图、纯转向不加点、垂直投影、历史越界取景、第二视角/路径绘制/状态提交/reset 失败的文件清理与状态/轨迹回滚、正常退出、960/480 渲染。报告为 `outputs/merged_map_check_ck4b953z/report.json`，临时脚本为 `/tmp/spatialharness-merged-map-check.py` 与 `/tmp/spatialharness-merged-map-inject.py`。没有调用真实模型服务或 GPU 重建。

已将最新真实会话 `camera_20261008_190813_940511` 的全部 13 张人工预览重新拼为三栏，中栏使用原有含历史路径的地图。独立输入图片哈希保持不变，既有对话和状态记录仍保留当时的四图格式；新运行使用三图格式。已查看最新预览 `0013_j55.png`，确认路径和方向标记同时显示。重建脚本为 `/tmp/spatialharness-rebuild-merged-previews.py`，报告为 `/tmp/spatialharness-three-panel-rebuild-report.json`。


## 27. camera_action 恢复按键参数

用户要求恢复 w/a/s/d、q/e、j/l/i/k、+/- 按键。`agent/tools.py` 的函数和 schema 改为 `camera_action(key, magnitude=None)`，删除英文动作名映射，直接调用环境的单键接口。工具描述与 `main_agent.py` 英文 system prompt 逐个解释十二个按键的意义，保留当前第一视角参照、水平移动保持高度、q/e 沿场景竖直轴、距离和角度单位、固定步长及幅度限制；README 同步参数与示例。key 只接受单个按键，幅度单独传入；不接受旧 action 参数、英文动作名、组合命令或按键串。三图设置不变。

真实 Blender 合成点云与脚本模型经 Qwen XML 解析、Agent 工具执行检查通过：十二个按键的位移、朝向、俯仰和点半径变化正确，每次自动附加三图，状态与 reset 正常；十二种无效参数（旧 action、英文动作名、组合命令、按键串、大写/空键、不支持的幅度、非正/非有限幅度）均返回错误且保持状态，不附加图片。英文提示词格式化、schema、Python 语法与 diff 检查通过。报告为 `outputs/key_actions_check_j3zxcgzo/report.json`，临时脚本为 `/tmp/spatialharness-key-actions-check.py`。未调用真实模型服务或重跑 GPU 重建。


## 28. 导航决策提示词

分析真实会话 `camera_20261008_193217_140353`：一次观察后执行 39 次动作，其中水平移动 18 次、累计约 14 scene units，水平转向 17 次、累计 1015 度；工具调用无错误，最终第一视角确实对着马桶。主要问题为路线与入口假设反复改变、地图与按键解释不稳定、参考帧通道被用于当前导航、近处遮挡后原地转向和增大点半径。

用户授权按讨论方案修改 `main_agent.py` 的英文 SYSTEM_PROMPT。用 Evidence from the views 明确三视角用途和参考通道需要当前观察确认；增加 Navigation planning、Action and verification、Recovery、Completion 分段。要求短路线和当前路标、动作前英文简述目的与预期、动作后验证、连续三步无进展且无新信息时重新规划、贴近表面完全遮挡时先退回清晰位置、避免无依据的反向转头与重复路线、不推算未标定的世界坐标/地图距离、j/l 弧线只表示旋转、满足最终第一视角条件后停止多余调整。保留原视角说明、工具工作流、第一视角参照及按键单位，通用空间问答仍按证据回答。不改工具、图片设置、模型参数或 Agent 循环。

Python AST 语法检查、纯英文检查、分段和四个格式占位符检查、米制/相对单位两种填充模式及 diff 检查通过。本轮未重跑模型导航，实际动作效率改善仍需新会话验证；运行中的 Agent 不会自动更新既有 system message，重启 `main_agent.py` 后使用新提示词。


## 29. agent 仅保留前进和转向

用户要求剥夺 a/s/d，仅保留 w 和转向。按“仅保留前进和转向”实现，已向用户说明 agent 可用键为 w、j/l、i/k；q/e 与 +/- 同样不再提供。`agent/tools.py` 使用同一五键列表生成 schema 并在调用相机前检查，旧按键不能绕过枚举限制。手动环境的导航、键盘、地图图标保留原功能；英文 SYSTEM_PROMPT 说明地图 a/s/d 只是方位参考，横向或返回旧位置必须先转向再前进，完全遮挡时先转向最后清晰位置并小步前进。距离说明只对应 w，角度仍对应 j/l/i/k；删除点半径动作的提示及无用的 point_step 格式填充。README 同步。

真实 Blender 合成点云、脚本模型和 Qwen XML 协议检查通过：五键接口、转向后前进、转身后沿原路前进、抬头低头、三图附件、状态与 reset 正常；17 种无效参数返回错误且不改变状态或附加图片。另检查已移除按键、组合命令和错误类型不会到达相机执行函数。Python 语法、纯英文及米制/相对单位格式化、diff 检查通过。报告为 `outputs/forward_turns_check_d2v25zrg/report.json`，临时脚本为 `/tmp/spatialharness-forward-turns-check.py`。未重跑真实模型导航；重启 `main_agent.py` 后使用新工具与提示词。


## 30. 俯视图恢复单前进箭头

用户要求删除俯视图 a/s/d 标记，恢复单箭头，保留 w 和 j/l 弧线。`scene/rendering/views.py` 删除三个短臂、字母及底框，前进箭杆和箭头合为单个蓝色网格，保留 w 字母、橙色位置圆点、绿色 j/l 弧形箭头；删除无用的灰色和白色标记材质。朝向旋转、字母正立、放大字号和低分辨率最小尺寸逻辑沿用。英文 SYSTEM_PROMPT 和 README 同步单箭头描述，手动按键和 agent 五键限制不变。

真实 Blender 在 960/480、yaw 90/45 检查通过：仅有 w/j/l 三个字母，无 a/s/d 对象，前进箭头与实际移动一致、左右转弧线与动作一致、字母正立、俯仰不改变水平标记、第一视角隐藏地图标记。已查看 480 俯视图确认图标外观。报告为 `outputs/single_arrow_check_v_bk14fp/report.json`，预览为 `480/.views/0001_yaw90_top_down.png`；临时脚本 `/tmp/spatialharness-single-arrow-check.py`。Python 语法、纯英文提示词填充、diff 检查通过。新启动的 Blender worker 使用新图标，既有图片未重写。


## 31. 恢复简短导航提示词

用户在观察 `camera_20261008_195840_789666` 的原地反复转向后，要求恢复未添加多项导航约束的 system prompt。`main_agent.py` 撤回 Navigation planning、Action and verification、Recovery、Completion 四段，恢复原来的 Combining the views 和简短 Navigation and answers。移除固定路标、动作前说明预期、三步无进展、遮挡恢复和通道验证等新增要求。保留当前三图输入、单蓝色 w 箭头和 j/l 弧线说明、仅 w/j/l/i/k 的动作接口、第一视角参照、距离与角度单位、基本工具工作流及参考帧用途。用户已有模型参数和代码外中文任务注释原样保留，没有增加循环检测或工具反馈。

Python 语法、纯英文、米制/相对单位填充、五键/三图/单箭头说明以及新增约束移除检查通过，diff 检查通过。本轮未重跑模型或 Blender；重启 main_agent.py 后使用恢复后的提示词，既有会话的 system message 不会自动改变。


## 32. 俯视图目标与路线工具

用户授权增加两个仅作用于 top-down 的计划工具。`agent/tools.py` 新增 `camera_set_target(observation_id, point, look_at=None)` 与 `camera_set_route(observation_id, points)`；工具总数为六，动作仍仅 w/j/l/i/k。参数为最新观察的 observation_id 和归一化 [x, y] 坐标（左上 [0, 0]、右下 [1, 1]）。每个成功渲染的记录新增 observation_id 与当前地图坐标下的 planning。旧编号、未观察、非有限数、布尔值、越界坐标或错误结构均被拒绝。两个工具不移动相机、不修改实际轨迹，仍自动返回原来的三张独立观察图片和三栏预览；没有第四张图片，也没有新增通用工具。

`CameraSession` 将目标、朝向点与有序路线保存在场景坐标中，经 CameraClient JSON 桥接调用，计划和状态一样在渲染、记录及 state.json 保存成功后才提交。渲染器保存最后一次成功地图的投影参数，保证失败渲染后仍可使用上一次成功的 observation_id。俯视图用红色 G 圆圈标记相机站立位置、红色 LOOK 和箭头表示应面向的位置；带编号的蓝点和蓝色虚线表示计划，原紫红轨迹表示实际运动。路线自动从调用时当前相机位置起始；途经点列表包含终点。地图取景包含历史与计划标记，缩放后重新投影。第一视角隐藏所有计划标记，参考帧不加标记。修改目标会清除旧路线，point=null 清除全部计划，points=[] 仅清除路线；移动、观察、转向和 reset 保留计划，reset 不移动旧路线的起点。工具不提供碰撞检查、自动寻路或执行路线。

`main_agent.py` 添加简短英文 Navigation planning on the top-down map 段，说明先标目的地、画路线、检查返回地图再执行相机动作；工具描述和观察附件说明同为英文。README 同步六个工具、坐标、清除和保留行为。用户已有的 MAX_CONVERSATION_IMAGES=1*3、模型设置与中文任务注释均未改动。

真实 Blender 子进程通信与脚本模型经 Qwen XML 协议检查通过：两个新工具的参数解析与三图附件、标记只改变俯视图、相机与实际轨迹不变、目的地坐标转换、移动/转向/reset 保留场景计划、远距离移动触发地图重取景后的重新投影、旧观察及无效坐标拒绝、计划绘制和 state.json 提交失败时的相机/轨迹/计划/文件回滚、替换/清除和 worker 正常退出。报告为 `outputs/planning_check_tc_po9bj/report.json`；临时脚本 `/tmp/spatialharness-planning-check.py` 和 `/tmp/spatialharness-planning-inject.py`。另复用当前实际场景已有重建，验证初始位置的马桶目标与三段路线显示；报告为 `outputs/planning_scene_check_fnm46nwd/report.json`，已查看 `.views/0003_set_route_top_down.png`，人工预览为 `0003_set_route.png`，临时脚本 `/tmp/spatialharness-planning-scene-check.py`。没有调用真实模型服务或 GPU 重建，也未评估新增标记对自主导航成功率的改善。AST、英文提示词/格式化和 diff 检查通过。


## 32. 给定路线的马桶任务 prompt

用户希望将任务改为直接告诉模型从出发点到马桶的路线，以检查能否执行。`main_agent.py` 参数下的任务示例注释改为英文单行 prompt，适用于当前场景的新会话初始位置：先 camera_observe，再依次执行 w 1.0、l 21、w 1.83、j 8、w 0.42、l 92、k 15。明确 key 和 magnitude 分开传入，每次只调用一个动作，沿床左侧向床头前进后转向马桶，按给定序列执行，最终必须用当前第一视角确认马桶可见并正对它。通用 SYSTEM_PROMPT、工具和模型参数保持不变。注释不会自动进入模型请求，运行后需要将英文任务复制到 agent>。

路线根据之前成功会话 `camera_20261008_193217_140353` 的相机位置推导，复用当前 `camera_20261008_222550_137283/reconstruction`，通过真实 Navigator 七次动作与 Blender 终点渲染验证。最终位置约 [0.74427, 0.27340, 3.14080]，yaw 344.956、pitch -15，第一视角清楚显示马桶；预览为 `outputs/guided_route_check_qg3tvkdu/0001_guided_route.png`，报告为同目录 `report.json`，临时脚本 `/tmp/spatialharness-guided-route-check.py`。没有逐步渲染中间观察，也未调用真实模型服务或 GPU 重建；验证证明当前无碰撞检测的相机环境能够到达该目标视角，不证明真实物理通道可通行或 Qwen 能遵循路线。Python AST 与 diff 检查通过。


## 33. 目标与路线按任务自主选择

用户要求目标/路线工具不限定于 navigation，也不强制先设置目标再规划路线。`main_agent.py` 的英文 SYSTEM_PROMPT 将该段改为 Optional targets and routes on the top-down map，允许根据任务和当前观察选择任一工具、两个工具或都不用。检查标记后仅在移动有助于任务时执行 camera_action；到位和朝向验证也仅用于任务有相应要求时。归一化坐标、观察编号、图例、标记持久化和清除行为沿用。没有改工具、模型参数或图片设置。AST、纯英文、格式占位符和 diff 检查通过；未重跑模型或 Blender，重启 main_agent.py 后使用新提示词。


## 34. system prompt 与工具说明分工

用户要求消除 system prompt 与工具 description 的重复，避免每次新增工具都修改 system prompt。`main_agent.py` 的英文 SYSTEM_PROMPT 现在仅包含角色、三视角用途、证据判断、按任务自主选择工具/可选计划、逐次检查结果及环境事实；不列工具名称、按键、参数、坐标、单位、默认值、图例或工具特定流程。不再执行 SYSTEM_PROMPT.format。移动和最终朝向仍根据当前视角证据确认，参考帧与当前视角的区别、点云缺口、地图取景变化和非地理轴说明保留。

`agent/tools.py` 的 create_tools 增加可选 distance_units、move_step、look_step 关键字参数，入口传入当前环境配置，动态生成动作 schema 中的单位与默认步长；俯仰范围移入动作 description。沿用 create_tools(camera) 的兼容调用方式，未提供步长时只说明使用已配置步长。当前位置、w 朝向箭头和 j/l 弧线的图例移到观察消息，与原有实际轨迹和计划图例一起输出。具体相机动作仍由 schema 说明第一视角参照。工具实现、三图、模型参数与用户已有配置没有改变。README 同步分工及动态工具描述。

AST、纯英文、无工具名称/格式占位符的通用 system prompt、米制与 VGGT 相对单位/自定义默认步长的 schema 生成、旧 create_tools 调用兼容、现有实际观察的三图与图例，以及 Qwen 请求构造检查通过，diff 检查通过。没有重跑模型导航、Blender 或重建；重启 main_agent.py 后生效。


## 35. 工具 description 补充使用场景示例

用户希望工具描述说明常见使用场景，但不限制用途。`agent/tools.py` 为六个工具各增加一句英文 Useful, for example：动作可用于接近位置、换视点查看或调方向；观察可用于初始查看或不移动地复查；状态查询可用于无图确认位姿/角度；reset 可用于返回初始视点或从初始位置开始新任务；目标可用于保留目的地、选观察位置或记住最终朝向；路线可用于安排探索、组织观察视点或比较路径。示例不构成强制调用规则或适用范围限制，system prompt 沿用通用工具选择原则。仅改说明文字，参数和执行行为不变。AST、英文 schema 生成与 diff 检查通过；未重跑模型或 Blender。


## 36. camera_action 单步撤销

用户授权通过现有动作参数增加 `camera_action(key="undo")`，不新增工具。`CameraSession` 只保存最近一次成功非 undo 动作前的完整状态，包含位置、yaw、pitch 与点半径；成功普通动作替换备份，成功 undo 或 reset 清空备份。观察、状态查询和目标/路线操作不覆盖备份，失败动作、undo 或 reset 也不覆盖/消费备份。所有状态更新和备份变化在图片与记录成功保存后提交。undo 不接受非空 magnitude，无可撤销状态时返回英文错误。沿用 CameraClient 的 execute 请求，无独立 undo 通信接口。

撤销自动返回三张观察图片；目标、朝向点与计划路线保留。实际历史不删除，位置撤销会追加返回路径，纯转向/俯仰/点半径撤销不新增位置点。动作 schema 的 key enum 增加 undo，英文 description 说明用途和备份生命周期，reset 描述说明清除备份；README 同步。system prompt、模型和图片预算配置均未改。

真实 Blender 子进程通信与脚本模型经 Qwen XML 检查通过：undo 工具参数与三图附件、无备份错误、移动/转向/俯仰/点半径的完整恢复、只撤销最近一步且不可连续使用、观察/状态/目标/路线保留备份、目标与路线保留、历史追加返回位置、不合法参数与渲染失败动作保留备份、undo 的俯视渲染失败及 state.json 保存失败后的状态/计划/轨迹/文件回滚和成功重试、失败 reset 保留备份、成功 reset 清空备份、原视角恢复后的图片像素相等、图片预算整组裁剪与 worker 正常退出。报告为 `outputs/undo_check_1l4e8u2j/report.json`，临时脚本 `/tmp/spatialharness-undo-check.py` 和 `/tmp/spatialharness-undo-inject.py`。AST、六工具英文 schema 和 diff 检查通过。未调用真实模型服务或 GPU 重建；重启 main_agent.py 后使用 undo。


## 37. 强化当前位置与朝向标记

用户要求相机朝向标记更醒目、放大，并置于最高图层。`scene/rendering/views.py` 将当前位置改为青色圆点，前进箭头改为更宽更长的青色箭头，均增加白边与深色外轮廓；标记整体基础比例从 .025 提高至 .032，保留 w 和绿色 j/l 弧线、正立字母。相机标记相对于俯视相机的深度改为 -.01，位于计划（-.04）和轨迹（-.06）前方；只缩放 x/y，避免大地图的缩放改变深度或引起裁剪。`agent/tools.py` 同步英文观察图例，camera_set_route 描述增加通常建议先 camera_set_target 设置目的地的英文句子，不强制调用顺序。README 同步，system prompt 和模型配置未改。

复用 camera_20261009_003409_499055 的重建进行真实 Blender 渲染，查看三栏预览并检查目标、路线和历史轨迹与相机标记重叠时的层级；960/480、yaw 0/45/90/180 的朝向、字母正立、层级和裁剪检查通过，第一视角隐藏标记，三图附件和英文说明检查通过。报告为 `outputs/camera_marker_check_gn7fu9np/report.json`，普通预览为 `0001_distinct_current_camera.png`，重叠预览为 `0002_overlap_priority.png`；脚本为 `/tmp/spatialharness-camera-marker-check.py`。没有调用模型导航或 GPU 重建；新启动的 worker 使用新标记，既有会话图片不重写。


## 38. 路线规划沿空地避开障碍

用户要求 camera_set_route 提醒模型走空地，避免穿模和撞墙。`agent/tools.py` 的英文 description 增加每段路线沿可见空地和通道规划、与墙体/隔断/家具/设施保持间距的说明；点云缺口不代表可通行，不确定时检查当前第一视角。仅修改工具说明，仍不提供碰撞检测或自动执行路线。语法和 diff 检查通过，未运行模型或 Blender。


## 39. 恢复 agent WASD 与四方向标记

用户要求将 a/s/d 加回 agent，并恢复俯视图四个移动方向。`agent/tools.py` 的 camera_action 允许 w/a/s/d/j/l/i/k 和 undo；英文 description、距离参数、默认步长及错误说明同步，删除横向移动必须先转向再 w 的旧说明。所有移动仍相对于当前第一视角的水平朝向，保持高度和朝向。环境导航原本支持 WASD，无需修改底层动作。`scene/rendering/views.py` 保留醒目的青色圆点和长 w 箭头，添加短白色 a/s/d 臂和字母，恢复三短一长十字；保留白边/深色轮廓、最前层、绿色 j/l 弧线和六字母正立。观察英文图例和 README 同步，通用 system prompt、地图坐标格式和模型配置不变。

复用已有重建完成真实 Blender 三栏及重叠预览，960/480、yaw 0/45/90/180、pitch 0/60 的四方向标记与实际移动方向/距离一致，移动保持高度与朝向，六字母正立、标记层级/裁剪/第一视角隐藏及 action schema 检查通过。报告为 `outputs/camera_marker_check_votzhj9l/report.json`，预览为 `0001_distinct_current_camera.png`；临时脚本 `/tmp/spatialharness-wasd-marker-check.py`。语法与 diff 检查通过，未调用模型导航或 GPU 重建；重启 main_agent.py 后生效。


## 40. 撤回 agent ASD 与四方向标记

用户再次要求删除 a/s/d，覆盖上一节。camera_action 恢复只允许 w/j/l/i/k 和 undo，英文动作说明、距离参数、默认步长和观察图例同步恢复。俯视图删除三个短臂及 a/s/d 字母，保留醒目的青色圆点、带轮廓的单 w 箭头、最前层和绿色 j/l 弧线。README 同步；手动环境底层动作沿用原有实现。语法、工具 schema 和 diff 检查通过，本轮未重跑 Blender 或模型；重启 main_agent.py 后生效。


## 41. /new 复用环境开始新对话

用户要求 main_agent.py 支持 /new，跳过重复重建并清空聊天记录。交互循环识别大小写不敏感的 /new，先将当前 conversation.json 归档为 conversation_<时间戳>.json，再调用已有 Agent.reset() 清空消息并保留 system prompt；新对话继续写入 conversation.json。同一个 backend、Blender worker 和重建结果继续使用，相机位姿、轨迹、目标/路线标记与撤销记录保留。启动帮助和 README 同步。没有修改 agent 核心或环境代码。

用脚本模型、模拟重建进程和相机 worker 验证完整入口交互：多轮问答中的工具消息及推理在 /new 后不进入下一次模型请求，两次 /new 各保留旧日志，最新 conversation.json 只含新对话，/new 不发送给模型，重建/backend/worker 各只启动一次并在 /exit 时正常释放。临时材料在 /tmp/spatialharness-new-chat-owteoykz。语法和 diff 检查通过，未调用真实模型、Blender 或 GPU 重建。


## 42. /new 同时重置全部探索状态

用户澄清 /new 要连相机和历史轨迹等全部重置，覆盖上一节的环境保留行为。CameraClient 和 CameraSession 的 reset 增加关键字 fresh=False；/new 先调用 camera.reset(fresh=True)，恢复初始位置、yaw、pitch、点半径，轨迹只保留初始点，并清空 target/look_at/route 和 undo。环境重置成功后才归档旧聊天并清空模型消息，保留 system prompt。复用重建、Blender worker 和模型客户端；旧观察文件保留，编号递增避免覆盖。常规 camera_reset/reset() 仍保留旧轨迹和规划标记。fresh 重置沿用提交与失败回滚，失败时保留原位姿、轨迹、计划和 undo。README 同步。

用合成点云 fixture、真实 Blender 子进程和脚本模型验证 main_agent.py 完整交互：移动/转向/俯仰/点半径改变和目标/路线设置后，两次 /new 全量恢复；轨迹为一个起点、规划为空、undo 不可用；首次新模型请求只含 system 和新任务，旧聊天分别归档，重建/worker/backend 各只启动一次。常规 reset 保留轨迹与规划，注入失败的 fresh reset 保留状态文件及 undo 并可重试，worker 正常退出。重置后第一视角与俯视图像素均与最初观察完全一致。报告为 /tmp/spatialharness-new-environment-0wbznu1d/report.json，临时脚本 /tmp/spatialharness-new-environment-check.py 和 /tmp/spatialharness-fresh-reset-inject.py。语法与 diff 检查通过，未调用真实模型服务或 GPU 重建。


## 43. /new 新建独立 camera 目录并冻结旧目录

用户进一步要求 /new 新建 outputs/camera_<时间戳>/，旧目录保持原样，不在旧目录归档聊天。本节覆盖前两节的归档方式。main_agent.py 为每次 /new 创建同一父目录下的新 camera 目录，reconstruction/ 符号链接指向本次进程最初的重建目录；调用 CameraClient.start_session(output) 后更新当前 output 与 agent.conversation_path，并清空聊天。新对话、状态、图片及日志只写入新目录；不移动、改名或覆盖旧目录的 conversation.json。仍复用同一个 Blender worker、已加载场景及模型客户端，不重复重建。

CameraSession.start_session 在 Renderer.new_session 上下文中完整重置位姿、点半径、轨迹、target/look_at/route 和 undo。Renderer 同时切换输出路径、观察编号、地图投影元数据及 worker stdout/stderr，确保后续渲染和 Blender 退出日志不写回旧目录；新编号从 1 开始。切换或初始渲染失败时恢复原输出路径、编号、地图元数据、日志描述符及相机状态，客户端日志路径也恢复。模型工具仍为原有六个，未暴露新通用工具。README 同步。

使用合成重建 fixture、真实 Blender 和脚本模型检查完整入口：两次 /new 各创建独立 camera 目录，新的 conversation.json 仅含新任务，初始观察编号为 1，全部环境状态清空；原始重建通过符号链接复用，重建/worker/backend 各只初始化一次。切换前快照核对旧目录全部文件内容、文件和目录修改时间，在后续动作和 /exit 后完全不变；没有生成归档文件。注入失败的切换保持旧目录、状态/轨迹/计划/undo，后续切换可重试；新第一视角与俯视图像素与最初观察一致。报告为 /tmp/spatialharness-new-directory-dtijofjt/report.json，脚本 /tmp/spatialharness-new-directory-check.py。语法与 diff 检查通过，未调用真实模型服务或 GPU 重建。
