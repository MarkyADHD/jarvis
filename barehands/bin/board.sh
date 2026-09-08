#!/bin/bash
# barehands: move things on your screen with your bare hands.
# Copyright (C) 2026 Jared Rhodenizer
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# board.sh — your AI's HANDS on the board. POSTs one JSON command to the
# barehands server's /cmd channel (localhost only — this can reach
# nothing else). The server enforces its own action allowlist and the
# media-airlock jail, so this is safe to hand to an AI assistant.
#
# Usage:
#   board.sh '{"a":"add_card","title":"HELLO","body":"first card"}'
#   board.sh '{"a":"add_img","src":"misc/logo.png"}'
#   board.sh '{"a":"hand","src":"models/car.glb"}'     # deliver to reach
#   board.sh '{"a":"explode"}'                          # part the model
#   board.sh '{"a":"reset"}'                            # ring center stage
#
# Prints the HTTP code: 204 = the board took it, 400 = rejected.
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
# Portable interpreter, VALIDATED BY RUNNING one rather than by finding
# one. python3 does not exist on Windows, where the python.org installer
# provides py and python instead -- but a clean Windows 11 answers to
# BOTH those names with a Microsoft Store placeholder that `command -v`
# finds happily and that exits without running. So each candidate is
# executed before it is trusted. python3 is tried first, so macOS and
# Linux resolve exactly as before.
PYBIN=""
for c in python3 python py; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c "pass" >/dev/null 2>&1; then
        PYBIN="$c"; break
    fi
done
# Last resort on a full agent stack: the voice line's own interpreter,
# the one Python such an install guarantees. These scripts are standard
# library only, so any Python 3 runs them.
if [ -z "$PYBIN" ] && [ -x "$DIR/../backtalk/.venv/bin/python" ]; then
    PYBIN="$DIR/../backtalk/.venv/bin/python"
fi
if [ -z "$PYBIN" ] && [ -x "$DIR/../backtalk/.venv/Scripts/python.exe" ]; then
    PYBIN="$DIR/../backtalk/.venv/Scripts/python.exe"
fi
if [ -z "$PYBIN" ]; then
    echo "No working Python found (tried python3, python, py)." >&2
    echo "On Windows the name 'python' may be a Microsoft Store placeholder" >&2
    echo "that is not an interpreter. Install the real one from python.org." >&2
    exit 1
fi
PORT=$("$PYBIN" -c "import json;print(json.load(open('$DIR/barehands.json')).get('port',8794))" 2>/dev/null || echo 8794)
JSON="${1:-}"
if [ -z "$JSON" ]; then
    echo 'usage: board.sh <json-command>' >&2
    exit 1
fi
curl -sS --max-time 5 -X POST "http://127.0.0.1:$PORT/cmd" \
    -H "Content-Type: application/json" \
    -d "$JSON" -o /dev/null -w "%{http_code}\n"
