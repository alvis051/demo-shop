"""Run the shop: `python -m app [--host H] [--port N]`.

Port 0 (the default outside Render) picks a free port and prints it, so a test
harness can start several copies side by side.
"""

import argparse
import os
import socket

import uvicorn

from app.config import get_settings
from app.main import create_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "0")))
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET6 if ":" in args.host else socket.AF_INET)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.host, args.port))
    sock.listen(128)  # connections queue until uvicorn starts accepting
    port = sock.getsockname()[1]

    settings = get_settings()
    app = create_app(settings)
    # Printed once the DB is ready, so a harness can start using the URL straight away.
    app.state.ready_message = f"demo-shop listening on http://{args.host}:{port}"
    config = uvicorn.Config(app, proxy_headers=True, forwarded_allow_ips="*", access_log=settings.env != "test")
    uvicorn.Server(config).run(sockets=[sock])


if __name__ == "__main__":
    main()
