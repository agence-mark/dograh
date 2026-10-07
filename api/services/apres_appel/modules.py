"""[.mark] The after-call modules (A6, A7): set on the organization, switched on agent by
agent, off by default.

A module is one step of the chain: ``executer(contexte)`` does its sending and returns
what it did, or raises ``ModuleEnEchec`` (retried, A10). A new module = one entry in
``MODULES`` and its name in ``MODULES_CONNUS`` (``api/schemas/apres_appel.py``): the
chain does not change. L5 (connectors) and L6 (SMS) add theirs here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from api.schemas.apres_appel import ApresAppelAgent, ReglagesApresAppel
from api.services.apres_appel.reglages import CleManquante, secret

DELAI_WEBHOOK_S = 10.0
EN_TETE_SECRET = "X-Mark-Secret"


def nouveau_client(**options) -> httpx.AsyncClient:
    """The HTTP client of the modules (a test gives its stand-in here)."""
    return httpx.AsyncClient(**options)


class ModuleEnEchec(RuntimeError):
    """A sending failed. ``definitif``: retrying will not help (a setting is missing)."""

    def __init__(self, message: str, definitif: bool = False):
        super().__init__(message)
        self.definitif = definitif


class ModuleSansObjet(RuntimeError):
    """Nothing to send for this call (the step is shown « skipped », with the reason)."""


@dataclass
class ContexteModule:
    organization_id: int
    run: Any
    reglages: ReglagesApresAppel
    agent: ApresAppelAgent
    envoi: dict
    ecriture: dict = field(default_factory=dict)  # {appel_id, demande_id…} once written
    synthese: str | None = None
    tentative: int = 1
    fuseau: str | None = None  # the organization's timezone, for the texts


@dataclass
class ResultatModule:
    detail: str
    envois: list[dict] = field(default_factory=list)  # [{canal, destinataire, statut}]


Executeur = Callable[[ContexteModule], Awaitable[ResultatModule]]


def charge_utile(contexte: ContexteModule) -> dict:
    """What a module sends about the call: never the transcript, never the organization."""
    envoi = contexte.envoi
    return {
        "run_id": envoi.get("dograh_run_id"),
        "agent_id": envoi.get("dograh_workflow_id"),
        "agent": envoi.get("agent_nom"),
        "etablissement": envoi.get("etablissement"),
        "canal": envoi.get("canal"),
        "sens": envoi.get("sens"),
        "numero_appelant": envoi.get("numero_appelant"),
        "numero_appele": envoi.get("numero_appele"),
        "debut": envoi.get("debut"),
        "duree_s": envoi.get("duree_s"),
        "issue": envoi.get("issue"),
        "motif": envoi.get("motif"),
        "fiche": {c["nom"]: c["valeur"] for c in envoi.get("champs") or []},
        "demande": {
            **(envoi.get("demande") or {}),
            "id": contexte.ecriture.get("demande_id"),
        }
        if envoi.get("demande")
        else None,
        "appel_id": contexte.ecriture.get("appel_id"),
        "synthese": contexte.synthese,
    }


async def _webhook(contexte: ContexteModule) -> ResultatModule:
    reglage = contexte.reglages.webhook
    if not reglage.url:
        raise ModuleEnEchec(
            "No address set for the custom webhook (« After the call »).",
            definitif=True,
        )
    try:
        valeur = await secret(
            reglage.secret, contexte.organization_id, "webhook", "the webhook secret"
        )
    except CleManquante as erreur:
        raise ModuleEnEchec(str(erreur), definitif=True) from None
    try:
        async with nouveau_client(timeout=DELAI_WEBHOOK_S) as client:
            reponse = await client.post(
                reglage.url,
                json=charge_utile(contexte),
                headers={
                    EN_TETE_SECRET: valeur,
                    "Idempotency-Key": f"apres-appel-{contexte.run.id}",
                },
            )
    except httpx.HTTPError as erreur:
        raise ModuleEnEchec(
            f"The webhook does not answer ({type(erreur).__name__})."
        ) from None
    if reponse.status_code >= 400:
        raise ModuleEnEchec(
            f"The webhook answered HTTP {reponse.status_code}.",
            definitif=400 <= reponse.status_code < 500
            and reponse.status_code not in (408, 429),
        )
    return ResultatModule(
        detail=f"HTTP {reponse.status_code}",
        envois=[{"canal": "webhook", "destinataire": reglage.url, "statut": "envoyee"}],
    )


async def _connecteurs(contexte: ContexteModule) -> ResultatModule:
    """L5 (A1, A6; replaces D10 of the connectors plan): the actions that WRITE and fell back
    during the call (deadline, software down) are done now, through the same relay, with this
    run's organization (never one the call carries)."""
    from api.services.integrations.connectors.catalogue import trouver
    from api.services.integrations.connectors.execution import CLE_DIFFERES, appeler, contexte_de
    from api.services.integrations.connectors.nango import ConnexionAbsente, NangoIndisponible

    differes = (contexte.run.gathered_context or {}).get(CLE_DIFFERES) or []
    if not differes:
        raise ModuleSansObjet("No connector action was put aside during the call.")
    from api.db import db_client

    fiche = contexte.run.gathered_context or {}
    # A retry never redoes an action already done (a booking made twice is worse than none).
    bloc = await db_client.lire_apres_appel(contexte.run.id)
    faites = set(((bloc.get("etapes") or {}).get("module:connecteurs") or {}).get("faites") or [])
    envois, echecs = [], []
    for indice, entree in enumerate(differes):
        if indice in faites:
            continue
        trouve = trouver(entree.get("connecteur", ""), entree.get("action", ""))
        if trouve is None:
            echecs.append(f"unknown action {entree.get('connecteur')}.{entree.get('action')}")
            continue
        connecteur, action = trouve
        ctx = contexte_de(action, entree.get("reglages"), fiche, contexte.envoi.get("numero_appelant"))
        try:
            await appeler(contexte.organization_id, connecteur, action, entree.get("arguments") or {}, ctx, 20.0)
            faites.add(indice)
            await db_client.fusionner_apres_appel(
                contexte.run.id, etape="module:connecteurs", valeur={"faites": sorted(faites)}
            )
            envois.append({"canal": "agenda" if "agenda" in connecteur.nom else "crm", "destinataire": f"{connecteur.libelle} · {action.nom}", "statut": "envoyee"})
        except ConnexionAbsente as erreur:
            raise ModuleEnEchec(str(erreur), definitif=True) from None
        except (NangoIndisponible, Exception) as erreur:  # noqa: BLE001 -- retried by the chain
            echecs.append(f"{connecteur.nom}.{action.nom}: {erreur}")
    if echecs:
        raise ModuleEnEchec("; ".join(echecs))
    return ResultatModule(detail=f"{len(envois)} action(s) done after the call", envois=envois)


async def _sms(contexte: ContexteModule) -> ResultatModule:
    """L6 (plan sms-recapitulatif): the SMS to the caller and to the team, by the client's Twilio."""
    from api.db import db_client
    from api.services.apres_appel import sms
    from api.services.telephony.factory import get_telephony_provider_for_run

    reglage = contexte.agent.sms
    if not (reglage.appelant.actif or reglage.equipe.actif):
        raise ModuleSansObjet("No SMS switched on for this agent.")
    raison = sms.sans_objet(contexte.envoi)
    if raison:
        raise ModuleSansObjet(raison)
    fiche = sms.fiche_de_l_envoi(contexte.envoi)

    a_envoyer: list[tuple[str, str, str]] = []  # (who, number, text template)
    if reglage.appelant.actif:
        numero = sms.numero_de_l_appelant(contexte.run, contexte.envoi, contexte.agent.champ("numero_rappel"))
        if numero:
            a_envoyer.append(("appelant", numero, reglage.appelant.texte or ""))
    if reglage.equipe.actif:
        a_envoyer += [("equipe", n, reglage.equipe.texte or "") for n in reglage.equipe.numeros]
    if not a_envoyer:
        raise ModuleSansObjet("The caller's number is not a French mobile: no SMS.")

    try:
        fournisseur = await get_telephony_provider_for_run(contexte.run, contexte.organization_id)
    except Exception as erreur:  # noqa: BLE001 -- no telephony set: nothing to retry
        raise ModuleEnEchec(f"No telephony account to send the SMS ({type(erreur).__name__}).", definitif=True) from None
    sid, jeton = getattr(fournisseur, "account_sid", None), getattr(fournisseur, "auth_token", None)
    if not (sid and jeton):
        raise ModuleEnEchec("The SMS goes through a Twilio account of « Telephony »; none is set.", definitif=True)
    expediteur = reglage.expediteur or getattr(fournisseur, "default_from_number", None) or next(
        iter(getattr(fournisseur, "from_numbers", None) or []), None
    )
    if not expediteur:
        raise ModuleEnEchec("No sender: set a sender name or a number in « Telephony ».", definitif=True)

    # D6: what was already sent for this call is never sent again (a retry, a replay).
    bloc = await db_client.lire_apres_appel(contexte.run.id)
    deja = set(((bloc.get("etapes") or {}).get(sms.ETAPE) or {}).get("envoyes") or [])
    envois, echecs, definitif = [], [], True
    for qui, numero, modele in a_envoyer:
        cle = f"{contexte.run.id}:{numero}"
        texte, coupe = sms.remplir(modele, fiche)
        if cle in deja:
            envois.append({"canal": "sms", "destinataire": numero, "statut": "envoyee", "deja": True})
            continue
        try:
            await sms.envoyer(sid, jeton, expediteur, numero, texte)
        except sms.EchecTwilio as erreur:
            echecs.append(f"{qui}: {erreur}")
            definitif = definitif and erreur.definitif
            continue
        deja.add(cle)
        await db_client.fusionner_apres_appel(contexte.run.id, etape=sms.ETAPE, valeur={"envoyes": sorted(deja)})
        envois.append({"canal": "sms", "destinataire": numero, "statut": "envoyee", "coupe": coupe})
    if echecs:
        raise ModuleEnEchec("; ".join(echecs), definitif=definitif)
    return ResultatModule(detail=f"{len(envois)} SMS sent", envois=envois)


MODULES: dict[str, Executeur] = {
    "webhook": _webhook,
    # L5: the connector actions put aside during the call.
    "connecteurs": _connecteurs,
    # L6: the SMS to the caller and the team.
    "sms": _sms,
}
