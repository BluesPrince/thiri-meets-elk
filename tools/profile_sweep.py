#!/usr/bin/env python3
"""profile_sweep.py — THIRI voice-ceiling sweep on Elk Stomp (or desktop dry-run).

Drives a RUNNING Sushi over gRPC: sweeps the plugin's `num_voices` parameter 0..5,
and for each point records Sushi's own per-processor timing statistics
(TimingController). It never starts or stops Sushi — use sushi_board.sh /
sushi_desktop.sh for the lifecycle (SIGINT-only on the board!).

UNITS: Sushi's Timings{average,min,max} are a FRACTION OF THE BLOCK PERIOD
(not ms — elkpy's docstring is wrong; sushi-gui renders value*100 as %).
max >= 1.0 means the processor missed the deadline at least once: that is the
xrun proxy (Sushi has no xrun counter). Pass thresholds: <0.7 shippable headroom,
<1.0 hard deadline.

Run from the Mac via the devkit's uv env (has grpcio):
  cd $ELK_DEVKIT && uv run python tools/profile_sweep.py \
      --host desktop --addr localhost:51051 --voices 0,1,2,3,4,5 --settle 3 --measure 10

  cd $ELK_DEVKIT && uv run python tools/profile_sweep.py \
      --host board --addr <board-ip>:51051 --ssh mind@<board-ip> \
      --voices 0,1,2,3,4,5 --settle 10 --measure 60 --notes "sweep 1 of 3"
"""
import argparse, csv, datetime, hashlib, os, subprocess, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
import grpc                       # noqa: E402
import sushi_rpc_pb2 as pb        # noqa: E402
import sushi_rpc_pb2_grpc as rpc  # noqa: E402

NUM_VOICES_MAX = 5                # param range 0..5 -> normalized = v / 5
CSV_FIELDS = [
    "timestamp_iso", "host", "board_ip", "sushi_version", "block_size", "sample_rate",
    "voice_count", "voicing", "role", "settle_s", "measure_s",
    "thiri_avg", "thiri_min", "thiri_max", "thiri_max_ms",
    "sax_avg", "sax_max", "track_avg", "track_max", "engine_avg", "engine_max",
    "max_lt_0p7", "max_lt_1p0",
    "affinity_psr", "rtprio", "cpu0_freq_khz", "cpu1_freq_khz", "governor",
    "plugin_sha256", "config_file", "session_mode", "notes",
]


def ssh(target, cmd, timeout=10):
    """Run a read-only command on the board; return stdout or 'na' on any failure."""
    try:
        r = subprocess.run(["ssh", "-o", "ConnectTimeout=5", target, cmd],
                           capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else "na"
    except Exception:
        return "na"


def board_snapshots(target):
    aff = ssh(target, "ps -eLo psr,rtprio,comm | grep -i sushi | sort -u | tr '\\n' ';'")
    freq0 = ssh(target, "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null")
    freq1 = ssh(target, "cat /sys/devices/system/cpu/cpu1/cpufreq/scaling_cur_freq 2>/dev/null")
    gov = ssh(target, "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null")
    rt = "na"
    if aff not in ("", "na"):
        # highest rtprio among sushi threads
        prios = [p.split()[1] for p in aff.split(";") if len(p.split()) >= 2 and p.split()[1].isdigit()]
        rt = max(prios, key=int) if prios else "0"
    return aff or "na", rt, freq0 or "na", freq1 or "na", gov or "na"


def plugin_sha(args):
    if args.ssh:
        out = ssh(args.ssh, "sha256sum /home/mind/plugins/THIRI.vst3/Contents/armv7l-linux/THIRI.so 2>/dev/null | cut -d' ' -f1")
        if out != "na" and out:
            return out
    local = os.path.join(REPO, "plugin/build/THIRI_artefacts/Release/VST3/THIRI.vst3/Contents/MacOS/THIRI")
    if os.path.exists(local):
        return hashlib.sha256(open(local, "rb").read()).hexdigest()
    return "na"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", choices=["board", "desktop"], required=True)
    ap.add_argument("--addr", default="localhost:51051")
    ap.add_argument("--ssh", default=None, help="mind@<board-ip> for per-point snapshots (board only)")
    ap.add_argument("--voices", default="0,1,2,3,4,5")
    ap.add_argument("--settle", type=float, default=10.0)
    ap.add_argument("--measure", type=float, default=60.0)
    ap.add_argument("--notes", default="")
    ap.add_argument("--out", default=os.path.join(REPO, "profiling-results.csv"))
    ap.add_argument("--config-file", default="", help="recorded in the CSV for provenance")
    args = ap.parse_args()
    voices = [int(v) for v in args.voices.split(",")]

    chan = grpc.insecure_channel(args.addr)
    try:
        grpc.channel_ready_future(chan).result(timeout=10)
    except grpc.FutureTimeoutError:
        sys.exit(f"FATAL: no Sushi gRPC at {args.addr} — start it first (sushi_board.sh / sushi_desktop.sh)")
    timing = rpc.TimingControllerStub(chan)
    params = rpc.ParameterControllerStub(chan)
    graph = rpc.AudioGraphControllerStub(chan)
    system = rpc.SystemControllerStub(chan)
    void = pb.GenericVoidValue()

    # ── session facts (once) ──
    info = system.GetBuildInfo(void)
    block_size, sushi_version = info.audio_buffer_size, info.version
    thiri = graph.GetProcessorId(pb.GenericStringValue(value="thiri")).id
    sax = graph.GetProcessorId(pb.GenericStringValue(value="SaxSource")).id
    track = graph.GetTrackId(pb.GenericStringValue(value="main")).id

    def pident(name):
        # GetParameterId returns a complete ParameterIdentifier message as .id
        return params.GetParameterId(pb.ParameterIdRequest(
            processor=pb.ProcessorIdentifier(id=thiri), ParameterName=name)).id

    nv_ident = pident("num_voices")
    voicing_str = params.GetParameterValueAsString(pident("voicing")).value
    role_str = params.GetParameterValueAsString(pident("role")).value
    # sweep-validity guard: gateCount == num_voices only when THIRI seats 5 voices
    if "jazz" not in voicing_str.lower():
        sys.exit(f"FATAL: voicing is '{voicing_str}', not jazz — voice counts 4/5 would alias. "
                 f"Use the profile config (voicing normalized 1.0).")

    timing.SetTimingsEnabled(pb.GenericBoolValue(value=True))
    sha = plugin_sha(args)
    sr = 48000
    print(f"session: sushi {sushi_version} | block {block_size} | voicing {voicing_str} | "
          f"role {role_str} | thiri id {thiri} | sha {sha[:12]}")
    if args.host == "board" and block_size != 64:
        print(f"NOTE: block size is {block_size}, not 64 — recording as-is (the contingent axis).")

    new_file = not os.path.exists(args.out)
    rows_written = 0
    with open(args.out, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if new_file:
            w.writeheader()
        for v in voices:
            params.SetParameterValue(pb.ParameterValue(
                parameter=nv_ident, value=v / NUM_VOICES_MAX))
            # Sushi applies param changes asynchronously on the audio thread —
            # an immediate readback returns the old value. Retry briefly.
            got = None
            for _ in range(20):
                time.sleep(0.25)
                back = params.GetParameterValue(nv_ident).value
                got = round(back * NUM_VOICES_MAX)
                if got == v:
                    break
            if got != v:
                sys.exit(f"FATAL: num_voices readback {got} != requested {v} "
                         f"(raw {back}) — aborting; {rows_written} rows written")
            time.sleep(args.settle)
            timing.ResetAllTimings(void)
            time.sleep(args.measure)
            t_thiri = timing.GetProcessorTimings(pb.ProcessorIdentifier(id=thiri)).timings
            t_sax = timing.GetProcessorTimings(pb.ProcessorIdentifier(id=sax)).timings
            t_track = timing.GetTrackTimings(pb.TrackIdentifier(id=track)).timings
            t_eng = timing.GetEngineTimings(void).main
            aff, rt, f0, f1, gov = board_snapshots(args.ssh) if args.ssh else ("na",) * 5
            max_ms = t_thiri.max * block_size / sr * 1000.0
            row = dict(
                timestamp_iso=datetime.datetime.now().isoformat(timespec="seconds"),
                host=args.host, board_ip=(args.addr.split(":")[0] if args.host == "board" else ""),
                sushi_version=sushi_version, block_size=block_size, sample_rate=sr,
                voice_count=v, voicing=voicing_str, role=role_str,
                settle_s=args.settle, measure_s=args.measure,
                thiri_avg=f"{t_thiri.average:.4f}", thiri_min=f"{t_thiri.min:.4f}",
                thiri_max=f"{t_thiri.max:.4f}", thiri_max_ms=f"{max_ms:.3f}",
                sax_avg=f"{t_sax.average:.4f}", sax_max=f"{t_sax.max:.4f}",
                track_avg=f"{t_track.average:.4f}", track_max=f"{t_track.max:.4f}",
                engine_avg=f"{t_eng.average:.4f}", engine_max=f"{t_eng.max:.4f}",
                max_lt_0p7=t_thiri.max < 0.7, max_lt_1p0=t_thiri.max < 1.0,
                affinity_psr=aff, rtprio=rt, cpu0_freq_khz=f0, cpu1_freq_khz=f1, governor=gov,
                plugin_sha256=sha, config_file=args.config_file,
                session_mode="single-session", notes=args.notes,
            )
            w.writerow(row); f.flush()
            rows_written += 1
            verdict = "PASS<0.7" if t_thiri.max < 0.7 else ("PASS<1.0" if t_thiri.max < 1.0 else "FAIL>=1.0")
            print(f"  v={v}  thiri max {t_thiri.max:.3f} of period ({max_ms:.2f} ms)  "
                  f"avg {t_thiri.average:.3f}  {verdict}")
    print(f"done: {rows_written} rows -> {args.out}")


if __name__ == "__main__":
    main()
