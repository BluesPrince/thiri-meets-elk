---
name: midi-controller-profile
description: Find out what a MIDI controller actually transmits — message types, numbers, ranges and resting values — before designing anything around its manual. Use whenever mapping a wind controller, keyboard, expression pedal or breath controller to plugin parameters, whenever an expressive gesture "does nothing" downstream, whenever a manual lists a capability you cannot find in the data, before committing to a control layout, and whenever a mapped parameter sits at the wrong value when nobody is touching the instrument. Manuals describe what an instrument can be configured to do; only a capture tells you what this unit is doing right now.
---

# Profiling what a controller really sends

A manual is a description of the instrument's **capabilities**. What you need is its
**current behaviour**: this unit, this patch, this menu state. The gap between those two is
where control-mapping projects lose their days.

The gap is rarely subtle once measured. On a digital wind controller we designed around
bite and thumb as expression sources for a week before capturing the stream and finding they
ship on **pitch bend**, not CC — and pitch bend cannot be reached by a host's CC mapping at
all. The fix was a menu change on the instrument, not code. Nothing downstream could have
revealed it.

---

## Procedure

**1. Find it.**

```bash
aconnect -l          # ALSA sequencer clients; note the client:port of the instrument
amidi -l             # raw MIDI devices, hw:X,Y,Z
```

**2. Capture with nothing being touched.** Ten seconds of silence first. Anything that
appears is idle traffic — active sensing, clock, a control that self-transmits. You need to
know what the noise floor is before you can read the signal.

```bash
amidi -d -p hw:0,0,0
```

`aseqdump -p <client>:0` is far more readable if present, since it decodes message types
rather than printing hex.

**3. Move one control at a time, through its full travel, slowly.** Name it out loud in your
notes before you move it. The whole method depends on knowing which gesture produced which
bytes, and two controls moved together are unattributable forever.

For each, record: **message type**, **number**, **channel**, **observed minimum and
maximum**, and **resting value**.

**4. Push each control to its physical extremes** and check the data actually reaches 0 and
127. Many do not. A control with an effective range of 20–100 mapped naively to a parameter
means the parameter can never reach either end, and this presents as "the mapping feels
wrong" rather than as a number problem.

---

## What to look for

**Message type first, number second.** CC, pitch bend, channel aftertouch and poly
aftertouch are four different transports. Only CC is reachable by a typical host CC mapping.
If the expressive gesture you care about is on pitch bend or aftertouch, either reassign it
on the instrument or handle it in the plugin — no amount of config will find it.

**Resting values are a design input, not a detail.** A breath sensor rests at 0. A bite or
lever on pitch bend rests at **centre**. Map a centred control to a 0→1 parameter and the
parameter sits at 50% when nobody is playing — the delay is half-fed back and the chorus is
half-on before a note is played. Decide deliberately: bipolar controls want a parameter
whose midpoint is meaningful, or a remap.

**Channel matters if you use it.** Controllers often transmit on channel 1 but can be split
across channels per zone. `"channel": "all"` in a host mapping sidesteps this — until two
zones send the same CC and fight.

**Ask whether the controller is also making the sound.** Instruments without a Local Off
always play their own internal engine. If you are processing that audio downstream, the
patch selected on the instrument *is* the timbre of everything you build — the
highest-leverage, zero-cost variable in the rig, and one that will never appear in your
code.

---

## Two traps specific to running this on a board

**Capturing severs the host's MIDI link.** Running `amidi` on the raw device starves the
ALSA sequencer path and drops any connection the host had. After every capture session,
re-link — see `elk-midi-routing`. Symptom if you forget: everything worked, you profiled the
controller, and now nothing works and no config changed.

**Do not run a capture while the host is reading the same device.** They fight, and the
result is that both look broken. Stop the host first.

---

## The artifact

Commit a small table next to the rig config. It is the thing you will actually reread, and
it prevents the whole exercise being redone when someone changes a menu.

| control | type | number | ch | range seen | rest | mapped to |
| --- | --- | --- | --- | --- | --- | --- |
| breath | CC | 2 | all | 0–127 | 0 | wet/dry |
| lever, right | CC | 5 | all | 0–127 | 0 | delay feedback (capped 0.85) |
| bite | CC | 1 | all | 0–127 | 0 | chorus amount (capped 0.8) |

Record the **instrument menu settings** that produce this table alongside it. A profile
without its menu state is not reproducible — the next person to pick up the controller will
find different behaviour and no way to tell whether the table is stale or the instrument
moved.
