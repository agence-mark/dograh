"""[.mark] The anticipated action (plan connecteurs-agent D17, D18).

A READ-ONLY action whose tool box « anticipable » is ticked (off by default) is launched as soon
as its trigger fields are known in the record (each write of the record goes through ``noter``,
the single write point of the tool, the postscript and the clerk), without waiting for the
model to call it. When the model calls it with the same parameters, it gets the result already
there, with no wait. Different parameters: the result is thrown away, the normal call runs.
⛔ Never an action that writes (refused at load and at save).

Each anticipation is stamped: launched, used or thrown away, time saved.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import OrderedDict
from dataclasses import dataclass, field

from loguru import logger

from api.services.integrations.connectors.catalogue import trouver
from api.services.integrations.connectors.execution import (
    appeler,
    arguments_permis,
    contexte_de,
    estampiller,
)


def cle(arguments: dict) -> str:
    return json.dumps(
        {k: str(v) for k, v in sorted(arguments.items())}, ensure_ascii=False
    )


@dataclass
class Lancement:
    cle: str
    tache: asyncio.Task
    debut: float
    fin: float | None = None


@dataclass
class OutilAnticipable:
    nom: str  # the function name the model sees
    config: dict
    organization_id: int
    lancements: dict[str, Lancement] = field(default_factory=dict)
    # l-agent-collegue (L5): the call an internal action reads (context, run).
    appel: dict = field(default_factory=dict)
    run_id: int | None = None


class Anticipateur:
    """The anticipations of ONE call (one record)."""

    def __init__(self) -> None:
        self.outils: dict[str, OutilAnticipable] = {}

    def inscrire(
        self,
        nom: str,
        config: dict,
        organization_id: int,
        appel: dict | None = None,
        run_id: int | None = None,
    ) -> None:
        trouve = trouver(config.get("connecteur", ""), config.get("action", ""))
        if (
            trouve is None
            or trouve[1].ecrit
            or not trouve[1].anticipable_permis
            or not config.get("anticipable")
        ):
            return
        self.outils[nom] = OutilAnticipable(
            nom, config, organization_id, appel=dict(appel or {}), run_id=run_id
        )

    def arguments_de_la_fiche(
        self, outil: OutilAnticipable, fiche: dict
    ) -> dict | None:
        """The action's parameters read in the record by the triggers (parameter → field);
        None while one is missing."""
        connecteur, action = trouver(outil.config["connecteur"], outil.config["action"])
        declencheurs = outil.config.get("declencheurs") or {}
        if not declencheurs:
            return None
        extraites = fiche.get("extracted_variables") or {}
        arguments = {}
        for parametre, champ in declencheurs.items():
            valeur = extraites.get(champ)
            if valeur in (None, "", [], {}):
                return None
            arguments[parametre] = valeur
        return arguments_permis(action, arguments)

    def sur_note(self, fiche: dict) -> None:
        for outil in self.outils.values():
            arguments = self.arguments_de_la_fiche(outil, fiche)
            if not arguments:
                continue
            k = cle(arguments)
            if k in outil.lancements:
                continue
            connecteur, action = trouver(
                outil.config["connecteur"], outil.config["action"]
            )
            ctx = contexte_de(
                action,
                outil.config.get("reglages"),
                fiche,
                outil.appel.get("caller_number"),
                organization_id=outil.organization_id,
                appel=outil.appel,
                run_id=outil.run_id,
            )
            delai = max(0.5, float(outil.config.get("delai_ms") or 5000) / 1000) * 3
            lancement = Lancement(k, None, time.monotonic())  # type: ignore[arg-type]

            # Every loop value bound now: the task runs after the loop has moved on (two
            # anticipable tools must never swap their organization or their deadline).
            async def lancer(
                lancement=lancement,
                outil=outil,
                connecteur=connecteur,
                action=action,
                arguments=arguments,
                ctx=ctx,
                delai=delai,
            ):
                try:
                    return await asyncio.wait_for(
                        appeler(
                            outil.organization_id,
                            connecteur,
                            action,
                            arguments,
                            ctx,
                            delai,
                        ),
                        timeout=delai,
                    )
                finally:
                    lancement.fin = time.monotonic()

            lancement.tache = asyncio.get_running_loop().create_task(lancer())
            outil.lancements[k] = lancement
            estampiller(
                fiche,
                {"outil": outil.nom, "anticipee": "lancee", "arguments": arguments},
            )

    def prendre(self, nom: str, arguments: dict, fiche: dict) -> asyncio.Task | None:
        """The anticipated result for these parameters, or None (the normal call runs).
        Launches with other parameters are thrown away, and stamped."""
        outil = self.outils.get(nom)
        if outil is None:
            return None
        k = cle(arguments)
        pris = None
        for cle_lancee, lancement in list(outil.lancements.items()):
            if cle_lancee == k and not (
                lancement.tache.done() and lancement.tache.exception()
            ):
                pris = lancement
                continue
            if not lancement.tache.done():
                lancement.tache.cancel()
            estampiller(
                fiche,
                {
                    "outil": nom,
                    "anticipee": "jetee",
                    "arguments": json.loads(cle_lancee),
                },
            )
            outil.lancements.pop(cle_lancee, None)
        if pris is None:
            return None
        outil.lancements.pop(k, None)
        gagne = int(((pris.fin or time.monotonic()) - pris.debut) * 1000)
        estampiller(
            fiche,
            {
                "outil": nom,
                "anticipee": "utilisee",
                "gain_ms": gagne,
                "prete": pris.tache.done(),
            },
        )
        return pris.tache


# One anticipator per call, found from its record. The record itself is kept with it and checked
# by identity (an id is reused once a dict is gone); bounded, the oldest calls leave first.
_MAX = 200
_PAR_FICHE: OrderedDict[int, tuple[dict, Anticipateur]] = OrderedDict()


def pour_la_fiche(fiche: dict, creer: bool = True) -> Anticipateur | None:
    entree = _PAR_FICHE.get(id(fiche))
    if entree is not None and entree[0] is fiche:
        return entree[1]
    if not creer:
        return None
    a = Anticipateur()
    _PAR_FICHE[id(fiche)] = (fiche, a)
    while len(_PAR_FICHE) > _MAX:
        _PAR_FICHE.popitem(last=False)
    return a


def oublier(fiche: dict) -> None:
    entree = _PAR_FICHE.get(id(fiche))
    if entree is not None and entree[0] is fiche:
        _PAR_FICHE.pop(id(fiche), None)


def apres_une_note(fiche: dict) -> None:
    """Called by ``noter`` after every note. Never raises: anticipating must not cost a note."""
    try:
        a = pour_la_fiche(fiche, creer=False)
        if a is not None and a.outils:
            a.sur_note(fiche)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Anticipation skipped: {erreur!r}")
