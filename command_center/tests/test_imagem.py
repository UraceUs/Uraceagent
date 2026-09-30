"""Imagens comprimidas (issue #21): WebP, no máximo 1600 px, na orientação certa, sem EXIF."""
import io
import os

import pytest
from PIL import Image

os.environ["URACE_ENV"] = "/nao/existe"

from command_center.providers import imagem  # noqa: E402


def _foto(tamanho=(4000, 3000), orientacao=None, fmt="JPEG"):
    im = Image.new("RGB", tamanho, (200, 30, 30))
    exif = Image.Exif()
    exif[0x010F] = "Apple"                                  # Make
    exif[0x8825] = {1: "N", 2: (28.0, 32.0, 0.0)}           # GPS: onde a foto foi tirada
    if orientacao:
        exif[0x0112] = orientacao
    buf = io.BytesIO()
    im.save(buf, fmt, exif=exif.tobytes(), quality=95)
    return buf.getvalue()


def test_foto_de_celular_vira_webp_pequeno_sem_exif():
    original = _foto()
    novo, ext = imagem.comprimir(original)
    im = Image.open(io.BytesIO(novo))
    assert ext == ".webp" and im.format == "WEBP"
    assert max(im.size) == 1600 and im.size == (1600, 1200)
    assert not im.getexif(), "nada de EXIF (nem GPS) sai"
    assert len(novo) < len(original) / 3


def test_orientacao_da_camera_vira_pixel():
    novo, _ = imagem.comprimir(_foto((400, 300), orientacao=6))     # 6 = girar 90°
    assert Image.open(io.BytesIO(novo)).size == (300, 400), "foto em pé continua em pé"


def test_imagem_pequena_nao_cresce_e_transparencia_fica():
    buf = io.BytesIO(); Image.new("RGBA", (64, 32), (0, 0, 0, 0)).save(buf, "PNG")
    novo, _ = imagem.comprimir(buf.getvalue())
    im = Image.open(io.BytesIO(novo))
    assert im.size == (64, 32) and im.mode == "RGBA"


@pytest.mark.parametrize("lixo", [b"", b"\x89PNG falso", b"MZ\x90\x00executavel", b"<svg onload=alert(1)>"])
def test_o_que_nao_e_imagem_e_recusado(lixo):
    with pytest.raises(imagem.ImagemInvalida):
        imagem.comprimir(lixo)


def test_bomba_de_descompressao_e_recusada(monkeypatch):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
    with pytest.raises(imagem.ImagemInvalida):
        imagem.comprimir(_foto((100, 100)))
