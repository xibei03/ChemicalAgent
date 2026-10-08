"""E5：新建物流，规定温度、压力、质量流量、组成，确认闪蒸完成。

要回答的问题：
  Q1 新建一股物流之后，每个量是已知还是未知？写入的顺序有没有要求？
  Q2 温度、压力、质量流量、摩尔分率各怎么写（成员、单位字符串）？
  Q3 写完哪一步之后闪蒸完成（气相分率、摩尔流量、焓等计算值变为已知）？
  Q4 组成写进去的是摩尔分率，读回来的质量分率、质量流量是多少，和手算一致吗？
  Q5 写错了会怎样：组成之和不为 1、负流量、不存在的单位。
  Q6 同名物流再建一次会怎样（顺手记，系统的测试在 0C）。
做法：新开实例，建 0B 模型的 Basis（甲苯、苯、对二甲苯、间二甲苯、邻二甲苯，pengrob），
建物流 Feed：380 °C、2500 kPa、10000 kg/h 纯甲苯，每写一步读一次状态。

用法：python spikes/e5_stream.py [--tag 名字]
输出：spikes/out/e5_stream_<tag>.txt
"""

import argparse

import pywintypes
from _common import Log, new_instance, use_utf8, watch

use_utf8()

COMPONENTS = ("Toluene", "Benzene", "p-Xylene", "m-Xylene", "o-Xylene")
TOLUENE_MOLECULAR_WEIGHT = 92.1384


def build_basis(app):
    """新建 Case、组分列表、流体包，结束 Basis。返回 (case, package)。"""
    case = app.SimulationCases.Add("e5")
    manager = case.BasisManager
    component_list = manager.ComponentLists.Add("CL-1")
    for name in COMPONENTS:
        component_list.Components.Add(name)
    package = manager.FluidPackages.Add("Basis-1")
    package.ComponentList = component_list
    package.PropertyPackageName = "pengrob"
    manager.EndBasisChange()
    return case, package


def safe(call) -> str:
    """读一个值；读取抛 COM 异常时返回说明，不中断。"""
    try:
        return f"{call():.4f}"
    except pywintypes.com_error as exc:
        return f"读取抛 com_error({exc.args[0]})"


def describe_stream(log: Log, stream, label: str) -> None:
    """一股物流当前各个量的已知性和数值。"""
    rows = []
    for member, unit in (
        ("Temperature", "C"),
        ("Pressure", "kPa"),
        ("MassFlow", "kg/h"),
        ("MolarFlow", "kgmole/h"),
    ):
        variable = getattr(stream, member)
        known = variable.IsKnown
        value = safe(lambda variable=variable, unit=unit: variable.GetValue(unit))
        rows.append(f"{member}: IsKnown={known}，GetValue={value}")
    rows.append(f"VapourFractionValue={safe(lambda: stream.VapourFractionValue)}")
    rows.append(f"VapourFraction.IsKnown={stream.VapourFraction.IsKnown}")
    known = stream.ComponentMolarFraction.IsKnown
    rows.append(f"组成已知个数={sum(bool(k) for k in known)}/{len(known)}")
    log.say(f"  [{label}]")
    for row in rows:
        log.say(f"      {row}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run1")
    args = parser.parse_args()
    log = Log(f"e5_stream_{args.tag}")
    with new_instance(log) as (app, _pid):
        with watch(log, "build_basis"):
            case, _package = build_basis(app)
        flowsheet = case.Flowsheet
        log.say("== Q1 新建物流 ==")
        stream = flowsheet.MaterialStreams.Add("Feed")
        describe_stream(log, stream, "新建后")

        log.say("== Q2、Q3 按 T、P、组成、质量流量的顺序写，每步读一次 ==")
        log.attempt(
            "Temperature.SetValue(380, 'C')", lambda: stream.Temperature.SetValue(380.0, "C")
        )
        describe_stream(log, stream, "写 T 后")
        log.attempt(
            "Pressure.SetValue(2500, 'kPa')", lambda: stream.Pressure.SetValue(2500.0, "kPa")
        )
        describe_stream(log, stream, "写 P 后")
        log.attempt(
            "ComponentMolarFraction.Values = (1,0,0,0,0)",
            lambda: setattr(stream.ComponentMolarFraction, "Values", (1.0, 0.0, 0.0, 0.0, 0.0)),
        )
        describe_stream(log, stream, "写组成后")
        log.attempt(
            "MassFlow.SetValue(10000, 'kg/h')", lambda: stream.MassFlow.SetValue(10000.0, "kg/h")
        )
        describe_stream(log, stream, "写质量流量后")

        log.say("== Q4 读回，与手算对照 ==")
        expected_kmol_h = 10000.0 / TOLUENE_MOLECULAR_WEIGHT
        log.attempt(
            f"MolarFlow(kgmole/h)，手算 {expected_kmol_h:.4f}",
            lambda: stream.MolarFlow.GetValue("kgmole/h"),
        )
        log.attempt("ComponentMassFlow(kg/h)", lambda: stream.ComponentMassFlow.GetValues("kg/h"))
        log.attempt("ComponentMassFraction", lambda: stream.ComponentMassFraction.Values)
        log.attempt("VapourFractionValue", lambda: stream.VapourFractionValue)
        for member in ("StdLiqVolFlow", "HeatFlow"):
            log.attempt(
                f"{member}（已知吗）", lambda member=member: getattr(stream, member).IsKnown
            )
        log.attempt(
            "Temperature.State / CanModify",
            lambda: (stream.Temperature.State, stream.Temperature.CanModify),
        )
        log.attempt(
            "VapourFraction 变量的状态",
            lambda: (stream.VapourFraction.IsKnown, stream.VapourFraction.State),
        )

        log.say("== 改写其中一个量：质量流量 20000，再改回 ==")
        log.attempt("MassFlow = 20000", lambda: stream.MassFlow.SetValue(20000.0, "kg/h"))
        log.attempt("MolarFlow 读回", lambda: stream.MolarFlow.GetValue("kgmole/h"))
        log.attempt("MassFlow = 10000", lambda: stream.MassFlow.SetValue(10000.0, "kg/h"))
        log.attempt("MolarFlow 读回", lambda: stream.MolarFlow.GetValue("kgmole/h"))

        log.say("== Q5 写错了会怎样（在另一股物流上试） ==")
        bad = flowsheet.MaterialStreams.Add("Bad")
        log.attempt(
            "组成之和为 0.9",
            lambda: setattr(bad.ComponentMolarFraction, "Values", (0.9, 0, 0, 0, 0)),
        )
        log.attempt("组成读回（和为 0.9 之后）", lambda: bad.ComponentMolarFraction.Values)
        log.attempt(
            "组成之和为 1.2",
            lambda: setattr(bad.ComponentMolarFraction, "Values", (1.2, 0, 0, 0, 0)),
        )
        log.attempt("组成读回（和为 1.2 之后）", lambda: bad.ComponentMolarFraction.Values)
        log.attempt(
            "组成只给 3 个数",
            lambda: setattr(bad.ComponentMolarFraction, "Values", (0.5, 0.5, 0.0)),
        )
        log.attempt("负的质量流量", lambda: bad.MassFlow.SetValue(-100.0, "kg/h"))
        log.attempt("负流量读回", lambda: bad.MassFlow.GetValue("kg/h"))
        log.attempt("温度写不认识的单位", lambda: bad.Temperature.SetValue(100.0, "degC"))
        log.attempt("温度 -300 C（低于绝对零度）", lambda: bad.Temperature.SetValue(-300.0, "C"))
        log.attempt("温度读回", lambda: bad.Temperature.GetValue("C"))

        log.say("== Q6 同名物流 ==")
        ok, again = log.attempt(
            "MaterialStreams.Add('Feed')（已存在）", lambda: flowsheet.MaterialStreams.Add("Feed")
        )
        if ok:
            log.attempt("  返回的是已有的那股吗：T(C)", lambda: again.Temperature.GetValue("C"))
        log.attempt("MaterialStreams.Names", lambda: list(flowsheet.MaterialStreams.Names))
        log.attempt("case.Close()", case.Close)


if __name__ == "__main__":
    main()
