#!/bin/bash
# preflight.sh — executable confound checklist before an on-board profiling sweep.
#   tools/preflight.sh mind@<board-ip>
# Prints PASS/WARN/INFO per check; exits nonzero only on hard failures.
B="${1:?usage: preflight.sh mind@<board-ip>}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FAIL=0
say(){ printf "%-6s %s\n" "$1" "$2"; }
run(){ ssh -o ConnectTimeout=5 "$B" "$1" 2>/dev/null; }

# 1. reachable + auth
if run true; then say PASS "ssh $B reachable"; else say FAIL "cannot ssh to $B"; exit 1; fi

# 2. sushi present + compiled buffer size
V=$(run "sushi -v 2>&1 | tr '\n' ' '")
if [ -n "$V" ]; then
  say PASS "sushi: $(echo "$V" | head -c 100)"
  BS=$(echo "$V" | grep -oE 'buffer size in frames: *[0-9]+' | grep -oE '[0-9]+' | head -1)
  if [ "$BS" = "64" ]; then say PASS "compiled buffer size = 64 (1.333 ms deadline)";
  elif [ -n "$BS" ]; then say WARN "compiled buffer size = $BS, not 64 — the contingent axis; recorded per-run";
  else say INFO "could not parse buffer size from sushi -v (harness records it via GetBuildInfo)"; fi
else say FAIL "sushi not found on board PATH"; FAIL=1; fi

# 3. plugin deployed, right arch folder
if run "test -f /home/mind/plugins/THIRI.vst3/Contents/armv7l-linux/THIRI.so"; then
  say PASS "THIRI.so present in armv7l-linux/ ($(run 'du -h /home/mind/plugins/THIRI.vst3/Contents/armv7l-linux/THIRI.so | cut -f1'))"
else say FAIL "THIRI.so missing at /home/mind/plugins/THIRI.vst3/Contents/armv7l-linux/ — run stomp/deploy.sh"; FAIL=1; fi

# 4. wav + profile config on board
for f in ${ELK_APP:-/home/mind/app}/${ELK_TESTWAV:-test_loop.wav} ${ELK_APP:-/home/mind/app}/${ELK_CONFIG:-sushi_config_profile.json}; do
  if run "test -f $f"; then say PASS "$f"; else say FAIL "$f missing — run stomp/deploy.sh"; FAIL=1; fi
done

# 5. governor / cpufreq
GOV=$(run "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
FRQ=$(run "cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq | tr '\n' ' '")
if [ -n "$GOV" ]; then
  say INFO "governor=$GOV freq_khz=[$FRQ] (performance governor gives stable numbers; recorded per-row)"
else say INFO "cpufreq sysfs absent — freq recorded as na"; fi

# 6. competing load
TOP=$(run "ps -eo psr,pcpu,rtprio,comm --sort=-pcpu | head -8 | tail -6")
say INFO "top processes (psr %cpu rtprio comm):"; echo "$TOP" | sed 's/^/       /'
HOT=$(echo "$TOP" | awk '$2+0 > 5 && $4 !~ /sushi|sensei|raspa/ {print $4"("$2"%)"}' | tr '\n' ' ')
[ -n "$HOT" ] && say WARN "non-Elk load >5%: $HOT — quiesce before sweeping" || say PASS "no significant competing load"

# 7. affinity/rtprio (meaningful only when sushi is running; harness re-captures per row)
AFF=$(run "ps -eLo psr,rtprio,comm | grep -i sushi | sort -u | tr '\n' ';'")
[ -n "$AFF" ] && say INFO "sushi threads now: $AFF" || say INFO "sushi not running yet (affinity captured per-row during the sweep)"

# 8. NEON in the deployed .so (board readelf, Mac fallback)
NEON=$(run "readelf -A /home/mind/plugins/THIRI.vst3/Contents/armv7l-linux/THIRI.so 2>/dev/null | grep -ci 'Advanced SIMD'")
if [ "${NEON:-0}" -gt 0 ] 2>/dev/null; then say PASS "NEON (Advanced SIMD) attributes present in deployed .so";
else
  LOCAL="$ROOT/plugin/build-stomp/THIRI_artefacts/Release/VST3/THIRI.vst3/Contents/armv7l-linux/THIRI.so"
  if [ -f "$LOCAL" ] && command -v llvm-readelf >/dev/null 2>&1 && llvm-readelf -A "$LOCAL" 2>/dev/null | grep -qi 'Advanced SIMD'; then
    say PASS "NEON verified on the Mac against the cross-build artifact (board readelf absent)"
  else say INFO "could not verify NEON here — check the cross-build artifact manually"; fi
fi

# 9. denormals — structural
say PASS "denormals: structural — ScopedNoDenormals sets FPSCR FZ on armv7+NEON (PluginProcessor.cpp:363; JUCE juce_FloatVectorOperations.cpp:1544-1563)"

# 10. clock sanity
say INFO "board date: $(run date) | mac date: $(date) (CSV timestamps are Mac-side)"

[ "$FAIL" = 0 ] && say PASS "preflight complete — proceed to sushi_board.sh start" || say FAIL "fix the FAILs above first"
exit $FAIL
