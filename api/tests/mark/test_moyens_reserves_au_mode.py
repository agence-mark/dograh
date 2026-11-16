"""[.mark] M90 (appel 2574) : un moyen de paiement que la source réserve à certains modes n'est ni proposé ni accepté hors de ces modes.

Mécanisme commun du moteur de commande (``_le_reglement``) : la source déclare ``moyens_reserves_au_mode`` ; sans déclaration, rien ne change.
"""

from __future__ import annotations

from api.services.commande import moteur
from api.services.restauration.source_commande import SourceClasseur


class _Source:
    libelles_des_moyens = {"carte": "par carte", "especes": "en espèces", "a_la_porte": "à la porte"}
    moyens_reserves_au_mode = {"a_la_porte": ("livraison",)}

    async def reglages(self):
        return {"moyens_paiement": ["carte", "especes", "a_la_porte"]}


class _SansDeclaration(_Source):
    moyens_reserves_au_mode = None


async def test_hors_du_mode_le_moyen_reserve_n_est_ni_propose_ni_accepte():
    _, demande = await moteur._le_reglement(_Source(), {"mode": "emporter"}, 1000, {})
    assert demande.faits["acceptes"] == ["carte", "especes"], demande.faits
    _, refus = await moteur._le_reglement(_Source(), {"mode": "emporter"}, 1000, {"moyen": "a_la_porte"})
    assert refus.statut == "MOYEN_NON_ACCEPTE", refus


async def test_dans_son_mode_le_moyen_reserve_est_propose_et_accepte():
    _, demande = await moteur._le_reglement(_Source(), {"mode": "livraison"}, 1000, {})
    assert demande.faits["acceptes"] == ["carte", "especes", "a_la_porte"]
    paiement, refus = await moteur._le_reglement(_Source(), {"mode": "livraison"}, 1000, {"moyen": "a_la_porte"})
    assert refus is None and paiement["moyens"][0]["moyen"] == "a_la_porte"


async def test_sans_declaration_rien_ne_change():
    _, demande = await moteur._le_reglement(_SansDeclaration(), {"mode": "emporter"}, 1000, {})
    assert demande.faits["acceptes"] == ["carte", "especes", "a_la_porte"]


def test_le_module_restauration_reserve_la_carte_a_la_livraison_a_la_livraison():
    assert SourceClasseur.moyens_reserves_au_mode == {"carte_livraison": ("livraison",)}
