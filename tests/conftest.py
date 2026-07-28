"""Shared test setup.

``Route`` carries a forward reference to ``RoutingPreference``, which lives in
``router.py`` to keep the model layer free of a dependency on the routing
layer. The rebuild that resolves it therefore runs on ``router`` import, so a
test subset that never imports the router (``pytest tests/core/``) would fail
to construct a ``Route`` at all. Importing it here makes every subset behave
like the full run.
"""

from __future__ import annotations

import payment_router.router  # noqa: F401
