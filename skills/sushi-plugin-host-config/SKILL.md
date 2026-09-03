---
name: sushi-plugin-host-config
description: Reference for Sushi's session config JSON — tracks, channels, inputs/outputs, plugin declarations (internal/vst3x/lv2), initial_state, and the gRPC control API (elkpy) for reading/writing parameters at runtime — plus what a hosted VST3 can see of Sushi's transport (playing state yes, tempo/position never), the elkpy timing-statistics API, and the initial_state traps that impersonate plugin bugs (unset params start at 0: JX10 pitch bend at −100 %, glide; a synth replaces upstream audio; one flat name namespace). Use whenever writing or debugging a Sushi config file, whenever a plugin loads but its parameters don't respond, whenever play/stop or tap tempo must reach a plugin, or whenever you need to control a running Sushi instance programmatically.
---

# Sushi config JSON + gRPC control reference

Compiled 2026-08-21 building and debugging HORN SXTN's Sushi configs. Sushi is
Elk's headless multitrack plugin host — no timeline, no editor, just tracks
with plugin chains, configured by JSON and controlled at runtime over gRPC
(port 51051 by default) or a limited OSC surface.

## Minimal config anatomy

```json
{
  "host_config": { "samplerate": 48000, "playing_mode": "playing" },
  "tracks": [{
    "name": "main",
    "channels": 2,
    "inputs":  [{ "engine_channel": 0, "track_channel": 0 }],
    "outputs": [{ "engine_channel": 0, "track_channel": 0 },
                { "engine_channel": 1, "track_channel": 1 }],
    "plugins": [
      { "uid": "sushi.testing.gain", "name": "gain", "type": "internal" },
      { "path": "MyPlugin.vst3", "uid": "MyPlugin", "name": "myplug", "type": "vst3x" },
      { "uri": "http://example.org/plugin", "name": "lv2plug", "type": "lv2" }
    ]
  }],
  "initial_state": [
    { "processor": "myplug", "parameters": { "gain": 0.8 }, "properties": { "file": "x.wav" } }
  ]
}
```

- **`inputs`/`outputs`** map one **engine channel** (the physical/OS audio
  device channel) to one **track channel**. `outputs` can also use `"engine_bus"`/
  `"track_bus"` — a bus is shorthand for an adjacent channel pair.
- **`plugins`** identification differs by type: `internal` needs a `uid`
  (Sushi built-ins like `sushi.testing.wav_streamer`, `sushi.testing.gain`,
  `sushi.testing.freeverb`, `sushi.testing.send`/`sushi.testing.return` for aux
  sends); `vst3x`/`vst2x` need `uid` (must match the plugin's FUID/PRODUCT_NAME,
  see **juce-elk-plugin-cmake**) + `path`; `lv2` needs a `uri` instead of a path.
- **`initial_state`** sets startup values, addressed by the plugin's `name`
  (the config-local identifier you chose, not the class/uid) — `parameters`
  by **parameter name string** (must match the plugin's actual param name
  exactly, see the naming gotcha in **juce-elk-plugin-cmake**), `properties`
  for non-numeric config like a file path.

## Aux sends/returns (reverb buses, etc.)

An aux track has no `inputs`; a `sushi.testing.send` at the end of the source
track's chain and a `sushi.testing.return` at the start of the aux track's
chain, connected via a **property** in `initial_state`:

```json
{ "processor": "Send_rev", "properties": { "destination_name": "Return_rev" } }
```

## gRPC control at runtime (elkpy)

```python
from elkpy import async_sushicontroller as sc
c = sc.SushiController("localhost:51051")
proc_id = await c.audio_graph.get_processor_id("myplug")
param_id = await c.parameters.get_parameter_id(proc_id, "gain")
v = await c.parameters.get_parameter_value(proc_id, param_id)
await c.parameters.set_parameter_value(proc_id, param_id, 0.5)
```

Parameter values over gRPC (and OSC) are always **normalized [0,1]**, never
the plugin's native range — you convert on both sides.

## What a VST3 plugin can and cannot see from Sushi's transport (measured 2026-09-03)

Probe build (a plugin printing its `AudioPlayHead` position each second) under desktop
Sushi 1.3, transport driven with elkpy:

| via `getPlayHead()->getPosition()` | under Sushi |
|---|---|
| `getIsPlaying()` | **follows `set_playing_mode`** (1 → 0 → 1 across a STOPPED window) |
| `getBpm()` / `getPpqPosition()` | **empty** (Sushi never flags them valid) |

So a plugin that gates its own clock on the host's playing state works with the app's
play/stop, but **tap tempo / tempo changes must be written into the plugin's own `tempo`
parameter** — nothing arrives through the host. Set the playing mode with **elkpy's
`PlayingMode` enum**; hand-built raw-proto values read back inverted (STOPPED=1, PLAYING=2,
RECORDING=3 in both, but a naive `pb.PlayingMode.X` probe got the numbering wrong and
"proved" the opposite for an hour).

## Timing statistics API (elkpy)

`c.timings.get_processor_timings(pid)` returns a plain **tuple** `(average, min, max)` as a
*fraction of the block period* (elkpy's docstring says ms — wrong); `get_engine_timings()`
returns a `Timings` object. Desktop dummy-frontend `max` values are scheduler noise (we saw
3× and 13× on a track averaging 0.002) — only `average` trends mean anything off the board.

## initial_state traps that look like plugin bugs

- **Every parameter you do not set starts at 0**, not at the plugin's default. mda JX10's
  `Pitch Bend` at 0 = **−100 %**, so every note is a semitone or two flat until you set it
  to 0.5; its `Glide` at 0.3 = Poly-Legato with `Gld Rate 0` = slowest → every note slides.
  Set `Pitch Bend 0.5`, `Glide 0.0` (Poly) in any config that must play exact pitches.
- **A synth after a plugin replaces the audio** the plugin wrote — a click or any audio a
  MIDI-domain plugin adds to its pass-through is inaudible on a `plugin → synth` track. Put
  it on its own track.
- Sushi keeps **one flat namespace** for tracks and processors: a plugin may not reuse its
  track's name, and a second instance of the same plugin needs a distinct `name` (`arp` and
  `metro`, both `uid: "THIRI MIDI"`, is fine).
- Sushi writes `timings.txt` into its **cwd** when timing statistics are on; if that file is
  tracked in the repo, restore it before committing.

## OSC control plane (prototyping only — know its real limits)

Sushi's OSC receiver does **exact-match dispatch** on `(address, typetag)`
pairs it registered itself. No wildcards, no custom addresses, no way to
register your own — unknown addresses are silently dropped. The auto-generated
surface: `/parameter/<proc>/<param>` (float, normalized), `/property/<proc>/<prop>`
(string — yes, string params ARE OSC-addressable), `/keyboard_event/<track>`,
`/program/<proc>`, `/bypass/<proc>`, `/engine/set_tempo`. If you need a custom
wire protocol, build a small relay process that translates into this surface —
don't expect to extend Sushi's OSC receiver directly.

## The wav_streamer offline-render trap

`sushi.testing.wav_streamer` underruns in **offline** (`-o`) faster-than-
real-time renders — see **raspa-frontend-select** for the full explanation and
the engine-input workaround. It's fine in real-time frontends.

## Board vs desktop config differences

Only two things typically change between desktop and board configs: the audio
routing (board has 4 fixed engine channels: guitar in L/R = 0/1, line in
stereo = 2/3; guitar out L/R = 0/1, headphones = 2/3) and plugin `path`
(board plugin paths resolve relative to `$VSTPLUGINS_PATH`, set by
`bin/setup-sushi-env.sh` to `/home/mind/plugins/`). Everything else —
tracks, initial_state, plugin chain order — stays identical.

## Related skills

- **raspa-frontend-select** — which Sushi binary flag to launch this config
  with, and the offline-render timing gotcha in more depth.
- **juce-elk-plugin-cmake** — building the vst3x plugin this config loads,
  including the parameter-name-must-match gotcha.
- **elk-board-deploy** — the board-specific config differences in full.
