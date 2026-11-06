"""[.mark] U12 (E104, point 4) : le miroir des conversations Claude Code dans le fork.

Des hooks Claude Code (message envoyé, action du MCP dograh, fin de réponse) envoient, par une route authentifiée par la clé MCP de la
personne, ses messages, les réponses de Claude et les NOMS d'actions avec un résumé (jamais les résultats bruts d'outils ni le contenu des
fichiers). Le fork range la conversation avec l'agent concerné, marquée « Claude Code · <prénom> », en lecture seule, en direct, avec le même
fil et les mêmes cartes qu'un chat de l'écran : c'est une ``mark_builder_conversations`` de genre ``claude_code`` et ses événements.

* **Un interrupteur par personne**, ÉTEINT par défaut (la conversation d'une personne ne quitte sa machine que si elle l'a voulu) :
  ligne ``MARK_MIROIR:<compte>``. Éteint, la route répond ``actif: false`` et ne range rien.
* **Filtre** (``filtre.py``) appliqué à tout ce qui est reçu, avant d'écrire : aucun secret, aucun contenu de ``.env``.
* **Bornes** : 20 événements par envoi, textes bornés, nom d'action en caractères sûrs ; limite de débit par compte (route).
* **Organisation** relue de la clé (jamais du corps) ; l'agent cité est relu AVEC cette organisation, sinon ignoré.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, Field, field_validator

from api.db import db_client
from api.services import modifications_live as live
from api.services.builder import fil as service_fil
from api.services.builder import stock
from api.services.miroir.filtre import borner, filtrer

PREFIXE_REGLAGE = "MARK_MIROIR:"
ENVOI_EVENEMENTS_MAX = 20
TEXTE_MAX = 8000
RESUME_MAX = 400
TITRE_MAX = 60
NOM_ACTION = re.compile(r"^[A-Za-z0-9_.:\-]{1,80}$")
SESSION = re.compile(r"^[A-Za-z0-9_\-]{6,80}$")
PAR_MINUTE = 120


def cle_reglage(compte: int) -> str:
    return f"{PREFIXE_REGLAGE}{compte}"


async def actif(organisation: int, compte: int) -> bool:
    return bool((await stock.lire(organisation, cle_reglage(compte)) or {}).get("actif"))


async def regler(organisation: int, compte: int, valeur: bool) -> bool:
    await stock.ecrire(organisation, cle_reglage(compte), {"actif": bool(valeur)})
    return bool(valeur)


class EvenementMiroir(BaseModel):
    type: Literal["message", "texte", "action", "fin"]
    texte: str = Field(default="", max_length=60_000)
    nom: str = Field(default="", max_length=80)
    resume: str = Field(default="", max_length=4000)
    ok: bool = True

    @field_validator("nom")
    @classmethod
    def _nom_sur(cls, v: str) -> str:
        if v and not NOM_ACTION.match(v):
            raise ValueError("an action name is letters, digits and _ . : - only")
        return v


class ChargeMiroir(BaseModel):
    session: str = Field(min_length=6, max_length=80)
    workflow_id: int | None = Field(default=None, ge=1)
    evenements: list[EvenementMiroir] = Field(min_length=1, max_length=ENVOI_EVENEMENTS_MAX)

    @field_validator("session")
    @classmethod
    def _session_sure(cls, v: str) -> str:
        if not SESSION.match(v):
            raise ValueError("the session id is letters, digits, _ and - only")
        return v


def _propre(texte: str, maxi: int) -> tuple[str, bool]:
    filtre, retire = filtrer(texte)
    return borner(filtre.strip(), maxi), retire


async def _agent_de_l_organisation(organisation: int, workflow_id: int | None) -> int | None:
    if workflow_id is None:
        return None
    try:
        return workflow_id if await db_client.get_workflow(workflow_id, organization_id=organisation) else None
    except Exception:  # noqa: BLE001
        return None


async def _fil_de_la_session(user: Any, charge: ChargeMiroir, premier_message: str) -> Any:
    organisation = user.selected_organization_id
    fil = await db_client.fil_de_la_session(organisation, charge.session, user.id)
    if fil is not None:
        return fil
    agent = await _agent_de_l_organisation(organisation, charge.workflow_id)
    titre = borner((premier_message.splitlines() or ["Claude Code"])[0].strip() or "Claude Code", TITRE_MAX)
    return await db_client.creer_fil(
        organisation, user.id, agent, titre, genre="claude_code", session_externe=charge.session, auteur=live.auteur_de(user)
    )


async def recevoir(user: Any, charge: ChargeMiroir) -> dict[str, Any]:
    """Range les événements reçus dans la conversation de la session (créée au premier envoi)."""
    organisation = user.selected_organization_id
    if not await actif(organisation, user.id):
        return {"actif": False, "recus": 0, "filtres": 0}
    premier = next((e.texte for e in charge.evenements if e.type == "message" and e.texte.strip()), "")
    fil = await _fil_de_la_session(user, charge, filtrer(premier)[0])
    agent = await _agent_de_l_organisation(organisation, charge.workflow_id)
    if agent is not None and fil.workflow_id is None:
        await db_client.modifier_fil(organisation, fil.id, workflow_id=agent)
    recus = retires = 0
    etat = None
    for e in charge.evenements:
        retire = False
        if e.type == "message":
            texte, retire = _propre(e.texte, TEXTE_MAX)
            if not texte:
                continue
            await service_fil.noter(fil.id, {"type": "message", "role": "user", "texte": texte})
            etat = "en_cours"
        elif e.type == "texte":
            texte, retire = _propre(e.texte, TEXTE_MAX)
            if not texte:
                continue
            await service_fil.noter(fil.id, {"type": "texte", "texte": texte})
        elif e.type == "action":
            if not e.nom:
                continue
            resume, retire = _propre(e.resume, RESUME_MAX)
            identifiant = uuid.uuid4().hex[:12]
            await service_fil.noter(fil.id, {"type": "action", "id": identifiant, "nom": e.nom, "arguments": {"resume": resume}})
            await service_fil.noter(fil.id, {"type": "resultat", "id": identifiant, "nom": e.nom, "ok": e.ok, "resultat": {"resume": resume}})
            etat = "en_cours"
        else:
            await service_fil.noter(fil.id, {"type": "fin", "raison": "fin"})
            etat = "terminee"
        recus += 1
        retires += 1 if retire else 0
    if etat is not None:
        await db_client.modifier_fil(organisation, fil.id, etat=etat)
    await live.noter(organisation, f"conversation:{fil.id}", "miroir", source="claude_code", auteur=live.auteur_de(user))
    if retires:
        logger.info(f"[miroir] session {charge.session[:8]}: {retires} element(s) filtre(s)")  # jamais le contenu
    return {"actif": True, "recus": recus, "filtres": retires, "fil_id": fil.id}
