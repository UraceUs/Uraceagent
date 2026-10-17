"""Imagem que entra no painel sai comprimida (issue #21).

Foto de celular chega com 3–6 MB, 4000 px e EXIF — inclusive a posição GPS de onde foi
tirada. Aqui ela vira **WebP de no máximo 1600 px**, na orientação certa (a câmera grava
"deitada" e marca a rotação no EXIF) e **sem metadado nenhum**. Uma foto de peça fica
com ~100–250 KB e abre rápido no 4G do galpão.

Revisão do #172: o Pillow só **recusa** acima do dobro do `MAX_IMAGE_PIXELS` (120 MP); entre 60 e 120 MP ele só
avisa (`DecompressionBombWarning`) e abria, e um PNG de cor lisa de 100 MP cabe em poucos KB e pede ~300 MB de
memória. Agora o tamanho se confere no cabeçalho, **antes** de decodificar (`PIXELS_MAX`: a foto de 48–50 MP de um
celular passa; 100 MP não), e o aviso do Pillow também vira recusa.
"""
import io
import warnings

from PIL import Image, ImageOps

LADO_MAX = 1600
QUALIDADE = 80
PIXELS_MAX = 60_000_000                      # acima disso é bomba de descompressão, não foto
Image.MAX_IMAGE_PIXELS = PIXELS_MAX
GRANDE_DEMAIS = "foto com pixels demais (até 60 megapixels): diminua a foto e tente de novo"


class ImagemInvalida(ValueError):
    pass


def abrir(dados):
    """A imagem aberta só pelo cabeçalho (nada decodificado ainda), já conferido o tamanho em pixels."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            im = Image.open(io.BytesIO(dados))
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as e:
            raise ImagemInvalida(GRANDE_DEMAIS) from e
        except (Image.UnidentifiedImageError, OSError, SyntaxError) as e:
            raise ImagemInvalida("não é uma imagem que dê para abrir") from e
    if im.width * im.height > PIXELS_MAX:
        raise ImagemInvalida(GRANDE_DEMAIS)
    return im


def comprimir(dados, lado_max=LADO_MAX, qualidade=QUALIDADE):
    """bytes de PNG/JPG/WEBP → (bytes WebP, ".webp"). Levanta ImagemInvalida se não for imagem."""
    im = abrir(dados)
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            im.load()
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as e:
            raise ImagemInvalida(GRANDE_DEMAIS) from e
        except (Image.UnidentifiedImageError, OSError, SyntaxError) as e:
            raise ImagemInvalida("não é uma imagem que dê para abrir") from e
    im = ImageOps.exif_transpose(im)                  # a rotação que a câmera marcou vira pixel
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if "A" in im.getbands() or im.mode == "P" else "RGB")
    im.thumbnail((lado_max, lado_max), Image.Resampling.LANCZOS)
    saida = io.BytesIO()
    im.save(saida, "WEBP", quality=qualidade, method=6)   # sem exif=: nenhum metadado sai
    return saida.getvalue(), ".webp"
