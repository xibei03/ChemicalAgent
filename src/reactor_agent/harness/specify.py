"""SPECIFY 和 VALIDATE 状态：让 LLM 写 TaskSpec，代码校验和换算，通过了冻结成 ModelSpec。

这里只做编排：组装上下文、调 LLM、调 spec/ 的纯函数和 Recipe 的规则、保存、决定下一步。
换算、归一化和规则判断都不在这里；重写的轮数和终态的判定在 recovery.py 和 failures.py。
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from reactor_agent.harness.calls import LlmCaller
from reactor_agent.harness.failures import NeedsInputError, rule_error
from reactor_agent.harness.recovery import SpecAction, decide_spec
from reactor_agent.llm.client import LlmClient
from reactor_agent.llm.prompts import rewrite_content, specify_prompt
from reactor_agent.llm.system_prompt import load_system_prompt
from reactor_agent.observability.trace import EventBody, TraceWriter, spec_issues_event
from reactor_agent.recipes.base import ReactorRecipe
from reactor_agent.skill_loader import REFERENCES_DIR, load_skill, read_file
from reactor_agent.spec.components import ComponentTable
from reactor_agent.spec.enums import CallPoint, Checkpoint, EventType, ReactorType, WorkflowState
from reactor_agent.spec.intake import intake
from reactor_agent.spec.model_spec import ModelSpec, spec_hash
from reactor_agent.spec.results import Issue, SpecIssues
from reactor_agent.spec.selection import SelectionResult
from reactor_agent.spec.task_spec import blocking_missing, task_spec_model
from reactor_agent.spec.units import UnitTable
from reactor_agent.state.models import TaskState
from reactor_agent.state.store import ArtifactName, StateStore

MODELING_SKILL = "reactor-modeling"


@dataclass(frozen=True)
class Specifier:
    """写规格和校验规格的两个状态的处理函数。"""

    llm: LlmClient
    store: StateStore
    trace: TraceWriter
    recipes: Mapping[ReactorType, ReactorRecipe]
    skills_dir: Path
    components: ComponentTable
    units: UnitTable

    def specify(self, task: TaskState) -> WorkflowState:
        """SPECIFY：组装上下文，问 LLM，保存 TaskSpec。重写时带上上一次的 TaskSpec 和问题清单。"""
        selection = self.store.read_artifact(task.task_id, ArtifactName.SELECTION, SelectionResult)
        reactor_type = selection.chosen_type()
        model = task_spec_model(reactor_type)
        skill = load_skill(self.skills_dir, MODELING_SKILL)
        knowledge = [skill.body, read_file(skill, REFERENCES_DIR, f"{reactor_type.value}.md")]
        text = self.store.read_input(task.task_id)
        system = load_system_prompt()
        prompt = specify_prompt(system, knowledge, model, self.components, selection, text)
        if task.spec_rewrites > 0:
            previous = self.store.read_artifact(task.task_id, ArtifactName.TASK_SPEC, model)
            found = self.store.read_artifact(task.task_id, ArtifactName.SPEC_ISSUES, SpecIssues)
            prompt = replace(prompt, user=rewrite_content(prompt, previous, found.issues))
        caller = LlmCaller(self.llm, self.store, self.trace)
        spec = caller.ask(task, CallPoint.SPECIFY, skill, prompt, model)
        self.store.write_artifact(task.task_id, ArtifactName.TASK_SPEC, spec)
        saved = Checkpoint.TASK_SPEC_SAVED
        self._emit(task, EventBody(type=EventType.CHECKPOINT, name=saved.value))
        return WorkflowState.VALIDATE

    def validate(self, task: TaskState) -> WorkflowState:
        """VALIDATE：收下 TaskSpec（换算、通用规则、Recipe 的规则）；通过了就冻结。"""
        selection = self.store.read_artifact(task.task_id, ArtifactName.SELECTION, SelectionResult)
        reactor_type = selection.chosen_type()
        model = task_spec_model(reactor_type)
        task_spec = self.store.read_artifact(task.task_id, ArtifactName.TASK_SPEC, model)
        recipe = self.recipes[reactor_type]
        taken = intake(
            task_spec,
            self.store.read_input(task.task_id),
            reactor_type,
            (self.components, self.units),
            lambda spec: recipe.rules(spec, self.components),
        )
        if taken.spec is not None:
            return self._freeze(task, taken.spec)
        missing = bool(blocking_missing(task_spec))
        return self._not_passed(task, taken.issues, missing_declared=missing)

    def _freeze(self, task: TaskState, spec: ModelSpec) -> WorkflowState:
        path = self.store.write_artifact(task.task_id, ArtifactName.MODEL_SPEC, spec)
        task.freeze_spec(path, spec_hash(spec), tuple(case.name for case in spec.cases))
        self._emit(task, EventBody(type=EventType.CHECKPOINT, name=Checkpoint.SPEC_FROZEN.value))
        return WorkflowState.PLAN

    def _not_passed(
        self, task: TaskState, issues: tuple[Issue, ...], *, missing_declared: bool
    ) -> WorkflowState:
        """没有通过：问题清单落盘并进 Trace，然后重写，或者请用户补充，或者中止。"""
        saved = SpecIssues(rewrites_used=task.spec_rewrites, issues=issues)
        self.store.write_artifact(task.task_id, ArtifactName.SPEC_ISSUES, saved)
        self._emit(task, spec_issues_event(issues, task.spec_rewrites))
        action = decide_spec(issues, missing_declared, task.spec_rewrites)
        if action is SpecAction.REWRITE:
            task.count_rewrite()
            return WorkflowState.SPECIFY
        raise NeedsInputError(issues) if action is SpecAction.ASK_USER else rule_error(issues)

    def _emit(self, task: TaskState, body: EventBody) -> None:
        self.trace.append(task.task_id, task.spec_hash, task.current_state, None, body)
