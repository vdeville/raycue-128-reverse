# RayCue 128K — pilote maison

L'app officielle « Raycue 128K » n'est plus disponible. Ce dossier contient un
remplaçant maison pour envoyer des images à l'écran du dock, obtenu par
reverse-engineering du protocole.

## Utilisation

Le Mac (ou la machine) doit être connecté au **Wi‑Fi du dock** (le dock est la
passerelle `192.168.0.1`). Aucune dépendance : le redimensionnement se fait avec
`sips`, natif macOS.

```bash
# une image -> mode UNIQUE (image fixe)
python3 send.py photo.jpg

# plusieurs images -> mode LOOP (diaporama)
python3 send.py img/rouge.jpg img/vert.jpg img/bleu.jpg

# remplacer UNE seule image d'un loop (garde les autres slots)
python3 send.py --slot 2 photo.jpg

# vider un slot, ou tout effacer
python3 send.py --clear 2
python3 send.py --clear-all

# écouter le trafic brut du dock (debug)
python3 send.py --listen
```

Les images sont stockées **par slot** dans le dock et persistent : on peut
remplacer un slot isolément (`ATTR` avec le bon index + ses données, sans
renvoyer la commande de mode ni les autres images). Le protocole est en revanche
**à sens unique** — aucune commande ne permet de relire les images du dock.

Les images sont redimensionnées automatiquement en **480×320** (résolution de
l'écran). Le dossier `img/` contient des aplats de couleur de test.

## Le protocole (UDP, port 2327)

Toutes les trames ont la même structure :

```
A5 5A | longueur(2, big-endian) | cmd | payload | checksum
```
- `A5 5A` : en-tête fixe
- `longueur` = `len(payload) + 4` (c.-à-d. taille totale de la trame − 2)
- `checksum` = somme de tous les octets précédents, `& 0xFF`

### Commandes

| cmd  | rôle                                   | payload                          |
|------|----------------------------------------|----------------------------------|
| `30` | heartbeat / synchro horloge (toutes 10 s) | date-heure (7 octets)         |
| `50` | passer en mode image fixe              | vide                             |
| `51` | passer en mode loop (diaporama)        | vide                             |
| `40` | attributs de l'image à venir           | `[tailleHi, tailleMid, tailleLo, slot]` |
| `41` | trame de données                       | `[seqHi, seqLo, …2040 octets]`   |
| `42` | **dernière** trame de données (= fin)  | `[seqHi, seqLo, …reste]`         |
| `43` | supprimer l'image d'un slot            | `[slot]`                         |

- `taille` = taille du JPEG sur 3 octets (24 bits).
- `slot` = index de l'image (0 en mode unique ; 0,1,2… en mode loop).
  Le mode loop est plafonné à **9 images maximum** (slots 0 à 8) par l'app et le
  dock. L'octet `slot` fait 1 octet, mais l'app bloque l'ajout au-delà de 9.
- Les données sont découpées en morceaux de **2040 octets** ; chaque trame porte
  son numéro de séquence. La dernière utilise `42` au lieu de `41`.
- L'image est un **JPEG 480×320**.

### Séquence d'un envoi

```
-> 50 (ou 51 pour le loop)          <- ACK
pour chaque image (slot 0,1,…) :
   -> 40  (taille + slot)           <- ACK
   -> 41  (seq 0, 2040 o)           <- ACK  A5 5A 00 07 41 01 <seq> <ck>
   -> 41  (seq 1, 2040 o)           <- ACK
   -> …
   -> 42  (dernière trame)          <- ACK  A5 5A 00 05 42 01 47  (= terminé)
```

Les trames data sont envoyées **en rafale** (pas d'attente ACK entre chaque) ;
`send.py` retransmet les séquences non acquittées si besoin. Un ACK a `status =
01` à l'octet 5.

### Délai du mode loop

**Non pilotable** par ce protocole : l'app n'envoie aucune commande de durée. La
cadence du diaporama est gérée par le firmware du dock (intervalle fixe), seuls
ses boutons physiques pourraient éventuellement la régler.

## Comment ça a été reversé

1. Décompilation de l'APK Android (Flutter) avec **blutter** → assembleur Dart.
2. Lecture du code (`ble_control.dart`, `FileSender.dart`, `udp_manager.dart`)
   pour le squelette du protocole.
3. Correction via une **capture réseau réelle** : APK lancé dans l'émulateur
   Android (patché pour contourner le contrôle Wi‑Fi « réseau Raycue »), envoi
   d'une image au vrai dock, capture `tcpdump` sur l'interface du Mac.
4. La capture a corrigé plusieurs erreurs de lecture de l'assembleur :
   en-tête `A5 5A` (et non `4A B4`), commandes data `41`/`42` (les `82`/`84` lus
   étaient des entiers *tagués* Dart = valeur ×2), résolution 480×320.
```
