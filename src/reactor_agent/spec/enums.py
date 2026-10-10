"""工具契约里用到的全部枚举。

取值只列台账（docs/HYSYS_INTEGRATION.md）里验证过的；需要白名单的地方，枚举本身就是白名单。
"""

from enum import StrEnum


class ToolName(StrEnum):
    """工具名，格式是“分组.动作”。"""

    SESSION_CONNECT = "session.connect"
    CASE_ENSURE = "case.ensure"
    CASE_SAVE = "case.save"
    CASE_CLOSE = "case.close"
    BASIS_ENSURE_THERMO = "basis.ensure_thermo"
    BASIS_ENSURE_REACTION = "basis.ensure_reaction"
    BASIS_ENSURE_REACTION_SET = "basis.ensure_reaction_set"
    FLOWSHEET_ENSURE_STREAM = "flowsheet.ensure_stream"
    FLOWSHEET_ENSURE_REACTOR = "flowsheet.ensure_reactor"
    FLOWSHEET_SET_SPEC = "flowsheet.set_spec"
    SOLVER_SOLVE = "solver.solve"
    MODEL_READ_SNAPSHOT = "model.read_snapshot"


class ResultStatus(StrEnum):
    """工具成功时对象的变化：新建、没有变化、被修改。"""

    CREATED = "created"
    UNCHANGED = "unchanged"
    UPDATED = "updated"


class ReactorType(StrEnum):
    """反应器类型。全项目只在这里定义一次；HYSYS 的 Backend 目前只支持前三种。"""

    CONVERSION = "conversion"
    EQUILIBRIUM = "equilibrium"
    GIBBS = "gibbs"
    PFR = "pfr"
    CSTR = "cstr"


class PropertyPackage(StrEnum):
    """物性包。HYSYS 里的内部名由 Backend 映射。"""

    PENG_ROBINSON = "peng_robinson"


class PressureBasis(StrEnum):
    """压力的基准：绝压、表压，或者原文没有说明。"""

    ABSOLUTE = "absolute"
    GAUGE = "gauge"
    UNSTATED = "unstated"


class ReactionKind(StrEnum):
    """反应类型。"""

    CONVERSION = "conversion"
    EQUILIBRIUM = "equilibrium"


class ReactionPhase(StrEnum):
    """反应发生的相。合并相用于进料是固液浆料的转化反应。"""

    VAPOUR = "vapour"
    COMBINED = "combined"


class KeqSource(StrEnum):
    """平衡常数的来源。"""

    GIBBS_ENERGY = "gibbs_energy"
    FIXED_K = "fixed_k"


class HeatMode(StrEnum):
    """反应器的热模式：规定出口温度、绝热、规定热负荷。"""

    SPECIFIED_OUTLET_TEMPERATURE = "specified_outlet_temperature"
    ADIABATIC = "adiabatic"
    SPECIFIED_DUTY = "specified_duty"


class SpecVariable(StrEnum):
    """flowsheet.set_spec 可以修改的工况变量，对象一律是反应器。"""

    OUTLET_TEMPERATURE_C = "outlet_temperature_c"
    DUTY_KW = "duty_kw"


class StreamKind(StrEnum):
    """物流的种类。"""

    MATERIAL = "material"
    ENERGY = "energy"


class ConnectMode(StrEnum):
    """连接 HYSYS 的方式：新开实例，或者接管已经在运行的实例（只用于调试）。"""

    LAUNCH = "launch"
    ATTACH = "attach"


class CaseMode(StrEnum):
    """case.ensure 的模式：新建空白 Case，或者打开已有文件。"""

    NEW = "new"
    OPEN = "open"


class ObjectState(StrEnum):
    """流程图对象的求解状态。"""

    OK = "ok"
    NOT_SOLVED = "not_solved"
    WARNING = "warning"
    UNDER_SPECIFIED = "under_specified"
    ERROR = "error"


class MetricKind(StrEnum):
    """待求指标的种类。"""

    CONVERSION = "conversion"
    YIELD = "yield"
    RATIO = "ratio"


class MetricUnit(StrEnum):
    """指标值的单位：百分数，或者无量纲的比值。"""

    PERCENT = "percent"
    RATIO = "ratio"


class ComponentPhase(StrEnum):
    """组分在常温常压下的相态。"""

    GAS = "gas"
    LIQUID = "liquid"
    SOLID = "solid"


class StepPhase(StrEnum):
    """建模计划里一步所属的阶段：Basis、流程图，或者某个工况。"""

    BASIS = "basis"
    FLOWSHEET = "flowsheet"
    CASE = "case"


class CheckId(StrEnum):
    """结果检查的编号。V1 至 V8 见计划 §12.3；带后缀的是某种反应器专有的检查。"""

    SOLVED = "V1"
    STRUCTURE = "V2"
    FEEDS = "V3"
    SPECIFICATIONS = "V4"
    OUTPUTS = "V5"
    PHYSICAL = "V6"
    CONSERVATION = "V7"
    REQUESTED = "V8"
    CONVERSION_SPECIFIED = "V4-conversion"
    FIXED_K_SATISFIED = "V4-fixed-k"


class CheckSeverity(StrEnum):
    """检查的级别：致命的失败使任务失败，警告只使任务带警告完成。"""

    FATAL = "fatal"
    WARNING = "warning"


class TaskStatus(StrEnum):
    """任务的终态。"""

    COMPLETE = "complete"
    COMPLETE_WITH_WARNINGS = "complete_with_warnings"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"
    NEEDS_INPUT = "needs_input"


class WorkflowState(StrEnum):
    """任务经过的状态（计划 §7.3）。终态是 TaskStatus，不在这里。"""

    INIT = "INIT"
    SELECT = "SELECT"
    SPECIFY = "SPECIFY"
    VALIDATE = "VALIDATE"
    PLAN = "PLAN"
    PREFLIGHT = "PREFLIGHT"
    BUILD_BASIS = "BUILD_BASIS"
    BUILD_FLOWSHEET = "BUILD_FLOWSHEET"
    SOLVE = "SOLVE"
    VERIFY = "VERIFY"
    REPORT = "REPORT"


class RecoveryAction(StrEnum):
    """出错时执行器可以采取的动作：重试当前这一步、干净重建、中止。"""

    RETRY = "retry"
    REBUILD = "rebuild"
    ABORT = "abort"


class EventType(StrEnum):
    """Trace 事件的类型（计划 §14.1）。"""

    STATE_TRANSITION = "state_transition"
    TOOL_CALL = "tool_call"
    VALIDATION = "validation"
    CHECKPOINT = "checkpoint"
    RECOVERY = "recovery"
    ERROR = "error"
    LLM_CALL = "llm_call"


class CallPoint(StrEnum):
    """调用 LLM 的地方，名字用在 llm/ 日志的文件名和 Trace 事件里。之后往这里加写解读。"""

    SELECT = "select"
    SPECIFY = "specify"


class Checkpoint(StrEnum):
    """检查点事件的名字：输入、选型、TaskSpec 保存，规格冻结，计划保存，工况的 Case 和结果保存。"""

    INPUT_SAVED = "input_saved"
    SELECTION_SAVED = "selection_saved"
    TASK_SPEC_SAVED = "task_spec_saved"
    SPEC_FROZEN = "spec_frozen"
    PLAN_SAVED = "plan_saved"
    CASE_SAVED = "case_saved"
    RESULT_SAVED = "result_saved"
