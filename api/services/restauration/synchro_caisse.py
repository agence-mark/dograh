"""[.mark] Module Restauration, lot 9 : ce que la caisse dit de la carte, des ruptures et de l'état du restaurant, versé dans le classeur.

Générique : il ne lit que la FICHE de la prise (``capacites``) et ses gestes communs ; jamais le nom d'un fournisseur. Chaque morceau (carte, ruptures,
état) est indépendant : l'échec de l'un ne perd pas les autres et se voit (liaison « erreur » avec un code fermé, jamais un texte de fournisseur). Rejouable
sans effet double : on n'écrit que ce qui change et l'on n'émet dans le flux que ce qui a changé.

Ce que la caisse porte prime sur le portail (E-49) : l'état du restaurant écrit ici est en lecture seule dans le portail. Les horaires de la caisse sont
COMPARÉS à ceux de la fiche de l'établissement : s'ils diffèrent, la liaison porte l'avertissement ``horaires_differents``, jamais un écrasement.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger

from api.db.bases_clients import restauration
from api.db.bases_clients import restauration_liaison as liaison_db
from api.db.bases_clients.restauration_commun import Connexion, maintenant
from api.db.bases_clients.restauration_reglage import (
    reglages_du_module,
    source_tenue_ici,
)
from api.services.restauration import flux
from api.services.restauration.prises.import_carte import importer_selon_la_portee
from api.services.restauration.prises.prise import Prise


def code_d_erreur(erreur: BaseException) -> str:
    """Le code fermé d'une erreur de prise (``ErreurHubrise.code``…) ; tout le reste : ``reponse_inattendue``. Jamais le texte."""
    code = getattr(erreur, "code", None)
    return code if code in liaison_db.CODES_D_ERREUR else "reponse_inattendue"


async def dire_la_liaison(connexion: Connexion, organization_id: int, etablissement_id: int, etat: str, erreur: str | None = None, *, synchro: bool = False) -> None:
    """Change l'état de la liaison ; le flux (``caisse.liaison``) n'est émis que si l'état a CHANGÉ."""
    if await liaison_db.marquer_la_liaison(connexion, etablissement_id, etat, erreur, synchro=synchro):
        await flux.emettre(organization_id, etablissement_id, "caisse.liaison", {"etat": etat})


def _creneaux(horaires: dict | None) -> dict[str, list[tuple[str, str]]]:
    return {jour: sorted((c["from"], c["to"]) for c in (liste or [])) for jour, liste in (horaires or {}).items() if liste}


def horaires_differents(caisse: dict | None, fiche: dict | None) -> bool:
    """Vrai si la caisse a posé des horaires et qu'ils ne sont pas ceux de la fiche. Une caisse sans horaires ne signale rien."""
    return caisse is not None and _creneaux(caisse) != _creneaux(fiche)


async def appliquer_l_etat(connexion: Connexion, organization_id: int, etablissement_id: int, etat: dict[str, Any]) -> bool:
    """L'état lu chez la caisse (mode, minutes, reprise, temps de préparation, horaires) -> classeur. ``True`` si changé (``caisse.etat`` émis)."""
    if await source_tenue_ici(connexion, etablissement_id, "etat"):
        return False  # l'état est tenu ici (F4) : on ne lit plus celui de la caisse
    horaires = None if await source_tenue_ici(connexion, etablissement_id, "horaires") else etat.get("horaires")
    change = await liaison_db.poser_etat_de_la_caisse(connexion, etablissement_id, etat, horaires=horaires)
    if horaires is not None:
        ecart = horaires_differents(horaires, await liaison_db.horaires_de_l_etablissement(connexion, etablissement_id))
        actuels = (await liaison_db.liaison(connexion, etablissement_id) or {}).get("avertissements", [])
        voulus = sorted(set(actuels) - {"horaires_differents"} | ({"horaires_differents"} if ecart else set()))
        if voulus != sorted(actuels):
            await liaison_db.poser_la_veille(connexion, etablissement_id, avertissements=voulus)
    if change:
        donnees: dict[str, Any] = {"mode": etat["mode"]}
        if etat["mode"] == "deborde":
            donnees["minutes_en_plus"] = int(etat.get("minutes_en_plus") or 0)
        if etat.get("reprise") is not None:
            donnees["reprise"] = etat["reprise"]
        await flux.emettre(organization_id, etablissement_id, "caisse.etat", donnees)
    return change


async def appliquer_les_ruptures(
    connexion: Connexion, organization_id: int, etablissement_id: int, ruptures: list[dict], *, complet: bool
) -> int:
    """Les ruptures lues chez la caisse -> classeur (source ``caisse``). ``complet`` : la liste est tout l'inventaire, un produit qu'elle ne cite plus
    et qui était en rupture par la caisse est repris. Rend le nombre de changements ; chacun émet ``rupture.changee``."""
    if await source_tenue_ici(connexion, etablissement_id, "ruptures"):
        return 0  # les ruptures sont tenues ici (F4) : on ne lit plus celles de la caisse
    maintenant_ = await maintenant(connexion)
    connues = {r["code_caisse"]: r for r in await restauration.ruptures_du_restaurant(connexion, etablissement_id, maintenant_)}
    changements = 0
    cites = set()
    for r in ruptures:
        code = r["code_caisse"]
        cites.add(code)
        deja = code in connues  # une rupture ACTIVE dans le classeur
        fin = r.get("fin") if isinstance(r.get("fin"), datetime) and r["fin"] > maintenant_ else None
        if r["disponible"] == (not deja) and (not deja or (connues[code]["fin"] == fin)):
            continue
        pas = await restauration.poser_rupture(connexion, etablissement_id, code, r["disponible"], fin, "caisse")
        if pas.statut != "OK":
            continue  # un code que la carte ne connaît pas (INTROUVABLE) : jamais inventé
        changements += 1
        await flux.emettre(organization_id, etablissement_id, "rupture.changee", {"code_caisse": code, "disponible": r["disponible"], **({"fin": fin} if fin else {})})
    if complet:
        for code, r in connues.items():
            if code not in cites and r["source"] == "caisse":
                pas = await restauration.poser_rupture(connexion, etablissement_id, code, True, None, "caisse")
                if pas.statut == "OK":
                    changements += 1
                    await flux.emettre(organization_id, etablissement_id, "rupture.changee", {"code_caisse": code, "disponible": True})
    return changements


async def importer_la_caisse(prise: Prise, connexion: Connexion, organization_id: int, etablissement_id: int) -> dict[str, Any]:
    """Import complet au branchement, relecture de nuit et sur ``catalog.update`` : carte, ruptures, état. Chaque morceau selon la fiche de la prise.
    Rend ``{carte, ruptures, etat, erreur}`` ; une erreur laisse les autres morceaux faits et passe la liaison à « erreur » (code fermé)."""
    capacites = prise.capacites
    bilan: dict[str, Any] = {"carte": None, "ruptures": None, "etat": None, "erreur": None}
    morceaux = []
    ici = (await reglages_du_module(connexion, etablissement_id))["sources"]  # F4 : un objet tenu ici n'est plus lu chez la caisse
    if capacites.carte == "lue" and ici.get("carte") != "ici":
        morceaux.append(("carte", prise.lire_carte))
    if capacites.ruptures == "lues" and ici.get("ruptures") != "ici":
        morceaux.append(("ruptures", prise.lire_ruptures))
    if capacites.lit_l_etat and ici.get("etat") != "ici":
        morceaux.append(("etat", prise.lire_etat))
    for nom, lire in morceaux:
        try:
            lu = await lire()
            if nom == "carte":
                bilan["carte"] = await importer_selon_la_portee(connexion, etablissement_id, lu, "caisse")
            elif nom == "ruptures":
                bilan["ruptures"] = await appliquer_les_ruptures(connexion, organization_id, etablissement_id, lu, complet=True)
            elif lu is not None:
                bilan["etat"] = await appliquer_l_etat(connexion, organization_id, etablissement_id, lu)
        except Exception as erreur:  # noqa: BLE001 -- R1 : l'échec se voit (liaison « erreur »), les autres morceaux continuent
            bilan["erreur"] = code_d_erreur(erreur)
            logger.warning(f"[.mark] Till import ({nom}) failed for establishment {etablissement_id}: {type(erreur).__name__}")
            if bilan["erreur"] == "jeton_refuse":
                await dire_la_liaison(connexion, organization_id, etablissement_id, "rompue", "jeton_refuse")
                return bilan
    if bilan["erreur"]:
        await dire_la_liaison(connexion, organization_id, etablissement_id, "erreur", bilan["erreur"])
    else:
        await dire_la_liaison(connexion, organization_id, etablissement_id, "ok", synchro=True)
    return bilan
