#!/bin/sh
# DocForge @VERSION@ — самораспаковывающийся установщик для Linux (x86_64).
#   ./DocForge-@VERSION@-linux-x86_64.run              установка для текущего пользователя (~/.local/share/DocForge)
#   sudo ./DocForge-….run                              установка для всех (/opt/DocForge)
#   ./DocForge-….run --target DIR                      установка в указанную папку
#   ./DocForge-….run --extract DIR                     только распаковать (без ярлыков)
#   ./DocForge-….run --uninstall [--target DIR]        удалить
set -e
NAME=DocForge
VERSION="@VERSION@"
TARGET=""
MODE=install

while [ $# -gt 0 ]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --extract) MODE=extract; TARGET="$2"; shift 2 ;;
    --uninstall) MODE=uninstall; shift ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "Неизвестный параметр: $1" >&2; exit 2 ;;
  esac
done

if [ "$(id -u)" = "0" ]; then
  SYSTEM=1
  DEFAULT_TARGET=/opt/$NAME
  BIN_DIR=/usr/local/bin
  APP_DIR=/usr/share/applications
else
  SYSTEM=0
  DEFAULT_TARGET="${XDG_DATA_HOME:-$HOME/.local/share}/$NAME"
  BIN_DIR="$HOME/.local/bin"
  APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
fi
[ -n "$TARGET" ] || TARGET="$DEFAULT_TARGET"

if [ "$MODE" = "uninstall" ]; then
  rm -f "$BIN_DIR/docforge" "$APP_DIR/docforge.desktop"
  rm -rf "$TARGET"
  command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
  echo "$NAME удалён."
  exit 0
fi

LINE=$(awk '/^__PAYLOAD_BELOW__$/ { print NR + 1; exit 0 }' "$0")
mkdir -p "$TARGET"
echo "Распаковка в $TARGET …"
tail -n +"$LINE" "$0" | tar xz -C "$TARGET" --strip-components=1

if [ "$MODE" = "extract" ]; then
  echo "Готово: $TARGET/DocForge"
  exit 0
fi

mkdir -p "$BIN_DIR" "$APP_DIR"
ln -sf "$TARGET/DocForge" "$BIN_DIR/docforge"
sed -e "s|@EXEC@|$TARGET/DocForge|" -e "s|@ICON@|$TARGET/icon.png|" "$TARGET/docforge.desktop" > "$APP_DIR/docforge.desktop"
chmod 644 "$APP_DIR/docforge.desktop"
cat > "$TARGET/uninstall.sh" <<UNINSTALL
#!/bin/sh
rm -f "$BIN_DIR/docforge" "$APP_DIR/docforge.desktop"
rm -rf "$TARGET"
echo "$NAME удалён."
UNINSTALL
chmod +x "$TARGET/uninstall.sh"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true

echo "$NAME $VERSION установлен."
echo "  Запуск: docforge   (или из меню приложений)"
echo "  Удаление: $TARGET/uninstall.sh"
case ":$PATH:" in *":$BIN_DIR:"*) ;; *) echo "  Примечание: $BIN_DIR нет в PATH — запускайте из меню приложений или $TARGET/DocForge" ;; esac
exit 0
__PAYLOAD_BELOW__
