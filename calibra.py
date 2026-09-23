"""
CALIBRA - l'occhio impara da solo dove sono le luci.

Non serve piu' scrivere le coordinate a mano: il programma accende e spegne
le luci qualche volta, guarda dalla webcam quali pixel cambiano, e segna li'
la zona da controllare. Va rilanciato ogni volta che si sposta la webcam.

Il risultato finisce in zone.json, che occhio.py legge all'avvio.

Serve l'amministratore (usa CALIBRA.cmd).

By WhyEd
"""

import ctypes
import json
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np

URL = "http://127.0.0.1:8099/flusso"
CARTELLA = Path(__file__).parent
CONFIG = CARTELLA / "zone.json"
DLL = CARTELLA / "sdk" / "MysticLight_SDK_x64.dll"
ZONE_LED = range(8)
GIRI = 4                      # quante volte accende e spegne

_ole = ctypes.WinDLL("oleaut32")
_ole.SysAllocString.restype = ctypes.c_void_p
_ole.SysAllocString.argtypes = [ctypes.c_wchar_p]


def fotogramma():
    dati = b""
    with urllib.request.urlopen(URL, timeout=10) as f:
        while len(dati) < 400000:
            p = f.read(32768)
            if not p:
                break
            dati += p
    fine = dati.rfind(b"\xff\xd9")
    inizio = dati.rfind(b"\xff\xd8", 0, fine)
    if inizio < 0 or fine < 0:
        return None
    return cv2.imdecode(np.frombuffer(dati[inizio:fine + 2], np.uint8), cv2.IMREAD_COLOR)


class Luci:
    def __init__(self):
        self.dll = ctypes.WinDLL(str(DLL))
        r = self.dll.MLAPI_Initialize()
        if r != 0:
            raise RuntimeError(f"MLAPI_Initialize -> {r}")
        self.dll.MLAPI_SetLedStyle.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                              ctypes.c_void_p]
        self.dll.MLAPI_SetLedColor.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                              ctypes.c_int, ctypes.c_int, ctypes.c_int]
        self.dev = _ole.SysAllocString("MSI_MB")
        fisso = _ole.SysAllocString("NoAnimation")
        for i in ZONE_LED:
            self.dll.MLAPI_SetLedStyle(self.dev, i, fisso)

    def imposta(self, r, g, b):
        for i in ZONE_LED:
            self.dll.MLAPI_SetLedColor(self.dev, i, r, g, b)


def main():
    print("cerco le luci guardando cosa cambia quando le accendo...", flush=True)
    try:
        luci = Luci()
    except (OSError, RuntimeError) as e:
        print(f"non riesco a comandare le luci: {e}")
        print("serve l'amministratore e i servizi MSI attivi.")
        return

    prova = fotogramma()
    if prova is None:
        print("l'occhio non risponde: avvialo prima con AVVIA OCCHIO.cmd")
        return
    h, w = prova.shape[:2]
    somma = np.zeros((h, w), dtype=np.float32)

    for giro in range(GIRI):
        luci.imposta(0, 0, 0)
        time.sleep(1.4)
        spente = fotogramma()
        luci.imposta(255, 255, 255)
        time.sleep(1.4)
        accese = fotogramma()
        if spente is None or accese is None:
            continue
        d = cv2.absdiff(accese, spente)
        somma += cv2.cvtColor(d, cv2.COLOR_BGR2GRAY).astype(np.float32)
        print(f"  giro {giro + 1}/{GIRI}", flush=True)

    somma = cv2.GaussianBlur(somma, (15, 15), 0)
    massimo = float(somma.max())
    print(f"\ndifferenza massima trovata: {massimo:.0f}")

    if massimo < 12:
        print("Non ho visto NESSUN cambiamento accendendo e spegnendo.")
        print("O le luci non si accendono, o la webcam non inquadra il case.")
        return

    # tutti i punti che cambiano davvero, non solo il massimo
    mappa = (somma > massimo * 0.45).astype(np.uint8) * 255
    ys, xs = np.nonzero(mappa)
    x1, x2 = int(xs.min()), int(xs.max())
    y1, y2 = int(ys.min()), int(ys.max())
    # un po' di margine, ma senza uscire dal fotogramma
    mx, my = max(12, (x2 - x1) // 4), max(12, (y2 - y1) // 4)
    x1, y1 = max(0, x1 - mx), max(0, y1 - my)
    x2, y2 = min(w, x2 + mx), min(h, y2 + my)

    zone = {
        "striscia": [round(x1 / w, 4), round(y1 / h, 4),
                     round(x2 / w, 4), round(y2 / h, 4)],
        "pixel": [x1, y1, x2, y2],
        "misura": round(massimo, 1),
        "quando": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    CONFIG.write_text(json.dumps(zone, indent=1), encoding="utf-8")

    print(f"luci trovate in ({x1},{y1}) - ({x2},{y2}), "
          f"cioe' {x2-x1}x{y2-y1} pixel")
    print(f"salvato in {CONFIG.name}: riavvia l'occhio e guardera' li'.")

    prova = fotogramma()
    if prova is not None:
        cv2.rectangle(prova, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.imwrite(str(CARTELLA / "calibrazione.jpg"), prova)
        print("controllo visivo salvato in calibrazione.jpg")

    luci.imposta(255, 190, 120)


if __name__ == "__main__":
    main()
