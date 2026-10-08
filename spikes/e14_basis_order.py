"""E14（1A）：结束 Basis 之后再建反应和反应集，反应器能不能用上，结果对不对。

背景：R3（D15 已确认）要求 basis.ensure_thermo 在末尾 EndBasisChange()，所以之后的
basis.ensure_reaction、basis.ensure_reaction_set 都是在 Basis 结束之后建反应和反应集。
0A 至 0C 的探针里反应集都是在 EndBasisChange 之前建的，E6 只证明了结束之后可以 Reactions.Add。

要回答的问题：
  Q1 结束 Basis 之后 Reactions.Add、ReactionSets.Add、ActiveReactions.Add、AssociateFluidPackage
     能不能成功（不调用 StartBasisChange）？
  Q2 之后把反应集挂到转化反应器，求解结果与解析解（甲苯歧化，摩尔分率 0.5/0.25/0.06/0.13/0.06）
     一致吗？
  Q3 如果 Q1 失败，用 StartBasisChange() ... EndBasisChange() 包住这些调用行不行？
  Q4 ReactionPhase 显式写 0（气相）和 5（合并相），读回是否一致？

用法：python spikes/e14_basis_order.py [--tag 名字]
输出：spikes/out/e14_basis_order_<tag>.txt；direct 变体的 Case 另存为同名 .hsc。
"""

import argparse
import traceback

from _common import OUT_DIR, Log, dialog_guard, new_instance, use_utf8
from chain_kit import (
    add_reaction,
    add_reaction_set,
    add_reactor,
    make_feed,
    new_case_with_basis,
    read_stream,
    status_counts,
)

use_utf8()

COMPONENTS = ("Toluene", "Benzene", "p-Xylene", "m-Xylene", "o-Xylene")
STOICHIOMETRY = (
    ("Toluene", -2.0),
    ("Benzene", 1.0),
    ("p-Xylene", 0.24),
    ("m-Xylene", 0.52),
    ("o-Xylene", 0.24),
)
EXPECTED = {"Toluene": 0.5, "Benzene": 0.25, "p-Xylene": 0.06, "m-Xylene": 0.13, "o-Xylene": 0.06}
FRACTION_TOLERANCE = 0.001
VARIANTS = ("direct", "wrapped")


def build(log: Log, app, variant: str, save_path) -> bool:
    """结束 Basis 之后建反应、反应集和反应器；wrapped 变体用 Start/EndBasisChange 包住建反应集。"""
    basis = new_case_with_basis(app, f"e14_{variant}", COMPONENTS)
    manager = basis.manager
    manager.EndBasisChange()
    log.say(f"[{variant}] EndBasisChange 之后 IsChangingBasis={manager.IsChangingBasis}")
    if variant == "wrapped":
        manager.StartBasisChange()
        log.say(f"[{variant}] StartBasisChange 之后 IsChangingBasis={manager.IsChangingBasis}")
    base = basis.package.Components.Item("Toluene")
    add_reaction(
        basis,
        "Tol-Disp",
        "conversionrxn",
        STOICHIOMETRY,
        BaseComponent=base,
        Conversion=50.0,
        ReactionPhase=0,
    )
    reaction_set = add_reaction_set(basis, "Conv-Set", ("Tol-Disp",))
    if variant == "wrapped":
        manager.EndBasisChange()
    log.say(f"[{variant}] 反应集成员 {list(reaction_set.ActiveReactions.Names)}")
    log.say(f"[{variant}] 流体包的反应集 {list(basis.package.ReactionPackage.ReactionSets.Names)}")
    flowsheet = basis.case.Flowsheet
    feed = make_feed(flowsheet, basis, "Feed", 380.0, 25.0 * 100.0, {"Toluene": 1.0}, 108.53)
    vapour = flowsheet.MaterialStreams.Add("Vap")
    liquid = flowsheet.MaterialStreams.Add("Liq")
    add_reactor(
        flowsheet, "CRV-100", "ConversionReactorOp", (feed,), vapour, liquid, None, reaction_set
    )
    counts = status_counts(basis.case)
    log.say(f"[{variant}] 求解后的流程图状态 {counts}")
    data = read_stream(vapour, basis.components)
    worst = max(abs(data["fractions"][name] - EXPECTED[name]) for name in COMPONENTS)
    log.say(f"[{variant}] 出口摩尔分率 { {k: round(v, 4) for k, v in data['fractions'].items()} }")
    log.say(f"[{variant}] 与解析解的最大偏差 {worst:.5f}（要求 ≤ {FRACTION_TOLERANCE}）")
    passed = worst <= FRACTION_TOLERANCE and counts["OK"] == 4
    if save_path is not None:
        basis.case.SaveAs(str(save_path))
        log.say(f"[{variant}] Case 已另存为 {save_path}")
    if variant == "direct":
        check_phases(log, basis)
    basis.case.Close()
    return passed


def check_phases(log: Log, basis) -> None:
    """Q4：显式写 ReactionPhase 0 和 5，读回。"""
    log.say("== Q4 ReactionPhase 显式写入 ==")
    reactions = basis.manager.ReactionPackageManager.Reactions
    for phase in (0, 5):
        name = f"Phase-{phase}"
        reaction = reactions.Add(name, "conversionrxn")
        reaction.Reactants.Add("Toluene").StoichiometricCoefficientValue = -2.0
        reaction.Reactants.Add("Benzene").StoichiometricCoefficientValue = 1.0
        reaction.Reactants.Add("p-Xylene").StoichiometricCoefficientValue = 1.0
        log.say(f"  {name} 默认 ReactionPhase={reaction.ReactionPhase}")
        reaction.ReactionPhase = phase
        log.say(f"  {name} 写 {phase} 之后读回 {reaction.ReactionPhase}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run1")
    args = parser.parse_args()
    log = Log(f"e14_basis_order_{args.tag}")
    outcomes = {}
    for variant in VARIANTS:
        log.say(f"==== 变体 {variant} ====")
        save_path = OUT_DIR / f"e14_basis_order_{args.tag}.hsc" if variant == "direct" else None
        try:
            with new_instance(log) as (app, pid), dialog_guard(log, pid, include_hidden=True):
                outcomes[variant] = build(log, app, variant, save_path)
        except Exception:  # 探针：失败原因本身就是要记录的结果
            log.say(traceback.format_exc())
            outcomes[variant] = False
        log.say(f"[{variant}] {'通过' if outcomes[variant] else '未通过'}")
    log.conclude(f"各变体的结果 {outcomes}")
    return 0 if outcomes["direct"] or outcomes["wrapped"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
