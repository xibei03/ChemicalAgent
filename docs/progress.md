# 进度与交接

每完成一个任务就更新这份文件并提交。它是跨会话的唯一记忆：新会话靠它知道做到了哪里，对话被压缩后也靠它找回方向。

## 当前状态

- **阶段 0B：已完成**（2026-10-08 12:30 开始，19:25 结束，UTC+8；与 0A 的会话 3 是同一个会话，中间因用量额度中断约 6 小时，实际工作约 1 小时）。**闸门 G0 通过**：`spikes/e7_conversion_chain.py` 从空白 Case 用代码建出四产物分数系数的甲苯歧化转化反应器，连续两次运行出料摩尔分率与解析解偏差 0.00000、质量守恒误差 1.52e-05、出口温度 378.59 °C、两次运行摩尔流量相对偏差 0。**每一步都是第 1 级集成方式（COM 编程）**，没有降级。**分数计量系数可用**，一个转化反应即可。任务 5：同一基准组分的多个转化反应**默认并行**（12/26/12% 三个反应，出口甲苯 0.5000）；反应集排序（Conversion Rankings）**只能读（XML）不能写**，用代码写排序的路全部走不通（H24、H26、H32），含义从 AspenTech 示例 Case 的排序值反推（排序值最小的先算、相同的并行、后面的对剩下的基准组分算）；依次进行的 0.573 没有用代码验证，Recipe 不设排序。台账 H1 至 H26 里 0B 要求的 14 项都有实测证据，"调用序列 → 转化反应器"小节已写成 Backend 的蓝本。
- **阶段 0C 进行中，开始于 2026-10-08 19:26（UTC+8）。**目标和完成标准见 `docs/prompts/phase-0c.md`：e8 平衡反应器两个工况在容差内；e9 Gibbs（含多股进料、绝热两个小试验）；e10 固体碳的四个通过条件和五个问题；E11 鲁棒性（至少同名对象、进程中断）、E12 保存重开；E13 备选路线对照（界面自动化、文件和脚本，各有证据）；台账定稿（H1 至 H26 没有“未测试”、平衡和 Gibbs 调用序列、十一个组分规范名、路线对照、对工具契约的影响）。
- **下一步：阶段 0C。**用户 2026-10-08 回复"审查 0B 是否完成，若已完成则继续做 0C"，所以 0C 在这个会话里接着做（这个会话已经被压缩过一次，按 `CLAUDE.md` 的规矩本来应当建议开新会话；每个任务做完都更新本文件，万一再被压缩，从"下一步"接着做）。
- 阶段 0A：**已完成**（主体 2026-10-08 10:55 结束，UTC+8；用户答复后补做 D11，12:00 结束）。首次开始于 2026-10-03 09:50，共 3 个会话（见"已完成"的时间表）。任务 1 至 3、5 至 11 都完成，完成标准的 6 条都有实际运行的验证。**任务 4（E0，LLM 连通性）挂起**，等用户给出供应商、模型和密钥所在的环境变量（D1）。**D11（参考 Case）已由助手用代码建成并补跑了 E3，不再等用户。**下一个会话做阶段 0B。当前没有残留的 HYSYS 进程。
- **用户 2026-10-08 的答复（0A 交接之后）：D11 由助手自行创建参考 Case，建好后补跑 E3；D9 之后的提交署名改为 `xibei03 <jsl_03@163.com>`；"完成后续跑"。** 我的理解和假设：自行创建用 COM 代码做（没有别的手段），所以这部分工作等于提前做了 0B/0C 的一部分探针（E4 至 E9），台账里按探针记录；"完成后续跑"理解为做完这些之后补跑 E3，**不进入阶段 0B**（阶段边界不变，0B 仍在新会话里做，可以直接用这里的结论）。如果用户的意思是连续做 0B，请在回复里明说。（用户随后回复“继续 0B”，0B 在同一个会话里做了。）
- 最近通过的闸门：**G0（2026-10-08，阶段 0B）**。0B 结束时质量工具全绿：`ruff format --check`、`ruff check`、`mypy src`、`pytest`（13 passed）；本阶段没有改 `src/` 和 `tests/`；`python tests/test_code_health.py` 输出 `src/` 各模块 0 行（`src/` 还是空的）、没有忽略检查的注释。
- 最近一次更新：2026-10-08 19:30
- 时间记法：本机时钟是 UTC，进度文件里的时间一律换算成 UTC+8（加 8 小时）。
- 推送状态：本阶段每个任务的提交都已推送到 `origin/main`，没有强制推送；推送方式见"环境事实"的"GitHub 凭据"。

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
| 反向探测用的参考 Case 的路径 | **`spikes/ref_cases/three_reactors.hsc`**（D11，助手用代码建的，178 KB，已提交）：PR 流体包 8 个组分，转化反应器 R-Conv、平衡反应器 R-Eq、Gibbs 反应器 R-Gibbs，全部求解；重建命令 `.venv\Scripts\python.exe spikes\build_reference_case.py`。另有自带示例 `C:\Program Files\AspenTech\Aspen HYSYS V15.0\Samples\Synthesis Gas Production.hsc`（2 台转化、3 台平衡反应器；先复制到临时目录再打开） |
| LLM 供应商、模型、密钥所在的环境变量名 | 待用户提供（D1） |
| 远程仓库地址 | `https://github.com/xibei03/ChemicalAgent.git`（2026-10-08 由用户给出，已配置为 `origin`，默认分支 `main`）。远端仓库是公开的，不登录也能 `fetch`，推送需要登录 |
| GitHub 凭据 | 2026-10-08 接手时这台机器上没有任何凭据；用户随后在应用的终端里运行 `gh auth login`，登录为 `xibei03`（令牌在 Windows 凭据库，协议 https）。`git` 的凭据助手仍然是系统级的 `manager`（GCM），没有运行 `gh auth setup-git`，所以推送时用一次性助手，不改任何持久配置：`git -c credential.helper= -c "credential.helper=!gh auth git-credential" push`。助手不代填、不收口令或令牌 |
| Git 署名 | 机器上没有配置全局 `user.name` 和 `user.email`。**2026-10-08 起仓库级配置是 `xibei03 <jsl_03@163.com>`（D9，用户指定）**；此前的提交（到 `07940e6`）署名是 `xibeibei63 <xibeibei63@gmail.com>`，已推送，不改写历史 |

## 已完成

每个阶段开始和结束时各记一行时间，阶段 5 用它整理开发时间线。

| 阶段 | 开始和结束的时间 | 会话数 |
|---|---|---|
| 0A | 2026-10-03 09:50 开始，2026-10-08 12:00 结束（UTC+8）。会话 1：10-03 09:50 至 09:58，在别的机器上停在任务 1；会话 2：10-03 10:25 至 10:50，E1 前两次运行，因用量上限中断；会话 3：10-08 09:50 至 10:55，之后用户答复 D9、D11，11:25 至 12:00 补做参考 Case。实际工作时间约 2 小时 20 分钟 | 3 |
| 0B | 2026-10-08 12:30 开始，19:25 结束（UTC+8）。12:30 至 12:58 做 G0 和任务 5 的前半，因用量额度用尽中断约 6 小时；18:55 起做任务 5 的排序、台账定稿和收尾。实际工作约 1 小时 | 0（接着 0A 的会话 3 做） |

| 阶段 | 任务 | 提交 | 验证方式 |
|---|---|---|---|
| 0A | 1 确认能执行 Windows 程序 | 无代码改动 | `python --version` 得 3.12.4；`platform.architecture()` 得 64bit、WindowsPE；`HKLM\SOFTWARE\AspenTech` 存在，`C:\Program Files\AspenTech\Aspen HYSYS V15.0` 存在 |
| 0A | 2 仓库和工具 | fbfc7bf | `ruff check .` 通过；`ruff format --check .` 3 个文件已格式化；`mypy src` 无问题；`pytest` 13 passed；`PYTHONUTF8` 的实测见"环境事实" |
| 0A | 3 建台账 | 029bbe7 | `docs/HYSYS_INTEGRATION.md` 有 10 个固定节名，接口事实表有 H1 至 H26 共 26 行，状态均为"未测试" |
| 0A | 5 连接 HYSYS（E1），run1 至 run9，已完成 | 2427c43（run1）、4904693（run2）、58c29f4（run3 至 run9、`_common.py`） | run1：`Dispatch("HYSYS.Application")` 冷启动 35.2 秒，`Version` 为 `Aspen HYSYS Version 15 (41.0)`，进程 `AspenHysys.exe`，窗口所属进程与 `tasklist` 一致。run2：已有实例被复用（0.0 秒），`Quit()` 后 3.5 秒内消失。run3、run5：`NewInstance` 每次新开进程，`Quit()` 只结束自己（run5 里 7280 退出，14024 继续运行）。run6：丢掉 COM 引用并 `CoUninitialize()` 后 60 秒内实例仍在。run7：`taskkill /PID /T /F` 1.6 秒内结束。run8、run9：`EnsureDispatch` 返回 `gen_py` 的 `_Application`，属性名区分大小写（`app.Name` 报错，类型库里是 `name`），包装生成后 `Dispatch` 也返回同一个类。H1 升为已确认，新增 H27、H28。每次运行后 `tasklist` 无残留进程 |
| 0A | 6 导出类型库（`typelib_dump.py`） | 6378949 | `.venv\Scripts\python.exe spikes/typelib_dump.py` 成功运行：类型库 1140 个类型（726 个 dispatch 接口、377 个枚举、22 个组件类）；42 个接口有 `Add`，多数是 `Add(name: VARIANT[opt], Type: VARIANT[opt])`；`EnsureModule` 2 至 4 秒生成包装（758 个类），`ReactionSets`、`Reactions`、`Operations`、`FluidPackages`、`SimulationCases` 的包装类都有 `Add`。输出 5 个文件，最大 629 KB，都小于 1 MB。三种反应器是 dispatch 接口 `ConversionReactor`、`EquilibriumReactor`、`GibbsReactor`；XML、`PlayScript`、`BackDoor` 三条降级通道在类型库里都有。结论都只在类型库层面，没有运行验证 |
| 0A | 7 找含反应器的参考 Case | 0b2cdba | `spikes/find_ref_case.py` 打开 6 个候选示例：Synthesis Gas Production 含 2 台转化反应器（`conversionreactorop`）和 3 台平衡反应器（`equilibriumreactorop`）；Ammonia Synthesis 含 3 台 PFR；CSTR - Dynamic Model 含 1 台 CSTR；Toluene_Disproportionation_Example 是分子级炼油反应器；Ethanol Dehydration、Ethanol Plant 没有反应器；Green Ammonia Process 弹出 Aspen Properties 模态对话框，`Open` 卡住，看门狗读出文字，`BM_CLICK` 关闭。**没有一个示例含 Gibbs 反应器**，需要用户手工建参考 Case（D11）。`Open` 返回类型化的 `_SimulationCase`，`Item(i)` 返回具体的反应器类型，不需要 `CastTo` |
| 0A | 8 读写已有 Case（E2、E2b） | 7609ad0 | `spikes/e2_read_write.py` 两次运行（run1、run2）：流体包 `Basis-1`、物性包 `PengRobinson`、7 个组分可读；物流 T、P、流量用 `GetValue(unit)`、`SetValue(value, unit)`，写后读回一致，不认识的单位抛错；写入同步重算（热负荷 6558.8 → 6544.7 kW）；`Solver.CanSolve=False` 时改进料流量，出料不变（475.36），`CanSolve=True` 这一句 0.46 秒同步求出新值（523.26）；没有规定的变量 `IsKnown` 为 False、值为 -32767.0；新物流 `MaterialStreams.Add("probe")` 成功并能写组成、闪蒸完成；8.3 短路径打开 Case 失败，长路径成功。`spikes/e2b_quit_with_case.py`：Case 打开着或改过时，`Quit()`、`Close()` 都不弹窗。H2、H6、H13、H17、H22 升为已确认 |
| 0A | 9 反向探测（E3），示例 Case | b4df369 | `spikes/e3_reverse_probe.py` 对 Synthesis Gas Production 的 5 台反应器（2 转化、3 平衡）、4 个反应、3 个反应集做只读探测：`Item(i)` 直接返回具体类型；反应 `TypeName` 为 `conversionrxn`、`equilibriumrxn`，反应集为 `rxnset`；出口温度规定在气相出料物流上（`State` 1、`CanModify` True），带能流的反应器热负荷是计算值；反应集成员是 `ActiveReactions`/`InactiveReactions`，与流体包的关联是出现在 `fp.ReactionPackage.ReactionSets` 里；转化率是百分数、同一基准组分的多个转化反应并行按进料算（Reformer 40%+30%，进料甲烷 90.72，反应掉 63.50 kgmole/h）；没连能流时 `op.EnergyStream` 抛 `com_error`。XML 导出 6.5 MB 但不含反应定义。**未解决：**`LnKSource` 读出 4 与类型库枚举对不上；Gibbs 反应器没有样本。H16、H26 部分确认，H18、H20 已确认 |
| 0A | 10 检索官方帮助 | 3a6e467 | `hh.exe -decompile` 解开 4 个 `.chm`（共 2882 个文件），只有 `xhysys.chm` 是 Automation 对象参考：`operation_types.htm` 列出 `Operations.Add` 的类型字符串（`ConversionReactorOp`、`EquilibriumReactorOp`、`GibbsReactorOp`），示例 `Flowsheet.Operations.Add "Pump1", "PumpOp"`；没有 `Reactions.Add`、`ReactionSets.Add` 的说明，枚举页没有界面选项名。台账 L9 |
| 0A | 11 台账收尾和完成标准核对 | 3a6e467 | 台账 10 个节名俱全；H1、H2、H6、H13、H17、H18、H22 都是已确认；三种反应器的类型名、反应、反应集、反应器的成员已记录；"创建反应的线索"按可能性排序；探索日志 L0 至 L9，每个探针都有一条。`python spikes/e1_connect.py` 原样运行，打印版本 `Aspen HYSYS Version 15 (41.0)` 和进程号。`python tests/test_code_health.py` 与四个质量工具见交接报告 |
| 0A | 4 LLM 连通性（E0） | 未做 | 挂起：用户说需要密钥的先跳过，等 D1 |
| 0A（D11） | E4 新建 Case 和 Basis（含 E4b 物性包） | 8a7ec7e | `spikes/e4_basis.py`、`e4b_property_package.py`：`SimulationCases.Add("name")` 新建空白 Case，新 Case 一开始就在 Basis 修改状态；`ComponentLists.Add` 加组分列表，`Components.Add(name)`（库名大小写不敏感，分子式不行）；`FluidPackages.Add` 加流体包，`fp.ComponentList = cl`，**`fp.PropertyPackageName = "pengrob"`（物性包内部名；界面名等 10 种写法都 E_INVALIDARG）**；`EndBasisChange()`、`SaveAs`、`Close`、`Open` 重开后 Basis 完好。固体碳 `Carbon` 在库里，`IsSolid` 为 True。H3、H4、H7、H8 已确认，H5、H21、H25 部分确认 |
| 0A（D11） | E6 创建反应和反应集（含 E6b Keq 来源） | f20af38 | `spikes/e6_reaction.py`、`e6b_keq_source.py`：**`Reactions.Add(name, "conversionrxn")` 第一次就成功**，返回类型化的 `ConversionReaction`（`equilibriumrxn`、`kineticrxn` 同理，界面名、整数、省略 `Type` 都 E_FAIL）；`Reactants.Add(组分名)` 加反应物，`StoichiometricCoefficientValue` 写系数（负为反应物），`BaseComponent`、`Conversion = 50.0`；分数系数 0.24 能写；`ReactionSets.Add(name)`、`ActiveReactions.Add(反应名)`、`AssociateFluidPackage(fp)`（挂上之后流体包才列出这个集合）；`EndBasisChange()` 之后也能直接建反应；另存重开后全部保留，系数被质量守恒微调 5e-5。**`LnKSource` 实际取值：1 Ln(K) 公式、2 Gibbs 自由能（默认）、3 固定 K、4 K–T 表，写 0 被忽略**（依据 `equirxn.rdf` 和实测）；固定 K 写 `EquilibriumConstant` 可用。H5、H9 已确认，H10、H11 部分确认 |
| 0A（D11） | 参考 Case 构建（E5 物流、E7 转化、E8 平衡、E9 Gibbs） | 本次提交 | `spikes/build_reference_case.py` 从空白 Case 一次建出并求解三种反应器，连续两次运行结果逐项相同：转化反应器出口摩尔分率甲苯 0.5000、苯 0.2500、对二甲苯 0.2500（偏差 < 1e-5）；平衡反应器 710 °C、600 °C 与独立参照值的摩尔分率最大偏差 0.0046、0.0014（容差 0.02），CH4 转化率 54.0%、30.3%，热负荷 +39989 kW、+20160 kW；Gibbs 反应器与平衡反应器最大偏差 1e-5；质量守恒误差 < 2e-5；流程图 14 个对象全是 OK。`Operations.Add(name, "ConversionReactorOp")` 等帮助文件的写法有效；出口温度规定在气相出料物流上。台账 H12、H14、H15、H16、H20 已确认，H19 部分确认，写出"调用序列"三个小节 |
| 0A（D11） | E9b Gibbs 反应器类型 | 本次提交 | `spikes/e9b_gibbs_type.py`：`ReactorType` 0 = NO Reactions (=Separator)，2 = Specify Equilibrium Reactions（要挂反应集），3 = Gibbs Reactions Only（默认）；1 写得进去但反应器未求解。界面选项原文来自 `Support\OdfRdfVariables.sdb`。台账 H31 |
| 0A（D11） | E3 补跑：参考 Case | 本次提交 | `spikes/e3_reverse_probe.py --case spikes/ref_cases/three_reactors.hsc --tag three`：三种反应器、3 个反应、2 个反应集的读法与示例一致；`LnKSource` 为 2（Gibbs 自由能）；Gibbs 的 `ReactorType` 为 3。0A 遗留的两个未解决项都已解决 |
| 0B | 2 新建物流（E5） | ff85892 | `spikes/e5_stream.py`：新物流所有量未知；T、P、组成写完闪蒸完成，再写质量流量，摩尔流量等随之已知；10000 kg/h 甲苯读回 108.5296 kgmole/h；组成写入被静默归一化，负流量不校验，-300 °C 被拒，同名 `Add` 返回已有物流 |
| 0B | 4 转化反应器全链路（E7，闸门 G0）及 E7b 未求解原因 | ff85892 | `spikes/e7_conversion_chain.py --repeat 2`：从空白 Case 一次建出四产物分数系数的甲苯歧化转化反应器并求解；出料摩尔分率 0.5000 / 0.2500 / 0.0600 / 0.1300 / 0.0600，与解析解偏差 0.00000（容差 0.001）；质量守恒误差 1.52e-05（容差 1e-4）；出口温度 378.59 °C（容差 ±10）；两次运行各组分摩尔流量相对偏差 0（容差 1e-4）；挂起求解器的做法结果相同。**G0 通过，全部用第一级（COM 编程）**。求解随写入同步完成；判断已求解：`IsSolving` 为 False，`GetFlowsheetStatus` 里只有 OK。`spikes/e7b_unsolved_reasons.py`：缺进料、出料、反应集都是反应器 `UnderSpecified`，要读反应器成员区分；反应集没加入流体包写入即报错；类型不匹配的反应集会弹模态对话框，用 `_common.dialog_guard` 处理 |
| 0B | 1、3 新建 Case 和 Basis（E4）、创建反应和反应集（E6） | 8a7ec7e、f20af38 | 0A 的 D11 里已经做完（用户指示助手自行创建参考 Case），0B 没有重做；G0 脚本用同一条链，换成 0B 的四产物版本重新跑通。见上面两条 0A（D11）记录 |
| 0B | 4（补）G0 终版再验证 | 5a45a89 | 给 `e7_conversion_chain.py` 加了"最后一次运行另存 Case"（`spikes/out/e7_conversion_chain_run3.hsc`，154 KB）；`--repeat 2 --tag run3` 两次通过，摩尔流量相对偏差 0。另存的 Case 重新打开：反应 `Tol-Disp`，基准组分甲苯，转化率 50，系数 -2 / 1 / 0.24 / 0.52 / 0.24，出料摩尔分率 0.5 / 0.25 / 0.06 / 0.13 / 0.06，流程图 4 个对象全是 OK，没有弹窗 |
| 0B | 5 并行的转化反应和排序（E6b、E6c） | 4845c3c、05ac2a5 | `spikes/e6b_parallel_reactions.py`：三个基准组分相同的转化反应（12/26/12%）放进同一个反应集，不设排序时出口甲苯 **0.5000**，默认并行；排序在操作 XML 的 `ReactionRanks` 里，默认全是 0；`flags=0` 的 `ApplyXMLForOperation` 返回 False 并弄坏 Case。`spikes/e6c_rank_channels.py`（run1 至 run4）：XML 的 12 种 `flags`、Case 级 `ApplyXML`、BackDoor（用进料温度校准 moniker 写法）、`ActiveReactions.Add` 的第二个参数，都不能写排序；示例 Case 的 Combustor 排序 (1,1,0)、指定转化率 35/65/100、实际 18.09/33.60/48.31%，说明排序值小的先算、相同的并行 |
| 0B | 台账定稿和完成标准核对 | bdf9abe（进度文件在其后一次提交） | 台账：转化反应器调用序列换成 G0 版本（9 步表、结果表、分数系数、并行与排序），H24 改为不可行、H26 补导入结果、新增 H32，清掉 H4、H5、H9 至 H12、H14 至 H16、H18、H20 里"留给 E3/E5/E6/0B"的过时说法，鲁棒性观察补 0B 五条，探索日志补 L20、L21。完成标准七条逐条核对见交接报告 |
| 0A | 只读勘查（计划模式下完成，无脚本） | 2427c43 | 注册表 ProgID、`hysys.tlb` 的接口名与集合的 `Add` 签名、安装目录里的 `hysys.hh`、定义文件、帮助文件，写入台账 L0 和"创建反应的线索"初稿（均未运行验证） |

## 进行中

没有进行中的任务。D11（参考 Case）已完成，见"已完成"。

## 下一步

阶段 0B 已完成。现在做**阶段 0C**（`docs/prompts/phase-0c.md`）：平衡反应器 E8、Gibbs 反应器 E9、固体碳 E10、鲁棒性 E11 和保存重开 E12、备选路线对照 E13、台账定稿（含"对工具契约的影响"）。0C 的起点：

1. **D11 已经提前验证了的**（`spikes/build_reference_case.py`，台账"调用序列"的平衡、Gibbs 两小节）：平衡反应器 710 °C、600 °C 与参照值的最大偏差 0.0046、0.0014，热负荷 +39989 kW、+20160 kW（吸热为正）；Gibbs 反应器（`ReactorType` 3，不挂反应集）与平衡反应器结果相差 1e-5。0C 仍要按提示词用 `e8_equilibrium_chain.py`、`e9_gibbs_gas.py` 重新做成蓝本脚本。
2. **还没验证的**：固定 K 来源下求解（只验证了属性读写）；Ln(K) 公式、K–T 表来源；绝热平衡反应器和绝热 Gibbs 反应器（去掉能流）；把进料拆成多股；**固体碳（E10）**；鲁棒性 E11、保存重开 E12；备选路线 E13；`H21`、`H23`、`H24`（已记不可行）等。
3. **0B 留下的**：排序"依次"没有验证，Recipe 不设排序（H32）；`ReactionPhase` 对转化反应的影响没有试（G0 用的 0 = 气相，默认值是 5）。
4. **E0**：用户给出 LLM 信息（D1）之后做，现在不卡；**D12** 要在阶段 1A 之前定。

## 待决策

需要用户确认的事项。默认值来自 `MASTER_PLAN.md` §25，用户没有另行指示时按默认值执行。

| 编号 | 事项 | 默认 | 状态 |
|---|---|---|---|
| D1 | LLM 供应商和模型；VM 能否直连。任务 4（E0）因此挂起；用户 2026-10-08 说需要密钥的先跳过，必要时再要 | 待用户提供 | 未定，到阶段 2A 之前必须解决 |
| D2 | 场景 3 是否加入氧气 | 不加，按题面建模，在报告中说明 | 按默认 |
| D3 | "80000 Nm³/h"的含义 | 进料的总摩尔流量 | 按默认 |
| D4 | 二甲苯异构体分配 | 对 : 间 : 邻 = 24 : 52 : 24 | 按默认 |
| D5 | 压力是绝压还是表压 | 绝压 | 按默认 |
| D6 | 场景 1 的进料流量基准 | CH4 1000 kmol/h | 按默认 |
| D7 | Demo 形态 | 命令行，HYSYS 窗口可见 | 按默认 |
| D8 | 机动时间先做泛化还是先做加固 | 先泛化 | 按默认 |
| D9 | Git 署名的名字和邮箱 | 之后的提交署名 `xibei03 <jsl_03@163.com>`，历史提交不改 | **已定**（用户 2026-10-08 指定）。此前 13 个提交署名是 `xibeibei63`，不改写历史（会需要强制推送）；若想让展示统一，可以加 `.mailmap`，没加，等用户说 |
| D11 | 三种反应器的参考 Case `spikes/ref_cases/three_reactors.hsc` | 用户 2026-10-08 指示由助手自行创建 | **已解决**：助手用代码建成并求解（`build_reference_case.py`），E3 已补跑；Gibbs 类型选项和出口温度规定的位置已查清（台账 H31、E8 小节），不需要用户手工建。用户若想在界面里看一眼，打开这个文件即可 |
| D12 | 弹窗会让 COM 调用卡死（H23）。已见两种：打开用到 Aspen Properties 的 Case，反应集类型与反应器不匹配。0A、0B 的探针用一个后台线程盯着 HYSYS 进程的对话框并点 OK（`spikes/_common.py` 的 `dialog_guard`）。正式系统同样需要，但 `CLAUDE.md` 架构不变量 7 说系统不用多线程 | 建议：允许在 `backends/hysys_com/` 内部用一个守护线程专门处理弹窗（只调用 Win32，不碰 COM 对象），其余仍然同步；备选是只靠事先校验避免已知的弹窗，遇到未知弹窗只能靠超时后按进程号结束 | 未定，等用户确认（0B 之后、1A 之前） |
| D13 | 反应集排序没有办法用代码写入（H32），所以“依次进行”的 0.573 没有验证 | Recipe 不设排序，保持默认并行；需要依次时建议用两台转化反应器串联或合并反应 | 按默认。可选：用户想确认 0.573 的话，可以打开我另存的三反应 Case，在界面里把 Conversion Rankings 改成 1、2、3，读出口甲苯摩尔分率（需要时告诉我，我把 e6b 的 Case 另存出来） |
| D10 | GitHub 登录：这台机器原本没有存储的凭据 | 用户登录后，助手补推全部提交 | 已解决（用户 `gh auth login` 登录为 `xibei03`，首次推送 2026-10-08 成功）。可选：用户若想让以后的 `git push` 不再需要一次性助手，自行运行 `gh auth setup-git` |

## 决策日志

实现过程中做出的设计决定和假设。

| 日期 | 决策 | 原因 |
|---|---|---|
| 2026-10-08 | 远端 `main` 上已有只含 `README.md` 的 `Initial commit`，与本地历史无共同祖先。用 `git merge --allow-unrelated-histories` 合并，不用 `rebase`，不强制推送 | 合并保留远端的全部历史，本地提交的哈希不变（本文件和台账引用了它们），推送是快进。两边没有同名文件，没有冲突 |
| 2026-10-08 | 接手时发现工作区里的 `docs/progress.md` 和 `.gitignore` 被覆盖成旧版（未提交）。旧版备份到会话的临时目录后，用已提交的版本恢复 | 已提交的版本更新（记录了任务 1 至 3、5 的结果，`.gitignore` 里有 `*.rdp` 和 `Claude outputs/`）；旧版的内容是它的子集，没有信息丢失 |
| 2026-10-08 | 用户指示 D11 自行创建、D9 署名 `xibei03 <jsl_03@163.com>`：参考 Case 用 COM 代码建，建 Case 的过程当作探针 E4 至 E9 记录；署名用 `git config user.name/user.email`（仓库级） | 用户的明确指示。代码创建 = 0B 的目标，所以顺带验证 0B/0C 的创建链；0B 仍按提示词重新做，但起点高得多 |
| 2026-10-08 | 复用 2026-10-03 已完成的任务 1 至 3、任务 5 的 run1 和 run2、只读勘查 L0，不重做 | 逐项复核：质量工具全绿、台账结构完整、E1 脚本和输出齐全，都可用 |
| 2026-10-08 | 0B 任务 1（E4）、任务 3（E6）不重做，G0 脚本直接沿用 D11 的创建链 | D11 里已经用代码跑通并写进台账，重做没有新信息；0B 的增量是四产物分数系数版本、与解析解的对比、两次运行一致性 |
| 2026-10-08 | 反应集排序用不了代码写，Recipe 不设排序，保持默认并行 | 默认（全 0）就是并行，正好是"同一基准组分的主、副反应各按进料算"这种需要的语义；依次进行可以用串联反应器表达。D13 |
| 2026-10-08 | 用户回复"审查 0B 是否完成，若已完成则继续做 0C"：先把 0B 剩下的收尾做完（任务 5 的 E6c、台账、进度），再进入 0C | 0B 的完成标准 4、5、7 当时没有满足（调用序列小节、排序结论、提交），审查结论是"未完成"，所以先补完再继续 |

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
| 2026-10-08 | `LnKSource` 读出 4，与类型库的枚举对不上（任务 9） | 示例里的平衡反应 Rxn-4 用的是 K–T 表（`ActivateKTable` 为 True），类型库里 `eqrxn_Table=3`、`eqrxn_FixedExtent=4`，读出的却是 4；`Basis` 读出 2 与枚举吻合 | **已解决（E6b，D11）**：实际取值 1 = Ln(K) 公式、2 = Gibbs 自由能（默认）、3 = 固定 K、4 = K–T 表；依据是 `Support\equirxn.rdf` 里界面分组的可见范围和新建反应的默认值（2）。类型库枚举名与实际取值对不上，不要用 |
| 2026-10-08 | 想靠 XML 导出创建或修改反应（任务 9，走不通） | `ProvideXMLForCase(0 或 1)` 6.5 MB，检索 'Stoich'、'rxnset'、'ReactionSet'、'LnK'、'Rxn-4'，全是 0 次 | XML 里没有反应和反应集的定义，只有反应器上引用反应名的部分。这条路线不能创建反应，在"创建反应的线索"里排最后 |
| 2026-10-08 | `fp.PropertyPackageName = "Peng-Robinson"` 抛 `E_INVALIDARG`（D11 的 E4） | 试了 10 种写法、先设组分列表再设物性包、`FluidPackages.Add(name, Type)` 传枚举值和字符串，都不行；没设物性包就保存，重开时弹模态对话框卡住 `Open` | 读示例 Case 的 `fp.PropertyPackage`：`TypeName` 是 `pengrob`、`VisibleTypeName` 是 `Peng-Robinson`；设置要用内部名 `pengrob`，成功。台账 H7 |
| 2026-10-08 | 把探针输出接给 `head` 之后，脚本被管道关闭打断，留下一个 HYSYS 实例（D11 的 E4 run1） | 用 `taskkill` 按进程号结束 | 以后运行探针一律把标准输出丢到 `/dev/null`，从 `spikes/out/` 的日志文件读结果（`Log` 本来就边打印边落盘） |
| 2026-10-08 | 写 `LnKSource = 0`（想设 Gibbs 自由能）读回仍是 2，一度以为设不上（D11 的 E6） | 逐个写 0 至 4：1 至 4 都读回原值，0 被忽略；读 `equirxn.rdf` 找界面分组的可见范围，得到真实对应 | 默认值 2 就是 Gibbs 自由能，不需要写。教训：类型库的枚举名不可信，枚举值要用 rdf 或实测核对。台账 H10、L13 |
| 2026-10-08 | 反应集排序（Conversion Rankings）写不进去（0B 任务 5） | 类型库和 `GetIDsOfNames`（14 个候选名字）没有成员；`ActiveReactions.Add(name, 数)` 第二个参数被忽略；`ApplyXMLForOperation` 在 12 种 `flags`/内容组合下，`flags` 没有 128 时返回 False 并把出口组成弄成各 0.2，带 128 时返回 True 但压降、进料温度、排序都不变；Case 级 `ApplyXML` 同样不变；BackDoor 用 `UniqueID`、IMoniker 显示名、复合 IMoniker 十几种写法，连值已知的进料温度都读不出（返回有效的包装，变量为空）。共 6 类做法、`e6c` 四次运行 | 走不通，没有降到第三、四级（需要用户配合）。含义改从 AspenTech 示例 Case 的排序值反推（Combustor 排序 (1,1,0)，实际转化率 18.09/33.60/48.31%）；Recipe 不设排序（H24、H26、H32，D13） |
| 2026-10-08 | 整份操作 XML 写回把 Case 弄坏（e6b 草稿） | 第一次写回带 windows-1252 声明，msxml 报 Invalid xml declaration；去掉声明后返回 False，进料组成变成各 0.2；之后每个写回实验都用新 Case，并在写回前后读进料组成和排序 | 台账 H26、鲁棒性观察：写回返回 True 不代表改了，写回之后必须读回 |
| 2026-10-08 | 用量额度在任务 5 中途用尽，会话被中断约 6 小时 | 中断前把停点写进本文件（做了什么、`e6c` 草稿还没运行、时间盒、"不要降级"），提交并推送 | 恢复后从停点接着做，没有重做；见上面 0B 时间表 |

## 与计划的偏差

实现与 `MASTER_PLAN.md` 不一致的地方，以及原因。

| 日期 | 计划中的说法 | 实际做法 | 原因 |
|---|---|---|---|
| 2026-10-08 | §16.4 E3：在 GUI 里手工建好含三种反应器的参考 Case 再反向探测 | 先用自带示例 Synthesis Gas Production 探测转化和平衡反应器、反应、反应集；Gibbs 部分等用户手工建的 Case（D11） | 示例里没有 Gibbs 反应器，不想让探测等人 |
| 2026-10-08 | §16.2 H3、H9 等把"新建"归给 E4 至 E6 | E2 里顺带验证了新建物流（`MaterialStreams.Add`）和写组成，H12、H14 已部分确认 | 为了读"没有规定的变量"必须新建一股物流，结果可以直接用 |
| 2026-10-08 | 0B 提示词任务 5：把排序设成依次，用 0.573 判断排序的含义 | 没有做到：排序不能用代码写入；并行的 0.5000 已验证，含义改从示例 Case 的排序值反推 | 见"问题与解决"；提示词允许任务 5 受阻时推后，这里是走不通而不是推后 |
| 2026-10-08 | 0B 提示词任务 1（E4）、任务 3（E6）单独成脚本做 | 在 0A 的 D11 里已经完成，0B 没有重做 | 用户指示 D11 由助手自行创建参考 Case，创建链提前跑通 |
| 2026-10-08 | 0B 提示词"不要降到第三、四级" | 没有降级；第二级（XML、BackDoor）试了，没有走通 | 排序不是 G0 的组成部分，G0 全部是第 1 级 |
