"""Chiave d'accesso locale: solo il browser aperto dall'app può usare l'interfaccia.

Il server ascolta solo su 127.0.0.1, ma su un computer condiviso anche altri utenti o programmi
possono collegarsi a 127.0.0.1. Per questo ogni avvio genera una chiave segreta:

- il launcher apre il browser su `/?c=<codice monouso>`; il server consuma il codice e consegna
  la chiave in un cookie HttpOnly + SameSite=Strict (il codice nella barra degli indirizzi non vale
  più nulla, e altri siti non ricevono il cookie);
- ogni chiamata a /api/* richiede la chiave (cookie, oppure header X-Banana-Token per il launcher);
- la chiave sta anche in ~/.banana-split/token (permessi 0600), così un secondo avvio può chiedere
  un nuovo codice all'app già aperta;
- prima di fidarsi di un server già in ascolto, il launcher gli chiede di dimostrare di conoscere la
  chiave (HMAC su un numero casuale) senza mai inviargliela: un falso server non può rispondere.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs

COOKIE = "bs_token"
HEADER = b"x-banana-token"
CODE_TTL = 120  # secondi di validità di un codice monouso
OPEN_PATHS = {"/api/hello"}  # unico endpoint senza chiave: dimostra solo l'identità


def new_token() -> str:
    return secrets.token_urlsafe(32)


def proof(token: str, nonce: str) -> str:
    return hmac.new(token.encode(), nonce.encode(), hashlib.sha256).hexdigest()


def write_token_file(path: Path, token: str) -> None:
    """Scrive la chiave leggibile solo dall'utente (0600), in modo atomico."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(token)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def read_token_file(path: Path) -> str | None:
    try:
        return path.read_text().strip() or None
    except OSError:
        return None


class LocalAuth:
    def __init__(self, token: str):
        self.token = token
        self._codes: dict[str, float] = {}
        self._lock = threading.Lock()

    def check(self, value: str | None) -> bool:
        return bool(value) and hmac.compare_digest(value, self.token)

    def new_code(self) -> str:
        code = secrets.token_urlsafe(18)
        with self._lock:
            now = time.time()
            self._codes = {c: t for c, t in self._codes.items() if t > now}
            self._codes[code] = now + CODE_TTL
        return code

    def consume(self, code: str | None) -> bool:
        if not code:
            return False
        with self._lock:
            expires = self._codes.pop(code, 0)
        return expires > time.time()


def _cookies(headers: dict) -> dict:
    out = {}
    for part in headers.get(b"cookie", b"").decode("latin-1").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


class AuthMiddleware:
    def __init__(self, app, auth: LocalAuth):
        self.app = app
        self.auth = auth

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        headers = dict(scope.get("headers") or [])

        # apertura dal launcher: codice monouso → cookie con la chiave, poi la pagina pulita
        if path == "/" and scope.get("method") == "GET":
            code = parse_qs(scope.get("query_string", b"").decode()).get("c", [None])[0]
            if code is not None:
                if self.auth.consume(code):
                    cookie = f"{COOKIE}={self.auth.token}; Path=/; HttpOnly; SameSite=Strict"
                    await send({"type": "http.response.start", "status": 303, "headers": [
                        (b"location", b"/"), (b"set-cookie", cookie.encode()),
                        (b"cache-control", b"no-store"), (b"content-length", b"0")]})
                    await send({"type": "http.response.body", "body": b""})
                    return
                # codice scaduto o già usato: la pagina si apre ma senza chiave non può fare nulla

        if path.startswith("/api/") and path not in OPEN_PATHS:
            given = headers.get(HEADER, b"").decode("latin-1") or _cookies(headers).get(COOKIE)
            if not self.auth.check(given):
                body = json.dumps({"detail": "Accesso non autorizzato: apri Banana Split dalla sua icona."}).encode()
                await send({"type": "http.response.start", "status": 401, "headers": [
                    (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)
