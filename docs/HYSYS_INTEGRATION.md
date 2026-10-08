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
| H2 | 打开 Case、取活动 Case | 未测试 | | | 计划假设：`SimulationCases.Open(path)`、`ActiveDocument`。计划状态：官方文档确认（V7.3 版）。探针 E2 类型库（2026-10-08，未运行验证）：`SimulationCases.Open(name: BSTR) -> IDispatch`、`Count`、`Item(index)`、`Close()`；`Application.ActiveDocument`。 |
| H3 | 新建空白 Case | 未测试 | | | 计划假设：`SimulationCases.Add()`。探针 E4 类型库（2026-10-08，未运行验证）：`SimulationCases.Add(name, Type)`，两个参数都是可选的 VARIANT。 |
| H4 | 保存、另存、关闭 | 未测试 | | | 计划假设：`Save`、`SaveAs`、`Close`。探针 E4、E12 类型库（2026-10-08，未运行验证）：`SimulationCase.Save()`、`SaveAs(...)`、`SaveAs2`、`SaveCopyAs`、`Close()`、`IsDirty`。 |
| H5 | Basis 修改事务 | 未测试 | | | 计划假设：`BasisManager.StartBasisChange`、`EndBasisChange`。计划状态：官方文档确认（V7.3 版）。探针 E4 类型库（2026-10-08，未运行验证）：`BasisManager.StartBasisChange()`、`EndBasisChange()`、`IsChangingBasis`、`CanEndBasisChange`。 |
| H6 | 读取流体包、物性包、组分 | 未测试 | | | 计划假设：`FluidPackages.Item(i)`、`PropertyPackageName`、`Components`。计划状态：官方文档确认（V7.3 版）。探针 E2 类型库（2026-10-08，未运行验证）：`BasisManager.FluidPackages`（集合）；`FluidPackage.PropertyPackageName`（可读写）、`Components`、`ReactionPackage`、`ComponentList`。 |
| H7 | 新建流体包并指定物性包 | 未测试 | | | 计划假设：`FluidPackages.Add(...)`。探针 E4 类型库（2026-10-08，未运行验证）：`FluidPackages.Add(name, Type)`；`FluidPackage.PropertyPackageName` 可写；`PropertyPackageType_enum` 有 `ppkg_PR=5891`。 |
| H8 | 添加库组分 | 未测试 | | | 计划假设：`Components.Add(name)`，以及库中的规范名。探针 E4 类型库（2026-10-08，未运行验证）：`FluidPackage.Components.Add(name, Type)`；`Component` 有 `IsSolid`、`Formula`、`CAS_Number`。 |
| H9 | 创建转化反应（计量系数、基准组分、转化率） | 未测试 | | | 计划假设：无。计划状态：未知。探针 E6 类型库（2026-10-08，未运行验证）：`ReactionPackageManager.Reactions.Add(name, Type)` 返回 VARIANT；`ConversionReaction`：`Reactants`（集合，有 `Add`）、`Reactant.StoichiometricCoefficientValue`（可写）、`BaseComponent`（可写）、`Conversion`（double，可写）、`ReactionPhase`、`BalanceStoichiometry()`。 |
| H10 | 创建平衡反应并指定 Keq 来源（Gibbs 自由能、固定值、随温度变化） | 未测试 | | | 计划假设：无。计划状态：未知。探针 E8 类型库（2026-10-08，未运行验证）：`EquilibriumReaction`：`LnKSource`（`eqrxn_Gibbs=0`、`eqrxn_LnKEquation=1`、`eqrxn_FixedK=2`、`eqrxn_Table=3`、`eqrxn_FixedExtent=4`）、`EquilibriumConstant`、`LnKEquationA/B/C/DParameter`、`MinTemperatureValue`、`MaxTemperatureValue`、`Basis`、`ReactionPhase`。 |
| H11 | 创建反应集、加入成员、挂到流体包 | 未测试 | | | 计划假设：无。计划状态：未知。探针 E6 类型库（2026-10-08，未运行验证）：`ReactionPackageManager.ReactionSets.Add(name, Type)`；`ReactionSet.AssociateFluidPackage(fluidPkg)`；`ActiveReactions` 和 `InactiveReactions`（`Reactions` 集合，加成员的方式待查）；`Operations`、`SolverMethod`。 |
| H12 | 新建物流和能流 | 未测试 | | | 计划假设：`MaterialStreams.Add(name)`、`EnergyStreams.Add(name)`。探针 E5 类型库（2026-10-08，未运行验证）：`Flowsheet.MaterialStreams`、`Flowsheet.EnergyStreams`（都是 `Streams`，有 `Add(name, Type)`）。 |
| H13 | 写入 T、P、流量 | 未测试 | | | 计划假设：`Temperature.SetValue(value, unit)` 等。计划状态：官方文档确认（V7.3 版）。探针 E2、E5 类型库（2026-10-08，未运行验证）：`RealVariable.SetValue(val: double, unit: VARIANT[opt])`、`GetValue(unit)`、`Value`；`ProcessStream` 的 `Temperature`/`TemperatureValue`、`Pressure`/`PressureValue`、`MolarFlow`/`MolarFlowValue`、`MassFlow`、`StdLiqVolFlow`。 |
| H14 | 写入组成 | 未测试 | | | 计划假设：`ComponentMolarFraction.Values = [...]`。计划状态：读取有公开示例，写入待验证。探针 E5 类型库（2026-10-08，未运行验证）：`ProcessStream.ComponentMolarFraction`（`RealFlexVariable`：`Values`、`SetValues(val, unit)`、`GetValues(unit)`）和 `ComponentMolarFractionValue`。 |
| H15 | 新建反应器 | 未测试 | | | 计划假设：`Operations.Add(name, typeName)`，三种反应器的 `typeName` 通过反向探测获得。探针 E3、E7 类型库（2026-10-08，未运行验证）：`Flowsheet.Operations(OperClassOrType[opt]).Add(name, Type)`。反应器接口：`ConversionReactor`、`EquilibriumReactor`、`GibbsReactor`，另有 `KineticReactor`、`PFReactor`、`YieldReactor`。`Type` 的取值（字符串还是枚举）待 E3。 |
| H16 | 反应器连接与配置（进出料、能流、反应集、压降、Gibbs 模式） | 未测试 | | | 计划假设：无。计划状态：未知。探针 E7 至 E9 类型库（2026-10-08，未运行验证）：三种反应器共有：`Feeds`（`Attachments`，`Add(Item)`）、`VapourProduct`、`LiquidProduct`、`EnergyStream`（可写，`ProcessStream*`）、`PressureDropValue`（可写）、`ReactionSet`（可写）、`HeatFlowValue`（可写）。Gibbs 另有 `ReactorType`（`gr_NoReactions=0`、`gr_SpecdRxnsOnly=2`、`gr_GibbsRxnsOnly=3`）、`InertSpeciesValue`、`FractionSpecifiedValue`、`FixedSpecificationValue`。接口里没有出口温度成员。 |
| H17 | 求解控制 | 未测试 | | | 计划假设：`Solver.CanSolve`。计划状态：官方文档确认（V7.3 版）。探针 E2 类型库（2026-10-08，未运行验证）：`Solver.CanSolve`（可读写）、`IsSolving`、`Mode`；`SimulationCase.Solver`。 |
| H18 | 变量是否已知，是规定值还是计算值 | 未测试 | | | 计划假设：`IsKnown`、`State`。计划状态：官方文档确认（V7.3 版）。探针 E2 类型库（2026-10-08，未运行验证）：`RealVariable.IsKnown`、`State`（`vsCalculated=0`、`vsSpecified=1`、`vsDefaultedValue=2`、`vsSpecifiedOutside=4`、`vsDefaultOutside=5`）、`CanModify`。 |
| H19 | 对象状态文本（未求解、欠规定等提示） | 未测试 | | | 计划假设：无。计划状态：未知。探针 E7 |
| H20 | 读取结果（T、P、流量、组成、分组分流量、热负荷） | 未测试 | | | 计划假设：`GetValue(unit)`、`ComponentMolarFraction.Values`。计划状态：基本读取有官方文档，分组分流量和热负荷待验证。探针 E7 类型库（2026-10-08，未运行验证）：反应器：`ComponentTotalInValue`、`ComponentTotalOutValue`、`ComponentTotalReactedValue`（转化、平衡）；`ComponentTotalFeedValue`、`ComponentTotalProductValue`（Gibbs）；`RxnPercentConversionValue`、`HeatFlowValue`。物流：`ComponentMolarFlow`、`ComponentMassFlow`。 |
| H21 | 固体碳组分及其在 Gibbs 反应器中的行为 | 未测试 | | | 计划假设：库组分 `Carbon`。计划状态：未知。探针 E10 类型库（2026-10-08，未运行验证）：`Component.IsSolid` 可以读，库里能不能加固体碳要实测。 |
| H22 | 空值的表示方式 | 未测试 | | | 计划假设：约定的哨兵值。探针 E2 |
| H23 | 模态弹窗对 COM 调用的阻塞 | 部分确认 | 阻塞：`SimulationCases.Open` 在弹窗出现时不返回。检测：枚举 HYSYS 进程的顶层窗口，类名 `#32770` 的是对话框，读它的 `Static` 子控件得到文字（`spikes/_common.py` 的 `windows_of`、`child_texts`、`watch`）。关闭：对 OK 按钮发 `BM_CLICK`（`win32gui.PostMessage`） | `spikes/find_ref_case.py`，2026-10-08，输出 `spikes/out/find_ref_case_scan.txt` | 只见过一种弹窗：打开用到 Aspen Properties 的 Case（Green Ammonia Process）时的 "To use Aspen Properties in HYSYS, at least one databank should be installed..."。`BM_CLICK` 能关闭对话框；阻塞的调用在对话框关闭后能否返回没测到。计划假设：无。探针 E11 |
| H24 | 降级通道：内部变量访问、脚本回放 | 未测试 | | | 计划假设：无。计划状态：未知。仅在 E6 至 E9 受阻时探测 类型库（2026-10-08，未运行验证）：`Application.BackDoor(obj[opt])` 返回 `BackDoor`：`BackDoorVariable(moniker)`、`BackDoorRealVariable`、`BackDoorTextVariable`、`BackDoorVariables(monikers)`、`SendBackDoorMessage(message)`；`Application.PlayScript(ScriptFileName)`。 |
| H25 | 组分库的枚举或检索（按名称、分子式查到规范名） | 未测试 | | | 计划假设：无。计划状态：未知。探针 E4 |
| H26 | Case 导出为可读文本并重新导入 | 未测试 | | | 计划假设：无。计划状态：未知。探针 E13 类型库（2026-10-08，未运行验证）：`SimulationCase.GetXMLForCase()`、`ProvideXMLForCase(flags)`、`ApplyXML(flags, sXML)`、`ApplyXMLFromFile(flags, filePath)`、`ProvideXMLForOperation(tagName, flags)`、`ApplyXMLForOperation(tagName, flags, sXML)`；`XMLOptionFlags_enum` 的取值见 `typelib_enums.txt`。这是文件路线最有希望的入口，E13 再测。 |
| H27 | 同时运行多个实例；按进程号管理实例 | 已确认 | `Dispatch("HYSYS.Application.NewInstance")` 新开进程；连接前后的 `tasklist` 差集得到新进程号；`app.Quit()` 只结束该实例；`taskkill /PID <pid> /T /F` 强制结束 | `spikes/e1_connect.py` run3、run5、run7，2026-10-08 | 释放 COM 引用不会让实例退出（run6）。两个实例的窗口标题相同，只能靠进程号区分。非计划内的能力，Backend 的会话管理会用到 |
| H28 | 早绑定（gen_py 包装）与类型库 | 已确认 | `gencache.EnsureModule("{DFC1C58B-AE9F-11CF-8EB2-0020AF119B90}", 0, 3, 2)` 生成包装；`pythoncom.LoadRegTypeLib(guid, 3, 2, 0)` 读类型信息 | `spikes/e1_connect.py` run8、run9，2026-10-08 | 包装缓存在 `%TEMP%\gen_py\3.12`。属性名区分大小写；生成之后 `Dispatch` 也返回包装类。集合 `Item()` 返回 `IDispatch`，是否需要 `CastTo` 待 E3 |

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

三种反应器都不是组件类（coclass）：类型库里只有 22 个组件类（`Application`、`SimulationCase` 及其单实例、Plant/Process/Engine 变体）。反应器对象只能从 `Operations.Add` 或 `Operations.Item` 取得。

### 集合对象的通用形状

`Reactions`、`ReactionSets`、`FluidPackages`、`Components`、`Streams`、`Operations`、`Reactants`、`SimulationCases` 都是同一种形状：`Count`、`Item(index: VARIANT) -> IDispatch`、`Names`、`index(name)`、`Add(name: VARIANT[opt], Type: VARIANT[opt]) -> VARIANT`、`Remove(index)`、`RemoveAll()`。

- `Item` 的参数是 VARIANT（下标和名字大概都行，待测），返回类型是泛型 `IDispatch`。早绑定下取出的对象能否直接访问具体接口的成员、要不要 `CastTo`，要在 E3 里验证。
- `Add` 的两个参数都是可选的 VARIANT：`Type` 的取值（字符串、枚举数值、省略）和返回值是什么都不知道。`Attachments`（反应器的 `Feeds`）的 `Add` 只有一个参数 `Item: VARIANT`。
- `Flowsheet.Operations` 是带参数的属性：`Operations(OperClassOrType: VARIANT[opt])`。

### 反应对象

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

**`ReactionSets` 和 `ReactionSet`（类型库）。**

- 取得方式有两条：`Case.BasisManager.ReactionPackageManager.ReactionSets`，或 `FluidPackage.ReactionPackage.ReactionSets`。
- `ReactionSet`：`AssociateFluidPackage(fluidPkg: FluidPackage*)`（把反应集挂到流体包）、`ActiveReactions` 和 `InactiveReactions`（都是 `Reactions` 集合，**怎么往里加反应不知道**）、`Operations`（`Attachments`，用了这个反应集的操作）、`SolverMethod`（可写，`ReactionSetSolverMethodEnum_enum`：rs_RateIteration=0、rs_RateIntegration=1、rs_AutoSelected=2、rs_RBNewton1=3）、`TraceLevel`、`UsePreviousSolution` 等求解选项。
- `ReactionPackage`：`FluidPackage`、`ReactionSets`、`ReactionPackageManager`。`ReactionPackageManager`：`BasisManager`、`ReactionSets`、`Reactions`、`Components`。

### 反应器对象

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

**依据：类型库（2026-10-08，`spikes/typelib_dump.py`），尚未运行验证。** E3 会补上 `Operations.Add` 的类型字符串和 `Item()` 取出对象的行为，到时按实测重排。

| 序 | 线索 | 依据 | 下一步 |
|---|---|---|---|
| 1 | **COM 直接创建（降级阶梯的 I1）**：`Case.BasisManager.ReactionPackageManager.Reactions.Add(name, Type)` 建反应；同一个管理器的 `ReactionSets.Add(name, Type)` 建反应集；`Flowsheet.Operations.Add(name, Type)` 建反应器 | 三个集合都有 `Add(name: VARIANT[opt], Type: VARIANT[opt]) -> VARIANT`，说明 HYSYS 把创建统一成这一种接口。设置路径是完整的：反应对象有可写的 `Reactants`、`BaseComponent`、`Conversion`、`LnKSource`；反应器有可写的 `ReactionSet`、`VapourProduct`、`LiquidProduct`、`EnergyStream`、`Feeds.Add` | 0B：先试 `Reactions.Add("R1", <类型>)`，`Type` 依次试省略、字符串（如 `"Conversion"`）、整数，读回 `Count` 和 `Names`；用 E3 得到的 `TypeName` 试 `Operations.Add`。建反应要在 `StartBasisChange()` 之后 |
| 2 | **反应集成员**：`ReactionSet.ActiveReactions.Add(反应名)`，再 `ReactionSet.AssociateFluidPackage(流体包)` | `ActiveReactions` 是 `Reactions` 集合，有 `Add`；`AssociateFluidPackage` 的签名明确 | 0B：试 `Add(反应名)`；不行就看 E3 里 GUI 建好的反应集的 `ActiveReactions.Names`，或查 `Support\rxnset.rdf` 里反应集成员的内部变量名 |
| 3 | **从 GUI 建好的 Case 反推**（E3） | 用户或示例里已有的 Case 是"标准答案"：可以读出 `TypeName`、反应集成员的名字和各成员取值的含义 | 本阶段任务 9 |
| 4 | **XML 路线**：`SimulationCase.GetXMLForCase()`、`ProvideXMLForCase(flags)`、`ApplyXML(flags, sXML)`、`ApplyXMLFromFile(flags, path)`，以及按操作的 `ProvideXMLForOperation(tagName, flags)`、`ApplyXMLForOperation(tagName, flags, sXML)` | 类型库里有。`XMLOptionFlags_enum` 有 14 个选项（`opt_SpecsOnly=1`、`opt_UseUserUnitSet=2`、`opt_IncludeAttachments=4`、`opt_NoBasisData=2048` 等）。如果导出的 XML 含反应和反应集，就能改文本再导回，绕开"COM 不能创建"的缺口；也是 H26 的入口 | 在 E3 的参考 Case 上 `GetXMLForCase()`，看是否含反应；0B 里 COM 创建受阻时才用 |
| 5 | **脚本回放**：`Application.PlayScript(ScriptFileName)`、`PlayScriptRelativeTo` | 类型库里有；脚本格式未知 | 只在 1 至 4 受阻时 |
| 6 | **内部变量通道**：`Application.BackDoor(obj[opt])` 返回 `BackDoor`，有 `BackDoorVariable(moniker)`、`BackDoorRealVariable`、`BackDoorTextVariable`、`BackDoorVariables(monikers)`、`SendBackDoorMessage(message)`；安装目录的 `Support\*.rdf`、`*.sgxml`（`convrxn.rdf`、`equirxn.rdf`、`rxnset.rdf`、`rxnop.rdf`）给出内部变量名，`ExtSDK\hysys.hh` 可查签名 | 类型库里有；moniker 的写法要靠 rdf 文件和 E3 里读到的 `Moniker` 属性猜 | 只在 1 至 4 受阻时 |
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
