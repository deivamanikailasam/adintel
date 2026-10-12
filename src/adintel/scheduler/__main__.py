"""``python -m adintel.scheduler`` — APScheduler in the brand's timezone.

| Job | When | Why |
|-----|------|-----|
| Weekly brand run | Mon 02:00 brand-local + 0–89 min stagger | Report by 08:00 local |
| Retry failed runs | Mon 06:00 brand-local | "All platforms down → retry at 06:00" |
| Audit chain verification | daily 03:30 UTC | Tamper evidence (P1 on break) |
| Execution reconciliation | daily 04:00 UTC | Executed == approved (P1 on mismatch) |
| Campaign narratives | daily 01:00 UTC | Numbers → sentences for RAG |
| Expire recommendations | hourly | Stale approvals |
| DLQ check | every 5 min | P2 when depth > 0 |
| Cost anomaly | daily 23:30 UTC | P3 on > 2× day-over-day |
| Outcome tracking | daily 05:00 UTC | Actual vs predicted impact, 14 days after execution |
| Weekly triage | Mon 09:00 UTC | What humans should look at next week |
| Retention purge | daily 02:30 UTC | Delete what the catalogue says we no longer need (legal hold respected) |
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from adintel.config import get_settings
from adintel.feedback.outcomes import outcomes_job
from adintel.feedback.triage import triage_job
from adintel.observability.logging import configure_logging
from adintel.privacy.retention import retention_job
from adintel.scheduler import jobs
from adintel.storage import get_database

log = logging.getLogger("adintel.scheduler")


def build(scheduler: BlockingScheduler) -> None:
    db = get_database()
    window = get_settings().schedule_stagger_minutes
    for b in jobs.active_brands(db):
        tz = (b.get("profile") or {}).get("timezone", "UTC")
        offset = jobs.stagger_minutes(b["tenant_id"], b["brand_id"], window)
        at = datetime(2000, 1, 1, 2, 0) + timedelta(minutes=offset)
        scheduler.add_job(
            jobs.trigger_brand_run,
            CronTrigger(day_of_week="mon", hour=at.hour, minute=at.minute, timezone=tz),
            args=[db, b["tenant_id"], b["brand_id"]],
            id=f"run:{b['tenant_id']}:{b['brand_id']}",
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
        )
        scheduler.add_job(
            jobs.trigger_brand_run,
            CronTrigger(day_of_week="mon", hour=6, minute=offset % 30, timezone=tz),
            args=[db, b["tenant_id"], b["brand_id"]],
            id=f"retry:{b['tenant_id']}:{b['brand_id']}",
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
        )
    scheduler.add_job(jobs.verify_audit_job, CronTrigger(hour=3, minute=30, timezone="UTC"), args=[db], id="audit")
    scheduler.add_job(jobs.reconcile_job, CronTrigger(hour=4, minute=0, timezone="UTC"), args=[db], id="reconcile")
    scheduler.add_job(jobs.narratives_job, CronTrigger(hour=1, minute=0, timezone="UTC"), args=[db], id="narratives")
    scheduler.add_job(jobs.expire_recommendations_job, CronTrigger(minute=5), args=[db], id="expire")
    scheduler.add_job(jobs.dlq_check_job, CronTrigger(minute="*/5"), id="dlq")
    scheduler.add_job(jobs.cost_anomaly_job, CronTrigger(hour=23, minute=30, timezone="UTC"), args=[db], id="cost")
    scheduler.add_job(retention_job, CronTrigger(hour=2, minute=30, timezone="UTC"), args=[db], id="retention")
    scheduler.add_job(outcomes_job, CronTrigger(hour=5, minute=0, timezone="UTC"), args=[db], id="outcomes")
    scheduler.add_job(
        triage_job, CronTrigger(day_of_week="mon", hour=9, minute=0, timezone="UTC"), args=[db], id="triage"
    )


def main() -> None:
    os.environ.setdefault("ADINTEL_PROCESS_ROLE", "scheduler")
    s = get_settings()
    configure_logging(s.log_level, s.log_json)
    sched = BlockingScheduler(timezone="UTC")
    build(sched)
    for j in sched.get_jobs():
        log.info("job_scheduled", extra={"job": j.id, "trigger": str(j.trigger)})
    sched.start()


if __name__ == "__main__":
    main()
