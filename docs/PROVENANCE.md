# 来源、数据与贡献

## 外部来源

- 官方赛事页：<https://tch.tencentcloud.com/contest/44>
- 用户邮件所链接的 42 页参赛手册：<https://drive.google.com/file/d/1W894c8ISZvOD4tYsAtQyTFypV5N5HDbS/view>
- 用户提供的 DISP-002 样例：<https://drive.google.com/file/d/1f6KAuu5ZFqBKHvsAVlg-ZC_FgHazbqNF/view>
- 提交入口：<https://forms.gle/CPV5HQELE4x83eBc6>

读取日期：2026-10-02。官方数据如更新，应重新核对来源及差异。本仓库不附加开放许可来替代原始材料的权利归属；数据仅作为私有参赛开发输入保留。

## 本次贡献边界

- 琪琪：提供需求、团队分工和接口约定，负责 Evidence/Data + tools。
- 队友：提供初始流程和 Advocate/Judge 草案；对应模块及正式评估 UI 的实现归属队友，尚未在本仓库验证。
- Codex：在琪琪授权下辅助实现本模块、构造标注的 synthetic 联调用例、编写文档和测试。
- 官方 DISP-002：来源于用户提供的样例，不声称由琪琪或 Codex 原创。

手册要求的 CodeBuddy/WorkBuddy 使用证据尚未取得；不得把本次 Codex 记录改标为这些工具的使用记录。

## 私有与数据最小化

仓库保持 Private；不自动邀请协作者。`.venv`、凭据、个人邮件截图、WhatsApp 群链接均不纳入提交。生产乘客数据不在本轮范围内。

本地服务只绑定 127.0.0.1，拒绝外部 Host/Origin，响应禁用缓存，不记录请求体或源数据日志。需要真实业务数据和外部部署时，另行设计鉴权、授权、留存及脱敏流程。
