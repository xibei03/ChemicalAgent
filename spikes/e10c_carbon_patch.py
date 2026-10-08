"""E10c（0C 任务 3 的诊断）：改库里碳的 Gibbs 函数，Gibbs 反应器的结果能不能回到参照值。

E10b 的结论：库里 Carbon 的 EvaluateGibbs(298.15 K) 是 +671.3 kJ/mol（气态碳原子），不是石墨的 0。
这个探针只验证“根因就是它”：把碳的 GibbsCoeffs 改成石墨的 0，再按 E10 的做法求解，看结果有没有向
参照值（CO 1017、H2 981、CH4 22、碳 1491 kgmole/h）靠拢。它不是替代做法，改库里的数据属于
用户要决定的事（进度文件 D14 的选项 B）。

要回答的问题：
  Q1 GibbsCoeffs 是什么结构、能不能用 COM 写？写完 EvaluateGibbs 变成多少？
  Q2 改完之后 Gibbs 反应器 1400 °C 的结果与参照值差多少？
  Q3 如果结果仍然不对，说明还差什么（固体相的化学势没有被修正）。

用法：python spikes/e10c_carbon_patch.py [--tag 名字]
输出：spikes/out/e10c_carbon_patch_<tag>.txt
"""

import argparse
import traceback

from _common import Log, dialog_guard, new_instance, use_utf8
from chain_kit import make_feed, new_case_with_basis, read_stream
from e10_gibbs_carbon import (
    COMPONENTS,
    FEED_FLOW_KMOL_H,
    FEED_PRESSURE_KPA,
    FEED_TEMPERATURE_C,
    OUTLET_TEMPERATURE_C,
    connect_gibbs,
)

use_utf8()

REFERENCE_KMOL_H = {"CO": 1017.0, "Hydrogen": 981.0, "Methane": 22.0, "H2O": 11.0, "CO2": 3.5}
REFERENCE_CARBON_KMOL_H = 1491.0
TEMPERATURE_K = 1673.15


def solve_and_report(log: Log, label: str, app, case_name: str, patch) -> None:
    """建 E10 的模型，patch(component) 改碳的数据，1400 °C 求解，打印与参照值的对照。"""
    basis = new_case_with_basis(app, case_name, COMPONENTS)
    carbon = basis.package.Components.Item("Carbon")
    log.say(f"-- {label} --")
    patch(carbon)
    log.attempt(
        "  EvaluateGibbs(298.15 K)、(1673.15 K)",
        lambda: (carbon.EvaluateGibbs(298.15), carbon.EvaluateGibbs(TEMPERATURE_K)),
    )
    basis.manager.EndBasisChange()
    flowsheet = basis.case.Flowsheet
    fractions = {"Carbon": 0.710, "H2O": 0.290}
    feed = make_feed(
        flowsheet, basis, "Feed", FEED_TEMPERATURE_C, FEED_PRESSURE_KPA, fractions, FEED_FLOW_KMOL_H
    )
    vapour = flowsheet.MaterialStreams.Add("Vap")
    liquid = flowsheet.MaterialStreams.Add("Liq")
    energy = flowsheet.EnergyStreams.Add("Q-100")
    connect_gibbs(flowsheet, (feed,), vapour, liquid, energy, energy_first=True)
    vapour.Temperature.SetValue(OUTLET_TEMPERATURE_C, "C")
    gas = read_stream(vapour, basis.components)
    solid = read_stream(liquid, basis.components)
    log.say(
        f"  气相 kgmole/h { {k: round(v, 2) for k, v in gas['flows'].items() if abs(v) > 0.005} }"
    )
    log.say(
        f"  液相 kgmole/h { {k: round(v, 2) for k, v in solid['flows'].items() if abs(v) > 0.005} }"
    )
    for name, ref in REFERENCE_KMOL_H.items():
        log.say(f"      {name}: HYSYS {gas['flows'][name]:.2f}，参照 {ref}")
    log.say(
        f"      碳（液相）: HYSYS {solid['flows']['Carbon']:.2f}，参照 {REFERENCE_CARBON_KMOL_H}；"
        f"热负荷 {energy.HeatFlow.GetValue('kW') / 1000:.2f} MW（参照约 85）"
    )
    basis.case.Close()


def do_nothing(_component) -> None:
    """对照：不改。"""


def write_zero_gibbs(log: Log):
    """把 GibbsCoeffs 写成全 0（石墨的 Gibbs 生成能在任何温度都是 0）。"""

    def patch(component) -> None:
        coefficients = component.GibbsCoeffs
        log.attempt("  GibbsCoeffs 的类型", lambda: type(coefficients).__name__)
        ok, values = log.attempt("  GibbsCoeffs.Values（改之前）", lambda: coefficients.Values)
        count = len(values) if ok and values else 0
        log.attempt(
            f"  GibbsCoeffs.Values = {count} 个 0",
            lambda: setattr(coefficients, "Values", tuple(0.0 for _ in range(count))),
        )
        log.attempt("  GibbsCoeffs.Values（改之后）", lambda: coefficients.Values)

    return patch


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run1")
    args = parser.parse_args()
    log = Log(f"e10c_carbon_patch_{args.tag}")
    try:
        with new_instance(log) as (app, pid), dialog_guard(log, pid, include_hidden=True):
            solve_and_report(log, "对照：不改", app, "e10c_base", do_nothing)
            solve_and_report(log, "GibbsCoeffs 写成 0", app, "e10c_zero", write_zero_gibbs(log))
    except Exception:  # 探针：任何失败都要连同堆栈记进日志，再以非零状态退出
        log.say(traceback.format_exc())
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
