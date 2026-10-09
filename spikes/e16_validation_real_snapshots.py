"""E16（1B 收尾，D19）：验证层在真实 HYSYS 快照上的表现。

1B 的检查（V1 至 V8）、指标和结局判定只在手算的快照上试过。独立审查指出风险：空相出料读回的是
0.0 还是 None，V6 新增的物流内部一致性和分子量容差会不会对真实数据误报，V4 读出口温度的方式。
要回答：
  Q1 Recipe 从三份黄金规格编译出的计划，能不能原样在 HYSYS 里执行？
  Q2 每个工况的真实快照喂给 V1 至 V8 和专有检查，全部通过吗？哪一项误报？
  Q3 没有流量的出料（空相），读回的流量、组分流量、分率是 0.0 还是 None？温度和压力有没有值？
  Q4 V6 的物流内部一致性在真实数据上偏差多大（组分之和与总流量，质量流量与摩尔流量乘分子量，
     摩尔分率与流量占比）？离容差有多远？
  Q5 指标、干基组成、热负荷和结局判定在真实结果上是什么？结果与计划 §17 的参照值一致吗？

做法：用生产代码的 Backend 和 ToolExecutor，按 Recipe 的计划执行（基础和流程图一次，每个工况
改规定值、求解、读快照），把真实快照交给验证层；只记录，不断言。每份规格一个新的 Case，结束时
另存、关闭。

用法：python spikes/e16_validation_real_snapshots.py [--tag 名字]
输出：spikes/out/e16_validation_real_snapshots_<tag>.txt；Case 另存为 e16_<规格名>_<tag>.hsc。
"""

import argparse
import math
import traceback
from datetime import UTC, datetime
from pathlib import Path

from _common import OUT_DIR, Log, use_utf8

from reactor_agent.backends.hysys_com.backend import HysysComBackend
from reactor_agent.recipes import recipe_for
from reactor_agent.spec.components import load_component_table, molecular_weights
from reactor_agent.spec.enums import CaseMode, ToolName
from reactor_agent.spec.model_spec import load_model_spec, spec_hash
from reactor_agent.spec.results import CaseRecord, CheckContext, Provenance
from reactor_agent.spec.snapshot import StreamSnapshot
from reactor_agent.spec.tool_args import (
    CloseCaseArgs,
    ConnectArgs,
    EnsureCaseArgs,
    ReadSnapshotArgs,
    SaveCaseArgs,
    SolveArgs,
)
from reactor_agent.tools.definitions import register_tools
from reactor_agent.tools.registry import ToolExecutor
from reactor_agent.validation.checks import run_common_checks
from reactor_agent.validation.normalized import assemble_result, decide_outcome

use_utf8()

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "evals" / "golden_specs"
TABLE_FILE = REPO / "config" / "components.yaml"
SPEC_NAMES = ("toluene_conversion", "smr_equilibrium", "slurry_gibbs")
SOLVE_TIMEOUT_S = 120.0
EMPTY_FLOW_KMOL_H = 1e-9
# 计划 §17 的参照值（独立算出的，不是 HYSYS 的输出）：规格 → 工况 → (出料, 湿基摩尔分率, 容差)
REFERENCES = {
    "toluene_conversion": {
        "base": (
            "Vap",
            {"Toluene": 0.5, "Benzene": 0.25, "p-Xylene": 0.06, "m-Xylene": 0.13, "o-Xylene": 0.06},
            0.001,
        )
    },
    "smr_equilibrium": {
        "T710": (
            "Vap",
            {"Methane": 0.094, "H2O": 0.381, "Hydrogen": 0.411, "CO": 0.047, "CO2": 0.067},
            0.02,
        ),
        "T600": (
            "Vap",
            {"Methane": 0.162, "H2O": 0.499, "Hydrogen": 0.269, "CO": 0.012, "CO2": 0.058},
            0.02,
        ),
    },
    "slurry_gibbs": {"base": ("Vap-2", {"CO": 0.500, "Hydrogen": 0.482}, 0.02)},
}
CO_YIELD_RANGE_PERCENT = (38.0, 42.0)


def object_name(args: object) -> str:
    return getattr(args, "name", None) or getattr(args, "object_name", "")


def call(executor: ToolExecutor, log: Log, tool: str, args: object, label: str = ""):
    """调一个工具；失败时记下错误码、消息和细节，返回 None。"""
    result = executor.call(tool, args)
    if not result.ok:
        error = result.error
        log.say(
            f"    {label or tool} 失败：{error.code.value} {error.message} {dict(error.details)}"
        )
        return None
    return result


def observe_stream(log: Log, stream: StreamSnapshot, weights: dict[str, float]) -> None:
    """一股物流的真实读回：状态、总量，以及 V6 的几个一致性量。空相出料另记它的读回形式。"""
    flows = [c.molar_flow_kmol_h for c in stream.components]
    masses = [c.mass_flow_kg_h for c in stream.components]
    fractions = [c.mole_fraction for c in stream.components]
    total_n, total_m = stream.molar_flow_kmol_h, stream.mass_flow_kg_h
    log.say(
        f"    [{stream.name}] T={stream.temperature_c!r} °C  P={stream.pressure_bar!r} bar  "
        f"N={total_n!r} kmol/h  M={total_m!r} kg/h  汽相分率={stream.vapour_fraction!r}  "
        f"重液相分率={stream.heavy_liquid_fraction!r}"
    )
    notes = []
    if total_n is not None and None not in flows:
        notes.append(f"Σ组分摩尔流量−总流量={math.fsum(flows) - total_n:+.2e}")
    if total_m is not None and None not in masses:
        notes.append(f"Σ组分质量流量−总质量流量={math.fsum(masses) - total_m:+.2e}")
    ratios = [
        abs(mass / (flow * weights[c.name]) - 1.0)
        for c, flow, mass in zip(stream.components, flows, masses, strict=True)
        if flow and mass and flow > EMPTY_FLOW_KMOL_H
    ]
    if ratios:
        notes.append(f"质量÷(摩尔×分子量)−1 的最大偏差={max(ratios):.2e}")
    if total_n and total_n > EMPTY_FLOW_KMOL_H:
        shares = [
            abs(x - flow / total_n)
            for x, flow in zip(fractions, flows, strict=True)
            if x is not None and flow is not None
        ]
        if shares:
            notes.append(f"|分率−流量占比| 最大偏差={max(shares):.2e}")
    if None not in fractions:
        notes.append(f"Σ分率−1={math.fsum(fractions) - 1.0:+.2e}")
    log.say("        " + "；".join(notes))
    if total_n is None or total_n <= EMPTY_FLOW_KMOL_H:
        log.say(
            f"        空相出料：总流量={total_n!r}；"
            f"组分流量的不同取值={sorted(set(map(repr, flows)))}；"
            f"分率的不同取值={sorted(set(map(repr, fractions)))}"
        )


def log_result(log: Log, result) -> None:
    log.say("    -- 检查 --")
    for check in result.checks:
        mark = "通过" if check.passed else "未通过"
        log.say(f"    {check.check_id.value:14s} {mark}  实测：{check.actual}")
    for metric in result.metrics:
        log.say(f"    指标 {metric.name} = {metric.value!r} {metric.unit.value}")
    log.say(f"    热负荷合计 = {result.duty_kw!r} kW")
    for outlet in result.outlets:
        dry = {
            c.name: round(c.dry_mole_fraction, 4) for c in outlet.components if c.dry_mole_fraction
        }
        if dry:
            log.say(f"    干基组成 [{outlet.name}] = {dry}")


def compare_reference(log: Log, name: str, case_name: str, result, problems: list[str]) -> None:
    reference = REFERENCES.get(name, {}).get(case_name)
    if reference is None:
        return
    stream_name, fractions, tolerance = reference
    outlet = next(s for s in result.outlets if s.name == stream_name)
    worst = max(
        abs((c.mole_fraction or 0.0) - fractions[c.name])
        for c in outlet.components
        if c.name in fractions
    )
    log.say(
        f"    与计划 §17 参照值的最大摩尔分率偏差 {worst:.4f}（容差 {tolerance}）[{stream_name}]"
    )
    if worst > tolerance:
        problems.append(f"{name}/{case_name}：偏离参照值 {worst:.4f} > {tolerance}")
    if name == "slurry_gibbs":
        co_yield = next(m.value for m in result.metrics if m.name.startswith("CO 收率"))
        low, high = CO_YIELD_RANGE_PERCENT
        log.say(f"    CO 收率 {co_yield:.2f}%（参照范围 {low} 至 {high}）")
        if not low <= co_yield <= high:
            problems.append(f"{name}：CO 收率 {co_yield:.2f}% 不在 {low} 至 {high}")


def run_case(ctx: dict, case, problems: list[str]):
    """执行一个工况的规定值、求解、读快照，把真实快照交给验证层。返回 NormalizedResult 或 None。"""
    executor, log, spec, table, plan, recipe = (
        ctx[key] for key in ("executor", "log", "spec", "table", "plan", "recipe")
    )
    log.say(f"  -- 工况 {case.name}：{case.model_dump(exclude_none=True)} --")
    for step in plan.case_steps(case.name):
        if call(executor, log, step.tool, step.args, f"步骤 {step.number}") is None:
            problems.append(f"{ctx['name']}/{case.name}：改规定值失败")
            return None
    solved = call(executor, log, ToolName.SOLVER_SOLVE, SolveArgs(timeout_s=SOLVE_TIMEOUT_S))
    if solved is None:
        problems.append(f"{ctx['name']}/{case.name}：求解失败")
        return None
    log.say(f"    求解 {solved.data.duration_s:.2f} 秒，对象 {len(solved.data.status.objects)} 个")
    read = call(executor, log, ToolName.MODEL_READ_SNAPSHOT, ReadSnapshotArgs())
    if read is None:
        problems.append(f"{ctx['name']}/{case.name}：读快照失败")
        return None
    snapshot = read.data
    weights = dict(molecular_weights(table))
    for stream in snapshot.streams:
        observe_stream(log, stream, weights)
    context = CheckContext(spec=spec, case=case, plan=plan, components=table, snapshot=snapshot)
    checks = (*run_common_checks(context), *recipe.checks(context))
    provenance = Provenance(
        simulator_version=ctx["version"],
        case_path=snapshot.case_path,
        read_at=datetime.now(UTC),
        spec_hash=spec_hash(spec),
    )
    result = assemble_result(context, checks, provenance)
    log_result(log, result)
    compare_reference(log, ctx["name"], case.name, result, problems)
    for check in result.checks:
        if not check.passed:
            problems.append(
                f"{ctx['name']}/{case.name}：{check.check_id.value} 未通过：{check.actual}"
            )
    return result


def run_model(executor: ToolExecutor, log: Log, name: str, ctx: dict, problems: list[str]) -> None:
    spec = load_model_spec(GOLDEN / f"{name}.yaml")
    recipe = recipe_for(spec.reactor_type)
    table = ctx["table"]
    log.say(f"== 规格 {name}（{spec.reactor_type.value}）==")
    issues = recipe.rules(spec, table)
    log.say(f"  规则：{'没有问题' if not issues else [i.message for i in issues]}")
    if issues:
        problems.append(f"{name}：规则有问题")
        return
    plan = recipe.compile(spec, table)
    log.say(f"  计划：{len(plan.steps)} 步")
    case_path = OUT_DIR / f"e16_{name}_{ctx['tag']}.hsc"
    for leftover in OUT_DIR.glob(f"e16_{name}_{ctx['tag']}.*"):
        if leftover.suffix != ".txt":
            leftover.unlink()
    created = call(
        executor, log, ToolName.CASE_ENSURE, EnsureCaseArgs(path=case_path, mode=CaseMode.NEW)
    )
    if created is None:
        problems.append(f"{name}：新建 Case 失败")
        return
    ctx = {**ctx, "name": name, "spec": spec, "plan": plan, "recipe": recipe}
    for step in plan.steps:
        if step.case_name is not None:
            continue
        result = call(executor, log, step.tool, step.args, f"步骤 {step.number}")
        if result is None:
            problems.append(f"{name}：计划第 {step.number} 步（{step.tool.value}）失败")
            call(executor, log, ToolName.CASE_CLOSE, CloseCaseArgs(save=False))
            return
        log.say(
            f"    步骤 {step.number:2d} {step.tool.value} {object_name(step.args)} "
            f"→ {result.status.value}"
        )
    results = [run_case(ctx, case, problems) for case in spec.cases]
    saved = call(executor, log, ToolName.CASE_SAVE, SaveCaseArgs())
    if saved is not None:
        log.say(f"  另存 {saved.data.path.name}，{saved.data.size_bytes} 字节")
    records = [
        CaseRecord(case_name=case.name, result=result, case_file_saved=saved is not None)
        for case, result in zip(spec.cases, results, strict=True)
    ]
    outcome = decide_outcome([case.name for case in spec.cases], records)
    log.say(f"  结局判定：{outcome.value}")
    if outcome.value != "complete":
        problems.append(f"{name}：结局 {outcome.value}")
    call(executor, log, ToolName.CASE_CLOSE, CloseCaseArgs(save=False))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run1")
    args = parser.parse_args()
    log = Log(f"e16_validation_real_snapshots_{args.tag}")
    problems: list[str] = []
    backend = HysysComBackend()
    try:
        executor = ToolExecutor(register_tools(backend))
        connected = call(executor, log, ToolName.SESSION_CONNECT, ConnectArgs(visible=False))
        if connected is None:
            log.say("== E16 没能连上 HYSYS ==")
            return 2
        log.say(f"HYSYS：{connected.data.version}，进程号 {connected.data.process_id}")
        ctx = {
            "table": load_component_table(TABLE_FILE),
            "version": connected.data.version,
            "tag": args.tag,
            "log": log,
            "executor": executor,
        }
        for name in SPEC_NAMES:
            try:
                run_model(executor, log, name, ctx, problems)
            except Exception:  # 探针：出了什么错本身就是要记录的结果
                log.say(traceback.format_exc())
                problems.append(f"{name}：脚本异常")
        log.say(f"弹窗：{backend.dialog_messages()}")
    finally:
        backend.shutdown()
    if problems:
        log.say(f"== E16 发现 {len(problems)} 个问题 ==")
        for problem in problems:
            log.say(f"  - {problem}")
        return 1
    log.say("== E16 通过：三份规格的真实快照全部通过 V1 至 V8，结局都是 complete ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
