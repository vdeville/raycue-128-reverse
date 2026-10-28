# RayCue 128K — pilote maison

L'app officielle « Raycue 128K » n'est plus disponible. Ce dépôt contient un
remplaçant maison, `send.py`, pour envoyer des images à l'écran du dock, obtenu
par reverse-engineering du protocole.

## Installation

- Python 3.10+ (macOS, Linux ou Windows).
- La machine doit être connectée au **Wi‑Fi du dock** (le dock est la passerelle
  `192.168.0.1`).

```bash
pip install -r requirements.txt   # Pillow + pillow-heif (photos HEIC d'iPhone)
```

`pillow-heif` est facultatif : sans lui, tout fonctionne sauf les fichiers
`.heic` / `.heif` (le script indique alors comment l'installer).

## Interface graphique

```bash
python3 gui/app.py      # ouvre http://127.0.0.1:8128/ (options : --no-browser --port --dock-host --dock-port)
```

Aucune dépendance en plus de `requirements.txt` : un petit serveur local en
bibliothèque standard + une page web sans ressource externe (le Wi‑Fi du dock
n'a pas Internet). Le navigateur ne parle qu'au serveur, qui envoie les paquets
UDP via `send.py`. Style « Macintosh 128K », comme le dock.

**Éditer et envoyer**

1. Cliquer sur l'écran du boîtier (ou y glisser une photo) : il fait 480×320,
   ce qu'on y voit est exactement ce qui part au dock.
2. Retoucher : glisser pour déplacer, molette pour zoomer, *Ajuster* (image
   entière + bandes de la couleur *Fond*) ou *Remplir* (rognage, le fond ne se
   voit plus), rotation, miroir, luminosité, contraste, saturation.
3. Choisir l'emplacement (album ou liste) puis **Envoyer** — seul cet
   emplacement change — ou **Image fixe** pour n'afficher que cette image.

**Reprendre une image déjà envoyée** : le dock ne sait pas renvoyer ses images,
donc le navigateur garde, pour chaque envoi, l'original (IndexedDB), les
réglages et la vignette (localStorage). **Éditer** sur un emplacement de
l'album recharge l'original avec ses réglages dans l'éditeur et choisit cet
emplacement ; **Envoyer** le remplace. Ça ne marche que dans le navigateur qui a
fait l'envoi ; pour les envois antérieurs à cette fonction, seule la vignette
480×320 est retouchable.

**Mode du dock** (fenêtre Album) : **Image fixe** (affiche l'emplacement 1) ou
**Diaporama**, sans renvoyer d'image. Le dock ne permet pas de lire son mode :
les boutons montrent le dernier mode envoyé depuis ce navigateur.

**Tout renvoyer au dock** (fenêtre Album) : remet le dock exactement comme
l'album — commande de mode (celle affichée, sinon diaporama s'il y a plusieurs
images), chaque emplacement rempli re-rendu depuis son original et ses réglages,
puis suppression sur le dock des emplacements vides dans l'album. Pratique après
un reset du dock ou des envois faits ailleurs (qui seront écrasés).

**Autres actions** : **Diaporama…** (9 images max, mêmes réglages que
l'éditeur), **×** pour vider un emplacement, **Tout effacer**, **Journal** des
échanges sous l'écran. Mise en page adaptée au mobile.

**API locale** (servie par `gui/app.py`, utilisable depuis un script) :

| Route | Rôle |
|---|---|
| `GET /api/status` | `reachable` (adresse sur le réseau du dock), SSID, mot de passe, nombre de slots |
| `POST /api/image?slot=N&mode=fixed\|loop&quality=Q` | corps = image (idéalement 480×320) ; commande de mode facultative puis envoi dans le slot ; renvoie `ok`, `log` et le JPEG envoyé (base64) |
| `POST /api/mode?mode=fixed\|loop` | bascule seulement le mode |
| `POST /api/clear?slot=N[,M…]` | vide un ou plusieurs slots |
| `POST /api/decode` | corps = image (HEIC, TIFF…) → PNG lisible par le navigateur |

**État du dock** (en haut à droite) :
- 🔴 *injoignable* : pas d'adresse sur le réseau du dock, ou dernier envoi non
  acquitté. Une fenêtre indique le Wi‑Fi **Raycue 128K**, mot de passe
  **12345678**.
- 🟠 *réseau OK — dock non confirmé* : adresse en 192.168.0.x, mais une box peut
  utiliser la même plage ; le dock ne peut pas être sondé sans rien modifier.
- 🟢 *joignable* : le dock a acquitté une commande dans la session.

## Ligne de commande

```bash
python3 send.py photo.heic                       # 1 image -> mode fixe
python3 send.py img/rouge.jpg img/vert.jpg img/  # fichiers et/ou dossiers -> mode loop (9 max)
python3 send.py a.jpg b.jpg -m fixed             # force le mode (ne garde que la 1re image)
python3 send.py --slot 2 photo.jpg               # remplace UNE image d'un loop (garde les autres)
python3 send.py --slot 6 a.jpg b.jpg c.jpg       # remplit les slots 6, 7 et 8
python3 send.py --clear 2 5                      # vide les slots 2 et 5
python3 send.py --clear-all a.jpg b.jpg          # efface tout, puis envoie
python3 send.py -m loop                          # bascule seulement le mode (fixed / loop)
python3 send.py photo.jpg -f cover               # remplit l'écran en rognant
python3 send.py logo.png -b "#ffffff" -r 90      # fond blanc, rotation horaire 90°
python3 send.py img/ --save out/                 # prépare les JPEG sans envoyer (aperçu)
python3 send.py -h                               # aide complète
```

### Options

| Option | Défaut | Rôle |
|---|---|---|
| `images…` | — | Fichiers image et/ou dossiers (contenu trié par nom). Formats : jpg, png, gif, bmp, webp, tiff, heic/heif |
| `-m, --mode auto\|fixed\|loop` | `auto` | `auto` = `fixed` pour 1 image, `loop` sinon. `fixed` n'envoie que la 1re image, `loop` au plus 9. Sans image : bascule seulement le mode |
| `-s, --slot N` | — | Écrit dans le slot N (0‑8), puis N+1… si plusieurs images, **sans commande de mode** : les autres slots sont conservés. Incompatible avec `--mode` |
| `--clear N [N…]` | — | Vide ces slots (commande `43`) |
| `--clear-all` | — | Vide les slots 0 à 8 |
| `-f, --fit contain\|cover\|stretch` | `contain` | `contain` = image entière + bandes ; `cover` = remplit l'écran en rognant ; `stretch` = déforme |
| `-b, --background` | `black` | Couleur des bandes et de la transparence (nom CSS ou `#rrggbb`) |
| `-r, --rotate 0\|90\|180\|270` | `0` | Rotation horaire supplémentaire, après correction EXIF |
| `-q, --quality` | `90` | Qualité JPEG (1‑95) |
| `--save DIR` | — | Écrit les JPEG préparés dans `DIR` (`<slot>_<nom>.jpg`) et n'envoie rien |
| `--host` | `192.168.0.1` | Adresse du dock |
| `--port` | `2327` | Port UDP du dock |
| `--timeout` | `1.0` | Attente d'un ACK de commande (s) |
| `--retries` | `8` | Tentatives par commande / passes de retransmission des données |
| `--delay` | `0.02` | Pause entre deux trames de données (s) |

Ordre d'exécution : les `--clear` / `--clear-all` passent **avant** l'envoi
d'images. `--clear` accepte plusieurs numéros : placer les images avant
(`send.py a.jpg --clear 2`) ou séparer avec `--` (`send.py --clear 2 -- a.jpg`).

Code de sortie : `0` si tout a été acquitté, `1` sinon (image incomplète, slot
non vidé, dock muet).

### Préparation des images

Chaque image est convertie en **JPEG baseline 480×320** (résolution de l'écran) :

1. orientation EXIF appliquée (photos de téléphone prises en portrait) ;
2. rotation `--rotate` éventuelle ;
3. transparence (PNG, GIF…) aplatie sur `--background` ;
4. mise à l'échelle selon `--fit`, ratio conservé sauf en `stretch`.

Le dossier `img/` contient des aplats de couleur de test.

### Slots

Les images sont stockées **par slot** (0 à 8) dans le dock et persistent. On
peut remplacer ou vider un slot isolément, sans renvoyer la commande de mode ni
les autres images. Le protocole est en revanche **à sens unique** : aucune
commande ne permet de relire le contenu du dock.

### Fiabilité (UDP)

- **Commandes** (mode, `40`, `43`) : renvoyées jusqu'à `--retries` fois tant
  que l'ACK n'arrive pas dans `--timeout`.
- **Données** : envoyées en rafale ; chaque ACK `41 01 <seq>` retire la
  séquence de la liste d'attente, puis seules les séquences non acquittées sont
  renvoyées (jusqu'à `--retries` passes). Une image incomplète est signalée
  (`incomplet [3, 7]`).
- L'ACK de la trame finale `42` ne valide **que** la dernière trame : l'image
  n'est déclarée complète que lorsque toutes les séquences ont été acquittées.
  Si un ACK se perd, la trame correspondante est renvoyée en double (le numéro
  de séquence permet au dock de la replacer).
- Réseau instable : augmenter `--delay` et/ou `--retries`.

## Le protocole (UDP, port 2327)

Toutes les trames ont la même structure :

```
A5 5A | longueur(2, big-endian) | cmd | payload | checksum
```
- `A5 5A` : en-tête fixe
- `longueur` = `len(payload) + 4` (c.-à-d. taille totale de la trame − 2)
- `checksum` = somme de tous les octets précédents, `& 0xFF`

Un ACK du dock reprend la même structure avec la commande acquittée à l'octet 4
et `status = 01` à l'octet 5.

### Commandes

| cmd  | rôle                                   | payload                          |
|------|----------------------------------------|----------------------------------|
| `30` | heartbeat / synchro horloge (toutes 10 s, envoyé par l'app ; inutile à `send.py`) | date-heure (7 octets) |
| `50` | passer en mode image fixe              | vide                             |
| `51` | passer en mode loop (diaporama)        | vide                             |
| `40` | attributs de l'image à venir           | `[tailleHi, tailleMid, tailleLo, slot]` |
| `41` | trame de données                       | `[seqHi, seqLo, …2040 octets]`   |
| `42` | **dernière** trame de données (= fin)  | `[seqHi, seqLo, …reste]`         |
| `43` | supprimer l'image d'un slot            | `[slot]`                         |

- `taille` = taille du JPEG sur 3 octets (24 bits).
- `slot` = index de l'image (0 en mode fixe ; 0 à 8 en mode loop). L'octet fait
  1 octet, mais l'app et le dock plafonnent le loop à **9 images**.
- Les données sont découpées en morceaux de **2040 octets** ; chaque trame porte
  son numéro de séquence. La dernière utilise `42` au lieu de `41`.
- L'image est un **JPEG 480×320**.

### Séquences

Envoi complet :

```
-> 50 (ou 51 pour le loop)          <- ACK
pour chaque image (slot 0,1,…) :
   -> 40  (taille + slot)           <- ACK
   -> 41  (seq 0, 2040 o)           <- ACK  A5 5A 00 07 41 01 <seq> <ck>
   -> 41  (seq 1, 2040 o)           <- ACK
   -> …
   -> 42  (dernière trame)          <- ACK  A5 5A 00 05 42 01 47  (= terminé)
```

Remplacement d'un slot (`--slot`) : même chose **sans** la commande `50`/`51`.

Suppression (`--clear`) : `-> 43 [slot]   <- ACK`, une fois par slot.

Changement de mode seul (`-m fixed|loop` sans image, boutons « Mode du dock » de
l'interface) : `-> 50 / 51   <- ACK`. L'app officielle n'envoie jamais cette
commande sans images derrière : que le dock bascule bien en gardant ses slots
(et qu'en mode fixe il affiche le slot 0) reste **à confirmer** sur le matériel.

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
