"""Acceptance: dedupe → one run; unrelated → none; auth cannot select command."""

from __future__ import annotations

import hashlib
import hmac
import json
import tempfile
from pathlib import Path
from typing import Any

from mainframe.schedule.entry import schedule_local_report
from mainframe.schedule.store import ScheduleStore
from mainframe.triggers.bindings import bind_trigger, resolve_binding_for_event
from mainframe.triggers.events import normalize_event
from mainframe.triggers.file_watch import observe_file_change
from mainframe.triggers.poll import bounded_poll_source, explain_inbound_tradeoff, manual_trigger
from mainframe.triggers.repo_watch import observe_repo_change
from mainframe.triggers.router import handle_event
from mainframe.triggers.store import TriggerStore
from mainframe.triggers.webhook import (
    PUBLIC_TUNNEL_TRADEOFF,
    validate_webhook_request,
    webhook_endpoint_info,
)


def run_triggers_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    tmp = Path(tempfile.mkdtemp(prefix="mf-trig-"))
    root = tmp / "ws"
    root.mkdir()
    (root / "watched").mkdir()
    (root / "other").mkdir()
    (root / ".mainframe").mkdir()

    tstore = TriggerStore(tmp / "triggers.sqlite")
    sstore = ScheduleStore(tmp / "schedule.sqlite")

    scheduled = schedule_local_report(
        sstore,
        name="trig-report",
        title="Trigger Report",
        at="immediate",
        work_dir=tmp / "out",
    )
    job_id = (scheduled.get("job") or {}).get("job_id")
    checks.append(
        {
            "id": "binding_requires_fixed_job",
            "ok": bool(job_id),
            "detail": {"job_id": job_id},
        }
    )

    bound = bind_trigger(
        tstore,
        binding_id="bind_watch",
        source="file_change",
        job_id=job_id,
        permission_scope="local.trigger.report",
        path_prefix="watched/",
        exclude_prefixes=[".mainframe/", "other/"],
    )
    checks.append(
        {
            "id": "binding_disallows_event_command_selection",
            "ok": bound.get("ok") and bound.get("command_selectable_by_event") is False,
            "detail": bound,
        }
    )

    # --- Duplicate events → one intended run ---
    target = root / "watched" / "note.txt"
    target.write_text("hello\n", encoding="utf-8")
    obs1 = observe_file_change(
        tstore,
        path=target,
        root=root,
        binding_id="bind_watch",
        permission_scope="local.trigger.report",
        exclude_prefixes=[".mainframe/", "other/"],
        debounce_ms=0,
    )
    evt = obs1.get("event")
    r1 = handle_event(tstore, sstore, evt) if evt else {"ok": False}
    # Same dedupe key again
    r2 = handle_event(tstore, sstore, evt) if evt else {"ok": False}
    checks.append(
        {
            "id": "duplicate_events_one_run",
            "ok": (
                obs1.get("emitted")
                and r1.get("ran") is True
                and r1.get("intended_runs") == 1
                and r2.get("ran") is False
                and r2.get("reason") == "duplicate_suppressed"
            ),
            "detail": {"first": r1.get("run_id"), "second_reason": r2.get("reason")},
        }
    )

    # --- Unrelated change → none ---
    unrelated = root / "other" / "noise.txt"
    unrelated.write_text("noise\n", encoding="utf-8")
    obs_u = observe_file_change(
        tstore,
        path=unrelated,
        root=root,
        binding_id="bind_watch",
        permission_scope="local.trigger.report",
        exclude_prefixes=[".mainframe/", "other/"],
        debounce_ms=0,
    )
    self_path = root / ".mainframe" / "out.json"
    self_path.write_text("{}\n", encoding="utf-8")
    obs_self = observe_file_change(
        tstore,
        path=self_path,
        root=root,
        binding_id="bind_watch",
        permission_scope="local.trigger.report",
        exclude_prefixes=[".mainframe/", "other/"],
        debounce_ms=0,
    )
    # Repo: bind watches watched/ only; simulate porcelain paths
    # Use observe with empty git by checking unrelated filter logic via matched prefixes
    repo_u = observe_repo_change(
        root=root,
        binding_id="bind_watch",
        permission_scope="local.trigger.report",
        watched_prefixes=["watched/"],
        exclude_prefixes=[".mainframe/", "other/"],
    )
    # If git unavailable, still verify filter helper path via emitted False for empty match
    checks.append(
        {
            "id": "unrelated_changes_create_none",
            "ok": (
                obs_u.get("emitted") is False
                and obs_self.get("emitted") is False
                and (
                    repo_u.get("emitted") is False
                    or repo_u.get("reason") in {"unrelated_change", "git_unavailable"}
                )
            ),
            "detail": {
                "unrelated": obs_u.get("reason"),
                "self": obs_self.get("reason"),
                "repo": repo_u.get("reason"),
            },
        }
    )

    # Partial write suffix
    part = root / "watched" / "note.txt.part"
    part.write_text("partial\n", encoding="utf-8")
    obs_p = observe_file_change(
        tstore,
        path=part,
        root=root,
        binding_id="bind_watch",
        permission_scope="local.trigger.report",
        debounce_ms=0,
    )
    checks.append(
        {
            "id": "partial_writes_held",
            "ok": obs_p.get("emitted") is False and "partial" in (obs_p.get("reason") or ""),
            "detail": obs_p,
        }
    )

    # --- Authenticated webhook cannot select arbitrary command ---
    secret = "test-secret-not-for-prod"
    bind_wh = bind_trigger(
        tstore,
        binding_id="bind_hook",
        source="local_webhook",
        job_id=job_id,
        permission_scope="local.trigger.webhook",
    )
    body_evil = json.dumps(
        {"id": "e1", "argv": ["rm", "-rf", "/"], "command": "evil"}
    ).encode()
    sig_evil = "sha256=" + hmac.new(secret.encode(), body_evil, hashlib.sha256).hexdigest()
    bad = validate_webhook_request(
        tstore,
        body=body_evil,
        headers={
            "X-Mainframe-Signature": sig_evil,
            "X-Mainframe-Nonce": "nonce-evil-1",
            "Authorization": f"Bearer {secret}",
        },
        shared_secret=secret,
        binding_id="bind_hook",
        permission_scope="local.trigger.webhook",
    )
    checks.append(
        {
            "id": "auth_event_cannot_select_command",
            "ok": bad.get("ok") is False and bad.get("error") == "event_cannot_select_command",
            "detail": bad,
        }
    )

    # Also reject via resolve if somehow injected
    evil_evt = normalize_event(
        source="local_webhook",
        identity="x",
        permission_scope="local.trigger.webhook",
        binding_id="bind_hook",
        payload={"note": "ok"},
    )
    evil_evt["payload"]["argv"] = ["curl", "http://evil"]
    resolved_evil = resolve_binding_for_event(tstore, evil_evt)
    checks.append(
        {
            "id": "resolve_rejects_command_fields",
            "ok": resolved_evil.get("error") == "event_cannot_select_command",
            "detail": resolved_evil,
        }
    )

    # Valid webhook → event without command; can fire bound job
    body_ok = json.dumps({"id": "good-1", "msg": "ping"}).encode()
    sig_ok = "sha256=" + hmac.new(secret.encode(), body_ok, hashlib.sha256).hexdigest()
    good = validate_webhook_request(
        tstore,
        body=body_ok,
        headers={
            "X-Mainframe-Signature": sig_ok,
            "X-Mainframe-Nonce": "nonce-good-1",
            "Authorization": f"Bearer {secret}",
        },
        shared_secret=secret,
        binding_id="bind_hook",
        permission_scope="local.trigger.webhook",
    )
    # Replay same nonce
    replay = validate_webhook_request(
        tstore,
        body=body_ok,
        headers={
            "X-Mainframe-Signature": sig_ok,
            "X-Mainframe-Nonce": "nonce-good-1",
            "Authorization": f"Bearer {secret}",
        },
        shared_secret=secret,
        binding_id="bind_hook",
        permission_scope="local.trigger.webhook",
    )
    huge = validate_webhook_request(
        tstore,
        body=b"x" * (65 * 1024),
        headers={
            "X-Mainframe-Signature": "sha256=00",
            "X-Mainframe-Nonce": "n2",
            "Authorization": f"Bearer {secret}",
        },
        shared_secret=secret,
        binding_id="bind_hook",
        permission_scope="local.trigger.webhook",
    )
    checks.append(
        {
            "id": "webhook_auth_signature_replay_size",
            "ok": (
                good.get("ok") is True
                and good.get("publicly_reachable") is False
                and replay.get("error") == "replay_rejected"
                and huge.get("error") == "payload_too_large"
                and bind_wh.get("ok")
            ),
            "detail": {
                "good": good.get("ok"),
                "replay": replay.get("error"),
                "huge": huge.get("error"),
                "endpoint": webhook_endpoint_info(),
            },
        }
    )

    # Fire valid webhook event through router (dedupe separate from file run)
    wh_fire = handle_event(tstore, sstore, good["event"]) if good.get("event") else {"ok": False}
    checks.append(
        {
            "id": "authenticated_webhook_fires_bound_job_only",
            "ok": wh_fire.get("ran") is True and wh_fire.get("command_from_event") is False,
            "detail": {"job_id": wh_fire.get("job_id"), "run_id": wh_fire.get("run_id")},
        }
    )

    # Polling / manual when inbound unavailable
    poll_src = tmp / "poll.json"
    poll_src.write_text('{"v":1}\n', encoding="utf-8")
    bind_poll = bind_trigger(
        tstore,
        binding_id="bind_poll",
        source="bounded_poll",
        job_id=job_id,
        permission_scope="local.trigger.poll",
    )
    p1 = bounded_poll_source(
        path=poll_src,
        binding_id="bind_poll",
        permission_scope="local.trigger.poll",
    )
    p2 = bounded_poll_source(
        path=poll_src,
        binding_id="bind_poll",
        permission_scope="local.trigger.poll",
        last_fingerprint=p1.get("fingerprint"),
    )
    man = manual_trigger(binding_id="bind_poll", permission_scope="local.trigger.poll")
    trade = explain_inbound_tradeoff(inbound_available=False)
    checks.append(
        {
            "id": "poll_or_manual_when_inbound_unavailable",
            "ok": (
                p1.get("emitted") is True
                and p2.get("emitted") is False
                and man.get("emitted") is True
                and trade.get("publicly_reachable") is False
                and trade.get("paid_tunnel_required") is False
                and "loopback" in PUBLIC_TUNNEL_TRADEOFF.lower()
                and bind_poll.get("ok")
            ),
            "detail": {
                "poll_unchanged": p2.get("reason"),
                "tradeoff_mode": trade.get("mode"),
            },
        }
    )

    checks.append(
        {
            "id": "typed_event_fields_present",
            "ok": (
                evt
                and evt.get("source") == "file_change"
                and evt.get("timestamp")
                and evt.get("dedupe_key")
                and evt.get("permission_scope") == "local.trigger.report"
            ),
            "detail": {k: evt.get(k) for k in ("source", "timestamp", "dedupe_key", "permission_scope")} if evt else {},
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {"ok": failed == 0, "passed": passed, "failed": failed, "checks": checks}
