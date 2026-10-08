"""e8、e9、e10 共用的建模步骤和读结果函数。

每个函数对应台账"调用序列"里的一步，只用已确认的调用（H3 至 H20）。参数里的物理量带单位后缀。
不进 src/；阶段 1A 写 Backend 时以台账为准，不是以这个文件为准。
"""

from dataclasses import dataclass

STATUS_FLAGS = {"OK": 1, "NotSolved": 2, "Warning": 4, "UnderSpecified": 8, "Error": 16}
PROPERTY_PACKAGE = "pengrob"
MASS_BALANCE_TOLERANCE = 1e-4


@dataclass
class Basis:
    """新建 Case 的 Basis 一侧：Case、Basis 管理器、流体包、组分顺序。"""

    case: object
    manager: object
    package: object
    components: tuple[str, ...]


def new_case_with_basis(app, case_name: str, components: tuple[str, ...]) -> Basis:
    """新建空白 Case，建组分列表、流体包，物性包用内部名 pengrob（H3、H7、H8）。"""
    case = app.SimulationCases.Add(case_name)
    manager = case.BasisManager
    component_list = manager.ComponentLists.Add("CL-1")
    for name in components:
        component_list.Components.Add(name)
    package = manager.FluidPackages.Add("Basis-1")
    package.ComponentList = component_list
    package.PropertyPackageName = PROPERTY_PACKAGE
    return Basis(case, manager, package, components)


def add_reaction(basis: Basis, name: str, type_name: str, stoichiometry, **settings):
    """建一个反应，计量系数负为反应物、正为产物；其余设置按成员名写入（H9、H10）。"""
    reaction = basis.manager.ReactionPackageManager.Reactions.Add(name, type_name)
    for component, coefficient in stoichiometry:
        reaction.Reactants.Add(component).StoichiometricCoefficientValue = coefficient
    for member, value in settings.items():
        setattr(reaction, member, value)
    return reaction


def add_reaction_set(basis: Basis, name: str, members: tuple[str, ...]):
    """建反应集，加入成员，挂到流体包（H11）。"""
    reaction_set = basis.manager.ReactionPackageManager.ReactionSets.Add(name)
    for member in members:
        reaction_set.ActiveReactions.Add(member)
    reaction_set.AssociateFluidPackage(basis.package)
    return reaction_set


def make_feed(
    flowsheet,
    basis: Basis,
    name: str,
    temperature_c: float,
    pressure_kpa: float,
    fractions: dict[str, float],
    molar_flow_kmol_h: float,
):
    """进料物流：T、P、组成（摩尔分率）、摩尔流量，写完立即闪蒸（H12 至 H14）。"""
    stream = flowsheet.MaterialStreams.Add(name)
    stream.Temperature.SetValue(temperature_c, "C")
    stream.Pressure.SetValue(pressure_kpa, "kPa")
    stream.ComponentMolarFraction.Values = tuple(fractions.get(c, 0.0) for c in basis.components)
    stream.MolarFlow.SetValue(molar_flow_kmol_h, "kgmole/h")
    return stream


def add_reactor(
    flowsheet, name: str, type_name: str, feeds, vapour, liquid, energy=None, reaction_set=None
):
    """建反应器并连接进料（可多股）、两股出料、可选的能流和反应集，压降 0（H15、H16）。"""
    reactor = flowsheet.Operations.Add(name, type_name)
    for feed in feeds:
        reactor.Feeds.Add(feed)
    reactor.VapourProduct = vapour
    reactor.LiquidProduct = liquid
    if energy is not None:
        reactor.EnergyStream = energy
    if reaction_set is not None:
        reactor.ReactionSet = reaction_set
    reactor.PressureDrop.SetValue(0.0, "kPa")
    return reactor


def read_stream(stream, components: tuple[str, ...]) -> dict[str, object]:
    """物流的温度、压力、总流量、按组分的摩尔流量和摩尔分率（H20）。"""
    flows = dict(zip(components, stream.ComponentMolarFlow.GetValues("kgmole/h"), strict=True))
    fractions = dict(zip(components, stream.ComponentMolarFraction.Values, strict=True))
    return {
        "T_C": stream.Temperature.GetValue("C"),
        "P_kPa": stream.Pressure.GetValue("kPa"),
        "kmol_h": stream.MolarFlow.GetValue("kgmole/h"),
        "kg_h": stream.MassFlow.GetValue("kg/h"),
        "flows": flows,
        "fractions": fractions,
    }


def mass_balance_error(feeds, vapour, liquid) -> float:
    """质量守恒相对误差：|出 - 进| / 进，质量流量 kg/h。"""
    mass_in = sum(feed.MassFlow.GetValue("kg/h") for feed in feeds)
    mass_out = vapour.MassFlow.GetValue("kg/h") + liquid.MassFlow.GetValue("kg/h")
    return abs(mass_out - mass_in) / mass_in


def status_counts(case) -> dict[str, int]:
    """流程图各状态的对象个数（H19）。"""
    return {name: int(case.GetFlowsheetStatus(flag)) for name, flag in STATUS_FLAGS.items()}
