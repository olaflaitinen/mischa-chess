#!/usr/bin/env python3
"""Smoke tests for the Mischa UCI engine.

Usage: python3 tests/smoke_test.py path/to/mischa

Only the Python standard library is needed. Every test talks to the engine through the
UCI protocol, the same way a chess GUI or lichess-bot does.
"""

import queue
import re
import subprocess
import sys
import threading
import time

MOVE_RE = re.compile(r"^bestmove ([a-h][1-8][a-h][1-8][qrbn]?)")


class Engine:
    def __init__(self, path):
        self.proc = subprocess.Popen(
            [path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
        )
        self.lines = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        for line in self.proc.stdout:
            self.lines.put(line.rstrip("\r\n"))

    def send(self, command):
        self.proc.stdin.write(command + "\n")
        self.proc.stdin.flush()

    def wait_for(self, prefix, timeout=30.0):
        """Return (matching line, all lines read) once a line starts with prefix."""
        seen = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                line = self.lines.get(timeout=0.1)
            except queue.Empty:
                if self.proc.poll() is not None:
                    break
                continue
            seen.append(line)
            if line.startswith(prefix):
                return line, seen
        raise AssertionError("timed out waiting for %r, got: %s" % (prefix, seen[-10:]))

    def bestmove(self, position, go, options=None, timeout=60.0):
        for name, value in (options or {}).items():
            self.send("setoption name %s value %s" % (name, value))
        self.send("ucinewgame")
        self.send(position)
        self.send("isready")
        self.wait_for("readyok")
        self.send(go)
        line, seen = self.wait_for("bestmove", timeout)
        match = MOVE_RE.match(line)
        assert match, "malformed bestmove line: %r" % line
        return match.group(1), seen

    def close(self):
        try:
            self.send("quit")
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


FAILURES = []


def check(name, condition, detail=""):
    status = "ok  " if condition else "FAIL"
    print("[%s] %s%s" % (status, name, (": " + detail) if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    eng = Engine(sys.argv[1])
    try:
        # handshake and options

        eng.send("uci")
        _, seen = eng.wait_for("uciok")
        text = "\n".join(seen)
        check("engine identifies as Mischa", "id name Mischa" in text)
        check("author line present", "id author Yunus Imanov" in text)
        for option in ("UCI_LimitStrength", "UCI_Elo", "HumanTime", "Flair", "RandomSeed", "HumanVerbose"):
            check("option %s advertised" % option, "option name %s " % option in text)

        eng.send("setoption name HumanTime value false")
        eng.send("setoption name HumanVerbose value true")

        # a normal human-mode move on a clock

        move, seen = eng.bestmove(
            "position startpos moves e2e4 e7e5 g1f3 b8c6 f1c4 g8f6 d2d3 f8c5 c2c3 d7d6 "
            "e1g1 e8g8 a2a4 a7a6 b2b4 c5a7 h2h3 h7h6",
            "go wtime 60000 btime 60000 winc 1000 binc 1000",
        )
        check("human mode returns a move", bool(move))
        check("human mode explains its choice", any("info string Mischa:" in l for l in seen))

        # mate in one is never missed (white: Qh5xf7#)

        mate_fen = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"
        hits = 0
        for _ in range(10):
            move, _ = eng.bestmove("position fen " + mate_fen, "go wtime 30000 btime 30000")
            hits += move == "h5f7"
        check("mate in one found 10 out of 10 times", hits == 10, "found %d" % hits)

        # the only legal move is played

        only_fen = "7k/8/8/8/8/8/6q1/7K w - - 0 1"
        move, _ = eng.bestmove("position fen " + only_fen, "go wtime 30000 btime 30000")
        check("only legal move is played", move == "h1g2", move)

        # a free queen is taken (white Rd1xd8)

        free_fen = "3qk3/8/8/8/8/8/8/3RK3 w - - 0 1"
        hits = 0
        for _ in range(10):
            move, _ = eng.bestmove("position fen " + free_fen, "go wtime 30000 btime 30000")
            hits += move == "d1d8"
        check("free queen taken 10 out of 10 times", hits == 10, "found %d" % hits)

        # fixed depth and fixed time searches still work

        move, _ = eng.bestmove("position startpos", "go depth 4")
        check("go depth works", bool(move))
        move, _ = eng.bestmove("position startpos moves e2e4", "go movetime 300")
        check("go movetime works", bool(move))

        # full strength (original OpenTal search)

        eng.send("setoption name UCI_LimitStrength value false")
        move, seen = eng.bestmove(
            "position fen r1bq1rk1/pp2bppp/2n1pn2/3p4/2PP4/2N1PN2/PP3PPP/R2QKB1R w KQ - 0 8", "go depth 8")
        check("full strength search returns a move", bool(move))
        check("full strength reaches depth 8", any(l.startswith("info depth 8") for l in seen))
        eng.send("setoption name UCI_LimitStrength value true")

        # "stop" interrupts an infinite analysis

        eng.send("position startpos")
        eng.send("go infinite")
        time.sleep(0.5)
        eng.send("stop")
        line, _ = eng.wait_for("bestmove", 10)
        check("stop ends go infinite", bool(MOVE_RE.match(line)))

        # human timing: with HumanTime on the engine takes a human amount of time

        eng.send("setoption name HumanTime value true")
        start = time.time()
        move, _ = eng.bestmove(
            "position startpos moves e2e4 c7c5 g1f3 d7d6 d2d4 c5d4 f3d4 g8f6 b1c3 a7a6 "
            "c1g5 e7e6 f2f4 f8e7 d1f3 d8c7 e1c1 b8d7",
            "go wtime 20000 btime 20000 winc 0 binc 0",
        )
        elapsed = time.time() - start
        check("human time stays within budget", 0.0 < elapsed < 3.5, "%.2f s" % elapsed)

        # "stop" during the human pause returns at once

        eng.send("ucinewgame")
        eng.send("position startpos moves e2e4 c7c5 g1f3 d7d6 d2d4 c5d4 f3d4 g8f6 b1c3 a7a6")
        eng.send("go wtime 600000 btime 600000")
        time.sleep(0.3)
        start = time.time()
        eng.send("stop")
        line, _ = eng.wait_for("bestmove", 10)
        check("stop interrupts the human pause", time.time() - start < 2.0)
    finally:
        eng.close()

    print()
    if FAILURES:
        print("%d check(s) failed: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
