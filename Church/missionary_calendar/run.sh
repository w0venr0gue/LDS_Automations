#!/bin/sh
# Wrapper used by cron: runs one of the scripts with the project's virtual environment
# and appends its output, with a timestamp, to logs/<script name>.log
# usage: sh run.sh weekly_missionary_update.py [options]
cd "$(dirname "$0")" || exit 1
mkdir -p logs
log="logs/$(basename "$1" .py).log"
echo "=== $(date '+%Y-%m-%d %H:%M:%S')" >> "$log"
.venv/bin/python "$@" >> "$log" 2>&1
