---
name: audio-gain-staging
description: Diagnose "it sounds distorted / too loud / too quiet / wrong" in an audio chain by measuring the level at every stage instead of reasoning about the DSP — offline capture, peak/RMS/crest factor, and bisecting the chain to find the stage that is actually hot. Use whenever audio sounds wrong but the code looks right, whenever you are tempted to blame a pitch shifter or a saturator for distortion, whenever adding voices or plugins changes perceived loudness, before turning any volume down as a "fix", and whenever setting up a new signal chain on a headless box with no meters. Level bugs impersonate algorithm bugs extremely well.
---

# Finding the stage that is actually too hot

Distortion is a symptom with a large hypothesis space and one cheap discriminator: **the
level going into each stage.** Measure that first. Almost every "the shifter sounds bad"
report is a gain-structure report wearing a costume.

The rule that saves the most time: **a mental model of the level is not a measurement of
the level.** Assume nothing about what the bus is actually carrying, including — especially
— numbers you derived from the config.

---

## Why this fools people

Nonlinear output stages do not announce themselves. A gentle soft-saturator has no clip
light and no obvious onset; it just gradually stops sounding like the input. A real one:

```cpp
float mix = (dry[s] * (1.0f - wetDry) + wet[s] * wetDry) * master;
out[s] = std::tanh(mix * 1.3f) * 0.85f;      // "gentle saturation, no hard clip"
```

Slope at zero is `1.3 * 0.85 = 1.105` — so it is **+0.87 dB at low level** and progressively
compressive above that. Feed it 5× what it expects and it is a fuzz box. Feed it what it
expects and it is transparent. Nothing in the code changes between those two cases, which
is exactly why reading the code will not find the bug.

Turning the master down "fixes" the symptom while leaving the chain wrong, and hides the
next problem too. Find the level first.

---

## Capture, on a box with no meters

On a headless target, insert a file writer at the point you want to inspect and render a
fixed input through it. In Sushi that is `sushi.testing.wav_writer` as the last plugin on
the track.

Prefer a **capture** over a **meter**. A peak-meter plugin gives one scalar you then have to
trust, cannot be re-analysed, and in practice would not calibrate for us at all. A WAV can
be re-measured any number of ways after the fact and keeps its evidence.

Then measure:

```python
import soundfile as sf, numpy as np
x, sr = sf.read(path)
x = x if x.ndim == 1 else x[:, 0]
peak = np.max(np.abs(x))
rms  = np.sqrt(np.mean(x**2))
print(f"peak {peak:.3f}  rms {rms:.4f}  crest {peak/rms:.2f}  dBFS {20*np.log10(peak):.1f}")
```

**Crest factor is the diagnostic**, more than peak alone. A signal that got squashed by a
saturator has a *lower* crest factor than its input at the same peak. If crest drops across
a stage, that stage is compressing — whether or not it was supposed to.

---

## Bisect the chain

One variable per capture. Build one-shot configs; do not try to reason your way to the
answer from a single recording.

1. **Dry only.** Source into the writer, everything else bypassed. This is the number you
   are least entitled to assume and the one most often wrong.
2. **Unity.** Your plugin loaded, but every processing stage neutral (wet/dry fully dry,
   master at 1.0). Output should match step 1. If it does not, you have found a fixed gain
   you did not know about.
3. **One element.** One voice, one effect — whichever thing is accused. Compare to step 1.
4. **Full chain.** Only now.

The point of steps 1 and 2 is to make the accused element's contribution a *difference*
rather than an absolute you have to interpret.

---

## Two ways we got this wrong, in opposite directions

Both are worth knowing because they are the two available errors.

**Claiming the chain was fine.** Computed "0.4% compression, inaudible" — from a premise
that the dry bus sat at 0.36. It was actually at **5.40**, about 15× hot. The arithmetic
was correct and the input to it was invented. *A calculation inherits the confidence of its
weakest assumption, and assumptions do not feel weak from the inside.*

**Claiming a stage had enormous gain.** Then concluded the pitch-shift path had ~19× gain.
A direct A/B — one voice against dry, same input, same everything else — showed one voice at
**0.76× dry**. The stage was attenuating.

The measurement that settled it was the simplest one available and could have been taken
first. Take it first.

---

## Where to fix it

Fix at the **earliest** stage that is wrong, not the last one you can reach. Trimming the
input gain restores every downstream stage to the levels it was designed for. Pulling the
master down leaves the saturator still being overdriven and every internal stage still hot —
you have changed the volume, not the gain structure.

If the source is an instrument with its own output level (a synth, a digital wind
controller, a modeller), its output setting is part of your gain structure. Record what it
was set to alongside the capture, or the measurement is not reproducible.

---

## Checklist

- [ ] Captured the dry bus and know its peak/RMS — measured, not derived
- [ ] Compared crest factor across the suspect stage, not just peak
- [ ] A/B'd the accused element against dry with one variable changed
- [ ] Checked the output stage for a fixed multiplier or a soft nonlinearity
- [ ] Recorded the source instrument's own output level with the numbers
- [ ] Fixed at the earliest hot stage, then re-captured to confirm
