"""[.mark] Lot 7b-C2, ce qui manque à la demande, le règlement, la remise et la commande introuvable (``restauration_commande``) : chaque refus fermé ne porte plus de texte (lot 7b-C7, A3) ;
C7 B9 : le catalogue supprimé, ce que disait le texte d'avant est dans le statut, le manque et les faits (le texte reste écrit ici comme mémoire)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from api.db.bases_clients import restauration_commande as RC
from api.services.commande.phrases_du_manque import Manque
from api.tests.mark import test_base_client as BASE
from api.tests.mark import test_restauration_classeur_commande as CLASSEUR

# Les fixtures du classeur, reprises par affectation (jamais d'import qui ne sert qu'à les enregistrer).
base_essai, base_prete, commerce = BASE.base_essai, BASE.base_prete, CLASSEUR.commerce
brouillon, enregistrer = CLASSEUR.brouillon, CLASSEUR.enregistrer

MAINTENANT = datetime(2026, 11, 12, 12, 0, tzinfo=ZoneInfo("Europe/Paris"))
TEL = "+33612345678"


def _verifie(r, statut: str, faits: dict, manque: str | None = None):
    """C7 (A3) : le refus ne porte plus de texte ; B9 : ce que disait le texte d'avant est dans ses faits (ceux qu'il lisait, ou tous quand il était fixe)."""
    assert (r.statut, r.suggestion, r.manque) == (statut, "", manque), r
    assert ({k: r.faits.get(k) for k in faits} if faits else r.faits) == faits, r  # {} : le refus ne porte aucun fait


def _demande(**plus) -> dict:
    return {"mode": "emporter", "lignes": [{"code_caisse": "X"}], "client": {"telephone": TEL}, **plus}


def _manque(brouillon_: dict, jeton: str | None = "relu-1"):
    return RC._manques_de_la_demande(brouillon_, jeton, MAINTENANT)


def _doit(r, statut: str, texte: str, manque: str, du_catalogue: Manque | None = None):
    """``texte`` : le texte d'avant, gardé comme mémoire (B9) ; il était fixe : le statut, le manque et l'absence de faits portent tout ce qu'il disait."""
    assert (r.statut, r.suggestion, r.manque) == (statut, "", manque), r
    assert r.faits == {}, r


# --- ce qui manque à la demande ---------------------------------------------------------------------------------------------------------------------


def test_manque_les_articles():
    _doit(_manque(_demande(lignes=[])), "INCOMPLETE", "Qu'est-ce que je vous mets ?", "lignes", Manque.ARTICLES)


def test_manque_le_telephone():
    _doit(_manque(_demande(client={})), "INCOMPLETE", "Quel est votre numéro de téléphone ?", "telephone", Manque.TELEPHONE)


def test_manque_l_adresse_de_livraison():
    _doit(_manque(_demande(mode="livraison")), "INCOMPLETE", "Quelle est l'adresse de livraison ?", "adresse", Manque.ADRESSE_ET_COMMUNE)


def test_manque_la_zone():
    _doit(_manque(_demande(mode="livraison", adresse={"commune": "Senlis"})), "INCOMPLETE", "Je dois situer l'adresse de livraison.", "zone")


def test_manque_la_relecture():
    _doit(_manque(_demande(), None), "INCOMPLETE", "Je vous relis la commande avant de l'enregistrer.", "relecture")


def test_origine_invalide():
    _doit(_manque(_demande(cree_par="pigeon")), "ARGUMENT_INVALIDE", "Origine de la commande invalide.", "cree_par")


def test_heure_non_valable():
    _doit(_manque(_demande(heure_voulue=MAINTENANT.replace(hour=9))), "ARGUMENT_INVALIDE", "L'heure demandée n'est pas valable.", "heure_voulue")


def test_prenom_trop_long():
    _doit(_manque(_demande(client={"telephone": TEL, "prenom": "x" * 61})), "ARGUMENT_INVALIDE", "Prénom trop long.", "prenom")


# --- le règlement -----------------------------------------------------------------------------------------------------------------------------------


def _reglages(**module) -> dict:
    return {"moyens_paiement": ["carte", "especes", "titre_restaurant"], "plafond_titre": 2500, "module": {"titre_alcool_exclu": False, "titre_sans_rendu": False, **module}}


def _regle(moyens: list[dict], total: int = 2000, calculees: list[dict] | None = None, reglages: dict | None = None, **paiement):
    return RC._controler_le_reglement({"paiement": {"moyens": moyens, **paiement}}, reglages or _reglages(), total, calculees or [])


def test_vous_reglez_comment():
    r = _regle([])
    _doit(r, "INCOMPLETE", "Vous réglez comment ?", "paiement", Manque.PAIEMENT)


def test_reglement_invalide():
    _verifie(_regle([{"moyen": "carte"}]), "ARGUMENT_INVALIDE", {}, "paiement")


def test_moyen_non_accepte():
    r = _regle([{"moyen": "cheque", "montant": 2000}])
    _verifie(r, "MOYEN_NON_ACCEPTE", {'moyen': 'cheque', 'acceptes': ['carte', 'especes', 'titre_restaurant']})
    assert r.faits == {"moyen": "cheque", "acceptes": ["carte", "especes", "titre_restaurant"]}


def test_plafond_des_titres_restaurant():
    r = _regle([{"moyen": "titre_restaurant", "montant": 2600}], total=2600)
    _verifie(r, "PLAFOND_TITRE_RESTAURANT", {'plafond': 2500, 'montant': 2600})
    assert r.faits == {"plafond": 2500, "montant": 2600}


def test_titres_restaurant_et_alcool():
    calculees = [{"alcool": True, "prix_unitaire": 1000, "quantite": 1}, {"alcool": False, "prix_unitaire": 1000, "quantite": 1}]
    r = _regle([{"moyen": "titre_restaurant", "montant": 2000}], 2000, calculees, _reglages(titre_alcool_exclu=True))
    _verifie(r, "PLAFOND_TITRE_RESTAURANT", {'plafond': 1000, 'montant': 2000, 'raison': 'alcool'})
    assert r.faits == {"plafond": 1000, "montant": 2000, "raison": "alcool"}


def test_titres_restaurant_sans_rendu():
    r = _regle([{"moyen": "titre_restaurant", "montant": 2000}], 2000, None, _reglages(titre_sans_rendu=True), rendu_sur="titre_restaurant")
    _verifie(r, "MOYEN_NON_ACCEPTE", {'moyen': 'titre_restaurant', 'acceptes': ['carte', 'especes', 'titre_restaurant'], 'raison': 'sans_rendu'})
    assert r.faits["raison"] == "sans_rendu" and r.faits["moyen"] == "titre_restaurant"


def test_montant_de_paiement_invalide():
    _verifie(_regle([{"moyen": "carte", "montant": -5}]), "ARGUMENT_INVALIDE", {}, "paiement")


def test_le_reglement_ne_couvre_pas_le_total():
    r = _regle([{"moyen": "carte", "montant": 1000}])
    _verifie(r, "INCOMPLETE", {'total': 2000}, "paiement")
    assert r.faits == {"total": 2000}


# --- la remise et la commande introuvable ------------------------------------------------------------------------------------------------------------


async def test_remise_qui_ne_s_applique_pas(commerce):
    r = await enregistrer(commerce, brouillon(remises=[{"ref": "INCONNUE"}]))
    _verifie(r, "REFUSEE", {'raison': 'remise_inconnue'})
    assert r.faits == {"raison": "remise_inconnue"}


async def test_commande_introuvable(commerce):
    r = await RC.statut_commande(commerce.c, commerce.a, telephone="+33600000000")
    _verifie(r, "INTROUVABLE", {})
    assert r.faits == {}
