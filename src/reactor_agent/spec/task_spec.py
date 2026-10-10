"""TaskSpec：LLM 写下的“用户说了什么”。

数值和单位照原文抄，不换算；来源、假设和缺失都显式声明。代码把它规范化成 ModelSpec（normalize.py）。
结构要浅，每个字段的含义要单一：LLM 填得对不对，主要取决于它。每个字段的 description 会被渲染成
给 LLM 的字段说明（llm/schema_guide.py），所以要写准确、简短。

给 LLM 的 JSON Schema 只用台账 L39 验证过的子集：没有默认值、没有长度约束、没有联合。所以每种反应器
一个类，类型由选型结论决定，LLM 的输出里没有这个字段，它没法改；约束写在校验器里。
"""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Self

from pydantic import Field, model_validator

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.base import FrozenModel
from reactor_agent.spec.enums import PressureBasis, ReactorType


class Source(StrEnum):
    """一个量的来源。"""

    USER = "user"
    ASSUMED = "assumed"


class CompositionBasis(StrEnum):
    """组成的基准。体积分率只对气体成立，按摩尔分率处理。"""

    MOLE = "mole"
    MASS = "mass"
    VOLUME = "volume"


class AmountScale(StrEnum):
    """组成里各项数值的写法：0 到 1 的分率、百分数，或者配比。"""

    FRACTION = "fraction"
    PERCENT = "percent"
    RATIO = "ratio"


class AssumptionField(StrEnum):
    """一条假设针对规格里的哪一部分。取值就是规格里的字段名。"""

    FEEDS = "feeds"
    REACTIONS = "reactions"
    COMPONENTS = "components"
    CASES = "cases"
    METRICS = "metrics"


class MissingField(StrEnum):
    """缺失信息的种类。代码按它判断缺的是不是可以假设的量。"""

    FEED_TEMPERATURE = "feed_temperature"
    FEED_PRESSURE = "feed_pressure"
    FEED_COMPOSITION = "feed_composition"
    FEED_FLOW = "feed_flow"
    CONVERSION = "conversion"
    REACTIONS = "reactions"
    OTHER = "other"


class Quantity(FrozenModel):
    """一个物理量：数值、单位（照原文）、来源。"""

    value: float = Field(description="原文里的数值，照抄；不要换算，不要做算术")
    unit: str = Field(
        description="原文里的单位写法，照抄（如 ℃、MPa、kg/h、Nm3/h）；不要换算成别的单位"
    )
    source: Source = Field(description="user：原文给出的数；assumed：原文没有给、由你假设的数")
    rationale: str | None = Field(description="source 为 assumed 时写假设的依据；为 user 时写 null")

    @model_validator(mode="after")
    def _assumption_has_a_reason(self) -> Self:
        if self.source is Source.ASSUMED and not (self.rationale or "").strip():
            raise ValueError("来源是 assumed 的量必须写 rationale（假设的依据）")
        return self


class PressureQuantity(Quantity):
    """压力：多一个基准。"""

    basis: PressureBasis = Field(
        description="absolute：原文说是绝压；gauge：原文说是表压；unstated：原文没有说明"
    )


class CompositionItem(FrozenModel):
    """组成里的一项。"""

    component: str = Field(
        description="组分名，用常用英文名或分子式（如 methane、CH4、water）；不必是 HYSYS 的规范名"
    )
    amount: float | None = Field(
        description="原文里这个组分的份额、百分数或配比中的一项，照抄；余量组分写 null"
    )
    is_remainder: bool = Field(
        description="是不是“其余”“余量”（原文没给份额，是总量减去其他组分）；是则 amount 写 null"
    )


class CompositionTask(FrozenModel):
    """一股进料的组成：基准、数值的写法、各项。代码负责归一化和换算，你不要算。"""

    basis: CompositionBasis = Field(
        description="mole：摩尔分率或摩尔比；mass：质量分率、质量浓度或质量比；volume：气体的体积分率"
    )
    scale: AmountScale = Field(
        description="各项 amount 的写法：fraction 是 0 到 1 的小数，percent 是百分数"
        "（62 表示 62%），ratio 是配比（1 : 2.7 写成 1 和 2.7；纯物质写一项，amount 为 1）"
    )
    items: tuple[CompositionItem, ...] = Field(description="各组分，至少一项")
    source: Source = Field(
        description="user：份额是原文给的（组分名是你替换的也算）；assumed：原文没有给份额，是你编的"
    )
    rationale: str | None = Field(description="source 为 assumed 时写依据；为 user 时写 null")


class FeedTask(FrozenModel):
    """一股进料。原文没有给的量写 null，并且列进 missing。"""

    name: str = Field(description="这股进料的称呼，如“进料”“空气”；只有一股时写“进料”")
    temperature: Quantity | None = Field(description="进料温度；原文没有给写 null")
    pressure: PressureQuantity | None = Field(
        description="原文明确说是这股进料的压力。原文只给了一个压力、没说是进料的"
        "（操作压力、反应压力、出口压力）时写 null，放进 reactor_pressure"
    )
    flow: Quantity | None = Field(
        description="这股进料的总流量，摩尔、质量或标准体积流量都行，单位照原文。原文没有给、"
        "或者题面允许自定时，由你给一个合理的取值，source 写 assumed 并写依据"
    )
    pure_component: str | None = Field(
        description="进料只有一种物质（原文只说进料是它，没提别的物质）时写它的名字，"
        "composition 写 null；进料有几种物质时写 null"
    )
    composition: CompositionTask | None = Field(
        description="进料有几种物质时的组成；进料是纯物质（写了 pure_component）时写 null；"
        "原文完全没有给组成时也写 null"
    )


class CaseTask(FrozenModel):
    """一个工况：同一台反应器在不同规定下的一次计算。"""

    name: str = Field(description="工况的称呼，如 T710、基准工况；只有一个工况时写“基准工况”")
    outlet_temperature: Quantity | None = Field(
        description="规定的出口温度，包括反应温度、操作温度、出口温度；没有规定写 null"
    )
    duty: Quantity | None = Field(description="规定的热负荷；没有规定写 null")


class TermTask(FrozenModel):
    """反应式里的一项。"""

    component: str = Field(description="组分名，常用英文名或分子式")
    coefficient: float = Field(description="这一项的系数，照原文，写正数；原文没写系数就是 1")


class ShareTask(FrozenModel):
    """一个产物拆给的某个组分，和它所占的配比。"""

    component: str = Field(description="组分名，常用英文名或分子式")
    share: float = Field(description="这个组分所占的配比，不要求归一化（如 24、52、24）")


class SplitProductTask(FrozenModel):
    """一个产物拆给几个组分（比如几种异构体）。代码按配比把系数分下去。"""

    coefficient: float = Field(description="这个产物在反应式里的系数，写正数")
    shares: tuple[ShareTask, ...] = Field(description="拆给的各个组分和配比")


class ReactionTask(FrozenModel):
    """各类反应共有的部分：反应式。"""

    reactants: tuple[TermTask, ...] = Field(description="反应物")
    products: tuple[TermTask, ...] = Field(description="产物里只对应一个组分的项")
    split_products: tuple[SplitProductTask, ...] = Field(
        description="产物里拆给几个组分的项（比如几种异构体）；没有写空数组"
    )


class ConversionReactionTask(ReactionTask):
    """转化反应：基准组分按转化率反应。"""

    base_component: str = Field(description="转化率针对的基准组分（反应物之一）")
    conversion: Quantity | None = Field(
        description="转化率，照原文写（50% 写 50，单位 %）；原文没有给写 null"
    )


class EquilibriumReactionTask(ReactionTask):
    """平衡反应。"""

    equilibrium_constant: float | None = Field(
        description="原文给出的平衡常数数值，照抄；没有给写 null（由 Gibbs 自由能计算）"
    )


class ConversionMetricTask(FrozenModel):
    """待求指标：某个组分的转化率。"""

    component: str = Field(description="被转化的组分")


class YieldMetricTask(FrozenModel):
    """待求指标：收率 = 产物的出料摩尔流量 ÷ 参照组分的进料摩尔流量。用户另有定义时按用户的。"""

    product: str = Field(description="产物组分")
    reference_component: str = Field(description="收率相对的原料组分")


class RatioMetricTask(FrozenModel):
    """待求指标：两个组分出料摩尔流量之比。"""

    numerator: str = Field(description="分子组分")
    denominator: str = Field(description="分母组分")


class AssumptionTask(FrozenModel):
    """一条假设：针对规格的哪一部分、做了什么假设、依据。"""

    field: AssumptionField = Field(description="针对规格的哪一部分")
    statement: str = Field(description="假设的内容，一句话，含取值")
    rationale: str = Field(description="依据")


class MissingItem(FrozenModel):
    """一条缺失信息。"""

    field: MissingField = Field(description="缺的是哪一类信息")
    feed_index: int | None = Field(description="缺的是第几股进料的（从 0 起）；与进料无关写 null")
    description: str = Field(description="缺什么，一句话")


class TaskSpecBase(FrozenModel):
    """各类反应器共有的部分。三个子类各自加上这种反应器需要的字段。"""

    feeds: tuple[FeedTask, ...] = Field(description="全部进料，一股一项；只建原文给出的进料")
    reactor_pressure: PressureQuantity | None = Field(
        description="原文给的不属于某股进料的压力（操作压力、反应压力、出口压力）；没有写 null"
    )
    pressure_drop: Quantity | None = Field(description="原文给的反应器压降；没有给写 null")
    cases: tuple[CaseTask, ...] = Field(
        description="工况：每个出口温度或热负荷一个；都没有规定时写一个工况，两个量都写 null"
    )
    adiabatic_stated: bool = Field(description="原文明确说了绝热操作")
    property_package: str | None = Field(
        description="原文指定的物性包或状态方程，照抄；没有指定写 null"
    )
    conversion_metrics: tuple[ConversionMetricTask, ...] = Field(
        description="用户要求计算的转化率；没有写空数组"
    )
    yield_metrics: tuple[YieldMetricTask, ...] = Field(
        description="用户要求计算的收率；没有写空数组"
    )
    ratio_metrics: tuple[RatioMetricTask, ...] = Field(
        description="用户要求计算的两个组分的比值；没有写空数组"
    )
    assumptions: tuple[AssumptionTask, ...] = Field(
        description="你做的、不能用某个量的 source 表达的假设；没有写空数组"
    )
    ambiguities: tuple[str, ...] = Field(
        description="原文有歧义的地方，以及用户给了但你觉得不合理的数值（照原值，不要改）；没有写空数组"
    )
    missing: tuple[MissingItem, ...] = Field(
        description="原文没有给、又不能由你假设的信息；没有写空数组"
    )


class ConversionTaskSpec(TaskSpecBase):
    """转化反应器：每个反应带基准组分和转化率。"""

    reactions: tuple[ConversionReactionTask, ...] = Field(description="原文给出的全部反应")


class EquilibriumTaskSpec(TaskSpecBase):
    """平衡反应器：每个反应是可逆的平衡反应。"""

    reactions: tuple[EquilibriumReactionTask, ...] = Field(description="原文给出的全部反应")


class GibbsTaskSpec(TaskSpecBase):
    """Gibbs 反应器：不需要反应式，产物由组分表决定。"""

    product_components: tuple[str, ...] = Field(
        description="可能生成的产物组分（进料里已有的不用重复），常用英文名或分子式；"
        "用户写出的反应的产物，和这类过程常见的副产物，都要列进来"
    )


TaskSpec = ConversionTaskSpec | EquilibriumTaskSpec | GibbsTaskSpec
# 缺失信息里可以由 LLM 假设一个取值的种类；其余的缺了就是缺少关键信息，只能请用户补充。
ASSUMABLE_MISSING = frozenset({MissingField.FEED_FLOW})

TASK_SPEC_MODELS: Mapping[ReactorType, type[TaskSpec]] = MappingProxyType(
    {
        ReactorType.CONVERSION: ConversionTaskSpec,
        ReactorType.EQUILIBRIUM: EquilibriumTaskSpec,
        ReactorType.GIBBS: GibbsTaskSpec,
    }
)


def task_spec_model(reactor_type: ReactorType) -> type[TaskSpec]:
    """这种反应器的 TaskSpec 类。没有的（PFR、CSTR）是 E_UNSUPPORTED。"""
    model = TASK_SPEC_MODELS.get(reactor_type)
    if model is None:
        raise ReactorAgentError(ErrorCode.UNSUPPORTED, f"还不支持 {reactor_type.value} 反应器")
    return model


def blocking_missing(task: TaskSpec) -> tuple[MissingItem, ...]:
    """缺失信息里不可以假设的那些：重写也变不出信息，只能请用户补充。"""
    return tuple(item for item in task.missing if item.field not in ASSUMABLE_MISSING)
