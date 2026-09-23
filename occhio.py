"""
OCCHIO - visione dal vivo sulla webcam.

Cosa fa:
  - guarda la webcam in tempo reale
  - trova quello che si muove e lo chiude in un riquadro colorato
  - trova i volti
  - misura il colore dominante di ogni cosa che trova e lo dice a parole
  - punta il MIRINO A DUE ASSI sul bersaglio principale: le due righe si
    incrociano esattamente al centro dell'oggetto piu' importante
  - salva da solo i fotogrammi dei momenti importanti in catture\
  - scrive quello che vede in visione.json, cosi' Claude puo' leggerlo

Tasti:  Q esci   S salva subito   M mostra/nascondi la maschera del movimento

By WhyEd
"""

import cv2
import numpy as np
import json
import time
from pathlib import Path
from datetime import datetime
from analisi_luci import AnalisiLuci
import web

# ---------------------------------------------------------------- impostazioni

CARTELLA = Path(__file__).parent
CATTURE = CARTELLA / "catture"
STATO = CARTELLA / "visione.json"

NOME_CAM = 0            # indice della webcam
# Il case, in frazioni del fotogramma (sinistra, alto, destra, basso).
ZONA_CASE = [0.27, 0.30, 0.61, 0.85]
# La STRISCIA: il punto esatto dove si accendono le luci, trovato con mappa.py
# accendendo una zona per volta. Guardare qui invece che tutto il case fa la
# differenza tra "20 pixel accesi su 172.000" e una misura vera.
ZONA_STRISCIA = [0.40, 0.65, 0.49, 0.76]
AREA_MINIMA = 900       # sotto questa area il movimento e' rumore
PAUSA_CATTURA = 3.0     # secondi minimi tra due catture automatiche
MAX_OGGETTI = 12

CATTURE.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------ nomi dei colori

COLORI_NOTI = [
    ("rosso",    (0, 0, 255)),
    ("arancione", (0, 128, 255)),
    ("giallo",   (0, 255, 255)),
    ("verde",    (0, 255, 0)),
    ("ciano",    (255, 255, 0)),
    ("blu",      (255, 0, 0)),
    ("viola",    (255, 0, 128)),
    ("magenta",  (255, 0, 255)),
    ("bianco",   (255, 255, 255)),
    ("grigio",   (128, 128, 128)),
    ("nero",     (0, 0, 0)),
]


def nome_colore(bgr):
    """Dice a parole che colore e' un BGR."""
    b, g, r = [int(v) for v in bgr]
    migliore, distanza_min = "sconosciuto", None
    for nome, (cb, cg, cr) in COLORI_NOTI:
        d = (b - cb) ** 2 + (g - cg) ** 2 + (r - cr) ** 2
        if distanza_min is None or d < distanza_min:
            distanza_min, migliore = d, nome
    return migliore


def colore_dominante(ritaglio):
    """Colore medio della zona, ignorando i pixel troppo scuri."""
    if ritaglio.size == 0:
        return (0, 0, 0)
    pixel = ritaglio.reshape(-1, 3).astype(np.int32)
    luminosi = pixel[pixel.sum(axis=1) > 90]
    if len(luminosi) < 10:
        luminosi = pixel
    return tuple(int(v) for v in luminosi.mean(axis=0))


# ---------------------------------------------------------------- disegno

def mirino(frame, cx, cy, colore=(0, 255, 255)):
    """Le due assi che incrociandosi fanno centro sul bersaglio."""
    h, w = frame.shape[:2]
    cv2.line(frame, (0, cy), (w, cy), colore, 1, cv2.LINE_AA)
    cv2.line(frame, (cx, 0), (cx, h), colore, 1, cv2.LINE_AA)
    cv2.circle(frame, (cx, cy), 22, colore, 1, cv2.LINE_AA)
    cv2.circle(frame, (cx, cy), 3, colore, -1, cv2.LINE_AA)
    # tacche sui quattro lati, come un vero mirino
    for dx, dy in ((-34, 0), (34, 0), (0, -34), (0, 34)):
        cv2.line(frame, (cx + dx // 2, cy + dy // 2),
                 (cx + dx, cy + dy), colore, 1, cv2.LINE_AA)


def etichetta(frame, testo, x, y, colore):
    (tw, th), _ = cv2.getTextSize(testo, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
    y = max(y, th + 6)
    cv2.rectangle(frame, (x, y - th - 6), (x + tw + 8, y + 2), colore, -1)
    cv2.putText(frame, testo, (x + 4, y - 3), cv2.FONT_HERSHEY_SIMPLEX,
                0.45, (0, 0, 0), 1, cv2.LINE_AA)


def pannello(frame, righe):
    """Il riquadro nero in alto a sinistra con quello che sta vedendo."""
    if not righe:
        return
    alt = 20 + 18 * len(righe)
    sovra = frame.copy()
    cv2.rectangle(sovra, (10, 10), (330, 10 + alt), (0, 0, 0), -1)
    cv2.addWeighted(sovra, 0.55, frame, 0.45, 0, frame)
    cv2.rectangle(frame, (10, 10), (330, 10 + alt), (60, 60, 60), 1)
    for i, (testo, col) in enumerate(righe):
        cv2.putText(frame, testo, (20, 32 + 18 * i),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1, cv2.LINE_AA)


# ---------------------------------------------------------------- programma

def main():
    cam = cv2.VideoCapture(NOME_CAM, cv2.CAP_DSHOW)
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    if not cam.isOpened():
        print("Webcam non disponibile. Se e' aperta in un altro programma, chiudilo.")
        return

    modello = CARTELLA / "yunet.onnx"
    volti = None
    if modello.exists():
        volti = cv2.FaceDetectorYN.create(str(modello), "", (320, 320), 0.7)
    fondo = cv2.createBackgroundSubtractorMOG2(
        history=500, varThreshold=40, detectShadows=False)

    luci = AnalisiLuci(secondi=5.0, fps_attesi=20.0)
    stato_luci = {"stato": "sto guardando", "sicurezza": 0.0}

    mostra_maschera = False
    maschera_aperta = False
    ultima_cattura = 0.0
    n_catture = 0
    t0 = time.time()
    fotogrammi = 0

    indirizzo = web.avvia()
    print("OCCHIO avviato. Q per uscire, S per salvare, M per la maschera.")
    print(f"Dal telefono, stesso wifi: {indirizzo}")

    while True:
        ok, frame = cam.read()
        if not ok:
            break
        fotogrammi += 1
        h, w = frame.shape[:2]
        vista = frame.copy()
        trovati = []

        # --- movimento -------------------------------------------------
        maschera = fondo.apply(frame)
        maschera = cv2.morphologyEx(
            maschera, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        maschera = cv2.dilate(maschera, np.ones((9, 9), np.uint8), iterations=2)
        contorni, _ = cv2.findContours(
            maschera, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contorni = sorted(contorni, key=cv2.contourArea, reverse=True)

        for c in contorni[:MAX_OGGETTI]:
            area = cv2.contourArea(c)
            if area < AREA_MINIMA:
                continue
            x, y, bw, bh = cv2.boundingRect(c)
            bgr = colore_dominante(frame[y:y + bh, x:x + bw])
            trovati.append({
                "tipo": "movimento",
                "colore": nome_colore(bgr),
                "bgr": list(bgr),
                "area": int(area),
                "centro": [int(x + bw / 2), int(y + bh / 2)],
                "riquadro": [int(x), int(y), int(bw), int(bh)],
            })

        # --- volti -----------------------------------------------------
        grigio = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if volti is not None:
            volti.setInputSize((w, h))
            _, facce = volti.detect(frame)
            for f in (facce if facce is not None else []):
                x, y, bw, bh = [int(v) for v in f[:4]]
                trovati.append({
                    "tipo": "volto",
                    "colore": "-",
                    "bgr": [0, 200, 255],
                    "sicurezza": round(float(f[-1]), 2),
                    "area": int(bw * bh),
                    "centro": [int(x + bw / 2), int(y + bh / 2)],
                    "riquadro": [x, y, bw, bh],
                })

        # --- disegno ---------------------------------------------------
        trovati.sort(key=lambda o: (o["tipo"] != "volto", -o["area"]))

        for o in trovati:
            x, y, bw, bh = o["riquadro"]
            col = (0, 200, 255) if o["tipo"] == "volto" else tuple(o["bgr"])
            cv2.rectangle(vista, (x, y), (x + bw, y + bh), col, 2)
            testo = "VOLTO" if o["tipo"] == "volto" else o["colore"].upper()
            etichetta(vista, testo, x, y, col)

        bersaglio = trovati[0] if trovati else None
        if bersaglio:
            mirino(vista, bersaglio["centro"][0], bersaglio["centro"][1])

        # --- le luci si giudicano guardando SOLO la striscia ---
        sx1, sy1 = int(ZONA_STRISCIA[0] * w), int(ZONA_STRISCIA[1] * h)
        sx2, sy2 = int(ZONA_STRISCIA[2] * w), int(ZONA_STRISCIA[3] * h)
        luci.aggiungi(frame, time.time(), (sx1, sy1, sx2 - sx1, sy2 - sy1))
        if fotogrammi % 5 == 0:
            stato_luci = luci.verdetto()

        # il case, con gli angoli
        zx1, zy1 = int(ZONA_CASE[0] * w), int(ZONA_CASE[1] * h)
        zx2, zy2 = int(ZONA_CASE[2] * w), int(ZONA_CASE[3] * h)
        col_case = (0, 210, 255)
        for (ax, ay, bx, by) in ((zx1, zy1, zx1 + 26, zy1), (zx1, zy1, zx1, zy1 + 26),
                                 (zx2 - 26, zy1, zx2, zy1), (zx2, zy1, zx2, zy1 + 26),
                                 (zx1, zy2 - 26, zx1, zy2), (zx1, zy2, zx1 + 26, zy2),
                                 (zx2, zy2 - 26, zx2, zy2), (zx2 - 26, zy2, zx2, zy2)):
            cv2.line(vista, (ax, ay), (bx, by), col_case, 4)
        etichetta(vista, "CASE", zx1, zy1 - 4, col_case)

        # la striscia, col colore che sta facendo adesso
        bgr = stato_luci.get("bgr") or [200, 200, 200]
        col_str = tuple(int(c) for c in bgr)
        cv2.rectangle(vista, (sx1, sy1), (sx2, sy2), col_str, 2)
        etichetta(vista, f"STRISCIA  {stato_luci.get('stato', '')}",
                  sx1, sy1 - 4, col_str)
        # ingrandimento della striscia, in alto a destra: cosi' si vede davvero
        rit = frame[sy1:sy2, sx1:sx2]
        if rit.size:
            zoom = cv2.resize(rit, (240, 150), interpolation=cv2.INTER_NEAREST)
            vista[14:164, w - 254:w - 14] = zoom
            cv2.rectangle(vista, (w - 254, 14), (w - 14, 164), col_str, 2)
            etichetta(vista, "ingrandimento", w - 254, 12, col_str)

        lum = int(grigio.mean())
        fps = fotogrammi / max(time.time() - t0, 0.001)
        col_luci = {
            "SPENTE": (120, 120, 120), "FISSE": (255, 255, 255),
            "RESPIRO": (255, 200, 100), "LAMPEGGIO": (0, 200, 255),
            "ARCOBALENO": (255, 0, 255), "A RITMO": (0, 255, 0),
        }.get(stato_luci.get("stato"), (170, 170, 170))

        righe = [
            (f"OCCHIO  {datetime.now():%H:%M:%S}   {fps:4.1f} fps", (255, 255, 255)),
            (f"LUCI: {stato_luci.get('stato')}", col_luci),
        ]
        if stato_luci.get("descrizione"):
            righe.append(("  " + stato_luci["descrizione"], col_luci))
        elif stato_luci.get("hz", 0) > 0:
            righe.append((f"  ritmo {stato_luci['hz']} Hz   giro colore "
                          f"{stato_luci.get('giro_colore_gradi', 0)} gradi", col_luci))
        righe += [
            (f"oggetti visti: {len(trovati)}", (0, 255, 0) if trovati else (140, 140, 140)),
            (f"luce ambiente: {lum}/255", (200, 200, 200)),
            (f"catture salvate: {n_catture}", (200, 200, 200)),
        ]
        if bersaglio:
            righe.append((
                f"bersaglio: {bersaglio['tipo']} {bersaglio['colore']}",
                (0, 255, 255)))
        pannello(vista, righe)

        # --- cattura dei momenti importanti ----------------------------
        adesso = time.time()
        importante = any(o["tipo"] == "volto" for o in trovati) or \
            (bersaglio is not None and bersaglio["area"] > (w * h) * 0.06)
        if importante and adesso - ultima_cattura > PAUSA_CATTURA:
            nome = CATTURE / f"{datetime.now():%Y%m%d_%H%M%S}.jpg"
            cv2.imwrite(str(nome), vista)
            ultima_cattura = adesso
            n_catture += 1

        # --- stato leggibile da Claude ---------------------------------
        if fotogrammi % 10 == 0:
            STATO.write_text(json.dumps({
                "ora": datetime.now().isoformat(timespec="seconds"),
                "fps": round(fps, 1),
                "luce": lum,
                "luci_rgb": stato_luci,
                "oggetti": trovati[:MAX_OGGETTI],
                "catture": n_catture,
            }, indent=1), encoding="utf-8")

        web.aggiorna(vista, {
            "ora": datetime.now().isoformat(timespec="seconds"),
            "luci_rgb": stato_luci,
            "oggetti": len(trovati),
        })

        cv2.imshow("OCCHIO", vista)
        if mostra_maschera:
            cv2.imshow("movimento", maschera)
            maschera_aperta = True
        elif maschera_aperta:
            cv2.destroyWindow("movimento")
            maschera_aperta = False

        tasto = cv2.waitKey(1) & 0xFF
        if tasto in (ord("q"), 27):
            break
        if tasto == ord("s"):
            nome = CATTURE / f"manuale_{datetime.now():%Y%m%d_%H%M%S}.jpg"
            cv2.imwrite(str(nome), vista)
            n_catture += 1
        if tasto == ord("m"):
            mostra_maschera = not mostra_maschera

    cam.release()
    cv2.destroyAllWindows()
    print(f"Chiuso. Catture salvate: {n_catture} in {CATTURE}")


if __name__ == "__main__":
    main()
