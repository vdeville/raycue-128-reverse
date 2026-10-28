#!/usr/bin/env python3
"""Affiche une ou plusieurs images sur le dock RayCue 128K (protocole UDP reversé).

  python3 send.py photo.jpg                  # mode UNIQUE (une image fixe)
  python3 send.py a.jpg b.jpg c.jpg          # mode LOOP (diaporama, 9 images max)
  python3 send.py --slot 2 photo.jpg         # remplace juste le slot 2 (garde les autres)
  python3 send.py --clear 2                   # vide le slot 2
  python3 send.py --clear-all                 # efface tous les slots
  python3 send.py --listen                   # écoute brute sur :2327

Protocole (vérifié par capture d'un envoi réel de l'app) :
  Trame = A5 5A | len(2,BE)=len(payload)+4 | cmd | payload | checksum(somme&0xFF)
  0x50 : entrer en mode fixe        0x51 : entrer en mode loop
  0x40 : ATTR   payload = [tailleHi, tailleMid, tailleLo, slot]   (taille JPEG 24 bits)
  0x41 : DATA   payload = [seqHi, seqLo, *données]  (morceaux de 2040 o)
  0x42 : DATA dernière trame (même format, signale la fin)
  L'écran attend un JPEG 480x320. Le dock ACK chaque trame (A5 5A .. <cmd> 01 ..).
"""
import socket, time, argparse, subprocess, tempfile, os

DOCK = ("192.168.0.1", 2327)
W, H, CHUNK = 480, 320, 2040
MAX_SLOTS = 9            # le mode loop est plafonné à 9 images (slots 0..8) par l'app/dock
MAGIC = b"\xa5\x5a"

def frame(payload, cmd):
    n = len(payload) + 4
    body = MAGIC + bytes([(n >> 8) & 0xFF, n & 0xFF, cmd]) + bytes(payload)
    return body + bytes([sum(body) & 0xFF])

def jpeg_480x320(path):
    tmp = tempfile.mktemp(suffix=".jpg")
    subprocess.run(["sips", "-s", "format", "jpeg", "--resampleHeightWidth", str(H), str(W),
                    path, "--out", tmp], check=True, capture_output=True)
    d = open(tmp, "rb").read(); os.unlink(tmp)
    return d

def connect():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", 0)); s.settimeout(1.0)
    return s

def cmd(s, payload, c, tag):
    for _ in range(8):
        s.sendto(frame(payload, c), DOCK)
        try:
            while True:
                d, _w = s.recvfrom(2048)
                if d[:2] == MAGIC and d[4] == c and len(d) > 5 and d[5] == 1:
                    print(f"-> {tag}: OK"); return True
        except socket.timeout:
            pass
    print(f"!! {tag} sans ACK"); return False

def send_image(s, img, slot):
    n = -(-len(img) // CHUNK)
    L = len(img)
    cmd(s, [(L >> 16) & 0xFF, (L >> 8) & 0xFF, L & 0xFF, slot & 0xFF], 0x40, f"ATTR slot{slot}")
    def dframe(i):
        c = 0x42 if i == n - 1 else 0x41
        return frame([(i >> 8) & 0xFF, i & 0xFF] + list(img[i*CHUNK:(i+1)*CHUNK]), c)
    pending = set(range(n)); done = False
    for _ in range(10):
        for i in sorted(pending):
            s.sendto(dframe(i), DOCK); time.sleep(0.02)
        t = time.time()
        while time.time() - t < 1.0:
            try:
                d, _w = s.recvfrom(2048)
            except socket.timeout:
                break
            if d[:2] != MAGIC or len(d) < 6 or d[5] != 1:
                continue
            if d[4] == 0x42:
                done = True; pending.clear(); break
            if d[4] == 0x41 and len(d) >= 8:
                pending.discard((d[6] << 8) | d[7])
        if done or not pending:
            break
    print(f"   image slot{slot}: {'OK' if done or not pending else 'incomplet '+str(sorted(pending))}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="*")
    ap.add_argument("--listen", action="store_true")
    ap.add_argument("--slot", type=int,
                    help="remplace UNIQUEMENT ce slot (0-8) d'un loop existant, sans tout renvoyer")
    ap.add_argument("--clear", type=int, metavar="N", help="supprime l'image du slot N")
    ap.add_argument("--clear-all", action="store_true", help="supprime toutes les images (slots 0-8)")
    a = ap.parse_args()

    if not (a.images or a.listen or a.clear is not None or a.clear_all):
        ap.error("donne au moins une image (ou --listen / --clear N / --clear-all)")

    s = connect()
    if a.listen:
        s.settimeout(None)
        while True:
            d, w = s.recvfrom(2048); print(w[0], d.hex(" "))

    # Suppression : commande 0x43 avec le numéro de slot en payload.
    if a.clear_all:
        for i in range(MAX_SLOTS):
            cmd(s, [i], 0x43, f"clear slot{i}")
        print("fini."); return
    if a.clear is not None:
        if not 0 <= a.clear < MAX_SLOTS:
            ap.error(f"--clear doit être entre 0 et {MAX_SLOTS-1}")
        cmd(s, [a.clear], 0x43, f"clear slot{a.clear}")
        print("fini."); return

    # Mise à jour d'un seul slot : pas de commande de mode (le dock garde les autres).
    if a.slot is not None:
        if not 0 <= a.slot < MAX_SLOTS:
            ap.error(f"--slot doit être entre 0 et {MAX_SLOTS-1}")
        print(f"remplace le slot {a.slot}")
        send_image(s, jpeg_480x320(a.images[0]), a.slot)
        print("fini."); return

    if len(a.images) > MAX_SLOTS:
        print(f"! {len(a.images)} images demandées, le dock n'en gère que {MAX_SLOTS} -> on garde les {MAX_SLOTS} premières")
        a.images = a.images[:MAX_SLOTS]
    imgs = [jpeg_480x320(p) for p in a.images]
    loop = len(imgs) > 1
    print(f"{len(imgs)} image(s) -> mode {'LOOP' if loop else 'UNIQUE'}")
    cmd(s, [], 0x51 if loop else 0x50, "LOOP" if loop else "FIXED")
    for slot, img in enumerate(imgs):
        send_image(s, img, slot)
    print("fini.")

if __name__ == "__main__":
    main()
