# AGENTS

## 项目目标

一句话目标：构建一个面向教学与研究的跨境汇款路由模拟器 CLI，用可追溯的数据来源演示不同支付网络下的路径、费用与时效权衡。

## 范围

- 三个 network：`wise`、`sepa`、`swift`
- 四个货币：当前默认 `USD`、`EUR`、`GBP`、`CNY`
- 支持输出 Mermaid 路由可视化
- 本地 Web 控制台（`remit serve`）：FastAPI API + 静态单页前端
- 可插拔 FX 汇率源：默认冻结教学表；`--fx live` 使用 ECB 参考汇率快照，
  离线时显式回退并降级标注
- 时效区间模型与敏感性分析：每跳携带 [min, max] 时效边界（SEPA 采用
  scheme 上限语义，SWIFT 场景带登记的波动带），`remit sensitivity` 与
  Web 面板展示权重扫描的翻转边界与均衡稳定区间
- 可选 AI 解读：仅在 Anthropic 凭证可解析时启用；解读必须严格基于控制台
  展示的 JSON，保留教学模拟器免责声明，不得编造数字
- 不做用户系统

## 技术栈与版本

- Python `>=3.11`
- `uv` 管理依赖与运行
- `networkx` 用于图算法
- `typer` 用于 CLI
- `pydantic v2` 用于数据模型
- `httpx` 仅用于后续 Wise 网络请求
- `fastapi` + `uvicorn` + `anthropic` 仅在可选 `web` extra 中，用于本地
  Web 控制台与可选 AI 解读
- `pytest` + `pytest-httpx` 用于测试
- `ruff` 用于 lint

## 目录约定

- `src/payment_router/networks/`：各支付网络实现与抽象基类
- `src/payment_router/core/models.py`：`Hop`、`Route`、`NetworkQuote` 等核心模型
- `src/payment_router/core/fx.py`：可插拔 FX 汇率源（冻结教学表 + ECB 实时快照）
- `src/payment_router/core/graph.py`：从 networks 构造 `networkx` 图
- `src/payment_router/router.py`：路由算法
- `src/payment_router/service.py`：CLI 与 Web 共享的请求校验与路由会话服务层
- `src/payment_router/provenance.py`：可审计的数据来源与假设注册表
- `src/payment_router/visualizer.py`：Mermaid 输出与共享数字格式化
- `src/payment_router/cli.py`：Typer CLI 入口
- `src/payment_router/web/`：FastAPI 应用、JSON 序列化与静态前端资源
- `tests/`：镜像 `src/` 的测试结构

## 数据诚信原则

- 每条费率、时效、汇率数据都必须显式标注 `data_source`
- 允许的来源级别只有：`VERIFIED`、`INDUSTRY_AVERAGE`、`ESTIMATED`
- fee、time、FX 分项标注；quote 汇总等级必须等于三者中可信度最低者
- 禁止使用未标注来源的数据进入模型、测试或示例
- 对外说明时必须注明这是 simulator，不代表真实生产报价或清算承诺

## 路由不变量

- 平行支付网络必须保留为独立边，top-N 不得按货币节点路径合并
- 同币种支付网络使用 self-loop；不得把实际转账静默当成零费用换汇
- 每条候选路径必须按逐跳余额重放，余额无法覆盖下一跳费用时拒绝该路径
- Mermaid 中间余额必须使用与 router 相同的逐跳计算公式

## 工作规则

- 每次任务只修改与当前需求直接相关的文件
- 每次改动完成后必须运行 `pytest -x`
- 新增 network 时必须同时补齐对应的 mock 测试
- 核心包不得引入新的运行时第三方依赖；Web 控制台依赖必须留在可选
  `web` extra 中；依赖范围以 `pyproject.toml` 为准
- 前端静态资源必须自包含，不得引入 CDN 或外部请求

## 非目标

- 不对接真实资金通道或生产清算网络
- 不提供用户注册、登录、权限或账户系统
- 不提供后台管理界面或在线服务部署；Web 控制台仅面向本地运行
- 不承诺真实费率、真实到账时间或合规校验结果
