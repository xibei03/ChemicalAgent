"""E15（1A）：固定 K 的平衡反应，写 Basis、LnKSource、EquilibriumConstant 会不会改掉 ReactionPhase。

背景：1A 的集成测试里，先写 ReactionPhase = 0（气相），再写固定 K 的三个成员，读回的反应相变成了
5（合并相）。要回答：
  Q1 先写反应相再写固定 K 时，哪一步写入把反应相改成了 5？
  Q2 先写固定 K 的三个成员，最后写反应相 0：Basis、LnKSource、EquilibriumConstant、ReactionPhase
     读回是否都保持？
  Q3 Gibbs 自由能来源（默认）的平衡反应，写反应相 0 会不会改掉 LnKSource？
  Q4 用 Q2 的顺序建出的固定 K 反应，放进平衡反应器求解，出口组成与质量作用定律的手算解一致吗？

用法：python spikes/e15_fixed_k_order.py [--tag 名字]
输出：spikes/out/e15_fixed_k_order_<tag>.txt；Case 另存为同名 .hsc。
"""

import argparse
import traceback

from _common import OUT_DIR, Log, dialog_guard, new_instance, use_utf8
from chain_kit import (
    add_reaction_set,
    add_reactor,
    make_feed,
    new_case_with_basis,
    read_stream,
    status_counts,
)

use_utf8()

COMPONENTS = ("CO", "H2O", "CO2", "Hydrogen")
SHIFT = (("CO", -1.0), ("H2O", -1.0), ("CO2", 1.0), ("Hydrogen", 1.0))
FIXED_K = 4.0
FIXED_K_BASIS_MOLE_FRACTION = 5
LN_K_SOURCE_FIXED = 3
EXPECTED_FRACTIONS = {"CO": 1 / 6, "H2O": 1 / 6, "CO2": 1 / 3, "Hydrogen": 1 / 3}
FRACTION_TOLERANCE = 0.001


def new_reaction(basis, name: str):
    reaction = basis.manager.ReactionPackageManager.Reactions.Add(name, "equilibriumrxn")
    for component, coefficient in SHIFT:
        reaction.Reactants.Add(component).StoichiometricCoefficientValue = coefficient
    return reaction


def state(reaction) -> dict[str, object]:
    return {
        "ReactionPhase": reaction.ReactionPhase,
        "Basis": reaction.Basis,
        "LnKSource": reaction.LnKSource,
        "AutoDetect": reaction.AutoDetect,
    }


def phase_first(log: Log, basis) -> None:
    """Q1：先写反应相，再逐个写固定 K 的三个成员，每一步之后读回。"""
    log.say("== Q1 先写反应相，再写固定 K ==")
    reaction = new_reaction(basis, "PhaseFirst")
    log.say(f"  新建之后 {state(reaction)}")
    reaction.ReactionPhase = 0
    log.say(f"  写 ReactionPhase = 0 之后 {state(reaction)}")
    reaction.Basis = FIXED_K_BASIS_MOLE_FRACTION
    log.say(f"  写 Basis = 5 之后 {state(reaction)}")
    reaction.LnKSource = LN_K_SOURCE_FIXED
    log.say(f"  写 LnKSource = 3 之后 {state(reaction)}")
    reaction.EquilibriumConstant = FIXED_K
    log.say(f"  写 K = {FIXED_K} 之后 {state(reaction)}，K 读回 {reaction.EquilibriumConstant}")


def phase_last(log: Log, basis):
    """Q2：先写固定 K 的三个成员，最后写反应相。"""
    log.say("== Q2 先写固定 K，最后写反应相 ==")
    reaction = new_reaction(basis, "PhaseLast")
    reaction.Basis = FIXED_K_BASIS_MOLE_FRACTION
    reaction.LnKSource = LN_K_SOURCE_FIXED
    reaction.EquilibriumConstant = FIXED_K
    log.say(f"  写完固定 K 之后 {state(reaction)}，K 读回 {reaction.EquilibriumConstant}")
    reaction.ReactionPhase = 0
    log.say(
        f"  最后写 ReactionPhase = 0 之后 {state(reaction)}，K 读回 {reaction.EquilibriumConstant}"
    )
    return reaction


def gibbs_source(log: Log, basis) -> None:
    """Q3：Gibbs 自由能来源，写反应相 0 之后 LnKSource 还是 2 吗。"""
    log.say("== Q3 Gibbs 自由能来源的反应，写反应相 0 ==")
    reaction = new_reaction(basis, "GibbsSource")
    log.say(f"  新建之后 {state(reaction)}")
    reaction.ReactionPhase = 0
    log.say(f"  写 ReactionPhase = 0 之后 {state(reaction)}")


def solve_fixed_k(log: Log, basis, reaction_name: str) -> bool:
    """Q4：用 Q2 顺序建出的反应求解，与质量作用定律的手算解比较。"""
    log.say("== Q4 平衡反应器求解 ==")
    flowsheet = basis.case.Flowsheet
    reaction_set = add_reaction_set(basis, "FixedK-Set", (reaction_name,))
    feed = make_feed(flowsheet, basis, "Feed", 400.0, 500.0, {"CO": 0.5, "H2O": 0.5}, 100.0)
    vapour = flowsheet.MaterialStreams.Add("Vap")
    liquid = flowsheet.MaterialStreams.Add("Liq")
    energy = flowsheet.EnergyStreams.Add("Q-100")
    add_reactor(
        flowsheet, "ERV-100", "EquilibriumReactorOp", (feed,), vapour, liquid, energy, reaction_set
    )
    vapour.Temperature.SetValue(400.0, "C")
    counts = status_counts(basis.case)
    data = read_stream(vapour, basis.components)
    worst = max(abs(data["fractions"][name] - EXPECTED_FRACTIONS[name]) for name in COMPONENTS)
    log.say(f"  流程图状态 {counts}")
    log.say(f"  出口摩尔分率 { {k: round(v, 4) for k, v in data['fractions'].items()} }")
    log.say(
        f"  与手算解（1/6、1/6、1/3、1/3）的最大偏差 {worst:.5f}（要求 ≤ {FRACTION_TOLERANCE}）"
    )
    return worst <= FRACTION_TOLERANCE and counts["OK"] == 5


def run(log: Log, app, save_path) -> bool:
    basis = new_case_with_basis(app, "e15", COMPONENTS)
    basis.manager.EndBasisChange()
    phase_first(log, basis)
    reaction = phase_last(log, basis)
    gibbs_source(log, basis)
    passed = solve_fixed_k(log, basis, str(reaction.name))
    basis.case.SaveAs(str(save_path))
    log.say(f"  Case 已另存为 {save_path}")
    basis.case.Close()
    return passed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run1")
    args = parser.parse_args()
    log = Log(f"e15_fixed_k_order_{args.tag}")
    try:
        with new_instance(log) as (app, pid), dialog_guard(log, pid, include_hidden=True):
            passed = run(log, app, OUT_DIR / f"e15_fixed_k_order_{args.tag}.hsc")
    except Exception:  # 探针：失败原因本身就是要记录的结果
        log.say(traceback.format_exc())
        return 1
    log.conclude(f"Q4 {'通过' if passed else '未通过'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
