"""结果文件 artifacts/result.json：每个工况验证后增量写，任务结束时补上终态。

执行器不把完整的结果放在内存或状态文件里，所以 VERIFY 和 REPORT 之间、重建之后、中止之前，
都靠这个文件交接。
"""

from collections.abc import Sequence

from reactor_agent.spec.enums import TaskStatus
from reactor_agent.spec.results import CaseRecord, RunResult
from reactor_agent.state.store import ArtifactName, StateStore


def read_records(store: StateStore, task_id: str) -> tuple[CaseRecord, ...]:
    """已经记下的各工况的结果。"""
    return store.read_artifact(task_id, ArtifactName.RESULT, RunResult).cases


def write_result(
    store: StateStore, task_id: str, status: TaskStatus | None, records: Sequence[CaseRecord]
) -> None:
    """写结果文件；任务还在运行时 status 是 None。"""
    run = RunResult(task_id=task_id, status=status, cases=tuple(records))
    store.write_artifact(task_id, ArtifactName.RESULT, run)


def with_record(records: Sequence[CaseRecord], record: CaseRecord) -> tuple[CaseRecord, ...]:
    """加入一个工况的记录；同名的覆盖，位置不变，所以重试不会打乱工况的顺序。"""
    if any(item.case_name == record.case_name for item in records):
        return tuple(record if i.case_name == record.case_name else i for i in records)
    return (*records, record)
