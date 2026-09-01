# THIRI meets Elk Audio

**Measuring whether a real-time music-intelligence layer fits inside a 1.333 ms audio
callback on a £-few-hundred pedal.** It does. Here is the harness, the data, and the
method — so you can do it to your own DSP and disbelieve us properly.

---

## Why this measurement, and not another one

Agentic music tools are going to need two things they mostly do not have yet.

**A theory of correctness.** Today's generative audio models produce finished waveforms.
They are remarkable, and you cannot ask one to change the third of a chord — because
there is no chord, there is a spectrogram. An agent that makes musical decisions needs a
layer where decisions *exist*: where "flat 9 over a dominant" is a thing that is either
right or wrong, inspectable and constrainable before it becomes audio.

**A real-time substrate.** Music happens at a deadline. An agent that only runs in a
cloud GPU is not in the loop with a player — it is a rendering service. If musical
intelligence is going to sit in the signal path, it has to survive inside the audio
callback, on the hardware people actually put on a stage.

The first is a design problem. The second is an empirical one, and it is the one this
repo answers: **does a deterministic harmony engine plus five voices of pitch shifting
fit in 1.333 ms on a dual-core Cortex-A7?**

The engine here is [THIRI](https://thiri.ai). The hardware is the
[Elk Audio](https://elk.audio) Stomp — STM32MP157, two Cortex-A7 cores at 400–800 MHz,
32-bit ARMv7, 48 kHz, **64-sample buffer**. Elk Audio OS 1.2.2, Sushi 1.3.0.

**The engine is not in this repo, and does not need to be.** What is reusable is the
measurement discipline, and it applies to any plugin you want to put on any real-time
Linux box.

---

## The answer

Five pitch-shifted harmony voices, plus full chord-intelligence and pitch tracking, on a
stock Stomp. `1.0` = the 1.333 ms deadline. Every row measured on hardware.

| voices | avg | worst block |
| --- | --- | --- |
| 0 *(engine + tracker only)* | 0.568 | 0.726 |
| 1 | 0.577 | 0.749 |
| 3 | 0.588 | 0.757 |
| **5** | **0.592** | **0.788** |

Three sweeps of six points each, 60 s per point. **The fifth voice costs almost exactly
what the first did** — marginal cost is **0.005 of the block period per voice**.

That flatness is the finding. Not the headroom.

---

## Three regimes, visible in one CSV

`data/profiling-results.csv` is append-only and contains every run including the failures.
Reading it top to bottom is the actual story:

| build | avg @ 5 voices | worst block | verdict |
| --- | --- | --- | --- |
| Phase vocoder, unsliced tracker | 2.08 | **5.94** | tracker spike, 6× over deadline |
| Phase vocoder, tau-sliced tracker | 1.83 | 2.93 | **over real time at ONE voice** (1.07 avg) |
| PSOLA, tau-sliced tracker | **0.59** | **0.79** | ships |

Three things worth taking from that table.

**A worst-case spike is not a CPU problem.** The first build averaged 0.67–0.80 — healthy
by any CPU meter — while one block in eight ran 5.94× over deadline, because an O(n²)
analysis fired once per hop and landed entirely in a single block. Average CPU cannot see
this. Spreading the identical arithmetic across the hop's eight blocks dropped the worst
block **8×** with no change in results.

**No buffer size fixes an average.** The phase vocoder exceeds real time at *one voice*
(1.07 avg). Doubling the buffer doubles the deadline and the work; the fraction does not
move. That build was never going to ship and the data said so before anyone tuned it.

**The cheap algorithm won by 52×.** Marginal cost per voice: PSOLA **0.005**, phase
vocoder **0.254**, measured over the same 0→5 span. The board was never the constraint.
Choosing an algorithm that suited the constraint was.

---

## Two findings that generalise beyond us

**Pin your control surface, or it will eat your deadline silently.** The audio thread is
pinned to CPU 1 by the driver; CPU 0 sits idle. A hardware daemon and a control app,
left unpinned, land on the audio core:

| | worst block |
| --- | --- |
| audio host alone | 0.770 |
| + control surface, unpinned | **2.273** ← missed deadlines |
| + control surface, `taskset -c 0` | 0.760 |

**The average never moved** — ~0.60 in all three cases. Watching a CPU meter you would
have seen a comfortable 60% while audio dropped out. Elk's reference launcher does not
pin, so this is worth checking in any Elk app, not just ours.

**Vectorising is not free money on an A7.** We assumed NEON would give ~4× on the
tracker's multiply-accumulate inner loop. Measured with a known-instruction-count
calibration: **10.7 cycles per vector operation** in accumulation chains — about what
scalar VFP does. GCC also will not auto-vectorise float loops without
`-funsafe-math-optimizations`. Budget from measurement, not from the ISA datasheet.

---

## The method — the actual contribution

Six disciplines, described in full in **[METHOD.md](METHOD.md)**. In brief:

1. **The bit-identity gate.** A change is either provably output-identical or it is a
   change. Render a fixed input offline, `sha256` it, compare to a committed baseline.
   Every optimisation here passed it or was reverted.
2. **Void the rows.** When you find a confound, every measurement taken before the fix is
   void. Do not patch the numbers; re-sweep. Cheaper than one wrong decision.
3. **The confound checklist.** `tools/preflight.sh` — competing load, CPU governor,
   affinity and RT priority, NEON attributes in the deployed binary, denormals. Run it
   before every sweep, record the answers per row.
4. **Hash, don't timestamp.** The board has no RTC and reports 2025. File mtimes are
   meaningless. Every row records the `sha256` of the deployed binary, which is the only
   reliable statement of what produced a number.
5. **Figures are generated from the data, never hand-typed.** `tools/make_figures.py`
   reads the CSV, asserts the claims, and emits the SVGs. Doing this caught three errors
   that had already been published in slides.
6. **The average lies. Measure the worst block.** Sushi has no xrun counter; `max ≥ 1.0`
   is the proxy. Every headline failure in this project was invisible to average CPU.

---

## Reproduce it

Needs an Elk board, Elk's desktop devkit, and a plugin of your own to point it at.

```bash
tools/preflight.sh mind@<board-ip>            # confound checklist — all PASS/INFO
tools/sushi_board.sh start mind@<board-ip>    # SIGINT-only lifecycle
python3 tools/profile_sweep.py \
    --host board --addr <board-ip>:51051 --ssh mind@<board-ip> \
    --voices 0,1,2,3,4,5 --settle 10 --measure 60 --notes "sweep 1 of 3"
tools/sushi_board.sh stop mind@<board-ip>     # SIGINT only — SIGTERM wedges audio_evl
python3 tools/make_figures.py                 # figures, regenerated from the CSV
```

Full runbook and the reasoning behind each design choice: **[RUNBOOK.md](RUNBOOK.md)**.

The sweep parameter is ours (`num_voices`, a gate on the shifter voices). Point it at
whatever axis your own plugin scales along — the harness only cares that it is a
parameter it can set over gRPC and read back.

---

## What is here, and what is not

**Here:** the sweep harness, the confound preflight, the board lifecycle scripts, all 51
rows of data including the builds that failed, the figure generator, and the method.

**Not here, deliberately:** the harmony engine. THIRI's voicing logic, chord identifier,
pitch tracker and shifter voices are not open. That is not the reproducible part and it
is not what you need from us.

What you need from us is the part that is hard to get right and easy to get wrong: how to
measure a real-time DSP claim so that it survives contact with someone who disbelieves it.

---

*Numbers measured on Elk Audio OS 1.2.2, Sushi 1.3.0, STM32MP157 at 800 MHz with the
performance governor, 64-sample buffer at 48 kHz. Every figure in this repo regenerates
from `data/profiling-results.csv`.*
