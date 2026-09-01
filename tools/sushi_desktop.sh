#!/bin/bash -e
# sushi_desktop.sh — desktop Sushi lifecycle for harness dry-runs (plumbing only;
# x86 timing numbers are meaningless for the board decision).
#
#   tools/profiling/sushi_desktop.sh start [--dummy]   # --dummy = no audio device (-d)
#   tools/profiling/sushi_desktop.sh stop
#   tools/profiling/sushi_desktop.sh log
DEVKIT="${ELK_DEVKIT:-$HOME/elk-desktop-devkit}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PLUGDIR="$DEVKIT/plugins/vstplugins-macos"
VST3="$ROOT/plugin/build/THIRI_artefacts/Release/VST3/THIRI.vst3"
CONF_SRC="$ROOT/config/sushi_config_profile_desktop.json"
CONF="/tmp/sushi_profile_desktop.json"
STATE="/tmp/horn_profile_desktop_pid"
LOG="/tmp/sushi_profile_desktop.log"

case "${1:?start|stop|log}" in
  start)
    [ -d "$VST3" ] || { echo "!! build first: cmake --build plugin/build --target THIRI_All"; exit 1; }
    rm -rf "$PLUGDIR/THIRI.vst3"; cp -R "$VST3" "$PLUGDIR/"
    xattr -rc "$PLUGDIR/THIRI.vst3" 2>/dev/null || true
    # absolutize the wav path into a temp copy of the config
    python3 - "$CONF_SRC" "$CONF" "$ROOT" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
c["initial_state"][0]["properties"]["file"] = sys.argv[3] + "/assets/audio/${ELK_TESTWAV:-test_loop.wav}"
json.dump(c, open(sys.argv[2], "w"), indent=2)
PY
    FRONTEND="--coreaudio"; [ "${2:-}" = "--dummy" ] && FRONTEND="-d"
    rm -f "$LOG"
    "$DEVKIT/bin/macos/sushi" $FRONTEND --timing-statistics --log-flush-interval=1 \
        -c "$CONF" --base-plugin-path="$PLUGDIR" > "$LOG" 2>&1 &
    echo $! > "$STATE"
    echo "==> desktop sushi started (pid $(cat "$STATE"), $FRONTEND); waiting for gRPC :51051"
    for i in $(seq 1 15); do
      nc -z -w1 localhost 51051 2>/dev/null && { echo "==> gRPC up"; exit 0; }
      sleep 1
    done
    echo "!! gRPC never came up — tail $LOG"; exit 1
    ;;
  stop)
    PID=$(cat "$STATE" 2>/dev/null || true)
    [ -n "$PID" ] && kill -INT "$PID" 2>/dev/null || true
    rm -f "$STATE"; echo "==> stopped"
    ;;
  log) tail -40 "$LOG";;
  *) echo "usage: $0 start [--dummy] | stop | log"; exit 1;;
esac
