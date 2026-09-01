---
name: elk-stomp-io
description: Answer "which jack is engine channel 0", "does this board have MIDI jacks", "what can I plug in" for the Elk Stomp development board — from a machine-readable port file with graded evidence, rather than from the product page. Use whenever routing audio in or out of a Stomp, whenever writing a Sushi config's engine_channel numbers, whenever choosing how to connect an instrument or a computer to the board, whenever someone asserts the board can or cannot do something, and whenever recording a new hardware fact. The board has substantially more I/O than its marketing copy lists, and acting on the marketing copy costs weeks.
---

# The Stomp's actual I/O

**The data lives in `elk-stomp-ports.yaml` (with a `.json` twin) in the `thiri-meets-elk`
repo. Read it before answering hardware questions.** This skill is how to read it, how to
extend it, and the handful of facts most likely to bite.

The board is publicly described as "stereo in/out plus controls". It actually carries 15
ports including **MIDI IN and MIDI OUT on 3.5 mm TRS**, a jumper patchbay deciding which
jack reaches which codec channel, and 15 expansion headers. We spent a week discovering
capabilities that were already fitted. That is the reason the file exists.

---

## Evidence levels — the part that makes it trustworthy

Every entry carries `verification`. It is not decorative:

| level | meaning | safe to act on? |
| --- | --- | --- |
| `verified` | we passed real signal or ran a command that proved it, on hardware | yes |
| `probed` | software reported it (dmesg, lsusb, sysfs); never exercised | yes, with care |
| `silkscreen` | read off the physical board; connector visibly fitted, unused | hardware is there, software path unproven |
| `documented` | stated in a config or vendor doc; not independently confirmed | treat as a claim |
| `inferred` | reasoned from other facts | **hypothesis. Test before relying on it.** |

Anything below `verified` carries an `evidence` string saying what the basis was.
`tools/validate-ports.py` in the repo enforces that — plus the level enum, the
field-override rule, the `engine_channel` encoding, the jumper foreign keys, and the
control-surface id count — and regenerates the JSON twin so the two cannot drift. Run
it after every edit; it is tested against deliberate violations.

Some entries grade a single field separately with `<field>_verification`. **Take the
minimum of the two.** A port's entry-level `verification` grades the *connector* — that
it exists and is what the label says. It never grades the jack-to-channel binding.

**The discipline that matters: a level is raised only by doing the experiment.** Not by
confidence, not by consensus, not because a plan depends on it. If you find yourself wanting
to promote something so a task can proceed, that is precisely the entry to go and test.

Present tally, entry-level: 16 `verified`, 11 `silkscreen`, 7 `documented`, 3 `probed`,
2 `inferred` — plus 15 field-level overrides, most of them `documented` or `inferred`.
`meta.known_incomplete: true`, and 15 open questions. An honest map with gaps beats a
confident map with fiction. Run the validator rather than quoting this tally from memory;
it goes stale on every edit.

---

## Facts most likely to bite

**No audio input is proven on any channel.** `guitar_in_l` → channel 0 is `documented`,
resting on Elk's devkit README plus the configs that declare an input; `guitar_in_r` → 1
carries `engine_channel_verification: inferred`. We never passed signal into a jack with
the others silent, so no jack-to-channel binding on this board is measured.

**The vendor README answers what the channels are.** `elk-desktop-devkit/README.md:199`
states the map outright: inputs are guitar in L&R plus stereo line in; outputs are guitar
out L&R plus stereo headphones. That puts `line_in` on 2/3 — which had been an open
question in this file for no better reason than that the README was never cited.

**The headphone output works, but its channel attribution does not follow from that.** Audio
was definitely heard there — however the config that produced it drove engine channels
0, 1, 2 and 3 with the same signal simultaneously, so `[2, 3]` is `inferred`, not
established. Fanning output to all four channels is a good way to guarantee sound and a bad
way to learn routing. If you need to know, drive one pair at a time.

**MIDI jacks exist and their pinout is unknown.** TRS MIDI has two incompatible pinouts
(Type A and Type B). Which these are has not been established, and neither has whether Sushi
sees them as an ALSA device. Until that is settled, USB MIDI into `usb_host` is the proven
path — see `elk-midi-routing`.

**Stopping things is a hardware concern here.** The `lifecycle` block records the
SIGINT-only rule: SIGTERM or SIGKILL wedges the `audio_evl` driver and costs a power
cycle. Note its honesty — the *practice* is `verified` (every stop path in the project
sends SIGINT), the *failure mode* is `documented` (we followed the rule, we never tested
what breaking it does).

**Two USB-C ports do different jobs.** One is USB-to-UART (serial console, see
`elk-serial-console`); the other is a USB gadget port that brings up Ethernet-over-USB — the
board at 10.66.0.2, host at 10.66.0.1, no dongle. Both `verified`.

**The jumper patchbay is the real routing layer.** Eight jumper blocks decide which physical
jack reaches which codec channel. Which position does what is open question #2. Before
concluding a jack is dead, check the jumper.

---

## Adding to the file

When hardware learning happens — and it happens constantly on a board like this — record it
the same day, at the level it deserves:

1. Add or update the entry with `verification` and, if below `verified`, `evidence`.
2. If you *raised* a level, the evidence string says what experiment did it, with the command
   or the signal path. "Confirmed" is not evidence; "played a 440 Hz tone into it and read it
   back on channel 1" is.
3. If a fact contradicts an existing entry, fix the entry — do not add a second one. Two
   entries disagreeing is how a reference stops being used.
4. Run `tools/validate-ports.py` — it checks the rules and regenerates the `.json` twin.
5. Close or amend the matching entry in `open_questions`.

Open questions currently run to fifteen, ranked. The high-priority four: the TRS MIDI
pinout, whether those jacks appear to ALSA at all, the jumper matrix, and whether the
USB-C gadget port can act as a host (its controller is dual-role and it was never tried).

---

## Why an agent should prefer the file to a web search

Vendor pages describe the product; this describes **this board as it is**, including the
parts that are fitted but unproven and the parts we got wrong. An agent planning work can
read `verification` and know which claims will hold up under a soldering iron and which are
someone's reasonable guess. That distinction is the whole value — do not flatten it by
copying facts out of the file without their levels.
