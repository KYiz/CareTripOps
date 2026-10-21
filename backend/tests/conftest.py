"""Point the suite at a dedicated database before any app module reads settings.

When TEST_DATABASE_URL is set (Compose sets it), tests use that database, create it if needed and
migrate it, so they never write into the demo database or race the running worker service.
Without it (CI), DATABASE_URL is already a throwaway database.
"""
import os

# Tests are hermetic: the supplier simulator runs in-process (reset per test) and payments are simulated
# unless a test swaps in another provider. Never touch the running supplier container or real Stripe.
os.environ["SUPPLIER_BASE_URL"] = ""
os.environ["PAYMENT_PROVIDER"] = "simulated"
os.environ.pop("STRIPE_SECRET_KEY", None)
os.environ["REDIS_URL"] = ""  # Per-process limiters; test_ratelimit exercises Redis via TEST_REDIS_URL.

test_url = os.environ.get("TEST_DATABASE_URL")
if test_url:
    os.environ["DATABASE_URL"] = test_url
    try:
        import psycopg
        from sqlalchemy.engine import make_url

        url = make_url(test_url)
        admin = url.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False)
        with psycopg.connect(admin, autocommit=True) as conn:
            if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (url.database,)).fetchone():
                conn.execute(f'CREATE DATABASE "{url.database}"')
        from alembic import command
        from alembic.config import Config

        command.upgrade(Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini")), "head")
    except Exception as exc:  # Unit tests still run; integration tests skip without a database.
        print(f"Test database unavailable: {exc}")


import pytest


@pytest.fixture
def override_settings(monkeypatch):
    """Replace settings everywhere at once: in app.config and in every app module that imported them."""
    def apply(**changes):
        import dataclasses
        import sys
        import importlib
        importlib.import_module("app.main")  # Load every module holding a reference first.
        from app import config

        current = config.settings
        updated = dataclasses.replace(current, **changes)
        for name, module in list(sys.modules.items()):
            if (name == "app" or name.startswith("app.")) and getattr(module, "settings", None) is current:
                monkeypatch.setattr(module, "settings", updated)
        return updated
    return apply


@pytest.fixture
def integration_mode(monkeypatch, override_settings):
    """Keep database acceptance tests independent of live Gemini quota and output."""
    import app.api.common as common
    from app.payments import set_payments
    from app.ratelimit import SlidingWindowLimiter
    from app.suppliers import set_supplier
    from supplier_sim.app import reset as reset_supplier

    override_settings(model_mode="mock_llm", case_create_limit_per_ip=10_000, case_create_limit_global=10_000,
                      login_code_limit_per_email=10_000, login_code_limit_per_ip=10_000, auth_dev_return_code=True,
                      embedded_worker=True, worker_poll_seconds=0.05)
    monkeypatch.setattr(common, "case_limiter", SlidingWindowLimiter())
    monkeypatch.setattr(common, "login_limiter", SlidingWindowLimiter())
    reset_supplier()
    set_supplier(None)
    set_payments(None)
    monkeypatch.setenv("GEMINI_PLANNING_ENABLED", "false")
