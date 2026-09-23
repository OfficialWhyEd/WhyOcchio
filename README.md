# WhyOcchio

**Give a coding agent eyes: a local webcam service that captures, analyses and serves frames so the agent can check the physical world (LEDs, screens, objects).**

Nato per un problema concreto: le luci RGB del PC non rispondevano e l'agente non poteva vederle.
Invece di chiedere ogni volta "di che colore sono?", Occhio guarda al posto suo.

| File | Cosa fa |
|---|---|
| `occhio.py` | il servizio: cattura dalla webcam, salva i fotogrammi |
| `web.py` | pagina locale per vedere la webcam anche dal telefono |
| `calibra.py`, `mappa.py` | calibrazione dell'inquadratura e mappa delle zone |
| `luci.py`, `analisi_luci.py`, `mystic.py` | legge colore e luminosità dei LED e li confronta con i comandi mandati |
| `guarda.py` | uno scatto al volo, per l'agente |

```
AVVIA OCCHIO.cmd   /   FERMA OCCHIO.cmd
```
Le catture restano sul PC e non entrano mai nel repo.

---

Parte di **[WhyEcosystem 2023-2026](https://github.com/OfficialWhyEd/WhyEcosystem-2023-2026)**: il percorso di WhyEd, producer e sound engineer che costruisce sistemi AI dirigendo gli agenti.  
Costruito da WhyEd con Claude Code
