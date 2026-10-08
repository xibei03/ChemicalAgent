# 进度与交接

每完成一个任务就更新这份文件并提交。它是跨会话的唯一记忆：新会话靠它知道做到了哪里，对话被压缩后也靠它找回方向。

## 当前状态

- **阶段 0B：已完成**（2026-10-08 12:30 开始，19:25 结束，UTC+8；与 0A 的会话 3 是同一个会话，中间因用量额度中断约 6 小时，实际工作约 1 小时）。**闸门 G0 通过**：`spikes/e7_conversion_chain.py` 从空白 Case 用代码建出四产物分数系数的甲苯歧化转化反应器，连续两次运行出料摩尔分率与解析解偏差 0.00000、质量守恒误差 1.52e-05、出口温度 378.59 °C、两次运行摩尔流量相对偏差 0。**每一步都是第 1 级集成方式（COM 编程）**，没有降级。**分数计量系数可用**，一个转化反应即可。任务 5：同一基准组分的多个转化反应**默认并行**（12/26/12% 三个反应，出口甲苯 0.5000）；反应集排序（Conversion Rankings）COM 成员、XML 写回、BackDoor 都写不了，**0C 发现 `PlayScript` 可以写**（排序 (0,1,2) 出口甲苯 0.5731、(1,1,0) 为 0.5456，与预测一致，H24、H32）；含义：排序值最小的先算、相同的并行、后面的对剩下的基准组分算；按 D13 Recipe 不设排序。台账 H1 至 H26 里 0B 要求的 14 项都有实测证据，"调用序列 → 转化反应器"小节已写成 Backend 的蓝本。
- **阶段 0C：已完成，除了 E0 的最后一步**（2026-10-08 19:26 开始，20:42 结束，UTC+8；与 0A、0B 是同一个会话）。完成标准六条：①`e8` 两个工况在容差内（710 °C 偏差 0.0046、600 °C 偏差 0.0014），`e9` 通过（Gibbs 与平衡反应器偏差 1e-5，多股进料、绝热两个小试验通过），**`e10` 不满足通过条件**：Gibbs 反应器 + 库里的固体碳算出的结果是错的（碳的 Gibbs 函数是气态碳原子的，E10b、E10c），证据已交给用户决定（D14）；两段式（计划 §17.3）的可行性我试了，四条通过条件全满足（E10d），没有采用；②固体碳五个问题的答案在台账 Gibbs 反应器小节；③H1 至 H26 没有“未测试”；④路线对照表有四条路线的对照，每条有证据，LLM 视觉操作如实写未试验（没有桌面屏幕工具）；⑤台账有三种反应器的调用序列、十一个组分规范名、鲁棒性观察和“对工具契约的影响”（R1 至 R12，登记为 D15）；⑥本文件已更新并提交。**另外：`PlayScript` 是个能用的第二级通道**，能写 COM 写不了的内部变量（反应集排序已验证）和建对象；用户答复 D12 批准后台线程、D13 保持默认排序。
- **阶段 1A：进行中**（2026-10-08 21:10 开始，UTC+8；新会话）。开始时用户答复了 0C 留下的两个决定：**D14 采用方案 A（两段式：转化反应器按限量反应物算 C + H2O → CO + H2，再用 Gibbs 反应器算气相平衡，未反应的碳从第一台的液相出料旁路）；D15 全部按建议确认（R1 至 R12）**。所以 1A 提示词里"还有待确认的条目先问用户"的条件已满足，可以直接做。
- **D1 的 LLM 配置已记下，但连通性测试没做完**：用户说密钥已经配置在环境变量 `DASHSCOPE_API_KEY` 里，但助手的进程（以及通过终端工具新开的标签）读不到它，用户级和机器级环境变量也没有，应该只设在用户自己终端的会话里。`spikes/e0_llm_connectivity.py` 已写好、没有密钥时安全退出，**需要用户在设了变量的那个终端里运行**：`.\.venv\Scripts\python.exe spikes\e0_llm_connectivity.py --tag run1 --capabilities`，再告诉助手去读 `spikes/out/e0_llm_connectivity_run1.txt`（脚本不打印密钥）。网络已验证：用假密钥访问百炼的国内站和国际站都返回 HTTP 401（台账 L30），说明这台机器能直连。通过以前 D1 不标完成。
- **下一步：阶段 1A**（`docs/prompts/phase-1a.md`）。开始前需要用户：①D14（固体碳：两段式 A、改假想组分 B 还是别的）；②D15（工具契约建议 R1 至 R12，1A 提示词要求“待确认”的条目先问用户）；③D1 的连通性测试（2A 之前必须通过，不挡 1A）。
- 阶段 0A：**已完成**（主体 2026-10-08 10:55 结束，UTC+8；用户答复后补做 D11，12:00 结束）。首次开始于 2026-10-03 09:50，共 3 个会话（见"已完成"的时间表）。任务 1 至 3、5 至 11 都完成，完成标准的 6 条都有实际运行的验证。**任务 4（E0，LLM 连通性）挂起**，等用户给出供应商、模型和密钥所在的环境变量（D1）（2026-10-08 用户已给出，探针 `spikes/e0_llm_connectivity.py` 待用户运行，见 0C 的说明）。**D11（参考 Case）已由助手用代码建成并补跑了 E3，不再等用户。**当前没有残留的 HYSYS 进程。
- **用户 2026-10-08 的答复（0A 交接之后）：D11 由助手自行创建参考 Case，建好后补跑 E3；D9 之后的提交署名改为 `xibei03 <jsl_03@163.com>`；"完成后续跑"。** 我的理解和假设：自行创建用 COM 代码做（没有别的手段），所以这部分工作等于提前做了 0B/0C 的一部分探针（E4 至 E9），台账里按探针记录；"完成后续跑"理解为做完这些之后补跑 E3，**不进入阶段 0B**（阶段边界不变，0B 仍在新会话里做，可以直接用这里的结论）。如果用户的意思是连续做 0B，请在回复里明说。（用户随后回复“继续 0B”，0B 在同一个会话里做了。）
- 最近通过的闸门：**G0（2026-10-08，阶段 0B）**；0C 没有闸门。0B、0C 结束时质量工具全绿：`ruff format --check`、`ruff check`、`mypy src`、`pytest`（13 passed）；本阶段没有改 `src/` 和 `tests/`；`python tests/test_code_health.py` 输出 `src/` 各模块 0 行（`src/` 还是空的）、没有忽略检查的注释。
- 最近一次更新：2026-10-08 20:42
- 时间记法：本机时钟是 UTC，进度文件里的时间一律换算成 UTC+8（加 8 小时）。
- 推送状态：本阶段每个任务的提交都已推送到 `origin/main`，没有强制推送；推送方式见"环境事实"的"GitHub 凭据"。

阶段顺序：0A → 0B → 0C → 1A → 1B → 1C → 2A → 2B → 2C → 3A → 3B（可选）→ 4（可选）→ 5。一个会话只做一个阶段。

## 环境事实

由阶段 0A 填写，之后发现变化时更新。

| 项 | 值 |
|---|---|
| 助手执行命令的机器 | 工作站 `myWin10VM`（Windows 10 Pro 19045，用户 `mywin10vm\azureuser`），时钟为 UTC |
| Python 版本与解释器路径 | 3.12.4，64 位，`C:\Program Files\Python312\python.exe`（`py.exe` 在 `C:\Windows\py.exe`）。PowerShell 里 `python` 直接可用 |
| 虚拟环境 | `C:\Users\azureuser\Desktop\ChemicalAgent\.venv`，解释器 `.venv\Scripts\python.exe`，已 `pip install -e ".[dev]"`（pywin32 312、ruff 0.16.10、mypy 2.4.0、pytest 9.1.1、pydantic 2.13.5）。运行脚本一律写 `.\.venv\Scripts\python.exe`，不依赖激活。**E13a 另装了 pywinauto 0.6.9（连带 comtypes 1.4.17、six 1.17.0），只在虚拟环境里，没有写进 `pyproject.toml`**，只有 `spikes/e13a_ui_automation.py` 用 |
| 输出编码的设置（如 `PYTHONUTF8`） | 实测：没有 `PYTHONUTF8` 和 `PYTHONIOENCODING` 时，输出被管道接走的 Python 进程用 cp1252，打印中文抛 `UnicodeEncodeError`；设 `PYTHONUTF8=1` 后正常。做法：`setx PYTHONUTF8 1`（用户级，对之后新启动的进程生效）。助手的会话进程由宿主预设了 `PYTHONIOENCODING=utf-8:surrogateescape`，所以不依赖 `setx`。探针脚本开头自己 `sys.stdout.reconfigure(encoding="utf-8")`，输出文件由脚本用 `encoding="utf-8"` 写 |
| HYSYS 版本与 ProgID | `Aspen HYSYS Version 15 (41.0)`（`app.Version` 实测）。通用 ProgID `HYSYS.Application`（= `.Latest`，CurVer 为 `HYSYS.Application.V15.0`），已有实例就复用；每次新开进程的是 `HYSYS.Application.NewInstance`（run3、run5 已验证）。进程名 `AspenHysys.exe`。早绑定用 `gencache.EnsureDispatch`，包装缓存在 `%TEMP%\gen_py\3.12`。详见台账"连接与绑定方式" |
| HYSYS 安装目录 | `C:\Program Files\AspenTech\Aspen HYSYS V15.0` |
| 反向探测用的参考 Case 的路径 | **`spikes/ref_cases/three_reactors.hsc`**（D11，助手用代码建的，178 KB，已提交）：PR 流体包 8 个组分，转化反应器 R-Conv、平衡反应器 R-Eq、Gibbs 反应器 R-Gibbs，全部求解；重建命令 `.venv\Scripts\python.exe spikes\build_reference_case.py`。另有自带示例 `C:\Program Files\AspenTech\Aspen HYSYS V15.0\Samples\Synthesis Gas Production.hsc`（2 台转化、3 台平衡反应器；先复制到临时目录再打开） |
| LLM 供应商、模型、密钥所在的环境变量名 | 用户 2026-10-08 答复（D1）：阿里云百炼 Qwen（OpenAI 兼容接口），主模型 `qwen3.8-max`、快速模型 `qwen3.8-flash`、备用模型 `qwen3.7-plus`，密钥环境变量 `DASHSCOPE_API_KEY`（用户在自己的终端会话里配置，助手的进程读不到）；连通性测试 `spikes/e0_llm_connectivity.py` 待用户运行 |
| 远程仓库地址 | `https://github.com/xibei03/ChemicalAgent.git`（2026-10-08 由用户给出，已配置为 `origin`，默认分支 `main`）。远端仓库是公开的，不登录也能 `fetch`，推送需要登录 |
| GitHub 凭据 | 2026-10-08 接手时这台机器上没有任何凭据；用户随后在应用的终端里运行 `gh auth login`，登录为 `xibei03`（令牌在 Windows 凭据库，协议 https）。`git` 的凭据助手仍然是系统级的 `manager`（GCM），没有运行 `gh auth setup-git`，所以推送时用一次性助手，不改任何持久配置：`git -c credential.helper= -c "credential.helper=!gh auth git-credential" push`。助手不代填、不收口令或令牌 |
| Git 署名 | 机器上没有配置全局 `user.name` 和 `user.email`。**2026-10-08 起仓库级配置是 `xibei03 <jsl_03@163.com>`（D9，用户指定）**；此前的提交（到 `07940e6`）署名是 `xibeibei63 <xibeibei63@gmail.com>`，已推送，不改写历史 |

## 已完成

每个阶段开始和结束时各记一行时间，阶段 5 用它整理开发时间线。

| 阶段 | 开始和结束的时间 | 会话数 |
|---|---|---|
| 0A | 2026-10-03 09:50 开始，2026-10-08 12:00 结束（UTC+8）。会话 1：10-03 09:50 至 09:58，在别的机器上停在任务 1；会话 2：10-03 10:25 至 10:50，E1 前两次运行，因用量上限中断；会话 3：10-08 09:50 至 10:55，之后用户答复 D9、D11，11:25 至 12:00 补做参考 Case。实际工作时间约 2 小时 20 分钟 | 3 |
| 0B | 2026-10-08 12:30 开始，19:25 结束（UTC+8）。12:30 至 12:58 做 G0 和任务 5 的前半，因用量额度用尽中断约 6 小时；18:55 起做任务 5 的排序、台账定稿和收尾。实际工作约 1 小时 | 0（接着 0A 的会话 3 做） |
| 0C | 2026-10-08 19:26 开始，20:42 结束（UTC+8）；与 0A、0B 同一个会话。实际工作约 76 分钟（含等待探针运行） | 0（接着 0A 的会话 3 做） |
| 1A | 2026-10-08 21:10 开始（UTC+8）；新会话 | 1 |

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
| 0C | 1 平衡反应和平衡反应器（E8） | 35fa647 | `spikes/e8_equilibrium_chain.py`（建模步骤抽到 `spikes/chain_kit.py`）：710 °C、600 °C 与参照值最大偏差 0.0046、0.0014（容差 0.02），CH4 转化率 54.0%、30.3%，热负荷 +39989、+20160 kW（吸热为正）；Keq 来源默认就是 Gibbs 自由能；改出口温度同步重算；绝热（出口 422.63 °C）、规定热负荷（39989.2 kW 回到 710.00 °C）、固定 K（摩尔分率基准）都能求解 |
| 0C | 2 Gibbs 反应器，纯气相（E9） | ce6d389 | `spikes/e9_gibbs_gas.py`：不挂反应集、`ReactorType` 默认 3，710 °C 与参照值最大偏差 0.0046、与同 Case 的平衡反应器 0.00001；多股进料（每股 `Feeds.Add`）与单股进料相同；绝热 422.63 °C，与绝热平衡反应器差 0.01 °C。run1 因物流重名崩溃，run2 通过 |
| 0C | 3 固体碳（E10、E10b、E10c、E10d） | 2941945、cf8f9ba、594b948 | `spikes/e10_gibbs_carbon.py`：Gibbs 反应器 + 库里的碳**结果错**（与温度无关，全部氧变 CO、全部氢变 CH4、氢气为 0），四条通过条件第 2、4 条不满足；`e10b` 找到根因（碳的 `EvaluateGibbs(298.15 K)` 是 +671.3 kJ/mol，气态碳原子）；`e10c` 库组分数据写不了（`E_ACCESSDENIED`）；`e10d` 两段式四条通过条件全满足，没有采用。D14 |
| 0C | 4 鲁棒性（E11）和保存重开（E12） | bb742b6、928c4e7 | `spikes/e11_robustness.py`：同名创建、进程中断（错误号 -2147023174 / -2147023170）、弹窗、窗口隐藏的实测，台账 L26；`spikes/e12_save_reopen.py`：保存重开结果和求解状态完全保留，台账 L27 |
| 0C | 5 备选路线对照（E13） | ec67534 | `spikes/e13a_ui_automation.py`（pywinauto，双击 Model Palette 的 ConversionReactor 建出 CRV-100，2/2）、`spikes/e13b_file_script.py`（Case 级 `ApplyXML` 建对象但不带连接；`PlayScript` 建反应器、写反应集排序，排序 0.5731/0.5456 与预测一致）；视觉操作未试验；台账“路线对照”一节 |
| 0C | 6 台账定稿 | 59f7275 | 路线对照表、对工具契约的影响（R1 至 R12）、鲁棒性观察、L26 至 L29、H4/H16/H21/H23/H24/H26/H32 更新、调用序列三个小节补实测 |
| 1A | 第一段：契约（任务 1 至 5） | 36e9068、22c7d7b、a1ac4f6、d35d07f、25d5c43 | `ruff format --check`、`ruff check`、`mypy src`（14 个源文件无问题）、`pytest` 146 passed（全是不需要 HYSYS 的单元测试）；`python tests/test_code_health.py`：`src/` 721 行（spec 541、tools 77、errors 60、backends 43），最长函数 17 行，最深嵌套 2 层，没有忽略检查的注释。错误码 27 个与计划 §13.2 逐码对照；可重试集合 9 个；12 个入参模型拒绝非法值；`ToolExecutor` 三种错误和回调事件有测试；“配置是否一致”的 5 个纯函数有测试 |
| 0A | 4（补）LLM 连通性（E0） | 未完成 | `spikes/e0_llm_connectivity.py` 已写好并提交，没有密钥时安全退出；**等用户在设了 `DASHSCOPE_API_KEY` 的终端里运行**（见“当前状态”） |
| 0A | 只读勘查（计划模式下完成，无脚本） | 2427c43 | 注册表 ProgID、`hysys.tlb` 的接口名与集合的 `Add` 签名、安装目录里的 `hysys.hh`、定义文件、帮助文件，写入台账 L0 和"创建反应的线索"初稿（均未运行验证） |

## 进行中

**阶段 1A：Backend 和 Tool 层**（提示词 `docs/prompts/phase-1a.md`，时间盒约 3 小时，21:10 开始）。分两段：第一段定契约（不需要 HYSYS），第二段在真实 HYSYS 上实现并做集成测试。

### 第一段（契约）设计草图（**已完成**，21:10 至 约 22:00；实际与草图的差别：多了 `spec/base.py`（冻结模型的基类，8 行），`SimBackend` 的方法名是 `connect`、`ensure_case` 等）

| 文件 | 内容与公开接口 | 估计行数 |
|---|---|---|
| `errors.py` | `ErrorCode`（计划 §13.2 的 27 个码）；`RETRYABLE_ERROR_CODES`（唯一来源：策略链以 R0 开头的码，即 `E_TIMEOUT`、`E_NOT_FOUND`、`E_READBACK_MISMATCH`、`E_ATTACH_FAILED`、`E_CONNECT_FAILED`、`E_IO`、`E_CASE_OPEN`、`E_NOT_CONVERGED`、`E_VALIDATION_FATAL`）；`ReactorAgentError(code, message, details)` | 90 |
| `spec/enums.py` | 全部 `StrEnum`：`ToolName`（12 个）、`ReactorType`（五种）、`PropertyPackage`、`ReactionKind`、`ReactionPhase`（气相、合并相）、`KeqSource`（Gibbs 自由能、固定 K）、`HeatMode`（规定出口温度、绝热、规定热负荷）、`SpecVariable`（出口温度、热负荷）、`StreamKind`、`ConnectMode`、`CaseMode`、`ObjectState` | 100 |
| `spec/tool_args.py` | 值模型 `StoichiometricTerm`、`ConversionReaction`、`EquilibriumReaction`（可区分联合 `ReactionDefinition`）、`CompositionEntry`、`FeedConditions`；12 个入参模型：`ConnectArgs`、`EnsureCaseArgs`、`SaveCaseArgs`、`CloseCaseArgs`、`EnsureThermoArgs`、`EnsureReactionArgs`、`EnsureReactionSetArgs`、`EnsureStreamArgs`、`EnsureReactorArgs`、`SetSpecArgs`、`SolveArgs`、`ReadSnapshotArgs`。全部冻结、`extra="forbid"`、序列用 `tuple`，物理量带单位后缀 | 280 |
| `spec/tool_results.py` | `ResultStatus`、`Outcome[DataT]`（Backend 的返回：状态 + 数据）、12 个结果数据模型、`ToolError`（`retryable` 由码算出）、`ToolResult`（信封，`ok` / `status` / `data` / `error`）、`ToolCallEvent` | 200 |
| `spec/snapshot.py` | `ModelSnapshot` 及其组成：`ThermoSnapshot`、`ReactionSnapshot`、`ReactionSetSnapshot`、`StreamSnapshot`（含 `StreamComponent`）、`EnergyStreamSnapshot`、`ReactorSnapshot`、`SolveStatus`；读不到的值是 `None` | 130 |
| `spec/matching.py` | 纯函数：`reaction_differences`、`stream_differences`、`reactor_differences`、`reaction_set_differences`、`thermo_differences`，返回人能读的差异描述元组（空表示一致）；容差写成具名常量 | 130 |
| `backends/base.py` | `SimBackend` Protocol，12 个方法，各对应一个工具 | 50 |
| `tools/definitions.py` | `bind(model, handler)`；`register_tools(backend)` 把 12 个工具登记成 `ToolName → ToolRunner` | 80 |
| `tools/registry.py` | `ToolExecutor.call(name, args) -> ToolResult`：未知工具 `E_TOOL_NOT_ALLOWED`、入参类型不对 `E_SCHEMA`、Backend 抛 `ReactorAgentError` 转失败信封、计时并交给可选回调 | 70 |
| `tests/unit/` | `test_errors.py`、`test_tool_args.py`、`test_matching.py`、`test_tool_executor.py`（几十行的桩 Backend 在测试文件里） | 约 400 |

### 第二段（HYSYS 实现）设计草图（`backends/hysys_com/`）

| 文件 | 职责 | 估计行数 |
|---|---|---|
| `com_errors.py` | **`com_error` 这个名字只出现在这里。**`com_call(code, action)` 上下文管理器（也可当装饰器）把 COM 异常转成领域错误，RPC 断开的两个错误号（-2147023174、-2147023170）一律映射 `E_COM_DISCONNECTED`；`read_optional` 读可能没连接的引用（HYSYS 对没连的引用抛错）返回 `None` | 50 |
| `variables.py` | **单位字符串和空值哨兵只出现在这里。**`Quantity` 枚举（单位 + 到规范单位的系数）、`read_quantity`、`read_quantities`、`write_quantity`、`read_plain`（`…Value` 双精度成员的哨兵处理）、`read_fractions` | 80 |
| `dialogs.py` | 弹窗看门狗（D12 批准的守护线程，只调 Win32，不碰 COM）：每 0.5 秒枚举 HYSYS 进程的 `#32770`（含不可见的），读文字，点“确定”，记录；同一个对话框 5 秒内只点一次 | 90 |
| `session.py` | `Session`（应用对象、进程号、是否复用）；`connect`（NewInstance 或接管；`tasklist` 差集取进程号；版本检查）；`shutdown`（`Quit`，超时后 `taskkill`，复用的实例不动） | 110 |
| `cases.py` | 路径入口校验（目录存在、文件名合法、`resolve` 成长路径）；`ensure_case`（新建后立刻 `SaveAs`，按 `FullName` 找已打开的 Case）、`save_case`（读回文件存在且非空）、`close_case` | 120 |
| `thermo.py` | `ensure_thermo`（组分列表、流体包、内部名 `pengrob`、末尾 `EndBasisChange`）、`read_thermo` | 90 |
| `reactions.py` | `ensure_reaction`、`ensure_reaction_set`、`read_reaction`、`read_reaction_set`；类型字符串映射表 | 200 |
| `streams.py` | `ensure_stream`（物流和能流）、`read_stream`、`read_energy_stream` | 130 |
| `reactor_kinds.py` | **三种反应器的差别全在这张表里**：操作类型字符串、读回的 `TypeName`、可挂的反应类型（Gibbs 不挂反应集）、已验证的热模式 | 50 |
| `reactors.py` | `ensure_reactor`（先查名字、连接顺序固定、读回比对）、`read_reactor`、`set_spec` | 190 |
| `solving.py` | `solve`（确保求解器放开、轮询 `IsSolving` 到超时、读流程图状态并映射 `E_NOT_SOLVED` / `E_NOT_CONVERGED`） | 80 |
| `snapshot.py` | `read_snapshot`：把各读取函数的结果拼成 `ModelSnapshot` | 50 |
| `backend.py` | `HysysComBackend`：持有会话、当前 Case、弹窗看门狗；构造时不连接；十二个方法各调一个模块函数 | 150 |

### 已做出的设计决定（假设，用户未另行指示时按此执行）

1. **`ReactorType` 等枚举放在 `spec/enums.py`**，而不是 `tool_args.py`：入参模型加枚举超过 300 行的上限，拆开后各自单一职责。`ReactorType` 仍只定义一次。
2. **转化率用 `conversion_percent`（0 < x ≤ 100）**，与 HYSYS 和计划 §9.4 规则 5 一致，Backend 不做换算。
3. **`session.connect` 有 `mode`（`launch` / `attach`）**：R1 说 attach 只用于调试，但提示词要求结果里放“是否复用”，所以两种都实现；默认 `launch`（NewInstance）。
4. **`ensure_reactor` 的 `heat_mode` 是自洽性声明**：绝热 ⇔ 没有能流；其余两种必须有能流。具体的出口温度或热负荷只通过 `set_spec` 设置；Backend 对未验证的组合（Gibbs 和转化反应器的规定热负荷）抛 `E_UNSUPPORTED`。
5. **`set_spec` 的变量白名单：** `outlet_temperature_c`（写在反应器气相出料物流上）和 `duty_kw`（写在反应器的能流上）；对象一律是反应器名。变量当前是计算值（`CanModify` 为假）时拒绝，避免过规定。
6. **错误细节的类型是 `Mapping[str, str]`**（键是对象名或字段名，值是状态文本，例如 `{"CRV-100": "UnderSpecified"}`）。它是有语义的映射，不是靠位置区分含义的元组，也不是任意值的裸 `dict`。
7. **结果信封里不放耗时**：耗时在 `ToolCallEvent` 里（提示词：事件带耗时；`readback` 字段按提示词不要）。
8. **台账里没有验证的一个顺序要先探：** 结束 Basis 之后建反应集并 `AssociateFluidPackage`（0A 至 0C 的探针都是在 `EndBasisChange` 之前建反应集）。R3 要求 `ensure_thermo` 末尾结束 Basis，所以先写探针 `spikes/e14_basis_order.py` 验证，记入台账，才在 `src/` 里用。

## 下一步

阶段 0C 已完成（E0 的最后一步除外）。下一个会话做**阶段 1A**（`docs/prompts/phase-1a.md`）：Backend 和 Tool 层。开始前：

1. **用户要答复的**：D14（固体碳）、D15（工具契约建议 R1 至 R12；1A 提示词要求“待确认”条目先问用户）。D1 的连通性测试要在 2A 之前通过，不挡 1A。
2. **1A 可以直接用的**：台账“调用序列”三个小节、“对工具契约的影响”（R1 至 R12）、“鲁棒性观察”、`spikes/chain_kit.py` 和 `e7`、`e8`、`e10d` 的步骤函数。弹窗看门狗（D12 已批准）的参考实现是 `spikes/_common.py` 的 `dialog_guard`（含不可见对话框）。
3. **D14 的结果会改 `gibbs` Recipe**：如果用户选两段式，场景 3 的模型是“转化反应器 + Gibbs 反应器”，参考 `spikes/e10d_two_stage.py`。
4. **D13** 保持默认排序；需要依次进行时用 `PlayScript`（H24、H32）。

## 待决策

需要用户确认的事项。默认值来自 `MASTER_PLAN.md` §25，用户没有另行指示时按默认值执行。

| 编号 | 事项 | 默认 | 状态 |
|---|---|---|---|
| D1 | LLM 供应商和模型；VM 能否直连。任务 4（E0）因此挂起 | **用户 2026-10-08 已答复**：阿里云百炼 Qwen，主 `qwen3.8-max`、快速 `qwen3.8-flash`、备用 `qwen3.7-plus`，密钥 `DASHSCOPE_API_KEY`；要求不硬编码、统一封装 Provider/Client（模型名可配置）、为 Agent/工具调用/结构化输出预留接口（阶段 2A）、不增加别的模型和复杂路由 | **等连通性测试**：`spikes/e0_llm_connectivity.py` 已写好，助手的进程读不到变量，要用户在设了变量的终端里运行（命令见“当前状态”）；通过后才把 D1 标为完成，2A 之前必须通过 |
| D2 | 场景 3 是否加入氧气 | 不加，按题面建模，在报告中说明 | 按默认 |
| D3 | "80000 Nm³/h"的含义 | 进料的总摩尔流量 | 按默认 |
| D4 | 二甲苯异构体分配 | 对 : 间 : 邻 = 24 : 52 : 24 | 按默认 |
| D5 | 压力是绝压还是表压 | 绝压 | 按默认 |
| D6 | 场景 1 的进料流量基准 | CH4 1000 kmol/h | 按默认 |
| D7 | Demo 形态 | 命令行，HYSYS 窗口可见 | 按默认 |
| D8 | 机动时间先做泛化还是先做加固 | 先泛化 | 按默认 |
| D9 | Git 署名的名字和邮箱 | 之后的提交署名 `xibei03 <jsl_03@163.com>`，历史提交不改 | **已定**（用户 2026-10-08 指定）。此前 13 个提交署名是 `xibeibei63`，不改写历史（会需要强制推送）；若想让展示统一，可以加 `.mailmap`，没加，等用户说 |
| D11 | 三种反应器的参考 Case `spikes/ref_cases/three_reactors.hsc` | 用户 2026-10-08 指示由助手自行创建 | **已解决**：助手用代码建成并求解（`build_reference_case.py`），E3 已补跑；Gibbs 类型选项和出口温度规定的位置已查清（台账 H31、E8 小节），不需要用户手工建。用户若想在界面里看一眼，打开这个文件即可 |
| D12 | 弹窗会让 COM 调用卡死（H23）。已见两种：打开用到 Aspen Properties 的 Case，反应集类型与反应器不匹配。0A、0B 的探针用一个后台线程盯着 HYSYS 进程的对话框并点 OK（`spikes/_common.py` 的 `dialog_guard`）。正式系统同样需要，但 `CLAUDE.md` 架构不变量 7 说系统不用多线程 | 建议：允许在 `backends/hysys_com/` 内部用一个守护线程专门处理弹窗（只调用 Win32，不碰 COM 对象），其余仍然同步；备选是只靠事先校验避免已知的弹窗，遇到未知弹窗只能靠超时后按进程号结束 | **已定（用户 2026-10-08：“D12 批准使用后台线程”）**：按建议，在 `backends/hysys_com/` 内部用一个守护线程处理弹窗，只调用 Win32，不碰 COM 对象；其余仍然同步。`CLAUDE.md` 架构不变量 7 写的是“不用多线程”，这是用户批准的例外；1A 实现时引用本条，需要的话再改 `CLAUDE.md` |
| D13 | 反应集排序没有办法用代码写入（H32），所以“依次进行”的 0.573 没有验证 | Recipe 不设排序，保持默认并行；需要依次时建议用两台转化反应器串联或合并反应 | **已定（用户 2026-10-08：“D13 保持排序”）**。我的理解：保持默认的排序（不设排序、并行），不再验证 0.573，也不继续找写排序的办法；如果用户的意思不同，请指出 |
| D14 | **固体碳在 Gibbs 反应器里算不对**（场景 3，E10，台账 L24、L25）。进料含固体碳时 Gibbs 反应器的结果与温度无关：全部氧变成 CO、全部氢变成 CH4、氢气为 0（CO 1035、CH4 517.5、碳 981.5 kgmole/h；参照 CO 1017、H2 981、CH4 22、碳 1491）；四条通过条件里第 2、4 条不满足，碳元素守恒和 CO 收率恰好通过，是看起来合理但错的结果。原因：库里 `Carbon` 的 Gibbs 生成能函数是气态碳原子的（+671.3 kJ/mol），生成焓却是石墨的 0，没有升华蒸气压和临界性质，Gibbs 反应器把碳当成特别不稳定的物质。含碳进料本身能正常闪蒸（当作重液相），未反应的碳从液相出料离开。 | **建议 A**（计划 §17.3 的两段式）：先用转化反应器按限量反应物算 C + H2O → CO + H2（水为基准组分，转化率 100%），再用 Gibbs 反应器算气相平衡，未反应的碳从第一台反应器的液相出料旁路；主模型仍是 Gibbs 反应器，报告里如实说明。B：改库里碳的热力学数据——E10c 试了，库组分的 `GibbsCoeffs` 写入被拒绝（`E_ACCESSDENIED`），只能新建假想组分，没有试，没有把握。C：用假想固体组分（没有试）。**我试了 A 的可行性（E10d，没有采用）：四条通过条件全部满足**——气相 CO 1012.6、H2 984.8、CH4 18.2、H2O 13.9、CO2 4.3 kgmole/h（参照 CO 1017、H2 981、CH4 22、H2O 11、CO2 3.5），CO 收率 39.96%，未反应的碳 1499.0（参照 1491，相差 0.5%）从第一段的液相出料离开，总外供热 84.6 MW（参照约 85）。等你决定是否采用 | **已定（用户 2026-10-08：采用方案 A）**。场景 3 的模型是“转化反应器（C + H2O → CO + H2，基准组分水，转化率 100%，反应相用合并相）+ Gibbs 反应器（进料是第一台的气相）”，两台都带能流、气相出料写 1400 °C；未反应的碳从第一台的液相出料离开。`gibbs` Recipe（1B）按这个结构编译，报告里如实说明主模型仍是 Gibbs 反应器；参考 `spikes/e10d_two_stage.py`（四条通过条件全满足）。1A 的集成测试按这个结构建第三个模型 |
| D15 | **对计划 §9.3 工具契约的修改建议 R1 至 R12**（台账“对工具契约的影响”一节，逐条有原因和状态）。要点：`session.connect` 一律 `NewInstance`（R1）；`case.ensure` 新建后立刻 `SaveAs`，可重入靠按 `FullName` 找（R2）；`basis.ensure_thermo` 末尾结束 Basis、物性包存内部名（R3）；`ensure_reaction` 读回容差 1e-3、Keq 来源只开 Gibbs 自由能和固定 K、加 `phase` 参数（R4）；`ensure_reactor` 先查名字、同名不同类型报冲突且不调 Add、连接顺序固定、热模式只开已验证的组合（R5）；`solver.solve` 改成检查、默认不挂起、两个 RPC 错误号映射成断开（R6）；所有“确保存在”先查再改（R7）；弹窗看门狗放进 Backend（R8，D12 已批准）；路径入口校验（R9）；反应集排序不进契约（R10，D13）；含固体碳的体系等 D14（R11）；`PlayScript` 只作 Backend 内部备用通道（R12） | 全部按建议 | **已确认（用户 2026-10-08：“D15 全部按建议确认”）**。R1 至 R12 在台账里的状态都改为“已确认”；R11 随 D14 落实为两段式。一处补充：R4 的 `phase` 参数不能只开放气相——两段式第一台转化反应器的进料是碳水浆料（重液相），反应相要用合并相（E10d 用的就是转化反应的默认值 5），所以 1A 的 `ReactionPhase` 开放两个都验证过的取值：气相（G0）、合并相（E10d） |
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
| 2026-10-08 | D12 批准：弹窗看门狗可以用后台线程（限 `backends/hysys_com/` 内部，只调 Win32，不碰 COM） | 用户答复。探针里的 `dialog_guard` 就是这种做法，0C 的 E11 证明它在窗口可见和隐藏时都能处理弹窗 |
| 2026-10-08 | D13：保持默认排序（不设排序、并行） | 用户答复“保持排序”，按我的理解记录（见 D13 一行） |
| 2026-10-08 | D1：LLM 统一用阿里云百炼的 Qwen API，密钥只从环境变量 `DASHSCOPE_API_KEY` 读取；主模型 `qwen3.8-max`（复杂推理、反应器判断、任务规划），快速模型 `qwen3.8-flash`（参数提取、场景识别、结果解释），备用模型 `qwen3.7-plus`（主模型异常或能力不足时切换）；不增加别的模型，不做复杂路由 | 用户答复。要求：不硬编码密钥；统一封装 Provider/Client，模型名可配置；为 Agent、工具调用、结构化输出预留接口（阶段 2A 做）；先做最小连通性测试，通过后才把 D1 标为完成 |
| 2026-10-08 | E10d 两段式只作为 D14 的可行性证据，不进正式模型 | 0C 提示词要求 Gibbs 反应器不能正确处理固体碳时不自行改用两段式；证据（四条通过条件全满足）交给用户 |
| 2026-10-08 | 对工具契约的建议 R1 至 R12 写进台账、登记 D15，不改 `MASTER_PLAN.md` | 0C 提示词要求：只写建议，每条标状态，需要确认的登记待决策 |
| 2026-10-08 | H24 写“部分确认”而不是 0C 提示词建议的“不需要” | 主路线没有因 H24 受阻，但为了设反应集排序实际用了 `PlayScript`，写“不需要”会丢掉有用的信息 |
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
| 2026-10-08 | 同名不同类型的 `Operations.Add` 使 HYSYS 进程崩溃（0C 任务 4，E11） | 在已有 `ERV-100` 的 Case 里再 Add 一个同名的 Gibbs 反应器：弹出 "Duplicate Object Name … Creating New Object ERV-100_2"，看门狗点 OK 后同一个对话框接连再弹 6 至 8 次，随后 `RPC call failed`、进程崩溃；怀疑是看门狗点得太快，改成同一个对话框 5 秒内只点一次，结果一样；第四次运行点一次就顺利建出 `ERV-100_2`，所以是偶发 | 台账 L26：创建类调用先按 `Names` 查，同名不同类型报冲突、绝不调 Add（R5、R7） |
| 2026-10-08 | 反应集排序一度被认为写不了（0B、0C 前半），后来 `PlayScript` 写成功 | 0C 任务 5 查脚本回放时读了安装目录 `Template\*.scp`，发现命令里的路径和变量写法与 XML 的 moniker 一致；手写 `Specify "<反应集路径>" ":Index.400.<序号>" <值>`，Case 隐藏时弹 "Could Not Find Target"，`case.Visible = True` 之后成功 | 台账 H24、H32、L29；教训：备选路线对照不是走过场，它补上了主路线的缺口 |
| 2026-10-08 | 终端工具开的新标签读不到用户配置的 `DASHSCOPE_API_KEY`，而且标签的 shell 集成加载失败，命令没有被输入 | 检查进程、用户、机器三级环境变量都没有；`run_in_terminal` 报 "Claude terminal integration did not load"，标签被关闭 | 密钥只设在用户自己的终端会话里，助手不碰；E0 探针写好，由用户运行（D1） |
| 2026-10-08 | E10 的 Gibbs 结果看起来合理但与温度无关（0C 任务 3） | 结果出来后没有直接接受：碳元素守恒误差 0、CO 收率 40.85% 都通过，但氢气恰好为 0、CH4 恰好是 CO 的一半。依次排除连接顺序、挂起求解器、碳和水分两股进料（结果完全相同），再排除气相热力学（不含碳、碳全部气化的两个对照，水煤气变换表观平衡常数一致，0.298 和 0.299），温度扫描 1000 至 1600 °C 组成不变，最后读组分库数据，发现碳的 `EvaluateGibbs(298.15 K)` 是 +671.3 kJ/mol（气态碳原子） | Gibbs 反应器不能直接处理库里的固体碳。登记 D14，等用户决定是否改用计划 §17.3 的两段式。台账 L24、L25 |

## 与计划的偏差

实现与 `MASTER_PLAN.md` 不一致的地方，以及原因。

| 日期 | 计划中的说法 | 实际做法 | 原因 |
|---|---|---|---|
| 2026-10-08 | §16.4 E3：在 GUI 里手工建好含三种反应器的参考 Case 再反向探测 | 先用自带示例 Synthesis Gas Production 探测转化和平衡反应器、反应、反应集；Gibbs 部分等用户手工建的 Case（D11） | 示例里没有 Gibbs 反应器，不想让探测等人 |
| 2026-10-08 | §16.2 H3、H9 等把"新建"归给 E4 至 E6 | E2 里顺带验证了新建物流（`MaterialStreams.Add`）和写组成，H12、H14 已部分确认 | 为了读"没有规定的变量"必须新建一股物流，结果可以直接用 |
| 2026-10-08 | 0B 提示词任务 5：把排序设成依次，用 0.573 判断排序的含义 | 没有做到：排序不能用代码写入；并行的 0.5000 已验证，含义改从示例 Case 的排序值反推 | 见"问题与解决"；提示词允许任务 5 受阻时推后，这里是走不通而不是推后 |
| 2026-10-08 | 0B 提示词任务 1（E4）、任务 3（E6）单独成脚本做 | 在 0A 的 D11 里已经完成，0B 没有重做 | 用户指示 D11 由助手自行创建参考 Case，创建链提前跑通 |
| 2026-10-08 | 0B 提示词"不要降到第三、四级" | 没有降级；第二级（XML、BackDoor）试了，没有走通 | 排序不是 G0 的组成部分，G0 全部是第 1 级 |
| 2026-10-08 | 0C 提示词任务 3：`e10` 满足四个通过条件，或者把不满足的现象和证据交给用户 | 不满足，已交给用户（D14）；还额外做了根因诊断（E10b、E10c）和两段式的可行性证据（E10d，没有采用） | Gibbs 反应器 + 库里的碳算错 |
| 2026-10-08 | 0C 提示词任务 5：LLM 视觉操作（如果有屏幕操作工具） | 未试验 | 本会话只有浏览器窗格里的页面操作工具，没有操作桌面应用的工具 |
| 2026-10-08 | 阶段 0A 任务 4（E0）等用户给出 LLM 信息后做 | 用户已给，但助手的进程读不到密钥变量，探针写好待用户运行，未标完成 | 见 D1 |
