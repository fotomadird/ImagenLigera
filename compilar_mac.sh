#!/bin/bash
# ImagenLigera: compila la app de macOS (.app) y la empaqueta en un .dmg
# Uso: abre Terminal en esta carpeta y ejecuta:  bash compilar_mac.sh
set -euo pipefail
cd "$(dirname "$0")"

APP="ImagenLigera"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' imagenligera/__init__.py)"
PY="${PYTHON:-python3}"

echo "=== $APP $VERSION: compilando para macOS ($(uname -m)) ==="
command -v "$PY" >/dev/null || { echo "Instala Python 3.10+ desde python.org"; exit 1; }
"$PY" --version

[ -x .venv-mac/bin/python ] || "$PY" -m venv .venv-mac
source .venv-mac/bin/activate
python -m pip install --upgrade pip >/dev/null

# Con Python <= 3.13 se usa Qt 6.8 LTS: la app funciona desde macOS 12
PIN=""
if python -c 'import sys; sys.exit(0 if sys.version_info < (3, 14) else 1)'; then
  PIN="PySide6-Essentials>=6.8,<6.9"
fi
pip install -r requirements.txt $PIN

pyinstaller --noconfirm --clean ImagenLigera.spec

# DMG con acceso directo a Aplicaciones
DMG="dist/$APP-$VERSION-mac-$(uname -m).dmg"
rm -rf dist/dmg "$DMG"
mkdir -p dist/dmg
ditto "dist/$APP.app" "dist/dmg/$APP.app"
ln -s /Applications dist/dmg/Aplicaciones
for i in 1 2 3; do
  hdiutil create -volname "$APP" -srcfolder dist/dmg -ov -format UDZO "$DMG" && break
  echo "hdiutil ocupado, reintento $i…"; sleep 5
done
rm -rf dist/dmg
[ -f "$DMG" ] || { echo "No se pudo crear el DMG (la app sí está en dist/$APP.app)"; exit 1; }

echo
echo "Listo:"
echo "  App: $(pwd)/dist/$APP.app"
echo "  DMG: $(pwd)/$DMG"
