#!/bin/sh
# Собирает из dist/DocForge два Linux-артефакта: переносимый .tar.gz и установщик .run.
# Использование: packaging/linux/make-run.sh <версия> [каталог_вывода]
set -e
VERSION="${1:?укажите версию}"
OUT="${2:-output}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ARCH=x86_64
NAME="DocForge-$VERSION-linux-$ARCH"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

[ -d "$ROOT/dist/DocForge" ] || { echo "Нет dist/DocForge — сначала pyinstaller" >&2; exit 1; }
mkdir -p "$OUT" "$STAGE/$NAME"
cp -a "$ROOT/dist/DocForge/." "$STAGE/$NAME/"
cp "$ROOT/docforge/resources/icon.png" "$STAGE/$NAME/icon.png"
cp "$ROOT/packaging/linux/docforge.desktop" "$STAGE/$NAME/docforge.desktop"
cp "$ROOT/LICENSE" "$STAGE/$NAME/LICENSE"
chmod +x "$STAGE/$NAME/DocForge"

# переносимый архив: распаковать и запустить ./DocForge
cat > "$STAGE/$NAME/README.txt" <<TXT
DocForge $VERSION (Linux, $ARCH)
Запуск: ./DocForge
Для ярлыка в меню приложений используйте установщик .run.
TXT
tar czf "$OUT/$NAME.tar.gz" -C "$STAGE" "$NAME"

# установщик: скрипт-заголовок + тот же архив
sed "s|@VERSION@|$VERSION|g" "$ROOT/packaging/linux/run-header.sh" > "$STAGE/header.sh"
cat "$STAGE/header.sh" "$OUT/$NAME.tar.gz" > "$OUT/$NAME.run"
chmod +x "$OUT/$NAME.run"
echo "Готово: $OUT/$NAME.tar.gz  $OUT/$NAME.run"
