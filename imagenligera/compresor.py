"""Motor de compresión de ImagenLigera.

Objetivo: que cada imagen ocupe como máximo `max_bytes`, con la mejor calidad posible.
- JPG / WEBP: búsqueda binaria de calidad; si ni con la calidad mínima entra, reduce resolución.
- PNG: sin pérdida optimizado -> 256 colores -> reduce resolución.
Diseñado por Olivier Melín · tecmad.es
"""
from __future__ import annotations

import io
import math
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError, features

# HEIC/HEIF (fotos de iPhone) si el plugin está disponible
try:  # pragma: no cover - depende de la plataforma
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIC_OK = True
except Exception:  # noqa: BLE001
    HEIC_OK = False

Image.MAX_IMAGE_PIXELS = 300_000_000  # fotos panorámicas grandes

EXTENSIONES = {".jpg", ".jpeg", ".jpe", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
if HEIC_OK:
    EXTENSIONES |= {".heic", ".heif"}

FORMATOS = {"WEBP": ".webp", "JPG": ".jpg", "PNG": ".png"}
CARPETA_SALIDA = "optimizadas"

# Rangos de calidad: por debajo del mínimo se prefiere reducir tamaño de imagen
Q_RANGO = {"JPG": (50, 92), "WEBP": (45, 90)}
LADO_MINIMO = 64


@dataclass
class Opciones:
    formato: str = "WEBP"          # WEBP | JPG | PNG
    max_bytes: int = 250_000       # 0,25 MB
    lado_max: int = 1920           # 0 = sin límite
    nombres_web: bool = True
    carpeta: str | None = None     # None = subcarpeta "optimizadas" junto a cada original


@dataclass
class Resultado:
    origen: str
    destino: str = ""
    peso_original: int = 0
    peso_final: int = 0
    ancho: int = 0
    alto: int = 0
    detalle: str = ""
    ok: bool = False
    error: str = ""


# ----------------------------------------------------------------- utilidades
def nombre_web(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t.lower()).strip("-")
    return t or "imagen"


def carpeta_destino(origen: Path, opciones: Opciones) -> Path:
    if opciones.carpeta:
        return Path(opciones.carpeta)
    return origen.parent / CARPETA_SALIDA


def reservar_destinos(origenes: list[Path], opciones: Opciones) -> list[Path]:
    """Calcula nombres de salida únicos (sin pisar archivos existentes ni entre sí)."""
    ext = FORMATOS[opciones.formato]
    usados: set[str] = set()
    salida: list[Path] = []
    for src in origenes:
        carpeta = carpeta_destino(src, opciones)
        base = nombre_web(src.stem) if opciones.nombres_web else src.stem
        n = 1
        while True:
            nombre = f"{base}{ext}" if n == 1 else f"{base}-{n}{ext}"
            dst = carpeta / nombre
            clave = str(dst).lower()
            if clave not in usados and not dst.exists():
                break
            n += 1
        usados.add(clave)
        salida.append(dst)
    return salida


def recopilar(rutas: list[str]) -> list[Path]:
    """Expande carpetas (recursivo) y filtra por extensión admitida."""
    vistos: set[str] = set()
    res: list[Path] = []

    def add(p: Path):
        k = str(p.resolve()).lower()
        if k not in vistos and p.suffix.lower() in EXTENSIONES and not p.name.startswith("."):
            vistos.add(k)
            res.append(p)

    for r in rutas:
        p = Path(r)
        if p.is_dir():
            for raiz, dirs, archivos in os.walk(p):
                dirs[:] = [d for d in dirs if d != CARPETA_SALIDA and not d.startswith(".")]
                for a in sorted(archivos):
                    add(Path(raiz) / a)
        elif p.is_file():
            add(p)
    return res


# ------------------------------------------------------------------- lectura
def _a_srgb(img: Image.Image) -> tuple[Image.Image, bytes | None]:
    """Convierte a sRGB si trae otro perfil ICC. Devuelve (imagen, icc_a_conservar)."""
    icc = img.info.get("icc_profile")
    if not icc:
        return img, None
    try:
        src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        desc = (ImageCms.getProfileDescription(src) or "").lower()
    except Exception:  # noqa: BLE001 - perfil ilegible: se descarta
        return img, None
    if "srgb" in desc and img.mode != "CMYK":
        return img, None
    try:
        modo_sal = "RGBA" if img.mode == "RGBA" else "RGB"
        dst = ImageCms.createProfile("sRGB")
        return ImageCms.profileToProfile(img, src, dst, outputMode=modo_sal), None
    except Exception:  # noqa: BLE001 - no convertible: se conserva el perfil
        return img, icc


def abrir(ruta: Path, lado_max: int):
    """Devuelve (imagen RGB/RGBA en sRGB, icc a conservar, formato, tamaño y si trae metadatos)."""
    with Image.open(ruta) as img:  # cierra el archivo (Windows no lo deja bloqueado)
        meta = (img.format or "", img.size, bool(img.info.get("exif") or img.info.get("xmp")))
        return (*_normalizar(img, lado_max), *meta)


def _normalizar(img: Image.Image, lado_max: int) -> tuple[Image.Image, bytes | None]:
    try:
        img.seek(0)  # GIF/WEBP animados: primer fotograma
    except Exception:  # noqa: BLE001
        pass
    if lado_max and img.format == "JPEG":
        img.draft(None, (lado_max, lado_max))  # decodificación rápida a escala
    img.load()
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:  # noqa: BLE001
        pass

    # Normalizar modo
    if img.mode in ("I;16", "I;16B", "I;16L", "I", "F"):
        img = img.convert("I").point(lambda v: v * (1 / 256)).convert("L")
    if img.mode == "CMYK":
        img, icc = _a_srgb(img)
        if img.mode != "RGB":
            img = img.convert("RGB")
        return img, icc
    tiene_alfa = img.mode in ("RGBA", "LA", "PA") or (
        img.mode == "P" and "transparency" in img.info
    )
    img = img.convert("RGBA" if tiene_alfa else "RGB")
    if tiene_alfa and img.getextrema()[3][0] == 255:
        img = img.convert("RGB")  # canal alfa totalmente opaco: se descarta
    return _a_srgb(img)


# ---------------------------------------------------------------- codificado
def _guardar(img: Image.Image, formato: str, calidad: int | None, icc: bytes | None) -> bytes:
    buf = io.BytesIO()
    extra = {"icc_profile": icc} if icc else {}
    if formato == "JPG":
        img.save(buf, "JPEG", quality=calidad, optimize=True, progressive=True,
                 subsampling=2, **extra)
    elif formato == "WEBP":
        img.save(buf, "WEBP", quality=calidad, method=4, **extra)
    else:
        img.save(buf, "PNG", optimize=True, **extra)
    return buf.getvalue()


def _reducir(img: Image.Image, factor: float) -> Image.Image:
    w, h = img.size
    nw, nh = max(1, round(w * factor)), max(1, round(h * factor))
    return img.resize((nw, nh), Image.Resampling.LANCZOS)


def _factor(peso: int, objetivo: int) -> float:
    # el peso escala ~ con el nº de píxeles -> raíz cuadrada; margen 5 %
    return max(0.5, min(0.92, math.sqrt(objetivo / peso) * 0.95))


def _con_perdida(img, formato, objetivo, icc):
    qmin, qmax = Q_RANGO[formato]
    if formato == "JPG" and img.mode == "RGBA":
        fondo = Image.new("RGB", img.size, (255, 255, 255))
        fondo.paste(img, mask=img.getchannel("A"))
        img = fondo
    while True:
        minimo = _guardar(img, formato, qmin, icc)
        if len(minimo) > objetivo:
            if max(img.size) <= LADO_MINIMO:
                return minimo, img, qmin
            img = _reducir(img, _factor(len(minimo), objetivo))
            continue
        datos = _guardar(img, formato, qmax, icc)
        if len(datos) <= objetivo:
            return datos, img, qmax
        lo, hi, mejor = qmin, qmax, minimo  # lo cabe, hi no
        while hi - lo > 1:
            mid = (lo + hi) // 2
            d = _guardar(img, formato, mid, icc)
            if len(d) <= objetivo:
                lo, mejor = mid, d
            else:
                hi = mid
        return mejor, img, lo


def _cuantizar(img: Image.Image) -> Image.Image:
    if features.check_feature("libimagequant"):
        metodo = Image.Quantize.LIBIMAGEQUANT
    elif img.mode == "RGBA":
        metodo = Image.Quantize.FASTOCTREE
    else:
        metodo = Image.Quantize.MEDIANCUT
    return img.quantize(colors=256, method=metodo)


def _png(img, objetivo, icc):
    # estimación rápida: si ni de lejos cabe sin pérdida, no se pierde tiempo optimizando
    buf = io.BytesIO()
    img.save(buf, "PNG", compress_level=1)
    if buf.tell() < objetivo * 1.6:
        datos = _guardar(img, "PNG", None, icc)
        if len(datos) <= objetivo:
            return datos, img, "sin pérdida"
    while True:
        datos = _guardar(_cuantizar(img), "PNG", None, icc)
        if len(datos) <= objetivo or max(img.size) <= LADO_MINIMO:
            return datos, img, "256 colores"
        img = _reducir(img, max(0.3, min(0.92, math.sqrt(objetivo / len(datos)) * 0.95)))


# ------------------------------------------------------------------ pública
def comprimir(origen: Path, destino: Path, opciones: Opciones) -> Resultado:
    r = Resultado(origen=str(origen), destino=str(destino))
    try:
        r.peso_original = origen.stat().st_size
        img, icc, fmt_origen, tam_origen, con_meta = abrir(origen, opciones.lado_max)
        if opciones.lado_max and max(img.size) > opciones.lado_max:
            img.thumbnail((opciones.lado_max, opciones.lado_max), Image.Resampling.LANCZOS)

        if opciones.formato == "PNG":
            datos, final, info = _png(img, opciones.max_bytes, icc)
            r.detalle = info
        else:
            datos, final, q = _con_perdida(img, opciones.formato, opciones.max_bytes, icc)
            r.detalle = f"calidad {q}"

        # Si la original ya era del mismo formato, ligera, del mismo tamaño y sin metadatos
        # (EXIF/GPS), se copia tal cual para no empeorarla
        if (_MISMO.get(fmt_origen) == opciones.formato and not con_meta
                and r.peso_original <= min(len(datos), opciones.max_bytes)
                and sorted(final.size) == sorted(tam_origen)):
            datos = origen.read_bytes()
            r.detalle = "ya era ligera"

        destino.parent.mkdir(parents=True, exist_ok=True)
        tmp = destino.with_name(destino.name + ".tmp")
        tmp.write_bytes(datos)
        os.replace(tmp, destino)

        r.peso_final = len(datos)
        r.ancho, r.alto = final.size
        r.ok = r.peso_final <= opciones.max_bytes
        if not r.ok:
            r.error = "No se pudo bajar del límite"
    except UnidentifiedImageError:
        r.error = "No es una imagen válida o está dañada"
    except Image.DecompressionBombError:
        r.error = "Imagen demasiado grande"
    except PermissionError:
        r.error = "Sin permiso para leer o guardar"
    except MemoryError:
        r.error = "Sin memoria suficiente para esta imagen"
    except Exception as e:  # noqa: BLE001
        r.error = str(e) or e.__class__.__name__
    return r


_MISMO = {"JPEG": "JPG", "MPO": "JPG", "WEBP": "WEBP", "PNG": "PNG"}


def formato_peso(n: int) -> str:
    if n < 1_000_000:
        return f"{n / 1000:.0f} KB"
    return f"{n / 1_000_000:.1f} MB".replace(".", ",")
