"""Prometheus metrics: per-route request counts and the state of queued work."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import postgres_available

pytestmark = pytest.mark.skipif(not postgres_available(), reason="Migrated PostgreSQL is unavailable")


def test_metrics_count_routes_by_template_and_report_open_work(override_settings):
    with TestClient(app) as client:
        client.get("/healthz")
        client.get("/api/cases/00000000-0000-0000-0000-000000000000")  # 401, recorded under the route template.
        client.get("/no/such/page")
        body = client.get("/metrics").text
        assert 'caretrip_http_requests_total{method="GET",route="/healthz",status="200"}' in body
        assert 'route="/api/cases/{case_id}",status="401"' in body
        assert 'route="unmatched"' in body and "/no/such/page" not in body
        for gauge in ("caretrip_open_reviews", "caretrip_open_help_requests", "caretrip_oldest_queued_job_seconds"):
            assert gauge in body
        override_settings(metrics_token="s3cret")
        assert client.get("/metrics").status_code == 401
        assert client.get("/metrics", headers={"Authorization": "Bearer s3cret"}).status_code == 200
