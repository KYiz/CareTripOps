"""Prometheus metrics: request rate and latency per route, and the state of the work the service owes people."""

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.core import GaugeMetricFamily
from sqlalchemy import func, select

from app.db import Case, HelpRequest, Job, Notification, Order, ReviewTask, SessionLocal

registry = CollectorRegistry()
REQUESTS = Counter("caretrip_http_requests_total", "HTTP requests", ["method", "route", "status"], registry=registry)
LATENCY = Histogram("caretrip_http_request_seconds", "HTTP request duration", ["method", "route"], registry=registry,
                    buckets=(0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10))


def observe(method: str, route: str, status: int, seconds: float) -> None:
    REQUESTS.labels(method, route, str(status)).inc()
    LATENCY.labels(method, route).observe(seconds)


class StateCollector:
    """Read at scrape time from the database, so the numbers hold however many API and worker processes run."""

    def collect(self):
        with SessionLocal() as session:
            def grouped(name, help_text, model, column, *where):
                family = GaugeMetricFamily(name, help_text, labels=["status"])
                for status, count in session.execute(select(column, func.count()).select_from(model).where(*where)
                                                     .group_by(column)).all():
                    family.add_metric([status], count)
                return family

            yield grouped("caretrip_jobs", "Workflow runs by status", Job, Job.status, Job.status.in_(("QUEUED", "RUNNING")))
            yield grouped("caretrip_notifications", "Emails waiting or given up on", Notification, Notification.status,
                          Notification.status.in_(("PENDING", "FAILED")))
            yield grouped("caretrip_cases", "Trips by status", Case, Case.status)
            yield grouped("caretrip_orders", "Orders by status", Order, Order.status)
            for name, help_text, value in (
                ("caretrip_open_reviews", "Evidence reviews waiting for an advisor",
                 session.scalar(select(func.count()).select_from(ReviewTask).where(ReviewTask.status == "OPEN"))),
                ("caretrip_open_help_requests", "Help requests no advisor has picked up",
                 session.scalar(select(func.count()).select_from(HelpRequest).where(HelpRequest.acknowledged_at.is_(None)))),
                ("caretrip_oldest_queued_job_seconds", "Age of the oldest queued run",
                 session.scalar(select(func.coalesce(func.extract("epoch", func.now() - func.min(Job.created_at)), 0))
                                .where(Job.status == "QUEUED")) or 0),
            ):
                yield GaugeMetricFamily(name, help_text, value=float(value))


registry.register(StateCollector())


def render() -> bytes:
    return generate_latest(registry)
