"""把各个读取函数的结果拼成整个模型的快照。只读，没有副作用。"""

from collections.abc import Callable
from typing import Any, TypeVar

from reactor_agent.backends.hysys_com.cases import case_path
from reactor_agent.backends.hysys_com.com_errors import com_call
from reactor_agent.backends.hysys_com.lookup import basis_is_changing, names_of
from reactor_agent.backends.hysys_com.reactions import read_reaction, read_reaction_set
from reactor_agent.backends.hysys_com.reactors import read_reactor
from reactor_agent.backends.hysys_com.solving import read_solve_status
from reactor_agent.backends.hysys_com.streams import read_energy_stream, read_stream
from reactor_agent.backends.hysys_com.thermo import read_thermo
from reactor_agent.errors import ErrorCode
from reactor_agent.spec.snapshot import (
    EnergyStreamSnapshot,
    ModelSnapshot,
    ReactorSnapshot,
    SolveStatus,
    StreamSnapshot,
)

ItemT = TypeVar("ItemT")


def _read_all(collection: Any, what: str, read: Callable[[Any], ItemT]) -> tuple[ItemT, ...]:
    with com_call(ErrorCode.NOT_FOUND, f"读取{what}"):
        return tuple(read(collection.Item(name)) for name in names_of(collection, what))


def _read_flowsheet(
    case: Any, components: tuple[str, ...]
) -> tuple[
    tuple[StreamSnapshot, ...],
    tuple[EnergyStreamSnapshot, ...],
    tuple[ReactorSnapshot, ...],
    SolveStatus,
]:
    with com_call(ErrorCode.NOT_FOUND, "取流程图"):
        flowsheet = case.Flowsheet
    streams = _read_all(
        flowsheet.MaterialStreams, "物流", lambda item: read_stream(item, components)
    )
    energy_streams = _read_all(flowsheet.EnergyStreams, "能流", read_energy_stream)
    operations = _read_all(flowsheet.Operations, "操作", read_reactor)
    reactors = tuple(reactor for reactor in operations if reactor is not None)
    return streams, energy_streams, reactors, read_solve_status(case)


def read_snapshot(case: Any) -> ModelSnapshot:
    """读整个模型：流体包、反应、反应集、物流、能流、反应器和求解状态。"""
    thermo = read_thermo(case)
    with com_call(ErrorCode.NOT_FOUND, "取反应管理器"):
        manager = case.BasisManager.ReactionPackageManager
    reactions = _read_all(manager.Reactions, "反应", read_reaction)
    reaction_sets = _read_all(
        manager.ReactionSets, "反应集", lambda item: read_reaction_set(case, item)
    )
    streams: tuple[StreamSnapshot, ...] = ()
    energy_streams: tuple[EnergyStreamSnapshot, ...] = ()
    reactors: tuple[ReactorSnapshot, ...] = ()
    solve = SolveStatus(is_solving=False, objects=())
    if thermo is not None and not basis_is_changing(case):
        components = tuple(component.name for component in thermo.components)
        streams, energy_streams, reactors, solve = _read_flowsheet(case, components)
    return ModelSnapshot(
        case_path=case_path(case),
        thermo=thermo,
        reactions=reactions,
        reaction_sets=reaction_sets,
        streams=streams,
        energy_streams=energy_streams,
        reactors=reactors,
        solve=solve,
    )
