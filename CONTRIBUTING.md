# Contributing

Thank you for improving `payment-router`. Small, reviewable changes with clear
evidence are preferred.

## Local setup

```bash
git clone https://github.com/qinhzy/payment-router.git
cd payment-router
uv sync --dev
uv run pytest -x
uv run ruff check .
uv run ruff format --check .
uv build
```

Python 3.11, 3.12, and 3.13 are tested in CI.

## Before opening a pull request

- Add tests for behavior changes and provider response variants.
- Keep every fee, time, and FX value explicitly classified.
- Update `docs/DATA_SOURCES.md` when changing any external fact or assumption.
- Use a primary source for `VERIFIED` or `INDUSTRY_AVERAGE` claims.
- Label incomplete evidence `ESTIMATED`; do not infer certainty from a provider
  name or from an AI-generated summary.
- Preserve the simulator disclaimer and avoid production-transfer claims.
- Do not add account systems, payment execution, compliance decisions, or a web
  service to an MVP change.

## Adding a network

A network implementation belongs in `src/payment_router/networks/` and must:

1. implement `PaymentNetwork`;
2. return `NetworkQuote` or `None` for an unsupported corridor;
3. classify fee, time, and FX independently;
4. fail with a concise provider-specific error;
5. include deterministic mocked tests for success, rejection, malformed data,
   and timeout behavior;
6. add its evidence records and documentation.

## Pull request scope

Explain what changed, why it belongs in the teaching model, user-visible impact,
data-source changes, and the commands used for validation. Avoid bundling
unrelated cleanup with a feature or fix.
