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

ProgID、早绑定还是晚绑定、怎么取得进程号、怎么退出。由阶段 0A 写，任务 5 和任务 6 完成后填。**目前只写了 E1 的两次运行（run1、run2）和只读勘查得到的部分，其余标"待测"。**

**ProgID（注册表实测，`HKCR`）。**

| ProgID | CLSID | 服务器登记（`LocalServer32`） | 说明 |
|---|---|---|---|
| `HYSYS.Application`（等同 `HYSYS.Application.Latest`，CurVer 为 `HYSYS.Application.V15.0`） | `{0963D456-4B58-4A20-A4B0-B1372D4DA588}` | `aspenhysys.exe /Automation` | 通用写法，已用它连接成功。带版本号的是 `HYSYS.Application.V15.0`（未测） |
| `HYSYS.Application.NewInstance`（另有 `.V15.0`、`.Latest`） | `{824AD71C-1A11-42CD-8A9E-912E73F4C91A}` | `aspenhysys.exe /AutomationSingleUse` | 从登记看每次新开进程（待测） |
| `HYSYS.Application.NewInstance.RTO`、`.Runtime` | `{6326FC09-6814-4B85-8E7A-C3AEA6FE324D}`、`{5393F4CF-F3A8-4AAD-A16F-F90488E1091D}` | 参数 `/RTOHYSYS`、`/RuntimeHYSYS` | 未探测 |

**已确认（E1 run1、run2）。**

- 晚绑定 `Dispatch("HYSYS.Application")` 可用。进程是 `AspenHysys.exe`（安装目录 `C:\Program Files\AspenTech\Aspen HYSYS V15.0`），没有单独的 COM 服务进程。
- 取进程号：枚举可见的顶层窗口，标题含 `hysys` 的窗口，用 `win32process.GetWindowThreadProcessId` 取进程号，与 `tasklist` 里的 `AspenHysys.exe` 一致。窗口标题是 `<No Document> - Aspen HYSYS V15 - aspenONE`。
- `Visible` 初值为 False，设为 True 后读回 True。
- **已有实例会被复用**（run2）：HYSYS 已在运行时，`Dispatch("HYSYS.Application")` 用时 0.0 秒，进程清单不变（仍是 PID 2092），`Visible` 保持上一次设的 True。所以脚本不能假定拿到的是全新实例，也不能假定实例里没有别人的 Case。
- **退出**：`app.Quit()` 有效，进程在 3.5 秒内消失，`tasklist` 里没有残留。这次实例没有打开任何 Case，有 Case 时是否弹保存对话框未测。
- **保留**：脚本结束时不调用 `Quit()`，实例继续运行（run1）。

**待测，下一个会话继续：**

- `HYSYS.Application.NewInstance` 是否确实新开进程，新开的实例能否单独 `Quit()`（`--progid HYSYS.Application.NewInstance`）。
- 释放 COM 引用、`taskkill /PID` 各自的效果；`Quit()` 在有打开的 Case 时是否弹窗。命令是 `.\.venv\Scripts\python.exe spikes\e1_connect.py --exit release|kill --tag <名字>`。
- 早绑定：类型库是 `hysys.tlb`，GUID `{DFC1C58B-AE9F-11CF-8EB2-0020AF119B90}` v3.2，`gencache.EnsureModule` 或 `EnsureDispatch` 是否可用，是否需要 `CastTo`。

---

## 接口事实表

计划 §16.2 的 H1 至 H26，逐项更新；新发现的能力从 H27 起追加。"备注"列开头的"计划假设"是 `MASTER_PLAN.md` 当时的写法，不是实测结果。

| 编号 | 能力 | 状态 | 实际可用的调用形式 | 证据（脚本、日期） | 备注 |
|---|---|---|---|---|---|
| H1 | COM 连接 | 部分确认 | `win32com.client.Dispatch("HYSYS.Application")`（晚绑定）得到 Application 对象；`Version`、`Name`、`FullName`、`Path`、`ActiveDocument` 可读，`Visible` 可读写 | `spikes/e1_connect.py`，2026-10-03，输出 `spikes/out/e1_connect_run1_launch_keep.txt`、`e1_connect_run2_attach_quit.txt` | 只在"通用 ProgID、晚绑定、HYSYS 事先没有运行"的条件下实测：冷启动 35.2 秒，随后只有一个 `AspenHysys.exe` 进程，没有弹窗，`Version` 读出 `Aspen HYSYS Version 15 (41.0)`。run2：HYSYS 已在运行时，`Dispatch` 用时 0.0 秒、没有新进程，取得的是已有实例，`Visible` 保持 True；`app.Quit()` 后进程在 3.5 秒内消失，没有残留（当时实例没有打开任何 Case）。未测：带版本号的 `HYSYS.Application.V15.0`、`HYSYS.Application.NewInstance`、早绑定 `EnsureDispatch`、`Quit` 时有打开 Case 的行为、释放引用和 `taskkill` 的效果。计划假设的 `Dispatch("HYSYS.Application")` 形式成立 |
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
