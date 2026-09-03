---
name: golden-vector-port-verify
description: Port deterministic logic (theory engines, calculators, arpeggiators/sequencers, algorithms — integer OR floating-point) from one language to another that can't call the original directly — e.g. a JS/TS engine into C++ for a real-time audio thread that can't allocate, call an HTTP API, or link TypeScript — and PROVE the port is faithful by running both against thousands of identical inputs and diffing outputs bitwise, instead of trusting a careful manual translation. Covers what makes double-precision ports bit-exact (op order, -ffp-contract=off, JS rounding semantics, PRNG draw order as a contract), two-level vectors (primitives + full pipeline), negative controls, gzipped pins, and running the port with agents against the harness. Use whenever code needs to reproduce another codebase's logic across a language boundary, whenever "port," "reimplement," or "translate this engine to X" comes up, or whenever a plugin/embedded/sandboxed target can't literally import the source implementation.
---

# Golden-vector port verification

Hard-won 2026-08-21 porting THIRI's JS harmony engine (`scales.js` +
`harmony.js`) to allocation-free C++17 for a real-time audio plugin. The
general technique is not Elk- or audio-specific — reuse it any time you port
deterministic logic across a language boundary you can't bridge by importing.

## Why "I translated it carefully" is not verification

A hand-translated port that silently drifts from the original is **worse**
than no port — it looks correct, passes casual testing, and slowly diverges as
the canonical engine evolves without anyone noticing. The fix isn't more
careful translation; it's an automated contract that turns any future drift
into a **failing test**, not a silent fork.

## The technique

1. **Generate golden vectors from the REAL canonical implementation**, not from
   memory or docs. Write a small script in the source language that imports
   the actual engine and evaluates it over a large, systematic input grid
   (every relevant combination of key/mode/input-type/parameter — don't
   hand-pick a few examples, sweep the space). Emit results as flat TSV or
   JSON — something trivial to parse from the target language with zero
   dependencies.

   ```js
   // gen_golden.mjs — imports the REAL engine, not a copy
   import { getHarmonyNotes } from '<path-to-real-engine>/harmony.js';
   const rows = [];
   for (const key of KEYS) for (const mode of MODES) for (const lead of LEADS) {
     rows.push({ key, mode, lead, out: getHarmonyNotes(lead, key, mode, ...) });
   }
   // write TSV: one row per line, tab-separated, array outputs comma-joined
   ```

2. **Run the ported implementation over the identical inputs.** Parse the same
   TSV, call the port's equivalent function with the same arguments.

3. **Assert exact equality**, not "close enough." For deterministic
   integer/discrete logic (music theory, state machines, parsers), exact match
   is achievable and is the right bar — don't accept fuzzy tolerance for logic
   that has no floating-point reason to drift.

   ```cpp
   // golden_test.cpp — no test framework needed, just a diff-and-count loop
   int pass = 0, fail = 0;
   while (read_row(...)) {
     auto got = port_equivalent_fn(row.inputs...);
     if (got == row.expected) ++pass; else { ++fail; report(row, got); }
   }
   printf("GOLDEN: %d passed, %d failed\n", pass, fail);
   return fail == 0 ? 0 : 1;
   ```

4. **Regenerate on demand.** Ship a `--regen` flag/script that re-runs step 1
   against the current canonical engine and re-checks. If the canonical engine
   changes, this is how drift surfaces — as a red test, immediately, not as a
   bug report months later.

## Sizing the vector grid

Don't hand-pick a dozen examples — sweep systematically. For HORN SXTN this
meant every key × every mode × every voicing type × every direction × a spread
of lead notes × representative chord qualities, which produced ~16,000
vectors from a few hundred lines of generator code. More vectors cost nothing
at test time (a diff loop is fast) and catch edge cases hand-picked examples
never would.

## What this buys you beyond correctness

A port with a golden-vector suite is safe to hand off, safe to refactor
aggressively (any behavior change shows up immediately), and gives you a
concrete, quotable number ("16,353/16,353 match") instead of "I think this is
right" — a genuine trust signal for anyone reviewing the work.

## Floating-point ports CAN be bit-exact — if you control four things

Extended 2026-09-03 porting a TS arpeggiator engine (seeded PRNG, greedy voice-leading
solver, scheduler, humanize) to C++: **18,080/18,080 vectors bitwise, doubles included**.
The earlier "DSP math generally is not exact" caveat below is about *different algorithms*
(another FFT); a faithful port of the *same* arithmetic is exact when:

1. **Same width, same op order.** `double` wherever the source has `number`; keep every
   expression's association verbatim (`a + (b - a) * t`, `(base*accent)*tens + (...)`).
   Basic ops (+ − × ÷) are correctly rounded everywhere, so identical order ⇒ identical bits.
2. **No FMA, no fast-math.** clang on arm64 fuses `a*b+c` by default — compile every TU that
   includes the port with `-ffp-contract=off`, and never let it inherit a target's
   `-funsafe-math-optimizations` (isolate it in its own target if the audio plugin has them).
3. **Language rounding semantics, not libm's.** JS `Math.round` ties toward +∞ (`std::round`
   is away-from-zero): `f = floor(x); return x - f >= 0.5 ? f + 1 : f`. JS `%` on negatives
   keeps the dividend's sign like C++. `Math.max(0, -0)` is +0. `>>> 0` / `|0` / `Math.imul` =
   wrapping uint32 arithmetic. Write these helpers once and name them (`jsRound`, `jsSign`).
4. **The PRNG draw order is the contract.** Write the draw sites down as a table at the top of
   the port (site → how many draws, in execution order, including draws whose result is
   unused) and never add/remove/reorder one. Pin the generator itself with a primitive vector
   (first N draws for many seeds, incl. 0 and 2³²−1).

Transcendentals (`pow`, `exp`, `log`) are the one place libm may differ in the last ulp; pin
them with a tolerance *and* count exact matches separately — on this Mac `440·2^((m−69)/12)`
happened to be bit-exact with V8, and the harness said so instead of assuming.

## Two-level vectors: primitives + the full pipeline

Emit **primitive** vectors (each pure function over a grid) *and* **end-to-end** vectors
(the whole render over a sampled parameter product, thousands of them). Primitives localise a
mismatch to a module in seconds; end-to-end vectors catch draw-order and integration drift the
primitives can't. Sweep the product deterministically (an index-based selection, never
`Math.random`) so regeneration is byte-identical — verify that with a sha256 of the TSV.
Always run a **negative control** once: change one constant in a scratch copy of the port and
confirm the harness fails (ours: 339 fixtures) — a harness that cannot fail proves nothing.

## Repo hygiene for big vector files

A full-pipeline TSV can reach tens of MB (ours: 17.8 MB). Commit it **gzipped** (3.3 MB),
git-ignore the raw file, and have the run script inflate it when missing or older than the
`.gz`; `--regen` rewrites both. Build/run the harness at -O0, -O2 and -O3 and require the
three summaries to be identical.

## Working the port with agents (the harness is the judge)

Write a **hazard spec** first — every rounding/draw/op-order trap you found reading the
source, plus the exact fixture format and C++ API — then fan out: one agent writes the
generator + diff harness (it owns the format), another writes the port from the spec, a
third builds and iterates until green. The oracle makes the port mechanically checkable, so
agents can do it; the spec is what stops them "fixing" the source's semantics. The reviewer
you still owe afterwards is a human-style line-by-line read of the port against the source
for cases the grid may not reach (register edges, empty lists, n=1, unused draws).

## When NOT to reach for exact-match golden vectors

If the target has legitimate floating-point divergence from the source (e.g.
a different FFT library, different trig implementation), exact match is the
wrong bar — use a tolerance and say so explicitly. This technique is for
**deterministic, discrete** logic. Music theory (semitones, pitch classes,
scale degrees) is exactly that; DSP math generally is not.

## Related skills

- **juce-elk-plugin-cmake** — where the ported engine typically lands (a C++
  plugin that can't call the original JS/API at runtime).
- **rt-prerender-playback** — how a ported *generative* engine (a sequencer /
  arpeggiator) is then run off the audio thread and played on it.
- **audio-signal-proof** — the analogous "don't trust listening, measure it"
  discipline applied to the plugin's *audio output* rather than its logic.
