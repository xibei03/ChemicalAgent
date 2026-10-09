"""Basis：组分列表、流体包和物性包。

新建的 Case 一开始就处在 Basis 修改状态（台账 H3、H5），配好流体包后要 EndBasisChange 才有流程图。
本阶段只支持新 Case：已经有流体包时只做确认，不修改（R3）。同名的流体包会弹窗并再建一个（L26），
所以创建之前先看有没有。
"""

from typing import Any

from reactor_agent.backends.hysys_com.com_errors import com_call
from reactor_agent.backends.hysys_com.lookup import (
    basis_is_changing,
    find_by_name,
    fluid_package_of,
    names_of,
    require_fluid_package,
)
from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.enums import PropertyPackage, ResultStatus
from reactor_agent.spec.matching import require_match, thermo_differences
from reactor_agent.spec.snapshot import ComponentInfo, ThermoSnapshot
from reactor_agent.spec.tool_args import EnsureThermoArgs
from reactor_agent.spec.tool_results import Outcome, ThermoData

# 物性包要用内部名设置，界面名都被拒绝（台账 H7）。
PROPERTY_PACKAGE_NAMES = {PropertyPackage.PENG_ROBINSON: "pengrob"}
COMPONENT_LIST_NAME = "CL-1"
FLUID_PACKAGE_NAME = "Basis-1"


def _component_info(component: Any) -> ComponentInfo:
    return ComponentInfo(
        name=str(component.name),
        formula=str(component.Formula).strip() or None,  # HYSYS 给的分子式带尾部空格
        is_solid=bool(component.IsSolid),
    )


def _package_from_internal_name(internal_name: str) -> PropertyPackage | None:
    for package, name in PROPERTY_PACKAGE_NAMES.items():
        if name == internal_name:
            return package
    return None


def read_thermo(case: Any) -> ThermoSnapshot | None:
    """读流体包的物性包和组分表；还没有流体包时是 None。"""
    package = fluid_package_of(case)
    if package is None:
        return None
    with com_call(ErrorCode.NOT_FOUND, "读取流体包"):
        components = tuple(
            _component_info(package.Components.Item(name)) for name in package.Components.Names
        )
        return ThermoSnapshot(
            fluid_package=str(package.name),
            property_package=_package_from_internal_name(str(package.PropertyPackage.TypeName)),
            components=components,
        )


def component_names(case: Any) -> tuple[str, ...]:
    """流体包的组分名，顺序就是物流组成向量的顺序。还没有流体包是 E_NOT_FOUND。"""
    return names_of(require_fluid_package(case).Components, "组分")


def _add_component(component_list: Any, name: str) -> None:
    with com_call(ErrorCode.COMPONENT_NOT_FOUND, f"添加组分 {name}"):
        canonical = str(component_list.Components.Add(name).name)
    if canonical != name:
        raise ReactorAgentError(
            ErrorCode.COMPONENT_NOT_FOUND,
            f"组分名 {name!r} 不是库里的规范名，应当是 {canonical!r}",
            {"requested": name, "canonical": canonical},
        )


def _component_list(manager: Any) -> Any:
    """名为 CL-1 的组分列表，没有就建。上次建到一半失败留下的列表直接复用，最后靠读回比对组分表。"""
    existing = find_by_name(manager.ComponentLists, COMPONENT_LIST_NAME, "组分列表")
    if existing is not None:
        return existing
    with com_call(ErrorCode.COMPONENT_NOT_FOUND, "建组分列表"):
        return manager.ComponentLists.Add(COMPONENT_LIST_NAME)


def _build(case: Any, args: EnsureThermoArgs) -> None:
    manager = case.BasisManager
    component_list = _component_list(manager)
    for name in args.components:
        _add_component(component_list, name)
    with com_call(ErrorCode.PP_UNSUPPORTED, "建流体包"):
        package = manager.FluidPackages.Add(FLUID_PACKAGE_NAME)
        package.ComponentList = component_list
    with com_call(ErrorCode.PP_UNSUPPORTED, "设置物性包"):
        package.PropertyPackageName = PROPERTY_PACKAGE_NAMES[args.property_package]
    with com_call(ErrorCode.BASIS_LOCKED, "结束 Basis 的修改"):
        manager.EndBasisChange()


def _require_basis_ended(case: Any, code: ErrorCode) -> None:
    """结束 Basis 的修改是 ensure_thermo 的后置条件，写完要读回确认（台账 H5）。"""
    if basis_is_changing(case):
        raise ReactorAgentError(code, "Basis 还在修改状态：流体包已经配好，但结束修改没有完成")


def _thermo_data(snapshot: ThermoSnapshot, args: EnsureThermoArgs) -> ThermoData:
    return ThermoData(
        fluid_package=snapshot.fluid_package,
        components=args.components,
        property_package=args.property_package,
    )


def ensure_thermo(case: Any, args: EnsureThermoArgs) -> Outcome[ThermoData]:
    """确保组分表和物性包就绪，并结束 Basis 的修改。已有的流体包只确认，不一致是冲突。"""
    existing = read_thermo(case)
    if existing is not None:
        require_match(ErrorCode.CONFLICT, "流体包", thermo_differences(existing, args))
        _require_basis_ended(case, ErrorCode.CONFLICT)
        return Outcome(ResultStatus.UNCHANGED, _thermo_data(existing, args))
    _build(case, args)
    created = read_thermo(case)
    if created is None:
        raise ReactorAgentError(ErrorCode.READBACK_MISMATCH, "创建流体包之后读不到它")
    require_match(ErrorCode.READBACK_MISMATCH, "流体包", thermo_differences(created, args))
    _require_basis_ended(case, ErrorCode.READBACK_MISMATCH)
    return Outcome(ResultStatus.CREATED, _thermo_data(created, args))
