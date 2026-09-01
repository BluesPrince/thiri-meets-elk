---
name: elk-serial-console
description: Drive an Elk board over its USB-to-UART serial console when the network is down, unconfigured, or you need a session that outlives your shell — running commands, moving files without scp, and working inside a BusyBox userland that quietly rejects common GNU flags. Use whenever a board is unreachable over SSH, whenever bringing one up for the first time, whenever background processes die the moment you log out, whenever you need to change network config without a network, and whenever a command that works on your Mac fails strangely on the board.
---

# Working over the serial console

The console is the fallback that always works — and for one job it is not a fallback but the
correct tool.

**Serial logins persist; SSH logins do not.** `systemd-logind` reaps the user scope when an
SSH session ends, taking any background process with it. `setsid` and `nohup` were both
observed *not* to save a daemon started over SSH. For a rig that must stay up while you walk
away, start it from the serial console — or install it as a systemd service.

---

## The helper

`scripts/elk-serial.py` — stdlib only, no pyserial.

```bash
python3 scripts/elk-serial.py ports                    # find the device
python3 scripts/elk-serial.py run 'uname -a'           # one command, clean output
python3 scripts/elk-serial.py run - < script.sh        # a whole script from stdin
python3 scripts/elk-serial.py push local.json /home/mind/app/local.json
```

On this Mac the board's adapter appears as `/dev/cu.URT1` and `/dev/cu.URT2`; the second is
usually the console. 115200 8N1, no flow control.

*Status: the script is syntax-checked and its port discovery is verified. The transport
recipe it implements — marker-delimited commands, base64-over-UART with a python3 decode —
is what worked in this project, but this implementation has not been run end to end against
a live board. Treat the first session with it as a test.*

### Why it works the way it does

**Marker-delimited output.** A serial console gives you a byte stream containing your typed
command echoed back, the output, a prompt, and any kernel message that felt like arriving.
Wrapping each command in a unique begin/end marker is the only reliable way to know which
bytes are the answer. Exit status rides on the end marker.

**base64 for file transfer.** There is no scp when there is no network, and a UART is not
dependably 8-bit clean. base64 the file, append it in small chunks, decode on the far side.
Chunk it — a UART has a small buffer and no flow control you should trust — and **verify the
size afterwards**. A transfer is not finished until the far side agrees about the byte count.

**`python3`, not `base64`.** BusyBox has no `base64` binary. It does have python3.

---

## BusyBox reality

The userland is BusyBox. Commands you have typed for twenty years behave differently, and
the failures look like your logic is wrong rather than your flags.

| you typed | what happens | use instead |
| --- | --- | --- |
| `head -5 file` | invalid option | `head -n 5 file` |
| `base64 file` | not found | `python3 -c "import base64,..."` |
| `tail -f` with GNU flags | subset supported | keep it to the basics |

Assume any flag beyond the most common form is absent. When something fails inexplicably,
test the flag on its own before doubting the surrounding script.

---

## Board facts that shape what you can do here

- **The clock is wrong.** No RTC; it reports 2025. Do not use mtimes to decide what is newer
  — hash instead. This matters most when you are moving files by hand and cannot remember
  which copy is current.
- **Root is nearly full** (~83% on ours) and `/home` is on it. Do not push large files over
  the console; check free space first.
- **Shut audio down with SIGINT only.** SIGTERM or SIGKILL wedges the `audio_evl` driver and
  the next launch hangs until a power cycle. This applies just as much to a process you
  started from the console as one started any other way — and `kill 0` in a trap handler is
  the usual way people hit it by accident.

---

## When to stop using serial and get the network back

Serial is slow — a few hundred bytes per chunk with an acknowledgement round trip. Moving a
plugin binary over it is painful. The Stomp's second USB-C port is a USB gadget port that
brings up Ethernet-over-USB with no dongle (board `10.66.0.2`, host `10.66.0.1`). Getting
that up is usually the first thing worth doing *from* the console, after which `scp` and
`ssh` are available again for everything except the persistence problem above.
