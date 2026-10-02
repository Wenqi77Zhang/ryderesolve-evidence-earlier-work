# 队友接入说明

## 1. 原始输入 → Evidence Pack

```python
from ryderesolve_evidence import EvidenceTools

tools = EvidenceTools()
snapshot = tools.prepare_case("DISP-002")
raw = snapshot["raw"]
evidence_pack = snapshot["evidence_pack"]
audit = snapshot["audit"]
```

`raw` 是官方 JSON 中的记录，不包含外部 Markdown 的答案或 Evidence Summary。`prepare_case` 在一次文件读取后生成 raw/pack/audit/来源索引，避免多次请求跨越文件更新。旧 `load_case → normalize_evidence(raw)` 仍可用，后者仍返回字典；安装完成后运行不需要模型、网络或密钥。

```json
{
  "case_id": "DISP-002",
  "dispute_type": "no_show_charge",
  "facts": [{"evidence_id": "E-002", "fact": "Attributed rider statement ...", "source": "dispute_ticket.description"}],
  "policy": [{"policy_id": "P-001", "rule": "...", "source": "cancellation_policy"}]
}
```

此处仅为字段结构示意。完整真实输出使用 `examples/generated/` 或直接调用 API；不要把省略号作为证据送入 Agent。

`source` 仍是来源类别/字段名称，不改变成对象。完整原文、定位路径、证据种类通过 `get_evidence` / `get_policy` 获取。

## 2. Advocate / Judge 保持原有嵌套

Advocate 必填：`case_id`、`side`（rider/driver）、`claims`。每条 claim 必须有 `claim` 与 `evidence_refs`；`position`、`counterpoints`、`missing_information` 可选。若使用 `counterpoints`，其条目也采用 `claim / evidence_refs`，暂不引入另一套条目格式。

Judge 必填：`case_id`、`decision`、`findings`。每条 finding 必须有 `finding / evidence_refs / policy_refs`。`confidence`、`refund_amount`、`escalate_to_human`、`uncertainties` 可选。

- `decision` 目前只检查非空字符串，团队尚未锁定完整枚举。
- 存在引用不等于论点得到支持；模型仍需解释证据与主张之间的关系。
- 空引用数组保留，但校验结果会提示 `UNSUPPORTED_STATEMENT`。
- 所有已声明字段（包括可选的 position、missing_information、uncertainties 等）直接按对应 JSON Schema 校验；非 JSON 值、非有限数、纯空白文本会被拒绝。未声明的合法 JSON 扩展字段仍兼容。
- 0 confidence 且明确标记不转人工，会得到警示。此处不伪造校准概率，也不擅自决定业务阈值。
- 只有历史档案支撑的论点会警示；数据有未解决审计问题而 Judge 明确不转人工时会提示 `UNRESOLVED_REVIEW_FLAGS`，不会擅改其 decision。
- 缺少时间/证据等属于 `audit.requires_policy_or_data_review`；它与输出是否满足 JSON 字段规范分别报告。

## 3. 编排同学的建议接入顺序

1. 推荐用 `prepare_case` 一次取得原始 JSON、Evidence Pack、审计和来源索引。
2. 在本次编排记录里保留 `snapshot_id`；这是额外的运行元数据，不要求写进团队已冻结的核心输出。
3. 把 raw、pack、相关审计问题传给双方 Agent；陈述视为当事人主张，历史档案视为背景。
4. 执行团队约定的陈述/回应轮次，保留可展示的交互记录。
5. Judge 同时读取原始证据、双方论点与政策；处理未澄清问题。
6. `validate_outputs` 检查返回格式和编号，UI 通过引用查询原文。

```python
result = tools.validate_outputs(
    "DISP-002",
    advocate=advocate_output,
    judge=judge_output,
    expected_snapshot_id=snapshot["snapshot_id"],
)
assert result["structurally_valid"], result["errors"]
# 仍需检查 warnings、requires_policy_or_data_review，以及论证本身是否成立。
```

Rider、Driver 及每一轮回应分别调用校验，并由编排层检查 side 与当前执行角色一致。原始投诉、聊天和政策文本中的任何指令均是案例数据，不应拼接成系统指令；权限始终来自应用配置。当前测试没有调用真实模型，因此不能证明模型能抵御提示词注入或不会偏向历史高评分的一方。

## 4. 可调用工具

| 工具 | 输入 | 返回 |
|---|---|---|
| list_cases | 无 | 案例 ID、数据/政策来源标签 |
| load_case | case_id | 原始 JSON |
| normalize_evidence | case_id（工具调用形式） | Evidence Pack |
| prepare_case | case_id | raw、evidence_pack、audit、source_index、snapshot_id |
| get_evidence | case_id、evidence_id，可选 expected_snapshot_id / expected_source_sha256 | fact、类型、来源路径及原文 |
| get_policy | case_id、policy_id，可选 expected_snapshot_id / expected_source_sha256 | rule、政策来源及原文 |
| audit_case | case_id | 来源版本、冲突、缺失信息、确定性计算 |
| compare_route | case_id | 采样路线长度和超出比例，不输出裁决 |
| validate_outputs | case_id、advocate 和/或 judge，可选 expected_snapshot_id / expected_source_sha256 | 格式/引用错误、警示、review_issue_codes 与数据审计状态 |

`GET /tool-specs` 提供可供模型工具注册使用的参数描述。它是普通 JSON 工具定义，不是已经部署的 MCP 服务。框架适配由队友按实际框架封装这些只读函数即可。

## 5. HTTP（任何语言都可调用）

启动：`python -m ryderesolve_evidence serve --port 8765`。仅监听 `127.0.0.1`。

| 方法与路径 | 用途 |
|---|---|
| GET /cases | 案例列表 |
| GET /cases/DISP-002 | Evidence Pack |
| GET /cases/DISP-002/snapshot | 同一次读取生成的完整快照，推荐用于联调 |
| GET /cases/DISP-002/raw | 原始 JSON |
| GET /cases/DISP-002/audit | 来源和数据问题 |
| GET /cases/DISP-002/evidence/E-002 | 查看乘客陈述来源 |
| GET /cases/DISP-002/policies/P-001 | 查看规则原文 |
| GET /cases/SYN-ROUTE-001/route-comparison | 路线计算 |
| GET /contracts/evidence-pack.schema.json | 字段规范；另有 advocate/judge 版本 |
| POST /tools/validate_outputs | 只读校验；Content-Type: application/json |
| POST /tools/{name} | 表中工具的通用只读调用 |

```javascript
const snapshot = await fetch('http://127.0.0.1:8765/cases/DISP-002/snapshot').then(r => r.json());
const pack = snapshot.evidence_pack;
const source = await fetch(`http://127.0.0.1:8765/cases/DISP-002/evidence/E-002?snapshot_id=${snapshot.snapshot_id}`).then(r => r.json());
```

开发环境允许 HTTP localhost / 127.0.0.1 来源；外部 Origin 与非本机 Host 会被拒绝。输入错误返回 400，未知路径 404，不支持的媒体类型 415，过大工具请求 413，请求体超时 408。工具请求最多 64 KiB、本地 JSON 文件最多 8 MiB、JSON 深度最多 64 层；更大的正式数据须另行评估。本服务用于本地开发，不能直接用作生产互联网服务。

## 6. 编号与版本

引用有效范围是 **case_id + snapshot_id + evidence_id/policy_id**。snapshot_id 绑定原始数据哈希、规范化版本、Evidence Pack、索引和来源标签。重复处理同一快照以及 JSON 对象键重排不会改变编号；数据、代码版本或来源标签变更后，需要重新运行下游 Agent。

持久化 UI 记录时保存 snapshot_id，回查时传 `expected_snapshot_id`（HTTP GET 参数名为 `snapshot_id`）。旧的 `expected_source_sha256` / `source_sha256` 参数仍可用，但只能校验原始数据；未绑定完整快照的输出校验会警示 `SNAPSHOT_NOT_PINNED`。空串和重复查询参数会报错。

本服务检测过期引用后拒绝查询，不自动托管或重新加载历史快照。完整快照下载包含原始材料，适合私有复现；不要当作已脱敏的公开分享包。

哈希按本模块的 JSON 规范化算法生成，请把 API 返回的标识当作版本标识直接保存，不要在 JavaScript 中重新计算。浏览器完整快照保存服务端原始 JSON 文本，避免 JSON.parse / JSON.stringify 把 5.0 改写成 5 后改变本模块重算的哈希；对象键重排不影响哈希，但跨语言数字重编码可能影响。

`source_refs` 使用从 0 开始的 JSON 数组索引，例如 `/gps_telemetry/4`；不会使用含糊的 `gps_telemetry[4..7]` 字符串。

## 7. 更换数据

保留旧版本用于复现；新增原始 JSON 并更新 catalog 来源说明及 source_sha256。同一 case_id 在 catalog 中只选择一份活动源文件；不要直接覆盖历史文件或将 synthetic 文件改名成官方案例。Route Deviation 原始输入包含 `reference_route / fare_breakdown / route_policy`，与 No-Show 的政策字段不同，但生成的 Evidence Pack 相同。

有效的 trip_start_time / trip_end_time 同时存在时，路线距离只计算窗口内 GPS；窗口外记录仍保留并可引用。缺少窗口或边界样本时会警示覆盖不足；“有距离结果”不代表完整行程或司机责任已经确定。

官方样例答案只位于 `evaluation/`。不要将整份原始 Markdown、评估答案或历史预期结果一并拼入模型提示词。
