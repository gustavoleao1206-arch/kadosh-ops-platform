"""Gera os ícones PNG do painel a partir do mesmo desenho do favicon.svg.

Por que PNG e por que um script: o iOS **não aceita SVG** em `apple-touch-icon`. Sem um PNG, ao
adicionar o painel à tela de início o iPhone usa uma miniatura da página — fica ilegível e some no
meio dos outros ícones. O Android/Chrome aceita SVG no manifesto, mas usa os mesmos PNGs sem
reclamar, então um conjunto só serve aos dois.

O desenho é o do `web/public/favicon.svg`, deliberadamente: o "K" em champagne sobre obsidiana já é
o ícone deste sistema, e trocá-lo por outro seria uma decisão de marca que não cabe a um script.
(O wordmark completo "KADOSH DETAIL" não é opção aqui: a 180px ele vira um borrão.)

Rodar só quando o desenho mudar — os PNGs são versionados:

    backend/.venv/Scripts/python.exe scripts/gerar-icones.py

Depende de Pillow, que é ferramenta de máquina local e NÃO entra em backend/requirements.txt: a
imagem de produção não gera ícone nenhum.
"""

import pathlib
import sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ModuleNotFoundError:
    sys.exit("Pillow não está instalado. Rode: backend/.venv/Scripts/python.exe -m pip install Pillow")

# paleta da marca (a mesma de web/src/index.css)
OBSIDIANA = (11, 11, 13, 255)
CHAMPAGNE = (216, 189, 126, 255)

# Georgia acompanha o Windows e é a serifa do favicon.svg. Em outra máquina, troque por qualquer
# serifa com peso bold — o script avisa em vez de gerar um ícone com a fonte errada em silêncio.
FONTE = pathlib.Path("C:/Windows/Fonts/georgiab.ttf")

SAIDA = pathlib.Path(__file__).resolve().parents[1] / "web" / "public"

# 180 é o que o iOS pede em apple-touch-icon; 192 e 512 são os do manifesto (Android/Chrome).
TAMANHOS = (180, 192, 512)


def desenhar(lado: int) -> Image.Image:
    img = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # cantos arredondados na mesma proporção do SVG (raio 12 num quadro de 64)
    raio = round(lado * 12 / 64)
    d.rounded_rectangle([(0, 0), (lado - 1, lado - 1)], radius=raio, fill=OBSIDIANA)

    fonte = ImageFont.truetype(str(FONTE), round(lado * 0.56))
    # centraliza pela caixa REAL do glifo, não pela métrica da fonte: o "K" tem folga desigual em
    # cima e embaixo, e centralizar pela métrica o deixa visivelmente alto dentro do quadrado
    caixa = d.textbbox((0, 0), "K", font=fonte)
    largura, altura = caixa[2] - caixa[0], caixa[3] - caixa[1]
    d.text(((lado - largura) / 2 - caixa[0], (lado - altura) / 2 - caixa[1]), "K", font=fonte, fill=CHAMPAGNE)
    return img


def main() -> int:
    if not FONTE.exists():
        print(f"Fonte não encontrada: {FONTE}")
        return 1
    SAIDA.mkdir(parents=True, exist_ok=True)
    for lado in TAMANHOS:
        img = desenhar(lado)
        nome = "apple-touch-icon.png" if lado == 180 else f"icone-{lado}.png"
        img.save(SAIDA / nome, "PNG", optimize=True)
        print(f"{nome}  {lado}x{lado}  {(SAIDA / nome).stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
