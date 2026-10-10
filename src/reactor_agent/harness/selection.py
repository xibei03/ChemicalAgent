"""SELECT 状态：问 LLM 抽特征并推荐，与规则结论对照，必要时重问一次，得出选型结果。

这里只做编排：组装上下文、调 LLM、检查和对照（spec/selection_rules.py 的纯函数）、保存。
LLM 调用的全文存进运行目录的 llm/，摘要进 Trace。
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from pathlib import Path

from reactor_agent.harness.budgets import MAX_SELECTION_REASKS
from reactor_agent.harness.calls import LlmCaller
from reactor_agent.harness.context import reask_content, selection_prompt
from reactor_agent.harness.results import write_result
from reactor_agent.llm.client import LlmClient
from reactor_agent.llm.prompts import Prompt
from reactor_agent.llm.system_prompt import load_system_prompt
from reactor_agent.observability.trace import EventBody, TraceWriter, selection_saved_event
from reactor_agent.recipes.base import ReactorRecipe
from reactor_agent.skill_loader import Skill, load_rules, load_skill
from reactor_agent.spec.enums import CallPoint, Checkpoint, EventType, ReactorType, WorkflowState
from reactor_agent.spec.selection import SelectionDraft, SelectionResult, SelectionRules
from reactor_agent.spec.selection_rules import assess, build_result, require_supported
from reactor_agent.state.models import TaskState
from reactor_agent.state.store import ArtifactName, StateStore

SELECTION_SKILL = "reactor-selection"
Ask = Callable[[str], SelectionDraft]


def select_reactor(ask: Ask, prompt: Prompt, text: str, rules: SelectionRules) -> SelectionResult:
    """问一次；有分歧或有依据不是原文原话时，带着问题重问（最多 MAX_SELECTION_REASKS 次）。"""
    draft = ask(prompt.user)
    assessment = assess(draft, text, rules)
    reasks = 0
    while not assessment.settled and reasks < MAX_SELECTION_REASKS:
        draft = ask(reask_content(prompt, draft, assessment))
        assessment = assess(draft, text, rules)
        reasks += 1
    return build_result(draft, text, assessment, reasked=reasks > 0)


@dataclass(frozen=True)
class Selector:
    """从文字描述开始的任务：创建任务，并处理 SELECT 状态。"""

    llm: LlmClient
    store: StateStore
    trace: TraceWriter
    recipes: Mapping[ReactorType, ReactorRecipe]
    skills_dir: Path

    def create_task(self, text: str) -> TaskState:
        """建运行目录，存下用户的原文，任务从 SELECT 开始。"""
        task_id = self.store.new_run(datetime.now().astimezone())
        task = TaskState(task_id=task_id, current_state=WorkflowState.SELECT)
        self.store.write_input(task_id, text)
        write_result(self.store, task_id, None, ())
        self.store.save(task)
        self._emit(task, EventBody(type=EventType.CHECKPOINT, name=Checkpoint.INPUT_SAVED.value))
        return task

    def run(self, task: TaskState) -> WorkflowState:
        """SELECT 的处理函数。不是反应过程，或者选出的类型还没有 Recipe，抛 E_UNSUPPORTED。"""
        text = self.store.read_input(task.task_id)
        skill = load_skill(self.skills_dir, SELECTION_SKILL)
        prompt = selection_prompt(load_system_prompt(), skill, text)
        ask = partial(self._ask, task, skill, prompt.system)
        result = select_reactor(ask, prompt, text, load_rules(skill, SelectionRules))
        self.store.write_artifact(task.task_id, ArtifactName.SELECTION, result)
        task.record_selection(result.summary)
        self._emit(task, selection_saved_event(result))
        require_supported(result, self.recipes)
        return WorkflowState.SPECIFY

    def _ask(self, task: TaskState, skill: Skill, system: str, user: str) -> SelectionDraft:
        caller = LlmCaller(self.llm, self.store, self.trace)
        return caller.ask(task, CallPoint.SELECT, skill, Prompt(system, user), SelectionDraft)

    def _emit(self, task: TaskState, body: EventBody) -> None:
        self.trace.append(task.task_id, task.spec_hash, task.current_state, None, body)
