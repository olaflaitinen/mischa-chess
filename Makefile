# Simple build without CMake:  make            (portable)
#                              make popcnt     (x86-64 CPUs with POPCNT, faster)
#                              make test       (runs the UCI smoke test)

CXX      ?= g++
CXXFLAGS ?= -O3
override CXXFLAGS += -std=c++14 -DNDEBUG -Wall -Wno-unknown-pragmas
override LDFLAGS += -pthread
SRC       = $(wildcard src/*.cpp)
EXE       = mischa

.PHONY: all popcnt native test clean

all: $(EXE)

$(EXE): $(SRC) src/*.h
	$(CXX) $(CXXFLAGS) -DNO_MM_POPCNT $(SRC) -o $(EXE) $(LDFLAGS)

popcnt: $(SRC) src/*.h
	$(CXX) $(CXXFLAGS) -mpopcnt $(SRC) -o $(EXE) $(LDFLAGS)

native: $(SRC) src/*.h
	$(CXX) $(CXXFLAGS) -march=native $(SRC) -o $(EXE) $(LDFLAGS)

test: $(EXE)
	python3 tests/smoke_test.py ./$(EXE)

clean:
	rm -f $(EXE)
