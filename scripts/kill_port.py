"""Kill all processes bound to a given port (Windows).

Uses taskkill /F /T to kill entire process trees, which handles
uvicorn parent+child process pairs that os.kill() may miss.
"""
import re
import subprocess
import sys


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "8000"
    out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
    pids: set[str] = set()
    for line in out.splitlines():
        # Match any TCP line with our port (LISTEN, ESTABLISHED, TIME_WAIT, etc.)
        if f":{port} " in line and "TCP" in line:
            m = re.search(r"(\d+)\s*$", line)
            if m and m.group(1) != "0":
                pids.add(m.group(1))
    if not pids:
        print(f"No process on port {port}")
        return
    for pid in pids:
        print(f"Killing PID {pid} (with tree)...")
        r = subprocess.run(
            ["taskkill", "/F", "/T", "/PID", pid],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            print(f"  OK: {r.stdout.strip()}")
        else:
            print(f"  {r.stderr.strip() or r.stdout.strip()}")


if __name__ == "__main__":
    main()
