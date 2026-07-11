#!/usr/bin/env sh
# Сборка статической вики Cognopolis (MYH-86) ОДНОЙ командой: ./build.sh
# Результат — site/ (готовый HTML для kindomklaster.com/wiki).
#
# Контент не трогаем: README.md стейджится как index.md (ссылки docs/… укорачиваются),
# docs/ копируется как есть в .build/docs — оттуда mkdocs и собирает.
# Зависимости: uv (тогда ничего ставить не надо) ИЛИ установленный mkdocs-material
# (pip install -r requirements.txt).
set -eu
cd "$(dirname "$0")"

rm -rf .build site
mkdir -p .build/docs
cp -R docs/. .build/docs/
# README — обложка репо → главная страница вики; её ссылки вида (docs/…) становятся (…).
sed 's|](docs/|](|g' README.md > .build/docs/index.md

if command -v uv >/dev/null 2>&1; then
    uv tool run --from 'mkdocs>=1.6,<2' --with 'mkdocs-material>=9.5,<10' mkdocs build
else
    mkdocs build
fi

echo "OK: $(find site -name '*.html' -not -path '*/assets/*' | wc -l | tr -d ' ') HTML-страниц в site/"
