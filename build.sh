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
# Публичная вики — ТОЛЬКО игроку (решение автора 2026-07-12): раздел разработчика —
# внутренний, движок не выкладываем. Страницы остаются в docs/ для команды.
rm -rf '.build/docs/04-разработчику'
# Главная вики — docs/index.md (обложка с плитками и скриншотом), она копируется вместе с docs/.
# README.md остаётся обложкой РЕПО для GitHub: там нет разметки Material, зато читается без рендера.
# Если своей главной нет — падаем на старое поведение: README стейджится как index (ссылки (docs/…)
# укорачиваются, блоки <!-- wiki:internal-start/end --> вырезаются).
if [ ! -f docs/index.md ]; then
    sed 's|](docs/|](|g' README.md | sed '/wiki:internal-start/,/wiki:internal-end/d' > .build/docs/index.md
fi

if command -v uv >/dev/null 2>&1; then
    uv tool run --from 'mkdocs>=1.6,<2' --with 'mkdocs-material>=9.5,<10' \
        --with 'mkdocs-glightbox>=0.4,<1' mkdocs build
else
    mkdocs build
fi

echo "OK: $(find site -name '*.html' -not -path '*/assets/*' | wc -l | tr -d ' ') HTML-страниц в site/"
