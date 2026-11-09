# ImagenLigera 1.0

Compresor de fotos para web (Windows y macOS). Cada imagen sale con **0,25 MB como máximo**
(configurable) en **WEBP, JPG o PNG**, con la mejor calidad posible.

Diseñado por Olivier Melín · tecmad.es

## Compilar en Windows
1. Instala **Python 3.10 o superior** desde python.org (marca *Add python.exe to PATH*).
2. Doble clic en **`compilar_windows.bat`**.
3. Resultado: `dist\ImagenLigera.exe` (un único archivo, no necesita instalación).

## Compilar en Mac
1. Instala **Python 3.12** desde python.org (recomendado: así la app funciona desde macOS 12).
2. En Terminal, dentro de esta carpeta: `bash compilar_mac.sh`
3. Resultado: `dist/ImagenLigera.app` y `dist/ImagenLigera-1.0.0-mac-arm64.dmg`
   (o `-x86_64` si se compila en un Mac Intel). Cada Mac necesita la versión de su procesador.

## Compilar los dos sin tener Mac (GitHub)
1. Sube esta carpeta a un repositorio de GitHub (puede ser privado).
2. Pestaña **Actions → Compilar ImagenLigera → Run workflow**.
3. En unos 10 min, al pie de la ejecución, en *Artifacts*: el `.exe` de Windows y los `.dmg`
   de Mac Apple Silicon e Intel.

## Primer arranque en el ordenador de la clienta
La app no está firmada con certificado de pago, así que el sistema avisa la primera vez:
- **Windows**: «Windows protegió su PC» → *Más información* → *Ejecutar de todas formas*.
- **Mac**: abrir el DMG y arrastrar la app a Aplicaciones. Al abrirla y salir el aviso:
  *Ajustes del Sistema → Privacidad y seguridad → «Abrir igualmente»*.
  Si dijera que está «dañada»: en Terminal `xattr -cr /Applications/ImagenLigera.app`

## Uso
1. Arrastrar fotos o carpetas a la ventana (o *Añadir fotos… / Añadir carpeta…*).
2. Elegir formato (WEBP recomendado), peso máximo (250 KB) y lado máximo (1920 px recomendado).
3. **Comprimir**. Las fotos se guardan en la subcarpeta `optimizadas` junto a las originales
   (o en la carpeta elegida). **Nunca se tocan las originales.**

Doble clic en una fila abre la foto comprimida. Supr/Retroceso quita filas de la lista.
La app recuerda los últimos ajustes.

## Cómo comprime
- **WEBP / JPG**: busca la calidad más alta que cabe en el peso; si ni con calidad mínima
  (50 JPG / 45 WEBP) entra, reduce la resolución lo justo y repite.
- **PNG**: primero sin pérdida; si no cabe, 256 colores; si aún no, reduce resolución.
  PNG es para logos y gráficos; para fotos, WEBP o JPG dan mucha más calidad con el mismo peso.
- Corrige la orientación de las fotos de móvil, convierte a sRGB, quita datos EXIF/GPS,
  aplana transparencias sobre blanco en JPG y lee HEIC de iPhone.
- Si una foto ya era del mismo formato, cumplía el peso y no había que reducirla, se copia
  tal cual para no empeorarla.

## Estructura
```
main.py                     arranque
imagenligera/compresor.py   motor de compresión (Pillow)
imagenligera/ventana.py     interfaz (PySide6)
ImagenLigera.spec           receta de PyInstaller (Windows y Mac)
compilar_windows.bat        compila el .exe
compilar_mac.sh             compila la .app y el .dmg
.github/workflows/          compilación automática en GitHub
assets/                     iconos
```
Para cambiar la versión: `imagenligera/__init__.py`.
