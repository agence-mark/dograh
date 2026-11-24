"""[.mark] Chantier Partie 1, lot 4 (n° 149, 150) : monte les bases de retouches des agents installés à la forme actuelle (``services/gabarits/forme.py``).

    python -m api.outils.monter_la_forme                 # compte ce qui serait monté, n'écrit rien
    python -m api.outils.monter_la_forme --ecrire        # monte et écrit
    python -m api.outils.monter_la_forme --ecrire --organisation 42

Idempotent : une base déjà à la forme actuelle n'est pas touchée, rejouer ne change rien. Une base d'avant les réglages d'étape reprend les réglages de l'agent tel qu'il est
(elle valait ce que l'agent porte : jamais une retouche inventée). L'empreinte des retouches est recalculée avec la base montée ; l'ancienne base et son ancienne empreinte sont gardées dans ``retouches`` (``sauvegarde_avant_la_montee``), une fois. Ne lit ni n'écrit aucun secret.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import sys
from typing import Any

from api.db import db_client
from api.db.gabarits_client import etapes_de
from api.services.gabarits import diffusion as D
from api.services.gabarits import installation as I
from api.services.gabarits.forme import FORME_ACTUELLE, monter

PAGE = 200
CLE_DE_LA_SAUVEGARDE = "sauvegarde_avant_la_montee"  # dans ``retouches`` : ce que l'application portait avant sa montée (retour en arrière possible)


def _formes_en_attente(retouches: dict[str, Any]) -> dict[str, Any]:
    """Les formes gardées par une diffusion en attente (``forme`` de chaque étape) : montées aussi, sans agent à lire."""
    attente = copy.deepcopy(retouches.get("en_attente") or {})
    for etape in (attente.get("etapes") or {}).values():
        if isinstance(etape.get("forme"), dict):
            etape["forme"] = monter(etape["forme"])
    return attente


async def monter_une_application(application: dict[str, Any], *, ecrire: bool) -> int:
    """Rend le nombre de bases montées pour cette application (et les écrit si ``ecrire``)."""
    retouches = copy.deepcopy(application.get("retouches") or {})
    bases = retouches.get("base") or {}
    avant = {"base": copy.deepcopy(bases), "en_attente": copy.deepcopy(retouches.get("en_attente")), "empreinte_retouches": application.get("empreinte_retouches")}  # ce que l'application portait ; la suite n'y touche pas
    montees = 0
    for etape, wid in etapes_de(application["agents"]).items():
        base = bases.get(etape)
        if not isinstance(base, dict) or base.get("forme") == FORME_ACTUELLE:
            continue
        etat = await D._etat_actuel(wid)
        bases[etape] = monter(base, I.forme_de_l_agent(getattr(etat, "workflow_json", None)))
        montees += 1
    en_attente = retouches.get("en_attente")
    if en_attente:
        retouches["en_attente"] = _formes_en_attente(retouches)
        montees += int(retouches["en_attente"] != en_attente)
    if montees and ecrire:
        retouches.setdefault(CLE_DE_LA_SAUVEGARDE, avant)  # l'ancienne base et son empreinte, gardées une fois : un second passage ne les écrase jamais
        retouches["base"] = bases
        await db_client.ecrire_l_application(
            application["organization_id"], application["workflow_id"], retouches=retouches, empreinte_retouches=I.empreinte(bases)
        )
    return montees


async def monter_les_applications(*, ecrire: bool, organisation: int | None = None) -> dict[str, int]:
    """Toutes les applications du gabarit (d'une organisation, ou de toutes) : ``{applications, montees}``."""
    from api.services.gabarits import gabarit as G

    vues = montees = 0
    apres = 0
    while True:
        page = await db_client.applications_du_gabarit(G.RESTAURATION, organization_id=organisation, apres_id=apres, limite=PAGE)
        if not page:
            break
        for application in page:
            vues += 1
            montees += await monter_une_application(application, ecrire=ecrire)
        apres = page[-1]["id"]
    return {"applications": vues, "montees": montees}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--ecrire", action="store_true", help="écrit les bases montées (sans cela : compte seulement)")
    p.add_argument("--organisation", type=int, help="une seule organisation")
    a = p.parse_args()
    bilan = asyncio.run(monter_les_applications(ecrire=a.ecrire, organisation=a.organisation))
    print(f"{bilan['applications']} application(s) lue(s), {bilan['montees']} base(s) {'montée(s)' if a.ecrire else 'à monter'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
