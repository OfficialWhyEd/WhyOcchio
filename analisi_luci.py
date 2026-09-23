"""
ANALISI LUCI - capisce da sola in che stato sono le luci RGB riprese dalla webcam.

Riconosce:
    SPENTE      buio, nessuna luce
    FISSE       un colore che non cambia
    RESPIRO     la luminosita' sale e scende piano, colore fermo
    LAMPEGGIO   accende e spegne a una frequenza precisa (te la dice in Hz)
    ARCOBALENO  il colore ruota in continuazione lungo la ruota dei colori
    A RITMO     varia forte ma senza una frequenza fissa: sta seguendo la musica

Come lo fa, tre misure diverse messe insieme:
    1. FFT sulla luminosita' nel tempo  -> trova la frequenza del lampeggio
    2. rotazione della tonalita' in HSV -> trova l'arcobaleno (il colore che gira)
    3. irregolarita' della variazione    -> distingue la musica da un lampeggio fisso

By WhyEd
"""

import numpy as np
import cv2
from collections import deque

# soglie, tarate su webcam a 20 fps in stanza buia
BUIO = 12.0             # sotto questa luminosita' media: spente
FERMO_V = 3.0           # deviazione della luminosita' sotto cui e' "fissa"
FERMO_H = 4.0           # deviazione della tonalita' sotto cui il colore e' fermo
GIRO_MINIMO = 25.0      # gradi di rotazione tonalita' per parlare di arcobaleno
PICCO_FFT = 3.0         # quanto il picco deve superare il fondo per essere un ritmo
MIN_CAMPIONI = 40


class AnalisiLuci:
    """Accumula i fotogrammi e a richiesta dice in che stato sono le luci."""

    def __init__(self, secondi=5.0, fps_attesi=20.0):
        self.n = max(int(secondi * fps_attesi), MIN_CAMPIONI)
        self.v = deque(maxlen=self.n)      # luminosita'
        self.h = deque(maxlen=self.n)      # tonalita' (0-179 in OpenCV)
        self.s = deque(maxlen=self.n)      # saturazione
        self.t = deque(maxlen=self.n)      # istanti
        self.bgr = (0, 0, 0)

    # ------------------------------------------------------------- raccolta

    def aggiungi(self, frame, istante, riquadro=None):
        """Campiona un fotogramma. riquadro = (x, y, w, h) per guardare solo li'."""
        if riquadro:
            x, y, w, h = riquadro
            frame = frame[y:y + h, x:x + w]
        if frame.size == 0:
            return

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        vch = hsv[:, :, 2]

        # guardo solo i pixel accesi: il nero attorno falserebbe la tonalita'
        accesi = vch > 40
        quanti = int(accesi.sum())

        if quanti < 30:
            self.v.append(float(vch.mean()))
            self.h.append(np.nan)
            self.s.append(0.0)
        else:
            self.v.append(float(vch[accesi].mean()))
            # tonalita' come media circolare: 179 e 0 sono vicini, non lontani
            ang = hsv[:, :, 0][accesi].astype(np.float32) * (2 * np.pi / 180.0)
            mx, my = np.cos(ang).mean(), np.sin(ang).mean()
            self.h.append((np.degrees(np.arctan2(my, mx)) % 360.0) / 2.0)
            self.s.append(float(hsv[:, :, 1][accesi].mean()))
            self.bgr = tuple(int(c) for c in frame.reshape(-1, 3)[accesi.ravel()].mean(axis=0))

        self.t.append(istante)

    @property
    def pronto(self):
        return len(self.v) >= MIN_CAMPIONI

    # -------------------------------------------------------------- misure

    def _fps_reale(self):
        if len(self.t) < 2:
            return 0.0
        durata = self.t[-1] - self.t[0]
        return (len(self.t) - 1) / durata if durata > 0 else 0.0

    def _frequenza(self, serie, fps):
        """FFT: restituisce (hz del picco, quanto il picco spicca sul fondo)."""
        x = np.asarray(serie, dtype=np.float64)
        x = x - x.mean()
        if len(x) < MIN_CAMPIONI or fps <= 0 or np.allclose(x, 0):
            return 0.0, 0.0
        x = x * np.hanning(len(x))
        spettro = np.abs(np.fft.rfft(x))
        freq = np.fft.rfftfreq(len(x), d=1.0 / fps)
        # ignoro la continua e le frequenze sopra Nyquist utile
        valide = (freq > 0.25) & (freq < fps / 2.5)
        if not valide.any():
            return 0.0, 0.0
        spettro, freq = spettro[valide], freq[valide]
        i = int(np.argmax(spettro))
        fondo = np.median(spettro) or 1e-9
        return float(freq[i]), float(spettro[i] / fondo)

    def _rotazione_tonalita(self):
        """Quanti gradi ha girato il colore, e se gira sempre nello stesso verso."""
        h = np.asarray([x for x in self.h if not np.isnan(x)], dtype=np.float64)
        if len(h) < MIN_CAMPIONI // 2:
            return 0.0, 0.0
        gradi = h * 2.0
        d = np.diff(gradi)
        d = (d + 180.0) % 360.0 - 180.0     # differenza sul cerchio
        giro = float(np.abs(d).sum())
        verso = float(abs(d.sum()) / (np.abs(d).sum() + 1e-9))   # 1 = sempre stesso verso
        return giro, verso

    # ------------------------------------------------------------ verdetto

    def verdetto(self):
        if not self.pronto:
            return {"stato": "sto guardando", "sicurezza": 0.0}

        fps = self._fps_reale()
        v = np.asarray(self.v, dtype=np.float64)
        v_media, v_dev = float(v.mean()), float(v.std())
        giro, verso = self._rotazione_tonalita()
        hz, spicco = self._frequenza(v, fps)

        h_validi = [x for x in self.h if not np.isnan(x)]
        h_dev = float(np.std(np.asarray(h_validi) * 2.0)) if len(h_validi) > 5 else 0.0
        s_media = float(np.mean(self.s)) if self.s else 0.0

        dati = {
            "luminosita": round(v_media, 1),
            "oscillazione": round(v_dev, 1),
            "giro_colore_gradi": round(giro, 1),
            "verso_costante": round(verso, 2),
            "hz": round(hz, 2),
            "picco": round(spicco, 1),
            "saturazione": round(s_media, 1),
            "fps": round(fps, 1),
            "bgr": list(self.bgr),
        }

        # 1. spente
        if v_media < BUIO:
            return {"stato": "SPENTE", "sicurezza": 0.95, **dati}

        # 2. arcobaleno: il colore gira tanto e quasi sempre nello stesso verso
        if giro > GIRO_MINIMO * (len(self.v) / self.n) and verso > 0.35 and s_media > 60:
            return {"stato": "ARCOBALENO", "sicurezza": min(0.6 + verso / 2, 0.98), **dati}

        # 3. lampeggio: picco netto nello spettro.
        # sopra 2 Hz e' troppo veloce per un effetto della scheda: sta seguendo un suono
        if spicco > PICCO_FFT and v_dev > FERMO_V * 1.3 and hz > 0.4:
            if hz > 2.0:
                return {"stato": "A RITMO", "sicurezza": min(spicco / 8, 0.95),
                        "descrizione": f"segue la musica, {hz:.1f} impulsi al secondo",
                        **dati}
            return {"stato": "LAMPEGGIO", "sicurezza": min(spicco / 10, 0.97),
                    "descrizione": f"lampeggia a {hz:.1f} volte al secondo", **dati}

        # 4. respiro: oscilla piano, colore fermo, senza picco netto
        if v_dev > FERMO_V and h_dev < FERMO_H and hz < 1.2:
            return {"stato": "RESPIRO", "sicurezza": 0.75, **dati}

        # 5. a ritmo: varia forte ma in modo irregolare
        if v_dev > FERMO_V * 2.5 and spicco <= PICCO_FFT:
            return {"stato": "A RITMO", "sicurezza": 0.7,
                    "descrizione": "varia senza una cadenza fissa: sta seguendo un suono", **dati}

        # 6. altrimenti e' ferma
        return {"stato": "FISSE", "sicurezza": 0.85, **dati}


def nome_tonalita(gradi):
    """Da gradi di tonalita' al nome del colore."""
    tabella = [(15, "rosso"), (45, "arancione"), (70, "giallo"), (160, "verde"),
               (200, "ciano"), (260, "blu"), (290, "viola"), (330, "magenta"), (360, "rosso")]
    g = gradi % 360
    for limite, nome in tabella:
        if g < limite:
            return nome
    return "rosso"
