"""Ticket 8 operator entrypoints."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .activation import (
    ActionJournal, ActivationController, Approval, ApprovalStore, RealApiAdapter,
    make_activation_server, normalized_preview_actions, normalized_preview_digest,
)
from .app import VerificationStore
from .contact_candidates import JsonContactLedger, VerifiedMessageScope
from .reconciliation import ProlificSubmissionClient
from .triggers import JsonTriggerStore, ReconciliationTrigger, run_periodic


def _configured_datetime(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be an ISO-8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _verified_scope(config: dict[str, Any]) -> VerifiedMessageScope:
    raw = config.get("message_scope", config.get("verified_message_scope"))
    if not isinstance(raw, dict):
        raise ValueError("message_scope or verified_message_scope is required")
    mode = raw.get("mode", "workspace")
    if mode not in {"workspace", "personal"}:
        raise ValueError("message scope mode must be workspace or personal")
    proof = raw.get("personal_proof")
    if mode == "personal" and (not isinstance(proof, dict) or not isinstance(proof.get("sole_member_id"), str) or not proof.get("sole_member_id")):
        raise ValueError("personal scope requires personal_proof.sole_member_id")
    return VerifiedMessageScope(
        researcher_id=str(raw.get("researcher_id", "")),
        workspace_id=str(raw.get("workspace_id", "")),
        coverage_start=_configured_datetime(raw.get("coverage_start"), "coverage_start"),
        coverage_end=_configured_datetime(raw.get("coverage_end"), "coverage_end"),
        workspace_visibility_verified=raw.get("workspace_visibility_verified") is True if mode == "workspace" else False,
        verification_note=str(raw.get("verification_note", "")),
        checked_at=_configured_datetime(raw.get("checked_at"), "checked_at"),
        expires_at=_configured_datetime(raw.get("expires_at"), "expires_at"),
        mode=mode,
        personal_proof=proof if mode == "personal" else None,
    )


def build_controller(config: dict[str, Any], journal: ActionJournal, *, execute: bool = False) -> ActivationController:
    """Build the reviewed API, store, ledger, scope, and policy from config."""
    study_id = str(config["study_id"])
    data_dir = Path(config["data_dir"])
    token = config.get("token")
    if not isinstance(token, str) or not token:
        raise ValueError("configured API token is required")
    if config.get("routine_policy") is not True:
        raise ValueError("routine_policy must be explicitly true")
    activation_boundary = config.get("activation_boundary")
    if not isinstance(activation_boundary, str) or not activation_boundary:
        raise ValueError("activation_boundary is required")
    scope = _verified_scope(config)
    client = ProlificSubmissionClient(token, str(config["base_url"]))
    trigger = ReconciliationTrigger(client, data_dir, study_id, JsonTriggerStore(data_dir / "events.json"))
    store = VerificationStore(
        [], list(config["auto_labels"]), data_dir, int(config.get("bundle_size", 1)),
        int(config.get("redundancy", 1)), str(config.get("completion_url", "https://app.prolific.com/submissions/complete")), False,
    )
    consent_path = Path(config["consent_evidence_path"]) if config.get("consent_evidence_path") else None
    adapter = RealApiAdapter(client, data_dir, study_id, scope=scope, consent_evidence_path=consent_path)
    return ActivationController(
        trigger=trigger, store=store, ledger=JsonContactLedger(data_dir / "contacts.json"), adapter=adapter,
        journal=journal, study_id=study_id, approvals=ApprovalStore(data_dir / "approval.json"),
        production_enabled=execute, activation_boundary=activation_boundary,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--journal', type=Path, required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    disable = sub.add_parser('disable')
    disable.add_argument('reason')
    sub.add_parser('status')
    preview = sub.add_parser('preview')
    preview.add_argument('--report', type=Path, required=True)
    approve = sub.add_parser('approve')
    approve.add_argument('--approval', type=Path, required=True)
    approve.add_argument('--study-id', required=True)
    approve.add_argument('--preview-sha256', required=True)
    approve.add_argument('--approved-by', required=True)
    approve.add_argument('--session', action='append', default=[])
    approve.add_argument('--historical-session', action='append', default=[])
    approve.add_argument('--routine-policy', action='store_true')
    approve.add_argument('--preview-report', type=Path)
    receiver = sub.add_parser('receiver')
    receiver.add_argument('--config', type=Path, required=True)
    receiver.add_argument('--secret', required=True)
    receiver.add_argument('--port', type=int, default=0)
    receiver.add_argument('--execute', action='store_true')
    scheduler = sub.add_parser('scheduler')
    scheduler.add_argument('--config', type=Path, required=True)
    scheduler.add_argument('--interval', type=float, default=300.0)
    scheduler.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    journal = ActionJournal(args.journal)
    if args.command == 'disable':
        journal.disable(args.reason)
        print(json.dumps({'status': 'disabled'}))
        return 0
    if args.command == 'status':
        print(json.dumps({'status': 'ok', 'disabled': journal.disabled}))
        return 0
    if args.command == 'preview':
        report = json.loads(args.report.read_text(encoding='utf-8'))
        print(json.dumps({'status': 'preview', 'writes_performed': False, 'study_id': report.get('study_id'), 'preview_sha256': normalized_preview_digest(report, str(report.get('study_id', ''))), 'actions': report.get('submissions', [])}, sort_keys=True))
        return 0
    if args.command == 'approve':
        historical_records = ()
        if args.preview_report:
            report = json.loads(args.preview_report.read_text(encoding='utf-8'))
            digest = normalized_preview_digest(report, args.study_id)
            if digest != args.preview_sha256:
                raise ValueError('preview digest does not match normalized report')
            historical_ids = set(args.historical_session)
            historical_records = tuple({
                'session_id': row.get('session_id'), 'study_id': row.get('study_id'),
                'participant_id': row.get('participant_id'), 'action': normalized_preview_actions({'submissions': [row]})[0].get('action'),
                'preview_sha256': digest,
            } for row in report.get('submissions', []) if isinstance(row, dict) and row.get('session_id') in historical_ids)
        historical = set(args.historical_session)
        sessions = set(args.session) | historical
        ApprovalStore(args.approval).save(Approval(
            args.study_id, args.preview_sha256, tuple(sorted(sessions)),
            tuple(sorted(historical)), tuple(sorted(sessions - historical)),
            routine_enabled=args.routine_policy, approved_at='operator-recorded', approved_by=args.approved_by, historical_records=historical_records,
        ))
        print(json.dumps({'status': 'approved', 'production': False}))
        return 0
    config = json.loads(args.config.read_text(encoding='utf-8'))
    controller = build_controller(config, journal, execute=getattr(args, "execute", False))
    if args.command == 'receiver':
        server = make_activation_server(controller, args.secret, config, port=args.port)
        print(json.dumps({'status': 'listening', 'address': server.server_address}))
        server.serve_forever()
        return 0
    stop = __import__('threading').Event()
    while not stop.is_set():
        controller.scheduled_reassessment()
        stop.wait(args.interval)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
