# 进度与交接

每完成一个任务就更新这份文件并提交。它是跨会话的唯一记忆：新会话靠它知道做到了哪里，对话被压缩后也靠它找回方向。

## 当前状态

- 阶段：0A 进行中，**因用量上限在任务 5（E1）中途停止**。首次开始于 2026-10-03 09:50（UTC+8），当时命令在别的机器上执行，在任务 1 暂停；10:25 在装有 HYSYS 的工作站（主机名 myWin10VM）上恢复。任务 1 至 3 已完成，任务 5 只做了第一次运行，任务 4、6 至 11 未开始。
- 最近通过的闸门：无（质量工具在任务 2 全绿；本次未改 `src/`）
- 最近一次更新：2026-10-03 10:50
- 时间记法：本机时钟是 UTC，进度文件里的时间一律换算成 UTC+8（加 8 小时）。

阶段顺序：0A → 0B → 0C → 1A → 1B → 1C → 2A → 2B → 2C → 3A → 3B（可选）→ 4（可选）→ 5。一个会话只做一个阶段。

## 环境事实

由阶段 0A 填写，之后发现变化时更新。

| 项 | 值 |
|---|---|
| 助手执行命令的机器 | 工作站 `myWin10VM`（Windows 10 Pro 19045，用户 `mywin10vm\azureuser`），时钟为 UTC |
| Python 版本与解释器路径 | 3.12.4，64 位，`C:\Program Files\Python312\python.exe`（`py.exe` 在 `C:\Windows\py.exe`）。PowerShell 里 `python` 直接可用 |
| 虚拟环境 | `C:\Users\azureuser\Desktop\ChemicalAgent\.venv`，解释器 `.venv\Scripts\python.exe`，已 `pip install -e ".[dev]"`（pywin32 312、ruff 0.16.10、mypy 2.4.0、pytest 9.1.1、pydantic 2.13.5）。运行脚本一律写 `.\.venv\Scripts\python.exe`，不依赖激活 |
| 输出编码的设置（如 `PYTHONUTF8`） | 实测：没有 `PYTHONUTF8` 和 `PYTHONIOENCODING` 时，输出被管道接走的 Python 进程用 cp1252，打印中文抛 `UnicodeEncodeError`；设 `PYTHONUTF8=1` 后正常。做法：`setx PYTHONUTF8 1`（用户级，对之后新启动的进程生效）。助手的会话进程由宿主预设了 `PYTHONIOENCODING=utf-8:surrogateescape`，所以不依赖 `setx`。探针脚本开头自己 `sys.stdout.reconfigure(encoding="utf-8")`，输出文件由脚本用 `encoding="utf-8"` 写 |
| HYSYS 版本与 ProgID | `Aspen HYSYS Version 15 (41.0)`（`app.Version` 实测）。通用 ProgID `HYSYS.Application`（= `.Latest`，CurVer 为 `HYSYS.Application.V15.0`）；每次新开进程的是 `HYSYS.Application.NewInstance`（待验证）。进程名 `AspenHysys.exe`。详见台账"连接与绑定方式" |
| HYSYS 安装目录 | `C:\Program Files\AspenTech\Aspen HYSYS V15.0` |
| 反向探测用的参考 Case 的路径 | 待任务 7 |
| LLM 供应商、模型、密钥所在的环境变量名 | 待用户提供（D1） |
| 远程仓库地址 | 待用户提供，之前只做本地提交 |
| Git 署名 | 机器上没有配置 `user.name` 和 `user.email`。暂用仓库级配置：`xibeibei63 <xibeibei63@gmail.com>`（取自账号邮箱），等用户确认 |

## 已完成

每个阶段开始和结束时各记一行时间，阶段 5 用它整理开发时间线。

| 阶段 | 开始和结束的时间 | 会话数 |
|---|---|---|

| 阶段 | 任务 | 提交 | 验证方式 |
|---|---|---|---|
| 0A | 1 确认能执行 Windows 程序 | 无代码改动 | `python --version` 得 3.12.4；`platform.architecture()` 得 64bit、WindowsPE；`HKLM\SOFTWARE\AspenTech` 存在，`C:\Program Files\AspenTech\Aspen HYSYS V15.0` 存在 |
| 0A | 2 仓库和工具 | fbfc7bf | `ruff check .` 通过；`ruff format --check .` 3 个文件已格式化；`mypy src` 无问题；`pytest` 13 passed；`PYTHONUTF8` 的实测见"环境事实" |
| 0A | 3 建台账 | 029bbe7 | `docs/HYSYS_INTEGRATION.md` 有 10 个固定节名，接口事实表有 H1 至 H26 共 26 行，状态均为"未测试" |
| 0A | 5 连接 HYSYS（E1），**只完成第一次运行** | 本次提交 | `spikes/e1_connect.py --exit keep` 运行成功：`Dispatch("HYSYS.Application")` 冷启动 35.2 秒，`Version` 为 `Aspen HYSYS Version 15 (41.0)`，进程 `AspenHysys.exe`（PID 2092），窗口所属进程与 `tasklist` 一致。H1 记为部分确认。"已有实例是否复用"和"退出方式"未验证 |
| 0A | 只读勘查（计划模式下完成，无脚本） | 本次提交 | 注册表 ProgID、`hysys.tlb` 的接口名与集合的 `Add` 签名、安装目录里的 `hysys.hh`、定义文件、帮助文件，写入台账 L0 和"创建反应的线索"初稿（均未运行验证） |

## 进行中

当前任务的设计草图（涉及的文件、公开接口、估计行数）写在这里，做完后移到"已完成"。

**阶段 0A 总览（2026-10-03 10:35）。** 全部是探针，不写 `src/`。每个脚本独立运行，开头自己把 stdout 设成 UTF-8，输出由脚本写到 `spikes/out/`，结束前关闭自己打开的 Case，不留 HYSYS 进程。

| 文件 | 作用 | 估计行数 |
|---|---|---|
| `docs/HYSYS_INTEGRATION.md` | 台账：10 个固定节名，H1–H26 逐项更新，每个探针一条日志 | 约 300 |
| `spikes/e0_llm_ping.py` | 最小 LLM 请求，密钥只读环境变量（等用户给出供应商） | 约 40 |
| `spikes/e1_connect.py` | 查注册表 ProgID，取 Application，打印版本和进程号，演示退出与保留 | 约 100 |
| `spikes/typelib_dump.py` | 用 `EnsureDispatch` 生成类型库包装，整理接口名与成员，检索关键词 | 约 120 |
| `spikes/e2_read_write.py` | 流体包、物流读写、求解器开关、已知性、空值哨兵 | 约 160 |
| `spikes/e3_reverse_probe.py` | 枚举单元操作，对三种反应器、反应、反应集做反向探测 | 约 200 |

## 下一步

先重读 `CLAUDE.md`、本文件和 `docs/prompts/phase-0a.md`，然后按顺序做本阶段剩下的工作：

1. **收完任务 5（E1）。** 先查 `tasklist` 有没有残留的 `AspenHysys.exe`（E1 第一次运行留下 PID 2092，窗口里没有 Case，可以退出）。再做对照运行：对已有实例 `--exit keep` 连一次，看有没有新进程；`--progid HYSYS.Application.NewInstance`；`--exit quit`、`--exit release`、`--exit kill` 各一次，用 `tasklist` 核对。结果写进台账 H1、"连接与绑定方式"和探索日志。
2. **任务 6。** 写 `spikes/typelib_dump.py`：`gencache.EnsureModule` 生成早绑定包装，整理接口和成员到 `spikes/out/typelib_members.txt`（小于 1 MB），检索 `Reaction`、`ReactionSet`、`Equilibrium`、`Conversion`、`Gibbs`、`Reactor`、`Add`、`BackDoor`、`XML`、`Script`；用 `ExtSDK\hysys.hh` 核对 `Add` 的参数类型；弄清早绑定是否需要 `CastTo`。
3. **任务 7。** 把候选示例复制到临时目录再用 COM 打开，列单元操作类型名，最多 20 分钟（候选见台账 L0）。凑不齐三种反应器就把阶段提示词里的清单发给用户，同时继续任务 8。
4. **任务 8（E2）、任务 9（E3）**，然后任务 10（帮助文件，时间不够可推后）、任务 4（E0，等用户给出 LLM 信息）、任务 11（收尾）。
5. E1 验证之后，把公共的连接、进程清单、日志输出抽到 `spikes/_common.py`，后面的探针导入它，每个脚本仍可单独运行。

本阶段沿用的约定：只结束本脚本启动的实例，对已有实例只在没有打开任何 Case 时才退出；示例 Case 先复制到临时目录再打开，不保存回原位置，也不提交 Aspen 的示例文件；用户在 HYSYS 界面里手工建参考 Case 时，探针用 `NewInstance` 另开实例，不碰用户的窗口；COM 调用卡住超过一分钟，先截屏看有没有弹窗，再请用户看一眼。

## 待决策

需要用户确认的事项。默认值来自 `MASTER_PLAN.md` §25，用户没有另行指示时按默认值执行。

| 编号 | 事项 | 默认 | 状态 |
|---|---|---|---|
| D1 | LLM 供应商和模型；VM 能否直连 | 待用户提供 | 未定 |
| D2 | 场景 3 是否加入氧气 | 不加，按题面建模，在报告中说明 | 按默认 |
| D3 | "80000 Nm³/h"的含义 | 进料的总摩尔流量 | 按默认 |
| D4 | 二甲苯异构体分配 | 对 : 间 : 邻 = 24 : 52 : 24 | 按默认 |
| D5 | 压力是绝压还是表压 | 绝压 | 按默认 |
| D6 | 场景 1 的进料流量基准 | CH4 1000 kmol/h | 按默认 |
| D7 | Demo 形态 | 命令行，HYSYS 窗口可见 | 按默认 |
| D8 | 机动时间先做泛化还是先做加固 | 先泛化 | 按默认 |
| D9 | 远程仓库地址；Git 署名的名字和邮箱（暂用仓库级配置 `xibeibei63 <xibeibei63@gmail.com>`，取自账号邮箱） | 待用户提供，之前只做本地提交 | 未定 |

## 决策日志

实现过程中做出的设计决定和假设。

| 日期 | 决策 | 原因 |
|---|---|---|

## 问题与解决

遇到的问题、试过的做法、最后的结论。走不通的尝试也记在这里，它们是考核报告"探索过程"一节的素材。

| 日期 | 问题 | 试过什么 | 结论 |
|---|---|---|---|
| 2026-10-03 | 阶段 0A 任务 1：助手执行命令的机器（主机名 WIN-607I4J4LV6S）不是装有 HYSYS 的工作站 | 在这台机器上查：注册表 HKCR 里没有 HYSYS/Aspen 的 ProgID，HKLM 下没有 AspenTech 键，没有 HYSYS 进程。这台机器上的 `mstsc.exe` 已经连着工作站的 3389 端口，所以远程桌面是通的，但助手的工具不经过这条连接，命令仍然在本机执行。本机的 `python` 是 Microsoft Store 占位程序，可用的解释器在 Anaconda（3.12，64 位），这只是本机的情况 | 暂停，等用户决定：在工作站上运行助手（推荐），或者用共享文件夹中转。**已解决**：用户改在工作站（myWin10VM，装有 Aspen HYSYS V15.0）上重开会话，2026-10-03 10:25 恢复，任务 1 重新核对通过 |
| 2026-10-03 | 输出被管道接走的 Python 进程打印中文报 `UnicodeEncodeError`（任务 2） | 去掉 `PYTHONIOENCODING` 和 `PYTHONUTF8` 复现：默认 cp1252。设 `PYTHONUTF8=1` 后正常 | `setx PYTHONUTF8 1`；探针脚本自己 `sys.stdout.reconfigure(encoding="utf-8")`。详见"环境事实" |
| 2026-10-03 | 想靠扫描示例 `.hsc` 的字节找出含反应器的 Case（任务 7 的预案） | 对 212 个文件按 ASCII 和 UTF-16 查 `conreactor`、`eqreactor`、`gibbsreactor` 等字符串，0 个命中 | 走不通：`.hsc` 是压缩格式，只能用 COM 打开并枚举单元操作。见台账 L0 |
| 2026-10-03 | 会话在 E1 第一次运行之后因用量上限中断 | E1 run1 按 `--exit keep` 留下了 HYSYS 实例 | 见"下一步"第 1 条 |

## 与计划的偏差

实现与 `MASTER_PLAN.md` 不一致的地方，以及原因。

| 日期 | 计划中的说法 | 实际做法 | 原因 |
|---|---|---|---|
