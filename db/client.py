"""
Firestore client — um ponto de inicialização, três formas de credencial.

    FIRESTORE_EMULATOR_HOST          emulador local (testes; nenhuma credencial)
    GOOGLE_APPLICATION_CREDENTIALS   caminho do JSON da service account (padrão GCP)
    FIREBASE_SERVICE_ACCOUNT_JSON    idem, nome que o .env deste projeto usa

O project id vem de FIRESTORE_PROJECT_ID, ou do próprio JSON da credencial.
Falhar aqui, alto e cedo, é o comportamento correto: um client sem projeto
definido falharia na primeira leitura com um erro que não nomeia a causa.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_db = None


def get_db():
    """Client singleton. Threads do FastAPI podem compartilhar: o client do
    Firestore é thread-safe."""
    global _db
    if _db is not None:
        return _db

    if not (os.environ.get("FIRESTORE_PROJECT_ID")
            or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            or os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
            or os.environ.get("FIRESTORE_EMULATOR_HOST")):
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")

    from google.cloud import firestore

    cred_path = (os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
                 or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))
    project = os.environ.get("FIRESTORE_PROJECT_ID")

    if os.environ.get("FIRESTORE_EMULATOR_HOST"):
        # Emulador: sem credencial. O SDK detecta o host pelo env var; só o
        # projeto precisa de um nome (qualquer um, consistente entre runs).
        _db = firestore.Client(project=project or "urace-emulator")
        return _db

    if cred_path:
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(cred_path)
        if not project:
            project = json.loads(Path(cred_path).read_text())["project_id"]
        _db = firestore.Client(project=project, credentials=creds)
        return _db

    if project:
        _db = firestore.Client(project=project)  # ADC (gcloud auth, GCE, etc.)
        return _db

    raise RuntimeError(
        "Firestore não configurado. Defina FIRESTORE_EMULATOR_HOST (testes), "
        "ou FIREBASE_SERVICE_ACCOUNT_JSON / GOOGLE_APPLICATION_CREDENTIALS "
        "(+ FIRESTORE_PROJECT_ID se o JSON não tiver project_id).")


def contact_id(channel: str, external_id: str) -> str:
    """Doc ID determinístico de contato — é a UNIQUE(channel, external_id).

    '/' não pode aparecer em doc ID; um handle contendo barra viraria path.
    """
    return f"{channel}__{str(external_id).replace('/', '_')}"


def follow_up_id(lead_id: str, attempt_number: int) -> str:
    """Doc ID determinístico — é a UNIQUE(lead_id, attempt_number)."""
    return f"{lead_id}__{attempt_number}"
