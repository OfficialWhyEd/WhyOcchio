# WhyOcchio

**Give a coding agent eyes: a local webcam service that watches the physical world and tells the agent what it sees. Plus the RGB light engine it was built to debug.**

`Python` · `OpenCV` · `NumPy` · `soundcard` · `MSI Mystic Light SDK` · stato: **funzionante**

Le luci RGB del PC non rispondevano e l'agente non poteva vederle. Invece di chiedere ogni volta "di che
colore sono?", Occhio guarda al posto suo, capisce cosa stanno facendo le luci e lo scrive in un file.

## Cosa fa
- **guarda dalla webcam**: movimento, volti, colore dominante descritto a parole, mirino sul bersaglio principale;
- **salva solo i momenti importanti** in `catture/` e scrive lo stato in `visione.json`, che l'agente legge;
- **riconosce lo stato delle luci**: spente, fisse, respiro, lampeggio (con la frequenza in Hz), arcobaleno, a ritmo di musica;
- **pagina web locale** sulla porta 8099: la webcam si vede anche dal telefono;
- **comanda le luci della scheda madre** e le fa ballare con la musica e la voce, mai ferme.

## Come funziona
```
webcam ─► occhio.py ─► movimento, volti, colore ─► visione.json + catture/ ─► l'agente legge
                    └► analisi_luci.py: FFT sulla luminosità, rotazione della tonalità, irregolarità
                    └► web.py ─► http://PC:8099 (telefono)

audio di sistema (loopback) ─► luci.py ─► colpo di cassa ─► mystic.py ─► LED della scheda madre
```
Una scrittura di colore sul chip costa circa 660 ms, quindi `luci.py` non scrive a orologio: aspetta il colpo e
scrive subito, così il colore scatta insieme alla cassa. Quando c'è silenzio passa agli effetti del chip, più fluidi.

## Struttura
| File | Cosa fa |
|---|---|
| `occhio.py` | il servizio: cattura, analisi, salvataggi, `visione.json` |
| `analisi_luci.py` | capisce lo stato delle luci riprese |
| `web.py` | pagina locale sulla porta 8099 |
| `guarda.py` | legge un fotogramma dal servizio, per l'agente |
| `mystic.py` | ponte Python verso l'SDK MSI Mystic Light |
| `calibra.py` | accende una zona per volta e impara dalla webcam dove sta (`zone.json`) |
| `mappa.py`, `_mappa.cmd` | mappa zona dell'SDK e punto fisico |
| `luci.py` | il motore delle luci: stili a caso, a ritmo di musica e voce |
| `AVVIA OCCHIO.cmd`, `FERMA OCCHIO.cmd` | avvio e arresto con un doppio clic |

## Come si avvia
```
pip install opencv-python numpy soundcard
python occhio.py        # oppure doppio clic su AVVIA OCCHIO.cmd
python luci.py          # il motore delle luci, serve l'amministratore
```
Per le luci serve `MysticLight_SDK_x64.dll` di MSI accanto agli script. Prima di dare un colore a una zona va
messa in modalità `NoAnimation`, altrimenti l'SDK risponde -103.

## Stato
Funziona e ha dato la risposta che serviva: le 8 zone dell'SDK accendono tutte **lo stesso punto**. Non sono luci
in fila, quindi onde e arcobaleni che scorrono sono impossibili; si può variare solo nel tempo. Il motore delle
luci è costruito su questa misura.

## Perché è nato
Un agente che non vede non può verificare il proprio lavoro sul mondo fisico. Con Occhio può accendere una luce,
guardarla e sapere se ha funzionato, senza chiedere niente a nessuno.

---

Parte di **[WhyEcosystem 2023-2026](https://github.com/OfficialWhyEd/WhyEcosystem-2023-2026)**: il percorso di WhyEd, producer e sound engineer che costruisce sistemi AI dirigendo gli agenti.  
Costruito da WhyEd con Claude Code
