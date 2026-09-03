---
name: audio-signal-proof
description: Verify claims about audio-processing code (pitch content, timing, whether output is derived from a specific input vs. synthesized) using objective signal-domain measurement — Goertzel single-frequency energy probes, envelope/tremolo-inheritance tests, chord-boundary timing detection — instead of trusting a listening impression or assuming tests that check "the right notes" also prove "the right signal path." Use whenever you need to verify an audio plugin's actual behavior without a human listening, whenever reviewing DSP code for correctness, or whenever a stated audio-processing behavior (harmonizer, EQ, timing-locked effect) needs objective proof rather than a description of what it should do.
---

# Proving audio-processing claims without listening

Hard-won 2026-08-21 on HORN SXTN — including a real case where signal-domain
testing caught that a "correct-sounding" harmonizer was secretly a synthesizer
(right notes, wrong signal path entirely) that pitch-content-only tests had
missed. See **rt-audio-phase-vocoder** for what was being tested here.

## The core principle

A test that checks "did the output land on the expected pitches" can pass for
**two completely different implementations**: one that derives those pitches
from the actual input signal (a real harmonizer/pitch-shifter), and one that
synthesizes them from scratch (an oscillator bank that happens to compute the
right target frequencies). Both produce correct-sounding-on-paper output.
Only signal-domain measurement distinguishes them — pick a test that can only
pass if the mechanism is the one you actually intend.

## Technique 1: Goertzel single-frequency energy probe

Cheaper than a full FFT when you only care about specific frequencies (e.g.,
"is this chord tone present, and how strong relative to others"). Pure
stdlib Python, no numpy needed:

```python
def goertzel(samples, sr, freq):
    w = 2*math.pi*freq/sr; coeff = 2*math.cos(w)
    s1 = s2 = 0.0
    for x in samples:
        s0 = x + coeff*s1 - s2; s2 = s1; s1 = s0
    return math.sqrt(s1*s1 + s2*s2 - coeff*s1*s2) / len(samples)
```

Use it to build a "which pitch classes are present" probe by summing energy
across octaves of each MIDI pitch class, then rank-order the results — the
strongest few should be exactly the chord tones your engine calculated, with
non-chord-tones near zero (a small amount of harmonic-overtone leakage from
the fundamental is normal and expected).

## Technique 2: prove output is DERIVED from input, not synthesized

Feed the system under test a **distinctive, artificial modulation** that no
plausible alternative implementation would spontaneously produce — e.g. a
steady tone with an unusual amplitude tremolo rate (3 Hz is a good choice:
close to natural vibrato but distinct enough to measure cleanly). Render the
output, then measure its amplitude-envelope modulation spectrum (rectify,
decimate to a low sample rate, Goertzel-probe candidate rates):

```python
env = [avg(abs(sig[i:i+dec])) for i in range(0, len(sig)-dec, dec)]
# then Goertzel-probe env at [1, 2, 2.5, 3, 3.5, 4, 5, 6, 8] Hz
```

If the exact input tremolo rate reappears as the dominant modulation in the
output, the output is **mechanically** derived from the input — there is no
other way that specific modulation gets there. If it's a synthesizer
underneath, the output holds a steady note with no 3 Hz modulation at all,
full stop. This is a binary, unambiguous test — much stronger evidence than
"it sounds plausible."

## Technique 3: chord/state-boundary timing detection

To prove a system's internal clock genuinely tracks a parameter (tempo, a
timer, a scheduled state change) rather than just replaying a fixed pattern,
render the same test at two different settings and measure **when** a
detectable state transition happens, then check it against the expected
formula:

```python
def boundary(path, pcA, pcB, sustain=4):
    """First time B's energy exceeds A's AND STAYS ahead for `sustain`
    consecutive windows — a real transition, not a single flickering frame
    caused by a transient."""
    ...
```

Requiring the flip to **sustain** across several consecutive analysis windows
(not just cross once) matters — a single-note attack transient or measurement
noise can cause one frame to flicker across the threshold; sustained dominance
is what distinguishes a real state change. Then assert the measured time
matches the expected formula (e.g. `60/tempo × beats_per_bar`) within a small
tolerance — this proves the clock is computed, not hardcoded.

## Technique 4: "did the synth play THE note" — pitch-class argmax per expected window

Added 2026-09-03 proving an arpeggiator's MIDI reached a synth with the *right* notes (64/64
windows). Given the expected `(onset, duration, midi)` list from the engine, for each event:

1. take the window `[onset + 30 ms, onset + dur − 20 ms]` (skip attack/release);
2. Goertzel-probe the 12 pitch classes at exact fundamentals across 3 octaves around the
   expected note, sum per pitch class;
3. the **argmax pitch class must equal the expected one** — no thresholds to tune, robust to
   level and timbre, and it still fails loudly for a semitone error.

Also assert the A/B (RMS with the source off must be ~0), that every window has energy at
all (the note *sounded* on time), and that the tail after the last note-off is silent (no
stuck notes). Three things that failed this test and were NOT wrong notes:

- attributing a window to a chord by its raw onset while the engine humanizes onsets (a
  downbeat jittered 5 ms into the previous chord) — attribute by the *nominal* step;
- the synth's `Pitch Bend` initialised to −100 % and a Poly-Legato glide (see
  **sushi-plugin-host-config**) — every note flat and sliding;
- comparing waveforms after a time shift: a synth's oscillator phases are **not
  time-shift-invariant**, so "the same form one bar later" must be checked with the pitch
  windows shifted, never by sample-wise subtraction.

When a window *does* fail, sweep the fine spectrum first (Goertzel every 4 Hz, list the top
peaks and their ratio to the expected f0); a consistent ratio of ~0.89–0.94 said "bend/glide",
not "wrong MIDI", in one look.

## Rendering for measurement: use offline, not real-time capture

Don't try to record real-time playback for these tests — use the DSP host's
offline/file-render frontend if one exists (see **elk-desktop-smoke-test** for
Sushi's `-o` flag and its wav_streamer gotcha) so the test is fast,
deterministic, and needs no audio hardware or human presence.

## Related skills

- **rt-audio-phase-vocoder** — a concrete system these techniques were built
  to verify.
- **golden-vector-port-verify** — the equivalent rigor for a system's
  *decision logic*, as opposed to its *audio output*.
- **elk-desktop-smoke-test** — the offline-render mechanics these techniques
  build on.
