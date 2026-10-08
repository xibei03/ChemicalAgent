"""E10（0C 任务 3）：固体碳在 Gibbs 反应器里的行为（水煤浆气化，只有碳和水进料）。

模型（阶段提示词 0C 任务 3）：
  流体包 Peng-Robinson；组分 碳、水、CO、氢气、CO2、甲烷
  进料 40 °C，4000 kPa，总摩尔流量 3569 kgmole/h，摩尔分率 碳 0.710、水 0.290（质量分率 0.62、0.38）
  Gibbs 反应器 GBR-100：纯自由能最小化，一股进料、气液两股出料、一股能流，压降 0，出口 1400 °C
参照值（独立计算）：出口气体 CO 约 1017、H2 约 981、CH4 约 22、H2O 约 11、CO2 约 3.5 kgmole/h，
未反应的固体碳约 1491 kgmole/h，CO 收率约 40%，外供热约 85 MW。

通过条件（四条都要满足）：
  1 CO 收率（出口 CO ÷ 进料碳）在 38% 至 42%
  2 气相出料里 CO、H2 的摩尔分率与 0.500、0.482 各自相差不超过 0.02
  3 碳元素守恒：进料的碳 = 各股出料里 CO、CO2、CH4 和未反应碳的碳之和，相对误差不超过 0.1%
  4 没反应掉的碳以固体的形式从某一股明确的出料离开，量与 1491 kgmole/h 相差不超过 5%

要回答的五个问题：
  Q1 组分库里有没有碳、叫什么、HYSYS 把它当作什么相
  Q2 含固体的进料物流在 40 °C 能不能正常闪蒸
  Q3 Gibbs 反应器是否让碳作为固体参与平衡
  Q4 没反应掉的碳从哪股出料离开
  Q5 碳元素是否守恒

做法：每个变体从空白 Case 开始，只改一样东西，用来找出结果为什么对或者不对：
  base            进料一股，先接出料再接能流（run1 的做法，会弹出绝热警告）
  energy-first    先接能流再接出料（避免连接过程中先按绝热求解）
  hold-solver     建模期间挂起求解器，建完释放
  split-feeds     碳和水两股进料分别进反应器
  water-rich      水过量（碳 : 水 = 1 : 5），碳应当全部气化，没有固体
  no-carbon       不含碳，甲烷 + 水蒸气，只测气相的 Gibbs 平衡
  温度路径        在 energy-first 的 Case 里依次改出口温度 1000、1200、1600、再回到 1400 °C

用法：python spikes/e10_gibbs_carbon.py [--tag 名字] [--only 变体名]
输出：spikes/out/e10_gibbs_carbon_<tag>.txt；energy-first 的 Case 另存为同名 .hsc。
"""

import argparse
import traceback
from dataclasses import dataclass

from _common import OUT_DIR, Log, dialog_guard, new_instance, use_utf8, watch
from chain_kit import (
    Basis,
    make_feed,
    mass_balance_error,
    new_case_with_basis,
    read_stream,
    status_counts,
)

use_utf8()

COMPONENTS = ("Carbon", "H2O", "CO", "Hydrogen", "CO2", "Methane")
FEED_TEMPERATURE_C = 40.0
FEED_PRESSURE_KPA = 4000.0
FEED_FLOW_KMOL_H = 3569.0
OUTLET_TEMPERATURE_C = 1400.0
EXPECTED_MASS_FRACTIONS = {"Carbon": 0.62, "H2O": 0.38}
MASS_FRACTION_TOLERANCE = 0.001
CARBON_ATOMS = {"Carbon": 1, "CO": 1, "CO2": 1, "Methane": 1}
REFERENCE_UNREACTED_CARBON_KMOL_H = 1491.0
REFERENCE_GAS_FRACTIONS = {"CO": 0.500, "Hydrogen": 0.482}
YIELD_RANGE = (0.38, 0.42)
FRACTION_TOLERANCE = 0.02
CARBON_BALANCE_TOLERANCE = 1e-3
CARBON_AMOUNT_TOLERANCE = 0.05
REFERENCE_DUTY_MW = 85.0
TEMPERATURE_PATH_C = (1000.0, 1200.0, 1600.0, 1400.0)
CARBON_FRACTION = 0.710
WATER_RICH_CARBON_FRACTION = 1.0 / 6.0
GAS_ONLY_METHANE_FRACTION = 0.2703


@dataclass(frozen=True)
class Variant:
    """一个变体：进料怎么给、连接顺序、是否挂起求解器。"""

    name: str
    carbon_fraction: float | None  # None 表示不含碳；甲烷和水按 GAS_ONLY 的比例
    split: bool = False
    energy_first: bool = False
    hold_solver: bool = False


VARIANTS = (
    Variant("base", CARBON_FRACTION),
    Variant("energy-first", CARBON_FRACTION, energy_first=True),
    Variant("hold-solver", CARBON_FRACTION, energy_first=True, hold_solver=True),
    Variant("split-feeds", CARBON_FRACTION, split=True, energy_first=True),
    Variant("water-rich", WATER_RICH_CARBON_FRACTION, energy_first=True),
    Variant("no-carbon", None, energy_first=True),
)
FORMAL_VARIANT = "energy-first"


def feed_specs(variant: Variant) -> list[tuple[str, dict[str, float], float]]:
    """进料物流清单：(名字, 摩尔分率, 摩尔流量)。"""
    if variant.carbon_fraction is None:
        fractions = {"Methane": GAS_ONLY_METHANE_FRACTION, "H2O": 1.0 - GAS_ONLY_METHANE_FRACTION}
        return [("Feed", fractions, FEED_FLOW_KMOL_H)]
    carbon = variant.carbon_fraction
    if not variant.split:
        return [("Feed", {"Carbon": carbon, "H2O": 1.0 - carbon}, FEED_FLOW_KMOL_H)]
    return [
        ("FeedC", {"Carbon": 1.0}, FEED_FLOW_KMOL_H * carbon),
        ("FeedW", {"H2O": 1.0}, FEED_FLOW_KMOL_H * (1.0 - carbon)),
    ]


def describe_components(log: Log, basis: Basis) -> None:
    """Q1：组分库里的碳。"""
    log.say("== Q1 组分库里的碳 ==")
    for name in COMPONENTS:
        component = basis.package.Components.Item(name)
        log.attempt(
            f"  {name}: 名字 / 分子式 / IsSolid",
            lambda component=component: (component.name, component.Formula, component.IsSolid),
        )


def describe_stream(log: Log, label: str, stream, basis: Basis) -> dict[str, object]:
    """读物流：T、P、流量、相分率、按组分的摩尔流量和质量分率。"""
    data = read_stream(stream, basis.components)
    log.say(f"  -- {label} --")
    log.say(
        f"    T={data['T_C']:.2f} C，P={data['P_kPa']:.1f} kPa，F={data['kmol_h']:.3f} kgmole/h，"
        f"{data['kg_h']:.1f} kg/h"
    )
    log.say(f"    各组分 kgmole/h { {k: round(v, 3) for k, v in data['flows'].items()} }")
    for member in ("VapourFractionValue", "LiquidFractionValue", "HeavyLiquidFractionValue"):
        log.attempt(f"    {member}", lambda member=member: getattr(stream, member))
    mass = dict(zip(basis.components, stream.ComponentMassFraction.Values, strict=True))
    log.say(f"    质量分率 { {k: round(v, 5) for k, v in mass.items()} }")
    return data


def connect_gibbs(flowsheet, feeds, vapour, liquid, energy, energy_first: bool):
    """建 Gibbs 反应器并连接。energy_first 为真时先接能流再接出料。"""
    reactor = flowsheet.Operations.Add("GBR-100", "GibbsReactorOp")
    for feed in feeds:
        reactor.Feeds.Add(feed)
    if energy_first:
        reactor.EnergyStream = energy
    reactor.VapourProduct = vapour
    reactor.LiquidProduct = liquid
    if not energy_first:
        reactor.EnergyStream = energy
    reactor.PressureDrop.SetValue(0.0, "kPa")
    return reactor


def carbon_atoms_out(outlets: dict[str, dict[str, object]]) -> float:
    return sum(
        count * data["flows"][name]
        for data in outlets.values()
        for name, count in CARBON_ATOMS.items()
    )


def judge(log: Log, carbon_in: float, vapour: dict, liquid: dict, duty_kw: float) -> bool:
    """四条通过条件，加未反应的碳在哪股出料里。"""
    log.say("== 判定（四条通过条件） ==")
    co_yield = (vapour["flows"]["CO"] + liquid["flows"]["CO"]) / carbon_in
    in_range = YIELD_RANGE[0] <= co_yield <= YIELD_RANGE[1]
    log.say(
        f"  [{'通过' if in_range else '未通过'}] 1 CO 收率 {co_yield:.4f}（要求 {YIELD_RANGE}）"
    )
    gas_ok = True
    for name, ref in REFERENCE_GAS_FRACTIONS.items():
        diff = abs(vapour["fractions"][name] - ref)
        gas_ok = gas_ok and diff <= FRACTION_TOLERANCE
        log.say(
            f"      气相 {name} 摩尔分率 {vapour['fractions'][name]:.4f}，参照 {ref}，差 {diff:.4f}"
        )
    log.say(
        f"  [{'通过' if gas_ok else '未通过'}] 2 气相 CO、H2 与参照值各自相差"
        f" ≤ {FRACTION_TOLERANCE}"
    )
    outlets = {"气相出料": vapour, "液相出料": liquid}
    carbon_out = carbon_atoms_out(outlets)
    balance = abs(carbon_out - carbon_in) / carbon_in
    balance_ok = balance <= CARBON_BALANCE_TOLERANCE
    verdict = "通过" if balance_ok else "未通过"
    log.say(
        f"  [{verdict}] 3 碳元素守恒：进 {carbon_in:.3f}，出 {carbon_out:.3f} kgmole/h，"
        f"相对误差 {balance:.2e}（要求 ≤ {CARBON_BALANCE_TOLERANCE}）"
    )
    for label, data in outlets.items():
        log.say(f"      {label}里的碳（Carbon 组分）{data['flows']['Carbon']:.3f} kgmole/h")
    holder = max(outlets, key=lambda label: outlets[label]["flows"]["Carbon"])
    amount = outlets[holder]["flows"]["Carbon"]
    deviation = abs(amount - REFERENCE_UNREACTED_CARBON_KMOL_H) / REFERENCE_UNREACTED_CARBON_KMOL_H
    amount_ok = deviation <= CARBON_AMOUNT_TOLERANCE
    log.say(
        f"  [{'通过' if amount_ok else '未通过'}] 4 未反应的碳从“{holder}”离开"
        f" {amount:.3f} kgmole/h，参照 {REFERENCE_UNREACTED_CARBON_KMOL_H}，"
        f"相差 {deviation:.1%}（要求 ≤ {CARBON_AMOUNT_TOLERANCE:.0%}）"
    )
    log.say(f"      外供热 {duty_kw / 1000:.2f} MW（参照约 {REFERENCE_DUTY_MW} MW）")
    return in_range and gas_ok and balance_ok and amount_ok


def summary_line(label: str, vapour: dict, liquid: dict, duty_kw: float) -> str:
    """一行摘要：气相和液相里各组分的 kgmole/h，加热负荷。"""
    gas = {k: round(v, 1) for k, v in vapour["flows"].items() if abs(v) > 0.05}
    liq = {k: round(v, 1) for k, v in liquid["flows"].items() if abs(v) > 0.05}
    return f"{label}: 气相 {gas}；液相 {liq}；热负荷 {duty_kw / 1000:.2f} MW"


def reactor_totals(log: Log, reactor, basis: Basis) -> None:
    """反应器自己报告的按组分进出量，和出料物流对照。"""
    for member in ("ComponentTotalFeed", "ComponentTotalProduct"):
        log.attempt(
            f"    反应器.{member}(kgmole/h)",
            lambda member=member: dict(
                zip(
                    basis.components,
                    [round(v, 3) for v in getattr(reactor, member).GetValues("kgmole/h")],
                    strict=True,
                )
            ),
        )


def run_variant(log: Log, app, variant: Variant, save_path=None) -> dict[str, object]:
    """从空白 Case 建一个变体，1400 °C 求解，读结果。"""
    log.say(f"######## 变体 {variant.name} ########")
    with watch(log, f"建 Basis（{variant.name}）"):
        basis = new_case_with_basis(app, f"e10_{variant.name}", COMPONENTS)
    if variant.name == FORMAL_VARIANT:
        describe_components(log, basis)
    basis.manager.EndBasisChange()
    flowsheet = basis.case.Flowsheet
    if variant.hold_solver:
        basis.case.Solver.CanSolve = False
    feeds = [
        make_feed(flowsheet, basis, name, FEED_TEMPERATURE_C, FEED_PRESSURE_KPA, fractions, flow)
        for name, fractions, flow in feed_specs(variant)
    ]
    carbon_in = sum(
        flow * fractions.get("Carbon", 0.0) for _, fractions, flow in feed_specs(variant)
    )
    if variant.name == FORMAL_VARIANT:
        log.say("== Q2 含固体的进料物流（40 C，4000 kPa） ==")
        describe_stream(log, "进料", feeds[0], basis)
    vapour = flowsheet.MaterialStreams.Add("Vap")
    liquid = flowsheet.MaterialStreams.Add("Liq")
    energy = flowsheet.EnergyStreams.Add("Q-100")
    reactor = connect_gibbs(flowsheet, feeds, vapour, liquid, energy, variant.energy_first)
    vapour.Temperature.SetValue(OUTLET_TEMPERATURE_C, "C")
    if variant.hold_solver:
        basis.case.Solver.CanSolve = True
    log.say(f"  ReactorType {reactor.ReactorType}；状态 {status_counts(basis.case)}")
    vapour_data = describe_stream(log, "气相出料", vapour, basis)
    liquid_data = describe_stream(log, "液相出料", liquid, basis)
    reactor_totals(log, reactor, basis)
    error = mass_balance_error(feeds, vapour, liquid)
    log.say(f"    质量守恒相对误差 {error:.2e}")
    duty_kw = energy.HeatFlow.GetValue("kW")
    result = {
        "name": variant.name,
        "summary": summary_line(variant.name, vapour_data, liquid_data, duty_kw),
    }
    if variant.carbon_fraction is not None and carbon_in > 0:
        result["passed"] = judge(log, carbon_in, vapour_data, liquid_data, duty_kw)
    if variant.name == FORMAL_VARIANT:
        result["path"] = temperature_path(log, vapour, liquid, energy, basis)
    if save_path is not None:
        basis.case.SaveAs(str(save_path))
        log.say(f"  Case 已另存为 {save_path}")
    basis.case.Close()
    return result


def temperature_path(log: Log, vapour, liquid, energy, basis: Basis) -> list[str]:
    """同一个 Case 里依次改出口温度，看结果是否依赖路径。"""
    log.say("== 温度路径：1000、1200、1600，再回到 1400 C ==")
    lines = []
    for temperature in TEMPERATURE_PATH_C:
        vapour.Temperature.SetValue(temperature, "C")
        gas = read_stream(vapour, basis.components)
        liq = read_stream(liquid, basis.components)
        line = summary_line(f"{temperature:.0f} C", gas, liq, energy.HeatFlow.GetValue("kW"))
        log.say(f"  {line}")
        lines.append(line)
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run2")
    parser.add_argument("--only", default=None, help="只跑指定名字的变体")
    args = parser.parse_args()
    log = Log(f"e10_gibbs_carbon_{args.tag}")
    results = []
    try:
        with new_instance(log) as (app, pid), dialog_guard(log, pid) as dialogs:
            for variant in VARIANTS:
                if args.only and variant.name != args.only:
                    continue
                save = (
                    OUT_DIR / f"e10_gibbs_carbon_{args.tag}.hsc"
                    if variant.name == FORMAL_VARIANT
                    else None
                )
                results.append(run_variant(log, app, variant, save))
            log.say(f"== 全程看门狗处理过的弹窗 {len(dialogs)} 个 ==")
            for message in dialogs:
                log.say(f"  {message}")
    except Exception:  # 探针：任何失败都要连同堆栈记进日志，再以非零状态退出
        log.say(traceback.format_exc())
        return 1
    log.say("== 各变体摘要（kgmole/h） ==")
    for result in results:
        log.say(f"  {result['summary']}")
    formal = [r for r in results if r["name"] == FORMAL_VARIANT]
    passed = bool(formal and formal[0].get("passed"))
    log.say(
        f"== E10 正式变体 {FORMAL_VARIANT}："
        f"{'四条通过条件都满足' if passed else '有未通过的条件'} =="
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
