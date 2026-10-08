"""反应和反应集。

反应的内部类型名、反应相和平衡常数来源的取值见台账 H9 至 H11；类型库里的枚举名和实际取值对不上，
不要用枚举名。反应集创建之后要 AssociateFluidPackage 才算加入流体包。结束 Basis 之后建反应和反应集
完全可用，不需要 StartBasisChange（台账 L31）。
"""

from collections.abc import Mapping
from typing import Any, TypeVar

from reactor_agent.backends.hysys_com.com_errors import com_call
from reactor_agent.backends.hysys_com.lookup import find_by_name, names_of
from reactor_agent.backends.hysys_com.thermo import component_names
from reactor_agent.backends.hysys_com.variables import read_plain
from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.enums import KeqSource, ReactionKind, ReactionPhase, ResultStatus
from reactor_agent.spec.matching import (
    name_differences,
    reaction_differences,
    reaction_set_differences,
    require_match,
)
from reactor_agent.spec.snapshot import ReactionSetSnapshot, ReactionSnapshot
from reactor_agent.spec.tool_args import (
    ConversionReaction,
    EnsureReactionArgs,
    EnsureReactionSetArgs,
    EquilibriumReaction,
    ReactionDefinition,
    StoichiometricTerm,
)
from reactor_agent.spec.tool_results import Outcome, ReactionData, ReactionSetData

REACTION_TYPE_NAMES = {
    ReactionKind.CONVERSION: "conversionrxn",
    ReactionKind.EQUILIBRIUM: "equilibriumrxn",
}
PHASE_CODES = {ReactionPhase.VAPOUR: 0, ReactionPhase.COMBINED: 5}
# LnKSource 的实际取值：2 是 Gibbs 自由能（新建时的默认值，不用写），3 是固定 K（台账 H10）。
KEQ_SOURCE_CODES = {KeqSource.GIBBS_ENERGY: 2, KeqSource.FIXED_K: 3}
# 固定 K 按摩尔分率基准：ReactionBasis_enum 的 rbMoleFracBasis。
FIXED_K_BASIS = 5
# BalanceErrorValue 是计量系数乘分子量之和（kg/kmol），平衡的反应为 0；分数系数只有舍入的误差。
BALANCE_ERROR_TOLERANCE_KG_PER_KMOL = 0.1

KeyT = TypeVar("KeyT")


def _key_for(table: Mapping[KeyT, Any], value: object, what: str) -> KeyT:
    for key, code in table.items():
        if code == value:
            return key
    raise ReactorAgentError(ErrorCode.UNSUPPORTED, f"不支持的{what}：{value}")


def _read_definition(reaction: Any, kind: ReactionKind) -> ReactionDefinition:
    stoichiometry = tuple(
        StoichiometricTerm(component=str(name), coefficient=float(coefficient))
        for name, coefficient in zip(
            reaction.Reactants.Names, reaction.ReactantStoichCoefValue, strict=True
        )
    )
    phase = _key_for(PHASE_CODES, int(reaction.ReactionPhase), "反应相")
    if kind is ReactionKind.CONVERSION:
        return ConversionReaction(
            stoichiometry=stoichiometry,
            phase=phase,
            base_component=str(reaction.BaseComponent.name),
            conversion_percent=float(reaction.Conversion),
        )
    source = _key_for(KEQ_SOURCE_CODES, int(reaction.LnKSource), "平衡常数来源")
    constant = float(reaction.EquilibriumConstant) if source is KeqSource.FIXED_K else None
    return EquilibriumReaction(
        stoichiometry=stoichiometry, phase=phase, keq_source=source, equilibrium_constant=constant
    )


def reaction_kind(reaction: Any) -> ReactionKind:
    """反应的类型，由 HYSYS 读回的内部类型名决定。"""
    with com_call(ErrorCode.NOT_FOUND, "读取反应类型"):
        return _key_for(REACTION_TYPE_NAMES, str(reaction.TypeName), "反应类型")


def read_reaction(reaction: Any) -> ReactionSnapshot:
    """读一个反应的定义和质量不守恒量。"""
    kind = reaction_kind(reaction)
    with com_call(ErrorCode.NOT_FOUND, "读取反应"):
        return ReactionSnapshot(
            name=str(reaction.name),
            definition=_read_definition(reaction, kind),
            balance_error_kg_per_kmol=read_plain(reaction.BalanceErrorValue),
        )


def _write_parameters(case: Any, reaction: Any, definition: ReactionDefinition) -> None:
    if isinstance(definition, ConversionReaction):
        package = case.BasisManager.FluidPackages.Item(0)
        reaction.BaseComponent = package.Components.Item(definition.base_component)
        reaction.Conversion = definition.conversion_percent
    elif definition.keq_source is KeqSource.FIXED_K:
        reaction.Basis = FIXED_K_BASIS
        reaction.LnKSource = KEQ_SOURCE_CODES[KeqSource.FIXED_K]
        reaction.EquilibriumConstant = definition.equilibrium_constant


def _check_components(case: Any, definition: ReactionDefinition) -> None:
    known = set(component_names(case))
    missing = sorted({term.component for term in definition.stoichiometry} - known)
    if missing:
        raise ReactorAgentError(
            ErrorCode.COMPONENT_NOT_FOUND,
            f"反应里的组分不在组分表里：{missing}",
            {"components": ", ".join(missing)},
        )


def _create_reaction(case: Any, reactions: Any, args: EnsureReactionArgs) -> Any:
    definition = args.reaction
    _check_components(case, definition)
    with com_call(ErrorCode.REACTION_INVALID, f"创建反应 {args.name}"):
        reaction = reactions.Add(args.name, REACTION_TYPE_NAMES[definition.kind])
        for term in definition.stoichiometry:
            reactant = reaction.Reactants.Add(term.component)
            reactant.StoichiometricCoefficientValue = term.coefficient
        _write_parameters(case, reaction, definition)
        # 反应相要最后写：写 Basis 会把它重置成合并相（台账 H10、L34）。
        reaction.ReactionPhase = PHASE_CODES[definition.phase]
    return reaction


def _check_balance(snapshot: ReactionSnapshot) -> None:
    error = snapshot.balance_error_kg_per_kmol
    if error is None or abs(error) > BALANCE_ERROR_TOLERANCE_KG_PER_KMOL:
        raise ReactorAgentError(
            ErrorCode.REACTION_INVALID,
            f"反应 {snapshot.name} 的质量不守恒（计量系数乘分子量之和 {error} kg/kmol）",
            {"balance_error_kg_per_kmol": str(error)},
        )


def _reaction_data(snapshot: ReactionSnapshot) -> ReactionData:
    return ReactionData(
        name=snapshot.name,
        kind=snapshot.definition.kind,
        balance_error_kg_per_kmol=snapshot.balance_error_kg_per_kmol,
    )


def _reactions_of(case: Any) -> Any:
    with com_call(ErrorCode.NOT_FOUND, "取反应集合"):
        return case.BasisManager.ReactionPackageManager.Reactions


def ensure_reaction(case: Any, args: EnsureReactionArgs) -> Outcome[ReactionData]:
    """确保反应存在，计量系数和类型参数读回一致。已有同名反应只确认，不一致是冲突。"""
    reactions = _reactions_of(case)
    subject = f"反应 {args.name}"
    existing = find_by_name(reactions, args.name, "反应")
    if existing is not None:
        snapshot = read_reaction(existing)
        differences = reaction_differences(snapshot.definition, args.reaction)
        require_match(ErrorCode.CONFLICT, subject, differences)
        return Outcome(ResultStatus.UNCHANGED, _reaction_data(snapshot))
    created = read_reaction(_create_reaction(case, reactions, args))
    differences = (
        *name_differences(created.name, args.name),
        *reaction_differences(created.definition, args.reaction),
    )
    require_match(ErrorCode.READBACK_MISMATCH, subject, differences)
    _check_balance(created)
    return Outcome(ResultStatus.CREATED, _reaction_data(created))


def _manager_of(case: Any) -> Any:
    with com_call(ErrorCode.NOT_FOUND, "取反应管理器"):
        return case.BasisManager.ReactionPackageManager


def read_reaction_set(case: Any, reaction_set: Any) -> ReactionSetSnapshot:
    """读一个反应集的成员，以及有没有挂到流体包。"""
    with com_call(ErrorCode.NOT_FOUND, "读取反应集"):
        package = case.BasisManager.FluidPackages.Item(0)
        name = str(reaction_set.name)
        return ReactionSetSnapshot(
            name=name,
            reactions=tuple(str(member) for member in reaction_set.ActiveReactions.Names),
            attached_to_fluid_package=name in list(package.ReactionPackage.ReactionSets.Names),
        )


def reaction_set_kinds(case: Any, name: str) -> frozenset[ReactionKind] | None:
    """反应集里各个成员的反应类型；没有这个反应集返回 None。"""
    manager = _manager_of(case)
    reaction_set = find_by_name(manager.ReactionSets, name, "反应集")
    if reaction_set is None:
        return None
    members = names_of(reaction_set.ActiveReactions, "反应集成员")
    return frozenset(reaction_kind(manager.Reactions.Item(member)) for member in members)


def _check_members_exist(manager: Any, args: EnsureReactionSetArgs) -> None:
    missing = sorted(set(args.reactions) - set(names_of(manager.Reactions, "反应")))
    if missing:
        raise ReactorAgentError(
            ErrorCode.NOT_FOUND,
            f"反应集 {args.name} 的成员反应还没有创建：{missing}",
            {"reactions": ", ".join(missing)},
        )


def ensure_reaction_set(case: Any, args: EnsureReactionSetArgs) -> Outcome[ReactionSetData]:
    """确保反应集存在、成员一致并且已挂到流体包。已有同名反应集只确认，不一致是冲突。"""
    manager = _manager_of(case)
    subject = f"反应集 {args.name}"
    existing = find_by_name(manager.ReactionSets, args.name, "反应集")
    if existing is not None:
        snapshot = read_reaction_set(case, existing)
        require_match(ErrorCode.CONFLICT, subject, reaction_set_differences(snapshot, args))
        data = ReactionSetData(name=args.name, reactions=snapshot.reactions)
        return Outcome(ResultStatus.UNCHANGED, data)
    _check_members_exist(manager, args)
    with com_call(ErrorCode.ATTACH_FAILED, f"创建反应集 {args.name}"):
        reaction_set = manager.ReactionSets.Add(args.name)
        for member in args.reactions:
            reaction_set.ActiveReactions.Add(member)
        reaction_set.AssociateFluidPackage(case.BasisManager.FluidPackages.Item(0))
    created = read_reaction_set(case, reaction_set)
    require_match(ErrorCode.READBACK_MISMATCH, subject, reaction_set_differences(created, args))
    return Outcome(
        ResultStatus.CREATED, ReactionSetData(name=args.name, reactions=created.reactions)
    )
