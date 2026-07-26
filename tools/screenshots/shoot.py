"""Снимает экраны Cognopolis с обводками-выносками для вики.

Каждый кадр описывается декларативно: маршрут SPA, что подготовить кликами, что обвести.
Обводка рисуется в самой странице (DOM-оверлей) — линии выходят векторно-чёткими,
а номера на обводках совпадают с нумерованной легендой под картинкой в вики.

Запуск:  uv run --quiet --with playwright --with pillow python shoot.py [имя кадра ...]
"""
import io
import json
import pathlib
import sys

from PIL import Image
from playwright.sync_api import sync_playwright

BASE = "https://kindomklaster.com"
OUT = pathlib.Path(__file__).resolve().parents[2] / "docs" / "assets" / "img"
OUT.mkdir(exist_ok=True)

VIEWPORT = {"width": 1280, "height": 1000}
DSF = 2
TARGET_WIDTH = 1600  # ширина картинки в вики (2x к типичной колонке)

# ── рисование обводок ────────────────────────────────────────────────────────
OVERLAY_JS = """
({boxes, dim}) => {
  document.querySelectorAll('.wiki-callout-layer').forEach(n => n.remove());
  const layer = document.createElement('div');
  layer.className = 'wiki-callout-layer';
  layer.style.cssText = 'position:fixed;inset:0;z-index:99999;pointer-events:none';
  if (dim) {
    const veil = document.createElement('div');
    veil.style.cssText = 'position:absolute;inset:0;background:rgba(0,0,0,.45)';
    layer.appendChild(veil);
  }
  boxes.forEach((b, i) => {
    const pad = b.pad === undefined ? 8 : b.pad;
    const x = b.x - pad, y = b.y - pad, w = b.width + pad * 2, h = b.height + pad * 2;
    if (dim) {
      const hole = document.createElement('div');
      hole.style.cssText = `position:absolute;left:${x}px;top:${y}px;width:${w}px;height:${h}px;
        border-radius:12px;box-shadow:0 0 0 9999px rgba(0,0,0,0);background:transparent;
        backdrop-filter:brightness(1.9) saturate(1.15)`;
      layer.appendChild(hole);
    }
    const box = document.createElement('div');
    box.style.cssText = `position:absolute;left:${x}px;top:${y}px;width:${w}px;height:${h}px;
      border:3px solid #f2a03d;border-radius:12px;
      box-shadow:0 0 0 2px rgba(0,0,0,.75), 0 0 22px rgba(242,160,61,.45)`;
    layer.appendChild(box);
    if (b.n) {
      const side = b.side || 'left';
      const badge = document.createElement('div');
      let bx = side === 'right' ? x + w + 5 : x - 35;
      bx = Math.min(Math.max(bx, 3), window.innerWidth - 33);
      badge.textContent = b.n;
      const by = Math.min(Math.max(y + h / 2 - 15, 3), window.innerHeight - 33);
      badge.style.cssText = `position:absolute;left:${bx}px;top:${by}px;width:30px;height:30px;
        border-radius:50%;background:#f2a03d;color:#1a1206;font:700 17px/30px -apple-system,
        'Segoe UI',system-ui,sans-serif;text-align:center;
        box-shadow:0 2px 8px rgba(0,0,0,.8), 0 0 0 2px rgba(0,0,0,.55)`;
      layer.appendChild(badge);
    }
  });
  document.body.appendChild(layer);
}
"""

MASK_JS = """
(sels) => {
  sels.forEach(s => document.querySelectorAll(s).forEach(el => {
    el.style.filter = 'blur(7px)';
  }));
}
"""


def locate(page, sel):
    """'t:Текст' — по тексту, 'e:Точный текст' — точное совпадение, иначе CSS."""
    if sel.startswith("t:"):
        return page.get_by_text(sel[2:], exact=False).first
    if sel.startswith("e:"):
        return page.get_by_text(sel[2:], exact=True).first
    if sel.startswith("b:"):
        return page.get_by_role("button", name=sel[2:]).first
    return page.locator(sel).first


def shoot(page, shot):
    name = shot["name"]
    page.evaluate("document.querySelectorAll('.wiki-callout-layer').forEach(n=>n.remove())")
    if shot.get("url"):
        page.goto(shot["url"], wait_until="networkidle")
        page.wait_for_timeout(shot.get("settle", 3000))
    elif shot.get("route") is not None:
        # Если предыдущий кадр уводил на сторонний адрес (например /docs), сменой хеша в SPA
        # уже не вернуться — нужен полный переход, иначе снимем не тот экран.
        from urllib.parse import urlparse

        if urlparse(page.url).path not in ("", "/"):
            page.goto(f"{BASE}/#{shot['route']}", wait_until="networkidle")
            page.wait_for_timeout(shot.get("settle", 2600) + 2000)
        else:
            page.evaluate(f"location.hash = '#{shot['route']}'")
            page.wait_for_timeout(shot.get("settle", 2600))
    for act in shot.get("before", []):
        kind, arg = act[0], act[1]
        if kind == "click":
            locate(page, arg).click()
        elif kind == "hover":
            locate(page, arg).hover()
        elif kind == "wait":
            page.wait_for_timeout(arg)
        elif kind == "js":
            page.evaluate(arg)
        elif kind == "key":
            page.keyboard.press(arg)
        elif kind == "mouse":
            # наведение на объект ВНУТРИ канваса карты: доли габарита канваса → координаты мыши
            sel, fx, fy = arg
            cb = locate(page, sel).bounding_box()
            page.mouse.move(cb["x"] + cb["width"] * fx, cb["y"] + cb["height"] * fy)
        elif kind == "scroll":
            locate(page, arg).scroll_into_view_if_needed()
        page.wait_for_timeout(act[2] if len(act) > 2 else 900)

    if shot.get("mask"):
        page.evaluate(MASK_JS, shot["mask"])

    boxes = []
    for i, c in enumerate(shot.get("callouts", []), start=1):
        sel = c["sel"]
        try:
            loc = locate(page, sel)
            loc.scroll_into_view_if_needed(timeout=3000) if c.get("scroll") else None
            box = loc.bounding_box(timeout=4000)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {name}: не найден {sel} ({type(e).__name__})", file=sys.stderr)
            continue
        if not box:
            print(f"  ! {name}: пустой bbox {sel}", file=sys.stderr)
            continue
        box = dict(box)
        # frac: [x, y, w, h] в долях от габарита найденного элемента — так обводятся объекты
        # внутри канваса карты (спрайты жителей, врагов, вход в шахту), к которым нет DOM-узла.
        if c.get("frac"):
            fx, fy, fw, fh = c["frac"]
            box = {
                "x": box["x"] + box["width"] * fx,
                "y": box["y"] + box["height"] * fy,
                "width": box["width"] * fw,
                "height": box["height"] * fh,
            }
        box["n"] = c.get("n", i)
        box["pad"] = c.get("pad", 8)
        box["side"] = c.get("side", "left")
        boxes.append(box)
    if boxes or shot.get("dim"):
        page.evaluate(OVERLAY_JS, {"boxes": boxes, "dim": shot.get("dim", False)})
        page.wait_for_timeout(250)

    clip = None
    if shot.get("clip"):
        c = shot["clip"]
        try:
            b = locate(page, c["sel"]).bounding_box(timeout=6000)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {name}: кроп не найден {c['sel']} ({type(e).__name__}) — снимаю целиком", file=sys.stderr)
            b = None
    if shot.get("clip") and b:
        pad = c.get("pad", 12)
        clip = {
            "x": max(0, b["x"] - pad),
            "y": max(0, b["y"] - pad),
            "width": min(VIEWPORT["width"], b["width"] + pad * 2),
            "height": min(VIEWPORT["height"], b["height"] + pad * 2),
        }
    raw = page.screenshot(clip=clip)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    if shot.get("trim"):
        # Кроп по элементу часто прихватывает пустой хвост колонки — срезаем почти-чёрные строки снизу.
        px = img.load()
        bottom = img.height
        step = max(1, img.width // 160)
        while bottom > 40:
            row = bottom - 1
            if max(max(px[x, row]) for x in range(0, img.width, step)) > 44:
                break
            bottom -= 1
        img = img.crop((0, 0, img.width, min(img.height, bottom + 20)))
    if img.width > TARGET_WIDTH:
        img = img.resize((TARGET_WIDTH, round(img.height * TARGET_WIDTH / img.width)), Image.LANCZOS)
    img.save(OUT / f"{name}.webp", "WEBP", quality=88, method=6)
    print(f"  ok {name}  {img.width}x{img.height}  {(OUT / (name + '.webp')).stat().st_size // 1024} KB")


def main():
    spec_path = pathlib.Path(__file__).parent / "shots.json"
    shots = json.loads(spec_path.read_text())
    only = set(sys.argv[1:])
    if only:
        shots = [s for s in shots if s["name"] in only]
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport=VIEWPORT, device_scale_factor=DSF)
        page.goto(BASE + "/", wait_until="networkidle")
        # кадры экрана входа снимаем до логина
        pre = [s for s in shots if s.get("stage") == "login"]
        for s in pre:
            shoot(page, s)
        if any(s.get("stage") != "login" for s in shots):
            page.get_by_text("войти под тестовым пользователем").click()
            page.wait_for_timeout(4500)
            for s in [s for s in shots if s.get("stage") != "login"]:
                shoot(page, s)
        b.close()


if __name__ == "__main__":
    main()
