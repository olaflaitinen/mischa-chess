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
WORKERS=$(( ${SLURM_CPUS_PER_TASK:-8} > 8 ? ${SLURM_CPUS_PER_TASK:-8} - 4 : ${SLURM_CPUS_PER_TASK:-8} ))

# hundreds of engine processes run at the same time
ulimit -n 65536 2>/dev/null || true
ulimit -u 65536 2>/dev/null || true

# Hundreds of engines start at the same time. Loading them from node-local memory instead
# of the network file system keeps the start-up fast.
LOCAL="/dev/shm/mischa-${SLURM_JOB_ID:-$$}"
mkdir -p "$LOCAL"
trap 'rm -rf "$LOCAL"' EXIT
cp -r "$WORK/bin/." "$LOCAL/"

"$WORK/venv/bin/python" "$REPO/testing/run_suite.py" \
    --mischa "$LOCAL/mischa" \
    --mischa-asan "$LOCAL/mischa-asan" \
    --stockfish "$LOCAL/stockfish" \
    --profile full \
    --stages "$STAGES" \
    --workers "$WORKERS" \
    --out "$OUT"

echo "report: $OUT/REPORT.md"
