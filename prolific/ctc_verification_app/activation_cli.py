"""Ticket 8 operator entrypoints."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .activation import (
    ActionJournal, ActivationController, Approval, ApprovalStore, RealApiAdapter,
    make_activation_server,
)
from .app import VerificationStore
from .contact_candidates import JsonContactLedger
from .reconciliation import ProlificSubmissionClient
from .triggers import JsonTriggerStore, ReconciliationTrigger, run_periodic


def build_controller(config: dict[str, Any], journal: ActionJournal) -> ActivationController:
    """Build reviewed concrete components from an operator configuration."""
    study_id = str(config['study_id'])
    data_dir = Path(config['data_dir'])
    token = config.get('token')
    if not isinstance(token, str) or not token:
        raise ValueError('configured API token is required')
    client = ProlificSubmissionClient(token, str(config['base_url']))
    trigger = ReconciliationTrigger(
        client, data_dir, study_id, JsonTriggerStore(data_dir / 'events.json')
    )
    store = VerificationStore(
        [], list(config['auto_labels']), data_dir, int(config.get('bundle_size', 1)),
        int(config.get('redundancy', 1)),
        str(config.get('completion_url', 'https://app.prolific.com/submissions/complete')),
        False,
    )
    adapter = RealApiAdapter(client, data_dir, study_id)
    return ActivationController(
        trigger=trigger, store=store, ledger=JsonContactLedger(data_dir / 'contacts.json'),
        adapter=adapter, journal=journal, study_id=study_id,
        approvals=ApprovalStore(data_dir / 'approval.json'), production_enabled=True,
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
    receiver = sub.add_parser('receiver')
    receiver.add_argument('--config', type=Path, required=True)
    receiver.add_argument('--secret', required=True)
    receiver.add_argument('--port', type=int, default=0)
    scheduler = sub.add_parser('scheduler')
    scheduler.add_argument('--config', type=Path, required=True)
    scheduler.add_argument('--interval', type=float, default=300.0)
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
        print(json.dumps({'status': 'preview', 'writes_performed': False, 'actions': report.get('submissions', [])}, sort_keys=True))
        return 0
    if args.command == 'approve':
        historical = set(args.historical_session)
        sessions = set(args.session) | historical
        ApprovalStore(args.approval).save(Approval(
            args.study_id, args.preview_sha256, tuple(sorted(sessions)),
            tuple(sorted(historical)), tuple(sorted(sessions - historical)),
            approved_at='operator-recorded', approved_by=args.approved_by,
        ))
        print(json.dumps({'status': 'approved', 'production': False}))
        return 0
    config = json.loads(args.config.read_text(encoding='utf-8'))
    controller = build_controller(config, journal)
    if args.command == 'receiver':
        server = make_activation_server(controller, args.secret, config, port=args.port)
        print(json.dumps({'status': 'listening', 'address': server.server_address}))
        server.serve_forever()
        return 0
    run_periodic(controller.trigger, args.interval, __import__('threading').Event())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
