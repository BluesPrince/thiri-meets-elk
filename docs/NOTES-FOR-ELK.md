# Notes for Elk

**Status: draft, 2026-09-28.** Written for Gustav Andersson and Justine Reverdell at Elk Audio after the
Elk Audio challenge. One item is still open (the MIDI jack probe, under Questions); it gets filled in after
the board session of 2026-09-28, and the document goes to Elk after that. Every number here comes from
[`data/profiling-results.csv`](../data/profiling-results.csv), [`elk-stomp-ports.yaml`](../elk-stomp-ports.yaml)
or the build log behind them.

## What we built on the Stomp

HORN SXTN is a harmonizer for horn players: a saxophone or a Roland Aerophone goes in, a correctly voiced
section comes out, with the harmony decided by THIRI, our deterministic theory engine. It runs as a headless
JUCE VST3 under Sushi on a stock Stomp development board: Elk Audio OS 1.2.2, Sushi 1.3.0, 64 samples at
48 kHz. It is our project on Elk's hardware, not an Elk product.

Measured on the board, three sweeps of six points at 60 s each, with 1.0 meaning the 1.333 ms deadline: the
engine plus pitch tracking alone sits at 0.568 average and 0.726 worst block; five harmony voices on top sit
at 0.592 average and 0.788 worst block. Each voice costs 0.005 of the block. The phase vocoder we ran at the
hackathon was over the deadline at one voice, so the shipped voices use PSOLA. The harness, the method, the
data and the board map are in this repository; the engine itself is closed.

## Three things you may want to know

### 1. An unpinned control app eats the audio deadline, and the CPU meter never shows it

The audio thread is pinned to CPU 1 by the driver and CPU 0 sits idle. Sensei and a control app left unpinned
land on CPU 1. Sixty seconds of steady playback per arm, worst block as a fraction of the period:

| Arm | Worst block |
|---|---|
| Sushi alone | 0.770 |
| Sushi + Sensei + control app, unpinned | 2.273 |
| Same, control app and Sensei pinned with `taskset -c 0` | 0.760 |

The average stayed near 0.60 in all three, so a CPU meter reads a healthy 60 percent while the audio drops
out. The devkit's `run-example.sh` does not pin, so this reaches any Stomp app built from the examples. One
line in the launcher fixes it.

### 2. Two small things in Sushi 1.3.0's VST3 wrapper

- **The transport flag.** `vst3x_wrapper` builds the process-context capability mask with an ampersand where
  an or is needed, so the mask is always zero and a VST3 plugin never sees host transport under Sushi. We
  found it because our plugin's host-clock mode could only be proven inside Ableton.
- **The event bus direction.** `_setup_event_buses` loops over the output bus count but passes `kInput`, and
  the error text says output bus. Sushi therefore never activates a plugin's event output bus. JUCE plugins
  still emit notes because JUCE initialises `isMidiOutputBusEnabled` to true and nothing turns it off; a
  spec-conforming non-JUCE VST3 is entitled to emit nothing. Verified against `elk-audio/sushi` master at
  `08f24e9` and JUCE 8.0.15.

Both look like one-line fixes. We are glad to open the pull requests if that is useful.

### 3. The board is more capable than its product page

The public description says stereo in and out plus controls. The board we audited from nine close-up
photographs on 1 September carries seven audio jacks, MIDI IN and MIDI OUT on 3.5 mm TRS, an S/PDIF header,
a jumper patchbay that decides which jack reaches which codec channel, and fifteen expansion headers (I2S,
ADC, GPIO, SPI, I2C, USART, STLINK, VBAT). We designed around the product page for a week and routed a wind
controller in over USB because we believed there was no hardware MIDI. A one-page connector and jumper map
from Elk would save every new Stomp owner that week. Ours, graded by how each fact was verified, is
[`elk-stomp-ports.yaml`](../elk-stomp-ports.yaml).

## Platform notes, offered as reference

- `/usr/bin/sushi` is a 561-byte POSIX shell script that selects `sushi_b32`, `sushi_b64` or `sushi_b128` from the
  buffer size in `/udata/.elk-system/elk-system.conf`. Inspecting it with `ldd` or `strings` says nothing;
  inspect the real binary. This cost us an hour and nearly became a support ticket about missing MIDI support.
- Sushi launched from a systemd user unit gets zero audio callbacks and every gRPC write returns success: the
  user manager caps real-time priority at 0. A pam ssh shell can take priority 99. Launch from the shell with
  `setsid` and `nohup`.
- Stop Sushi with SIGINT only. SIGTERM, SIGKILL or a dropped ssh session wedges `audio_evl` until a power
  cycle. `run-example.sh` traps INT and runs `kill 0`, which sends SIGTERM to the group.
- `/tmp/sushi.log` flushes only on a clean exit; use `--log-flush-interval=1` for unattended runs.
- The board's clock is wrong (it reports 2025) and file times are not usable as provenance. We identify every
  deployed binary by its sha256 and record it beside every measurement.
- Three USB controllers, not one contended port: the console (four ttys, the lowest is the console), USB HOST
  for instruments, and the USB-C gadget port, which gave us a network to the Mac over a single cable with no
  dongle. All three ran at once.
- Audio lives in `audio_evl` outside ALSA; MIDI lives in ALSA. A USB audio interface will not add channels to
  Sushi; a USB MIDI device works natively.
- Class-compliant USB MIDI works with zero setup. A Roland Aerophone AE-10 enumerated on USB HOST with no
  driver and no config, and 45 s of playing captured cleanly: 4,067 CC2 messages, 308 pitch bends, 72
  note-ons and 72 note-offs. This is a strong story for the platform and we are happy to have it on the record.
- Sushi does not connect itself to a hardware MIDI input; without the `aconnect` link the `cc_mappings` are
  silently deaf. The `midi-connections` service in Elk's docs is the right fix and we will use it.

## Questions for Elk

1. **MIDI IN and MIDI OUT on the 3.5 mm TRS jacks.** Type A or type B, and are they wired to a USART on the
   SoM? Do they appear to ALSA on the stock image, or does that need a device-tree overlay? Result of our own
   probe: pending (board session of 2026-09-28).
2. **The jumper patchbay.** Which shunt routes which jack to which codec channel? Verified so far on this unit:
   GUITAR IN L is engine channel 0; HEADPHONE OUT and LINE OUT both carry channels 2 and 3 and are not
   exclusive; GUITAR OUT L and R are the 0 and 1 pair.
3. **Can the USB-C gadget port act as a USB host?** The controller is dual-role.
4. **Is `track_out_connections` safe to depend on for hardware MIDI out?** It is in the configuration docs but
   not in `midi_schema.json`, which validates it only because `additionalProperties` is not set to false.

## What we would like from the two mentoring sessions

**Session one:** the four questions above, the two wrapper fixes, and a look at our rig builder, a browser
tool that edits the live Sushi graph over gRPC, maps the Stomp's pots, encoders and switches to plugin
parameters without code, and boots one rig file on the desktop devkit or the board.

**Session two, after our demo video:** the path from a stock Stomp to a product, and what Elk would need from
us to show the pedal.

## Where the evidence lives

- [`data/profiling-results.csv`](../data/profiling-results.csv): every measured row, with the binary hash and
  the config beside it.
- [`elk-stomp-ports.yaml`](../elk-stomp-ports.yaml): the connector and control map, each fact graded by how
  it was verified.
- [`METHOD.md`](../METHOD.md) and [`RUNBOOK.md`](../RUNBOOK.md): the measurement discipline and the exact
  commands.
- [`skills/`](../skills): the compiled board knowledge, written as agent skills.
