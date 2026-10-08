"""E6：用代码创建反应和反应集（全项目风险最高的一步）。

要回答的问题：
  Q1 Reactions.Add(name, Type) 的 Type 传什么？返回什么对象？
  Q2 转化反应：怎么加反应物和产物、写计量系数、设基准组分和转化率？
  Q3 平衡反应：计量系数、Keq 来源（Gibbs 自由能、固定 K）、相态怎么设？
  Q4 反应集：怎么建、怎么放进反应、怎么加入流体包？
  Q5 建这些要不要在 Basis 修改状态里？结束 Basis 之后再建行不行？
  Q6 另存重开之后反应和反应集还在吗？
做法：和 E4 一样新建 Case、组分列表、流体包（物性包 pengrob），然后逐个试。
每试一种写法都记录成功或失败；Type 的各种候选各用一个临时名字，试完删掉。

用法：python spikes/e6_reaction.py [--tag 名字]
输出：spikes/out/e6_reaction_<tag>.txt；另存的 Case 在临时目录，不提交。
"""

import argparse
import shutil
import tempfile
from pathlib import Path

from _common import Log, first_ok, new_instance, use_utf8, watch

use_utf8()

COMPONENTS = ("Methane", "H2O", "CO", "CO2", "Hydrogen", "Toluene", "Benzene", "p-Xylene")
NOTHING = object()
TYPE_CANDIDATES = (
    NOTHING,
    "conversionrxn",
    "equilibriumrxn",
    "kineticrxn",
    "Conversion",
    "Equilibrium",
    "Kinetic",
    "ConversionReaction",
    "EquilibriumReaction",
    0,
    1,
    2,
    3,
)


def make_basis(log: Log, app, directory: Path):
    """新建 Case、组分列表、流体包，停在 Basis 修改状态（还没有 EndBasisChange）。"""
    case = app.SimulationCases.Add("e6")
    manager = case.BasisManager
    component_list = manager.ComponentLists.Add("CL-1")
    for name in COMPONENTS:
        component_list.Components.Add(name)
    package = manager.FluidPackages.Add("Basis-1")
    package.ComponentList = component_list
    package.PropertyPackageName = "pengrob"
    log.say(f"Basis 已建好：{list(package.Components.Names)}")
    log.say(f"CanEndBasisChange={manager.CanEndBasisChange}")
    return case, manager, package


def add_with_type(reactions, name: str, candidate):
    """按候选写法调用 Add；NOTHING 表示不传 Type。"""
    if candidate is NOTHING:
        return reactions.Add(name)
    return reactions.Add(name, candidate)


def probe_types(log: Log, reactions) -> None:
    """Q1：Reactions.Add 的 Type 候选，每个用一个临时反应名，看返回什么。"""
    log.say("== Q1 Reactions.Add 的 Type ==")
    log.attempt("Reactions.Count（开始）", lambda: reactions.Count)
    for index, candidate in enumerate(TYPE_CANDIDATES):
        name = f"T{index}"
        label = "省略" if candidate is NOTHING else repr(candidate)
        ok, obj = log.attempt(
            f"Add({name!r}) [Type {label}]",
            lambda name=name, candidate=candidate: add_with_type(reactions, name, candidate),
        )
        if not ok:
            continue
        log.say(
            f"      返回类型 {type(obj).__name__}；Count={reactions.Count}；{list(reactions.Names)}"
        )
        for member in ("name", "TypeName", "VisibleTypeName"):
            log.attempt(
                f"      返回对象.{member}", lambda member=member, obj=obj: getattr(obj, member)
            )
        log.attempt(f"      Remove({name!r})", lambda name=name: reactions.Remove(name))
    log.attempt("Reactions.Names（试完后）", lambda: list(reactions.Names))


def build_conversion(log: Log, reactions, package):
    """Q2：转化反应 2 甲苯 → 苯 + 对二甲苯，基准组分甲苯，转化率 50%。"""
    log.say("== Q2 转化反应 ==")
    ok, reaction, _ = first_ok(
        log,
        "Reactions.Add('Tol-Disp', conversionrxn)",
        lambda: reactions.Add("Tol-Disp", "conversionrxn"),
    )
    if not ok:
        return None
    log.say(f"  类型 {type(reaction).__name__}")
    components = package.Components
    for name, coefficient in (("Toluene", -2.0), ("Benzene", 1.0), ("p-Xylene", 1.0)):
        ok, reactant, _ = first_ok(
            log,
            f"Reactants.Add({name!r})",
            lambda name=name: reaction.Reactants.Add(name),
            lambda name=name: reaction.Reactants.Add(components.Item(name)),
            lambda name=name: reaction.Reactants.Add(name, ""),
        )
        if ok:
            log.say(f"      返回对象类型 {type(reactant).__name__}")
            log.attempt(
                f"  {name}.StoichiometricCoefficientValue = {coefficient}",
                lambda reactant=reactant, coefficient=coefficient: setattr(
                    reactant, "StoichiometricCoefficientValue", coefficient
                ),
            )
    log.attempt("Reactants.Names", lambda: list(reaction.Reactants.Names))
    log.attempt("ReactantStoichCoefValue", lambda: reaction.ReactantStoichCoefValue)
    log.attempt(
        "BaseComponent = Toluene",
        lambda: setattr(reaction, "BaseComponent", components.Item("Toluene")),
    )
    log.attempt("BaseComponent 读回", lambda: reaction.BaseComponent.name)
    log.attempt("Conversion = 50", lambda: setattr(reaction, "Conversion", 50.0))
    log.attempt("Conversion 读回", lambda: reaction.Conversion)
    log.attempt("ReactionPhase", lambda: reaction.ReactionPhase)
    log.attempt("BalanceStoichiometry()", reaction.BalanceStoichiometry)
    log.attempt("BalanceErrorValue", lambda: reaction.BalanceErrorValue)
    return reaction


def probe_fractional(log: Log, reactions) -> None:
    """分数计量系数写得进去吗（后面的甲苯歧化要用 0.24、0.52 这样的系数）。"""
    log.say("== 分数计量系数 ==")
    ok, reaction = log.attempt(
        "Reactions.Add('Frac', conversionrxn)", lambda: reactions.Add("Frac", "conversionrxn")
    )
    if not ok:
        return
    for name, coefficient in (("Toluene", -2.0), ("Benzene", 1.0), ("p-Xylene", 0.24)):
        _, reactant = log.attempt(
            f"Reactants.Add({name!r})", lambda name=name: reaction.Reactants.Add(name)
        )
        log.attempt(
            f"  {name} 系数 = {coefficient}",
            lambda reactant=reactant, coefficient=coefficient: setattr(
                reactant, "StoichiometricCoefficientValue", coefficient
            ),
        )
    log.attempt(
        "ReactantStoichCoefValue（分数系数写入后）", lambda: reaction.ReactantStoichCoefValue
    )
    log.attempt("BalanceErrorValue", lambda: reaction.BalanceErrorValue)
    log.attempt("Reactions.Remove('Frac')", lambda: reactions.Remove("Frac"))


def add_reactants(log: Log, reaction, package, stoichiometry) -> None:
    for name, coefficient in stoichiometry:
        ok, reactant = log.attempt(
            f"Reactants.Add({name!r})", lambda name=name: reaction.Reactants.Add(name)
        )
        if ok:
            log.attempt(
                f"  {name}.StoichiometricCoefficientValue = {coefficient}",
                lambda reactant=reactant, coefficient=coefficient: setattr(
                    reactant, "StoichiometricCoefficientValue", coefficient
                ),
            )
    log.attempt("Reactants.Names", lambda: list(reaction.Reactants.Names))
    log.attempt("ReactantStoichCoefValue", lambda: reaction.ReactantStoichCoefValue)


def build_equilibrium(log: Log, reactions, package, name, stoichiometry):
    """Q3：平衡反应，先读默认值，再写计量系数，Keq 来源试 Gibbs 自由能。"""
    log.say(f"== Q3 平衡反应 {name} ==")
    ok, reaction = log.attempt(
        f"Reactions.Add({name!r}, equilibriumrxn)", lambda: reactions.Add(name, "equilibriumrxn")
    )
    if not ok:
        return None
    for member in (
        "LnKSource",
        "Basis",
        "BasisUnits",
        "ReactionPhase",
        "AutoDetect",
        "ActivateKTable",
        "MinTemperatureValue",
        "MaxTemperatureValue",
        "TemperatureApproachValue",
        "LogBasis",
    ):
        log.attempt(f"默认 {member}", lambda member=member: getattr(reaction, member))
    add_reactants(log, reaction, package, stoichiometry)
    log.attempt("BalanceStoichiometry()", reaction.BalanceStoichiometry)
    log.attempt("BalanceErrorValue", lambda: reaction.BalanceErrorValue)
    log.attempt("HeatOfReactionValue", lambda: reaction.HeatOfReactionValue)
    log.attempt("LnKSource = 0（Gibbs）", lambda: setattr(reaction, "LnKSource", 0))
    log.attempt("LnKSource 读回", lambda: reaction.LnKSource)
    log.attempt("ReactionPhase = 0（气相）", lambda: setattr(reaction, "ReactionPhase", 0))
    log.attempt("ReactionPhase 读回", lambda: reaction.ReactionPhase)
    return reaction


def build_sets(log: Log, manager, package) -> None:
    """Q4：反应集。"""
    log.say("== Q4 反应集 ==")
    sets = manager.ReactionPackageManager.ReactionSets
    log.attempt("ReactionSets.Count（开始）", lambda: sets.Count)
    log.attempt(
        "流体包的 ReactionPackage.ReactionSets.Names（开始）",
        lambda: list(package.ReactionPackage.ReactionSets.Names),
    )
    for set_name, members in (("Conv-Set", ("Tol-Disp",)), ("Eq-Set", ("SMR", "WGS"))):
        ok, rset, _ = first_ok(
            log,
            f"ReactionSets.Add({set_name!r})",
            lambda set_name=set_name: sets.Add(set_name),
            lambda set_name=set_name: sets.Add(set_name, "rxnset"),
        )
        if not ok:
            continue
        log.say(f"      返回类型 {type(rset).__name__}，TypeName={rset.TypeName}")
        log.attempt(
            "  Add 之后、Associate 之前，流体包的反应集",
            lambda: list(package.ReactionPackage.ReactionSets.Names),
        )
        for member in members:
            first_ok(
                log,
                f"  {set_name}.ActiveReactions.Add({member!r})",
                lambda member=member, rset=rset: rset.ActiveReactions.Add(member),
                lambda member=member, rset=rset: rset.ActiveReactions.Add(
                    manager.ReactionPackageManager.Reactions.Item(member)
                ),
            )
        log.attempt(
            f"  {set_name}.ActiveReactions.Names",
            lambda rset=rset: list(rset.ActiveReactions.Names),
        )
        log.attempt(
            f"  {set_name}.InactiveReactions.Names",
            lambda rset=rset: list(rset.InactiveReactions.Names),
        )
        log.attempt(
            f"  {set_name}.AssociateFluidPackage(fp)",
            lambda rset=rset: rset.AssociateFluidPackage(package),
        )
    log.attempt("ReactionSets.Names", lambda: list(sets.Names))
    log.attempt(
        "流体包的 ReactionPackage.ReactionSets.Names",
        lambda: list(package.ReactionPackage.ReactionSets.Names),
    )


def finish_and_verify(log: Log, app, case, manager, directory: Path) -> None:
    """Q5、Q6：结束 Basis，另存，关闭，重开，核对反应和反应集还在。"""
    log.say("== Q5、Q6 结束 Basis、另存、重开 ==")
    log.attempt("EndBasisChange()", manager.EndBasisChange)
    log.attempt("IsChangingBasis", lambda: manager.IsChangingBasis)
    reactions = manager.ReactionPackageManager.Reactions
    log.say("-- Basis 结束后，直接建反应（没有 StartBasisChange） --")
    log.attempt(
        "Reactions.Add('late1', conversionrxn)", lambda: reactions.Add("late1", "conversionrxn")
    )
    log.attempt("Reactions.Names", lambda: list(reactions.Names))
    log.say("-- StartBasisChange 之后再建 --")
    log.attempt("StartBasisChange()", manager.StartBasisChange)
    log.attempt("IsChangingBasis", lambda: manager.IsChangingBasis)
    log.attempt(
        "Reactions.Add('late2', conversionrxn)", lambda: reactions.Add("late2", "conversionrxn")
    )
    log.attempt("Reactions.Remove('late2')", lambda: reactions.Remove("late2"))
    log.attempt("Reactions.Remove('late1')", lambda: reactions.Remove("late1"))
    log.attempt("Reactions.Names", lambda: list(reactions.Names))
    log.attempt("EndBasisChange()", manager.EndBasisChange)
    log.attempt("IsChangingBasis", lambda: manager.IsChangingBasis)
    path = directory / "e6_saved.hsc"
    log.attempt("SaveAs", lambda: case.SaveAs(str(path)))
    log.attempt("Close", case.Close)
    with watch(log, "Open"):
        ok, reopened = log.attempt("Open", lambda: app.SimulationCases.Open(str(path)))
    if not ok:
        return
    rpm = reopened.BasisManager.ReactionPackageManager
    log.attempt("重开后 Reactions.Names", lambda: list(rpm.Reactions.Names))
    log.attempt("重开后 ReactionSets.Names", lambda: list(rpm.ReactionSets.Names))
    for reaction_name in list(rpm.Reactions.Names):
        reaction = rpm.Reactions.Item(reaction_name)
        log.attempt(
            f"重开后 {reaction_name}",
            lambda reaction=reaction: (
                type(reaction).__name__,
                list(reaction.Reactants.Names),
                reaction.ReactantStoichCoefValue,
            ),
        )
    for reaction_name in ("Tol-Disp", "SMR", "WGS"):
        reaction = rpm.Reactions.Item(reaction_name)
        for member in (
            "ReactionPhase",
            "HeatOfReactionValue",
            "BalanceErrorValue",
            "LnKSource",
            "Basis",
            "AutoDetect",
            "BaseComponent",
            "Conversion",
        ):
            log.attempt(
                f"重开后 {reaction_name}.{member}",
                lambda reaction=reaction, member=member: (
                    lambda value: value.name if hasattr(value, "name") else value
                )(getattr(reaction, member)),
            )
    for set_name in list(rpm.ReactionSets.Names):
        rset = rpm.ReactionSets.Item(set_name)
        log.attempt(
            f"重开后 {set_name}.ActiveReactions", lambda rset=rset: list(rset.ActiveReactions.Names)
        )
    log.attempt("reopened.Close()", reopened.Close)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run1")
    args = parser.parse_args()
    log = Log(f"e6_reaction_{args.tag}")
    directory = Path(tempfile.mkdtemp(prefix="hysys_e6_")).resolve()
    try:
        with new_instance(log) as (app, _pid):
            with watch(log, "make_basis"):
                case, manager, package = make_basis(log, app, directory)
            reactions = manager.ReactionPackageManager.Reactions
            probe_types(log, reactions)
            build_conversion(log, reactions, package)
            probe_fractional(log, reactions)
            build_equilibrium(
                log,
                reactions,
                package,
                "SMR",
                (("Methane", -1.0), ("H2O", -1.0), ("CO", 1.0), ("Hydrogen", 3.0)),
            )
            build_equilibrium(
                log,
                reactions,
                package,
                "WGS",
                (("CO", -1.0), ("H2O", -1.0), ("CO2", 1.0), ("Hydrogen", 1.0)),
            )
            build_sets(log, manager, package)
            finish_and_verify(log, app, case, manager, directory)
    finally:
        shutil.rmtree(directory, ignore_errors=True)


if __name__ == "__main__":
    main()
