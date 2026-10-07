"""[.mark] « Direct to a person » during a call (chantier l-agent-collegue, L2, C7 to C10).

The handler of the internal action ``equipe.diriger_vers_personne``:

1. The person is named by her KEY. ⛔ A key outside the closed list of the call
   (``equipe_cles``, built at pick-up), a phone number or an e-mail is REFUSED: the model is
   told to choose from the list, nothing is dialled, nothing is assigned (C7).
2. The person is read from the in-memory copy (never from what the model says): active,
   her phone number, whether she may be reached by transfer (C8).
3. Transfer when it is asked (the default) AND possible (``joignable_par_transfert`` and a
   number): Dograh's own transfer handler is played with that number -- the same phone
   path, the same simulated transfer in a test window. The model is never given the number.
4. Otherwise, or when the transfer fails (no answer, refused, error): the request is PASSED
   ON to her -- assigned to her, and the after-call mail goes to her first -- and a sentence
   of the catalogue is said (C9: never a silence). Default texts below; an organization
   replaces them with the sentences ``phrase_transfert_personne`` and
   ``phrase_transmission_personne`` of its catalogue (``{{prenom}}`` is her first name).
5. Every gesture is written in the record (``equipe_gestes``) for the after-call: the
   transfer with the number dialled, whether she answered and how long it took (C10), the
   passing on with the reason. The request's assignee is ``equipe_assignation``.
6. R-3 (decision of Evan, 07/10): when the transfer FAILED (no answer, refused, error), the
   agent takes the call back and the request reaches her as a CALL-BACK TO MAKE: the
   caller's number (from the call, never from the model), the object, the slot he wished if
   he said it (``rappel_souhaite``). The same call-back request as the planner's
   (``services/apres_appel/rappels.py``), assigned to her, a certain mention of her.

R1: nothing here is swallowed in silence; every outcome is stamped in ``connecteurs`` too.
"""

from __future__ import annotations

import dataclasses
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from loguru import logger

from api.schemas.base_client import Personne
from api.services.apres_appel.rappels import CLE_RAPPEL, ORIGINE_EQUIPE
from api.services.equipe.appel import cles_de_lappel
from api.utils.template_renderer import render_template

CLE_GESTES = "equipe_gestes"
CLE_ASSIGNATION = "equipe_assignation"
VARIABLE_PHRASE_TRANSFERT = "phrase_transfert_personne"
VARIABLE_PHRASE_TRANSMISSION = "phrase_transmission_personne"
PHRASE_TRANSFERT_DEFAUT = "Je vous mets en relation avec {{prenom}}, ne quittez pas."
PHRASE_TRANSMISSION_DEFAUT = (
    "Je transmets votre demande à {{prenom}}, qui reviendra vers vous."
)


def phrase(contexte: dict | None, variable: str, defaut: str, personne: Personne) -> str:
    """The catalogue's sentence when the organization wrote one, else the default text."""
    brut = (contexte or {}).get(variable)
    texte = brut if isinstance(brut, str) and brut.strip() else defaut
    rendu = render_template(texte, {"prenom": personne.prenom, "nom": personne.nom or ""})
    return " ".join(str(rendu or "").split())


async def personne_de_la_copie(
    organization_id: int, cle: str, etablissement_id: str | None
) -> Personne | None:
    """The active person of this organization AND reachable from the establishment served
    (hers, or one of the whole company): a key that slipped into the list from elsewhere
    reaches no one of another establishment."""
    from api.services.etablissements.copie import lire_copie_complete

    equipe = (await lire_copie_complete(organization_id)).equipe
    return next(
        (
            p
            for p in equipe.personnes
            if p.cle == cle and p.actif and (p.etablissement is None or p.etablissement == etablissement_id)
        ),
        None,
    )


def _noter(fiche: dict | None, geste: dict) -> None:
    if isinstance(fiche, dict):
        fiche.setdefault(CLE_GESTES, []).append(geste)


def _estampiller(fiche: dict | None, nom: str, statut: str, message: str | None = None) -> None:
    from api.services.integrations.connectors.execution import estampiller

    estampiller(
        fiche,
        {
            "outil": nom,
            "connecteur": "equipe",
            "action": "diriger_vers_personne",
            "statut": statut,
            "duree_ms": None,
            "message": message,
        },
    )


def creer_gestionnaire(manager: Any, tool: Any, nom_de_fonction: str):
    """The handler, given the engine's custom tool manager (its transfer is reused)."""
    from api.services.integrations.connectors.outil import config_de

    config = config_de(tool)
    reglages = {"delai_transfert_s": 30, **(config.get("reglages") or {})}

    async def gestionnaire(params) -> None:
        engine = manager._engine
        fiche = getattr(engine, "_gathered_context", None)
        contexte = getattr(engine, "_call_context_vars", None) or {}
        arguments = params.arguments or {}
        cle = str(arguments.get("personne") or "").strip()
        geste = str(arguments.get("geste") or "transferer").strip()
        motif = str(arguments.get("motif") or "").strip()[:300] or None
        souhait = str(arguments.get("rappel_souhaite") or "").strip()[:200] or None

        # 1. The closed list (C7): the one the code stamped on the run at pick-up, never the one in
        # the context the pre-call fetch or a replay may have written.
        cles_permises, etablissement_servi = cles_de_lappel(contexte)
        if cle not in cles_permises:
            logger.warning(
                f"[.mark] « Direct to a person » refused: « {cle[:40]} » is not a key of the team"
            )
            _estampiller(fiche, nom_de_fonction, "refus", "unknown person")
            await params.result_callback(
                {
                    "status": "refused",
                    "reason": "unknown_person",
                    "instruction": "Name the person by her key from the team list; never a phone number nor an e-mail.",
                    "keys": list(cles_permises),
                }
            )
            return

        # 2. The person, from the copy (C8).
        organization_id = await manager.get_organization_id()
        personne = (
            await personne_de_la_copie(organization_id, cle, etablissement_servi) if organization_id else None
        )
        if personne is None:
            _estampiller(fiche, nom_de_fonction, "refus", "person no longer in the team")
            await params.result_callback(
                {
                    "status": "refused",
                    "reason": "person_unavailable",
                    "instruction": "This person cannot be reached now; offer to take a message.",
                }
            )
            return

        async def transmettre(raison: str | None = None, rappel: bool = False) -> None:
            texte = phrase(contexte, VARIABLE_PHRASE_TRANSMISSION, PHRASE_TRANSMISSION_DEFAUT, personne)
            le = datetime.now(UTC).isoformat()
            _noter(
                fiche,
                {"geste": "transmission", "personne": personne.cle, "motif": motif,
                 "le": le, "raison": raison, **({"rappel": True} if rappel else {})},
            )
            if isinstance(fiche, dict):
                fiche[CLE_ASSIGNATION] = personne.cle
                if rappel:
                    # R-3: a call-back to make, by her. The number is the call's, never the model's.
                    fiche.setdefault(CLE_RAPPEL, []).append(
                        {"origine": ORIGINE_EQUIPE, "mode": "rappel", "personne": personne.cle,
                         "prenom": personne.prenom, "numero": contexte.get("caller_number") or None,
                         "objet": motif, "souhait": souhait, "raison": raison, "le": le}
                    )
            _estampiller(fiche, nom_de_fonction, "transmis", raison)
            await engine.queue_text_message(texte, mute_user=True)
            await params.result_callback(
                {
                    "status": "passed_on",
                    "person": personne.prenom,
                    "said_to_caller": texte,
                    **({"callback": True} if rappel else {}),
                    "instruction": (
                        "She could not take the call: she will call the caller back. Do not repeat "
                        "this sentence, take the call back and go on with it."
                        if rappel
                        else "The request was passed on; do not repeat this sentence, go on with the call."
                    ),
                }
            )

        # 3. Transfer when asked and possible.
        if not (geste != "transmettre" and personne.joignable_par_transfert and personne.telephone):
            raison = None
            if geste != "transmettre":
                raison = "not reachable by transfer" if not personne.joignable_par_transfert else "no phone number"
            await transmettre(raison)
            return

        debut = time.monotonic()
        le = datetime.now(UTC).isoformat()
        outil_de_transfert = SimpleNamespace(
            tool_uuid=getattr(tool, "tool_uuid", None),
            name=getattr(tool, "name", nom_de_fonction),
            category="transfer_call",
            definition={
                "type": "transfer_call",
                "config": {
                    "destination_source": "static",
                    "destination": personne.telephone,
                    "timeout": int(reglages.get("delai_transfert_s") or 30),
                    "messageType": "custom",
                    "customMessage": phrase(
                        contexte, VARIABLE_PHRASE_TRANSFERT, PHRASE_TRANSFERT_DEFAUT, personne
                    ),
                },
            },
        )
        rendu: dict = {}

        async def au_resultat(resultat, *args, **kwargs):
            statut = (resultat or {}).get("status") if isinstance(resultat, dict) else None
            decroche = statut in ("transfer_success", "success")
            _noter(
                fiche,
                {"geste": "transfert", "personne": personne.cle, "numero": personne.telephone,
                 "le": le, "decroche": decroche,
                 "duree_s": round(time.monotonic() - debut), "motif": motif},
            )
            if decroche:
                _estampiller(fiche, nom_de_fonction, "transfere")
                rendu["fait"] = True
                return await params.result_callback(resultat, *args, **kwargs)
            # 4. Failed transfer: the request is passed on, said, never a silence (C9).
            rendu["fait"] = True
            await transmettre(
                f"transfer failed ({(resultat or {}).get('reason', 'unknown')})", rappel=True
            )

        await manager._create_transfer_call_handler(outil_de_transfert, nom_de_fonction)(
            dataclasses.replace(params, result_callback=au_resultat)
        )
        if not rendu:
            # The transfer handler returned without an outcome: never leave the model waiting.
            await transmettre("transfer gave no outcome", rappel=True)

    return gestionnaire


def delai_du_transfert(tool: Any) -> float:
    """Pipecat's deadline for this action: the transfer's own, plus the sentences."""
    from api.services.integrations.connectors.outil import config_de

    try:
        attente = int(((config_de(tool).get("reglages") or {}).get("delai_transfert_s")) or 30)
    except (TypeError, ValueError):
        attente = 30
    return float(min(max(attente, 5), 120)) + 75.0
