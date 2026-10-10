"""TaskSpec 测试共用的构造函数：理想的 LLM 会为三类体系写出的 TaskSpec，和零件。

体系是通用的类比体系，不是考核场景的原文；数值取整，方便手算。单位表和组分表读的是 config/ 下
真正在用的那两份，所以测试检查的就是真实的配置。
"""

from pathlib import Path

from reactor_agent.spec.components import ComponentTable, load_component_table
from reactor_agent.spec.enums import PressureBasis
from reactor_agent.spec.task_spec import (
    AmountScale,
    CaseTask,
    CompositionBasis,
    CompositionItem,
    CompositionTask,
    ConversionReactionTask,
    ConversionTaskSpec,
    EquilibriumReactionTask,
    EquilibriumTaskSpec,
    FeedTask,
    GibbsTaskSpec,
    PressureQuantity,
    Quantity,
    ShareTask,
    Source,
    SplitProductTask,
    TermTask,
)
from reactor_agent.spec.units import UnitTable, load_unit_table

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def components() -> ComponentTable:
    return load_component_table(CONFIG_DIR / "components.yaml")


def units() -> UnitTable:
    return load_unit_table(CONFIG_DIR / "units.yaml")


def q(value: float, unit: str, *, assumed: str | None = None) -> Quantity:
    """用户给的量；写了 assumed（依据）就是假设的量。"""
    if assumed is None:
        return Quantity(value=value, unit=unit, source=Source.USER, rationale=None)
    return Quantity(value=value, unit=unit, source=Source.ASSUMED, rationale=assumed)


def pressure(
    value: float,
    unit: str = "bar",
    basis: PressureBasis = PressureBasis.UNSTATED,
    *,
    assumed: str | None = None,
) -> PressureQuantity:
    source = Source.USER if assumed is None else Source.ASSUMED
    return PressureQuantity(value=value, unit=unit, source=source, rationale=assumed, basis=basis)


def composition(
    *items: tuple[str, float | None],
    basis: CompositionBasis = CompositionBasis.MOLE,
    scale: AmountScale = AmountScale.RATIO,
) -> CompositionTask:
    """各项是（组分名，份额）；份额为 None 的是余量组分。"""
    return CompositionTask(
        basis=basis,
        scale=scale,
        items=tuple(
            CompositionItem(component=name, amount=amount, is_remainder=amount is None)
            for name, amount in items
        ),
        source=Source.USER,
        rationale=None,
    )


def feed(
    temperature: Quantity | None,
    flow: Quantity | None,
    mix: CompositionTask | str | None,
    *,
    own_pressure: PressureQuantity | None = None,
    name: str = "进料",
) -> FeedTask:
    """mix 是字符串时是纯物质（pure_component），否则是混合物的组成。"""
    return FeedTask(
        name=name,
        temperature=temperature,
        pressure=own_pressure,
        flow=flow,
        pure_component=mix if isinstance(mix, str) else None,
        composition=None if isinstance(mix, str) else mix,
    )


def terms(*items: tuple[str, float]) -> tuple[TermTask, ...]:
    return tuple(TermTask(component=name, coefficient=value) for name, value in items)


def conversion_reaction(
    reactants: tuple[tuple[str, float], ...],
    products: tuple[tuple[str, float], ...],
    base: str,
    percent: Quantity | None,
    splits: tuple[SplitProductTask, ...] = (),
) -> ConversionReactionTask:
    return ConversionReactionTask(
        reactants=terms(*reactants),
        products=terms(*products),
        split_products=splits,
        base_component=base,
        conversion=percent,
    )


def split(coefficient: float, *shares: tuple[str, float]) -> SplitProductTask:
    return SplitProductTask(
        coefficient=coefficient,
        shares=tuple(ShareTask(component=name, share=share) for name, share in shares),
    )


def equilibrium_reaction(
    reactants: tuple[tuple[str, float], ...],
    products: tuple[tuple[str, float], ...],
    constant: float | None = None,
) -> EquilibriumReactionTask:
    return EquilibriumReactionTask(
        reactants=terms(*reactants),
        products=terms(*products),
        split_products=(),
        equilibrium_constant=constant,
    )


COMMON: dict[str, object] = {
    "pressure_drop": None,
    "adiabatic_stated": False,
    "property_package": None,
    "conversion_metrics": (),
    "yield_metrics": (),
    "ratio_metrics": (),
    "assumptions": (),
    "ambiguities": (),
    "missing": (),
}


def equilibrium_task(**changes: object) -> EquilibriumTaskSpec:
    """两个可逆反应、两个出口温度、流量由 LLM 假设、只给了一个操作压力的平衡反应器任务。"""
    mix = composition(("methane", 1.0), ("water", 2.7))
    data: dict[str, object] = {
        **COMMON,
        "feeds": (feed(q(500, "℃"), q(2000, "kmol/h", assumed="取一个中等规模"), mix),),
        "reactor_pressure": pressure(10.0, "bar"),
        "cases": (
            CaseTask(name="T700", outlet_temperature=q(700, "°C"), duty=None),
            CaseTask(name="T600", outlet_temperature=q(600, "℃"), duty=None),
        ),
        "reactions": (
            equilibrium_reaction((("methane", 1), ("water", 1)), (("CO", 1), ("hydrogen", 3))),
            equilibrium_reaction((("CO", 1), ("water", 1)), (("CO2", 1), ("hydrogen", 1))),
        ),
        **changes,
    }
    return EquilibriumTaskSpec.model_validate(data)


def conversion_task(**changes: object) -> ConversionTaskSpec:
    """质量流量、MPa 压力、产物拆给三种异构体、没有出口温度的转化反应器任务。"""
    reaction = conversion_reaction(
        (("toluene", 2),),
        (("benzene", 1),),
        "toluene",
        q(50, "%"),
        (split(1, ("p-xylene", 24), ("m-xylene", 52), ("o-xylene", 24)),),
    )
    data: dict[str, object] = {
        **COMMON,
        "feeds": (feed(q(380, "℃"), q(10000, "kg/h"), "toluene"),),
        "reactor_pressure": pressure(2.5, "MPa"),
        "cases": (CaseTask(name="基准工况", outlet_temperature=None, duty=None),),
        "reactions": (reaction,),
        **changes,
    }
    return ConversionTaskSpec.model_validate(data)


def gibbs_task(**changes: object) -> GibbsTaskSpec:
    """标准体积流量、质量浓度带余量、固体进料、指定出口温度的 Gibbs 反应器任务。"""
    mix = composition(
        ("coal", 62.0), ("water", None), basis=CompositionBasis.MASS, scale=AmountScale.PERCENT
    )
    data: dict[str, object] = {
        **COMMON,
        "feeds": (feed(q(40, "摄氏度"), q(80000, "Nm3/h"), mix, own_pressure=pressure(40, "bar")),),
        "reactor_pressure": None,
        "cases": (CaseTask(name="基准工况", outlet_temperature=q(1400, "度"), duty=None),),
        "product_components": ("CO", "H2", "CO2", "CH4"),
        **changes,
    }
    return GibbsTaskSpec.model_validate(data)


def smr_task(**changes: object) -> EquilibriumTaskSpec:
    """同一个平衡体系，另一组数：入口温度、操作压力、流量和两个出口温度都不同。"""
    mix = composition(("methane", 1.0), ("water", 2.7))
    data: dict[str, object] = {
        "feeds": (feed(q(520, "℃"), q(3700, "kmol/h", assumed="取一个中等规模"), mix),),
        "reactor_pressure": pressure(13.5, "bar"),
        "cases": (
            CaseTask(name="T710", outlet_temperature=q(710, "°C"), duty=None),
            CaseTask(name="T600", outlet_temperature=q(600, "℃"), duty=None),
        ),
        **changes,
    }
    return equilibrium_task(**data)
