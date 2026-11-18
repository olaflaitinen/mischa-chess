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

#pragma once

#include "rodent.h"

// Human-like move selection layer.
//
// Instead of always playing the engine's best move, Mischa searches a small set of
// candidate moves to a limited depth, estimates how difficult the position is for a
// human, and then picks a move the way a club player would: usually a good one, now
// and then a slightly worse one, and on rare occasions a real mistake. Mistakes become
// more likely in complicated positions and under time pressure. Thinking time is also
// spent like a human: quick in obvious positions, longer when the position is sharp.

constexpr int HUMAN_MIN_ELO     = 1000;
constexpr int HUMAN_MAX_ELO     = 2600;
constexpr int HUMAN_DEFAULT_ELO = 2000;

struct sHuman {
    bool limit_strength;    // UCI_LimitStrength: humanizer on/off
    bool human_time;        // HumanTime: spend thinking time like a human
    bool verbose;           // HumanVerbose: print the reasoning as "info string"
    int  elo;               // UCI_Elo: target playing strength (FIDE-like scale)
    int  flair;             // Flair: 0..200, preference for forcing and sacrificial moves (100 = Tal)
    int  seed;              // RandomSeed: 0 = random, otherwise reproducible games

    // information about the last move played on the board, filled by POS::ParseMoves()

    int  last_to_sq;
    bool last_was_capture;

    void Init();
    void ResetHistory();
    void SetElo(int elo_in);
    void Reseed();

    // strength parameters derived from Elo

    int MaxDepth() const;
    int Candidates() const;
    int NoiseSigma() const;        // centipawns
    int BlunderPerMille() const;   // base chance of a real mistake per move
    int NormalLossCap() const;     // largest loss accepted from ordinary noise
    int BlunderLossCap() const;    // largest loss accepted in a mistake
    int MateVision() const;        // mates up to this many moves are never missed
    int BookPlies() const;
};

extern sHuman Human;

// Returns true when the humanizer handled the "go" command and printed "bestmove".
// Returns false when the normal engine search should be used instead.

bool HumanGo(POS *p, int base, int inc, int movestogo, bool movestogo_given, bool strict_time);

// Short human-like pause before playing a book move on a clock.

void HumanBookDelay(int base);
