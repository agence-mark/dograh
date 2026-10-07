"""[.mark] The two internal actions of the connector ``dossier`` (L6, V1 to V7).

``verifier_appelant`` (the code decides, V1):

1. The record is identified by the number calling (read from the CALL, never from the model;
   it identifies even when it does not count as a factor), else by a reference the caller gives. Once identified, the call stays on THAT record: an
   answer is always compared with it (no fishing across records within a call).
2. Factors (V2), each counted once: ``numero`` passes by itself when the number calling is one
   of the record's; ``question`` when every control field chosen by the client matches
   (``comparer``); ``code_sms`` when the code sent to the record's mobile is given back.
3. A question answered wrong, or a wrong code, is a failed attempt. Two failed attempts (V6):
   blocked for the rest of the call, nothing is ever read, a call-back by a human is noted
   (``services/apres_appel/rappels.py``) and a sentence of the catalogue is SAID by the code.
4. The model gets the outcome only: verified or not, which kinds of data it may now read, what
   to ask next, attempts left. Never the record, never the expected answer, never whether a
   record exists for this number.
5. Every attempt is noted for the after-call (``verification_appelant``: the record's id, the
   factors tried and passed, the result) -- never what the caller said, never the code.

``lire_dossier`` returns NOTHING unless the level required for that kind of data is reached in
THIS call's state (Redis, ``etat``); then only the fields declared readable.

Off unless the agent's switch ``verification_appelant`` is on (V7, X2).
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

from loguru import logger

from api.schemas.verification import (
    CODE_LONGUEUR,
    CODE_VALIDITE_S,
    TENTATIVES_MAX,
    TYPES_LISIBLES,
    ReglagesVerification,
)
from api.services.apres_appel.rappels import CLE_RAPPEL, ORIGINE_VERIFICATION
from api.services.integrations.connectors.outil import CLE_A_DIRE, CLE_A_NOTER
from api.services.verification import etat as etats
from api.services.verification import source as sources
from api.services.verification.comparer import egal
from api.services.verification.reglages import interrupteur_allume, lire_reglages
from api.services.verrou import Occupe, verrou

CLE_TRACE = "verification_appelant"
CLE_LECTURES = "dossier_lu"
VARIABLE_PHRASE_RAPPEL = "phrase_verification_rappel"
PHRASE_RAPPEL_DEFAUT = (
    "Je ne peux pas vous donner ces informations sans vérifier votre identité : "
    "je note votre demande, un collègue vous rappelle."
)
INDISPONIBLE = {
    "status": "unavailable",
    "instruction": (
        "Caller verification is not available: never give any information from a record; "
        "offer that a colleague calls back."
    ),
}
JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre")


class Indisponible(RuntimeError):
    pass


async def _contexte(ctx) -> tuple[ReglagesVerification, Any]:
    """The settings, once checked that THIS call's agent switched the verification on."""
    from api.db import db_client

    if not ctx.organization_id or not ctx.run_id:
        raise Indisponible("no organization or no run")
    run, organisation = await db_client.get_workflow_run_with_context(ctx.run_id)
    if run is None or organisation != ctx.organization_id:
        raise Indisponible("run of another organization")
    definition = getattr(run, "definition", None)
    if not interrupteur_allume(getattr(definition, "workflow_configurations", None)):
        raise Indisponible("switched off for this agent")
    return await lire_reglages(ctx.organization_id), run


def lisibles(reglages: ReglagesVerification, etat: etats.Etat) -> list[str]:
    if etat.bloque or not etat.dossier:
        return []
    actifs = len(reglages.facteurs_actifs())
    return [
        t for t, n in reglages.lisibles.items()
        if n.champs and n.facteurs_requis <= etat.niveau() and n.facteurs_requis <= actifs
    ]


def _a_demander(reglages: ReglagesVerification, etat: etats.Etat) -> list[str]:
    reste = []
    if reglages.question and "question" not in etat.reussis:
        reste += reglages.champs_controle
    if reglages.code_sms and "code_sms" not in etat.reussis:
        reste.append("code_sms")
    return reste


async def _garder(org: int, run_id: int, etat: etats.Etat) -> None:
    """The state kept even if the tool's deadline cancels the call meanwhile (``shield``): a
    failed attempt or a code sent is never lost for being slow."""
    await asyncio.shield(etats.enregistrer(org, run_id, etat))


async def _envoyer_code(ctx, run, dossier: dict, etat: etats.Etat, delai: float) -> bool:
    """V5: the code by the client's Twilio, DURING the call. Wired, off, never tried for real:
    proven by stand-ins only. False when it cannot leave (no mobile, no account, timeout)."""
    from api.schemas.apres_appel import est_un_mobile, numero_e164
    from api.services.apres_appel import sms
    from api.services.telephony.factory import get_telephony_provider_for_run

    mobile = next(
        (n for n in (numero_e164(t) for t in dossier.get("telephones") or []) if est_un_mobile(n)), None
    )
    if not mobile or etat.code_envois >= TENTATIVES_MAX:
        return False
    fournisseur = await get_telephony_provider_for_run(run, ctx.organization_id)
    sid, jeton = getattr(fournisseur, "account_sid", None), getattr(fournisseur, "auth_token", None)
    expediteur = getattr(fournisseur, "default_from_number", None) or next(
        iter(getattr(fournisseur, "from_numbers", None) or []), None
    )
    if not (sid and jeton and expediteur):
        return False
    code, sel, empreinte = etats.nouveau_code(CODE_LONGUEUR)
    texte = f"Votre code de vérification : {code}. Il expire dans {CODE_VALIDITE_S // 60} minutes."
    await asyncio.wait_for(sms.envoyer(sid, jeton, expediteur, mobile, texte), timeout=delai)
    etat.code_empreinte, etat.code_sel = empreinte, sel
    etat.code_expire = time.time() + CODE_VALIDITE_S
    etat.code_envois += 1
    return True


def _phrase(ctx) -> str:
    from api.utils.template_renderer import render_template

    brut = (ctx.appel or {}).get(VARIABLE_PHRASE_RAPPEL)
    texte = brut if isinstance(brut, str) and brut.strip() else PHRASE_RAPPEL_DEFAUT
    return " ".join(str(render_template(texte, {}) or "").split())


async def verifier(arguments: dict, ctx, delai_s: float) -> dict:
    debut = time.monotonic()
    try:
        reglages, run = await _contexte(ctx)
    except Indisponible as raison:
        logger.info(f"[.mark] Caller verification unavailable: {raison}")
        return dict(INDISPONIBLE)
    org, run_id = ctx.organization_id, ctx.run_id
    # Pipecat runs the tool calls of a turn in parallel: read, compare, write is ONE step per
    # call, or four wrong answers would count as two attempts and a success could be overwritten.
    try:
        async with verrou(f"verification:{int(org)}:{int(run_id)}", attente_s=max(1.0, delai_s - 0.5)):
            return await _verifier(arguments, ctx, delai_s, debut, reglages, run)
    except Occupe:
        logger.warning("[.mark] Caller verification busy, nothing read")
        return dict(INDISPONIBLE)


async def _verifier(arguments: dict, ctx, delai_s: float, debut: float, reglages: ReglagesVerification, run) -> dict:
    org, run_id = ctx.organization_id, ctx.run_id
    etat = await etats.charger(org, run_id)
    source = sources.source_de(reglages)
    if etat.bloque:
        return {"status": "blocked", "readable": [],
                "instruction": "The caller could not be verified: read nothing; a colleague calls back."}
    def reste() -> float:
        return max(0.3, delai_s - (time.monotonic() - debut) - 0.3)

    # 1. The record: by the number calling, else by a reference given; then always the same.
    dossier = None
    appelant = (ctx.appel or {}).get("caller_number")
    if etat.dossier:
        dossier = await sources.lire(org, etat.source or source, etat.dossier, delai=reste())
    else:
        # The number identifies the record even when it does not count as a factor.
        if appelant:
            dossier = await sources.trouver(org, source, telephone=appelant, delai=reste())
        if dossier is None and arguments.get("reference"):
            dossier = await sources.trouver(org, source, reference=str(arguments["reference"]), delai=reste())
        if dossier is not None:
            etat.source, etat.dossier = source, str(dossier["id_externe"])

    essayes: list[str] = []
    rate = False
    from api.schemas.apres_appel import numero_e164

    # 2a. The number calling (from the call, never the model).
    numeros = {numero_e164(t) for t in (dossier or {}).get("telephones") or []}
    if reglages.numero and dossier and "numero" not in etat.reussis and numero_e164(appelant) in numeros - {None}:
        essayes.append("numero")
        etat.reussis.append("numero")

    # 2b. The control question: every field chosen, compared by the code.
    reponses = {c: arguments.get(c) for c in reglages.champs_controle if arguments.get(c) not in (None, "")}
    if reglages.question and "question" not in etat.reussis and reponses:
        manquants = [c for c in reglages.champs_controle if c not in reponses]
        if manquants:
            await _garder(org, run_id, etat)
            return {"status": "ask", "ask_for": manquants,
                    "instruction": "Ask the caller for these too, then call again with all of them."}
        essayes.append("question")
        if dossier is not None and all(egal(c, reponses[c], dossier) for c in reglages.champs_controle):
            etat.reussis.append("question")
        else:
            rate = True

    # 2c. The code by SMS (V5): the code given back is checked here; the send comes LAST.
    resultat_code: dict = {}
    envoi_demande = arguments.get("envoyer_code") in (True, "true", "oui", 1)
    if reglages.code_sms and "code_sms" not in etat.reussis and arguments.get("code"):
        essayes.append("code_sms")
        if etats.code_juste(etat, str(arguments["code"]), time.time()):
            etat.reussis.append("code_sms")
            etat.code_empreinte = etat.code_sel = etat.code_expire = None
        else:
            rate = True
        envoi_demande = False

    if rate:
        etat.tentatives_echouees += 1
    if etat.tentatives_echouees >= TENTATIVES_MAX:
        etat.bloque = True
    # The attempt is kept BEFORE anything slow (the send): a deadline must not lose a failure.
    try:
        await _garder(org, run_id, etat)
    except Exception as erreur:  # noqa: BLE001 -- fail closed: nothing is readable
        logger.error(f"[.mark] Verification state not kept, nothing readable: {erreur!r}")
        return dict(INDISPONIBLE)

    if envoi_demande and reglages.code_sms and "code_sms" not in etat.reussis and not etat.bloque:
        envoye = False
        if dossier is not None:
            try:
                envoye = await _envoyer_code(ctx, run, dossier, etat, reste())
            except Exception as erreur:  # noqa: BLE001 -- never raises during a call: logged
                logger.warning(f"[.mark] Verification code not sent: {erreur!r}")
        resultat_code = (
            {"code": "sent", "instruction": "Ask the caller for the code he just received by SMS, then call again with « code »."}
            if envoye else {"code": "not_sent"}
        )
        if envoye:
            try:
                await _garder(org, run_id, etat)  # the digest of the code just sent
            except Exception as erreur:  # noqa: BLE001 -- fail closed: no code is expected
                logger.error(f"[.mark] Verification state not kept after the send: {erreur!r}")
                return dict(INDISPONIBLE)

    peut_lire = lisibles(reglages, etat)
    issue = (
        "bloque" if etat.bloque
        else "echec" if rate
        else "verifie" if peut_lire
        else "insuffisant"
    )

    trace = {"le": datetime.now(UTC).isoformat(), "source": etat.source or source, "dossier": etat.dossier,
             "facteurs_essayes": essayes, "facteurs_reussis": sorted(set(etat.reussis)), "resultat": issue}
    notes: dict = {CLE_TRACE: trace} if (essayes or issue == "bloque") else {}
    if issue == "bloque":
        notes[CLE_RAPPEL] = {"origine": ORIGINE_VERIFICATION, "mode": "rappel", "raison": "caller not verified",
                             "numero": appelant or None, "le": trace["le"]}
        return {"status": "blocked", "readable": [],
                "instruction": "The caller could not be verified: read nothing; a call-back by a colleague was noted and said; go on with the call.",
                CLE_A_DIRE: _phrase(ctx), CLE_A_NOTER: notes}
    sortie: dict = {
        "status": "verified" if peut_lire else "not_verified",
        "readable": peut_lire,
        "attempts_left": TENTATIVES_MAX - etat.tentatives_echouees,
        **resultat_code,
    }
    if not peut_lire:
        demander = _a_demander(reglages, etat)
        sortie["ask_for"] = demander
        sortie.setdefault(
            "instruction",
            "Do not give any information from a record. Ask the caller for: " + ", ".join(demander) + "."
            if demander else "The caller cannot be verified with the factors set: offer a call-back by a colleague.",
        )
    if notes:
        sortie[CLE_A_NOTER] = notes
    return sortie


def _date(iso: str | None, heure: bool) -> str | None:
    from zoneinfo import ZoneInfo

    try:
        m = datetime.fromisoformat(str(iso)).astimezone(ZoneInfo("Europe/Paris"))
    except (TypeError, ValueError):
        return None
    jour = "1er" if m.day == 1 else str(m.day)
    texte = f"{JOURS[m.weekday()]} {jour} {MOIS[m.month - 1]} {m.year}"
    if heure:
        texte += f" à {m.hour} h" + (f" {m.minute:02d}" if m.minute else "")
    return texte


def _presenter(quoi: str, element: dict, champs: list[str]) -> dict:
    sortie = {}
    for c in champs:
        v = element.get(c)
        if v in (None, ""):
            continue
        if c in ("creee_le", "debut", "fin"):
            v = _date(v, heure=c != "creee_le") or v
        sortie[c] = v
    return sortie


async def lire(arguments: dict, ctx, delai_s: float) -> dict:
    quoi = str(arguments.get("quoi") or "")
    if quoi not in TYPES_LISIBLES:
        return {"status": "refused", "reason": "unknown_kind", "kinds": list(TYPES_LISIBLES)}
    try:
        reglages, _run = await _contexte(ctx)
    except Indisponible:
        return {"status": "refused", "reason": "not_verified",
                "instruction": "Do not give any information from a record."}
    etat = await etats.charger(ctx.organization_id, ctx.run_id)
    if quoi not in lisibles(reglages, etat):
        # V1: nothing of the record, whatever the model claims.
        return {"status": "refused", "reason": "not_verified",
                "instruction": "The caller is not verified for this: call the verification first; never give any information from a record."}
    dossier = await sources.lire(ctx.organization_id, etat.source or sources.source_de(reglages), etat.dossier,
                                 delai=max(0.3, delai_s - 0.3))
    if dossier is None:
        return {"status": "not_found", "instruction": "The record cannot be read now; offer a call-back by a colleague."}
    champs = reglages.lisibles[quoi].champs
    elements = [_presenter(quoi, e, champs) for e in dossier.get(quoi) or [] if isinstance(e, dict)]
    return {
        "status": "ok",
        "quoi": quoi,
        "elements": elements,
        CLE_A_NOTER: {CLE_LECTURES: {"le": datetime.now(UTC).isoformat(), "quoi": quoi,
                                     "nombre": len(elements), "dossier": etat.dossier}},
    }


async def executer(action, arguments: dict, ctx, delai_s: float) -> dict:
    """``executer_interne`` of the connector ``dossier``."""
    if action.nom == "verifier_appelant":
        return await verifier(arguments, ctx, delai_s)
    if action.nom == "lire_dossier":
        return await lire(arguments, ctx, delai_s)
    raise RuntimeError(f"Unknown record action « {action.nom} ».")
