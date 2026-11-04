"""RA-A, R3 (b) (audit du 04/11, 02 B6) : une seule liste de noms réservés, contrôlée dans les deux sens.

Il y avait trois listes : la fiche (``NOMS_RESERVES``), les phrases du catalogue (``VARIABLES_RESERVEES``) et les
variables que le code pose (injections de ``run_pipeline.py``). Un objet refusait le nom d'une phrase mais pas
l'inverse ; ``annonce_pause`` ou ``direction`` passaient comme nom d'objet ; un champ de fiche pouvait prendre le nom
d'une variable posée par le code. Maintenant : une source (``schemas/noms_reserves.py``) que les validateurs
importent tous, et ce test échoue si un nom est refusé d'un côté seulement.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.routes.objets_agent import _verifier_le_nom
from api.schemas import fiche_agent, phrases
from api.schemas.fiche_agent import ChampFiche, verifier_champs
from api.schemas.phrases import Phrase
from api.services.objets_agent import noms_poses_par_le_code as posees
from api.services.variables_agent import catalogue


def _tous_les_noms() -> set[str]:
    """Chaque liste d'origine, plus ce que le code pose : la réunion de tout ce qu'un côté réserve."""
    return (
        set(fiche_agent.NOMS_RESERVES)
        | set(phrases.VARIABLES_RESERVEES)
        | set(posees.variables_posees_par_le_code())
    )


def _refuse_par_la_fiche(nom: str) -> bool:
    try:
        verifier_champs([ChampFiche(nom=nom)])
    except ValueError:
        return True
    return False


def _refuse_par_les_phrases(nom: str) -> bool:
    try:
        Phrase(variable=nom)
    except ValidationError:
        return True
    return False


async def _refuse_par_les_objets(nom: str) -> bool:
    try:
        await _verifier_le_nom(1, None, nom, None)
    except HTTPException:
        return True
    except Exception:  # le contrôle est allé jusqu'au catalogue de phrases : le nom n'était pas réservé
        return False
    return False


def test_la_liste_est_assez_fournie_pour_que_le_test_ne_soit_pas_vide():
    assert len(_tous_les_noms()) > 70


@pytest.mark.asyncio
async def test_un_nom_reserve_d_un_cote_l_est_des_quatre_cotes(monkeypatch):
    async def vide(organization_id):
        return []

    monkeypatch.setattr(catalogue, "_objets", vide)
    monkeypatch.setattr(catalogue, "_phrases", vide)
    du_catalogue = {v.cle for v in await catalogue.catalogue_de(1)}
    manques: list[str] = []
    for nom in sorted(_tous_les_noms()):
        refus = {
            "fiche": _refuse_par_la_fiche(nom),
            "phrases": _refuse_par_les_phrases(nom) if len(nom) >= 2 else True,
            "objets": await _refuse_par_les_objets(nom),
            "variables": nom in du_catalogue,
        }
        absents = [cote for cote, ok in refus.items() if not ok]
        if absents:
            manques.append(f"{nom}: pas refusé par {', '.join(absents)}")
    assert not manques, "Un nom réservé d'un côté seulement :\n" + "\n".join(manques)


def test_la_source_unique_couvre_ce_que_le_code_pose():
    """Une injection nouvelle de ``run_pipeline.py`` dont la clé n'est pas dans la liste unique fait échouer."""
    from api.schemas import noms_reserves

    absents = sorted(set(posees.variables_posees_par_le_code()) - set(noms_reserves.NOMS_RESERVES))
    assert not absents, f"posées par le code mais pas dans la liste unique : {absents}"


def test_les_trois_anciens_noms_sont_la_meme_liste():
    from api.schemas import noms_reserves

    assert fiche_agent.NOMS_RESERVES is noms_reserves.NOMS_RESERVES
    assert phrases.VARIABLES_RESERVEES is noms_reserves.NOMS_RESERVES
