#!/usr/bin/env python3
"""Mischa test suite.

Runs a complete, reproducible evaluation of the engine and writes a Markdown report.

Stages (run in this order, each can be selected with --stages):

  perft       move generator correctness on standard positions
  robustness  thousands of random positions and UCI command sequences: legal moves,
              no crashes, no hangs, clock limits respected, sanitizer-clean (optional)
  strength    Mischa at UCI_Elo 2000 against several Stockfish UCI_Elo levels
  scale       every UCI_Elo level from 1200 to 2400 against nearby Stockfish levels
  human       games on a real clock with human timing switched on
  analysis    every Mischa move from the stages above checked by full-strength Stockfish:
              centipawn loss, mistakes, accuracy, by game phase and by position complexity
  report      REPORT.md and summary.json

Requirements: Python 3.8+, python-chess (pip install chess), a Stockfish executable.

Examples:
  python3 testing/run_suite.py --mischa build/mischa --stockfish stockfish --profile quick
  python3 testing/run_suite.py --mischa build/mischa --stockfish stockfish --profile full \\
      --workers 380 --out testing/results/full-run

Interrupted runs can be resumed by running the same command with the same --out folder:
finished games and positions are not repeated.
"""

import argparse
import datetime
import json
import math
import multiprocessing
import os
import platform
import queue
import random
import re
import statistics
import subprocess
import sys
import threading
import time

try:
    import chess
    import chess.engine
    import chess.pgn
except ImportError:
    sys.exit("python-chess is required: pip install chess")


# ---------------------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------------------

PROFILES = {
    # a few minutes on a laptop or the Roihu "test" partition; checks that everything works
    "quick": {
        "perft": "quick",
        "robust_positions": 400,
        "strength_anchors": [1800, 2000, 2200],
        "strength_games": 8,
        "strength_tc": "5+0.05",
        "scale_levels": [1400, 2000, 2400],
        "scale_games": 4,
        "scale_tc": "5+0.05",
        "human_games": 4,
        "human_tc": "30+0.3",
        "analysis_depth": 10,
    },
    # the real evaluation; about two hours on one 384-core Roihu node
    "full": {
        "perft": "full",
        "robust_positions": 20000,
        "strength_anchors": [1600, 1800, 2000, 2200, 2400],
        "strength_games": 2000,
        "strength_tc": "60+0.6",
        "scale_levels": [1200, 1400, 1600, 1800, 2000, 2200, 2400],
        "scale_games": 400,
        "scale_tc": "60+0.6",
        "human_games": 380,
        "human_tc": "600+5",
        "analysis_depth": 12,
    },
}

ALL_STAGES = ["perft", "robustness", "strength", "scale", "human", "analysis", "report"]

# Stockfish's UCI_Elo range
SF_MIN_ELO = 1320
SF_MAX_ELO = 3190

PERFT_POSITIONS = [
    # name, fen, {depth: nodes}
    ("start position", chess.STARTING_FEN,
     {4: 197281, 5: 4865609, 6: 119060324}),
    ("kiwipete", "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
     {3: 97862, 4: 4085603, 5: 193690690}),
    ("position 3", "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
     {5: 674624, 6: 11030083, 7: 178633661}),
    ("position 4", "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
     {4: 422333, 5: 15833292}),
    ("position 4 mirrored", "r2q1rk1/pP1p2pp/Q4n2/bbp1p3/Np6/1B3NBn/pPPP1PPP/R3K2R b KQ - 0 1",
     {4: 422333, 5: 15833292}),
    ("position 5", "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
     {4: 2103487, 5: 89941194}),
    ("position 6", "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10",
     {4: 3894594, 5: 164075551}),
]
PERFT_DEPTHS = {"quick": 0, "full": -1}   # index into sorted depths: 0 = smallest, -1 = largest

# Balanced openings, every one is played with both colors
OPENINGS = [
    "e2e4 e7e5 g1f3 b8c6 f1b5 a7a6",
    "e2e4 e7e5 g1f3 b8c6 f1c4 f8c5",
    "e2e4 e7e5 g1f3 b8c6 d2d4 e5d4 f3d4",
    "e2e4 e7e5 g1f3 g8f6 f3e5 d7d6",
    "e2e4 e7e5 b1c3 g8f6 f2f4",
    "e2e4 e7e5 f2f4 e5f4 g1f3 g7g5",
    "e2e4 c7c5 g1f3 d7d6 d2d4 c5d4 f3d4 g8f6",
    "e2e4 c7c5 g1f3 b8c6 d2d4 c5d4 f3d4 g7g6",
    "e2e4 c7c5 g1f3 e7e6 d2d4 c5d4 f3d4 a7a6",
    "e2e4 c7c5 b1c3 b8c6 g2g3 g7g6",
    "e2e4 c7c5 c2c3 g8f6 e4e5 f6d5",
    "e2e4 e7e6 d2d4 d7d5 b1c3 g8f6",
    "e2e4 e7e6 d2d4 d7d5 e4e5 c7c5",
    "e2e4 c7c6 d2d4 d7d5 e4e5 c8f5",
    "e2e4 c7c6 d2d4 d7d5 b1c3 d5e4 c3e4",
    "e2e4 d7d6 d2d4 g8f6 b1c3 g7g6",
    "e2e4 d7d5 e4d5 d8d5 b1c3 d5a5",
    "e2e4 g8f6 e4e5 f6d5 d2d4 d7d6",
    "d2d4 d7d5 c2c4 e7e6 b1c3 g8f6",
    "d2d4 d7d5 c2c4 c7c6 g1f3 g8f6",
    "d2d4 d7d5 c2c4 d5c4 g1f3 g8f6",
    "d2d4 g8f6 c2c4 g7g6 b1c3 f8g7 e2e4 d7d6",
    "d2d4 g8f6 c2c4 g7g6 b1c3 d7d5",
    "d2d4 g8f6 c2c4 e7e6 b1c3 f8b4",
    "d2d4 g8f6 c2c4 e7e6 g1f3 b7b6",
    "d2d4 g8f6 c2c4 c7c5 d4d5 e7e6",
    "d2d4 g8f6 c2c4 c7c5 d4d5 b7b5",
    "d2d4 f7f5 g2g3 g8f6 f1g2 g7g6",
    "d2d4 d7d5 g1f3 g8f6 c1f4 e7e6",
    "c2c4 e7e5 b1c3 g8f6 g1f3 b8c6",
    "c2c4 c7c5 g1f3 g8f6 b1c3 b8c6",
    "g1f3 d7d5 g2g3 g8f6 f1g2 c7c6",
]

INFO_RE = re.compile(
    r"Mischa: elo (\d+) depth (\d+) complexity ([\d.]+) sigma (\d+) pick (\d+)/(\d+) loss (-?\d+) \((.+)\)")


def parse_tc(tc):
    base, _, inc = tc.partition("+")
    return float(base), float(inc or 0)


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg):
    print("[%s] %s" % (now(), msg), flush=True)


# ---------------------------------------------------------------------------------------
# Result storage (JSON lines, resumable)
# ---------------------------------------------------------------------------------------

def load_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        pass   # a line cut off by an interrupted run
    return rows


def run_jobs(func, jobs, out_path, workers, label):
    """Run jobs in parallel, append each result to out_path, skip jobs already done."""
    done = {r["id"] for r in load_jsonl(out_path)}
    todo = [j for j in jobs if j["id"] not in done]
    total = len(jobs)
    if not todo:
        log("%s: all %d jobs already done" % (label, total))
        return
    log("%s: %d jobs to run (%d already done), %d workers" % (label, len(todo), total - len(todo), workers))
    start = time.time()
    finished = 0
    step = max(1, len(todo) // 20)
    with open(out_path, "a") as out, multiprocessing.Pool(processes=min(workers, len(todo))) as pool:
        for result in pool.imap_unordered(func, todo):
            out.write(json.dumps(result) + "\n")
            out.flush()
            finished += 1
            if finished % step == 0 or finished == len(todo):
                elapsed = time.time() - start
                eta = elapsed / finished * (len(todo) - finished)
                log("%s: %d/%d done, %.0f s elapsed, about %.0f s left" % (label, finished, len(todo), elapsed, eta))


# ---------------------------------------------------------------------------------------
# Raw UCI process (used where exact control of the protocol is needed)
# ---------------------------------------------------------------------------------------

class RawEngine:
    def __init__(self, path, env=None):
        self.path = path
        self.proc = subprocess.Popen([path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1, env=env)
        self.lines = queue.Queue()
        self.log = []   # everything the engine printed (kept short)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            for line in self.proc.stdout:
                self.lines.put(line.rstrip("\r\n"))
        except ValueError:
            pass
        self.lines.put(None)

    def send(self, cmd):
        try:
            self.proc.stdin.write(cmd + "\n")
            self.proc.stdin.flush()
            return True
        except (BrokenPipeError, OSError, ValueError):
            return False

    def wait_for(self, prefix, timeout):
        """Return (line, seen) or (None, seen) on timeout or engine exit."""
        seen = []
        deadline = time.time() + timeout
        while True:
            left = deadline - time.time()
            if left <= 0:
                return None, seen
            try:
                line = self.lines.get(timeout=min(left, 0.2))
            except queue.Empty:
                continue
            if line is None:
                return None, seen
            seen.append(line)
            if line.startswith(prefix):
                return line, seen

    def alive(self):
        return self.proc.poll() is None

    def close(self):
        try:
            self.send("quit")
            self.proc.wait(timeout=3)
        except Exception:
            self.proc.kill()


# ---------------------------------------------------------------------------------------
# Stage: perft
# ---------------------------------------------------------------------------------------

def stage_perft(args, profile, out_dir):
    which = PERFT_DEPTHS[profile["perft"]]
    rows = []
    eng = RawEngine(args.mischa)
    try:
        eng.send("uci")
        eng.wait_for("uciok", 30)
        for name, fen, table in PERFT_POSITIONS:
            depth = sorted(table)[which]
            expected = table[depth]
            eng.send("position fen " + fen)
            eng.send("perft %d" % depth)
            line, _ = eng.wait_for("perft ", 3600)
            got = int(line.split()[3]) if line else None
            ms = int(line.split()[5]) if line else None
            rows.append({"name": name, "fen": fen, "depth": depth, "expected": expected,
                         "nodes": got, "ms": ms, "ok": got == expected})
            log("perft %-20s depth %d: %s (%s)" % (name, depth, got, "ok" if got == expected else "MISMATCH"))
    finally:
        eng.close()
    with open(os.path.join(out_dir, "perft.json"), "w") as f:
        json.dump(rows, f, indent=1)


# ---------------------------------------------------------------------------------------
# Stage: robustness
# ---------------------------------------------------------------------------------------

SPECIAL_FENS = [
    "4k3/1P6/8/8/8/8/6p1/4K3 w - - 0 1",                       # promotions for both sides
    "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1",                    # all castling rights
    "rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3",   # en passant
    "7k/5Q2/6K1/8/8/8/8/8 w - - 0 1",                          # mate in one, stalemate traps
    "8/8/8/8/8/5k2/5p2/5K2 w - - 0 1",                         # only one legal move
    "k7/8/1K6/8/8/8/8/7R w - - 0 1",                           # mate in one with a rook
    "8/8/8/3k4/8/8/3K4/8 w - - 50 120",                        # bare kings
    "8/P7/8/8/8/8/7p/K6k b - - 0 1",                           # promotion race
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 99 200",   # 50-move counter edge
]


def random_position(rng):
    """A random reachable position: random but plausible moves from the start."""
    board = chess.Board()
    plies = rng.randint(0, 140)
    for _ in range(plies):
        moves = list(board.legal_moves)
        if not moves or board.is_game_over():
            break
        captures = [m for m in moves if board.is_capture(m)]
        # captures are a bit more likely, so material comes off and endgames appear
        move = rng.choice(captures) if captures and rng.random() < 0.4 else rng.choice(moves)
        board.push(move)
    return board


def robustness_job(job):
    rng = random.Random(job["seed"])
    env = dict(os.environ)
    path = job["engine"]
    if job.get("asan"):
        env["ASAN_OPTIONS"] = "detect_leaks=0:abort_on_error=0"
        env["UBSAN_OPTIONS"] = "print_stacktrace=1"
    failures = []
    stats = {"commands": 0, "illegal": 0, "crash": 0, "timeout": 0, "overrun": 0, "sanitizer": 0}

    def start():
        e = RawEngine(path, env)
        e.send("uci")
        line, _ = e.wait_for("uciok", 60)
        return e if line else None

    eng = start()
    if eng is None:
        return {"id": job["id"], "stats": dict(stats, crash=1), "failures": [{"what": "no uciok"}]}

    for k in range(job["count"]):
        # position
        if k < len(job["special"]):
            board = chess.Board(job["special"][k])
            position_cmd = "position fen " + board.fen()
        else:
            board = random_position(rng)
            if board.is_game_over():
                continue
            if rng.random() < 0.5:
                position_cmd = "position fen " + board.fen()
            else:
                moves = " ".join(m.uci() for m in board.move_stack)
                position_cmd = "position startpos" + (" moves " + moves if moves else "")
        if board.is_game_over():
            continue

        # options
        opts = {
            "UCI_LimitStrength": rng.random() < 0.8,
            "UCI_Elo": rng.choice([1000, 1200, 1500, 1800, 2000, 2200, 2600, rng.randint(1000, 2600)]),
            "HumanTime": rng.random() < 0.3,
            "Flair": rng.choice([0, 50, 100, 200]),
            "UseBook": rng.random() < 0.5,
            "MultiPV": 1 if rng.random() < 0.85 else rng.randint(2, 4),
        }
        for name, value in opts.items():
            eng.send("setoption name %s value %s" % (name, str(value).lower() if isinstance(value, bool) else value))
        if rng.random() < 0.1:
            eng.send("ucinewgame")
        eng.send(position_cmd)

        # search command
        kind = rng.choice(["depth", "movetime", "clock", "clock", "clock", "nodes", "infinite"])
        limit_ms = None
        if kind == "depth":
            go = "go depth %d" % rng.randint(1, 9)
            wait = 120
        elif kind == "movetime":
            go = "go movetime %d" % rng.randint(20, 400)
            wait = 30
        elif kind == "nodes":
            go = "go nodes %d" % rng.randint(500, 200000)
            wait = 60
        elif kind == "infinite":
            go = "go infinite"
            wait = 30
        else:
            base = rng.choice([150, 500, 2000, 10000, 60000, 300000])
            inc = rng.choice([0, 0, 10, 100, 1000])
            go = "go wtime %d btime %d winc %d binc %d" % (base, base, inc, inc)
            if rng.random() < 0.2:
                go += " movestogo %d" % rng.randint(1, 40)
            # the engine must never use more than its whole clock; with the human layer
            # on, never more than 15 % of it (plus process and scheduling slack)
            if opts["UCI_LimitStrength"] and opts["MultiPV"] == 1:
                limit_ms = 0.15 * base + 400
            else:
                limit_ms = base + inc + 400
            wait = max(30, limit_ms / 1000.0 * 3)

        stats["commands"] += 1
        eng.send("isready")
        eng.wait_for("readyok", 60)
        t0 = time.time()
        eng.send(go)
        if kind == "infinite":
            time.sleep(rng.uniform(0.05, 0.3))
            eng.send("stop")
        elif rng.random() < 0.15:
            eng.send("isready")       # GUIs ping engines while they think
        line, seen = eng.wait_for("bestmove", wait)
        elapsed_ms = (time.time() - t0) * 1000.0

        sanitizer = [l for l in seen if "Sanitizer" in l or "runtime error" in l]
        case = {"position": position_cmd, "go": go, "options": opts}

        if sanitizer:
            stats["sanitizer"] += 1
            failures.append(dict(case, what="sanitizer", detail=sanitizer[:5]))
        if line is None:
            if eng.alive():
                stats["timeout"] += 1
                failures.append(dict(case, what="no bestmove within %.0f s" % wait))
                eng.proc.kill()
            else:
                stats["crash"] += 1
                failures.append(dict(case, what="engine exited", detail=seen[-5:]))
            eng.close()
            eng = start()
            if eng is None:
                break
            continue

        move_str = line.split()[1] if len(line.split()) > 1 else ""
        try:
            move = chess.Move.from_uci(move_str)
            legal = move in board.legal_moves
        except ValueError:
            legal = False
        if not legal:
            stats["illegal"] += 1
            failures.append(dict(case, what="illegal move %s" % move_str))
        if limit_ms is not None and elapsed_ms > limit_ms:
            stats["overrun"] += 1
            failures.append(dict(case, what="used %.0f ms, limit %.0f ms" % (elapsed_ms, limit_ms)))

    if eng is not None:
        eng.close()
    return {"id": job["id"], "asan": bool(job.get("asan")), "stats": stats, "failures": failures[:50]}


def stage_robustness(args, profile, out_dir):
    total = profile["robust_positions"]
    per_job = 50
    jobs = []
    n_jobs = max(1, total // per_job)
    for i in range(n_jobs):
        asan = bool(args.mischa_asan) and i % 10 == 0     # every tenth batch with sanitizers
        jobs.append({
            "id": "robust-%d" % i,
            "seed": args.seed * 100003 + i,
            "engine": args.mischa_asan if asan else args.mischa,
            "asan": asan,
            "count": per_job,
            "special": SPECIAL_FENS if i == 0 else [],
        })
    run_jobs(robustness_job, jobs, os.path.join(out_dir, "robustness.jsonl"), args.workers, "robustness")


# ---------------------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------------------

def play_game(job):
    """Play one game Mischa against Stockfish. Returns a JSON-serialisable record."""
    base, inc = parse_tc(job["tc"])
    board = chess.Board()
    for uci in job["opening"].split():
        board.push_uci(uci)
    opening_plies = len(board.move_stack)

    record = {"id": job["id"], "stage": job["stage"], "mischa_elo": job["mischa_elo"],
              "sf_elo": job["sf_elo"], "mischa_white": job["mischa_white"], "tc": job["tc"],
              "opening": job["opening"], "human_time": job["human_time"], "moves": [],
              "result": None, "termination": None, "error": None}

    mischa = stockfish = None
    try:
        mischa = chess.engine.SimpleEngine.popen_uci(job["mischa"])
        stockfish = chess.engine.SimpleEngine.popen_uci(job["stockfish"])
        mischa.configure({
            "UCI_LimitStrength": True, "UCI_Elo": job["mischa_elo"], "HumanTime": job["human_time"],
            "HumanVerbose": True, "UseBook": False, "RandomSeed": job["seed"], "Hash": 16, "Threads": 1,
        })
        stockfish.configure({"UCI_LimitStrength": True, "UCI_Elo": job["sf_elo"], "Threads": 1, "Hash": 16})

        mischa_color = chess.WHITE if job["mischa_white"] else chess.BLACK
        clocks = {chess.WHITE: base, chess.BLACK: base}

        while True:
            if board.is_game_over(claim_draw=True):
                record["result"] = board.result(claim_draw=True)
                outcome = board.outcome(claim_draw=True)
                record["termination"] = outcome.termination.name.lower() if outcome else "unknown"
                break
            if len(board.move_stack) >= 400:
                record["result"], record["termination"] = "1/2-1/2", "move_limit"
                break

            side = board.turn
            engine = mischa if side == mischa_color else stockfish
            limit = chess.engine.Limit(white_clock=clocks[chess.WHITE], black_clock=clocks[chess.BLACK],
                                       white_inc=inc, black_inc=inc)
            started = time.monotonic()
            play = engine.play(board, limit, info=chess.engine.INFO_ALL if side == mischa_color else chess.engine.INFO_NONE)
            spent = time.monotonic() - started
            clock_before = clocks[side]
            clocks[side] -= spent

            if play.move is None or play.move not in board.legal_moves:
                record["result"] = "0-1" if side == chess.WHITE else "1-0"
                record["termination"] = "illegal_move_by_%s" % ("mischa" if side == mischa_color else "stockfish")
                break
            if clocks[side] < 0:
                record["result"] = "0-1" if side == chess.WHITE else "1-0"
                record["termination"] = "time_forfeit_by_%s" % ("mischa" if side == mischa_color else "stockfish")
                break
            clocks[side] += inc

            entry = {"uci": play.move.uci(), "mischa": side == mischa_color,
                     "time": round(spent, 3), "clock": round(clock_before, 3)}
            if side == mischa_color:
                text = (play.info or {}).get("string", "")
                m = INFO_RE.search(text or "")
                if m:
                    entry["depth"] = int(m.group(2))
                    entry["complexity"] = float(m.group(3))
                    entry["pick"] = int(m.group(5))
                    entry["candidates"] = int(m.group(6))
                    entry["reason"] = m.group(8)
                elif text and "only move" in text:
                    entry["reason"] = "only move"
                else:
                    entry["reason"] = "book or other"
            record["moves"].append(entry)
            board.push(play.move)
    except Exception as exc:   # engine crash or protocol error: recorded, game excluded from ratings
        record["error"] = "%s: %s" % (type(exc).__name__, exc)
    finally:
        for e in (mischa, stockfish):
            if e is not None:
                try:
                    e.quit()
                except Exception:
                    try:
                        e.close()
                    except Exception:
                        pass

    record["opening_plies"] = opening_plies
    if record["result"] == "1-0":
        record["score"] = 1.0 if job["mischa_white"] else 0.0
    elif record["result"] == "0-1":
        record["score"] = 0.0 if job["mischa_white"] else 1.0
    elif record["result"] == "1/2-1/2":
        record["score"] = 0.5
    else:
        record["score"] = None
    return record


def game_jobs(args, stage, pairs, games, tc, human_time):
    """pairs: list of (mischa_elo, sf_elo). Openings rotate, colors alternate."""
    rng = random.Random("%s-%d" % (stage, args.seed))
    jobs = []
    for mischa_elo, sf_elo in pairs:
        for g in range(games):
            opening = OPENINGS[(g // 2) % len(OPENINGS)]
            jobs.append({
                "id": "%s-%d-%d-%d" % (stage, mischa_elo, sf_elo, g),
                "stage": stage, "mischa": args.mischa, "stockfish": args.stockfish,
                "mischa_elo": mischa_elo, "sf_elo": sf_elo, "mischa_white": g % 2 == 0,
                "opening": opening, "tc": tc, "human_time": human_time,
                "seed": rng.randint(1, 1000000),
            })
    return jobs


def write_pgn(records, path):
    with open(path, "w") as f:
        for r in records:
            game = chess.pgn.Game()
            node = game
            for uci in r["opening"].split():
                node = node.add_variation(chess.Move.from_uci(uci))
            for mv in r["moves"]:
                node = node.add_variation(chess.Move.from_uci(mv["uci"]))
                if mv["mischa"] and "complexity" in mv:
                    node.comment = "complexity %.2f, pick %d/%d, %s, %.1fs" % (
                        mv["complexity"], mv["pick"], mv["candidates"], mv["reason"], mv["time"])
            m, s = "Mischa %d" % r["mischa_elo"], "Stockfish %d" % r["sf_elo"]
            game.headers["Event"] = "Mischa test suite, %s" % r["stage"]
            game.headers["White"] = m if r["mischa_white"] else s
            game.headers["Black"] = s if r["mischa_white"] else m
            game.headers["Result"] = r["result"] or "*"
            game.headers["TimeControl"] = r["tc"]
            game.headers["Termination"] = r["termination"] or (r["error"] or "")
            print(game, file=f, end="\n\n")


def stage_strength(args, profile, out_dir):
    pairs = [(2000, a) for a in profile["strength_anchors"]]
    jobs = game_jobs(args, "strength", pairs, profile["strength_games"], profile["strength_tc"], False)
    run_jobs(play_game, jobs, os.path.join(out_dir, "strength.jsonl"), args.workers, "strength")


def scale_anchors(level):
    anchors = sorted({min(SF_MAX_ELO, max(SF_MIN_ELO, level + d)) for d in (-200, 0, 200)})
    return anchors


def stage_scale(args, profile, out_dir):
    pairs = [(lvl, a) for lvl in profile["scale_levels"] for a in scale_anchors(lvl)]
    jobs = game_jobs(args, "scale", pairs, profile["scale_games"], profile["scale_tc"], False)
    run_jobs(play_game, jobs, os.path.join(out_dir, "scale.jsonl"), args.workers, "scale")


def stage_human(args, profile, out_dir):
    pairs = [(2000, 2000)]
    jobs = game_jobs(args, "human", pairs, profile["human_games"], profile["human_tc"], True)
    run_jobs(play_game, jobs, os.path.join(out_dir, "human.jsonl"), args.workers, "human")


# ---------------------------------------------------------------------------------------
# Stage: analysis
# ---------------------------------------------------------------------------------------

def win_percent(cp):
    """Lichess' conversion from centipawns to winning chances (0..100)."""
    cp = max(-1000, min(1000, cp))
    return 50.0 + 50.0 * (2.0 / (1.0 + math.exp(-0.00368208 * cp)) - 1.0)


def move_accuracy(wp_before, wp_after):
    """Lichess' per-move accuracy formula (0..100)."""
    acc = 103.1668 * math.exp(-0.04354 * max(0.0, wp_before - wp_after)) - 3.1669
    return max(0.0, min(100.0, acc))


def phase_of(board):
    if board.fullmove_number <= 12:
        return "opening"
    values = {chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
    material = sum(v * len(board.pieces(p, c)) for p, v in values.items() for c in (chess.WHITE, chess.BLACK))
    return "endgame" if material <= 26 else "middlegame"


def analysis_job(job):
    out = {"id": job["id"], "moves": []}
    engine = None
    try:
        engine = chess.engine.SimpleEngine.popen_uci(job["stockfish"])
        engine.configure({"Threads": 1, "Hash": 64})
        board = chess.Board()
        for uci in job["opening"].split():
            board.push_uci(uci)
        limit = chess.engine.Limit(depth=job["depth"])
        for mv in job["moves"]:
            move = chess.Move.from_uci(mv["uci"])
            if mv["mischa"]:
                me = board.turn
                best = engine.analyse(board, limit)["score"].pov(me).score(mate_score=10000)
                played = engine.analyse(board, limit, root_moves=[move])["score"].pov(me).score(mate_score=10000)
                best_c, played_c = max(-1000, min(1000, best)), max(-1000, min(1000, played))
                loss = max(0, best_c - played_c)
                wb, wa = win_percent(best), win_percent(played)
                out["moves"].append({
                    "ply": len(board.move_stack), "phase": phase_of(board), "best": best, "played": played,
                    "loss": loss, "accuracy": round(move_accuracy(wb, wa), 2),
                    "complexity": mv.get("complexity"), "reason": mv.get("reason"),
                    "time": mv["time"], "clock": mv["clock"],
                })
            board.push(move)
    except Exception as exc:
        out["error"] = "%s: %s" % (type(exc).__name__, exc)
    finally:
        if engine is not None:
            try:
                engine.quit()
            except Exception:
                pass
    return out


def stage_analysis(args, profile, out_dir):
    jobs = []
    for stage in ("strength", "human"):
        for r in load_jsonl(os.path.join(out_dir, stage + ".jsonl")):
            if r.get("score") is None:
                continue
            jobs.append({"id": r["id"], "stockfish": args.stockfish, "depth": profile["analysis_depth"],
                         "opening": r["opening"], "moves": r["moves"]})
    if not jobs:
        log("analysis: no games to analyse (run the strength or human stage first)")
        return
    run_jobs(analysis_job, jobs, os.path.join(out_dir, "analysis.jsonl"), args.workers, "analysis")


# ---------------------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------------------

def expected(r, a):
    return 1.0 / (1.0 + 10.0 ** ((a - r) / 400.0))


def mle_rating(results):
    """results: list of (anchor, n_games, total_score). Returns (rating, 95% half-width) or None."""
    games = sum(n for _, n, _ in results)
    score = sum(s for _, _, s in results)
    if games == 0 or score <= 0 or score >= games:
        return None
    r = sum(a * n for a, n, _ in results) / games
    k = math.log(10) / 400.0
    for _ in range(100):
        grad = sum(s - n * expected(r, a) for a, n, s in results) * k
        info = sum(n * expected(r, a) * (1 - expected(r, a)) for a, n, _ in results) * k * k
        if info <= 0:
            return None
        step = grad / info
        r += max(-200, min(200, step))
        if abs(step) < 0.01:
            break
    info = sum(n * expected(r, a) * (1 - expected(r, a)) for a, n, _ in results) * k * k
    return r, 1.96 / math.sqrt(info)


def elo_diff(score):
    score = min(max(score, 1e-3), 1 - 1e-3)
    return -400.0 * math.log10(1.0 / score - 1.0)


def summarize_games(records):
    """Per (mischa_elo, sf_elo): wins, draws, losses, score."""
    table = {}
    for r in records:
        if r.get("score") is None:
            continue
        key = (r["mischa_elo"], r["sf_elo"])
        t = table.setdefault(key, {"w": 0, "d": 0, "l": 0})
        t["w" if r["score"] == 1.0 else ("d" if r["score"] == 0.5 else "l")] += 1
    return table


def pct(values, q):
    if not values:
        return float("nan")
    values = sorted(values)
    k = (len(values) - 1) * q
    f, c = math.floor(k), math.ceil(k)
    return values[int(k)] if f == c else values[f] + (values[c] - values[f]) * (k - f)


def pearson(xs, ys):
    if len(xs) < 3:
        return float("nan")
    mx, my = statistics.mean(xs), statistics.mean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy) if sx and sy else float("nan")


# ---------------------------------------------------------------------------------------
# Stage: report
# ---------------------------------------------------------------------------------------

def stage_report(args, profile, out_dir):
    lines = []
    summary = {"profile": args.profile, "created": now(), "seed": args.seed}
    w = lines.append

    w("# Mischa test report")
    w("")
    w("* Created: %s" % now())
    w("* Profile: `%s`" % args.profile)
    w("* Machine: %s, %s, %d CPUs used" % (platform.node(), cpu_model(), args.workers))
    w("* Mischa: `%s` (%s)" % (args.mischa, engine_name(args.mischa)))
    w("* Stockfish: `%s` (%s)" % (args.stockfish, engine_name(args.stockfish)))
    w("")
    w("Ratings below are on the Stockfish `UCI_Elo` scale, which the Stockfish team calibrates "
      "against the CCRL engine rating list. See `docs/CALIBRATION.md` for how they relate to "
      "FIDE, Lichess and Chess.com ratings. Error bars are 95 % confidence intervals.")
    w("")

    # perft
    perft_path = os.path.join(out_dir, "perft.json")
    if os.path.exists(perft_path):
        rows = json.load(open(perft_path))
        ok = all(r["ok"] for r in rows)
        summary["perft_ok"] = ok
        w("## 1. Move generator (perft)")
        w("")
        w("| position | depth | expected | Mischa | time | result |")
        w("|---|---|---|---|---|---|")
        for r in rows:
            w("| %s | %d | %d | %s | %s ms | %s |" % (r["name"], r["depth"], r["expected"], r["nodes"],
                                                    r["ms"], "ok" if r["ok"] else "**MISMATCH**"))
        w("")
        w("**%s**" % ("All positions match." if ok else "Some positions do not match."))
        w("")

    # robustness
    rob = load_jsonl(os.path.join(out_dir, "robustness.jsonl"))
    if rob:
        tot = {}
        for r in rob:
            for k, v in r["stats"].items():
                tot[k] = tot.get(k, 0) + v
        asan_cmds = sum(r["stats"]["commands"] for r in rob if r.get("asan"))
        summary["robustness"] = tot
        w("## 2. Robustness")
        w("")
        w("Random positions (from random games, special positions for promotions, castling, en "
          "passant, stalemate and mate), random options and every kind of `go` command, "
          "including `stop` and `isready` while thinking.")
        w("")
        w("| check | count |")
        w("|---|---|")
        w("| commands tested | %d |" % tot.get("commands", 0))
        w("| of these with the sanitizer build | %d |" % asan_cmds)
        w("| illegal moves | %d |" % tot.get("illegal", 0))
        w("| crashes | %d |" % tot.get("crash", 0))
        w("| no answer (hang) | %d |" % tot.get("timeout", 0))
        w("| time limit exceeded | %d |" % tot.get("overrun", 0))
        w("| sanitizer reports | %d |" % tot.get("sanitizer", 0))
        w("")
        fails = [f for r in rob for f in r["failures"]]
        if fails:
            w("First failures:")
            w("")
            w("```")
            for f in fails[:15]:
                w(json.dumps(f))
            w("```")
            w("")

    # strength
    strength = load_jsonl(os.path.join(out_dir, "strength.jsonl"))
    if strength:
        w("## 3. Playing strength at UCI_Elo 2000")
        w("")
        res = report_matches(w, strength)
        summary["strength"] = res
        report_terminations(w, strength)

    # scale
    scale = load_jsonl(os.path.join(out_dir, "scale.jsonl"))
    if scale:
        w("## 4. UCI_Elo scale")
        w("")
        w("Each level against Stockfish 200 below, equal and 200 above (within Stockfish's range).")
        w("")
        w("| UCI_Elo | games | measured | difference |")
        w("|---|---|---|---|")
        table = summarize_games(scale)
        xs, ys, out = [], [], []
        for lvl in sorted({k[0] for k in table}):
            results = [(a, t["w"] + t["d"] + t["l"], t["w"] + 0.5 * t["d"]) for (l, a), t in table.items() if l == lvl]
            n = sum(x[1] for x in results)
            est = mle_rating(results)
            if est:
                xs.append(lvl)
                ys.append(est[0])
                out.append({"level": lvl, "games": n, "rating": round(est[0]), "error": round(est[1])})
                w("| %d | %d | %.0f +/- %.0f | %+.0f |" % (lvl, n, est[0], est[1], est[0] - lvl))
            else:
                w("| %d | %d | out of range | |" % (lvl, n))
        w("")
        if len(xs) >= 2:
            mx, my = statistics.mean(xs), statistics.mean(ys)
            b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
            a = my - b * mx
            w("Linear fit: measured = %.0f + %.3f x UCI_Elo (a slope of 1.000 would be a perfect scale)." % (a, b))
            w("")
            summary["scale_fit"] = {"intercept": round(a, 1), "slope": round(b, 4)}
        summary["scale"] = out

    # human timing
    human = load_jsonl(os.path.join(out_dir, "human.jsonl"))
    if human:
        w("## 5. Human timing (HumanTime on, %s)" % human[0]["tc"])
        w("")
        report_matches(w, human)
        report_terminations(w, human)
        mm = [m for r in human if r.get("score") is not None for m in r["moves"] if m["mischa"]]
        times = [m["time"] for m in mm]
        if times:
            w("| measure | value |")
            w("|---|---|")
            w("| Mischa moves | %d |" % len(times))
            w("| think time median | %.1f s |" % pct(times, 0.5))
            w("| think time 10th / 90th percentile | %.1f s / %.1f s |" % (pct(times, 0.1), pct(times, 0.9)))
            w("| longest think | %.1f s |" % max(times))
            obvious = ("recapture", "sees the mate", "takes the free material", "only move")
            sel = [m["time"] for m in mm if m.get("reason") in obvious]
            if sel:
                w("| median think time, obvious moves (recaptures, short mates, free material, only moves) | %.1f s |" % pct(sel, 0.5))
            sel = [m["time"] for m in mm if m.get("reason") not in obvious]
            if sel:
                w("| median think time, all other moves | %.1f s |" % pct(sel, 0.5))
            buckets = complexity_buckets(mm)
            for name, sel in buckets:
                if sel:
                    w("| median think time, %s complexity | %.1f s |" % (name, pct([m["time"] for m in sel], 0.5)))
            cx = [(m["complexity"], m["time"]) for m in mm if m.get("complexity") is not None]
            if cx:
                w("| correlation complexity / think time | %.2f |" % pearson([c for c, _ in cx], [t for _, t in cx]))
            w("")
            summary["human_time"] = {"median": pct(times, 0.5), "p10": pct(times, 0.1), "p90": pct(times, 0.9)}

    # analysis
    ana = load_jsonl(os.path.join(out_dir, "analysis.jsonl"))
    if ana:
        moves = [m for r in ana for m in r["moves"]]
        by_game = {r["id"]: r["moves"] for r in ana}
        games = len([r for r in ana if r["moves"]])
        w("## 6. Quality of Mischa's moves")
        w("")
        w("Every Mischa move from sections 3 and 5 was checked by full-strength Stockfish at depth %d. "
          "Accuracy uses the Lichess formula, so it can be compared with the accuracy Lichess shows "
          "for human games." % profile["analysis_depth"])
        w("")
        w("| group | moves | avg. centipawn loss | accuracy | inaccuracies 50-99 | mistakes 100-299 | blunders 300+ |")
        w("|---|---|---|---|---|---|---|")
        groups = [("all moves", moves)]
        for ph in ("opening", "middlegame", "endgame"):
            groups.append((ph, [m for m in moves if m["phase"] == ph]))
        for name, sel in complexity_buckets(moves):
            groups.append(("%s complexity" % name, sel))
        for name, sel in groups:
            if not sel:
                continue
            n = len(sel)
            w("| %s | %d | %.1f | %.1f %% | %.2f %% | %.2f %% | %.2f %% |" % (
                name, n, statistics.mean(m["loss"] for m in sel), statistics.mean(m["accuracy"] for m in sel),
                100.0 * sum(50 <= m["loss"] < 100 for m in sel) / n,
                100.0 * sum(100 <= m["loss"] < 300 for m in sel) / n,
                100.0 * sum(m["loss"] >= 300 for m in sel) / n))
        w("")
        per_game_acc = [statistics.mean(m["accuracy"] for m in ms) for ms in by_game.values() if ms]
        per_game_err = [sum(100 <= m["loss"] < 300 for m in ms) for ms in by_game.values() if ms]
        per_game_bl = [sum(m["loss"] >= 300 for m in ms) for ms in by_game.values() if ms]
        w("Per game (%d games): accuracy median %.1f %% (10th to 90th percentile %.1f to %.1f %%), "
          "%.2f mistakes and %.2f blunders on average." % (
              games, pct(per_game_acc, 0.5), pct(per_game_acc, 0.1), pct(per_game_acc, 0.9),
              statistics.mean(per_game_err), statistics.mean(per_game_bl)))
        w("")
        summary["analysis"] = {
            "moves": len(moves), "acpl": round(statistics.mean(m["loss"] for m in moves), 2),
            "accuracy": round(statistics.mean(m["accuracy"] for m in moves), 2),
            "mistakes_per_game": round(statistics.mean(per_game_err), 3),
            "blunders_per_game": round(statistics.mean(per_game_bl), 3),
        }

    with open(os.path.join(out_dir, "REPORT.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1)

    for stage in ("strength", "scale", "human"):
        recs = load_jsonl(os.path.join(out_dir, stage + ".jsonl"))
        if recs:
            write_pgn(recs, os.path.join(out_dir, stage + ".pgn"))
    log("report written to %s" % os.path.join(out_dir, "REPORT.md"))


def complexity_buckets(moves):
    return [("low", [m for m in moves if m.get("complexity") is not None and m["complexity"] < 0.33]),
            ("medium", [m for m in moves if m.get("complexity") is not None and 0.33 <= m["complexity"] < 0.66]),
            ("high", [m for m in moves if m.get("complexity") is not None and m["complexity"] >= 0.66])]


def report_matches(w, records):
    table = summarize_games(records)
    w("| Mischa | opponent | games | +  | =  | -  | score | Elo difference |")
    w("|---|---|---|---|---|---|---|---|")
    results = {}
    for (me, sf), t in sorted(table.items()):
        n = t["w"] + t["d"] + t["l"]
        s = (t["w"] + 0.5 * t["d"]) / n
        est = mle_rating([(sf, n, t["w"] + 0.5 * t["d"])])
        diff = ("%+.0f +/- %.0f" % (est[0] - sf, est[1])) if est else "out of range"
        w("| %d | Stockfish %d | %d | %d | %d | %d | %.1f %% | %s |" % (me, sf, n, t["w"], t["d"], t["l"], 100 * s, diff))
        results.setdefault(me, []).append((sf, n, t["w"] + 0.5 * t["d"]))
    w("")
    out = {}
    for me, res in results.items():
        est = mle_rating(res)
        if est:
            w("**Estimated strength of Mischa %d: %.0f +/- %.0f** (maximum likelihood over all opponents)." % (me, est[0], est[1]))
            out[str(me)] = {"rating": round(est[0]), "error": round(est[1]),
                            "games": sum(n for _, n, _ in res)}
    w("")
    return out


def report_terminations(w, records):
    counts = {}
    for r in records:
        key = r["termination"] or ("error: " + (r["error"] or "unknown"))
        counts[key] = counts.get(key, 0) + 1
    w("Game endings: " + ", ".join("%s %d" % (k, v) for k, v in sorted(counts.items(), key=lambda kv: -kv[1])) + ".")
    w("")


def cpu_model():
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown CPU"


def engine_name(path):
    try:
        eng = RawEngine(path)
        eng.send("uci")
        _, seen = eng.wait_for("uciok", 20)
        eng.close()
        for l in seen:
            if l.startswith("id name "):
                return l[8:]
    except Exception:
        pass
    return "unknown"


# ---------------------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mischa", required=True, help="Mischa executable (with its books folder next to it)")
    parser.add_argument("--mischa-asan", help="optional Mischa build with -fsanitize=address,undefined")
    parser.add_argument("--stockfish", required=True, help="Stockfish executable")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="quick")
    parser.add_argument("--stages", default=",".join(ALL_STAGES),
                        help="comma separated list from: " + ", ".join(ALL_STAGES))
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1),
                        help="parallel games / jobs (default: CPUs - 1)")
    parser.add_argument("--out", help="output folder (default: testing/results/<date>-<profile>)")
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()

    for path in (args.mischa, args.stockfish) + ((args.mischa_asan,) if args.mischa_asan else ()):
        if not (os.path.isfile(path) and os.access(path, os.X_OK)):
            sys.exit("not an executable file: %s" % path)
    args.mischa = os.path.abspath(args.mischa)
    args.stockfish = os.path.abspath(args.stockfish)
    if args.mischa_asan:
        args.mischa_asan = os.path.abspath(args.mischa_asan)

    stages = [s.strip() for s in args.stages.split(",") if s.strip()]
    unknown = [s for s in stages if s not in ALL_STAGES]
    if unknown:
        sys.exit("unknown stage(s): " + ", ".join(unknown))

    profile = PROFILES[args.profile]
    out_dir = args.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), "results",
                                       datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + args.profile)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "config.json"), "w") as f:
        json.dump({"args": vars(args), "profile": profile}, f, indent=1)

    log("Mischa test suite, profile %s, %d workers, output %s" % (args.profile, args.workers, out_dir))
    funcs = {"perft": stage_perft, "robustness": stage_robustness, "strength": stage_strength,
             "scale": stage_scale, "human": stage_human, "analysis": stage_analysis, "report": stage_report}
    for stage in ALL_STAGES:
        if stage in stages:
            t0 = time.time()
            log("=== stage %s ===" % stage)
            funcs[stage](args, profile, out_dir)
            log("stage %s finished in %.0f s" % (stage, time.time() - t0))
    log("done")


if __name__ == "__main__":
    main()
