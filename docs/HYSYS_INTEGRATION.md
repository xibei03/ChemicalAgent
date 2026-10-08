# HYSYS 接口台账

这份文件是 HYSYS 接口的**事实台账和探索日志**。`src/` 里只允许使用这里标为"已确认"的接口，标为"部分确认"的只能在备注写明的条件之内使用（`CLAUDE.md` 架构不变量 3）。

每个探针跑完立刻往这里写，不攒到最后。后面的阶段按节名查找内容，节名不要改。

## 状态的含义

| 状态 | 含义 |
|---|---|
| 已确认 | 在本机运行过，看到了结果 |
| 部分确认 | 只在备注写明的条件下实测通过，后面的代码只能在这些条件之内使用 |
| 不可行 | 试过，走不通，备注里有证据 |
| 未测试 | 还没有试 |
| 不需要 | 主路线已经走通，这项备用能力不必探测 |

台账以本机的实测为准。`MASTER_PLAN.md` §16.2 里的调用形式是来自旧版本公开资料的假设，已抄在下面表格的"备注"列，供对照。

---

## 连接与绑定方式

ProgID、早绑定还是晚绑定、怎么取得进程号、怎么退出。由阶段 0A 写。E1 共 9 次运行（run1 至 run9，输出在 `spikes/out/e1_connect_<run>.txt`）覆盖了下面全部结论；`Quit()` 在有打开的 Case 时的行为留给 E2。

**ProgID（注册表实测，`HKCR`）。**

| ProgID | CLSID | 服务器登记（`LocalServer32`） | 说明 |
|---|---|---|---|
| `HYSYS.Application`（等同 `HYSYS.Application.Latest`，CurVer 为 `HYSYS.Application.V15.0`） | `{0963D456-4B58-4A20-A4B0-B1372D4DA588}` | `aspenhysys.exe /Automation` | 通用写法。已有实例就复用，没有就启动。带版本号的是 `HYSYS.Application.V15.0`（登记相同，未单独测） |
| `HYSYS.Application.NewInstance`（另有 `.V15.0`、`.Latest`） | `{824AD71C-1A11-42CD-8A9E-912E73F4C91A}` | `aspenhysys.exe /AutomationSingleUse` | **每次都新开进程**（run3、run5），不碰已有的实例 |
| `HYSYS.Application.NewInstance.RTO`、`.Runtime` | `{6326FC09-6814-4B85-8E7A-C3AEA6FE324D}`、`{5393F4CF-F3A8-4AAD-A16F-F90488E1091D}` | 参数 `/RTOHYSYS`、`/RuntimeHYSYS` | 未探测，本项目不需要 |

**已确认（E1 run1 至 run9）。**

| 问题 | 结论 | 证据 |
|---|---|---|
| 怎么连接 | `win32com.client.Dispatch("HYSYS.Application")`（晚绑定）和 `win32com.client.gencache.EnsureDispatch("HYSYS.Application")`（早绑定）都能连上。进程是 `AspenHysys.exe`（安装目录 `C:\Program Files\AspenTech\Aspen HYSYS V15.0`），没有单独的 COM 服务进程。`Version` 读出 `Aspen HYSYS Version 15 (41.0)` | run1、run8 |
| 实例是新的还是已有的 | `HYSYS.Application`：HYSYS 已在运行时用 0.0 秒取得已有实例，进程清单不变，`Visible` 保持上一次设的值；没有运行时启动新实例。冷启动 35.2 秒（run1）和 34.5 秒（run3），之后 12 至 15 秒（run4、run8）。所以脚本不能假定拿到的是全新实例，也不能假定实例里没有别人的 Case | run1、run2、run4、run6 |
| 另开一个实例 | `HYSYS.Application.NewInstance` 每次都新开进程。已有实例 14024 在运行时，它新开了 7280，两个窗口标题相同（`<No Document> - Aspen HYSYS V15 - aspenONE`），只能靠进程号区分 | run3、run5 |
| 怎么得到进程号 | 连接前后各取一次 `tasklist /FO CSV /NH`（映像名 `AspenHysys.exe`），**新出现的进程就是新实例**；复用已有实例时进程号不变。备选：枚举可见顶层窗口、标题含 `hysys`，用 `win32process.GetWindowThreadProcessId` 取进程号，与 `tasklist` 一致。有多个实例时只用前一种 | run1、run5 |
| 怎么让实例退出 | `app.Quit()`：进程在 1.6 至 4.0 秒内消失，`tasklist` 无残留。只结束被调用的那个实例：run5 里新实例 7280 退出后，14024 继续运行 | run2、run3、run5、run8 |
| 释放 COM 引用够不够 | **不够**。丢掉全部引用并 `CoUninitialize()` 之后，实例在 60 秒内都没有退出 | run6 |
| 强制结束 | `taskkill /PID <pid> /T /F` 有效，1.6 秒内进程消失，无残留。HYSYS 进程是 svchost（DCOM 启动器）的子进程，按进程号结束不会误伤别的实例 | run7 |
| 怎么让实例留着 | 脚本结束时不调用 `Quit()`，实例继续运行 | run1、run4 |
| `Visible` | 初值 False，设 True 后读回 True | run1、run3、run8 |
| 弹窗 | 以上 9 次运行（没有打开 Case）没有出现弹窗 | 各次输出 |

**早绑定（run8、run9，类型库导出见探索日志）。**

- 类型库是 `HYSYS 15.0 Type Library`，GUID `{DFC1C58B-AE9F-11CF-8EB2-0020AF119B90}` v3.2（64 位的 `hysys.tlb`）。`gencache.EnsureModule(guid, 0, 3, 2)` 用 2 至 4 秒生成包装，缓存在 `%TEMP%\gen_py\3.12\`（这里是 `C:\Users\AZUREU~1\AppData\Local\Temp\gen_py\3.12`）。包装里有 758 个类（`CLSIDToClassMap`）。
- `EnsureDispatch` 返回的对象类型是 `win32com.gen_py.DFC1C58B-...x0x3x2._Application`，`app.SimulationCases` 返回类型化的 `SimulationCases`。
- **早绑定的属性名区分大小写，以类型库为准。** `app.Name` 抛 `AttributeError`，类型库里写的是小写的 `name`；晚绑定下 `app.Name` 可用（IDispatch 按名字查找不区分大小写）。
- **生成包装之后，连 `Dispatch("HYSYS.Application")` 也返回同一个 gen_py 类**（run9 的 `type(app)` 与 run8 相同）。所以只要缓存存在，"晚绑定"就不再是纯晚绑定；`gen_py` 缓存被清掉之后才是。要保证行为不随缓存变化，代码里统一用 `gencache.EnsureDispatch`。
- 未测：纯动态对象（`win32com.client.dynamic.Dispatch`）；从集合 `Item()` 取出的对象是否需要 `CastTo`（返回类型是 `IDispatch`，见 E3）。

**绑定方式的结论（暂定，E3 之后确认）：** 统一用早绑定，`gencache.EnsureDispatch`。

**脚本管理 HYSYS 会话的约定（后面所有探针沿用）：**

- 连接前后各取一次进程清单。新进程是自己启动的，结束时 `Quit()`；没有新进程说明复用了别人的实例，只在没有打开任何 Case 时才退出它。
- 需要独占时用 `HYSYS.Application.NewInstance`，用新进程号管理它。
- 调用卡住超过 45 秒，`_common.watch` 会打印 HYSYS 进程的窗口和弹窗文字，用来判断是不是模态弹窗阻塞。

---

## 接口事实表

计划 §16.2 的 H1 至 H26，逐项更新；新发现的能力从 H27 起追加。"备注"列开头的"计划假设"是 `MASTER_PLAN.md` 当时的写法，不是实测结果。

| 编号 | 能力 | 状态 | 实际可用的调用形式 | 证据（脚本、日期） | 备注 |
|---|---|---|---|---|---|
| H1 | COM 连接 | 已确认 | `win32com.client.gencache.EnsureDispatch("HYSYS.Application")`（早绑定，推荐）或 `Dispatch("HYSYS.Application")` 得到 Application 对象；`Version`、`FullName`、`Path`、`ActiveDocument` 可读，`Visible` 可读写；早绑定下名称成员是小写的 `name` | `spikes/e1_connect.py` run1 至 run9，2026-10-03 和 2026-10-08，输出 `spikes/out/e1_connect_run*.txt` | 条件：HYSYS 未运行（冷启动 35 秒，之后 12 至 15 秒）或已在运行（复用，0.0 秒）都成立；没有弹窗。`Version` 读出 `Aspen HYSYS Version 15 (41.0)`。打开 Case 时 `Quit()` 的行为见 H4 和 E2。计划假设的 `Dispatch("HYSYS.Application")` 形式成立。详见"连接与绑定方式" |
| H2 | 打开 Case、取活动 Case | 未测试 | | | 计划假设：`SimulationCases.Open(path)`、`ActiveDocument`。计划状态：官方文档确认（V7.3 版）。探针 E2 |
| H3 | 新建空白 Case | 未测试 | | | 计划假设：`SimulationCases.Add()`。探针 E4 |
| H4 | 保存、另存、关闭 | 未测试 | | | 计划假设：`Save`、`SaveAs`、`Close`。探针 E4、E12 |
| H5 | Basis 修改事务 | 未测试 | | | 计划假设：`BasisManager.StartBasisChange`、`EndBasisChange`。计划状态：官方文档确认（V7.3 版）。探针 E4 |
| H6 | 读取流体包、物性包、组分 | 未测试 | | | 计划假设：`FluidPackages.Item(i)`、`PropertyPackageName`、`Components`。计划状态：官方文档确认（V7.3 版）。探针 E2 |
| H7 | 新建流体包并指定物性包 | 未测试 | | | 计划假设：`FluidPackages.Add(...)`。探针 E4 |
| H8 | 添加库组分 | 未测试 | | | 计划假设：`Components.Add(name)`，以及库中的规范名。探针 E4 |
| H9 | 创建转化反应（计量系数、基准组分、转化率） | 未测试 | | | 计划假设：无。计划状态：未知。探针 E6 |
| H10 | 创建平衡反应并指定 Keq 来源（Gibbs 自由能、固定值、随温度变化） | 未测试 | | | 计划假设：无。计划状态：未知。探针 E8 |
| H11 | 创建反应集、加入成员、挂到流体包 | 未测试 | | | 计划假设：无。计划状态：未知。探针 E6 |
| H12 | 新建物流和能流 | 未测试 | | | 计划假设：`MaterialStreams.Add(name)`、`EnergyStreams.Add(name)`。探针 E5 |
| H13 | 写入 T、P、流量 | 未测试 | | | 计划假设：`Temperature.SetValue(value, unit)` 等。计划状态：官方文档确认（V7.3 版）。探针 E2、E5 |
| H14 | 写入组成 | 未测试 | | | 计划假设：`ComponentMolarFraction.Values = [...]`。计划状态：读取有公开示例，写入待验证。探针 E5 |
| H15 | 新建反应器 | 未测试 | | | 计划假设：`Operations.Add(name, typeName)`，三种反应器的 `typeName` 通过反向探测获得。探针 E3、E7 |
| H16 | 反应器连接与配置（进出料、能流、反应集、压降、Gibbs 模式） | 未测试 | | | 计划假设：无。计划状态：未知。探针 E7 至 E9 |
| H17 | 求解控制 | 未测试 | | | 计划假设：`Solver.CanSolve`。计划状态：官方文档确认（V7.3 版）。探针 E2 |
| H18 | 变量是否已知，是规定值还是计算值 | 未测试 | | | 计划假设：`IsKnown`、`State`。计划状态：官方文档确认（V7.3 版）。探针 E2 |
| H19 | 对象状态文本（未求解、欠规定等提示） | 未测试 | | | 计划假设：无。计划状态：未知。探针 E7 |
| H20 | 读取结果（T、P、流量、组成、分组分流量、热负荷） | 未测试 | | | 计划假设：`GetValue(unit)`、`ComponentMolarFraction.Values`。计划状态：基本读取有官方文档，分组分流量和热负荷待验证。探针 E7 |
| H21 | 固体碳组分及其在 Gibbs 反应器中的行为 | 未测试 | | | 计划假设：库组分 `Carbon`。计划状态：未知。探针 E10 |
| H22 | 空值的表示方式 | 未测试 | | | 计划假设：约定的哨兵值。探针 E2 |
| H23 | 模态弹窗对 COM 调用的阻塞 | 未测试 | | | 计划假设：无。计划状态：未知。探针 E11 |
| H24 | 降级通道：内部变量访问、脚本回放 | 未测试 | | | 计划假设：无。计划状态：未知。仅在 E6 至 E9 受阻时探测 |
| H25 | 组分库的枚举或检索（按名称、分子式查到规范名） | 未测试 | | | 计划假设：无。计划状态：未知。探针 E4 |
| H26 | Case 导出为可读文本并重新导入 | 未测试 | | | 计划假设：无。计划状态：未知。探针 E13 |
| H27 | 同时运行多个实例；按进程号管理实例 | 已确认 | `Dispatch("HYSYS.Application.NewInstance")` 新开进程；连接前后的 `tasklist` 差集得到新进程号；`app.Quit()` 只结束该实例；`taskkill /PID <pid> /T /F` 强制结束 | `spikes/e1_connect.py` run3、run5、run7，2026-10-08 | 释放 COM 引用不会让实例退出（run6）。两个实例的窗口标题相同，只能靠进程号区分。非计划内的能力，Backend 的会话管理会用到 |
| H28 | 早绑定（gen_py 包装）与类型库 | 已确认 | `gencache.EnsureModule("{DFC1C58B-AE9F-11CF-8EB2-0020AF119B90}", 0, 3, 2)` 生成包装；`pythoncom.LoadRegTypeLib(guid, 3, 2, 0)` 读类型信息 | `spikes/e1_connect.py` run8、run9，2026-10-08 | 包装缓存在 `%TEMP%\gen_py\3.12`。属性名区分大小写；生成之后 `Dispatch` 也返回包装类。集合 `Item()` 返回 `IDispatch`，是否需要 `CastTo` 待 E3 |

---

## 对象模型速查

三种反应器的类型名；反应、反应集、反应器对象的成员和取值含义。由阶段 0A 写，任务 6 和任务 9 完成后填。

### 三种反应器的类型名

（待填）

### 反应对象

（待填）

### 反应集对象

（待填）

### 反应器对象

（待填）

---

## 创建反应的线索

类型库里看起来能用来创建反应、反应集、反应器的接口和方法，按可能性排序。这是阶段 0B 的起点。由阶段 0A 写。

**初稿。来自类型库的只读勘查（`pythoncom.LoadTypeLib` 载入 `hysys.tlb`，见探索日志 L0），一条都没有运行验证。** 任务 6 和任务 9 完成后按实测重排。

| 序 | 线索 | 依据 | 下一步 |
|---|---|---|---|
| 1 | `Reactions.Add(name, Type)`，`Type` 的取值枚举待查 | `Reactions` 集合有 `Add(name, Type)`、`Remove(index)`、`RemoveAll()`、`Count`、`Item(index)`、`Names`、`index(name)`；`ReactionPackageManager` 有 `Reactions`、`ReactionSets`、`Components`、`BasisManager` 属性 | 先找到 `ReactionPackageManager` 从哪里取得（`BasisManager` 下？），再试 `Add`。属性枚举 `ReactionProperty_enum`（`rpBaseReactant`、`rpBasisConversion`、`rpStoichiometricCoefficients` 等）和 `ReactionBasis_enum` 对应反应的设置项 |
| 2 | `ReactionSets.Add(name, Type)`，再 `ReactionSet.AssociateFluidPackage(fluidPkg)` | `ReactionSets` 同样有 `Add`；`ReactionSet` 有 `AssociateFluidPackage`、`ActiveReactions`、`InactiveReactions`、`Operations`、`SolverMethod` | 同上。成员加入反应集的方式要看 `ActiveReactions` 的类型 |
| 3 | `Operations.Add(name, typeName)` 建反应器 | 类型库有 `ConversionReactor`、`EquilibriumReactor`、`GibbsReactor`、`KineticReactor`（CSTR）、`PFReactor`、`YieldReactor`。`GibbsReactorType_enum`：`gr_NoReactions=0`、`gr_SpecdRxnsOnly=2`、`gr_GibbsRxnsOnly=3` | `typeName` 字符串由 E3 反向探测获得，不要凭记忆写 |
| 4 | 具体的反应对象类型：`ConversionReaction`、`EquilibriumReaction`、`KineticReaction`、`SimpleRateReaction` | 类型库有这些接口，估计是 `Reactions.Item(i)` 取出的对象应有的类型，只暴露基类 `_IReaction` 时需要 `CastTo` | E3 |
| 5 | 降级：内部变量通道、脚本、XML | `Support\*.rdf`、`*.sgxml` 给出内部变量名；`ExtSDK\hysys.hh` 可 grep 签名；`BackDoor`、`XML`、`Script` 的命中待任务 6 检索 | 只在 1 至 4 受阻时 |

---

## 调用序列

每种反应器一小节，写"从空白 Case 到求解完成"的完整调用顺序，每一步都是实测通过的调用。

### 转化反应器

阶段 0B 填写。

（待填）

### 平衡反应器

阶段 0C 填写。

（待填）

### Gibbs 反应器

阶段 0C 填写。

（待填）

---

## 组分规范名

用到的每个组分在 HYSYS 组分库里的确切名字。阶段 0B、0C 填写。

| 用途 | 规范名 | 来源（脚本、日期） |
|---|---|---|

---

## 鲁棒性观察

同名对象、进程中断、弹窗、保存重开。阶段 0C 填写。

（待填）

---

## 路线对照

主路线和备选路线的对比。阶段 0C 填写。

（待填）

---

## 对工具契约的影响

实测结果要求对计划 §9.3 的工具做哪些调整。阶段 0C 填写。

（待填）

---

## 探索日志

每个探针一条：目的、做法、结果、结论。失败的尝试同样记录，它们是考核报告"探索过程"一节的素材。新条目写在最后。

条目格式：

- **目的**：这个探针要回答什么问题
- **做法**：做了什么
- **结果**：看到了什么，附关键输出
- **结论**：对台账哪几项有什么影响
- **脚本与输出**：文件路径

### L0 只读勘查：注册表、类型库、安装目录（2026-10-03）

- **目的**：动手写探针之前，先弄清这台机器上有什么：ProgID、类型库、示例 Case、帮助、定义文件。
- **做法**：用 `winreg` 枚举 `HKCR` 里含 `hysys` 的键；`pythoncom.LoadTypeLib` 载入 `hysys.tlb`，只在内存里列类型名和成员，没有生成包装文件；列安装目录；对 212 个示例 `.hsc` 扫描反应器类型字符串。
- **结果**：
  - ProgID 见"连接与绑定方式"。
  - 类型库注册为 `HYSYS 15.0 Type Library`，GUID `{DFC1C58B-AE9F-11CF-8EB2-0020AF119B90}` v3.2，路径 `hysys.tlb`（64 位）、`hysys32.tlb`（32 位）。共 1140 个类型：726 dispatch、377 enum、22 coclass。另有 `HysysSvr 41.0 Type Library`（`{8F00838C-4B87-4C32-B377-80DDF3E010AD}` v29.0，在 `HysysSvr.exe` 里），未查看。
  - 反应相关的接口和 `Add` 方法见"创建反应的线索"。
  - 安装目录里有：`ExtSDK\hysys.hh`（23 MB 的 C++ 头文件，可以 grep 方法签名）；`Support\*.rdf` 和 `*.sgxml`（单元操作的界面和变量定义，如 `convrxn.rdf`、`equirxn.rdf`、`rxnset.rdf`、`rxnop.rdf`，操作对象名 `ConversionReactorOpObject`、`EquilibriumReactorOpObject`、`GibbsReactorOpObject`）；四个帮助文件 `ww10_com.chm`、`xhysys.chm`、`ww10_cxx.chm`、`ww10_000.chm`；`C:\Windows\hh.exe`。
  - **走不通的尝试**：直接扫示例 `.hsc` 的字节找反应器类型字符串，0 个文件命中。文件是压缩格式，只能用 COM 打开才能看到单元操作。
  - 名字上最可能含反应器的示例：`Samples\Synthesis Gas Production.hsc`、`Samples\Ammonia Synthesis.hsc`、`Samples\Refining Cases\MB Examples\Toluene_Disproportionation_Example.hsc`、`Samples\Sustainability\Alkaline Electrolysis\Green Ammonia Process.hsc`、`Samples\CSTR - Dynamic Model.hsc`（都在 `C:\Program Files\AspenTech\Aspen HYSYS V15.0\` 下）。
- **结论**：创建反应、反应集的入口在类型库层面存在，但没有运行验证，H9 至 H11、H15、H16 仍是"未测试"。
- **脚本与输出**：无脚本，交互式只读命令。

### L1 E1：连接 HYSYS，第一次运行（2026-10-03）

- **目的**：Q1 ProgID 是什么；Q2 HYSYS 已在运行时取得的是已有实例还是新实例；Q3 怎样得到进程号；Q4 脚本结束时怎样退出或保留实例。这次运行只覆盖 Q1、Q3，以及"HYSYS 未运行时 Dispatch 做了什么"。
- **做法**：HYSYS 未运行，执行 `.\.venv\Scripts\python.exe spikes\e1_connect.py --exit keep --tag run1_launch_keep`：枚举 `HKCR`，`tasklist` 取连接前后的进程，`Dispatch("HYSYS.Application")`，读成员，设 `Visible=True`，用窗口取进程号，不退出实例。
- **结果**：
  - `Dispatch` 用时 35.2 秒，连接后出现新进程 `AspenHysys.exe`（PID 2092）。
  - `app.Version = 'Aspen HYSYS Version 15 (41.0)'`，`Name = 'Aspen HYSYS'`，`FullName` 为 `...\aspenhysys.exe`，`Visible` 初值 False、设置后读回 True，`ActiveDocument` 为 None。
  - 可见窗口 `<No Document> - Aspen HYSYS V15 - aspenONE` 属于 PID 2092，与 `tasklist` 一致。没有弹窗。
- **结论**：H1 在"通用 ProgID、晚绑定、HYSYS 未运行"的条件下通过，记为部分确认。Q2 和 Q4 待测，见"连接与绑定方式"。
- **脚本与输出**：`spikes/e1_connect.py`，`spikes/out/e1_connect_run1_launch_keep.txt`。

### L2 E1：复用已有实例，并用 Quit 退出（2026-10-03，run2）

- **目的**：Q2 HYSYS 已在运行时 `Dispatch` 得到的是已有实例还是新实例；Q4 `app.Quit()` 能否让实例退出。
- **做法**：run1 留下的实例（PID 2092，窗口标题 `<No Document>`，没有打开任何 Case）还开着，先确认标题仍是 `<No Document>`，再执行 `.\.venv\Scripts\python.exe spikes\e1_connect.py --exit quit --tag run2_attach_quit`。
- **结果**：
  - `Dispatch('HYSYS.Application')` 用时 0.0 秒，连接前后进程清单都是 `{2092: 'AspenHysys.exe'}`，没有新进程：取得的是已有实例。`Visible` 读出 True（run1 设的），`ActiveDocument` 为 None。
  - `app.Quit()` 之后进程 2092 在 3.5 秒内消失，随后 `tasklist` 和 `Get-Process` 里都没有 HYSYS 进程。
- **结论**：`HYSYS.Application` 复用已有实例；`Quit()` 可用于结束实例。`NewInstance`、释放引用、`taskkill` 和早绑定仍未测，见"连接与绑定方式"。
- **脚本与输出**：`spikes/e1_connect.py`，`spikes/out/e1_connect_run2_attach_quit.txt`。

### L3 E1：NewInstance、释放引用、强制结束、早绑定（2026-10-08，run3 至 run9）

- **目的**：补完 E1 剩下的问题。`NewInstance` 是否新开进程、能否单独退出；只释放 COM 引用能否让实例退出；`taskkill` 的效果；早绑定能否连接。
- **做法**：先修了脚本（`spikes/e1_connect.py` 在有多个实例时会取错进程号；`release` 模式的引用其实还被调用方持有），公共部分抽到 `spikes/_common.py`。依次运行：run3 `NewInstance` 无实例时连接再 `Quit()`；run4 默认 ProgID、不退出（实例 A 留着）；run5 `NewInstance` 在 A 运行时连接再 `Quit()`；run6 复用 A，丢掉引用并 `CoUninitialize()`；run7 复用 A，`taskkill`；run8 `EnsureDispatch` 连接再 `Quit()`；run9 `Dispatch` 连接再 `Quit()`（和 run8 对照）。
- **结果**：
  - run3：`NewInstance` 用时 34.5 秒，新进程 9140，`Quit()` 后 4.0 秒内消失。
  - run4：默认 ProgID 用时 12.5 秒，新进程 14024，留着。
  - run5：`NewInstance` 用时 12.5 秒，新进程 7280，两个实例的窗口标题相同；`Quit()` 后 7280 在 1.7 秒内消失，14024 继续运行。
  - run6：`Dispatch` 0.0 秒复用 14024；丢掉引用并 `CoUninitialize()` 后，60 秒内进程仍在。
  - run7：复用 14024；`taskkill /PID 14024 /T /F` 成功，1.6 秒内消失，无残留（它是 PID 996 的子进程）。
  - run8：`EnsureDispatch` 用时 15.3 秒，对象类型 `win32com.gen_py.DFC1C58B-...x0x3x2._Application`；`app.Name` 抛 `AttributeError`（类型库里是小写的 `name`）；`Quit()` 后 1.6 秒内消失。
  - run9：`Dispatch`（包装已存在）返回的对象类型与 run8 相同。
- **结论**：H1 升为已确认，新增 H27、H28。"连接与绑定方式"一节已按这些结果重写。走过的弯路：第一版脚本的 `release` 没有真正释放引用，`pick_pid` 在两个实例时会取到别人的进程号，这两处在 run5 之前就改掉了。
- **脚本与输出**：`spikes/e1_connect.py`、`spikes/_common.py`，`spikes/out/e1_connect_run3_newinstance_quit.txt` 至 `e1_connect_run9_late_quit.txt`。
