#!/usr/bin/env bash
# Собирает фильтры печати foo2zjs, foo2xqx, foo2qpdl, foo2slx, foo2lava для ПК в build/filters/.
# Linux: нужен gcc. Windows: запускать в оболочке MSYS2 (MINGW64) с пакетом mingw-w64-x86_64-gcc.
# Ошибка одного фильтра не останавливает остальные; без исходников программа просто соберётся без этих драйверов
# (в окне печати они будут помечены «нет в этой сборке», остальные способы работают).
set -u
cd "$(dirname "$0")/.."

SRC=build-drivers/foo2zjs
OUT=build/filters
CC="${CC:-gcc}"
FILTERS="foo2zjs foo2xqx foo2qpdl foo2slx foo2lava"
SUFFIX=""
EXTRA=""
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) SUFFIX=".exe"; EXTRA="-static" ;;  # без зависимости от DLL компилятора
esac

if ! command -v "$CC" >/dev/null 2>&1; then
  echo "::warning::Компилятор $CC не найден, фильтры печати не собраны"
  exit 0
fi
if [ ! -f "$SRC/foo2zjs.c" ]; then
  rm -rf "$SRC"
  mkdir -p build-drivers
  echo "Скачиваю исходники foo2zjs…"
  git clone --depth 1 https://github.com/koenkooi/foo2zjs.git "$SRC" 2>/dev/null \
    || { curl -fsSL http://foo2zjs.rkkda.com/foo2zjs.tar.gz | tar xz -C build-drivers; }
fi
if [ ! -f "$SRC/foo2zjs.c" ]; then
  echo "::warning::Исходники foo2zjs не скачались, фильтры печати не собраны"
  exit 0
fi

mkdir -p "$OUT"
built=""
for name in $FILTERS; do
  srcs="$SRC/$name.c"
  [ -f "$srcs" ] || { echo "  $name: нет файла $name.c"; continue; }
  for extra in jbig.c jbig_ar.c; do [ -f "$SRC/$extra" ] && srcs="$srcs $SRC/$extra"; done
  log="$(mktemp)"
  # -w и gnu99: исходники старые, современный компилятор иначе ругается на неявные объявления функций
  if "$CC" -O2 -w -std=gnu99 -D_GNU_SOURCE -I"$SRC" $EXTRA -o "$OUT/$name$SUFFIX" $srcs -lm 2>"$log"; then
    strip "$OUT/$name$SUFFIX" 2>/dev/null || true
    echo "  $name: собран"
    built="$built $name"
  else
    echo "  $name: не собрался, пропускаю"
    tail -n 5 "$log"
    rm -f "$OUT/$name$SUFFIX"
  fi
  rm -f "$log"
done
if [ -z "$built" ]; then
  echo "::warning::Ни один фильтр печати не собрался, программа будет без них"
else
  echo "Собрано:$built"
fi
exit 0
