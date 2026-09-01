---
name: rt-budget-proof
description: Prove whether a DSP change fits inside a real-time audio deadline, with numbers that survive someone disbelieving them — worst-block measurement, the confound checklist, the bit-identity gate, and hash-based provenance. Use this whenever you are about to claim code is "fast enough", whenever a plugin might xrun, whenever optimising audio DSP, whenever a CPU meter looks healthy but the audio drops out, whenever choosing between two algorithms on cost grounds, or whenever writing performance results up for anyone outside the room. Reach for it early — retrofitting rigour onto numbers you already published is how you find out three of them were wrong.
---

# Proving a real-time DSP claim

Real-time audio does not fail on average. It fails on one block, once, audibly. Every
discipline here follows from that one sentence.

The worked example throughout is a harmony plugin on an Elk Stomp: 64 samples at 48 kHz,
a **1.333 ms** deadline, dual Cortex-A7. None of the method is specific to that board.

---

## 1. Measure the worst block, not the average

Ask for `max`, budget against `max`, report `max`. The average is a comfort number.

Three failures from the source project, all invisible to average CPU:

| what happened | avg | worst block |
| --- | --- | --- |
| O(n²) analysis firing once per hop, landing in one block | 0.796 | **5.94** |
| Control surface left unpinned, sharing the audio core | ~0.60 | **2.27** |
| Same rig, control surface pinned off the audio core | ~0.60 | 0.76 |

In the second row a CPU meter showed a healthy 60% the whole time the audio was breaking.

The corollary reshapes optimisation work: the useful question is often not *"how do I make
this cheaper"* but *"how do I make this flatter."* Spreading that O(n²) analysis across the
hop's eight blocks changed no arithmetic — identical results, identical total work — and
took the worst block from **5.94 to 0.688**. That is what made the plugin shippable.

## 2. Know what your host's numbers mean

Sushi's `--timing-statistics` reports `{average, min, max}` as a **fraction of the block
period**, not milliseconds. `1.0` is the deadline exactly. elkpy's docstring says
milliseconds and is wrong — trust the arithmetic, not the docstring.

**Sushi has no xrun counter.** `max >= 1.0` *is* your xrun signal and nothing will tell you
to look. Assert on it in the harness or you will not notice.

Check the equivalent for any host before trusting a number: units, and whether it counts
dropouts at all.

## 3. Run the confound checklist before every sweep — and record it per row

A row that cannot prove its own conditions is not evidence.

| check | why it invalidates the measurement |
| --- | --- |
| competing load | anything else on the box steals cycles from the audio core |
| CPU governor / frequency | `ondemand` measures a moving target — pin it, record which |
| thread affinity | the audio thread owns a core; anything else there is interference |
| RT priority | a non-RT-scheduled host produces scheduler noise, not worst-case cost |
| SIMD in the *deployed* binary | verify the shipped `.so` contains the instructions you think you compiled |
| denormals | flush-to-zero changes cost by orders of magnitude in decaying tails |

Record affinity and priority in **every row**, not once at the top of the session. They
change under you.

**Desktop rows are plumbing checks only.** On a non-RT desktop frontend we logged a 44×
period spike that meant nothing at all. Only the trend in `avg` is meaningful there; worst
case is only real on the RT target.

## 4. When you find a confound, void the rows

Not adjust. Not annotate. Void, and re-sweep. A sweep costs minutes; a wrong architectural
decision costs weeks, and the failure mode is quiet — the old rows stay "for reference",
end up in a table, and later nobody remembers which were taken before the governor was
pinned.

Tractable version of the rule: **if fixing the confound moves the ceiling at all, earlier
rows are void.** If it demonstrably does not, say so in the notes column and keep them.

**Keep the failures in the dataset.** Ours contains every run including two builds that
never shipped. Those rows are why three regimes are visible instead of one number, and why
an algorithm could be abandoned on evidence rather than on taste.

## 5. Gate every optimisation on bit-identity

Every optimisation carries two claims: *faster*, and *the output is unchanged*. The second
is the one people skip and the only one that is cheaply checkable.

```
render fixed input offline -> sha256 -> compare to committed baseline -> pass or revert
```

- **Commit the baseline audio, not just the hash.** The hash says it broke; the WAV says
  how. Report first differing sample index and max absolute delta — `sample 88200, delta
  3e-7` is float reordering, `sample 0, delta 0.4` is a logic bug, and they need different
  responses.
- **Record provenance beside the baseline** — compiler, framework, SDK version. Otherwise a
  toolchain bump reads as a regression and costs you a day.
- **Make new parameters byte-identical no-ops at their defaults.** Append last, default to
  skipping the code path, prove it against the baseline. A profiling knob that changes the
  audio is not a profiling knob.

## 6. Hash the binary; do not trust timestamps

Embedded boards often have no RTC — this one reports 2025 and every mtime on it is fiction.
Record the **`sha256` of the deployed binary** in every row. It is the only statement of
what produced a number that survives a clock reset, a redeploy, or two people building from
slightly different trees. It costs one column and it is the single highest-value habit here.

## 7. Generate figures from the data — never hand-type a number

The figure script should read the dataset, **assert the claims it is about to draw**, and
emit the images. If the data stops supporting the headline, the build fails instead of the
chart quietly lying.

Doing this caught three errors already published in slides: two worst-case values wrong in
the third decimal, and one ratio computed over mismatched spans (0→4 against 0→5, inflating
52× to 65×). Every one was a careful person transcribing carefully — which is exactly why
the transcription step has to be deleted rather than double-checked.

---

## Reading a finished sweep

Three regimes from one dataset, same plugin, same board:

| build | avg @ 5 voices | worst block | verdict |
| --- | --- | --- | --- |
| phase vocoder, unsliced analysis | 2.08 | 5.99 | analysis spike, ~6× over |
| phase vocoder, sliced analysis | 1.83 | 2.79 | **over real time at ONE voice** (1.07 avg) |
| PSOLA, sliced analysis | **0.592** | **0.788** | ships |

Two conclusions worth stealing:

**No buffer size fixes an average.** Doubling the buffer doubles both the deadline and the
work; the fraction does not move. A build over 1.0 on average was never going to ship, and
the data said so before anyone tuned it.

**Compare marginal cost, not totals.** Per added voice: 0.005 of the block period against
0.254 — a 52× difference that totals obscure. Measure both algorithms over the *same* span
or the ratio is meaningless.

## What this does not cover

Whether it sounds good. Everything here measures whether the DSP *fits*. A 52× cost
advantage says nothing about which algorithm sounds better — it says one of them can exist
on this hardware. The discipline for the other question is a listening test with people.
