#!/bin/bash -e
# sushi_board.sh — safe Sushi lifecycle on the Elk Stomp for profiling.
#
#   tools/sushi_board.sh start mind@<board-ip>
#   tools/sushi_board.sh stop  mind@<board-ip>
#   tools/sushi_board.sh log   mind@<board-ip>
#
# RULES (they save a power-cycle):
#   - stop is SIGINT ONLY. SIGTERM/SIGKILL — or a dropped SSH session acting as the
#     kill — wedges the audio_evl driver: the next Sushi launch hangs and the board
#     must be power-cycled. start therefore uses setsid+nohup so the SSH channel
#     closing can never be the shutdown mechanism.
#   - --log-flush-interval=1 so a hung run still leaves a readable log.
CMD="${1:?start|stop|log}"; B="${2:?mind@<board-ip>}"
STATE="/tmp/horn_profile_sushi_pid"
# optional 3rd arg: config filename in ${ELK_APP:-/home/mind/app} (default = pv profile)
CONF="${ELK_APP:-/home/mind/app}/${3:-${ELK_CONFIG:-sushi_config_profile.json}}"

case "$CMD" in
  start)
    ssh -o ConnectTimeout=5 "$B" true || { echo "!! board unreachable"; exit 1; }
    PID=$(ssh "$B" "cd ${ELK_APP:-/home/mind/app} && setsid nohup env VSTPLUGINS_PATH=/home/mind/plugins/ \
        sushi -r --timing-statistics --log-flush-interval=1 -c $CONF \
        --base-plugin-path=/home/mind/plugins/ > sushi_profile.log 2>&1 & echo \$!")
    echo "$PID" > "$STATE"
    echo "==> sushi -r started on $B (pid $PID); waiting for gRPC :51051"
    IP="${B#*@}"
    for i in $(seq 1 30); do
      if nc -z -w1 "$IP" 51051 2>/dev/null; then echo "==> gRPC up"; exit 0; fi
      sleep 1
    done
    echo "!! gRPC never came up — check: $0 log $B"; exit 1
    ;;
  stop)
    PID=$(cat "$STATE" 2>/dev/null || true)
    [ -n "$PID" ] || PID=$(ssh "$B" "pgrep -x sushi | head -1")
    [ -n "$PID" ] || { echo "no sushi running"; exit 0; }
    echo "==> SIGINT to sushi pid $PID (the only safe stop)"
    ssh "$B" "kill -INT $PID"
    sleep 2
    if ssh "$B" "kill -0 $PID 2>/dev/null"; then
      echo "still exiting; waiting 5 more..."; sleep 5
      ssh "$B" "kill -0 $PID 2>/dev/null" && echo "!! sushi did not exit — do NOT SIGKILL; power-cycle if wedged" && exit 1
    fi
    rm -f "$STATE"
    echo "==> clean exit; last log lines:"
    ssh "$B" "tail -n 5 ${ELK_APP:-/home/mind/app}/sushi_profile.log" || true
    ;;
  log)
    ssh "$B" "tail -n 40 ${ELK_APP:-/home/mind/app}/sushi_profile.log"
    ;;
  *) echo "usage: $0 start|stop|log mind@<board-ip>"; exit 1;;
esac
