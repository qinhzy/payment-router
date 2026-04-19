# payment-router

`payment-router` 是一个教学/研究型的跨境汇款路由模拟器 CLI，用于演示不同支付网络下的费用、时效和路径选择；它不是生产系统，所有费率与时效数据都必须带有明确来源标记。

## 安装与运行

```bash
uv sync --dev
uv run payment-router --help
uv run pytest -x
```
