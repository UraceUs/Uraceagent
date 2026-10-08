"""Cofre de logins e senhas (#162): a criptografia.

Dono, 08/10: "somente no acesso livre crie uma sessão de logins e senhas de onde fiquem seguras e
consigam ser armazenadas por lá".

- AES-256-GCM (`cryptography`), nonce novo a cada gravação, o campo entra como dado associado
  (a senha de um item não serve como observação de outro).
- A chave vem de `CC_COFRE_CHAVE` (32 bytes em base64 url-safe), no `~/.urace/adminai.env` do
  VPS. Ela nunca vai para o banco nem para o repositório; o backup do banco leva só a cifra.
- Sem chave, o cofre fica desligado e diz por quê. Chave trocada: os itens antigos não abrem
  (a impressão `key_fp` mostra qual chave cifrou) e nada é sobrescrito.
"""
import base64
import hashlib
import os

VERSAO = "v1:"


class CofreDesligado(Exception):
    pass


class ChaveErrada(Exception):
    pass


def _chave():
    bruto = (os.environ.get("CC_COFRE_CHAVE") or "").strip()
    if not bruto:
        raise CofreDesligado("O cofre está desligado: falta a CC_COFRE_CHAVE no VPS.")
    try:
        k = base64.urlsafe_b64decode(bruto + "=" * (-len(bruto) % 4))
    except (ValueError, TypeError):
        k = b""
    if len(k) != 32:
        raise CofreDesligado("O cofre está desligado: a CC_COFRE_CHAVE não tem 32 bytes em base64.")
    return k


def ligado():
    try:
        _chave()
        return True, None
    except CofreDesligado as e:
        return False, str(e)


def impressao():
    """Identifica a chave sem revelá-la (8 hex do sha256)."""
    return hashlib.sha256(b"cofre-urace:" + _chave()).hexdigest()[:8]


def nova_chave():
    return base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")


def cifrar(texto, campo):
    if texto is None or texto == "":
        return None
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    cifra = AESGCM(_chave()).encrypt(nonce, texto.encode("utf-8"), f"cofre:{campo}".encode())
    return VERSAO + base64.b64encode(nonce + cifra).decode()


def decifrar(guardado, campo):
    if not guardado:
        return None
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not guardado.startswith(VERSAO):
        raise ChaveErrada("formato desconhecido")
    bruto = base64.b64decode(guardado[len(VERSAO):])
    try:
        return AESGCM(_chave()).decrypt(bruto[:12], bruto[12:], f"cofre:{campo}".encode()).decode("utf-8")
    except InvalidTag as e:
        raise ChaveErrada("Este item foi guardado com outra chave do cofre.") from e
