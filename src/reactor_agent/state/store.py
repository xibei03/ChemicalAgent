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
from reactor_agent.spec.llm import LlmCallRecord
from reactor_agent.spec.loading import parse_model, read_document
from reactor_agent.state.models import TaskState

STATE_FILE = "state.json"
ARTIFACTS_DIR = "artifacts"
# 建模用的 Case 和出错时留下的现场放在这里，不和各工况的 .hsc 混在一起，也就不会撞名。
WORK_DIR = "work"
# LLM 调用的全文（提示和回复）。摘要进 Trace，全文放这里。
LLM_DIR = "llm"
MAX_ID_ATTEMPTS = 20
TEMPORARY_SUFFIX = ".tmp"
TASK_ID_TIME_FORMAT = "%Y%m%d-%H%M%S"
ModelT = TypeVar("ModelT", bound=BaseModel)


class ArtifactName(StrEnum):
    """artifacts/ 下的文件。"""

    INPUT = "input.txt"
    SELECTION = "selection.json"
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

    def work_dir(self, task_id: str) -> Path:
        """建模用的 Case 和出错现场的目录。"""
        return self.run_dir(task_id) / WORK_DIR

    def create_run_dir(self, task_id: str) -> Path:
        """建运行目录、artifacts/ 和 work/。目录已经存在是 E_CONFLICT：不能覆盖别人的运行。"""
        directory = self.run_dir(task_id)
        try:
            directory.mkdir(parents=True)
            (directory / ARTIFACTS_DIR).mkdir()
            (directory / WORK_DIR).mkdir()
        except FileExistsError as error:
            raise ReactorAgentError(ErrorCode.CONFLICT, f"运行目录已经存在：{directory}") from error
        except OSError as error:
            raise ReactorAgentError(ErrorCode.IO, f"建不了运行目录 {directory}：{error}") from error
        return directory

    def new_run(self, now: datetime) -> str:
        """分配一个没有用过的任务标识并建好运行目录。

        标识的随机部分只有一个字节，同一秒内两次创建有 1/256 的概率撞号，撞了就换一个。
        """
        for _ in range(MAX_ID_ATTEMPTS):
            task_id = new_task_id(now)
            try:
                self.create_run_dir(task_id)
            except ReactorAgentError as error:
                if error.code is not ErrorCode.CONFLICT:
                    raise
                continue
            return task_id
        raise ReactorAgentError(ErrorCode.IO, f"连续 {MAX_ID_ATTEMPTS} 次分配的任务标识都已被用过")

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

    def write_input(self, task_id: str, text: str) -> Path:
        """把用户的原文存成 artifacts/input.txt，之后每一步都从这里读，不依赖调用方还拿着它。"""
        path = self.artifact_path(task_id, ArtifactName.INPUT)
        _write_atomically(path, text)
        return path

    def read_input(self, task_id: str) -> str:
        """读回用户的原文。"""
        path = self.artifact_path(task_id, ArtifactName.INPUT)
        try:
            return path.read_text(encoding="utf-8")
        except OSError as error:
            raise ReactorAgentError(ErrorCode.IO, f"读不了文件 {path}：{error}") from error

    def write_llm_log(self, task_id: str, call_point: str, record: LlmCallRecord) -> Path:
        """把一次 LLM 调用的全文存到 llm/<调用点>-<序号>.json，序号取第一个没用过的。"""
        directory = self.run_dir(task_id) / LLM_DIR
        try:
            directory.mkdir(exist_ok=True)
        except OSError as error:
            raise ReactorAgentError(ErrorCode.IO, f"建不了目录 {directory}：{error}") from error
        number = 1
        while (path := directory / f"{call_point}-{number}.json").exists():
            number += 1
        _write_atomically(path, record.model_dump_json(indent=2))
        return path
