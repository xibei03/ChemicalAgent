"""E6b：平衡反应的 Keq 来源（LnKSource）怎么设置，数字和界面选项怎么对应。

E6 里发现：新建的平衡反应 LnKSource 默认读出 2，写 0（类型库里的 eqrxn_Gibbs）之后读回仍是 2。
要回答：
  Q1 LnKSource 的写入到底有没有效果？哪些值写得进去？
  Q2 每个取值下，哪些相关成员可读（EquilibriumConstant、LnK 公式系数、K 表、热力学计算的 K）？
     这是把数字和界面选项（Gibbs 自由能、Ln(K) 公式、固定 K、K-T 表）对应起来的依据。
  Q3 写入的顺序有没有影响（先配好计量系数和相态，或先 BalanceStoichiometry）？
  Q4 默认来源下，求解时 HYSYS 用什么算平衡常数？（留给后面的反应器求解，这里只看设置）
做法：新建 Case 和 Basis，建 SMR 平衡反应，在不同条件下写 LnKSource 并读回。

用法：python spikes/e6b_keq_source.py [--tag 名字]
输出：spikes/out/e6b_keq_source_<tag>.txt
"""

import argparse

from _common import Log, new_instance, use_utf8, watch
from e6_reaction import add_reactants, make_basis

use_utf8()

SOURCE_VALUES = (0, 1, 2, 3, 4)
RELATED_MEMBERS = (
    "LnKSource",
    "EquilibriumConstant",
    "LnKEquationAParameter",
    "LnKEquationBParameter",
    "LnKEquationCParameter",
    "LnKEquationDParameter",
    "ActivateKTable",
    "AutoDetect",
    "Basis",
    "KEqValue",
    "KCalculatedValue",
    "HeatOfReactionValue",
    "MinTemperatureValue",
    "MaxTemperatureValue",
    "THighValue",
    "TLowValue",
)
SMR = (("Methane", -1.0), ("H2O", -1.0), ("CO", 1.0), ("Hydrogen", 3.0))


def read_related(log: Log, reaction, label: str) -> None:
    for member in RELATED_MEMBERS:
        log.attempt(f"{label}.{member}", lambda member=member: getattr(reaction, member))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run1")
    args = parser.parse_args()
    log = Log(f"e6b_keq_source_{args.tag}")
    with new_instance(log) as (app, _pid):
        with watch(log, "make_basis"):
            case, manager, package = make_basis(log, app, None)
        reactions = manager.ReactionPackageManager.Reactions
        reaction = reactions.Add("SMR", "equilibriumrxn")
        add_reactants(log, reaction, package, SMR)
        log.say("== 默认状态 ==")
        read_related(log, reaction, "默认")
        log.say("== Q1、Q2 逐个写 LnKSource ==")
        for value in SOURCE_VALUES:
            log.attempt(
                f"LnKSource = {value}", lambda value=value: setattr(reaction, "LnKSource", value)
            )
            log.attempt("  读回 LnKSource", lambda: reaction.LnKSource)
            read_related(log, reaction, f"  [写 {value} 之后]")
        log.say("== 固定 K：LnKSource = 3，写 EquilibriumConstant ==")
        log.attempt("LnKSource = 3", lambda: setattr(reaction, "LnKSource", 3))
        log.attempt(
            "EquilibriumConstant = 12.5", lambda: setattr(reaction, "EquilibriumConstant", 12.5)
        )
        log.attempt("EquilibriumConstant 读回", lambda: reaction.EquilibriumConstant)
        log.attempt("LnKSource 读回", lambda: reaction.LnKSource)
        log.attempt("LnKSource = 2（回到 Gibbs 自由能）", lambda: setattr(reaction, "LnKSource", 2))
        log.attempt("LnKSource 读回", lambda: reaction.LnKSource)
        log.say("== Q3 先 BalanceStoichiometry、再设相态，再写 LnKSource = 0 ==")
        log.attempt("BalanceStoichiometry()", reaction.BalanceStoichiometry)
        log.attempt("ReactionPhase = 0", lambda: setattr(reaction, "ReactionPhase", 0))
        log.attempt("LnKSource = 0", lambda: setattr(reaction, "LnKSource", 0))
        log.attempt("  读回 LnKSource", lambda: reaction.LnKSource)
        log.say("== 结束 Basis 之后再试一次 ==")
        log.attempt("EndBasisChange()", manager.EndBasisChange)
        log.attempt("LnKSource 读回", lambda: reaction.LnKSource)
        log.attempt("LnKSource = 0（Basis 结束后）", lambda: setattr(reaction, "LnKSource", 0))
        log.attempt("  读回 LnKSource", lambda: reaction.LnKSource)
        read_related(log, reaction, "  [Basis 结束后]")
        log.attempt("case.Close()", case.Close)


if __name__ == "__main__":
    main()
