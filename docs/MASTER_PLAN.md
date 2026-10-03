# MASTER_PLAN：AI 驱动的 HYSYS 反应器智能建模系统

| 项 | 内容 |
|---|---|
| 版本 | v0.2.1（2026-10-02）。v0.2 是对照需求文档严格审核后的修订版，审核记录见 §27。v0.2.1 是编写分阶段提示词时做的一致性修补，不改变架构，修补清单见 §27.5。Phase 0 实测后再修订 |
| 需求来源 | 《AI 驱动的化工反应器智能建模考核》。最高优先级，本文与其冲突时以需求文档为准 |
| 证据状态 | 本轮**没有在 VM 上执行任何 HYSYS 操作**。所有 HYSYS 接口结论按 §16.2 的四级状态标注，标为"未知 / 待实测"的内容一律是假设 |
| 用途 | 后续开发和 AI 编程助手会话的唯一架构基线。实现与本文不一致时，先改本文再改代码 |

## 目录

0. 结论先行
1. 需求理解
2. P0 / P1 / P2
3. MVP
4. 业务流程
5. 数据流
6. Agent 架构选择
7. Harness 架构
8. Skills 架构
9. Tool / MCP 架构
10. State 架构
11. Context 架构
12. Validation 架构
13. Recovery 架构
14. Observability 架构
15. Evaluation 架构
16. HYSYS 集成方案
17. 三个 Scenario 详细拆解
18. 风险矩阵
19. 工程任务拆解
20. 实施顺序
21. 各阶段验收标准
22. 最终目录结构与文档管理
23. 复用、扩展与可维护性
24. 反向审查（20 问）
25. 待确认决策与假设登记
26. 现在应该执行的第一件事
27. 审核记录（v0.1 → v0.2）

---

## 0. 结论先行

1. **架构选型**：选"规格驱动的 Agent Harness"（候选 C 的收敛形态，记为 E）。确定性状态机 Harness + 单一 LLM 决策者 + 4 个按需加载的 Skills + 13 个幂等的确定性 Tools + HYSYS Backend。不用 Multi-Agent，不用 LangGraph，MCP 降为 P2 的薄封装。
2. **最关键的一个设计动作**：把 LLM 的动作空间从"HYSYS API"提升为"模型规格（Spec）"。LLM 只回答"建什么"并给出理由；"怎么建、建成没有、算对没有"全部由代码回答。LLM 在主路径上**不调用任何工具**，因此不存在绕过 Harness 的通道。
3. **三场景映射**：场景 1 → Equilibrium Reactor（两个出口温度工况）；场景 2 → Conversion Reactor；场景 3 → Gibbs Reactor。运行时代码里不出现任何"场景"概念，这个映射只存在于评测集中。
4. **最高风险**：HYSYS V15 能否通过 COM 编程创建反应、反应集和反应器。本轮在公开版的官方 Customization Guide 中只查到"连接、读写已有对象"的内容，没有查到创建反应的示例。其次是场景 3 的固体碳在 Gibbs 反应器中的处理。
5. **第一件事**：在 VM 上做 HYSYS 探索与可行性验证。用场景 2 的转化反应器打通"连接 → 建 Basis → 建反应 → 建物流和反应器 → 求解 → 读结果"，时间盒约 6 小时，带降级闸门；随后对备选集成路线做一次最小对照并留证，因为需求文档把探索实现路径列为最重要的考核要素。详见 §26。
6. **范围纪律**：3 天按 30 个工作小时计，没有可以浪费的余量。必达线是"三个场景端到端，加上第一版录屏和报告"，按时间盒上限在第 25.5 小时达成。之后先用留出场景检验泛化，再做泛化功能，最后才是 Harness 加固。Harness 不超过约 600 行，全系统约 3000 行。
7. **需要你确认的点**（不阻塞 Phase 0，见 §25）：LLM 供应商与 VM 的联网情况；场景 3 是否引入氧气；"80000 Nm³/h"的含义；二甲苯异构体分配；压力是表压还是绝压；机动时间先做泛化还是先做加固。

---

## 1. 需求理解

### 1.1 一句话目标

用户用自然语言描述一个反应过程，系统自主判断反应器类型并解释理由，在 Aspen HYSYS V15 中实际创建并配置该反应器（含进出料物流和反应），求解后返回可信的计算结果。

### 1.2 需求清单

| 编号 | 需求（括号内是需求文档的章节） | 解读 |
|---|---|---|
| REQ-1 | 接收自然语言描述（§2.1） | 输入是一段中文文本，含错别字和口语化表达 |
| REQ-2 | 判断反应器类型并解释理由（§2.2） | **评分关键**。输出必须有类型、依据、备选及不选的原因 |
| REQ-3 | 在 HYSYS 中实际创建反应器，包括进出料物流和反应配置（§2.3） | 必须是 HYSYS 里真实存在的对象，不能是外部计算后的"假结果" |
| REQ-4 | 读取并返回计算结果，如产物组成、温度、收敛状态（§2.4） | 结果必须读自 HYSYS，并附收敛状态 |
| REQ-5 | 至少处理 3 个场景，考核时可能给出额外场景（§3） | 核心逻辑不能为 3 个场景硬编码 |
| REQ-6 | 参考选择逻辑和补充信息（§8、§9） | 需求 §8 是选择规则的来源，包含 CSTR / PFR |
| REQ-7 | 每个场景对应不同的反应器类型（§3 末） | 三个场景恰好覆盖 Conversion / Equilibrium / Gibbs |
| REQ-8 | 交付物：仓库和 README、录屏、AI 开发记录、1–2 页报告、Live Demo（§5） | Demo 必须稳定可复现 |
| REQ-9 | 评分：完成度 50%，探索与设计 25%，AI 协作 25%（§6） | 见 1.3 |
| REQ-10 | 3 天时限，必须使用 AI 编程助手，会检查 Git 提交历史（§7） | 从第一个探针脚本开始就提交 |
| REQ-11 | 技术栈自定，探索实现路径是最重要的考核要素（§2、§4） | 探索不只是为了降低风险。要有意识地比较不同的实现路线，留下试过什么、为什么放弃、为什么选定的证据 |

### 1.3 评分导向对设计的约束

| 评分维度 | 权重 | 对本计划的约束 |
|---|---|---|
| 系统完成度 | 50% | HYSYS 链路优先于一切。三个场景的冻结规格能确定性跑通，优先级高于任何架构加固 |
| 探索与系统设计 | 25% | 评分点包括"是否展示了独立探索不同方案的过程"。保留探针脚本、接口事实台账和探索日志（`spikes/`、`docs/HYSYS_INTEGRATION.md`），并对备选集成路线做最小对照实验（§16.4 的 E13）。架构决策可解释 |
| AI 协作质量 | 25% | AI 编程助手直接在 VM 上运行，自己执行探针、读取输出、迭代。`CLAUDE.md` 约束助手行为，`docs/progress.md` 做会话间记忆，会话记录随手导出。速度本身计分，所以禁止过度设计，并且先交付后加固 |

### 1.4 需求中的陷阱与歧义

| 编号 | 位置 | 问题 | 处理 |
|---|---|---|---|
| T1 | 场景 3 | 问"CO 的收率"。收率是**待求量**，不是已知量。需求 §8 说"给出收率时用 Conversion"指的是已知量 | Skill 中明确区分"已知量"和"待求量"，评测集加对抗样本 |
| T2 | 场景 3 | 给了"主要反应"方程，容易被误判为 Equilibrium | 黑箱、极高温、要求考虑副反应 → Gibbs |
| T3 | 场景 2 | 需求 §9 强调"可逆、受平衡影响"，容易被误判为 Equilibrium | 用户明确指定转化率反应器并给出转化率 50%，且声明不讨论动力学 → Conversion。50% 低于平衡极限（文献值约 55%–60%），热力学上可行 |
| T4 | 场景 1 | 两个出口温度工况 | 同一模型，两组工况规定，输出对比表 |
| T5 | 场景 1 | 进料流量自定，要求"符合工厂一年正常处理量" | 给出带工程依据的默认值并标注为假设。流量不影响平衡组成 |
| T6 | 场景 3 | "80000 Nm³/h"用于水煤浆；没有氧气进料；煤如何表示 | 见 §17.3 的假设 A3-1 至 A3-4，全部显式声明 |
| T7 | 场景 2 | 邻、间、对二甲苯的分配比例没有给出 | 默认取反应温度下的平衡分布近似值，标注为假设，可覆盖 |
| T8 | 全部 | 压力没有注明表压还是绝压 | 默认绝压并声明。对场景 1，两种理解下的转化率相差约 1 个百分点 |
| T9 | 全文 | 有错别字（"Conversation 反应器"、"一样化碳"） | 评测集使用原文，要求 LLM 对此鲁棒 |
| T10 | 需求 §8 | 规则含 CSTR / PFR，额外场景可能考动力学反应器 | 选择能力覆盖 5 类（P0）；CSTR / PFR 的 HYSYS 建模列为 P1 |
| T11 | 场景 1 | 有两个反应，容易因"多反应体系"被判成 Gibbs | 反应已由用户全部列出，且都是可逆反应 → Equilibrium。Gibbs 用于副反应没有也无法逐一列出的体系。评测集加对抗样本 |
| T12 | 场景 1 | "重整炉"是管式反应器，容易被判成 PFR | 需求 §8.3：管式反应器没有动力学参数时，回到需求 §8.2 的规则 |
| T13 | 需求 §8.2 | Equilibrium 的使用条件是"提供 Ka 或 Gibbs 自由能"。场景 1 没有给 Ka，额外场景可能会给 | 场景 1 用 Gibbs 自由能来源。固定 Keq 和 Keq 随温度变化两种来源列为泛化项（§2） |
| T14 | 需求 §8.2 | Conversion 的触发条件包括"转化率、收率或选择性"。额外场景可能只给收率或选择性 | 由代码把转化率、选择性、收率换算成各反应的转化率，列为泛化项（§2） |
| T15 | 场景 2、需求 §9.2 | "甲苯歧化不是想转化多少就转化多少"，暗示应当检查设定的转化率是否超过平衡极限 | P0 在理由中定性说明；P1 在 HYSYS 中算出平衡转化率做对比（§17.2） |

### 1.5 非目标

不做：多单元流程（换热、分离、循环）、动态模拟、参数优化、经济性评价、对 HYSYS 帮助文档做 RAG、多用户并发、Web 产品化。这些都不在需求文档内。

---

## 2. P0 / P1 / P2

优先级按需求文档的评分和交付要求排，不按架构的完整程度排。

| 级别 | 条目 | 理由 |
|---|---|---|
| **P0** | 探索记录：主路线探针、备选路线的最小对照、接口事实台账 | REQ-11，最重要的考核要素 |
| **P0** | 自然语言 → 反应器类型判断（5 类：Conversion、Equilibrium、Gibbs、CSTR、PFR）+ 理由 + 备选 | REQ-2，评分关键 |
| **P0** | 自然语言 → 结构化规格（组分、反应、进料、规定、工况、待求量、假设） | REQ-1 |
| **P0** | Conversion / Equilibrium / Gibbs 三类反应器在 HYSYS 中的真实创建、配置、求解 | REQ-3、REQ-7 |
| **P0** | 读回结果：出口组成、温度、压力、流量、热负荷、收敛状态；场景 1 两工况对比和年处理量；场景 3 的 CO 收率 | REQ-4 |
| **P0** | 确定性边界：Schema 校验、单位换算、业务规则、步骤读回、结果验证 | 结果准确性 |
| **P0** | 最小 Harness：状态循环、状态落盘、Trace、回路上限、三种恢复（步骤重试、干净重建、带诊断中止）、规格重述 | Agent 行为可控，Demo 稳定 |
| **P0** | CLI、报告输出、保存 `.hsc`、冻结规格回放模式（`--spec`） | REQ-8，Demo 兜底 |
| **P0** | 三场景的 L3 黄金用例 + L1 核心评测集 | 可验证的闭环 |
| **P0** | 交付物：README、录屏、AI 开发记录、报告。三场景端到端一通过就先出第一版 | REQ-8 |
| **P0** | 留出场景端到端：Conversion、Equilibrium、Gibbs 各一个没有参与开发的体系，在 HYSYS 中跑通（§15.7） | REQ-5，考核时可能给出额外场景 |
| P1-泛化 | 固定 Keq 和 Keq 随温度变化两种来源；转化率、选择性、收率到各反应转化率的换算 | T13、T14，需求 §8.2 明确列出 |
| P1-泛化 | 追问式修改重跑：用户用自然语言改一个条件或假设，系统生成新规格并重跑 | Live Demo 要现场回答问题 |
| P1-泛化 | CSTR / PFR 建模（动力学反应） | T10，需求 §8.1 |
| P1-泛化 | 组分解析增强：别名表未命中时，按分子式和名称在候选中确定 | 额外场景最容易在组分名上失败 |
| P1-泛化 | Conversion 的平衡可行性校验 | T15 |
| P1-加固 | 自动重启会话、中间快照和续跑、`FakeBackend` 和故障注入测试 | 鲁棒性加固 |
| P1-加固 | LLM 参与的修复回路（`SpecPatch`）；关键特征的正则证据；数字回查 | 降低误判 |
| P1-加固 | Backend 进程隔离与硬超时 | 仅当 Phase 0 观察到 COM 挂起时才做 |
| P2 | MCP 薄封装、Web UI、场景 3 加氧变体、用 Gibbs 交叉验证场景 1、多 LLM 切换、OpenTelemetry 导出、其他仿真后端 | 不影响考核闭环 |

P1 分成两组，**泛化组先于加固组**：额外场景和现场问答直接计入完成度，续跑和故障注入不在需求文档的评分项里。这个顺序与最初设计要求的侧重点不同，列为待确认决策 D8。

落后于计划时的裁剪顺序：P2 → P1-加固 → P1-泛化 → 留出场景。**三个场景的端到端闭环和四项交付物永不裁剪。**

---

## 3. MVP

MVP 是场景 2 的端到端薄切片，因为它的预期结果有解析解，可以把"HYSYS 是否算对"和"系统是否建对"分开验证。

```
场景 2 原文 → SELECT → SPECIFY → VALIDATE → PLAN → HYSYS 构建 → 求解 → 验证 → 报告
```

MVP 的完成标准：

1. 输入场景 2 原文，输出反应器类型 Conversion 及理由。
2. HYSYS 中出现流体包、5 个组分、1 个转化反应、反应集、进料流、反应器、两股出口流，求解完成。
3. 读回的出口摩尔分率满足：甲苯 0.500、苯 0.250、二甲苯合计 0.250（容差 ±0.001），质量守恒误差不超过 0.01%。
4. 连续运行 3 次结果一致，不残留重复对象。
5. 一次完整运行产生 `state.json`、`trace.jsonl`、`report.md` 和 `.hsc`。

MVP 之后按"场景 1（加入平衡反应、能流、多工况）→ 场景 3（加入 Gibbs、固体组分、派生指标）"的顺序扩展。每一步只新增一个 Recipe 和对应的 Skill 参考文件，不改 Harness。

---

## 4. 业务流程

```
User text
   |
   v
[1 SELECT]    LLM: features + reactor type + rationale          (Skill: reactor-selection)
   |
   v
[2 SPECIFY]   LLM: TaskSpec (components, reactions, feeds, specs, cases, metrics, assumptions)
   |                                                            (Skill: reactor-modeling/<type>)
   v
[3 VALIDATE]  code: schema -> units -> names -> rules -> DOF    => ModelSpec (frozen)
   |
   v
[4 PLAN]      code: Recipe.compile(ModelSpec)                   => BuildPlan (ordered, idempotent steps)
   |
   v
[5 PREFLIGHT] tools: connect HYSYS, new case, hold solver
   |
   v
[6 BUILD_BASIS]      tools: components, fluid package, reactions, reaction set
   |
   v
[7 BUILD_FLOWSHEET]  tools: streams, reactor, connections, specs
   |
   v
[8 SOLVE] <----+     tools: apply case specs, release solver, wait
   |           |
   v           |  next operating case
[9 VERIFY] ----+     code: snapshot -> result checks -> NormalizedResult
   |
   v
[10 REPORT]   code renders tables; LLM writes interpretation    (Skill: result-reporting)
   |
   v
User: reactor type + rationale + assumptions + results + validation + .hsc path
```

用户最终得到的内容固定为六块：反应器类型与理由（含备选及不选原因）；解析出的参数和显式假设；HYSYS 模型摘要；各工况结果表和派生指标；验证结论（收敛、守恒、规定满足情况）；`.hsc` 路径和 Trace 摘要。LLM 写的解读文字是这六块之外单独的一节，并注明来源。

---

## 5. 数据流

| 数据对象 | 产生者 | 消费者 | 存储 | 是否进入 LLM |
|---|---|---|---|---|
| `user_text` | 用户 | SELECT、SPECIFY、REPORT | `state.input` | 是，原文 |
| `SelectionResult` | LLM | SPECIFY、选型规则校验、REPORT | `state.selection` | 是，精简后 |
| `TaskSpec` | LLM | VALIDATE | `state.task_spec`，保留原样供审计 | 仅在重述时回传 |
| `ModelSpec` | 代码（规范化 + 校验） | PLAN、VERIFY、REPORT | `state.model_spec`，带 `spec_hash`，冻结 | 精简后进入 REPORT |
| `BuildPlan` | 代码（Recipe） | 执行器 | `state.plan` | 否 |
| Tool 结果信封 | Tool 层 | Harness | `trace.jsonl` 全量，`state` 只存摘要 | 否，只有失败步骤的错误摘要进入重述 |
| `ModelSnapshot` | `model.read_snapshot` | 读回校验、结果验证 | `runs/<id>/snapshots/` | 否 |
| `ValidationReport` | 验证层 | 完成判定、REPORT | `state.validation` | 仅摘要 |
| `NormalizedResult` | 验证层 | 报告渲染、LLM 解读 | `state.results`、`result.json` | 是 |
| 报告 | 代码渲染 + LLM 解读 | 用户 | `report.md` | 不适用 |

两层规格是确定性边界的实体化：`TaskSpec` 是"LLM 说了什么"（保留用户原始单位和数值，逐项标注来源），`ModelSpec` 是"代码接受了什么"（规范单位、HYSYS 规范组分名、已应用的默认值和假设）。LLM 不做任何单位换算和算术。

`TaskSpec` 示意（场景 1 节选）：

```yaml
reactor: {type: equilibrium, thermal_mode: outlet_temperature}
components: [CH4, H2O, CO, CO2, H2]
reactions:
  - {id: R1, type: equilibrium, stoich: {CH4: -1, H2O: -1, CO: 1, H2: 3}, keq_source: gibbs}
  - {id: R2, type: equilibrium, stoich: {CO: -1, H2O: -1, CO2: 1, H2: 1}, keq_source: gibbs}
feeds:
  - name: Feed
    temperature: {value: 520, unit: C, source: user}
    pressure:    {value: 13.5, unit: bar, source: user}
    flow:        {value: 3700, unit: kmol/h, source: assumed, rationale: "..."}
    composition: {basis: mole, values: {CH4: 1, H2O: 2.7}}   # 代码负责归一化
operating_cases:
  - {id: T710, outlet_temperature: {value: 710, unit: C}}
  - {id: T600, outlet_temperature: {value: 600, unit: C}}
metrics: [{kind: conversion, component: CH4}, {kind: ratio, num: H2, den: CO}, {kind: dry_basis}]
assumptions: [{id: A1, item: feed_flow, reason: "..."}, {id: A2, item: pressure_basis, value: absolute}]
```

---

## 6. Agent 架构选择

### 6.1 从业务形状出发

四个事实决定了架构，而不是技术偏好：

1. **流程是固定管线**。变化点只有三处：语言理解、规格表达、异常解释。
2. **给定一份合法规格，HYSYS 的构建序列是确定的**。先 Basis 后 Flowsheet，先物流后单元，不需要 LLM 逐步决定"下一步调哪个 API"。
3. **HYSYS 是单会话、有状态、有副作用的外部系统**。一次任务只操作一个 Case，没有可以并行的子任务。
4. **任务上下文很小**（几千 token），没有上下文隔离的需求。

### 6.2 普通 Agent 会出什么问题，Harness 怎么解决

"用户 → LLM → Tool → LLM → Tool → …"的自由循环在本项目中的失败模式，以及本架构的结构性对策：

| 问题 | 根因 | 对策（由结构保证，不靠提示词） |
|---|---|---|
| 无限调用工具 | 循环何时结束由 LLM 决定 | LLM 不调用工具。步骤数等于计划长度，另有预算上限（§7.4） |
| 重复创建 Reactor | `create` 语义，且不查询现状 | 工具全部是 `ensure` 语义，先在 HYSYS 中查存在性；对象名由代码生成 |
| 参数错误 | LLM 直接填写 API 参数 | `TaskSpec` → 校验 → `ModelSpec`；单位换算由代码做；每步读回比对 |
| 忘记之前的执行结果 | 依赖聊天历史 | 状态存在 `state.json`；每次 LLM 调用都是无状态的 |
| 上下文污染 | 工具输出不断堆进对话 | LLM 上下文是"状态的视图"，原始输出只进 Trace |
| HYSYS 失败后不知道如何恢复 | 错误只是一段文本 | 错误码 → 恢复策略表（§13）；默认手段是干净重建 |
| 自认为完成但 HYSYS 没算成功 | 完成由 LLM 宣称 | 完成判定是验证层计算出来的谓词（§7.5） |
| 工具返回错误后继续执行 | 错误没有控制流语义 | 结果信封 `ok=false` 强制进入 RECOVER |
| 调用不存在的工具 | 工具名由 LLM 生成 | 计划由 Recipe 编译，工具名来自注册表 |
| 修改已经完成的对象 | 没有阶段约束 | 规格冻结；计划由 Recipe 编译，求解阶段只含工况变量的设值；给 LLM 开放工具时再启用状态到工具组的白名单 |
| 中途退出后无法恢复 | 状态在内存和对话里 | 每次状态迁移原子落盘；用冻结规格重跑（P0）；从中间快照续跑（P1） |

### 6.3 候选方案对比

| 方案 | 形态 | 新增复杂度 | 鲁棒性 | 可维护性 | 扩展性 | 结论 |
|---|---|---|---|---|---|---|
| A 单 Agent + Tools | LLM 在循环中逐个调用十余个 HYSYS 工具 | 最低 | 差。6.2 的 11 类问题全部存在，每次运行路径不同，Demo 风险高 | 提示词越堆越大 | 加工具容易，行为不可预测 | 不选 |
| B Agent + Workflow | 固定管线，其中 2–3 步由 LLM 完成 | 低 | 主路径好，但没有状态、恢复和验证 | 好 | 新反应器要改管线 | 作为骨架采纳，单独不够 |
| C Harness + Skills + Tools | LLM 在状态约束下调用工具 | 中 | 好，但 LLM 仍在选择 API 级调用，需要大量权限和纠偏逻辑 | 中 | 好 | 方向正确，但把不需要智能的构建序列交给了 LLM |
| D 多 Agent + Harness | 选型、建模、验证各一个 Agent | 高 | 更差。交接丢信息，延迟和成本成倍，HYSYS 单会话无法并行 | 调试困难 | 表面清晰，实际耦合在交接协议上 | 不选 |
| **E 规格驱动的 Harness** | 确定性状态机；LLM 只在 3 个调用点产出结构化规格或文字；Recipe 把规格编译为工具计划 | 中。比 C 少一层工具调用循环，多一个规格编译器 | 最好。LLM 调用次数固定，构建完全确定 | 好 | 新反应器 = 新 Recipe + Skill 参考文件 + 测试 | **选** |

### 6.4 选择 E 的论证

- **为什么选**：它与 6.1 的四个事实一一对应。智能只用在需要智能的地方（理解、判断、解释），其余全部确定化。
- **为什么不选 A、C**：两者都让 LLM 决定 API 级的调用顺序，而这个顺序没有任何不确定性。把确定的事情交给概率模型，只增加失败面。
- **为什么不选 D**：Agent 的拆分应当由"需要独立上下文、独立工具权限或并行"驱动。本项目三者都不存在。
- **为什么不止于 B**：B 没有回答"失败了怎么办、怎么知道算对了、中断了怎么续"。补上这些之后就是 E。
- **增加的复杂度**：`ModelSpec` Schema、Recipe 编译、状态存储、验证层，约 1200 行。同时省掉了工具调用循环、对话管理和上下文压缩。
- **收益**：主路径每个任务固定 3 次 LLM 调用；同一份冻结规格可以无 LLM 重放（测试、Demo 兜底）；评测可以分层进行。
- **对鲁棒性**：非确定性被限制在 `TaskSpec` 这一个产物里，并且它在进入 HYSYS 之前经过两道校验。
- **对可维护性**：每一层只有一个变化理由（§23.3）。
- **对后续扩展**：新增反应器、反应、后端、LLM 都落在注册表和适配器上，不改 Harness（§23.1）。
- **代价**：规格表达不了的需求，系统做不了。它会明确返回 `UNSUPPORTED`，而不是去试。对一个要 Live Demo 的系统，这是想要的行为。

### 6.5 不引入的东西

| 不引入 | 理由 |
|---|---|
| LangGraph / LangChain | 状态机只有 12 个状态且基本线性，自己实现约 300 行，可以完全控制持久化和 Trace。VM 上依赖越少越好 |
| Multi-Agent | 见 6.4 |
| 运行时 MCP | 进程内 Python 函数足够。MCP 的定位见 §9.6 |
| RAG / 向量库 | HYSYS 帮助文档是开发者的探索资源，运行时不需要 |
| 上下文压缩 / 对话记忆 | 每次 LLM 调用无状态，输入只有几千 token |

### 6.6 五个角色的职责边界

| 角色 | 负责 | 不负责 |
|---|---|---|
| LLM 决策者（本架构中的"Agent"） | 理解语言、抽取特征、推荐反应器并给出理由、表达规格、声明假设、解释结果和异常 | 调用工具、单位换算、算术、判断成功与否、对象命名 |
| Skill | 可复用的领域知识和输出约定，按需注入 LLM | 执行任何动作 |
| Recipe | 每种反应器类型的确定性插件：规格规则、编译为步骤、验证项 | 与 LLM 交互 |
| Tool / Backend | 幂等、带契约的确定性执行；隔离 HYSYS COM 细节 | 决定做什么 |
| Harness | 状态、顺序、权限、预算、验证、恢复、落盘、完成判定 | 任何化工知识 |

---

## 7. Harness 架构

### 7.1 Harness 的 18 项职责

| 职责 | 机制 | 所在模块 |
|---|---|---|
| 任务初始化 | 生成 `task_id` 和 run 目录，加载配置，注册 Skill / Tool / Recipe，加任务锁，检测是否续跑 | `harness/engine.py` |
| 任务理解 | SELECT、SPECIFY 两次结构化 LLM 调用 | `llm/`、`skills/` |
| 任务规划 | `Recipe.compile(ModelSpec)` 生成 `BuildPlan`，纯代码 | `recipes/` |
| 状态管理 | 单一 `TaskState` 文档，每次迁移原子落盘 | `state/` |
| 上下文管理 | 按状态从 `TaskState` 生成最小视图 | `harness/context.py` |
| Skill 发现 | 启动时扫描 `SKILL.md` 的 frontmatter，按状态确定性路由 | `skill_loader.py` |
| Tool 选择 | 由 `BuildPlan` 决定，不由 LLM 决定 | `recipes/` |
| Tool 权限控制 | 状态 → 工具组白名单，另有可写变量白名单 | `tools/registry.py` |
| 工具执行 | Schema 校验 → 前置检查 → 调用 → 结果信封 | `tools/` |
| 执行结果观察 | 结果信封 + `model.read_snapshot` 读回 | `tools/`、`backends/` |
| 结果验证 | 步骤后置条件 + 结果验证层 | `validation/` |
| 失败恢复 | 错误码 → 恢复策略（R0–R5） | `harness/recovery.py` |
| 重试 | 按步骤和错误码计数，只对可重试错误生效 | `harness/recovery.py` |
| 状态持久化 | `state.json`（原子写）+ `trace.jsonl`（追加） | `state/`、`observability/` |
| Checkpoint | 逻辑检查点（步骤日志）+ 物理检查点（`.hsc` 快照） | `state/` |
| 任务继续执行 | 载入状态 → 与 HYSYS 现状对账 → 幂等重放 | `harness/engine.py` |
| 最终验收 | 完成谓词 | `validation/` |
| 任务完成判断 | 只有 Harness 能写入终态 | `harness/engine.py` |

### 7.2 执行闭环

`Observe → Plan → Act → Observe → Verify → Recover → Continue → Complete` 在两个粒度上成立。

| 环节 | 任务级 | 步骤级（BuildPlan 中的每一步） |
|---|---|---|
| Observe | 读取 `TaskState` | 在 HYSYS 中查询目标对象是否已存在、是否已符合期望 |
| Plan | LLM 产出规格，Recipe 编译计划 | 无（步骤已确定） |
| Act | 推进一个状态 | 调用一个工具 |
| Observe | 状态产物 | 结果信封 + 读回 |
| Verify | 状态出口条件 | 后置条件比对（类型、连接、数值容差） |
| Recover | §13 的策略表 | 同左 |
| Continue | 状态迁移并落盘 | 步骤标记为完成并落盘 |
| Complete | 完成谓词为真 | 无 |

### 7.3 任务状态机

```
INIT -> SELECT -> SPECIFY -> VALIDATE -> PLAN -> PREFLIGHT -> BUILD_BASIS -> BUILD_FLOWSHEET
                     ^           |                                                 |
                     +-- issues -+                                                 v
                                                      +--------------------->   SOLVE
                                                      |  next operating case      |
                                                      +----------- VERIFY <-------+
                                                                     |
                                                                     v
                                                                  REPORT -> COMPLETE | COMPLETE_WITH_WARNINGS

any state --error--> RECOVER --> retry step | reconnect | clean rebuild | back to SPECIFY | NEEDS_INPUT | FAILED
SELECT / PLAN --unsupported--> UNSUPPORTED
```

与设计要求中参考状态机的差异及原因：UNDERSTAND 拆成 SELECT 和 SPECIFY（选型是评分关键，单独成步便于单独评测，也让第二步只加载选中类型的知识）；VALIDATE 放在 PLAN 之前（不对未校验的输入做规划）；BUILD_MODEL 和 CONFIGURE 按 HYSYS 的两个环境重新划分为 BUILD_BASIS 和 BUILD_FLOWSHEET（流程图建好之后再改 Basis 代价很高）；新增 PREFLIGHT（动手之前确认会话健康）和 REPORT；SOLVE 与 VERIFY 对工况循环（场景 1 需要两个工况）。

**各状态的输入、输出与工具权限**

| 状态 | 输入 | 输出 | 允许调用 | 明确禁止 |
|---|---|---|---|---|
| INIT | 用户文本，或续跑的 `task_id` | `TaskState`、run 目录、任务锁 | 无 | 一切 LLM 和 HYSYS 调用 |
| SELECT | 用户原文 + `reactor-selection` | `SelectionResult` | LLM 结构化输出 | HYSYS 工具 |
| SPECIFY | 用户原文 + `SelectionResult` + `reactor-modeling/<type>` | `TaskSpec` | LLM 结构化输出 | HYSYS 工具 |
| VALIDATE | `TaskSpec` | 冻结的 `ModelSpec`，或问题清单 | 无，纯代码 | LLM、HYSYS 工具 |
| PLAN | `ModelSpec` | `BuildPlan` | 无，Recipe 编译 | LLM、HYSYS 工具 |
| PREFLIGHT | `BuildPlan` | 会话信息、空白 Case、求解器挂起 | `session.connect`、`case.ensure`、`model.read_snapshot` | `basis.*`、`flowsheet.*` |
| BUILD_BASIS | 计划中的 Basis 步骤 | 组分、流体包、反应、反应集就绪 | `basis.*`、`model.read_snapshot`、`case.save` | `flowsheet.*`、`solver.*` |
| BUILD_FLOWSHEET | 计划中的 Flowsheet 步骤 | 物流、反应器、连接、规定就绪 | `flowsheet.ensure_*`、`model.read_snapshot`、`case.save` | `basis.*`（Basis 已冻结）、`solver.solve` |
| SOLVE | 当前工况 | 求解状态 | `flowsheet.set_spec`（仅工况变量白名单）、`solver.solve`、`model.read_snapshot` | `ensure_*`（结构已冻结） |
| VERIFY | `ModelSnapshot` + `ModelSpec` | `ValidationReport`、`NormalizedResult` | `model.read_snapshot`、`case.save` | 任何写模型的工具 |
| REPORT | `NormalizedResult` + `SelectionResult` + 假设清单 | `report.md`、`result.json` | LLM（只写解读文字） | HYSYS 工具 |
| RECOVER | 错误信封 + `TaskState` | 恢复决策 | `session.restart`、`case.close`、`case.ensure`、`model.read_snapshot` | 写入 COMPLETE |

**各状态的迁移、失败与重试条件**

| 状态 | 进入下一状态的条件 | 失败条件 | 重试与回退 |
|---|---|---|---|
| INIT | 状态落盘成功 | 加锁失败（已有任务在跑）、配置缺失 | 不重试，FAILED |
| SELECT | 输出通过 Schema，类型在白名单内 | LLM 报错；类型不在支持范围 | LLM 调用重试不超过 3 次（退避）；不支持则 UNSUPPORTED |
| SPECIFY | 输出通过 Schema | LLM 报错或输出非法 | 同上 |
| VALIDATE | 没有致命问题，`ModelSpec` 冻结 | 存在致命问题 | 带问题清单回到 SPECIFY，不超过 2 轮；仍失败则 NEEDS_INPUT 或 FAILED |
| PLAN | 计划非空，每一步的工具都已注册 | 该类型没有 Recipe | 不重试，UNSUPPORTED（仍输出选型结论和理由） |
| PREFLIGHT | 版本符合，Case 为空白，求解器已挂起 | 连接失败、许可证问题 | `session.restart` 不超过 1 次 |
| BUILD_BASIS | 所有步骤读回通过 | 组分不存在、反应创建失败 | 步骤重试不超过 2 次 → 干净重建不超过 1 次 → 组分类错误回到 SPECIFY |
| BUILD_FLOWSHEET | 所有步骤读回通过 | 创建或连接失败、读回不一致 | 步骤重试不超过 2 次 → 干净重建不超过 1 次 |
| SOLVE | 求解器空闲，关键变量已知 | 超时、欠规定、不收敛 | 重解 1 次 → 干净重建不超过 1 次 → 规格类错误回到 SPECIFY |
| VERIFY | 没有致命检查失败；还有工况则回到 SOLVE | 任一致命检查失败 | 重新读取 1 次，然后进入 RECOVER |
| REPORT | 报告文件已生成 | LLM 报错 | 重试不超过 3 次；仍失败则输出不含解读文字的报告（数字不依赖 LLM） |

终态共五个：`COMPLETE`、`COMPLETE_WITH_WARNINGS`、`FAILED`、`UNSUPPORTED`、`NEEDS_INPUT`（暂停，等待用户补充后续跑）。

### 7.4 预算与终止

| 预算 | 上限 | 超限行为 |
|---|---|---|
| LLM 调用次数 | 8 次 / 任务（正常路径 3 次） | `FAILED(E_BUDGET)` |
| 规格重述轮数 | 2 | NEEDS_INPUT 或 FAILED |
| 单步重试 | 2 | 升级为干净重建 |
| 干净重建 | 1 | FAILED |
| 状态迁移总数 | 60 | FAILED |
| 任务总时长 | 15 分钟 | FAILED |
| 单次求解等待 | 120 秒 | `E_TIMEOUT` |
| 单次 COM 调用（软超时，调用返回后检查） | 30 秒 | `E_TIMEOUT`。调用阻塞不返回时无法在进程内打断，需要进程隔离，见 K9 |

工具调用总数因此有上界：计划长度 ×（1 + 单步重试上限）×（1 + 重建上限）。不存在无限循环的路径。

### 7.5 完成判定

`COMPLETE` 当且仅当以下条件全部为真，由代码计算：

1. 每个工况的致命检查失败数为 0（§12.3）。
2. 用户请求的每一项输出和派生指标都存在且有值。
3. `.hsc` 已保存，文件存在。
4. 报告已生成。

有警告级检查未通过时为 `COMPLETE_WITH_WARNINGS`。LLM 的任何输出都不能改变终态。

### 7.6 规模约束

Harness 不超过 600 行代码（不含空行、注释和 docstring，由 `tests/test_code_health.py` 检查）：`engine.py`（状态循环和处理函数）、`recovery.py`（恢复策略）、`context.py`（LLM 上下文组装）、`budgets.py`（回路上限）。超出这个规模时应当停下来审视是否过度设计。

### 7.7 P0 与 P1 的实现范围

本节的设计是完整的，实现分两步。P0 只做保证三个场景稳定跑通所需的部分。

| 部分 | P0 | P1 |
|---|---|---|
| 状态循环、状态落盘、Trace | 全部 | 无 |
| 回路上限 | 规格重述 2 轮、单步重试 2 次、干净重建 1 次、求解超时 | 迁移总数、总时长等全局预算 |
| 恢复 | R0 步骤重试、R2 干净重建、R3 规格重述、R5 带诊断中止 | R1 自动重启会话、R4 交互式补充 |
| 检查点 | 冻结 LLM 产物（CP1–CP3），保存已求解的 Case（CP6） | CP4、CP5 的中间快照和 `resume` |
| 工具权限 | 执行器里的一条断言 | 状态到工具组的白名单 |
| 任务锁 | 不做 | `runs/.hysys.lock` |

工具权限放在 P1 的原因：主路径上唯一的工具调用方是按计划执行的执行器，权限门此时防的只是程序缺陷。它在给 LLM 开放工具（P1 的修复回路）时才真正起作用。

任务锁放在 P1 的原因：系统是单用户、任务串行使用的。进程异常退出后残留的锁文件会挡住下一次运行，在现场演示时这个风险比两个任务同时运行更现实。

---

## 8. Skills 架构

### 8.1 原则

Skill 是给 LLM 的按需知识包，不含执行逻辑。本项目区分两类受众：**运行时 Skill** 注入系统内的 LLM 调用；**开发时 Skill** 给 AI 编程助手使用。两者不混放。

### 8.2 候选清单的取舍

| 候选 | 决定 | 理由 |
|---|---|---|
| `reactor-selection` | 保留 | 选型规则是独立、稳定、评分关键的知识 |
| `reaction-parameterization` | 并入 `reactor-modeling` | 参数化方式随反应器类型而变，按类型拆成参考文件更自然 |
| `hysys-modeling` | 不做运行时 Skill | 运行时 LLM 不操作 HYSYS，不需要这份知识。建模序列是 Recipe 和 Backend 的代码。探索 COM 的方法另做开发时 Skill |
| `hysys-validation`、`result-validation` | 不做 Skill | 验证必须是确定性代码，不能交给 LLM |
| `scenario-analysis` | 不做 | 运行时不应有"场景"概念。为场景写 Skill 等于把答案写进系统，与"自主判断"相悖 |
| `troubleshooting` | 保留为 `hysys-troubleshooting` | P0 用于把失败解释给用户；P1 用于提出修复补丁 |
| （新增）`result-reporting` | 新增 | 结果解读的结构和措辞约定可复用 |

### 8.3 最终清单：4 个运行时 Skill

| 问题 | `reactor-selection` | `reactor-modeling` | `result-reporting` | `hysys-troubleshooting` |
|---|---|---|---|---|
| 解决什么问题 | 依据需求 §8、§9 判断反应器类型，给出可审计的理由 | 把反应体系写成合法的 `TaskSpec` | 把 `NormalizedResult` 解读为工程结论 | 把失败翻译成诊断和可选的修复 |
| 何时触发 | SELECT，每任务一次 | SPECIFY，每任务一次；重述时再次 | REPORT | RECOVER，且确定性策略已用尽 |
| 输入 | 用户原文 | 用户原文、`SelectionResult`、重述时的问题清单 | `NormalizedResult`、`SelectionResult`、假设清单 | 错误摘要、`ModelSpec` 摘要、失败的检查项 |
| 输出 | `SelectionResult` | `TaskSpec` | 解读文字，不得自造数字 | 诊断文字；P1 增加 `SpecPatch` |
| 使用的资源 | 选型规则与优先级、"已知量与待求量"辨析、反例 | 通用约定 + `references/<type>.md`（只加载选中的类型）+ 组分别名表 + 物性包选用指引 | 报告结构、工况对比写法、趋势解释要点 | 错误码 → 原因 → 修复动作对照表 |
| 是否包含脚本 | 否。附 `rules.yaml`（各类型的必要输入和优先级），供代码校验 | 否 | 否，表格由代码渲染 | 否 |
| 是否调用 Tools | 否 | 否 | 否 | 否 |
| 能否被复用 | 能。与 HYSYS 无关，任何需要反应器选型的流程可用 | 规格约定与后端无关；命名部分随后端替换 | 能 | 绑定 HYSYS 后端 |
| 如何测试 | L1 评测：类型准确率、5 次重复一致性、对抗样本 | L1 评测：参数抽取正确率、Schema 通过率 | 数字回查：解读中的数字必须能在 `NormalizedResult` 中找到 | 故障注入用例对照期望诊断 |
| 如何版本管理 | frontmatter 中的 `version` + Git。每次 LLM 调用把 Skill 名、版本、内容哈希写入 Trace，评测报告记录 Skill 版本 | 同左 | 同左 | 同左 |

### 8.4 文件结构与加载方式

```
skills/reactor-selection/
├── SKILL.md              # frontmatter: name, description, version, used_in: [SELECT]
├── references/
│   ├── selection_rules.md   # 需求 §8、§9 的规则与优先级
│   └── pitfalls.md          # 已知量与待求量、显式指定优先、黑箱体系、聚合反应例外
├── rules.yaml            # 各类型的必要输入和优先级，供 spec/selection.py 校验
└── examples/             # few-shot，不得使用三个考核场景原文
```

三级渐进加载：元数据（Harness 启动时读取，不进入 LLM）→ `SKILL.md` 正文（进入对应状态时注入）→ `references/`（按条件加载，例如只加载选中反应器类型的那一份）。

"Skill 发现"采用确定性路由（状态 → Skill），不让 LLM 自己挑选。4 个 Skill、3 个调用点，用不上检索；数量增长到十几个以后再考虑基于描述的匹配。文件格式沿用开放的 Agent Skills 约定，同一份 Skill 也可以被 Claude Code 等宿主直接加载。

few-shot 示例使用类比体系（环氧乙烷水合、乙苯脱氢、二氧化硫氧化等），不使用考核场景原文，也不与评测集（§15.3）和留出场景（§15.7）的体系重合，避免泄题造成虚高的准确率。

### 8.5 开发时 Skill

`.claude/skills/hysys-com-probing/`：给 AI 编程助手的 COM 探测方法（类型库导出、从 GUI 建好的参考 Case 反向探测、事实台账的记录格式）。它服务于最高风险项和"AI 协作质量"，不参与运行时。只做这一个。

### 8.6 Skill 还是 Agent：以"判断 Reactor 类型"为例

| 方案 | 评价 |
|---|---|
| A 独立的 Reactor Agent | 不选。选型是一次性分类，不需要工具、多步探索或独立上下文。做成 Agent 只会多出交接和循环 |
| B Reactor Selection Skill | 采纳一半。知识应当是 Skill，但只靠 LLM 输出缺乏可审计性 |
| C 确定性规则 + LLM 结构化输出 | 采纳一半。规则无法直接读自然语言，但能在结构化特征上做判定 |

**结论是 B 与 C 的组合**：Skill 提供知识，一次结构化 LLM 调用同时输出特征（是否给出动力学参数、是否给出转化率或收率的数值、反应是否已全部列出、产物分布是否未知、相态、用户是否显式指定了反应器等）和推荐类型。代码用 `rules.yaml` 做两件事。

第一件，判断每种类型的**必要输入是否齐备**。这是客观事实，不涉及工程判断：

| 类型 | 必要输入 |
|---|---|
| Conversion | 转化率的数值，或能换算成转化率的收率、选择性 |
| Equilibrium | 反应已明确：写出了全部反应式，或点明了一个确定的反应，并且没有要求考虑未写出的副反应。没有给 Keq 时由 HYSYS 按 Gibbs 自由能计算 |
| Gibbs | 没有额外要求。候选产物组分在写规格时确定 |
| PFR / CSTR | 动力学参数。设备尺寸缺失时仍选动力学反应器，并把尺寸列为缺失信息 |

第二件，在必要输入齐备的类型里，按需求 §8 的优先级取第一个，作为规则结论。

规则结论与 LLM 的推荐一致则通过。不一致时带着分歧重问一次，要求 LLM 对照原文核对特征，因为分歧通常来自某个特征抽错了。仍不一致时采用规则结论，把 LLM 的推荐连同理由列为备选写进报告。以规则结论为准的原因是：这个优先级就是需求 §8 自己的选择逻辑，结论可复现、可审计。

需求 §8 末尾提示"没有固定的反应器类型，只有合不合适"。它在这个设计里体现为三点：用户显式指定的类型，只要必要输入齐备就采纳；输出永远带备选和不选的理由；必要输入齐备的类型都保留为备选，被排除的只有做不了的类型。P1 再加一层正则证据（原文里是否出现"转化率为 xx%"、"活化能"、"平衡常数"等），为最关键的三个特征提供与 LLM 无关的旁证。

`SelectionResult` 示意（场景 3）。注意"给出了转化率"和"要求计算收率"是两个不同的特征：

```json
{
  "reactor_type": "gibbs",
  "features": {"user_named_reactor": null, "kinetics_given": false, "conversion_given": false,
               "yield_requested": true, "reactions_fully_listed": false,
               "product_distribution_unknown": true, "max_temperature_C": 1400},
  "rationale": "气化属于高温黑箱体系，产物分布由热力学平衡决定……",
  "evidence": ["气化炉出口温度为1400度", "希望考虑到里面有副反应的情况", "出口组成及CO的收率"],
  "alternatives": [
    {"type": "conversion",  "why_not": "收率是待求量，题面没有给出转化率"},
    {"type": "equilibrium", "why_not": "只给出一个主反应，副反应无法逐一列出"}
  ]
}
```

选型的优先级（来自需求 §8）：

1. 用户显式指定了反应器类型 → 必要输入齐备就采纳；不齐备时说明原因，按后面的规则选择。
2. 给出了动力学参数 → 动力学反应器：管式为 PFR，釜式为 CSTR；没有说明设备形式时，气相为 PFR，液相为 CSTR。聚合反应不适用此规则。只提到管式或釜式而没有动力学参数时，按第 3 至 6 条判断。
3. 没有动力学，但给出了转化率、收率或选择性的**数值** → Conversion。
4. 气化、燃烧、裂解这类高温黑箱体系，或用户明说产物分布未知 → Gibbs。即使用户写出了一个主反应式也是如此，因为实际的产物分布不是这一个反应能描述的。
5. 反应已明确，平衡可由 Keq 或 Gibbs 自由能确定 → Equilibrium。
6. 其余 → Gibbs。

一项能力值得做成 Agent，需要至少满足其一：开放式的多步探索且依赖工具反馈；需要独立的上下文；需要独立的工具权限；可以并行。本项目没有任何能力满足这些条件。

---

## 9. Tool / MCP 架构

### 9.1 分层

```
Harness (executor)
   |  call(tool, args)          <- state-based permission gate
   v
Tool layer       contract: JSON Schema in/out, idempotency, error codes, timeout, trace
   |
   v
SimBackend       backend-neutral domain operations (interface)
   |-- HysysComBackend    pywin32 COM, HYSYS V15
   |-- FakeBackend        in-memory, for harness tests and CI
   v
HYSYS V15
```

Tool 层定义与后端无关的契约，并承担横切关注点（校验、权限、幂等、错误映射、Trace）。Backend 只承担 HYSYS 的机制。两层都要薄：Tool 层是一个通用装饰器加注册表（约 150 行），不是每个工具一份样板。

### 9.2 对候选工具的重新设计

| 候选 | 处理 | 理由 |
|---|---|---|
| `create_case` | 改为 `case.ensure` | 以 run 目录下的路径为身份，可重入 |
| `create_stream` + `set_stream_property` | 合并为 `flowsheet.ensure_stream`；工况变量用 `flowsheet.set_spec` | 创建与配置合并为"期望状态"，重试安全 |
| `create_reaction` + `configure_reaction` | 合并为 `basis.ensure_reaction` | 同上 |
| `create_reactor` + `configure_reactor` | 合并为 `flowsheet.ensure_reactor` | 连接、反应集、规定一次声明 |
| `run_simulation` | 改为 `solver.solve` | HYSYS 稳态在自由度满足时自动求解，"运行"实际是"释放求解器并等待完成" |
| `get_results` | 改为 `model.read_snapshot` | 只读、结构化，同时用于步骤读回和结果读取 |
| `validate_model` | 不是工具 | 属于验证层，消费快照 |
| 新增 | `session.connect`、`session.restart`、`basis.ensure_thermo`、`basis.ensure_reaction_set`、`case.save`、`case.close` | 会话和 Basis 是 HYSYS 的真实结构，候选清单里没有 |

最终 13 个工具，分 6 组：`session`、`case`、`basis`、`flowsheet`、`solver`、`model`。

这份清单和 9.3 的契约是**暂定**的。工具的粒度取决于 Phase 0 的结论（例如反应集是否必须和反应一起创建），G0 之后以 `docs/HYSYS_INTEGRATION.md` 的台账为准修订一次。

### 9.3 工具契约

统一的结果信封：

```json
{"ok": true,  "status": "created|updated|unchanged", "data": {}, "readback": {}, "duration_ms": 0}
{"ok": false, "error": {"code": "E_NOT_FOUND", "message": "...", "retryable": true, "details": {}}}
```

**输入、输出、前置与后置条件**

| 工具 | 输入要点 | 输出要点 | 前置条件 | 后置条件（读回验证） |
|---|---|---|---|---|
| `session.connect` | `visible`、`mode`（attach / launch / auto） | 版本、进程号、是否复用 | 无 | 版本为 V15，COM 对象可用 |
| `session.restart` | 无 | 进程号 | 仅 RECOVER | 旧进程已结束，新会话可用 |
| `case.ensure` | `path`、`mode`（new / open） | Case 标识、路径、是否新建 | 会话已连接 | 活动 Case 路径等于 `path`；new 模式下为空白 |
| `case.save` | `path`（可选） | 路径、字节数 | Case 已打开 | 文件存在且非空 |
| `case.close` | `save` | 是否已关闭 | Case 已打开 | 没有活动 Case |
| `basis.ensure_thermo` | 组分规范名列表、物性包 | 新增与已有组分、流体包名 | 要改动 Basis 时流程图须为空；已符合期望则直接返回 `unchanged` | 流体包存在，组分表与输入一致，物性包一致 |
| `basis.ensure_reaction` | 名称、类型、计量系数、类型参数（转化反应：基准组分和转化率；平衡反应：Keq 来源） | 状态、平衡误差 | 组分已存在 | 反应存在，计量系数读回一致，平衡误差为 0 |
| `basis.ensure_reaction_set` | 名称、成员反应、流体包 | 状态、成员 | 反应已存在 | 成员一致，已挂到流体包 |
| `flowsheet.ensure_stream` | 名称、类别（物流 / 能流）、可选规定（T、P、流量、组成） | 状态、读回值 | Basis 就绪 | 物流存在，已规定的值读回在容差内 |
| `flowsheet.ensure_reactor` | 名称、类型、进料（一股或多股）、气相出口、液相出口、能流（可选）、反应集（可选）、Gibbs 模式、压降、热模式。出口温度是工况变量，不在这里，经 `flowsheet.set_spec` 设置 | 状态、连接 | 相关物流存在，反应集已挂载 | 类型、连接、反应集、规定读回一致 |
| `flowsheet.set_spec` | 对象、变量（白名单）、值、单位 | 读回值 | 对象存在 | 读回在容差内 |
| `solver.solve` | `timeout_s` | 是否求解完成、耗时、各对象状态 | 模型已构建 | 求解器空闲 |
| `model.read_snapshot` | 对象列表（可选） | Basis、物流、反应器的结构化快照 | Case 已打开 | 只读，无副作用 |

**校验、幂等、超时、重试、错误码与调用方**

| 工具 | 参数校验 | 幂等 | 超时 | 重试 | 主要错误码 | 调用方 |
|---|---|---|---|---|---|---|
| `session.connect` | 枚举值 | 是，已连接则复用 | 60 s | 1 | `E_COM_UNAVAILABLE`、`E_VERSION`、`E_LICENSE` | Harness |
| `session.restart` | 无 | 是 | 90 s | 0 | `E_COM_UNAVAILABLE` | Harness，仅 RECOVER |
| `case.ensure` | 路径必须在 run 目录内 | 是，以路径为身份 | 30 s | 1 | `E_CASE_OPEN`、`E_IO` | Harness |
| `case.save` | 路径在 run 目录内 | 是，覆盖 | 30 s | 1 | `E_IO` | Harness |
| `case.close` | 无 | 是 | 30 s | 1 | `E_COM_DISCONNECTED` | Harness，仅 RECOVER 和收尾 |
| `basis.ensure_thermo` | 组分名已规范化，物性包在白名单 | 是 | 30 s | 2 | `E_COMPONENT_NOT_FOUND`、`E_PP_UNSUPPORTED`、`E_BASIS_LOCKED` | Harness |
| `basis.ensure_reaction` | 系数非零，类型在白名单 | 是 | 30 s | 2 | `E_REACTION_INVALID`、`E_NOT_FOUND` | Harness |
| `basis.ensure_reaction_set` | 成员类型与反应器类型兼容 | 是 | 30 s | 2 | `E_SET_INCOMPATIBLE`、`E_ATTACH_FAILED` | Harness |
| `flowsheet.ensure_stream` | 数值为规范单位，组成和为 1 | 是 | 30 s | 2 | `E_CONFLICT`、`E_READBACK_MISMATCH` | Harness |
| `flowsheet.ensure_reactor` | 类型在白名单，连接对象存在 | 是 | 30 s | 2 | `E_CONFLICT`、`E_CONNECT_FAILED`、`E_READBACK_MISMATCH` | Harness |
| `flowsheet.set_spec` | 变量在白名单（白名单就是入参里的枚举），数值范围 | 是，设同值无变化 | 30 s | 2 | `E_SCHEMA`、`E_READBACK_MISMATCH` | Harness |
| `solver.solve` | 超时不超过上限 | 是，对已解模型重解状态不变 | 120 s | 1 | `E_TIMEOUT`、`E_NOT_SOLVED`、`E_NOT_CONVERGED` | Harness |
| `model.read_snapshot` | 无 | 是，只读 | 30 s | 2 | `E_COM_DISCONNECTED`、`E_NOT_FOUND` | Harness；P1 可对 LLM 只读开放 |

表里的"重试"一列是各工具重试上限的参考值。实现上重试只在 Harness 里做，策略以 §13.2 按错误码的表为准，工具和 Backend 自己不重试。

主路径上所有工具都只能由 Harness 调用，LLM 没有任何工具。P1 的修复回路中，`model.read_snapshot` 是唯一可能开放给 LLM 的只读工具。

### 9.4 确定性边界

```
LLM -> structured output -> schema validation -> normalization (units, names) -> business rules
    -> ModelSpec (frozen) -> Recipe.compile -> Tool (pre-check, act, readback) -> HYSYS
    -> snapshot -> result validation -> NormalizedResult -> numbers rendered by code -> LLM interpretation
```

| 归属 | 内容 |
|---|---|
| LLM 负责 | 自然语言理解；特征抽取；候选反应器及理由；反应式、组分、进料、规定的结构化表达；假设和歧义的显式声明；异常解释；结果解读 |
| 代码负责 | Schema 校验；单位换算；配比归一化；组分名解析；元素守恒检查；范围检查；反应器、反应类型、物性包白名单；自由度检查；对象命名；构建顺序；HYSYS API 调用；读回比对；收敛判断；守恒检查；派生指标计算；报告中的全部数字；完成判定 |
| 绝不交给 LLM | 直接调用 HYSYS；决定工具调用顺序；判断是否成功；做任何数值计算；生成对象名；修改已冻结的规格（只能提出补丁，由代码校验后应用） |

规格层的业务规则（通用部分；每种反应器的专有规则在其 Recipe 中）：

1. 反应器类型、反应类型、物性包、热模式都在白名单内。
2. 每个组分名都能解析为 HYSYS 规范名。
3. 每个反应元素守恒（按组分分子式计算）；反应涉及的组分都在组分表内。
4. 每股进料的 T、P、流量、组成齐全；组成基准明确，可归一化。
5. 数值范围合法：温度高于绝对零度，压力和流量为正，转化率在 (0, 100]，同一基准组分的并行转化率之和不超过 100。
6. 反应类型与反应器类型兼容。
7. 自由度一致：热模式与能流、出口温度或热负荷的规定匹配，不欠定也不过定。
8. 待求指标引用的组分存在。
9. 每个取了默认值的字段都有对应的假设条目。没有声明的默认值视为错误。
10. 单位与相态相符：气体体积单位（如 Nm³/h）用于含固体或液体的进料时，按摩尔流量换算，并登记一条歧义假设。

### 9.5 幂等性

设计要求里问"重复调用 `create_case`、`create_stream`、`create_reactor` 怎么办"。本设计的回答是：这三个动作不存在。

- **资源身份**：`(case_path, kind, name)`。名称由代码按约定生成（`Feed`、`Vap`、`Liq`、`Q-100`、`Rxn-1`、`RxnSet-1`、`CRV-100` / `ERV-100` / `GBR-100`），LLM 不参与命名。
- **`ensure` 算法**：查找对象。不存在则创建；存在且与期望一致则返回 `unchanged`；存在但不一致（类型、连接或配置不同）则返回 `E_CONFLICT`，由 Harness 走干净重建。不做"只更新差异"的局部修补：构建只需几秒，重建比修补可靠，Backend 也少一类逻辑。`ensure_*` 从不修改已有对象，规定值不同也算不一致。唯一会修改已有对象的工具是 `flowsheet.set_spec`，它只用于白名单里的工况变量。
- **幂等键**：`sha1(task_id, step_id, 规范化参数)`，记在步骤日志里。日志只用于加速。续跑时仍以 HYSYS 现状做存在性检查，不轻信日志。
- **真相来源的优先级**：HYSYS 现状 > 状态文件 > LLM 的任何说法。

| 类别 | 工具 | 说明 |
|---|---|---|
| 天然幂等 | `model.read_snapshot`、`solver.solve`、`case.save`、`session.connect` | 重复调用不改变状态 |
| 通过 `ensure` 语义幂等 | `case.ensure`、`basis.ensure_*`、`flowsheet.ensure_*`、`flowsheet.set_spec` | `ensure_*` 先查后建，返回 `created` 或 `unchanged`，不一致时报 `E_CONFLICT`；`set_spec` 返回 `updated` 或 `unchanged` |
| 有破坏性但受控 | `session.restart`、`case.close`（不保存） | 仅 RECOVER 状态可调用，受重建预算限制 |
| 非确定 | LLM 调用 | 产物冻结后不再重复调用，续跑直接复用 |

### 9.6 MCP 的定位

**P0 不使用 MCP。** 同一进程内的 Python 函数已经足够。MCP 增加的是传输层和服务生命周期，不增加可靠性。

它在两种情况下才有价值：想用 Claude Desktop、Claude Code 这类外部宿主作为对话入口；或者 VM 访问不了 LLM，需要把 Harness 放在 VM 外、把 HYSYS 能力留在 VM 上。

如果要做（P2），**暴露的是 Harness，不是 HYSYS**：任务级工具 `run_reactor_task`、`get_task_status`、`get_task_trace`，外加只读的 `read_snapshot`。把 `ensure_reactor` 这类细粒度写工具暴露给外部 LLM，等于拆掉 9.4 的确定性边界。工具已经是 JSON Schema 输入、JSON 信封输出，MCP 封装约 60 行。

---

## 10. State 架构

### 10.1 原则

状态与上下文解耦。任务不依赖聊天历史推进。LLM 上下文全部清空后，仅凭状态文件和 HYSYS 现状就能继续。

### 10.2 TaskState

```json
{
  "task_id": "20261002-153012-a7",
  "run_id": 2,
  "input": {"text": "...", "lang": "zh"},
  "current_state": "BUILD_FLOWSHEET",
  "status": "RUNNING",
  "selection": {"reactor_type": "equilibrium", "features": {}, "rationale": "...", "alternatives": []},
  "task_spec": {},
  "model_spec": {"spec_hash": "a3f1...", "...": "..."},
  "plan": {
    "recipe": "equilibrium@1",
    "cursor": 7,
    "steps": [
      {"id": "S07", "tool": "flowsheet.ensure_reactor", "args_hash": "9c2e...",
       "status": "done", "attempts": 1, "result": {"status": "created"}}
    ]
  },
  "hysys": {
    "version": "V15", "pid": 4312, "case_path": "runs/<task_id>/case.hsc",
    "resources": {"fluid_package": "Basis-1", "reactions": ["Rxn-1", "Rxn-2"], "reaction_set": "RxnSet-1",
                  "streams": ["Feed", "Vap", "Liq"], "energy": ["Q-100"], "reactor": "ERV-100"},
    "checkpoints": [{"id": "CP4", "file": "checkpoints/cp4_basis.hsc"}]
  },
  "execution": {
    "case_index": 0,
    "last_tool_call": {"step": "S07", "tool": "flowsheet.ensure_reactor", "ok": true},
    "retries": {"S07": 0},
    "budget": {"llm_calls": 2, "respecify": 0, "rebuilds": 0, "transitions": 9}
  },
  "validation": {"spec": {"fatal": 0, "warn": 1}, "cases": []},
  "results": {"cases": []},
  "errors": []
}
```

### 10.3 五类状态

| 类别 | 字段 | 真相来源 | 更新时机 |
|---|---|---|---|
| Task State | `task_id`、`run_id`、`input`、`current_state`、`status` | `state.json` | 每次状态迁移 |
| Model State | `selection`、`task_spec`、`model_spec`、`spec_hash` | `state.json`，冻结后不可变 | SELECT、SPECIFY、VALIDATE |
| HYSYS State | `version`、`pid`、`case_path`、`resources`、`checkpoints` | **HYSYS 本身**；`state.json` 只存索引 | 每个步骤读回之后 |
| Execution State | `plan.steps[].status`、`cursor`、`case_index`、`last_tool_call`、`retries`、`budget` | `state.json` | 每个步骤之后 |
| Validation State | `validation`、`results` | `state.json`、`result.json` | VALIDATE、VERIFY |

设计要求中示例字段的去向：`scenario` 不设（运行时没有场景概念，评测时用 `label` 仅作标注）；`reactor_type` 在 `selection`；`parameters` 即 `model_spec`；`case_id` 即 `hysys.case_path`；`stream_ids`、`reaction_ids`、`reactor_id` 在 `hysys.resources`；`tool_result` 全量在 Trace，状态里只存摘要；`error` 是 `errors[]`；`retry_count` 是 `execution.retries`。

### 10.4 存储

每个任务一个目录 `runs/<task_id>/`：`state.json`（写临时文件后原子改名）、`trace.jsonl`、`artifacts/`（`selection.json`、`task_spec.json`、`model_spec.json`、`plan.json`、`result.json`、`report.md`）、`*.hsc`（每个工况求解后的 Case，直接放在运行目录下便于查找）、`llm/`（提示词和回复全文）。P1 的中间快照放在 `checkpoints/`。

不使用数据库。单用户、任务串行，文件可以直接打开查看，也方便在 Demo 中展示。P1 用 `runs/.hysys.lock` 保证同一时刻只有一个任务操作 HYSYS（见 §7.7）。

### 10.5 Checkpoint

两级检查点：**逻辑检查点**是步骤日志（每个步骤完成即落盘）；**物理检查点**是 `.hsc` 快照，只在有意义的边界保存。P0 只做 LLM 产物的冻结和已求解 Case 的保存（CP1–CP3、CP6–CP8），CP4、CP5 的中间快照和 `resume` 属于 P1。

| 检查点 | 含义 | 持久化内容 | 从此处恢复时 |
|---|---|---|---|
| CP1 SELECTED | 反应器判断完成 | `selection.json` | 不再调用 SELECT |
| CP2 SPEC_FROZEN | 需求解析和校验完成 | `model_spec.json` + `spec_hash` | 不再调用任何理解类 LLM |
| CP3 PLANNED | 计划编译完成 | `plan.json` | 直接进入 PREFLIGHT |
| CP4 BASIS_READY | 组分、流体包、反应、反应集完成 | `cp4_basis.hsc` + 步骤日志 | 打开快照，从 Flowsheet 步骤继续 |
| CP5 FLOWSHEET_READY | 物流、反应器、连接、规定完成 | `cp5_flowsheet.hsc` + 步骤日志 | 打开快照，进入 SOLVE |
| CP6[k] SOLVED | 工况 k 求解完成 | `case_<k>.hsc` | 打开快照，进入 VERIFY |
| CP7[k] VERIFIED | 工况 k 结果验证完成 | `result.json` 中的工况 k | 进入下一工况或 REPORT |
| CP8 REPORTED | 报告完成 | `report.md` | 终态 |

与设计要求中 8 个检查点的对应关系："Reactor 判断"和"需求解析"是 CP1 和 CP2，顺序相反（先选型再写规格）；"Case、Stream、Reaction、Reactor"四项由步骤日志逐步覆盖，物理快照只落在 CP4 和 CP5 两个边界；HYSYS 中 Reaction 必须先于 Stream（先 Basis 后 Flowsheet）；"Simulation 完成"是 CP6，"Result 验证完成"是 CP7。

检查点有效的条件：`spec_hash` 一致、文件存在、打开后对账通过。任一条不满足就退回上一个有效检查点。

一个务实的判断：这类模型的完整构建只有十几次 COM 调用，耗时是秒级。所以**构建阶段出错时最可靠的恢复手段是丢弃当前 Case，从空白 Case 干净重建**，细粒度的中途续建价值有限。检查点的真正价值在两处：冻结 LLM 产物（续跑不重新询问 LLM，保证可复现），以及保存已求解的 Case。

---

## 11. Context 架构

原则：**状态是真相，上下文是视图。** 每次 LLM 调用都是"系统提示 + Skill + 状态视图"的纯函数，不携带对话历史。

| 上下文类别 | 内容 | 生命周期 | 存放位置 | 进入 LLM 的方式 |
|---|---|---|---|---|
| System Context | 角色、输出契约、硬规则（不做算术、不做换算、缺失即声明） | 永久，约 400 token | `prompts/system.md`，带版本 | 每次调用 |
| Task Context | 用户原文、语言 | 任务期内 | `state.input` | SELECT、SPECIFY、REPORT 原样注入 |
| Scenario Context | 运行时不存在，对应物是 `ModelSpec` | 任务期内，冻结 | `state.model_spec` | REPORT 和重述时注入精简 JSON |
| HYSYS State | 对象、连接、数值、状态 | 实时 | HYSYS 本身，快照落盘 | 不直接进入。只在诊断时注入摘要 |
| Tool Result | 结果信封 | 每次调用 | Trace 全量，状态里存摘要 | 不进入。只有失败步骤的错误摘要进入重述或诊断 |
| Skill Context | `SKILL.md` 正文和参考文件 | 按状态加载 | `skills/` | 按状态路由；参考文件按反应器类型加载 |
| Error Context | 错误码、步骤、消息、读回差异、尝试次数 | 只保留最近 3 条 | `state.errors` | 仅重述和诊断 |
| Validation Context | 检查项、期望值、实测值 | 任务期内 | `state.validation` | 重述时只给失败项；REPORT 给摘要 |

永不进入 LLM 上下文：COM 对象引用、原始 COM 输出、API 密钥、完整 Trace、之前的 LLM 对话。

| 调用点 | 上下文组成 | 输入规模（估计） |
|---|---|---|
| SELECT | 系统提示 + `reactor-selection` + 用户原文 | 约 3k token |
| SPECIFY | 系统提示 + `reactor-modeling` 正文 + 选中类型的参考文件 + 组分别名摘要 + 用户原文 + `SelectionResult`（重述时加问题清单） | 约 4–5k token |
| REPORT | 系统提示 + `result-reporting` + `NormalizedResult` + `SelectionResult` + 假设清单 | 约 3–4k token |
| 诊断（失败时） | 系统提示 + `hysys-troubleshooting` + 错误摘要 + `ModelSpec` 摘要 | 约 3k token |

因此本项目不需要摘要、压缩或记忆模块。这是有意省掉的复杂度。

LLM 调用约定：温度设为 0；用供应商原生的结构化输出（JSON Schema 或工具调用形式），返回后再过一遍 pydantic 校验，不合法时带着校验错误重问一次；不带对话历史；输出语言跟随用户输入；每次调用把模型名、提示词版本、Skill 版本写入 Trace。

---

## 12. Validation 架构

验证分三道门，全部是确定性代码。

### 12.1 门 A：规格验证（VALIDATE 状态）

Schema → 规范化 → 通用业务规则（§9.4）→ Recipe 专有规则。产出冻结的 `ModelSpec` 或结构化的问题清单。

### 12.2 门 B：步骤读回（每个工具调用之后）

每个写操作之后立即读回，比对类型、连接和数值。读回不一致即 `E_READBACK_MISMATCH`，不带着错误往下走。

### 12.3 门 C：结果验证（VERIFY 状态）

| 编号 | 检查 | 级别 |
|---|---|---|
| V1 | 求解完成：求解器空闲、未超时，各对象的状态都是已求解。变量有没有值归 V5 | 致命 |
| V2 | 结构：期望的对象全部存在，类型和连接与 `ModelSpec` 一致 | 致命 |
| V3 | 进料读回：T、P、流量、组成与 `ModelSpec` 一致（相对容差 1e-4） | 致命 |
| V4 | 规定满足：出口温度等于目标（±0.1 °C）；转化率等于设定（±0.1 个百分点）；压降等于设定 | 致命 |
| V5 | 输出存在：产物流的 T、P、流量、组成都有值，不是 HYSYS 的空值 | 致命 |
| V6 | 物理有效：摩尔分率各项非负且和为 1（±1e-6），流量非负 | 致命 |
| V7 | 守恒：总质量守恒（相对误差不超过 0.01%）；C、H、O 等元素守恒（不超过 0.1%），由代码按分子式计算 | 致命 |
| V8 | 请求满足：用户要的每项输出和指标都已算出（两个工况都有结果、三种异构体都出现、CO 收率有值） | 致命 |
| V9 | 合理性：与独立参照值比对；趋势检查（吸热反应的转化率随温度升高）；设定转化率是否超过平衡极限 | 警告 |

V7 的意义在于它能发现"HYSYS 报告已求解，但模型本身是错的"这一类问题，例如计量系数写错或固体相丢失。

### 12.4 从原始结果到用户

```
HYSYS -> ModelSnapshot (raw, HYSYS units)
      -> checks V1-V9
      -> NormalizedResult (canonical units, derived metrics, validation summary, assumptions, provenance)
      -> tables rendered by code
      -> LLM writes interpretation only
      -> user
```

`NormalizedResult` 的规范单位：°C、bar（绝压）、kmol/h、kg/h、摩尔分率和质量分率、kW。派生指标（转化率、收率、比值）由代码按 `ModelSpec.metrics` 里的请求计算；气相出料的干基组成不需要请求，总是给出。出处信息包括 HYSYS 版本、Case 路径、时间戳、`spec_hash`。

报告里的所有数字由代码填入表格，LLM 只写解读文字。P1 增加数字回查：解读中出现的数字必须能在 `NormalizedResult` 中找到。

---

## 13. Recovery 架构

### 13.1 恢复级别

| 级别 | 动作 | 上限 |
|---|---|---|
| R0 | 重试当前步骤，参数不变，依赖幂等 | 每步 2 次 |
| R1 | 重连或重启会话，然后重试 | 1 次 |
| R2 | 干净重建：关闭 Case 不保存 → 用新的文件名新建空白 Case → 从计划第 0 步幂等重放 | 1 次 |
| R3 | 重述规格：把结构化问题清单交给 LLM 重新产出 `TaskSpec`，再过 VALIDATE | 2 轮 |
| R4 | 请求用户补充（NEEDS_INPUT） | 无 |
| R5 | 中止（FAILED），输出诊断 | 无 |

每个错误码对应一条策略链，沿链逐级升级，每一级都有上限。

### 13.2 错误码与策略

| 错误码 | 类别 | 策略链 |
|---|---|---|
| `E_LLM`（超时、限流、非法 JSON） | LLM | 退避重试不超过 3 次 → R5 |
| `E_SCHEMA`、`E_RULE` | 规格 | R3 → R4 或 R5 |
| `E_UNSUPPORTED` | 范围 | 终态 UNSUPPORTED，仍输出选型结论和原因 |
| `E_COM_UNAVAILABLE`、`E_COM_DISCONNECTED` | 会话 | R1 → R2 → R5 |
| `E_TIMEOUT` | 执行 | R0（1 次）→ R1 → R2 → R5 |
| `E_NOT_FOUND`、`E_READBACK_MISMATCH`、`E_ATTACH_FAILED`、`E_CONNECT_FAILED` | 执行 | R0 → R2 → R5 |
| `E_IO`、`E_CASE_OPEN` | 文件与 Case | R0 → R2 → R5 |
| `E_VERSION`、`E_LICENSE` | 环境 | R5，提示用户处理环境问题 |
| `E_CONFLICT`、`E_BASIS_LOCKED` | 状态污染 | R2 → R5 |
| `E_COMPONENT_NOT_FOUND`、`E_PP_UNSUPPORTED` | 规格 | R3 → R5 |
| `E_REACTION_INVALID`、`E_SET_INCOMPATIBLE` | 规格 | R3 → R5 |
| `E_NOT_SOLVED`（欠规定） | 规格或 Recipe 缺陷 | 收集对象状态 → Recipe 的确定性补救 → R3 → R5 |
| `E_NOT_CONVERGED` | 数值 | 重解 1 次 → R2 → R5，附诊断 |
| `E_VALIDATION_FATAL` | 结果 | 重读 1 次 → R2 → R5。**绝不报告成功** |
| `E_BUDGET` | 预算 | R5 |
| `E_TOOL_NOT_ALLOWED`、`E_VAR_NOT_ALLOWED` | 程序缺陷 | R5。属于代码缺陷，不重试，应由 L2 测试提前发现 |

### 13.3 续跑流程（P1）

1. 载入 `state.json`，`run_id` 加 1。
2. 状态早于 PREFLIGHT：直接从该状态继续，已冻结的 LLM 产物不重新生成。
3. 否则：连接 HYSYS → 找到最近的有效检查点 → 打开对应的 `.hsc`（没有就新建空白 Case）→ 读取快照与计划对账 → 从第一个未满足的步骤继续。因为工具是 `ensure` 语义，对账等价于从头幂等重放，已满足的步骤返回 `unchanged`。
4. 快照与计划矛盾（`E_CONFLICT`）时走 R2。

### 13.4 P0 与 P1 的边界

P0 实现 R0、R2、R5，以及规格校验触发的 R3。会话失效时 P0 直接以 R5 中止并给出诊断，由操作者重启 HYSYS 后用冻结规格重跑。P1 再做 R1 的自动重启、运行期的 `SpecPatch`（LLM 从白名单动作中选一个，例如更换物性包、增补组分、切换 Keq 来源）和 R4 的交互。**失败时给出清晰的诊断，比自动修复更重要。**

---

## 14. Observability 架构

### 14.1 事件模型

`trace.jsonl` 每行一个事件：

```json
{"ts": "2026-10-02T15:30:41.203+08:00", "task_id": "20261002-153012-a7", "run_id": 1, "seq": 17,
 "state": "BUILD_FLOWSHEET", "type": "tool_call", "name": "flowsheet.ensure_reactor", "attempt": 1,
 "input": {"name": "ERV-100", "type": "equilibrium"},
 "output": {"ok": true, "status": "created"}, "duration_ms": 412,
 "error": null, "skill": null, "spec_hash": "a3f1..."}
```

`type` 取值：`state_transition`、`llm_call`、`skill_load`、`tool_call`、`validation`、`checkpoint`、`recovery`、`error`。`llm_call` 事件记录模型名、Skill 名与版本、提示词哈希、输入输出 token 数和耗时，提示词和回复全文写入 `runs/<id>/llm/`。API 密钥不落盘。

设计要求中列出的记录字段全部覆盖：`task_id`、`run_id`、`scenario`（评测时的 `label`）、`agent`（本架构中是调用点名 `select` / `specify` / `explain`）、`skill`、`tool`、`input`、`output`、`duration`、`error`、`retry`（`attempt`）、`state_transition`、`validation_result`。

### 14.2 Task Trace

`reactor-agent trace <task_id>` 把事件渲染成时间线。下面是场景 2 的示意，耗时为假想值：

```
Task 20261002-153012-a7   run 1
  INIT
  SELECT            llm:select   skill=reactor-selection@1.0      -> conversion       [CP1]
  SPECIFY           llm:specify  skill=reactor-modeling@1.0 (+references/conversion.md)
  VALIDATE          rules ok, 3 assumptions declared                                  [CP2]
  PLAN              recipe=conversion@1, 9 steps                                      [CP3]
  PREFLIGHT         session.connect, case.ensure
  BUILD_BASIS       basis.ensure_thermo, basis.ensure_reaction, basis.ensure_reaction_set   [CP4]
  BUILD_FLOWSHEET   flowsheet.ensure_stream x3, flowsheet.ensure_reactor              [CP5]
  SOLVE[base]       solver.solve                                                      [CP6]
  VERIFY[base]      V1-V8 pass, V9 pass                                               [CP7]
  REPORT            llm:explain  skill=result-reporting@1.0                           [CP8]
  COMPLETE
```

### 14.3 实现

一个追加写 JSONL 的 `trace.py`，一个渲染命令。不引入外部可观测性平台。每次运行向 `runs/index.jsonl` 追加一行汇总（耗时、LLM 调用数、token 数、工具调用数、重试数、终态），供评测汇总使用。

---

## 15. Evaluation 架构

### 15.1 三层评估

| 层 | 评什么 | 需要 HYSYS | 需要 LLM | 运行位置 | 核心指标 |
|---|---|---|---|---|---|
| L1 理解 | SELECT + SPECIFY + VALIDATE | 否 | 是 | 任何机器（`--dry-run`） | 类型准确率、参数正确率、Schema 通过率、重复一致性 |
| L2 执行（P1） | Harness + Tools，使用 FakeBackend | 否 | 否 | 任何机器、CI | 状态迁移、幂等、故障恢复、续跑、预算 |
| L3 结果 | 冻结规格 → HYSYS → 结果 | 是 | 否 | VM | 结构、规定满足、守恒、与参照值的偏差、可重复性 |
| E2E | 原文 → 报告 | 是 | 是 | VM | 三场景连续通过次数 |

把 LLM 的不确定性（L1）和 HYSYS 的不确定性（L3）分开测量，任何一层出问题都能直接定位。

### 15.2 用例格式

`Input → Expected Reactor → Expected Parameters → Expected HYSYS State → Expected Result`：

```yaml
id: S2-toluene-disproportionation
input: "请帮我完成甲苯歧化反应的模拟……"      # 需求原文，逐字
expected:
  reactor: conversion
  features: {conversion_given: true, kinetics_given: false, user_named_reactor: true}
  params:                                       # 规范化后比较，数值相对容差 1e-3
    feed: {T_C: 380, P_bar: 25, mass_flow_kg_h: 10000, composition: {Toluene: 1}}
    reactions: [{stoich: {Toluene: -2, Benzene: 1}, base: Toluene, conversion_pct: 50}]
  hysys_state:
    objects: {reactor: conversion, material_streams: 3, reactions: 1, reaction_sets: 1}
  results:
    outlet_mole_frac: {Toluene: [0.499, 0.501], Benzene: [0.249, 0.251]}
    xylenes_total_mole_frac: [0.249, 0.251]
    mass_balance_rel_err_max: 1.0e-4
```

### 15.3 L1 评测集

| 编号 | 输入要点 | 期望 |
|---|---|---|
| L1-S1 | 场景 1 原文 | Equilibrium；2 个反应；2 个工况；流量标为假设 |
| L1-S2 | 场景 2 原文 | Conversion；转化率 50% |
| L1-S3 | 场景 3 原文 | Gibbs；CO 收率是待求量 |
| L1-S1b | 场景 1 改写：英文，单位换成 MPa 和 K | Equilibrium；规范化后参数与 L1-S1 一致 |
| L1-S2b | 场景 2 去掉"转化率反应器"字样 | Conversion |
| L1-S3b | 场景 3 改写：只问 CO 收率 | Gibbs，不得因"收率"二字选 Conversion |
| L1-K1 | 气相反应，给出指前因子、活化能、反应级数、管长管径 | PFR |
| L1-K2 | 液相反应，给出动力学和釜体积 | CSTR |
| L1-K3 | 聚合反应，给出动力学 | 标注为规则例外，不套用 CSTR / PFR 规则 |
| L1-E1 | 甲醇合成，给出 Keq 与温度的关系 | Equilibrium |
| L1-G1 | 乙烷蒸汽裂解，求裂解气组成 | Gibbs |
| L1-C1 | 给定转化率和选择性的简单反应 | Conversion |
| L1-X1 | 缺少温度或压力 | 明确指出缺失项，不静默补值 |
| L1-X2 | 计量式不守恒 | VALIDATE 拦截 |
| L1-X3 | 转化率 120% | VALIDATE 拦截 |
| L1-X4 | 不存在的组分名 | 组分解析失败，报错清晰 |
| L1-X5 | 要求模拟精馏塔 | UNSUPPORTED |

### 15.4 L2 测试矩阵

L2 属于 P1-加固。P0 阶段的执行正确性由 L3 的重复运行和 E11 中的真实故障复现来保证。

| 测试 | 断言 |
|---|---|
| 幂等 | 同一计划连续执行两遍，第二遍的创建数为 0，全部返回 `unchanged` |
| 故障注入 | 对每个错误码，在每类步骤上注入，恢复路径和终态与 §13.2 一致 |
| 续跑 | 在每个状态之后终止进程，`resume` 后终态与不中断时一致，LLM 调用数不增加 |
| 预算 | 注入永久性失败，在上限内到达 FAILED |
| 权限 | 在不允许的状态调用工具，返回 `E_TOOL_NOT_ALLOWED` |
| 完成判定 | 注入致命检查失败，不可能到达 COMPLETE |

### 15.5 L3 的参照值

场景 2 的期望值是解析解。场景 1 和场景 3 的期望值是本轮用 JANAF 标准生成 Gibbs 自由能数据、按理想气体独立计算的平衡组成；场景 1 另用常用的 Keq 关联式交叉核对，两种数据来源算出的转化率相差不到 0.5 个百分点。具体数值见 §17，计算方法和脚本见附录 B。

这些是量级核对用的参照值，**不是 HYSYS 的结果**。HYSYS 的物性数据和状态方程会带来小的偏差，所以容差放在主要组分摩尔分率绝对偏差 0.02。

### 15.6 通过门槛

| 指标 | 门槛 |
|---|---|
| L1：三个原文场景的类型判断，各重复 5 次 | 15 / 15 |
| L1：扩展集类型准确率 | 不低于 90% |
| L1：Schema 通过率（含不超过 2 轮重述） | 100% |
| L1：关键参数正确率（规范化后） | 不低于 95% |
| L1：病态输入被拦截或正确拒绝 | 100%，不允许静默建模 |
| L2：全部测试（P1，做了才适用） | 通过 |
| L3：三场景的致命检查 | 全部通过 |
| L3：与参照值的偏差 | 主要组分摩尔分率绝对偏差不超过 0.02；场景 2 不超过 0.001 |
| L3：同一冻结规格连续运行 3 次 | 结果一致（相对偏差不超过 1e-4，求解器容差量级），无重复对象 |
| E2E：三场景连续 3 轮 | 9 / 9 |
| E2E：留出场景（§15.7） | HO-1 至 HO-3 通过致命检查；HO-4 选型正确并明确返回不支持 |

评测运行器把结果写入自动生成的 `docs/EVAL_RESULTS.md`，同时记录模型名、Skill 版本和提交哈希。

### 15.7 留出场景

三个考核场景之外，再准备至少四个没有参与开发调试的体系，从原文到 HYSYS 结果端到端运行。目的是在 Live Demo 之前发现"只对三个场景有效"的问题：组分名解析不了，规格字段表达不了，Recipe 换一个体系就不收敛。

| 编号 | 体系 | 期望类型 | 检验的能力 |
|---|---|---|---|
| HO-1 | 给定转化率的气相反应，例如乙醇脱水制乙烯 | Conversion | 新组分、新计量式。P1 再加选择性的换算 |
| HO-2 | 合成氨，给定温度、压力和氢氮比，求平衡转化率 | Equilibrium | 新组分。P1 再加用户给定 Keq 的来源 |
| HO-3 | 甲烷与空气燃烧，绝热，求烟气组成和温度 | Gibbs | 多股进料、绝热模式、含惰性组分 |
| HO-4 | 给出动力学参数和管式反应器尺寸的气相反应 | PFR | P0 只检验选型结论和"不支持"时的表现。P1 建模 |

留出场景的原文不进入 few-shot，也不在调提示词时反复使用，否则就不再是留出集。

---

## 16. HYSYS 集成方案

### 16.1 路线比较与选择

| 路线 | 说明 | 结论 |
|---|---|---|
| COM 自动化，Python（pywin32） | 通过 COM 驱动 HYSYS 对象模型 | **主路线**。官方支持的自动化方式，公开示例最多，与 LLM 和测试工具链衔接最好 |
| COM 自动化，.NET 或 VBA | 同一套对象模型，宿主不同 | 不选。Excel 的 VBA 对象浏览器可以作为探测辅助 |
| 种子 Case 模板 + COM 改参 | 预置只含骨架的 `.hsc`，COM 只负责参数 | 降级方案，见 16.5 的 I3 级 |
| 脚本录制回放 | HYSYS 自带的脚本功能 | 仅作为探测手段和降级候选，V15 是否可用待确认 |
| GUI 自动化 | 模拟键鼠 | 最后手段。脆弱、慢、难验证 |
| 文件路线 | 把 Case 导出为可读文本（如 XML），改写后再导入 | 候选。V15 是否提供、反应定义是否包含在内，都待确认。若可行，可以绕开"COM 无法创建反应"的缺口 |
| LLM 视觉操作 | 让带屏幕操作能力的模型像人一样操作 HYSYS 界面 | 候选，只作对照。预期慢、不可重复、难验证，但它是"AI 直接操作软件"最直观的路线，值得用一次最小实验说明为什么不选 |

需求文档把探索实现路径列为最重要的考核要素，评分点之一是"是否展示了独立探索不同方案的过程"。所以主路线之外，至少对两条备选路线做最小对照实验并留下证据（16.4 的 E13），结论写进报告。

### 16.2 接口事实台账

四级状态在本文中的用法：

- **【已确认】**：在本项目的 VM 上实测通过。**当前为 0 项。**
- **【官方文档确认】**：AspenTech 官方 Customization Guide 中有明确说明或示例。本轮核对的是公开可获取的 V7.3 版指南，不是 V15 版，V15 上仍要实测。
- **【需要实际 HYSYS V15 验证】**：按对象模型的惯例和经验判断大概率存在，但本轮没有查到官方示例。
- **【未知】**：没有可靠依据。

这四级是本文写作时的证据状态。Phase 0 起，实测结果记在 `docs/HYSYS_INTEGRATION.md` 里，那里用另一套五种状态：已确认、部分确认（只在备注写明的条件下实测通过）、不可行、未测试、不需要（主路线已经走通，这项备用能力不必探测）。

| 编号 | 能力 | 预期形式（假设） | 状态 | 探针 |
|---|---|---|---|---|
| H1 | COM 连接 | `Dispatch("HYSYS.Application")`，另有带版本号的 ProgID | 形式【官方文档确认】；V15 的 ProgID 字符串【需要实际 HYSYS V15 验证】 | E1 |
| H2 | 打开 Case、取活动 Case | `SimulationCases.Open(path)`、`ActiveDocument` | 【官方文档确认】 | E2 |
| H3 | 新建空白 Case | `SimulationCases.Add()` | 【需要实际 HYSYS V15 验证】 | E4 |
| H4 | 保存、另存、关闭 | `Save`、`SaveAs`、`Close` | 【需要实际 HYSYS V15 验证】 | E4、E12 |
| H5 | Basis 修改事务 | `BasisManager.StartBasisChange`、`EndBasisChange` | 【官方文档确认】 | E4 |
| H6 | 读取流体包、物性包、组分 | `FluidPackages.Item(i)`、`PropertyPackageName`、`Components` | 【官方文档确认】 | E2 |
| H7 | 新建流体包并指定物性包 | `FluidPackages.Add(...)` | 【需要实际 HYSYS V15 验证】 | E4 |
| H8 | 添加库组分 | `Components.Add(name)`，以及库中的规范名 | 【需要实际 HYSYS V15 验证】 | E4 |
| H9 | 创建转化反应（计量系数、基准组分、转化率） | 无 | 【未知】 | E6 |
| H10 | 创建平衡反应并指定 Keq 来源（Gibbs 自由能、固定值、随温度变化） | 无 | 【未知】 | E8 |
| H11 | 创建反应集、加入成员、挂到流体包 | 无 | 【未知】 | E6 |
| H12 | 新建物流和能流 | `MaterialStreams.Add(name)`、`EnergyStreams.Add(name)` | 【需要实际 HYSYS V15 验证】 | E5 |
| H13 | 写入 T、P、流量 | `Temperature.SetValue(value, unit)` 等 | 【官方文档确认】 | E2、E5 |
| H14 | 写入组成 | `ComponentMolarFraction.Values = [...]` | 读取有公开示例；写入【需要实际 HYSYS V15 验证】 | E5 |
| H15 | 新建反应器 | `Operations.Add(name, typeName)`，以及三种反应器的 `typeName` | 【需要实际 HYSYS V15 验证】，`typeName` 通过反向探测获得 | E3、E7 |
| H16 | 反应器连接与配置（进出料、能流、反应集、压降、Gibbs 模式） | 无 | 【未知】 | E7–E9 |
| H17 | 求解控制 | `Solver.CanSolve` | 【官方文档确认】 | E2 |
| H18 | 变量是否已知，是规定值还是计算值 | `IsKnown`、`State` | 【官方文档确认】 | E2 |
| H19 | 对象状态文本（未求解、欠规定等提示） | 无 | 【未知】 | E7 |
| H20 | 读取结果（T、P、流量、组成、分组分流量、热负荷） | `GetValue(unit)`、`ComponentMolarFraction.Values` | 基本读取【官方文档确认】；分组分流量和热负荷【需要实际 HYSYS V15 验证】 | E7 |
| H21 | 固体碳组分及其在 Gibbs 反应器中的行为 | 库组分 `Carbon` | 【未知】 | E10 |
| H22 | 空值的表示方式 | 约定的哨兵值 | 【需要实际 HYSYS V15 验证】 | E2 |
| H23 | 模态弹窗对 COM 调用的阻塞 | 无 | 【未知】 | E11 |
| H24 | 降级通道：内部变量访问、脚本回放 | 无 | 【未知】 | 仅在 E6–E9 受阻时探测 |
| H25 | 组分库的枚举或检索（按名称、分子式查到规范名） | 无 | 【未知】 | E4 |
| H26 | Case 导出为可读文本并重新导入 | 无 | 【未知】 | E13 |

本轮在公开版 Customization Guide 中**没有查到**通过自动化新建物流、单元操作或反应的示例（检索基于自动摘要，可能有遗漏）。官方文档覆盖的是"连接、读写已有对象"，而本项目的核心需求是"创建"。这就是 Phase 0 必须先做的原因。

### 16.3 探测方法

1. **类型库导出**。用 pywin32 的 `makepy` 为 HYSYS 类型库生成包装代码，在生成的文件里检索 `Reaction`、`Equilibrium`、`Conversion`、`Gibbs`、`Reactor`、`Add`。这一步直接回答"对象模型里有什么"。
2. **反向探测**。在 GUI 里手工建一个最小参考 Case（三种反应器各一台，带反应和反应集），保存后用 COM 打开，枚举对象，打印类型名和成员。这一步回答"GUI 建出来的东西在 COM 里长什么样"，三种反应器的 `typeName` 由此获得。
3. **官方帮助**。VM 上 HYSYS 的 Help 菜单中查 Automation 和 Customization 章节，以及三种反应器的操作说明（需求文档已指明这是可用资源）。帮助文件如果是 `.chm` 格式，用 `hh.exe -decompile <输出目录> <文件.chm>` 解包成 HTML，交给 AI 编程助手全文检索，比在帮助窗口里翻页快得多。
4. **录制对照**（如可用）。录制一次 GUI 操作，查看产生的脚本文本，推断内部对象名。
5. **探索日志**。每个探针在 `docs/HYSYS_INTEGRATION.md` 里记一条：目的、做法、结果、结论、对应脚本。走不通的路线同样记录，它们是报告"探索过程"一节的直接素材。

探针脚本草案。除 `Dispatch` 之外，成员名都是待验证的假设，大小写以类型库为准：

```python
# spikes/e3_reverse_probe.py
import win32com.client as w32

app = w32.gencache.EnsureDispatch("HYSYS.Application")   # 早绑定，同时生成类型库包装
app.Visible = True
case = app.SimulationCases.Open(r"C:\work\ref_cases\three_reactors.hsc")   # GUI 手工建好的参考 Case
fs = case.Flowsheet
for i in range(fs.Operations.Count):
    op = fs.Operations.Item(i)
    print(op.name, op.TypeName)                               # 三种反应器的 typeName
    print([m for m in dir(op) if not m.startswith("_")])      # 可用成员
```

### 16.4 Phase 0 探针清单

| 编号 | 内容 | 通过标准 | 时间盒 |
|---|---|---|---|
| E0 | 环境 | 64 位 Python、pywin32、Git 可用；从 VM 发出一次最小 LLM 调用并得到回复 | 20 分钟 |
| E1 | 连接 | 取得 Application 对象并读到版本；确认注册表中的 ProgID | 15 分钟 |
| E2 | 读写已有 Case | 读 T、P、流量、组成；改温度后自动重算；`CanSolve` 开关有效；记录空值的表示 | 30 分钟 |
| E3 | 类型库导出和反向探测 | 在 GUI 中手工建好参考 Case；得到三种反应器的 `typeName`，以及反应、反应集、反应器对象的成员清单 | 60 分钟 |
| E4 | 新建 Case 和 Basis | 代码新建 Case、流体包（PR）、5 个组分；另存后重开一致；弄清组分库能否按名称或分子式检索 | 45 分钟 |
| E5 | 新建物流 | 代码新建物流并规定 T、P、流量、组成，闪蒸完成 | 30 分钟 |
| E6 | 反应和反应集 | 代码创建转化反应和反应集并挂到流体包，GUI 中可见且正确 | 90 分钟。**最高风险** |
| E7 | 转化反应器全链路 | 代码建反应器、连接、挂反应集、设压降、求解；读回结果与场景 2 解析解一致；弄清求解是否随调用同步完成，以及用什么判断求解结束 | 60 分钟。**闸门 G0** |
| E8 | 平衡反应和平衡反应器 | Keq 来源为 Gibbs 自由能，另试一次固定 Keq；能流加出口温度规定；与场景 1 参照值的偏差在容差内 | 60 分钟 |
| E9 | Gibbs 反应器（纯气相） | 用场景 1 的进料，不挂反应集；结果与 E8 接近 | 30 分钟 |
| E10 | 固体碳 | 库中能加入碳组分；40 °C、40 bar 的浆料物流能闪蒸；Gibbs 反应器在 1400 °C 收敛；未反应碳的去向明确；与场景 3 参照值量级一致 | 60 分钟 |
| E11 | 鲁棒性 | 同一脚本连跑两次的行为；求解中途结束 HYSYS 进程后的异常形态；是否出现阻塞性弹窗 | 30 分钟 |
| E12 | 保存与重开 | 保存的 `.hsc` 重新打开后结果一致 | 15 分钟 |
| E13 | 备选路线对照 | 用同一个最小任务（在空白 Case 中加一台转化反应器）试两条备选路线：界面自动化（控件树或视觉操作）和文件路线（文本导出导入、脚本回放是否存在）。各记录是否可行、耗时、可重复性、可验证性 | 60 分钟 |

E0 到 E7 约 6 小时，E8 到 E13 约 4 小时。时间盒是上限，探针比预期顺利时，省下的时间进入机动。E13 在 G0 之后做；如果主路线在 E6 受阻，E13 提前，它的结论直接决定降级方向。

闸门规则：

- **G0（E7 通过）**：证明 I1 路线可行。进入 Phase 1，E8–E13 继续进行。
- E6 的时间盒用尽仍未通过：依次尝试降级阶梯的 I2、I3，每级再给 60 分钟。
- G0 通过之前，不投入 Harness 和 LLM 部分的大规模开发。与 HYSYS 无关的 Schema、Skill 文本、评测集可以并行准备。

### 16.5 降级阶梯

| 级别 | 做法 | 对"实际创建"的满足程度 | 代价 |
|---|---|---|---|
| I1 | 全部通过 COM 编程创建 | 完全满足 | 无 |
| I2 | COM 加内部变量通道补缺口 | 完全满足 | 依赖未公开接口，在报告中说明 |
| I3 | 种子 Case：每种反应器类型预置一个只含骨架的 `.hsc`（空反应集、未连接的反应器），COM 负责组分、计量系数、物流、连接、规定 | 部分满足。对象是真实的，但不是从零创建 | 新反应器类型需要新的种子文件；在报告中如实说明 |
| I4 | 只对 COM 做不到的那一步使用 GUI 自动化 | 满足 | 脆弱，Demo 风险高 |
| I5 | 全 GUI 自动化 | 满足 | 不建议 |

按能力逐项选择能跑通的最低级别。级别封装在 Backend 内部，Tool 契约和 Harness 不变。

### 16.6 COM 使用纪律

1. 所有 COM 调用在同一线程内执行。
2. 构建期间挂起求解器，构建完成后释放，避免每次写入触发重算和中间态报错。
3. 写入一律带单位，读取一律指定单位。Backend 内部只使用一套固定单位，单位换算在规格层完成。
4. 每次写入后读回。
5. 记录 HYSYS 进程号。会话失效时按进程号结束并重启，不误伤其他实例。
6. Backend 之外不出现任何 COM 对象引用。
7. 所有探针结论写入 `docs/HYSYS_INTEGRATION.md`，记录接口、调用形式、验证日期、对应的探针脚本。**没有进入台账的接口不允许在 Backend 中使用。**

### 16.7 部署形态

Harness、Tools、Backend 运行在 VM 上的同一个 Python 进程里，LLM 通过 HTTPS 访问。前提是 VM 能访问 LLM API，由 E0 验证。

不能访问时的备选：Harness 留在开发机，VM 上只运行一个把工具注册表暴露出去的薄服务。Tool 契约是 JSON 进、JSON 出，这个拆分不改 Harness。

---

## 17. 三个 Scenario 详细拆解

三个小节的结构相同：流程拆解、假设、HYSYS 构建计划、期望结果、异常。三个场景走同一条状态路径（§7.3），差别只在 SELECT 的结论、加载的参考文件、使用的 Recipe 和工况数。期望结果中的数值是独立参照值（来源见 §15.5），不是 HYSYS 输出。

### 17.1 场景 1：甲烷蒸汽重整

**流程拆解**

| 环节 | 内容 |
|---|---|
| Natural Language | 甲烷和水蒸气摩尔比 1 : 2.7；主反应和副反应各一个；工况 1 出口 710 °C，工况 2 出口 600 °C；压力 13.5 bar；进料 520 °C；流量自定 |
| Parameter Extraction | 进料 T = 520 °C，P = 13.5 bar，组成 CH4 : H2O = 1 : 2.7（摩尔）；两个工况的出口温度；流量缺失，取假设值；待求量是出口组分分布 |
| Reactor Selection | **Equilibrium Reactor**。没有动力学参数，没有给定转化率；给出了两个显式的可逆反应；目标是不同温度下的平衡产物分布。备选 Gibbs 能得到几乎相同的结果，但用户已经写明反应方程，按需求 §8 的逻辑 Equilibrium 更贴切。Conversion 没有转化率可用 |
| Skill | `reactor-selection`、`reactor-modeling`（`references/equilibrium.md`）、`result-reporting` |
| Plan | Recipe `equilibrium`：11 个构建步骤，2 个工况 |
| Tool | 见构建计划 |
| HYSYS | 流体包 Peng-Robinson；5 个组分；2 个平衡反应；1 个反应集；3 股物流和 1 股能流；1 台平衡反应器 |
| Validation | V1–V9，外加工况间的趋势检查 |
| Result | 两个工况的出口组成（湿基和干基）、CH4 转化率、H2/CO 比、热负荷、对比说明；进料的小时流量和折算的年处理量 |

反应：R1 为 CH4 + H2O ⇌ CO + 3 H2；R2 为 CO + H2O ⇌ CO2 + H2。

两个容易判错的方向：有两个反应不等于"产物分布未知"，反应已经全部列出，不选 Gibbs；重整炉是管式反应器，但没有动力学参数，按需求 §8.3 不选 PFR。

**假设**

| 编号 | 假设 | 说明 |
|---|---|---|
| A1-1 | 进料 CH4 1000 kmol/h，H2O 2700 kmol/h，合计 3700 kmol/h | CH4 约 22400 Nm³/h、16 t/h。按年操作 8000 小时约 1.8 亿 Nm³/a，量级上对应约 30 万吨/年合成氨装置的工艺原料气。流量不影响平衡组成，只影响流量和热负荷的绝对值 |
| A1-2 | 13.5 bar 为绝压 | 如果是表压，CH4 转化率下降约 1 个百分点（710 °C 工况约 1.4，600 °C 工况约 0.8） |
| A1-3 | 进料压力等于 13.5 bar，反应器压降为 0 | 题面只给了一个压力 |
| A1-4 | Keq 由 Gibbs 自由能计算 | 用户没有提供平衡常数，符合需求 §8 对 Equilibrium 的使用条件 |
| A1-5 | 进料只含 CH4 和 H2O | 题面如此 |

**HYSYS 构建计划**

| 步 | 工具 | 内容 |
|---|---|---|
| 1 | `session.connect` | 连接 HYSYS |
| 2 | `case.ensure` | 新建空白 Case |
| 3 | `basis.ensure_thermo` | 甲烷、水、CO、CO2、氢气；Peng-Robinson |
| 4 | `basis.ensure_reaction` | `Rxn-1`，平衡反应，R1 的计量系数，Keq 来源为 Gibbs 自由能 |
| 5 | `basis.ensure_reaction` | `Rxn-2`，平衡反应，R2 的计量系数 |
| 6 | `basis.ensure_reaction_set` | `RxnSet-1` 包含两个反应，挂到流体包。CP4 |
| 7 | `flowsheet.ensure_stream` | `Feed`：520 °C，13.5 bar，3700 kmol/h，CH4 0.2703，H2O 0.7297 |
| 8–10 | `flowsheet.ensure_stream` | `Vap`、`Liq`、能流 `Q-100` |
| 11 | `flowsheet.ensure_reactor` | `ERV-100`，连接进出料和能流，挂 `RxnSet-1`，压降 0。CP5 |
| 工况 T710 | `flowsheet.set_spec` → `solver.solve` → `model.read_snapshot` | 出口温度 710 °C，求解，读回，验证 |
| 工况 T600 | 同上 | 出口温度 600 °C |

**期望结果（参照值）**

| 量 | 710 °C | 600 °C |
|---|---|---|
| CH4 转化率 | 约 55% | 约 30% |
| 出口湿基摩尔分率：CH4 | 0.094 | 0.162 |
| 出口湿基摩尔分率：H2O | 0.381 | 0.499 |
| 出口湿基摩尔分率：H2 | 0.411 | 0.269 |
| 出口湿基摩尔分率：CO | 0.047 | 0.012 |
| 出口湿基摩尔分率：CO2 | 0.067 | 0.058 |
| 出口干基摩尔分率：H2 / CH4 / CO / CO2 | 0.663 / 0.152 / 0.076 / 0.109 | 0.537 / 0.323 / 0.024 / 0.117 |
| 出口总摩尔流量 | 约 4800 kmol/h | 约 4305 kmol/h |
| H2/CO | 约 8.7 | 约 23 |
| 热负荷 | 正值（吸热） | 正值，小于 710 °C 工况 |

趋势检查：温度升高时，强吸热的重整反应正向移动，CH4 转化率升高；放热的变换反应逆向移动，CO 与 CO2 的比值升高。

**异常**

- Keq 来源无法通过 COM 设置：先看默认来源是否就是 Gibbs 自由能，其次尝试 HYSYS 内置的平衡反应库，仍不行则走 I3 种子 Case。
- 同时规定了出口温度和热负荷：Recipe 规则保证只规定其一。
- 气相反应的液相出口流量为零：属正常，V6 允许零流量。

### 17.2 场景 2：甲苯歧化

**流程拆解**

| 环节 | 内容 |
|---|---|
| Natural Language | 甲苯进入转化率反应器；2 C7H8 → C6H6 + C8H10；10000 kg/h；380 °C；2.5 MPa；转化率 50%；产物是苯和邻、间、对二甲苯；不讨论动力学，不考虑副反应 |
| Parameter Extraction | 进料为纯甲苯，质量流量 10000 kg/h，T = 380 °C，P = 2.5 MPa；基准组分甲苯，转化率 50%；三种异构体的分配比缺失，取假设值；待求量是产物分布和流股组成 |
| Reactor Selection | **Conversion Reactor**。用户显式指定了转化率反应器，给出了转化率数值，并声明不讨论动力学。备选 Equilibrium：该反应确实受平衡限制，但用户要的是指定转化率下的出口分布。50% 低于平衡极限（文献值约 55%–60%），设定可行 |
| Skill | `reactor-selection`、`reactor-modeling`（`references/conversion.md`）、`result-reporting` |
| Plan | Recipe `conversion`：9 个构建步骤，1 个工况 |
| HYSYS | 流体包 Peng-Robinson；5 个组分；1 个转化反应；1 个反应集；3 股物流；1 台转化反应器，绝热 |
| Validation | V1–V9，与解析解逐项比对 |
| Result | 出口组成（摩尔和质量）、各组分流量、三种异构体分布、出口温度 |

**假设**

| 编号 | 假设 | 说明 |
|---|---|---|
| A2-1 | 2.5 MPa 为绝压，进料压力等于操作压力，压降为 0 | 题面只给了操作压力 |
| A2-2 | 绝热操作，不接能流 | 题面没有给出口温度；需求 §9 说明该反应热效应不强。出口温度作为结果输出 |
| A2-3 | 二甲苯异构体按对 : 间 : 邻 = 24 : 52 : 24 分配 | 题面未给。取反应温度附近热力学平衡分布的文献近似值，可由用户覆盖 |
| A2-4 | 转化率以甲苯为基准，与温度无关 | 题面给的是固定值 |

反应的实现方式：首选单个转化反应，产物用分数计量系数，即 2 甲苯 → 1 苯 + 0.24 对二甲苯 + 0.52 间二甲苯 + 0.24 邻二甲苯。三种二甲苯分子量相同，反应严格配平。备选是三个并行反应，转化率分别为 12%、26%、12%，但需要先确认 HYSYS 对并行转化反应的排序语义。两种方式在 E6 中各试一次。

**HYSYS 构建计划**

| 步 | 工具 | 内容 |
|---|---|---|
| 1 | `session.connect` | 连接 |
| 2 | `case.ensure` | 新建空白 Case |
| 3 | `basis.ensure_thermo` | 甲苯、苯、对二甲苯、间二甲苯、邻二甲苯；Peng-Robinson |
| 4 | `basis.ensure_reaction` | `Rxn-1`，转化反应，基准组分甲苯，转化率 50% |
| 5 | `basis.ensure_reaction_set` | `RxnSet-1`，挂到流体包。CP4 |
| 6 | `flowsheet.ensure_stream` | `Feed`：380 °C，25 bar，10000 kg/h，纯甲苯 |
| 7–8 | `flowsheet.ensure_stream` | `Vap`、`Liq` |
| 9 | `flowsheet.ensure_reactor` | `CRV-100`，连接进出料，挂 `RxnSet-1`，压降 0，不接能流。CP5 |
| 工况 base | `solver.solve` → `model.read_snapshot` | 求解，读回，验证 |

**期望结果（解析解）**

进料 10000 kg/h ÷ 92.14 kg/kmol = 108.53 kmol/h。反应前后总摩尔数不变。

| 组分 | 摩尔流量 kmol/h | 摩尔分率 | 质量流量 kg/h |
|---|---|---|---|
| 甲苯 | 54.26 | 0.500 | 5000 |
| 苯 | 27.13 | 0.250 | 2119 |
| 对二甲苯 | 6.51 | 0.060 | 691 |
| 间二甲苯 | 14.11 | 0.130 | 1498 |
| 邻二甲苯 | 6.51 | 0.060 | 691 |
| 合计 | 108.53 | 1.000 | 10000 |

出口温度应接近 380 °C。与进料温度相差超过 10 °C 时给出警告。

**异常**

- HYSYS 不接受分数计量系数：改用三个并行反应。
- 380 °C 高于甲苯的临界温度（约 319 °C），进料是单一气相，液相出口流量为零属正常。
- 设定转化率与平衡极限的关系：需求 §9.2 特别提到该反应受平衡限制。P0 在选型理由中定性说明。P1 用同一进料在 HYSYS 中再跑一台 Gibbs 反应器，得到平衡转化率，与设定的 50% 并列报告；设定值超过平衡值时给出警告，不阻止建模。

### 17.3 场景 3：水煤浆气化

**流程拆解**

| 环节 | 内容 |
|---|---|
| Natural Language | 进料为煤和水；流量 80000 Nm³/h；压力 40 bar；水煤浆浓度 62 wt%；进料 40 °C；主要反应 C + H2O → CO + H2；出口 1400 °C；求出口组成和 CO 收率；不考虑灰分。提示：CO 收率指有多少煤转化成了 CO，并且希望考虑副反应 |
| Parameter Extraction | 进料 T = 40 °C，P = 40 bar，流量 80000 Nm³/h，质量分率 C 0.62、H2O 0.38；出口温度 1400 °C；待求量是出口组成和 CO 收率 |
| Reactor Selection | **Gibbs Reactor**。气化是典型的黑箱体系，极高温，产物分布由热力学平衡决定；用户要求考虑副反应，而副反应没有逐一给出；没有动力学，也没有给定的转化率。备选 Equilibrium：只给了一个主反应，副反应写不全。备选 Conversion：CO 收率是待求量，不是已知量 |
| Skill | `reactor-selection`、`reactor-modeling`（`references/gibbs.md`）、`result-reporting` |
| Plan | Recipe `gibbs`：8 个构建步骤，1 个工况 |
| HYSYS | 流体包 Peng-Robinson；6 个组分（碳、水、CO、氢气、CO2、甲烷）；不建反应集，使用 Gibbs 反应器的纯自由能最小化模式；3 股物流和 1 股能流；1 台 Gibbs 反应器 |
| Validation | V1–V9，重点是碳元素守恒 |
| Result | 出口气体组成、未反应的碳量、CO 收率、碳转化率、所需热负荷 |

Gibbs 反应器的"副反应"通过**组分清单**体现：把可能生成的 CO2 和 CH4 加入组分表，自由能最小化就会自动包含变换、甲烷化等反应。这一条写进 `references/gibbs.md`；Recipe 的规则同时检查组分表覆盖了进料里的每一种元素。

**假设**

| 编号 | 假设 | 说明 |
|---|---|---|
| A3-1 | 煤按纯碳（石墨）处理 | 题面说明不考虑灰分，并且用 C 书写主反应 |
| A3-2 | 80000 Nm³/h 是进料的总摩尔流量（碳和水合计），折合 3569 kmol/h | Nm³/h 是气体体积单位，用于浆料不寻常。这里按"以标准体积表示的摩尔流量"理解，标准状态取 0 °C、101.325 kPa，即 22.414 Nm³/kmol。流量只影响绝对量，不影响出口组成和 CO 收率 |
| A3-3 | 62 wt% 是碳的质量分率，水为 38 wt% | 水煤浆浓度的通常含义 |
| A3-4 | 进料中没有氧气 | 题面的进料只有煤和水。出口 1400 °C 通过能流供热实现，报告给出所需热负荷。**这是对结果影响最大的一条假设，建议向出题方确认** |
| A3-5 | 40 bar 为绝压，反应器压降为 0 | 题面只给了一个压力 |
| A3-6 | CO 收率 = 出口 CO 摩尔流量 ÷ 进料碳摩尔流量 | 来自题面提示 |

由假设推出的进料量（代码计算）：摩尔分率 C 0.710、H2O 0.290；碳 2534 kmol/h（30.4 t/h，约 730 t/d）；水 1035 kmol/h（18.7 t/h）；浆料合计 49.1 t/h。碳与水的摩尔比是 2.45 : 1，水是限量反应物，所以 CO 收率的上限是 40.9%。

**HYSYS 构建计划**

| 步 | 工具 | 内容 |
|---|---|---|
| 1 | `session.connect` | 连接 |
| 2 | `case.ensure` | 新建空白 Case |
| 3 | `basis.ensure_thermo` | 碳、水、CO、氢气、CO2、甲烷；Peng-Robinson。CP4 |
| 4 | `flowsheet.ensure_stream` | `Feed`：40 °C，40 bar，3569 kmol/h，摩尔分率 C 0.710、H2O 0.290（由质量分率 0.62、0.38 换算；规格里的组成一律用摩尔分率） |
| 5–7 | `flowsheet.ensure_stream` | `Vap`、`Liq`、能流 `Q-100` |
| 8 | `flowsheet.ensure_reactor` | `GBR-100`，纯 Gibbs 模式，连接进出料和能流，压降 0。CP5 |
| 工况 base | `flowsheet.set_spec` → `solver.solve` → `model.read_snapshot` | 出口温度 1400 °C，求解，读回，验证 |

**期望结果（参照值）**

| 量 | 参照值 |
|---|---|
| 出口气体 CO | 约 1017 kmol/h，摩尔分率 0.500 |
| 出口气体 H2 | 约 981 kmol/h，摩尔分率 0.482 |
| 出口气体 CH4 | 约 22 kmol/h，摩尔分率 0.011 |
| 出口气体 H2O | 约 11 kmol/h，摩尔分率 0.005 |
| 出口气体 CO2 | 约 3.5 kmol/h，摩尔分率 0.002 |
| 未反应的固体碳 | 约 1491 kmol/h，占进料碳的 59% |
| **CO 收率** | **约 40%** |
| 碳转化率（气化的碳 ÷ 进料碳） | 约 41% |
| 所需外供热 | 约 85 MW（粗估） |

工程提示：按题面建模（没有氧气）时，1400 °C 的出口温度要靠约 85 MW 的外供热维持，真实气化炉里这部分热量来自氧气的部分氧化；同时水量把 CO 收率限制在约 41% 以内。系统按题面如实建模，把这两点作为显式假设和工程提示写进报告。加氧变体列为 P2，不擅自加入。

**异常与降级**

| 问题 | 处理 |
|---|---|
| 组分库中没有可用的碳，或 Gibbs 反应器不把它作为固相参与平衡 | 首选直接使用库组分。不行时改用两段法：先用计量反应把碳和水按限量反应物转成 CO 和 H2，再用 Gibbs 反应器做气相平衡，未反应的碳作为惰性物穿过。主模型仍是 Gibbs 反应器，在报告中如实说明 |
| 含固体的浆料物流在 40 °C 闪蒸异常 | 改为碳和水两股进料分别进入反应器 |
| "80000 Nm³/h"的理解被否定 | 流量是规格中的一个字段，改值后重跑 |
| Gibbs 反应器在 1400 °C 不收敛 | 检查组分表是否缺少必要产物，检查压降规定 |

---

## 18. 风险矩阵

| 编号 | 风险 | 概率 | 影响 | 发现方式 | 缓解与降级 | 阶段 |
|---|---|---|---|---|---|---|
| K1 | COM 无法创建或配置反应、反应集 | 中 | 高 | E6 | 降级阶梯 I2–I4 | Phase 0 |
| K2 | 反应器的专有配置（挂反应集、Gibbs 模式、压降）COM 不可达 | 中 | 高 | E7–E9 | 同上 | Phase 0 |
| K3 | 固体碳在 Gibbs 反应器中不可用或行为异常 | 中 | 高（场景 3） | E10 | §17.3 的两段法 | Phase 0 |
| K4 | 平衡反应的 Keq 来源无法通过 COM 设置 | 中 | 中（场景 1） | E8 | 默认来源或内置反应库，仍不行则 I3 | Phase 0 |
| K5 | LLM 反应器误判：场景 3 判成 Conversion 或 Equilibrium，场景 1 判成 Gibbs 或 PFR | 中 | 高 | L1 评测 | Skill 规则、选型规则校验（必要输入和优先级）、对抗样本、温度 0、重复一致性 | Phase 2 |
| K6 | LLM 参数抽取错误（配比、单位、基准） | 中 | 中 | L1 评测、V3 | 代码换算、读回、报告回显解析结果 | Phase 2 |
| K7 | 需求歧义导致结果与考官预期不一致 | 高 | 中 | §25 | 显式假设登记并在报告中声明；流量、压力基准等都是可改字段 | 全程 |
| K8 | VM 无法访问 LLM API | 低到中 | 高 | E0 | 拆分部署（§16.7） | Phase 0 |
| K9 | COM 调用被模态弹窗或许可证提示挂起 | 中 | 中 | E11 | 窗口可见、软超时；必要时做进程隔离（P1） | Phase 0、4 |
| K10 | HYSYS 会话不稳定、残留进程 | 中 | 中 | E11、运行中 | PREFLIGHT 检查、按进程号重启、任务锁 | Phase 1、4 |
| K11 | 时间超支、过度设计 | 高 | 高 | 进度跟踪 | 薄切片优先、裁剪顺序（§2）、Harness 规模上限（§7.6） | 全程 |
| K12 | 额外场景超出支持范围 | 中 | 中 | 无法预先发现 | 选型覆盖 5 类；不支持时明确返回并给出选型结论；P1 做 CSTR 和 PFR | Phase 3 |
| K13 | Demo 时 LLM 输出波动 | 中 | 高 | 重复一致性评测 | 温度 0；冻结规格回放作为兜底；Demo 前预跑 | Phase 2、5 |
| K14 | 报告数字被 LLM 改写或编造 | 低 | 高 | 数字回查 | 数字由代码渲染 | Phase 2 |
| K15 | V15 的 ProgID、类型名与旧版公开资料不同 | 中 | 低 | E1、E3 | 反向探测 | Phase 0 |
| K16 | 组分库名称与别名表不一致 | 中 | 中。额外场景最容易在这里失败 | E4、留出场景 | 别名表以实测为准；未命中时按分子式和名称在候选中确定（P1）；失败时错误清晰 | Phase 1、3 |
| K17 | 探索过程只有主路线，没有对照证据 | 中 | 中 | 报告评审 | E13 备选路线对照；探索日志 | Phase 0 |
| K18 | 时间盒按上限用满，交付物被挤到最后 | 中 | 高 | 进度跟踪 | 三场景端到端后立即出第一版交付物（M1）；最终交付预留 2.5 小时不挪用 | 全程 |

---

## 19. 工程任务拆解

估时是时间盒的上限。3 天按 30 个工作小时计。

| 任务 | 内容 | 依赖 | 产出 | 估时 |
|---|---|---|---|---|
| **Phase 0** | **探索与可行性（VM）** | | | **约 10.5 小时** |
| T0.1 | 建 GitHub 仓库，提交需求文档和本文，写 `CLAUDE.md` 和 `progress.md`；AI 编程助手在 VM 上就位 | 无 | 首次提交 | 0.5 h |
| T0.2 | E0–E3：环境、连接、读写、类型库导出、反向探测 | T0.1 | `spikes/e0`–`e3`、参考 Case | 2 h |
| T0.3 | E4–E7：Basis、物流、反应、转化反应器全链路 | T0.2 | `spikes/e4`–`e7`，闸门 G0 | 4 h |
| T0.4 | E8–E12：平衡、Gibbs、固体碳、鲁棒性、保存 | T0.3 | `spikes/e8`–`e12` | 3 h |
| T0.5 | E13：备选路线对照 | T0.3 | 对照结论和证据 | 1 h |
| T0.6 | 填写接口事实台账和探索日志，确定各能力的集成级别，修订 §9 的工具契约 | T0.2–T0.5 | `docs/HYSYS_INTEGRATION.md` | 随做随写 |
| **Phase 1** | **建模内核（不含 LLM）** | | | **约 6.5 小时** |
| T1.1 | `SimBackend` 接口和 `HysysComBackend`，把探针代码收敛为工具操作 | G0 | `backends/` | 2 h |
| T1.2 | Tool 注册表和结果信封（校验、幂等、错误映射、Trace 钩子） | T1.1 | `tools/` | 1 h |
| T1.3 | `ModelSpec` Schema，三个场景的手写黄金规格 | 无 | `spec/model_spec.py`、`evals/golden_specs/` | 1 h |
| T1.4 | 三个 Recipe（规则、编译、验证项） | T1.2、T1.3 | `recipes/` | 1 h |
| T1.5 | 最小执行器：状态循环、状态落盘、Trace、回路上限、R0 / R2 / R5 | T1.4、T1.6 | `harness/`、`state/`、`observability/` | 1 h |
| T1.6 | 结果验证 V1–V8 和 `NormalizedResult`（纯函数，只依赖规格和快照，先于执行器完成） | T1.3 | `validation/` | 0.5 h |
| **Phase 2** | **理解层和端到端** | | | **约 5 小时** |
| T2.1 | `TaskSpec` Schema、规范化（单位表、组分别名表）、业务规则 | T1.3 | `spec/` | 1.5 h |
| T2.2 | `LLMClient`，结构化输出，可更换供应商 | 无 | `llm/` | 0.5 h |
| T2.3 | `reactor-selection` Skill、选型规则校验、SELECT | T2.2 | `skills/reactor-selection/` | 1 h |
| T2.4 | `reactor-modeling` Skill（三份参考文件）、SPECIFY、重述回路 | T2.1、T2.3 | `skills/reactor-modeling/` | 1 h |
| T2.5 | L1 评测集和运行器（`--dry-run`） | T2.4 | `evals/` | 0.5 h |
| T2.6 | 接通端到端：三个场景从原文到报告 | T1.6、T2.4 | `report/`、`result-reporting` | 0.5 h |
| **M1** | **第一版交付物** | | | **约 1.5 小时** |
| TM.1 | 三个场景的第一版录屏、README 初稿、报告初稿、AI 会话导出 | G2 | 可提交的最小交付 | 1.5 h |
| **Phase 3** | **泛化** | | | |
| T3.1 | 留出场景 HO-1 至 HO-4 端到端，修复暴露的问题（P0） | M1 | 留出用例 | 1.5 h |
| T3.2 | Keq 的其他来源；转化率、选择性、收率的换算 | T3.1 | Recipe 和参考文件更新 | 1 h |
| T3.3 | 追问式修改重跑 | T3.1 | `revise` 命令 | 1 h |
| T3.4 | CSTR 和 PFR（动力学反应） | T3.1 | 新 Recipe 和参考文件 | 2–3 h |
| T3.5 | 组分解析增强；Conversion 的平衡可行性校验 | T3.1 | | 1 h |
| **Phase 4** | **加固** | | | |
| T4.1 | R1 自动重启、中间快照和 `resume` | M1 | `harness/recovery.py` | 1.5 h |
| T4.2 | `FakeBackend` 和 L2 测试矩阵 | T4.1 | `backends/fake.py`、`tests/harness/` | 1.5 h |
| T4.3 | `SpecPatch` 修复回路、正则证据、数字回查 | T4.1 | | 1.5 h |
| **Phase 5** | **最终交付（预留，不挪用）** | | | **约 2.5 小时** |
| T5.1 | E2E 三场景连续 3 轮和留出场景复测，生成评测结果 | Phase 3 | `docs/EVAL_RESULTS.md` | 0.5 h |
| T5.2 | 正式录屏、README 和报告定稿、Demo 排练（含一个留出场景和一次追问修改） | T5.1 | 交付物 | 2 h |

时间账：按上表的任务估时，Phase 0 到 M1 合计 23.5 小时。实际执行时按 `docs/prompts/` 分成多个会话：Phase 0 三个（0A、0B、0C），Phase 1 三个（1A 做 T1.1 和 T1.2，1B 做 T1.3、T1.4、T1.6，1C 做 T1.5 和闸门 G1），Phase 2 和 M1 三个（2A、2B、2C）。每个会话都有读入上下文的开销，所以到 M1 的时间盒合计是 25.5 小时。再加留出场景 1.5 小时和 Phase 5 预留的 2.5 小时，P0 共 29.5 小时。剩下约半小时是机动时间，从 T3.2 起按顺序消耗，有剩余再做 Phase 4。时间盒是上限而不是估计：每份提示词写明了时间不够时先保什么、可以推后什么。Phase 0 如果比时间盒快，省下的时间全部进入机动。

---

## 20. 实施顺序

排序依据是风险、依赖和价值，不是日历。价值按需求文档的评分和交付要求衡量。

| 顺序 | 工作 | 风险 | 依赖 | 排在这里的理由 |
|---|---|---|---|---|
| 1 | Phase 0：探索与可行性 | 最高。项目里唯一不可约的未知 | 无 | 需求文档把探索实现路径列为最重要的考核要素。工具粒度、规格字段和集成级别都取决于它 |
| 2 | Phase 1：冻结规格 → HYSYS → 验证过的结果 | 中 | Phase 0 | 直接对应 50% 的完成度。到这一步系统已经是一个可演示的"规格驱动建模器" |
| 3 | Phase 2：理解层和端到端 | 中。选型是评分关键 | Schema 与 HYSYS 无关，可以提前 | 三个场景的闭环成立 |
| 4 | M1：第一版交付物 | 低 | Phase 2 | 四项交付物是硬性要求。先拿到可提交的版本，之后的工作都是在它之上改进 |
| 5 | Phase 3：泛化 | 中 | M1 | 考核时可能给出额外场景，Live Demo 要现场回答问题 |
| 6 | Phase 4：加固 | 低。工程上确定性高 | M1 | 把"能跑"变成"可靠"。不在评分项里，所以排在泛化之后 |
| 7 | Phase 5：最终交付 | 低 | 全部 | 正式录屏、定稿、排练。时间预留，不被前面的阶段挤占 |

两条并行轨道：

- **轨道 A（VM）**：Phase 0 → Phase 1。
- **轨道 B（任何机器）**：Schema、单位表和组分别名表、Skill 文本、L1 评测集。

轨道 B 可以在 G0 之前开始，但只限于与 HYSYS 无关的部分，并且不得挤占 Phase 0 的时间。它适合交给 AI 编程助手并行推进。

每个阶段结束时系统都应处于可演示的状态。Phase 1 结束时能从规格文件建模，Phase 2 结束时能从自然语言建模，M1 之后的任何时刻都有一套可提交的交付物。

---

## 21. 各阶段验收标准

### 21.1 闸门

| 闸门 | 通过标准 |
|---|---|
| G0（Phase 0 中途） | E7 通过：代码从空白 Case 建出转化反应器并求解，读回结果与解析解一致，全过程没有手工操作 |
| Phase 0 结束 | E8–E13 有明确结论（通过，或已确定集成级别）；台账中 H1–H26 的状态全部更新，没有"未测试"残留；探索日志记录了主路线和至少两条备选路线的结论 |
| G1（Phase 1 结束） | 三个场景的黄金规格各自从空白 Case 确定性建模，通过 V1–V8；连续 3 次结果一致，没有重复对象；`.hsc` 能在 GUI 中打开查看；每次运行留下 `state.json` 和 `trace.jsonl` |
| G2（Phase 2 结束） | L1 门槛达标（§15.6）；三个场景的原文各自端到端产出报告并通过致命检查 |
| M1 | 第一版录屏覆盖三个场景；README 能让他人在 VM 上复现；报告初稿写完技术选型、系统架构、探索过程、问题与解决四部分 |
| G3（Phase 3） | 必达：留出场景 HO-1 至 HO-3 通过致命检查，HO-4 选型正确，且没有改动 `harness/`。其余各项做到哪一项，哪一项要有对应的用例通过 |
| G4（Phase 4，可选） | L2 测试矩阵通过；在构建和求解中途终止进程后 `resume` 成功 |
| G5（Phase 5 结束） | E2E 三场景连续 3 轮 9 / 9；正式录屏、README、报告、AI 开发记录齐备；Demo 排练完成 |

### 21.2 最终交付标准

| 类别 | 标准 | 验证方式 |
|---|---|---|
| 功能 | 自然语言 → 参数解析 → 反应器判断 → HYSYS 建模 → 计算 → 结果 → 用户 | E2E 三场景和留出场景 |
| 鲁棒性 | 错误输入可识别 | L1-X1 至 L1-X5 |
| 鲁棒性 | 工具失败可恢复 | P0：在真实 HYSYS 上复现两类故障各一次。同名对象冲突，验证干净重建；中途结束 HYSYS 进程，验证带诊断中止和用冻结规格重跑。P1：L2 故障注入 |
| 鲁棒性 | HYSYS 异常可处理 | 同上 |
| 鲁棒性 | Agent 的错误决策可约束 | 规格校验和选型规则校验；L1 对抗样本 |
| 鲁棒性 | 重复调用可控 | L3 连续 3 次无重复对象。P1：L2 幂等测试 |
| 鲁棒性 | 任务中断可恢复 | P0：用冻结规格从头重跑，不重新询问 LLM。P1：`resume` 和 L2 续跑测试 |
| 复用性 | 新增场景不修改 Harness | 留出场景端到端通过，且 `harness/` 没有改动 |
| 可维护性 | 分层清晰 | §23.3 的依赖方向检查 |
| 可扩展性 | 新增反应器、反应、Skill、Tool、LLM、后端不重写核心 | §23.1 的变更清单。P1 的 CSTR 和 PFR 是一次实测 |

---

## 22. 最终目录结构与文档管理

### 22.1 目录结构

```
reactor-agent/
├── CLAUDE.md                          # AI 编程助手的工作约定
├── README.md
├── pyproject.toml
├── config/
│   ├── settings.yaml                  # LLM 供应商和模型、预算、超时、路径
│   ├── components.yaml                # 规范名、别名（中文、英文、分子式）、分子式、分子量
│   └── units.yaml                     # 单位换算表
├── src/reactor_agent/
│   ├── cli.py                         # run / revise / resume / trace / eval，支持 --dry-run 和 --spec
│   ├── harness/                       # engine.py, recovery.py, context.py, budgets.py
│   ├── llm/                           # client.py（接口）, providers/, prompts/system.md
│   ├── errors.py                      # 错误码和领域异常
│   ├── skill_loader.py                # 扫描、路由、加载 skills/
│   ├── spec/                          # 全部跨模块的数据模型和纯函数：tool_args.py, tool_results.py, snapshot.py,
│   │                                  # model_spec.py, components.py, plan.py, results.py, selection.py, task_spec.py, normalize.py, rules.py
│   ├── recipes/                       # base.py, conversion.py, equilibrium.py, gibbs.py
│   ├── tools/                         # registry.py, definitions.py
│   ├── backends/                      # base.py（SimBackend）, hysys_com/（按关注点分成几个文件）, fake.py（P1）
│   ├── validation/                    # checks.py, metrics.py, normalized.py
│   ├── state/                         # models.py, store.py
│   ├── observability/                 # trace.py, render.py
│   └── report/                        # render.py, templates/
├── skills/                            # 运行时 Skill
│   ├── reactor-selection/
│   ├── reactor-modeling/
│   ├── result-reporting/
│   └── hysys-troubleshooting/
├── .claude/skills/hysys-com-probing/  # 开发时 Skill
├── evals/
│   ├── cases/                         # L1 和 E2E 用例
│   ├── golden_specs/                  # 三个场景的冻结 ModelSpec（L3）
│   ├── oracle/                        # 独立参照值的计算脚本
│   └── run_evals.py
├── tests/                             # test_code_health.py（依赖方向和规模）, unit/, harness/（FakeBackend，P1）, integration/（需要 HYSYS）
├── spikes/                            # Phase 0 探针脚本，保留作为探索证据
├── runs/                              # 运行产物，不入库
└── docs/
    ├── MASTER_PLAN.md
    ├── HYSYS_INTEGRATION.md
    ├── progress.md
    ├── REPORT.md
    ├── ai_sessions/                   # AI 开发记录导出
    ├── TOOLS.md                       # 自动生成
    └── EVAL_RESULTS.md                # 自动生成
```

与设计要求中参考结构的差异：没有 `agent/`（LLM 决策者没有独立的循环，归入 `llm/` 和 `harness/`）；没有 `workflows/`（状态机在 `harness/`，随反应器类型变化的部分在 `recipes/`）；`hysys/` 改为 `backends/`（为替换后端留出接口）；`models/` 拆成 `spec/` 和 `state/models.py`（两类模型的变化原因不同）。

规模预算：全系统约 3000 行代码（不含空行、注释和 docstring）。其中 Harness 不超过 600，由 `tests/test_code_health.py` 检查；其余是参考值：Backend 约 500，规格层约 700（全部数据模型都在这里），Recipes 约 300，验证层约 300，Tools 约 200，其余约 400。单个文件不超过 300 行，单个函数不超过 40 行，同样由测试检查。

### 22.2 文档管理

| 文档 | 处理 | 理由 |
|---|---|---|
| `MASTER_PLAN.md` | 保留，手工维护 | 架构基线 |
| `HYSYS_INTEGRATION.md` | 保留，Phase 0 起持续更新 | 接口事实台账和探索日志（主路线与备选路线的对照结论）。是 Backend 的唯一依据，也是报告中"探索过程"的素材 |
| `progress.md` | 保留 | 任务看板加上决策和问题日志。每次 AI 会话开始时读、结束时写，充当会话间的记忆，同时是报告的素材 |
| `CLAUDE.md` | 保留，放在仓库根目录 | 约束 AI 编程助手的行为 |
| `README.md`、`REPORT.md` | 保留 | 交付物 |
| `TOOLS.md` | 由工具注册表自动生成 | 手写会与代码漂移 |
| `EVAL_RESULTS.md` | 由评测运行器自动生成 | 同上 |
| `ARCHITECTURE.md`、`HARNESS.md`、`SKILLS.md`、`STATE_MODEL.md` | 暂不单列 | 内容就是本文 §6–§13。Skill 由各自的 `SKILL.md` 自描述，状态模型以 pydantic 定义为准。本文某一节膨胀到影响阅读时再拆 |
| `TEST_PLAN.md`、`EVALUATION.md` | 暂不单列 | 内容是本文 §15，用例本身在 `evals/` 和 `tests/` |

手写维护的文档共 4 份，自动生成 2 份，交付物 2 份。

### 22.3 CLAUDE.md 要点

1. 需求文档和本文是最高依据。要改架构，先改本文。
2. 没有进入 `HYSYS_INTEGRATION.md` 台账的 COM 接口不得使用。不确定的接口先写探针。
3. COM 对象不得出现在 `backends/` 之外。
4. LLM 不得获得任何能写 HYSYS 的工具。
5. 运行时代码中不得出现场景名，不得为特定场景写分支。
6. 每个任务结束时更新 `progress.md`，小步提交。
7. 改了 Skill 或提示词必须跑 L1 评测，改了 Harness 必须跑 L2。
8. 不新增本文目录结构之外的顶层模块。确有需要时先在本文写明理由。
9. 探针由助手在 VM 上直接执行。每个探针的目的、做法、结果、结论写进探索日志，走不通的路线同样记录。

---

## 23. 复用、扩展与可维护性

### 23.1 变更影响表

| 新增 | 需要改动 | 不需要改动 |
|---|---|---|
| 同类型反应器的新场景（新反应、新组分、新条件） | 没有代码改动。必要时在 `components.yaml` 补别名，加一条评测用例 | 全部代码 |
| 新反应器类型（如 PFR、CSTR） | 一个 Recipe 文件；`reactor-modeling` 的一份参考文件；`ModelSpec` 中该类型的参数段；Backend 中 `ensure_reactor` 的对应分支；评测用例 | Harness、Tool 契约、其他 Recipe |
| 新反应类型（如动力学反应） | `ModelSpec` 的反应参数段；Backend 中 `ensure_reaction` 的对应分支；参考文件 | Harness |
| 新的 HYSYS 操作（如加热器） | 一个新 Tool 及其 Backend 方法；使用它的 Recipe | Harness、已有 Tool |
| 新仿真软件 | 一个新的 `SimBackend` 实现；组分别名表增加一列 | Harness、Tool 契约、Recipe、Skill 中与后端无关的部分 |
| 新 LLM | 一个 provider 文件；`settings.yaml` | 其余全部 |
| 新 Skill | 一个 Skill 目录；状态到 Skill 的路由配置 | Harness 代码 |
| 新评估指标 | `validation/metrics.py` 中的一个函数；用例中的期望字段 | 其余全部 |

已知边界：多单元流程（反应器前后加换热、分离、循环）超出当前 Recipe 模型，需要把 `ModelSpec` 从"单反应器"扩展为"单元列表加连接"。这不在需求内，不预先实现。

### 23.2 扩展机制

四个注册表（Recipe、Tool、Skill、LLM Provider）加一个接口（`SimBackend`）。核心代码里不出现针对反应器类型的 `if/else`，按类型的分支只存在于 Recipe 和 Backend 内部。

Recipe 的接口只有三个方法，新增一种反应器就是实现这三个方法。派生指标不在 Recipe 里：它由 `ModelSpec.metrics` 里有类型的请求驱动，统一在 `validation/metrics.py` 计算。

```python
class ReactorRecipe(Protocol):
    type: str                                                    # conversion / equilibrium / gibbs / ...
    def rules(self, spec: ModelSpec, components: ComponentTable) -> tuple[Issue, ...]: ...   # 专有规格规则
    def compile(self, spec: ModelSpec) -> BuildPlan: ...         # 规格 -> 有序、幂等的工具步骤
    def checks(self, spec: ModelSpec, case: OperatingCase, snap: ModelSnapshot) -> tuple[CheckResult, ...]: ...   # 专有的结果验证项
```

### 23.3 依赖方向

```
cli     -> everything (composition root)
harness -> { llm, skill_loader, recipes, tools, validation, state, observability, report, spec, errors }
tools   -> backends, spec, errors
backends, recipes, validation, state, observability, llm, skill_loader, report -> spec, errors
spec    -> errors
errors  -> (nothing)
```

规则只有四句：

1. `errors` 不依赖任何模块，`spec` 只依赖 `errors`。
2. `backends`、`tools`、`recipes`、`validation`、`state`、`observability`、`llm`、`skill_loader`、`report` 只依赖 `spec` 和 `errors`；`tools` 另外依赖 `backends`。
3. `harness` 可以依赖除 `backends` 和 `cli` 之外的所有模块。
4. `cli.py` 是唯一的装配点：它创建具体的 Backend、LLM 客户端、状态存储和 Trace，把它们传给执行器。它可以导入任何模块，其他模块都不导入它。

为了做到这一点，`spec` 是共享的纯数据层：规格、工具的入参和结果、快照、建模计划、检查结果、选型结论这些跨模块传递的数据模型都定义在这里，另外只放纯函数，以及把规格和配置文件读成模型的加载函数。这样 `recipes`、`tools`、`backends`、`validation`、`state` 之间不需要互相导入。

COM 库（`win32com`、`pythoncom`、`pywintypes`）只在 `backends/hysys_com/` 里导入。以上规则由 `tests/test_code_health.py` 检查，这个测试随仓库启动包提供。

八条解耦原则的落点：

| 原则 | 落点 |
|---|---|
| LLM 与 HYSYS 解耦 | LLM 只产出 `TaskSpec`，中间隔着校验、编译、Tool 三层 |
| Agent 与 HYSYS 解耦 | 同上，LLM 没有工具 |
| Skill 与 Tool 解耦 | Skill 是纯文本知识，不引用工具名 |
| Harness 与业务 Skill 解耦 | Harness 只知道"状态 → Skill 名"的路由配置 |
| Scenario 与核心引擎解耦 | 运行时没有场景概念，场景只存在于 `evals/` |
| 状态与上下文解耦 | 状态在 `state.json`，上下文每次由状态生成 |
| 规划与执行解耦 | LLM 写规格，Recipe 编译计划，执行器执行 |
| 验证与执行解耦 | `validation/` 只消费快照，不调用写工具 |

### 23.4 最终架构图

```
                         User text
                             |
                             v
+---------------------- Harness (deterministic state machine) ----------------------+
|  state store | budgets | tool permission gate | trace | recovery | skill routing  |
+-----+----------------------+-------------------------+----------------------------+
      | (1) structured output | (2) compile            | (3) execute step by step
      v                       v                         v
+-----------+  TaskSpec  +-----------------+ BuildPlan +----------------------+
|    LLM    | ---------> | Spec validation | --------> | Tools (idempotent,   |
| decision  |            | + Recipe        |           | contract, readback)  |
|   maker   |            | registry        |           +----------+-----------+
+-----^-----+            +-----------------+                      |
      | Skills (routed by state)                                  v
+-----------+                                          +----------------------+
|  Skills   |                                          | SimBackend           | --> HYSYS V15 (COM)
+-----------+                                          | (HysysCom / Fake)    |
                                                       +----------+-----------+
                                                                  |
                                                                  v
                                       snapshot -> result validation -> NormalizedResult
                                                                  |
                                                                  v
                           report: tables rendered by code + LLM interpretation -> User
```

与设计要求中参考图的主要区别：Skills 不在 Agent 之上而在其侧面（由 Harness 按状态注入）；Agent 的输出不是"调用工具的计划"而是"规格"，计划由 Recipe 编译；验证有三道门而不是一道。

---

## 24. 反向审查（20 问）

| 编号 | 问题 | 回答 |
|---|---|---|
| 1 | 有没有过度设计？ | 有这个风险。v0.1 的裁剪：没有多 Agent、框架、MCP、RAG、数据库、上下文压缩；LLM 没有工具；文档从 10 份减到 4 份手写。v0.2 的审核又把一批内容从主线移到 P1-加固：工具权限白名单、`FakeBackend` 和故障注入矩阵、中间快照和 `resume`、自动重启会话；`ensure` 不再做局部修补。Harness 600 行的规模上限是硬约束 |
| 2 | Agent 是否过多？ | 没有独立的 Agent。只有一个 LLM 决策者，3 个调用点 |
| 3 | Skill 是否真的有复用价值？ | `reactor-selection` 和 `result-reporting` 与 HYSYS 无关，可以直接复用。`reactor-modeling` 的价值主要在按类型渐进加载和独立的版本管理。`hysys-troubleshooting` 在 P0 的价值最低，时间紧时先只做一张错误码到中文说明的静态表 |
| 4 | Harness 是否真的解决了 Agent 的可靠性问题？ | §6.2 的 11 个问题都有结构性对策，不依赖提示词。P0 用真实运行验证，P1 用 L2 测试矩阵系统地验证 |
| 5 | Agent 能否绕过 Harness 直接操作 Tool？ | 不能。LLM 没有工具接口，工具只由执行器按编译好的计划调用 |
| 6 | LLM 能否绕过 Validation？ | 不能。LLM 的产物只有 `TaskSpec` 和文字。进入 HYSYS 的只有通过门 A 的 `ModelSpec`，报告里的数字不经过 LLM。残余风险是解读文字里出现错误的数字，由 P1 的数字回查处理 |
| 7 | HYSYS 是否与 Agent 强耦合？ | 否。两者之间隔着规格、Recipe、Tool、Backend 四层 |
| 8 | Tool 是否与 HYSYS API 强耦合？ | 契约不耦合，实现耦合，且只在 `hysys_com.py` 一个文件里。坦率地说，契约是按 HYSYS 的概念（Basis、流体包、反应集）抽象的，换到其他软件时部分字段需要映射 |
| 9 | 是否支持任务恢复？ | P0 支持用冻结规格从头重跑，不重新询问 LLM，构建只需几秒。从中间快照续跑属于 P1 |
| 10 | 是否支持幂等重试？ | 支持。写工具全部是 `ensure` 语义，以 HYSYS 现状为准 |
| 11 | 是否存在无限循环风险？ | 不存在。所有回路都有计数上限（P0）；迁移总数和总时长的全局上限属于 P1 |
| 12 | 能否观察完整的 Task Trace？ | 能。状态迁移、LLM 调用、Skill 加载、工具调用、验证、恢复都有事件 |
| 13 | 能否进行自动化评估？ | 能。L1 和 L2 不需要 HYSYS，可在任何机器上运行；L3 和 E2E 在 VM 上运行 |
| 14 | 新增 Scenario 是否需要修改核心逻辑？ | 同类型反应器不需要任何代码改动 |
| 15 | 新增 Reactor 是否需要修改核心 Harness？ | 不需要。改动在 Recipe、参考文件、规格的类型参数段和 Backend 分支 |
| 16 | 新增 Skill 是否需要修改 Agent？ | 不需要。加一个目录和一条路由配置 |
| 17 | HYSYS API 变化能否隔离？ | 能，隔离在 `hysys_com.py`。台账记录了每个接口的验证版本 |
| 18 | 是否存在单点故障？ | 存在三个：HYSYS 单实例会话、LLM API、VM 本身。对策分别是重启会话加干净重建、退避重试加冻结规格回放、Demo 前确认环境 |
| 19 | 哪个模块最脆弱？ | `HysysComBackend`，尤其是反应和反应器的配置部分，以及场景 3 的固体碳。它是唯一建立在未验证假设之上的模块 |
| 20 | 哪个问题最应该优先验证？ | HYSYS V15 能否通过 COM 从空白 Case 创建反应、反应集和反应器并求解（E6、E7） |

审查中对设计要求里的参考设计做出的三处修正：`create_*` 工具改为 `ensure_*`（幂等来自语义而不是防重逻辑）；8 个顺序检查点改为"步骤日志加边界快照"两级（构建只需几秒，干净重建比细粒度续建可靠）；验证类候选 Skill 移入代码（验证不能交给 LLM）。

v0.2 对照需求文档做的严格审核见 §27。

---

## 25. 待确认决策与假设登记

以下事项都有默认值，不阻塞 Phase 0。D2 和 D3 建议向出题方确认。

| 编号 | 事项 | 当前默认 | 影响范围 | 需要确定的时间 |
|---|---|---|---|---|
| D1 | LLM 供应商和模型；VM 能否直连 | 选一个结构化输出可靠的模型；接口同时支持 Anthropic 和 OpenAI 兼容端点 | 部署形态 | E0 |
| D2 | 场景 3 是否加入氧气 | 不加，按题面建模，在报告中说明 | 场景 3 的全部结果数值 | Phase 1 之前 |
| D3 | "80000 Nm³/h"的含义 | 进料的总摩尔流量 | 只影响流量和热负荷的绝对值。浆料浓度不变时，出口组成和 CO 收率不受影响 | Phase 1 之前 |
| D4 | 二甲苯异构体分配 | 对 : 间 : 邻 = 24 : 52 : 24 | 场景 2 的异构体分布 | Phase 1 |
| D5 | 压力是绝压还是表压 | 绝压 | 场景 1 的转化率相差约 1 个百分点；场景 2 无影响；场景 3 影响很小 | Phase 1 |
| D6 | 场景 1 的进料流量基准 | CH4 1000 kmol/h | 只影响绝对量 | Phase 1 |
| D7 | Demo 形态 | 命令行，HYSYS 窗口可见 | 录屏和 Live Demo | M1 之前 |
| D8 | 机动时间先做泛化还是先做加固 | 先泛化。额外场景和现场问答直接计分，续跑和故障注入不在需求文档的评分项里 | Phase 3、4 的顺序 | M1 之前 |

各场景的完整假设清单见 §17 的 A1、A2、A3 系列。运行时每一条假设都会出现在报告里。

---

## 26. 现在应该执行的第一件事

### 26.1 第一件事

**在 VM 上执行 Phase 0 的 E0–E7：用代码从空白 Case 建出一台转化反应器并求解，把读回的结果与场景 2 的解析解比对。**

具体动作：

1. 建 GitHub 仓库，提交需求文档和本文。Git 历史从这里开始。AI 编程助手直接在 VM 上运行。
2. E0：确认 Python、pywin32 可用，确认 VM 能调通 LLM。
3. 在 HYSYS 的 GUI 里手工建一个最小参考 Case，三种反应器各一台，保存。这 20 分钟的手工操作同时是后面所有 Recipe 的"标准答案"，也能让你先把三种反应器在 GUI 里的配置项过一遍。
4. E1–E3：连接、读写、类型库导出、对参考 Case 做反向探测。同时把 Help 文件解包，交给助手检索。
5. E4–E7：从空白 Case 编程重建转化反应器，结果与解析解比对。
6. 把每一条结论写进 `docs/HYSYS_INTEGRATION.md`，包括走不通的尝试。
7. G0 通过后做 E13：用一小时对照两条备选路线并留证。

### 26.2 为什么它比直接开发 Agent 更重要

1. **它是项目里唯一不可约的未知。** LLM 结构化输出、状态机、校验、Trace 都是有成熟做法的工程问题，做了就能成。HYSYS 能否被代码创建反应和反应器，本轮查到的官方公开文档没有给出答案。
2. **Agent 的设计依赖它的结论。** 工具的粒度、`ModelSpec` 的字段、是否需要种子 Case、场景 3 是否要用两段法，都要等探针结果。先写 Agent 就是在未验证的接口上堆代码。
3. **50% 的分数直接由它决定**，并且需求文档写明探索实现路径是最重要的考核要素。
4. **失败越早越便宜。** 如果需要降级到种子 Case 或局部 GUI 自动化，第一天发现还有时间调整，第三天发现就没有了。
5. **它的产出不会浪费。** 探针脚本收敛成 Backend，参考 Case 变成黄金用例，台账变成报告里的"探索过程"。

---

## 27. 审核记录（v0.1 → v0.2）

审核方法：逐条重读需求文档，把每一句话对应到本文的设计、优先级和验收标准上，检查有没有读错、漏掉或排错顺序；再反过来检查本文的每个组件能否在需求文档里找到存在的理由。

### 27.1 结论

架构选型（规格驱动的 Harness）、三个场景的反应器映射、确定性边界和三个场景的建模方案，复核后没有发现需要推翻的问题。发现的问题集中在三类：对"探索"这一最重要考核要素的落实不够；任务顺序和时间账没有保护交付物；对"额外场景"的准备停留在选型层面。另有若干内部不一致和可以简化的设计。

### 27.2 发现与修订

| 编号 | 严重度 | 发现 | 依据 | 修订 |
|---|---|---|---|---|
| F1 | 高 | v0.1 把 Phase 0 当成"验证一条已选路线的风险闸门"，没有安排对不同路线的对照，也没有规定探索日志 | 需求 §4"探索实现路径……是最重要的考核要素"；需求 §6"是否展示了独立探索不同方案的过程" | 新增 E13 备选路线对照和两条候选路线（§16.1、§16.4）；探索日志并入台账（§16.3、§22.2）；Phase 0 的验收增加对照结论（§21.1） |
| F2 | 高 | 录屏、README、报告排在最后一个阶段；30 小时的估时等于全部可用时间，却写了"留有余量" | 需求 §5 的四项交付物是硬性要求；需求 §7 时限 3 天 | 新增里程碑 M1：三场景端到端后立即出第一版交付物；最终交付预留 2.5 小时；给出时间账（§19–§21） |
| F3 | 高 | 对额外场景的准备只有 L1 层面的选型用例，没有在 HYSYS 中跑过任何留出体系 | 需求 §3"考核时可能给出额外场景" | 新增留出场景 HO-1 至 HO-4，端到端运行，列入 P0（§2、§15.7） |
| F4 | 中 | P1 把泛化能力和 Harness 加固混在一起，阶段安排上加固先于泛化 | 需求 §6 的完成度指标；需求 §5 的 Live Demo 要现场回答问题 | P1 分成泛化组和加固组，泛化在前；顺序列为待确认决策 D8（§2、§20、§25） |
| F5 | 中 | Equilibrium 只支持 Gibbs 自由能一种 Keq 来源；Conversion 只支持直接给定转化率 | 需求 §8.2：Equilibrium"需要提供 Ka 或 Gibbs 自由能"；Conversion 的条件是"转化率、收率或选择性" | 列为 P1-泛化的第一项；E8 增加固定 Keq 的探测（§1.4 的 T13 和 T14、§2、§16.4） |
| F6 | 中 | 选型规则表没有区分"必要输入是否齐备"和"优先级"两层；用户显式指定的类型不经可行性检查就采纳；与 LLM 不一致时，LLM 的意见被直接丢弃 | 需求 §8 末尾"没有固定的反应器的类型，只有合不合适" | 规则分成必要输入和优先级两层；显式指定的类型也要通过必要输入检查；不一致时仍以规则结论为准，但把 LLM 的推荐列为备选（§8.6） |
| F7 | 中 | 场景 1 的两个误判方向没有被识别：两个反应被当成"多反应体系"判成 Gibbs；"重整炉"被当成管式反应器判成 PFR | 需求 §1 的类型表；需求 §8.3 | 新增 T11、T12，列入风险 K5 和对抗样本（§1.4、§17.1、§18） |
| F8 | 中 | 组分名解析被评为低影响，而它是额外场景最容易失败的地方 | 需求 §3 | K16 调高；E4 增加组分库检索的探测；解析增强列入 P1-泛化（§16.2 的 H25、§18） |
| F9 | 中 | 内部不一致：§2 把续跑和故障注入列为 P1，§19 和 §21 却把它们放在主线并作为闸门；G2 只要求场景 2 端到端 | 本文自查 | Phase 1 就建带状态落盘和 Trace 的最小执行器；续跑、`FakeBackend`、故障注入移到 Phase 4；G2 改为三个场景端到端（§7.7、§19、§21） |
| F10 | 中 | 一批组件在 P0 没有实际作用：状态到工具组的权限白名单（主路径上只有执行器调用工具）、中间快照、自动重启会话、`ensure` 的局部修补 | 需求 §6"开发速度本身也是评价因素" | 保留设计，推迟实现；`ensure` 简化为"不存在则创建，一致则跳过，不一致则重建"（§7.7、§9.5、§10.5、§13.4） |
| F11 | 低 | 场景 1 的输出没有包含年处理量 | 场景 1"要求符合一个工厂一年正常的处理量" | 输出进料的小时流量和折算的年处理量（§17.1） |
| F12 | 低 | 场景 2 的平衡限制只是理由里的一句话 | 需求 §9.2"不是想转化多少就转化多少" | P1：在 HYSYS 中用 Gibbs 反应器算出平衡转化率并列报告（§17.2） |
| F13 | 低 | 没有覆盖"改一个条件再算"这类现场追问 | 需求 §5"现场演示系统运行并回答问题" | 新增追问式修改重跑，列入 P1-泛化（§2、§19） |
| F14 | 低 | 工具契约写得像定稿，但粒度取决于探针结论；气体体积单位用于浆料没有对应的规则；重复运行的一致性容差定得过严 | 本文自查 | 契约标为暂定（§9.2）；新增单位与相态规则（§9.4）；容差放宽到 1e-4（§15.6） |

### 27.3 复核后维持不变的判断

| 判断 | 复核依据 |
|---|---|
| 场景 1 用 Equilibrium | 两个反应都已列出，且都是可逆反应；需求 §9.1 说明主副反应均为可逆反应、受化学平衡控制；用户没有给 Ka，用 Gibbs 自由能来源，符合需求 §8.2 |
| 场景 2 用 Conversion | 用户显式指定转化率反应器并给出 50% 的转化率，声明不讨论动力学；必要输入齐备 |
| 场景 3 用 Gibbs | 需求 §9.3 称气化炉是典型黑箱；题面要求考虑没有列出的副反应；CO 收率是待求量，不是已知量 |
| 场景 3 不加氧气 | 题面的进料只有煤和水，加氧会改变题目。作为显式假设声明，并建议向出题方确认 |
| CO 收率的定义 | 题面提示"煤炭有多少转化成 CO"，即出口 CO 摩尔流量除以进料碳摩尔流量 |
| LLM 不调用工具 | 需求没有规定 Agent 的形态。给定规格后建模序列是确定的，这个设计让三个场景的结果可复现 |
| 第一件事是 HYSYS 探索 | 需求 §4 把探索实现路径列为最重要的考核要素 |

### 27.4 这次审核没有解决的问题

1. 这是一次文档审核。HYSYS 接口的证据状态没有变化，【已确认】仍是 0 项，§16 的所有调用形式仍是假设。
2. 场景 3 是否加氧气、"80000 Nm³/h"指什么、二甲苯异构体如何分配，从需求文本无法确定，只能靠显式假设和向出题方确认。
3. 各阶段的估时没有实测依据。Phase 0 的实际耗时出来之后，§19 的时间账要重算一次。

### 27.5 v0.2.1 修补清单

编写分阶段提示词（`docs/prompts/`）时，对照每个阶段要写的代码逐节核对本文，做了下面这些一致性修补。架构、优先级和三个场景的方案没有变。

| 位置 | 修补 | 原因 |
|---|---|---|
| §22.1、§23.3 | 依赖规则改写成四句白名单；全部跨模块的数据模型归入 `spec/`；`cli.py` 明确为装配点；新增 `errors.py` | 原来的写法没有说明 `state`、`observability` 能依赖谁，建模计划和检查结果这些类型没有归属 |
| §23.2、附录 A | Recipe 接口从四个方法减为三个，去掉 `metrics` | 指标由规格里的请求驱动，统一计算；Recipe 再算一遍是重复 |
| §9.5 | `ensure_*` 从不修改已有对象，规定值不同也算不一致；只有 `set_spec` 修改已有对象 | 原文"物流规定是例外"有两种读法，会让幂等和冲突的判断不确定 |
| §9.3 | 说明"重试"一列是参考值，重试只在 Harness 里按错误码做；反应器的进料可以有多股 | 与 §13.2 统一；留出场景有两股进料 |
| §8.4、§15.3 | few-shot 示例和评测集换成不与留出场景重合的体系 | 原来三处都用了合成氨和甲烷燃烧，留出场景就不是"没见过的" |
| §8.6 | 必要输入只保留"没有它就建不了"的条件；优先级里把"黑箱类体系选 Gibbs"放到 Equilibrium 之前；动力学反应器缺设备尺寸时仍然选它并列为缺失信息 | 写出了反应式的燃烧、气化体系按原规则会被判成 Equilibrium，与需求 §8、§9.3 不符 |
| §12.3 | V1 只看求解状态，变量有没有值归 V5 | 两项检查原来有重叠 |
| §17.3 | 进料组成写成摩尔分率 | 规格里的组成统一用摩尔分率，换算由代码完成 |
| §7.6、§22.1 | 规模预算的口径改为代码行（不含空行、注释、docstring），文件和函数的上限由测试检查 | 代码规范要求中文 docstring 之后，按总行数计的预算会逼着把代码写挤 |
| §7.7、§10.4 | 任务锁移到 P1；`.hsc` 直接放在运行目录下 | 残留的锁文件在演示时是风险；文件便于查找 |
| §19、§0 | 时间账按会话划分重算：到 M1 是 25.5 小时，P0 共 29.5 小时 | Phase 1 分成 1A、1B、1C 三个会话 |
| §21.2 | P0 的故障复现改为：对象冲突验证干净重建，结束 HYSYS 进程验证带诊断中止 | 与 §13.4 的 P0 恢复范围一致 |
| §9.3、§23.2 | `ensure_reactor` 不带出口温度；Recipe 的规则多一个组分表入参，方法的返回值用 `tuple` | 出口温度是工况变量；Gibbs 的元素覆盖检查要用分子式 |
| §4、§12.4 | 解读文字是六块之外单独的一节；干基组成总是给出，不作为指标请求 | 报告层不能自己重算，数据要在结果里现成 |
| §16.2、§21.1 | 说明实测台账用五种状态 | 与台账的实际写法一致 |
| `pyproject.toml`、`tests/test_code_health.py` | 按实测调整了 lint 规则，体检测试增加了嵌套层数、文件编码、忽略注释、HYSYS 实现的导入范围等检查 | 写了一套示例代码实测：去掉会逼出别扭写法的规则，补上规范里写了但没有机器检查的条目 |

---

## 附录 A：术语

| 术语 | 含义 |
|---|---|
| TaskSpec | LLM 产出的结构化理解，保留用户原始单位和数值，逐项标注来源 |
| ModelSpec | 代码规范化并校验后的规格，冻结，带哈希 |
| BuildPlan | Recipe 从 `ModelSpec` 编译出的有序步骤 |
| Recipe | 每种反应器类型的确定性插件：规则、编译、验证项 |
| Tool | 带契约、幂等的确定性操作，与后端无关 |
| Backend | Tool 契约在某个仿真软件上的实现 |
| Skill | 给 LLM 的按需知识包 |
| 步骤读回 | 每次写操作之后立即读取并比对 |
| 干净重建 | 丢弃当前 Case，从空白 Case 幂等重放整个计划 |
| 冻结规格回放 | 跳过 LLM，直接用已保存的 `ModelSpec` 运行 |

## 附录 B：独立参照值的计算方法

- **场景 1**：理想气体，两个独立反应的平衡方程联立求解。平衡常数由 JANAF 表的标准生成 Gibbs 自由能按温度线性插值得到，另用关联式 K_SMR = exp(−26830/T + 30.114)（bar²）、K_WGS = exp(4400/T − 4.036) 交叉核对。
- **场景 2**：按计量关系直接计算。
- **场景 3**：理想气体加过量的纯固体碳（活度取 1）。三个独立平衡（C + H2O、C + CO2、C + 2 H2）加氢、氧元素守恒联立求解。热负荷由生成焓和显焓粗估。

计算脚本是 `evals/oracle/reference_estimates.py`，随本文一并提供，只依赖 numpy 和 scipy，是 V9 的参照来源。脚本中的热力学数据是手工录入的 JANAF 表值，纳入评测前请与原表核对。

## 附录 C：参考资料

- Aspen HYSYS Customization Guide，公开镜像，V7.3 版：<https://vdoc.pub/documents/aspen-hysys-customization-guide-29tdc3mctk60>、<https://ia801808.us.archive.org/25/items/manualzz-id-1157209/1157209.pdf>
- How to Connect Aspen HYSYS to Python：<https://medium.com/@toliati.hamid/how-to-connect-aspen-hysys-to-python-6f788e64515e>
- CAChemE/stochastic-optimization 中的 `hyInterface.py`：<https://github.com/CAChemE/stochastic-optimization/blob/master/ConventionalDistillationColumn/hyInterface.py>
- Use of Automation to Link Aspen HYSYS with Third-Party Software（综述）：<https://austinpublishinggroup.com/chemical-engineering/fulltext/ace-v10-id1105.pdf>

