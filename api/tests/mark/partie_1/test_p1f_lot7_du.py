"""[.mark] Lot 7a, ``Du`` : ce qui est dû à la personne est constaté UNE fois, à la sortie de toute fiche, aux deux métiers (``du.constater``), et lu par la table de la
parole. Le constat reste interne : la copie que le modèle lit ne le porte pas."""

from __future__ import annotations

from api.services.actions_communes import consignes as C
from api.services.actions_communes import enveloppe_legere
from api.services.actions_communes.du import CLE_DU, Du, du_du_retour
from api.tests.mark import test_restauration_reservation as RESERVATION
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation

salle = RESERVATION.salle


async def test_une_fiche_vide_est_constatee_sans_rien_changer(essai_de):
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita", ajouter=[{"article": "margherita", "quantite": 1}])
    r = await e.tour("d'accord")
    assert du_du_retour(r).rien_change and r[CLE_DU]["rien_change"] is True, r


async def test_une_question_nee_est_constatee(essai_de):
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    r = await e.tour("une margherita", ajouter=[{"article": "margherita", "quantite": 1}])
    assert du_du_retour(r).question == "variante" and not du_du_retour(r).rien_change, r


async def test_un_refus_hors_zone_est_constate_comme_refus_et_fait_bloquant(essai_de):
    e = await essai_de("casa-italia")
    e.dit("Deux reines normales, livrées à Compiègne")
    e.montrer()
    r = await e.fiche(ajouter=[{"article": "pizza reine", "quantite": 2, "variante": "Normale"}], mode_de_retrait="livraison", adresse="8 Rue Solférino",
                      commune="Compiègne", _montrer=False)
    du = du_du_retour(r)
    assert "fait_bloquant" in du.faits_au_modele, du


async def test_le_constat_ne_part_jamais_vers_le_modele(essai_de):
    e = await essai_de()
    r = await e.tour("à emporter", mode_de_retrait="emporter")
    assert CLE_DU in r and CLE_DU not in enveloppe_legere.pour_le_modele(r)


async def test_la_reservation_passe_par_le_meme_constat(salle, monkeypatch):
    e = EssaiReservation(salle, monkeypatch)
    r = await e.tour("quatre personnes samedi à vingt heures au nom d'Alice", personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    assert isinstance(r.get(CLE_DU), dict) and Du(**{k: tuple(v) if isinstance(v, list) else v for k, v in r[CLE_DU].items()}).question == "recapitulatif", r.get(CLE_DU)


# --- M5 : les ``poser_*`` rendent un élément de ``Du`` ; ``assembler`` les range et écrit les drapeaux que le modèle lit


def _contexte():
    from types import SimpleNamespace

    return SimpleNamespace(fiche={})


def test_le_prix_du_poids_et_la_regle_de_la_ligne_rendent_chacun_un_element_de_du():
    from api.services.actions_communes import du as DU
    from api.services.commande import porte
    from api.services.commande.briques import ligne_de_formule_limitee

    retour: dict = {"statut": "FAIT", "faits": {}}
    # C6 n° 11 (décision d'Evan 25/11 9 h 30) : le prix au poids est un fait du retour que le modèle dit, plus un prix que le code dit après sa phrase
    prix = porte.poser_le_prix_du_poids([{"faits": {"ajoute": "x", "grammes": 300, "quantite": 1, "prix_de_la_ligne": 540}}], retour)
    assert prix == DU.Du(consignes=((C.REFUS_A_DIRE, porte.A_FAIRE_DU_PRIX_AU_POIDS),)) and retour["faits"]["prix_au_poids"][0]["prix"] == 540, retour
    regle = porte.poser_la_regle_de_la_ligne([{"faits": {"raison": ligne_de_formule_limitee.RAISON, "regle_prix_max": 300, "article": "x", "etape": "y"}}], retour)
    assert regle == DU.Du(consignes=((C.REFUS_A_DIRE, porte.A_FAIRE_DE_LA_REGLE),)) and retour["faits"]["regle_de_la_ligne"]  # la règle est un fait du retour, que le modèle dit
    DU.assembler(retour, prix, regle)
    assert "prix_dit_par_le_code_apres_ta_phrase" not in retour and "regle_dite_par_le_code" not in retour and "dit_avant_ta_phrase" not in retour
    assert porte.A_FAIRE_DE_LA_REGLE in retour["a_faire"] and porte.A_FAIRE_DU_PRIX_AU_POIDS in retour["a_faire"] and len(DU.faits_du_refus(retour)) == 2, retour


async def test_le_minimum_et_le_poids_arrivent_dans_le_meme_du(essai_de):
    """Un retour avec le minimum de la zone ET un prix au poids : les deux éléments sont dans le ``Du`` assemblé."""
    from api.services.actions_communes import du as DU

    retour: dict = {"statut": "FAIT"}
    # C6 n° 11 (décision d'Evan 25/11 9 h 30) : le prix au poids est une consigne et un fait, plus un ``prix_apres``
    DU.assembler(retour, DU.Du(faits_qui_engagent=("x",)), DU.Du(consignes=((C.REFUS_A_DIRE, "dis le prix"),)), None)
    du = DU.du_du_retour(retour)
    assert du.faits_qui_engagent == ("x",) and (C.REFUS_A_DIRE, "dis le prix") in du.consignes, du


def test_r6_chaque_constante_du_constat_a_une_seule_source_et_un_seul_sens():
    """R6 : ``du`` est la seule source des clés et des statuts du constat ; la parole n'en redéfinit aucune, n'a pas de ``__all__`` et ses noms publics se lisent sans tiret bas."""
    from api.services.actions_communes import du as DU, enveloppe_legere, parole, table_de_parole

    assert not hasattr(parole, "__all__") and not hasattr(parole, "BLOQUANTS") and not hasattr(parole, "RETRAIT_D_UNE_LIGNE") and not hasattr(parole, "CLE_FAITS_A_DIRE")
    assert parole.FAITS_A_DIRE != DU.CLE_FAITS_A_DIRE  # un motif de la décision, une clé du retour : deux noms, deux sens
    assert enveloppe_legere.CLE_DU is DU.CLE_DU and table_de_parole.RETRAIT_D_UNE_LIGNE is DU.RETRAIT_D_UNE_LIGNE
    assert not hasattr(parole, "repli_sans_le_fait_bloquant_de") and not hasattr(parole, "_repli_sans_le_fait_bloquant_de")  # C5 : le repli composé est retiré
    assert "refus" not in DU.Du().vers_json()  # aucun lecteur : retiré


def test_un_constat_qui_ne_peut_pas_se_poser_ne_leve_pas_le_retour_reste_tel_quel(monkeypatch):
    """Reprise 7 : ``constater`` ne lève jamais, même au dernier geste (la pose du constat dans le retour)."""
    from api.services.actions_communes import du as DU

    def casse(_retour):
        raise TypeError("forme inattendue")

    monkeypatch.setattr(DU, "du_du_retour", casse)
    retour = {"statut": "FAIT"}
    sortie = DU.constater(retour, None, {}, lambda _d: None, 3)
    assert sortie["statut"] == "FAIT" and DU.CLE_DU not in sortie
