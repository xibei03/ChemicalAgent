"""E2：读写已有的 Case，弄清变量怎么读、怎么写、单位怎么指定、求解器怎么控制。

要回答的问题：
  Q0 8.3 短路径是不是 Open 失败（E_ACCESSDENIED）的原因？
  Q1 流体包的清单、物性包的名字、组分清单各怎么读？
  Q2 物流的温度、压力、摩尔流量、质量流量、组成各用什么成员读？单位字符串怎么写？
  Q3 温度、压力、流量各写一次再读回，怎么写？写入后模型会不会自动重算？
  Q4 求解器怎么挂起和释放（Solver.CanSolve），是否生效？
  Q5 怎么判断一个变量是已知还是未知、是规定值还是计算值？
  Q6 未知的值读出来是什么（空值的表示）？
做法：复制示例 Synthesis Gas Production 到临时目录（长路径），用 NewInstance 的实例打开，
读写它的反应器进料和产物；另外临时加一股没有任何规定的物流来读空值。全程不保存。

用法：python spikes/e2_read_write.py [--tag 名字]
输出：spikes/out/e2_read_write_<tag>.txt
"""

import argparse
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import win32api
import win32com.client
from _common import Log, hysys_processes, use_utf8, wait_gone, watch

use_utf8()

SAMPLE = Path(r"C:\Program Files\AspenTech\Aspen HYSYS V15.0\Samples\Synthesis Gas Production.hsc")
TEMPERATURE_UNITS = ("C", "K", "F", "R", "degC", "foo")
PRESSURE_UNITS = ("kPa", "bar", "psia", "atm", "MPa")
MOLAR_FLOW_UNITS = ("kgmole/h", "kmol/h", "lbmole/h", "gmole/s")
MASS_FLOW_UNITS = ("kg/h", "lb/hr", "kg/s", "t/h")


def read_with_units(log: Log, label: str, variable, units: tuple[str, ...]) -> None:
    """用 GetValue(unit) 在多个单位下读同一个变量，另外读 .Value（内部单位）。"""
    log.attempt(f"{label}.Value", lambda: variable.Value)
    for unit in units:
        log.attempt(f"{label}.GetValue({unit!r})", lambda unit=unit: variable.GetValue(unit))


def describe_variable(log: Log, label: str, variable) -> None:
    for member in ("IsKnown", "State", "CanModify", "IsInconsistent", "UnitConversionType"):
        log.attempt(f"{label}.{member}", lambda member=member: getattr(variable, member))


def experiment_path_form(log: Log, app, directory: Path) -> None:
    """Q0：同一个副本，用三种路径形式打开：目录是短名、目录和文件名都是短名、长路径。"""
    log.say("== Q0 路径形式对 Open 的影响（同一个副本，同一种复制方式） ==")
    long_path = directory / SAMPLE.name
    shutil.copyfile(SAMPLE, long_path)
    short_dir_only = Path(win32api.GetShortPathName(str(directory))) / SAMPLE.name
    short_full = Path(win32api.GetShortPathName(str(long_path)))
    for label, path in (
        ("目录短名、文件名长名", short_dir_only),
        ("目录和文件名都是短名", short_full),
        ("长路径", long_path),
    ):
        log.say(f"  {label}: {path}")
        ok, case = log.attempt(
            f"Open({label})", lambda path=path: app.SimulationCases.Open(str(path))
        )
        if ok:
            log.attempt("case.FullName", lambda case=case: case.FullName)
            log.attempt("case.Close()", case.Close)


def read_basis(log: Log, case) -> None:
    log.say("== Q1 流体包、物性包、组分 ==")
    manager = case.BasisManager
    packages = manager.FluidPackages
    log.attempt("FluidPackages.Count", lambda: packages.Count)
    log.attempt("FluidPackages.Names", lambda: list(packages.Names))
    for i in range(int(packages.Count)):
        package = packages.Item(i)
        log.attempt(f"[{i}].name", lambda package=package: package.name)
        log.attempt(
            f"[{i}].PropertyPackageName", lambda package=package: package.PropertyPackageName
        )
        log.attempt(f"[{i}].Components.Count", lambda package=package: package.Components.Count)
        log.attempt(
            f"[{i}].Components.Names", lambda package=package: list(package.Components.Names)
        )
    log.attempt("Flowsheet.FluidPackage.name", lambda: case.Flowsheet.FluidPackage.name)


def read_stream(log: Log, stream, name: str) -> None:
    log.say(f"== Q2 读物流 {name} ==")
    read_with_units(log, f"{name}.Temperature", stream.Temperature, TEMPERATURE_UNITS)
    read_with_units(log, f"{name}.Pressure", stream.Pressure, PRESSURE_UNITS)
    read_with_units(log, f"{name}.MolarFlow", stream.MolarFlow, MOLAR_FLOW_UNITS)
    read_with_units(log, f"{name}.MassFlow", stream.MassFlow, MASS_FLOW_UNITS)
    log.attempt(f"{name}.TemperatureValue", lambda: stream.TemperatureValue)
    log.attempt(
        f"{name}.ComponentMolarFraction.Values", lambda: stream.ComponentMolarFraction.Values
    )
    log.attempt(f"{name}.ComponentMolarFractionValue", lambda: stream.ComponentMolarFractionValue)
    log.attempt(
        f"{name}.ComponentMolarFlow.GetValues('kgmole/h')",
        lambda: stream.ComponentMolarFlow.GetValues("kgmole/h"),
    )
    log.attempt(
        f"{name}.ComponentMassFlow.GetValues('kg/h')",
        lambda: stream.ComponentMassFlow.GetValues("kg/h"),
    )
    log.attempt(f"{name}.VapourFractionValue", lambda: stream.VapourFractionValue)


def snapshot(stream) -> dict[str, float]:
    return {
        "T_C": stream.Temperature.GetValue("C"),
        "P_kPa": stream.Pressure.GetValue("kPa"),
        "F_kgmole_h": stream.MolarFlow.GetValue("kgmole/h"),
    }


def write_and_read_back(log: Log, reactor, feed, product) -> None:
    """Q3：改进料的 T、P、流量，读回，并看出料是否随之变化。"""
    log.say("== Q3 写入并读回（进料），并观察出料 ==")
    before = snapshot(product)
    log.say(f"  出料写入前 {before}")
    log.attempt("写入前 Reformer 热负荷 kW", lambda: reactor.HeatFlow.GetValue("kW"))
    target = feed.Temperature.GetValue("C") + 10.0
    start = time.time()
    log.attempt(
        f"feed.Temperature.SetValue({target}, 'C')", lambda: feed.Temperature.SetValue(target, "C")
    )
    log.say(f"  写入用时 {time.time() - start:.2f} 秒")
    log.attempt("读回 T(C)", lambda: feed.Temperature.GetValue("C"))
    log.attempt("读回 T(K)", lambda: feed.Temperature.GetValue("K"))
    log.attempt("写入后 Reformer 热负荷 kW", lambda: reactor.HeatFlow.GetValue("kW"))
    after = snapshot(product)
    log.say(f"  出料写入后 {after}")
    changed = any(abs(after[k] - before[k]) > 1e-9 for k in before)
    verdict = "变了：模型自动重算了" if changed else "没变：没有自动重算，或者出料不受影响"
    log.conclude(f"改进料温度之后出料{verdict}")
    pressure = feed.Pressure.GetValue("kPa") * 1.05
    log.attempt(
        f"feed.Pressure.SetValue({pressure:.2f}, 'kPa')",
        lambda: feed.Pressure.SetValue(pressure, "kPa"),
    )
    log.attempt("读回 P(kPa)", lambda: feed.Pressure.GetValue("kPa"))
    log.attempt("读回 P(bar)", lambda: feed.Pressure.GetValue("bar"))
    flow = feed.MolarFlow.GetValue("kgmole/h") * 1.1
    log.attempt(
        f"feed.MolarFlow.SetValue({flow:.2f}, 'kgmole/h')",
        lambda: feed.MolarFlow.SetValue(flow, "kgmole/h"),
    )
    log.attempt("读回 F(kgmole/h)", lambda: feed.MolarFlow.GetValue("kgmole/h"))
    log.attempt("读回 F 的 MassFlow(kg/h)", lambda: feed.MassFlow.GetValue("kg/h"))
    log.attempt("写入一个不认识的单位", lambda: feed.Temperature.SetValue(500.0, "foo"))
    log.attempt("T 写入之后仍是原值吗", lambda: feed.Temperature.GetValue("C"))
    log.say(f"  出料最后 {snapshot(product)}")


def solver_control(log: Log, case, reactor, feed, product) -> None:
    """Q4：挂起求解器，改进料流量，出料应保持不变；释放后出料更新。"""
    log.say("== Q4 求解器的挂起和释放（改进料流量，出料流量会随之变） ==")
    solver = case.Solver
    log.attempt("Solver.CanSolve（初值）", lambda: solver.CanSolve)
    log.attempt("Solver.IsSolving", lambda: solver.IsSolving)
    log.attempt("Solver.Mode", lambda: solver.Mode)
    log.attempt("Solver.CanSolve = False", lambda: setattr(solver, "CanSolve", False))
    log.attempt("读回 CanSolve", lambda: solver.CanSolve)
    held = snapshot(product)
    value = feed.MolarFlow.GetValue("kgmole/h") * 1.2
    log.attempt(
        f"挂起时 feed.F.SetValue({value:.2f}, 'kgmole/h')",
        lambda: feed.MolarFlow.SetValue(value, "kgmole/h"),
    )
    log.attempt("挂起时读回进料流量", lambda: feed.MolarFlow.GetValue("kgmole/h"))
    now = snapshot(product)
    log.say(f"  挂起时出料 写入前 {held}，写入后 {now}")
    log.conclude(f"挂起求解器时改进料流量，出料{'没有' if now == held else '已经'}更新")
    start = time.time()
    log.attempt("Solver.CanSolve = True", lambda: setattr(solver, "CanSolve", True))
    log.say(f"  释放用时 {time.time() - start:.2f} 秒（求解是否同步完成看下一行）")
    log.attempt("释放之后 IsSolving", lambda: solver.IsSolving)
    released = snapshot(product)
    log.say(f"  释放后出料 {released}")
    log.conclude(f"释放求解器后出料{'更新了' if released != now else '没有变化'}")
    log.attempt("释放之后 Reformer 热负荷 kW", lambda: reactor.HeatFlow.GetValue("kW"))


def read_unknown(log: Log, flowsheet):
    """Q5、Q6：加一股没有任何规定的物流，读它的状态和空值。"""
    log.say("== Q5、Q6 已知性与空值：临时加一股没有规定的物流 ==")
    streams = flowsheet.MaterialStreams
    log.attempt("MaterialStreams.Count（加之前）", lambda: streams.Count)
    created = None
    for label, call in (
        ("Add('probe')", lambda: streams.Add("probe")),
        ("Add('probe', '')", lambda: streams.Add("probe", "")),
    ):
        ok, created = log.attempt(f"MaterialStreams.{label}", call)
        if ok:
            break
    log.attempt("MaterialStreams.Count（加之后）", lambda: streams.Count)
    log.attempt("MaterialStreams.Names 末尾", lambda: list(streams.Names)[-3:])
    ok, probe = log.attempt("取回 probe", lambda: streams.Item("probe"))
    if not ok:
        return None
    log.say(f"  Add 的返回值: {created!r}")
    for member in ("Temperature", "Pressure", "MolarFlow", "MassFlow"):
        variable = getattr(probe, member)
        describe_variable(log, f"probe.{member}", variable)
        log.attempt(f"probe.{member}.Value", lambda variable=variable: variable.Value)
    log.attempt("probe.Temperature.GetValue('C')", lambda: probe.Temperature.GetValue("C"))
    log.attempt("probe.ComponentMolarFraction.Values", lambda: probe.ComponentMolarFraction.Values)
    log.attempt("probe.ComponentMolarFractionValue", lambda: probe.ComponentMolarFractionValue)
    log.attempt(
        "probe.ComponentMolarFraction.IsKnown", lambda: probe.ComponentMolarFraction.IsKnown
    )
    log.attempt(
        "probe.Temperature.SetValue(25, 'C')", lambda: probe.Temperature.SetValue(25.0, "C")
    )
    describe_variable(log, "probe.Temperature（写入后）", probe.Temperature)
    return probe


def fill_probe(log: Log, probe, flowsheet) -> None:
    """H14：给新物流写组成、压力、流量，看闪蒸是否完成；最后删掉这股物流。"""
    if probe is None:
        return
    log.say("== H14 给新物流写组成、压力、流量 ==")
    fractions = (0.9, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0)
    component = probe.ComponentMolarFraction
    log.attempt("写法 a：Values = tuple", lambda: setattr(component, "Values", fractions))
    log.attempt("读回 a", lambda: component.Values)
    log.attempt("写法 b：SetValues(tuple)", lambda: component.SetValues((0.8, 0.2, 0, 0, 0, 0, 0)))
    log.attempt("读回 b", lambda: component.Values)
    log.attempt("写法 c：SetValues(tuple, '')", lambda: component.SetValues(fractions, ""))
    log.attempt("读回 c", lambda: component.Values)
    log.attempt("ComponentMolarFraction.IsKnown", lambda: component.IsKnown)
    log.attempt("P SetValue(1000, 'kPa')", lambda: probe.Pressure.SetValue(1000.0, "kPa"))
    log.attempt("F SetValue(100, 'kgmole/h')", lambda: probe.MolarFlow.SetValue(100.0, "kgmole/h"))
    for member in ("VapourFractionValue", "TemperatureValue", "PressureValue"):
        log.attempt(f"probe.{member}", lambda member=member: getattr(probe, member))
    log.attempt("MassFlow kg/h", lambda: probe.MassFlow.GetValue("kg/h"))
    log.attempt(
        "ComponentMolarFlow kgmole/h", lambda: probe.ComponentMolarFlow.GetValues("kgmole/h")
    )
    log.attempt(
        "MaterialStreams.Remove('probe')", lambda: flowsheet.MaterialStreams.Remove("probe")
    )
    log.attempt("MaterialStreams.Names 末尾", lambda: list(flowsheet.MaterialStreams.Names)[-2:])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="default")
    args = parser.parse_args()
    log = Log(f"e2_read_write_{args.tag}")
    before = hysys_processes()
    app = win32com.client.gencache.EnsureDispatch("HYSYS.Application.NewInstance")
    mine = next((pid for pid in hysys_processes() if pid not in before), None)
    log.say(f"新实例的进程号: {mine}")
    app.Visible = True
    scratch = Path(tempfile.mkdtemp(prefix="hysys_e2_")).resolve()
    try:
        experiment_path_form(log, app, scratch)
        with watch(log, "Open(长路径)"):
            case = app.SimulationCases.Open(str(scratch / SAMPLE.name))
        flowsheet = case.Flowsheet
        reactor = flowsheet.Operations.Item(0)
        log.say(f"反应器 {reactor.name}（{reactor.TypeName}），进料 {list(reactor.Feeds.Names)}")
        feed = flowsheet.MaterialStreams.Item(next(iter(reactor.Feeds.Names)))
        product = reactor.VapourProduct
        log.say(f"进料 {feed.name}，出料 {product.name}")
        read_basis(log, case)
        read_stream(log, feed, "进料")
        read_stream(log, product, "出料")
        log.say("== 进料和出料各自的已知性 ==")
        describe_variable(log, "进料.Temperature", feed.Temperature)
        describe_variable(log, "出料.Temperature", product.Temperature)
        write_and_read_back(log, reactor, feed, product)
        solver_control(log, case, reactor, feed, product)
        fill_probe(log, read_unknown(log, flowsheet), flowsheet)
        log.attempt("case.IsDirty", lambda: case.IsDirty)
    finally:
        # 改过的 Case 不保存；Quit 时有没有弹窗留给 e2b_quit_with_case.py
        log.say("== 收尾：不保存，按进程号结束本脚本启动的实例 ==")
        if mine is not None:
            subprocess.run(["taskkill", "/PID", str(mine), "/T", "/F"], capture_output=True)
            gone = wait_gone(mine)
            log.say(f"  实例 {mine} {'已结束' if gone is not None else '仍在运行'}")
        shutil.rmtree(scratch, ignore_errors=True)
    log.say(f"结束时的 HYSYS 进程: {hysys_processes() or '无'}")


if __name__ == "__main__":
    main()
