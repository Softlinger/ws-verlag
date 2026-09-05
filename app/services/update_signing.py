"""Signatur/Verifikation des Update-Manifests (Ed25519).

Der Pull erfolgt ohnehin strikt per Image-Digest (Docker prueft die Integritaet des
Images). Was damit nicht abgedeckt ist: dass das MANIFEST (version.json) selbst vom
Herausgeber stammt. Ein Angreifer, der nur die statische Website kompromittiert,
koennte ein beliebiges, ihm gehoerendes Image-Digest ausliefern. Dieses Modul
signiert/verifiziert die kanonischen Manifest-Nutzdaten mit einem Ed25519-Paar; die
App prueft (opt-in via settings.update_manifest_public_key), dass signature zu den
kanonischen Bytes passt.

Kanonisierung ist ABSICHTLICH schmal und stabil: nur die fuer das Update relevanten
Felder, sortiert, als kompakter UTF-8-JSON. Release-Tooling und App muessen
dieselbe canonical_bytes()-Funktion verwenden (deshalb hier ausgelagert).
"""
from base64 import b64decode, b64encode
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

CANONICAL_FIELDS = ("version", "image", "image_digest", "changelog", "release_date")


def canonical_bytes(manifest: dict) -> bytes:
    subset = {field: str(manifest.get(field, "")) for field in CANONICAL_FIELDS}
    return json.dumps(subset, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_manifest(manifest: dict, private_key_b64: str) -> str:
    private_key = Ed25519PrivateKey.from_private_bytes(b64decode(private_key_b64))
    return b64encode(private_key.sign(canonical_bytes(manifest))).decode("ascii")


def verify_manifest(manifest: dict, public_key_b64: str) -> None:
    """Wirft InvalidSignature/ValueError, wenn Signatur fehlt/ungueltig ist."""
    signature = manifest.get("signature")
    if not signature:
        raise ValueError("Manifest traegt keine 'signature'.")
    public_key = Ed25519PublicKey.from_public_bytes(b64decode(public_key_b64))
    public_key.verify(b64decode(signature), canonical_bytes(manifest))


def generate_keypair_b64() -> tuple[str, str]:
    """Hilfsfunktion fuer die Einrichtung: (public_key_b64, private_key_b64)."""
    private_key = Ed25519PrivateKey.generate()
    pub = b64encode(private_key.public_key().public_bytes_raw()).decode("ascii")
    priv = b64encode(private_key.private_bytes_raw()).decode("ascii")
    return pub, priv


__all__ = [
    "InvalidSignature",
    "CANONICAL_FIELDS",
    "canonical_bytes",
    "sign_manifest",
    "verify_manifest",
    "generate_keypair_b64",
]
