#!/usr/bin/env python3
"""Interface web locale pour le dock RayCue 128K.

  python3 gui/app.py            # ouvre l'interface dans le navigateur
  python3 gui/app.py --no-browser --port 8128

Le navigateur ne parle qu'à ce serveur (127.0.0.1) ; c'est lui qui envoie les paquets UDP au dock via send.py.
"""
import argparse, base64, io, json, socket, sys, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
import send  # noqa: E402

WIFI_SSID, WIFI_PASSWORD = "Raycue 128K", "12345678"
DOCK = ("192.168.0.1", 2327)
LOCK = threading.Lock()  # ponytail: un seul échange avec le dock à la fois, le protocole n'est pas concurrent


def on_dock_network():
    """Vrai si la machine a une adresse dans le même /24 que le dock (aucun paquet envoyé).
    ponytail: un réseau domestique en 192.168.0.x passe aussi ; un vrai échec d'envoi le détecte ensuite."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(DOCK)
            return s.getsockname()[0].rsplit(".", 1)[0] == DOCK[0].rsplit(".", 1)[0]
    except OSError:
        return False


def with_dock(fn):
    """fn(dock) -> bool, exécuté sous verrou. Renvoie {"ok", "log"}."""
    lines = []
    with LOCK:
        ok = fn(send.Dock(*DOCK, log=lines.append))
    return {"ok": ok, "log": "".join(line + "\n" for line in lines)}


def status(q, body):
    return {"reachable": on_dock_network(), "ssid": WIFI_SSID, "password": WIFI_PASSWORD, "host": DOCK[0], "slots": send.SLOTS}


def image(q, body):
    """Corps = image 480x320 préparée par la page. slot=N, mode=fixed|loop (commande de mode avant), quality."""
    slot, mode = int(q.get("slot", 0)), q.get("mode")
    if not 0 <= slot < send.SLOTS:
        raise ValueError(f"slot entre 0 et {send.SLOTS - 1}")
    jpeg = send.to_jpeg(io.BytesIO(body), "stretch", quality=int(q.get("quality", 90)))
    r = with_dock(lambda d: (not mode or d.mode(mode)) and d.send(jpeg, slot))
    return {**r, "jpeg": base64.b64encode(jpeg).decode()}


def mode(q, body):
    """Bascule seulement le mode du dock (commande 50/51), sans renvoyer d'image."""
    if (m := q.get("mode")) not in ("fixed", "loop"):
        raise ValueError("mode = fixed ou loop")
    return with_dock(lambda d: d.mode(m))


def clear(q, body):
    slots = range(send.SLOTS) if q.get("slot", "all") == "all" else [int(q["slot"])]
    return with_dock(lambda d: all([d.clear(n) for n in slots]))


def decode(q, body):
    """Image que le navigateur ne sait pas lire (HEIC, TIFF…) -> PNG, EXIF appliqué, 2400 px max."""
    im = send.load(io.BytesIO(body))
    im.thumbnail((2400, 2400))
    buf = io.BytesIO()
    im.convert("RGBA").save(buf, "PNG")
    return buf.getvalue()


ROUTES = {("GET", "/api/status"): status, ("POST", "/api/image"): image,
          ("POST", "/api/mode"): mode, ("POST", "/api/clear"): clear, ("POST", "/api/decode"): decode}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def dispatch(self, method):
        url = urlparse(self.path)
        if method == "GET" and url.path == "/":
            return self.reply(200, (ROOT / "index.html").read_bytes(), "text/html; charset=utf-8")
        route = ROUTES.get((method, url.path))
        if not route:
            return self.reply(404, {"error": "introuvable"})
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        try:
            res = route({k: v[0] for k, v in parse_qs(url.query).items()}, body)
        except (ValueError, KeyError) as e:
            return self.reply(400, {"ok": False, "error": str(e)})
        self.reply(200, res, "image/png" if isinstance(res, bytes) else "application/json")

    def reply(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    global DOCK
    ap = argparse.ArgumentParser(description="Interface web locale pour le dock RayCue 128K.")
    ap.add_argument("--port", type=int, default=8128, help="port HTTP local (0 = au hasard)")
    ap.add_argument("--no-browser", action="store_true", help="n'ouvre pas le navigateur")
    ap.add_argument("--dock-host", default=DOCK[0], help="adresse du dock")
    ap.add_argument("--dock-port", type=int, default=DOCK[1], help="port UDP du dock")
    a = ap.parse_args()
    DOCK = (a.dock_host, a.dock_port)

    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"Interface RayCue : {url}  (Ctrl+C pour quitter)")
    if not a.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
