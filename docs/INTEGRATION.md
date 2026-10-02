# 队友接入说明

## 1. 原始输入 → Evidence Pack

```python
from ryderesolve_evidence import EvidenceTools, normalize_evidence

tools = EvidenceTools()
raw = tools.load_case("DISP-002")
evidence_pack = normalize_evidence(raw)
audit = tools.audit_case("DISP-002")
```

`raw` 是官方 JSON 中的记录，不包含外部 Markdown 的答案或 Evidence Summary。`normalize_evidence(raw)` 返回 JSON 可序列化的字典；运行时不需要模型、网络或密钥。

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
- 0 confidence 且明确标记不转人工，会得到警示。此处不伪造校准概率，也不擅自决定业务阈值。
- 缺少时间/证据等属于 `audit.requires_policy_or_data_review`；它与输出是否满足 JSON 字段规范分别报告。

## 3. 编排同学的建议接入顺序

1. `load_case` 读取原始 JSON。
2. `normalize_evidence` 获取 pack；同时读取 `audit_case`，保留数据问题和 `source_sha256`。
3. 把 raw、pack、相关审计问题传给双方 Agent；陈述视为当事人主张，历史档案视为背景。
4. 执行团队约定的陈述/回应轮次，保留可展示的交互记录。
5. Judge 同时读取原始证据、双方论点与政策；处理未澄清问题。
6. `validate_outputs` 检查返回格式和编号，UI 通过引用查询原文。

```python
result = tools.validate_outputs(
    "DISP-002",
    advocate=advocate_output,
    judge=judge_output,
    expected_source_sha256=audit["source_sha256"],
)
assert result["structurally_valid"], result["errors"]
# 仍需检查 warnings、requires_policy_or_data_review，以及论证本身是否成立。
```

## 4. 可调用工具

| 工具 | 输入 | 返回 |
|---|---|---|
| list_cases | 无 | 案例 ID、数据/政策来源标签 |
| load_case | case_id | 原始 JSON |
| normalize_evidence | case_id（工具调用形式） | Evidence Pack |
| get_evidence | case_id、evidence_id，可选 expected_source_sha256 | fact、类型、来源路径及原文 |
| get_policy | case_id、policy_id，可选 expected_source_sha256 | rule、政策来源及原文 |
| audit_case | case_id | 来源版本、冲突、缺失信息、确定性计算 |
| compare_route | case_id | 采样路线长度和超出比例，不输出裁决 |
| validate_outputs | case_id、advocate 和/或 judge，可选 expected_source_sha256 | 格式/引用错误、警示与数据审计状态 |

`GET /tool-specs` 提供可供模型工具注册使用的参数描述。它是普通 JSON 工具定义，不是已经部署的 MCP 服务。框架适配由队友按实际框架封装这些只读函数即可。

## 5. HTTP（任何语言都可调用）

启动：`python -m ryderesolve_evidence serve --port 8765`。仅监听 `127.0.0.1`。

| 方法与路径 | 用途 |
|---|---|
| GET /cases | 案例列表 |
| GET /cases/DISP-002 | Evidence Pack |
| GET /cases/DISP-002/raw | 原始 JSON |
| GET /cases/DISP-002/audit | 来源和数据问题 |
| GET /cases/DISP-002/evidence/E-002 | 查看乘客陈述来源 |
| GET /cases/DISP-002/policies/P-001 | 查看规则原文 |
| GET /cases/SYN-ROUTE-001/route-comparison | 路线计算 |
| GET /contracts/evidence-pack.schema.json | 字段规范；另有 advocate/judge 版本 |
| POST /tools/validate_outputs | 只读校验；Content-Type: application/json |
| POST /tools/{name} | 表中工具的通用只读调用 |

```javascript
const pack = await fetch('http://127.0.0.1:8765/cases/DISP-002').then(r => r.json());
const source = await fetch('http://127.0.0.1:8765/cases/DISP-002/evidence/E-002').then(r => r.json());
```

开发环境允许 HTTP localhost / 127.0.0.1 来源；外部 Origin 与非本机 Host 会被拒绝。输入错误返回 400，未知路径 404，不支持的媒体类型 415，过大工具请求 413。本服务用于本地开发，不能直接用作生产互联网服务。

## 6. 编号与版本

引用有效范围是 **case_id + source_sha256 + evidence_id/policy_id**。在同一来源版本内，重复规范化和 JSON 对象键重排不会改变编号。来源内容或数组顺序变更后，版本改变，需要重新运行下游 Agent。

持久化 UI 记录时保存来源版本，回查时传 `expected_source_sha256`（HTTP GET 参数名为 `source_sha256`）。编号查询不做模糊匹配；不存在、跨来源版本的引用会报错。

`source_refs` 使用从 0 开始的 JSON 数组索引，例如 `/gps_telemetry/4`；不会使用含糊的 `gps_telemetry[4..7]` 字符串。

## 7. 更换数据

保留旧版本用于复现；新增原始 JSON 并更新 catalog 来源说明。不要将 synthetic 文件改名成官方案例。Route Deviation 原始输入包含 `reference_route / fare_breakdown / route_policy`，与 No-Show 的政策字段不同，但生成的 Evidence Pack 相同。

官方样例答案只位于 `evaluation/`。不要将整份原始 Markdown、评估答案或历史预期结果一并拼入模型提示词。
