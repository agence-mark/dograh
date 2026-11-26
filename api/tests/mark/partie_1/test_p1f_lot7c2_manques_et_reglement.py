"""[.mark] Lot 7b-C2, ce qui manque à la demande, le règlement, la remise et la commande introuvable (``restauration_commande``) : chaque refus fermé ne porte plus de texte (lot 7b-C7, A3) ;
le texte d'avant se refait toujours de ses seuls faits (``textes_de_secours_commande``) ou vient du catalogue des manques (``phrases_du_manque``)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from api.db.bases_clients import restauration_commande as RC
from api.db.bases_clients import textes_de_secours_commande as TSC
from api.services.commande import textes_de_secours as TS
from api.services.commande.phrases_du_manque import Manque, phrase_du_manque
from api.tests.mark import test_base_client as BASE
from api.tests.mark import test_restauration_classeur_commande as CLASSEUR

# Les fixtures du classeur, reprises par affectation (jamais d'import qui ne sert qu'à les enregistrer).
base_essai, base_prete, commerce = BASE.base_essai, BASE.base_prete, CLASSEUR.commerce
brouillon, enregistrer = CLASSEUR.brouillon, CLASSEUR.enregistrer

MAINTENANT = datetime(2026, 11, 12, 12, 0, tzinfo=ZoneInfo("Europe/Paris"))
TEL = "+33612345678"


def _verifie(r, statut: str, texte: str, secours, manque: str | None = None):
    """C7 (A3) : le refus ne porte plus de texte ; le texte d'avant se refait toujours de ses seuls faits (il sort avec le catalogue, lot B)."""
    assert (r.statut, r.suggestion, r.manque) == (statut, "", manque), r
    assert secours(r.faits) == texte, r


def _demande(**plus) -> dict:
    return {"mode": "emporter", "lignes": [{"code_caisse": "X"}], "client": {"telephone": TEL}, **plus}


def _manque(brouillon_: dict, jeton: str | None = "relu-1"):
    return RC._manques_de_la_demande(brouillon_, jeton, MAINTENANT)


def _doit(r, statut: str, texte: str, manque: str, du_catalogue: Manque | None = None, secours=None):
    assert (r.statut, r.suggestion, r.manque) == (statut, "", manque), r
    assert r.faits == {}, r
    if du_catalogue is not None:
        assert phrase_du_manque(du_catalogue) == texte
    else:
        assert secours(r.faits) == texte


# --- ce qui manque à la demande ---------------------------------------------------------------------------------------------------------------------


def test_manque_les_articles():
    _doit(_manque(_demande(lignes=[])), "INCOMPLETE", "Qu'est-ce que je vous mets ?", "lignes", Manque.ARTICLES)


def test_manque_le_telephone():
    _doit(_manque(_demande(client={})), "INCOMPLETE", "Quel est votre numéro de téléphone ?", "telephone", Manque.TELEPHONE)


def test_manque_l_adresse_de_livraison():
    _doit(_manque(_demande(mode="livraison")), "INCOMPLETE", "Quelle est l'adresse de livraison ?", "adresse", Manque.ADRESSE_ET_COMMUNE)


def test_manque_la_zone():
    _doit(_manque(_demande(mode="livraison", adresse={"commune": "Senlis"})), "INCOMPLETE", "Je dois situer l'adresse de livraison.", "zone", secours=TSC.situer_l_adresse)


def test_manque_la_relecture():
    _doit(_manque(_demande(), None), "INCOMPLETE", "Je vous relis la commande avant de l'enregistrer.", "relecture", secours=TSC.relire_la_commande)


def test_origine_invalide():
    _doit(_manque(_demande(cree_par="pigeon")), "ARGUMENT_INVALIDE", "Origine de la commande invalide.", "cree_par", secours=TSC.origine_invalide)


def test_heure_non_valable():
    _doit(_manque(_demande(heure_voulue=MAINTENANT.replace(hour=9))), "ARGUMENT_INVALIDE", "L'heure demandée n'est pas valable.", "heure_voulue", secours=TSC.heure_non_valable)


def test_prenom_trop_long():
    _doit(_manque(_demande(client={"telephone": TEL, "prenom": "x" * 61})), "ARGUMENT_INVALIDE", "Prénom trop long.", "prenom", secours=TSC.prenom_trop_long)


# --- le règlement -----------------------------------------------------------------------------------------------------------------------------------


def _reglages(**module) -> dict:
    return {"moyens_paiement": ["carte", "especes", "titre_restaurant"], "plafond_titre": 2500, "module": {"titre_alcool_exclu": False, "titre_sans_rendu": False, **module}}


def _regle(moyens: list[dict], total: int = 2000, calculees: list[dict] | None = None, reglages: dict | None = None, **paiement):
    return RC._controler_le_reglement({"paiement": {"moyens": moyens, **paiement}}, reglages or _reglages(), total, calculees or [])


def test_vous_reglez_comment():
    r = _regle([])
    _doit(r, "INCOMPLETE", "Vous réglez comment ?", "paiement", Manque.PAIEMENT)


def test_reglement_invalide():
    _verifie(_regle([{"moyen": "carte"}]), "ARGUMENT_INVALIDE", "Règlement invalide.", TSC.reglement_invalide, "paiement")


def test_moyen_non_accepte():
    r = _regle([{"moyen": "cheque", "montant": 2000}])
    _verifie(r, "MOYEN_NON_ACCEPTE", "Ce moyen de paiement n'est pas accepté.", TS.moyen_refuse)
    assert r.faits == {"moyen": "cheque", "acceptes": ["carte", "especes", "titre_restaurant"]}


def test_plafond_des_titres_restaurant():
    r = _regle([{"moyen": "titre_restaurant", "montant": 2600}], total=2600)
    _verifie(r, "PLAFOND_TITRE_RESTAURANT", "Le montant en titres-restaurant dépasse le plafond.", TSC.plafond_titre_depasse)
    assert r.faits == {"plafond": 2500, "montant": 2600}


def test_titres_restaurant_et_alcool():
    calculees = [{"alcool": True, "prix_unitaire": 1000, "quantite": 1}, {"alcool": False, "prix_unitaire": 1000, "quantite": 1}]
    r = _regle([{"moyen": "titre_restaurant", "montant": 2000}], 2000, calculees, _reglages(titre_alcool_exclu=True))
    _verifie(r, "PLAFOND_TITRE_RESTAURANT", "Les titres-restaurant ne paient pas l'alcool.", TSC.titre_et_alcool)
    assert r.faits == {"plafond": 1000, "montant": 2000, "raison": "alcool"}


def test_titres_restaurant_sans_rendu():
    r = _regle([{"moyen": "titre_restaurant", "montant": 2000}], 2000, None, _reglages(titre_sans_rendu=True), rendu_sur="titre_restaurant")
    _verifie(r, "MOYEN_NON_ACCEPTE", "On ne rend pas la monnaie sur un titre-restaurant.", TSC.titre_sans_rendu)
    assert r.faits["raison"] == "sans_rendu" and r.faits["moyen"] == "titre_restaurant"


def test_montant_de_paiement_invalide():
    _verifie(_regle([{"moyen": "carte", "montant": -5}]), "ARGUMENT_INVALIDE", "Montant de paiement invalide.", TSC.montant_de_paiement_invalide, "paiement")


def test_le_reglement_ne_couvre_pas_le_total():
    r = _regle([{"moyen": "carte", "montant": 1000}])
    _verifie(r, "INCOMPLETE", "Le règlement ne couvre pas exactement le total.", TSC.reglement_incomplet, "paiement")
    assert r.faits == {"total": 2000}


# --- la remise et la commande introuvable ------------------------------------------------------------------------------------------------------------


async def test_remise_qui_ne_s_applique_pas(commerce):
    r = await enregistrer(commerce, brouillon(remises=[{"ref": "INCONNUE"}]))
    _verifie(r, "REFUSEE", "Cette remise ne s'applique pas à votre commande.", TSC.remise_non_applicable)
    assert r.faits == {"raison": "remise_inconnue"}


async def test_commande_introuvable(commerce):
    r = await RC.statut_commande(commerce.c, commerce.a, telephone="+33600000000")
    _verifie(r, "INTROUVABLE", "Je ne trouve pas cette commande.", TSC.commande_introuvable)
    assert r.faits == {}
