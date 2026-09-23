"""
WEB - la vista dell'OCCHIO sul telefono, dentro casa.

Apre un piccolo server sulla rete locale. Dal telefono, collegato allo stesso
wifi, apri l'indirizzo che ti stampa e vedi la stessa cosa che vede Claude:
video dal vivo, mirino, e lo stato delle luci aggiornato.

Non esce niente su internet: e' solo la tua rete di casa.

By WhyEd
"""

import json
import socket
import threading
import time

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

PORTA = 8099
SCHERMO_FPS = 6          # bastano per seguire, e non pesano sul PC
SCHERMO_LARGO = 1100     # ridimensionato per il telefono

# l'ultimo fotogramma annotato, riempito da occhio.py
_ultimo = {"jpg": None, "stato": {}}
_schermo = {"jpg": None}
_lucchetto = threading.Lock()


def _cattura_schermo():
    """Gira per conto suo e tiene aggiornata l'ultima foto dello schermo."""
    import mss
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        pausa = 1.0 / SCHERMO_FPS
        while True:
            try:
                grezzo = np.asarray(sct.grab(monitor))[:, :, :3]
                h, w = grezzo.shape[:2]
                if w > SCHERMO_LARGO:
                    k = SCHERMO_LARGO / w
                    grezzo = cv2.resize(grezzo, (SCHERMO_LARGO, int(h * k)),
                                        interpolation=cv2.INTER_AREA)
                ok, buf = cv2.imencode(".jpg", grezzo,
                                       [cv2.IMWRITE_JPEG_QUALITY, 62])
                if ok:
                    with _lucchetto:
                        _schermo["jpg"] = buf.tobytes()
            except Exception:
                pass
            time.sleep(pausa)


def aggiorna(frame, stato):
    """Chiamata da occhio.py a ogni fotogramma."""
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
    if ok:
        with _lucchetto:
            _ultimo["jpg"] = buf.tobytes()
            _ultimo["stato"] = stato


def indirizzo_locale():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


PAGINA = """<!doctype html><html lang="it"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>OCCHIO</title><style>
*{box-sizing:border-box}
body{margin:0;background:#0b0b0d;color:#e8e8ea;font:15px/1.5 -apple-system,system-ui,sans-serif}
header{padding:14px 16px;border-bottom:1px solid #232327;display:flex;
 align-items:center;gap:10px}
h1{margin:0;font-size:16px;letter-spacing:.14em;font-weight:600}
.pallino{width:9px;height:9px;border-radius:50%;background:#2ecc71;
 box-shadow:0 0 10px #2ecc71}
img{width:100%;display:block;background:#000}
.titolo{padding:10px 16px 6px;font-size:11px;letter-spacing:.18em;
 color:#7a7a83;text-transform:uppercase;border-top:1px solid #1c1c20}
.stato{padding:16px}
.grande{font-size:26px;font-weight:700;letter-spacing:.04em;margin:0 0 4px}
.nota{color:#8a8a92;margin:0 0 16px}
table{width:100%;border-collapse:collapse;font-size:14px}
td{padding:7px 0;border-bottom:1px solid #1c1c20}
td:last-child{text-align:right;color:#b9b9c0;font-variant-numeric:tabular-nums}
</style></head><body>
<header><span class="pallino"></span><h1>OCCHIO</h1></header>
<img src="/flusso" alt="webcam dal vivo">
<img src="/schermo" alt="schermo del PC">
<div class="stato">
 <p class="grande" id="s">...</p>
 <p class="nota" id="d"></p>
 <table id="t"></table>
</div>
<script>
const ETI={luminosita:"luminosita",oscillazione:"oscillazione",hz:"ritmo (Hz)",
 picco:"nettezza del picco",saturazione:"saturazione",
 giro_colore_gradi:"giro del colore",fps:"fotogrammi al secondo"};
const COL={SPENTE:"#6b6b73",FISSE:"#ffffff",RESPIRO:"#ffc46b",
 LAMPEGGIO:"#ffb02e",ARCOBALENO:"#ff5cf0","A RITMO":"#39d98a"};
async function giro(){
 try{
  const r=await fetch("/stato",{cache:"no-store"}), j=await r.json();
  const L=j.luci_rgb||{};
  const s=document.getElementById("s");
  s.textContent=L.stato||"...";
  s.style.color=COL[L.stato]||"#e8e8ea";
  document.getElementById("d").textContent=L.descrizione||"";
  document.getElementById("t").innerHTML=Object.keys(ETI)
   .filter(k=>L[k]!==undefined)
   .map(k=>`<tr><td>${ETI[k]}</td><td>${L[k]}</td></tr>`).join("");
 }catch(e){}
 setTimeout(giro,1000);
}
giro();
</script></body></html>"""


class Gestore(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass                                  # niente rumore in console

    def do_GET(self):
        if self.path == "/":
            corpo = PAGINA.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        elif self.path == "/stato":
            with _lucchetto:
                corpo = json.dumps(_ultimo["stato"]).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        elif self.path in ("/flusso", "/schermo"):
            sorgente = _ultimo if self.path == "/flusso" else _schermo
            self.send_response(200)
            self.send_header(
                "Content-Type", "multipart/x-mixed-replace; boundary=fotogramma")
            self.end_headers()
            try:
                while True:
                    with _lucchetto:
                        jpg = sorgente["jpg"]
                    if jpg:
                        self.wfile.write(b"--fotogramma\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(
                            f"Content-Length: {len(jpg)}\r\n\r\n".encode())
                        self.wfile.write(jpg)
                        self.wfile.write(b"\r\n")
                    threading.Event().wait(0.05)
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_error(404)


def avvia():
    """Fa partire il server in un thread e stampa l'indirizzo per il telefono."""
    srv = ThreadingHTTPServer(("0.0.0.0", PORTA), Gestore)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    threading.Thread(target=_cattura_schermo, daemon=True).start()
    ind = f"http://{indirizzo_locale()}:{PORTA}"
    print(f"OCCHIO sul telefono: {ind}")
    return ind
