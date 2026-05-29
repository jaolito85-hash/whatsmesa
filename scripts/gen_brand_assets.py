"""Gera os assets de marca do Klink a partir das imagens originais.

- Recorta o fundo do mascote (flood fill a partir das bordas) -> PNG transparente
- Gera favicon (32, 64) e apple-touch-icon (180) a partir do mascote
- Copia a foto real do painel para a landing

Uso: python scripts/gen_brand_assets.py
"""
from __future__ import annotations

import shutil
from collections import deque
from pathlib import Path

from PIL import Image

MEDIA = Path(r"C:\projetos\klink-video\media")
OUT = Path(__file__).resolve().parent.parent / "static" / "brand"
OUT.mkdir(parents=True, exist_ok=True)


def remove_white_bg(src: Path, tol: int = 40, feather: bool = True) -> Image.Image:
    """Remove o fundo branco conectado às bordas (preserva reflexos internos)."""
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    px = im.load()

    def is_white(x: int, y: int) -> bool:
        r, g, b, _ = px[x, y]
        return r > 255 - tol and g > 255 - tol and b > 255 - tol

    bg = bytearray(w * h)  # 1 = fundo
    seen = bytearray(w * h)
    q: deque[tuple[int, int]] = deque()

    for x in range(w):
        for y in (0, h - 1):
            q.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            q.append((x, y))

    while q:
        x, y = q.popleft()
        if x < 0 or y < 0 or x >= w or y >= h:
            continue
        idx = y * w + x
        if seen[idx]:
            continue
        seen[idx] = 1
        if not is_white(x, y):
            continue
        bg[idx] = 1
        q.append((x + 1, y))
        q.append((x - 1, y))
        q.append((x, y + 1))
        q.append((x, y - 1))

    # aplica transparência
    for y in range(h):
        for x in range(w):
            if bg[y * w + x]:
                r, g, b, _ = px[x, y]
                px[x, y] = (r, g, b, 0)

    # feather: suaviza a franja (pixels do objeto vizinhos do fundo recebem alpha parcial se claros)
    if feather:
        for y in range(1, h - 1):
            for x in range(1, w - 1):
                idx = y * w + x
                if bg[idx]:
                    continue
                # vizinho de fundo?
                if bg[idx - 1] or bg[idx + 1] or bg[idx - w] or bg[idx + w]:
                    r, g, b, a = px[x, y]
                    lum = (r + g + b) / 3
                    if lum > 235:  # franja clara -> reduz alpha p/ tirar halo branco
                        px[x, y] = (r, g, b, 90)

    # recorta para o conteúdo
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    return im


def fit_square(im: Image.Image, size: int, pad_ratio: float = 0.06, bg=None) -> Image.Image:
    """Centraliza a imagem num quadrado size x size."""
    canvas = Image.new("RGBA", (size, size), bg or (0, 0, 0, 0))
    inner = int(size * (1 - pad_ratio * 2))
    w, h = im.size
    scale = min(inner / w, inner / h)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    r = im.resize((nw, nh), Image.LANCZOS)
    canvas.paste(r, ((size - nw) // 2, (size - nh) // 2), r)
    return canvas


def main() -> None:
    print("Recortando mascote (pode levar alguns segundos)...")
    mascote = remove_white_bg(MEDIA / "logo-klink-branco.png")

    # mascote para web (max 600px de altura)
    big = mascote.copy()
    if big.height > 600:
        s = 600 / big.height
        big = big.resize((int(big.width * s), 600), Image.LANCZOS)
    big.save(OUT / "klink-mascote.png")
    print(f"  -> klink-mascote.png  {big.size}")

    # favicons (fundo transparente)
    fit_square(mascote, 64).save(OUT / "favicon-64.png")
    fit_square(mascote, 32).save(OUT / "favicon-32.png")
    # ico multi-tamanho
    fit_square(mascote, 64).save(
        OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)]
    )
    # apple touch (fundo claro, Apple ignora transparência)
    fit_square(mascote, 180, pad_ratio=0.1, bg=(254, 254, 255, 255)).save(
        OUT / "apple-touch-icon.png"
    )
    print("  -> favicon-32/64.png, favicon.ico, apple-touch-icon.png")

    # foto real do painel para a landing
    panel_src = MEDIA / "02-painel-pedidos.png"
    if panel_src.exists():
        shutil.copy(panel_src, OUT / "painel-klink.png")
        print("  -> painel-klink.png (copiado)")

    print("OK. Assets em:", OUT)


if __name__ == "__main__":
    main()
