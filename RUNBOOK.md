# RUNBOOK.md — running the sweep

Adapted from the runbook used to produce `data/profiling-results.csv`. The plugin-specific
parts are called out; everything else transfers.

## 0. What the numbers mean

- Sushi's `Timings{average,min,max}` are a **fraction of the block period**, not
  milliseconds. elkpy's docstring says ms and is wrong; sushi-gui renders `value*100` as
  a percentage. At 64 samples / 48 kHz, **`1.0` = the 1.333 ms deadline**.
- **`max >= 1.0` is a missed deadline.** Sushi has no xrun counter; this is the proxy.
- Suggested thresholds: **`max < 0.7`** = shippable headroom, **`< 1.0`** = hard deadline.
  The decision number is the largest scaling point passing your threshold on *all* rows.
- **Block size is compiled into the Sushi binary.** Record it per row (the harness reads
  `GetBuildInfo`). Elk ships `sushi_b32` / `sushi_b64` / `sushi_b128` and `/usr/bin/sushi`
  is a wrapper selecting one via `AUDIO_BUFFER_SIZE` in `/udata/.elk-system/elk-system.conf`.
  Note that inspecting `/usr/bin/sushi` with `ldd` or `strings` tells you nothing — it is
  a shell script. Inspect `sushi_b<size>`.

## 1. Board bring-up (once)

1. Serial cable, power on, wait ~30 s. The board exposes **four** `tty.usbserial-*`;
   use the **lowest**-numbered.
2. `picocom -b 115200 /dev/tty.usbserial-XXXX`. Login is Elk's documented default.
   Exit picocom with **Ctrl-A then Ctrl-X**.
3. Networking: a USB Ethernet dongle in the USB-C port *not* labelled `USB TO UART`, or
   USB-gadget networking. `ssh-copy-id` once, so per-row snapshots never prompt.
4. **Keep the serial cable attached during the first sweep** — it is the recovery console,
   and its login persists where an SSH session does not (systemd-logind reaps the user
   scope on logout).

## 2. The sweep

```bash
tools/preflight.sh mind@<board-ip>              # all PASS/INFO before proceeding
tools/sushi_board.sh start mind@<board-ip>
```

Smoke row first — check the worst case is plausible and affinity/priority populated:

```bash
python3 tools/profile_sweep.py --host board --addr <board-ip>:51051 \
    --ssh mind@<board-ip> --voices 5 --settle 10 --measure 20 --notes smoke
```

Then the full sweep, **three times**. Worst-of-worst per point is the decision number;
cross-run spread is the confidence check. Do not touch the board during a run.

```bash
python3 tools/profile_sweep.py --host board --addr <board-ip>:51051 \
    --ssh mind@<board-ip> --voices 0,1,2,3,4,5 --settle 10 --measure 60 \
    --notes "sweep 1 of 3"
```

Stop with **SIGINT only**. SIGTERM or SIGKILL wedges the `audio_evl` driver and the next
launch hangs until the board is power-cycled:

```bash
tools/sushi_board.sh stop mind@<board-ip>
```

## 3. Why it is built this way

- **One Sushi session per sweep**, parameters swept over gRPC with `ResetAllTimings`
  between points. Six times fewer restarts means six times fewer chances to wedge the
  driver, and warm plugin state is the *correct* steady-state measurement.
- **Settle 10 s** absorbs the transient after a parameter change. **Measure 60 s** is
  3.75 loops of the 16 s source material, so every point hears all of it regardless of
  loop phase.
- **Parameters apply asynchronously on the audio thread.** The harness retries readback
  before trusting a point. Without this you will silently measure the previous setting.
- **Sweep validity guard** *(plugin-specific)*: the scaling parameter must actually gate
  what you think it gates. Ours clamps a contiguous prefix of voices, preserving the
  shared-analysis owner invariant, so the engine's own cost stays constant across points
  and row deltas are pure shifter cost. The harness aborts if the mode readback is wrong,
  because otherwise the voice counts alias and the sweep is meaningless.
- **Zero is the control row.** Point 0 isolates everything that runs regardless of
  scaling. It is the most useful single number in the dataset.

## 4. Outputs

1. `data/profiling-results.csv` — append-only, every run including failures.
2. The decision number: largest scaling point with `max` under your threshold on all rows.
3. The isolated engine cost: the **point-0** rows.
4. Confounds found and fixed: note them in the CSV `notes` column *and* here. If fixing
   one moved the ceiling, the earlier rows are void — re-sweep (see METHOD.md §2).

## 5. Gotchas worth knowing before you hit them

- **`amidi` on the raw MIDI device severs the ALSA sequencer link to Sushi.** After any
  raw-MIDI capture, re-run `aconnect`. Without the link, CC mappings are silently deaf:
  configuration correct, connections registered, no error logged, parameters never move.
- **`GetAllCCInputConnections` reports `min=0.0 max=0.0`** for internal plugins even when
  the ranges are demonstrably applied. Trust parameter values, not the connection dump.
- **The board's clock is wrong** (no RTC). Identify artefacts by `sha256`, never mtime.
- **Elk's `run-example.sh` traps INT and runs `kill 0`** — SIGTERM to the process group,
  which is the signal that wedges the driver. Use SIGINT explicitly.
