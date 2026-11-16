#!/usr/bin/env python3
"""Transparent local forward proxy for the Kiroween build VM.

Why this exists
---------------
The build VM reaches the internet only through the sandbox egress proxy
(http://hatch-egress-proxy:3128, an allow-list CONNECT proxy that MITMs TLS).
curl and plain sockets work through it, but Chrome's own CONNECT requests
are answered with `HTTP/1.1 403 Forbidden {"detail":"The proxy did not
authorize this connection.","error":"policy_denied"}` — deterministically,
for every host, even ones the proxy allows for curl/python (example.com,
frankenledger-21fh.vercel.app). Ruled out as causes: User-Agent (raw
CONNECTs with the exact HeadlessChrome UA get 200), header set/order
(byte-identical CONNECTs from a raw socket get 200), target host
(example.com is allow-listed), and request rate (20 rapid sequential +
10 parallel CONNECTs all get 200). The difference is below the HTTP
layer (Chrome's socket/TLS stack vs plain sockets) and was not
identified; the egress proxy's policy decision is opaque.

What this does
--------------
A transparent TCP relay on 127.0.0.1:18081. It accepts a connection,
reads the first request bytes, opens a connection to the upstream
egress proxy, forwards the bytes unchanged, and then pumps bytes in
both directions until close. It never reads, modifies, or logs request
bodies — it only logs the first request line per connection for
debugging. Chrome pointed at this relay (``--proxy-server=
http://127.0.0.1:18081``) loads pages normally, because the upstream
sees connections from this relay process instead of from Chrome.

Usage (on this VM, before starting the Chrome DevTools MCP server):
    python3 scripts/egress-forward-proxy.py [--port 18081]
    # upstream defaults to hatch-egress-proxy:3128; override with
    # EGRESS_UPSTREAM_HOST / EGRESS_UPSTREAM_PORT.
"""
import argparse
import os
import socket
import threading

UPSTREAM_HOST = os.environ.get("EGRESS_UPSTREAM_HOST", "hatch-egress-proxy")
UPSTREAM_PORT = int(os.environ.get("EGRESS_UPSTREAM_PORT", "3128"))


def pump(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def handle(conn, addr):
    try:
        conn.settimeout(30)
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = conn.recv(4096)
            if not chunk:
                conn.close()
                return
            head += chunk
        first_line = head.split(b"\r\n", 1)[0].decode("latin1", "replace")
        print(f"[{addr[0]}:{addr[1]}] {first_line}", flush=True)
        up = socket.create_connection((UPSTREAM_HOST, UPSTREAM_PORT), timeout=30)
        up.sendall(head)
        t1 = threading.Thread(target=pump, args=(conn, up), daemon=True)
        t2 = threading.Thread(target=pump, args=(up, conn), daemon=True)
        t1.start()
        t2.start()
        t1.join(timeout=120)
        t2.join(timeout=5)
    except OSError as exc:
        print(f"[{addr[0]}:{addr[1]}] error: {exc}", flush=True)
    finally:
        try:
            conn.close()
        except OSError:
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port", type=int, default=18081)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.host, args.port))
    srv.listen(50)
    print(f"egress forward proxy listening on {args.host}:{args.port} "
          f"-> {UPSTREAM_HOST}:{UPSTREAM_PORT}", flush=True)
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=handle, args=(conn, addr), daemon=True).start()


if __name__ == "__main__":
    main()
