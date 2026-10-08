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
| H4 | 保存、另存、关闭 | 已确认 | `case.SaveAs(path)`：写出文件（只有一个流体包的 Case 约 141 KB），之后 `case.FullName` 变成新路径；`case.Close()`；`app.SimulationCases.Open(path)` 重新打开，Basis（流体包、物性包、组分）都在 | `spikes/e4_basis.py` run4，`spikes/e4b_property_package.py`，2026-10-08，输出 `spikes/out/e4_basis_run4.txt`、`e4b_property_package_run2.txt` | 确认的是 `SaveAs(path)`、`Close()`、`Open(path)`；`Save()`、`SaveAs2`、`SaveCopyAs` 没测，Backend 只会用前三个。路径必须是长路径（H2）。物性包没设好就保存，重开时会弹模态对话框 "Could not load the Property Package for Fluid Package ..."，`Open` 卡住（E4 run2）。`Close()` 和 `Quit()` 不弹保存确认（E2b）。 只测了关闭：`case.Close()` 0.2 秒返回，**没有保存确认弹窗**，Case 改过（`IsDirty` 为 True）也一样；`app.Quit()` 在 Case 打开着、改过或没改过时都不弹窗，实例 0.5 秒内退出。注意 `IsDirty` 在刚打开、没改过的 Case 上也是 True，不能用它判断"有没有改过"。保存另存留给 E4、E12。 计划假设：`Save`、`SaveAs`、`Close`。探针 E4、E12 类型库（2026-10-08，未运行验证）：`SimulationCase.Save()`、`SaveAs(...)`、`SaveAs2`、`SaveCopyAs`、`Close()`、`IsDirty`。 |
| H5 | Basis 修改事务 | 已确认 | 新 Case 一开始就在 Basis 修改状态；流体包配好后 `manager.EndBasisChange()`；之后要改 Basis 用 `manager.StartBasisChange()`（`IsChangingBasis` 变 True），改完再 `EndBasisChange()` | `spikes/e6_reaction.py` run4、`spikes/e6b_keq_source.py` run2，2026-10-08，输出 `spikes/out/e6_reaction_run4.txt`、`e6b_keq_source_run2.txt` | **建反应和反应集不需要在 Basis 修改状态里**：`EndBasisChange()` 之后直接 `Reactions.Add` 也成功（E6 run4）；`StartBasisChange()` 在 Basis 结束后可用。 `CanEndBasisChange` 为 False 时调用 `EndBasisChange()` 抛 `com_error`（E_FAIL）。`CanEndBasisChange` 要求流体包已经有物性包和组分列表。**已经结束 Basis 之后再改 Basis（比如加反应）要不要先 `StartBasisChange()`，留给 E6。** 计划假设：`BasisManager.StartBasisChange`、`EndBasisChange`。计划状态：官方文档确认（V7.3 版）。探针 E4 类型库（2026-10-08，未运行验证）：`BasisManager.StartBasisChange()`、`EndBasisChange()`、`IsChangingBasis`、`CanEndBasisChange`。 |
| H6 | 读取流体包、物性包、组分 | 已确认 | `fps = case.BasisManager.FluidPackages`；`fps.Count`、`list(fps.Names)`、`fps.Item(i)`（下标从 0 开始）；`fp.name`、`fp.PropertyPackageName`、`fp.Components.Count`、`list(fp.Components.Names)`；`case.Flowsheet.FluidPackage.name` | `spikes/e2_read_write.py`，2026-10-08，输出 `spikes/out/e2_read_write_run1.txt`、`e2_read_write_run2.txt` | 示例 Synthesis Gas Production：流体包名 `Basis-1`，`PropertyPackageName` 读出 `PengRobinson`（没有空格和连字符），组分 `['Methane', 'H2O', 'CO', 'CO2', 'Hydrogen', 'Nitrogen', 'Oxygen']`，物流的组成向量按这个顺序排。 计划假设：`FluidPackages.Item(i)`、`PropertyPackageName`、`Components`。计划状态：官方文档确认（V7.3 版）。探针 E2 类型库（2026-10-08，未运行验证）：`BasisManager.FluidPackages`（集合）；`FluidPackage.PropertyPackageName`（可读写）、`Components`、`ReactionPackage`、`ComponentList`。 |
| H7 | 新建流体包并指定物性包 | 已确认 | `fp = manager.FluidPackages.Add("Basis-1")`；`fp.ComponentList = component_list`；`fp.PropertyPackageName = "pengrob"`。读回 `fp.PropertyPackageName` 得 `Peng-Robinson`，`fp.PropertyPackage.TypeName` 得 `pengrob` | `spikes/e4_basis.py` run4，`spikes/e4b_property_package.py`，2026-10-08，输出 `spikes/out/e4_basis_run4.txt`、`e4b_property_package_run2.txt` | **设置时必须用物性包的内部名 `pengrob`（它的 `TypeName`）**。界面名 `Peng-Robinson`、读到的名字、`PengRobinson`、`PR`、`ppkg_PR`、`5891` 等 10 种写法都抛 `E_INVALIDARG`（-2147024809），`FluidPackages.Add(name, Type)` 的 `Type` 传 5891、`"ppkg_PR"`、`"Peng-Robinson"` 等也不会设上物性包（e4b run1、run2）。读和写用的名字不同。没有组分列表时 `CanEndBasisChange` 为 False。其他物性包的内部名没有试。 计划假设：`FluidPackages.Add(...)`。探针 E4 类型库（2026-10-08，未运行验证）：`FluidPackages.Add(name, Type)`；`FluidPackage.PropertyPackageName` 可写；`PropertyPackageType_enum` 有 `ppkg_PR=5891`。 |
| H8 | 添加库组分 | 已确认 | V15 里组分挂在组分列表上：`component_list = manager.ComponentLists.Add("CL-1")`；`component_list.Components.Add("Methane")` 返回 `Component`；读 `list(component_list.Components.Names)`；再 `fp.ComponentList = component_list`，`fp.Components.Names` 随之有内容 | `spikes/e4_basis.py` run4，`spikes/e4b_property_package.py`，2026-10-08，输出 `spikes/out/e4_basis_run4.txt`、`e4b_property_package_run2.txt` | 库里的名字大小写不敏感，返回规范名（`methane` 得 `Methane`）；`Add` 一个已有的组分（含别名 `H2` 得 `Hydrogen`）不报错也不重复。**不接受**：分子式（`CH4`、`C7H8`、`C6H6`）、`Water`、`CarbonMonoxide`、`CarbonDioxide`、`C1`、`pXylene`、`PXYLENE`、`C`、`Graphite`，抛 `E_FAIL`。规范名见"组分规范名"一节。 计划假设：`Components.Add(name)`，以及库中的规范名。探针 E4 类型库（2026-10-08，未运行验证）：`FluidPackage.Components.Add(name, Type)`；`Component` 有 `IsSolid`、`Formula`、`CAS_Number`。 |
| H9 | 创建转化反应（计量系数、基准组分、转化率） | 已确认 | `reaction = manager.ReactionPackageManager.Reactions.Add("Tol-Disp", "conversionrxn")` 返回 `ConversionReaction`；`reactant = reaction.Reactants.Add("Toluene")` 返回 `Reactant`；`reactant.StoichiometricCoefficientValue = -2.0`（负为反应物，正为产物）；`reaction.BaseComponent = fp.Components.Item("Toluene")`；`reaction.Conversion = 50.0`（百分数）；`reaction.ReactionPhase = 0`（气相） | `spikes/e6_reaction.py` run4、`spikes/e6b_keq_source.py` run2，2026-10-08，输出 `spikes/out/e6_reaction_run4.txt`、`e6b_keq_source_run2.txt` | **`Type` 必须是反应的内部类型名**：`conversionrxn`、`equilibriumrxn`、`kineticrxn`。界面名 `Conversion`、类名 `ConversionReaction`、整数 0 至 3、省略 `Type`，都抛 `E_FAIL`。**分数计量系数能写**（0.24 读回 0.24，此时 `BalanceErrorValue` 非零，是质量不守恒的提示）。调用 `BalanceStoichiometry()`、另存重开之后读回，最后一个组分的系数被微调了，使质量守恒（甲苯歧化的对二甲苯：1.0 变 1.00005；SMR 的氢：3.0 变 2.9996；具体是哪一步改的没有单独验证），读回比对要留容差（1e-3）。`ReactionPhase` 的默认值：转化反应 5（合并相），平衡反应 0（气相）。`Reactions.Remove(name)` 可用。新建的反应 `HeatOfReactionValue` 读取抛 `E_FAIL`（重开后也是），要等被反应器用上再说。重开后反应的设置都在。 E3 实测（只读）：转化反应的 `TypeName` 是 `conversionrxn`；读到的结构是 `Reactants`（负为反应物、正为产物）、`BaseComponent`、`Conversion`（百分数）。写入路径等 0B。 计划假设：无。计划状态：未知。探针 E6 类型库（2026-10-08，未运行验证）：`ReactionPackageManager.Reactions.Add(name, Type)` 返回 VARIANT；`ConversionReaction`：`Reactants`（集合，有 `Add`）、`Reactant.StoichiometricCoefficientValue`（可写）、`BaseComponent`（可写）、`Conversion`（double，可写）、`ReactionPhase`、`BalanceStoichiometry()`。 |
| H10 | 创建平衡反应并指定 Keq 来源（Gibbs 自由能、固定值、随温度变化） | 部分确认 | `reaction = ...Reactions.Add("SMR", "equilibriumrxn")` 返回 `EquilibriumReaction`；计量系数同转化反应。**Keq 来源 `LnKSource` 的实际取值：1 = Ln(K) 公式，2 = Gibbs 自由能（新建时的默认值），3 = 固定 K，4 = K–T 表。**固定 K：`reaction.LnKSource = 3`，`reaction.EquilibriumConstant = 12.5`，读回 12.5；改回 `LnKSource = 2` 可用 | `spikes/e6_reaction.py` run4、`spikes/e6b_keq_source.py` run2，2026-10-08，输出 `spikes/out/e6_reaction_run4.txt`、`e6b_keq_source_run2.txt` | **写 0 被静默忽略**（读回还是原值）；类型库枚举的名字（`eqrxn_Gibbs=0`、`eqrxn_FixedK=2`、`eqrxn_Table=3`、`eqrxn_FixedExtent=4`）和实际取值对不上，**不要用枚举名**。映射的依据：`Support\equirxn.rdf` 里界面分组的可见范围（Ln(K) 公式 1，Gibbs 自由能 2，固定 K 3，K–T 表 4），加上实测（新建默认读出 2，示例里用 K–T 表的反应读出 4，写 1 至 4 都读回原值）。写入任何一个明确的来源都会把 `AutoDetect` 变成 False。默认值：`Basis` 1（`rbActivityBasis`），`ReactionPhase` 0，温度范围 -273.15 至 3000 °C。**只确认了创建和设置；HYSYS 求解时是否真的按 Gibbs 自由能算 K，要看反应器的结果（E8）。** E3 实测（只读）：平衡反应的 `TypeName` 是 `equilibriumrxn`；`LnKSource` 读出的数字和类型库枚举对不上（K–T 表读出 4），要用 Gibbs 来源的参考 Case 核对。写入路径等 0B、0C。 计划假设：无。计划状态：未知。探针 E8 类型库（2026-10-08，未运行验证）：`EquilibriumReaction`：`LnKSource`（`eqrxn_Gibbs=0`、`eqrxn_LnKEquation=1`、`eqrxn_FixedK=2`、`eqrxn_Table=3`、`eqrxn_FixedExtent=4`）、`EquilibriumConstant`、`LnKEquationA/B/C/DParameter`、`MinTemperatureValue`、`MaxTemperatureValue`、`Basis`、`ReactionPhase`。 |
| H11 | 创建反应集、加入成员、挂到流体包 | 部分确认 | `rset = manager.ReactionPackageManager.ReactionSets.Add("Conv-Set")` 返回 `ReactionSet`（`TypeName` 为 `rxnset`，不需要 `Type`）；`rset.ActiveReactions.Add("Tol-Disp")`（按名字）；`rset.AssociateFluidPackage(fp)` | `spikes/e6_reaction.py` run4、`spikes/e6b_keq_source.py` run2，2026-10-08，输出 `spikes/out/e6_reaction_run4.txt`、`e6b_keq_source_run2.txt` | **`AssociateFluidPackage` 才是"加入流体包"**：`Add` 之后、`AssociateFluidPackage` 之前，`fp.ReactionPackage.ReactionSets.Names` 里没有这个集合，调用之后才有。反应集和成员重开后都在。**反应集挂到反应器上之后的求解效果还没验证**（E7）。 E3 实测（只读）：反应集 `TypeName` 是 `rxnset`；成员是 `ActiveReactions.Names` 和 `InactiveReactions.Names`；与流体包的关联体现为出现在 `fp.ReactionPackage.ReactionSets.Names` 里。怎么加成员、怎么挂到流体包等 0B。 计划假设：无。计划状态：未知。探针 E6 类型库（2026-10-08，未运行验证）：`ReactionPackageManager.ReactionSets.Add(name, Type)`；`ReactionSet.AssociateFluidPackage(fluidPkg)`；`ActiveReactions` 和 `InactiveReactions`（`Reactions` 集合，加成员的方式待查）；`Operations`、`SolverMethod`。 |
| H12 | 新建物流和能流 | 部分确认 | `stream = flowsheet.MaterialStreams.Add("name")` 返回 `ProcessStream`（只给名字，不给 `Type`）；`flowsheet.MaterialStreams.Item("name")` 按名字取回；`flowsheet.MaterialStreams.Remove("name")` 删除；`Count`、`Names` 随之变化 | `spikes/e2_read_write.py`，2026-10-08，输出 `spikes/out/e2_read_write_run1.txt`、`e2_read_write_run2.txt` | 只在已有流体包的已求解 Case 里试过物流：新物流的组成向量长度是 7，与该 Case 唯一的流体包一致。能流 `EnergyStreams.Add` 没测，空白 Case 里建物流留给 E5。 计划假设：`MaterialStreams.Add(name)`、`EnergyStreams.Add(name)`。探针 E5 类型库（2026-10-08，未运行验证）：`Flowsheet.MaterialStreams`、`Flowsheet.EnergyStreams`（都是 `Streams`，有 `Add(name, Type)`）。 |
| H13 | 写入 T、P、流量 | 已确认 | 写：`stream.Temperature.SetValue(value, "C")`、`stream.Pressure.SetValue(value, "kPa")`、`stream.MolarFlow.SetValue(value, "kgmole/h")`；读：`GetValue(unit)`。单位字符串见 H29。写入后立即读回一致 | `spikes/e2_read_write.py`，2026-10-08，输出 `spikes/out/e2_read_write_run1.txt`、`e2_read_write_run2.txt` | 写入用时 0.02 秒。写入不认识的单位抛 `com_error`（`E_FAIL`，`-2147467259`），原值不变，不会静默写错。`.Value` 属性是 HYSYS 的内部单位（C、kPa、kgmole/s、kg/s），**不要用**，一律 `GetValue(unit)`、`SetValue(value, unit)`。 计划假设：`Temperature.SetValue(value, unit)` 等。计划状态：官方文档确认（V7.3 版）。探针 E2、E5 类型库（2026-10-08，未运行验证）：`RealVariable.SetValue(val: double, unit: VARIANT[opt])`、`GetValue(unit)`、`Value`；`ProcessStream` 的 `Temperature`/`TemperatureValue`、`Pressure`/`PressureValue`、`MolarFlow`/`MolarFlowValue`、`MassFlow`、`StdLiqVolFlow`。 |
| H14 | 写入组成 | 部分确认 | `stream.ComponentMolarFraction.Values = (0.9, 0.1, 0, 0, 0, 0, 0)`，或 `.SetValues(tuple)`、`.SetValues(tuple, "")`，三种写法都成功；读 `.Values`、`ComponentMolarFractionValue`（元组）；`ComponentMolarFlow.GetValues("kgmole/h")` | `spikes/e2_read_write.py`，2026-10-08，输出 `spikes/out/e2_read_write_run1.txt`、`e2_read_write_run2.txt` | 条件：在已求解的示例 Case 里新建的物流上，7 个组分，写的是摩尔分数且和为 1。向量顺序是流体包的组分顺序。写 T=25 °C、P=1000 kPa、F=100 kgmole/h 之后闪蒸立即完成：`VapourFractionValue` 0.9029，`MassFlow` 1624.0 kg/h，分组分摩尔流量 (90, 10, 0, ...)。空白 Case 里重新验证留给 E5。 计划假设：`ComponentMolarFraction.Values = [...]`。计划状态：读取有公开示例，写入待验证。探针 E5 类型库（2026-10-08，未运行验证）：`ProcessStream.ComponentMolarFraction`（`RealFlexVariable`：`Values`、`SetValues(val, unit)`、`GetValues(unit)`）和 `ComponentMolarFractionValue`。 |
| H15 | 新建反应器 | 未测试 |  |  | E3 实测（只读）：转化反应器 `TypeName` 是 `conversionreactorop`，平衡 `equilibriumreactorop`（Gibbs 推测 `gibbsreactorop`，没有样本）。`Operations.Add(name, Type)` 没有调用过，等 0B。 计划假设：`Operations.Add(name, typeName)`，三种反应器的 `typeName` 通过反向探测获得。探针 E3、E7 类型库（2026-10-08，未运行验证）：`Flowsheet.Operations(OperClassOrType[opt]).Add(name, Type)`。反应器接口：`ConversionReactor`、`EquilibriumReactor`、`GibbsReactor`，另有 `KineticReactor`、`PFReactor`、`YieldReactor`。`Type` 的取值（字符串还是枚举）待 E3。 帮助文件 `xhysys.chm`（`general/operation_types.htm`）列出 `Operations.Add` 能用的类型字符串，反应器是 `ConversionReactorOp`、`EquilibriumReactorOp`、`KineticReactorOP`、`GibbsReactorOp`、`ReactorOP`、`PFRReactorOp`（界面名依次为 Conversion Reactor、Equilibrium Reactor、Kinetic Reactor、Gibbs Energy Minimization Reactor、Reactor、Plug Flow Reactor），并说明"These types are used in the Add of the Operations"；示例 `Flowsheet.Operations.Add "Pump1", "PumpOp"`（`general/adding_an_object_to_a_flowsheet.htm`）。这是文档，没有运行过；运行时读回的 `TypeName` 是全小写。 |
| H16 | 反应器连接与配置（进出料、能流、反应集、压降、Gibbs 模式） | 部分确认 | 只读，见"对象模型速查"：`op.Feeds`（`Names`、`Item(i)`）、`op.VapourProduct`、`op.LiquidProduct`、`op.EnergyStream`（没连接时读取抛 `com_error`）、`op.ReactionSet`、`op.PressureDrop.GetValue("kPa")`、`op.HeatFlow.GetValue("kW")`；出口温度规定在气相出料物流的 `Temperature` 上 | `spikes/e3_reverse_probe.py`，2026-10-08，输出 `spikes/out/e3_reverse_probe_sample.txt` | 条件：只读，在示例的转化和平衡反应器上。写入（连接进出料、挂反应集、规定出口温度）没有试，等 0B。Gibbs 的类型选项没有样本。 计划假设：无。计划状态：未知。探针 E7 至 E9 类型库（2026-10-08，未运行验证）：三种反应器共有：`Feeds`（`Attachments`，`Add(Item)`）、`VapourProduct`、`LiquidProduct`、`EnergyStream`（可写，`ProcessStream*`）、`PressureDropValue`（可写）、`ReactionSet`（可写）、`HeatFlowValue`（可写）。Gibbs 另有 `ReactorType`（`gr_NoReactions=0`、`gr_SpecdRxnsOnly=2`、`gr_GibbsRxnsOnly=3`）、`InertSpeciesValue`、`FractionSpecifiedValue`、`FixedSpecificationValue`。接口里没有出口温度成员。 |
| H17 | 求解控制 | 已确认 | `solver = case.Solver`；`solver.CanSolve = False` 挂起，`solver.CanSolve = True` 释放；读 `solver.CanSolve`、`solver.IsSolving`、`solver.Mode`（0 为稳态） | `spikes/e2_read_write.py`，2026-10-08，输出 `spikes/out/e2_read_write_run1.txt`、`e2_read_write_run2.txt` | **挂起有效：** `CanSolve=False` 时改进料流量，出料流量保持 475.36 kgmole/h 不变。**释放时同步求解：** `CanSolve=True` 这一句用 0.46 秒返回，返回后 `IsSolving` 已是 False，出料已更新到 523.26 kgmole/h，不需要轮询。`CanSolve` 为 True 时每次写入都会立刻重算（写进料压力、流量后出料立即变，热负荷 6558.8 kW 随进料温度变到 6544.7 kW）。 计划假设：`Solver.CanSolve`。计划状态：官方文档确认（V7.3 版）。探针 E2 类型库（2026-10-08，未运行验证）：`Solver.CanSolve`（可读写）、`IsSolving`、`Mode`；`SimulationCase.Solver`。 |
| H18 | 变量是否已知，是规定值还是计算值 | 已确认 | `variable.IsKnown`、`variable.State`、`variable.CanModify`：规定值 `State=1`、`CanModify=True`，计算值 `State=0`、`CanModify=False`，没有值时 `IsKnown=False` | `spikes/e2_read_write.py`、`spikes/e3_reverse_probe.py`，2026-10-08 | E3 补上了计算值：出料的 P 和流量 `State` 0、`CanModify` False，能流热负荷同。注意没有规定的变量 `State` 也是 1，判断"有没有值"只能靠 `IsKnown`。 实测：没有规定的变量 `IsKnown` 为 False；写入之后为 True。进料温度 `State` 为 1（vsSpecified）、`CanModify` 为 True。**注意：没有规定的变量 `State` 也是 1，所以判断"有没有值"只能靠 `IsKnown`，不能靠 `State`。** 未测：计算出来的变量（`State` 应为 0，`CanModify` 应为 False），留给 E3 在反应器出料上测。 计划假设：`IsKnown`、`State`。计划状态：官方文档确认（V7.3 版）。探针 E2 类型库（2026-10-08，未运行验证）：`RealVariable.IsKnown`、`State`（`vsCalculated=0`、`vsSpecified=1`、`vsDefaultedValue=2`、`vsSpecifiedOutside=4`、`vsDefaultOutside=5`）、`CanModify`。 |
| H19 | 对象状态文本（未求解、欠规定等提示） | 未测试 | | | 计划假设：无。计划状态：未知。探针 E7 |
| H20 | 读取结果（T、P、流量、组成、分组分流量、热负荷） | 已确认 | 物流同前；反应器按组分的进出量：`op.ComponentTotalIn.GetValues("kgmole/h")`、`ComponentTotalReacted`、`ComponentTotalOut`（Gibbs 是 `ComponentTotalFeed`、`ComponentTotalProduct`），组分顺序见 `op.ComponentName.Values`；`op.HeatFlow.GetValue("kW")`；转化率 `RxnPercentConversionValue`，平衡常数 `EqConstantValue`、`RxnExtentValue` | `spikes/e2_read_write.py`、`spikes/e3_reverse_probe.py`，2026-10-08 | 转化和平衡反应器已实测；Gibbs 没有样本。`ComponentTotal…` 的 `…Value` 属性是 kgmole/s，一律用 `GetValues("kgmole/h")`。 物流和热负荷已实测（转化反应器 Reformer 热负荷读出 6558.76 kW）。反应器自己的结果（分组分进出量、转化率、平衡常数）留给 E3。 计划假设：`GetValue(unit)`、`ComponentMolarFraction.Values`。计划状态：基本读取有官方文档，分组分流量和热负荷待验证。探针 E7 类型库（2026-10-08，未运行验证）：反应器：`ComponentTotalInValue`、`ComponentTotalOutValue`、`ComponentTotalReactedValue`（转化、平衡）；`ComponentTotalFeedValue`、`ComponentTotalProductValue`（Gibbs）；`RxnPercentConversionValue`、`HeatFlowValue`。物流：`ComponentMolarFlow`、`ComponentMassFlow`。 |
| H21 | 固体碳组分及其在 Gibbs 反应器中的行为 | 部分确认 | 库里有 `Carbon`：`components.Add("Carbon")` 成功，读回规范名 `Carbon`，`IsSolid` 为 True，`Formula` 为 `C` | `spikes/e4_basis.py` run4，`spikes/e4b_property_package.py`，2026-10-08，输出 `spikes/out/e4_basis_run4.txt`、`e4b_property_package_run2.txt` | 只验证了"库里有固体碳"。含固体的物流闪蒸、Gibbs 反应器里碳是否作为固体参与平衡，留给 E10。 计划假设：库组分 `Carbon`。计划状态：未知。探针 E10 类型库（2026-10-08，未运行验证）：`Component.IsSolid` 可以读，库里能不能加固体碳要实测。 |
| H22 | 空值的表示方式 | 已确认 | 空值是 **-32767.0**：`variable.Value`、`GetValue(unit)`、组成向量里的每个元素都是 -32767.0；同时 `IsKnown` 为 False（组成是全 False 的元组） | `spikes/e2_read_write.py`，2026-10-08，输出 `spikes/out/e2_read_write_run1.txt`、`e2_read_write_run2.txt` | 对空值调 `GetValue("C")` 也返回 -32767.0，不做单位换算，所以不能靠数值是否合理判断，要先看 `IsKnown`。后面"结果是否存在"一律用 `IsKnown`，-32767.0 只作为兜底校验。 计划假设：约定的哨兵值。探针 E2 |
| H23 | 模态弹窗对 COM 调用的阻塞 | 部分确认 | 阻塞：`SimulationCases.Open` 在弹窗出现时不返回。检测：枚举 HYSYS 进程的顶层窗口，类名 `#32770` 的是对话框，读它的 `Static` 子控件得到文字（`spikes/_common.py` 的 `windows_of`、`child_texts`、`watch`）。关闭：对 OK 按钮发 `BM_CLICK`（`win32gui.PostMessage`） | `spikes/find_ref_case.py`，2026-10-08，输出 `spikes/out/find_ref_case_scan.txt` | 只见过一种弹窗：打开用到 Aspen Properties 的 Case（Green Ammonia Process）时的 "To use Aspen Properties in HYSYS, at least one databank should be installed..."。`BM_CLICK` 能关闭对话框；阻塞的调用在对话框关闭后能否返回没测到。计划假设：无。探针 E11 |
| H24 | 降级通道：内部变量访问、脚本回放 | 未测试 | | | 计划假设：无。计划状态：未知。仅在 E6 至 E9 受阻时探测 类型库（2026-10-08，未运行验证）：`Application.BackDoor(obj[opt])` 返回 `BackDoor`：`BackDoorVariable(moniker)`、`BackDoorRealVariable`、`BackDoorTextVariable`、`BackDoorVariables(monikers)`、`SendBackDoorMessage(message)`；`Application.PlayScript(ScriptFileName)`。 帮助文件 `xhysys.chm` 里 `PlayScript` 只有一句"plays the specified HYSYS script"，`BackDoor` 只有成员签名，都没有 moniker 的写法和脚本格式的说明。 |
| H25 | 组分库的枚举或检索（按名称、分子式查到规范名） | 部分确认 | 按名称：`Components.Add(name)`（大小写不敏感，返回规范名）。没有找到枚举或检索组分库的接口 | `spikes/e4_basis.py` run4，`spikes/e4b_property_package.py`，2026-10-08，输出 `spikes/out/e4_basis_run4.txt`、`e4b_property_package_run2.txt` | 分子式不能当名字用（`CH4`、`C7H8` 都失败）；类型库里 `Components`、`ComponentList(s)`、`HypoComponents` 都没有搜索方法。遇到新组分时，只能让 LLM 给出候选英文名，逐个 `Add` 试，失败的丢弃。 计划假设：无。计划状态：未知。探针 E4 |
| H26 | Case 导出为可读文本并重新导入 | 部分确认 | 导出：`case.ProvideXMLForCase(flags)`（flags 0 或 1）得到 6.5 或 6.1 MB 的字符串，`case.GetXMLForCase()` 0.47 MB，`case.ProvideXMLForOperation(name, flags)` 2.4 MB。导入没有试 | `spikes/e3_reverse_probe.py`，2026-10-08，输出 `spikes/out/e3_reverse_probe_sample.txt` | **XML 里没有反应和反应集的定义**：'Stoich'、'rxnset'、'ReactionSet'、'LnK'、'Rxn-4' 出现 0 次，只有反应器上引用反应名的 `ConReactionInfo`。所以这条路线不能创建或修改反应，只能改反应器等对象的设置，在"创建反应的线索"里排在最后。 计划假设：无。计划状态：未知。探针 E13 类型库（2026-10-08，未运行验证）：`SimulationCase.GetXMLForCase()`、`ProvideXMLForCase(flags)`、`ApplyXML(flags, sXML)`、`ApplyXMLFromFile(flags, filePath)`、`ProvideXMLForOperation(tagName, flags)`、`ApplyXMLForOperation(tagName, flags, sXML)`；`XMLOptionFlags_enum` 的取值见 `typelib_enums.txt`。这是文件路线最有希望的入口，E13 再测。 |
| H27 | 同时运行多个实例；按进程号管理实例 | 已确认 | `Dispatch("HYSYS.Application.NewInstance")` 新开进程；连接前后的 `tasklist` 差集得到新进程号；`app.Quit()` 只结束该实例；`taskkill /PID <pid> /T /F` 强制结束 | `spikes/e1_connect.py` run3、run5、run7，2026-10-08 | 释放 COM 引用不会让实例退出（run6）。两个实例的窗口标题相同，只能靠进程号区分。非计划内的能力，Backend 的会话管理会用到 |
| H28 | 早绑定（gen_py 包装）与类型库 | 已确认 | `gencache.EnsureModule("{DFC1C58B-AE9F-11CF-8EB2-0020AF119B90}", 0, 3, 2)` 生成包装；`pythoncom.LoadRegTypeLib(guid, 3, 2, 0)` 读类型信息 | `spikes/e1_connect.py` run8、run9，2026-10-08 | 包装缓存在 `%TEMP%\gen_py\3.12`。属性名区分大小写；生成之后 `Dispatch` 也返回包装类。集合 `Item()` 返回 `IDispatch`，是否需要 `CastTo` 待 E3 |
| H29 | 单位字符串 | 已确认 | 温度 `C`、`K`、`F`、`R`；压力 `kPa`、`bar`、`psia`、`atm`、`MPa`；摩尔流量 `kgmole/h`、`lbmole/h`、`gmole/s`；质量流量 `kg/h`、`lb/hr`、`kg/s` | `spikes/e2_read_write.py` run1，2026-10-08 | 不认识的：`degC`、`kmol/h`、`t/h`、`foo`（`GetValue`、`SetValue` 都抛 `com_error` `E_FAIL`）。摩尔流量的单位是 `kgmole/h`，不是 `kmol/h`。体积流量、能量单位等没测 |
| H30 | 同时写入后的求解语义 | 已确认 | 见 H17：`CanSolve=True` 时每次写入同步重算，`CanSolve=False` 时不算，释放时同步算完 | `spikes/e2_read_write.py` run2，2026-10-08 | 没有未收敛状态的样本；不收敛时 `IsSolving`、对象状态文本怎么表现，留给 E7 |

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

**`ReactionSets` 和 `ReactionSet`（类型库）。**

- 取得方式有两条：`Case.BasisManager.ReactionPackageManager.ReactionSets`，或 `FluidPackage.ReactionPackage.ReactionSets`。
- `ReactionSet`：`AssociateFluidPackage(fluidPkg: FluidPackage*)`（把反应集挂到流体包）、`ActiveReactions` 和 `InactiveReactions`（都是 `Reactions` 集合，**怎么往里加反应不知道**）、`Operations`（`Attachments`，用了这个反应集的操作）、`SolverMethod`（可写，`ReactionSetSolverMethodEnum_enum`：rs_RateIteration=0、rs_RateIntegration=1、rs_AutoSelected=2、rs_RBNewton1=3）、`TraceLevel`、`UsePreviousSolution` 等求解选项。
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
- **Gibbs 反应器没有实测**（示例里没有）。`ReactorType` 的数字与界面选项的对应要等用户的参考 Case。

**三种反应器共有（类型库）。**

- 进料：`Feeds`（`Attachments`，`Add(Item)`）。出料：`VapourProduct`、`LiquidProduct`、`EnergyStream`，都是可写的 `ProcessStream*`（另有 `…Var` 形式的 `ObjectVariable`）。
- `ReactionSet`（可写，`ReactionSet*`）；压降 `PressureDropValue`（可写，double）；热负荷 `HeatFlowValue`（可写，double）；`VesselType`（`HeatCoolEnum_enum`：Cooling=0、Heating=1）；`Volume`、`LiquidVolume`、`LiquidLevel`；`FluidPackage`（可写）；`CreateFluid()`。
- **三种反应器的类型库接口里都没有"出口温度"成员。** 出口温度很可能规定在出料物流或能流上，待 E3 确认。

**各自特有。**

- 转化反应器：按反应分行的数组：`rxnName`、`RxnBaseCmpName`、`ConversionValue`（可写）、`RxnPercentConversionValue`、`HeatOfReactionValue`；按组分分行：`ComponentName`、`ComponentTotalInValue`、`ComponentTotalReactedValue`、`ComponentTotalOutValue`。
- 平衡反应器：`rxnName`、`RxnBaseCmpName`、`RxnPercentConversionValue`、`EqConstantValue`、`RxnExtentValue`、`HeatOfReactionValue`，以及同样的 `ComponentTotal…`；`EquilibriumConstantParameterArray`、`EquilibriumTemperatureApproachParameterArray`、`EquilibriumFractionalApproachParameterArray`（可写）。
- Gibbs 反应器：`ReactorType`（可写，`GibbsReactorType_enum`：gr_NoReactions=0、gr_SpecdRxnsOnly=2、gr_GibbsRxnsOnly=3）；`ComponentName`、`ComponentTotalFeedValue`、`ComponentTotalProductValue`；`InertSpeciesValue`、`FractionSpecifiedValue`、`FixedSpecificationValue`（可写）。`gr_` 前缀的三个值与界面上的哪个选项对应，待 E3 和用户确认。

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

**结果（2026-10-08，D11）：第 1、2 条已经用代码验证成功，不需要往下降级。** `Reactions.Add(name, "conversionrxn")` 等，`ReactionSets.Add(name)`，`ActiveReactions.Add(反应名)`，`AssociateFluidPackage(fp)` 都在 E6 里跑通，重开后保持；`Operations.Add(name, "…ReactorOp")` 在 E7 里验证。下面的表是 0A 结束时写的线索，保留作为探索过程的记录。

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

同名对象、进程中断、弹窗、保存重开。阶段 0C 填写。下面先记 0A 里碰到的零散观察，0C 再系统化。

**阶段 0A 的观察。**

- **弹窗会让 COM 调用一直不返回。** 打开用到 Aspen Properties 的 Case 时弹出模态对话框，`SimulationCases.Open` 卡住。用 Win32 枚举 HYSYS 进程的 `#32770` 窗口能读到文字和按钮，`BM_CLICK` 能关掉它（H23）。`_common.watch` 是现成的看门狗。
- **路径形式。** 8.3 短路径一律 `E_ACCESSDENIED`，必须用长路径（H2）。
- **实例复用。** `HYSYS.Application` 会接管已经运行的实例，重复运行脚本可能碰到上一次遗留的 Case；需要干净环境时用 `NewInstance`，按进程号管理（H27）。
- **退出。** 释放 COM 引用不会让实例退出；`Quit()` 有效且不弹窗；卡住时 `taskkill /PID /T /F` 有效（连接节）。
- **求解。** 写入是同步重算；挂起后释放同步求解完（H17）。

(待 0C 补：同名对象、求解中途结束进程后的异常形态、保存重开)

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
