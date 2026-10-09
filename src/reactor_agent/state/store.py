"""运行目录：state.json 和 artifacts/ 的读写。

每个任务一个目录 runs/<task_id>/。写入都是原子的：先写同目录下的临时文件，再替换正式文件，
进程在任何时刻被中断，读到的文件都是完整的。
"""

import secrets
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.loading import parse_model, read_document
from reactor_agent.state.models import TaskState

STATE_FILE = "state.json"
ARTIFACTS_DIR = "artifacts"
TEMPORARY_SUFFIX = ".tmp"
TASK_ID_TIME_FORMAT = "%Y%m%d-%H%M%S"
ModelT = TypeVar("ModelT", bound=BaseModel)


class ArtifactName(StrEnum):
    """artifacts/ 下的文件。"""

    MODEL_SPEC = "model_spec.json"
    PLAN = "plan.json"
    RESULT = "result.json"


def new_task_id(now: datetime) -> str:
    """任务标识：本地时间加两位随机十六进制，如 20261002-153012-a7（计划 §10.2）。"""
    return f"{now.strftime(TASK_ID_TIME_FORMAT)}-{secrets.token_hex(1)}"


def _write_atomically(path: Path, text: str) -> None:
    temporary = path.with_name(path.name + TEMPORARY_SUFFIX)
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    except OSError as error:
        raise ReactorAgentError(ErrorCode.IO, f"写不了文件 {path}：{error}") from error


class StateStore:
    """某个 runs 目录下所有任务的状态和产物。"""

    def __init__(self, runs_dir: Path) -> None:
        self._runs_dir = runs_dir

    def run_dir(self, task_id: str) -> Path:
        """一个任务的运行目录。"""
        return self._runs_dir / task_id

    def create_run_dir(self, task_id: str) -> Path:
        """建运行目录和 artifacts/。目录已经存在说明任务标识撞了，不能覆盖别人的运行。"""
        directory = self.run_dir(task_id)
        try:
            (directory / ARTIFACTS_DIR).mkdir(parents=True)
        except OSError as error:
            raise ReactorAgentError(ErrorCode.IO, f"建不了运行目录 {directory}：{error}") from error
        return directory

    def artifact_path(self, task_id: str, name: ArtifactName) -> Path:
        """artifacts/ 下某个文件的路径。"""
        return self.run_dir(task_id) / ARTIFACTS_DIR / name.value

    def save(self, task: TaskState) -> None:
        """把任务状态原子地写到 state.json。"""
        _write_atomically(self.run_dir(task.task_id) / STATE_FILE, task.model_dump_json(indent=2))

    def load(self, task_id: str) -> TaskState:
        """读回任务状态。"""
        path = self.run_dir(task_id) / STATE_FILE
        return parse_model(TaskState, read_document(path), STATE_FILE)

    def write_artifact(self, task_id: str, name: ArtifactName, model: BaseModel) -> Path:
        """把一个模型写成 artifacts/ 下的 JSON 文件，返回路径。"""
        path = self.artifact_path(task_id, name)
        _write_atomically(path, model.model_dump_json(indent=2))
        return path

    def read_artifact(self, task_id: str, name: ArtifactName, model: type[ModelT]) -> ModelT:
        """读 artifacts/ 下的 JSON 文件并校验。"""
        return parse_model(model, read_document(self.artifact_path(task_id, name)), name.value)
