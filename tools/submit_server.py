#!/usr/bin/env python3
"""The reference server for in-app pack submission.

This is not the production server. It is the contract, written as something that runs, so the
Android client can be tested end to end on an emulator before anybody pays for hosting — and so
whoever writes the real one has an exact specification rather than a description.

    python3 submit_server.py            # listens on 8787
    python3 submit_server.py --port 9000

The emulator reaches the host machine at 10.0.2.2, which is what the debug build's
SUBMIT_BASE_URL points at.

Three endpoints:

    POST /account/code    {"email","name"}          -> 204, and prints the code to this console
    POST /account/verify  {"email","code"}          -> {"token"}
    POST /packs           multipart, Bearer token   -> {"id"}

Everything lands in ./submissions/ and nothing is published. A refusal is 4xx with {"error"} and
the client shows that text, so the wording here is the wording a person reads.

WHAT THE REAL SERVER MUST ADD, none of which is here:

  * Actually sending the email. This prints the code instead.
  * Durable storage for accounts, tokens and submissions; this forgets everything on restart.
  * Rate limits: codes per address per hour, verify attempts per code, submissions per account
    per day. Without these the code is brute-forceable in a few thousand tries.
  * Hostile-zip handling. PackArchive.kt on the Android side is the specification: a fixed
    whitelist of entry names, never used as filesystem paths; sizes counted while streaming
    rather than trusted from the header; caps on entry count, total bytes, per-file bytes and
    JSON nesting depth; and a decompression-ratio cap, because an unauthenticated upload
    endpoint is where a zip bomb arrives first. This file does the name and size checks only.
  * Deletion: an account must be able to remove itself and its submissions.
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import shutil
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
INBOX = HERE / "submissions"

# Matches PackDownloader.MAX_BYTES. A pack larger than this can never be downloaded by the app,
# so accepting one would publish something nobody can install.
MAX_UPLOAD = 8 * 1024 * 1024

# Matches PackArchive on the Android side.
MAX_ENTRIES = 40
ALLOWED = re.compile(r"^(manifest\.json|tray\.png|stickers/[0-9a-zA-Z_.-]+)$")

codes: dict[str, str] = {}
names: dict[str, str] = {}
tokens: dict[str, str] = {}


def normalise(email: str) -> str:
    """Must agree with AccountStore.normalise on the client, or the two disagree about identity."""
    email = email.strip().lower()
    if "@" not in email:
        return email
    local, _, domain = email.rpartition("@")
    local = local.split("+", 1)[0]
    if domain in ("gmail.com", "googlemail.com"):
        local = local.replace(".", "")
    return f"{local}@{domain}"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter console
        print(f"  {fmt % args}")

    def _send(self, status: int, payload: dict | None = None) -> None:
        body = json.dumps(payload).encode() if payload is not None else b""
        self.send_response(status)
        if body:
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _refuse(self, status: int, message: str) -> None:
        self._send(status, {"error": message})

    def _json_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 64 * 1024:
            return None
        try:
            return json.loads(self.rfile.read(length))
        except (ValueError, OSError):
            return None

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/account/code":
            return self.account_code()
        if self.path == "/account/verify":
            return self.account_verify()
        if self.path == "/packs":
            return self.packs()
        self._refuse(404, "No such thing here.")

    def account_code(self) -> None:
        body = self._json_body()
        if not body or not body.get("email") or not body.get("name"):
            return self._refuse(400, "A name and an email are needed.")
        email = normalise(str(body["email"]))
        code = f"{secrets.randbelow(1_000_000):06d}"
        codes[email] = code
        names[email] = str(body["name"])[:60]
        print(f"\n  *** code for {email}: {code} ***\n")
        self._send(204)

    def account_verify(self) -> None:
        body = self._json_body()
        if not body:
            return self._refuse(400, "That did not look right.")
        email = normalise(str(body.get("email", "")))
        code = str(body.get("code", ""))
        if not code or codes.get(email) != code:
            return self._refuse(401, "That code does not match. Check it and try again.")
        del codes[email]
        token = secrets.token_urlsafe(24)
        tokens[token] = email
        self._send(200, {"token": token})

    def packs(self) -> None:
        auth = self.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        email = tokens.get(token)
        if not email:
            return self._refuse(401, "Sign in again to send this.")

        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return self._refuse(400, "Nothing arrived.")
        if length > MAX_UPLOAD + 64 * 1024:
            return self._refuse(413, "That pack is too big to send.")

        raw = self.rfile.read(length)
        ctype = self.headers.get("Content-Type", "")
        if "boundary=" not in ctype:
            return self._refuse(400, "That did not arrive as a pack.")
        boundary = ("--" + ctype.split("boundary=", 1)[1].strip()).encode()

        fields: dict[str, str] = {}
        pack: bytes | None = None
        # Exact, not approximate. Each part is "<headers>\r\n\r\n<payload>\r\n" and the payload
        # is a zip: trimming a trailing set of characters instead of exactly that one CRLF eats
        # bytes off the end of the central directory and the archive stops opening.
        pieces = raw.split(boundary)
        for piece in pieces[1:-1]:
            head, sep, data = piece.partition(b"\r\n\r\n")
            if not sep or b'name="' not in head:
                continue
            name = head.split(b'name="', 1)[1].split(b'"', 1)[0].decode()
            if data.endswith(b"\r\n"):
                data = data[:-2]
            if name == "pack":
                pack = data
            else:
                fields[name] = data.decode("utf-8", "replace")

        if pack is None or not pack:
            return self._refuse(400, "The pack was missing.")
        if len(pack) > MAX_UPLOAD:
            return self._refuse(413, "That pack is too big to send.")
        if not fields.get("credit", "").strip():
            return self._refuse(400, "A credit name is needed.")

        INBOX.mkdir(exist_ok=True)
        pending = INBOX / f"{secrets.token_hex(6)}.peel"
        pending.write_bytes(pack)

        problem = inspect(pending)
        if problem:
            print(f"  refused {pending.name}: {problem}")
            pending.unlink(missing_ok=True)
            return self._refuse(400, problem)

        (pending.with_suffix(".json")).write_text(
            json.dumps(
                {
                    "from": email,
                    "name": names.get(email, ""),
                    "credit": fields.get("credit", "").strip(),
                    "note": fields.get("note", "").strip(),
                    "bytes": len(pack),
                    "state": "waiting for review",
                },
                indent=2,
            )
        )
        print(f"  received {pending.name} from {email} ({len(pack)} bytes)")
        self._send(200, {"id": pending.stem})


def inspect(path: Path) -> str | None:
    """A first look at the archive. The real server needs considerably more than this."""
    try:
        with zipfile.ZipFile(path) as z:
            entries = z.namelist()
            if len(entries) > MAX_ENTRIES:
                return "That does not look like a Peel pack."
            for name in entries:
                if not ALLOWED.match(name):
                    return "That does not look like a Peel pack."
            if "manifest.json" not in entries:
                return "That does not look like a Peel pack."
            manifest = json.loads(z.read("manifest.json"))
            if manifest.get("format") != "peel-pack":
                return "That does not look like a Peel pack."
            stickers = manifest.get("stickers") or []
            if not 3 <= len(stickers) <= 30:
                return "A pack needs between 3 and 30 stickers."
    except (zipfile.BadZipFile, ValueError, KeyError, OSError):
        return "That file could not be opened."
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    INBOX.mkdir(exist_ok=True)
    print(f"Peel submission reference server on http://0.0.0.0:{args.port}")
    print(f"  emulator reaches this at http://10.0.2.2:{args.port}")
    print(f"  submissions land in {INBOX}")
    print("  codes are printed here instead of emailed\n")
    HTTPServer(("0.0.0.0", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
