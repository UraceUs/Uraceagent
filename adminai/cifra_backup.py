"""A cópia do banco que sai da VPS vai cifrada (#299).

Dono, 16/10: *"eu preciso que dados de clientes como e-mails, nomes, informações de contatos, sejam armazenados
em um banco de dados"*. Decisão: **SQLite + backup diário**. A cópia que fica no Google Drive tem a base inteira
(nome, e-mail, telefone, valor). Cifrada, ela não abre para quem chegar ao arquivo sem a chave.

- **AES-256-GCM** (a mesma do cofre, #162): quem tiver o arquivo e não a chave não lê nada, e um byte trocado no
  caminho faz a abertura falhar em vez de devolver um banco errado.
- **A chave** vem de `CC_BACKUP_CHAVE` (32 bytes em base64 url-safe), no `~/.urace/adminai.env` da VPS. O deploy
  cria uma vez e nunca mostra. **Guarde uma cópia do `adminai.env` fora da VPS**: sem a chave, a cópia do Drive
  não abre, e perder a VPS é justamente quando ela faz falta.
- O arquivo diz com qual chave foi cifrado (8 hex do sha256, nunca a chave): chave trocada não abre e o erro
  diz qual era.
"""
import base64
import hashlib
import os

MAGICA = b"URACEBK1"
SUFIXO = ".enc"


class ChaveAusente(RuntimeError):
    pass


class ChaveErrada(RuntimeError):
    pass


def chave():
    bruto = (os.environ.get("CC_BACKUP_CHAVE") or "").strip()
    if not bruto:
        raise ChaveAusente("sem CC_BACKUP_CHAVE no ~/.urace/adminai.env: rode o deploy, que cria a chave uma vez")
    try:
        k = base64.urlsafe_b64decode(bruto + "=" * (-len(bruto) % 4))
    except ValueError as e:
        raise ChaveAusente("CC_BACKUP_CHAVE não é base64") from e
    if len(k) != 32:
        raise ChaveAusente("CC_BACKUP_CHAVE precisa ter 32 bytes")
    return k


def impressao(k=None):
    """Identifica a chave sem revelá-la."""
    return hashlib.sha256(b"backup-urace:" + (k or chave())).hexdigest()[:8]


def nova_chave():
    return base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")


def cifrar(origem, destino=None):
    """Arquivo → `<arquivo>.enc` (600). Devolve o caminho."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    k = chave()
    fp = impressao(k).encode()
    with open(origem, "rb") as f:
        dados = f.read()
    nonce = os.urandom(12)
    saida = MAGICA + fp + nonce + AESGCM(k).encrypt(nonce, dados, MAGICA + fp)
    destino = destino or origem + SUFIXO
    with open(destino, "wb") as f:
        f.write(saida)
    os.chmod(destino, 0o600)
    return destino


def decifrar(origem, destino):
    """`.enc` → o arquivo de antes. Chave errada ou arquivo mexido: erro, nunca um banco pela metade."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    with open(origem, "rb") as f:
        bruto = f.read()
    if not bruto.startswith(MAGICA) or len(bruto) < len(MAGICA) + 8 + 12 + 16:
        raise ChaveErrada("este arquivo não é uma cópia cifrada do Command Center")
    fp = bruto[len(MAGICA):len(MAGICA) + 8]
    k = chave()
    if fp.decode(errors="replace") != impressao(k):
        raise ChaveErrada(f"a cópia foi cifrada com a chave {fp.decode(errors='replace')}; a desta VPS é {impressao(k)}")
    nonce = bruto[len(MAGICA) + 8:len(MAGICA) + 20]
    try:
        dados = AESGCM(k).decrypt(nonce, bruto[len(MAGICA) + 20:], MAGICA + fp)
    except InvalidTag as e:
        raise ChaveErrada("a cópia não abriu: o arquivo foi alterado ou está incompleto") from e
    with open(destino, "wb") as f:
        f.write(dados)
    os.chmod(destino, 0o600)
    return destino
