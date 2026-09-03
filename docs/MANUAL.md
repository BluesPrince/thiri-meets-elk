# THIRI meets Elk — Manual

**A measurement harness and method for proving a real-time DSP claim on the Elk
Stomp.** The headline result: a deterministic harmony engine plus five voices of
formant-preserving pitch shifting fits inside the 1.333 ms audio callback on a
dual-core Cortex-A7 — worst block 0.788 of the deadline at 5 voices. This manual
is the operating guide; the narrative and the argument are in [README.md](../README.md),
the full method in [METHOD.md](../METHOD.md), the step-by-step in [RUNBOOK.md](../RUNBOOK.md).

---

## Contents

1. [What this repo is (and isn't)](#1-what-this-repo-is-and-isnt)
2. [The result](#2-the-result)
3. [Running a profiling sweep](#3-running-a-profiling-sweep)
4. [The method, in one page](#4-the-method-in-one-page)
5. [The port file](#5-the-port-file)
6. [The skills](#6-the-skills)
7. [Reading the data](#7-reading-the-data)
8. [Doc index](#8-doc-index)

---

## 1. What this repo is (and isn't)

**Here:** the sweep harness, the confound preflight, the board-lifecycle scripts,
every row of profiling data (including the builds that failed), the figure
generator, the evidence-graded I/O port map, and the method as reusable skills.

**Not here, deliberately:** the harmony engine itself. THIRI's voicing logic,
chord identifier, pitch tracker and shifter voices are closed. The reusable part
is the *measurement discipline* — it applies to any plugin you want to put on any
real-time Linux box.

Hardware: Elk Stomp — STM32MP157, 2× Cortex-A7 @ 400–800 MHz, 32-bit ARMv7,
48 kHz, **64-sample buffer** (1.333 ms). Elk Audio OS 1.2.2, Sushi 1.3.0.

---

## 2. The result

`1.0` = the 1.333 ms deadline. Every row measured on hardware.

| voices | avg | worst block |
|---|---|---|
| 0 *(engine + tracker only)* | 0.568 | 0.726 |
| 1 | 0.577 | 0.749 |
| 3 | 0.588 | 0.757 |
| **5** | **0.592** | **0.788** |

The fifth voice costs almost exactly what the first did — **0.005 of the block
period per voice**. The flatness is the finding, not the headroom.

---

## 3. Running a profiling sweep

Needs an Elk board, Elk's desktop devkit, and a plugin of your own with a
parameter the harness can set over gRPC and read back.

```bash
tools/preflight.sh mind@<board-ip>            # confound checklist — must be all PASS/INFO
tools/sushi_board.sh start mind@<board-ip>    # SIGINT-only lifecycle
python3 tools/profile_sweep.py \
    --host board --addr <board-ip>:51051 --ssh mind@<board-ip> \
    --voices 0,1,2,3,4,5 --settle 10 --measure 60 --notes "sweep 1 of 3"
tools/sushi_board.sh stop mind@<board-ip>     # SIGINT only — SIGTERM wedges audio_evl
python3 tools/make_figures.py                 # figures, regenerated from the CSV
```

The sweep axis here is `num_voices` (a gate on the shifter voices). Point it at
whatever parameter your own plugin scales along.

> **Run `preflight.sh` before every sweep.** It checks competing load, the CPU
> governor, affinity and RT priority, the NEON attributes actually present in the
> deployed binary, and denormals — and records the answers per row. A confound
> found later **voids every row taken before the fix**; re-sweep, don't patch the
> numbers.

---

## 4. The method, in one page

Six disciplines (full text in [METHOD.md](../METHOD.md)):

1. **The bit-identity gate.** A change is either provably output-identical
   (render a fixed input offline, `sha256`, compare to a committed baseline) or it
   is a change. Every optimisation passed it or was reverted.
2. **Void the rows.** A confound voids all measurements before the fix. Re-sweep.
3. **The confound checklist** (`tools/preflight.sh`) — run before every sweep.
4. **Hash, don't timestamp.** The board has no RTC and reports 2025; mtimes are
   meaningless. Every row records the `sha256` of the deployed binary.
5. **Figures are generated from the data, never hand-typed** (`tools/make_figures.py`
   asserts the claims and emits the SVGs — it caught three already-published errors).
6. **The average lies; measure the worst block.** Sushi has no xrun counter, so
   `max ≥ 1.0` is the proxy. Every headline failure here was invisible to average CPU.

Two findings that generalise:

- **Pin your control surface** (`taskset -c 0`) or it lands on the audio core and
  eats the deadline silently — worst block 0.77 → 2.27 unpinned, while the average
  never moved. Elk's reference launcher does not pin.
- **Vectorising is not free on an A7** — measured 10.7 cycles per vector op in
  accumulation chains, about what scalar VFP does. Budget from measurement, not the
  ISA datasheet.

---

## 5. The port file

`elk-stomp-ports.yaml` is the machine-readable board I/O map, every jack graded by
**evidence level** (`verified` > `measured` > `documented` > `silkscreen` >
`inferred` > `null`). `elk-stomp-ports.json` is its generated twin.

```bash
tools/validate-ports.py        # validate the YAML and regenerate the JSON twin
```

Verified this cycle: GUITAR IN L = engine ch 0; the two output pairs (0/1 vs 2/3)
are physically distinct; LINE OUT carries the 2/3 pair together with HEADPHONE OUT;
Sushi under a systemd **user unit** gets zero audio callbacks (launch from a pam
shell instead). Raise a level only from a result, and record the command that
produced it as the evidence.

---

## 6. The skills

`skills/` holds the board knowledge and the measurement method as agent-actionable
skills (kept in sync with the installed skill set by `tools/sync-skills.sh`). The
deny list of what not to sync lives **outside** the repo at
`~/.thiri/skills-deny.txt` — the gate fails closed if it is missing.

---

## 7. Reading the data

`data/profiling-results.csv` is append-only and contains every run, including the
failures. Read top-to-bottom it is the actual story — three regimes:

| build | avg @ 5 voices | worst block | verdict |
|---|---|---|---|
| phase vocoder, unsliced tracker | 2.08 | 5.94 | tracker spike, 6× over |
| phase vocoder, τ-sliced tracker | 1.83 | 2.93 | over real time at ONE voice |
| **PSOLA, τ-sliced tracker** | **0.59** | **0.79** | ships |

The cheap algorithm won by 52× on marginal cost per voice (PSOLA 0.005 vs phase
vocoder 0.254). The board was never the constraint; choosing an algorithm that
suited the constraint was.

---

## 8. Doc index

| doc | topic |
|---|---|
| [README.md](../README.md) | the argument + the result |
| [METHOD.md](../METHOD.md) | the six disciplines in full |
| [RUNBOOK.md](../RUNBOOK.md) | step-by-step, and the reasoning behind each choice |
| `elk-stomp-ports.yaml` | evidence-graded board I/O map |
| `data/profiling-results.csv` | every row, including failures |

*Numbers measured on Elk Audio OS 1.2.2, Sushi 1.3.0, STM32MP157 @ 800 MHz,
performance governor, 64-sample buffer at 48 kHz.*
