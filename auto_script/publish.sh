#!/bin/zsh
set -eu
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN=/Users/seven_ding/AppData/miniconda3/bin/python
export TMPDIR="$REPO_DIR/../EveryDayPaper/temp"
mkdir -p "$TMPDIR"
"$PYTHON_BIN" -B -c 'import sys; assert sys.executable == "/Users/seven_ding/AppData/miniconda3/bin/python"; assert sys.prefix == "/Users/seven_ding/AppData/miniconda3"'
exec "$PYTHON_BIN" -B "$REPO_DIR/publisher.py" publish "$@"
