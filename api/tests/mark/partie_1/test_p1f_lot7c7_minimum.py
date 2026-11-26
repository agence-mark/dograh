"""[.mark] C7 B6 (F3) : le minimum de la livraison arrive au modèle en lettres.

« Pas juste une suppression » (Evan 25/11 ~10 h) : le texte « Le minimum de commande est de quinze euros » disait le montant ; ``A_FAIRE_DU_MINIMUM`` demande au modèle de le
dire, mais la copie allégée retire les montants en centimes (``CLES_CHIFFREES``). Le montant passe en fait brut en lettres (``minimum_dit``, ``manque_dit``), jamais une phrase.
"""

from __future__ import annotations

from api.services.actions_communes.enveloppe_legere import pour_le_modele
from api.services.commande import panier as P
from api.services.commande import porte
from api.services.commande.etat_pour_le_modele import CLE_CONNU, cle_du_chiffrage


def _en_livraison_sous_le_minimum(sous_total: int = 1200, minimum: int = 1500) -> dict:
    p = P.nouveau()
    p.update({"mode": "livraison", "zone": {"id": 7}, "commune_dite": "Senlis",
              "lignes": [{"n": 1, "nom": "Margherita", "code": "m", "quantite": 1, "choix": [], "retires": []}]})
    p[CLE_CONNU] = {"minimums": {"7": minimum}, "chiffrage": {"cle": cle_du_chiffrage("livraison", P.pour_le_chiffrage(p), 7), "sous_total": sous_total}}
    return p


def test_f3_le_modele_recoit_le_minimum_et_ce_qui_manque_en_lettres():
    """Client « C'est tout. » (livraison, il manque trois euros) / avant : le modèle n'a que des centimes retirés de sa copie / après : « Il y a quinze euros minimum pour la livraison,
    il vous manque trois euros : vous ajoutez quelque chose ? »."""
    p = _en_livraison_sous_le_minimum()
    faits = porte.faits_du_minimum(p)
    assert faits is not None, "le panier d'essai doit être sous le minimum"
    vu = pour_le_modele({"faits": {"minimum_de_la_commande": faits}})["faits"]["minimum_de_la_commande"]
    assert vu.get("minimum_dit") == "quinze euros" and vu.get("manque_dit") == "trois euros", vu


def test_f3_voisin_minimum_atteint_aucun_fait_du_minimum():
    assert porte.faits_du_minimum(_en_livraison_sous_le_minimum(sous_total=1500)) is None
