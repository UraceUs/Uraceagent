"""Imagem que entra no painel sai comprimida (issue #21).

Foto de celular chega com 3–6 MB, 4000 px e EXIF — inclusive a posição GPS de onde foi
tirada. Aqui ela vira **WebP de no máximo 1600 px**, na orientação certa (a câmera grava
"deitada" e marca a rotação no EXIF) e **sem metadado nenhum**. Uma foto de peça fica
com ~100–250 KB e abre rápido no 4G do galpão.
"""
import io

from PIL import Image, ImageOps

LADO_MAX = 1600
QUALIDADE = 80
Image.MAX_IMAGE_PIXELS = 60_000_000          # acima disso é bomba de descompressão, não foto


class ImagemInvalida(ValueError):
    pass


def comprimir(dados, lado_max=LADO_MAX, qualidade=QUALIDADE):
    """bytes de PNG/JPG/WEBP → (bytes WebP, ".webp"). Levanta ImagemInvalida se não for imagem."""
    try:
        im = Image.open(io.BytesIO(dados))
        im.load()
    except (Image.DecompressionBombError, Image.UnidentifiedImageError, OSError, SyntaxError) as e:
        raise ImagemInvalida("não é uma imagem que dê para abrir") from e
    im = ImageOps.exif_transpose(im)                  # a rotação que a câmera marcou vira pixel
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if "A" in im.getbands() or im.mode == "P" else "RGB")
    im.thumbnail((lado_max, lado_max), Image.Resampling.LANCZOS)
    saida = io.BytesIO()
    im.save(saida, "WEBP", quality=qualidade, method=6)   # sem exif=: nenhum metadado sai
    return saida.getvalue(), ".webp"
