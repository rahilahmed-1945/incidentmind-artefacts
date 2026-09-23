#!/bin/bash
# Refuse to start a second orchestrator.
#
# A duplicate launch during the halted V1 injected a fault while another run was
# mid-reset and contaminated two persistence controls. This guard makes that
# failure mode impossible. It matches only genuine interpreter processes, never
# the shell that invoked it, by checking each candidate's argv[0].
set -u
MODE="${1:-all}"
cd "$(dirname "$0")"

for pid in $(pgrep -f run_v1r 2>/dev/null); do
    [ "$pid" = "$$" ] && continue
    exe=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | awk '{print $1}')
    case "$exe" in
        *python3*)
            echo "REFUSED: orchestrator already running (pid $pid)"
            exit 1
            ;;
    esac
done

mkdir -p results
nohup python3 -u run_v1r.py "$MODE" >> "results/v1r_${MODE}_stdout.log" 2>&1 &
echo "launched mode=$MODE pid $!"
