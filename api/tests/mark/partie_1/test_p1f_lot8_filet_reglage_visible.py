"""[.mark] Plan final Partie 1, lot 8b-1b (audit 8b-1a, remarque 3 ; refus 18 : un chiffre du métier est toujours un réglage visible) : le délai du filet des commandes
retenues (``filet_retenue_min``) se lit et se règle dans les réglages du module de l'écran, avec sa valeur par défaut et ses bornes (celles de la migration 054).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from api.db.bases_clients.restauration_ecran import ecrire_les_reglages, reglages_pour_l_ecran
from api.db.bases_clients.restauration_reglage import PAR_DEFAUT_DU_MODULE, reglages_du_module
from api.schemas.restauration_ecran import ReglageChange, ReglageDuModule
from api.tests.mark import test_restauration_classeur_commande as _classeur

commerce = _classeur.commerce  # fixture du dossier reprise par nom


async def test_le_delai_du_filet_se_lit_et_se_regle_a_l_ecran(commerce):
    lu = await reglages_pour_l_ecran(commerce.c, commerce.a)
    assert lu["reglage"]["filet_retenue_min"] == PAR_DEFAUT_DU_MODULE["filet_retenue_min"] == ReglageDuModule().filet_retenue_min, lu["reglage"]
    change = ReglageChange(filet_retenue_min=7).model_dump(exclude_none=True)
    await ecrire_les_reglages(commerce.c, commerce.a, {"reglage": change}, "essai")
    assert (await reglages_pour_l_ecran(commerce.c, commerce.a))["reglage"]["filet_retenue_min"] == 7
    assert (await reglages_du_module(commerce.c, commerce.a))["filet_retenue_min"] == 7


@pytest.mark.parametrize("hors_bornes", [0, 121])
def test_le_delai_du_filet_a_les_bornes_de_la_base(hors_bornes):
    with pytest.raises(ValidationError):
        ReglageChange(filet_retenue_min=hors_bornes)


ECRAN = Path(__file__).resolve().parents[4] / "ui" / "src" / "components" / "mark" / "restauration"


@pytest.mark.parametrize("reglage", ["filet_retenue_min", "conservation_client_mois"])
def test_le_reglage_se_voit_et_s_enregistre_dans_l_ecran_des_reglages(reglage):
    """Reprise de l'audit de 8b-1b (refus 18 à moitié) : le réglage a son type, son champ dans « Réglages restaurant » et part avec l'enregistrement des réglages des
    commandes (voisin : la conservation de la fiche client se voyait sans jamais s'enregistrer). Lecture des sources de l'écran : forme seulement."""
    types = (ECRAN / "donnees.ts").read_text(encoding="utf-8")
    ecran = (ECRAN / "reglages-restaurant.tsx").read_text(encoding="utf-8")
    assert f"    {reglage}: number;" in types, reglage
    assert f"valeur={{String(reglage.{reglage})}}" in ecran, reglage
    sauver = ecran[ecran.index("const sauver = () => {"):]
    sauver = sauver[: sauver.index("};")]
    assert f"{reglage}: reglage.{reglage}" in sauver, reglage
