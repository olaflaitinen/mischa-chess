#!/usr/bin/env python3
"""Measure Mischa's playing strength against Stockfish's UCI_Elo levels.

Example:
    pip install chess
    python3 tools/calibrate.py --mischa build/mischa --stockfish stockfish \\
        --anchors 1600 1800 2000 2200 --games 40 --tc 10+0.1 --concurrency 4

For every anchor level the script plays a match (colors alternate, every opening is played
from both sides), prints the score and turns it into a performance rating. The combined
estimate is a weighted average of the per-anchor performances.

Stockfish's UCI_Elo is calibrated against the CCRL engine rating list, not against human
FIDE ratings, so the number printed here is an engine-list estimate. See
docs/CALIBRATION.md for how to translate it and how to validate it against people.
"""

import argparse
import concurrent.futures
import math
import random
import sys
import time

try:
    import chess
    import chess.engine
    import chess.pgn
except ImportError:
    sys.exit("python-chess is required: pip install chess")

# Short, balanced openings (UCI moves). Each one is played twice, once with each color.
OPENINGS = [
    "e2e4 e7e5 g1f3 b8c6 f1b5 a7a6",
    "e2e4 e7e5 g1f3 b8c6 f1c4 f8c5",
    "e2e4 c7c5 g1f3 d7d6 d2d4 c5d4 f3d4 g8f6",
    "e2e4 c7c5 g1f3 b8c6 d2d4 c5d4 f3d4 g7g6",
    "e2e4 e7e6 d2d4 d7d5 b1c3 g8f6",
    "e2e4 c7c6 d2d4 d7d5 e4e5 c8f5",
    "e2e4 d7d6 d2d4 g8f6 b1c3 g7g6",
    "d2d4 d7d5 c2c4 e7e6 b1c3 g8f6",
    "d2d4 d7d5 c2c4 c7c6 g1f3 g8f6",
    "d2d4 g8f6 c2c4 g7g6 b1c3 f8g7 e2e4 d7d6",
    "d2d4 g8f6 c2c4 e7e6 b1c3 f8b4",
    "d2d4 g8f6 c2c4 c7c5 d4d5 e7e6",
    "c2c4 e7e5 b1c3 g8f6 g1f3 b8c6",
    "g1f3 d7d5 g2g3 g8f6 f1g2 c7c6",
    "e2e4 e7e5 f2f4 e5f4 g1f3 g7g5",
    "e2e4 g8f6 e4e5 f6d5 d2d4 d7d6",
]


def parse_tc(tc):
    base, _, inc = tc.partition("+")
    return float(base), float(inc or 0)


def play_game(args, anchor, opening, mischa_white, seed):
    base, inc = parse_tc(args.tc)
    board = chess.Board()
    for uci in opening.split():
        board.push_uci(uci)

    mischa = chess.engine.SimpleEngine.popen_uci(args.mischa)
    stockfish = chess.engine.SimpleEngine.popen_uci(args.stockfish)
    try:
        mischa.configure({
            "UCI_LimitStrength": True,
            "UCI_Elo": args.elo,
            "HumanTime": args.human_time,
            "UseBook": False,
            "RandomSeed": seed,
        })
        stockfish.configure({"UCI_LimitStrength": True, "UCI_Elo": anchor, "Threads": 1, "Hash": 16})

        clocks = {chess.WHITE: base, chess.BLACK: base}
        engines = {chess.WHITE: mischa if mischa_white else stockfish,
                   chess.BLACK: stockfish if mischa_white else mischa}
        result = None

        while not board.is_game_over(claim_draw=True):
            side = board.turn
            limit = chess.engine.Limit(white_clock=clocks[chess.WHITE], black_clock=clocks[chess.BLACK],
                                       white_inc=inc, black_inc=inc)
            started = time.monotonic()
            play = engines[side].play(board, limit)
            clocks[side] -= time.monotonic() - started
            if clocks[side] < 0:
                result = "0-1" if side == chess.WHITE else "1-0"   # lost on time
                break
            clocks[side] += inc
            board.push(play.move)
            if board.fullmove_number > 200:
                result = "1/2-1/2"
                break
        if result is None:
            result = board.result(claim_draw=True)
    finally:
        mischa.quit()
        stockfish.quit()

    if result == "1-0":
        score = 1.0 if mischa_white else 0.0
    elif result == "0-1":
        score = 0.0 if mischa_white else 1.0
    else:
        score = 0.5

    game = chess.pgn.Game.from_board(board)
    game.headers["White"] = "Mischa %d" % args.elo if mischa_white else "Stockfish %d" % anchor
    game.headers["Black"] = "Stockfish %d" % anchor if mischa_white else "Mischa %d" % args.elo
    game.headers["Result"] = result
    game.headers["TimeControl"] = args.tc
    return score, game


def elo_from_score(score):
    score = min(max(score, 0.001), 0.999)
    return -400.0 * math.log10(1.0 / score - 1.0)


def elo_error(scores):
    """95 % confidence half-width of the Elo difference (normal approximation)."""
    n = len(scores)
    if n < 2:
        return float("inf")
    mean = sum(scores) / n
    var = sum((s - mean) ** 2 for s in scores) / (n - 1)
    se = math.sqrt(var / n)
    lo, hi = mean - 1.96 * se, mean + 1.96 * se
    return (elo_from_score(hi) - elo_from_score(lo)) / 2.0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mischa", required=True, help="path to the Mischa executable")
    parser.add_argument("--stockfish", default="stockfish", help="path to a Stockfish executable")
    parser.add_argument("--elo", type=int, default=2000, help="UCI_Elo given to Mischa")
    parser.add_argument("--anchors", type=int, nargs="+", default=[1800, 2000, 2200],
                        help="Stockfish UCI_Elo levels to play against")
    parser.add_argument("--games", type=int, default=32, help="games per anchor (rounded up to even)")
    parser.add_argument("--tc", default="10+0.1", help="time control in seconds, base+increment")
    parser.add_argument("--concurrency", type=int, default=2, help="games played in parallel")
    parser.add_argument("--human-time", action="store_true", help="let Mischa use its human timing")
    parser.add_argument("--pgn", help="write all games to this PGN file")
    parser.add_argument("--seed", type=int, default=1, help="random seed for the schedule")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    pgn_out = open(args.pgn, "w") if args.pgn else None
    total_weight = 0.0
    weighted = 0.0

    print("Mischa UCI_Elo %d, time control %s" % (args.elo, args.tc))
    for anchor in args.anchors:
        pairs = (args.games + 1) // 2
        jobs = []
        for i in range(pairs):
            opening = OPENINGS[i % len(OPENINGS)]
            jobs.append((opening, True, rng.randint(1, 1000000)))
            jobs.append((opening, False, rng.randint(1, 1000000)))

        scores = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = [pool.submit(play_game, args, anchor, o, w, s) for o, w, s in jobs]
            for fut in concurrent.futures.as_completed(futures):
                score, game = fut.result()
                scores.append(score)
                if pgn_out:
                    print(game, file=pgn_out, end="\n\n")
                    pgn_out.flush()

        n = len(scores)
        mean = sum(scores) / n
        wins = scores.count(1.0)
        draws = scores.count(0.5)
        losses = scores.count(0.0)
        diff = elo_from_score(mean)
        err = elo_error(scores)
        perf = anchor + diff
        print("  vs Stockfish %4d: +%d =%d -%d  score %.1f%%  diff %+.0f +/- %.0f  performance %.0f"
              % (anchor, wins, draws, losses, 100.0 * mean, diff, err, perf))

        # anchors close to Mischa's strength carry more information
        weight = mean * (1.0 - mean) * n
        if 0.05 < mean < 0.95:
            weighted += weight * perf
            total_weight += weight

    if pgn_out:
        pgn_out.close()

    if total_weight > 0:
        print("Estimated strength on the Stockfish UCI_Elo (CCRL) scale: %.0f" % (weighted / total_weight))
    else:
        print("All matches were one-sided; add anchors closer to Mischa's strength.")


if __name__ == "__main__":
    main()
