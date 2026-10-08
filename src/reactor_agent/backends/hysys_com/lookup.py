"""按名字在 HYSYS 的集合里查找对象。

同名创建时 HYSYS 的行为各不相同：自动改名、再建一个、重复加一行、弹窗，甚至进程崩溃（台账 L26），
所以创建之前一律先查，不依赖 HYSYS 自己对同名的处理。
"""

from typing import Any

from reactor_agent.backends.hysys_com.com_errors import com_call
from reactor_agent.errors import ErrorCode, ReactorAgentError


def names_of(collection: Any, what: str) -> tuple[str, ...]:
    """集合里全部对象的名字。"""
    with com_call(ErrorCode.NOT_FOUND, f"列出{what}"):
        return tuple(str(name) for name in collection.Names)


def find_by_name(collection: Any, name: str, what: str) -> Any | None:
    """按名字取集合里的对象；没有这个名字返回 None。"""
    with com_call(ErrorCode.NOT_FOUND, f"查找{what} {name}"):
        return collection.Item(name) if name in list(collection.Names) else None


def basis_is_changing(case: Any) -> bool:
    """Basis 是否还在修改状态。新建的 Case 一开始就是，ensure_thermo 结束它（台账 H5）。"""
    with com_call(ErrorCode.NOT_FOUND, "读取 Basis 状态"):
        return bool(case.BasisManager.IsChangingBasis)


def flowsheet_of(case: Any) -> Any:
    """Case 的流程图。Basis 还在修改状态时流程图不可用，那是 E_BASIS_LOCKED。"""
    if basis_is_changing(case):
        raise ReactorAgentError(
            ErrorCode.BASIS_LOCKED, "Basis 还在修改状态，先调用 basis.ensure_thermo"
        )
    with com_call(ErrorCode.NOT_FOUND, "取流程图"):
        return case.Flowsheet


def fluid_package_of(case: Any) -> Any | None:
    """Case 的流体包（本阶段只有一个）；还没有时是 None。"""
    with com_call(ErrorCode.NOT_FOUND, "取流体包"):
        packages = case.BasisManager.FluidPackages
        return packages.Item(0) if int(packages.Count) > 0 else None


def require_fluid_package(case: Any) -> Any:
    """Case 的流体包；还没有时是 E_NOT_FOUND。"""
    package = fluid_package_of(case)
    if package is None:
        raise ReactorAgentError(ErrorCode.NOT_FOUND, "还没有流体包，先调用 basis.ensure_thermo")
    return package


def reaction_manager_of(case: Any) -> Any:
    """Case 的反应管理器，反应和反应集都挂在它下面。"""
    with com_call(ErrorCode.NOT_FOUND, "取反应管理器"):
        return case.BasisManager.ReactionPackageManager
