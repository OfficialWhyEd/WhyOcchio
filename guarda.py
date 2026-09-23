"""
Guarda dentro il case e conta i punti luminosi colorati, invece di fare la media.
La media di una zona quasi tutta nera nasconde due LED accesi.
"""

import sys
import urllib.request

import cv2
import numpy as np

URL = "http://127.0.0.1:8099/flusso"
ZONA = (0.27, 0.30, 0.61, 0.85)     # la stessa che usa l'occhio


def un_fotogramma():
    dati = b""
    with urllib.request.urlopen(URL, timeout=8) as f:
        while len(dati) < 300000:
            p = f.read(32768)
            if not p:
                break
            dati += p
    fine = dati.rfind(b"\xff\xd9")
    inizio = dati.rfind(b"\xff\xd8", 0, fine)
    if inizio < 0 or fine < 0:
        return None
    buf = np.frombuffer(dati[inizio:fine + 2], dtype=np.uint8)
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def main():
    img = un_fotogramma()
    if img is None:
        print("non riesco a prendere un fotogramma")
        return
    h, w = img.shape[:2]
    x1, y1 = int(ZONA[0] * w), int(ZONA[1] * h)
    x2, y2 = int(ZONA[2] * w), int(ZONA[3] * h)
    # tolgo un bordo: l'occhio disegna li' il rettangolo del case, e misurarlo
    # significherebbe misurare il proprio disegno invece delle luci
    b = 8
    case = img[y1 + b:y2 - b, x1 + b:x2 - b]
    cv2.imwrite(r"E:\Occhio\solo_case.jpg", case)

    hsv = cv2.cvtColor(case, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[:, :, 0].astype(int), hsv[:, :, 1].astype(int), hsv[:, :, 2].astype(int)
    totali = case.shape[0] * case.shape[1]

    # un LED acceso e' un pixel LUMINOSO e COLORATO
    accesi = (V > 150) & (S > 90)
    n = int(accesi.sum())
    print(f"zona del case: {case.shape[1]}x{case.shape[0]} = {totali} pixel")
    print(f"pixel accesi e colorati (V>150, S>90): {n}   ({n/totali*100:.3f}%)")

    if n:
        toni = H[accesi] * 2
        nomi = [(15, "rosso"), (45, "arancione"), (70, "giallo"), (160, "verde"),
                (200, "ciano"), (260, "blu"), (290, "viola"), (330, "magenta"), (361, "rosso")]
        conteggio = {}
        for t in toni:
            for limite, nome in nomi:
                if t < limite:
                    conteggio[nome] = conteggio.get(nome, 0) + 1
                    break
        print("colori trovati:", dict(sorted(conteggio.items(), key=lambda x: -x[1])))
        print(f"luminosita' media dei punti accesi: {int(V[accesi].mean())}")
    else:
        print("nessun punto acceso e colorato: le luci sono spente davvero")

    # i 6 punti piu' luminosi in assoluto, colorati o no
    piatta = V.flatten()
    idx = np.argsort(piatta)[-6:][::-1]
    print("\ni 6 punti piu' luminosi nel case:")
    for k in idx:
        yy, xx = divmod(int(k), case.shape[1])
        b, g, r = case[yy, xx]
        print(f"  ({xx:4},{yy:4})  rgb=({r:3},{g:3},{b:3})  V={V[yy,xx]:3}  S={S[yy,xx]:3}")


if __name__ == "__main__":
    main()
