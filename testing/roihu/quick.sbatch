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
WORKERS=$(( ${SLURM_CPUS_PER_TASK:-4} - 2 ))

"$WORK/venv/bin/python" "$REPO/testing/run_suite.py" \
    --mischa "$WORK/bin/mischa" \
    --mischa-asan "$WORK/bin/mischa-asan" \
    --stockfish "$WORK/bin/stockfish" \
    --profile quick \
    --workers "$WORKERS" \
    --out "$OUT"

echo "report: $OUT/REPORT.md"
