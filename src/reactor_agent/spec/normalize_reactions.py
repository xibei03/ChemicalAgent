"""反应、组分表和待求指标的规范化。

反应式：反应物取负、产物取正；拆给几个组分的产物（几种异构体），按配比把系数分下去（系数的总和不变，
元素守恒不受影响）。转化率换算成百分数并检查范围；平衡常数没有给时，来源取 Gibbs 自由能并登记假设。
Gibbs 反应器没有反应式，组分表是进料的组分加上候选产物。
"""

from collections.abc import Mapping
from dataclasses import dataclass

from reactor_agent.errors import ErrorCode
from reactor_agent.spec.enums import KeqSource, MetricKind, ReactionKind
from reactor_agent.spec.notes import Context
from reactor_agent.spec.quantities import (
    CONVERSION,
    MAX_CONVERSION_PERCENT,
    convert_value,
    resolve_name,
)
from reactor_agent.spec.task_spec import (
    ConversionReactionTask,
    EquilibriumReactionTask,
    GibbsTaskSpec,
    ReactionTask,
    SplitProductTask,
    TaskSpec,
    TermTask,
)

Term = dict[str, object]
# 配比小于它就当作 0：这个组分在产物里不出现。
ZERO_SHARE = 1e-12


@dataclass(frozen=True)
class ReactionData:
    """一个反应的规格（还没有校验，最后由 ModelSpec 校验），和它用到的组分。"""

    spec: Mapping[str, object]
    components: tuple[str, ...]


def _terms(ctx: Context, items: tuple[TermTask, ...], sign: float, path: str) -> list[Term]:
    terms: list[Term] = []
    for index, item in enumerate(items):
        name = resolve_name(ctx, item.component, f"{path}[{index}].component")
        if item.coefficient <= 0:
            message = f"系数要写正数（反应物和产物由所在的列表区分），这里是 {item.coefficient:g}"
            ctx.notes.problem(ErrorCode.SCHEMA, f"{path}[{index}].coefficient", message)
        elif name is not None:
            terms.append({"component": name, "coefficient": sign * item.coefficient})
    return terms


def _split_terms(ctx: Context, items: tuple[SplitProductTask, ...], path: str) -> list[Term]:
    """拆给几个组分的产物：每个组分的系数是产物的系数乘它的配比占比。"""
    terms: list[Term] = []
    for index, product in enumerate(items):
        where = f"{path}[{index}]"
        total = sum(share.share for share in product.shares)
        if product.coefficient <= 0 or total <= 0 or any(s.share < 0 for s in product.shares):
            ctx.notes.problem(ErrorCode.SCHEMA, where, "系数和配比要写正数，配比之和要大于 0")
            continue
        for k, share in enumerate(product.shares):
            name = resolve_name(ctx, share.component, f"{where}.shares[{k}].component")
            if name is None or share.share < ZERO_SHARE:
                continue  # 配比为 0 的组分不生成，系数为 0 的项没有意义
            terms.append(
                {"component": name, "coefficient": product.coefficient * share.share / total}
            )
    return terms


def _stoichiometry(ctx: Context, task: ReactionTask, path: str) -> list[Term]:
    """反应式的各项。反应物或产物为空，由 ModelSpec 的校验报告。"""
    return [
        *_terms(ctx, task.reactants, -1.0, f"{path}.reactants"),
        *_terms(ctx, task.products, 1.0, f"{path}.products"),
        *_split_terms(ctx, task.split_products, f"{path}.split_products"),
    ]


def _names(terms: list[Term], *extra: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys([*(str(t["component"]) for t in terms), *extra]))


def _conversion(ctx: Context, task: ConversionReactionTask, path: str) -> float | None:
    """转化率（百分数）。没有给、是假设、超出 (0, 100] 都是问题。"""
    where = f"{path}.conversion_percent"
    if task.conversion is None:
        ctx.notes.problem(ErrorCode.RULE, where, "转化率没有给出", user_fixable=True)
        return None
    percent = convert_value(ctx, task.conversion, where, CONVERSION)
    if percent is not None and percent > MAX_CONVERSION_PERCENT:
        given = f"{task.conversion.value:g} {task.conversion.unit}".strip()
        message = f"转化率 {given} 超过了 100%"
        ctx.notes.problem(ErrorCode.RULE, where, message, user_fixable=True)
        return None
    return percent


def _conversion_reaction(
    ctx: Context, task: ConversionReactionTask, path: str
) -> ReactionData | None:
    terms = _stoichiometry(ctx, task, f"{path}.stoichiometry")
    base = resolve_name(ctx, task.base_component, f"{path}.base_component")
    percent = _conversion(ctx, task, path)
    if base is None or percent is None:
        return None
    spec: dict[str, object] = {
        "kind": ReactionKind.CONVERSION,
        "stoichiometry": terms,
        "base_component": base,
        "conversion_percent": percent,
    }
    return ReactionData(spec, _names(terms, base))


def _equilibrium_reaction(
    ctx: Context, task: EquilibriumReactionTask, path: str
) -> ReactionData | None:
    terms = _stoichiometry(ctx, task, f"{path}.stoichiometry")
    spec: dict[str, object] = {"kind": ReactionKind.EQUILIBRIUM, "stoichiometry": terms}
    constant = task.equilibrium_constant
    if constant is None:
        reason = "原文没有给平衡常数，由 Gibbs 自由能计算"
        spec["keq_source"] = ctx.notes.default(f"{path}.keq_source", KeqSource.GIBBS_ENERGY, reason)
    elif constant <= 0:
        message = f"平衡常数 {constant:g} 必须是正数"
        ctx.notes.problem(
            ErrorCode.RULE, f"{path}.equilibrium_constant", message, user_fixable=True
        )
        return None
    else:
        spec["keq_source"] = KeqSource.FIXED_K
        spec["equilibrium_constant"] = constant
    return ReactionData(spec, _names(terms))


def normalize_reactions(ctx: Context, task: TaskSpec) -> list[ReactionData]:
    """转化、平衡反应器的反应。Gibbs 反应器没有反应式；没有反应是一个问题。"""
    if isinstance(task, GibbsTaskSpec):
        return []
    if not task.reactions:
        ctx.notes.problem(ErrorCode.RULE, "reactions", "没有给出反应", user_fixable=True)
    built: list[ReactionData | None] = []
    for index, reaction in enumerate(task.reactions):
        path = f"reactions[{index}]"
        if isinstance(reaction, ConversionReactionTask):
            built.append(_conversion_reaction(ctx, reaction, path))
        elif isinstance(reaction, EquilibriumReactionTask):
            built.append(_equilibrium_reaction(ctx, reaction, path))
    return [item for item in built if item is not None]


def product_components(ctx: Context, task: TaskSpec) -> tuple[str, ...]:
    """Gibbs 反应器的候选产物（规范名）；别的反应器没有。"""
    if not isinstance(task, GibbsTaskSpec):
        return ()
    names = [
        resolve_name(ctx, text, f"product_components[{index}]")
        for index, text in enumerate(task.product_components)
    ]
    return tuple(name for name in names if name is not None)


def normalize_metrics(ctx: Context, task: TaskSpec) -> list[Mapping[str, object]]:
    """待求指标：转化率、收率、比值，组分名解析成规范名。问题的路径是 TaskSpec 里的字段。"""
    metrics: list[Mapping[str, object]] = []
    for index, item in enumerate(task.conversion_metrics):
        name = resolve_name(ctx, item.component, f"conversion_metrics[{index}].component")
        if name is not None:
            metrics.append({"kind": MetricKind.CONVERSION, "component": name})
    for index, item_y in enumerate(task.yield_metrics):
        where = f"yield_metrics[{index}]"
        product = resolve_name(ctx, item_y.product, f"{where}.product")
        basis = resolve_name(ctx, item_y.reference_component, f"{where}.reference_component")
        if product is not None and basis is not None:
            metrics.append({"kind": MetricKind.YIELD, "product": product, "basis": basis})
    for index, item_r in enumerate(task.ratio_metrics):
        where = f"ratio_metrics[{index}]"
        top = resolve_name(ctx, item_r.numerator, f"{where}.numerator")
        bottom = resolve_name(ctx, item_r.denominator, f"{where}.denominator")
        if top is not None and bottom is not None:
            metrics.append({"kind": MetricKind.RATIO, "numerator": top, "denominator": bottom})
    return metrics
