# 进度与交接

每完成一个任务就更新这份文件并提交。它是跨会话的唯一记忆：新会话靠它知道做到了哪里，对话被压缩后也靠它找回方向。

## 当前状态

- 阶段：0A 进行中。首次开始于 2026-10-03 09:50（UTC+8），当时命令在别的机器上执行，在任务 1 暂停；10:25 在装有 HYSYS 的工作站（主机名 myWin10VM）上恢复，因用量上限在任务 5（E1）中途停止。**第 3 个会话于 2026-10-08 09:50（UTC+8）接手。**任务 1 至 3、5（E1，共 9 次运行）、6（类型库导出）、7（找参考 Case）、8（E2 读写）、9（E3 反向探测，只用了示例 Case，Gibbs 部分等用户的参考 Case）已完成；任务 4（等 D1）、10、11 未开始。当前没有残留的 HYSYS 进程。
- 最近通过的闸门：无（质量工具 2026-10-08 复核全绿：ruff format/check、mypy src、pytest 13 passed；本阶段不改 `src/`）
- 最近一次更新：2026-10-08 11:00
- 时间记法：本机时钟是 UTC，进度文件里的时间一律换算成 UTC+8（加 8 小时）。
- 推送状态：本地 main 已合并远端的初始提交，并已推送（`ea240ed..ff56cdb`）。推送方式见"环境事实"的"GitHub 凭据"。

阶段顺序：0A → 0B → 0C → 1A → 1B → 1C → 2A → 2B → 2C → 3A → 3B（可选）→ 4（可选）→ 5。一个会话只做一个阶段。

## 环境事实

由阶段 0A 填写，之后发现变化时更新。

| 项 | 值 |
|---|---|
| 助手执行命令的机器 | 工作站 `myWin10VM`（Windows 10 Pro 19045，用户 `mywin10vm\azureuser`），时钟为 UTC |
| Python 版本与解释器路径 | 3.12.4，64 位，`C:\Program Files\Python312\python.exe`（`py.exe` 在 `C:\Windows\py.exe`）。PowerShell 里 `python` 直接可用 |
| 虚拟环境 | `C:\Users\azureuser\Desktop\ChemicalAgent\.venv`，解释器 `.venv\Scripts\python.exe`，已 `pip install -e ".[dev]"`（pywin32 312、ruff 0.16.10、mypy 2.4.0、pytest 9.1.1、pydantic 2.13.5）。运行脚本一律写 `.\.venv\Scripts\python.exe`，不依赖激活 |
| 输出编码的设置（如 `PYTHONUTF8`） | 实测：没有 `PYTHONUTF8` 和 `PYTHONIOENCODING` 时，输出被管道接走的 Python 进程用 cp1252，打印中文抛 `UnicodeEncodeError`；设 `PYTHONUTF8=1` 后正常。做法：`setx PYTHONUTF8 1`（用户级，对之后新启动的进程生效）。助手的会话进程由宿主预设了 `PYTHONIOENCODING=utf-8:surrogateescape`，所以不依赖 `setx`。探针脚本开头自己 `sys.stdout.reconfigure(encoding="utf-8")`，输出文件由脚本用 `encoding="utf-8"` 写 |
| HYSYS 版本与 ProgID | `Aspen HYSYS Version 15 (41.0)`（`app.Version` 实测）。通用 ProgID `HYSYS.Application`（= `.Latest`，CurVer 为 `HYSYS.Application.V15.0`），已有实例就复用；每次新开进程的是 `HYSYS.Application.NewInstance`（run3、run5 已验证）。进程名 `AspenHysys.exe`。早绑定用 `gencache.EnsureDispatch`，包装缓存在 `%TEMP%\gen_py\3.12`。详见台账"连接与绑定方式" |
| HYSYS 安装目录 | `C:\Program Files\AspenTech\Aspen HYSYS V15.0` |
| 反向探测用的参考 Case 的路径 | 自带示例 `C:\Program Files\AspenTech\Aspen HYSYS V15.0\Samples\Synthesis Gas Production.hsc`（2 台转化反应器、3 台平衡反应器，没有 Gibbs；先复制到临时目录再打开）。三种反应器齐全的 `spikes/ref_cases/three_reactors.hsc` 等用户手工建（D11） |
| LLM 供应商、模型、密钥所在的环境变量名 | 待用户提供（D1） |
| 远程仓库地址 | `https://github.com/xibei03/ChemicalAgent.git`（2026-10-08 由用户给出，已配置为 `origin`，默认分支 `main`）。远端仓库是公开的，不登录也能 `fetch`，推送需要登录 |
| GitHub 凭据 | 2026-10-08 接手时这台机器上没有任何凭据；用户随后在应用的终端里运行 `gh auth login`，登录为 `xibei03`（令牌在 Windows 凭据库，协议 https）。`git` 的凭据助手仍然是系统级的 `manager`（GCM），没有运行 `gh auth setup-git`，所以推送时用一次性助手，不改任何持久配置：`git -c credential.helper= -c "credential.helper=!gh auth git-credential" push`。助手不代填、不收口令或令牌 |
| Git 署名 | 机器上没有配置全局 `user.name` 和 `user.email`。仓库级配置：`xibeibei63 <xibeibei63@gmail.com>`（取自账号邮箱）。远端初始提交的作者是 `xibei03 <jsl_03@163.com>`，见 D9 |

## 已完成

每个阶段开始和结束时各记一行时间，阶段 5 用它整理开发时间线。

| 阶段 | 开始和结束的时间 | 会话数 |
|---|---|---|

| 阶段 | 任务 | 提交 | 验证方式 |
|---|---|---|---|
| 0A | 1 确认能执行 Windows 程序 | 无代码改动 | `python --version` 得 3.12.4；`platform.architecture()` 得 64bit、WindowsPE；`HKLM\SOFTWARE\AspenTech` 存在，`C:\Program Files\AspenTech\Aspen HYSYS V15.0` 存在 |
| 0A | 2 仓库和工具 | fbfc7bf | `ruff check .` 通过；`ruff format --check .` 3 个文件已格式化；`mypy src` 无问题；`pytest` 13 passed；`PYTHONUTF8` 的实测见"环境事实" |
| 0A | 3 建台账 | 029bbe7 | `docs/HYSYS_INTEGRATION.md` 有 10 个固定节名，接口事实表有 H1 至 H26 共 26 行，状态均为"未测试" |
| 0A | 5 连接 HYSYS（E1），run1 至 run9，已完成 | 2427c43（run1）、4904693（run2）、58c29f4（run3 至 run9、`_common.py`） | run1：`Dispatch("HYSYS.Application")` 冷启动 35.2 秒，`Version` 为 `Aspen HYSYS Version 15 (41.0)`，进程 `AspenHysys.exe`，窗口所属进程与 `tasklist` 一致。run2：已有实例被复用（0.0 秒），`Quit()` 后 3.5 秒内消失。run3、run5：`NewInstance` 每次新开进程，`Quit()` 只结束自己（run5 里 7280 退出，14024 继续运行）。run6：丢掉 COM 引用并 `CoUninitialize()` 后 60 秒内实例仍在。run7：`taskkill /PID /T /F` 1.6 秒内结束。run8、run9：`EnsureDispatch` 返回 `gen_py` 的 `_Application`，属性名区分大小写（`app.Name` 报错，类型库里是 `name`），包装生成后 `Dispatch` 也返回同一个类。H1 升为已确认，新增 H27、H28。每次运行后 `tasklist` 无残留进程 |
| 0A | 6 导出类型库（`typelib_dump.py`） | 本次提交 | `.venv\Scripts\python.exe spikes/typelib_dump.py` 成功运行：类型库 1140 个类型（726 个 dispatch 接口、377 个枚举、22 个组件类）；42 个接口有 `Add`，多数是 `Add(name: VARIANT[opt], Type: VARIANT[opt])`；`EnsureModule` 2 至 4 秒生成包装（758 个类），`ReactionSets`、`Reactions`、`Operations`、`FluidPackages`、`SimulationCases` 的包装类都有 `Add`。输出 5 个文件，最大 629 KB，都小于 1 MB。三种反应器是 dispatch 接口 `ConversionReactor`、`EquilibriumReactor`、`GibbsReactor`；XML、`PlayScript`、`BackDoor` 三条降级通道在类型库里都有。结论都只在类型库层面，没有运行验证 |
| 0A | 7 找含反应器的参考 Case | 本次提交 | `spikes/find_ref_case.py` 打开 6 个候选示例：Synthesis Gas Production 含 2 台转化反应器（`conversionreactorop`）和 3 台平衡反应器（`equilibriumreactorop`）；Ammonia Synthesis 含 3 台 PFR；CSTR - Dynamic Model 含 1 台 CSTR；Toluene_Disproportionation_Example 是分子级炼油反应器；Ethanol Dehydration、Ethanol Plant 没有反应器；Green Ammonia Process 弹出 Aspen Properties 模态对话框，`Open` 卡住，看门狗读出文字，`BM_CLICK` 关闭。**没有一个示例含 Gibbs 反应器**，需要用户手工建参考 Case（D11）。`Open` 返回类型化的 `_SimulationCase`，`Item(i)` 返回具体的反应器类型，不需要 `CastTo` |
| 0A | 8 读写已有 Case（E2、E2b） | 本次提交 | `spikes/e2_read_write.py` 两次运行（run1、run2）：流体包 `Basis-1`、物性包 `PengRobinson`、7 个组分可读；物流 T、P、流量用 `GetValue(unit)`、`SetValue(value, unit)`，写后读回一致，不认识的单位抛错；写入同步重算（热负荷 6558.8 → 6544.7 kW）；`Solver.CanSolve=False` 时改进料流量，出料不变（475.36），`CanSolve=True` 这一句 0.46 秒同步求出新值（523.26）；没有规定的变量 `IsKnown` 为 False、值为 -32767.0；新物流 `MaterialStreams.Add("probe")` 成功并能写组成、闪蒸完成；8.3 短路径打开 Case 失败，长路径成功。`spikes/e2b_quit_with_case.py`：Case 打开着或改过时，`Quit()`、`Close()` 都不弹窗。H2、H6、H13、H17、H22 升为已确认 |
| 0A | 9 反向探测（E3），示例 Case | 本次提交 | `spikes/e3_reverse_probe.py` 对 Synthesis Gas Production 的 5 台反应器（2 转化、3 平衡）、4 个反应、3 个反应集做只读探测：`Item(i)` 直接返回具体类型；反应 `TypeName` 为 `conversionrxn`、`equilibriumrxn`，反应集为 `rxnset`；出口温度规定在气相出料物流上（`State` 1、`CanModify` True），带能流的反应器热负荷是计算值；反应集成员是 `ActiveReactions`/`InactiveReactions`，与流体包的关联是出现在 `fp.ReactionPackage.ReactionSets` 里；转化率是百分数、同一基准组分的多个转化反应并行按进料算（Reformer 40%+30%，进料甲烷 90.72，反应掉 63.50 kgmole/h）；没连能流时 `op.EnergyStream` 抛 `com_error`。XML 导出 6.5 MB 但不含反应定义。**未解决：**`LnKSource` 读出 4 与类型库枚举对不上；Gibbs 反应器没有样本。H16、H26 部分确认，H18、H20 已确认 |
| 0A | 只读勘查（计划模式下完成，无脚本） | 2427c43 | 注册表 ProgID、`hysys.tlb` 的接口名与集合的 `Add` 签名、安装目录里的 `hysys.hh`、定义文件、帮助文件，写入台账 L0 和"创建反应的线索"初稿（均未运行验证） |

## 进行中

当前任务的设计草图（涉及的文件、公开接口、估计行数）写在这里，做完后移到"已完成"。

**阶段 0A 总览（2026-10-03 10:35，2026-10-08 更新）。** 全部是探针，不写 `src/`。每个脚本独立运行，开头自己把 stdout 设成 UTF-8，输出由脚本写到 `spikes/out/`，结束前关闭自己打开的 Case，不留 HYSYS 进程。

| 文件 | 作用 | 估计行数 | 状态 |
|---|---|---|---|
| `docs/HYSYS_INTEGRATION.md` | 台账：10 个固定节名，H1–H28 逐项更新，每个探针一条日志 | 约 300 | 持续更新 |
| `spikes/_common.py` | 探针共用：UTF-8 输出、边打印边落盘的日志、HYSYS 进程和窗口检测、看门狗 | 约 150 | 已完成 |
| `spikes/e1_connect.py` | 查注册表 ProgID，取 Application，打印版本和进程号，演示退出与保留 | 约 150 | 已完成 |
| `spikes/typelib_dump.py` | 导出类型库：接口和成员、枚举、关键词命中、反应相关接口的完整签名、早绑定包装检查 | 约 270 | 已完成 |
| `spikes/e0_llm_ping.py` | 最小 LLM 请求，密钥只读环境变量（等用户给出供应商） | 约 40 | 挂起（D1） |
| `spikes/find_ref_case.py` | 任务 7：把示例 Case 复制到临时目录，用 COM 打开，列单元操作类型名 | 约 140 | 已完成 |
| `spikes/e2_read_write.py` | 流体包、物流读写、求解器开关、已知性、空值哨兵 | 约 260 | 已完成 |
| `spikes/e2b_quit_with_case.py` | 有打开的 Case 时 `Quit()`、`Close()` 会不会弹窗 | 约 110 | 已完成 |
| `spikes/e3_reverse_probe.py` | 枚举单元操作，对三种反应器、反应、反应集做反向探测 | 约 290 | 示例 Case 已完成，等用户的参考 Case 补跑 |

## 下一步

先重读 `CLAUDE.md`、本文件和 `docs/prompts/phase-0a.md`，然后按顺序做本阶段剩下的工作：

1. **任务 10（帮助文件）。** 用 `hh.exe -decompile` 解包 `ww10_com.chm`、`xhysys.chm` 到 `spikes/out/help_html/`（已在 `.gitignore`），检索 `Reactions.Add`、`ReactionSet`、`ActiveReactions`、`Type` 参数的说明，以及 Gibbs 反应器的类型选项；把有用的页面标题和结论记进台账。
2. 任务 11（收尾）：核对台账 H1、H2、H6、H13、H17、H18、H22 和三个节；跑 `python tests/test_code_health.py`；写交接报告。
3. **用户的参考 Case 到了之后**（D11）：补跑 `.venv\Scripts\python.exe spikes\e3_reverse_probe.py --case spikes\ref_cases\three_reactors.hsc --tag three`，解决 `LnKSource` 的数字对应和 Gibbs 的 `ReactorType`，更新台账。
4. **任务 4（E0）** 等用户给出 LLM 供应商、模型和密钥所在的环境变量（D1）；用户说"需要密钥的先跳过"，所以现在不做，需要时再向用户要。

本阶段沿用的约定：只结束本脚本启动的实例，对已有实例只在没有打开任何 Case 时才退出；示例 Case 先复制到临时目录再打开，不保存回原位置，也不提交 Aspen 的示例文件；用户在 HYSYS 界面里手工建参考 Case 时，探针用 `NewInstance` 另开实例，不碰用户的窗口；COM 调用卡住超过一分钟，先截屏看有没有弹窗（`_common.watch` 会自动打印窗口），再请用户看一眼。每个任务提交后用一次性凭据助手推送（见"环境事实"）。

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
| D9 | Git 署名的名字和邮箱。仓库级配置是 `xibeibei63 <xibeibei63@gmail.com>`（取自账号邮箱），而远端初始提交的作者是 `xibei03 <jsl_03@163.com>`。署名不一致时，GitHub 不会把提交关联到 `xibei03` 的账号 | 保持现状，历史提交的署名不改 | 未定（远程地址已于 2026-10-08 给出） |
| D11 | 用户在 HYSYS 界面里手工建参考 Case `spikes/ref_cases/three_reactors.hsc`（清单见 `docs/prompts/phase-0a.md` 任务 7）：自带示例里没有 Gibbs 反应器 | 用户建好后，助手补跑 E3，并向用户确认 Gibbs 类型选项和出口温度规定在界面上的位置 | 等用户 |
| D10 | GitHub 登录：这台机器原本没有存储的凭据 | 用户登录后，助手补推全部提交 | 已解决（用户 `gh auth login` 登录为 `xibei03`，首次推送 2026-10-08 成功）。可选：用户若想让以后的 `git push` 不再需要一次性助手，自行运行 `gh auth setup-git` |

## 决策日志

实现过程中做出的设计决定和假设。

| 日期 | 决策 | 原因 |
|---|---|---|
| 2026-10-08 | 远端 `main` 上已有只含 `README.md` 的 `Initial commit`，与本地历史无共同祖先。用 `git merge --allow-unrelated-histories` 合并，不用 `rebase`，不强制推送 | 合并保留远端的全部历史，本地提交的哈希不变（本文件和台账引用了它们），推送是快进。两边没有同名文件，没有冲突 |
| 2026-10-08 | 接手时发现工作区里的 `docs/progress.md` 和 `.gitignore` 被覆盖成旧版（未提交）。旧版备份到会话的临时目录后，用已提交的版本恢复 | 已提交的版本更新（记录了任务 1 至 3、5 的结果，`.gitignore` 里有 `*.rdp` 和 `Claude outputs/`）；旧版的内容是它的子集，没有信息丢失 |
| 2026-10-08 | 复用 2026-10-03 已完成的任务 1 至 3、任务 5 的 run1 和 run2、只读勘查 L0，不重做 | 逐项复核：质量工具全绿、台账结构完整、E1 脚本和输出齐全，都可用 |

## 问题与解决

遇到的问题、试过的做法、最后的结论。走不通的尝试也记在这里，它们是考核报告"探索过程"一节的素材。

| 日期 | 问题 | 试过什么 | 结论 |
|---|---|---|---|
| 2026-10-03 | 阶段 0A 任务 1：助手执行命令的机器（主机名 WIN-607I4J4LV6S）不是装有 HYSYS 的工作站 | 在这台机器上查：注册表 HKCR 里没有 HYSYS/Aspen 的 ProgID，HKLM 下没有 AspenTech 键，没有 HYSYS 进程。这台机器上的 `mstsc.exe` 已经连着工作站的 3389 端口，所以远程桌面是通的，但助手的工具不经过这条连接，命令仍然在本机执行。本机的 `python` 是 Microsoft Store 占位程序，可用的解释器在 Anaconda（3.12，64 位），这只是本机的情况 | 暂停，等用户决定：在工作站上运行助手（推荐），或者用共享文件夹中转。**已解决**：用户改在工作站（myWin10VM，装有 Aspen HYSYS V15.0）上重开会话，2026-10-03 10:25 恢复，任务 1 重新核对通过 |
| 2026-10-03 | 输出被管道接走的 Python 进程打印中文报 `UnicodeEncodeError`（任务 2） | 去掉 `PYTHONIOENCODING` 和 `PYTHONUTF8` 复现：默认 cp1252。设 `PYTHONUTF8=1` 后正常 | `setx PYTHONUTF8 1`；探针脚本自己 `sys.stdout.reconfigure(encoding="utf-8")`。详见"环境事实" |
| 2026-10-03 | 想靠扫描示例 `.hsc` 的字节找出含反应器的 Case（任务 7 的预案） | 对 212 个文件按 ASCII 和 UTF-16 查 `conreactor`、`eqreactor`、`gibbsreactor` 等字符串，0 个命中 | 走不通：`.hsc` 是压缩格式，只能用 COM 打开并枚举单元操作。见台账 L0 |
| 2026-10-03 | 会话在 E1 之后因用量上限中断 | run1 按 `--exit keep` 留下了 HYSYS 实例；确认它没有打开 Case 后，run2 用 `--exit quit` 退出了它 | 无残留进程。剩余工作见"下一步" |
| 2026-10-08 | 用户的交接说明与仓库现状不符：说"没有 Git 仓库和台账、进度显示尚未开始"，实际已有 4 个提交、台账和 E1 的两次运行 | 核对 `git log`、台账、`spikes/out/`，并对照 `git diff` 发现工作区的 `progress.md`、`.gitignore` 是旧版 | 以已提交的版本为准，复用已完成的任务（见决策日志） |
| 2026-10-08 | 首次推送失败：`fatal: could not read Username for 'https://github.com'` | 先用 `git ls-remote` 确认远端是公开的、只有一个提交；`git credential-manager github list`、`cmdkey /list`、`gh auth status` 都没有凭据；再合并远端提交；用非交互模式推送，得到上面的错误；又在后台发起一次允许交互的推送，等用户在 VM 桌面上授权 | 认证拦截，没有任何内容到达远端。本地提交全部保留。需要用户登录一次（D10） |
| 2026-10-08 | 类型库完整导出 2.0 MB，超过单个文件 1 MB 的提交上限（任务 6） | 先把 533 个接口里重复的基础成员抽成公共组，仍有 1.6 MB；最后改成成员文件只写成员名（629 KB），完整签名只写反应相关的 111 个接口（212 KB）和关键词命中（74 KB） | 见台账 L4。想看某个接口的完整签名，查 `typelib_reaction_api.txt`；不在里面的，重新运行 `typelib_dump.py` 改一下 `RELEVANT_INTERFACE` |
| 2026-10-08 | 看检索结果时漏看了降级通道（任务 6） | 为了缩短显示，按"不以下划线开头"过滤命中行，把 `_SimulationCase`、`_Application` 上的 XML、`PlayScript` 全过滤掉了，一度以为 XML 路线只有 `SetStreamAssayFromXML` | 用不过滤的结果核对后，发现 `GetXMLForCase`、`ApplyXML`、`PlayScript`、`BackDoor` 都在，写进了台账 H24、H26 和"创建反应的线索" |
| 2026-10-08 | 第一次 `SimulationCases.Open` 失败：`com_error -2147352567 ... -2147024891`（E_ACCESSDENIED）（任务 7） | 副本在 `C:\Users\AZUREU~1\AppData\Local\Temp\...`（8.3 短路径），用 `shutil.copy2` 复制；改成 `shutil.copyfile`、`chmod` 可写、`Path.resolve()` 得到长路径后成功 | 同时改了三处，没有分开验证。E2 里单独验证短路径是不是原因；之后给 HYSYS 的路径一律先 `resolve()` |
| 2026-10-08 | 打开 Green Ammonia Process 时 `Open` 卡住（任务 7） | `_common.watch` 45 秒后打印 HYSYS 窗口：模态对话框 "To use Aspen Properties in HYSYS, at least one databank should be installed..."；用 `BM_CLICK` 点 OK 关闭；脚本被外层超时杀掉，实例用 `taskkill` 结束 | 这台机器没有注册 Aspen Properties 数据库，用到它的 Case 都会弹这个窗口。我们的流体包只用 HYSYS 自带物性包。台账 H23 记为部分确认 |
| 2026-10-08 | E2 第一次运行的求解器测试没有说明问题（任务 8） | 挂起求解器后只改了进料温度，而出料温度是规定值，出料本来就不变，分不清"没重算"和"挂起生效" | run2 改成改进料流量（出料流量随进料变）：挂起时出料不变，释放后同步更新。台账 H17 |
| 2026-10-08 | 8.3 短路径是不是 `Open` 失败的原因（任务 7 遗留，任务 8 验证） | 同一个副本、同一种复制方式，分别用"目录短名""目录和文件名都短""长路径"打开 | 短路径两种都 `E_ACCESSDENIED`，长路径成功。给 HYSYS 的路径先 `Path.resolve()`。台账 H2 |
| 2026-10-08 | `case.IsDirty` 在刚打开、没改过的 Case 上也是 True（任务 8） | E2b 三种情况都读到 True | 不能用 `IsDirty` 判断 Case 有没有改过；`Quit()` 和 `Close()` 本来就不弹保存确认，不需要它 |
| 2026-10-08 | E3 第一次运行在第二台反应器上崩溃（任务 9） | `Combustor` 没有连能流，`op.EnergyStream` 抛 `com_error`（E_FAIL），而脚本只捕获了 `AttributeError` | 加 `optional_attr`，把 `com_error` 当作"没有连接"。台账 H16 记了这个行为 |
| 2026-10-08 | `LnKSource` 读出 4，与类型库的枚举对不上（任务 9） | 示例里的平衡反应 Rxn-4 用的是 K–T 表（`ActivateKTable` 为 True），类型库里 `eqrxn_Table=3`、`eqrxn_FixedExtent=4`，读出的却是 4；`Basis` 读出 2 与枚举吻合 | 没有解决。要等用户的参考 Case（Keq 来源为 Gibbs 自由能）读到另一个数字。0B 写 Keq 来源时必须先核对这个映射 |
| 2026-10-08 | 想靠 XML 导出创建或修改反应（任务 9，走不通） | `ProvideXMLForCase(0 或 1)` 6.5 MB，检索 'Stoich'、'rxnset'、'ReactionSet'、'LnK'、'Rxn-4'，全是 0 次 | XML 里没有反应和反应集的定义，只有反应器上引用反应名的部分。这条路线不能创建反应，在"创建反应的线索"里排最后 |

## 与计划的偏差

实现与 `MASTER_PLAN.md` 不一致的地方，以及原因。

| 日期 | 计划中的说法 | 实际做法 | 原因 |
|---|---|---|---|
