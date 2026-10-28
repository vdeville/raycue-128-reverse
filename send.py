#!/usr/bin/env python3
"""Affiche une ou plusieurs images sur le dock RayCue 128K (protocole UDP reversé, voir README).

  python3 send.py photo.heic                      # mode fixe (1 image)
  python3 send.py a.jpg b.png dossier/            # mode loop (diaporama, 9 images max)
  python3 send.py --slot 2 photo.jpg              # remplace juste le slot 2 (garde les autres)
  python3 send.py --clear 2 5                     # vide les slots 2 et 5
  python3 send.py --clear-all a.jpg b.jpg         # efface tout puis envoie
  python3 send.py -m loop                         # bascule seulement le mode (fixed / loop)
  python3 send.py photo.jpg --fit cover           # remplit l'écran en rognant
  python3 send.py dossier/ --save out/            # prépare les JPEG sans rien envoyer
"""
import argparse, io, socket, struct, sys, time
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIF = True
except ImportError:
    HEIF = False

W, H, CHUNK = 480, 320, 2040
SLOTS = 9                # le mode loop est plafonné à 9 images (slots 0..8) par l'app/dock
MAGIC = b"\xa5\x5a"
FIXED, LOOP, ATTR, DATA, LAST, CLEAR = 0x50, 0x51, 0x40, 0x41, 0x42, 0x43
EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".heic", ".heif"}


def frame(cmd, payload=b""):
    """A5 5A | longueur = len(payload)+4 (BE) | cmd | payload | somme des octets & 0xFF"""
    body = MAGIC + struct.pack(">HB", len(payload) + 4, cmd) + bytes(payload)
    return body + bytes([sum(body) & 0xFF])


def load(src):
    """Ouvre une image (chemin ou fichier binaire), orientation EXIF appliquée. ValueError si illisible."""
    try:
        return ImageOps.exif_transpose(Image.open(src))
    except UnidentifiedImageError:
        raise ValueError("image illisible" + ("" if HEIF else " (photo HEIC ? `pip install pillow-heif`)")) from None


def to_jpeg(src, fit="contain", background="black", quality=90, rotate=0):
    """Image quelconque -> JPEG baseline 480x320 ; ratio conservé sauf en stretch, transparence aplatie sur le fond."""
    im = load(src).rotate(-rotate, expand=True)  # sens horaire
    im = Image.alpha_composite(Image.new("RGBA", im.size, background), im.convert("RGBA")).convert("RGB")
    im = {"contain": lambda: ImageOps.pad(im, (W, H), Image.LANCZOS, color=background),
          "cover": lambda: ImageOps.fit(im, (W, H), Image.LANCZOS),
          "stretch": lambda: im.resize((W, H), Image.LANCZOS)}[fit]()
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality)  # ponytail: baseline (pas progressive), c'est ce que sips produisait
    return buf.getvalue()


def collect(inputs):
    files = []
    for p in map(Path, inputs):
        if p.is_dir():
            files += sorted(f for f in p.iterdir() if f.suffix.lower() in EXTS)
        elif p.is_file():
            files.append(p)
        else:
            sys.exit(f"introuvable : {p}")
    return files


class Dock:
    """Échanges avec le dock. Chaque méthode renvoie True si tout a été acquitté ; `log` reçoit le journal."""

    def __init__(self, host="192.168.0.1", port=2327, timeout=1.0, retries=8, delay=0.02, log=print):
        self.addr, self.retries, self.delay, self.log = (host, port), retries, delay, log
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.bind(("0.0.0.0", 0))
        self.s.settimeout(timeout)

    def acks(self, deadline):
        """Itère sur les ACK (cmd, payload) reçus jusqu'à `deadline`."""
        while time.time() < deadline:
            try:
                d, _ = self.s.recvfrom(2048)
            except socket.timeout:
                return
            if d[:2] == MAGIC and len(d) >= 6 and d[5] == 1:
                yield d[4], d[6:]

    def command(self, cmd, payload, tag):
        for _ in range(self.retries):
            self.s.sendto(frame(cmd, payload), self.addr)
            if any(c == cmd for c, _ in self.acks(time.time() + self.s.gettimeout())):
                self.log(f"-> {tag}: OK")
                return True
        self.log(f"!! {tag} sans ACK")
        return False

    def mode(self, mode):
        return self.command(LOOP if mode == "loop" else FIXED, b"", mode.upper())

    def clear(self, slot):
        return self.command(CLEAR, bytes([slot]), f"CLEAR slot{slot}")

    def send(self, img, slot):
        """Envoie un JPEG dans un slot : ATTR, puis données en rafale, retransmises tant que non acquittées."""
        n = -(-len(img) // CHUNK)
        if not self.command(ATTR, len(img).to_bytes(3, "big") + bytes([slot]), f"ATTR slot{slot}"):
            return False
        pending = set(range(n))
        for _ in range(self.retries):
            for i in sorted(pending):
                self.s.sendto(frame(LAST if i == n - 1 else DATA, i.to_bytes(2, "big") + img[i * CHUNK:(i + 1) * CHUNK]), self.addr)
                time.sleep(self.delay)
            for c, p in self.acks(time.time() + 1.0):
                if c == LAST:  # l'ACK 42 ne porte pas de séquence : il ne valide que la dernière trame
                    pending.discard(n - 1)
                elif c == DATA and len(p) >= 2:
                    pending.discard(int.from_bytes(p[:2], "big"))
                if not pending:
                    self.log(f"   image slot{slot}: OK ({len(img)} o, {n} trames)")
                    return True
        self.log(f"   image slot{slot}: incomplet {sorted(pending)}")
        return False


def slot_type(v):
    if not 0 <= (n := int(v)) < SLOTS:
        raise argparse.ArgumentTypeError(f"slot entre 0 et {SLOTS - 1}")
    return n


def main():
    ap = argparse.ArgumentParser(description="Pilote maison pour l'écran du dock RayCue 128K.",
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("images", nargs="*", help="fichiers image et/ou dossiers (triés par nom)")
    ap.add_argument("-m", "--mode", choices=["auto", "fixed", "loop"], default="auto",
                    help="auto = fixed pour 1 image, loop sinon")
    ap.add_argument("-s", "--slot", type=slot_type,
                    help="remplace uniquement ce slot (puis les suivants si plusieurs images), sans commande de mode")
    ap.add_argument("--clear", type=slot_type, nargs="+", default=[], metavar="N", help="vide ces slots (avant envoi éventuel)")
    ap.add_argument("--clear-all", action="store_true", help=f"vide tous les slots 0-{SLOTS - 1} (avant envoi éventuel)")
    ap.add_argument("-f", "--fit", choices=["contain", "cover", "stretch"], default="contain",
                    help="contain = bandes autour, cover = rogne pour remplir, stretch = déforme")
    ap.add_argument("-b", "--background", default="black", help="couleur des bandes / de la transparence (nom ou #rrggbb)")
    ap.add_argument("-r", "--rotate", type=int, choices=[0, 90, 180, 270], default=0,
                    help="rotation horaire supplémentaire (après correction EXIF)")
    ap.add_argument("-q", "--quality", type=int, default=90, help="qualité JPEG (1-95)")
    ap.add_argument("--save", metavar="DIR", help="écrit les JPEG préparés dans DIR et n'envoie rien")
    ap.add_argument("--host", default="192.168.0.1", help="adresse du dock")
    ap.add_argument("--port", type=int, default=2327, help="port UDP du dock")
    ap.add_argument("--timeout", type=float, default=1.0, help="attente d'un ACK (s)")
    ap.add_argument("--retries", type=int, default=8, help="tentatives par commande / passes de retransmission")
    ap.add_argument("--delay", type=float, default=0.02, help="pause entre trames data (s)")
    a = ap.parse_args()

    files = collect(a.images)
    clears = range(SLOTS) if a.clear_all else a.clear
    if not files and not clears and a.mode == "auto":
        ap.error("donne au moins une image (ou --clear N / --clear-all / --mode fixed|loop)")
    if a.slot is not None and a.mode != "auto":
        ap.error("--slot n'envoie pas de commande de mode : incompatible avec --mode")

    if a.slot is not None:
        first, mode, limit = a.slot, None, SLOTS - a.slot
    else:
        first, mode = 0, a.mode if a.mode != "auto" else ("fixed" if len(files) == 1 else "loop")
        limit = 1 if mode == "fixed" else SLOTS
    if len(files) > limit:
        print(f"! {len(files)} images, seulement {limit} slot(s) disponible(s) -> on garde les {limit} premières")
        files = files[:limit]

    imgs = []
    for p in files:
        try:
            imgs.append(to_jpeg(p, a.fit, a.background, a.quality, a.rotate))
        except ValueError as e:
            sys.exit(f"{p} : {e}")
    if a.save:
        out = Path(a.save)
        out.mkdir(parents=True, exist_ok=True)
        for slot, (p, img) in enumerate(zip(files, imgs), first):
            (out / f"{slot}_{p.stem}.jpg").write_bytes(img)
        print(f"{len(imgs)} JPEG écrits dans {out}")
        return

    dock = Dock(a.host, a.port, a.timeout, a.retries, a.delay)
    ok = all([dock.clear(n) for n in clears])
    if imgs or a.mode != "auto":   # --mode seul : bascule le mode sans renvoyer d'image
        if mode:
            print(f"mode {mode.upper()}" + (f" ({len(imgs)} image(s))" if imgs else ""))
            if not dock.mode(mode):
                sys.exit("le dock ne répond pas (connecté à son Wi-Fi ?)")
        ok = all([dock.send(img, slot) for slot, img in enumerate(imgs, first)]) and ok
    print("fini." if ok else "fini avec erreurs.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
