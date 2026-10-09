# 进度与交接

每完成一个任务就更新这份文件并提交。它是跨会话的唯一记忆：新会话靠它知道做到了哪里，对话被压缩后也靠它找回方向。

## 当前状态

- **阶段 0B：已完成**（2026-10-08 12:30 开始，19:25 结束，UTC+8；与 0A 的会话 3 是同一个会话，中间因用量额度中断约 6 小时，实际工作约 1 小时）。**闸门 G0 通过**：`spikes/e7_conversion_chain.py` 从空白 Case 用代码建出四产物分数系数的甲苯歧化转化反应器，连续两次运行出料摩尔分率与解析解偏差 0.00000、质量守恒误差 1.52e-05、出口温度 378.59 °C、两次运行摩尔流量相对偏差 0。**每一步都是第 1 级集成方式（COM 编程）**，没有降级。**分数计量系数可用**，一个转化反应即可。任务 5：同一基准组分的多个转化反应**默认并行**（12/26/12% 三个反应，出口甲苯 0.5000）；反应集排序（Conversion Rankings）COM 成员、XML 写回、BackDoor 都写不了，**0C 发现 `PlayScript` 可以写**（排序 (0,1,2) 出口甲苯 0.5731、(1,1,0) 为 0.5456，与预测一致，H24、H32）；含义：排序值最小的先算、相同的并行、后面的对剩下的基准组分算；按 D13 Recipe 不设排序。台账 H1 至 H26 里 0B 要求的 14 项都有实测证据，"调用序列 → 转化反应器"小节已写成 Backend 的蓝本。
- **阶段 0C：已完成**（E0 的最后一步 2026-10-09 补做，通过，见台账 L35；2026-10-08 19:26 开始，20:42 结束，UTC+8；与 0A、0B 是同一个会话）。完成标准六条：①`e8` 两个工况在容差内（710 °C 偏差 0.0046、600 °C 偏差 0.0014），`e9` 通过（Gibbs 与平衡反应器偏差 1e-5，多股进料、绝热两个小试验通过），**`e10` 不满足通过条件**：Gibbs 反应器 + 库里的固体碳算出的结果是错的（碳的 Gibbs 函数是气态碳原子的，E10b、E10c），证据已交给用户决定（D14）；两段式（计划 §17.3）的可行性我试了，四条通过条件全满足（E10d），没有采用；②固体碳五个问题的答案在台账 Gibbs 反应器小节；③H1 至 H26 没有“未测试”；④路线对照表有四条路线的对照，每条有证据，LLM 视觉操作如实写未试验（没有桌面屏幕工具）；⑤台账有三种反应器的调用序列、十一个组分规范名、鲁棒性观察和“对工具契约的影响”（R1 至 R12，登记为 D15）；⑥本文件已更新并提交。**另外：`PlayScript` 是个能用的第二级通道**，能写 COM 写不了的内部变量（反应集排序已验证）和建对象；用户答复 D12 批准后台线程、D13 保持默认排序。
- **阶段 1A：已完成**（2026-10-08 21:10 开始，2026-10-09 00:30 结束，UTC+8；新会话，中间因用量额度中断约 1 小时 55 分，实际工作约 1 小时 25 分）。开始时用户答复了 D14（采用方案 A 两段式）和 D15（R1 至 R12 全部按建议）。**完成标准五条：**①`ruff format --check`、`ruff check`、`mypy src`（29 个源文件）、`pytest`（230 passed，含 `tests/test_code_health.py` 的 13 个）全部通过；②`pytest -m hysys tests/integration`：39 passed（约 73 秒），三个模型都只通过 `ToolExecutor` 建成：转化反应器与解析解偏差 0.00000，平衡反应器 710 °C、600 °C 与参照值最大偏差 0.0046、0.0014，两段式气化 CO 收率 39.96%；另有纯气相 Gibbs 反应器、固定 K 两个测试；幂等、冲突、哨兵数的断言通过；③`src/` 里除 `backends/hysys_com/` 之外没有 COM 相关代码和 `Any`，`test_hysys_backend_isolation.py` 检查 `com_error` 的名字、单位字符串、哨兵数各只出现在一个文件里；④交接报告里有体检输出和独立审查的处理结果；⑤本文件已更新，改动分多次提交并推送。**两个意外：**HYSYS 自己偶发崩溃（访问冲突，集成测试 9 次完整运行里 1 次，台账 L33）；写 `Basis` 会静默重置平衡反应的反应相（读回比对发现，台账 L34）。`src/` 共 1971 行代码，见 D17。
- **阶段 1C：已完成，闸门 G1 通过**（2026-10-09 18:35 开始，20:55 主体结束，21:50 处理完用户的答复后收尾，UTC+8；新会话，时间盒 2 小时，超出约 20 分钟：其中约 1 小时 20 分花在排查旧集成测试的间歇性失败上，见台账 L38）。开始时用户的指示里写“progress.md 当前写明下一步是 phase-0a.md、目录中没有 Git 仓库和台账”，与实际不符（0A 至 1B 都已完成并推送，台账和仓库都在），但最后一句写明“目前进行到 1C（未做）”，所以按进度文件做 1C。远端地址与 `origin` 一致，不需要重新配置。**闸门 G1 的八条：**①`ruff format --check`、`ruff check`、`mypy src`（59 个源文件）、`pytest`（837 passed，含 `tests/test_code_health.py`；D20 之后 839）全部通过；②`pytest -m hysys tests/integration`：54 passed（约 170 秒，连跑 3 次都通过；D20 加了两个测试之后 56 passed，又连跑 3 次都通过）——三份规格各自完成，V1 至 V8 全部通过，结果在容差内；每份规格连续运行 3 次，出料摩尔分率和摩尔流量相对偏差不超过 1e-4；每次运行后 Case 里的物流、能流、反应、反应集、反应器的名字与计划完全一致；重新打开每个工况另存的 `.hsc`，已求解且出口温度是该工况的；干净重建的测试里 Trace 恰好一条恢复事件（`E_CONFLICT`，重建），Case 文件名与之前不同，终态完成；第二个工况求解失败时，第一个工况的 `.hsc` 没被覆盖，现场另存在 `work/failed.hsc`；③每次运行的目录里有 `state.json`、`trace.jsonl`、`artifacts/` 下三个文件、每个工况一份 `.hsc`（另有 `work/`）；④`reactor-agent trace <task_id>` 打印出时间线；⑤用户在 HYSYS 界面里打开了生成的 `.hsc`（给的是 `runs/20261009-125257-f1/` 下平衡反应器的两个工况文件），答复“第五条通过”（我没有记下他看的是哪一个文件和哪些数）；⑥`harness/` 352 行代码（目标约 400）；⑦交接报告里有体检输出和独立审查的处理结果；⑧本文件已更新，改动分多次提交并推送。**三个意外：**旧的集成测试（1A、1B 的）在加入执行器的集成测试之后间歇性失败，根因没有查明，对策是每个测试文件用一个新的 HYSYS 实例（台账 L38，D20）；独立审查（子代理）指出 20 条，其中 7 条确定的缺陷都已修复（最重要的一条：中止时原地保存会覆盖上一个已验证工况的 `.hsc`）；会话失效的试验（E17）通过，不到 1 秒以 `FAILED` 结束并给出重跑命令，重跑通过（台账 L37）。`src/` 共 4630 行代码，超过 D17 约定的 4500 行触发点，见 D17。**用户 2026-10-09 晚的答复：“第五条通过，D20 重建一次，D17 继续”。**我的理解：第 5 条通过；D20 按我的建议，保持文件级夹具，并让 `E_NOT_SOLVED` 不重试、重建一次、再中止（已实现，提交 51a5c49，真实 HYSYS 上有两个测试）；D17 继续做，不在 2A 之前合并或删减，每个阶段结束报行数。
- **D1：已完成**（2026-10-09 10:08，UTC+8）。用户在自己的终端里运行 `./.venv/Scripts/python.exe spikes/e0_llm_connectivity.py --ask-key --tag run1 --capabilities` 并输入密钥（助手的进程读不到环境变量里的密钥，探针的 `--ask-key` 用 `getpass` 不回显，密钥只留在探针进程的内存里）。结果见 `spikes/out/e0_llm_connectivity_run1.txt` 和台账 L35：国内站 `https://dashscope.aliyuncs.com/compatible-mode/v1` 通；主模型 `qwen3.8-max`、快速模型 `qwen3.8-flash`、备用模型 `qwen3.7-plus` 都返回 200；主模型的 `response_format=json_object` 和 `tools` 函数调用通过。没有测的（`json_schema`、流式、关闭思考、限流、超时）留给 2A。
- **阶段 1B：已完成**（2026-10-09 09:20 开始，10:45 主体结束，18:30 补做 D18、D19 后收尾，UTC+8；与 1A 同一个会话）。用户 2026-10-09 的指示：“D17继续做；完成后继续测试 D1；如果 A1 的任务已经完成则开始做 A2；需要 APIKEY 就从环境变量读，读不到就给我一条命令我在终端里输入”。我的理解：D17 按默认继续；D1 的测试等用户运行 `--ask-key` 命令（已通过）；“A2”是按项目顺序的下一阶段 1B——2A 的“开始前先读”要读 `harness/engine.py`、`state/models.py`、`cli.py`，它们是 1C 才产生的，所以 2A 不能越过 1B、1C。阶段边界的约定（一个会话一个阶段）由用户的这条指示暂时放宽。**完成标准六条：**①`ruff format --check`、`ruff check`、`mypy src`（46 个源文件）、`pytest`（651 passed，含 `tests/test_code_health.py`）全部通过；另有 49 个 `-m hysys` 的集成测试（1A 的 39 个加 D19 新增的 10 个），D19 时运行，全部通过（94 秒）；②三份黄金规格加载、过 Recipe 的规则、编译，计划与计划 §17 的构建表一致（去掉头两步；场景 3 按 D14 是转化反应器加 Gibbs 反应器的两段式，14 步），并在 HYSYS 里原样执行；③V1 至 V8 每项有通过和失败的用例，“破坏 → 应当失败的检查集合”表 36 项逐项与预期一致，三份规格的真实快照全部通过（E16）；④转化率、收率（不乘计量系数）、比值和干基组成用手算值验证；⑤交接报告里有 `test_code_health.py` 的输出和独立审查（子代理）的处理结果；⑥本文件已更新，改动分 14 次提交并推送。**三个意外：**对三个场景的正确快照逐字段破坏（改 5% 或设为 None）来探查检查的漏洞，210 处没有任何检查发现，补上 V6 的物流内部一致性之后剩 101 处（都是有意不查的量，见“设计决定”第 16 条）；独立审查发现 V4、V2 的期望值取自计划而不是规格、结局判定不核对检查是否齐全，都已修复；用户同意后在 1B 里运行 HYSYS（D19，E16 探针和 10 个集成测试）：验证层在真实快照上没有误报，空相出料读回的是 0.0（台账 L36）。D18 按用户的答复修改了隔离测试的规则。`src/` 共 3716 行代码（见 D17）。
- 阶段 0A：**已完成**（主体 2026-10-08 10:55 结束，UTC+8；用户答复后补做 D11，12:00 结束）。首次开始于 2026-10-03 09:50，共 3 个会话（见"已完成"的时间表）。任务 1 至 3、5 至 11 都完成，完成标准的 6 条都有实际运行的验证。**任务 4（E0，LLM 连通性）挂起**，等用户给出供应商、模型和密钥所在的环境变量（D1）（2026-10-08 用户已给出；2026-10-09 用户运行探针，通过，见台账 L35）。**D11（参考 Case）已由助手用代码建成并补跑了 E3，不再等用户。**当前没有残留的 HYSYS 进程。
- **用户 2026-10-08 的答复（0A 交接之后）：D11 由助手自行创建参考 Case，建好后补跑 E3；D9 之后的提交署名改为 `xibei03 <jsl_03@163.com>`；"完成后续跑"。** 我的理解和假设：自行创建用 COM 代码做（没有别的手段），所以这部分工作等于提前做了 0B/0C 的一部分探针（E4 至 E9），台账里按探针记录；"完成后续跑"理解为做完这些之后补跑 E3，**不进入阶段 0B**（阶段边界不变，0B 仍在新会话里做，可以直接用这里的结论）。如果用户的意思是连续做 0B，请在回复里明说。（用户随后回复“继续 0B”，0B 在同一个会话里做了。）
- 最近通过的闸门：**G1（2026-10-09，阶段 1C）**，此前是 G0（2026-10-08，阶段 0B）；0C、1A、1B 没有闸门。1C 结束时质量工具全绿：`ruff format --check`、`ruff check`、`mypy src`（59 个源文件）、`pytest`（839 passed）、`pytest -m hysys tests/integration`（56 passed，约 180 秒）；`python tests/test_code_health.py` 输出 `src/` 4630 行代码，`harness` 352 行，最长函数 28 行，最深嵌套 3 层，没有忽略检查的注释。1A 结束时质量工具全绿：`ruff format --check`、`ruff check`、`mypy src`、`pytest`（230 passed）、`pytest -m hysys tests/integration`（39 passed）；`python tests/test_code_health.py` 输出 `src/` 1971 行代码（`backends` 1280、`spec` 548、`tools` 83、`errors` 60），最长函数 27 行，最深嵌套 3 层，没有忽略检查的注释。
- 最近一次更新：2026-10-09 21:50
- 时间记法：本机时钟是 UTC，进度文件里的时间一律换算成 UTC+8（加 8 小时）。
- 推送状态：本阶段每个任务的提交都已推送到 `origin/main`，没有强制推送；推送方式见"环境事实"的"GitHub 凭据"。

阶段顺序：0A → 0B → 0C → 1A → 1B → 1C → 2A → 2B → 2C → 3A → 3B（可选）→ 4（可选）→ 5。一个会话只做一个阶段。

## 环境事实

由阶段 0A 填写，之后发现变化时更新。

| 项 | 值 |
|---|---|
| 助手执行命令的机器 | 工作站 `myWin10VM`（Windows 10 Pro 19045，用户 `mywin10vm\azureuser`），时钟为 UTC |
| Python 版本与解释器路径 | 3.12.4，64 位，`C:\Program Files\Python312\python.exe`（`py.exe` 在 `C:\Windows\py.exe`）。PowerShell 里 `python` 直接可用 |
| 虚拟环境 | `C:\Users\azureuser\Desktop\ChemicalAgent\.venv`，解释器 `.venv\Scripts\python.exe`，已 `pip install -e ".[dev]"`（pywin32 312、ruff 0.16.10、mypy 2.4.0、pytest 9.1.1、pydantic 2.13.5）。运行脚本一律写 `.\.venv\Scripts\python.exe`，不依赖激活。**E13a 另装了 pywinauto 0.6.9（连带 comtypes 1.4.17、six 1.17.0），只在虚拟环境里，没有写进 `pyproject.toml`**，只有 `spikes/e13a_ui_automation.py` 用 |
| 输出编码的设置（如 `PYTHONUTF8`） | 实测：没有 `PYTHONUTF8` 和 `PYTHONIOENCODING` 时，输出被管道接走的 Python 进程用 cp1252，打印中文抛 `UnicodeEncodeError`；设 `PYTHONUTF8=1` 后正常。做法：`setx PYTHONUTF8 1`（用户级，对之后新启动的进程生效）。助手的会话进程由宿主预设了 `PYTHONIOENCODING=utf-8:surrogateescape`，所以不依赖 `setx`。探针脚本开头自己 `sys.stdout.reconfigure(encoding="utf-8")`，输出文件由脚本用 `encoding="utf-8"` 写 |
| HYSYS 版本与 ProgID | `Aspen HYSYS Version 15 (41.0)`（`app.Version` 实测）。通用 ProgID `HYSYS.Application`（= `.Latest`，CurVer 为 `HYSYS.Application.V15.0`），已有实例就复用；每次新开进程的是 `HYSYS.Application.NewInstance`（run3、run5 已验证）。进程名 `AspenHysys.exe`。早绑定用 `gencache.EnsureDispatch`，包装缓存在 `%TEMP%\gen_py\3.12`。详见台账"连接与绑定方式" |
| HYSYS 安装目录 | `C:\Program Files\AspenTech\Aspen HYSYS V15.0` |
| 反向探测用的参考 Case 的路径 | **`spikes/ref_cases/three_reactors.hsc`**（D11，助手用代码建的，178 KB，已提交）：PR 流体包 8 个组分，转化反应器 R-Conv、平衡反应器 R-Eq、Gibbs 反应器 R-Gibbs，全部求解；重建命令 `.venv\Scripts\python.exe spikes\build_reference_case.py`。另有自带示例 `C:\Program Files\AspenTech\Aspen HYSYS V15.0\Samples\Synthesis Gas Production.hsc`（2 台转化、3 台平衡反应器；先复制到临时目录再打开） |
| LLM 供应商、模型、密钥所在的环境变量名 | 用户 2026-10-08 答复（D1）：阿里云百炼 Qwen（OpenAI 兼容接口），主模型 `qwen3.8-max`、快速模型 `qwen3.8-flash`、备用模型 `qwen3.7-plus`，密钥环境变量 `DASHSCOPE_API_KEY`（用户在自己的终端会话里配置，助手的进程读不到）；连通性测试 2026-10-09 通过（`spikes/e0_llm_connectivity.py --ask-key`，台账 L35），国内站 `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 远程仓库地址 | `https://github.com/xibei03/ChemicalAgent.git`（2026-10-08 由用户给出，已配置为 `origin`，默认分支 `main`）。远端仓库是公开的，不登录也能 `fetch`，推送需要登录 |
| GitHub 凭据 | 2026-10-08 接手时这台机器上没有任何凭据；用户随后在应用的终端里运行 `gh auth login`，登录为 `xibei03`（令牌在 Windows 凭据库，协议 https）。`git` 的凭据助手仍然是系统级的 `manager`（GCM），没有运行 `gh auth setup-git`，所以推送时用一次性助手，不改任何持久配置：`git -c credential.helper= -c "credential.helper=!gh auth git-credential" push`。助手不代填、不收口令或令牌 |
| Git 署名 | 机器上没有配置全局 `user.name` 和 `user.email`。**2026-10-08 起仓库级配置是 `xibei03 <jsl_03@163.com>`（D9，用户指定）**；此前的提交（到 `07940e6`）署名是 `xibeibei63 <xibeibei63@gmail.com>`，已推送，不改写历史 |

## 已完成

每个阶段开始和结束时各记一行时间，阶段 5 用它整理开发时间线。

| 阶段 | 开始和结束的时间 | 会话数 |
|---|---|---|
| 0A | 2026-10-03 09:50 开始，2026-10-08 12:00 结束（UTC+8）。会话 1：10-03 09:50 至 09:58，在别的机器上停在任务 1；会话 2：10-03 10:25 至 10:50，E1 前两次运行，因用量上限中断；会话 3：10-08 09:50 至 10:55，之后用户答复 D9、D11，11:25 至 12:00 补做参考 Case。实际工作时间约 2 小时 20 分钟 | 3 |
| 0B | 2026-10-08 12:30 开始，19:25 结束（UTC+8）。12:30 至 12:58 做 G0 和任务 5 的前半，因用量额度用尽中断约 6 小时；18:55 起做任务 5 的排序、台账定稿和收尾。实际工作约 1 小时 | 0（接着 0A 的会话 3 做） |
| 0C | 2026-10-08 19:26 开始，20:42 结束（UTC+8）；与 0A、0B 同一个会话。实际工作约 76 分钟（含等待探针运行） | 0（接着 0A 的会话 3 做） |
| 1A | 2026-10-08 21:10 开始，2026-10-09 00:30 结束（UTC+8）。21:10 至 21:57 做契约、E14、Backend 和集成测试；因用量额度用尽中断约 1 小时 55 分；23:52 起处理台账、独立审查、E15 和审查修复。实际工作约 1 小时 25 分 | 1 |
| 1B | 2026-10-09 09:20 开始，10:45 主体结束，18:30 补做 D18、D19 后收尾（UTC+8）；与 1A 同一个会话，中间等用户运行 D1 的连通性命令、等子代理审查（约 21 分钟）、因用量额度用尽中断约 7 小时 40 分。实际工作约 2 小时 | 0（接着 1A 的会话做） |
| 1C | 2026-10-09 18:35 开始，20:55 结束（UTC+8）。18:35 至 19:40 做第一段（执行器，不需要 HYSYS）；19:40 至 20:05 第二段（真实 HYSYS 的集成测试、E17）；20:05 至 20:55 先后排查旧集成测试的间歇性失败（L38，约 1 小时 20 分，与审查同时进行）、处理 20 条审查意见、写文档。时间盒 2 小时，超出约 20 分钟 | 1（新会话）；子代理审查 1 次 |

| 阶段 | 任务 | 提交 | 验证方式 |
|---|---|---|---|
| 0A | 1 确认能执行 Windows 程序 | 无代码改动 | `python --version` 得 3.12.4；`platform.architecture()` 得 64bit、WindowsPE；`HKLM\SOFTWARE\AspenTech` 存在，`C:\Program Files\AspenTech\Aspen HYSYS V15.0` 存在 |
| 0A | 2 仓库和工具 | fbfc7bf | `ruff check .` 通过；`ruff format --check .` 3 个文件已格式化；`mypy src` 无问题；`pytest` 13 passed；`PYTHONUTF8` 的实测见"环境事实" |
| 0A | 3 建台账 | 029bbe7 | `docs/HYSYS_INTEGRATION.md` 有 10 个固定节名，接口事实表有 H1 至 H26 共 26 行，状态均为"未测试" |
| 0A | 5 连接 HYSYS（E1），run1 至 run9，已完成 | 2427c43（run1）、4904693（run2）、58c29f4（run3 至 run9、`_common.py`） | run1：`Dispatch("HYSYS.Application")` 冷启动 35.2 秒，`Version` 为 `Aspen HYSYS Version 15 (41.0)`，进程 `AspenHysys.exe`，窗口所属进程与 `tasklist` 一致。run2：已有实例被复用（0.0 秒），`Quit()` 后 3.5 秒内消失。run3、run5：`NewInstance` 每次新开进程，`Quit()` 只结束自己（run5 里 7280 退出，14024 继续运行）。run6：丢掉 COM 引用并 `CoUninitialize()` 后 60 秒内实例仍在。run7：`taskkill /PID /T /F` 1.6 秒内结束。run8、run9：`EnsureDispatch` 返回 `gen_py` 的 `_Application`，属性名区分大小写（`app.Name` 报错，类型库里是 `name`），包装生成后 `Dispatch` 也返回同一个类。H1 升为已确认，新增 H27、H28。每次运行后 `tasklist` 无残留进程 |
| 0A | 6 导出类型库（`typelib_dump.py`） | 6378949 | `.venv\Scripts\python.exe spikes/typelib_dump.py` 成功运行：类型库 1140 个类型（726 个 dispatch 接口、377 个枚举、22 个组件类）；42 个接口有 `Add`，多数是 `Add(name: VARIANT[opt], Type: VARIANT[opt])`；`EnsureModule` 2 至 4 秒生成包装（758 个类），`ReactionSets`、`Reactions`、`Operations`、`FluidPackages`、`SimulationCases` 的包装类都有 `Add`。输出 5 个文件，最大 629 KB，都小于 1 MB。三种反应器是 dispatch 接口 `ConversionReactor`、`EquilibriumReactor`、`GibbsReactor`；XML、`PlayScript`、`BackDoor` 三条降级通道在类型库里都有。结论都只在类型库层面，没有运行验证 |
| 0A | 7 找含反应器的参考 Case | 0b2cdba | `spikes/find_ref_case.py` 打开 6 个候选示例：Synthesis Gas Production 含 2 台转化反应器（`conversionreactorop`）和 3 台平衡反应器（`equilibriumreactorop`）；Ammonia Synthesis 含 3 台 PFR；CSTR - Dynamic Model 含 1 台 CSTR；Toluene_Disproportionation_Example 是分子级炼油反应器；Ethanol Dehydration、Ethanol Plant 没有反应器；Green Ammonia Process 弹出 Aspen Properties 模态对话框，`Open` 卡住，看门狗读出文字，`BM_CLICK` 关闭。**没有一个示例含 Gibbs 反应器**，需要用户手工建参考 Case（D11）。`Open` 返回类型化的 `_SimulationCase`，`Item(i)` 返回具体的反应器类型，不需要 `CastTo` |
| 0A | 8 读写已有 Case（E2、E2b） | 7609ad0 | `spikes/e2_read_write.py` 两次运行（run1、run2）：流体包 `Basis-1`、物性包 `PengRobinson`、7 个组分可读；物流 T、P、流量用 `GetValue(unit)`、`SetValue(value, unit)`，写后读回一致，不认识的单位抛错；写入同步重算（热负荷 6558.8 → 6544.7 kW）；`Solver.CanSolve=False` 时改进料流量，出料不变（475.36），`CanSolve=True` 这一句 0.46 秒同步求出新值（523.26）；没有规定的变量 `IsKnown` 为 False、值为 -32767.0；新物流 `MaterialStreams.Add("probe")` 成功并能写组成、闪蒸完成；8.3 短路径打开 Case 失败，长路径成功。`spikes/e2b_quit_with_case.py`：Case 打开着或改过时，`Quit()`、`Close()` 都不弹窗。H2、H6、H13、H17、H22 升为已确认 |
| 0A | 9 反向探测（E3），示例 Case | b4df369 | `spikes/e3_reverse_probe.py` 对 Synthesis Gas Production 的 5 台反应器（2 转化、3 平衡）、4 个反应、3 个反应集做只读探测：`Item(i)` 直接返回具体类型；反应 `TypeName` 为 `conversionrxn`、`equilibriumrxn`，反应集为 `rxnset`；出口温度规定在气相出料物流上（`State` 1、`CanModify` True），带能流的反应器热负荷是计算值；反应集成员是 `ActiveReactions`/`InactiveReactions`，与流体包的关联是出现在 `fp.ReactionPackage.ReactionSets` 里；转化率是百分数、同一基准组分的多个转化反应并行按进料算（Reformer 40%+30%，进料甲烷 90.72，反应掉 63.50 kgmole/h）；没连能流时 `op.EnergyStream` 抛 `com_error`。XML 导出 6.5 MB 但不含反应定义。**未解决：**`LnKSource` 读出 4 与类型库枚举对不上；Gibbs 反应器没有样本。H16、H26 部分确认，H18、H20 已确认 |
| 0A | 10 检索官方帮助 | 3a6e467 | `hh.exe -decompile` 解开 4 个 `.chm`（共 2882 个文件），只有 `xhysys.chm` 是 Automation 对象参考：`operation_types.htm` 列出 `Operations.Add` 的类型字符串（`ConversionReactorOp`、`EquilibriumReactorOp`、`GibbsReactorOp`），示例 `Flowsheet.Operations.Add "Pump1", "PumpOp"`；没有 `Reactions.Add`、`ReactionSets.Add` 的说明，枚举页没有界面选项名。台账 L9 |
| 0A | 11 台账收尾和完成标准核对 | 3a6e467 | 台账 10 个节名俱全；H1、H2、H6、H13、H17、H18、H22 都是已确认；三种反应器的类型名、反应、反应集、反应器的成员已记录；"创建反应的线索"按可能性排序；探索日志 L0 至 L9，每个探针都有一条。`python spikes/e1_connect.py` 原样运行，打印版本 `Aspen HYSYS Version 15 (41.0)` 和进程号。`python tests/test_code_health.py` 与四个质量工具见交接报告 |
| 0A | 4 LLM 连通性（E0） | 见下面“4（补）” | 当时挂起：用户说需要密钥的先跳过，等 D1；2026-10-09 补做完成 |
| 0A（D11） | E4 新建 Case 和 Basis（含 E4b 物性包） | 8a7ec7e | `spikes/e4_basis.py`、`e4b_property_package.py`：`SimulationCases.Add("name")` 新建空白 Case，新 Case 一开始就在 Basis 修改状态；`ComponentLists.Add` 加组分列表，`Components.Add(name)`（库名大小写不敏感，分子式不行）；`FluidPackages.Add` 加流体包，`fp.ComponentList = cl`，**`fp.PropertyPackageName = "pengrob"`（物性包内部名；界面名等 10 种写法都 E_INVALIDARG）**；`EndBasisChange()`、`SaveAs`、`Close`、`Open` 重开后 Basis 完好。固体碳 `Carbon` 在库里，`IsSolid` 为 True。H3、H4、H7、H8 已确认，H5、H21、H25 部分确认 |
| 0A（D11） | E6 创建反应和反应集（含 E6b Keq 来源） | f20af38 | `spikes/e6_reaction.py`、`e6b_keq_source.py`：**`Reactions.Add(name, "conversionrxn")` 第一次就成功**，返回类型化的 `ConversionReaction`（`equilibriumrxn`、`kineticrxn` 同理，界面名、整数、省略 `Type` 都 E_FAIL）；`Reactants.Add(组分名)` 加反应物，`StoichiometricCoefficientValue` 写系数（负为反应物），`BaseComponent`、`Conversion = 50.0`；分数系数 0.24 能写；`ReactionSets.Add(name)`、`ActiveReactions.Add(反应名)`、`AssociateFluidPackage(fp)`（挂上之后流体包才列出这个集合）；`EndBasisChange()` 之后也能直接建反应；另存重开后全部保留，系数被质量守恒微调 5e-5。**`LnKSource` 实际取值：1 Ln(K) 公式、2 Gibbs 自由能（默认）、3 固定 K、4 K–T 表，写 0 被忽略**（依据 `equirxn.rdf` 和实测）；固定 K 写 `EquilibriumConstant` 可用。H5、H9 已确认，H10、H11 部分确认 |
| 0A（D11） | 参考 Case 构建（E5 物流、E7 转化、E8 平衡、E9 Gibbs） | 本次提交 | `spikes/build_reference_case.py` 从空白 Case 一次建出并求解三种反应器，连续两次运行结果逐项相同：转化反应器出口摩尔分率甲苯 0.5000、苯 0.2500、对二甲苯 0.2500（偏差 < 1e-5）；平衡反应器 710 °C、600 °C 与独立参照值的摩尔分率最大偏差 0.0046、0.0014（容差 0.02），CH4 转化率 54.0%、30.3%，热负荷 +39989 kW、+20160 kW；Gibbs 反应器与平衡反应器最大偏差 1e-5；质量守恒误差 < 2e-5；流程图 14 个对象全是 OK。`Operations.Add(name, "ConversionReactorOp")` 等帮助文件的写法有效；出口温度规定在气相出料物流上。台账 H12、H14、H15、H16、H20 已确认，H19 部分确认，写出"调用序列"三个小节 |
| 0A（D11） | E9b Gibbs 反应器类型 | 本次提交 | `spikes/e9b_gibbs_type.py`：`ReactorType` 0 = NO Reactions (=Separator)，2 = Specify Equilibrium Reactions（要挂反应集），3 = Gibbs Reactions Only（默认）；1 写得进去但反应器未求解。界面选项原文来自 `Support\OdfRdfVariables.sdb`。台账 H31 |
| 0A（D11） | E3 补跑：参考 Case | 本次提交 | `spikes/e3_reverse_probe.py --case spikes/ref_cases/three_reactors.hsc --tag three`：三种反应器、3 个反应、2 个反应集的读法与示例一致；`LnKSource` 为 2（Gibbs 自由能）；Gibbs 的 `ReactorType` 为 3。0A 遗留的两个未解决项都已解决 |
| 0B | 2 新建物流（E5） | ff85892 | `spikes/e5_stream.py`：新物流所有量未知；T、P、组成写完闪蒸完成，再写质量流量，摩尔流量等随之已知；10000 kg/h 甲苯读回 108.5296 kgmole/h；组成写入被静默归一化，负流量不校验，-300 °C 被拒，同名 `Add` 返回已有物流 |
| 0B | 4 转化反应器全链路（E7，闸门 G0）及 E7b 未求解原因 | ff85892 | `spikes/e7_conversion_chain.py --repeat 2`：从空白 Case 一次建出四产物分数系数的甲苯歧化转化反应器并求解；出料摩尔分率 0.5000 / 0.2500 / 0.0600 / 0.1300 / 0.0600，与解析解偏差 0.00000（容差 0.001）；质量守恒误差 1.52e-05（容差 1e-4）；出口温度 378.59 °C（容差 ±10）；两次运行各组分摩尔流量相对偏差 0（容差 1e-4）；挂起求解器的做法结果相同。**G0 通过，全部用第一级（COM 编程）**。求解随写入同步完成；判断已求解：`IsSolving` 为 False，`GetFlowsheetStatus` 里只有 OK。`spikes/e7b_unsolved_reasons.py`：缺进料、出料、反应集都是反应器 `UnderSpecified`，要读反应器成员区分；反应集没加入流体包写入即报错；类型不匹配的反应集会弹模态对话框，用 `_common.dialog_guard` 处理 |
| 0B | 1、3 新建 Case 和 Basis（E4）、创建反应和反应集（E6） | 8a7ec7e、f20af38 | 0A 的 D11 里已经做完（用户指示助手自行创建参考 Case），0B 没有重做；G0 脚本用同一条链，换成 0B 的四产物版本重新跑通。见上面两条 0A（D11）记录 |
| 0B | 4（补）G0 终版再验证 | 5a45a89 | 给 `e7_conversion_chain.py` 加了"最后一次运行另存 Case"（`spikes/out/e7_conversion_chain_run3.hsc`，154 KB）；`--repeat 2 --tag run3` 两次通过，摩尔流量相对偏差 0。另存的 Case 重新打开：反应 `Tol-Disp`，基准组分甲苯，转化率 50，系数 -2 / 1 / 0.24 / 0.52 / 0.24，出料摩尔分率 0.5 / 0.25 / 0.06 / 0.13 / 0.06，流程图 4 个对象全是 OK，没有弹窗 |
| 0B | 5 并行的转化反应和排序（E6b、E6c） | 4845c3c、05ac2a5 | `spikes/e6b_parallel_reactions.py`：三个基准组分相同的转化反应（12/26/12%）放进同一个反应集，不设排序时出口甲苯 **0.5000**，默认并行；排序在操作 XML 的 `ReactionRanks` 里，默认全是 0；`flags=0` 的 `ApplyXMLForOperation` 返回 False 并弄坏 Case。`spikes/e6c_rank_channels.py`（run1 至 run4）：XML 的 12 种 `flags`、Case 级 `ApplyXML`、BackDoor（用进料温度校准 moniker 写法）、`ActiveReactions.Add` 的第二个参数，都不能写排序；示例 Case 的 Combustor 排序 (1,1,0)、指定转化率 35/65/100、实际 18.09/33.60/48.31%，说明排序值小的先算、相同的并行 |
| 0B | 台账定稿和完成标准核对 | bdf9abe（进度文件在其后一次提交） | 台账：转化反应器调用序列换成 G0 版本（9 步表、结果表、分数系数、并行与排序），H24 改为不可行、H26 补导入结果、新增 H32，清掉 H4、H5、H9 至 H12、H14 至 H16、H18、H20 里"留给 E3/E5/E6/0B"的过时说法，鲁棒性观察补 0B 五条，探索日志补 L20、L21。完成标准七条逐条核对见交接报告 |
| 0C | 1 平衡反应和平衡反应器（E8） | 35fa647 | `spikes/e8_equilibrium_chain.py`（建模步骤抽到 `spikes/chain_kit.py`）：710 °C、600 °C 与参照值最大偏差 0.0046、0.0014（容差 0.02），CH4 转化率 54.0%、30.3%，热负荷 +39989、+20160 kW（吸热为正）；Keq 来源默认就是 Gibbs 自由能；改出口温度同步重算；绝热（出口 422.63 °C）、规定热负荷（39989.2 kW 回到 710.00 °C）、固定 K（摩尔分率基准）都能求解 |
| 0C | 2 Gibbs 反应器，纯气相（E9） | ce6d389 | `spikes/e9_gibbs_gas.py`：不挂反应集、`ReactorType` 默认 3，710 °C 与参照值最大偏差 0.0046、与同 Case 的平衡反应器 0.00001；多股进料（每股 `Feeds.Add`）与单股进料相同；绝热 422.63 °C，与绝热平衡反应器差 0.01 °C。run1 因物流重名崩溃，run2 通过 |
| 0C | 3 固体碳（E10、E10b、E10c、E10d） | 2941945、cf8f9ba、594b948 | `spikes/e10_gibbs_carbon.py`：Gibbs 反应器 + 库里的碳**结果错**（与温度无关，全部氧变 CO、全部氢变 CH4、氢气为 0），四条通过条件第 2、4 条不满足；`e10b` 找到根因（碳的 `EvaluateGibbs(298.15 K)` 是 +671.3 kJ/mol，气态碳原子）；`e10c` 库组分数据写不了（`E_ACCESSDENIED`）；`e10d` 两段式四条通过条件全满足，没有采用。D14 |
| 0C | 4 鲁棒性（E11）和保存重开（E12） | bb742b6、928c4e7 | `spikes/e11_robustness.py`：同名创建、进程中断（错误号 -2147023174 / -2147023170）、弹窗、窗口隐藏的实测，台账 L26；`spikes/e12_save_reopen.py`：保存重开结果和求解状态完全保留，台账 L27 |
| 0C | 5 备选路线对照（E13） | ec67534 | `spikes/e13a_ui_automation.py`（pywinauto，双击 Model Palette 的 ConversionReactor 建出 CRV-100，2/2）、`spikes/e13b_file_script.py`（Case 级 `ApplyXML` 建对象但不带连接；`PlayScript` 建反应器、写反应集排序，排序 0.5731/0.5456 与预测一致）；视觉操作未试验；台账“路线对照”一节 |
| 0C | 6 台账定稿 | 59f7275 | 路线对照表、对工具契约的影响（R1 至 R12）、鲁棒性观察、L26 至 L29、H4/H16/H21/H23/H24/H26/H32 更新、调用序列三个小节补实测 |
| 1A | 第一段：契约（任务 1 至 5） | 36e9068、22c7d7b、a1ac4f6、d35d07f、25d5c43 | `ruff format --check`、`ruff check`、`mypy src`（14 个源文件无问题）、`pytest` 146 passed（全是不需要 HYSYS 的单元测试）；`python tests/test_code_health.py`：`src/` 721 行（spec 541、tools 77、errors 60、backends 43），最长函数 17 行，最深嵌套 2 层，没有忽略检查的注释。错误码 27 个与计划 §13.2 逐码对照；可重试集合 9 个；12 个入参模型拒绝非法值；`ToolExecutor` 三种错误和回调事件有测试；“配置是否一致”的 5 个纯函数有测试 |
| 1A | E14 探针：结束 Basis 之后建反应和反应集 | e7de686 | `spikes/e14_basis_order.py`：direct 变体（`EndBasisChange` 之后直接建反应、反应集、`AssociateFluidPackage`、挂到转化反应器）和 wrapped 变体（`StartBasisChange` 包住）都通过，出口摩尔分率与解析解偏差 0.00000，流程图 4 个对象全是 OK；`ReactionPhase` 显式写 0 读回 0、写 5 读回 5。台账 L31，H5、H9、H11 补充 |
| 1A | 第二段：HYSYS 实现（任务 6） | b5667df、aae6008、6753080、52834e3 | `src/reactor_agent/backends/hysys_com/` 14 个模块文件；`ruff`、`mypy src`（29 个源文件）无问题；单元测试新增 `test_com_errors.py` 11 个、`test_variables.py` 11 个、`test_cases.py` 9 个（用假的 COM 对象检查 Case 的判断）、`test_reactor_kinds.py` 6 个、`test_dialog_guard.py` 2 个（真实的 Win32 模态对话框，不到 1 秒读出文字并点掉）。`grep` 核对：`com_error` 这个名字只在 `com_errors.py`，单位字符串和 -32767 只在 `variables.py`，`Any` 只在 `backends/hysys_com/`，`src/` 里没有 `noqa` 和 `type: ignore` |
| 1A | 集成测试（任务 7） | ea0d61f | `pytest -m hysys tests/integration`：38 passed，约 70 秒；共完整运行 8 次，7 次全过，1 次因 HYSYS 自己崩溃（访问冲突，台账 L33）。**转化反应器**出口摩尔分率与解析解偏差 0.00000（容差 0.001）；**平衡反应器** 710 °C、600 °C 与参照值最大偏差 0.0046、0.0014（容差 0.02），热负荷 +39989、+20160 kW；**两段式气化**（D14 方案 A）CO 收率 39.96%（要求 38% 至 42%），气相 CO、H2 摩尔分率 0.4979、0.4842（参照 0.500、0.482），未反应的碳 1499.06 kmol/h 从第一台的液相出料离开（参照 1491）；每个 ensure 再调一次全是“未改变”，对象个数不增加；对已有物流换温度是 `E_CONFLICT` 且物流不被修改；快照里没有 -32767；正常建模没有触发弹窗 |
| 1A | 台账更新 | cdb6ee3 | 新增“1A 的实现”一节（逐工具列出与计划 §9.3 的差别）、探索日志 L31 至 L33 |
| 1B | 任务 1 至 3：ModelSpec、组分表、规格加载、三份规格 | 550616c | `pytest` 316 passed。三份规格 `evals/golden_specs/*.yaml` 都能加载，导出 JSON 再加载哈希不变；每条一致性规则（组分未声明、进料名重复、组成之和不为 1、两种流量二选一、转化率范围、压降必填、工况与热模式不匹配、假设的字段路径不存在）有违反它的用例；文件不存在是 `E_IO`，内容不合法是 `E_SCHEMA`且消息里有字段路径；分子式解析覆盖括号（`Ca(OH)2`、`Al2(SO4)3`）和纯元素；组分表只有台账里有实测名字的 11 个组分 |
| 1B | 任务 4：BuildPlan 和三种 Recipe | a0463d7 | `pytest` 429 passed。三份规格各自编译出的计划与计划 §17 的构建表一致（去掉头两步；场景 3 按 D14 是转化反应器加 Gibbs 反应器的两段式，台账优先）：平衡反应器 11 步（含 2 个工况步）、转化反应器 7 步（绝热，工况没有步骤）、两段式 14 步；每条专有规则有违反它的用例；`recipe_for(PFR/CSTR)` 是 `None`；各 Recipe 的热模式范围与 Backend 的 `REACTOR_KINDS` 表由测试交叉核对；计划导出 JSON 再加载相等 |
| 1B | 任务 5、6：结果检查 V1 至 V8、指标、归一化结果、结局判定 | ffbbd53 | `pytest` 573 passed（含 `test_code_health.py`）。三个场景的正确快照（`tests/builders.py` 和 `tests/conftest.py` 的 fixture）全部检查通过；“破坏 → 应当失败的检查集合”表 28 项，每项与预期的集合完全一致；V1 至 V8各有通过和失败的用例；三种指标用手算值（转化率 55%、H2/CO = 1850/350、收率 185% 说明不乘计量系数）；干基组成手算（水 1950 kmol/h 扣除后 H2 = 1850/2850）；结局判定覆盖完成、带警告完成、致命失败、缺工况结果、文件没保存 |
| 1B | 探查检查的漏洞（逐字段破坏） | 4497fd7 | 对三个场景的正确快照，逐个字段改 5% 或设为 None，看有没有一个字段的破坏没有任何检查发现：210 处没有。出料的总流量、各组分的质量流量、没有流量的出料里混进的组分流量都没有被检查。V6 增加物流内部一致性（各组分之和等于总流量，组分质量流量等于摩尔流量乘分子量，摩尔分率等于流量占比），`V5`、`V6` 拆到 `validation/streams.py`；剩 101 处是有意不查的量；新增逐场景的“出料里任何一个数不对或缺失都被发现”的测试 |
| 1B | 独立审查（子代理，不带本阶段上下文）和修复 | bcbae41、66e9b57 | 审查报告 10 条确定的缺陷、8 条清单问题、5 条风格和测试缺口。采纳：V4 的期望取自规格的工况而不是计划；V2 增加计划里的流体包和反应与规格一致；`decide_outcome` 核对 V1 至 V8 齐全、结果属于这个工况、至少一个工况，`assemble_result` 把漏跑的检查按失败记；`CheckContext` 要求工况属于规格；非 UTF-8 文件是 `E_SCHEMA`；工况名不能做不了文件名；V3 的相对容差与实现一致；指标名带收率的基准；转化反应的基准组分要在进料里；Gibbs 自由能算 K 的反应不含固体；三处位置元组和裸字典改成冻结的 dataclass；重复的比较抽成 `_compare`；零流量一个阈值；`assert` 改成显式的错误；嵌套三元拆开；删恒真的测试，补容差边界、V2/V4 与规格不一致、结局核对的用例。**没有采纳**：空相出料读回的约定要用真实快照验证（D19，1B 不运行 HYSYS）；两段式的措辞和反应式写死（D14 已批准）；专有检查直接用 `spec.reactions` 求期望（V2 已核对计划里的反应等于规格，链条是通的）；`MetricResult.value` 的单位后缀（单位随指标种类变，放在 `unit` 字段） |
| 1B | D19：验证层在真实 HYSYS 快照上验证（E16） | 5524b22 | 用户答复“现在就跑 D19”。`spikes/e16_validation_real_snapshots.py` 把 Recipe 编译的三份计划原样在 HYSYS 里执行（每步 created，无弹窗），真实快照交给 V1 至 V8：全部通过，结局都是 complete；空相出料读回 0.0；质量÷（摩尔×分子量）最大偏差 5.1e-05（容差 1e-3）；V7 最大相对误差 2.1e-05；与参照值偏差 0.0000 至 0.0046；气化 CO 收率 39.98%。新增 `tests/integration/test_validation_real.py`（10 个）和 `plan_runner.py`；49 个集成测试 94 秒全部通过。台账 L36 |
| 1B | D18：隔离测试的单位规则改成看调用 | 509ee02 | 用户答复“D18修改”。`GetValue`、`SetValue`、`GetValues`、`SetValues` 只能在 `variables.py` 里调用，也不能在别处直接传单位字符串；删除 `NOT_A_UNIT` 例外；新增检测器自检的测试。`pytest` 651 passed |
| 1C | 第一段：执行器（任务 1 至 6，不需要 HYSYS） | 39dce26、efa80f3、d9a6d6d、03cd706、5a2675b、544f3b2 | `ruff format --check`、`ruff check`、`mypy src`（57 个源文件）、`pytest` 791 passed（1B 结束时 651）。执行器用 `tests/fake_tools.py` 的 ToolExecutor 桩和 1B 的手算快照测：三个场景正常路径的工具调用顺序与计划一致、状态依次经过 PLAN 至 REPORT；两个工况各一次改规定值/求解/读取/保存并各有结果；可重试错误重试一次后完成；重试用完后重建一次（Case 文件名 working-1.hsc 变 working-2.hsc，计划从头执行）；持续失败时 FAILED 且调用总数有上界；不可恢复错误（组分不存在、会话失效）立即中止、不重试；快照里有致命错误时终态不可能是完成；无 Recipe 是 UNSUPPORTED 且没有任何工具调用；规则失败是 E_RULE 中止；多工况在第二个工况上重建后两个工况重算；停在指定状态后可从保存的状态文件接着跑；篡改冻结的规格被拒绝。恢复策略对每个错误码走完策略链，与 `RETRYABLE_ERROR_CODES` 一致；状态存储保存再读回相同、没有残留临时文件、写入失败不破坏旧文件；命令行对不存在和非法的规格返回非 0、有可读的原因、没有 traceback。`harness/` 332 行代码 |
| 1C | 第二段：真实 HYSYS 上的验收（任务 7） | a97b2df、499ef30 | `pytest -m hysys tests/integration`：三份规格各跑 3 次都完成，V1 至 V8 全过，与参照值偏差在容差内（转化 0.0000、平衡 0.0046 和 0.0014、气化 CO 收率 39.98%）；3 次之间出料摩尔分率和摩尔流量相对偏差不超过 1e-4；每次运行后物流、能流、反应、反应集、反应器的名字与计划完全一致；重新打开每个工况的 `.hsc`，已求解且出口温度是该工况的；干净重建测试里 Trace 恰好一条恢复事件（`E_CONFLICT`、重建），Case 文件名不同，终态完成。命令行三份规格都跑到 complete，退出码 0，`trace` 打印出时间线 |
| 1C | 任务 9：会话失效的试验（E17） | a8c909d | `spikes/e17_session_loss.py`：第 9 次调用之后 `taskkill`，下一次调用得到 `E_COM_DISCONNECTED`，执行器不到 1 秒以 `FAILED` 结束，诊断里有停在的状态、出错的步骤、错误码和重跑命令，照命令重跑退出码 0、终态 complete；命令行收尾对已不存在的进程没有出错，没有残留进程。台账 L37 |
| 1C | 旧集成测试的间歇性失败（台账 L38，D20） | 499ef30 | 11 次全量运行里 7 次出现 2 至 3 个旧测试失败，根因没有查明；对策是每个测试文件一个新的 HYSYS 实例，之后连续通过 |
| 1C | 独立审查（子代理，不带本阶段上下文）和修复 | fb92a8c、d68863a | 20 条，逐条对照代码核实；采纳 7 条确定的缺陷、清单违反里的大部分和测试缺口，没有采纳的写在 1C 设计决定第 11 条；修复后 `pytest` 837 passed，集成测试 54 passed |
| 0A | 4（补）LLM 连通性（E0） | d4bb9c0（`--ask-key`）、本次提交（输出） | `spikes/e0_llm_connectivity.py --ask-key --tag run1 --capabilities` 由用户在自己的终端里运行，密钥 `getpass` 输入；三个模型都是 HTTP 200（`qwen3.8-max` 2.46 秒、`qwen3.8-flash` 1.36 秒、`qwen3.7-plus` 1.14 秒），`response_format=json_object` 返回可解析的 JSON，`tools` 返回 `tool_calls`；输出文件里只有密钥的长度。台账 L35，**D1 完成** |
| 0A | 只读勘查（计划模式下完成，无脚本） | 2427c43 | 注册表 ProgID、`hysys.tlb` 的接口名与集合的 `Add` 签名、安装目录里的 `hysys.hh`、定义文件、帮助文件，写入台账 L0 和"创建反应的线索"初稿（均未运行验证） |

## 代码地图（阶段 1A 结束时）

后面的阶段按这张表找东西。行数是 `tests/test_code_health.py` 的口径（代码行），合计 1971。

| 文件 | 职责 | 行 |
|---|---|---|
| `errors.py` | 27 个错误码、可重试集合（唯一来源）、`ReactorAgentError` | 60 |
| `spec/enums.py` | 全部枚举：`ToolName`、`ReactorType`（五种）、`PropertyPackage`、`ReactionKind`、`ReactionPhase`、`KeqSource`、`HeatMode`、`SpecVariable`、`StreamKind`、`ConnectMode`、`CaseMode`、`ObjectState`、`ResultStatus` | 57 |
| `spec/tool_args.py` | 12 个入参模型和值模型（反应的可区分联合 `ReactionDefinition`、`FeedConditions`） | 172 |
| `spec/tool_results.py` | `Outcome`、12 个结果数据、`ToolResult` 信封、`ToolCallEvent` | 110 |
| `spec/snapshot.py` | `ModelSnapshot` 及其组成 | 70 |
| `spec/matching.py` | “已有配置与期望是否一致”的纯函数、`require_match`、`values_close` | 136 |
| `backends/base.py` | `SimBackend` Protocol，12 个方法 | 43 |
| `backends/hysys_com/com_errors.py` | **`com_error` 只在这里**：`com_call`、`read_optional`、`attempt_cleanup` | 53 |
| `backends/hysys_com/variables.py` | **单位字符串和空值哨兵只在这里** | 47 |
| `backends/hysys_com/dialogs.py` | 弹窗看门狗线程（D12） | 78 |
| `backends/hysys_com/lookup.py` | 按名字查对象，取流体包、反应管理器、流程图 | 31 |
| `backends/hysys_com/session.py` | 连接、进程号、版本检查、结束实例 | 91 |
| `backends/hysys_com/cases.py` | Case 的创建、打开、保存、关闭，路径校验 | 95 |
| `backends/hysys_com/thermo.py` | 组分列表、流体包、物性包、结束 Basis | 93 |
| `backends/hysys_com/reactions.py` | 反应和反应集 | 187 |
| `backends/hysys_com/streams.py` | 物料流和能流 | 96 |
| `backends/hysys_com/reactor_kinds.py` | 三种反应器的差别（一张表） | 45 |
| `backends/hysys_com/reactors.py` | 反应器创建、连接、读回，`set_spec` | 152 |
| `backends/hysys_com/solving.py` | 求解检查和状态映射 | 62 |
| `backends/hysys_com/snapshot.py` | 拼出整个模型的快照 | 64 |
| `backends/hysys_com/backend.py` | `HysysComBackend`（另有 `is_running()`、`shutdown()`、`dialog_messages()`，不在 `SimBackend` 里） | 143 |
| `tools/registry.py` | `ToolExecutor`（键是 `ToolName`） | 36 |
| `tools/definitions.py` | `bind`、`register_tools` | 47 |

测试：`tests/unit/`（217 个，不需要 HYSYS）、`tests/integration/`（39 个，`-m hysys`；三个模型的手写步骤在 `hysys_models.py`，等价于 1B 的 Recipe 要编译出来的东西）、`tests/test_code_health.py`（13 个）。

### 阶段 1B 新增（`src/` 合计 3716 行代码，1B 之前是 1971 行）

| 文件 | 职责 | 行 |
|---|---|---|
| `spec/loading.py` | 读 YAML/JSON（`E_IO`、`E_SCHEMA`，非 UTF-8 也是 `E_SCHEMA`），把 `ValidationError` 变成带字段路径的领域错误 | 38 |
| `spec/components.py` | 组分表模型和加载、分子式解析、按名字或别名找组分、按分子式找组分、是否固体、水的分子式、进料的摩尔流量 | 88 |
| `spec/model_spec.py` | `ModelSpec` 及其组成、工况名可做文件名、假设和 `is_assumed`、`spec_hash`、`load_model_spec` | 150 |
| `spec/plan.py` | `BuildStep`、`BuildPlan`、`CaseSpecs`、`assemble_plan`、系统进料和出料的推导 | 92 |
| `spec/balances.py` | 按组分、按元素合计物流（缺值是 `None`）、转化率、零流量阈值 | 43 |
| `spec/results.py` | `Issue`、`make_issue`、`CheckResult`、`check_result`、`CheckContext`（要求工况属于规格）、`MetricResult`、`NormalizedResult`、`CaseRecord`、`COMMON_CHECK_IDS` | 131 |
| `recipes/base.py` | `ReactorRecipe` 接口；物性包、进料、出料、能流、工况的公共编译步骤；通用规则 | 213 |
| `recipes/conversion.py`、`equilibrium.py`、`gibbs.py` | 三种反应器的规则、编译和专有检查（转化率、固定 K） | 121、85、153 |
| `recipes/__init__.py` | 注册表 `RECIPES` 和 `recipe_for` | 16 |
| `validation/checks.py` | V1 至 V4，和把 V1 至 V7 排成一张表的 `run_common_checks` | 196 |
| `validation/streams.py` | V5、V6（含物流内部一致性） | 138 |
| `validation/conservation.py` | V7 | 65 |
| `validation/metrics.py` | 转化率、收率、比值 | 51 |
| `validation/normalized.py` | `assemble_result`（含干基组成和 V8，漏跑的检查按失败记）、`decide_outcome` | 108 |
| `config/components.yaml`、`evals/golden_specs/*.yaml` | 11 个组分；三份规格 | — |

另外改动了 1A 的 `spec/matching.py`（容差可传、`reactor_connection_differences`）、`spec/snapshot.py`（`unsolved_objects`、按名字取物流）。
测试：`tests/builders.py` 按计划手算三个场景的正确快照（`Scenario`），`tests/conftest.py` 把它们做成 fixture
（`conversion`、`equilibrium`、`gasification`，以及逐个场景运行的 `scenario`），1C 的执行器测试复用。
集成测试：`tests/integration/plan_runner.py`（按 Recipe 的计划执行：基础和流程图一次，每个工况改规定值、求解、读快照，1C 执行器主流程的前身）、
`test_validation_real.py`（真实快照上的验证，10 个）。探针 `spikes/e16_validation_real_snapshots.py`。

### 阶段 1C 新增（`src/` 合计 4630 行代码，1B 之后是 3716 行）

| 文件 | 职责 | 行 |
|---|---|---|
| `state/models.py` | `TaskState` 和修改它的方法（`enter`、`finish`、`complete_step`、`count_retry`、`reset_for_rebuild`、`record_case`、`record_error` 等）、`failure_report()`；`StepRecord`、`Position`、`SessionInfo`、`CaseSummary`、`TaskError` | 133 |
| `state/store.py` | `StateStore`（`state.json` 和 `artifacts/` 的原子读写，`new_run` 分配不撞号的任务标识并建 `artifacts/`、`work/`）、`ArtifactName`、`new_task_id` | 71 |
| `observability/trace.py` | `EventBody`、`TraceEvent`、`TraceWriter`（追加写 `trace.jsonl`）、`read_events`（忽略被中断的最后一行） | 83 |
| `observability/render.py` | `render_timeline`、`render_failure`、`render_summary` | 110 |
| `harness/engine.py` | `Dependencies`、`Engine`（`create_task`、`step`、`run`，八个状态的处理函数，`_call`/`_try_call`，`_recover`/`_rebuild`/`_preserve_case`） | 281 |
| `harness/failures.py` | `ToolStepError`（工具调用失败，带工具名和入参）、`rule_error`（规则问题 → `E_RULE` 或 `E_UNSUPPORTED`） | 18 |
| `harness/results.py` | `result.json` 的读、写、同名覆盖 | 15 |
| `harness/recovery.py` | 策略表 `POLICIES` 和 `decide` | 36 |
| `harness/budgets.py` | `SOLVE_TIMEOUT_S`、`MAX_REBUILDS` | 2 |
| `cli.py` | `main`、`run_spec`（可注入 `ToolExecutor`，测试用）、`run`/`trace` 两个命令，唯一的装配点 | 113 |
| `spec/enums.py`、`spec/results.py`、`spec/tool_results.py` | 新增 `WorkflowState`、`RecoveryAction`、`EventType`、`Checkpoint`；`RunResult`、`FailureReport`、`issue_details`；`ToolResult.data_as` | +32、+26、+7 |

运行目录：`runs/<task_id>/` 下是 `state.json`、`trace.jsonl`、`artifacts/`（`model_spec.json`、`plan.json`、`result.json`）、每个工况的 `<工况名>.hsc`，
以及 `work/`（建模用的 `working-<n>.hsc`，中止时的 `failed.hsc`）。

测试：`tests/unit/test_engine.py`（49 个）、`test_state.py`（15）、`test_recovery.py`（83，参数化）、`test_trace_render.py`（17）、`test_cli.py`（14）、`test_failures.py`（5）；
`tests/fake_tools.py` 是 `ToolExecutor` 的桩；`tests/integration/test_engine_real.py`（7 个，`-m hysys`）和 `references.py`（三份规格的参照值，与 `test_validation_real.py` 共用）。
探针 `spikes/e17_session_loss.py`。

## 进行中

没有进行中的阶段。1C 已完成（只等用户确认第 5 条），下一个会话做 2A（见“下一步”）。1C 的设计决定留在下面，后面的阶段按它们理解执行器；1B 的设计决定在其后。

### 阶段 1C 的设计草图（2026-10-09 18:40）

**新增文件与估计行数**（代码行）：`spec/enums.py` 加 `WorkflowState`、`RecoveryAction`、`EventType`、`StepStatus`（+30）；
`spec/results.py` 加 `FailureReport`、`RunResult`（+30）；`state/models.py`（`TaskState` 及修改它的几个方法，~110）、
`state/store.py`（原子写 `state.json`、读写 `artifacts/`，~60）；`observability/trace.py`（事件模型、追加写、读，~80）、
`observability/render.py`（时间线、诊断、结果摘要，~170）；`harness/recovery.py`（策略表和 `decide`，~45）、
`harness/budgets.py`（~8）、`harness/engine.py`（~280）；`cli.py`（~150）。`harness/` 合计约 340 行。

**执行器**：一张“状态 → 处理函数”的表；处理函数 `(TaskState) -> WorkflowState | TaskStatus`，返回下一个状态或终态，
每个处理函数只做自己这个状态的事（INIT、PLAN、PREFLIGHT、BUILD_BASIS、BUILD_FLOWSHEET、SOLVE、VERIFY、REPORT）。
`step()` 只做四件事：取处理函数、执行、迁移（或终结）、保存。

**错误只有一条路**：调用工具的入口 `_call` 失败时把信封里的错误还原成 `ReactorAgentError` 抛出，PLAN 的规则失败、
VERIFY 的致命检查失败（`E_VALIDATION_FATAL`）也是抛 `ReactorAgentError`；`step()` 里唯一的 `except` 把它交给 `_recover`，
`_recover` 查策略表得到 重试 / 重建 / 中止，并返回下一个状态。重试 = 留在当前状态，处理函数从游标处继续，所以不需要单独的重试循环；
重建 = 关 Case、换文件名、重置游标回到 PREFLIGHT；中止 = 尽量存 Case，终态 `FAILED`。

**重试计数按“位置”算**（状态、工况序号、游标）：同一位置的所有失败共用次数，位置变了（游标前进、换工况、换状态）就清零。
这样 VERIFY 里“读快照成功、检查失败”的循环不会因为读快照成功而清零计数。总调用数有上界：计划长度 ×（1 + 重试上限）×（1 + 重建上限）。

**Trace 事件由执行器的 `_call` 自己发**，不接 `ToolExecutor.on_event`：当前状态、尝试次数、耗时执行器本来就有，
用回调反而要让回调知道状态（共享的可变量）。`ToolExecutor` 的回调保留不动（单元测试在用），交接报告里说明。

**运行目录**：`working-<n>.hsc` 是建模用的 Case（n 随重建加一），每个工况求解后另存 `<工况名>.hsc`；
`artifacts/result.json` 在每个工况验证后增量写入，REPORT 或中止时补上终态。

### 阶段 1C 的设计决定（已实现）

1. **加一个状态要改三处**：`spec/enums.py` 的 `WorkflowState` 加一个枚举值；`harness/engine.py` 里写它的处理函数 `(TaskState) -> WorkflowState | TaskStatus`；
   `Engine.__init__` 里的 `_handlers` 表加一行。前一个状态的处理函数返回新状态即可接上。需要在新状态里逐工况的话，把它加进 `state/models.py` 的 `PER_CASE_STATES`。
2. **失败只有一条路**：`_call` 把失败的信封还原成 `ToolStepError`（`harness/failures.py`，`ReactorAgentError` 的子类，多带工具名和入参）抛出；PLAN 的规则失败
   （`rule_error`：只要有一条是 `E_UNSUPPORTED` 整体就是 `E_UNSUPPORTED`，否则 `E_RULE`，细节是 `{字段路径: 说明}`，同一字段的几条合并）、没有 Recipe（`E_UNSUPPORTED`）、
   INIT 的哈希不一致、VERIFY 的致命检查失败（`E_VALIDATION_FATAL`，细节是 `{检查编号: 说明}`）也抛 `ReactorAgentError`；`step()` 里唯一的 `except` 交给 `_recover`，
   `_recover` 用 `decide`（纯函数查表）得到 重试 / 重建 / 中止，并返回下一个状态；中止时终态按错误码选：`E_UNSUPPORTED` 是 `UNSUPPORTED`（退出码 3），其余是 `FAILED`。处理函数里没有 `try/except` 和计数。
3. **重试 = 留在当前状态**：处理函数每次从 `TaskState.cursor`（最后完成的计划步骤的编号）继续，所以重做的正好是失败的那一步，没有单独的重试循环。
   **计数按“位置”（`Position`：状态、工况序号、游标）算**，同一位置的所有失败共用次数，位置变了清零；VERIFY 里“读快照成功、检查失败”的循环因此不会被读快照的成功清掉计数。
   一个状态的处理函数里最多有两个工具调用（PREFLIGHT 的连接和新建 Case，VERIFY 的读快照和另存），重试时都要重做。
   工具调用总数的上界：（正常路径的调用数 + 重试上限 × 2）×（1 + 重建上限）+ 2，测试里对正常路径上的每个工具持续失败都断言了这个上界。
4. **重建**：`case.close(save=False)`（尽力，失败不拦着）→ `reset_for_rebuild`（游标、工况序号、已算完的工况、重试计数全部回到起点，会话保留，`rebuilds` 加一）→ `result.json` 清空 → 回到 PREFLIGHT。
   建模用的 Case 文件放在 `work/` 下，叫 `working-<重建次数+1>.hsc`，所以每次重建都是新文件名，也不会和工况名撞名（工况名不区分大小写地唯一，因为 Windows 文件名不区分）。
   每个工况求解后另存 `<工况名>.hsc`（读完快照之后、检查之前，所以致命检查失败的工况也有文件可看）。重建后旧的工况文件会被 `SaveAs` 静默覆盖，HYSYS 在旁边留下 `.bk0` 备份（台账 H4）。
5. **Trace 的事件由执行器的 `_call`/`_try_call` 自己发**，不接 `ToolExecutor.on_event`：当前状态、尝试次数、耗时执行器本来就有；用回调要让回调知道状态，
   就得有一份被执行器改、被回调读的共享可变量。`ToolExecutor` 的回调保留不动（`test_tool_executor.py` 在用），生产代码里没有人传它。收尾调用（关 Case、存现场）不编“第几次”。
   事件的状态是 `WorkflowState | TaskStatus`，验证事件有类型化的 `verdict`（检查编号 → 是否通过），检查点的名字是 `Checkpoint` 枚举。
6. **`result.json` 增量写**（`harness/results.py`）：每个工况验证后写入（同名覆盖，位置不变），重建时清空，`_finish` 补上终态。REPORT 只读它、调用 `decide_outcome`。失败的终态也写它，里面是已有的工况记录。
7. **中止时留下现场**：只在已经有 Case 的情况下做（`session.case_file` 非空，规则失败这类没碰过 HYSYS 的中止不调用任何工具），**另存到 `work/failed.hsc`**，不原地保存——
   原地保存会用失败工况的状态覆盖上一个已经验证过的工况的 `.hsc`（独立审查发现，有真实 HYSYS 上的测试）。另存失败了就算了，不盖住原来的错误。
8. **`FailureReport`（`spec/results.py`）是诊断的入参模型**，`TaskState.failure_report(trace_path, spec_path)` 从最后一条错误记录填它；`render_failure` 只认这个模型。
   会话失效（`E_COM_*`）时多打印一行“用同一份冻结的规格重跑”的命令。
9. **命令行**：`run_spec(tools, spec, spec_path, runs_dir)` 是不含 Backend 的主体，测试传桩；`run` 先校验规格，再在 `with _hysys()` 里创建 Backend 并在离开时 `shutdown()`（结束自己启动的 HYSYS，
   Case 里的内容都已经另存）。退出码：完成和带警告完成 0；失败和领域错误 1；不支持 3；需要补充 4。
10. **`Provenance.case_path` 是工况另存的文件**（`SaveData.path`），不是快照里的 `case_path`（读快照时活动 Case 还是上一个文件）。
11. **没有采纳的审查意见**：①`step()` 之外的 `E_IO`（`store.save`、`_finish`、`_recover` 内部写文件）会直接逃出 `run()`，状态文件停在上一步——运行目录写不了的时候没有地方可以记录失败，
    命令行已经打印领域错误并返回 1；加重试会掩盖磁盘问题，Windows 上文件被占用的瞬时失败概率很低，留给阶段 4 一起处理。②`StateStore.load`、`Engine.run(stop_at=…)`、`Engine.step` 公开但生产代码里只有
    测试和 `run()` 在用：提示词要求有这三样（读回状态、反复推进直到指定状态、推进一步），阶段 2 的 `--dry-run` 和阶段 4 的续跑要用。③`steps`、`cases`、`spec_file`、`process_id`、`warning_failures`
    写了没人读：提示词要求状态文件有这些摘要，给人读 `state.json` 和续跑用。④`TaskState` 是可变的，“只通过方法修改”没有机制保证：可变是有意的（它是全系统唯一不断更新的数据），约定写在类的文档里。
    ⑤时间线的标签宽度按字符数而不是显示宽度，中文工况名会错位，但标签和正文之间一定留出间隔。⑥两段式 Gibbs 的措辞“气化”、反应式写死（`recipes/gibbs.py`，1B 的代码，D14 已批准）不在本阶段范围。
12. **策略表与提示词的差别（用户同意，D20）**：`E_NOT_SOLVED` 不重试、重建一次、再中止（提示词的表里它属于“其余全部中止”）。理由：HYSYS 在长会话里偶尔建出结构全对却不求解的模型
    （台账 L38），新建 Case 重来能避开；真正欠规定的模型多重建一次才中止，诊断里仍有各对象的状态。


### 阶段 1B 的设计决定（已实现）

1. **Recipe 接口比计划 §23.2 多一点输入**：`rules(spec, components)`、`compile(spec, components)`、
   `checks(context)`，`context` 是提示词要求的冻结上下文 `CheckContext`（规格、当前工况、计划、组分表、快照）。
   含固体碳的 Gibbs 要在编译时知道哪个组分是固体、各组分的分子量；专有检查要用计划里的对象名。Protocol 里的
   参数是仅位置的，实现可以把用不到的参数写成 `_components`。注册表在 `recipes/__init__.py`，不在 `base.py`（循环导入）。
2. **反应相沿用 1A 入参里每个反应的 `phase`**：普通 Recipe 照规格传下去；两段式的前段转化反应固定用合并相。
3. **热模式包含“规定热负荷”**：只有平衡反应器验证过（台账第二节）。转化、Gibbs 的 Recipe 规则拒绝它，Gibbs 含
   固体碳时只接受规定出口温度。转化、Gibbs 的热模式范围与 Backend 的 `REACTOR_KINDS` 表由测试交叉核对；平衡反应器三种都验证过，
   所以它的规则不限制热模式（后端表一旦收窄，测试会提醒）。
4. **转化反应器的规则**：每个基准组分只能出现在以它为基准的反应里（否则 `E_UNSUPPORTED`，HYSYS 的转化率按进料里的量
   算，不支持前后串联的反应）；同一基准组分的并行转化率之和不超过 100%；基准组分要在进料里（否则 `E_RULE`，用户可补充）。
   因此专有检查“基准组分实际的转化率等于各反应转化率之和（±0.1 个百分点）”是精确的。
5. **Gibbs 含固体碳（D14 方案 A）**：进料只能是碳和水（别的固体或别的进料组分 `E_UNSUPPORTED`，没有水 `E_RULE`）；
   组分表要有 CO 和氢气；基准组分取进料里摩尔量少的那个（质量流量按分子量换成摩尔），转化率 100%，反应相合并相；
   第一段转化反应器、第二段 Gibbs 反应器都带能流、都写出口温度；压降由第一段承担。“元素都有非固体的组分可以
   容纳”理解为：进料里的每种元素至少出现在一个非固体的组分里；不在进料里的固体不能出现在 Gibbs 的组分表里
   （库里碳的热力学数据，台账 L25）。气化反应 C + H2O → CO + H2 的四个分子式是 `recipes/gibbs.py` 里的具名常量。
6. **系统的进料和出料从计划里推出来**（`spec/plan.py`）：进料是带规定的物料流，出料是反应器的出料里没有再被别的
   反应器当进料的。V2、V3、V5、V7、指标、干基组成都用它，验证层不重新实现命名规则。
7. **缺值与零流量**：V5 对没有流量的出料只要求温度、压力、总流量有值；V6 只看存在的物流，没有流量的物流不要求分率之和为 1
   （真实快照上空相出料的 T、P、流量和各组分流量是已知的 0.0，台账 L36）。
   缺失的物流归 V2、V5、V7。“没有流量”只有一个阈值 `spec/balances.py` 的 `ZERO_FLOW_KMOL_H`（1e-9 kmol/h）。
8. **检查结果的期望值和实测值是代码格式化好的字符串**；检查编号是 `CheckId` 枚举（V1 至 V8，另有 `V4-conversion`、
   `V4-fixed-k` 两个专有检查）。每项检查是“上下文 → 检查结果”的小函数，放在 `COMMON_CHECKS` 里依次执行。
9. **检查的期望值取自规格，不取自计划**：计划是 Recipe 编译出来的，编译错了，读回再和计划一致也是错的模型。V3 拿读回的进料和
   `ModelSpec` 比（进料名从计划里取，按顺序一一对应，温度、压力、流量相对容差 1e-4，摩尔分率绝对偏差 1e-4）；V4 比当前工况的出口温度
   （±0.1 °C）或热负荷（对计划里每台反应器都成立），以及全部反应器的压降合计与规格的压降；V2 另外核对计划里的流体包和规格里的反应与规格一致。
   为此把 `matching.reactor_differences` 拆成只比类型和连接的 `reactor_connection_differences`（V2 用）加压降。
10. **V6 要求一股物流里的数彼此一致**（超出计划 §12.3 对 V6 的字面定义）：各组分的流量之和等于总流量（摩尔和质量，相对 1e-6），
    组分质量流量等于摩尔流量乘组分表的分子量（相对 1e-3），摩尔分率等于组分流量占总流量的比（绝对 1e-6）。原因是报告同时展示总量和
    各组分的量，逐字段破坏的探查发现这些量原来没有任何检查。真实快照上的最大偏差是 5.1e-05，余量约 20 倍（台账 L36）。
11. **`MetricResult` 带单位枚举、名字和定义**（`MetricUnit`：百分数或比值），值是 `None` 表示算不出来；收率不乘计量系数，名字带基准
    （“CO 收率（以 Carbon 计）”）。
12. **`BuildStep` 的工具和阶段由入参的类型推出**（`assemble_plan(basis, flowsheet, cases: Sequence[CaseSpecs])`），Recipe 只产出入参；
    模型校验保证一致。
13. **平衡 Recipe 的专有检查和规则**：给定了 K 的反应，气相出料的反应商等于 K（摩尔分率基准，台账 H10），因为场景之外的题目可能直接给平衡常数；
    Gibbs 自由能算出的 K 没有独立的算法可以核对（V9 的参照值比对是 3A）；用 Gibbs 自由能算 K 的反应不能含固体组分（台账 L25，**只在
    Gibbs 反应器上验证过，平衡反应器上是推断**）。
14. **结局判定不放过不完整的结果**：`decide_outcome(case_names, records)` 对没有工况、缺工况记录、结果为空、结果属于别的工况、V1 至 V8 不齐、
    `.hsc` 没保存、有致命检查失败都判失败；只有警告是带警告完成（警告级的检查要等 V9，阶段 3A）。`assemble_result` 把漏跑的检查按失败记在结果里。
15. **规格边界**：工况名要用来给每个工况的 `.hsc` 命名，不能带 `\ / : * ? " < > |`、控制字符，首尾不能是空格或点；不是 UTF-8 的文件是 `E_SCHEMA`
    （`E_IO` 在可重试集合里，重试没有意义）。
16. **有意不查的量**：出口压力（HYSYS 算的，没有验证过“进口压力减压降”的语义）、没有规定的出口温度、热负荷的数值、空相出料的组成。它们的合理性
    比对（趋势、参照值）是 V9，阶段 3A。

## 下一步

阶段 1C 已完成（闸门 G1 通过）。下一个会话做**阶段 2A**（`docs/prompts/phase-2a.md`：给一段描述，系统判断反应器类型并说明理由）。开始前：

1. **用户的事项都已处理**：完成标准第 5 条通过；D20 按“重建一次”做了（`E_NOT_SOLVED` 不重试、重建一次、再中止）；D17 继续。没有待答复的事项。
2. **2A 要读的**：`harness/engine.py`（状态表和处理函数，加一个状态要改哪三处见 1C 设计决定第 1 条）、`state/models.py`、`cli.py`；LLM 的供应商和模型见"环境事实"，连通性见台账 L35，
   没测过的能力（`json_schema`、流式、关闭思考、限流、超时）由 2A 测。
3. **要接上的地方**：①`Engine.create_task(spec, spec_file)` 现在要一份已经加载好的规格和它的文件路径，`TaskState.spec_file` 是必填的 `Path`；2B 之后规格来自 LLM，
   没有文件，要把它改成可空或者记输入文本（计划 §10.2 的 `input`）。②`Engine.run(task, stop_at=…)` 已经有，`--dry-run` 可以用它停在 PREFLIGHT 之前。
   ③`WorkflowState` 里还没有 SELECT、SPECIFY、VALIDATE；`TaskStatus` 里有 `NEEDS_INPUT`，命令行的退出码表里也有，但没有状态会产生它。
   ④`ToolExecutor` 的 `on_event` 回调在生产代码里没人用（Trace 由执行器自己发）。
4. **提醒**：①HYSYS 在同一个实例里建了几十个 Case 之后偶尔出现不求解或不反应的模型（台账 L38），命令行每次运行起新实例所以不受影响，评测批量运行要定期换实例；
   ②一个状态的处理函数里有多个工具调用时，重试会把前面的调用也重做一遍（工具是幂等的，所以安全，但调用数要算上）；
   ③在命令行工具里用 heredoc 写 Python 脚本改文件时，双反斜杠会被合并成一个，字符串里的换行转义会变成真正的换行；改含反斜杠的行用编辑工具。

## 待决策

需要用户确认的事项。默认值来自 `MASTER_PLAN.md` §25，用户没有另行指示时按默认值执行。

| 编号 | 事项 | 默认 | 状态 |
|---|---|---|---|
| D1 | LLM 供应商和模型；VM 能否直连。任务 4（E0）因此挂起 | **用户 2026-10-08 已答复**：阿里云百炼 Qwen，主 `qwen3.8-max`、快速 `qwen3.8-flash`、备用 `qwen3.7-plus`，密钥 `DASHSCOPE_API_KEY`；要求不硬编码、统一封装 Provider/Client（模型名可配置）、为 Agent/工具调用/结构化输出预留接口（阶段 2A）、不增加别的模型和复杂路由 | **已完成**（用户 2026-10-09 运行 E0，通过）：三个模型都返回 200，主模型的 `json_object` 和 `tools` 通过，国内站 `https://dashscope.aliyuncs.com/compatible-mode/v1`；没有测的能力（`json_schema`、流式、关闭思考、限流、超时）由 2A 测。密钥读不到环境变量时，给用户一条 `--ask-key` 命令在自己的终端里输入，不贴进对话 |
| D2 | 场景 3 是否加入氧气 | 不加，按题面建模，在报告中说明 | 按默认 |
| D3 | "80000 Nm³/h"的含义 | 进料的总摩尔流量 | 按默认 |
| D4 | 二甲苯异构体分配 | 对 : 间 : 邻 = 24 : 52 : 24 | 按默认 |
| D5 | 压力是绝压还是表压 | 绝压 | 按默认 |
| D6 | 场景 1 的进料流量基准 | CH4 1000 kmol/h | 按默认 |
| D7 | Demo 形态 | 命令行，HYSYS 窗口可见 | 按默认 |
| D8 | 机动时间先做泛化还是先做加固 | 先泛化 | 按默认 |
| D9 | Git 署名的名字和邮箱 | 之后的提交署名 `xibei03 <jsl_03@163.com>`，历史提交不改 | **已定**（用户 2026-10-08 指定）。此前 13 个提交署名是 `xibeibei63`，不改写历史（会需要强制推送）；若想让展示统一，可以加 `.mailmap`，没加，等用户说 |
| D11 | 三种反应器的参考 Case `spikes/ref_cases/three_reactors.hsc` | 用户 2026-10-08 指示由助手自行创建 | **已解决**：助手用代码建成并求解（`build_reference_case.py`），E3 已补跑；Gibbs 类型选项和出口温度规定的位置已查清（台账 H31、E8 小节），不需要用户手工建。用户若想在界面里看一眼，打开这个文件即可 |
| D12 | 弹窗会让 COM 调用卡死（H23）。已见两种：打开用到 Aspen Properties 的 Case，反应集类型与反应器不匹配。0A、0B 的探针用一个后台线程盯着 HYSYS 进程的对话框并点 OK（`spikes/_common.py` 的 `dialog_guard`）。正式系统同样需要，但 `CLAUDE.md` 架构不变量 7 说系统不用多线程 | 建议：允许在 `backends/hysys_com/` 内部用一个守护线程专门处理弹窗（只调用 Win32，不碰 COM 对象），其余仍然同步；备选是只靠事先校验避免已知的弹窗，遇到未知弹窗只能靠超时后按进程号结束 | **已定（用户 2026-10-08：“D12 批准使用后台线程”）**：按建议，在 `backends/hysys_com/` 内部用一个守护线程处理弹窗，只调用 Win32，不碰 COM 对象；其余仍然同步。`CLAUDE.md` 架构不变量 7 写的是“不用多线程”，这是用户批准的例外；1A 实现时引用本条，需要的话再改 `CLAUDE.md` |
| D13 | 反应集排序没有办法用代码写入（H32），所以“依次进行”的 0.573 没有验证 | Recipe 不设排序，保持默认并行；需要依次时建议用两台转化反应器串联或合并反应 | **已定（用户 2026-10-08：“D13 保持排序”）**。我的理解：保持默认的排序（不设排序、并行），不再验证 0.573，也不继续找写排序的办法；如果用户的意思不同，请指出 |
| D14 | **固体碳在 Gibbs 反应器里算不对**（场景 3，E10，台账 L24、L25）。进料含固体碳时 Gibbs 反应器的结果与温度无关：全部氧变成 CO、全部氢变成 CH4、氢气为 0（CO 1035、CH4 517.5、碳 981.5 kgmole/h；参照 CO 1017、H2 981、CH4 22、碳 1491）；四条通过条件里第 2、4 条不满足，碳元素守恒和 CO 收率恰好通过，是看起来合理但错的结果。原因：库里 `Carbon` 的 Gibbs 生成能函数是气态碳原子的（+671.3 kJ/mol），生成焓却是石墨的 0，没有升华蒸气压和临界性质，Gibbs 反应器把碳当成特别不稳定的物质。含碳进料本身能正常闪蒸（当作重液相），未反应的碳从液相出料离开。 | **建议 A**（计划 §17.3 的两段式）：先用转化反应器按限量反应物算 C + H2O → CO + H2（水为基准组分，转化率 100%），再用 Gibbs 反应器算气相平衡，未反应的碳从第一台反应器的液相出料旁路；主模型仍是 Gibbs 反应器，报告里如实说明。B：改库里碳的热力学数据——E10c 试了，库组分的 `GibbsCoeffs` 写入被拒绝（`E_ACCESSDENIED`），只能新建假想组分，没有试，没有把握。C：用假想固体组分（没有试）。**我试了 A 的可行性（E10d，没有采用）：四条通过条件全部满足**——气相 CO 1012.6、H2 984.8、CH4 18.2、H2O 13.9、CO2 4.3 kgmole/h（参照 CO 1017、H2 981、CH4 22、H2O 11、CO2 3.5），CO 收率 39.96%，未反应的碳 1499.0（参照 1491，相差 0.5%）从第一段的液相出料离开，总外供热 84.6 MW（参照约 85）。等你决定是否采用 | **已定（用户 2026-10-08：采用方案 A）**。场景 3 的模型是“转化反应器（C + H2O → CO + H2，基准组分水，转化率 100%，反应相用合并相）+ Gibbs 反应器（进料是第一台的气相）”，两台都带能流、气相出料写 1400 °C；未反应的碳从第一台的液相出料离开。`gibbs` Recipe（1B）按这个结构编译，报告里如实说明主模型仍是 Gibbs 反应器；参考 `spikes/e10d_two_stage.py`（四条通过条件全满足）。1A 的集成测试按这个结构建第三个模型 |
| D15 | **对计划 §9.3 工具契约的修改建议 R1 至 R12**（台账“对工具契约的影响”一节，逐条有原因和状态）。要点：`session.connect` 一律 `NewInstance`（R1）；`case.ensure` 新建后立刻 `SaveAs`，可重入靠按 `FullName` 找（R2）；`basis.ensure_thermo` 末尾结束 Basis、物性包存内部名（R3）；`ensure_reaction` 读回容差 1e-3、Keq 来源只开 Gibbs 自由能和固定 K、加 `phase` 参数（R4）；`ensure_reactor` 先查名字、同名不同类型报冲突且不调 Add、连接顺序固定、热模式只开已验证的组合（R5）；`solver.solve` 改成检查、默认不挂起、两个 RPC 错误号映射成断开（R6）；所有“确保存在”先查再改（R7）；弹窗看门狗放进 Backend（R8，D12 已批准）；路径入口校验（R9）；反应集排序不进契约（R10，D13）；含固体碳的体系等 D14（R11）；`PlayScript` 只作 Backend 内部备用通道（R12） | 全部按建议 | **已确认（用户 2026-10-08：“D15 全部按建议确认”）**。R1 至 R12 在台账里的状态都改为“已确认”；R11 随 D14 落实为两段式。一处补充：R4 的 `phase` 参数不能只开放气相——两段式第一台转化反应器的进料是碳水浆料（重液相），反应相要用合并相（E10d 用的就是转化反应的默认值 5），所以 1A 的 `ReactionPhase` 开放两个都验证过的取值：气相（G0）、合并相（E10d） |
| D18 | **隔离测试的字符串规则有一处误报**：`tests/unit/test_hysys_backend_isolation.py` 逐个检查 `src/` 里的字符串常量，凡是等于 HYSYS 的单位字符串（`"C"`、`"bar"`、`"kPa"`、`"kgmole/h"`、`"kg/h"`、`"kW"`）都只能出现在 `variables.py`。`recipes/gibbs.py` 里固体碳的分子式 `"C"` 被当成摄氏度。1B 先把它写成一个解析反应式字符串的小技巧躲开，独立审查指出那是为过检查而写挤，改回四个具名常量，在测试里加一处带原因的例外（`NOT_A_UNIT`，另有测试保证例外仍然需要） | 按 `CLAUDE.md` 的做法：一处带原因的例外加一条待决策，继续做。备选：把规则改成只看传给 `GetValue`/`SetValue` 的字符串参数（更准，但要改测试的写法） | **已定（用户 2026-10-09：“D18修改”）**：选了备选。隔离测试的单位规则改成看调用——`GetValue`、`SetValue`、`GetValues`、`SetValues` 只能在 `variables.py` 里被调用，也不能在别处直接传单位字符串（比只看字符串参数更严，也不会误报分子式）；`NOT_A_UNIT` 例外删除（提交 509ee02） |
| D19 | **1B 的验证层（V1 至 V8、指标、结局判定）只在手算的快照上试过，没有在真实 HYSYS 快照上试过**（1B 提示词写了不运行 HYSYS）。独立审查指出这是风险最大的一处：空相出料读回的是 0.0 还是 `None`（1A 的集成测试两种都接受，台账 L32 写“0 或 None”，我在 1B 开始时看过的快照是已知的 0.0 但没有记录）、V6 新增的分子量容差 1e-3 和物流内部一致性会不会对重液相里的固体碳误报、V4 读出口温度的方式 | 建议：1C 的第一个任务写一个 `@pytest.mark.hysys` 的测试，用 Recipe 编译三份黄金规格→执行→读真实快照→喂给检查（见“下一步”第 5 条）；或者现在由我写好并运行一次（约 2 分钟，不改 `src/`，只读），这需要你同意，因为 1B 提示词写了不运行 HYSYS | **已解决（用户 2026-10-09：“现在就跑 D19”）**：E16 探针和 10 个集成测试在真实快照上验证，三份规格全部通过 V1 至 V8，结局 complete，没有误报；空相出料读回的是 0.0，温度、压力有值；V6 的分子量容差余量约 20 倍（台账 L36，提交 5524b22） |
| D10 | GitHub 登录：这台机器原本没有存储的凭据 | 用户登录后，助手补推全部提交 | 已解决（用户 `gh auth login` 登录为 `xibei03`，首次推送 2026-10-08 成功）。可选：用户若想让以后的 `git push` 不再需要一次性助手，自行运行 `gh auth setup-git` |
| D16 | **1A 里有两处与已确认的 R6、R8 措辞不完全一致的实现**：①R6 说 `solver.solve` 的 `timeout_s` 由看门狗线程实现（超时后按进程号结束）；实现只做了轮询 `IsSolving` 的超时，没有强制结束进程；②R8 说“文字白名单见 H23”；实现对任何对话框都点“确定”，已知文字只用来区分日志级别 | 按实现：①强制结束放进阶段 4 的执行器恢复策略（R1），②保持“都点”（不点会让 COM 调用永远卡住）。如果想改成只点已知文字，改 `dialogs.py` 的 `_handle` 一处即可 | **按默认**，用户若不同意请指出 |
| D17 | **`src/` 的行数预算**：阶段 1A 结束时 `src/` 有 1971 行代码（`backends` 1280、`spec` 548、`tools` 83、`errors` 60），已经占 `CLAUDE.md` 说的全系统约 3000 行的三分之二。后面还有 `recipes`、`validation`、`state`、`observability`、`llm`、`skill_loader`、`report`、`harness`（上限 600）和 `cli`，粗估总量会到 4000 行以上。1A 的代码都有用处（Backend 要处理 HYSYS 的各种怪癖），没有发现能直接砍掉的部分 | 继续做，不在 1B 之前砍；每个阶段结束报行数，2C 结束时如果超过 4500 行再决定合并或删除哪些。预算数字只是估计，除了 `harness` 的上限没有测试强制 | **已定（用户 2026-10-09：“D17继续做”）**：按建议继续，不砍；每个阶段结束报行数，2C 结束时超过 4500 行再决定。**1C 结束时 4630 行**（`backends` 1280、`spec` 1199、`recipes` 588、`validation` 558、`harness` 352、`state` 204、`observability` 193、`cli` 113、`tools` 83、`errors` 60），已经超过 4500 行触发点，但 2A 至 2C 还要加 `llm`、`skill_loader`、`report` 和执行器的几个状态。1C 自己的新增（state、observability、harness、cli）共 862 行，没有发现能直接砍的；计划 §22.1 的参考值（Backend 约 500、规格层约 700、Recipe 约 300、验证层约 300）早在 1A、1B 就超了一倍。**已定（用户 2026-10-09：“D17继续”）**：继续，不在 2A 之前合并或删减 spec/ 和 validation/ 里的模块；每个阶段结束仍然报行数 |
| D20 | **旧的集成测试在长会话里间歇性失败**（台账 L38）：整个测试会话共用一个 HYSYS 实例时，全量集成测试（53 个测试、约 60 个 Case）11 次运行里 7 次出现 2 至 3 个失败——新建的模型不求解（`E_NOT_SOLVED`）或转化反应器不反应，结构全部正确，把求解器关掉再放开也不解。根因没有查明，排除了 CPU、并发、内存、句柄、GDI、时间、单纯的 Case 数量。**我的做法（已做）**：把集成测试的 `backend`、`executor` 夹具从会话级改成文件级，每个测试文件一个新的 HYSYS 实例（多花约 45 秒），之后全量运行连续通过；与 1C 提示词“整个测试会话共用一个 HYSYS 连接”不同。**建议**：①保持文件级；②给 `E_NOT_SOLVED` 一次重建的机会（现在按提示词的策略表直接中止；重建只要几秒，能吃掉这类偶发的“不求解”，代价是真正欠规定的模型多重建一次才中止），改 `harness/recovery.py` 的策略表一行加一个测试 | **已定（用户 2026-10-09：“D20重建一次”）**：①文件级夹具保持；②`E_NOT_SOLVED` 不重试、重建一次、再中止，已实现（提交 51a5c49），执行器的单元测试和真实 HYSYS 上各有测试 |

## 决策日志

实现过程中做出的设计决定和假设。

| 日期 | 决策 | 原因 |
|---|---|---|
| 2026-10-08 | 远端 `main` 上已有只含 `README.md` 的 `Initial commit`，与本地历史无共同祖先。用 `git merge --allow-unrelated-histories` 合并，不用 `rebase`，不强制推送 | 合并保留远端的全部历史，本地提交的哈希不变（本文件和台账引用了它们），推送是快进。两边没有同名文件，没有冲突 |
| 2026-10-08 | 接手时发现工作区里的 `docs/progress.md` 和 `.gitignore` 被覆盖成旧版（未提交）。旧版备份到会话的临时目录后，用已提交的版本恢复 | 已提交的版本更新（记录了任务 1 至 3、5 的结果，`.gitignore` 里有 `*.rdp` 和 `Claude outputs/`）；旧版的内容是它的子集，没有信息丢失 |
| 2026-10-08 | 用户指示 D11 自行创建、D9 署名 `xibei03 <jsl_03@163.com>`：参考 Case 用 COM 代码建，建 Case 的过程当作探针 E4 至 E9 记录；署名用 `git config user.name/user.email`（仓库级） | 用户的明确指示。代码创建 = 0B 的目标，所以顺带验证 0B/0C 的创建链；0B 仍按提示词重新做，但起点高得多 |
| 2026-10-08 | 复用 2026-10-03 已完成的任务 1 至 3、任务 5 的 run1 和 run2、只读勘查 L0，不重做 | 逐项复核：质量工具全绿、台账结构完整、E1 脚本和输出齐全，都可用 |
| 2026-10-08 | 0B 任务 1（E4）、任务 3（E6）不重做，G0 脚本直接沿用 D11 的创建链 | D11 里已经用代码跑通并写进台账，重做没有新信息；0B 的增量是四产物分数系数版本、与解析解的对比、两次运行一致性 |
| 2026-10-08 | 反应集排序用不了代码写，Recipe 不设排序，保持默认并行 | 默认（全 0）就是并行，正好是"同一基准组分的主、副反应各按进料算"这种需要的语义；依次进行可以用串联反应器表达。D13 |
| 2026-10-08 | D12 批准：弹窗看门狗可以用后台线程（限 `backends/hysys_com/` 内部，只调 Win32，不碰 COM） | 用户答复。探针里的 `dialog_guard` 就是这种做法，0C 的 E11 证明它在窗口可见和隐藏时都能处理弹窗 |
| 2026-10-08 | D13：保持默认排序（不设排序、并行） | 用户答复“保持排序”，按我的理解记录（见 D13 一行） |
| 2026-10-08 | D1：LLM 统一用阿里云百炼的 Qwen API，密钥只从环境变量 `DASHSCOPE_API_KEY` 读取；主模型 `qwen3.8-max`（复杂推理、反应器判断、任务规划），快速模型 `qwen3.8-flash`（参数提取、场景识别、结果解释），备用模型 `qwen3.7-plus`（主模型异常或能力不足时切换）；不增加别的模型，不做复杂路由 | 用户答复。要求：不硬编码密钥；统一封装 Provider/Client，模型名可配置；为 Agent、工具调用、结构化输出预留接口（阶段 2A 做）；先做最小连通性测试，通过后才把 D1 标为完成 |
| 2026-10-08 | E10d 两段式只作为 D14 的可行性证据，不进正式模型 | 0C 提示词要求 Gibbs 反应器不能正确处理固体碳时不自行改用两段式；证据（四条通过条件全满足）交给用户 |
| 2026-10-08 | 对工具契约的建议 R1 至 R12 写进台账、登记 D15，不改 `MASTER_PLAN.md` | 0C 提示词要求：只写建议，每条标状态，需要确认的登记待决策 |
| 2026-10-08 | H24 写“部分确认”而不是 0C 提示词建议的“不需要” | 主路线没有因 H24 受阻，但为了设反应集排序实际用了 `PlayScript`，写“不需要”会丢掉有用的信息 |
| 2026-10-08 | 用户回复"审查 0B 是否完成，若已完成则继续做 0C"：先把 0B 剩下的收尾做完（任务 5 的 E6c、台账、进度），再进入 0C | 0B 的完成标准 4、5、7 当时没有满足（调用序列小节、排序结论、提交），审查结论是"未完成"，所以先补完再继续 |
| 2026-10-08 | 1A 的全部枚举放在 `spec/enums.py`（`ReactorType` 仍然只定义一次），不放 `tool_args.py` | 入参模型加枚举会超过 300 行的上限，拆开后各自只有一个职责 |
| 2026-10-08 | 转化率入参用 `conversion_percent`（百分数，0 < x ≤ 100），Backend 不做换算 | 与 HYSYS 和计划 §9.4 规则 5 一致，少一处单位换算就少一处单位错误 |
| 2026-10-08 | `session.connect` 有 `mode`（`launch` 默认、`attach` 只用于调试），结果带 `reused_instance` | R1 说 attach 只用于调试，提示词要求结果里放“是否复用”，后面的阶段靠它判断能不能结束进程 |
| 2026-10-08 | `ensure_reactor` 的 `heat_mode` 只是自洽性声明（绝热等价于没有能流）；`set_spec` 的白名单是出口温度（写在气相出料上）和热负荷（写在能流上），对象一律是反应器；变量当前是计算值时拒绝（`E_RULE`） | 出口温度和热负荷是工况变量；对计算值写入会过规定。Gibbs 和转化反应器的规定热负荷没有验证过，抛 `E_UNSUPPORTED`（R5） |
| 2026-10-08 | `case.ensure` 的 `new` 遇到已存在的文件、或者已经打开了另一个 Case，都报 `E_CONFLICT` | `ensure_*` 从不修改已有对象；干净重建要用新的文件名（R2）；Backend 一次只管一个 Case |
| 2026-10-08 | 反应的 `phase` 开放气相和合并相两个取值 | D14 选方案 A：两段式第一台转化反应器的进料是碳水浆料（重液相），要用合并相（E10d 用的就是转化反应的默认值）；气相反应用气相（G0） |
| 2026-10-08 | “结束 Basis 之后建反应集”先写探针 E14 验证，再在 `src/` 里用 | `CLAUDE.md` 架构不变量 3：只用台账里已确认的接口。结果：完全可用，不需要 `StartBasisChange` |
| 2026-10-08 | 弹窗看门狗对任何对话框都点“确定”（同一个窗口 5 秒内只点一次），已知文字（H23）只用来区分日志级别：已知记 INFO，未知记 WARNING；所有处理过的文字记在 `messages`，工具失败时放进错误细节的 `dialogs` | 不点未知对话框会让 COM 调用永远卡住，宁可点掉并告警。R8 里“文字白名单”我理解为已知对话框的清单，不是“只点白名单”；见 D16 |
| 2026-10-08 | 集成测试的夹具在每个测试前检查 HYSYS 进程（`HysysComBackend.is_running()`，只看进程号），崩溃了就重新连接 | HYSYS 偶发访问冲突崩溃（台账 L33），让一次崩溃只影响一个测试。这只是测试夹具，不是 Backend 的自动重启（那是阶段 4） |
| 2026-10-08 | 收尾的代码体检让一个不带本阶段上下文的子代理按清单审查 | `CLAUDE.md` 的要求；结果与处理见交接报告 |
| 2026-10-08 | 错误细节的类型是 `Mapping[str, str]`（键是对象名或字段名，值是说明文字，如 `{"CRV-100": "under_specified"}`），`ReactorAgentError.details` 是只读视图 | 它是有语义的映射，不是靠位置区分含义的元组，也不是任意值的裸 `dict` |
| 2026-10-09 | 阶段 1B 一开始就写了设计草图和 9 条设计决定；实现时按“设计决定（已实现）”调整 | 草图是估计，实现时发现 V3 要和规格比而不是和计划比、专有检查在固定 K 时有意义等 |
| 2026-10-09 | 用户说“如果 A1 已完成则做 A2”：我理解为按项目顺序的下一阶段 1B，不是 2A | 2A 的“开始前先读”要读 1C 才产生的 `harness/engine.py`、`state/models.py`、`cli.py`，2A 不能越过 1B、1C；阶段边界“一个会话一个阶段”由这条指示暂时放宽 |
| 2026-10-09 | `ModelSpec` 的假设必须指向规格里真实存在的字段路径（模型校验） | 报告靠字段路径判断哪些量是假设，指错了路径等于丢了假设；测试里改规格时这条校验也帮忙发现了改动破坏的假设 |
| 2026-10-09 | 测试夹具用反应进度手算三个场景的出料，不经过任何求解器，也不用 HYSYS 的输出 | 元素和质量自然守恒、数值可手工核对；检查函数的测试不依赖被检查的东西 |
| 2026-10-09 | D1 标为完成：E0 的三个模型都返回 200，主模型的 `json_object` 和 `tools` 通过 | 用户 2026-10-08 的要求：先做最小连通性测试，通过后才把 D1 标为完成；通过条件是三个模型都能调通 |
| 2026-10-09 | 对正确快照逐字段破坏来探查检查的漏洞，并把结果变成测试（出料里任何一个数不对或缺失都被发现） | 提示词的难点：检查写得宽松，错误的模型也会“通过”；手写的失败用例只覆盖想到的破坏，逐字段探查能找到没想到的 |
| 2026-10-09 | 采纳独立审查的 V4、V2、结局判定、容差、工况名、编码、指标名、规则、重复等修复，不采纳的写明理由 | `CLAUDE.md`：审查的发现逐条处理，没有采纳的写明理由；详见“问题与解决” |
| 2026-10-09 | 用户要求“继续完成 1B 收尾”后，没有擅自在真实 HYSYS 上验证验证层，登记 D19 等用户决定；用户答复“现在就跑 D19”后，在 1B 里运行了 HYSYS（E16） | 1B 提示词写明“不运行 HYSYS”，这是用户的明确范围规定，所以先问；得到同意后才运行，结果见台账 L36 |
| 2026-10-09 | D18 按用户的答复修改：隔离测试看对 `GetValue`/`SetValue`/`GetValues`/`SetValues` 的调用，而不是逐个比字符串常量 | 用户答复“D18修改”；看调用比看字符串更准，不会把碳的分子式当成摄氏度，也不需要例外 |
| 2026-10-09 | 子代理审查和收尾体检放在三块都提交之后 | `CLAUDE.md`：每个阶段结束前做；审查对象是 `git diff` 的整体 |
| 2026-10-09 | 1C 的执行器：处理函数返回下一个状态或终态；失败统一抛 `ReactorAgentError`，`step()` 里唯一的 `except` 交给 `_recover` 查表；重试 = 留在当前状态从游标处继续；重试计数按位置算 | 三种恢复动作走同一条路，处理函数里没有 `try/except` 和计数；游标本来就要保存，续跑（阶段 4）几乎免费 |
| 2026-10-09 | 子代理的审查报告当作数据，逐条对照代码核实后再改；没有采纳的写明理由（1C 设计决定第 11 条） | `CLAUDE.md`：审查的发现逐条处理；报告里的断言（比如“覆盖上一个工况的文件”）自己读代码和写测试确认过，不是照做 |
| 2026-10-09 | 旧集成测试间歇性失败：先查原因（花了约 1 小时 20 分），查不出来就用文件级夹具规避，并登记 D20，不改旧测试的内容、不放宽容差 | 失败的是 HYSYS 的偶发行为，不是断言太严；放宽容差或重试测试会掩盖它 |

## 问题与解决

遇到的问题、试过的做法、最后的结论。走不通的尝试也记在这里，它们是考核报告"探索过程"一节的素材。

| 日期 | 问题 | 试过什么 | 结论 |
|---|---|---|---|
| 2026-10-03 | 阶段 0A 任务 1：助手执行命令的机器（主机名 WIN-607I4J4LV6S）不是装有 HYSYS 的工作站 | 在这台机器上查：注册表 HKCR 里没有 HYSYS/Aspen 的 ProgID，HKLM 下没有 AspenTech 键，没有 HYSYS 进程。这台机器上的 `mstsc.exe` 已经连着工作站的 3389 端口，所以远程桌面是通的，但助手的工具不经过这条连接，命令仍然在本机执行。本机的 `python` 是 Microsoft Store 占位程序，可用的解释器在 Anaconda（3.12，64 位），这只是本机的情况 | 暂停，等用户决定：在工作站上运行助手（推荐），或者用共享文件夹中转。**已解决**：用户改在工作站（myWin10VM，装有 Aspen HYSYS V15.0）上重开会话，2026-10-03 10:25 恢复，任务 1 重新核对通过 |
| 2026-10-03 | 输出被管道接走的 Python 进程打印中文报 `UnicodeEncodeError`（任务 2） | 去掉 `PYTHONIOENCODING` 和 `PYTHONUTF8` 复现：默认 cp1252。设 `PYTHONUTF8=1` 后正常 | `setx PYTHONUTF8 1`；探针脚本自己 `sys.stdout.reconfigure(encoding="utf-8")`。详见"环境事实" |
| 2026-10-03 | 想靠扫描示例 `.hsc` 的字节找出含反应器的 Case（任务 7 的预案） | 对 212 个文件按 ASCII 和 UTF-16 查 `conreactor`、`eqreactor`、`gibbsreactor` 等字符串，0 个命中 | 走不通：`.hsc` 是压缩格式，只能用 COM 打开并枚举单元操作。见台账 L0 |
| 2026-10-03 | 会话在 E1 之后因用量上限中断 | run1 按 `--exit keep` 留下了 HYSYS 实例；确认它没有打开 Case 后，run2 用 `--exit quit` 退出了它 | 无残留进程。剩余工作见"下一步" |
| 2026-10-08 | 用户的交接说明与仓库现状不符：说"没有 Git 仓库和台账、进度显示尚未开始"，实际已有 4 个提交、台账和 E1 的两次运行 | 核对 `git log`、台账、`spikes/out/`，并对照 `git diff` 发现工作区的 `progress.md`、`.gitignore` 是旧版 | 以已提交的版本为准，复用已完成的任务（见决策日志） |
| 2026-10-08 | 首次推送失败：`fatal: could not read Username for 'https://github.com'` | 先用 `git ls-remote` 确认远端是公开的、只有一个提交；`git credential-manager github list`、`cmdkey /list`、`gh auth status` 都没有凭据；再合并远端提交；用非交互模式推送，得到上面的错误；又在后台发起一次允许交互的推送，等用户在 VM 桌面上授权 | 认证拦截，没有任何内容到达远端。本地提交全部保留。需要用户登录一次（D10） |
| 2026-10-08 | 类型库完整导出 2.0 MB，超过单个文件 1 MB 的提交上限（任务 6） | 先把 533 个接口里重复的基础成员抽成公共组，仍有 1.6 MB；最后改成成员文件只写成员名（629 KB），完整签名只写反应相关的 111 个接口（212 KB）和关键词命中（74 KB） | 见台账 L4。想看某个接口的完整签名，查 `typelib_reaction_api.txt`；不在里面的，重新运行 `typelib_dump.py` 改一下 `RELEVANT_INTERFACE` |
| 2026-10-08 | 看检索结果时漏看了降级通道（任务 6） | 为了缩短显示，按"不以下划线开头"过滤命中行，把 `_SimulationCase`、`_Application` 上的 XML、`PlayScript` 全过滤掉了，一度以为 XML 路线只有 `SetStreamAssayFromXML` | 用不过滤的结果核对后，发现 `GetXMLForCase`、`ApplyXML`、`PlayScript`、`BackDoor` 都在，写进了台账 H24、H26 和"创建反应的线索" |
| 2026-10-08 | 第一次 `SimulationCases.Open` 失败：`com_error -2147352567 ... -2147024891`（E_ACCESSDENIED）（任务 7） | 副本在 `C:\Users\AZUREU~1\AppData\Local\Temp\...`（8.3 短路径），用 `shutil.copy2` 复制；改成 `shutil.copyfile`、`chmod` 可写、`Path.resolve()` 得到长路径后成功 | 同时改了三处，没有分开验证。E2 里单独验证短路径是不是原因；之后给 HYSYS 的路径一律先 `resolve()` |
| 2026-10-08 | 打开 Green Ammonia Process 时 `Open` 卡住（任务 7） | `_common.watch` 45 秒后打印 HYSYS 窗口：模态对话框 "To use Aspen Properties in HYSYS, at least one databank should be installed..."；用 `BM_CLICK` 点 OK 关闭；脚本被外层超时杀掉，实例用 `taskkill` 结束 | 这台机器没有注册 Aspen Properties 数据库，用到它的 Case 都会弹这个窗口。我们的流体包只用 HYSYS 自带物性包。台账 H23 记为部分确认 |
| 2026-10-08 | E2 第一次运行的求解器测试没有说明问题（任务 8） | 挂起求解器后只改了进料温度，而出料温度是规定值，出料本来就不变，分不清"没重算"和"挂起生效" | run2 改成改进料流量（出料流量随进料变）：挂起时出料不变，释放后同步更新。台账 H17 |
| 2026-10-08 | 8.3 短路径是不是 `Open` 失败的原因（任务 7 遗留，任务 8 验证） | 同一个副本、同一种复制方式，分别用"目录短名""目录和文件名都短""长路径"打开 | 短路径两种都 `E_ACCESSDENIED`，长路径成功。给 HYSYS 的路径先 `Path.resolve()`。台账 H2 |
| 2026-10-08 | `case.IsDirty` 在刚打开、没改过的 Case 上也是 True（任务 8） | E2b 三种情况都读到 True | 不能用 `IsDirty` 判断 Case 有没有改过；`Quit()` 和 `Close()` 本来就不弹保存确认，不需要它 |
| 2026-10-08 | E3 第一次运行在第二台反应器上崩溃（任务 9） | `Combustor` 没有连能流，`op.EnergyStream` 抛 `com_error`（E_FAIL），而脚本只捕获了 `AttributeError` | 加 `optional_attr`，把 `com_error` 当作"没有连接"。台账 H16 记了这个行为 |
| 2026-10-08 | `LnKSource` 读出 4，与类型库的枚举对不上（任务 9） | 示例里的平衡反应 Rxn-4 用的是 K–T 表（`ActivateKTable` 为 True），类型库里 `eqrxn_Table=3`、`eqrxn_FixedExtent=4`，读出的却是 4；`Basis` 读出 2 与枚举吻合 | **已解决（E6b，D11）**：实际取值 1 = Ln(K) 公式、2 = Gibbs 自由能（默认）、3 = 固定 K、4 = K–T 表；依据是 `Support\equirxn.rdf` 里界面分组的可见范围和新建反应的默认值（2）。类型库枚举名与实际取值对不上，不要用 |
| 2026-10-08 | 想靠 XML 导出创建或修改反应（任务 9，走不通） | `ProvideXMLForCase(0 或 1)` 6.5 MB，检索 'Stoich'、'rxnset'、'ReactionSet'、'LnK'、'Rxn-4'，全是 0 次 | XML 里没有反应和反应集的定义，只有反应器上引用反应名的部分。这条路线不能创建反应，在"创建反应的线索"里排最后 |
| 2026-10-08 | `fp.PropertyPackageName = "Peng-Robinson"` 抛 `E_INVALIDARG`（D11 的 E4） | 试了 10 种写法、先设组分列表再设物性包、`FluidPackages.Add(name, Type)` 传枚举值和字符串，都不行；没设物性包就保存，重开时弹模态对话框卡住 `Open` | 读示例 Case 的 `fp.PropertyPackage`：`TypeName` 是 `pengrob`、`VisibleTypeName` 是 `Peng-Robinson`；设置要用内部名 `pengrob`，成功。台账 H7 |
| 2026-10-08 | 把探针输出接给 `head` 之后，脚本被管道关闭打断，留下一个 HYSYS 实例（D11 的 E4 run1） | 用 `taskkill` 按进程号结束 | 以后运行探针一律把标准输出丢到 `/dev/null`，从 `spikes/out/` 的日志文件读结果（`Log` 本来就边打印边落盘） |
| 2026-10-08 | 写 `LnKSource = 0`（想设 Gibbs 自由能）读回仍是 2，一度以为设不上（D11 的 E6） | 逐个写 0 至 4：1 至 4 都读回原值，0 被忽略；读 `equirxn.rdf` 找界面分组的可见范围，得到真实对应 | 默认值 2 就是 Gibbs 自由能，不需要写。教训：类型库的枚举名不可信，枚举值要用 rdf 或实测核对。台账 H10、L13 |
| 2026-10-08 | 反应集排序（Conversion Rankings）写不进去（0B 任务 5） | 类型库和 `GetIDsOfNames`（14 个候选名字）没有成员；`ActiveReactions.Add(name, 数)` 第二个参数被忽略；`ApplyXMLForOperation` 在 12 种 `flags`/内容组合下，`flags` 没有 128 时返回 False 并把出口组成弄成各 0.2，带 128 时返回 True 但压降、进料温度、排序都不变；Case 级 `ApplyXML` 同样不变；BackDoor 用 `UniqueID`、IMoniker 显示名、复合 IMoniker 十几种写法，连值已知的进料温度都读不出（返回有效的包装，变量为空）。共 6 类做法、`e6c` 四次运行 | 走不通，没有降到第三、四级（需要用户配合）。含义改从 AspenTech 示例 Case 的排序值反推（Combustor 排序 (1,1,0)，实际转化率 18.09/33.60/48.31%）；Recipe 不设排序（H24、H26、H32，D13） |
| 2026-10-08 | 整份操作 XML 写回把 Case 弄坏（e6b 草稿） | 第一次写回带 windows-1252 声明，msxml 报 Invalid xml declaration；去掉声明后返回 False，进料组成变成各 0.2；之后每个写回实验都用新 Case，并在写回前后读进料组成和排序 | 台账 H26、鲁棒性观察：写回返回 True 不代表改了，写回之后必须读回 |
| 2026-10-08 | 用量额度在任务 5 中途用尽，会话被中断约 6 小时 | 中断前把停点写进本文件（做了什么、`e6c` 草稿还没运行、时间盒、"不要降级"），提交并推送 | 恢复后从停点接着做，没有重做；见上面 0B 时间表 |
| 2026-10-08 | 同名不同类型的 `Operations.Add` 使 HYSYS 进程崩溃（0C 任务 4，E11） | 在已有 `ERV-100` 的 Case 里再 Add 一个同名的 Gibbs 反应器：弹出 "Duplicate Object Name … Creating New Object ERV-100_2"，看门狗点 OK 后同一个对话框接连再弹 6 至 8 次，随后 `RPC call failed`、进程崩溃；怀疑是看门狗点得太快，改成同一个对话框 5 秒内只点一次，结果一样；第四次运行点一次就顺利建出 `ERV-100_2`，所以是偶发 | 台账 L26：创建类调用先按 `Names` 查，同名不同类型报冲突、绝不调 Add（R5、R7） |
| 2026-10-08 | 反应集排序一度被认为写不了（0B、0C 前半），后来 `PlayScript` 写成功 | 0C 任务 5 查脚本回放时读了安装目录 `Template\*.scp`，发现命令里的路径和变量写法与 XML 的 moniker 一致；手写 `Specify "<反应集路径>" ":Index.400.<序号>" <值>`，Case 隐藏时弹 "Could Not Find Target"，`case.Visible = True` 之后成功 | 台账 H24、H32、L29；教训：备选路线对照不是走过场，它补上了主路线的缺口 |
| 2026-10-08 | 终端工具开的新标签读不到用户配置的 `DASHSCOPE_API_KEY`，而且标签的 shell 集成加载失败，命令没有被输入 | 检查进程、用户、机器三级环境变量都没有；`run_in_terminal` 报 "Claude terminal integration did not load"，标签被关闭 | 密钥只设在用户自己的终端会话里，助手不碰；E0 探针写好，由用户运行（D1） |
| 2026-10-08 | E10 的 Gibbs 结果看起来合理但与温度无关（0C 任务 3） | 结果出来后没有直接接受：碳元素守恒误差 0、CO 收率 40.85% 都通过，但氢气恰好为 0、CH4 恰好是 CO 的一半。依次排除连接顺序、挂起求解器、碳和水分两股进料（结果完全相同），再排除气相热力学（不含碳、碳全部气化的两个对照，水煤气变换表观平衡常数一致，0.298 和 0.299），温度扫描 1000 至 1600 °C 组成不变，最后读组分库数据，发现碳的 `EvaluateGibbs(298.15 K)` 是 +671.3 kJ/mol（气态碳原子） | Gibbs 反应器不能直接处理库里的固体碳。登记 D14，等用户决定是否改用计划 §17.3 的两段式。台账 L24、L25 |
| 2026-10-08 | 弹窗看门狗的单元测试第一次失败：`guard.messages` 是空的（1A 任务 6） | 用 `EnumWindows` 把窗口全列出来：对话框确实在，但所有者进程号不是 `Popen.pid`。虚拟环境里的 `python.exe` 是个启动器，真正的解释器是它的子进程，对话框属于后者 | 看门狗没有问题，是测试写法的问题：让子进程自己打印 `os.getpid()` 再交给看门狗。台账 L32 |
| 2026-10-08 | pytest 在 `Quit()` 时打印 `Windows fatal exception: code 0x800706ba` | 先在 `conftest.py` 导入时调用 `faulthandler.disable()`，没用：pytest 在配置阶段才启用 faulthandler，我的调用太早 | 挪到会话级夹具里关掉。这个 RPC 异常是 `Quit()` 杀掉进程时的正常现象，Backend 已经处理了它 |
| 2026-10-08 | 集成测试有一次运行到一半，HYSYS 进程消失，后面 21 个测试都报 `E_COM_DISCONNECTED`（1A 任务 7） | 查 Windows 事件日志：当天（UTC 11:44 至 13:47）`aspenhysys.exe` 有 11 次 `HysysEng.dll` 访问冲突（`0xc0000005`）加 1 次堆损坏，其中 13:47:14 的一次就是这次测试；之后连跑 6 次完整集成测试没有再现 | HYSYS 自己的偶发缺陷，不是 Backend 的问题（错误被正确转成了 `E_COM_DISCONNECTED`）。对策：夹具自愈；阶段 4 的 `session.restart` 和执行器的 R1 要覆盖它。**不说已解决**。台账 L33 |
| 2026-10-09 | 收尾的独立审查（子代理，不带本阶段上下文）报告 8 条清单问题加 7 条额外发现 | 逐条对照代码验证；`ToolExecutor(register_tools(...))` 过不了 mypy 这一条用 `MYPYPATH=src` 的 mypy 复现确认了（测试不过 mypy，所以之前没暴露，1C 装配时才会炸） | 采纳 14 项并修复（提交 41f4fdf、7015316）：装配类型错误；先校验再创建（不留空物流）；读回 `EndBasisChange`、`CanSolve`、`Close`；流体包已存在但 Basis 没结束要报冲突；每个工具调用外层再套一层 COM 异常转换；连接中途失败和另存失败不留孤儿实例和 Case；`connect` 发现旧会话进程没了就重连；重复的 `Item(0)` 等抽进 `lookup.py`；位置元组改成 `SaveData` 和冻结的 dataclass；读回的值不符合契约时转领域错误；注释里的具体体系名；新增无 HYSYS 的单元测试和“只在一个文件里”的隔离检查。**没有采纳**：非领域异常也发 Trace 事件（程序缺陷没有可记录的结果）；COM 返回 None 的防御（推测，没有证据）；`NOT_FOUND`、`IO` 用于确定性的前置错误（可重试集合按计划 §13.2 定）；建一半失败的清理（计划规定由上层丢弃 Case）；集成测试里复刻三个场景（提示词要求，那条不变量针对 `src/` 和 `skills/`） |
| 2026-10-09 | `test_hysys_backend_isolation.py` 报 `recipes/gibbs.py: 'C'` 和 `validation/checks.py: 'kW'`（1B） | 那个检查按字符串常量逐个比，不分上下文：碳的分子式 `"C"` 和说明文字里的 `"kW"` 都被当成单位 | `"kW"`：说明文字里去掉单位（变量名 `duty_kw` 本来带单位）。`"C"`：先写成解析反应式字符串来躲开，独立审查指出这是为过检查而写挤；改回四个具名常量并加一处带原因的例外，登记 D18；用户答复修改后，规则改成看调用（`GetValue` 一类的方法只能在 `variables.py` 里调用），例外删除（提交 509ee02） |
| 2026-10-09 | 逐字段破坏三个场景的正确快照，210 处没有任何检查发现（1B 收尾） | 脚本对每股物流的每个字段、每个组分的每个字段，分别改大 5%（原来是 0 的改成 0.05）和设为 `None`，再跑全部检查 | 出料的总流量、各组分的质量流量、没有流量的出料里混进的流量，原来都没有检查。V6 加物流内部一致性后剩 101 处，都是有意不查的量（设计决定第 16 条）。把“出料里任何一个数不对或缺失都被发现”写成测试 |
| 2026-10-09 | 独立审查（子代理）报告：V4、V2、专有检查的期望取自计划，`decide_outcome` 不核对检查是否齐全，空相出料的约定没有用真实快照验证 | 逐条对照代码，用临时脚本复现（工况 800 °C 而计划和快照 710 °C，V4 通过；`checks=()` 的结果判 COMPLETE；`decide_outcome([], [])` 判 COMPLETE） | 复现属实的都修复了（提交 bcbae41、66e9b57）；空相约定先登记 D19，用户同意后在真实快照上验证，没有误报（台账 L36）。审查提的另一类问题——不确定的两条（空相约定、固体的 Gibbs 自由能平衡常数）里，后一条按台账 L25 的证据加了规则，但只在 Gibbs 反应器上验证过 |
| 2026-10-09 | 验证层只在手算的快照上试过，不知道真实 HYSYS 快照会不会误报（D19） | 用户同意后写 `spikes/e16_validation_real_snapshots.py`，用生产的 Backend 和 `ToolExecutor` 执行 Recipe 的计划，把真实快照喂给 V1 至 V8；运行 1 次 | 一次通过，没有需要改验证层的地方：空相出料读回 0.0，V6 的分子量偏差最大 5.1e-05（容差 1e-3），V7 最大相对误差 2.1e-05。没有踩到任何坑，说明 1A 的 Backend、1B 的 Recipe 和验证层之间的约定是一致的。台账 L36 |
| 2026-10-09 | D1 的连通性测试要用户在自己的终端里输入密钥（助手的进程读不到环境变量） | 探针加 `--ask-key`（`getpass` 不回显，没有控制台时不等待，密钥只留在进程内存里）；助手在每个提交点看输出文件的修改时间，等用户运行 | 已解决：用户 2026-10-09 10:08 运行，三个模型都返回 200，`json_object` 和 `tools` 通过（台账 L35）；旧的无密钥输出不提交，提交的是这次的输出 |
| 2026-10-09 | 用户的交接说明与仓库现状不符（1C 开始时）：说“progress.md 写明下一步是 phase-0a.md、没有 Git 仓库和台账”，同一条消息最后又说“目前进行到 1C（未做）” | 核对 `git log`（0A 至 1B 的 60 多个提交都在）、`git remote`（`origin` 已配置、与用户给的地址一致）、进度文件和台账 | 以进度文件和仓库为准，做 1C，不重做 0A；记在“当前状态”里 |
| 2026-10-09 | 执行器测试里平衡反应器的场景失败（V4：出口温度应为 600 °C，实测 710 °C） | 规格有两个工况，桩只给了第一个工况的快照；检查正确地发现读到的状态和规格不符 | 测试的问题，不是执行器的：桩按“第 n 次求解之后读第 n 份快照”，场景给出每个工况各一份 |
| 2026-10-09 | 全量集成测试间歇性失败（旧的 1A、1B 测试，执行器自己的测试从不失败） | 逐项排除 CPU 满载、并发 pytest、内存句柄 GDI、单纯的 Case 数量、时间、重新打开 `.hsc` 的步骤、契约测试的类别；失败时转储 HYSYS 的状态，结构全对但反应器没有算；写了会话草稿里的转储和统计插件（没有提交）| 根因没有查明；每个测试文件一个新的 HYSYS 实例之后连续通过。台账 L38，D20 |
| 2026-10-09 | 独立审查发现：中止时 `case.save()` 不带路径是原地保存，会用失败工况的状态覆盖上一个已验证工况的 `.hsc`（`FailureReport.case_path` 还把这个被覆盖的文件标成“供检查”） | 读 `cases.save_case` 确认 `SaveAs` 之后 `FullName` 变成新路径、不带路径的保存写回当前路径；原来的测试只断言最后一个调用是 `case.save`，不看入参 | 另存到 `work/failed.hsc`；单元测试断言保存的路径，真实 HYSYS 上的测试重新打开两个文件核对温度（710 和 600） |
| 2026-10-09 | 用命令行工具的 heredoc 写 Python 脚本改文件，字符串里的双反斜杠被合并成一个，换行转义变成了真正的换行：把 `observability/render.py` 里的一个字符串字面量弄断（语法错误），后来又弄坏进度文件里的一行 | 读字节确认文件里是真换行；用正则和按偏移替换重写，因为同一个原因没有生效；用编辑工具一次修好 | 改含反斜杠的行一律用编辑工具；ruff 和 mypy 立刻就能发现这类语法错误，没有进入提交 |

## 与计划的偏差

实现与 `MASTER_PLAN.md` 不一致的地方，以及原因。

| 日期 | 计划中的说法 | 实际做法 | 原因 |
|---|---|---|---|
| 2026-10-08 | §16.4 E3：在 GUI 里手工建好含三种反应器的参考 Case 再反向探测 | 先用自带示例 Synthesis Gas Production 探测转化和平衡反应器、反应、反应集；Gibbs 部分等用户手工建的 Case（D11） | 示例里没有 Gibbs 反应器，不想让探测等人 |
| 2026-10-08 | §16.2 H3、H9 等把"新建"归给 E4 至 E6 | E2 里顺带验证了新建物流（`MaterialStreams.Add`）和写组成，H12、H14 已部分确认 | 为了读"没有规定的变量"必须新建一股物流，结果可以直接用 |
| 2026-10-08 | 0B 提示词任务 5：把排序设成依次，用 0.573 判断排序的含义 | 没有做到：排序不能用代码写入；并行的 0.5000 已验证，含义改从示例 Case 的排序值反推 | 见"问题与解决"；提示词允许任务 5 受阻时推后，这里是走不通而不是推后 |
| 2026-10-08 | 0B 提示词任务 1（E4）、任务 3（E6）单独成脚本做 | 在 0A 的 D11 里已经完成，0B 没有重做 | 用户指示 D11 由助手自行创建参考 Case，创建链提前跑通 |
| 2026-10-08 | 0B 提示词"不要降到第三、四级" | 没有降级；第二级（XML、BackDoor）试了，没有走通 | 排序不是 G0 的组成部分，G0 全部是第 1 级 |
| 2026-10-08 | 0C 提示词任务 3：`e10` 满足四个通过条件，或者把不满足的现象和证据交给用户 | 不满足，已交给用户（D14）；还额外做了根因诊断（E10b、E10c）和两段式的可行性证据（E10d，没有采用） | Gibbs 反应器 + 库里的碳算错 |
| 2026-10-08 | 0C 提示词任务 5：LLM 视觉操作（如果有屏幕操作工具） | 未试验 | 本会话只有浏览器窗格里的页面操作工具，没有操作桌面应用的工具 |
| 2026-10-08 | 阶段 0A 任务 4（E0）等用户给出 LLM 信息后做 | 用户已给，但助手的进程读不到密钥变量，探针写好待用户运行，未标完成 | 见 D1 |
| 2026-10-08 | §9.1/§9.2 共 13 个工具，含 `session.restart` | 本阶段 12 个，`session.restart` 留给阶段 4 | 1A 提示词：属于后面的加固阶段 |
| 2026-10-08 | §9.3 结果信封有 `readback` 和 `duration_ms` | 都没有：读回比对在工具内部，不一致就是失败；耗时在 `ToolCallEvent` 里 | 1A 提示词 |
| 2026-10-08 | §9.3 `flowsheet.set_spec` 的入参有“单位” | 没有 `unit`，单位由变量名决定（`outlet_temperature_c`、`duty_kw`） | 规范单位固定，少一处单位错误 |
| 2026-10-08 | §9.3 `flowsheet.ensure_reactor` 的入参有“Gibbs 模式”，`basis.ensure_reaction_set` 有“流体包”，`model.read_snapshot` 有“对象列表” | 都没有 | 1A 提示词：入参只有类型、连接、反应集、压降和热模式；本阶段只有一个流体包；只做全量读取。Gibbs 默认是纯自由能最小化（H31） |
| 2026-10-08 | §9.3 / R6 `solver.solve` 的超时“由看门狗线程结束进程” | `timeout_s` 只覆盖“求解器还在求解”的轮询等待，没有强制结束进程 | COM 调用不能被中断；强制结束属于恢复策略（R1），留给阶段 4。COM 调用本身卡死而又不是弹窗时目前没有保护 |
| 2026-10-08 | §17.3 / 1A 提示词：Gibbs 反应器（含固体碳）一台反应器 | 按 D14 方案 A，转化反应器 + Gibbs 反应器两段式 | D14（用户 2026-10-08 答复），台账 L24、L25 |
| 2026-10-09 | §23.2 / 1B 提示词：Recipe 的 `compile(规格)`、`checks(规格, 工况, 快照)`，Recipe 有 `type` 属性 | `compile(spec, components)`、`checks(context)`；没有 `type` 属性，反应器类型到 Recipe 的对应只在注册表里 | 含固体碳的 Gibbs 要知道哪个组分是固体和分子量；专有检查要用计划里的对象名，`CheckContext` 就是提示词要求的冻结上下文；类型只写一处 |
| 2026-10-09 | 1B 提示词：`recipes/base.py` 放“接口和注册表” | 注册表在 `recipes/__init__.py` | 三个 Recipe 要导入 `base.py`，注册表又要导入三个 Recipe，放在 `base.py` 里会循环导入 |
| 2026-10-09 | §17.3 / 1B 提示词的场景 3 构建表：一台 Gibbs 反应器，8 步 | 两段式 14 步：转化反应器 `CRV-100` + Gibbs 反应器 `GBR-100`，两段的出料、能流各自编号（`Vap-1`、`Liq-1`、`Q-1`、`Vap-2`……） | D14（用户 2026-10-08 答复）；提示词说台账里确认过的调整优先 |
| 2026-10-09 | §12.3 V4 “转化率等于设定” | 作为 Recipe 的专有检查 `V4-conversion`（以及固定 K 的 `V4-fixed-k`），不放在通用的 V4 里 | 提示词：专有检查在 Recipe 里，通用检查在验证层 |
| 2026-10-09 | 1B 提示词：Recipe 的规则“Gibbs 反应器的组分表要覆盖进料里的每一种元素” | 理解为：进料里的每种元素至少出现在一个非固体的组分里；另外规定不在进料里的固体不能出现在 Gibbs 的组分表里 | 固体不能作为 Gibbs 反应器的产物（库里碳的热力学数据，台账 L25）；这样组分表里的相态才用得上 |
| 2026-10-09 | §12.3 V6：摩尔分率非负且和为 1，流量非负 | 另加物流内部一致性：各组分流量之和等于总流量，组分质量流量等于摩尔流量乘分子量（相对 1e-3），摩尔分率等于流量占比 | 逐字段破坏的探查发现这些量没有任何检查；报告同时展示它们 |
| 2026-10-09 | §12.3 V2/V4：期望的对象和规定取自 `ModelSpec` | V2 另外核对计划里的流体包和反应与规格一致；V4 取规格里的当前工况值，对计划里每台反应器都成立 | 计划是 Recipe 编译出来的，期望取自计划等于让编译错误自己通过；独立审查指出 |
| 2026-10-09 | §7.5 完成判定 | `decide_outcome` 另外要求每个结果含 V1 至 V8、结果属于这个工况、至少有一个工况 | 否则执行器漏跑一项检查任务也“完成”；独立审查指出 |
| 2026-10-09 | 1B 提示词：指标请求的名字没有规定 | 收率的名字带基准，如“CO 收率（以 Carbon 计）” | 同一产物、不同基准的两个收率不会重名 |
| 2026-10-09 | 1B 提示词：“本阶段不做：不运行 HYSYS” | 用户 2026-10-09 答复“现在就跑 D19”之后运行了 HYSYS：E16 探针和 10 个集成测试，并重跑了 1A 的 39 个集成测试 | 验证层只在手算的快照上试过是独立审查指出的最大风险；先问了用户，得到同意后才运行 |
| 2026-10-09 | §10.2 TaskState：`run_id`、`selection`、`task_spec`、`plan`（含步骤列表）、`hysys.resources`、`budget`、`validation` | 只有 1C 有来源的字段：任务标识、规格文件、规格哈希、工况名、状态、终态、已完成步骤的记录、游标、会话（版本、进程号、当前 Case 文件）、工况序号、重试和重建计数、各工况摘要、错误记录；完整的规格、计划、结果在 `artifacts/` | 提示词：状态文件只存摘要，续跑和 LLM 产物的字段用到时再加 |
| 2026-10-09 | §14.1 事件：`run_id`、`skill` | 去掉；加 `case`（SOLVE/VERIFY 里的工况名，时间线用它写成 `SOLVE[T710]`） | 提示词：去掉现在没有来源的；时间线要按工况分组 |
| 2026-10-09 | §7.3 RECOVER 是一个状态；提示词：“工具调用事件通过 1A 在 ToolExecutor 上留的回调接入” | RECOVER 是 `_recover` 一次函数调用加两个 Trace 事件（错误、恢复决定）；工具调用事件由执行器自己发，不用回调 | 见设计决定第 5 条 |
| 2026-10-09 | 提示词：REPORT“写 result.json”，VERIFY“组装这个工况的结果” | `result.json` 在每个工况验证后增量写，REPORT 只补终态 | 工况的结果要在 VERIFY 和 REPORT 之间保存下来，状态文件不存完整结果；中止时也要留下已有的结果 |
| 2026-10-09 | 提示词：1C 的 `--spec` 读 YAML 或 `artifacts/model_spec.json` | 一致；`load_model_spec` 按扩展名读 JSON 或 YAML，已用测试和 E17 的重跑验证 | — |
| 2026-10-09 | 1C 提示词：每一步的执行记录有“状态” | `StepRecord` 没有状态字段，只记做完了的步骤 | 状态永远是“完成”，没有信息；失败的那一步（工具名和入参）记在错误记录里 |
| 2026-10-09 | 1C 提示词：没有 Recipe 直接进入 `UNSUPPORTED`，不经过策略表；规则不通过以 `E_RULE` 中止 | 没有 Recipe 也抛 `E_UNSUPPORTED` 由 `_recover` 处理（不在表里，结果相同）；规则里只要有一条是 `E_UNSUPPORTED` 就是 `UNSUPPORTED`，Backend 抛 `E_UNSUPPORTED` 也是；退出码 3 | 计划 §7.3“PLAN --unsupported--> UNSUPPORTED”；原来 Recipe 里的“不支持”被压成 `E_RULE`，终态是 `FAILED`（独立审查指出） |
| 2026-10-09 | 1C 提示词的运行目录：`*.hsc` 每个工况求解后的 Case | 多了 `work/`：建模用的 `working-<n>.hsc` 和中止时的 `failed.hsc` | 不和工况名撞名；中止时原地保存会覆盖已验证工况的文件 |
| 2026-10-09 | 1C 提示词：整个测试会话共用一个 HYSYS 连接，不要每个测试启动一次 | 每个测试文件一个实例 | 长会话里偶发不求解或不反应的模型（台账 L38），D20 |
| 2026-10-09 | 1C 提示词：不在计划里的调用（连接、求解、读快照、保存）也是执行器的步骤 | 这些调用只在 Trace 里，状态文件的步骤记录只有计划里的步骤 | 计划里没有它们；它们不影响游标 |
| 2026-10-09 | 1C 提示词的策略表：`E_NOT_SOLVED` 属于“其余全部”，直接中止（计划 §13.2：收集对象状态 → Recipe 的确定性补救 → R3 → R5） | `E_NOT_SOLVED` 不重试、重建一次、再中止 | 用户 2026-10-09 同意（D20）；HYSYS 偶发建出不求解的模型（台账 L38） |
