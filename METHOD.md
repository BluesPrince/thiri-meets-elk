# METHOD.md — how to measure a real-time DSP claim so it survives disbelief

Six disciplines. None is clever. Together they are the difference between a number you
can put in a decision and a number that merely sounds encouraging.

The context they came from: deciding whether a harmony engine plus five pitch-shift
voices fits a 64-sample buffer at 48 kHz — a **1.333 ms** deadline — on a dual-core
Cortex-A7. But nothing below is specific to that plugin or that board.

---

## 1. The bit-identity gate

**A change is either provably output-identical, or it is a change.**

Every optimisation carries a claim: *this is faster and the output is the same*. The
second half is the one people skip, and it is the half that is checkable.

Render a fixed input through the plugin offline, `sha256` the result, compare against a
committed baseline. If the hash moves, the optimisation altered the output and you now
have two things to evaluate instead of one.

```
render fixed input -> sha256 -> compare to baseline -> pass or revert
```

Practicalities that make it work rather than annoy:

- **Commit the baseline audio, not only the hash.** A hash tells you *that* it broke; the
  WAV tells you *how*. On failure, report the first differing sample index and the maximum
  absolute delta. `sample 88200, delta 3e-7` is float reordering. `sample 0, delta 0.4` is
  a logic bug. They need different responses.
- **Record provenance beside the baseline** — compiler version, framework version, SDK
  build. Otherwise a toolchain bump reads as a regression and you will spend a day on it.
- **Make new parameters byte-identical no-ops at their defaults.** Append them last, give
  them a default that skips the code path entirely, and prove it against the baseline. A
  profiling knob that changes the audio is not a profiling knob.

Every optimisation in the source project passed this gate or was reverted. The gate found
nothing dramatic — which is the point. It made "the output is unchanged" a fact rather
than a belief.

---

## 2. Void the rows

**When you find a confound, every measurement taken before the fix is void.**

Not adjusted. Not annotated. Void. Re-sweep.

This feels wasteful and is not. A sweep here costs seven minutes. A wrong architectural
decision costs weeks, and the failure mode is subtle: you keep the old rows "for
reference", they end up in a table, and six months later nobody remembers which rows were
taken before the governor was pinned.

The rule that makes it tractable: **if fixing a confound moves the ceiling at all, the
earlier rows are void.** If it demonstrably does not, say so explicitly in the notes
column and keep them.

Corollary — **keep the failures in the dataset.** The source CSV contains every run,
including two entire builds that never shipped. Those rows are what let you see three
regimes instead of one number, and they are why the phase-vocoder build could be
abandoned on evidence rather than on taste.

---

## 3. The confound checklist

Run before every sweep. Record the answers *per row*, not once at the top of the session.

| Check | Why it invalidates a measurement |
| --- | --- |
| **Competing load** | Anything else on the box steals cycles from the audio core. |
| **CPU governor / frequency** | An `ondemand` governor measures a moving target. Pin it and record which. |
| **Thread affinity** | The audio thread has a core; anything else on that core is measuring interference, not your DSP. |
| **RT priority** | Non-RT-scheduled hosts produce scheduler noise, not worst-case cost. |
| **SIMD attributes in the deployed binary** | Verify the shipped `.so` actually contains the vector instructions you think you compiled. |
| **Denormals** | Flush-to-zero on or off changes cost by orders of magnitude in decaying tails. |

Two hard-won notes:

- **Record affinity and priority in every row**, not just in preflight. They can change
  under you, and a row that cannot prove its own conditions is not evidence.
- **Desktop rows are plumbing checks only.** On a non-RT-scheduled desktop frontend, worst
  case is scheduler noise — we recorded 44× period spikes that meant nothing. Only the
  trend in `avg` is meaningful there. Worst case is only real on the RT target.

---

## 4. Hash, don't timestamp

**File modification times are not provenance.**

The board in this project has no RTC. It reports 2025. Every mtime on it is fiction, and
this is common on embedded targets.

So every row of the dataset records the **`sha256` of the deployed binary**. That is the
only statement of what actually produced a number that survives a clock reset, a redeploy,
or two people building from slightly different trees.

It paid for itself immediately: months later, `sha256sum` on the board matched the hash in
the CSV exactly, which is how we know the numbers still describe what is running.

If you take one thing from this document, take this one. It costs a single column.

---

## 5. Generate figures from the data

**Never hand-type a number into a chart.**

`tools/make_figures.py` reads the CSV, *asserts the claims it is about to draw*, and emits
the SVGs. If the data stops supporting the headline, the build fails rather than the chart
quietly lying.

Doing this caught **three errors that had already been published** in slides — two worst-case
values off in the third decimal, and one comparison computed over mismatched spans (one
engine measured 0→4 while the other was measured 0→5, inflating a ratio from 52× to 65×).

Every one of those was a careful person transcribing carefully. That is exactly why the
transcription step has to be deleted rather than double-checked.

---

## 6. The average lies

**Measure the worst block. It is the only number the deadline cares about.**

Real-time audio does not fail on average. It fails on one block, once, audibly.

Every significant failure in this project was invisible to average CPU:

- A build averaging **0.67** of the deadline had one block in eight running **5.94×** over
  it, because an O(n²) analysis fired once per hop and landed in a single block. Average
  said 67%. The audio was broken.
- Adding an unpinned control surface moved the worst block **0.77 → 2.27** while the
  average stayed at ~0.60. A CPU meter showed a healthy 60% throughout.

If your host has no xrun counter — Sushi does not — then `max ≥ 1.0` **is** your xrun
signal, and you must go looking for it. Nothing will tell you.

The corollary shapes optimisation work: **the useful question is often not "how do I make
this cheaper" but "how do I make this flatter."** Tau-slicing an O(n²) analysis across the
hop's blocks changed no arithmetic at all — identical results, identical total work — and
dropped the worst block by 8×. That is what made the plugin shippable.

---

## What this does not cover

Audio quality. Everything above measures whether the DSP *fits*, not whether it *sounds
good*. Those are independent, and the discipline for the second one is a listening test
with people, not a CSV.

Worth saying plainly because it is an easy conflation: a 52× cost advantage says nothing
about which algorithm sounds better. It says one of them can exist on this hardware.
