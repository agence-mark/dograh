"""[.mark] The verification state of ONE call (L6, V1, V6).

Kept in Redis, under the organization AND the run: never in the call's record (the extraction
of the model writes there), never in a parameter, never in the call context the model reads.
Two calls never share it (between callers), two organizations never (between clients). It
survives the turns of the keyboard (a new engine per message) and dies with the call (TTL).

Nothing here keeps what the caller answered. The SMS code is kept as a salted digest only,
with its expiry. Redis unreachable: the state reads as « nothing verified » (fail closed).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import asdict, dataclass, field

from loguru import logger

PREFIXE = "mark:verification:v1:"
DUREE_S = 4 * 3600


@dataclass
class Etat:
    source: str | None = None  # "hub" or a translator's name
    dossier: str | None = None  # the record identified (id in its source)
    reussis: list[str] = field(default_factory=list)  # distinct factors passed
    tentatives_echouees: int = 0
    bloque: bool = False
    code_empreinte: str | None = None
    code_sel: str | None = None
    code_expire: float | None = None  # epoch seconds
    code_envois: int = 0

    def niveau(self) -> int:
        return len(set(self.reussis))


def cle(organization_id: int, run_id: int) -> str:
    return f"{PREFIXE}{int(organization_id)}:{int(run_id)}"


async def _redis():
    from api.services.etablissements.copie import _redis as client

    return await client()


async def charger(organization_id: int, run_id: int) -> Etat:
    try:
        brut = await (await _redis()).get(cle(organization_id, run_id))
    except Exception as erreur:  # noqa: BLE001 -- fail closed: nothing verified
        logger.error(f"[.mark] Verification state unreadable, nothing verified: {erreur!r}")
        return Etat()
    if not brut:
        return Etat()
    try:
        donnees = json.loads(brut)
        return Etat(**{k: v for k, v in donnees.items() if k in Etat.__dataclass_fields__})
    except Exception:  # noqa: BLE001 -- a broken state is no state
        return Etat()


async def enregistrer(organization_id: int, run_id: int, etat: Etat) -> None:
    """Raises when Redis is unreachable: the caller refuses rather than forgetting a failure."""
    await (await _redis()).set(cle(organization_id, run_id), json.dumps(asdict(etat)), ex=DUREE_S)


def empreinte(code: str, sel: str) -> str:
    return hashlib.sha256(f"{sel}:{code}".encode()).hexdigest()


def nouveau_code(longueur: int) -> tuple[str, str, str]:
    """(code, salt, digest). Only the digest and the salt are kept."""
    code = "".join(secrets.choice("0123456789") for _ in range(longueur))
    sel = secrets.token_hex(8)
    return code, sel, empreinte(code, sel)


def code_juste(etat: Etat, propose: str, maintenant: float) -> bool:
    if not (etat.code_empreinte and etat.code_sel and etat.code_expire):
        return False
    if maintenant > etat.code_expire:
        return False
    chiffres = "".join(c for c in str(propose or "") if c.isdigit())
    return hmac.compare_digest(empreinte(chiffres, etat.code_sel), etat.code_empreinte)
