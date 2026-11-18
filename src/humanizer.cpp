/*
Mischa, a human-like chess engine in the style of Mikhail Tal.
Copyright (C) 2026 Yunus Imanov
Based on OpenTal / Rodent by Pawel Koziol and Sungorus by Pablo Vazquez.

This file is part of Mischa.

Mischa is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

Mischa is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without
even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
General Public License for more details.

You should have received a copy of the GNU General Public License along with this program.
If not, see <http://www.gnu.org/licenses/>.
*/

#include "rodent.h"
#include "humanizer.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <random>
#include <thread>

sHuman Human;

static std::mt19937_64 rng(12345);

static double Uniform() {
    return std::uniform_real_distribution<double>(0.0, 1.0)(rng);
}

static double Gauss() {
    return std::normal_distribution<double>(0.0, 1.0)(rng);
}

static int ClampInt(int v, int lo, int hi) {
    return v < lo ? lo : (v > hi ? hi : v);
}

static double ClampDbl(double v, double lo, double hi) {
    return v < lo ? lo : (v > hi ? hi : v);
}

// ---------------------------------------------------------------------------------------
// Parameters
// ---------------------------------------------------------------------------------------

void sHuman::Init() {
    limit_strength = true;
    human_time = true;
    verbose = false;
    flair = 100;
    seed = 0;
    ResetHistory();
    SetElo(HUMAN_DEFAULT_ELO);
    Reseed();
}

void sHuman::ResetHistory() {
    last_to_sq = -1;
    last_was_capture = false;
}

void sHuman::SetElo(int elo_in) {
    elo = ClampInt(elo_in, HUMAN_MIN_ELO, HUMAN_MAX_ELO);
    Par.book_depth = limit_strength ? BookPlies() : 256;
}

void sHuman::Reseed() {
    if (seed) rng.seed((U64)seed);
    else      rng.seed((U64)std::chrono::high_resolution_clock::now().time_since_epoch().count() ^ Glob.game_key);
}

// All strength parameters are simple functions of the target Elo. The constants were chosen
// so that the default (2000) plays like a solid club player; tools/calibrate.py can be used
// to measure the result and adjust them.

int sHuman::MaxDepth() const {
    return ClampInt(3 + (elo - 1000) / 200, 3, 11);        // 2000 -> 8
}

int sHuman::Candidates() const {
    return 6;
}

int sHuman::NoiseSigma() const {
    return 10 + (HUMAN_MAX_ELO - elo) / 40;                // 2000 -> 25 cp
}

int sHuman::BlunderPerMille() const {
    return 3 + (HUMAN_MAX_ELO - elo) / 50;                 // 2000 -> 15 (1.5 %)
}

int sHuman::NormalLossCap() const {
    return 40 + (HUMAN_MAX_ELO - elo) / 6;                 // 2000 -> 140 cp
}

int sHuman::BlunderLossCap() const {
    return 100 + (HUMAN_MAX_ELO - elo) / 4;                // 2000 -> 250 cp
}

int sHuman::MateVision() const {
    if (elo >= 2300) return 4;
    if (elo >= 1700) return 3;
    if (elo >= 1300) return 2;
    return 1;
}

int sHuman::BookPlies() const {
    return ClampInt((elo - 800) / 50, 4, 40);              // 2000 -> 24 plies (12 moves)
}

// ---------------------------------------------------------------------------------------
// Multi-candidate search with a depth limit
// ---------------------------------------------------------------------------------------

void cEngine::HumanSearch(POS *p, int max_depth, int n_cand, sHumanResult *res) {

    int val[MAX_PV + 1];
    Line line[MAX_PV + 1];
    int prev_best = 0;
    const int saved_multipv = Glob.multiPv;

    n_cand = ClampInt(n_cand, 1, MAX_PV);

    for (int i = 0; i <= MAX_PV; i++) {
        val[i] = 0;
        line[i].pv[0] = 0;
    }

    res->n = 0;
    res->depth = 0;
    res->best_changes = 0;
    res->first_impression = 0;

    // A value above one makes Slowdown() poll for "stop" and for the time limit
    // and keeps SearchRoot() from printing its own single-pv output.

    Glob.multiPv = Max(2, n_cand);
    mFlRootChoice = false;
    AgeHist();

    for (mRootDepth = 1; mRootDepth <= max_depth; mRootDepth++) {

        int found = 0;
        Glob.ClearAvoidList();

        for (int i = 1; i <= n_cand; i++) {
            line[i].pv[0] = 0;
            val[i] = Widen(p, mRootDepth, line[i].pv, val[i]);
            if (Glob.abort_search && mRootDepth > 1) break;
            if (!line[i].pv[0] || !p->Legal(line[i].pv[0])) break;
            Glob.SetAvoidMove(i, line[i].pv[0]);
            found = i;
        }

        // results of an interrupted iteration are not trustworthy, keep the previous ones
        // (depth 1 cannot be interrupted, see SearchRoot)

        if (Glob.abort_search && mRootDepth > 1) break;
        if (found == 0) break;

        // sort candidates by score, best first (aspiration windows can leave them unordered)

        int order[MAX_PV + 1];
        for (int i = 0; i < found; i++) order[i] = i + 1;
        std::stable_sort(order, order + found, [&](int a, int b) { return val[a] > val[b]; });

        res->n = found;
        res->depth = mRootDepth;
        for (int i = 0; i < found; i++) {
            const int src = order[i];
            res->move[i] = line[src].pv[0];
            res->score[i] = val[src];
            memcpy(res->pv[i], line[src].pv, sizeof(line[src].pv));
        }

        for (int i = found - 1; i >= 0; i--)
            DisplayPv(i + 1, res->score[i], res->pv[i]);

        if (mRootDepth == 2) res->first_impression = res->move[0];
        if (mRootDepth >= 3 && res->move[0] != prev_best) res->best_changes++;
        prev_best = res->move[0];

        // stop early once a forced mate is proven within the searched depth

        const int top = res->score[0];
        if (top > MAX_EVAL || top < -MAX_EVAL) {
            const int mate_plies = MATE - Abs(top);
            if (mate_plies <= mRootDepth) break;
        }
    }

    if (!res->first_impression && res->n) res->first_impression = res->move[0];

    Glob.ClearAvoidList();
    Glob.multiPv = saved_multipv;
}

// ---------------------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------------------

static cEngine &MainEngine() {
#ifndef USE_THREADS
    return EngineSingle;
#else
    return Engines.front();
#endif
}

static int CollectLegalMoves(POS *p, int *out) {

    int list[MAX_MOVES * 2];
    int *end = p->GenerateCaptures(list);
    end = p->GenerateQuiet(end);

    int n = 0;
    for (int *m = list; m < end; m++) {
        POS tmp = *p;
        tmp.DoMove(*m);
        if (tmp.Illegal()) continue;
        out[n++] = *m;
    }
    return n;
}

static bool IsCapture(const POS *p, int move) {
    return p->mPc[Tsq(move)] != NO_PC || MoveType(move) == EP_CAP;
}

static bool GivesCheck(const POS *p, int move) {
    POS tmp = *p;
    tmp.DoMove(move);
    return tmp.InCheck();
}

static int SquareDistance(int a, int b) {
    return Max(Abs((a & 7) - (b & 7)), Abs((a >> 3) - (b >> 3)));
}

// Scores on a single scale where mates are large but finite

static int UtilityScore(int score) {
    if (score > MAX_EVAL)  return  3000 - (MATE - score);
    if (score < -MAX_EVAL) return -3000 + (MATE + score);
    return ClampInt(score, -2500, 2500);
}

// Small bonus for the kind of moves Tal liked: checks, captures, sacrifices and moves
// that bring pieces close to the enemy king. Only matters between moves of similar value.

static int FlairBonus(POS *p, int move) {

    if (Human.flair == 0) return 0;

    int bonus = 0;
    const eColor op = ~p->mSide;
    const int to = Tsq(move);

    if (GivesCheck(p, move)) bonus += 6;

    if (IsCapture(p, move)) {
        bonus += 3;
        if (MoveType(move) != EP_CAP && p->Swap(Fsq(move), to) < 0) bonus += 6;   // sacrifice
    }

    if (p->TpOnSq(Fsq(move)) != K && SquareDistance(to, p->KingSq(op)) <= 2) bonus += 3;

    return bonus * Human.flair / 100;
}

static void WaitUntil(int start_ms, int target_ms) {

    char command[80];

    while (GetMS() - start_ms < target_ms) {
        if (InputAvailable()) {
            ReadLine(command, sizeof(command));
            if (strcmp(command, "stop") == 0) return;
            if (strcmp(command, "quit") == 0) exit(0);
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
}

static int EstimatedMovesLeft(int movestogo, bool movestogo_given) {
    if (movestogo_given) return Max(1, movestogo);
    const int move_no = Glob.moves_from_start / 2 + 1;
    return Max(18, 42 - move_no * 45 / 100);
}

// Average time a human would spend on a move with this clock

static int AverageMoveTime(int base, int inc, int movestogo, bool movestogo_given) {
    const int est = EstimatedMovesLeft(movestogo, movestogo_given);
    return base / est + inc * 85 / 100;
}

// Hard upper limit for one move: never more than 15 % of the clock, and always
// keep a reserve for lag.

static int MoveTimeCap(int base, int avg) {
    int cap = Min(base * 15 / 100, avg * 4);
    cap = Min(cap, base - Glob.time_buffer - 100);
    return Max(cap, 20);
}

// ---------------------------------------------------------------------------------------
// Main entry point
// ---------------------------------------------------------------------------------------

bool HumanGo(POS *p, int base, int inc, int movestogo, bool movestogo_given, bool strict_time) {

    if (!Human.limit_strength) return false;   // full strength: use the original engine
    if (Glob.multiPv > 1) return false;        // analysis mode: use the original engine
    if (Glob.pondering) return false;          // humans do not ponder in this sense

    const bool has_clock = !strict_time && base > 0;
    const int start = cEngine::msStartTime;

    // infinite analysis without a clock is left to the normal search

    if (!strict_time && !has_clock) return false;

    int legal[MAX_MOVES];
    const int n_legal = CollectLegalMoves(p, legal);
    if (n_legal == 0) return false;

    int avg = 0, cap = 0;

    if (has_clock) {
        avg = AverageMoveTime(base, inc, movestogo, movestogo_given);
        cap = MoveTimeCap(base, avg);
        cEngine::msMoveTime = cap;
    }

    // forced move: answer quickly, like a human would

    if (n_legal == 1) {
        if (has_clock && Human.human_time)
            WaitUntil(start, Min(cap, 300 + (int)(Uniform() * 500)));
        int pv[2] = { legal[0], 0 };
        if (Human.verbose) printf("info string Mischa: only move\n");
        ExtractMove(pv);
        return true;
    }

    // search the candidate moves

    sHumanResult res;
    const int depth = Min(Human.MaxDepth(), cEngine::msSearchDepth);
    MainEngine().HumanSearch(p, depth, Min(Human.Candidates(), n_legal), &res);
    Glob.abort_search = true;

    if (res.n == 0) {
        int pv[2] = { legal[0], 0 };
        ExtractMove(pv);
        return true;
    }

    // ---- describe the position ----

    int util[MAX_PV + 1], loss[MAX_PV + 1];
    bool forcing[MAX_PV + 1];

    for (int i = 0; i < res.n; i++) {
        util[i] = UtilityScore(res.score[i]);
        forcing[i] = IsCapture(p, res.move[i]) || GivesCheck(p, res.move[i]);
    }
    for (int i = 0; i < res.n; i++) loss[i] = util[0] - util[i];

    const int gap = res.n > 1 ? loss[1] : 0;
    const int best_move = res.move[0];
    const int best_score = res.score[0];

    // complexity in [0, 1]

    double instability = res.depth > 2 ? (double)res.best_changes / (res.depth - 2) : 0.0;
    instability = ClampDbl(instability, 0.0, 1.0);

    const int pieces = BB.PopCnt(p->OccBb() & ~(p->mTpBb[P] | p->mTpBb[K]));
    const double material = ClampDbl(pieces / 14.0, 0.0, 1.0);

    double only_move = 0.0;
    if (gap >= 120) only_move = forcing[0] ? 0.3 : 1.0;

    const double mobility = ClampDbl(n_legal / 40.0, 0.0, 1.0);

    double complexity = 0.35 * instability + 0.20 * material + 0.25 * only_move + 0.20 * mobility;
    if (p->InCheck()) complexity *= 0.7;
    complexity = ClampDbl(complexity, 0.0, 1.0);

    // obvious moves are never missed

    bool obvious = false;
    const char *reason = "choice";

    if (best_score > MAX_EVAL && (MATE - best_score + 1) / 2 <= Human.MateVision()) {
        obvious = true; reason = "sees the mate";
    } else if (Human.last_was_capture && Tsq(best_move) == Human.last_to_sq
               && IsCapture(p, best_move) && gap >= 80) {
        obvious = true; reason = "recapture";
    } else if (IsCapture(p, best_move) && MoveType(best_move) != EP_CAP
               && p->Swap(Fsq(best_move), Tsq(best_move)) >= 200 && gap >= 150) {
        obvious = true; reason = "takes the free material";
    }

    // pressure from the clock

    // (only modelled when human timing is on; with HumanTime off the engine plays
    // fast games without the extra clock-related mistakes, which is what calibration uses)

    double pressure = 1.0;
    if (has_clock && Human.human_time) {
        if (avg < 1500)      pressure = 1.5;
        else if (avg < 4000) pressure = 1.25;
        if (base < 10000)    pressure += 0.3;
    }

    double sigma = Human.NoiseSigma() * (0.6 + complexity) * pressure;
    if (Abs(best_score) > 600 && Abs(best_score) < MAX_EVAL) sigma *= 1.3;   // the game is decided, relax

    const double blunder_chance = Human.BlunderPerMille() / 1000.0 * (0.3 + 1.7 * complexity) * pressure;

    // ---- choose a move ----

    int chosen = 0;

    if (!obvious) {

        // ordinary play: each candidate is judged with some noise

        double best_u = -1e9;
        for (int i = 0; i < res.n; i++) {
            if (loss[i] > Human.NormalLossCap()) continue;
            const double u = util[i] + FlairBonus(p, res.move[i]) + Gauss() * sigma;
            if (u > best_u) { best_u = u; chosen = i; }
        }

        // occasionally a real mistake: usually the move that looked best at first sight

        if (Uniform() < blunder_chance) {

            int options[MAX_PV + 1], n_opt = 0, impression = -1;

            for (int i = 1; i < res.n; i++) {
                if (loss[i] < 50 || loss[i] > Human.BlunderLossCap()) continue;
                options[n_opt++] = i;
                if (res.move[i] == res.first_impression) impression = i;
            }

            if (impression >= 0 && Uniform() < 0.7) {
                chosen = impression; reason = "trusts the first impression";
            } else if (n_opt > 0) {
                chosen = options[(int)(Uniform() * n_opt) % n_opt]; reason = "overlooks something";
            }
        }
    }

    // ---- spend the time ----

    if (has_clock && Human.human_time) {

        const int move_no = Glob.moves_from_start / 2 + 1;
        double factor = obvious ? 0.25 : 0.45 + 1.6 * complexity;
        if (move_no <= 10) factor *= 0.55;                     // openings are played briskly
        factor *= std::exp(Gauss() * 0.35);                    // humans are not metronomes

        int target = (int)(avg * factor);
        const int floor_ms = base > 30000 ? 400 : (base > 5000 ? 150 : 30);
        target = ClampInt(target, Min(floor_ms, cap), cap);

        WaitUntil(start, target);
    }

    if (Human.verbose)
        printf("info string Mischa: elo %d depth %d complexity %.2f sigma %.0f pick %d/%d loss %d (%s)\n",
               Human.elo, res.depth, complexity, sigma, chosen + 1, res.n, loss[chosen], reason);

    ExtractMove(res.pv[chosen]);
    return true;
}

// A short pause before book moves when playing on a clock

void HumanBookDelay(int base) {
    if (!Human.limit_strength || !Human.human_time || base <= 0) return;
    const int target = Min(base / 50, 300 + (int)(Uniform() * 1200));
    WaitUntil(cEngine::msStartTime, target);
}
