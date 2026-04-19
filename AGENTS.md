# AGENTS

## 项目目标

一句话目标：构建一个面向教学与研究的跨境汇款路由模拟器 CLI，用可追溯的数据来源演示不同支付网络下的路径、费用与时效权衡。

## MVP 范围

- 三个 network：`wise`、`sepa`、`swift`
- 四个货币：当前默认 `USD`、`EUR`、`GBP`、`CNY`
- 支持输出 Mermaid 路由可视化
- 不做用户系统
- 不做 Web UI

## 技术栈与版本

- Python `>=3.11`
- `uv` 管理依赖与运行
- `networkx` 用于图算法
- `typer` 用于 CLI
- `pydantic v2` 用于数据模型
- `httpx` 仅用于后续 Wise 网络请求
- `pytest` + `pytest-httpx` 用于测试
- `ruff` 用于 lint

## 目录约定

- `src/payment_router/networks/`：各支付网络实现与抽象基类
- `src/payment_router/core/models.py`：`Hop`、`Route`、`NetworkQuote` 等核心模型
- `src/payment_router/core/graph.py`：从 networks 构造 `networkx` 图
- `src/payment_router/router.py`：路由算法
- `src/payment_router/visualizer.py`：Mermaid 输出
- `src/payment_router/cli.py`：Typer CLI 入口
- `tests/`：镜像 `src/` 的测试结构

## 数据诚信原则

- 每条费率、时效、汇率数据都必须显式标注 `data_source`
- 允许的来源级别只有：`VERIFIED`、`INDUSTRY_AVERAGE`、`ESTIMATED`
- 禁止使用未标注来源的数据进入模型、测试或示例
- 对外说明时必须注明这是 simulator，不代表真实生产报价或清算承诺

## 工作规则

- 每次任务只修改与当前需求直接相关的文件
- 每次改动完成后必须运行 `pytest -x`
- 新增 network 时必须同时补齐对应的 mock 测试
- 不得引入新的第三方依赖；依赖范围以 `pyproject.toml` 为准

## 非目标

- 不对接真实资金通道或生产清算网络
- 不提供用户注册、登录、权限或账户系统
- 不提供 Web UI、后台管理界面或在线服务部署
- 不承诺真实费率、真实到账时间或合规校验结果
