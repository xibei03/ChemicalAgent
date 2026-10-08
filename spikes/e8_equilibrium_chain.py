"""E8（0C 任务 1）：从空白 Case 用代码建出蒸汽重整的平衡反应器，两个工况与参照值对比。

模型（阶段提示词 0C 任务 1）：
  流体包 Peng-Robinson；组分 甲烷、水、CO、CO2、氢气
  两个平衡反应：Rxn-1 CH4 + H2O ⇌ CO + 3 H2，Rxn-2 CO + H2O ⇌ CO2 + H2
  Keq 来源用默认（Gibbs 自由能）
  反应集 RxnSet-1，加入流体包
  进料 520 °C，1350 kPa，3700 kgmole/h，摩尔分率 CH4 0.2703、H2O 0.7297
  平衡反应器 ERV-100：一股进料、气液两股出料、一股能流，压降 0；出口温度先 710 °C 再 600 °C

要回答的问题：
  Q1 Keq 来源默认是什么？出口温度规定在哪里？改规定后是否自动重算？热负荷怎么读、符号如何？
  Q2 两个工况的出口摩尔分率与参照值（独立计算的理想气体平衡）各自相差是否不超过 0.02？
  Q3 热模式：规定出口温度（Q2）、绝热（不接能流）、规定热负荷，三种各能不能求解？
  Q4 用户直接给出平衡常数（LnKSource = 3 固定 K）能不能通过代码设置，求解结果如何？

用法：python spikes/e8_equilibrium_chain.py [--tag 名字]
输出：spikes/out/e8_equilibrium_chain_<tag>.txt；Case 另存为同名 .hsc。
"""

import argparse
import traceback
from dataclasses import dataclass

from _common import OUT_DIR, Log, new_instance, use_utf8, watch
from chain_kit import (
    Basis,
    add_reaction,
    add_reaction_set,
    add_reactor,
    make_feed,
    mass_balance_error,
    new_case_with_basis,
    read_stream,
    status_counts,
)

use_utf8()

COMPONENTS = ("Methane", "H2O", "CO", "CO2", "Hydrogen")
FEED_FRACTIONS = {"Methane": 0.2703, "H2O": 0.7297}
FEED_TEMPERATURE_C = 520.0
FEED_PRESSURE_KPA = 1350.0
FEED_FLOW_KMOL_H = 3700.0
STEAM_REFORMING = (("Methane", -1.0), ("H2O", -1.0), ("CO", 1.0), ("Hydrogen", 3.0))
WATER_GAS_SHIFT = (("CO", -1.0), ("H2O", -1.0), ("CO2", 1.0), ("Hydrogen", 1.0))
# 阶段提示词给的独立参照值（理想气体平衡）：出口湿基摩尔分率、总流量
REFERENCE = {
    710.0: ({"Methane": 0.094, "H2O": 0.381, "Hydrogen": 0.411, "CO": 0.047, "CO2": 0.067}, 4800.0),
    600.0: ({"Methane": 0.162, "H2O": 0.499, "Hydrogen": 0.269, "CO": 0.012, "CO2": 0.058}, 4305.0),
}
FRACTION_TOLERANCE = 0.02
REPRODUCE_TOLERANCE = 1e-6
FIXED_K_BASIS_MOLE_FRACTION = 5  # ReactionBasis_enum: rbMoleFracBasis
LN_K_SOURCE_FIXED = 3  # 实测取值（H10）：1 Ln(K) 公式、2 Gibbs 自由能、3 固定 K、4 K–T 表


@dataclass
class Train:
    """一台平衡反应器和它的物流。"""

    reactor: object
    feed: object
    vapour: object
    liquid: object
    energy: object | None


def step_reactions(log: Log, basis: Basis):
    """两个平衡反应和反应集；读出 Keq 来源等默认设置。"""
    for name, stoichiometry in (("Rxn-1", STEAM_REFORMING), ("Rxn-2", WATER_GAS_SHIFT)):
        reaction = add_reaction(basis, name, "equilibriumrxn", stoichiometry, ReactionPhase=0)
        log.say(
            f"  {name}：LnKSource={reaction.LnKSource}（2 即 Gibbs 自由能），"
            f"Basis={reaction.Basis}，"
            f"AutoDetect={reaction.AutoDetect}，ReactionPhase={reaction.ReactionPhase}，"
            f"系数 {reaction.ReactantStoichCoefValue}"
        )
    return add_reaction_set(basis, "RxnSet-1", ("Rxn-1", "Rxn-2"))


def build_train(flowsheet, basis: Basis, tag: str, reaction_set, with_energy: bool) -> Train:
    """进料、两股出料、可选的能流、平衡反应器。"""
    feed = make_feed(
        flowsheet,
        basis,
        f"Feed{tag}",
        FEED_TEMPERATURE_C,
        FEED_PRESSURE_KPA,
        FEED_FRACTIONS,
        FEED_FLOW_KMOL_H,
    )
    vapour = flowsheet.MaterialStreams.Add(f"Vap{tag}")
    liquid = flowsheet.MaterialStreams.Add(f"Liq{tag}")
    energy = flowsheet.EnergyStreams.Add(f"Q{tag}") if with_energy else None
    reactor = add_reactor(
        flowsheet,
        f"ERV{tag}",
        "EquilibriumReactorOp",
        (feed,),
        vapour,
        liquid,
        energy,
        reaction_set,
    )
    return Train(reactor, feed, vapour, liquid, energy)


def conversion_of_methane(outlet: dict[str, object]) -> float:
    return 1.0 - outlet["flows"]["Methane"] / (FEED_FLOW_KMOL_H * FEED_FRACTIONS["Methane"])


def report(log: Log, label: str, train: Train, basis: Basis) -> dict[str, object]:
    """读出料、热负荷、质量守恒和反应器自己的结果。"""
    outlet = read_stream(train.vapour, basis.components)
    liquid_kmol_h = train.liquid.MolarFlow.GetValue("kgmole/h")
    error = mass_balance_error((train.feed,), train.vapour, train.liquid)
    shown = {k: round(v, 4) for k, v in outlet["fractions"].items()}
    log.say(f"  -- {label} --")
    log.say(
        f"    气相 T={outlet['T_C']:.2f} C，P={outlet['P_kPa']:.1f} kPa，"
        f"F={outlet['kmol_h']:.2f} kgmole/h，液相 F={liquid_kmol_h:.4f} kgmole/h"
    )
    log.say(f"    摩尔分率 {shown}；CH4 转化率 {conversion_of_methane(outlet):.1%}")
    log.say(f"    质量守恒相对误差 {error:.2e}")
    if train.energy is not None:
        duty = train.energy.HeatFlow
        log.say(
            f"    能流热负荷 {duty.GetValue('kW'):.1f} kW（State={duty.State}，"
            f"CanModify={duty.CanModify}）"
        )
    for member in ("RxnPercentConversionValue", "EqConstantValue", "RxnExtentValue"):
        log.attempt(f"    反应器.{member}", lambda member=member: getattr(train.reactor, member))
    return outlet


def compare(log: Log, temperature_c: float, outlet: dict[str, object]) -> bool:
    """与独立参照值比较，五个摩尔分率各自相差不超过容差。"""
    fractions, total = REFERENCE[temperature_c]
    worst = max(abs(outlet["fractions"][k] - v) for k, v in fractions.items())
    for name, ref in fractions.items():
        actual = outlet["fractions"][name]
        log.say(f"    {name}: HYSYS {actual:.4f}，参照 {ref:.3f}，差 {abs(actual - ref):.4f}")
    passed = worst <= FRACTION_TOLERANCE
    log.say(
        f"    [{'通过' if passed else '未通过'}] {temperature_c:.0f} C 最大偏差 {worst:.4f} "
        f"≤ {FRACTION_TOLERANCE}；总流量 {outlet['kmol_h']:.1f}（参照约 {total:.0f}）"
    )
    return passed


def run_specified_temperature(
    log: Log, flowsheet, basis: Basis, reaction_set
) -> tuple[bool, Train]:
    """Q1、Q2：规定出口温度 710、600、再回到 710，看自动重算和可复现。"""
    log.say("== Q1、Q2 规定出口温度（ERV-100，带能流） ==")
    train = build_train(flowsheet, basis, "-100", reaction_set, with_energy=True)
    log.say(f"  连接完、没规定出口温度时的状态 {status_counts(basis.case)}")
    results, first = [], None
    for temperature in (710.0, 600.0, 710.0):
        train.vapour.Temperature.SetValue(temperature, "C")
        log.say(f"  气相出料物流 Temperature.SetValue({temperature}, 'C')，同步重算后：")
        outlet = report(log, f"出口 {temperature:.0f} C", train, basis)
        results.append(compare(log, temperature, outlet))
        first = outlet if first is None else first
        if temperature == 710.0 and outlet is not first:
            diff = max(
                abs(outlet["fractions"][k] - first["fractions"][k]) for k in first["fractions"]
            )
            log.say(
                f"    第二次回到 710 C，与第一次摩尔分率最大差 {diff:.2e}"
                f"（要求 ≤ {REPRODUCE_TOLERANCE}）"
            )
            results.append(diff <= REPRODUCE_TOLERANCE)
    log.say(f"  全部求解后的流程图状态 {status_counts(basis.case)}")
    return all(results), train


def run_adiabatic(log: Log, flowsheet, basis: Basis, reaction_set) -> None:
    """Q3：绝热 = 不接能流，出口温度是计算结果。"""
    log.say("== Q3 绝热（ERV-ADI，不接能流） ==")
    train = build_train(flowsheet, basis, "-ADI", reaction_set, with_energy=False)
    outlet = report(log, "绝热", train, basis)
    log.say(
        f"    出口温度是否为计算值: State={train.vapour.Temperature.State}，"
        f"CanModify={train.vapour.Temperature.CanModify}；出口 {outlet['T_C']:.2f} C"
    )
    log.say(f"    流程图状态 {status_counts(basis.case)}")


def run_duty_specified(log: Log, flowsheet, basis: Basis, reaction_set, duty_kw: float) -> None:
    """Q3：规定热负荷 = 给能流写热负荷、不规定出口温度，用 710 °C 工况的热负荷，应当回到 710 °C。"""
    log.say(f"== Q3 规定热负荷（ERV-DUTY，能流 {duty_kw:.1f} kW，出口温度不规定） ==")
    train = build_train(flowsheet, basis, "-DUTY", reaction_set, with_energy=True)
    log.say(f"  写热负荷前的状态 {status_counts(basis.case)}")
    train.energy.HeatFlow.SetValue(duty_kw, "kW")
    outlet = report(log, "规定热负荷", train, basis)
    log.say(
        f"    出口温度 {outlet['T_C']:.2f} C（期望接近 710）；"
        f"能流 State={train.energy.HeatFlow.State}，CanModify={train.energy.HeatFlow.CanModify}"
    )
    log.say(f"    流程图状态 {status_counts(basis.case)}")


def run_fixed_k(log: Log, flowsheet, basis: Basis, reference: dict[str, object]) -> None:
    """Q4：固定 K。K 用摩尔分率基准，从 710 °C 的 Gibbs 来源结果反推，求解后应当回到同一个组成。"""
    y = reference["fractions"]
    k_reforming = y["CO"] * y["Hydrogen"] ** 3 / (y["Methane"] * y["H2O"])
    k_shift = y["CO2"] * y["Hydrogen"] / (y["CO"] * y["H2O"])
    log.say(f"== Q4 固定 K（摩尔分率基准）：Rxn-1K={k_reforming:.6g}，Rxn-2K={k_shift:.6g} ==")
    for name, stoichiometry, k_value in (
        ("Rxn-1K", STEAM_REFORMING, k_reforming),
        ("Rxn-2K", WATER_GAS_SHIFT, k_shift),
    ):
        reaction = add_reaction(basis, name, "equilibriumrxn", stoichiometry, ReactionPhase=0)
        reaction.Basis = FIXED_K_BASIS_MOLE_FRACTION
        reaction.LnKSource = LN_K_SOURCE_FIXED
        reaction.EquilibriumConstant = k_value
        log.say(
            f"  {name}：LnKSource={reaction.LnKSource}，Basis={reaction.Basis}，"
            f"EquilibriumConstant 读回 {reaction.EquilibriumConstant}"
        )
    fixed_set = add_reaction_set(basis, "RxnSet-K", ("Rxn-1K", "Rxn-2K"))
    train = build_train(flowsheet, basis, "-K", fixed_set, with_energy=True)
    train.vapour.Temperature.SetValue(710.0, "C")
    outlet = report(log, "固定 K，出口 710 C", train, basis)
    diff = max(abs(outlet["fractions"][k] - y[k]) for k in y)
    log.say(f"    与 Gibbs 来源 710 C 结果的摩尔分率最大差 {diff:.5f}（不要求通过）")
    log.say(f"    流程图状态 {status_counts(basis.case)}")


def run_once(log: Log, save_path) -> bool:
    with new_instance(log) as (app, _pid):
        with watch(log, "建 Basis"):
            basis = new_case_with_basis(app, "e8_equilibrium", COMPONENTS)
        log.say(
            f"  组分 {list(basis.package.Components.Names)}；"
            f"物性包 {basis.package.PropertyPackageName}"
        )
        reaction_set = step_reactions(log, basis)
        basis.manager.EndBasisChange()
        flowsheet = basis.case.Flowsheet
        passed, main_train = run_specified_temperature(log, flowsheet, basis, reaction_set)
        reference = read_stream(main_train.vapour, basis.components)
        duty_kw = main_train.energy.HeatFlow.GetValue("kW")
        run_adiabatic(log, flowsheet, basis, reaction_set)
        run_duty_specified(log, flowsheet, basis, reaction_set, duty_kw)
        run_fixed_k(log, flowsheet, basis, reference)
        basis.case.SaveAs(str(save_path))
        log.say(f"  Case 已另存为 {save_path}")
        basis.case.Close()
        return passed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run1")
    args = parser.parse_args()
    log = Log(f"e8_equilibrium_chain_{args.tag}")
    try:
        passed = run_once(log, OUT_DIR / f"e8_equilibrium_chain_{args.tag}.hsc")
    except Exception:  # 探针：任何失败都要连同堆栈记进日志，再以非零状态退出
        log.say(traceback.format_exc())
        return 1
    log.say(
        f"== E8 {'通过' if passed else '未通过'}：两个工况都在容差内且 710 C 可复现={passed} =="
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
