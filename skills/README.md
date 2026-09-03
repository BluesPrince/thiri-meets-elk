# Skills

Ten agent skills for building audio software on Elk Audio OS. They encode what this
project cost us to learn, in the form a coding agent can act on.

A skill is a folder with a `SKILL.md` — instructions an AI coding assistant loads when the
work matches. They are plain Markdown, so they are also just readable documentation if you
do not use an agent. Nothing here needs THIRI, our plugin, or our hardware beyond a Stomp.

## The set

| skill | answers |
| --- | --- |
| **rt-budget-proof** | Does this DSP fit the deadline, and will the number survive scrutiny? |
| **audio-gain-staging** | It sounds wrong — which stage is actually too hot? |
| **elk-midi-routing** | Why doesn't the board respond to my controller's CCs? |
| **elk-stomp-io** | Which jack is engine channel 0, and what else is on this board? |
| **elk-serial-console** | The network is down and I need to work on the board anyway. |
| **midi-controller-profile** | What is this instrument *actually* transmitting? |
| **golden-vector-port-verify** | I ported an engine to C++ — how do I *prove* it is the same engine, bit for bit? |
| **audio-signal-proof** | Did the plugin really play those notes? Measure the audio; don't listen. |
| **sushi-plugin-host-config** | Sushi's config, gRPC control, what a plugin can see of the transport, and the initial-state traps. |
| **rt-prerender-playback** | A sequencer/arpeggiator in a real-time plugin without the solver on the audio thread. |

The four added 2026-09-03 came out of putting an arpeggiator on the pedal: an engine
ported and pinned to its TypeScript original at 18,080/18,080 vectors, played off a render
thread, and proved through a synth with per-note pitch probes — plus the day's host facts
(Sushi tells a plugin it stopped, never what tempo it is at).

Three of the original six exist because of a failure mode that produces **no log line at all**: a MIDI
mapping that is deaf because nothing linked the ALSA sequencer, a control surface eating the
audio deadline while the CPU meter reads a healthy 60%, and a saturator being overdriven by
a bus that was 15× hotter than anyone believed. Those are the expensive kind, and they are
what an agent most needs told.

## Install

```bash
git clone https://github.com/<owner>/thiri-meets-elk
cp -R thiri-meets-elk/skills/* ~/.claude/skills/
```

Or copy individual folders — they are independent, and cross-reference each other by name
without requiring each other.

## What is deliberately not here

The harmony engine. THIRI's voicing logic, chord identifier, pitch tracker and shifter
voices are not open, and are not the reproducible part.

What is here is the part that is hard to get right and easy to get wrong: how to measure a
real-time claim, how to find the stage that is lying to you, and what this board actually
is as opposed to what its datasheet says.

The boundary is enforced rather than promised — `tools/sync-skills.sh` refuses to copy a
skill that names anything on the internal list, and it is tested against deliberate
violations so it cannot rot into a rule nobody checks.

## Provenance

Every number in these skills comes from `data/profiling-results.csv` in this repo, measured
on Elk Audio OS 1.2.2 / Sushi 1.3.0, STM32MP157 at 800 MHz, 64-sample buffer at 48 kHz.
Where something is unverified, the skill says so — see the evidence levels in
`elk-stomp-ports.yaml`, which the `elk-stomp-io` skill is a reader's guide to.

Corrections welcome. If a skill tells you something that is not true of your board, that is
a bug in the skill and we want the issue.
