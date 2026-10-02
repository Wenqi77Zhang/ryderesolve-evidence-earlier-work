# 项目基线 v0.1 · 2026-10-02

## 目标与分工

琪琪负责 Evidence/Data + tools。队友分别负责 Advocate system、Judge/Orchestration + evaluation UI。本仓库为琪琪这一模块的私有开发和交付仓库，不冒充团队完整作品。

团队选定场景：Route Deviation 与 No-Show Charge，属于 Digital Native / Ryde 赛道。用户已授权直接实现、创建 GitHub 私有仓库并同步上传。

## 已确定的团队约定（BASE）

- 整体目标：选择案例 → 整理证据 → 双方 Agent 陈述与回应 → Judge → 引用检查及 UI。
- 先接入官方 DISP-002，再补充同一输出接口的 synthetic Route Deviation。
- `case_id / evidence_id / evidence_refs / policy_refs / decision` 不改名。
- Evidence 保留 `facts[].evidence_id / fact / source`；Advocate 保留 `side / claims[].claim / claims[].evidence_refs`；Judge 保留 `decision / findings[].finding / findings[].evidence_refs / findings[].policy_refs`。
- `policy[].policy_id` 沿用原始草案，用来解析规则引用。
- 无来源时引用数组可空，禁止编造编号；有陈述来源时可引用该陈述，但不能把陈述本身视为已核实的事实。

## 来自手册的要求（REQ）

来源：腾讯云赛事官网及邮件所链接的 42 页手册，读取于 2026-10-02。

- 第 22、24 页：三个核心 Agent；至少两类争议的可运行流程；评委能观察 Agent 之间的信息交流。
- 第 24 页：真实 API 不可用时允许模拟 API/数据；高级 Agent 与多模态属于扩展目标。
- 第 25 页列出原型、架构图、演示、GitHub 源码等交付建议，同时保留鼓励替代实现的说明。
- 第 36 页：原创项目，至少使用 CodeBuddy 或 WorkBuddy；必须提供真实使用证明，提交清单要求至少 3 张开发对话截图或相应录屏。Codex 开发记录不能冒充这些产品的使用证明。
- 实际提交表写明截止时间为 2026-10-16 23:59 GMT+8。

来源链接见 `PROVENANCE.md`。本仓库只覆盖上述要求中的证据与工具部分。

## 本轮实现选择（INST）

- Python 3.12+、标准库运行时；项目独立 `.venv`；提供 Python/CLI/HTTP 三种接入方式。
- 事实生成采用固定模板与确定性计算，不用 LLM 改写原始证据。
- 核心 Evidence Pack 不新增必填字段；来源定位、分类、版本、核对问题通过附加查询返回。
- 官方 JSON 与模型输入之外的预期裁决分目录；runtime 只加载 catalog 允许的 JSON 文件。
- 用 SHA-256 标识原始 JSON 的语义版本；引用在同一 case_id 和来源版本内稳定。
- 合成路线仅用于功能联调；计算采样折线长度，不调用真实地图服务，不宣称最短/最优路线。
- 本地证据核对台仅用于该模块调试；它没有实现队友的多轮交互或 Judge。

## 待确认（TBD）

1. 团队最终语言和框架；现有 HTTP/JSON 接口可先跨语言接入。
2. `decision` 完整取值、金额单位、confidence 含义及转人工阈值；本模块不擅自冻结这些业务约定。
3. 官方 no-show 等待计时从订单字段、App 计时事件还是其他事件开始。
4. Route Deviation 官方数据与政策是否补发；目前只有团队自设的联调规则。
5. 团队总流程中的“一轮陈述＋一轮回应”：当前简化流程表只列了 Rider → Driver → Judge，需要编排同学补全回应阶段。`counterpoints` 扩展采用与 claim 相同的条目结构；轮次元数据放在编排事件中，不改核心字段。
6. 团队共享仓库及协作者权限、与两位队友的实际联调、比赛工具使用证明。

## 完成边界

本模块完成意味着：两类数据能被读取、规范化、回查来源、计算指标，并能检查队友输出中的编号引用；测试和 HTTP 调用通过。

不等于整个比赛系统完成，不等于裁决正确率已验证，也不等于已符合比赛所有提交条件。验证状态见 `VALIDATION.md`。
