"""ClipAvenue CLI.

    python -m clipavenue open          # launch dashboard (start server + open browser)
    python -m clipavenue serve --port N  # run the server in the foreground
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser

from clipavenue import DEFAULT_PORT


def _port() -> int:
    try:
        return int(os.environ.get("CLIPAVENUE_PORT", DEFAULT_PORT))
    except ValueError:
        return DEFAULT_PORT


def _server_alive(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def _spawn_server(port: int) -> None:
    """Start the server as a detached background process."""
    cmd = [sys.executable, "-m", "clipavenue", "serve", "--port", str(port)]
    kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        )
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)


def cmd_open() -> int:
    port = _port()
    if not _server_alive(port):
        try:
            _spawn_server(port)
        except Exception as exc:
            print(f"clipavenue: could not start server ({exc}) — continuing without the board")
            return 1
        deadline = time.time() + 15
        while time.time() < deadline:
            if _server_alive(port):
                break
            time.sleep(0.4)
        else:
            print("clipavenue: server did not come up in time — continuing without the board")
            return 1
    url = f"http://127.0.0.1:{port}/"
    try:
        webbrowser.open(url)
    except Exception:
        pass
    print(f"clipavenue: {url}")
    return 0


def cmd_serve(port: int) -> int:
    import uvicorn
    uvicorn.run("clipavenue.server:app", host="127.0.0.1", port=port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="clipavenue", description=__doc__)
    sub = parser.add_subparsers(dest="command")

    p_open = sub.add_parser("open", help="open the dashboard in the browser (starts server if needed)")
    p_serve = sub.add_parser("serve", help="run the ClipAvenue server in the foreground")
    p_serve.add_argument("--port", type=int, default=_port())
    p_worker = sub.add_parser("worker", help="run the clip agent worker in the foreground (for debugging)")
    p_worker.add_argument("--poll-interval", type=float, default=5.0, help="seconds between queue polls")

    args = parser.parse_args(argv)
    if args.command == "open":
        return cmd_open()
    if args.command == "serve":
        return cmd_serve(args.port)
    if args.command == "worker":
        from clipavenue.worker import serve_forever
        serve_forever(poll_interval=args.poll_interval)
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())