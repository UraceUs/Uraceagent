#!/usr/bin/env python3
"""
Kommo API client — the piece this repo was missing: code that actually calls
api.kommo.com. Everything else here (tools_impl.py, orchestrator.py) works
against the Postgres mirror of a lead, never the live CRM. This is what lets
an agent session — or eventually the Orchestrator — read a real card, write
qualification data back to it, and move it between stages.

Two limits are enforced here, not left as a reminder in a prompt:

    native channel send   raises. The Kommo API does not deliver Instagram/
                           Facebook/WhatsApp text — only Salesbot or a human
                           on the Kommo/Meta Business Suite screen can. A
                           caller that tries gets an error immediately,
                           instead of a silent no-op or a note mistaken for
                           a sent message.
    credentials            never hardcoded, never logged. Token comes from
                           KOMMO_TOKEN (env) or ~/.urace/kommo_token.txt, in
                           that order. See CLAUDE.md, "Conectar no Kommo".

Usage:
    python agent/kommo_client.py --self-test        # no network, no token
    python agent/kommo_client.py --whoami            # confirms the token works
    python agent/kommo_client.py --custom-fields     # lists live field IDs
    python agent/kommo_client.py --pipelines         # lists live pipeline/stage IDs
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://urace.kommo.com/api/v4"
TOKEN_FILE = Path.home() / ".urace" / "kommo_token.txt"


class KommoError(RuntimeError):
    """A Kommo API call failed — carries the status and body so a caller can
    tell 'lead not found' (404) apart from 'token expired' (401)."""

    def __init__(self, status: int, body: str):
        self.status = status
        self.body = body
        super().__init__(f"Kommo API {status}: {body[:300]}")


def _load_token() -> str:
    token = os.environ.get("KOMMO_TOKEN")
    if token:
        return token.strip()
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    raise RuntimeError(
        "No Kommo token found. Set KOMMO_TOKEN, or save one to "
        f"{TOKEN_FILE} (chmod 600). See CLAUDE.md, 'Conectar no Kommo'."
    )


class KommoClient:
    """Thin wrapper over the Kommo v4 REST API. Every method maps to one
    documented endpoint — no caching, no retry/backoff beyond what urllib
    gives for free, because the loop prompts (prompts/LOOP_CRM.md,
    prompts/LOOP_COMERCIAL_KOMMO.md) are the layer that decides batching,
    pacing, and which cards to touch."""

    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = (base_url or os.environ.get("KOMMO_BASE_URL")
                         or DEFAULT_BASE_URL).rstrip("/")
        self.token = token or _load_token()

    def _request(self, method: str, path: str, params: dict | None = None,
                body: Any = None) -> dict:
        url = f"{self.base_url}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raise KommoError(e.code, e.read().decode("utf-8", "replace")) from e

    # -------------------------------------------------------------------
    # READ
    # -------------------------------------------------------------------

    def whoami(self) -> dict:
        return self._request("GET", "/account")

    def get_custom_fields(self, entity: str = "leads") -> list[dict]:
        data = self._request("GET", f"/{entity}/custom_fields", params={"limit": 250})
        return data.get("_embedded", {}).get("custom_fields", [])

    def get_pipelines(self) -> list[dict]:
        data = self._request("GET", "/leads/pipelines")
        return data.get("_embedded", {}).get("pipelines", [])

    def get_leads(self, filters: dict | None = None, with_: tuple[str, ...] = (),
                  page: int = 1, limit: int = 250) -> list[dict]:
        """One page. `filters` uses Kommo's bracket query syntax verbatim,
        e.g. {"filter[updated_at][from]": 1758000000}. A caller that wants
        everything pages until a result comes back shorter than `limit`."""
        params: dict[str, Any] = {"page": page, "limit": limit}
        if with_:
            params["with"] = ",".join(with_)
        if filters:
            params.update(filters)
        data = self._request("GET", "/leads", params=params)
        return data.get("_embedded", {}).get("leads", [])

    def get_lead(self, lead_id: int, with_: tuple[str, ...] = ("contacts", "notes")) -> dict:
        params = {"with": ",".join(with_)} if with_ else None
        return self._request("GET", f"/leads/{lead_id}", params=params)

    def get_lead_events(self, lead_id: int) -> list[dict]:
        """The move-one-test-card check every loop prompt calls for before a
        batch stage change: confirm only lead_status_changed fires."""
        data = self._request("GET", "/events", params={
            "filter[entity]": "lead",
            "filter[entity_id][]": lead_id,
        })
        return data.get("_embedded", {}).get("events", [])

    # -------------------------------------------------------------------
    # WRITE
    # -------------------------------------------------------------------

    def update_lead(self, lead_id: int, custom_fields_values: list[dict] | None = None,
                    status_id: int | None = None, pipeline_id: int | None = None) -> dict:
        """PATCH semantics: fields left out are left alone. Never send a full
        custom_fields_values list unless the intent is to overwrite every
        field currently on the card."""
        body: dict[str, Any] = {}
        if custom_fields_values is not None:
            body["custom_fields_values"] = custom_fields_values
        if status_id is not None:
            body["status_id"] = status_id
        if pipeline_id is not None:
            body["pipeline_id"] = pipeline_id
        if not body:
            raise ValueError("update_lead called with nothing to update")
        return self._request("PATCH", f"/leads/{lead_id}", body=body)

    def add_note(self, lead_id: int, text: str, note_type: str = "common") -> dict:
        body = [{"note_type": note_type, "params": {"text": text}}]
        return self._request("POST", f"/leads/{lead_id}/notes", body=body)

    def send_native_channel_message(self, *_args, **_kwargs):
        """Structural, not a reminder: the Kommo API cannot deliver Instagram/
        Facebook/WhatsApp text (see CLAUDE.md, 'restrições'). A caller that
        reaches this finds out immediately, rather than the message silently
        never arriving or a note being mistaken for a sent reply.

        Confirmed live on 23/09/2026, not just inferred: GET /talks/{id} works
        (lists the real conversation — talk_id, chat_id, origin, e.g.
        "instagram_business") but /talks/{id}/messages returns 403 "Invalid
        scope". The Kommo UI's own "Keys and scopes" screen for this private
        integration has no scope selector at all (just secret key, ID,
        long-lived token) — there is nothing to check to unlock this. Chats
        API access is reserved for apps that went through Kommo Marketplace
        review plus Meta's own business-messaging app review; a private/
        custom integration cannot get it by generating a new token. This is
        closed at the product level — don't re-attempt it in a future
        session without a materially new fact (e.g. Kommo actually granting
        a public/reviewed app)."""
        raise NotImplementedError(
            "Kommo's API does not send native-channel messages (Instagram/"
            "Facebook/WhatsApp). Only Salesbot, configured in the Kommo UI, "
            "or a human sending from the Kommo/Meta Business Suite screen "
            "can. Email is the one channel this client can send directly — "
            "compose it through add_note() with the account's email note "
            "type, or the /leads/{id}/notes endpoint directly."
        )


def build_custom_field_index(fields: list[dict]) -> dict[str, int]:
    """name (lowercased) -> id, for a quick eye-diff against the mapping in
    db/002_seed_config.sql. Separate from get_custom_fields so a caller that
    wants the raw API shape still gets it unmodified."""
    return {f["name"].strip().lower(): f["id"] for f in fields}


# =============================================================================
# CLI — manual checks, same spirit as kb/indexer.py --self-test
# =============================================================================

def _self_test() -> None:
    """No network, no token — exercises the parts that need neither."""
    checks = 0

    idx = build_custom_field_index([{"id": 1, "name": "Interest"}, {"id": 2, "name": "Program"}])
    assert idx == {"interest": 1, "program": 2}, idx
    checks += 1

    err = KommoError(404, '{"detail":"not found"}')
    assert err.status == 404 and "404" in str(err)
    checks += 1

    client = KommoClient.__new__(KommoClient)  # skip __init__: no token needed
    try:
        client.send_native_channel_message()
        raise AssertionError("expected NotImplementedError")
    except NotImplementedError:
        checks += 1

    try:
        client.update_lead(1)
        raise AssertionError("expected ValueError on an empty update")
    except ValueError:
        checks += 1

    print(f"kommo_client --self-test: {checks}/4 OK")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--whoami", action="store_true")
    parser.add_argument("--custom-fields", action="store_true")
    parser.add_argument("--pipelines", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return

    if not any([args.whoami, args.custom_fields, args.pipelines]):
        parser.print_help()
        return

    client = KommoClient()

    if args.whoami:
        account = client.whoami()
        print(f"{account['name']} (subdomain {account['subdomain']}, "
              f"account_id {account['id']})")

    if args.custom_fields:
        for f in client.get_custom_fields():
            print(f"{f['id']:>10}  {f['name']}")

    if args.pipelines:
        for p in client.get_pipelines():
            print(f"pipeline {p['id']}: {p['name']}")
            for s in p.get("_embedded", {}).get("statuses", []):
                print(f"  {s['id']:>10}  {s['name']}")


if __name__ == "__main__":
    main()
