"""
MYSTIC - parla alla scheda madre MSI e le dice che colore fare.

Usa la libreria ufficiale MSI (MysticLight_SDK_x64.dll, firmata Micro-Star,
verificata secondo la Regola 1). Serve girare da amministratore.

Scoperta che costa sangue: per scrivere un colore la zona deve prima essere
messa su "NoAnimation". Se non lo fai, SetLedColor risponde -103 e non succede niente.

By WhyEd
"""

import ctypes
from pathlib import Path

DLL = Path(__file__).parent / "sdk" / "MysticLight_SDK_x64.dll"

_ole = ctypes.WinDLL("oleaut32")
_ole.SysAllocString.restype = ctypes.c_void_p
_ole.SysAllocString.argtypes = [ctypes.c_wchar_p]
_ole.SysFreeString.argtypes = [ctypes.c_void_p]


class ErroreMystic(Exception):
    pass


class Mystic:
    """La scheda madre, vista come una fila di zone a cui dare un colore."""

    def __init__(self):
        if not DLL.exists():
            raise ErroreMystic(f"manca la libreria: {DLL}")
        self.dll = ctypes.WinDLL(str(DLL))

        r = self.dll.MLAPI_Initialize()
        if r != 0:
            raise ErroreMystic(
                f"MLAPI_Initialize ha risposto {r}. "
                "Di solito vuol dire che manca l'amministratore o Mystic Light non e' installato.")

        self.dll.MLAPI_SetLedColor.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                               ctypes.c_int, ctypes.c_int, ctypes.c_int]
        self.dll.MLAPI_SetLedStyle.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                               ctypes.c_void_p]
        # la versione veloce: l'ultimo parametro e' "aspetta la scheda".
        # Con 0 non aspetta, e passa da 702 ms a 31 ms per zona (misurato).
        self.dll.MLAPI_SetLedColorEx.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                                 ctypes.c_void_p, ctypes.c_int,
                                                 ctypes.c_int, ctypes.c_int, ctypes.c_int]
        self.dll.MLAPI_GetDeviceInfo.argtypes = [ctypes.POINTER(ctypes.c_void_p),
                                                 ctypes.POINTER(ctypes.c_void_p)]

        self.dispositivo, self.zone = self._cerca_dispositivo()
        self._preparate = set()
        # BSTR allocate una volta sola e riusate: allocarle a ogni scrittura costa
        self._dev = _ole.SysAllocString(self.dispositivo)
        self._stile = _ole.SysAllocString("NoAnimation")

    # ------------------------------------------------------------------

    def _leggi_array(self, sa):
        fuori = []
        if not sa:
            return fuori
        lb, ub = ctypes.c_long(), ctypes.c_long()
        _ole.SafeArrayGetLBound(sa, 1, ctypes.byref(lb))
        _ole.SafeArrayGetUBound(sa, 1, ctypes.byref(ub))
        for i in range(lb.value, ub.value + 1):
            elem = ctypes.c_void_p()
            idx = ctypes.c_long(i)
            _ole.SafeArrayGetElement(sa, ctypes.byref(idx), ctypes.byref(elem))
            fuori.append(ctypes.cast(elem, ctypes.c_wchar_p).value if elem else None)
        return fuori

    def _cerca_dispositivo(self):
        tipi, conteggi = ctypes.c_void_p(), ctypes.c_void_p()
        r = self.dll.MLAPI_GetDeviceInfo(ctypes.byref(tipi), ctypes.byref(conteggi))
        if r != 0:
            raise ErroreMystic(f"MLAPI_GetDeviceInfo ha risposto {r}")
        nomi = self._leggi_array(tipi)
        quanti = self._leggi_array(conteggi)
        if not nomi:
            raise ErroreMystic("nessun dispositivo MSI trovato")
        try:
            n = int(quanti[0])
        except (TypeError, ValueError, IndexError):
            n = 1
        # l'ultima zona rifiuta sempre la scrittura su questa scheda: la escludo
        return nomi[0], max(n - 1, 1)

    # ------------------------------------------------------------------

    def _prepara(self, i):
        """Mette la zona su NoAnimation: senza questo il colore non entra."""
        if i in self._preparate:
            return
        self.dll.MLAPI_SetLedStyle(self._dev, i, self._stile)
        self._preparate.add(i)

    def colore(self, i, r, g, b):
        """Colore su una zona sola. Usa la via veloce che non aspetta la scheda."""
        self._prepara(i)
        return self.dll.MLAPI_SetLedColorEx(self._dev, i, self._stile,
                                            int(r), int(g), int(b), 0)

    def tutte(self, r, g, b):
        """Stesso colore su tutte le zone."""
        for i in range(self.zone):
            self.colore(i, r, g, b)

    def fila(self, colori):
        """Un colore diverso per ogni zona: colori = [(r,g,b), ...]."""
        for i, c in enumerate(colori[:self.zone]):
            self.colore(i, *c)

    def spegni(self):
        self.tutte(0, 0, 0)


if __name__ == "__main__":
    m = Mystic()
    print(f"dispositivo: {m.dispositivo}   zone scrivibili: {m.zone}")
    import time
    for c, nome in [((255, 0, 0), "rosso"), ((0, 255, 0), "verde"), ((0, 0, 255), "blu")]:
        print(f"  {nome}")
        m.tutte(*c)
        time.sleep(1.2)
