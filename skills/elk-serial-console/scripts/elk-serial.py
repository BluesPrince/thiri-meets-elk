#!/usr/bin/env python3
"""Drive an Elk board over its USB-to-UART console. No dependencies beyond stdlib.

Why this exists: when the board's network is down, misconfigured, or you are bringing
it up for the first time, the serial console is the only way in. It is also the only
login that SURVIVES you walking away -- systemd-logind reaps the user scope when an
ssh session ends, taking any background process with it.

    elk-serial.py ports                       # list candidate devices
    elk-serial.py run  'uname -a'             # run one command, print its output
    elk-serial.py run  -              # ...or read the script from stdin
    elk-serial.py push local.json /home/mind/app/local.json
    elk-serial.py login <user>                # answer a waiting login prompt

The board is a BusyBox userland. It has python3 but NOT base64(1), and its head/tail
reject the bare `-5` form -- see the skill for the full list.
"""
import argparse, base64, glob, os, random, string, sys, termios, time

BAUD = termios.B115200
DEFAULT_GLOBS = ["/dev/cu.URT*", "/dev/cu.usbserial*", "/dev/cu.usbmodem*", "/dev/ttyUSB*"]


def candidates():
    out = []
    for g in DEFAULT_GLOBS:
        out.extend(sorted(glob.glob(g)))
    return out


def pick(dev):
    if dev:
        return dev
    c = candidates()
    if not c:
        sys.exit("no serial device found. Tried: " + " ".join(DEFAULT_GLOBS))
    return c[0]


class Console:
    def __init__(self, dev, debug=False):
        self.dev, self.debug = dev, debug
        self.fd = os.open(dev, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        a = termios.tcgetattr(self.fd)
        # raw 8N1, no flow control, no echo, non-blocking reads
        a[0] = a[1] = a[3] = 0                       # iflag oflag lflag
        a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        a[4] = a[5] = BAUD                           # ispeed ospeed
        a[6] = list(a[6])
        a[6][termios.VMIN] = 0
        a[6][termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, a)
        termios.tcflush(self.fd, termios.TCIOFLUSH)

    def close(self):
        os.close(self.fd)

    def write(self, s):
        data = s.encode() if isinstance(s, str) else s
        while data:
            try:
                n = os.write(self.fd, data[:256])
                data = data[n:]
            except BlockingIOError:
                n = 0
            time.sleep(0.01)          # UART has no flow control worth trusting

    def read_until(self, marker, timeout):
        """Accumulate until marker appears or timeout. Returns everything read."""
        buf, deadline = "", time.time() + timeout
        while time.time() < deadline:
            try:
                chunk = os.read(self.fd, 4096)
            except (BlockingIOError, OSError):
                chunk = b""
            if chunk:
                buf += chunk.decode("utf-8", "replace")
                if marker in buf:
                    return buf
            else:
                time.sleep(0.02)
        return buf

    def run(self, cmd, timeout=30):
        """Run cmd, return (stdout_text, exit_status). Markers delimit the output so
        shell echo and the prompt never contaminate it."""
        nonce = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        beg, end = f"__B{nonce}__", f"__E{nonce}__"
        termios.tcflush(self.fd, termios.TCIFLUSH)
        self.write(f"\n echo {beg}; {cmd}\n echo {end}:$?\n")
        raw = self.read_until(end + ":", timeout)
        if self.debug:
            sys.stderr.write(raw)
        if beg not in raw or end + ":" not in raw:
            return raw, None                        # timed out; hand back what we saw
        body = raw.split(beg, 1)[1].split(end + ":", 1)[0]
        tail = raw.split(end + ":", 1)[1]
        status = None
        for ch in tail.strip():
            if ch.isdigit():
                status = int(ch) if status is None else status * 10 + int(ch)
            elif status is not None:
                break
        # drop the echoed command line the shell printed back at us
        lines = [l for l in body.splitlines() if not l.strip().startswith("echo " + end)]
        return "\n".join(lines).strip("\r\n"), status

    def push(self, local, remote, chunk=384):
        """Copy a local file to the board. base64 over the wire because a UART is not
        8-bit clean in practice; decoded with python3 because BusyBox has no base64."""
        data = open(local, "rb").read()
        b64 = base64.b64encode(data).decode()
        tmp = "/tmp/_ser_xfer.b64"
        out, _ = self.run(f": > {tmp}")
        sent = 0
        for i in range(0, len(b64), chunk):
            piece = b64[i:i + chunk]
            _, st = self.run(f"printf '%s' '{piece}' >> {tmp}", timeout=20)
            if st not in (0, None):
                sys.exit(f"chunk at byte {i} failed (status {st})")
            sent += len(piece)
            sys.stderr.write(f"\r  {sent}/{len(b64)} b64 chars")
        sys.stderr.write("\n")
        cmd = (f"python3 -c \"import base64,sys;"
               f"open('{remote}','wb').write(base64.b64decode(open('{tmp}').read()))\" "
               f"&& rm -f {tmp} && echo OK")
        out, st = self.run(cmd, timeout=60)
        if "OK" not in out:
            sys.exit(f"decode failed: {out}")
        # verify -- the transfer is not done until the far side agrees
        want = len(data)
        got, _ = self.run(f"wc -c < {remote}")
        if got.strip().split()[-1:] != [str(want)]:
            sys.exit(f"size mismatch: local {want}, remote '{got.strip()}'")
        print(f"pushed {local} -> {remote} ({want} bytes, size verified)")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dev", help="serial device (default: first match)")
    p.add_argument("--debug", action="store_true", help="dump raw console traffic to stderr")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ports")
    r = sub.add_parser("run");   r.add_argument("command"); r.add_argument("--timeout", type=int, default=30)
    u = sub.add_parser("push");  u.add_argument("local");   u.add_argument("remote")
    l = sub.add_parser("login"); l.add_argument("user")
    a = p.parse_args()

    if a.cmd == "ports":
        c = candidates()
        print("\n".join(c) if c else "none found")
        return

    con = Console(pick(a.dev), a.debug)
    try:
        if a.cmd == "run":
            cmd = sys.stdin.read() if a.command == "-" else a.command
            out, st = con.run(cmd, a.timeout)
            print(out)
            if st is None:
                sys.exit("!! no end marker -- board may be at a login prompt, or busy")
            sys.exit(st)
        elif a.cmd == "push":
            con.push(a.local, a.remote)
        elif a.cmd == "login":
            con.write("\n")
            time.sleep(0.5)
            con.write(a.user + "\n")
            print("username sent. Type the password yourself in a terminal on this "
                  "device -- this script deliberately does not handle passwords.")
    finally:
        con.close()


if __name__ == "__main__":
    main()
