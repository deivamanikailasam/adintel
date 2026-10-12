"""``adintel`` command line: seed, demo, run, verify-audit, reconcile, expire, models, token, outcomes, triage, flags, purge,
privacy-export, privacy-erase, offboard,
audit-archive, backup, restore, restore-drill."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from typing import Any


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_seed(args: argparse.Namespace) -> None:
    from adintel.seed.catalog import seed
    from adintel.storage import get_database

    _print(seed(get_database(), with_kb=not args.no_kb))


def cmd_demo(args: argparse.Namespace) -> None:
    """One night in production, end to end, in this process."""
    from adintel.graph.engine import RunEngine
    from adintel.seed.catalog import seed
    from adintel.storage import get_database

    db = get_database()
    seed(db)
    end = (
        date.fromisoformat(args.period_end)
        if args.period_end
        else date.today() - timedelta(days=date.today().weekday() + 1)
    )
    engine = RunEngine(db)
    for brand in args.brands.split(","):
        s = engine.run(
            tenant_id="brightwave",
            brand_id=brand,
            period_start=end - timedelta(days=6),
            period_end=end,
            trigger="demo",
            schedule_date=date.today(),
        )
        if s is None:
            print(f"{brand}: already ran for this period (idempotent); use a different --period-end")
            continue
        print(
            f"\n=== {s.brand_name}: {s.status}  ({s.usage.steps} steps, ${s.usage.cost_usd:.4f} notional, "
            f"{s.usage.tokens} tokens)"
        )
        for t in s.traces:
            print(f"  {t.step:>2}. {t.agent:<13} {t.status:<8} {t.summary}")
        for d in s.degradations:
            print(f"  ! {d.code}: {d.detail}")
        for r in s.recommendations:
            print(
                f"  → recommendation {r.recommendation_id}: {r.action_type} ${r.amount_usd_per_day:.2f}/day "
                f"(exposure ${r.daily_exposure_usd:.2f}, risk {r.risk}) — pending approval"
            )
        if s.abort_reason:
            print(f"  ✋ {s.abort_reason}")


def cmd_run(args: argparse.Namespace) -> None:
    from adintel.graph.engine import RunEngine
    from adintel.storage import get_database

    end = date.fromisoformat(args.period_end)
    s = RunEngine(get_database()).run(
        tenant_id=args.tenant, brand_id=args.brand, period_start=end - timedelta(days=6), period_end=end, trigger="cli"
    )
    _print({"status": s.status if s else "already_ran", "run_id": s.run_id if s else None})


def cmd_verify(args: argparse.Namespace) -> None:
    from adintel.scheduler.jobs import verify_audit_job
    from adintel.storage import get_database

    out = verify_audit_job(get_database())
    _print(out)
    sys.exit(1 if out["broken"] else 0)


def cmd_reconcile(args: argparse.Namespace) -> None:
    os.environ.setdefault("ADINTEL_PROCESS_ROLE", "executor")
    from adintel.scheduler.jobs import reconcile_job
    from adintel.storage import get_database

    out = reconcile_job(get_database())
    _print(out)
    sys.exit(1 if out["mismatches"] else 0)


def cmd_expire(args: argparse.Namespace) -> None:
    from adintel.scheduler.jobs import expire_recommendations_job
    from adintel.storage import get_database

    _print({"expired": expire_recommendations_job(get_database())})


def cmd_models(args: argparse.Namespace) -> None:
    from adintel.llm.providers.openai_compat import OpenAICompatProvider
    from adintel.llm.registry import get_registry

    reg = get_registry()
    out = {}
    for name, tier in reg.tiers.items():
        h = OpenAICompatProvider.shared().health(tier)
        out[name] = {
            "model_id": tier.model_id,
            "base_url": tier.base_url,
            "ok": h.get("ok"),
            "served": h.get("models"),
            "error": h.get("error"),
        }
    _print(out)


def cmd_token(args: argparse.Namespace) -> None:
    from adintel.approvals.service import load_user
    from adintel.security.auth import issue_token
    from adintel.storage import get_database

    print(issue_token(load_user(get_database(), args.tenant, args.user)))


def cmd_outcomes(args: argparse.Namespace) -> None:
    from adintel.feedback.outcomes import outcomes_job
    from adintel.storage import get_database

    _print(outcomes_job(get_database(), today=date.fromisoformat(args.today) if args.today else None))


def cmd_triage(args: argparse.Namespace) -> None:
    from adintel.feedback.triage import render_markdown, weekly_triage
    from adintel.storage import get_database

    r = weekly_triage(get_database(), args.tenant, days=args.days)
    if args.format == "json":
        _print(r)
    else:
        print(render_markdown(r))


def cmd_flags(args: argparse.Namespace) -> None:
    from adintel.harness.flags import FeatureFlags
    from adintel.storage import get_database

    flags = FeatureFlags(get_database(), args.tenant)
    if args.set:
        name, _, value = args.set.partition("=")
        flags.set(
            name, value.lower() in ("1", "true", "on"), actor_id=args.actor, reason=args.reason, brand_id=args.brand
        )
    _print(flags.effective(brand_id=args.brand))


def cmd_purge(args: argparse.Namespace) -> None:
    from adintel.privacy.retention import plan, purge
    from adintel.storage import get_database

    _print(
        {"plan": plan(), "deleted" if not args.dry_run else "would_delete": purge(get_database(), dry_run=args.dry_run)}
    )


def cmd_privacy_export(args: argparse.Namespace) -> None:
    from adintel.privacy.subjects import export_user
    from adintel.storage import get_database

    _print(export_user(get_database(), args.tenant, args.user, actor_id=args.actor))


def cmd_privacy_erase(args: argparse.Namespace) -> None:
    from adintel.privacy.subjects import erase_user
    from adintel.storage import get_database

    _print(erase_user(get_database(), args.tenant, args.user, actor_id=args.actor, reason=args.reason))


def cmd_offboard(args: argparse.Namespace) -> None:
    from pathlib import Path

    from adintel.privacy.offboarding import offboard_tenant
    from adintel.storage import get_database

    _print(
        offboard_tenant(
            get_database(),
            args.tenant,
            confirm=args.confirm,
            actor_id=args.actor,
            out_dir=Path(args.out),
            keep_legal_records=not args.delete_legal_records,
        )
    )


def cmd_audit_archive(args: argparse.Namespace) -> None:
    from adintel.audit.archive import archive_job, compare_with_database
    from adintel.storage import get_database
    from adintel.storage.tenant_repo import SystemRepo

    db = get_database()
    if not args.verify:
        out = archive_job(db)
        _print(out)
        sys.exit(1 if out["mismatched"] else 0)
    tenants = sorted({r["tenant_id"] for r in SystemRepo(db, "audit_log", purpose="audit archive").find({})})
    checks = [compare_with_database(db, t).__dict__ for t in tenants]
    _print(checks)
    sys.exit(0 if all(c["ok"] for c in checks) else 1)


def cmd_backup(args: argparse.Namespace) -> None:
    from pathlib import Path

    from adintel.ops.backup import backup, restore_drill
    from adintel.storage import get_database

    out = backup(get_database(), Path(args.out))
    if not args.no_drill:
        out["drill"] = restore_drill(Path(out["path"]))
    _print(out)
    sys.exit(0 if out.get("drill", {"passed": True})["passed"] else 1)


def cmd_restore(args: argparse.Namespace) -> None:
    from pathlib import Path

    from adintel.ops.backup import restore
    from adintel.storage import get_database

    out = restore(get_database(), Path(args.source), force=args.force)
    _print(out)
    sys.exit(0 if out["audit_chains_ok"] else 1)


def cmd_restore_drill(args: argparse.Namespace) -> None:
    from pathlib import Path

    from adintel.ops.backup import restore_drill

    out = restore_drill(Path(args.source))
    _print(out)
    sys.exit(0 if out["passed"] else 1)


def main(argv: list[str] | None = None) -> None:
    from adintel.config import get_settings
    from adintel.observability.logging import configure_logging

    s = get_settings()
    configure_logging(s.log_level if os.environ.get("ADINTEL_LOG_LEVEL") else "WARNING", s.log_json)
    p = argparse.ArgumentParser(prog="adintel", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("seed", help="load synthetic tenants, brands, users, rules and knowledge base")
    sp.add_argument("--no-kb", action="store_true")
    sp.set_defaults(fn=cmd_seed)
    sp = sub.add_parser("demo", help="run one night for the canonical brands in-process")
    sp.add_argument("--brands", default="urban-roast,fitely,northpeak")
    sp.add_argument("--period-end", help="YYYY-MM-DD (a Sunday); default: last Sunday")
    sp.set_defaults(fn=cmd_demo)
    sp = sub.add_parser("run", help="run one brand now")
    sp.add_argument("--tenant", default="brightwave")
    sp.add_argument("--brand", required=True)
    sp.add_argument("--period-end", required=True)
    sp.set_defaults(fn=cmd_run)
    sub.add_parser("verify-audit", help="verify every tenant's audit hash chain").set_defaults(fn=cmd_verify)
    sub.add_parser("reconcile", help="compare executed changes with approvals").set_defaults(fn=cmd_reconcile)
    sub.add_parser("expire", help="expire stale recommendations").set_defaults(fn=cmd_expire)
    sub.add_parser("models", help="check the mlx-lm servers behind each tier").set_defaults(fn=cmd_models)
    sp = sub.add_parser("token", help="issue a JWT for a seeded user (local only)")
    sp.add_argument("--tenant", default="brightwave")
    sp.add_argument("--user", required=True)
    sp.set_defaults(fn=cmd_token)
    sp = sub.add_parser("outcomes", help="grade executed changes 14 days later (actual vs predicted)")
    sp.add_argument("--today", help="YYYY-MM-DD; default: today")
    sp.set_defaults(fn=cmd_outcomes)
    sp = sub.add_parser("triage", help="weekly triage report: what humans should look at next")
    sp.add_argument("--tenant", default="brightwave")
    sp.add_argument("--days", type=int, default=7)
    sp.add_argument("--format", choices=("md", "json"), default="md")
    sp.set_defaults(fn=cmd_triage)
    sp = sub.add_parser("flags", help="show or set per-tenant/brand feature flags")
    sp.add_argument("--tenant", default="brightwave")
    sp.add_argument("--brand")
    sp.add_argument("--set", help="flag=on|off, e.g. agent.optimizer=off")
    sp.add_argument("--actor", default="cli:operator")
    sp.add_argument("--reason", default="set from CLI")
    sp.set_defaults(fn=cmd_flags)
    sp = sub.add_parser("purge", help="enforce retention periods from the collection catalogue")
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(fn=cmd_purge)
    for name, fn, helptext in (
        ("privacy-export", cmd_privacy_export, "export everything held about one user (access request)"),
        ("privacy-erase", cmd_privacy_erase, "pseudonymise one user and delete their chats and notes"),
    ):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--tenant", default="brightwave")
        sp.add_argument("--user", required=True)
        sp.add_argument("--actor", default="cli:privacy-officer")
        sp.add_argument("--reason", default="data subject request")
        sp.set_defaults(fn=fn)
    sp = sub.add_parser("offboard", help="export then delete one tenant's data (agency leaves)")
    sp.add_argument("--tenant", required=True)
    sp.add_argument("--confirm", required=True, help="type the tenant id again")
    sp.add_argument("--out", default="offboarding")
    sp.add_argument("--actor", default="cli:operator")
    sp.add_argument("--delete-legal-records", action="store_true", help="also delete approvals/executions/audit")
    sp.set_defaults(fn=cmd_offboard)
    sp = sub.add_parser("audit-archive", help="copy new audit entries to write-once storage, or --verify")
    sp.add_argument("--verify", action="store_true", help="compare the database with the archive")
    sp.set_defaults(fn=cmd_audit_archive)
    sp = sub.add_parser("backup", help="logical backup of every collection (+ automatic restore drill)")
    sp.add_argument("--out", default="backups")
    sp.add_argument("--no-drill", action="store_true")
    sp.set_defaults(fn=cmd_backup)
    sp = sub.add_parser("restore", help="restore a logical backup (refuses a non-empty database without --force)")
    sp.add_argument("source")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(fn=cmd_restore)
    sp = sub.add_parser("restore-drill", help="prove a backup restores cleanly, without touching live data")
    sp.add_argument("source")
    sp.set_defaults(fn=cmd_restore_drill)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
