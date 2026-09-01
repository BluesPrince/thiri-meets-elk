---
name: elk-midi-routing
description: Get MIDI from a physical instrument into a headless Sushi rig on Elk — cc_mappings that drive plugin parameters with no plugin rebuild, and the ALSA sequencer link whose absence makes the whole thing silently deaf. Use whenever a pedal or board should respond to CCs, whenever a mapping "is correct but nothing moves", whenever an expression pedal / breath / knob on a controller should reach a plugin parameter, whenever MIDI stops working after restarting Sushi or running a capture tool, or whenever deciding between MIDI-as-control and MIDI-as-notes. The most common failure here logs nothing at all, so check the link before debugging anything else.
---

# MIDI into a headless Sushi rig

Two different things travel over the same cable and they are wired up completely
differently. Decide which you want before writing any config.

- **Control** — a CC moves a plugin parameter. Handled by Sushi's MIDI dispatcher via
  `cc_mappings`. The note stream never enters the track. **No plugin change required.**
- **Notes** — MIDI events reach the plugin as events. Needs `track_connections` *and* a
  plugin that is a MIDI-accepting instrument or MIDI effect.

Most "make the pedal respond to the horn" work is the first one, and it is config-only.

---

## cc_mappings

```json
"midi": {
  "cc_mappings": [
    { "port": 0, "channel": "all", "cc_number": 2,
      "plugin_name": "thiri", "parameter_name": "wet_dry",
      "min_range": 0.0, "max_range": 1.0 },
    { "port": 0, "channel": "all", "cc_number": 5,
      "plugin_name": "delay", "parameter_name": "fb_coeff",
      "min_range": 0.0, "max_range": 0.85 }
  ]
}
```

- `plugin_name` is the `"name"` you gave the plugin **in this config**, not its vendor name.
- `parameter_name` is the VST3 **display name**. If the plugin pins display name to a
  snake_case id, use that verbatim; otherwise dump the parameter list over gRPC and copy the
  exact string. A typo produces `Invalid parameter name` in the log — one of the few
  failures here that does announce itself.
- `min_range`/`max_range` scale CC 0–127 into that span. Use it to make a control safe:
  capping feedback at 0.85 means the pedal cannot self-oscillate no matter how hard the
  expression is pushed.
- `host_config.midi_inputs` defaults to 1, so `"port": 0` needs no declaration.

**Keep destructive parameters off CCs.** One stray CC into a mode switch mid-set can put the
rig somewhere it cannot recover from — e.g. flipping an algorithm select from the cheap
implementation to one that misses every deadline. Map it in the glue app with a deliberate
gesture, or not at all.

---

## The failure that logs nothing: the ALSA sequencer link

**Sushi does not connect itself to hardware MIDI inputs.** Its ALSA sequencer client appears
asynchronously after start, and the instrument may be plugged in later still. Without an
explicit link:

- the config is correct
- Sushi registers the CC connections at startup
- nothing appears in any log
- the parameters simply never move

There is no error to search for. Check this **first**, every time, before doubting the
config.

```bash
aconnect -l                       # find Sushi's client id, and the instrument's
aconnect <instrument>:0 <sushi>:0
```

Automate it in the launcher rather than relying on memory — poll for Sushi's client for a
few seconds, then link every kernel-type input except client 0 (System):

```bash
sushi_cl=$(aconnect -l | sed -n "s/^client \([0-9]*\): 'Sushi'.*/\1/p" | head -n 1)
for src in $(aconnect -i | sed -n "s/^client \([0-9]*\): .*type=kernel.*/\1/p"); do
  [ "$src" = "0" ] && continue
  aconnect "${src}:0" "${sushi_cl}:0" 2>/dev/null && echo "linked ${src} -> ${sushi_cl}"
done
```

### Three things that sever the link, all silently

1. **Restarting Sushi.** New client id, no connections. Re-link every launch.
2. **Running a raw-MIDI tool on the same device** — `amidi -d -p hw:0,0,0` starves the
   sequencer path and takes the link with it. After any raw capture, re-link.
3. **Replugging the instrument.** New client number.

If CCs worked and then stopped, the answer is almost always one of these three and not your
config.

---

## Diagnosis ladder

Work down it; stop at the first failure.

1. `aconnect -l` — does the instrument appear as a client at all? No → USB/driver, not MIDI.
2. Does a `Sushi` client exist? No → Sushi is not running, or not built with MIDI support.
3. Is there a connection arrow between them? No → **this is the bug.** Link it.
4. `amidi -d -p hw:X,Y,Z` — is the controller actually transmitting that CC number? Manuals
   lie; see `midi-controller-profile`. **Re-link afterwards.**
5. Sushi's log for `Invalid parameter name` → the `parameter_name` string is wrong.
6. Read the parameter back over gRPC while moving the control — this separates "the
   parameter is not moving" from "the parameter moves but does nothing audible."

---

## If you do want notes in the track

`track_connections` routes the note stream to a plugin. Two consequences worth knowing
before you enable it:

- The plugin must actually be a MIDI-accepting instrument or MIDI effect. An audio effect
  will accept the connection and ignore the events.
- If the plugin is JUCE-built with `JUCE_VST3_EMULATE_MIDI_CC_WITH_PARAMETERS`, it exposes
  **16 channels × 130 controllers = 2080 phantom parameters** to the host. Index 128 is
  aftertouch and 129 is pitch bend. This bloats every parameter enumeration and makes the
  gRPC parameter list nearly unreadable. Turn it off unless you are deliberately using it.

Pitch bend and aftertouch are **not CCs** and cannot be reached by `cc_mappings` at all. If
a controller sends its most expressive gestures on pitch bend — many wind controllers do by
default — reassign them to real CC numbers on the instrument, or they are invisible here.
