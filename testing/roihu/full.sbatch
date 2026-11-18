#!/bin/bash
# The full test suite on one Roihu CPU node (384 cores). Takes about two hours.
# Submit from the repository root:
#
#     sbatch --account=<project> testing/roihu/full.sbatch
#
# If the job stops early (time limit, node failure), resubmit it with the same output
# folder; finished games are kept and only the rest is played:
#
#     sbatch --account=<project> --export=ALL,MISCHA_OUT=$PWD/testing/results/full-<jobid> \
#         testing/roihu/full.sbatch
#
# Single stages can be run with MISCHA_STAGES, for example MISCHA_STAGES=scale,report.
#
#SBATCH --job-name=mischa-full
#SBATCH --partition=medium
#SBATCH --time=05:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=384
#SBATCH --output=mischa-full-%j.out

set -euo pipefail

REPO="${SLURM_SUBMIT_DIR:-$PWD}"
[ -f "$REPO/testing/run_suite.py" ] || { echo "submit this job from the repository root"; exit 1; }
WORK="${MISCHA_WORK:-$REPO/testing/work}"
OUT="${MISCHA_OUT:-$REPO/testing/results/full-${SLURM_JOB_ID:-local}}"
STAGES="${MISCHA_STAGES:-perft,robustness,strength,scale,human,analysis,report}"
WORKERS=$(( ${SLURM_CPUS_PER_TASK:-8} - 4 ))

# hundreds of engine processes run at the same time
ulimit -n 65536 2>/dev/null || true
ulimit -u 65536 2>/dev/null || true

"$WORK/venv/bin/python" "$REPO/testing/run_suite.py" \
    --mischa "$WORK/bin/mischa" \
    --mischa-asan "$WORK/bin/mischa-asan" \
    --stockfish "$WORK/bin/stockfish" \
    --profile full \
    --stages "$STAGES" \
    --workers "$WORKERS" \
    --out "$OUT"

echo "report: $OUT/REPORT.md"
