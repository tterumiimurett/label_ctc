#!/usr/bin/env bash
set -euo pipefail

# Isolated acceptance only. No API token, production URL, webhook, or runtime
# data is used by this script. Production activation requires the human packet.
repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"
python3 -m unittest tests.test_ticket_08_activation tests.test_ticket_07_triggers tests.test_ticket_06_outbound tests.test_read_only_reconciliation
echo "Ticket 8 isolated acceptance passed; live validation and production activation remain blocked on human gates."
