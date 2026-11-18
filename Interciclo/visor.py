"""Canvas con coordenadas SUMO y mapa opcional de geometría vial."""
import json
from pathlib import Path
import tkinter as tk
from configuracion import PARADAS, ARCHIVO_MAPA


class VisorSimulacion(tk.Canvas):
    def __init__(self, master):
        super().__init__(master, bg="#e8eceb", highlightthickness=0)
        self.parada = "P1"
        self.buses = []
        self.calles = []
        self._cargar_mapa()
        self.bind("<Configure>", lambda event: self.dibujar())

    def _cargar_mapa(self):
        archivo = Path(__file__).resolve().parent / ARCHIVO_MAPA
        if archivo.exists():
            try:
                datos = json.loads(archivo.read_text(encoding="utf-8"))
                self.calles = datos.get("calles", [])
            except (OSError, ValueError):
                self.calles = []

    def seleccionar(self, parada):
        self.parada = parada
        self.dibujar()

    def actualizar_buses(self, buses):
        self.buses = list(buses)
        self.dibujar()

    def _limites(self):
        puntos = [(d["x"], d["y"]) for d in PARADAS.values()]
        puntos += [(b["x"], b["y"]) for b in self.buses]
        for calle in self.calles:
            puntos.extend((float(x), float(y)) for x, y in calle)
        if not puntos:
            return 7200, 8700, 8750, 9400
        xs, ys = zip(*puntos)
        # En ausencia del mapa, mantener un encuadre estable del tramo.
        if not self.calles:
            return 7300, 8750, 8700, 9250
        return min(xs), min(ys), max(xs), max(ys)

    def dibujar(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 80 or h < 80:
            return
        xmin, ymin, xmax, ymax = self._limites()
        margen = 28
        escala = min((w-2*margen)/max(1, xmax-xmin),
                     (h-2*margen)/max(1, ymax-ymin))
        cx, cy = (xmin+xmax)/2, (ymin+ymax)/2

        def proyectar(x, y):
            return w/2+(x-cx)*escala, h/2-(y-cy)*escala

        if self.calles:
            for calle in self.calles:
                if len(calle) >= 2:
                    coords = [v for p in calle for v in proyectar(*p)]
                    self.create_line(*coords, fill="#c4cecb", width=3,
                                     capstyle="round", joinstyle="round")
        else:
            # Ruta central aproximada; no se presenta como cartografía real.
            coords = [v for p in PARADAS.values()
                      for v in proyectar(p["x"], p["y"])]
            self.create_line(*coords, fill="#94a3b8", width=5)
            self.create_text(12, h-12, anchor="sw", fill="#64748b",
                             text="Mapa esquemático: falta mapa_linea3.json")

        for nombre, p in PARADAS.items():
            x, y = proyectar(p["x"], p["y"])
            elegido = nombre == self.parada
            self.create_oval(x-9, y-9, x+9, y+9,
                             fill="#2563eb" if elegido else "white",
                             outline="#1d4ed8", width=3)
            self.create_text(x+12, y-15, text=nombre, anchor="w",
                             fill="#1e3a8a", font=("Arial", 11, "bold"))

        for bus in self.buses:
            if not bus.get("visible_mapa", True):
                continue
            x, y = proyectar(bus["x"], bus["y"])
            relevante = self.parada in bus["paradas_pendientes"]
            color = "#dc2626" if relevante else "#94a3b8"
            self.create_rectangle(x-7, y-12, x+7, y+12,
                                  fill=color, outline="#334155", width=1)
            self.create_text(x, y-19, text=bus["id"].replace("bus_", ""),
                             fill="#0f172a", font=("Arial", 9, "bold"))

        self.create_rectangle(10, 10, 290, 38, fill="white", outline="")
        self.create_text(18, 24, anchor="w", fill="#334155",
                         text="Rojo: llega a tu parada  ·  Gris: ya pasó")
