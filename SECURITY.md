# Security policy

## Supported code

This project is pre-1.0. Security fixes target the latest `main` branch and the
most recent tagged release when a safe backport is practical.

## Reporting a vulnerability

Use GitHub private vulnerability reporting for this repository when available.
If that option is unavailable, open a minimal issue asking the maintainer for a
private reporting channel. Do not include exploit details, secrets, personal
data, or an unpatched proof of concept in a public issue.

Include the affected version or commit, impact, reproduction conditions, and a
suggested mitigation if known. Reports should receive an initial response on a
best-effort basis within seven days.

## Scope notes

The repository never processes real credentials or funds. Reports about code
execution, dependency compromise, unsafe parsing, secret exposure, CI workflow
permissions, or misleading security/financial claims are in scope. Differences
between simulated and real bank pricing are model-quality issues unless they
also create a security impact.
