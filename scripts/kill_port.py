"""Kill all processes listening on a given port (Windows)."""
import os
import re
import subprocess
import sys


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "8000"
    out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
    pids: set[str] = set()
    for line in out.splitlines():
        if f":{port} " in line and "LISTEN" in line:
            m = re.search(r"(\d+)\s*$", line)
            if m:
                pids.add(m.group(1))
    if not pids:
        print(f"No process listening on port {port}")
        return
    for pid in pids:
        print(f"Killing PID {pid}")
        try:
            os.kill(int(pid), 9)
        except OSError as e:
            print(f"  Failed: {e}")


if __name__ == "__main__":
    main()
