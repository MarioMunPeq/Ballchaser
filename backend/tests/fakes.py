"""Dobles de prueba para dependencias externas."""

from typing import Any

from app.core.errors import unauthorized
from app.core.security import Identity

BUILTIN_TOKENS: dict[str, Identity] = {
    "token-alice": Identity(uid="uid-alice", email="alice@example.com", display_name="Alice"),
    "token-bob": Identity(uid="uid-bob", email="bob@example.com", display_name="Bob"),
    "token-sin-email": Identity(uid="uid-sin-email", email=None, display_name=None),
}


class FakeIdentityVerifier:
    """Sustituye a Firebase: cada token de `identities` es valido.

    Cualquier token desconocido falla como lo haria Firebase con una firma
    invalida.
    """

    def __init__(self, identities: dict[str, Identity] | None = None) -> None:
        self.identities = dict(BUILTIN_TOKENS if identities is None else identities)
        self.seen_tokens: list[str] = []

    def verify(self, id_token: str) -> Identity:
        self.seen_tokens.append(id_token)
        try:
            return self.identities[id_token]
        except KeyError as exc:
            raise unauthorized() from exc


def bearer(token: str) -> dict[str, str]:
    """Cabecera `Authorization` para un token."""
    return {"Authorization": f"Bearer {token}"}


def make_token(uid: str, verifier: FakeIdentityVerifier, **claims: Any) -> str:
    """Registra una identidad nueva en el verificador y devuelve su token."""
    token = f"token-{uid}"
    verifier.identities[token] = Identity(uid=uid, **claims)
    return token
