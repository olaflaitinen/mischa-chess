#!/bin/bash
# Short run of the whole test suite on the Roihu "test" partition, to check the setup.
# Submit from the repository root:
#
#     sbatch --account=<project> testing/roihu/quick.sbatch
#
#SBATCH --job-name=mischa-quick
#SBATCH --partition=test
#SBATCH --time=00:15:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --mem-per-cpu=2000M
#SBATCH --output=mischa-quick-%j.out

set -euo pipefail

REPO="${SLURM_SUBMIT_DIR:-$PWD}"
[ -f "$REPO/testing/run_suite.py" ] || { echo "submit this job from the repository root"; exit 1; }
WORK="${MISCHA_WORK:-$REPO/testing/work}"
OUT="${MISCHA_OUT:-$REPO/testing/results/quick-${SLURM_JOB_ID:-local}}"
WORKERS=$(( ${SLURM_CPUS_PER_TASK:-4} > 4 ? ${SLURM_CPUS_PER_TASK:-4} - 2 : ${SLURM_CPUS_PER_TASK:-4} ))

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
    --profile quick \
    --workers "$WORKERS" \
    --out "$OUT"

echo "report: $OUT/REPORT.md"
