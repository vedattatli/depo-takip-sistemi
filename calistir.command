#!/bin/zsh
# Redecor Depo - cift tiklayarak calistirma dosyasi
cd "$(dirname "$0")" || exit 1

if [ ! -d ".venv" ]; then
  echo "Sanal ortam kuruluyor..."
  python3 -m venv .venv || exit 1
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet -r gereksinimler.txt || exit 1
fi

if [ ! -f "veri/depo.db" ]; then
  echo "Ilk kurulum yapiliyor..."
  ./.venv/bin/python kurulum.py
fi

echo ""
echo "================================================"
echo "  REDECOR DEPO calisiyor"
echo "  Tarayicida acin:  http://127.0.0.1:5051"
echo "  Durdurmak icin bu pencerede Ctrl+C yapin"
echo "================================================"
echo ""

( sleep 2 && open "http://127.0.0.1:5051" ) &
./.venv/bin/python app.py
