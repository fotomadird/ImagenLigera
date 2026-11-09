"""Ventana principal de ImagenLigera (PySide6). Diseñado por Olivier Melín · tecmad.es"""
from __future__ import annotations

import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QIcon, QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QProgressBar, QPushButton, QSpinBox,
    QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import __version__
from . import compresor as C

APP = "ImagenLigera"
VERDE, ROJO = QColor("#1f9d55"), QColor("#d64545")

ESTILO = """
#zona { border: 2px dashed palette(mid); border-radius: 14px; }
#zona[activa="true"] { border-color: #2f6fed; background: rgba(47,111,237,0.07); }
#titulo { font-size: 20px; font-weight: 600; }
#aviso { font-size: 12px; }
#pie { font-size: 11px; }
#principal { background: #2f6fed; color: white; border: none; border-radius: 8px;
             padding: 9px 22px; font-weight: 600; }
#principal:hover { background: #2559c9; }
#principal:disabled { background: palette(mid); color: palette(window); }
#principal[parar="true"] { background: #d64545; }
"""


def tenue(w: QWidget) -> QWidget:
    pal = w.palette()
    pal.setColor(QPalette.ColorRole.WindowText, pal.color(QPalette.ColorRole.PlaceholderText))
    w.setPalette(pal)
    return w


def recurso(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)
    return str(Path(base) / rel)


class Trabajo(QThread):
    hecho = Signal(int, object)  # fila, Resultado

    def __init__(self, tareas, opciones: C.Opciones):
        super().__init__()
        self.tareas, self.opciones = tareas, opciones
        self._parar = threading.Event()

    def parar(self):
        self._parar.set()  # las que estén en marcha terminan; el resto se salta

    def _una(self, src, dst):
        if self._parar.is_set():
            return None
        return C.comprimir(src, dst, self.opciones)

    def run(self):
        hilos = max(1, min(4, (os.cpu_count() or 2) - 1))
        with ThreadPoolExecutor(max_workers=hilos) as ex:
            futuros = {ex.submit(self._una, src, dst): fila for fila, src, dst in self.tareas}
            for f in as_completed(futuros):
                r = f.result()
                if r is not None:
                    self.hecho.emit(futuros[f], r)


class Ventana(QMainWindow):
    COLS = ["Archivo", "Original", "Resultado", "Medidas", "Estado"]

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP)
        self.setWindowIcon(QIcon(recurso("assets/icon.png")))
        self.setAcceptDrops(True)
        self.resize(900, 620)
        self.cfg = QSettings("tecmad", APP)
        self.items: list[dict] = []   # {src, estado: pend|ok|err, res}
        self.trabajo: Trabajo | None = None
        self.carpeta: str | None = self.cfg.value("carpeta") or None
        if self.carpeta and not Path(self.carpeta).is_dir():
            self.carpeta = None
        self._construir()
        self._refrescar()

    # ------------------------------------------------------------- interfaz
    def _construir(self):
        raiz = QWidget()
        v = QVBoxLayout(raiz)
        v.setContentsMargins(20, 16, 20, 10)
        v.setSpacing(10)

        t = QLabel(APP); t.setObjectName("titulo")
        s = QLabel("Fotos ligeras para la web: arrastra, elige formato y pulsa Comprimir.")
        s.setObjectName("sub")
        v.addWidget(t); v.addWidget(tenue(s))

        # Botones de añadir
        fila = QHBoxLayout()
        self.b_fotos = QPushButton("Añadir fotos…")
        self.b_carpeta_in = QPushButton("Añadir carpeta…")
        self.b_vaciar = QPushButton("Vaciar lista")
        self.b_fotos.clicked.connect(self._elegir_fotos)
        self.b_carpeta_in.clicked.connect(self._elegir_carpeta_in)
        self.b_vaciar.clicked.connect(self._vaciar)
        fila.addWidget(self.b_fotos); fila.addWidget(self.b_carpeta_in)
        fila.addStretch(1); fila.addWidget(self.b_vaciar)
        v.addLayout(fila)

        # Zona de arrastre / tabla
        self.pila = QStackedWidget()
        self.zona = QFrame(); self.zona.setObjectName("zona")
        zl = QVBoxLayout(self.zona)
        z = QLabel("Arrastra aquí tus fotos o carpetas\n\nJPG · PNG · WEBP · HEIC · TIFF · BMP · GIF"
                   if C.HEIC_OK else
                   "Arrastra aquí tus fotos o carpetas\n\nJPG · PNG · WEBP · TIFF · BMP · GIF")
        z.setAlignment(Qt.AlignCenter)
        f = z.font(); f.setPointSizeF(f.pointSizeF() * 1.25); z.setFont(f)
        zl.addWidget(z)

        self.tabla = QTableWidget(0, len(self.COLS))
        self.tabla.setHorizontalHeaderLabels(self.COLS)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setAlternatingRowColors(True)
        h = self.tabla.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, len(self.COLS)):
            h.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.tabla.cellDoubleClicked.connect(self._abrir_fila)
        QShortcut(QKeySequence(QKeySequence.StandardKey.Delete), self.tabla, activated=self._quitar_seleccion)
        QShortcut(QKeySequence(Qt.Key_Backspace), self.tabla, activated=self._quitar_seleccion)

        self.pila.addWidget(self.zona); self.pila.addWidget(self.tabla)
        v.addWidget(self.pila, 1)

        # Opciones
        op = QHBoxLayout(); op.setSpacing(8)
        self.c_formato = QComboBox()
        for txt, val in (("WEBP (recomendado)", "WEBP"), ("JPG", "JPG"), ("PNG (logos y gráficos)", "PNG")):
            self.c_formato.addItem(txt, val)
        self.c_formato.setCurrentIndex(max(0, self.c_formato.findData(self.cfg.value("formato", "WEBP"))))

        self.s_peso = QSpinBox(); self.s_peso.setRange(20, 10000); self.s_peso.setSuffix(" KB")
        self.s_peso.setSingleStep(10); self.s_peso.setValue(int(self.cfg.value("peso", 250)))

        self.c_lado = QComboBox()
        for txt, val in (("Sin límite", 0), ("1200 px", 1200), ("1600 px", 1600),
                         ("1920 px (recomendado)", 1920), ("2560 px", 2560)):
            self.c_lado.addItem(txt, val)
        self.c_lado.setCurrentIndex(max(0, self.c_lado.findData(int(self.cfg.value("lado", 1920)))))

        self.k_nombres = QCheckBox("Nombres aptos para web")
        self.k_nombres.setToolTip("Sin espacios, tildes ni mayúsculas: «Foto Boda Año 1.JPG» → «foto-boda-ano-1.webp»")
        self.k_nombres.setChecked(self.cfg.value("nombres", "true") in (True, "true"))

        for w, lbl in ((self.c_formato, "Formato"), (self.s_peso, "Peso máximo"), (self.c_lado, "Lado máximo")):
            op.addWidget(QLabel(lbl)); op.addWidget(w); op.addSpacing(8)
        op.addWidget(self.k_nombres); op.addStretch(1)
        v.addLayout(op)

        self.aviso = QLabel("PNG no es ideal para fotos: para llegar al peso se reducen colores y tamaño. "
                            "Para fotos usa WEBP o JPG.")
        self.aviso.setObjectName("aviso"); self.aviso.setWordWrap(True); tenue(self.aviso)
        v.addWidget(self.aviso)

        # Carpeta de salida
        sal = QHBoxLayout()
        self.e_salida = QLineEdit(); self.e_salida.setReadOnly(True)
        self.b_salida = QPushButton("Elegir…"); self.b_salida.clicked.connect(self._elegir_salida)
        self.b_salida_def = QPushButton("Por defecto"); self.b_salida_def.clicked.connect(self._salida_defecto)
        sal.addWidget(QLabel("Guardar en")); sal.addWidget(self.e_salida, 1)
        sal.addWidget(self.b_salida); sal.addWidget(self.b_salida_def)
        v.addLayout(sal)

        # Progreso y acciones
        self.progreso = QProgressBar(); self.progreso.setTextVisible(True)
        v.addWidget(self.progreso)
        acc = QHBoxLayout()
        self.resumen = QLabel("")
        self.b_abrir = QPushButton("Abrir carpeta"); self.b_abrir.clicked.connect(self._abrir_salida)
        self.b_go = QPushButton("Comprimir"); self.b_go.setObjectName("principal")
        self.b_go.clicked.connect(self._pulsar_principal)
        acc.addWidget(self.resumen, 1); acc.addWidget(self.b_abrir); acc.addWidget(self.b_go)
        v.addLayout(acc)

        pie = QLabel(f"Diseñado por Olivier Melín · tecmad.es  —  v{__version__}")
        pie.setObjectName("pie"); pie.setAlignment(Qt.AlignRight); tenue(pie)
        v.addWidget(pie)

        self.setCentralWidget(raiz)
        self.setStyleSheet(ESTILO)
        for w in (self.c_formato, self.c_lado):
            w.currentIndexChanged.connect(self._guardar_cfg)
        self.s_peso.valueChanged.connect(self._guardar_cfg)
        self.k_nombres.toggled.connect(self._guardar_cfg)

    # -------------------------------------------------------------- estado
    def _opciones(self) -> C.Opciones:
        return C.Opciones(
            formato=self.c_formato.currentData(),
            max_bytes=self.s_peso.value() * 1000,
            lado_max=int(self.c_lado.currentData()),
            nombres_web=self.k_nombres.isChecked(),
            carpeta=self.carpeta,
        )

    def _guardar_cfg(self, *_):
        self.cfg.setValue("formato", self.c_formato.currentData())
        self.cfg.setValue("peso", self.s_peso.value())
        self.cfg.setValue("lado", int(self.c_lado.currentData()))
        self.cfg.setValue("nombres", "true" if self.k_nombres.isChecked() else "false")
        self.cfg.setValue("carpeta", self.carpeta or "")
        self._refrescar()

    def _pendientes(self) -> list[int]:
        return [i for i, it in enumerate(self.items) if it["estado"] != "ok"]

    def _refrescar(self):
        ocupado = self.trabajo is not None
        n = len(self._pendientes())
        self.pila.setCurrentIndex(1 if self.items else 0)
        self.aviso.setVisible(self.c_formato.currentData() == "PNG")
        self.e_salida.setText(self.carpeta or f"Subcarpeta «{C.CARPETA_SALIDA}» junto a cada foto")
        self.b_salida_def.setEnabled(bool(self.carpeta) and not ocupado)
        for w in (self.b_fotos, self.b_carpeta_in, self.b_vaciar, self.c_formato, self.s_peso,
                  self.c_lado, self.k_nombres, self.b_salida):
            w.setEnabled(not ocupado)
        self.b_vaciar.setEnabled(bool(self.items) and not ocupado)
        self.b_abrir.setEnabled(any(it["estado"] == "ok" for it in self.items))
        self.b_go.setProperty("parar", ocupado)
        if ocupado:
            self.b_go.setText("Detener"); self.b_go.setEnabled(True)
        else:
            self.b_go.setText(f"Comprimir {n} foto{'s' if n != 1 else ''}" if n else "Comprimir")
            self.b_go.setEnabled(n > 0)
        self.b_go.style().unpolish(self.b_go); self.b_go.style().polish(self.b_go)

    # ------------------------------------------------------------- entrada
    def agregar(self, rutas: list[str]):
        if self.trabajo:
            return
        ya = {str(it["src"]).lower() for it in self.items}
        nuevos = [p for p in C.recopilar(rutas) if str(p).lower() not in ya]
        for p in nuevos:
            fila = self.tabla.rowCount()
            self.tabla.insertRow(fila)
            try:
                peso = C.formato_peso(p.stat().st_size)
            except OSError:
                peso = "?"
            vals = [p.name, peso, "", "", "Pendiente"]
            for c, val in enumerate(vals):
                it = QTableWidgetItem(val)
                if c in (1, 2):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if c == 0:
                    it.setToolTip(str(p))
                self.tabla.setItem(fila, c, it)
            self.items.append({"src": p, "estado": "pend", "res": None})
        if rutas and not nuevos and not self.items:
            self.resumen.setText("No se encontraron imágenes compatibles.")
        self._refrescar()

    def _elegir_fotos(self):
        ext = " ".join(f"*{e}" for e in sorted(C.EXTENSIONES))
        archivos, _ = QFileDialog.getOpenFileNames(self, "Elegir fotos", self._dir_inicial(),
                                                    f"Imágenes ({ext} {ext.upper()})")
        if archivos:
            self.cfg.setValue("ultima", str(Path(archivos[0]).parent))
            self.agregar(archivos)

    def _elegir_carpeta_in(self):
        d = QFileDialog.getExistingDirectory(self, "Elegir carpeta con fotos", self._dir_inicial())
        if d:
            self.cfg.setValue("ultima", d)
            self.agregar([d])

    def _dir_inicial(self) -> str:
        d = self.cfg.value("ultima") or ""
        return d if d and Path(d).is_dir() else str(Path.home())

    def _vaciar(self):
        self.items.clear(); self.tabla.setRowCount(0)
        self.progreso.reset(); self.resumen.setText("")
        self._refrescar()

    def _quitar_seleccion(self):
        if self.trabajo:
            return
        for fila in sorted({i.row() for i in self.tabla.selectedIndexes()}, reverse=True):
            self.tabla.removeRow(fila); del self.items[fila]
        self._refrescar()

    def dragEnterEvent(self, e):
        if not self.trabajo and e.mimeData().hasUrls():
            e.acceptProposedAction(); self._zona_activa(True)

    def dragLeaveEvent(self, e):
        self._zona_activa(False)

    def dropEvent(self, e):
        self._zona_activa(False)
        rutas = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if rutas:
            e.acceptProposedAction(); self.agregar(rutas)

    def _zona_activa(self, on: bool):
        self.zona.setProperty("activa", on)
        self.zona.style().unpolish(self.zona); self.zona.style().polish(self.zona)

    # -------------------------------------------------------------- salida
    def _elegir_salida(self):
        d = QFileDialog.getExistingDirectory(self, "Guardar las fotos comprimidas en…",
                                             self.carpeta or self._dir_inicial())
        if d:
            self.carpeta = d; self._guardar_cfg()

    def _salida_defecto(self):
        self.carpeta = None; self._guardar_cfg()

    def _abrir_salida(self):
        hechos = [it for it in self.items if it["estado"] == "ok"]
        d = self.carpeta or (str(Path(hechos[-1]["res"].destino).parent) if hechos else None)
        if d:
            QDesktopServices.openUrl(QUrl.fromLocalFile(d))

    def _abrir_fila(self, fila, _col):
        it = self.items[fila]
        ruta = it["res"].destino if it["estado"] == "ok" else str(it["src"])
        QDesktopServices.openUrl(QUrl.fromLocalFile(ruta))

    # ------------------------------------------------------------ proceso
    def _pulsar_principal(self):
        if self.trabajo:
            self.b_go.setEnabled(False); self.b_go.setText("Deteniendo…")
            self.trabajo.parar()
            return
        filas = self._pendientes()
        if not filas:
            return
        op = self._opciones()
        destinos = C.reservar_destinos([self.items[i]["src"] for i in filas], op)
        tareas = [(i, self.items[i]["src"], d) for i, d in zip(filas, destinos)]
        for i in filas:
            self._celda(i, 4, "En cola…")
            self._celda(i, 2, ""); self._celda(i, 3, "")
        self.progreso.setRange(0, len(tareas)); self.progreso.setValue(0)
        self.progreso.setFormat("%v / %m")
        self.resumen.setText("Comprimiendo…")
        self.trabajo = Trabajo(tareas, op)
        self.trabajo.hecho.connect(self._uno_hecho)
        self.trabajo.finished.connect(self._fin)
        self._refrescar()
        self.trabajo.start()

    def _celda(self, fila, col, txt, color: QColor | None = None):
        it = self.tabla.item(fila, col)
        it.setText(txt)
        it.setForeground(QBrush(color) if color else QBrush())

    def _uno_hecho(self, fila: int, r: C.Resultado):
        it = self.items[fila]
        it["res"] = r
        if r.ok:
            it["estado"] = "ok"
            self._celda(fila, 2, C.formato_peso(r.peso_final), VERDE)
            self._celda(fila, 3, f"{r.ancho}×{r.alto}")
            self._celda(fila, 4, f"✓ {r.detalle}", VERDE)
        else:
            it["estado"] = "err"
            if r.peso_final:
                self._celda(fila, 2, C.formato_peso(r.peso_final), ROJO)
            self._celda(fila, 4, f"✗ {r.error}", ROJO)
            self.tabla.item(fila, 4).setToolTip(r.error)
        self.progreso.setValue(self.progreso.value() + 1)

    def _fin(self):
        self.trabajo.deleteLater(); self.trabajo = None
        for i in self._pendientes():
            if self.items[i]["estado"] == "pend":
                self._celda(i, 4, "Pendiente")
        ok = [it["res"] for it in self.items if it["estado"] == "ok"]
        err = sum(1 for it in self.items if it["estado"] == "err")
        if ok:
            antes = sum(r.peso_original for r in ok)
            despues = sum(r.peso_final for r in ok)
            ahorro = round(100 * (1 - despues / antes)) if antes else 0
            txt = (f"{len(ok)} foto{'s' if len(ok) != 1 else ''} · {C.formato_peso(antes)} → "
                   f"{C.formato_peso(despues)} (−{ahorro} %)")
            if err:
                txt += f" · {err} con error"
            self.resumen.setText(txt)
        else:
            self.resumen.setText(f"{err} con error" if err else "Detenido")
        self._refrescar()

    def closeEvent(self, e):
        if self.trabajo:
            self.trabajo.parar(); self.trabajo.wait()
        super().closeEvent(e)


def main():
    if sys.platform == "win32":  # icono propio en la barra de tareas
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("tecmad.imagenligera")
        except Exception:  # noqa: BLE001
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP)
    app.setOrganizationName("tecmad")
    w = Ventana()
    w.show()
    rutas = [a for a in sys.argv[1:] if Path(a).exists()]  # arrastrar sobre el .exe
    if rutas:
        w.agregar(rutas)
    sys.exit(app.exec())
