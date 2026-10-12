"""``adintel`` command line: seed, demo, run, verify-audit, reconcile, expire, models, token."""

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
    end = date.fromisoformat(args.period_end) if args.period_end else date.today() - timedelta(days=date.today().weekday() + 1)
    engine = RunEngine(db)
    for brand in args.brands.split(","):
        s = engine.run(tenant_id="brightwave", brand_id=brand, period_start=end - timedelta(days=6), period_end=end,
                       trigger="demo", schedule_date=date.today())
        if s is None:
            print(f"{brand}: already ran for this period (idempotent); use a different --period-end")
            continue
        print(f"\n=== {s.brand_name}: {s.status}  ({s.usage.steps} steps, ${s.usage.cost_usd:.4f} notional, "
              f"{s.usage.tokens} tokens)")
        for t in s.traces:
            print(f"  {t.step:>2}. {t.agent:<13} {t.status:<8} {t.summary}")
        for d in s.degradations:
            print(f"  ! {d.code}: {d.detail}")
        for r in s.recommendations:
            print(f"  → recommendation {r.recommendation_id}: {r.action_type} ${r.amount_usd_per_day:.2f}/day "
                  f"(exposure ${r.daily_exposure_usd:.2f}, risk {r.risk}) — pending approval")
        if s.abort_reason:
            print(f"  ✋ {s.abort_reason}")


def cmd_run(args: argparse.Namespace) -> None:
    from adintel.graph.engine import RunEngine
    from adintel.storage import get_database

    end = date.fromisoformat(args.period_end)
    s = RunEngine(get_database()).run(tenant_id=args.tenant, brand_id=args.brand, period_start=end - timedelta(days=6),
                                      period_end=end, trigger="cli")
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
        out[name] = {"model_id": tier.model_id, "base_url": tier.base_url, "ok": h.get("ok"),
                     "served": h.get("models"), "error": h.get("error")}
    _print(out)


def cmd_token(args: argparse.Namespace) -> None:
    from adintel.approvals.service import load_user
    from adintel.security.auth import issue_token
    from adintel.storage import get_database

    print(issue_token(load_user(get_database(), args.tenant, args.user)))


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
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
