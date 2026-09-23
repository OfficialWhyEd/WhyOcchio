"""
LUCI - le luci del case di Whyed.

LA RICHIESTA, parole sue del 01/09:
    "vorrei tutti i tipi di led randomici e tutti gli effetti randomici,
     ma la cosa piu' figa e' che vanno pure a tempo e a volte a impulso
     delle parole"
    "anche quando non c'e' musica devono funzionare [...] basta che non si
     fermi, che c'e' per un motivo"
E il 02/09: "devono stare al massimo della luminosita'".

COME FUNZIONA
-------------
Due tipi di effetto, mescolati a caso:

1. **Effetti miei**, dove comando io il colore e reagisce al suono.
   Sette comportamenti diversi (scorre, pulsa, lampeggia, salta, alterna,
   respira, impazzisce), scelti a caso e cambiati ogni tanto.

2. **Effetti del chip** (Rainbow, Meteor, Lightning, Flashing, Marquee,
   Stack, Breathing, Random): li anima la scheda da sola, fluidi e senza
   consumare niente. Non reagiscono al suono, ma sono belli e non si fermano.

Quando c'e' suono si usano quelli miei, che rispondono. Quando cala il silenzio
si passa spesso a quelli del chip, che sono piu' fluidi. Ogni volta e' diverso.

PERCHE' NON CI SONO ONDE NE' ARCOBALENI CHE SCORRONO
Misurato accendendo una zona per volta e guardando dalla webcam: le 8 zone
dell'SDK accendono **tutte lo stesso punto**. Non sono luci in fila, e' una
luce sola. Ogni effetto "spaziale" e' impossibile: si puo' variare solo nel tempo.

VELOCITA': una scrittura di colore costa 660 ms. Per questo il programma non
scrive a orologio ma **aspetta il colpo e scrive subito**, cosi' il colore
scatta insieme alla cassa.

Serve l'amministratore. Parte da solo con l'attivita' "LUCI WhyEd".

By WhyEd
"""

import colorsys
import ctypes
import math
import random
import threading
import time
from pathlib import Path

import numpy as np
import soundcard as sc

# ------------------------------------------------------------- impostazioni

DLL = Path(__file__).parent / "sdk" / "MysticLight_SDK_x64.dll"
DISPOSITIVO = "MSI_MB"
ZONA = 1                    # la piu' luminosa nella prova con la webcam

CAMPIONI = 512
SILENZIO = 0.004
ATTESA_SILENZIO = 3.0
RAPPORTO = 8.0

MINIMO = 0.86               # la luce non scende MAI sotto: le vuole al massimo
COLPO = 0.30                # sopra questo picco si scrive subito
DURATA = (14.0, 28.0)       # quanto dura un effetto prima di cambiare

# effetti miei: reagiscono al suono
MIEI = ["scorre", "pulsa", "lampeggia", "salta", "alterna", "respira", "impazzisce"]
# effetti della scheda: li anima il chip, fluidi e gratis
CHIP = ["Rainbow", "Meteor", "Lightning", "Flashing", "Marquee", "Stack",
        "Breathing", "Random"]

_ole = ctypes.WinDLL("oleaut32")
_ole.SysAllocString.restype = ctypes.c_void_p
_ole.SysAllocString.argtypes = [ctypes.c_wchar_p]
_ole.SysFreeString.argtypes = [ctypes.c_void_p]   # senza questo va in overflow


# ------------------------------------------------------------------ scheda

class Striscia:
    def __init__(self):
        self.dll = ctypes.WinDLL(str(DLL))
        r = self.dll.MLAPI_Initialize()
        if r != 0:
            raise RuntimeError(f"MLAPI_Initialize -> {r}: serve l'amministratore "
                               "e i servizi MSI attivi")
        self.dll.MLAPI_SetLedStyle.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                               ctypes.c_void_p]
        self.dll.MLAPI_SetLedColor.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                               ctypes.c_int, ctypes.c_int, ctypes.c_int]
        self._dev = _ole.SysAllocString(DISPOSITIVO)
        self._fisso = _ole.SysAllocString("NoAnimation")
        self._modo_colore = False

    def pronta_per_colore(self):
        """Senza NoAnimation il colore non entra e risponde -103."""
        if not self._modo_colore:
            self.dll.MLAPI_SetLedStyle(self._dev, ZONA, self._fisso)
            self._modo_colore = True

    def colore(self, r, g, b):
        self.pronta_per_colore()
        return self.dll.MLAPI_SetLedColor(self._dev, ZONA, int(r), int(g), int(b))

    def stile(self, nome):
        b = _ole.SysAllocString(nome)
        r = self.dll.MLAPI_SetLedStyle(self._dev, ZONA, b)
        _ole.SysFreeString(b)
        self._modo_colore = (nome == "NoAnimation")
        return r


# ----------------------------------------------------------------- ascolto

class Orecchio:
    def __init__(self):
        self.livello = 0.0
        self.picco = 0.0
        self.ultimo_suono = 0.0
        self._vivo = True
        self._sorgenti = []
        try:
            u = sc.default_speaker()
            self._sorgenti.append(sc.get_microphone(u.name, include_loopback=True))
        except Exception:
            pass
        try:
            m = sc.default_microphone()
            if m and all(m.name != s.name for s in self._sorgenti):
                self._sorgenti.append(m)
        except Exception:
            pass
        if not self._sorgenti:
            raise RuntimeError("nessuna sorgente audio")
        for s in self._sorgenti:
            threading.Thread(target=self._ascolta, args=(s,), daemon=True).start()

    @property
    def sorgenti(self):
        return [s.name for s in self._sorgenti]

    def _ascolta(self, sorgente):
        try:
            with sorgente.recorder(samplerate=44100, channels=1,
                                   blocksize=CAMPIONI) as rec:
                while self._vivo:
                    dati = rec.record(numframes=CAMPIONI)
                    v = float(np.sqrt(np.mean(dati.astype(np.float64) ** 2)))
                    self.livello = max(v, self.livello * 0.80)
                    self.picco = max(self.picco, v)
                    if v > SILENZIO:
                        self.ultimo_suono = time.time()
        except Exception:
            pass

    def leggi(self):
        p, self.picco = self.picco, 0.0
        return self._scala(self.livello), self._scala(p)

    def _scala(self, v):
        """Normalizza sul volume VERO di questo PC, non su un numero a caso.
        Misurato il 02/09: con Discord e Spotify i picchi stanno sotto 0.02,
        e con la scala precedente (0.07) non scattava mai niente."""
        return min(v / 0.018, 1.0)

    @property
    def picco_ora(self):
        return self._scala(self.picco)

    @property
    def c_e_suono(self):
        return (time.time() - self.ultimo_suono) < ATTESA_SILENZIO

    def ferma(self):
        self._vivo = False


# ----------------------------------------------------------------- effetti

class Effetto:
    """Un comportamento: date le condizioni, dice che colore fare adesso."""

    def __init__(self, nome):
        self.nome = nome
        self.tinta = random.random()
        self.altra = (self.tinta + random.uniform(0.25, 0.5)) % 1.0
        self.passo = 0
        self.acceso = True

    def colore(self, t, forza, picco, suono):
        self.passo += 1
        n = self.nome
        sat = 1.0
        v = 1.0

        if n == "scorre":
            self.tinta += (0.055 if suono else 0.016) + picco * 0.25
            v = MINIMO + (1 - MINIMO) * (0.6 + 0.4 * forza) + picco * 0.4

        elif n == "pulsa":
            self.tinta += 0.008 + picco * 0.05
            base = 0.5 + 0.5 * math.sin(t * (3.0 if suono else 0.8))
            v = MINIMO + (1 - MINIMO) * (0.35 + 0.65 * base) + picco * 0.5

        elif n == "lampeggia":
            # Non lampeggio di luminosita': tra 100% e 86% non si vedrebbe, e le
            # vuole sempre al massimo. Lampeggio saltando al colore OPPOSTO,
            # che si vede benissimo e resta pieno.
            if picco > 0.18 or (not suono and self.passo % 2 == 0):
                self.acceso = not self.acceso
                self.tinta = (self.tinta + 0.5) % 1.0
            v = 1.0 if self.acceso else MINIMO + 0.08
            sat = 1.0

        elif n == "salta":
            # cambia colore di netto a ogni colpo: e' quello che si vede di piu'
            if picco > 0.2 or self.passo % (2 if suono else 6) == 0:
                self.tinta = random.random()
            v = MINIMO + (1 - MINIMO) * (0.5 + 0.5 * forza) + picco * 0.5

        elif n == "alterna":
            # due colori che si scambiano, a tempo
            if picco > 0.22 or self.passo % (2 if suono else 5) == 0:
                self.tinta, self.altra = self.altra, self.tinta
            self.altra += 0.004
            v = MINIMO + (1 - MINIMO) * (0.6 + 0.4 * forza) + picco * 0.4

        elif n == "respira":
            self.tinta += 0.006
            base = 0.5 + 0.5 * math.sin(t * (1.6 if suono else 0.45))
            v = MINIMO + (1 - MINIMO) * (0.45 + 0.55 * base)
            sat = 0.9 + 0.1 * math.sin(t * 0.3)

        else:   # impazzisce
            self.tinta += random.uniform(-0.25, 0.35) + picco * 0.3
            v = MINIMO + (1 - MINIMO) * random.uniform(0.5, 1.0) + picco * 0.4
            sat = random.uniform(0.85, 1.0)

        r, g, b = colorsys.hsv_to_rgb(self.tinta % 1.0, sat, min(v, 1.0))
        return int(r * 255), int(g * 255), int(b * 255)


# ---------------------------------------------------------------- principale

def main():
    if not DLL.exists():
        print(f"manca la libreria MSI: {DLL}")
        return
    try:
        luce = Striscia()
    except (OSError, RuntimeError) as e:
        print(f"non riesco a parlare alla scheda: {e}")
        return
    try:
        orecchio = Orecchio()
    except RuntimeError as e:
        print(f"audio non disponibile: {e}")
        return

    print(f"LUCI attive sulla zona {ZONA}.  CTRL+C per fermare.")
    for s in orecchio.sorgenti:
        print(f"  ascolto: {s}")
    print(flush=True)

    print(f"effetti in rotazione: {len(MIEI) + len(CHIP)}")
    print(f"  che reagiscono al suono: {', '.join(MIEI)}")
    print(f"  animati dalla scheda:    {', '.join(CHIP)}")
    print(flush=True)

    mazzo = MIEI + CHIP
    random.shuffle(mazzo)
    primo = mazzo.pop()
    if primo in MIEI:
        effetto, stile_chip = Effetto(primo), None
        luce.pronta_per_colore()
        tipo = "reagisce al suono"
    else:
        effetto, stile_chip = Effetto(MIEI[0]), primo
        luce.stile(primo)
        tipo = "animato dalla scheda"
    fine = time.time() + random.uniform(*DURATA)
    t0 = time.time()
    scritte = 0
    ultimo_rapporto = 0.0
    print(f"[{time.strftime('%H:%M:%S')}] >>> {primo}  ({tipo})", flush=True)

    try:
        while True:
            adesso = time.time()
            suono = orecchio.c_e_suono

            # --- e' ora di cambiare effetto? -------------------------------
            # Li voglio TUTTI, in rotazione: i miei e quelli della scheda.
            # Si estrae dal mazzo completo, e quando il mazzo finisce si
            # rimescola: cosi' col tempo si vedono davvero tutti e 15, non
            # sempre gli stessi tre.
            if adesso > fine:
                if not mazzo:
                    mazzo = MIEI + CHIP
                    random.shuffle(mazzo)
                    print(f"[{time.strftime('%H:%M:%S')}] "
                          f"nuovo giro, {len(mazzo)} effetti mescolati", flush=True)
                scelto = mazzo.pop()

                if scelto in MIEI:
                    stile_chip = None
                    effetto = Effetto(scelto)
                    luce.pronta_per_colore()
                    tipo = "reagisce al suono"
                else:
                    stile_chip = scelto
                    luce.stile(scelto)
                    tipo = "animato dalla scheda"
                fine = adesso + random.uniform(*DURATA)
                print(f"[{time.strftime('%H:%M:%S')}] >>> {scelto}  ({tipo})"
                      f"   restano {len(mazzo)} nel mazzo", flush=True)

            # --- se comanda il chip, non devo fare niente ------------------
            if stile_chip:
                time.sleep(0.25)
                continue

            # --- aspetto il colpo, ma non oltre mezzo secondo --------------
            limite = adesso + 0.5
            while time.time() < limite and orecchio.picco_ora < COLPO:
                time.sleep(0.012)

            forza, picco = orecchio.leggi()
            r, g, b = effetto.colore(time.time() - t0, forza, picco, suono)
            esito = luce.colore(r, g, b)
            scritte += 1

            if time.time() - ultimo_rapporto > RAPPORTO:
                print(f"[{time.strftime('%H:%M:%S')}] {effetto.nome:<11} "
                      f"{'a ritmo' if suono else 'silenzio'}  "
                      f"suono {forza:4.2f} picco {picco:4.2f}  "
                      f"rgb ({r:3},{g:3},{b:3})  "
                      f"{scritte/max(time.time()-t0,0.001):4.1f}/s  "
                      f"{'ok' if esito == 0 else 'ERRORE ' + str(esito)}", flush=True)
                ultimo_rapporto = time.time()

    except KeyboardInterrupt:
        print("\nchiudo, ma le luci restano vive: passo la scheda su Rainbow, "
              "che gira da sola anche senza programmi accesi.")
    finally:
        orecchio.ferma()
        luce.stile("Rainbow")


if __name__ == "__main__":
    main()
