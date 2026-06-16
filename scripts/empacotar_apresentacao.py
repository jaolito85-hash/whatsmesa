"""Empacota a apresentação de vendas num único arquivo .html.

Problema que resolve: o `apresentacao.html` aponta para imagens e CSS em
pastas vizinhas (`img/`, `css/`). Quando você envia só o .html pelo
WhatsApp/e-mail, essas pastas ficam pra trás e as imagens não abrem.

Este script lê a apresentação, embute o CSS e converte as imagens em
"data URI" (a imagem vira texto dentro do próprio HTML). O resultado é
UM arquivo só que abre perfeito em qualquer celular ou computador, mesmo
sem internet (as fontes do Google têm fallback pra fonte do sistema).

Rodar:  python scripts/empacotar_apresentacao.py
Gera:   material-vendas/Klink-Apresentacao.html
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "material-vendas"
ENTRADA = BASE / "apresentacao.html"
SAIDA = BASE / "Klink-Apresentacao.html"

# Número oficial de contato (mesmo da landing). Quem clicar no CTA cai aqui.
WHATSAPP = "https://wa.me/554431011918?text=Olá, vi a apresentação do Klink e quero testar no meu bar"


def como_data_uri(caminho: Path) -> str:
    """Lê um arquivo e devolve ele como data URI (base64) pra embutir no HTML."""
    mime = mimetypes.guess_type(caminho.name)[0] or "application/octet-stream"
    dados = base64.b64encode(caminho.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{dados}"


def main() -> None:
    html = ENTRADA.read_text(encoding="utf-8")

    css = (BASE / "css" / "klink-kit.css").read_text(encoding="utf-8")
    mascote = como_data_uri(BASE / "img" / "klink-mascote.png")
    favicon = como_data_uri(BASE / "img" / "favicon-64.png")

    # 1) CSS externo -> CSS embutido
    html = html.replace(
        '<link rel="stylesheet" href="css/klink-kit.css" />',
        f"<style>\n{css}\n</style>",
    )

    # 2) Imagens -> data URI (some a dependência da pasta img/)
    html = html.replace('href="img/favicon-64.png"', f'href="{favicon}"')
    html = html.replace('src="img/klink-mascote.png"', f'src="{mascote}"')

    # 3) Link da logo na navbar apontava pra index.html (que não vai junto)
    html = html.replace('href="index.html"', 'href="#"')

    # 4) Botão final agora leva ao WhatsApp de vendas, em nova aba
    html = html.replace(
        '<a class="btn btn-ink" href="#" id="cta-wpp">',
        f'<a class="btn btn-ink" href="{WHATSAPP}" id="cta-wpp" target="_blank" rel="noopener">',
    )

    SAIDA.write_text(html, encoding="utf-8")

    tamanho_kb = len(html.encode("utf-8")) / 1024
    sobrou = 'src="img/' in html or 'href="img/' in html or 'href="css/' in html
    print(f"Gerado: {SAIDA.name}")
    print(f"Tamanho: {tamanho_kb:.0f} KB (arquivo unico, pronto pra enviar)")
    print(f"Ainda depende de pasta externa? {'SIM - revisar!' if sobrou else 'NAO - tudo embutido'}")


if __name__ == "__main__":
    main()
