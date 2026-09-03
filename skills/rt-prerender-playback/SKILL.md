---
name: rt-prerender-playback
description: Run a generative music engine (arpeggiator, sequencer, pattern generator — anything with a solver, a PRNG, or more than a few microseconds of work) inside a real-time audio plugin by rendering a whole loop OFF the audio thread and playing the rendered event list ON it — the render-thread/arm-commit/player split, the beat-domain time model, sample-accurate loop wrap and count-in, stuck-note-proof MIDI emission, and the JUCE-free tests that prove it. Use whenever a plugin must "play" something computed rather than react per sample, whenever a solver or allocation would otherwise land on the audio thread, or whenever a sequencer-like feature needs Play/Stop, loop-top edits, tempo changes and a metronome without dropouts.
---

# Pre-render off the audio thread, play on it

Hard-won 2026-09-03 putting the THIRI Helix arpeggiator into a headless VST3 on the Elk
Stomp (64-sample blocks, 1.33 ms deadline). The engine (voice-leading solver + scheduler +
seeded humanize) is pure and deterministic: same inputs ⇒ same events. That one property
turns a "run a solver in processBlock" problem into a "copy a list at the loop top" problem.

## The split

| thread | does | never |
|---|---|---|
| **render** (`juce::Thread`, low priority, polls params every ~10 ms) | snapshot the inputs the render depends on into a POD struct; if it differs from the last rendered one → render the whole loop into a bounded list → `arm()` | touch audio-thread state |
| **audio** | at each **loop top** `tryCommit()` (try-flag + one bounded copy — never blocks; if the writer is mid-copy, try at the next loop top); every block walk the live list by beat position and emit note events | run the engine, allocate, lock, wait |

Why poll instead of signal: `pthread_cond_signal` from the audio thread is not RT-safe, and a
10 ms poll is invisible next to a loop-top commit. Why not re-render per loop like a web app
does: the render is deterministic, so only an input change needs one. Why a copy instead of
double-buffering: it mirrors the codebase's existing lock-free handoff (a spin flag the audio
side only *try*-acquires), it is a few µs for a 24 KB list, and the lifetime rules stay
trivial. Keep the copied struct compact (12-byte events: float beat, float duration, voice,
note, velocity) — the golden-verified render (doubles) decides *which* notes; the playback
copy only decides *when*, where a few microseconds of float error are irrelevant.

Under Sushi the JUCE message thread may not pump, and no message thread is needed here —
the render thread is the processor's own. Pin it off the audio core on the board
(`setAffinityMask`); an unpinned control thread on the audio core measured 2.3× the
deadline in an earlier project.

## Time model: beats, loop-relative

Store onsets and durations in **beats**, derived from the same sample counter the plugin's
chart clock uses, so the played pattern and the chart position can never disagree. A live
tempo change then rescales playback instead of desyncing it (and triggers a re-render that
lands at the next loop top). The player keeps its own monotonic beat counter for note-offs,
so a note that ends after the loop wraps releases on time in the next lap.

Per block: `pos` = loop position at the block's first sample (compute it from the counter
*before* this block's advance — many clocks add the block first and derive the bar from the
end), `nBeats` = the block's length. Collect the note-ons whose beat falls in `[pos, pos+n)`
(two ranges when the loop wraps inside the block) and the note-offs due before `t + n`,
sort by sample offset with **offs before ons at the same sample**, and apply them in order
through a set-diff emitter.

## Emission: reuse the set-diff, per-note velocity

Hand the emitter the *set of notes that should be sounding* after each boundary and let it
diff (note-off the departed, note-on the arrived, leave common tones alone). This gives you
for free: a diatonic 3rd landing on another voice's note sounds once and holds until the
last overlapping event ends; an exactly touching repeat re-strikes as off-then-on at the same
sample; stop/bypass/panic are one `allOff`. Add a per-note-velocity overload to the emitter
rather than a second emitter. Bound the active set (32) and *count* drops — never overflow.

## Transport

- `running = !gate || (run && hostPlaying)`. Hosts differ in what they forward (Sushi:
  playing state yes, tempo no — see **sushi-plugin-host-config**), so keep a plugin-side
  `run` parameter as belt and braces and let the control surface mirror both.
- **Stop** holds the clock and releases everything. **Start** restarts the form at bar 0 on
  the one — hold semantics would put the pattern and the chart at different places. Treat the
  first block after `prepareToPlay` as a start so a count-in also works from boot; at the
  defaults this re-zeroes counters that are already zero, so the render stays byte-identical.
- **Count-in** = one bar of clicks with the clock held; the block in which it ends gets a
  `sampleBase` (samples before the beat window starts) so the downbeat is sample-accurate,
  not block-quantised. The clock advance for that block is `n − remaining`.
- A **chart change** with a different loop length is adopted at the loop top and re-anchors
  the clock so the new form's bar 0 is that loop top, for the pattern and the chart alike.

## What to test, JUCE-free

Three sub-second tests caught every real bug (the fourth "bug" was a test rounding a float):

1. **Player ledger** — feed 64-sample blocks over a synthetic list; a downstream-synth model
   counts note-on/off per note, flags double-ons, orphan offs, out-of-order sample positions;
   assert one on + one off per event per lap, onsets within ±1 sample of the rendered beat,
   offs at onset + duration, wrap across the loop end, overlap folding, gate scaling, stop
   mid-note, list swap at the loop top while a note sounds, capacity overflow.
2. **Chord source** — chart → the engine's input struct: pitch classes, scale, bar/chord
   splitting, hold bars, free mode, capacity.
3. **End to end** — chart → render → arm/commit → player over several laps; plus a
   concurrent arm/commit stress (writer thread spinning `arm()` while the audio side
   `tryCommit`s — the list must stay intact) and the worst case (longest form × finest
   subdivision × widest harmony must fit the list exactly).

Then the host-level proofs (**audio-signal-proof**): offline render through a synth, every
expected note window at the expected pitch class, A/B silence, silent tail; and the
transport variants (`run=0` silent, count-in shifts the form by exactly one bar, clicks on
the count-in beats). The click has to live on its own track: a synth after the plugin
replaces the audio it adds.

## Related skills

- **golden-vector-port-verify** — proving the engine you are about to play is the engine.
- **audio-signal-proof** — measuring that the played notes reached the synth.
- **sushi-plugin-host-config** — what the host forwards (playing state) and what it never
  does (tempo), and the synth initial-state traps.
- **rt-budget-proof** — the worst-block measurement this design is meant to keep flat.
