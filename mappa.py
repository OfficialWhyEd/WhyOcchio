"""
MAPPA - scopre quale zona dell'SDK accende quale punto dentro il case.

Accende una zona per volta, guarda dalla webcam e segna dove si e' illuminato.
Alla fine dice: zona 3 -> la striscia in basso, zona 5 -> il logo, e cosi' via.
"""

import ctypes
import time
import urllib.request

import cv2
import numpy as np

URL = "http://127.0.0.1:8099/flusso"
ZONA_CASE = (0.27, 0.30, 0.61, 0.85)
COLORE = (255, 0, 0)          # rosso pieno: il piu' visibile attraverso il vetro
ZONE = range(8)

_ole = ctypes.WinDLL("oleaut32")
_ole.SysAllocString.restype = ctypes.c_void_p
_ole.SysAllocString.argtypes = [ctypes.c_wchar_p]


def fotogramma():
    dati = b""
    with urllib.request.urlopen(URL, timeout=8) as f:
        while len(dati) < 300000:
            p = f.read(32768)
            if not p:
                break
            dati += p
    fine = dati.rfind(b"\xff\xd9")
    inizio = dati.rfind(b"\xff\xd8", 0, fine)
    if inizio < 0:
        return None
    return cv2.imdecode(np.frombuffer(dati[inizio:fine + 2], np.uint8), cv2.IMREAD_COLOR)


def ritaglio(img):
    h, w = img.shape[:2]
    return img[int(ZONA_CASE[1] * h):int(ZONA_CASE[3] * h),
               int(ZONA_CASE[0] * w):int(ZONA_CASE[2] * w)]


def main():
    d = ctypes.WinDLL(r"E:\Occhio\sdk\MysticLight_SDK_x64.dll")
    print("init:", d.MLAPI_Initialize(), flush=True)
    dev = _ole.SysAllocString("MSI_MB")
    st = _ole.SysAllocString("NoAnimation")
    d.MLAPI_SetLedStyle.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    d.MLAPI_SetLedColor.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_int]

    def spegni_tutto():
        for i in ZONE:
            d.MLAPI_SetLedStyle(dev, i, st)
            d.MLAPI_SetLedColor(dev, i, 0, 0, 0)

    print("spengo tutto e prendo il riferimento al buio...", flush=True)
    spegni_tutto()
    time.sleep(1.5)
    base = ritaglio(fotogramma()).astype(np.int16)
    cv2.imwrite(r"E:\Occhio\mappa_spente.jpg", base.astype(np.uint8))

    risultati = []
    for z in ZONE:
        spegni_tutto()
        d.MLAPI_SetLedColor(dev, z, *COLORE)
        time.sleep(1.2)
        img = ritaglio(fotogramma())
        if img is None:
            continue
        diff = np.clip(img.astype(np.int16) - base, 0, 255).astype(np.uint8)
        grigio = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        grigio = cv2.GaussianBlur(grigio, (9, 9), 0)
        forza = int(grigio.max())
        _, _, _, punto = cv2.minMaxLoc(grigio)
        acceso = int((grigio > 40).sum())
        risultati.append((z, forza, acceso, punto))
        print(f"  zona {z}: differenza max {forza:3}  pixel accesi {acceso:5}  "
              f"posizione {punto}", flush=True)
        cv2.imwrite(rf"E:\Occhio\mappa_zona{z}.jpg", diff)

    print("\n=== chi si vede davvero ===", flush=True)
    for z, forza, acceso, punto in sorted(risultati, key=lambda r: -r[1]):
        dove = "in alto" if punto[1] < 130 else ("in mezzo" if punto[1] < 260 else "in basso")
        dove += " a sinistra" if punto[0] < 145 else (" al centro" if punto[0] < 290 else " a destra")
        if forza > 25:
            print(f"  zona {z}: SI, si vede ({forza})  ->  {dove}", flush=True)
        else:
            print(f"  zona {z}: no, non cambia niente ({forza})", flush=True)

    print("\nrimetto tutto acceso.", flush=True)
    for i in ZONE:
        d.MLAPI_SetLedColor(dev, i, 255, 255, 255)


if __name__ == "__main__":
    main()
