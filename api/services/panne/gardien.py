"""[.mark] The outage guard of ONE call (L7, PN1, PN4, PN6, PN7, PN8; P2 to P13).

Built at pick-up for an agent that switched the fallback on (X2); ``declencher`` is called by the
triggers (``declencheurs``) when a part of the agent fails. Once per call, whatever fails next:

1. the state of the establishment AT THAT INSTANT (hours, forcing), its second number;
2. the instruction given to the live call through the client's Twilio (F4):
   - inbound, open (or no hours) with a second number: hand-over sentence, ring it (PN1);
   - inbound otherwise: the call-back promise with the reopening date, hang up (PN1);
   - outbound: an apology, hang up, alert only (PN4, P13);
   - no Twilio (browser, keyboard): nothing to give, the call ends; the record and the alert stay;
3. the hang-up of the serializer left aside for this call (C2), BEFORE Twilio is updated;
4. on the run: ``gathered_context["panne"]`` (read by the after-call: a request « to call back »,
   chantier L4), an event ``mark-panne`` (the section Incidents, PN8), disposition
   ``panne_technique``;
5. the alert to the notification addresses (PN6), now, not after the call.

⛔ Never raises: the worst would be a guard that kills a call that could still be saved.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from loguru import logger

from api.schemas.panne import (
    DEFAUT_EXCUSE,
    DEFAUT_RAPPEL,
    DEFAUT_RENVOI,
    VARIABLE_EXCUSE,
    VARIABLE_RAPPEL,
    VARIABLE_RENVOI,
    PanneAgent,
)
from api.services.panne import consigne, raccroche
from api.services.panne import twilio as client_twilio

TYPE_EVENEMENT = "mark-panne"
CLE_FICHE = "panne"
ISSUE = "panne_technique"
PARIS = ZoneInfo("Europe/Paris")


def _vide(valeur) -> bool:
    return valeur is None or (isinstance(valeur, str) and not valeur.strip())


@dataclass
class ContextePanne:
    run_id: int
    organization_id: int
    workflow_id: int
    reglages: PanneAgent
    entrant: bool
    call_sid: str | None = None  # None: no Twilio (browser, keyboard)
    run: Any = None  # the workflow run (its telephony account)
    url_resultat: str | None = None  # where Twilio posts the result of the hand-over
    reglages_annonce: Any = None  # the organization's forced state, if any
    workflow_configurations: dict = field(default_factory=dict)


class GardienPanne:
    def __init__(self, contexte: ContextePanne, engine: Any):
        self.contexte = contexte
        self.engine = engine
        self.decision: str | None = None
        self.rappel_prepare: str | None = None
        self._verrou = asyncio.Lock()

    # ---- what the call knows ------------------------------------------------

    def _variables(self) -> dict:
        return dict(getattr(self.engine, "_call_context_vars", None) or {})

    def _phrase(self, variable: str, defaut: str) -> str:
        valeur = self._variables().get(variable)
        return defaut if _vide(valeur) else str(valeur)

    def _etat(self, maintenant: datetime | None = None) -> tuple[str | None, str]:
        """(state, spoken reopening) at this instant; (None, "") without hours nor forcing."""
        from api.services.pipecat.etat_ouverture import (
            CLE_ETAT,
            CLE_REOUVERTURE,
            injecter_etat_ouverture,
        )

        horaires = self._variables().get("horaires_ouverture") or (
            self.contexte.workflow_configurations or {}
        ).get("horaires_ouverture")
        calcule = injecter_etat_ouverture(
            {},
            {"horaires_ouverture": horaires},
            maintenant=maintenant,
            reglages=self.contexte.reglages_annonce,
        )
        return calcule.get(CLE_ETAT), calcule.get(CLE_REOUVERTURE) or ""

    async def _second_numero(self) -> str | None:
        from api.services.etablissements.appel import etablissement_de_lappel

        servi = await etablissement_de_lappel(
            self.contexte.organization_id, self.contexte.workflow_id, self._variables()
        )
        numero = getattr(getattr(servi, "etablissement", None), "second_numero", None)
        return None if _vide(numero) else numero

    # ---- the decision ---------------------------------------------------------

    def consigne_de_rappel(self) -> str:
        from api.services.pipecat.etat_ouverture import rendre_annonce

        _, reouverture = self._etat()
        texte = rendre_annonce(
            self._phrase(VARIABLE_RAPPEL, DEFAUT_RAPPEL), reouverture
        ).strip()
        return consigne.rappel(
            texte or rendre_annonce(DEFAUT_RAPPEL, reouverture).strip()
        )

    async def _choisir(self) -> tuple[str, str | None, str | None, str | None]:
        """(decision, TwiML, second number, state). ``self.rappel_prepare``: what the result
        route says if the second number does not answer (computed now, with the call's context)."""
        from api.services.annonce.constantes import OUVERT, SUR_RENDEZ_VOUS

        if not self.contexte.call_sid:
            return "sans_telephonie", None, None, None
        if not self.contexte.entrant:
            return (
                "excuse",
                consigne.rappel(self._phrase(VARIABLE_EXCUSE, DEFAUT_EXCUSE)),
                None,
                None,
            )
        etat, _ = self._etat()
        numero = await self._second_numero()
        joignable = (
            etat in (OUVERT, SUR_RENDEZ_VOUS) or etat is None
        )  # no hours: always reachable
        if numero and joignable and self.contexte.url_resultat:
            self.rappel_prepare = self.consigne_de_rappel()
            twiml = consigne.renvoi(
                self._phrase(VARIABLE_RENVOI, DEFAUT_RENVOI),
                numero,
                self.contexte.reglages.sonnerie_s,
                self.contexte.url_resultat,
            )
            return "renvoi", twiml, numero, etat
        return "rappel", self.consigne_de_rappel(), numero, etat

    async def _donner_la_consigne(self, twiml: str) -> str | None:
        """The instruction to the live call; None when done, else why not."""
        from api.services.telephony.factory import get_telephony_provider_for_run

        try:
            fournisseur = await get_telephony_provider_for_run(
                self.contexte.run, self.contexte.organization_id
            )
        except Exception as erreur:  # noqa: BLE001
            return f"no telephony account ({type(erreur).__name__})"
        sid, jeton = (
            getattr(fournisseur, "account_sid", None),
            getattr(fournisseur, "auth_token", None),
        )
        if not (sid and jeton):
            return "the fallback needs a Twilio account"
        raccroche.marquer_renvoye(self.contexte.call_sid)
        try:
            await client_twilio.mettre_a_jour_appel(
                sid, jeton, self.contexte.call_sid, twiml
            )
            return None
        except client_twilio.TwilioIndisponible as erreur:
            raccroche.oublier(
                self.contexte.call_sid
            )  # the call is not handed over: hang up as before
            return str(erreur)

    async def declencher(self, raison: str, brique: str, detail: Any = None) -> str:
        """Once per call; returns the decision (the same on every later call)."""
        async with self._verrou:
            if self.decision is not None:
                return self.decision
            self.decision = "en_cours"
            try:
                decision, twiml, numero, etat = await self._choisir()
                echec = await self._donner_la_consigne(twiml) if twiml else None
                if echec:
                    logger.error(
                        f"[.mark] Outage fallback not given to Twilio: {echec}"
                    )
                    decision = "echec_twilio"
            except Exception as erreur:  # noqa: BLE001 -- the record and the alert still go
                logger.error(f"[.mark] Outage fallback failed: {erreur!r}")
                decision, numero, etat, echec = "echec", None, None, repr(erreur)
            self.decision = decision
            await self._noter(raison, brique, detail, decision, numero, etat, echec)
            return decision

    # ---- the record and the alert -------------------------------------------

    async def _noter(
        self, raison, brique, detail, decision, numero, etat, echec
    ) -> None:
        maintenant = datetime.now(PARIS)
        appelant = (
            self._variables().get("caller_number")
            if self.contexte.entrant
            else self._variables().get("called_number")
        )
        trace = {
            "raison": raison,
            "brique": brique,
            "decision": decision,
            "numero_renvoi": numero,
            "etat_ouverture": etat,
            "detail": None if detail is None else str(detail)[:300],
            "echec": echec,
            "heure": maintenant.isoformat(),
            "a_rappeler": appelant if self.contexte.entrant else None,
            "sens": "entrant" if self.contexte.entrant else "sortant",
            "consigne_rappel": self.rappel_prepare,
        }
        try:
            fiche = getattr(self.engine, "_gathered_context", None)
            if isinstance(fiche, dict):
                fiche[CLE_FICHE] = trace
            if hasattr(self.engine, "set_call_disposition"):
                self.engine.set_call_disposition(ISSUE)
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[.mark] Outage not written on the run: {erreur!r}")
        try:
            from api.services.analyse_run.incidents_appel import ATTRIBUT_JOURNAL

            journal = getattr(self.engine, ATTRIBUT_JOURNAL, None)
            if journal is not None:
                await journal.append({"type": TYPE_EVENEMENT, "payload": trace})
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[.mark] Outage event not logged: {erreur!r}")
        asyncio.get_running_loop().create_task(self._alerter(trace))

    async def _alerter(self, trace: dict) -> None:
        from api.services.apres_appel.notification import notifier

        libelle = {
            "renvoi": "renvoyé vers le second numéro",
            "rappel": "promesse de rappel dite",
            "excuse": "appel sortant, excuse dite",
            "sans_telephonie": "appel d'essai sans téléphonie",
        }.get(trace["decision"], f"repli non donné ({trace['decision']})")
        lignes = [
            f"Panne sur l'appel n° {self.contexte.run_id} : {trace['brique']} ({trace['raison']}).",
            f"Ce qui a été fait : {libelle}.",
        ]
        if trace.get("a_rappeler"):
            lignes.append(f"À rappeler : {trace['a_rappeler']}.")
        if trace.get("echec"):
            lignes.append(f"Échec : {trace['echec']}.")
        await notifier(
            self.contexte.organization_id,
            "Panne de l'agent, appel à rappeler",
            "\n".join(lignes),
        )
