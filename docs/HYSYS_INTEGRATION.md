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
| 弹窗 | E1 的 9 次运行（没有打开 Case）没有弹窗。有打开的 Case 时（E2b）：`app.Quit()` 和 `case.Close()` 都不弹"是否保存"，Case 改过也一样；打开用到 Aspen Properties 的 Case 会弹模态对话框（H23） | 各次输出，`e2b_quit_with_case.txt`，`find_ref_case_scan.txt` |

**早绑定（run8、run9，类型库导出见探索日志）。**

- 类型库是 `HYSYS 15.0 Type Library`，GUID `{DFC1C58B-AE9F-11CF-8EB2-0020AF119B90}` v3.2（64 位的 `hysys.tlb`）。`gencache.EnsureModule(guid, 0, 3, 2)` 用 2 至 4 秒生成包装，缓存在 `%TEMP%\gen_py\3.12\`（这里是 `C:\Users\AZUREU~1\AppData\Local\Temp\gen_py\3.12`）。包装里有 758 个类（`CLSIDToClassMap`）。
- `EnsureDispatch` 返回的对象类型是 `win32com.gen_py.DFC1C58B-...x0x3x2._Application`，`app.SimulationCases` 返回类型化的 `SimulationCases`。
- **早绑定的属性名区分大小写，以类型库为准。** `app.Name` 抛 `AttributeError`，类型库里写的是小写的 `name`；晚绑定下 `app.Name` 可用（IDispatch 按名字查找不区分大小写）。
- **生成包装之后，连 `Dispatch("HYSYS.Application")` 也返回同一个 gen_py 类**（run9 的 `type(app)` 与 run8 相同）。所以只要缓存存在，"晚绑定"就不再是纯晚绑定；`gen_py` 缓存被清掉之后才是。要保证行为不随缓存变化，代码里统一用 `gencache.EnsureDispatch`。
- 未测：纯动态对象（`win32com.client.dynamic.Dispatch`）；从集合 `Item()` 取出的对象是否需要 `CastTo`（返回类型是 `IDispatch`，见 E3）。

**绑定方式的结论（暂定，E3 之后确认）：** 统一用早绑定，`gencache.EnsureDispatch`。`SimulationCases.Open()` 返回类型化的 `_SimulationCase`，`Operations.Item(i)` 返回具体的反应器类型（如 `ConversionReactor`），**不需要 `CastTo`**（L5）。

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
| H2 | 打开 Case、取活动 Case | 已确认 | `case = app.SimulationCases.Open(path)` 返回类型化的 `_SimulationCase`；`case.FullName`、`case.Flowsheet`、`case.BasisManager`、`case.Solver` 可用；`case.Close()` 关闭。`app.ActiveDocument` 在 `Open` 之后仍是 `None`，所以**不要用它**，自己拿着 `Open` 返回的对象 | `spikes/find_ref_case.py`、`spikes/e2_read_write.py`，2026-10-08 | **路径必须是长路径。** 8.3 短路径（`C:\Users\AZUREU~1\...`，目录短名或者目录和文件名都短）一律 `E_ACCESSDENIED`（`-2147024891`），同一个副本用长路径就成功（e2 run1 Q0）。给 HYSYS 的路径先 `Path.resolve()`。示例 `.hsc` 复制到临时目录后用副本。打开 Aspen Properties 的 Case 会被弹窗卡住（H23）。 计划假设：`SimulationCases.Open(path)`、`ActiveDocument`。计划状态：官方文档确认（V7.3 版）。探针 E2 类型库（2026-10-08，未运行验证）：`SimulationCases.Open(name: BSTR) -> IDispatch`、`Count`、`Item(index)`、`Close()`；`Application.ActiveDocument`。 |
| H3 | 新建空白 Case | 已确认 | `case = app.SimulationCases.Add("name")` 返回类型化的 `_SimulationCase`；新 Case 的 `Count` 加 1 | `spikes/e4_basis.py` run4，`spikes/e4b_property_package.py`，2026-10-08，输出 `spikes/out/e4_basis_run4.txt`、`e4b_property_package_run2.txt` | 新 Case 的 `FullName` 是 HYSYS 进程当前目录下的 `name.hsc`（`C:\Windows\system32\e4_new.hsc`），还没有保存；`Visible` 为 False，所以 `app.ActiveDocument` 是 None；**新 Case 一开始就处在 Basis 修改状态**：`BasisManager.IsChangingBasis` 为 True，`CanEndBasisChange` 为 False，没有流体包，没有组分列表。 计划假设：`SimulationCases.Add()`。探针 E4 类型库（2026-10-08，未运行验证）：`SimulationCases.Add(name, Type)`，两个参数都是可选的 VARIANT。 |
| H4 | 保存、另存、关闭 | 已确认 | `case.SaveAs(path)`：写出文件（只有一个流体包的 Case 约 141 KB），之后 `case.FullName` 变成新路径；`case.Close()`；`app.SimulationCases.Open(path)` 重新打开，Basis（流体包、物性包、组分）都在 | `spikes/e4_basis.py` run4，`spikes/e4b_property_package.py`，2026-10-08，输出 `spikes/out/e4_basis_run4.txt`、`e4b_property_package_run2.txt` | `SaveAs(path)` 覆盖已有文件时**不弹窗**，同目录留下 HYSYS 自动备份 `<名字>.bk0`（`.gitignore` 已排除）。 确认的是 `SaveAs(path)`、`Close()`、`Open(path)`；`Save()`、`SaveAs2`、`SaveCopyAs` 没测，Backend 只会用前三个。路径必须是长路径（H2）。物性包没设好就保存，重开时会弹模态对话框 "Could not load the Property Package for Fluid Package ..."，`Open` 卡住（E4 run2）。`Close()` 和 `Quit()` 不弹保存确认（E2b）。 只测了关闭：`case.Close()` 0.2 秒返回，**没有保存确认弹窗**，Case 改过（`IsDirty` 为 True）也一样；`app.Quit()` 在 Case 打开着、改过或没改过时都不弹窗，实例 0.5 秒内退出。注意 `IsDirty` 在刚打开、没改过的 Case 上也是 True，不能用它判断"有没有改过"。 计划假设：`Save`、`SaveAs`、`Close`。探针 E4、E12 类型库（2026-10-08，未运行验证）：`SimulationCase.Save()`、`SaveAs(...)`、`SaveAs2`、`SaveCopyAs`、`Close()`、`IsDirty`。 **0C（E12）补充**：另存到 `spikes/out/` 后 `case.FullName` 变成新路径；关闭、`Open` 重开后不重新求解就读到与保存前一致的出料、热负荷和流程图状态，求解器 `CanSolve` 为 True、`IsSolving` 为 False；重开后改规定可以重新求解，结果与保存前同一规定下一致；`Save()`（不带路径）写回当前路径并留下 `.bk0`；另一个新实例打开同一个文件结果一致（L27）。**`SaveAs` 到不存在的目录不报错但不写文件**，文件名含非法字符抛 .NET 异常（L26），所以 `SaveAs` 之后必须读回文件。 |
| H5 | Basis 修改事务 | 已确认 | 新 Case 一开始就在 Basis 修改状态；流体包配好后 `manager.EndBasisChange()`；之后要改 Basis 用 `manager.StartBasisChange()`（`IsChangingBasis` 变 True），改完再 `EndBasisChange()` | `spikes/e6_reaction.py` run4、`spikes/e6b_keq_source.py` run2，2026-10-08，输出 `spikes/out/e6_reaction_run4.txt`、`e6b_keq_source_run2.txt` | **建反应和反应集不需要在 Basis 修改状态里**：`EndBasisChange()` 之后直接 `Reactions.Add` 也成功（E6 run4）；`StartBasisChange()` 在 Basis 结束后可用。 `CanEndBasisChange` 为 False 时调用 `EndBasisChange()` 抛 `com_error`（E_FAIL）。`CanEndBasisChange` 要求流体包已经有物性包和组分列表。已经结束 Basis 之后建反应和反应集，不需要先 `StartBasisChange()`（见上）。 计划假设：`BasisManager.StartBasisChange`、`EndBasisChange`。计划状态：官方文档确认（V7.3 版）。探针 E4 类型库（2026-10-08，未运行验证）：`BasisManager.StartBasisChange()`、`EndBasisChange()`、`IsChangingBasis`、`CanEndBasisChange`。 |
| H6 | 读取流体包、物性包、组分 | 已确认 | `fps = case.BasisManager.FluidPackages`；`fps.Count`、`list(fps.Names)`、`fps.Item(i)`（下标从 0 开始）；`fp.name`、`fp.PropertyPackageName`、`fp.Components.Count`、`list(fp.Components.Names)`；`case.Flowsheet.FluidPackage.name` | `spikes/e2_read_write.py`，2026-10-08，输出 `spikes/out/e2_read_write_run1.txt`、`e2_read_write_run2.txt` | 示例 Synthesis Gas Production：流体包名 `Basis-1`，`PropertyPackageName` 读出 `PengRobinson`（没有空格和连字符），组分 `['Methane', 'H2O', 'CO', 'CO2', 'Hydrogen', 'Nitrogen', 'Oxygen']`，物流的组成向量按这个顺序排。 计划假设：`FluidPackages.Item(i)`、`PropertyPackageName`、`Components`。计划状态：官方文档确认（V7.3 版）。探针 E2 类型库（2026-10-08，未运行验证）：`BasisManager.FluidPackages`（集合）；`FluidPackage.PropertyPackageName`（可读写）、`Components`、`ReactionPackage`、`ComponentList`。 |
| H7 | 新建流体包并指定物性包 | 已确认 | `fp = manager.FluidPackages.Add("Basis-1")`；`fp.ComponentList = component_list`；`fp.PropertyPackageName = "pengrob"`。读回 `fp.PropertyPackageName` 得 `Peng-Robinson`，`fp.PropertyPackage.TypeName` 得 `pengrob` | `spikes/e4_basis.py` run4，`spikes/e4b_property_package.py`，2026-10-08，输出 `spikes/out/e4_basis_run4.txt`、`e4b_property_package_run2.txt` | **设置时必须用物性包的内部名 `pengrob`（它的 `TypeName`）**。界面名 `Peng-Robinson`、读到的名字、`PengRobinson`、`PR`、`ppkg_PR`、`5891` 等 10 种写法都抛 `E_INVALIDARG`（-2147024809），`FluidPackages.Add(name, Type)` 的 `Type` 传 5891、`"ppkg_PR"`、`"Peng-Robinson"` 等也不会设上物性包（e4b run1、run2）。读和写用的名字不同。没有组分列表时 `CanEndBasisChange` 为 False。其他物性包的内部名没有试。 计划假设：`FluidPackages.Add(...)`。探针 E4 类型库（2026-10-08，未运行验证）：`FluidPackages.Add(name, Type)`；`FluidPackage.PropertyPackageName` 可写；`PropertyPackageType_enum` 有 `ppkg_PR=5891`。 |
| H8 | 添加库组分 | 已确认 | V15 里组分挂在组分列表上：`component_list = manager.ComponentLists.Add("CL-1")`；`component_list.Components.Add("Methane")` 返回 `Component`；读 `list(component_list.Components.Names)`；再 `fp.ComponentList = component_list`，`fp.Components.Names` 随之有内容 | `spikes/e4_basis.py` run4，`spikes/e4b_property_package.py`，2026-10-08，输出 `spikes/out/e4_basis_run4.txt`、`e4b_property_package_run2.txt` | 库里的名字大小写不敏感，返回规范名（`methane` 得 `Methane`）；`Add` 一个已有的组分（含别名 `H2` 得 `Hydrogen`）不报错也不重复。**不接受**：分子式（`CH4`、`C7H8`、`C6H6`）、`Water`、`CarbonMonoxide`、`CarbonDioxide`、`C1`、`pXylene`、`PXYLENE`、`C`、`Graphite`，抛 `E_FAIL`。规范名见"组分规范名"一节。 计划假设：`Components.Add(name)`，以及库中的规范名。探针 E4 类型库（2026-10-08，未运行验证）：`FluidPackage.Components.Add(name, Type)`；`Component` 有 `IsSolid`、`Formula`、`CAS_Number`。 |
| H9 | 创建转化反应（计量系数、基准组分、转化率） | 已确认 | `reaction = manager.ReactionPackageManager.Reactions.Add("Tol-Disp", "conversionrxn")` 返回 `ConversionReaction`；`reactant = reaction.Reactants.Add("Toluene")` 返回 `Reactant`；`reactant.StoichiometricCoefficientValue = -2.0`（负为反应物，正为产物）；`reaction.BaseComponent = fp.Components.Item("Toluene")`；`reaction.Conversion = 50.0`（百分数）；`reaction.ReactionPhase = 0`（气相） | `spikes/e6_reaction.py` run4、`spikes/e6b_keq_source.py` run2，2026-10-08，输出 `spikes/out/e6_reaction_run4.txt`、`e6b_keq_source_run2.txt` | **G0 验证（0B）**：四产物分数系数的反应 2 甲苯 → 1 苯 + 0.24 对二甲苯 + 0.52 间二甲苯 + 0.24 邻二甲苯，系数全部写入并读回，求解后出料摩尔分率与解析解逐项相同（0.5000、0.2500、0.0600、0.1300、0.0600），所以**分数计量系数可用**，场景 2 用一个反应即可。 **`Type` 必须是反应的内部类型名**：`conversionrxn`、`equilibriumrxn`、`kineticrxn`。界面名 `Conversion`、类名 `ConversionReaction`、整数 0 至 3、省略 `Type`，都抛 `E_FAIL`。**分数计量系数能写**（0.24 读回 0.24，此时 `BalanceErrorValue` 非零，是质量不守恒的提示）。调用 `BalanceStoichiometry()`、另存重开之后读回，最后一个组分的系数被微调了，使质量守恒（甲苯歧化的对二甲苯：1.0 变 1.00005；SMR 的氢：3.0 变 2.9996；具体是哪一步改的没有单独验证），读回比对要留容差（1e-3）。`ReactionPhase` 的默认值：转化反应 5（合并相），平衡反应 0（气相）。`Reactions.Remove(name)` 可用。新建的反应 `HeatOfReactionValue` 读取抛 `E_FAIL`（重开后也是），要等被反应器用上再说。重开后反应的设置都在。 E3 实测（只读）：转化反应的 `TypeName` 是 `conversionrxn`；读到的结构是 `Reactants`（负为反应物、正为产物）、`BaseComponent`、`Conversion`（百分数）。 计划假设：无。计划状态：未知。探针 E6 类型库（2026-10-08，未运行验证）：`ReactionPackageManager.Reactions.Add(name, Type)` 返回 VARIANT；`ConversionReaction`：`Reactants`（集合，有 `Add`）、`Reactant.StoichiometricCoefficientValue`（可写）、`BaseComponent`（可写）、`Conversion`（double，可写）、`ReactionPhase`、`BalanceStoichiometry()`。 |
| H10 | 创建平衡反应并指定 Keq 来源（Gibbs 自由能、固定值、随温度变化） | 部分确认 | `reaction = ...Reactions.Add("SMR", "equilibriumrxn")` 返回 `EquilibriumReaction`；计量系数同转化反应。**Keq 来源 `LnKSource` 的实际取值：1 = Ln(K) 公式，2 = Gibbs 自由能（新建时的默认值），3 = 固定 K，4 = K–T 表。**固定 K：`reaction.LnKSource = 3`，`reaction.EquilibriumConstant = 12.5`，读回 12.5；改回 `LnKSource = 2` 可用 | `spikes/build_reference_case.py` run3、run4，2026-10-08，输出 `spikes/out/build_reference_case_run4.txt` | **Gibbs 自由能来源已经端到端验证**：SMR 和 WGS 用默认来源，平衡反应器 710 °C、600 °C 的摩尔分率与独立参照值相差不超过 0.0046、0.0014（容差 0.02），CH4 转化率 54.0% 和 30.3%。固定 K 只验证了属性读写；Ln(K) 公式和 K–T 表来源没有试。 **写 0 被静默忽略**（读回还是原值）；类型库枚举的名字（`eqrxn_Gibbs=0`、`eqrxn_FixedK=2`、`eqrxn_Table=3`、`eqrxn_FixedExtent=4`）和实际取值对不上，**不要用枚举名**。映射的依据：`Support\equirxn.rdf` 里界面分组的可见范围（Ln(K) 公式 1，Gibbs 自由能 2，固定 K 3，K–T 表 4），加上实测（新建默认读出 2，示例里用 K–T 表的反应读出 4，写 1 至 4 都读回原值）。写入任何一个明确的来源都会把 `AutoDetect` 变成 False。默认值：`Basis` 1（`rbActivityBasis`），`ReactionPhase` 0，温度范围 -273.15 至 3000 °C。E3 实测（只读）：平衡反应的 `TypeName` 是 `equilibriumrxn`；`LnKSource` 读出的数字和类型库枚举对不上（K–T 表读出 4），已用 Gibbs 来源的参考 Case 核对，见上。 计划假设：无。计划状态：未知。探针 E8 类型库（2026-10-08，未运行验证）：`EquilibriumReaction`：`LnKSource`（`eqrxn_Gibbs=0`、`eqrxn_LnKEquation=1`、`eqrxn_FixedK=2`、`eqrxn_Table=3`、`eqrxn_FixedExtent=4`）、`EquilibriumConstant`、`LnKEquationA/B/C/DParameter`、`MinTemperatureValue`、`MaxTemperatureValue`、`Basis`、`ReactionPhase`。 |
| H11 | 创建反应集、加入成员、挂到流体包 | 已确认 | `rset = manager.ReactionPackageManager.ReactionSets.Add("Conv-Set")` 返回 `ReactionSet`（`TypeName` 为 `rxnset`，不需要 `Type`）；`rset.ActiveReactions.Add("Tol-Disp")`（按名字）；`rset.AssociateFluidPackage(fp)` | `spikes/build_reference_case.py` run3、run4，2026-10-08，输出 `spikes/out/build_reference_case_run4.txt` | G0 里反应集（`Conv-Set`，含 Tol-Disp）加入流体包并挂到转化反应器，出料组成按反应变化。 反应集挂到转化反应器（`Conv-Set`）和平衡反应器（`Eq-Set`）之后，出料组成按反应变化，求解成功。 **`AssociateFluidPackage` 才是"加入流体包"**：`Add` 之后、`AssociateFluidPackage` 之前，`fp.ReactionPackage.ReactionSets.Names` 里没有这个集合，调用之后才有。反应集和成员重开后都在。 E3 实测（只读）：反应集 `TypeName` 是 `rxnset`；成员是 `ActiveReactions.Names` 和 `InactiveReactions.Names`；与流体包的关联体现为出现在 `fp.ReactionPackage.ReactionSets.Names` 里。 计划假设：无。计划状态：未知。探针 E6 类型库（2026-10-08，未运行验证）：`ReactionPackageManager.ReactionSets.Add(name, Type)`；`ReactionSet.AssociateFluidPackage(fluidPkg)`；`ActiveReactions` 和 `InactiveReactions`（`Reactions` 集合，加成员的方式待查）；`Operations`、`SolverMethod`。 |
| H12 | 新建物流和能流 | 已确认 | `flowsheet.MaterialStreams.Add("name")` 和 `flowsheet.EnergyStreams.Add("Q-1")` 都返回 `ProcessStream`；`flowsheet.MaterialStreams.Item("name")`、`Remove`、`Names` | `spikes/build_reference_case.py` run3、run4，2026-10-08，输出 `spikes/out/build_reference_case_run4.txt` | **`MaterialStreams.Add(已有的名字)` 不报错，返回已有的那一股**（读回 T 仍是 380 °C），`Names` 不重复，所以 Add 是幂等的（E5）。 空白 Case 里在 `EndBasisChange()` 之后建流程图对象。能流和物料流同一个类型，能流读热负荷用 `energy.HeatFlow.GetValue("kW")`。 新物流的组成向量长度等于流体包的组分数（示例 Case 是 7，G0 的模型是 5）。 计划假设：`MaterialStreams.Add(name)`、`EnergyStreams.Add(name)`。探针 E5 类型库（2026-10-08，未运行验证）：`Flowsheet.MaterialStreams`、`Flowsheet.EnergyStreams`（都是 `Streams`，有 `Add(name, Type)`）。 |
| H13 | 写入 T、P、流量 | 已确认 | 写：`stream.Temperature.SetValue(value, "C")`、`stream.Pressure.SetValue(value, "kPa")`、`stream.MolarFlow.SetValue(value, "kgmole/h")`；读：`GetValue(unit)`。单位字符串见 H29。写入后立即读回一致 | `spikes/e2_read_write.py`，2026-10-08，输出 `spikes/out/e2_read_write_run1.txt`、`e2_read_write_run2.txt` | 写入不校验取值（E5）：负的质量流量 -100 kg/h 写得进去并读回 -100；-300 °C 被拒（`E_INVALIDARG`，温度保持未知）；不认识的单位 `degC` 抛 `E_FAIL`。**校验必须在我们自己的代码里做。** 写入用时 0.02 秒。写入不认识的单位抛 `com_error`（`E_FAIL`，`-2147467259`），原值不变，不会静默写错。`.Value` 属性是 HYSYS 的内部单位（C、kPa、kgmole/s、kg/s），**不要用**，一律 `GetValue(unit)`、`SetValue(value, unit)`。 计划假设：`Temperature.SetValue(value, unit)` 等。计划状态：官方文档确认（V7.3 版）。探针 E2、E5 类型库（2026-10-08，未运行验证）：`RealVariable.SetValue(val: double, unit: VARIANT[opt])`、`GetValue(unit)`、`Value`；`ProcessStream` 的 `Temperature`/`TemperatureValue`、`Pressure`/`PressureValue`、`MolarFlow`/`MolarFlowValue`、`MassFlow`、`StdLiqVolFlow`。 |
| H14 | 写入组成 | 已确认 | `stream.ComponentMolarFraction.Values = (0.2703, 0.7297, 0, …)`（按流体包组分顺序的 8 元组，和为 1）；流量 `MassFlow.SetValue(10000.0, "kg/h")` 或 `MolarFlow.SetValue(3700.0, "kgmole/h")` | `spikes/build_reference_case.py` run3、run4，2026-10-08，输出 `spikes/out/build_reference_case_run4.txt`；`spikes/e5_stream.py` run3，2026-10-08，输出 `spikes/out/e5_stream_run3.txt` | **组成写入时被静默归一化**：写 (0.9, 0, 0, 0, 0) 或 (1.2, 0, 0, 0, 0) 读回都是 (1, 0, 0, 0, 0)，不报错；元组长度和组分数不一致抛 `E_INVALIDARG`。写入顺序没有要求：T、P、组成写完闪蒸就完成（气相分率已知，`MassFlow`、`MolarFlow` 仍未知），再写质量流量，摩尔流量、`StdLiqVolFlow`、`HeatFlow` 随之已知。新物流的 `VapourFractionValue` 在组成写入前读取抛 `E_FAIL`（`.Value`、`GetValue` 返回 -32767）。10000 kg/h 甲苯读回 108.5296 kgmole/h，与手算 108.53 一致。 空白 Case 里验证：写完 T、P、组成、流量立即闪蒸，读回 `VapourFractionValue`（1.0）、`MolarFlow`（10000 kg/h 甲苯读回 108.530 kgmole/h，3700 kgmole/h 读回 64683.45 kg/h）。 条件：在已求解的示例 Case 里新建的物流上，7 个组分，写的是摩尔分数且和为 1。向量顺序是流体包的组分顺序。写 T=25 °C、P=1000 kPa、F=100 kgmole/h 之后闪蒸立即完成：`VapourFractionValue` 0.9029，`MassFlow` 1624.0 kg/h，分组分摩尔流量 (90, 10, 0, ...)。空白 Case 里已重新验证（见上）。 计划假设：`ComponentMolarFraction.Values = [...]`。计划状态：读取有公开示例，写入待验证。探针 E5 类型库（2026-10-08，未运行验证）：`ProcessStream.ComponentMolarFraction`（`RealFlexVariable`：`Values`、`SetValues(val, unit)`、`GetValues(unit)`）和 `ComponentMolarFractionValue`。 |
| H15 | 新建反应器 | 已确认 | `reactor = flowsheet.Operations.Add("R-Conv", "ConversionReactorOp")` 返回 `ConversionReactor`；`EquilibriumReactorOp` 返回 `EquilibriumReactor`；`GibbsReactorOp` 返回 `GibbsReactor`。`reactor.TypeName` 读出全小写的 `conversionreactorop` 等 | `spikes/build_reference_case.py` run3、run4，2026-10-08，输出 `spikes/out/build_reference_case_run4.txt` | G0：转化反应器 `Operations.Add("CRV-100", "ConversionReactorOp")` 成功，一次建出并求解。 类型字符串用帮助文件里的写法（大小写如帮助）；全小写的 `TypeName` 形式没有试。三种反应器都新建成功。 E3 实测：转化反应器 `TypeName` 是 `conversionreactorop`，平衡 `equilibriumreactorop`，Gibbs 在参考 Case 里是 `gibbsreactorop`。 计划假设：`Operations.Add(name, typeName)`，三种反应器的 `typeName` 通过反向探测获得。探针 E3、E7 类型库（2026-10-08，未运行验证）：`Flowsheet.Operations(OperClassOrType[opt]).Add(name, Type)`。反应器接口：`ConversionReactor`、`EquilibriumReactor`、`GibbsReactor`，另有 `KineticReactor`、`PFReactor`、`YieldReactor`。`Type` 的取值（字符串还是枚举）待 E3。 帮助文件 `xhysys.chm`（`general/operation_types.htm`）列出 `Operations.Add` 能用的类型字符串，反应器是 `ConversionReactorOp`、`EquilibriumReactorOp`、`KineticReactorOP`、`GibbsReactorOp`、`ReactorOP`、`PFRReactorOp`（界面名依次为 Conversion Reactor、Equilibrium Reactor、Kinetic Reactor、Gibbs Energy Minimization Reactor、Reactor、Plug Flow Reactor），并说明"These types are used in the Add of the Operations"；示例 `Flowsheet.Operations.Add "Pump1", "PumpOp"`（`general/adding_an_object_to_a_flowsheet.htm`）。这是文档，没有运行过；运行时读回的 `TypeName` 是全小写。 |
| H16 | 反应器连接与配置（进出料、能流、反应集、压降、Gibbs 模式） | 已确认 | `reactor.Feeds.Add(feed)`（传物流对象）；`reactor.VapourProduct = vapour`；`reactor.LiquidProduct = liquid`；`reactor.EnergyStream = energy`；`reactor.ReactionSet = rset`；`reactor.PressureDrop.SetValue(0.0, "kPa")`；出口温度 `vapour.Temperature.SetValue(710.0, "C")`；Gibbs 的 `reactor.ReactorType` | `spikes/build_reference_case.py` run3、run4，2026-10-08，输出 `spikes/out/build_reference_case_run4.txt` | **G0 的连接顺序**：`Feeds.Add(进料)` → `VapourProduct = …` → `LiquidProduct = …` → `ReactionSet = …` → `PressureDrop.SetValue(0, "kPa")`。**压降新建时已经是规定值 0 kPa（`State` 1），可以不写**（E7b）。反应器要同时有进料、气相出料、液相出料和反应集才算规定完整，少任何一样流程图里该反应器都是 `UnderSpecified`（H19）。**反应集必须已经加入流体包**，否则 `ReactionSet = …` 抛 `E_INVALIDARG`；**反应集里的反应类型与反应器不匹配会弹模态对话框**（H23）。 三种反应器都用上面的写法建成、求解成功（流程图状态 14 个对象全是 OK）。**出口温度规定在气相出料物流上**；绝热反应器不接能流、不规定温度。没连反应集或能流时，读 `reactor.ReactionSet`、`reactor.EnergyStream` 抛 `com_error`。Gibbs 的 `ReactorType` 取值见 H31。绝热的 Gibbs 或平衡反应器、规定热负荷模式、多股进料没有试（0C）。 计划假设：无。计划状态：未知。探针 E7 至 E9 类型库（2026-10-08，未运行验证）：三种反应器共有：`Feeds`（`Attachments`，`Add(Item)`）、`VapourProduct`、`LiquidProduct`、`EnergyStream`（可写，`ProcessStream*`）、`PressureDropValue`（可写）、`ReactionSet`（可写）、`HeatFlowValue`（可写）。Gibbs 另有 `ReactorType`（`gr_NoReactions=0`、`gr_SpecdRxnsOnly=2`、`gr_GibbsRxnsOnly=3`）、`InertSpeciesValue`、`FractionSpecifiedValue`、`FixedSpecificationValue`。接口里没有出口温度成员。 **0C（E8、E9）补充**：热模式验证情况——平衡反应器：规定出口温度、绝热、规定热负荷都验证了；Gibbs 反应器：规定出口温度和绝热验证了，规定热负荷没有试；转化反应器：只验证了绝热（G0）。连接顺序用 `Feeds.Add` → `EnergyStream` → `VapourProduct` → `LiquidProduct` → `ReactionSet`，Gibbs 反应器先接出料后接能流会弹绝热警告（L24）；多股进料对每股调一次 `Feeds.Add`（L23）；同一股进料重复 `Feeds.Add` 抛 `E_FAIL`，同一股物流不能同时是两台反应器的出料（`E_INVALIDARG`）（L26）。 |
| H17 | 求解控制 | 已确认 | `solver = case.Solver`；`solver.CanSolve = False` 挂起，`solver.CanSolve = True` 释放；读 `solver.CanSolve`、`solver.IsSolving`、`solver.Mode`（0 为稳态） | `spikes/e2_read_write.py`，2026-10-08，输出 `spikes/out/e2_read_write_run1.txt`、`e2_read_write_run2.txt`；`spikes/e7_conversion_chain.py`（run2、hold），2026-10-08，输出 `spikes/out/e7_conversion_chain_run2.txt`、`e7_conversion_chain_hold.txt` | **建模期间要不要挂起（0B 问题）**：两种做法都成功，结果逐项相同。不挂起：每一步写入同步重算，建完时流程图 4 个对象全是 OK；挂起（`CanSolve = False`）：建完时 4 个对象全是 `NotSolved`、出料未知，释放这一句 0.01 秒返回，随后 4 个对象 OK、出料已知。小模型上两者耗时没有可测的差别（整条链 2 秒）。**判断"已经求解完成"**：`case.Solver.IsSolving` 为 False，`GetFlowsheetStatus(NotSolved)`、`UnderSpecified`、`Error` 都是 0（`OK` 的个数等于对象个数），出料变量 `IsKnown`。 **挂起有效：** `CanSolve=False` 时改进料流量，出料流量保持 475.36 kgmole/h 不变。**释放时同步求解：** `CanSolve=True` 这一句用 0.46 秒返回，返回后 `IsSolving` 已是 False，出料已更新到 523.26 kgmole/h，不需要轮询。`CanSolve` 为 True 时每次写入都会立刻重算（写进料压力、流量后出料立即变，热负荷 6558.8 kW 随进料温度变到 6544.7 kW）。 计划假设：`Solver.CanSolve`。计划状态：官方文档确认（V7.3 版）。探针 E2 类型库（2026-10-08，未运行验证）：`Solver.CanSolve`（可读写）、`IsSolving`、`Mode`；`SimulationCase.Solver`。 |
| H18 | 变量是否已知，是规定值还是计算值 | 已确认 | `variable.IsKnown`、`variable.State`、`variable.CanModify`：规定值 `State=1`、`CanModify=True`，计算值 `State=0`、`CanModify=False`，没有值时 `IsKnown=False` | `spikes/e2_read_write.py`、`spikes/e3_reverse_probe.py`，2026-10-08 | E3 补上了计算值：出料的 P 和流量 `State` 0、`CanModify` False，能流热负荷同。注意没有规定的变量 `State` 也是 1，判断"有没有值"只能靠 `IsKnown`。 实测：没有规定的变量 `IsKnown` 为 False；写入之后为 True。进料温度 `State` 为 1（vsSpecified）、`CanModify` 为 True。**注意：没有规定的变量 `State` 也是 1，所以判断"有没有值"只能靠 `IsKnown`，不能靠 `State`。** 计算出来的变量（出料）已在 E3 测过：`State` 0、`CanModify` False（见上）。 计划假设：`IsKnown`、`State`。计划状态：官方文档确认（V7.3 版）。探针 E2 类型库（2026-10-08，未运行验证）：`RealVariable.IsKnown`、`State`（`vsCalculated=0`、`vsSpecified=1`、`vsDefaultedValue=2`、`vsSpecifiedOutside=4`、`vsDefaultOutside=5`）、`CanModify`。 |
| H19 | 对象状态文本（未求解、欠规定等提示） | 部分确认 | `case.GetFlowsheetStatus(flag)` 返回该状态的对象个数，`case.GetFlowsheetObjectTypeAndName(flag)` 返回 `((类型, 名字), …)` 或 `None`；`flag` 为 `FlowSheetObjStatusFlag_enum`：OK=1、NotSolved=2、Warning=4、UnderSpecified=8、Error=16 | `spikes/build_reference_case.py`、`spikes/e9b_gibbs_type.py`，2026-10-08，输出 `build_reference_case_run4.txt`、`e9b_gibbs_type_run3.txt`；`spikes/e7b_unsolved_reasons.py` run3，2026-10-08，输出 `spikes/out/e7b_unsolved_reasons_run3.txt`；`spikes/e9b_gibbs_type.py` | **未求解的原因怎么读（E7b）**：流程图状态只能定位到对象和大类。进料、气相出料、液相出料、反应集四样里缺任何一样，反应器都是 `UnderSpecified`，两股出料是 `NotSolved`，状态相同；**要靠读反应器自己的成员区分缺哪样**：`Feeds.Names` 为空，`VapourProduct`、`LiquidProduct`、`ReactionSet` 没接时读取抛 `com_error`（`E_FAIL`）。进料流量没规定时，是进料物流、两股出料和反应器一起 `NotSolved`，反应器不是 `UnderSpecified`；原因要读进料物流的 `MassFlow.IsKnown`。逐步连接时（先建三股物流，再建反应器，依次接进料、气相出料、液相出料、反应集），反应器一直是 `UnderSpecified`，直到反应集挂上的那一步才变 OK。没有读到"哪个量没有规定"的文字说明。 全部求解后 14 个对象都是 OK，其余四种状态个数为 0（清单为 `None`）。故意把 Gibbs 反应器设成"Specify Equilibrium Reactions"又不挂反应集：`UnderSpecified` 列出 `('GibbsReactorOpObject', 'R-Gibbs')`，`NotSolved` 列出它的两股出料和能流。**只能定位到对象和大类，读不到"哪个量没有规定"**；原因要靠对照设置推断。 计划假设：无。计划状态：未知。探针 E7 |
| H20 | 读取结果（T、P、流量、组成、分组分流量、热负荷） | 已确认 | 物流同前；反应器按组分的进出量：`op.ComponentTotalIn.GetValues("kgmole/h")`、`ComponentTotalReacted`、`ComponentTotalOut`（Gibbs 是 `ComponentTotalFeed`、`ComponentTotalProduct`），组分顺序见 `op.ComponentName.Values`；`op.HeatFlow.GetValue("kW")`；转化率 `RxnPercentConversionValue`，平衡常数 `EqConstantValue`、`RxnExtentValue` | `spikes/build_reference_case.py` run3、run4，2026-10-08，输出 `spikes/out/build_reference_case_run4.txt` | G0：`vapour.ComponentMassFlow.GetValues("kg/h")` 读各组分质量流量（甲苯 5000.0、苯 2119.3、对二甲苯 691.3、间二甲苯 1497.9、邻二甲苯 691.3），与解析解相符；质量守恒相对误差 1.52e-05。 三种反应器的出料、热负荷、质量守恒都已读出并通过：转化反应器出口摩尔分率与期望值相差小于 1e-5；平衡和 Gibbs 反应器见"调用序列"。热负荷符号：**吸热为正**（平衡反应器 710 °C 为 +39989 kW）。 三种反应器都已实测。`ComponentTotal…` 的 `…Value` 属性是 kgmole/s，一律用 `GetValues("kgmole/h")`。 物流和热负荷已实测（转化反应器 Reformer 热负荷读出 6558.76 kW）。反应器自己的结果（分组分进出量、转化率、平衡常数）已由 E3 读出。 计划假设：`GetValue(unit)`、`ComponentMolarFraction.Values`。计划状态：基本读取有官方文档，分组分流量和热负荷待验证。探针 E7 类型库（2026-10-08，未运行验证）：反应器：`ComponentTotalInValue`、`ComponentTotalOutValue`、`ComponentTotalReactedValue`（转化、平衡）；`ComponentTotalFeedValue`、`ComponentTotalProductValue`（Gibbs）；`RxnPercentConversionValue`、`HeatFlowValue`。物流：`ComponentMolarFlow`、`ComponentMassFlow`。 |
| H21 | 固体碳组分及其在 Gibbs 反应器中的行为 | 不可行 | 组分库有碳：`Components.Add("Carbon")`，`IsSolid` 为 True，分子式 `C`，固体密度 1642 kg/m³，生成焓 0；含固体的进料能正常闪蒸（当作重液相）；未反应的碳从 Gibbs 反应器的**液相出料**离开。**但 Gibbs 反应器 + 库里的碳算出的平衡是错的**（见备注），所以按计划“不建反应集、纯自由能最小化”的做法对含固体碳的体系不可用 | `spikes/e4_basis.py` run4（库里有碳）；`spikes/e10_gibbs_carbon.py` run1、run2，`spikes/e10b_carbon_thermo.py` run1、run2，2026-10-08，输出 `spikes/out/e10_gibbs_carbon_run2.txt`、`e10b_carbon_thermo_run2.txt` | 进料 40 °C、4000 kPa、碳 0.710/水 0.290 摩尔分率，Gibbs 反应器 1400 °C：气相 CO 1035.0、CH4 517.5，氢气 0、水 0、CO2 0，液相出料碳 981.5 kgmole/h；参照 CO 1017、H2 981、CH4 22、H2O 11、CO2 3.5、碳 1491。**与温度无关**（1000、1200、1600 °C 组成完全相同）；连接顺序、挂起求解器、碳和水分两股进料都不改变结果；不含碳和碳全部气化的两个对照变体正常（水煤气变换表观平衡常数 0.298、0.299）。CO 收率 40.85% 和碳元素守恒恰好通过，是看起来合理但错的结果。**原因**（E10b）：`Carbon.EvaluateGibbs(298.15 K)` 是 +671285 kJ/kgmole（气态碳原子，+671.3 kJ/mol），不是石墨的 0，而 `HeatOfFormation` 是 0；`EvaluateVPsublim` 没有数据（-32767），`EvaluateAntoine` 无意义，临界性质为空，所以没有办法把气态碳的化学势修正成固体碳的。Gibbs 反应器把碳当成特别不稳定的物质，尽可能多地转成 CO 和 CH4。计划 §17.3 的两段式没有试，登记进度文件 D14。 计划假设：库组分 `Carbon`。 |
| H22 | 空值的表示方式 | 已确认 | 空值是 **-32767.0**：`variable.Value`、`GetValue(unit)`、组成向量里的每个元素都是 -32767.0；同时 `IsKnown` 为 False（组成是全 False 的元组） | `spikes/e2_read_write.py`，2026-10-08，输出 `spikes/out/e2_read_write_run1.txt`、`e2_read_write_run2.txt` | 对空值调 `GetValue("C")` 也返回 -32767.0，不做单位换算，所以不能靠数值是否合理判断，要先看 `IsKnown`。后面"结果是否存在"一律用 `IsKnown`，-32767.0 只作为兜底校验。 计划假设：约定的哨兵值。探针 E2 |
| H23 | 模态弹窗对 COM 调用的阻塞 | 部分确认 | 阻塞：`SimulationCases.Open` 在弹窗出现时不返回。检测：枚举 HYSYS 进程的顶层窗口，类名 `#32770` 的是对话框，读它的 `Static` 子控件得到文字（`spikes/_common.py` 的 `windows_of`、`child_texts`、`watch`）。关闭：对 OK 按钮发 `BM_CLICK`（`win32gui.PostMessage`） | `spikes/find_ref_case.py`，2026-10-08，输出 `spikes/out/find_ref_case_scan.txt` | 只见过一种弹窗：打开用到 Aspen Properties 的 Case（Green Ammonia Process）时的 "To use Aspen Properties in HYSYS, at least one databank should be installed..."。`BM_CLICK` 能关闭对话框；阻塞的调用在对话框关闭后能否返回没测到。计划假设：无。探针 E11 **第二种弹窗（0B，E7b）**：把平衡反应的反应集挂到转化反应器上，弹出模态对话框 "The reaction set Eq-Set is not the correct type to attach to reactor R-D6.  The reaction set will be unattached."，`ReactionSet = …` 一直不返回，点 OK 之后返回（没有报错），反应集没有挂上。**看门狗**：`spikes/_common.py` 的 `dialog_guard` 用一个后台线程每 0.5 秒枚举 HYSYS 进程的 `#32770` 窗口，记下 `Static` 文字，向 OK 按钮发 `BM_CLICK`，被卡住的 COM 调用随即返回（E7b run3）。**与"不用多线程"的架构不变量冲突，见进度文件的待决策 D12。** **0C 补充（L24、L26、L29）**：第三种弹窗——Gibbs 反应器先接出料后接能流时 "Since the energy stream is not supplied, the Gibbs Reactor operates at an adiabatic condition…"；重复的对象名 "Duplicate Object Name: … - Creating New Object …_2"（流体包；同名不同类型的操作，后者偶发地连续弹出并使进程崩溃）；PlayScript 的 "Could Not Find Target specified on Line N in File …"；写回坏 XML 之后 "Severe Error: You are low on memory"。**看门狗要处理不可见的对话框**（`dialog_guard(include_hidden=True)`）。关闭 Case、打开不存在或损坏的文件、另存都不弹窗，窗口可见和隐藏相同（L26）。D12 已批准在 `backends/hysys_com/` 里用后台线程处理弹窗。 |
| H24 | 降级通道：内部变量访问（BackDoor）、脚本回放（PlayScript） | 部分确认 | **PlayScript 可用**：脚本写成文件（纯 ASCII、CRLF），`app.PlayScript(绝对路径)` 回放；**要求目标 Case 的 `Visible = True`**（成为界面里的活动文档）；整个 HYSYS 窗口隐藏（`app.Visible = False`）时只要 `case.Visible = True` 也成立。写内部变量：`Specify "<对象路径>" ":<变量>.<ID>.<序号>" <数值>`，对象路径是 `UniqueID` 去掉 `文件!` 前缀的部分（例如 `FluidPkgMgr.300/RxnPackageManager.300/RxnSet.300(Conv-Set)`），变量写法同 `ProvideXMLForOperation(…, 8)` 导出的 `<Moniker>`（`:Index.400.0`）。建对象：`Specify "FlowSht.1" ":Selection.400" "ObjectType:ConversionReactorOpObject"` 加 `Message "FlowSht.1" "CreateAndView"`，建出 `CRV-100`（仿 `Template\\*.scp` 里加塔设备的 `CreateFromPFD` 写法没有效果）。**BackDoor 不可行**：任何 moniker 都解析不出真实变量 | `spikes/e13b_file_script.py` run2、run3、run4（PlayScript）；`spikes/e6c_rank_channels.py` run1 至 run4（BackDoor），2026-10-08，输出 `spikes/out/e13b_file_script_run2.txt`、`run4.txt`、`e6c_rank_channels_run4.txt` | **PlayScript 的坑**：Case 不可见时每条命令弹出 "Could Not Find Target specified on Line N in File …" 并且什么都不做；**失败时 `PlayScript` 不抛异常、返回 `None`**，所以回放之后必须读回，看门狗要记下弹窗；只验证了 `Specify`（数值）和 `Message … CreateAndView` 两类命令，`SpecifyText`、`AttachObject`、`Call` 没有试。安装目录 `Template\\*.scp` 是 HYSYS 自带的脚本，格式见 L29。**BackDoor**：`app.BackDoor` 可取到对象，`BackDoorRealVariable(moniker).Variable` 返回 `InternalRealVariable`（有 `GetValue`、`SetValue`、`IsKnown`），但试过的十几种 moniker（`UniqueID`、IMoniker 显示名、复合 IMoniker 对象，加上 `:Temperature.501.0`、`:Index.400.0` 等写法，连值已知的进料温度都读不出）全部读出空变量（`IsKnown` False、-32767.0），`SetValue` 抛 `E_FAIL`；解析不出来时不报错，包装的 `IsValid` 为 True，只能靠 `IsKnown` 发现。 计划假设：无。 |
| H25 | 组分库的枚举或检索（按名称、分子式查到规范名） | 部分确认 | 按名称：`Components.Add(name)`（大小写不敏感，返回规范名）。没有找到枚举或检索组分库的接口 | `spikes/e4_basis.py` run4，`spikes/e4b_property_package.py`，2026-10-08，输出 `spikes/out/e4_basis_run4.txt`、`e4b_property_package_run2.txt` | 分子式不能当名字用（`CH4`、`C7H8` 都失败）；类型库里 `Components`、`ComponentList(s)`、`HypoComponents` 都没有搜索方法。遇到新组分时，只能让 LLM 给出候选英文名，逐个 `Add` 试，失败的丢弃。 计划假设：无。计划状态：未知。探针 E4 |
| H26 | Case 导出为可读文本并重新导入 | 部分确认 | **导出可用，导入不能用来改设置。**导出：`case.ProvideXMLForCase(flags)`（flags 0 或 1）得到 6.5 或 6.1 MB 的字符串，`case.GetXMLForCase()` 0.47 MB，`case.ProvideXMLForOperation(name, flags)`（示例 2.4 MB，G0 的模型 0.35 MB）。`flags` 是位掩码（`XMLOptionFlags_enum`）：1 SpecsOnly、2 UseUserUnitSet、4 IncludeAttachments、8 SupplyMonikers（给变量节点加 `<Moniker>`）、16 TreatDefaultAsSpecs、32 SupplyCalcByInfo、64 HandleEmpties、128 OverlaySpecs、256 FPInteractionData、512 IncludeColumnEstimates、1024 MinCorrelationInfo、2048 NoBasisData、4096 MinStreamInfo、8192 CondenseData。**导入（E6b、E6c）：**`ApplyXMLForOperation(tag, flags, xml)` 要先去掉 XML 声明（字符串带 `encoding="windows-1252"` 的声明时 msxml 报 Invalid xml declaration）；flags 为 0、1、2、8、9、16 时返回 False，并且**弄坏 Case**（出口组成变成各 0.2）；flags 含 128（128、129、137、144）时返回 True，Case 完好，但**什么都不改**：操作自己的压降（0 → 50 kPa）、进料温度（380 → 400 °C）、反应集排序（0 → 0,1,2）写回后全都没变。Case 级 `ApplyXML` 同样什么都不改（返回 None）。 | `spikes/e3_reverse_probe.py`，2026-10-08，输出 `spikes/out/e3_reverse_probe_sample.txt`；`spikes/e6b_parallel_reactions.py` run1、`spikes/e6c_rank_channels.py` run4，输出 `spikes/out/e6b_parallel_reactions_run1.txt`、`e6c_rank_channels_run4.txt` | **`ProvideXMLForCase` 的 XML 里没有反应和反应集的定义**：'Stoich'、'rxnset'、'ReactionSet'、'LnK'、'Rxn-4' 出现 0 次，只有反应器上引用反应名的 `ConReactionInfo`。**但 `ProvideXMLForOperation` 的 XML 带 `Basis`，里面有这台反应器用到的反应和反应集（含排序）**，这是读排序的唯一位置（H32）。XML 路线不能创建反应，也不能写回改设置，在"创建反应的线索"里排在最后。**写回返回 True 不代表改了，写回之后必须读回。** 计划假设：无。计划状态：未知。探针 E13 类型库（2026-10-08）：`SimulationCase.GetXMLForCase()`、`ProvideXMLForCase(flags)`、`ApplyXML(flags, sXML)`、`ApplyXMLFromFile(flags, filePath)`、`ProvideXMLForOperation(tagName, flags)`、`ApplyXMLForOperation(tagName, flags, sXML)`。 **0C（E13b）补充**：Case 级 `ApplyXML(0 或 128, Case XML)` 导入空白 Case（Basis、反应、反应集已用 COM 建好）会建出反应器和物流并恢复进料的规定值，但**不恢复连接和反应集**（`Feeds.Names` 为空，读 `VapourProduct`、`ReactionSet` 抛 `E_FAIL`），状态是 3 个 NotSolved 加 1 个 UnderSpecified；操作级 `ApplyXMLForOperation` 对不存在的操作 `E_FAIL`，在没有建过反应的 Case 上还弹出 7 次 "Severe Error: You are low on memory" 并使进程崩溃（L29）。 |
| H27 | 同时运行多个实例；按进程号管理实例 | 已确认 | `Dispatch("HYSYS.Application.NewInstance")` 新开进程；连接前后的 `tasklist` 差集得到新进程号；`app.Quit()` 只结束该实例；`taskkill /PID <pid> /T /F` 强制结束 | `spikes/e1_connect.py` run3、run5、run7，2026-10-08 | 释放 COM 引用不会让实例退出（run6）。两个实例的窗口标题相同，只能靠进程号区分。非计划内的能力，Backend 的会话管理会用到 |
| H28 | 早绑定（gen_py 包装）与类型库 | 已确认 | `gencache.EnsureModule("{DFC1C58B-AE9F-11CF-8EB2-0020AF119B90}", 0, 3, 2)` 生成包装；`pythoncom.LoadRegTypeLib(guid, 3, 2, 0)` 读类型信息 | `spikes/e1_connect.py` run8、run9，2026-10-08 | 包装缓存在 `%TEMP%\gen_py\3.12`。属性名区分大小写；生成之后 `Dispatch` 也返回包装类。集合 `Item()` 返回 `IDispatch`，是否需要 `CastTo` 待 E3 |
| H29 | 单位字符串 | 已确认 | 温度 `C`、`K`、`F`、`R`；压力 `kPa`、`bar`、`psia`、`atm`、`MPa`；摩尔流量 `kgmole/h`、`lbmole/h`、`gmole/s`；质量流量 `kg/h`、`lb/hr`、`kg/s` | `spikes/e2_read_write.py` run1，2026-10-08 | 不认识的：`degC`、`kmol/h`、`t/h`、`foo`（`GetValue`、`SetValue` 都抛 `com_error` `E_FAIL`）。摩尔流量的单位是 `kgmole/h`，不是 `kmol/h`。体积流量、能量单位等没测 |
| H30 | 同时写入后的求解语义 | 已确认 | 见 H17：`CanSolve=True` 时每次写入同步重算，`CanSolve=False` 时不算，释放时同步算完 | `spikes/e2_read_write.py` run2，2026-10-08 | 没有未收敛状态的样本；不收敛时 `IsSolving`、对象状态文本怎么表现，留给 E7 |
| H31 | Gibbs 反应器的类型选项（`ReactorType`） | 已确认 | `reactor.ReactorType = 3`（默认，"Gibbs Reactions Only"，纯自由能最小化）；`0` = "NO Reactions (=Separator)"（不反应）；`2` = "Specify Equilibrium Reactions"（要挂反应集） | `spikes/e9b_gibbs_type.py` run3，2026-10-08 | 界面选项的原文来自 `Support\OdfRdfVariables.sdb`（`gibbrctr.ReactionTypeEnum`），数字靠行为对应：写 0，出料组成等于进料、流量不变；写 2 不挂反应集，反应器 `UnderSpecified`、出料未求解，挂上 `Eq-Set` 后与平衡反应器结果相同；写 3，纯 Gibbs，与是否挂反应集无关。**写 1 能写进去，但反应器变成未求解，不要用。**这里类型库枚举名（`gr_NoReactions=0`、`gr_SpecdRxnsOnly=2`、`gr_GibbsRxnsOnly=3`）与行为一致，和 `LnKSource` 的情况不同 |
| H32 | 同一基准组分的多个转化反应：并行还是依次（反应集的 Conversion Rankings） | 已确认 | **并行是默认，不用设**：同一个反应集里基准组分相同的多个转化反应，每个都按进料里的基准组分量乘自己的转化率计算（三个反应 12/26/12% → 出口甲苯 0.5000，`reactor.RxnPercentConversionValue` 读回 (12, 26, 12)）。**读排序**：`case.ProvideXMLForOperation(反应器名, 0)` 的 XML 里 `CaseDefinition/Basis/ReactionPackage/ReactionSetList/ReactionSet/ReactionRanks/ReactionRankSet/ReactionRank/Value`，按反应在反应集里的顺序，新建的反应集全是 0。**设排序：`PlayScript`**（H24）：`case.Visible = True` 之后回放每个反应一行的 `Specify "FluidPkgMgr.300/RxnPackageManager.300/RxnSet.300(Conv-Set)" ":Index.400.<序号>" <值>`，排序 (0,1,2) 出口甲苯 0.5731，(1,1,0) 为 0.5456 | `spikes/e6b_parallel_reactions.py` run1，`spikes/e6c_rank_channels.py` run1 至 run4，`spikes/e13b_file_script.py` run2、run4，2026-10-08，输出 `spikes/out/e6b_parallel_reactions_run1.txt`、`e6c_rank_channels_run4.txt`、`e13b_file_script_run2.txt`、`run4.txt` | **含义（两处证据一致）**：(1) 示例 Case Synthesis Gas Production 的 Combustor 反应集排序 (1, 1, 0)，指定转化率 35/65/100%，实际 18.09/33.60/48.31%，18.09/35 = 33.60/65 = 0.516868 = 1 − 0.483132；(2) 我们自己的三反应模型用 PlayScript 写排序：(0,1,2) 实际转化率 (12, 22.88, 7.814)，(1,1,0) 为 (10.56, 22.88, 12)，出口甲苯 0.5731 和 0.5456，与预测相同。即排序值最小的反应先算、排序相同的并行、后面的反应对剩下的基准组分按指定转化率算。界面名 Conversion Rankings，`Support\\rxnset.rdf` 里内部变量 `:Index.400.[]`（排序）、`:Boolean.400.[]`（是否用户指定）。**写不了的路**：类型库和 `GetIDsOfNames`（14 个候选名字）没有成员；`ActiveReactions.Add(name, 数)` 的第二个参数被忽略；XML 写回（H26）；BackDoor（H24）。整个 HYSYS 窗口隐藏、只让 Case 可见时 PlayScript 同样成立。Recipe 按 D13 保持默认并行，不设排序；需要依次时用 PlayScript，或两台转化反应器串联。 |

---

## 对象模型速查

三种反应器的类型名；反应、反应集、反应器对象的成员和取值含义。由阶段 0A 写，任务 6 和任务 9 完成后填。

**来源说明。** 标"类型库"的内容来自 `spikes/typelib_dump.py`（2026-10-08）：完整签名在 `spikes/out/typelib_reaction_api.txt`，全部成员名在 `spikes/out/typelib_members.txt`，枚举取值在 `spikes/out/typelib_enums.txt`。类型库只说明"接口里声明了什么"，**没有一条是运行验证过的**；能不能这样调用、取值是什么含义，要看 E3 和阶段 0B 的实测。

### 三种反应器的类型名

| 反应器 | 类型库里的接口 | `Operations.Add` 的类型字符串 |
|---|---|---|
| 转化反应器 | `ConversionReactor`（旧版本接口 `_ConversionReactor`、`_ConversionReactor2`） | `conversionreactorop`（`TypeName`，示例 Synthesis Gas Production 实测，界面名 `Conversion Reactor`）。未用 `Add` 验证 |
| 平衡反应器 | `EquilibriumReactor`（`_EquilibriumReactor`、`_EquilibriumReactor2`） | `equilibriumreactorop`（同上，界面名 `Equilibrium Reactor`）。未用 `Add` 验证 |
| Gibbs 反应器 | `GibbsReactor`（`_GibbsReactor`） | 推测是 `gibbsreactorop`，没有样本核实（示例里都没有 Gibbs 反应器），等用户的参考 Case |
| 其他（本项目暂不用，留给阶段 3B） | `KineticReactor`（`TypeName` 为 `kineticreactorop`，示例 CSTR - Dynamic Model 里是 CSTR）、`PFReactor`（`pfreactorop`，示例 Ammonia Synthesis）、`YieldReactor` | 见左 |

反应的 `TypeName`：转化 `conversionrxn`、平衡 `equilibriumrxn`；反应集 `rxnset`（E3 实测）。

三种反应器都不是组件类（coclass）：类型库里只有 22 个组件类（`Application`、`SimulationCase` 及其单实例、Plant/Process/Engine 变体）。反应器对象只能从 `Operations.Add` 或 `Operations.Item` 取得。

### 集合对象的通用形状

`Reactions`、`ReactionSets`、`FluidPackages`、`Components`、`Streams`、`Operations`、`Reactants`、`SimulationCases` 都是同一种形状：`Count`、`Item(index: VARIANT) -> IDispatch`、`Names`、`index(name)`、`Add(name: VARIANT[opt], Type: VARIANT[opt]) -> VARIANT`、`Remove(index)`、`RemoveAll()`。

- `Item` 的参数是 VARIANT（下标和名字大概都行，待测），返回类型是泛型 `IDispatch`。早绑定下取出的对象能否直接访问具体接口的成员、要不要 `CastTo`，要在 E3 里验证。
- `Add` 的两个参数都是可选的 VARIANT：`Type` 的取值（字符串、枚举数值、省略）和返回值是什么都不知道。`Attachments`（反应器的 `Feeds`）的 `Add` 只有一个参数 `Item: VARIANT`。
- `Flowsheet.Operations` 是带参数的属性：`Operations(OperClassOrType: VARIANT[opt])`。

### 反应对象

**实测（E3，示例 Synthesis Gas Production，2026-10-08）。**

- 取得：`case.BasisManager.ReactionPackageManager.Reactions`：`Count`（4）、`Names`、`Item(i)`（下标从 0 开始）。`Item(i)` 返回**具体类型** `ConversionReaction`、`EquilibriumReaction`，不需要 `CastTo`。
- `TypeName`：转化反应 `conversionrxn`（界面名 `Conversion`），平衡反应 `equilibriumrxn`（`Equilibrium`）。这很可能就是 `Reactions.Add(name, Type)` 的 `Type` 字符串，0B 验证。
- 计量系数：`Reactants` 集合：`Names`、`Item(j).Component.name`、`Item(j).StoichiometricCoefficientValue`；**负数是反应物，正数是产物**。Rxn-1 读出 Methane -1、H2O -1、CO 1、Hydrogen 3，即 CH4 + H2O → CO + 3 H2。向量形式 `ReactantStoichCoefValue`（元组，顺序同 `Reactants`）；`ReactantName.Values` 末尾多一个空字符串，是界面留给"新增一行"的空行。
- 基准组分 `BaseComponent`（`Component`，取 `.name`）。转化率 `Conversion`：**百分数**，40.0 表示 40%。`ConversionCoefficientsValue` 有三个数（C0、C1、C2），没用的是 -32767，第一个是常数项。
- 相态 `ReactionPhase`：0 即 `ptVapourPhase`（示例里全是 0）。反应热 `HeatOfReactionValue`（Rxn-1 读出 205310.0，单位没验证，应为 kJ/kgmole）。
- 平衡反应 Rxn-4（CO + H2O → CO2 + H2）：`LnKSource` 读出 **4**；`Basis` 读出 2（即 `rbPartialPressBasis`），`BasisUnits` 为 `atm`；`LnKEquationAParameter` 至 `DParameter` 为 -12.1076、5318.69、1.01205、0.000114369；`MinTemperatureValue` -273.15、`MaxTemperatureValue` 3000（单位 °C）；`TemperatureApproachValue` 0.0；`ActivateKTable` 为 True，`KEqValue` 是 35 个点的 K–T 表（4523.0 递减到 0.3843），`KCalculatedValue` 是按公式算的对照值；`AutoDetect` True，`LogBasis` False。`EquilibriumConstant`（固定 K）读取抛 `com_error`，因为当前来源不是固定 K。
- **`LnKSource` 的实际取值**（E6b 解决）：1 = Ln(K) 公式，2 = Gibbs 自由能（新建时的默认值），3 = 固定 K，4 = K–T 表；写 0 被忽略。类型库枚举 `LnKSourceEnum_enum` 的名字和数值与此对不上，不要用。示例里的 Rxn-4 读出 4，正是因为它用 K–T 表。

**`ConversionReaction`（类型库）。**

- 组成：`Reactants`（`Reactants` 集合，有 `Add`）、`ReactantName`、`ReactantStoichCoefValue`（可写，VARIANT 数组）、`ReactantMoleWeightValue`。`Reactant` 对象：`Component`（`Component*`）、`StoichiometricCoefficientValue`（可写，double）。
- 转化：`BaseComponent`（可写，`Component*`）、`Conversion`（double，可写；是百分数还是分率待查）、`ConversionCoefficientsValue`（可写，VARIANT）。
- 其他：`ReactionPhase`（可写，`PhaseType_enum`：ptVapourPhase=0、ptLiquidPhase=1、ptLiquid2Phase=2、ptCombinedLiquidPhase=3、ptSolidPhase=4、ptCombinedPhase=5、ptPolymerPhase=6、ptUnknownPhase=7）、`HeatOfReactionValue`、`BalanceStoichiometry()`、`BalanceErrorValue`。

**`EquilibriumReaction`（类型库）。** 与转化反应共有 `Reactants`、`ReactantStoichCoefValue`、`ReactionPhase`、`BalanceStoichiometry()`，没有 `BaseComponent` 和 `Conversion`。平衡特有：

- Keq 来源：`LnKSource`（可写，`LnKSourceEnum_enum`：eqrxn_Gibbs=0、eqrxn_LnKEquation=1、eqrxn_FixedK=2、eqrxn_Table=3、eqrxn_FixedExtent=4）。
- 固定 K：`EquilibriumConstant`（double，可写）。ln K 拟合式：`LnKEquationAParameter`、`BParameter`、`CParameter`、`DParameter`（可写）。
- 基准和范围：`Basis`（可写，`ReactionBasis_enum`：rbActivityBasis=1、rbPartialPressBasis=2、rbMolarConcBasis=3、rbMassConcBasis=4、rbMoleFracBasis=5、rbMassFracBasis=6、rbMolarityBasis=7、rbMolalityBasis=8）、`BasisUnits`、`MinTemperatureValue`、`MaxTemperatureValue`、`TemperatureApproachValue`。
- 读数：`KEqValue`、`KCalculatedValue`、`PercentErrorValue`、`R2Value`；其他：`AutoDetect`、`LogBasis`、`ActivateKTable`、`THighValue`、`TLowValue`。

其他反应类型接口：`KineticReaction`、`SimpleRateReaction`、`LHKineticReaction`、`ExtnKineticReaction`、`RYieldLumpOrDeLumpReaction`（动力学类，本项目暂不用）。`ReactionProperty_enum`（rpReactants=0、rpStoichiometricCoefficients=1、rpMinTemperature=2、rpMaxTemperature=3、rpReactionBasis=4、rpReactionPhase=5、rpBaseReactant=6、rpBasisConversion=7、rpRateConversion=8）可能是 `GetProperty(tag)` 一类接口用的枚举，用途待查。

### 反应集对象

**实测（E3，2026-10-08）。**

- 取得：`ReactionPackageManager.ReactionSets` 与 `fp.ReactionPackage.ReactionSets`（`fp = case.BasisManager.FluidPackages.Item(0)`）是同一批对象，示例里 3 个：`Reformer Rxn Set`、`Combustor Rxn Set`、`Shift Rxn Set`。`Item(i)` 返回 `ReactionSet`，`TypeName` 为 `rxnset`。
- **反应集与流体包的关联**：这三个集合都出现在 `fp.ReactionPackage.ReactionSets.Names` 里；`fp.ReactionPackage.FluidPackage.name` 读出 `Basis-1`。从集合反查流体包（`rset.ReactionPackage.FluidPackage.name`）读出空字符串，**不要用**。
- **集合成员**：`ActiveReactions.Names`（参加反应的）和 `InactiveReactions.Names`（在集合里但没启用的）。Reformer 集：Active `['Rxn-1', 'Rxn-2']`，Inactive `['Rxn-4']`，`Rxn-3` 根本不在这个集合里。所以"在不在集合里"和"启用不启用"是两层。
- `rset.Operations.Names`：用了这个集合的操作（反向引用），如 `Shift Rxn Set` 对应 `['Combustor Shift', 'Shift Reactor 1', 'Shift Reactor 2']`。
- `SolverMethod` 读出 -32767（未指定），`TraceLevel` 0。
- **转化反应的排序（界面里的 Conversion Rankings）没有 COM 成员**，只能在 `ProvideXMLForOperation` 的 XML 里读到；新建时全是 0（并行），COM 写不进去，`PlayScript` 可以，见 H24、H32。

**`ReactionSets` 和 `ReactionSet`（类型库）。**

- 取得方式有两条：`Case.BasisManager.ReactionPackageManager.ReactionSets`，或 `FluidPackage.ReactionPackage.ReactionSets`。
- `ReactionSet`：`AssociateFluidPackage(fluidPkg: FluidPackage*)`（把反应集挂到流体包）、`ActiveReactions` 和 `InactiveReactions`（都是 `Reactions` 集合；`ActiveReactions.Add(反应名)` 加反应，见 H11）、`Operations`（`Attachments`，用了这个反应集的操作）、`SolverMethod`（可写，`ReactionSetSolverMethodEnum_enum`：rs_RateIteration=0、rs_RateIntegration=1、rs_AutoSelected=2、rs_RBNewton1=3）、`TraceLevel`、`UsePreviousSolution` 等求解选项。
- `ReactionPackage`：`FluidPackage`、`ReactionSets`、`ReactionPackageManager`。`ReactionPackageManager`：`BasisManager`、`ReactionSets`、`Reactions`、`Components`。

### 反应器对象

**实测（E3，2026-10-08）。**

- **进料**：`op.Feeds`（`Attachments`）：`Count`、`Names`、`Item(i)` 返回 `ProcessStream`。**出料**：`op.VapourProduct`、`op.LiquidProduct`（`ProcessStream`）。**能流**：`op.EnergyStream`（`ProcessStream`），热负荷用 `.HeatFlow.GetValue("kW")` 读。**没有连接能流时，读 `op.EnergyStream` 抛 `com_error`（E_FAIL），不是返回 None**，判断有没有能流要用 try/except。
- **反应集**：`op.ReactionSet`（`ReactionSet`，取 `.name`）。**压降**：`op.PressureDrop.GetValue("kPa")`，`State` 为 1（规定值，示例里是 0）。**热负荷**：`op.HeatFlow.GetValue("kW")`，等于能流的热负荷，`State` 为 0、`CanModify` 为 False（计算值）。`VesselType` 读出 1，含义没验证。
- **出口温度规定在气相出料物流上。** 带能流的反应器（Reformer、Shift Reactor 1、Shift Reactor 2）：`VapourProduct.Temperature` 的 `State` 为 1、`CanModify` 为 True（规定值，分别是 926.67、454.44、398.89 °C），能流热负荷是计算值。没有能流的绝热反应器（Combustor、Combustor Shift）：`VapourProduct.Temperature` 是计算值（`State` 0，`CanModify` False）。液相出料的 T、P、流量永远是计算值。所以"出口温度 710 °C、带能流"的配置是：连上能流，对气相出料写 `Temperature.SetValue(710, "C")`。
- **计算值和规定值**：规定值 `State=1`、`CanModify=True`；计算值 `State=0`、`CanModify=False`（出料的 P 和流量、能流热负荷都是）。
- **结果**：转化反应器：`rxnName.Values`、`RxnBaseCmpName.Values`、`ConversionValue`（设置，百分数）、`RxnPercentConversionValue`（实际转化百分数）。平衡反应器：`rxnName.Values`、`EqConstantValue`、`RxnExtentValue`、`RxnPercentConversionValue`。两者都有 `HeatOfReactionValue`、`ComponentName.Values`，以及按组分的进出量 `ComponentTotalIn`、`ComponentTotalReacted`、`ComponentTotalOut`：**用 `.GetValues("kgmole/h")` 带单位读**，同名的 `…Value` 属性是 kgmole/s。`Reacted` 的符号：消耗为负，生成为正。
- **同一个基准组分的多个转化反应，转化率都是对进料里的基准组分算的（并行），不是对剩余量算。** Reformer：Rxn-1 40%、Rxn-2 30%，进料甲烷 90.72，反应掉 63.50 kgmole/h，正好是 70%，出口剩 27.22。若转化率之和超过 100%（Combustor 的 35、65、100），`RxnPercentConversionValue` 被缩放成 18.09、33.60、48.31（和为 100%），原因未深究。
- 平衡反应器的 `EquilibriumConstantParameterArrayValue` 读出一排 -32767，`EquilibriumFractionalApproachParameterArrayValue` 读取抛 `com_error`：示例里没有设这些。
- Gibbs 反应器见参考 Case 的 E3 补跑（`e3_reverse_probe_three.txt`）：`ReactorType` 默认 3；没连反应集时读 `ReactionSet` 抛 `com_error`；`ComponentName.Values` 末尾多一个空字符串；出口温度规定在气相出料上，与平衡反应器相同。

**三种反应器共有（类型库）。**

- 进料：`Feeds`（`Attachments`，`Add(Item)`）。出料：`VapourProduct`、`LiquidProduct`、`EnergyStream`，都是可写的 `ProcessStream*`（另有 `…Var` 形式的 `ObjectVariable`）。
- `ReactionSet`（可写，`ReactionSet*`）；压降 `PressureDropValue`（可写，double）；热负荷 `HeatFlowValue`（可写，double）；`VesselType`（`HeatCoolEnum_enum`：Cooling=0、Heating=1）；`Volume`、`LiquidVolume`、`LiquidLevel`；`FluidPackage`（可写）；`CreateFluid()`。
- **三种反应器的类型库接口里都没有"出口温度"成员。** 出口温度很可能规定在出料物流或能流上，待 E3 确认。

**各自特有。**

- 转化反应器：按反应分行的数组：`rxnName`、`RxnBaseCmpName`、`ConversionValue`（可写）、`RxnPercentConversionValue`、`HeatOfReactionValue`；按组分分行：`ComponentName`、`ComponentTotalInValue`、`ComponentTotalReactedValue`、`ComponentTotalOutValue`。
- 平衡反应器：`rxnName`、`RxnBaseCmpName`、`RxnPercentConversionValue`、`EqConstantValue`、`RxnExtentValue`、`HeatOfReactionValue`，以及同样的 `ComponentTotal…`；`EquilibriumConstantParameterArray`、`EquilibriumTemperatureApproachParameterArray`、`EquilibriumFractionalApproachParameterArray`（可写）。
- Gibbs 反应器：`ReactorType`（可写，`GibbsReactorType_enum`：gr_NoReactions=0、gr_SpecdRxnsOnly=2、gr_GibbsRxnsOnly=3）；`ComponentName`、`ComponentTotalFeedValue`、`ComponentTotalProductValue`；`InertSpeciesValue`、`FractionSpecifiedValue`、`FixedSpecificationValue`（可写）。三个值对应的界面选项见 H31（E9b）。

### Case、流体包、物流（类型库）

- `SimulationCase`：`Save`、`SaveAs`、`SaveAs2`、`SaveCopyAs`、`Close`、`IsDirty`、`Flowsheet`、`BasisManager`、`Solver`，以及 XML 一组（见"创建反应的线索"第 4 条）。`SimulationCases`：`Add`、`Open(name)`、`Close`、`Item`。
- `BasisManager`：`FluidPackages`、`StartBasisChange()`、`EndBasisChange()`、`IsChangingBasis`、`CanEndBasisChange`、`ReactionPackageManager`、`ComponentLists`。
- `FluidPackage`：`PropertyPackageName`（可写）、`Components`、`ReactionPackage`、`ComponentList`。`PropertyPackageType_enum` 里有 `ppkg_PR=5891`、`ppkg_SRK=5892` 等。`Component`：`IsSolid`、`IsHypothetical`、`Class`、`Formula`、`CAS_Number`。
- `Flowsheet`：`MaterialStreams`、`EnergyStreams`（都是 `Streams`）、`Operations`、`FluidPackage`。
- `ProcessStream`：`Temperature`/`TemperatureValue`、`Pressure`/`PressureValue`、`MolarFlow`/`MolarFlowValue`、`MassFlow`、`StdLiqVolFlow`、`VapourFractionValue`、`ComponentMolarFraction`/`ComponentMolarFractionValue`、`ComponentMolarFlow`、`ComponentMassFlow`、`ComponentMassFraction`、`HeatFlow`、`IsEnergyStream`、`FluidPackage`。
- 变量：`RealVariable`：`Value`、`SetValue(val, unit[opt])`、`GetValue(unit[opt])`、`IsKnown`、`State`（`VariableStatus_enum`：vsCalculated=0、vsSpecified=1、vsDefaultedValue=2、vsSpecifiedOutside=4、vsDefaultOutside=5）、`CanModify`、`Calculate(val, unit)`、`Erase()`。`RealFlexVariable` 是数组版：`Values`、`SetValues(val, unit)`、`GetValues(unit)`。
- `Solver`：`CanSolve`（可读写）、`IsSolving`、`Mode`（`SolverMode_enum`：sm_SteadyState=0、sm_Dynamic=1）。

---

## 创建反应的线索

类型库里看起来能用来创建反应、反应集、反应器的接口和方法，按可能性排序。这是阶段 0B 的起点。由阶段 0A 写。

**结果（2026-10-08，D11）：第 1、2 条已经用代码验证成功，不需要往下降级。** `Reactions.Add(name, "conversionrxn")` 等，`ReactionSets.Add(name)`，`ActiveReactions.Add(反应名)`，`AssociateFluidPackage(fp)` 都在 E6 里跑通，重开后保持；`Operations.Add(name, "…ReactorOp")` 在 E7 里验证。下面的表是 0A 结束时写的线索，保留作为探索过程的记录。0B、0C 为了设置反应集排序又试了第 4、5、6 条：XML 写回、BackDoor 走不通，**脚本回放（第 4 条 `PlayScript`）走通了**，见 H24、H26、H32。

**依据（写表时）：类型库（2026-10-08，`spikes/typelib_dump.py`）加 E3 的只读实测。创建本身（`Add`）当时没有运行过。** E3 补上了：`Item()` 取出的对象直接是具体类型（不需要 `CastTo`）；反应、反应集、反应器的 `TypeName`（`conversionrxn`、`equilibriumrxn`、`rxnset`、`conversionreactorop`、`equilibriumreactorop`）；反应集成员在 `ActiveReactions`；出口温度规定在气相出料物流上。

| 序 | 线索 | 依据 | 下一步 |
|---|---|---|---|
| 1 | **（已验证，E6）COM 直接创建（降级阶梯的 I1）**：`Case.BasisManager.ReactionPackageManager.Reactions.Add(name, Type)` 建反应；同一个管理器的 `ReactionSets.Add(name, Type)` 建反应集；`Flowsheet.Operations.Add(name, Type)` 建反应器 | 三个集合都有 `Add(name: VARIANT[opt], Type: VARIANT[opt]) -> VARIANT`，说明 HYSYS 把创建统一成这一种接口。设置路径是完整的：反应对象有可写的 `Reactants`、`BaseComponent`、`Conversion`、`LnKSource`；反应器有可写的 `ReactionSet`、`VapourProduct`、`LiquidProduct`、`EnergyStream`、`Feeds.Add` | 0B：先试 `Reactions.Add("R1", "conversionrxn")`（E3 读到的 `TypeName`），不行再试 `"Conversion"`（`VisibleTypeName`）、整数、省略；用 `conversionreactorop` 试 `Operations.Add`；读回 `Count`、`Names`。建反应要在 `StartBasisChange()` 之后。物流已经证实只给名字就能 `Add`（H12），先按这个模式试 |
| 2 | **（已验证，E6）反应集成员**：`ReactionSet.ActiveReactions.Add(反应名)`，再 `ReactionSet.AssociateFluidPackage(流体包)` | `ActiveReactions` 是 `Reactions` 集合，有 `Add`；`AssociateFluidPackage` 的签名明确 | 0B：试 `Add(反应名)`；不行就看 E3 里 GUI 建好的反应集的 `ActiveReactions.Names`，或查 `Support\rxnset.rdf` 里反应集成员的内部变量名 |
| 3 | **以 GUI 建好的 Case 为"标准答案"核对**（E3，已做了一半） | 示例已给出：`TypeName`、反应集成员的读法、出口温度的位置、`Reactants` 的符号约定、转化率是百分数。缺的是 Gibbs 和 Keq 来源为 Gibbs 自由能的平衡反应（`LnKSource` 数字对不上） | 用户的 `three_reactors.hsc` 到了之后，补跑 `e3_reverse_probe.py --case spikes/ref_cases/three_reactors.hsc --tag three` |
| 4 | **脚本回放**：`Application.PlayScript(ScriptFileName)`、`PlayScriptRelativeTo` | 类型库里有；脚本格式未知 | 只在 1 至 4 受阻时 |
| 5 | **XML 路线（E3 实测：不能创建反应）**：`SimulationCase.GetXMLForCase()`、`ProvideXMLForCase(flags)`、`ApplyXML(flags, sXML)`、`ApplyXMLFromFile(flags, path)`，以及按操作的 `ProvideXMLForOperation(tagName, flags)`、`ApplyXMLForOperation(tagName, flags, sXML)` | 类型库里有，E3 导出成功（6.5 MB）。但**导出的 XML 里没有反应和反应集的定义**（'Stoich'、'rxnset'、'LnK' 都是 0 次），所以不能靠它创建反应；最多用来改反应器的设置 | 0B 里 COM 创建受阻时，只可能用来配反应器，不必先试 |
| 6 | **内部变量通道（BackDoor）**：`Application.BackDoor(obj[opt])` 返回 `BackDoor`，有 `BackDoorVariable(moniker)`、`BackDoorRealVariable`、`BackDoorTextVariable`、`BackDoorVariables(monikers)`、`SendBackDoorMessage(message)`；安装目录的 `Support\*.rdf`、`*.sgxml`（`convrxn.rdf`、`equirxn.rdf`、`rxnset.rdf`、`rxnop.rdf`）给出内部变量名，`ExtSDK\hysys.hh` 可查签名 | 类型库里有；moniker 的写法要靠 rdf 文件和 E3 里读到的 `Moniker` 属性猜 | 只在 1 至 4 受阻时 |
| — | 暂不考虑 | `KineticReaction`、`SimpleRateReaction`、`LHKineticReaction`、`RYieldLumpOrDeLumpReaction` 是动力学类反应，三种目标反应器用不到 | 阶段 3B 才可能用 PFR、CSTR |

---

## 调用序列

每种反应器一小节，写"从空白 Case 到求解完成"的完整调用顺序，每一步都是实测通过的调用。

**说明。** 下面的内容来自 D11 参考 Case 的构建（`spikes/build_reference_case.py`，2026-10-08，连续运行两次，各组分摩尔流量的相对偏差为 0）。用户指示由助手自行创建参考 Case，所以 0A 提前跑通了 0B、0C 要做的创建链。转化反应器一节已经在阶段 0B 用四产物分数系数的模型重新验证（闸门 G0）；平衡反应器和 Gibbs 反应器两节仍按 0C 的提示词重新验证；还没有验证的项目在各小节末尾列出。所有调用都用早绑定（`gencache.EnsureDispatch`），属性名区分大小写，路径用长路径。

### 公共步骤：从空白 Case 到可以建反应器

1. **连接**：`app = win32com.client.gencache.EnsureDispatch("HYSYS.Application.NewInstance")`；记下新进程号；`app.Visible = True`（H1、H27）。
2. **新建 Case**：`case = app.SimulationCases.Add("name")`。新 Case 处在 Basis 修改状态（`manager = case.BasisManager`，`manager.IsChangingBasis` 为 True）（H3、H5）。
3. **组分列表**：`component_list = manager.ComponentLists.Add("CL-1")`；对每个组分 `component_list.Components.Add("Methane")`。名字用库里的规范名（H8，"组分规范名"一节）。
4. **流体包**：`package = manager.FluidPackages.Add("Basis-1")`；`package.ComponentList = component_list`；`package.PropertyPackageName = "pengrob"`（物性包的内部名，不是 `Peng-Robinson`）（H7）。此后 `manager.CanEndBasisChange` 为 True。
5. **反应**（要在第 7 步之前或之后都行）：`reactions = manager.ReactionPackageManager.Reactions`；`reaction = reactions.Add("Tol-Disp", "conversionrxn")`（平衡反应用 `"equilibriumrxn"`）；对每个组分 `reaction.Reactants.Add("Toluene").StoichiometricCoefficientValue = -2.0`（负为反应物，正为产物，分数系数可以）；转化反应再设 `reaction.BaseComponent = package.Components.Item("Toluene")`、`reaction.Conversion = 50.0`（百分数）；`reaction.ReactionPhase = 0`（气相）（H9、H10）。平衡反应的 Keq 来源默认就是 Gibbs 自由能（`LnKSource` 为 2），不用写。
6. **反应集**：`rset = manager.ReactionPackageManager.ReactionSets.Add("Conv-Set")`；对每个反应 `rset.ActiveReactions.Add("Tol-Disp")`；`rset.AssociateFluidPackage(package)`（挂到流体包，之后 `package.ReactionPackage.ReactionSets.Names` 才列出它）（H11）。
7. **结束 Basis**：`manager.EndBasisChange()`（`CanEndBasisChange` 为 False 时会抛 `E_FAIL`）。之后 `flowsheet = case.Flowsheet` 可用（H5）。
8. **进料物流**：`stream = flowsheet.MaterialStreams.Add("F-1")`；`stream.Temperature.SetValue(380.0, "C")`；`stream.Pressure.SetValue(2500.0, "kPa")`；`stream.ComponentMolarFraction.Values = (…)`（按流体包的组分顺序的摩尔分率元组，和为 1）；流量二选一：`stream.MassFlow.SetValue(10000.0, "kg/h")` 或 `stream.MolarFlow.SetValue(3700.0, "kgmole/h")`。写完立即闪蒸，读回 `VapourFractionValue`、`MolarFlow.GetValue("kgmole/h")` 核对（H12、H13、H14、H29）。
9. **出料物流和能流**：`vapour = flowsheet.MaterialStreams.Add("R-V")`，`liquid = flowsheet.MaterialStreams.Add("R-L")`；需要能流时 `energy = flowsheet.EnergyStreams.Add("Q-1")`（H12）。
10. **建反应器并连接**：见下面各小节。

### 转化反应器

接公共步骤的第 10 步。模型是 0B 闸门 G0 的甲苯歧化：2 甲苯 → 1 苯 + 0.24 对二甲苯 + 0.52 间二甲苯 + 0.24 邻二甲苯，基准组分甲苯，转化率 50%；纯甲苯 10000 kg/h，380 °C，2500 kPa；绝热，不接能流，压降 0。`spikes/e7_conversion_chain.py` 里每一步对应一个函数，Backend 照下面的顺序实现。**每一步都是第 1 级集成方式（COM 编程），没有手工步骤，也没有用到降级。**

| 步 | 调用 | 脚本函数 | 台账 |
|---|---|---|---|
| 1 | `app = gencache.EnsureDispatch("HYSYS.Application.NewInstance")`，记下新进程号；`case = app.SimulationCases.Add("name")` | `step_new_case` | H1、H3、H27 |
| 2 | 组分列表和 5 个库组分、流体包、`PropertyPackageName = "pengrob"`（公共步骤 3、4） | `step_basis` | H7、H8 |
| 3 | `reaction = reactions.Add("Tol-Disp", "conversionrxn")`；五个 `reaction.Reactants.Add(组分).StoichiometricCoefficientValue = -2.0 / 1.0 / 0.24 / 0.52 / 0.24`；`reaction.BaseComponent = package.Components.Item("Toluene")`；`reaction.Conversion = 50.0`；`reaction.ReactionPhase = 0` | `step_reaction` | H9 |
| 4 | `rset = ReactionSets.Add("Conv-Set")`；`rset.ActiveReactions.Add("Tol-Disp")`；`rset.AssociateFluidPackage(package)` | `step_reaction_set` | H11 |
| 5 | `manager.EndBasisChange()` | `step_end_basis` | H5 |
| 6 | 进料物流 `MaterialStreams.Add("Feed")`：`Temperature.SetValue(380.0, "C")`、`Pressure.SetValue(2500.0, "kPa")`、`ComponentMolarFraction.Values = (1, 0, 0, 0, 0)`、`MassFlow.SetValue(10000.0, "kg/h")` | `step_feed` | H12 至 H14 |
| 7 | 两股出料物流 `MaterialStreams.Add("Vap")`、`Add("Liq")` | `step_outlets` | H12 |
| 8 | `reactor = flowsheet.Operations.Add("CRV-100", "ConversionReactorOp")`；`reactor.Feeds.Add(feed)`；`reactor.VapourProduct = vapour`；`reactor.LiquidProduct = liquid`；`reactor.ReactionSet = rset`；`reactor.PressureDrop.SetValue(0.0, "kPa")`（新建时已经是规定值 0，写不写都行） | `step_reactor` | H15、H16 |
| 9 | 读结果：`vapour.Temperature.GetValue("C")`、`vapour.MolarFlow.GetValue("kgmole/h")`、`vapour.ComponentMolarFraction.Values`、`vapour.ComponentMolarFlow.GetValues("kgmole/h")`、`vapour.ComponentMassFlow.GetValues("kg/h")`、`liquid.MolarFlow.GetValue("kgmole/h")` | `read_results` | H17、H19、H20 |

**求解。**没有单独的"求解"调用：`case.Solver.CanSolve` 为 True（默认）时，上面每一步写入都同步重算，第 8 步最后一次写入返回时出料已经算好。**建模期间不需要挂起求解器**：挂起（`CanSolve = False`）再释放得到逐项相同的结果，释放这一句同步求解（0.01 秒）。判断"已经求解完成"：`case.Solver.IsSolving` 为 False，`case.GetFlowsheetStatus` 里 `NotSolved`、`UnderSpecified`、`Error` 的个数都是 0（`OK` 的个数等于对象个数，这个模型是 4：3 股物流加 1 台反应器），出料变量 `IsKnown`（H17、H19）。未求解时的原因读法见 H19（只能定位到对象；缺连接要读反应器的 `Feeds.Names`、`VapourProduct`、`LiquidProduct`、`ReactionSet`）。

**G0 的实测结果**（`spikes/out/e7_conversion_chain_run2.txt`，连续两次从空白 Case 建，每次一个新的 HYSYS 实例）：

| 组分 | 出口 kgmole/h | 摩尔分率 | 期望分率 | 偏差 | 出口 kg/h |
|---|---|---|---|---|---|
| 甲苯 | 54.265 | 0.5000 | 0.500 | 0.00000 | 5000.0 |
| 苯 | 27.132 | 0.2500 | 0.250 | 0.00000 | 2119.3 |
| 对二甲苯 | 6.512 | 0.0600 | 0.060 | 0.00000 | 691.3 |
| 间二甲苯 | 14.109 | 0.1300 | 0.130 | 0.00000 | 1497.9 |
| 邻二甲苯 | 6.512 | 0.0600 | 0.060 | 0.00000 | 691.3 |

进料 108.530 kgmole/h（解析值 108.530）；液相出口 0；出口温度 378.59 °C（与 380 °C 相差 1.41，要求 ≤ 10）；质量守恒相对误差 1.52e-05（要求 ≤ 1e-4）；两次运行各组分摩尔流量的相对偏差为 0（要求 ≤ 1e-4）。整条链的 COM 调用约 2 秒，新建 Case 1.5 秒，其余每步不到 0.2 秒。

**分数计量系数可用。**0.24、0.52、0.24 都能写进 `StoichiometricCoefficientValue` 并读回，求解后出料与解析解逐项相同，所以场景里的"一个反应、多个产物按比例分配"用**一个**转化反应即可，不需要拆成几个并行反应。注意 HYSYS 会在质量守恒检查时微调最后一个系数（H9：1.0 变 1.00005），读回比对要留 1e-3 的容差。

**同一基准组分的多个转化反应：默认并行；要依次进行，用 `PlayScript` 设排序。**把基准组分都是甲苯的三个转化反应（12%、26%、12%，各生成一种二甲苯）放进同一个反应集，什么排序都不设：出口甲苯摩尔分率 **0.5000**（`spikes/out/e6b_parallel_reactions_run1.txt`）。每个反应都按进料里的基准组分量计算（`reactor.RxnPercentConversionValue` 读回 12/26/12），三个转化率之和应当不超过 100%（超过时的行为没有试）。

- **排序是什么、在哪里读。**界面里叫 Conversion Rankings：反应集上每个转化反应一个排序值（`rxnset.rdf` 里是 `:Index.400.[]`）和“是否用户指定”（`:Boolean.400.[]`）。类型库和 `GetIDsOfNames` 里都没有对应成员。能读到的位置是操作的 XML：`case.ProvideXMLForOperation(反应器名, 0)` 里 `CaseDefinition/Basis/ReactionPackage/ReactionSetList/ReactionSet/ReactionRanks/ReactionRankSet/ReactionRank/Value`，按反应在反应集里的顺序；新建的反应集所有排序值都是 0。
- **排序值的含义（两处证据一致）：**(1) AspenTech 示例 Synthesis Gas Production 里 Combustor 的反应集排序 (1, 1, 0)，指定转化率 35/65/100%，实际起作用的转化率 18.09/33.60/48.31%，18.09/35 = 33.60/65 = 0.516868 = 1 − 0.483132（`spikes/out/e6c_rank_channels_run4.txt` 的 Q6）；(2) 我们自己的三反应模型用 `PlayScript` 写排序（`spikes/out/e13b_file_script_run2.txt`）：排序 (0,1,2) 出口甲苯 **0.5731**，实际转化率 (12, 22.88, 7.814)；排序 (1,1,0) 出口甲苯 **0.5456**，实际转化率 (10.56, 22.88, 12)，都和预测值相同。即**排序值最小的反应先算；排序相同的并行；后面的反应对剩下的基准组分按指定转化率算。**
- **怎么设“并行”：**不用设，新建的反应集全是 0，就是并行。
- **怎么设“依次”：**COM 成员、XML 写回、BackDoor 都写不了（H24、H26、H32），**`PlayScript` 可以**（E13b，H24）：`case.Visible = True` 之后（整个 HYSYS 窗口隐藏也行），把一行 `Specify "FluidPkgMgr.300/RxnPackageManager.300/RxnSet.300(Conv-Set)" ":Index.400.<序号>" <值>` 每个反应一行写进纯 ASCII、CRLF 的脚本文件，`app.PlayScript(绝对路径)` 回放，再读回排序和出口组成。`Case` 不可见时每行弹出 "Could Not Find Target" 而且什么都不改；脚本失败时 `PlayScript` 不抛异常，所以必须读回。
- **对 Recipe 的含义：**按 D13 保持默认并行，不设排序。需要“后一个反应对前一个剩下的算”时，可以用 `PlayScript` 设排序（或者两台转化反应器串联、合并成净反应）。

### 平衡反应器

接公共步骤的第 10 步（D11 的 R-Eq：带能流，出口温度规定在气相出料上）：

1. `reactor = flowsheet.Operations.Add("R-Eq", "EquilibriumReactorOp")`，返回 `EquilibriumReactor`，`TypeName` 为 `equilibriumreactorop`。
2. `reactor.Feeds.Add(feed)`；`reactor.VapourProduct = vapour`；`reactor.LiquidProduct = liquid`；`reactor.EnergyStream = energy`；`reactor.ReactionSet = eq_set`；`reactor.PressureDrop.SetValue(0.0, "kPa")`。
3. **规定出口温度**：`vapour.Temperature.SetValue(710.0, "C")`（规定在气相出料物流上，不在反应器上）；改成 600 °C 重新写一次即可，同步重算，再改回 710 °C 结果复现。
4. 读结果：同转化反应器；热负荷 `energy.HeatFlow.GetValue("kW")`（单位 kW，**吸热为正**；`State` 0、`CanModify` False，是计算值）（H20）。

D11 的实测结果（CH4 0.2703、H2O 0.7297，3700 kgmole/h，520 °C，1350 kPa，反应集 SMR + WGS，Keq 来源默认的 Gibbs 自由能）：

| 工况 | CH4 转化率 | 出口总流量 kgmole/h | 摩尔分率 CH4 / H2O / H2 / CO / CO2 | 与参照值的最大偏差 | 热负荷 kW |
|---|---|---|---|---|---|
| 710 °C | 54.0% | 4780.7 | 0.0962 / 0.3844 / 0.4064 / 0.0457 / 0.0673 | 0.0046 | +39989 |
| 600 °C | 30.3% | 4307.1 | 0.1617 / 0.4976 / 0.2702 / 0.0117 / 0.0588 | 0.0014 | +20160 |

参照值（理想气体平衡）：710 °C 为 0.094 / 0.381 / 0.411 / 0.047 / 0.067，约 4800 kmol/h；600 °C 约 4305 kmol/h。都在 0.02 的容差内；质量守恒相对误差都小于 2e-5。**0C（E8）重新验证和补充**（`spikes/e8_equilibrium_chain.py`，建模步骤函数在 `spikes/chain_kit.py`）：从空白 Case 建同一个模型，710 °C、600 °C 与参照值的最大偏差 0.0046、0.0014，通过；Keq 来源默认就是 Gibbs 自由能（`LnKSource` 2、`Basis` 1、`AutoDetect` True，不用写）；改出口温度同步重算，回到 710 °C 与第一次的摩尔分率差 3.9e-8。**三种热模式都验证了**：规定出口温度；绝热（不接能流，出口 422.63 °C 是计算值，`State` 0、`CanModify` False）；规定热负荷（给能流写 39989.2 kW、不规定出口温度，出口回到 710.00 °C；规定的热负荷 `State` 1、`CanModify` True）。**固定 K 验证了**：`reaction.Basis = 5`（摩尔分率基准）、`reaction.LnKSource = 3`、`reaction.EquilibriumConstant = K`，求解结果与 Gibbs 来源相同。**没有验证**：Ln(K) 公式和 K–T 表来源。把进料拆成多股在 Gibbs 反应器上验证过（见下），平衡反应器上没有试。

### Gibbs 反应器

接公共步骤的第 10 步（D11 的 R-Gibbs：不挂反应集，带能流，出口温度规定在气相出料上）：

1. `reactor = flowsheet.Operations.Add("R-Gibbs", "GibbsReactorOp")`，返回 `GibbsReactor`，`TypeName` 为 `gibbsreactorop`。
2. 连接同平衡反应器，**不设 `ReactionSet`**（没连反应集时读 `reactor.ReactionSet` 抛 `com_error`）。
3. `reactor.ReactorType` 新建时读出 3（"Gibbs Reactions Only"，纯自由能最小化），不用写。取值对应（E9b）：0 = "NO Reactions (=Separator)"（不反应，只做相平衡）；2 = "Specify Equilibrium Reactions"（只算指定的平衡反应，要挂反应集，否则流程图里该反应器是 `UnderSpecified`）；3 = "Gibbs Reactions Only"。**不要写 1**：写得进去，但反应器变成未求解。
4. 规定出口温度：`vapour.Temperature.SetValue(710.0, "C")`。
5. 读结果：同平衡反应器；按组分的进出量用 `reactor.ComponentTotalFeed.GetValues("kgmole/h")`、`ComponentTotalProduct.GetValues("kgmole/h")`。

D11 的实测结果：与平衡反应器的 710 °C 工况相比，各组分摩尔分率最大偏差 1e-5，热负荷 +39990 kW，600 °C 同样一致，和参照值的偏差同平衡反应器。**0C（E9、E10）验证和补充**（`spikes/e9_gibbs_gas.py`、`spikes/e10_gibbs_carbon.py`）：

- **连接顺序**：`Feeds.Add`（每股进料各调一次）→ `EnergyStream` → `VapourProduct` → `LiquidProduct`。先接出料后接能流时，含固体碳的体系会弹 "Since the energy stream is not supplied, the Gibbs Reactor operates at an adiabatic condition…" 的对话框，先接能流就不弹（L24）。
- **纯气相**（E9，不挂反应集，`ReactorType` 默认 3）：710 °C 与参照值最大偏差 0.0046，与同一个 Case 里的平衡反应器最大偏差 0.00001；**多股进料**（甲烷一股、水蒸气一股，各调一次 `Feeds.Add`）组成与单股进料相同；**绝热**（不接能流）直接求解，出口 422.63 °C 是计算值，与绝热平衡反应器相差 0.01 °C。规定热负荷在 Gibbs 反应器上没有试。
- **固体碳的五个问题（E10，L24、L25）：**
  1. **组分库里有碳吗，叫什么，当作什么相**：有，`Components.Add("Carbon")`，分子式 `C`，`IsSolid` 为 True，固体密度 1642 kg/m³，`HeatOfFormation` 为 0；在物流里当作**重液相**。
  2. **含固体的进料物流在 40 °C 能正常闪蒸吗**：能，所有量已知，`LiquidFraction` 1.0（`HeavyLiquidFraction` 1.0）；碳 0.710、水 0.290 的摩尔分率读回质量分率 0.6201、0.3799。
  3. **Gibbs 反应器让碳作为固体参与平衡吗**：**不，结果是错的**。出口与温度无关（1000 至 1600 °C 完全相同）：全部氧变成 CO、全部氢变成 CH4、氢气为 0（CO 1035.0、CH4 517.5、碳 981.5 kgmole/h；参照 CO 1017、H2 981、CH4 22、碳 1491）。原因：库里 `Carbon` 的 `EvaluateGibbs(298.15 K)` 是 +671.3 kJ/mol（气态碳原子），不是石墨的 0，升华蒸气压没有数据（L25）。
  4. **没反应掉的碳从哪股出料离开**：**液相出料**（重液相，100% 碳），981.5 kgmole/h，参照 1491，相差 34%。
  5. **碳元素是否守恒**：守恒（误差 0），但这个检查证明不了结果是对的；CO 收率 40.85% 落在 38% 至 42% 之内也是巧合（水限量，水全部变成了 CO）。
  四条通过条件：1 通过（巧合）、2 未通过、3 通过、4 未通过，**E10 不满足**。连接顺序、挂起求解器、碳和水分两股进料都不改变结果；不含碳、碳全部气化的两个对照变体正常，所以问题只出在固体碳上。D14 待决定（计划 §17.3 的两段式没有试）。

---

## 组分规范名

用到的每个组分在 HYSYS 组分库里的确切名字。阶段 0B、0C 填写。`Components.Add` 的参数大小写不敏感，下表是 `Add` 之后读回的规范名。分子式、`Water` 一类的俗名不被接受（H8）。

| 用途 | 规范名 | 来源（脚本、日期） |
|---|---|---|
| 甲烷 | `Methane` | `spikes/e4_basis.py` run4，2026-10-08：`Components.Add` 验证 |
| 水 | `H2O` | 同上 |
| 一氧化碳 | `CO` | 同上 |
| 二氧化碳 | `CO2` | 同上 |
| 氢气 | `Hydrogen` | 同上（别名 `H2` 也被接受） |
| 甲苯 | `Toluene` | 同上 |
| 苯 | `Benzene` | 同上 |
| 对二甲苯 | `p-Xylene` | 同上 |
| 间二甲苯 | `m-Xylene` | 同上 |
| 邻二甲苯 | `o-Xylene` | 同上 |
| 固体碳 | `Carbon` | 同上，`IsSolid` 为 True，分子式 `C` |
| 氮气 | `Nitrogen` | `spikes/e2_read_write.py`，2026-10-08：示例 Case 的组分清单，没有用 `Add` 验证 |
| 氧气 | `Oxygen` | 同上 |

---

## 鲁棒性观察

同名对象、进程中断、弹窗、保存重开。0A、0B、0C 各记一组观察，0C 的最系统。

**阶段 0A 的观察。**

- **弹窗会让 COM 调用一直不返回。** 打开用到 Aspen Properties 的 Case 时弹出模态对话框，`SimulationCases.Open` 卡住。用 Win32 枚举 HYSYS 进程的 `#32770` 窗口能读到文字和按钮，`BM_CLICK` 能关掉它（H23）。`_common.watch` 是现成的看门狗。
- **路径形式。** 8.3 短路径一律 `E_ACCESSDENIED`，必须用长路径（H2）。
- **实例复用。** `HYSYS.Application` 会接管已经运行的实例，重复运行脚本可能碰到上一次遗留的 Case；需要干净环境时用 `NewInstance`，按进程号管理（H27）。
- **退出。** 释放 COM 引用不会让实例退出；`Quit()` 有效且不弹窗；卡住时 `taskkill /PID /T /F` 有效（连接节）。
- **求解。** 写入是同步重算；挂起后释放同步求解完（H17）。
- **覆盖保存。** `SaveAs` 到已有文件不弹窗，静默覆盖并留下 `.bk0` 备份（H4）。
- **枚举写入不校验取值。** Gibbs 的 `ReactorType = 1` 写得进去，但反应器变成未求解（H31）；平衡反应的 `LnKSource = 0` 被静默忽略（H10）。所以写枚举之后一定要读回，并查流程图状态（H19）。
- **没连接的引用抛 `com_error`。** 读没接的 `EnergyStream`、`ReactionSet` 抛 `E_FAIL`，不是返回 None（H16）。

**阶段 0B 的观察。**

- **写回返回 True 不代表改了。** `ApplyXMLForOperation` 带 `opt_OverlaySpecs`(128) 时返回 True，Case 完好，但压降、进料温度、排序都没有变；不带时返回 False 并把出口组成弄成各 0.2（H26）。写入之后一定要读回比对。
- **BackDoor 解析不出 moniker 时不报错。** 返回有效的包装，变量 `IsKnown` 为 False、值 -32767.0，写入才抛 `E_FAIL`（H24）。
- **被静默忽略的写入。** `ActiveReactions.Add(name, 数)` 的第二个参数；`LnKSource = 0`（H10）。
- **新建 Case 的 `FullName`。** 在 HYSYS 进程的当前目录下（`C:\Windows\system32\name.hsc`），没保存之前不是一个可以依赖的路径（H3）。
- **一次运行一个新实例。** G0 连续两次各开一个新的 HYSYS 实例，每次从空白 Case 开始，结果逐项相同（H27）。同名对象、中途结束进程的行为留给 0C。

**阶段 0C 的观察（E8 至 E13，详见 L22 至 L29）。**

- **同名创建不能依赖 HYSYS 的行为**：Case、反应、反应集自动改名或再建一个；流体包弹窗并再建；反应物重复加一行；物流、能流、同类型操作返回已有对象；同名不同类型的操作弹窗，偶发地使进程崩溃（L26）。所以所有“确保存在”都先按 `Names` 查。
- **进程没了的表现**：调用之间 `com_error(-2147023174)`（RPC 服务器不可用），调用期间 `com_error(-2147023170)`（RPC 调用失败），之后每次调用立刻失败，不会卡住（L26）。
- **弹窗**：重复的对象名 "Duplicate Object Name: …"（流体包、同名不同类型的操作）；Gibbs 反应器没接能流时 "the Gibbs Reactor operates at an adiabatic condition…"（先接能流再接出料可避免，L24）；反应集类型与反应器不匹配（H23）；PlayScript 找不到目标 "Could Not Find Target specified on Line N in File …"（L29）；写回坏 XML 之后 "Severe Error: You are low on memory"（L29）。关闭 Case、打开不存在或损坏的文件、另存都不弹窗，窗口可见和隐藏一样。弹窗看门狗要处理不可见的对话框（L26；D12 已批准用线程）。
- **错误号不能望文生义**：打开不存在的文件和损坏的文件都是 `E_ACCESSDENIED`（`-2147024891`），和 8.3 短路径是同一个；`SaveAs` 到非法文件名是 .NET 异常 `0xE0434352`（`-532462766`）；`SaveAs` 到不存在的目录**不报错**，`FullName` 变了，文件没有写出（L26）。
- **返回 True 或 None 不代表成功**：`ApplyXMLForOperation` 带 128 返回 True 但什么都不改（H26）；`PlayScript` 失败时只弹窗、返回 `None`（H24）；BackDoor 解析不出 moniker 时返回有效的包装、变量为空（H24）。一律读回。
- **保存重开可靠**：求解状态和结果都保留，重开后可以直接改规定重新求解（L27）。
- **窗口隐藏不影响建模和求解**（L26）；但界面自动化和 `PlayScript` 需要 Case 可见（`case.Visible = True`，L28、L29）。

---

## 路线对照

主路线和备选路线的对比。阶段 0C 填写。

最小任务：在空白 Case 里加一台转化反应器。每条路线至少有一个实际运行的结果，证据见探索日志。耗时是 2026-10-08 在这台机器上的实测，不含 HYSYS 启动（约 12 至 18 秒）。

| 路线 | 是否可行 | 耗时 | 可重复性 | 结果能否由程序验证 | 证据 |
|---|---|---|---|---|---|
| 主路线：COM 编程 | 可行，全部步骤（Basis、反应、反应集、物流、反应器、连接、求解、读结果）都是第 1 级 | `Operations.Add` 0.07 秒；G0 整条链 2 秒 | 高：G0 连跑多次、每次新实例，摩尔流量相对偏差 0 | 能，每一步都读回 | L18（E7）、L22 至 L24 |
| 界面自动化（pywinauto UIA） | 加一台反应器可行：`case.Visible = True` 之后控件树 676 个元素，Model Palette 的按钮名字为空、自动化 ID 是操作类型名，双击 `ConversionReactor` 就建出 `CRV-100`；连接进出料、挂反应集、写计量系数没有试 | 约 7 秒（含固定等待 4.5 秒） | 中：2/2，但依赖桌面会话、窗口可见、Model Palette 打开和焦点 | 能：COM 读 `Operations.Names`、`TypeName` | L28 |
| 文件路线：XML 导出再导入 | 部分可行：Case 级 `ApplyXML` 能把供体的反应器和物流建到空白 Case 里并恢复进料规定，不恢复连接和反应集；反应和反应集不在 Case XML 里，要先用 COM 建；操作级 `ApplyXMLForOperation` 对不存在的操作 `E_FAIL`，个别情况下还弹 Severe Error 并使进程崩溃 | 导出 2.6 秒，导入 0.5 秒 | 中：flags 0、128 各 1 次，结果相同 | 能：COM 读回 | L29 |
| 脚本路线：`PlayScript` | 可行，要求 Case 可见：`Specify "FlowSht.1" ":Selection.400" "ObjectType:…"` 加 `Message "FlowSht.1" "CreateAndView"` 建出 `CRV-100`；还能写 COM 写不了的反应集排序（0.5731、0.5456，与预测一致）；脚本失败不抛异常，只弹窗 | 0.05 至 0.9 秒 | 中高：写排序 4/4 成功，建反应器 1 次成功（模板写法一次无效） | 能：读回；必须读回，因为失败时返回值也是 `None` | L29 |
| LLM 视觉操作（让模型像人一样操作界面） | **未试验**：本会话没有看屏幕和操作桌面应用的工具（只有浏览器窗格里的页面操作） | — | — | — | — |

**结论。**主路线 COM 在可行性、速度、可重复性、可验证性四项上都最好，选它的理由有实测依据，不是假设。界面自动化和 `PlayScript` 都不是“走不通”，它们的用处是补 COM 的缺口：`PlayScript` 已经补上了反应集排序，界面自动化可以作为再往后的最后手段。`PlayScript` 和 XML 导入都要事后读回，因为失败时不报错。

---

## 对工具契约的影响

实测结果要求对计划 §9.3 的工具做哪些调整。阶段 0C 填写。

依据：阶段 0A 至 0C 的全部探针（接口事实表 H1 至 H32、探索日志 L0 至 L29）。**只写建议，没有改 `docs/MASTER_PLAN.md`。**每条建议标一个状态：待确认（等用户答复）、已确认、已否决。用户确认之后，从阶段 1A 起以这一节里“已确认”的条目为准；需要用户确认的条目已登记进 `docs/progress.md` 的 D15。

**2026-10-08 用户答复：D15 全部按建议确认，D14 采用方案 A（两段式）。**下面 R1 至 R12 的状态已相应更新；一处补充：R4 的 `phase` 参数开放两个验证过的取值（气相、合并相），因为两段式第一台转化反应器的进料是碳水浆料（重液相），反应相要用合并相（E10d 用的就是转化反应的默认值）。

### 一、十三个工具逐个对照

| 工具 | 能否按计划实现 | 要改什么，为什么 |
|---|---|---|
| `session.connect` | 能 | `mode` 的 attach / launch 对应 ProgID：`HYSYS.Application` 接管已运行的实例，`HYSYS.Application.NewInstance` 总是新开进程（H1、H27）。建议 Harness 一律用 NewInstance、自己记进程号，attach 只留给调试。见 R1 |
| `session.restart` | 能 | `taskkill /PID <pid> /T /F` 后重新 NewInstance；E11 里中断之后新实例正常（L26）。没有要改的 |
| `case.ensure` | 能，要加检查 | 新建的 Case 路径在 HYSYS 进程的当前目录（`C:\\Windows\\system32\\名字.hsc`），没有保存之前不能当身份（H3）。`mode=new` 应当在 Add 之后立刻 `SaveAs(run 目录下的路径)`；`SimulationCases.Add` 同名**不会**返回已有的 Case，而是再建一个，Case 数加 1，所以“可重入”要靠先按 `FullName` 找已经打开的 Case（L26）。`Open` 之后 `app.ActiveDocument` 是 None，Backend 自己拿着返回的 Case 对象（H2）。见 R2 |
| `case.save` | 能，后置条件必须写死 | `SaveAs` 到**不存在的目录不报错**，`FullName` 变成那个路径但文件根本没有写出（E11）；文件名含非法字符抛 CLR 异常 `0xE0434352`。所以必须先建目录、检查文件名，并且按计划里“文件存在且非空”的后置条件读回。`SaveAs` 覆盖已有文件不弹窗，旁边留 `.bk0` 和 `.ads`（H4、L26） |
| `case.close` | 能 | `Close()` 不弹保存确认，改过没保存的也一样（E11） |
| `basis.ensure_thermo` | 能，范围收窄 | 新建的 Case 一开始就在 Basis 修改状态，组分列表、流体包、物性包设好之后要 `EndBasisChange()` 才有流程图；建议这个工具在末尾调 `EndBasisChange()`，后面的工具不用管 Basis 状态（H5）。物性包必须用**内部名** `pengrob`，界面名都被拒绝（H7），所以白名单要存“用户名 → 内部名”的映射，目前只验证过 PR。组分只有“按规范名 Add”一种办法，没有检索接口（H25）；`FluidPackages.Add` 同名**会弹窗并再建 Basis-2、Basis-3**（L26），所以要先查 `Names`。“流程图非空时改 Basis”没有验证，这个工具在 P0 只支持新 Case。见 R3 |
| `basis.ensure_reaction` | 能，要加检查，要改参数 | 类型字符串是 `conversionrxn` / `equilibriumrxn`（H9、H10）。`Reactions.Add` 同名**再建一个**（`Rxn-1` 变 `Rxn-2`），`Reactants.Add` 同名**重复加一行**（L26），所以“先查 `Names`、再决定新建或更新”是工具内部的事。分数计量系数可用，系数读回要留 1e-3 容差，计划里“平衡误差为 0”应当改成 `BalanceErrorValue` 小于容差（H9）。转化率是百分数。Keq 来源只验证了 Gibbs 自由能（默认）和固定 K（摩尔分率基准 `Basis = 5`）（L22），公式和表没有验证。`ReactionPhase` 默认值转化反应是 5（合并相）、平衡反应是 0（气相），G0 用的 0；液相反应没有验证。见 R4 |
| `basis.ensure_reaction_set` | 能 | `ActiveReactions.Add(名字)` 加成员，`AssociateFluidPackage(流体包)` 才算挂到流体包（H11）。同名再 Add 会自动改名为 `Set-1`（L26），要先查。计划里“成员类型与反应器类型兼容”的前置条件**确实需要**：平衡反应集挂到转化反应器会弹模态对话框、不报错、没挂上（H23）。Gibbs 纯自由能模式不用反应集 |
| `flowsheet.ensure_stream` | 能 | 写入顺序没有要求，写完 T、P、组成就闪蒸，再写流量（H12 至 H14）。HYSYS **不校验**取值：组成之和不是 1 会被静默归一化、负流量照收（H13、H14），所以计划里“组成和为 1、数值为规范单位”的参数校验是必须的，读回比对也是。摩尔流量单位是 `kgmole/h`（H29）。`MaterialStreams.Add` 和 `EnergyStreams.Add` 同名返回已有的那一股，天然幂等 |
| `flowsheet.ensure_reactor` | 能，要改参数，连接顺序有讲究 | 三种类型字符串 `ConversionReactorOp` / `EquilibriumReactorOp` / `GibbsReactorOp`（H15）。连接顺序：`Feeds.Add` → **`EnergyStream`** → `VapourProduct` → `LiquidProduct` → `ReactionSet`；Gibbs 反应器先接出料后接能流会弹“绝热不合适”的对话框（L24）。多股进料对每股调一次 `Feeds.Add`（L23）。同名 `Operations.Add`：同类型返回已有的，**同名不同类型会弹窗并让 HYSYS 进程崩溃**（L26），所以必须先查 `Operations.Names`，名字存在而类型不同时报 `E_CONFLICT`，**绝不调用 Add**。同一股物流不能同时是两台反应器的出料（`E_INVALIDARG`），同一股进料重复 `Feeds.Add` 抛 `E_FAIL`。热模式见第二节。见 R5 |
| `flowsheet.set_spec` | 能 | 出口温度写在**气相出料物流**的 `Temperature` 上，规定热负荷写能流的 `HeatFlow`，都是同步重算（H16、L22）。计划里“出口温度是工况变量、不在 `ensure_reactor` 里”与实测一致。变量白名单里要有“反应器气相出料的温度”和“能流的热负荷”两项 |
| `solver.solve` | 能，含义要改 | 没有单独的“求解”调用：`CanSolve` 为 True 时每次写入同步重算，写完就是解完的状态（H17）。所以这个工具实际是“检查”：`Solver.IsSolving` 为 False，`GetFlowsheetStatus` 里 `NotSolved`、`UnderSpecified`、`Error` 为 0，出料变量 `IsKnown`。COM 调用不能被中断，`timeout_s` 只能靠看门狗线程超时后按进程号结束来实现（D12 已批准）。建模期间挂起求解器不是必要的（G0 两种做法结果相同），建议默认不挂起。见 R6 |
| `model.read_snapshot` | 能 | 物流、能流、反应器的按组分进出量、转化率、平衡常数、流程图状态都能读（H18 至 H20）。未知量用 `IsKnown` 判断，不能靠数值（空值是 -32767.0，H22）。**读不到**：固体相的单独流量或分率（含固体的物流只能按“重液相”读，L24）；反应集排序只能在 XML 里读（H32） |

### 二、实测验证过的热模式和 Keq 来源（没有验证过的，后面的阶段不会使用）

| 反应器 | 规定出口温度 | 绝热（不接能流） | 规定热负荷 |
|---|---|---|---|
| 平衡反应器 | 已验证（L22，710 °C、600 °C） | 已验证（L22，出口 422.63 °C） | 已验证（L22，写 39989.2 kW 回到 710.00 °C） |
| Gibbs 反应器（纯气相） | 已验证（L23） | 已验证（L23，与平衡反应器 0.01 °C 之差） | **没有验证** |
| 转化反应器 | 已验证（L25 的 E10d：带能流，气相出料写 1400 °C，热负荷 85.76 MW） | 已验证（G0） | **没有验证** |

Keq 来源：Gibbs 自由能（默认）已验证；固定 K（摩尔分率基准，`LnKSource = 3`、`Basis = 5`）已验证；Ln(K) 公式、K–T 表**没有验证**。三个考核场景只用到“规定出口温度”（场景 1 的平衡反应器、场景 3 的 Gibbs 反应器）和“绝热”（场景 2 的转化反应器），都在已验证的范围里。

### 三、建议清单

| 编号 | 建议 | 原因 | 状态 |
|---|---|---|---|
| R1 | `session.connect` 一律 `NewInstance`、自己记进程号；`mode=attach` 只用于调试 | 重启和结束都按进程号，不误伤别的实例（H27）；接管已有实例可能碰到上一次遗留的 Case | 已确认（D15，用户 2026-10-08） |
| R2 | `case.ensure` 的 `mode=new`：Add 之后立刻 `SaveAs(run 目录下的路径)`；可重入靠按 `FullName` 找已打开的 Case，不靠 `Add` | `Add` 同名再建一个 Case；新 Case 的路径在 `system32` | 已确认（D15，用户 2026-10-08） |
| R3 | `basis.ensure_thermo` 在末尾调 `EndBasisChange()`；P0 只支持新 Case；物性包白名单存内部名（目前只有 `pengrob`） | H5、H7；流程图非空时改 Basis 没有验证 | 已确认（D15，用户 2026-10-08） |
| R4 | `basis.ensure_reaction` 的读回容差 1e-3；“平衡误差为 0”改为 `BalanceErrorValue` 在容差内；Keq 来源枚举只开放“Gibbs 自由能”“固定 K”两项；加一个 `phase` 参数，默认气相，液相反应暂不开放 | H9、H10、L22；`ReactionPhase` 对转化反应的影响没有验证 | 已确认（D15，用户 2026-10-08） |
| R5 | `flowsheet.ensure_reactor`：所有创建调用前先按名字查，**同名不同类型报 `E_CONFLICT` 且不调用 Add**；连接顺序固定为进料、能流、出料、反应集；热模式枚举只开放第二节“已验证”的组合；每个出料物流只能属于一台反应器 | 同名不同类型会弹窗并使进程崩溃（L26）；Gibbs 先接出料后接能流会弹窗（L24） | 已确认（D15，用户 2026-10-08） |
| R6 | `solver.solve` 改为“检查求解完成”，默认不挂起求解器；`timeout_s` 由看门狗线程实现；`session` 层把 `com_error` 的 `-2147023174`（RPC 服务器不可用）和 `-2147023170`（RPC 调用失败）都映射成 `E_COM_DISCONNECTED` | H17、G0；E11 中断实验里这两个错误号是进程被结束之后的全部表现（L26） | 已确认（D15，用户 2026-10-08） |
| R7 | 所有创建和写入工具的“幂等”都写成“先查再改”：`Names` 里有就复用或更新，没有才创建；写入之后一律读回 | 同名创建在不同集合里的行为各不相同（自动改名、弹窗、返回已有、重复加行、崩溃），靠 HYSYS 自己的行为无法统一（L26） | 已确认（D15，用户 2026-10-08） |
| R8 | 弹窗看门狗放进 `backends/hysys_com/`：后台线程只调 Win32，枚举进程的 `#32770` 窗口（含不可见的），读文字、点确定；文字白名单见 H23 | D12 已批准；E11 证明可见和隐藏窗口下都能用 | 已确认（D12） |
| R9 | 路径和文件名在工具入口校验（目录存在、文件名合法、长路径），`Open`/`SaveAs` 之后读回路径和文件 | `SaveAs` 到不存在的目录静默“成功”，`Open` 不存在或损坏的文件报 `E_ACCESSDENIED`（和 8.3 短路径同一个错误号，不代表权限问题）（L26） | 已确认（D15，用户 2026-10-08） |
| R10 | 反应集排序不进工具契约：Recipe 不设排序，同一基准组分的多个转化反应靠默认的并行；需要依次时在 Backend 内部用 `PlayScript` 设排序（要求 `case.Visible = True`，写完读回） | H32、H24、D13 | 已确认（D13） |
| R11 | `gibbs` Recipe 遇到含固体碳的体系时不能直接用 Gibbs 反应器 + 库里的碳，两段式或别的做法等 D14 的决定 | L24、L25 | 已确认（D14 选方案 A：两段式，用户 2026-10-08） |
| R12 | `PlayScript` 只作为 Backend 内部的第二级通道，P0 不使用：当前只有设反应集排序这一个用途，并且按 D13 不启用 | H24、L29；脚本失败不抛异常、要求 Case 可见，只验证了 `Specify` 数值和 `Message … CreateAndView` 两类命令 | 已确认（D15，用户 2026-10-08） |

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

### L4 类型库导出（2026-10-08）

- **目的**：回答"对象模型里有什么"：三种反应器、反应、反应集对应哪些接口；哪些集合有 `Add`；有没有降级通道；早绑定能不能用。
- **做法**：`spikes/typelib_dump.py`：`gencache.EnsureModule` 生成早绑定包装；`pythoncom.LoadRegTypeLib` 读类型信息，列出每个接口的成员签名（参数名、类型、可选标记）；对十个关键词检索；用生成的包装类核对几个关键接口。
- **结果**：
  - 类型库共 1140 个类型：726 个 dispatch 接口、377 个枚举、22 个组件类、12 个 interface、1 个 record、2 个别名。
  - 有 `Add` 成员的接口 42 个。大多数是 `Add(name: VARIANT[opt], Type: VARIANT[opt]) -> VARIANT`：`Components`、`ReactionSets`、`FluidPackages`、`Reactions`、`Streams`、`Operations`、`SimulationCases`、`Reactants` 等。
  - 关键词命中行数：Reaction 189、ReactionSet 37、Equilibrium 91、Conversion 200、Gibbs 80、Reactor 21、Add 138、BackDoor 41、XML 122、Script 113。
  - 三种反应器是 dispatch 接口 `ConversionReactor`、`EquilibriumReactor`、`GibbsReactor`，不是组件类；另有 `KineticReactor`、`PFReactor`、`YieldReactor`。
  - 降级通道在类型库里都有：`SimulationCase` 的 XML 一组，`Application.PlayScript`，`Application.BackDoor`。
  - 包装生成 2 至 4 秒，含 758 个类；`ReactionSets`、`Reactions`、`Operations`、`FluidPackages`、`SimulationCases` 的包装类都有 `Add`。
- **走过的弯路**：第一版把全部接口的完整签名写进 `typelib_members.txt`，2.0 MB，超过 1 MB 的提交上限，原因是 533 个接口各自重复了十几个基础成员。先试"把重复成员抽成公共组"，仍有 1.6 MB。最后改成：成员文件只写成员名（629 KB）；完整签名只写反应相关的 111 个接口（`typelib_reaction_api.txt`，212 KB，省略基础成员）和关键词命中（`typelib_hits.txt`，74 KB）。第一版检索结果的显示也漏看了：我按"不以下划线开头"过滤了命中行，把 `_SimulationCase`、`_Application` 上的 XML 和 PlayScript 都过滤掉了，重新按带下划线的接口查才发现。
- **结论**：创建反应、反应集、反应器的入口都在类型库里，设置路径完整，但没有一条运行验证过，所以 H9 至 H11、H15、H16 仍是"未测试"，备注里写了类型库层面的线索。H24、H26 的入口也在类型库里。"对象模型速查"和"创建反应的线索"两节已按类型库填写。
- **脚本与输出**：`spikes/typelib_dump.py`；`spikes/out/typelib_dump.txt`、`typelib_members.txt`、`typelib_reaction_api.txt`、`typelib_hits.txt`、`typelib_enums.txt`。

### L5 任务 7：在自带示例里找含反应器的 Case（2026-10-08）

- **目的**：反向探测需要一个含三种反应器的 Case，先看 HYSYS 自带的示例里有没有。顺带第一次用 COM 打开 Case，看对象的样子。
- **做法**：`spikes/find_ref_case.py`：按文件名挑候选，复制到临时目录，用 `NewInstance` 新开的实例 `SimulationCases.Open`，枚举 `Flowsheet.Operations`（含子流程图）的名字和 `TypeName`，不保存，`Close()`。第一遍只看 `Synthesis Gas Production`（输出 `find_ref_case_synthesis_gas.txt`），第二遍看其余五个（输出 `find_ref_case_scan.txt`）。
- **结果**：

| 示例 | `Open` 用时 | 反应器 |
|---|---|---|
| `Synthesis Gas Production` | 2.5 秒 | 转化反应器 2 台（`Reformer`、`Combustor`，`TypeName` 为 `conversionreactorop`），平衡反应器 3 台（`Combustor Shift`、`Shift Reactor 1`、`Shift Reactor 2`，`equilibriumreactorop`） |
| `Ammonia Synthesis` | 2.9 秒 | PFR 3 台，`pfreactorop` |
| `Ethanol Dehydration` | 1.3 秒 | 没有 |
| `CSTR - Dynamic Model` | 1.1 秒 | 动态 CSTR 1 台，`kineticreactorop` |
| `Toluene_Disproportionation_Example` | 15.8 秒 | 只有 1 个单元操作，`mbreactorbed`（分子级的炼油反应器，不是三种之一） |
| `Ethanol Plant` | 1.4 秒 | 没有 |
| `Green Ammonia Process` | 卡住 | 出现模态弹窗，见下 |

  - **没有一个示例含 Gibbs 反应器。** 所以需要用户手工建参考 Case（`spikes/ref_cases/three_reactors.hsc`）；`Synthesis Gas Production` 先拿来做转化和平衡反应器的反向探测。
  - `Open` 返回的对象类型直接是 `gen_py` 的 `_SimulationCase`；`Flowsheet.Operations.Item(i)` 返回的已经是具体类型：`ConversionReactor`、`EquilibriumReactor`、`PFReactor`、`SetOp`、`AdjustOp`、`SpreadsheetOp` 等。**早绑定下不需要 `CastTo`**（虽然类型库里 `Item` 的返回类型写的是 `IDispatch`，pywin32 在运行时按对象自己的类型信息选了具体的包装类）。
  - `Item(i)` 的下标从 0 开始；`Operations.Names` 给出名字列表，`Count` 与之相符。
  - 单元操作的 `TypeName` 字符串：`conversionreactorop`、`equilibriumreactorop`、`pfreactorop`、`kineticreactorop`；其他见输出，如 `valveop`、`mixerop`、`flashtank`、`coolerop`、`heatexop`、`teeop`、`recycle`、`compressor`、`adjust`、`setop`。Gibbs 反应器的字符串推测是 `gibbsreactorop`，没有样本核实。
  - `VisibleTypeName` 是界面上的名字：`Conversion Reactor`、`Equilibrium Reactor`。
  - `app.ActiveDocument` 在 `Open` 之后仍是 `None`（`NewInstance`，窗口可见）。要不要 `Activate()`，E2 里看。
  - **弹窗阻塞（H23）。** 打开 `Green Ammonia Process` 时出现模态对话框：标题 `Aspen HYSYS`，类名 `#32770`，文字 "To use Aspen Properties in HYSYS, at least one databank should be installed and registered through Aspen Properties database configuration tool"，一个 OK 按钮。`SimulationCases.Open` 一直不返回。`_common.watch` 在 45 秒后打印了这个窗口和文字；用 Win32 的 `BM_CLICK` 点 OK 按钮，对话框随即关闭。阻塞的 COM 调用在对话框关闭后能否返回没有测到（脚本已被外层超时杀掉，实例按进程号 `taskkill`）。**这台机器没有注册 Aspen Properties 的数据库，凡是用到 Aspen Properties 的 Case 都会遇到它，所以我们的流体包只能用 HYSYS 自带的物性包（Peng-Robinson）。**
  - **走过的弯路：第一次 `Open` 失败。** `com_error -2147352567 ... -2147024891`（`E_ACCESSDENIED`）。当时副本在 `C:\Users\AZUREU~1\AppData\Local\Temp\...`（8.3 短路径），用 `shutil.copy2` 复制；改成 `shutil.copyfile` 加长路径（`Path.resolve()`）之后成功。到底是短路径还是别的原因，同时改了两处，没有分开验证，E2 里单独验证。
- **结论**：H23 升为部分确认；三种反应器里转化、平衡的 `TypeName` 已有实测；Gibbs 缺参考 Case。`Item()` 不需要 `CastTo`，写进"绑定方式的结论"。
- **脚本与输出**：`spikes/find_ref_case.py`；`spikes/out/find_ref_case_synthesis_gas.txt`、`find_ref_case_scan.txt`。

### L6 E2：读写已有 Case（2026-10-08）

- **目的**：弄清变量怎么读、怎么写、单位怎么指定、求解器怎么控制、空值是什么；顺带验证 8.3 短路径是不是 `Open` 失败的原因。
- **做法**：`spikes/e2_read_write.py`：复制示例 Synthesis Gas Production 到临时目录，用 `NewInstance` 打开；读流体包、读 Reformer 的进料 `Natural Gas`（T 371.1 °C、P 3447.4 kPa、90.72 kgmole/h，纯甲烷）和出料 `Combustor Feed`；写 T、P、流量并读回；挂起和释放求解器；临时加一股没有规定的物流 `probe` 读空值，再给它写组成、T、P、流量，最后删掉。不保存，按进程号结束实例。运行两次：run1 发现第一版的求解器测试设计得不好（只改了进料温度，而出料温度是规定值，看不出差别），run2 改成改进料流量，并加了热负荷和组成写入。
- **结果**：
  - **Q0 短路径**：同一个副本、同一种复制方式，目录是短名、或目录和文件名都是短名，`Open` 都抛 `E_ACCESSDENIED`（`-2147024891`）；长路径成功。**8.3 短路径就是原因。**
  - Q1：见 H6。物性包名读出 `PengRobinson`，组分 `Methane`、`H2O`、`CO`、`CO2`、`Hydrogen`、`Nitrogen`、`Oxygen`。
  - Q2：见 H13、H20、H29。`.Value` 是内部单位（T 为 °C、P 为 kPa、流量为 kgmole/s 和 kg/s），不能直接当 `kgmole/h` 用。
  - Q3：写入用时 0.02 秒，读回一致，不认识的单位抛错、原值不变。**自动重算**：写进料压力和流量后，出料压力、流量立即更新；写进料温度后，出料温度不变（是规定值 926.67 °C），但反应器热负荷从 6558.76 kW 变到 6544.70 kW。
  - Q4：见 H17。挂起时出料不变，释放这一句同步求解（0.46 秒），返回后即可读新值。
  - Q5：见 H18。进料和出料的温度 `IsKnown` 都是 True、`State` 都是 1（出料温度是规定值：**转化反应器的出口温度是规定在出料物流上的**）；没有规定的物流 `IsKnown` 是 False。
  - Q6：见 H22，空值是 -32767.0。
  - 新物流：`MaterialStreams.Add("probe")` 只给名字就成功，返回 `ProcessStream`；组成、T、P、流量写完后闪蒸立即完成（见 H14）。
- **结论**：H2、H6、H13、H17、H22 升为已确认；H4、H12、H14、H18、H20 升为部分确认；新增 H29、H30。其中 H2、H6、H13、H17、H18、H22 是阶段 0A 完成标准要求的项目。
- **脚本与输出**：`spikes/e2_read_write.py`；`spikes/out/e2_read_write_run1.txt`、`e2_read_write_run2.txt`。

### L7 E2b：有打开的 Case 时 Quit 和 Close 会不会弹窗（2026-10-08）

- **目的**：E1 遗留的问题：HYSYS 里有 Case 时 `Quit()` 会不会弹出"是否保存"并卡住。
- **做法**：`spikes/e2b_quit_with_case.py`：三种情况各开一个 `NewInstance`：没改过的 Case 直接 `Quit()`；改过（写了进料温度）的 Case 先 `Close()`；改过的 Case 直接 `Quit()`。后台线程 8 秒后查弹窗并准备点"否"的按钮。
- **结果**：三种情况都**没有弹窗**。`Quit()` 0.0 秒返回，进程 0.5 秒内消失；`Close()` 0.2 秒返回。`IsDirty` 在刚打开、没改过的 Case 上也是 True。
- **结论**：脚本里可以放心 `Close()` 和 `Quit()`，不会被保存确认卡住；H4 记为部分确认。要保存必须自己调用 `Save`/`SaveAs`（E4、E12）。
- **脚本与输出**：`spikes/e2b_quit_with_case.py`；`spikes/out/e2b_quit_with_case.txt`。

### L8 E3：反向探测（2026-10-08，示例 Synthesis Gas Production）

- **目的**：看 GUI 建出来的反应器、反应、反应集在 COM 里长什么样：各成员是哪个，出口温度规定在哪里，反应集成员怎么读，XML 路线能不能创建反应。
- **做法**：`spikes/e3_reverse_probe.py`：复制示例到临时目录，用 `NewInstance` 打开，只读。对 5 台反应器（2 台转化、3 台平衡）读进料、出料、能流、反应集、压降、热负荷、每个变量的 `IsKnown`/`State`/`CanModify`、反应结果和按组分的进出量；对 4 个反应读计量系数、基准组分、转化率、Keq 设置；对 3 个反应集读成员和与流体包的关联；导出 XML 并检索关键词。默认用示例；用户的参考 Case 建好后用 `--case` 补跑。
- **结果**：见"对象模型速查"各节的"实测"段落。要点：
  - `Item(i)` 直接返回具体类型，不需要 `CastTo`。反应 `TypeName`：`conversionrxn`、`equilibriumrxn`；反应集 `rxnset`。
  - 出口温度规定在气相出料物流上（`State` 1、`CanModify` True），带能流的反应器热负荷是计算值；没有能流的绝热反应器出口温度是计算值。
  - 反应集成员是 `ActiveReactions` 和 `InactiveReactions`；与流体包的关联是出现在 `fp.ReactionPackage.ReactionSets` 里。
  - 计量系数：负为反应物，正为产物；转化率是百分数；同一基准组分的多个转化反应并行地按进料算（Reformer：40% + 30% = 70%）。
  - 反应器进出量用 `ComponentTotalIn/Reacted/Out.GetValues("kgmole/h")` 读。
  - 没有连接能流时读 `op.EnergyStream` 抛 `com_error`，不是 None。
  - XML 导出 6.5 MB，但**不含反应和反应集的定义**。
  - **没有解决的**：`LnKSource` 读出 4，与类型库枚举（Table=3、FixedExtent=4）对不上；Gibbs 反应器没有样本，`ReactorType` 数字与界面选项的对应未知。
- **走过的弯路**：第一次运行在第二台反应器（Combustor）上崩溃：它没有连能流，`op.EnergyStream` 抛 `com_error`，而脚本只捕获了 `AttributeError`。改成 `optional_attr`（把 `com_error` 当作"没有连接"）后通过。
- **结论**：H16、H26 升为部分确认，H18、H20 升为已确认；H9、H10、H11、H15 仍是未测试，备注里写了读到的 `TypeName` 和结构。"创建反应的线索"据此重排：XML 路线降到最后，以 GUI Case 核对为第 3 条。
- **脚本与输出**：`spikes/e3_reverse_probe.py`；`spikes/out/e3_reverse_probe_sample.txt`。

### L9 任务 10：检索官方帮助（2026-10-08）

- **目的**：在安装目录的帮助文件里找 Automation 和反应相关的说明，尤其是 `Reactions.Add` 的 `Type` 参数、`Operations.Add` 的类型字符串、Gibbs 反应器的类型选项。
- **做法**：`hh.exe -decompile <目录> <文件>` 解包安装目录下的四个 `.chm`（`ww10_com`、`xhysys`、`ww10_cxx`、`ww10_000`）到 `spikes/out/help_html/`（已在 `.gitignore`，不提交），用 `Grep` 全文检索 `Reactions.Add`、`ReactionSets.Add`、`ActiveReactions`、`ReactionPackageManager`、`Operations.Add`、`conversionrxn` 等，再读相关页面。
- **结果**：
  - 四个文件各用 1.5 至 2.8 秒解开（共 2882 个文件，约 13 MB）。**只有 `xhysys.chm` 与本项目有关**：它是 HYSYS 的自定义和 Automation 对象参考（Flare 格式，792 个文件）。其余三个（`ww10_*`）从内容看是宏语言编辑器 WinWrap Basic 的帮助，与反应器无关。
  - `general/operation_types.htm` 列出 `Operations.Add` 的类型字符串（见 H15），`general/adding_an_object_to_a_flowsheet.htm` 给出写法 `Flowsheet.Operations.Add "Pump1", "PumpOp"`。**反应器的类型字符串在这里有文档依据**：`ConversionReactorOp`、`EquilibriumReactorOp`、`GibbsReactorOp`。
  - `general/hysys_application_progids.htm` 与实测一致：`HYSYS.Application`、`HYSYS.Application.NewInstance`、`.Latest`。
  - 枚举页（`enumerations/gibbsreactortype_enum.htm`、`lnksourceenum_enum.htm`）只有名字和数值，与类型库相同，**没有界面选项名**，所以 `LnKSource` 读出 4 的疑问和 Gibbs 的类型选项对应，帮助里查不到。
  - **没有 `Reactions.Add`、`ReactionSets.Add` 的说明**：`ReactionSet.htm`、`ReactionPackageManager.htm` 只是成员签名，没有加成员的方式。`PlayScript` 只有一句话，`BackDoor` 只有签名。
  - 安装目录里 `Help\*.hh` 只是帮助主题号的 `#define` 表，不是内容；产品的完整帮助不在本机的 `.chm` 里。
- **结论**：`Operations.Add` 的类型字符串有文档依据（H15 备注）；反应和反应集怎么创建，帮助里没有答案，只能靠 0B 的实测。
- **脚本与输出**：无脚本，命令行解包和检索；解包结果在 `spikes/out/help_html/`（不提交）。

### L10 E4：用代码新建 Case 和 Basis（2026-10-08）

- **目的**：怎么新建空白 Case、流体包、物性包、组分；Basis 要不要事务；组分库能不能检索；另存、关闭、重开之后 Basis 还在不在。
- **做法**：`spikes/e4_basis.py`：`NewInstance` 打开，`SimulationCases.Add`，在一个临时组分列表里试 12 类名字的 35 种写法，再建真正的组分列表 `CL-1`（8 个组分）和流体包 `Basis-1`，设物性包，`EndBasisChange()`，`SaveAs`，`Close`，重新 `Open`。共 4 次运行：run1 因为我把输出接给了 `head`，进程被管道关闭打断；run2 物性包没设上；run3 成功；run4 加了组分属性读取，是最终的日志。
- **结果**：
  - `SimulationCases.Add("name")` 成功，返回 `_SimulationCase`，新 Case 一开始就在 Basis 修改状态（H3、H5）。
  - **物性包设不上（走过的弯路）**：`fp.PropertyPackageName = "Peng-Robinson"` 抛 `E_INVALIDARG`；先设组分列表再设物性包、`FluidPackages.Add(name, Type)` 的 `Type` 传枚举值和字符串，都不行（E4b，20 多种写法）。没设物性包就 `SaveAs`，重新 `Open` 时弹模态对话框 "Could not load the Property Package for Fluid Package "Basis-1". A replacement Property Package will need to be selected before returning to the Simulation Environment."，`Open` 一直不返回，脚本被外层超时杀掉，实例按进程号结束。
  - **突破**：读示例 Case 的 `fp.PropertyPackage` 得到 `TypeName` 为 `pengrob`、`VisibleTypeName` 为 `Peng-Robinson`、`name` 为 `PengRobinson`。试了 `fp.PropertyPackageName = "pengrob"`，成功。**设置要用内部名，读出来的却是界面名。**
  - 组分：12 类名字里，库名（`Methane`、`H2O`、`CO`、`CO2`、`Hydrogen`、`Toluene`、`Benzene`、`p-Xylene`、`m-Xylene`、`o-Xylene`、`Carbon`）和别名 `H2` 被接受；分子式、`Water`、`CarbonMonoxide` 等不被接受（H8、H25）。`Carbon` 的 `IsSolid` 为 True（H21）。
  - `EndBasisChange()` 成功之后 `Flowsheet` 可用；`SaveAs` 得到 141 KB 的文件；重开后流体包 `Basis-1`、物性包 `Peng-Robinson`、8 个组分都在。
- **结论**：H3、H4、H7、H8 已确认；H5、H21、H25 部分确认；组分规范名表补了 11 个。没有答案的：`StartBasisChange()` 在 Basis 结束之后是否需要（E6）。
- **脚本与输出**：`spikes/e4_basis.py`、`spikes/e4b_property_package.py`；`spikes/out/e4_basis_run2.txt`（物性包没设上，重开卡住）、`e4_basis_run4.txt`（最终）、`e4b_property_package_run1.txt`、`e4b_property_package_run2.txt`。

### L12 E6：用代码创建反应和反应集（2026-10-08）

- **目的**：全项目风险最高的一步：`Reactions.Add` 的 `Type` 传什么？计量系数、基准组分、转化率怎么写？反应集怎么建、怎么放反应、怎么加入流体包？要不要在 Basis 修改状态里？重开后还在不在？
- **做法**：`spikes/e6_reaction.py`：沿用 E4 的 Case 和 Basis（8 个组分，`pengrob`），先用 13 种 `Type` 候选各建一个临时反应并删掉；再建转化反应 Tol-Disp（2 甲苯 → 苯 + 对二甲苯，基准组分甲苯，转化率 50%）；试分数系数；建两个平衡反应 SMR 和 WGS；建反应集 Conv-Set、Eq-Set；结束 Basis，在结束后再建反应；另存、关闭、重开，读回。共 4 次运行，run4 是最终日志。
- **结果**：
  - **第一条线索第一次就成了**：`Reactions.Add("T1", "conversionrxn")` 返回 `ConversionReaction`，`equilibriumrxn` 返回 `EquilibriumReaction`，`kineticrxn` 返回 `KineticReaction`。界面名、类名、整数、省略 `Type` 全部 `E_FAIL`。
  - 转化反应：`Reactants.Add("Toluene")` 返回 `Reactant`，系数写入后 `ReactantStoichCoefValue` 读回 `(-2.0, 1.0, 1.0)`；`BaseComponent`、`Conversion = 50.0` 读回一致。分数系数 0.24 能写。
  - 平衡反应：新建后默认 `LnKSource=2`、`Basis=1`、`ReactionPhase=0`、`AutoDetect=True`。写 `LnKSource = 0`（想设"Gibbs"）读回仍是 2，一度以为设不上。
  - 反应集：`ReactionSets.Add(name)`、`ActiveReactions.Add(反应名)`、`AssociateFluidPackage(fp)` 都成功；`AssociateFluidPackage` 之前，流体包的反应集清单里没有它。
  - `EndBasisChange()` 之后直接建反应也成功；`StartBasisChange()` 可用。
  - 另存重开：3 个反应、2 个反应集、成员、转化率、基准组分、`LnKSource` 都在。系数被微调：甲苯歧化的对二甲苯 1.0 变 1.00005，SMR 的氢 3.0 变 2.9996，WGS 的氢 1.0 变 1.00015（质量守恒修正）。
- **走过的弯路**：Keq 来源的数字对不上（见 L13）。
- **结论**：H9 已确认，H5 已确认，H10、H11 部分确认（创建和设置确认了，对求解的效果等 E7、E8）。分数系数可用，所以场景 2 的二甲苯异构体可以用一个反应写四种产物。
- **脚本与输出**：`spikes/e6_reaction.py`；`spikes/out/e6_reaction_run3.txt`（含 Basis 之后建反应）、`e6_reaction_run4.txt`（最终，加了分数系数）。

### L13 E6b：平衡反应的 Keq 来源（2026-10-08）

- **目的**：E6 里写 `LnKSource = 0` 没有效果，E3 里示例读出 4 与类型库枚举对不上。弄清真实的取值对应。
- **做法**：`spikes/e6b_keq_source.py`：新建 SMR 平衡反应，逐个写 0 至 4 并读回；再写固定 K；再读 `Support\equirxn.rdf`（界面定义）里各来源分组的可见范围。
- **结果**：
  - 写 1、2、3、4 都读回原值，写 0 被忽略（读回仍是前一个值）；写入任何明确的来源，`AutoDetect` 变成 False。
  - `equirxn.rdf`：`GibbsEnergyOp` 的 `VisibleRange ":ExtraData.611.1" 2 2`，`FixedKOp` 为 3，`KTableOp` 为 4，`LnKEquationOp` 为 1。界面标题分别是 "Source : Gibbs Free Energy"、"Source : Fixed K"、K–T 表、"Source : Ln (K) Equation"。
  - 固定 K：`LnKSource = 3` 后 `EquilibriumConstant = 12.5`，读回 12.5。
  - 只写来源、不写数值时，`EquilibriumConstant`、`KEqValue`、`KCalculatedValue` 等读取都抛 `E_FAIL`，所以不能靠"哪些成员可读"区分来源；写了固定 K 的数值之后能读回。
- **结论**：**1 = Ln(K) 公式，2 = Gibbs 自由能（默认），3 = 固定 K，4 = K–T 表。类型库枚举名对不上。**新建的平衡反应默认就是 Gibbs 自由能，不需要写。H10 的备注已更新。示例里 Rxn-4 读出 4 的疑问解决。
- **脚本与输出**：`spikes/e6b_keq_source.py`；`spikes/out/e6b_keq_source_run2.txt`。

### L14 参考 Case 的构建：E5 物流、E7 转化反应器、E8 平衡反应器、E9 Gibbs 反应器（2026-10-08，D11）

- **目的**：用户指示由助手自行创建三种反应器的参考 Case（D11）。顺带回答 0B、0C 的创建链问题：新建物流和能流、`Operations.Add` 的类型字符串、反应器怎么连、出口温度规定在哪里、改规定后是否重算、能流热负荷的符号、Gibbs 反应器默认类型。
- **做法**：`spikes/build_reference_case.py`：空白 Case 里建 Basis（8 个组分，`pengrob`）、3 个反应、2 个反应集；`EndBasisChange()`；3 股进料；每台反应器两股出料，平衡和 Gibbs 反应器各一股能流；连接后读结果并与独立参照值比较；平衡和 Gibbs 反应器的出口温度依次设 710、600、710 °C；最后保存为 `spikes/ref_cases/three_reactors.hsc`。run1 是第一版，run2 至 run4 是整理后的版本，run3、run4 连续运行，结果逐项相同。
- **结果**：
  - **一次就成功，没有走弯路**：E4、E6 的结论直接可用。`Operations.Add` 的帮助文件写法有效；`Feeds.Add(物流对象)`、`VapourProduct = …`、`LiquidProduct = …`、`EnergyStream = …`、`ReactionSet = …` 的赋值都成功。
  - 转化反应器（绝热）：气相摩尔分率甲苯 0.5000、苯 0.2500、对二甲苯 0.2500，与期望值相差小于 1e-5；出口温度 379.27 °C；质量守恒误差 1.5e-5。
  - 平衡反应器：710 °C 五个摩尔分率的最大偏差 0.0046，CH4 转化率 54.0%，总流量 4780.7，热负荷 +39989 kW；600 °C 最大偏差 0.0014，转化率 30.3%，总流量 4307.1，热负荷 +20160 kW。**改出口温度之后模型同步重算**，再改回 710 °C 结果复现。
  - Gibbs 反应器（不挂反应集，默认 `ReactorType` 为 3）：与平衡反应器的 710 °C、600 °C 工况摩尔分率最大偏差 1e-5，符合 0C 里"两者应当接近"的预期。
  - 流程图 14 个对象（3 进料、6 出料、2 能流、3 反应器）状态都是 OK。
  - `SaveAs` 到已有文件静默覆盖，留下 `three_reactors.bk0`（已加进 `.gitignore`，没有提交）。
- **结论**：H12、H14、H15、H16、H20 已确认，H10 部分确认（Gibbs 来源端到端验证，固定 K 和公式来源未求解验证），H11 已确认，H19 部分确认。"调用序列"一节的三个小节已按这次的实测写出。**这是 0A 里提前做的 0B、0C 工作，0B、0C 仍要按各自的提示词再做一遍**，尤其是：甲苯歧化四产物的分数系数版本和并行转化排序（0B），平衡反应器的绝热、固定 K 来源求解、多股进料（0C），固体碳（0C 的 E10）。
- **脚本与输出**：`spikes/build_reference_case.py`；`spikes/out/build_reference_case_run3.txt`、`build_reference_case_run4.txt`；参考 Case `spikes/ref_cases/three_reactors.hsc`（178 KB）。

### L15 E9b：Gibbs 反应器的 ReactorType 取值（2026-10-08）

- **目的**：界面上的三个选项（"Gibbs Reactions Only"、"Specify Equilibrium Reactions"、"NO Reactions (=Separator)"，原文来自 `Support\OdfRdfVariables.sdb`）对应 `ReactorType` 的哪个数字。
- **做法**：`spikes/e9b_gibbs_type.py`：打开参考 Case 的副本，对 `R-Gibbs` 逐个写 0、1、2、3，读出料和流程图状态；再对类型 2 挂上 `Eq-Set`；不保存。
- **结果**：默认 3；写 0，出料组成等于进料（0.2703、0.7297），流量 3700 不变，热负荷 9328 kW（只加热不反应）；写 1，出料全是 -32767，流程图有 4 个对象 `NotSolved`；写 2 不挂反应集，反应器 `UnderSpecified`，3 个对象 `NotSolved`；写 2 并挂上 `Eq-Set`，出料与平衡反应器完全相同（4780.75，热负荷 39989.77 kW）；写回 3，结果同样。
- **结论**：0 = NO Reactions，2 = Specify Equilibrium Reactions，3 = Gibbs Reactions Only（默认）。1 无效但写得进去。台账 H31、H19。
- **脚本与输出**：`spikes/e9b_gibbs_type.py`；`spikes/out/e9b_gibbs_type_run3.txt`。

### L16 E3 补跑：参考 Case（2026-10-08）

- **目的**：D11 的参考 Case 建好之后，按 0A 的约定补跑反向探测，对照示例 Case 的发现。
- **做法**：`.venv\Scripts\python.exe spikes\e3_reverse_probe.py --case spikes\ref_cases\three_reactors.hsc --tag three`。
- **结果**（`spikes/out/e3_reverse_probe_three.txt`）：三种反应器（含 Gibbs）、3 个反应、2 个反应集的读法和示例 Case 一致：`Item(i)` 返回具体类型；出口温度规定在气相出料上（`State` 1、`CanModify` True，值 710 °C），热负荷是计算值；Gibbs 反应器 `ReactorType` 读出 3，`ComponentName.Values` 末尾多一个空字符串，没连反应集时读 `ReactionSet` 抛 `com_error`；`ComponentTotalFeed`、`ComponentTotalProduct` 用 `GetValues("kgmole/h")` 读。平衡反应的 `LnKSource` 读出 2（Gibbs 自由能），与 E6b 一致。
- **结论**：0A 遗留的两个未解决项（`LnKSource` 对应、Gibbs `ReactorType` 对应）都已解决；Gibbs 的界面选项原文已记录。
- **脚本与输出**：`spikes/e3_reverse_probe.py`；`spikes/out/e3_reverse_probe_three.txt`。

### L17 E5：新建物流（2026-10-08，0B 任务 2）

- **目的**：新建物流，规定温度、压力、质量流量、组成，确认闪蒸完成；记录写入方式、单位、错误行为。
- **做法**：`spikes/e5_stream.py`：新开实例，建 0B 的 5 个组分的 Basis，建物流 `Feed`（380 °C、2500 kPa、10000 kg/h 纯甲苯），按 T、P、组成、质量流量的顺序写，每写一步读一次各量的已知性；再在另一股物流上试错误输入；最后试同名物流。共 3 次运行：run1 在读新物流的 `VapourFractionValue` 时抛 `E_FAIL` 崩溃（脚本没有保护），run2 修好，run3 加了同名物流的核对，是最终日志。
- **结果**：见 H12、H13、H14。要点：新物流所有量未知；T、P、组成写完闪蒸完成；质量流量 10000 kg/h 读回 108.5296 kgmole/h；组成被静默归一化；负流量不校验；同名 `Add` 返回已有物流。
- **走过的弯路**：新物流的 `VapourFractionValue` 读取抛 `E_FAIL`，而 `.Value`、`GetValue` 返回 -32767（H22 的补充：`…Value` 属性在未知时可能抛错而不是返回空值）。
- **结论**：H12、H13、H14 补充了错误行为；写入顺序没有要求。
- **脚本与输出**：`spikes/e5_stream.py`；`spikes/out/e5_stream_run3.txt`。

### L18 E7：转化反应器全链路，闸门 G0（2026-10-08，0B 任务 4）

- **目的**：从空白 Case 用代码建出甲苯歧化的转化反应器（四产物分数系数），求解，与解析解对比；连续运行两次；弄清求解语义和建模期间要不要挂起求解器。
- **做法**：`spikes/e7_conversion_chain.py`，按步骤拆成函数（新建 Case、Basis、反应、反应集、结束 Basis、进料、出料物流、反应器），每个函数对应"调用序列"里的一步。`--repeat 2` 连续从空白 Case 建两次，每次一个新的 HYSYS 实例；`--hold-solver` 在建模期间挂起求解器。运行 3 次：run1（单次）、run2（`--repeat 2`）、hold（`--repeat 2 --hold-solver`）。
- **结果**：**G0 通过。**
  - 出料摩尔分率：甲苯 0.5000、苯 0.2500、对二甲苯 0.0600、间二甲苯 0.1300、邻二甲苯 0.0600，与期望值的偏差都是 0.00000（容差 0.001）。各组分摩尔流量 54.265、27.132、6.512、14.109、6.512 kgmole/h；质量流量 5000.0、2119.3、691.3、1497.9、691.3 kg/h。
  - 质量守恒相对误差 1.52e-05（容差 1e-4）；出口温度 378.59 °C，与 380 °C 相差 1.41（容差 10）；液相出口流量 0；进料 108.530 kgmole/h，解析 108.530。
  - 两次运行（含各自新的 HYSYS 实例）各组分摩尔流量的相对偏差为 0（要求 ≤ 1e-4）；挂起求解器的两次运行结果相同。
  - 整条链的 COM 调用用时约 2 秒；新建 Case 1.5 秒，其余每步都不到 0.2 秒。
  - **求解随写入同步完成**，没有单独的"求解"调用；挂起时释放这一句同步求解（0.01 秒）。
- **结论**：全部用第一级集成方式（COM 编程创建），没有用到降级。H9、H11、H15、H16、H17、H20 补充了 G0 的证据；分数计量系数可用。
- **脚本与输出**：`spikes/e7_conversion_chain.py`；`spikes/out/e7_conversion_chain_run2.txt`、`e7_conversion_chain_hold.txt`。

### L19 E7b：模型没有求解时从哪里读原因（2026-10-08，0B 任务 4）

- **目的**：阶段提示词要求弄清"模型没有求解时，从哪里能读到原因（哪个量没有规定）"。
- **做法**：`spikes/e7b_unsolved_reasons.py`：一台反应器逐步连接，每步读流程图状态；另外 8 台各缺一样东西的反应器（没接进料、没接气相出料、没接液相出料、没挂反应集、反应集没加入流体包、反应集类型不匹配、进料流量没规定、对照组）。运行 3 次：run1 在"反应集没加入流体包"一例崩溃（`ReactionSet = …` 抛 `E_INVALIDARG`，脚本没有保护）；run2 在"反应集类型不匹配"一例卡死（弹模态对话框，被外层超时杀掉）；run3 加了弹窗看门狗，完整跑完。
- **结果**：见 H19、H16、H23。要点：状态只定位到对象；缺连接都是 `UnderSpecified`，要读反应器成员区分；进料流量没规定是 `NotSolved`；反应集没加入流体包写入即报错；类型不匹配弹窗。压降新建时就是规定值 0 kPa。
- **结论**：H19 补全；新增架构问题 D12（弹窗看门狗要不要用线程）。
- **脚本与输出**：`spikes/e7b_unsolved_reasons.py`；`spikes/out/e7b_unsolved_reasons_run3.txt`。

### L20 E6b：三个并行的转化反应，排序是什么（2026-10-08，0B 任务 5）

- **目的**：后面的阶段要支持"同一个基准组分有主、副两个反应，各有各的转化率"，所以要知道 HYSYS 怎么处理并行的转化反应：默认是并行还是依次，排序对应哪个成员、取值什么含义，怎么设。
- **做法**：`spikes/e6b_parallel_reactions.py`：沿用 `e7_conversion_chain.py` 的步骤函数，把一个反应换成三个转化反应 `R-pX`、`R-mX`、`R-oX`（基准组分都是甲苯，各生成一种二甲苯，转化率 12%、26%、12%），放进同一个反应集 `Conv-Set`。读默认排序下的出口；用 `GetIDsOfNames` 在反应集、反应器、反应上探测 14 个候选的排序成员名；从 `ProvideXMLForOperation` 的 XML 找到 `ReactionRanks`；再用 `ApplyXMLForOperation` 把排序改成 (0,1,2)、(1,1,0)、(2,1,0)、(5,5,5) 写回（每个实验用一个新 Case，写回前后各读一次进料组成和排序）。
- **结果**（`spikes/out/e6b_parallel_reactions_run1.txt`）：
  - 默认排序下出口摩尔分率甲苯 0.5000、苯 0.2500、对二甲苯 0.0600、间二甲苯 0.1300、邻二甲苯 0.0600，`RxnPercentConversionValue` 读回 (12, 26, 12)：**默认是并行**（依次进行应是 0.573）。
  - 14 个候选名字（`Rank`、`Ranking`、`ConversionRankings`、`ReactionRank`、`Order`、`Index`、`UserSpecified`……）在反应集、反应器、反应上都不存在。
  - XML 里排序在 `…/ReactionSet/ReactionRanks/ReactionRankSet/ReactionRank`，三个值都是 `0`，`Status` 为 `Specified`；操作的 XML 带 `Basis`，这是读到排序的唯一位置。
  - 5 个写回实验（整份 XML 去掉声明；只含排序的最小 XML，3 种排序）`flags=0` 全部返回 False，出口组成变成五个组分各 0.2（Case 被弄坏），排序读回仍是 0。
- **走过的弯路**：第一版把整份 XML 打印进日志（409 KB，超过 1 MB 以内的习惯，没有提交，已删）；第一次写回带着 XML 声明，msxml 报 "Invalid xml declaration"（字符串带 `windows-1252` 声明）；去掉声明后返回 False，随后发现进料组成被重置成 0.2，Case 被弄坏，此后每个写回实验都用新 Case。早期草稿版本的几次运行日志没有保留，提交的是重写后的 run1。
- **结论**：并行是默认；排序没有 COM 成员；`flags=0` 的 XML 写回不能用。下一步 E6c 试别的位掩码、BackDoor 和示例 Case。
- **脚本与输出**：`spikes/e6b_parallel_reactions.py`；`spikes/out/e6b_parallel_reactions_run1.txt`。

### L21 E6c：反应集排序能不能读写，含义是什么（2026-10-08，0B 任务 5）

- **目的**：E6b 之后还剩两件事：用别的通道设置排序（阶段提示词给第二级 60 分钟）；弄清排序值的含义。
- **做法**：`spikes/e6c_rank_channels.py`，同一个脚本四次运行（run1 至 run3 是逐步加实验的早期版本，run4 是最终版，含全部实验）：Q1 用 12 个 `flags` 导出操作 XML，看排序节点；Q2 BackDoor 读排序，并用值已知的进料温度校准 moniker 写法；Q3 BackDoor 写排序；Q4 带 `flags` 的 `ApplyXMLForOperation`（最小 XML 和整份 XML）、Case 级 `ApplyXML`；Q5 `ActiveReactions.Add(name, 数)` 的第二个参数；Q6 读示例 Case 里转化反应器的排序值、指定转化率和实际起作用的转化率。
- **结果**（`spikes/out/e6c_rank_channels_run4.txt`）：
  - Q1：`flags` 带 8（`opt_SupplyMonikers`）时排序节点多一个 `<Moniker>:Index.400.0</Moniker>`，其余 `flags` 只有 `Value`、`ValueType`、`Status`；`opt_CondenseData`(8192) 去掉了 `OwnerType`/`OwnerName` 属性。
  - Q2：所有者路径用 `UniqueID` 或 IMoniker 显示名，变量部分用 `:Index.400.0`、`:Index.400.[0]`、`.Index.400.0`，一律读出 `IsKnown` False、值 -32767.0；同样的写法读值已知的进料温度（`:Temperature.501.0` 等）也读出空变量，说明是 moniker 写法不对而不是排序变量特殊；IMoniker 对象和复合 IMoniker 直接当参数返回 None；`BackDoorVariablesAndObjects` 返回 `(None, None)`。
  - Q3：对排序变量 `SetValue` 抛 `E_FAIL`，排序仍是 0，出口仍是并行 0.5000。
  - Q4：最小 XML 的 `flags` 8、9 返回 False 并弄坏 Case；128、129、137 返回 True，什么都不改。整份 XML 把压降 0 → 50、进料温度 380 → 400、排序 → (0,1,2) 一起改：`flags` 1、2、16 返回 False 并弄坏 Case；128、144 返回 True，**三样都没变**。Case 级 `ApplyXML`（0、128、137）返回 None，什么都不改。
  - Q5：`ActiveReactions.Add('R-pX', 1)` 等返回正常，排序读回仍是 0，仍是并行。
  - Q6：Synthesis Gas Production 的 Combustor 反应集排序 (1, 1, 0)，指定转化率 (35, 65, 100)，实际起作用的转化率 (18.09, 33.60, 48.31)，实际/指定 = 0.516868 = 1 − 0.483132（吻合）；Reformer 排序 (0, 0)，实际等于指定（40, 30），并行。
- **走过的弯路**：run1 把 `Moniker` 属性（IMoniker 对象）当字符串拼进 moniker，得到 `<PyIUnknown at 0x…>` 的乱码，BackDoor 照样返回有效的包装而不报错；run2 用 `UniqueID` 拼，读到的变量仍然是空的，当时还不知道是 moniker 写法的问题还是排序变量的问题，所以 run3 加了用进料温度的校准，run4 又加了复合 IMoniker 和 Case 级 `ApplyXML`。
- **结论**：排序**能读（XML）、不能写**。含义从示例 Case 反推：排序值最小的反应先算，排序相同的并行，后面的反应对剩下的基准组分按指定转化率算。依次进行的 0.573 没有用代码验证；Recipe 不设排序（H32）。H24 记为不可行，H26 补充了导入的结果，新增 H32。**后来 0C 的 E13b 发现 `PlayScript` 可以写排序，上面“不能写”只适用于 COM 成员、XML、BackDoor 三条路，见 L29。**第二级的 60 分钟没有用完，试过的方式已经超过 5 种，按提示词的"走不通"标准停止，没有降到第三、四级。
- **脚本与输出**：`spikes/e6c_rank_channels.py`；`spikes/out/e6c_rank_channels_run1.txt` 至 `run4.txt`。

### L22 E8：平衡反应器，两个工况，三种热模式，固定 K（2026-10-08，0C 任务 1）

- **目的**：从空白 Case 用代码建出场景 1 的平衡反应器模型，两个出口温度的结果与参照值对比；弄清 Keq 来源的默认值、出口温度规定的位置、改规定后是否自动重算、热负荷的读法和符号；验证绝热和规定热负荷两种热模式；试一次固定 K。
- **做法**：`spikes/e8_equilibrium_chain.py`（沿用 `chain_kit.py` 里的建模函数）：甲烷、水、CO、CO2、氢气，PR；两个平衡反应 Rxn-1（CH4 + H2O ⇌ CO + 3 H2）、Rxn-2（CO + H2O ⇌ CO2 + H2），Keq 来源不写；反应集 RxnSet-1 加入流体包；进料 520 °C、1350 kPa、3700 kgmole/h、CH4 0.2703；ERV-100 带能流，气相出料温度依次写 710、600、710 °C。同一个 Case 里再建三台反应器：ERV-ADI（不接能流）、ERV-DUTY（接能流，写 710 °C 工况读出的热负荷 39989.2 kW，不规定出口温度）、ERV-K（固定 K：`Basis = 5`（摩尔分率基准）、`LnKSource = 3`、`EquilibriumConstant` 取 710 °C 结果反推的 0.0830251 和 1.55565）。运行 1 次（run1）。
- **结果**（`spikes/out/e8_equilibrium_chain_run1.txt`）：
  - **Keq 来源默认就是 Gibbs 自由能**：新建的平衡反应读出 `LnKSource` 2、`Basis` 1（Activity）、`AutoDetect` True，不用写。
  - **710 °C**：CH4 转化率 54.0%，出口总流量 4780.7 kgmole/h（参照约 4800），摩尔分率 CH4 0.0962、H2O 0.3844、H2 0.4064、CO 0.0457、CO2 0.0673，与参照值最大偏差 0.0046（容差 0.02）；热负荷 +39989.2 kW。**600 °C**：转化率 30.3%，总流量 4307.1（参照约 4305），最大偏差 0.0014；热负荷 +20159.8 kW，小于 710 °C 工况。两个工况通过。质量守恒相对误差都在 6.1e-06 以内；液相出口流量 0。
  - **改规定自动重算**：写气相出料物流的 `Temperature`，同步重算，不用额外调用；再回到 710 °C，摩尔分率与第一次最大差 3.9e-08。
  - **出口温度规定在气相出料物流上**，反应器上没有这个成员。连接完、没规定出口温度时，反应器和三个出口量（气相、液相、能流）都是 `NotSolved`，进料 OK；规定温度后 5 个对象全是 OK。
  - **热负荷**：`energy.HeatFlow.GetValue("kW")`，**吸热为正**；计算值 `State` 0、`CanModify` False；规定热负荷时 `State` 1、`CanModify` True。
  - **绝热**（不接能流）：直接求解，出口温度 422.63 °C 是计算值（`State` 0、`CanModify` False），CH4 转化率 8.8%。
  - **规定热负荷**：能流写 39989.2 kW、不规定出口温度，出口温度 710.00 °C，组成与规定 710 °C 的工况相同。
  - **固定 K**：`reaction.Basis = 5`、`reaction.LnKSource = 3`、`reaction.EquilibriumConstant = K`，读回一致；求解成功，与 Gibbs 来源 710 °C 的摩尔分率最大差 0.00000。反应器的 `EqConstantValue` 读出 Gibbs 来源（活度基准）K 为 (14.919, 1.561)（710 °C）、(0.520, 2.744)（600 °C）；活度基准的 K 与摩尔分率基准的 K 之比约等于 (P/P°)^Δν 再乘逸度系数的修正（SMR：Δν 为 2，14.92/0.0830 = 179.7；P° 取 1 atm 得 177.5，取 1 bar 得 182.3，两者都能解释，没有区分）。
  - 反应器自己的结果：`RxnPercentConversionValue` 读出 (54.03, -32767.0)（第二个反应没有基准组分，空值）；`RxnExtentValue`、`EqConstantValue` 按反应集里的反应顺序。
- **结论**：H10、H16、H20 补充（固定 K 已验证求解，三种热模式都验证过）。**实测验证过的热模式：规定出口温度、绝热、规定热负荷；Keq 来源：Gibbs 自由能（默认）、固定 K（摩尔分率基准）；Ln(K) 公式和 K–T 表没有验证。**
- **脚本与输出**：`spikes/e8_equilibrium_chain.py`、`spikes/chain_kit.py`；`spikes/out/e8_equilibrium_chain_run1.txt`、`e8_equilibrium_chain_run1.hsc`（Case，188 KB）。

### L23 E9：Gibbs 反应器，纯气相，多股进料，绝热（2026-10-08，0C 任务 2）

- **目的**：用任务 1 的进料和组分，不建反应、不挂反应集，用 Gibbs 反应器的纯自由能最小化模式，出口 710 °C，结果应与平衡反应器很接近；再各试一次多股进料和绝热。
- **做法**：`spikes/e9_gibbs_gas.py`（沿用 `chain_kit.py` 和 E8 的 `build_train`）：同一个 Case 里 Gibbs 反应器 GBR-100（带能流，气相出料写 710 °C）和平衡反应器 ERV-E（对照）；GBR-MULTI 把进料拆成甲烷 1000 kgmole/h 和水蒸气 2700 kgmole/h 两股，条件与单股进料相同；GBR-GADI 和 ERV-EADI 都不接能流。运行 2 次：run1 在最后一步崩溃，是脚本的名字冲突（见弯路），run2 是最终日志。
- **结果**（`spikes/out/e9_gibbs_gas_run2.txt`；run1 的 Q1、Q2 与它相同）：
  - **Gibbs 模式**：`reactor.ReactorType` 新建时读出 3（"Gibbs Reactions Only"，纯自由能最小化），不用写；不挂反应集，读 `reactor.ReactionSet` 抛 `com_error`（`E_FAIL`），但能正常求解；连接完、没规定出口温度时，反应器和三个出口量都是 `NotSolved`（和平衡反应器一样），写气相出料的温度后求解。
  - **710 °C**：出口总流量 4780.75 kgmole/h，摩尔分率 CH4 0.0962、H2O 0.3844、H2 0.4064、CO 0.0457、CO2 0.0673，CH4 转化率 54.0%，热负荷 +39989.8 kW。与参照值最大偏差 0.0046（容差 0.02），与同一个 Case 里的平衡反应器最大偏差 0.00001，热负荷差 0.6 kW。通过。
  - **多股进料**：`reactor.Feeds.Add(stream)` 对每股进料调用一次，`Feeds.Names` 读出 `['FeedCH4-M', 'FeedH2O-M']`；摩尔分率与单股混合进料相同（最大差 0.00000）；热负荷 40038.3 kW，比单股进料多 48.5 kW（0.12%），是两股分开进料的焓与混合后进料的焓不完全相等（PR 的混合热），不是模型问题。
  - **绝热**（不接能流）：Gibbs 反应器直接求解，出口温度 422.63 °C 是计算值（`State` 0、`CanModify` False），CH4 转化率 8.8%，与绝热平衡反应器（E8 的 422.63 °C）相差 0.01 °C，摩尔分率最大差 0.00001。
  - 质量守恒相对误差 8.2e-07 以内；全部求解后流程图 24 个对象全是 OK。
- **走过的弯路**：run1 里 Gibbs 和平衡反应器的绝热对照用了同一个名字后缀，`MaterialStreams.Add("Vap-ADI")` 对已有的名字返回已经接在 Gibbs 反应器上的那股物流（H12 的幂等），再把它设成平衡反应器的 `VapourProduct`，抛 `com_error`（`E_INVALIDARG`，`-2147024809`）：**一股物流不能同时是两台反应器的出料**。这条也记进鲁棒性观察；run2 改了名字。
- **结论**：Gibbs 纯气相、多股进料、绝热都已验证；三种热模式（规定出口温度、绝热、规定热负荷）只在平衡反应器上验证了规定热负荷（E8），Gibbs 反应器没有试规定热负荷。H16、H20、H31 补充。
- **脚本与输出**：`spikes/e9_gibbs_gas.py`；`spikes/out/e9_gibbs_gas_run1.txt`、`run2.txt`、`e9_gibbs_gas_run2.hsc`（Case，199 KB）。

### L24 E10：固体碳在 Gibbs 反应器里的行为（2026-10-08，0C 任务 3）

- **目的**：场景 3（水煤浆气化）只有碳和水进料，要用 Gibbs 反应器的纯自由能最小化得到 1400 °C 的出口组成。要回答五个问题：组分库有没有碳；含固体的进料能不能闪蒸；Gibbs 反应器是否让碳作为固体参与平衡；没反应掉的碳从哪股出料离开；碳元素是否守恒。
- **做法**：`spikes/e10_gibbs_carbon.py`：碳、水、CO、氢气、CO2、甲烷，PR；进料 40 °C、4000 kPa、3569 kgmole/h、摩尔分率碳 0.710、水 0.290；Gibbs 反应器 GBR-100 带能流，气相出料写 1400 °C。每个变体从空白 Case 开始、只改一样东西：`base`（先接出料再接能流）、`energy-first`（先接能流）、`hold-solver`（建模期间挂起求解器）、`split-feeds`（碳和水两股进料）、`water-rich`（碳 : 水 = 1 : 5，碳应当全部气化）、`no-carbon`（甲烷 + 水蒸气，不含碳）；另在 `energy-first` 的 Case 里依次改出口温度 1000、1200、1600、1400 °C。运行 2 次：run1 只有单一做法（旧版脚本），run2 是最终日志，含全部变体。
- **结果**（`spikes/out/e10_gibbs_carbon_run2.txt`）：
  - **Q1 组分库里的碳**：`Components.Add("Carbon")` 成功，名字 `Carbon`，分子式 `C`，`IsSolid` 为 True，固体密度 1642 kg/m³，`HeatOfFormation` 为 0。
  - **Q2 含固体的进料**：能正常闪蒸，所有量已知。HYSYS 把碳和水的浆料当作**重液相**：`VapourFraction` 0，`LiquidFraction` 1.0，`HeavyLiquidFraction` 1.0；49081.1 kg/h；质量分率读回碳 0.6201、水 0.3799（与 0.62、0.38 相差 1e-4，因为摩尔分率只给了三位）。
  - **Q3 碳是否作为固体参与平衡：否，结果是错的。**四个含碳的变体（`base`、`energy-first`、`hold-solver`、`split-feeds`）得到**完全相同**的结果：气相 CO 1035.0、CH4 517.5 kgmole/h，**氢气 0、水 0、CO2 0**；热负荷 73.00 MW。与参照值相差很大（参照 CO 1017、H2 981、CH4 22、H2O 11、CO2 3.5）。**出口温度改成 1000、1200、1600、1400 °C，组成一点都不变**（只有热负荷变：61.46、67.03、79.75、73.00 MW），所以这不是平衡计算的结果。
  - **Q4 没反应掉的碳**：从**液相出料**离开（重液相，100% 碳），981.5 kgmole/h，参照 1491，相差 34%。气相出料里没有碳。
  - **Q5 碳元素守恒**：进 2533.99，出 2533.99 kgmole/h，误差为 0。**这个检查通过，但结果是错的**：CO 收率 0.4085 落在 38% 至 42% 的范围里，只是因为水是限量反应物，水全部变成了 CO（1035 / 2534）。
  - 四条通过条件：1 CO 收率 通过（巧合）；2 气相 CO、H2 摩尔分率 未通过（0.667、0 对 0.500、0.482）；3 碳元素守恒 通过；4 固体碳的量 未通过（相差 34%）。**E10 不满足通过条件。**
  - **对照变体说明问题只出在固体碳上**：`no-carbon`（甲烷 : 水 = 1 : 2.7，1400 °C、4000 kPa）CH4 几乎全部重整（出口 CH4 0.5 kgmole/h），CO 838.5、H2 3018.2、CO2 125.7、H2O 1514.4，水煤气变换的表观平衡常数 0.299；`water-rich`（碳 : 水 = 1 : 5，碳全部反应，没有固体）CO 340.6、H2 849.0、CO2 254.2、H2O 2125.2，表观平衡常数 0.298，与前者一致。气相的 Gibbs 平衡在 1400 °C 是正常的。
  - **新的弹窗**：`base` 的连接顺序（Gibbs 反应器接完进料和出料、还没接能流）弹出模态对话框 "Since the energy stream is not supplied, the Gibbs Reactor operates at an adiabatic condition. But this condition is not suitable for the system you are simulating. You may specified Gibbs Reactor temperature to find out a reasonable heat duty to the Gibbs Reactor first."，看门狗点了 OK。先接能流再接出料（`energy-first`）不弹。挂起求解器（`hold-solver`）不影响结果。
- **走过的弯路**：run1 的结果一出来就很可疑（氢气恰好为 0、CH4 恰好是 CO 的一半），没有直接接受；我先怀疑连接顺序、求解器挂起、进料形态（所以有了后面三个变体），三样都不影响；然后怀疑 1400 °C 的气相热力学（`no-carbon`、`water-rich`），也正常；最后看到结果与温度无关，转去查组分库里碳的数据，见 L25。
- **结论**：**Gibbs 反应器 + 库里的固体碳（PR 物性包）不能给出正确的气化平衡**，原因见 L25。按提示词不自行改用计划 §17.3 的两段式替代做法，已登记进度文件 D14 请用户决定。
- **脚本与输出**：`spikes/e10_gibbs_carbon.py`；`spikes/out/e10_gibbs_carbon_run1.txt`、`run2.txt`、`e10_gibbs_carbon_run2.hsc`（Case，157 KB）。

### L25 E10b：Gibbs 反应器为什么算错碳，库里碳的热力学数据（2026-10-08，0C 任务 3）

- **目的**：E10 的结果与温度无关，说明不是平衡计算。假设库里的碳的数据有问题，读出来核对。
- **做法**：`spikes/e10b_carbon_thermo.py`：读六个组分的 `HeatOfFormation`、`EvaluateGibbs(T)`（"Evaluate Gibbs Free Energy at T in K"）、`EvaluateIdealH(T)`，以及碳的蒸气压数据；与教科书的 298.15 K 标准 Gibbs 生成能对照。运行 2 次：run1 读生成焓和 Gibbs 函数，run2 加了碳的蒸气压数据。
- **结果**（`spikes/out/e10b_carbon_thermo_run1.txt`、`run2.txt`，单位 kJ/kgmole）：
  - 298.15 K 的 `EvaluateGibbs`：H2O -227833（教科书 -228.6 kJ/mol）、CO -138008（-137.2）、CO2 -394379（-394.4）、CH4 -50273（-50.5）、氢气 0，**与教科书一致**；**碳是 +671285，这是气态碳原子 C(g) 的 Gibbs 生成能（+671.3 kJ/mol），不是石墨的 0。**1673.15 K 时碳还是 +450525。
  - `HeatOfFormation`：碳 0.0（石墨的值），H2O -241814、CO -110590、CO2 -393790、CH4 -74900。所以**碳的生成焓按石墨给，Gibbs 函数却按气态原子给，两者不一致。**
  - 碳的蒸气压数据：`EvaluateVPsublim`（升华蒸气压）读出 -32767（空值，没有数据），`VPsublim` 的温度范围是 -273.15 至 -273.15；`EvaluateAntoine(1673.15 K)` 读出 -1.67e9（无意义）；临界温度、临界压力是空值。也就是说，**没有任何数据能把气态碳的化学势修正成固体碳的化学势**。
- **结论**：Gibbs 反应器用碳的理想气体 Gibbs 生成能（+671 kJ/mol）当它的化学势，碳"特别不稳定"，自由能最小化就把碳尽可能多地转成 CO 和 CH4：全部氧变成 CO、全部氢变成 CH4，数量只受氧和氢的限制，所以结果与温度无关。库里的碳（PR 物性包）不能直接用于石墨平衡。可行的方向都要用户决定（D14）：计划 §17.3 的两段式（先用转化反应器按限量反应物算 C + H2O → CO + H2，再用 Gibbs 反应器算气相平衡，未反应的碳旁路）；或者改库里碳的数据（写 `GibbsCoeffs` 等，没有试，也没有把握）。
- **脚本与输出**：`spikes/e10b_carbon_thermo.py`；`spikes/out/e10b_carbon_thermo_run1.txt`、`run2.txt`。
- **追加（E10c）**：`spikes/e10c_carbon_patch.py`：读 `Carbon.GibbsCoeffs`（`RealFlexVariable`），`Values` 是 (716850.0, -151.45, -0.0046174, 0, 0, 空值 ×5)：多项式 A + B·T + C·T² 里的 A 就是气态碳原子的生成焓 716.85 kJ/mol，所以 298.15 K 的值是 +671285，根因得到确认。**写这个数组被拒绝**：`com_error`，scode `-2147024891`（`E_ACCESSDENIED`），库组分的数据是只读的，要改只能新建假想组分（Hypo），没有试。不改的对照结果与 E10 相同。输出 `spikes/out/e10c_carbon_patch_run1.txt`。
- **追加（E10d，计划 §17.3 两段式的可行性证据，没有采用）**：提示词要求 Gibbs 反应器不能正确处理固体碳时不自行改用两段式，所以这个探针没有改任何正式模型，只回答“如果用户选了两段式，结果和参照值差多少”。`spikes/e10d_two_stage.py`：第一段转化反应器 CRV-1（带能流，气相出料写 1400 °C）：C + H2O → CO + H2，基准组分水、转化率 100%，反应集挂上；气相出料 CO 1035.0、H2 1035.0 kgmole/h，**液相出料是没反应掉的碳 1499.0 kgmole/h，旁路**，热负荷 85.76 MW；第二段 Gibbs 反应器 GBR-2（进料是第一段的气相，带能流，出口 1400 °C，没有碳），热负荷 -1.17 MW。**四条通过条件全部满足**：气相 CO 1012.6、H2 984.8、CH4 18.2、H2O 13.9、CO2 4.3 kgmole/h（参照 CO 1017、H2 981、CH4 22、H2O 11、CO2 3.5）；CO 收率 39.96%；气相 CO、H2 摩尔分率 0.4979、0.4842（参照 0.500、0.482）；碳元素守恒误差 3.6e-16；未反应的碳 1499.0 kgmole/h（参照 1491，相差 0.5%），从第一段的液相出料离开；总外供热 84.60 MW（参照约 85）。这也顺带验证了转化反应器带能流、气相出料规定出口温度的热模式。输出 `spikes/out/e10d_two_stage_run1.txt`、`e10d_two_stage_run1.hsc`。

### L26 E11：鲁棒性观察，同名创建、进程中断、弹窗、窗口隐藏（2026-10-08，0C 任务 4）

- **目的**：后面的错误码和恢复策略要按真实的异常和行为设计：同名对象怎么办；HYSYS 进程被结束时 Python 一侧拿到什么；哪些操作会弹窗卡住 COM 调用；窗口隐藏时建模和求解正常吗。
- **做法**：`spikes/e11_robustness.py`，四节，每个可能弄坏实例的实验都在新实例里做：**A** 同名对象（A1 Case、Basis、反应、物流；A2 操作和连接，5 个场景各一个新实例）；**B** 进程中断（主线程循环做 COM 调用，定时器 3 秒后 `taskkill /F /PID`：B1 两次调用之间，B2 `SaveAs` 期间，B3 `Open` 期间）；**C** 弹窗（关闭改过没保存的 Case、关闭新建没保存过的 Case、打开不存在的文件、打开损坏的文件、另存到不存在的目录、另存到含非法字符的文件名；窗口可见和隐藏各一遍；看门狗线程也处理不可见的对话框，120 秒的安全网结束进程）；**D** 窗口隐藏（`Visible` 为 False 与 True 各建一遍 E8 的模型）。逐步加实验，保留了几次运行的日志：A2、A3（同名不同类型）、B1、C1（第一次弹窗，含一次崩溃）、C3、C4、D1，`run5` 是最终的完整运行。
- **结果**：
  - **A 同名创建，各集合的行为不同**（第二次调用同一个名字）：
    | 调用 | 结果 |
    |---|---|
    | `SimulationCases.Add` | 再建一个 Case，Case 数 1 变 3（`name` 都是 `Case`） |
    | `ComponentLists.Add('CL-1')` | 返回 `CL-1`，之后组分列表里多出一个自动命名的 `Component List - 1` |
    | `FluidPackages.Add('Basis-1')` | **弹窗** "Duplicate Object Name: Basis-1 - Disallowed"，并且**再建**了 `Basis-2`、`Basis-3` |
    | `Components.Add('Methane')`、`ActiveReactions.Add`、`AssociateFluidPackage` | 幂等，没有变化 |
    | `Reactions.Add('Rxn-1', …)` | 再建一个，自动改名 `Rxn-2` |
    | `Reactants.Add('Methane')` | **重复加一行**，反应物 `['Methane', 'Methane']` |
    | `ReactionSets.Add('RxnSet-1')` | 再建一个，自动改名 `Set-1` |
    | `MaterialStreams.Add`、`EnergyStreams.Add` | 返回已有的那一股（幂等） |
    | `Operations.Add('ERV-100', 同类型)` | 返回已有的操作，不弹窗 |
    | `Operations.Add('ERV-100', 另一种类型)` | **弹窗** "Duplicate Object Name: ERV-100 - Creating New Object ERV-100_2"；四次运行里**三次**看门狗点了 OK 之后同一个对话框又接连弹出 6 至 8 次，随后 `com_error(-2147023170, 'The remote procedure call failed.')`，**HYSYS 进程崩溃**，之后每次调用都是 `-2147023174`（A 第一次运行、A2、A3）；**一次**（run5）点一次就顺利建出名叫 `ERV-100_2` 的 Gibbs 反应器 |
    | 与操作同名的物流 | 允许，两者并存 |
    | `reactor.Feeds.Add(同一股物流)` 第二次 | `com_error`，scode `-2147467259`（`E_FAIL`），`Feeds` 仍是一股 |
    | 同一股物流设为第二台反应器的 `VapourProduct` | `com_error`，scode `-2147024809`（`E_INVALIDARG`）；第二台反应器已建出 |
  - **B 进程中断**：B1 两次调用之间：循环成功读了 59 次，第 3.13 秒第一次失败，`com_error(-2147023174, 'The RPC server is unavailable.', None, None)`（0x800706BA）；之后所有调用（读物流、`app.name`、`SimulationCases.Count`、`case.Flowsheet`、`case.Close()`）都是同一个错误，**立刻**返回（0.00 秒），不会卡住。B2 `SaveAs` 期间：成功循环 89 轮，第 3.13 秒在 `SaveAs` 上失败，`com_error(-2147023170, 'The remote procedure call failed.', None, None)`（0x800706BE）。B3 `Open` 期间：同样的 `-2147023170`。中断之后新开的实例正常（Case 数 0），中断时在写的文件和被打开的文件都能被新实例重新打开，读回物流名一致（这一次没有留下打不开的文件，不能据此认为写文件是原子的）。结束进程之后 `tasklist` 里偶尔还能看到该进程几百毫秒，随后消失。
  - **C 弹窗**：关闭改过没保存的 Case、关闭新建没保存过的 Case：不弹窗，`Close()` 0.14 至 0.63 秒返回，没有保存确认。打开不存在的文件、打开损坏的文件（文本文件改名 `.hsc`）：不弹窗，0.01 至 0.25 秒后 `com_error`，内层 scode **`-2147024891`（`E_ACCESSDENIED`）**，所以这个错误号不一定是权限问题，和 8.3 短路径（H2）是同一个。另存到**不存在的目录**：**不报错**，0.04 秒返回，`case.FullName` 变成那个不存在的路径，文件根本没有写出。另存到含非法字符的文件名 `a<b>.hsc`：`com_error(-532462766, 'OLE error 0xe0434352')`（0xE0434352 是 .NET 异常），`FullName` 不变，实例还活着。窗口可见和隐藏两遍的结果完全相同，没有一个场景弹窗或卡住。
  - **D 窗口隐藏**：`Visible` 为 False 与 True，E8 的 710 °C 模型的摩尔分率最大差 0，热负荷都是 39989.2 kW；隐藏时含启动共 15.4 秒，可见 18.4 秒。
- **走过的弯路**：A 第一次运行里，同名不同类型的 `Operations.Add` 让实例崩溃，后面的步骤全部报 RPC 错误，才把 A2 拆成每个场景一个新实例；我一度怀疑是看门狗连续点击造成的，把同一个对话框窗口 5 秒内只点一次（A3），结果还是接连弹出 6 次再崩溃，说明是 HYSYS 自己在重试，不是点击太快；run5 同样的调用又一次顺利，所以这个崩溃是**偶发**的，不能依赖它出现或不出现。C 第一次运行里打开损坏文件 3.28 秒后进程崩溃，之后用同样的顺序（先关 Case、打开不存在的文件、再打开损坏的文件）可见和隐藏各重复了几遍都只是 `E_ACCESSDENIED`，没有再现，同样记为偶发。
- **结论**：创建类调用不能依赖 HYSYS 的同名行为（自动改名、再建、重复加行、弹窗、崩溃各有各的）：Backend 的所有“确保存在”都要先按 `Names` 查再决定；`Operations.Add` 绝不能对已存在的名字调用；`com_error` 的 `-2147023174` 和 `-2147023170` 都表示进程没了，要走恢复；`SaveAs` 之后必须读回文件；打开文件之前先检查文件存在。窗口隐藏不影响建模和求解。
- **脚本与输出**：`spikes/e11_robustness.py`；`spikes/out/e11_robustness_A2.txt`、`A3`、`B1`、`C1`、`C3`、`C4`、`D1`、`run5`。

### L27 E12：保存重开（2026-10-08，0C 任务 4）

- **目的**：保存已求解的 Case，关闭后重新打开，结果和求解状态是否保留。
- **做法**：`spikes/e12_save_reopen.py`：建 E8 的平衡反应器模型，710 °C 求解，取 710、600、回到 710 °C 的快照；`SaveAs` 到 `spikes/out/`，读 `FullName`；`Close()`；`Open` 重开，不重新求解就读快照并比对；重开后改 600 °C、再改回 710 °C 比对；写 650 °C 后 `Save()`（不带路径）；另开一个新实例打开同一个文件。运行 1 次（run1）。
- **结果**（`spikes/out/e12_save_reopen_run1.txt`）：
  - `SaveAs` 之前 `case.FullName` 是 `C:\\Windows\\system32\\e12_save.hsc`，`SaveAs` 用 0.16 秒之后变成新路径；`IsDirty` 为 False；旁边只多出 `.hsc` 本身。
  - 关闭后 Case 数 0；`Open` 用 1.70 秒，`FullName` 是新路径；**`app.ActiveDocument` 仍是 `None`**，Case 数 1。
  - 重开后**不重新求解**读到的 710 °C 快照与保存前一致（摩尔分率最大差 3.9e-8，总流量相对差 9.0e-8，热负荷相对差 1.8e-7），流程图状态 5 个对象全是 OK，求解器 `(CanSolve, IsSolving)` 是 `(True, False)`，也就是求解状态保留。
  - 重开后改成 600 °C：与保存前 600 °C 的快照一致（差 1.9e-12 量级）；再改回 710 °C 与保存前一致。
  - `Save()` 不带路径：写回当前路径，文件修改时间变了，`FullName` 不变，同目录多出 `.bk0` 备份；没有弹窗；另一个新实例打开这个文件读到 650 °C，状态 OK。
- **结论**：保存重开是可靠的：结果、求解状态、可重新求解都保留；`SaveAs` 之后以 `FullName` 读回路径，`ActiveDocument` 不可信（H2、H4）。**E12 通过。**
- **脚本与输出**：`spikes/e12_save_reopen.py`；`spikes/out/e12_save_reopen_run1.txt`、`e12_save_reopen_run1.hsc`（Case，172 KB）。

### L28 E13a：备选路线之一，界面自动化（2026-10-08，0C 任务 5）

- **目的**：用同一个最小任务（在空白 Case 里加一台转化反应器）考察界面自动化这条备选路线：HYSYS 的界面元素能不能被程序定位和操作；记是否可行、耗时、可重复性、结果能否由程序验证。
- **做法**：`pywinauto` 0.6.9（UIA 后端；`pip install pywinauto` 只装进虚拟环境，连带 `comtypes` 1.4.17、`six` 1.17.0，没有写进 `pyproject.toml`）。`spikes/e13a_ui_automation.py`：新实例，COM 建空白 Case（Basis 加 `EndBasisChange`），`pywinauto` 连接进程，导出主窗口控件树，按快捷键和面板操作，最后用 COM 读 `Operations.Names` 验证。运行 8 次，保留 run1、run2、run5、run7、run8；其余是我的脚本问题（`F12` 把面板关掉了；按名字找按钮找不到；`descendants()` 在 0.6.9 里不支持按自动化 ID 过滤）。
- **结果**：
  - run1：COM 新建的 Case 默认 `Visible` 为 False，主窗口只显示起始页，控件树只有 91 个元素（Ribbon、File 菜单，没有流程图）。
  - run2：`case.Visible = True` 之后主窗口标题变成 `e13a.hsc - Aspen HYSYS V15 - aspenONE`，控件树 676 个元素（导出用时 2.4 秒），出现 **Model Palette** 窗口，页签有 All、Dynamics & Control、External Model、Heat Transfer、Manipulator、Piping & Hydraulics、Pressure Changer、**Reactor**、Separator，还有名叫 `Flowsheet Case (Main) - Solver Active` 的流程图面板和 `Flowsheet/Modify` 功能区页签。`F12` 在 V15 里是开关 Model Palette，不是旧版的 Unit Ops 对话框。
  - run5：点开 Reactor 页签后，面板里的按钮**名字是空的**，但**自动化 ID 就是操作类型名**：`KineticReactor`、`PFR`、`ConversionReactor`、`EquilibriumReactor`、`GibbsReactor`、`YieldShift`、`CatalyticReformer`、`FCC`……
  - run7、run8：按自动化 ID `ConversionReactor` 找到按钮，`double_click_input()`，3 秒内（含脚本里固定等待的 3 秒）流程图里多了 `CRV-100`，COM 读回 `TypeName` 为 `conversionreactorop`，同时弹出属性窗口 `Conversion Reactor: CRV-100`。**两次都成功**。
- **四项**：是否可行：对“加一台反应器”可行；耗时：控件树导出 2.4 秒 + 点页签 1.5 秒 + 双击 3 秒，合计 5 至 8 秒（COM 的 `Operations.Add` 是 0.07 秒）；可重复性：2/2，但依赖桌面会话、窗口状态（`Visible`、Model Palette 是否打开、焦点），换一台没有桌面的机器就不行；结果能否由程序验证：能（COM 读 `Operations.Names`、`TypeName`）。连接进出料、挂反应集、写计量系数要在属性窗口里逐个操作，没有试，预计每一步都要找控件。
- **结论**：界面自动化可行但慢、脆弱，只作为 COM 做不到时的最后手段。
- **脚本与输出**：`spikes/e13a_ui_automation.py`；`spikes/out/e13a_ui_automation_run1.txt`、`run2`、`run5`、`run7`、`run8`。

### L29 E13b：备选路线之二，文件和脚本（2026-10-08，0C 任务 5）

- **目的**：同一个最小任务，考察文件路线（Case 导出成可读文本再导入）和脚本路线（脚本录制回放），并看脚本能不能写 COM 写不了的内部变量（反应集排序，H32）。
- **做法**：`spikes/e13b_file_script.py`，每个实验一个新实例。安装目录的 `Template\\*.scp` 是 HYSYS 自带的脚本文件，语法是 `Message "<对象路径>" "<消息>"`、`Specify "<对象路径>" ":<变量>.<ID>.<序号>" <数值>`、`SpecifyText`、`AttachObject`、`ResponseMessage Yes`、`Call`；类型库里有 `Application.PlayScript(文件)`。Q1：供体是 G0 的 Case，导出 Case XML（2.5 MB）和操作 XML（1.7 MB），导入一个已建好 Basis、反应和反应集的空白 Case（Case 级 `ApplyXML` 和操作级 `ApplyXMLForOperation`，flags 各用 0 和 128）。Q2：手写 `.scp`，用 `PlayScript` 在空白 Case 里加转化反应器，Case 隐藏和 `Visible = True` 各试，两种写法。Q3：用 `PlayScript` 写反应集排序。运行 4 次（run1 至 run4）。
- **结果**：
  - **Q1 文本路线**：Case 级 `ApplyXML(0 或 128, Case XML)`：0.4 至 0.5 秒返回 `None`，空白 Case 里**多出了 `CRV-100`（`conversionreactorop`）和 `Feed`、`Vap`、`Liq` 三股物流**，`Feed` 的 380 °C、2500 kPa、10000 kg/h 也恢复了，但**反应器没有进料、没有出料、没有反应集**（读 `Feeds.Names` 为空，读 `VapourProduct`、`ReactionSet` 抛 `E_FAIL`），流程图状态是 3 个 NotSolved 加 1 个 UnderSpecified，仍要用 COM 连接。导出用时 2.6 秒。操作级 `ApplyXMLForOperation('CRV-100', …)` 导入一个**不存在**的操作：`E_FAIL`，什么都没建（flags 0 和 128 一样）；run1 里在没有反应的空白 Case 上同样的调用先 `E_FAIL`，随后弹出 7 次 "Severe Error: You are low on memory. Please close some other applications."，`case.Close()` 抛 `-2147023170`，进程崩溃。
  - **Q2 PlayScript 建反应器**：Case 隐藏时，第 2 行 `Message "FlowSht.1" "EnterBuild"` 弹出 "Could Not Find Target specified on Line 2 in File …\\add_reactor.scp"，什么都没做，`PlayScript` 返回 `None`（不抛异常）。`case.Visible = True` 之后仿模板里加塔设备的写法（`EnterBuild`、`CreatePFDAndView`、`CreateFromPFD`）不弹窗但也没有建出反应器；改成仿模板里加物流的写法 `Specify "FlowSht.1" ":Selection.400" "ObjectType:ConversionReactorOpObject"` 加 `Message "FlowSht.1" "CreateAndView"`，**0.11 秒建出 `CRV-100`**。
  - **Q3 PlayScript 写反应集排序**：`Specify "FluidPkgMgr.300/RxnPackageManager.300/RxnSet.300(Conv-Set)" ":Index.400.<序号>" <值>`。Case 隐藏时第 1 行 "Could Not Find Target"，排序不变，出口甲苯 0.5000。**`case.Visible = True` 时成功**：排序 (0,1,2) 读回 `['0','1','2']`，出口甲苯摩尔分率 **0.5731**，各反应实际转化率 (12, 22.88, 7.814)；排序 (1,1,0) 读回 `['1','1','0']`，出口甲苯 **0.5456**，实际转化率 (10.56, 22.88, 12)。都与预测值一致（依次进行 (1−0.12)(1−0.26)(1−0.12) = 0.5731；第三个先算、前两个在剩下的 88% 上并行 0.5456）。**整个 HYSYS 窗口隐藏（`app.Visible = False`）、只让 Case 可见时同样成功**（run4）。
- **四项**：文本路线：可行（部分）、导出 2.6 秒加导入 0.5 秒、2/2（flags 0、128）、能（COM 读回）；脚本路线：可行（要求 Case 可见）、0.05 至 0.9 秒、排序 4/4 个实验成功（可见和窗口隐藏各 2 个）、建反应器 1 次成功（模板写法一次无效）、能（COM 和 XML 读回）。
- **结论**：**`PlayScript` 是一个真正能用的第二级通道**：能写 COM 和 XML 都写不了的内部变量，还能建对象。用法的坑：必须先 `case.Visible = True`；脚本失败不抛异常，只弹窗并返回 `None`，所以每次回放之后必须读回，看门狗要记下弹窗；脚本是纯 ASCII、CRLF 的文本文件。这解决了 H32 留下的问题：排序含义在我们自己的模型上验证了（和示例 Case 反推的一致），也有了设置的办法。按 D13 的答复 Recipe 仍然不设排序（保持默认并行），需要时再启用。
- **脚本与输出**：`spikes/e13b_file_script.py`；`spikes/out/e13b_file_script_run1.txt`、`run2`、`run3`、`run4`。

### L30 E0（部分）：LLM 连通性，网络已通，真实密钥的测试待用户运行（2026-10-08，0A 任务 4 补做）

- **目的**：用户答复 D1（阿里云百炼 Qwen，密钥环境变量 `DASHSCOPE_API_KEY`，三个模型）之后，补做 E0：从这台机器发出一次最小的 LLM 调用并得到回复；顺便看这台机器能不能访问百炼。
- **做法**：`spikes/e0_llm_connectivity.py`：只用标准库 `urllib`，从环境变量读密钥（只打印“已设置”和长度，错误文字里的密钥片段会被抹掉），依次试国内站 `dashscope.aliyuncs.com` 和国际站 `dashscope-intl.aliyuncs.com` 的 `/compatible-mode/v1/chat/completions`，再用三个模型各发一次“请只回复 OK”；`--capabilities` 另测主模型的 JSON 输出（`response_format`）和函数调用（`tools`）。
- **结果**：
  - **助手的进程读不到密钥**：进程、用户、机器三级环境变量里都没有 `DASHSCOPE_API_KEY`（用户设在自己终端的会话里）；通过终端工具新开的标签也不行（标签的 shell 集成加载失败，命令没有被输入）。所以没有发出过带真实密钥的请求。
  - **网络是通的**：用一个假密钥，国内站和国际站都在 0.34 秒、0.05 秒内返回 HTTP 401（`invalid_api_key`，带 `request_id`），说明这台机器能直连百炼的两个站点；国际站对“Incorrect API key”的回应也说明接口是 OpenAI 兼容的。
  - **探针的逻辑用本机的假接口检查过**（临时脚本，不入库）：200 的解析、404 的错误分支、JSON 输出、函数调用的 `tool_calls` 分支、401 的两站依次尝试，都符合预期；错误文字里没有出现密钥。
- **结论**：E0 的网络部分通过；真实密钥的调用没有做，**D1 不标完成**。需要用户在设了变量的终端里运行 `.\.venv\Scripts\python.exe spikes\e0_llm_connectivity.py --tag run1 --capabilities`，日志 `spikes/out/e0_llm_connectivity_run1.txt` 不含密钥。如果用户想让助手自己运行，需要用户自己把变量永久写进用户环境（在自己的终端里 `setx DASHSCOPE_API_KEY …`），助手不收密钥。
- **脚本与输出**：`spikes/e0_llm_connectivity.py`。
