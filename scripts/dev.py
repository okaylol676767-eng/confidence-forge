"""Run the FastAPI backend (uvicorn :8000) and the Next.js frontend (:3000) together.

Usage:
    .venv/Scripts/python scripts/dev.py            # from the repo root

- Waits until both servers answer before reporting ready.
- Streams both logs with [api]/[web] prefixes.
- Ctrl+C shuts both down (kills the whole process tree on Windows).
"""
import atexit
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_PORT = int(os.environ.get("API_PORT", "8000"))
WEB_PORT = int(os.environ.get("WEB_PORT", "3000"))
API_URL = f"http://127.0.0.1:{API_PORT}/health"
WEB_URL = f"http://127.0.0.1:{WEB_PORT}"


def popen(args: list[str], cwd: Path) -> subprocess.Popen:
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    return subprocess.Popen(
        args,
        cwd=str(cwd),
        stdout=sys.stdout,
        stderr=subprocess.STDOUT,
        **kwargs,
    )


def kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        else:
            proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def wait_ready(url: str, name: str, timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status < 500:
                    print(f"[dev] {name} is up at {url}")
                    return True
        except urllib.error.HTTPError:
            # Got an HTTP response at all -> server is up (e.g. 404 on /health).
            print(f"[dev] {name} is up at {url}")
            return True
        except Exception:
            time.sleep(0.5)
    print(f"[dev] ERROR: {name} did not become ready within {timeout}s", file=sys.stderr)
    return False


def npm_command() -> list[str]:
    """Resolve npm's full path (on Windows it is npm.cmd, not a .exe)."""
    candidates = ("npm.cmd", "npm") if os.name == "nt" else ("npm",)
    for name in candidates:
        found = shutil.which(name)
        if found:
            return [found]
    raise FileNotFoundError("npm not found on PATH — install Node.js first")


def main() -> int:
    python = sys.executable
    print("[dev] starting FastAPI backend on port", API_PORT)
    api = popen(
        [python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
         "--port", str(API_PORT)],
        cwd=ROOT,
    )
    print("[dev] starting Next.js frontend on port", WEB_PORT)
    web = popen(
        [*npm_command(), "run", "dev", "--", "--port", str(WEB_PORT)],
        cwd=ROOT / "frontend",
    )

    atexit.register(kill_tree, api)
    atexit.register(kill_tree, web)

    ok = wait_ready(API_URL, "backend") and wait_ready(WEB_URL, "frontend")
    if ok:
        print(f"[dev] ready -> open http://127.0.0.1:{WEB_PORT} (API proxied from the same origin)")

    try:
        # Stay alive streaming output; exit if either child dies.
        while True:
            if api.poll() is not None or web.poll() is not None:
                print("[dev] a child process exited — shutting down")
                return api.returncode or web.returncode or 0
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[dev] shutting down…")
        return 0
    finally:
        kill_tree(web)
        kill_tree(api)


if __name__ == "__main__":
    sys.exit(main())
