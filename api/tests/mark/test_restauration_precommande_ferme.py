"""[.mark] Module Restauration, D15 (Evan, 16/11) : fermé, l'agent propose une précommande pour un créneau du prochain service.

Vrai gestionnaire d'outil, vraie base du client (R1). Le jeudi 12 novembre à midi, l'établissement A n'a plus son service du midi : il est fermé,
il rouvre à 18 h. Le réglage du type (``planifiee_permise``) décide : permis, l'agent pose le mode et prend une commande pour plus tard ;
non permis, le refus d'avant (rien n'est posé, la réouverture est dite).

| Test | Ce qu'il prouve |
|---|---|
| précommande | fermé + planifiable : le mode est posé, les articles s'ajoutent, ``finaliser`` demande l'heure (une question), la relecture et la confirmation disent l'heure, la commande est enregistrée à l'heure voulue |
| créneau refusé | une heure hors service est refusée AVANT la relecture avec la réouverture dite ; l'heure refusée n'est pas gardée ; une heure trop proche est refusée |
| non planifiable | fermé sans le réglage : refus, mode non posé, réouverture dite, ni proposition ni ``a_planifier`` |
| premier tour | une heure dite avec le mode est gardée jusqu'à ``finaliser`` (aucune question d'heure) |
| heure écrite par le modèle (M74) | une date-heure ISO sans fuseau ou des mots passés tels quels sont résolus par le code au fuseau du lieu, jamais refusés ni devinés |
| vocabulaire | aucun mot de restaurant dans les phrases du mécanisme commun de la précommande |

Lot 4 de la partie 1 (D49) : joué par les gestes nommés de la cuisine (montage ``appel_de_test`` de ``test_restauration_commande_lot6``) ;
l'heure passe par ``poser_l_heure`` (la case ``heure`` de la fiche) ; la fin est celle du contrat (récapitulatif, puis règlement et prénom).
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

import pytest

from api.services.commande import panier
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.tests.mark.commande_sur_la_fiche import article as A
from api.tests.mark.test_restauration_commande_lot6 import appel_de_test  # noqa: F401

JEUDI = 4  # isoweekday


async def _ferme_a_midi(commerce, planifiable: bool):  # noqa: F811
    """Le service du midi du jeudi n'existe plus : fermé à 12 h, ouvert à 18 h."""
    c, a = commerce.c, commerce.a
    await c.execute("DELETE FROM mark.horaire WHERE site_id = $1 AND jour = $2 AND ouverture = '11:00'::time", a, JEUDI)
    await c.execute(
        "UPDATE mark.resto_reglage_type SET planifiee_permise = $2, jours_a_l_avance = 3, delai_minimal = 30 WHERE site_id = $1 AND type = 'emporter'", a, planifiable
    )


async def _jusqu_a_la_relecture(jouer, heure: str | None):
    r = None
    for _ in range(6):
        r = await jouer("finaliser", **({"heure": heure} if heure else {}))
        if r.get("manque") == "relecture":
            return r
    return r


async def test_ferme_et_planifiable_une_precommande_est_enregistree_a_l_heure_voulue(appel_de_test, commerce):
    await _ferme_a_midi(commerce, True)
    jouer = appel_de_test.jouer
    r = await jouer("choisir_mode", mode="à emporter")
    assert r["statut"] == "FERME_PLANIFIABLE" and r["faits"]["a_planifier"] is True and r["faits"]["planifiee_permise"] is True, r
    assert r["faits"]["heure_proposee_dite"] == "dix-huit heures" and r["faits"]["reprise_dite"] == "dix-huit heures", r  # C7a, C7 B3 : statut et faits, le modèle pose la question
    assert appel_de_test.fiche[panier.CLE]["mode"] == "emporter" and appel_de_test.fiche[panier.CLE]["a_planifier"] is True
    ajout = await jouer("ajouter", articles=[A("regina", 1, "Normale"), "coca"])
    assert ajout["statut"] == "OK" and len(appel_de_test.fiche[panier.CLE]["lignes"]) == 2
    # finaliser propose le prochain service et le fait confirmer (aparté d'Evan du 20/11, lot 19) : une seule question
    demande = await jouer("finaliser")
    assert demande["statut"] == "FERME_PLANIFIABLE" and demande["manque"] == "heure_proposee" and demande["faits"]["heure_proposee_dite"] == "dix-huit heures", demande  # C7 B3
    assert demande["faits"]["heure_proposee"], demande
    quand = await jouer("resoudre_une_date", texte="ce soir", heure="19 h 30")
    assert quand["statut"] == "RETENU"
    relecture = await _jusqu_a_la_relecture(jouer, quand["faits"]["heure_voulue"])
    assert relecture["manque"] == "relecture" and relecture["faits"]["heure"] == "dix-neuf heures trente", relecture  # C6 (décision d'Evan 25/11 9 h 30) : l'heure est un fait
    fin = await jouer("finaliser", prenom="Alice", moyen="carte", confirmer=True)
    assert fin["statut"] == "ENREGISTREE" and (fin["suggestion"], fin["faits"]["quand_dit"]) == ("", "pour dix-neuf heures trente"), fin  # C7 B9 (0e89e408) : au fait ; C6 n° 5 (décision d'Evan 25/11 9 h 30) : le fait, sans M108 (la porte la dit après la phrase du modèle)
    ligne = await commerce.c.fetchrow("SELECT heure_voulue FROM mark.resto_commande WHERE site_id = $1", commerce.a)
    assert ligne["heure_voulue"].astimezone(ZoneInfo("Europe/Paris")).strftime("%H:%M") == "19:30"


async def test_une_heure_hors_service_est_refusee_avant_la_relecture_avec_la_reouverture(appel_de_test, commerce):
    await _ferme_a_midi(commerce, True)
    jouer = appel_de_test.jouer
    await jouer("choisir_mode", mode="à emporter", articles=["coca"])
    hors = await jouer("resoudre_une_date", texte="ce soir", heure="15 h")
    refus = await jouer("finaliser", heure=hors["faits"]["heure_voulue"])
    assert refus["manque"] == "heure_voulue" and refus["faits"]["raison"] == "ferme_horaires", refus
    assert refus["suggestion"] == "" and refus["faits"]["rouvre_dit"] == "dix-huit heures", refus  # lot 7b-C7 (A3) : la réouverture est un fait, le modèle la dit
    assert appel_de_test.fiche[panier.CLE]["heure_voulue"] is None  # l'heure refusée n'est pas gardée
    trop_tot = await jouer("resoudre_une_date", texte="ce soir", heure="12 h 10")
    proche = await jouer("finaliser", heure=trop_tot["faits"]["heure_voulue"])
    assert proche["statut"] == "ARGUMENT_INVALIDE" and proche["manque"] == "heure_voulue", proche  # sous le délai minimal
    assert await commerce.c.fetchval("SELECT count(*) FROM mark.resto_commande WHERE site_id = $1", commerce.a) == 0


async def test_ferme_sans_le_reglage_le_comportement_d_avant_est_inchange(appel_de_test, commerce):
    await _ferme_a_midi(commerce, False)
    jouer = appel_de_test.jouer
    r = await jouer("choisir_mode", mode="à emporter")
    assert r["statut"] == "FERME" and r["faits"]["planifiee_permise"] is False, r
    assert r["suggestion"] == "" and r["faits"]["reprise_dite"] == "dix-huit heures", r
    assert "a_planifier" not in r["faits"]
    assert appel_de_test.fiche.get(panier.CLE, {}).get("mode") is None  # rien n'est posé


async def test_une_heure_dite_au_premier_tour_est_gardee_jusqu_a_finaliser(appel_de_test, commerce):
    await _ferme_a_midi(commerce, True)
    jouer = appel_de_test.jouer
    quand = await jouer("resoudre_une_date", texte="ce soir", heure="19 h")
    r = await jouer("choisir_mode", mode="à emporter", articles=[A("regina", 1, "Normale")], heure=quand["faits"]["heure_voulue"])
    assert r["statut"] == "FERME_PLANIFIABLE", r
    # appel 2566 : l'heure déjà dite vaut accord pour plus tard ; le résultat dit pour quand, sans reproposer « plus tard »
    assert r["suggestion"] == "" and r["faits"]["heure_voulue_dite"] == "dix-neuf heures", r
    assert appel_de_test.fiche[panier.CLE]["heure_voulue"] == quand["faits"]["heure_voulue"]
    assert len(appel_de_test.fiche[panier.CLE]["lignes"]) == 1  # les articles dits dans le même geste suivent
    suite = await _jusqu_a_la_relecture(jouer, None)  # l'heure n'est PAS redite à finaliser
    assert suite["manque"] == "relecture" and suite["faits"]["heure"] == "dix-neuf heures", suite  # C6 (décision d'Evan 25/11 9 h 30) : l'heure est un fait
    fin = await jouer("finaliser", prenom="Alice", moyen="carte", confirmer=True)
    assert fin["statut"] == "ENREGISTREE", fin


async def test_une_heure_ecrite_par_le_modele_est_resolue_par_le_code_au_fuseau_du_lieu(appel_de_test, commerce):
    """M74 (appels 2562, 2563) : « 2026-11-12T19:00:00 » sans fuseau, ou « ce soir 19 h 30 » en mots, passés sans la résolution de la date."""
    await _ferme_a_midi(commerce, True)
    jouer = appel_de_test.jouer
    reference = await jouer("resoudre_une_date", texte="ce soir", heure="19 h")
    naive = reference["faits"]["heure_voulue"][:19]  # la même heure, sans fuseau, comme le modèle l'écrit
    r = await jouer("choisir_mode", mode="à emporter", articles=[A("regina", 1, "Normale")], heure=naive)
    assert r["statut"] == "FERME_PLANIFIABLE", r
    assert appel_de_test.fiche[panier.CLE]["heure_voulue"] == reference["faits"]["heure_voulue"]  # gardée, au fuseau du lieu
    en_mots = await _jusqu_a_la_relecture(jouer, "ce soir 19 h 30")  # des mots à finaliser : résolus, jamais « À quelle heure exactement ? »
    assert en_mots["manque"] == "relecture" and en_mots["faits"]["heure"] == "dix-neuf heures trente", en_mots  # C6 (décision d'Evan 25/11 9 h 30) : l'heure est un fait
    doute = await jouer("finaliser", heure="ce soir sept heures")
    assert doute["statut"] == "AMBIGU" and doute["manque"] == "heure", doute  # un doute se dit, jamais une heure devinée


# test_le_mode_dit_par_ajouter_est_pose_puis_les_articles_suivent : supprimé au lot 4 (D49), la fiche a sa case ``mode_de_retrait`` à côté d'``ajouter`` (un seul geste) ; sens repris par test_restauration_commande_lot6.py::test_le_mode_et_les_articles_dits_ensemble_sont_poses_en_un_geste.


def test_aucun_mot_de_restaurant_dans_la_precommande_du_mecanisme_commun():
    import re

    from api.tests.mark.test_restauration_contrat_classeur import RACINE

    corps = "\n".join(f.read_text(encoding="utf-8") for f in sorted((RACINE / "services/commande/moteur").glob("*.py")))
    dossier = RACINE / "services/commande/moteur"
    prealables, mode = (dossier / "prealables.py").read_text(encoding="utf-8"), (dossier / "mode_et_adresse.py").read_text(encoding="utf-8")
    morceau = prealables[prealables.index("async def heure_du_lieu"):prealables.index("async def lire_l_ouverture")] + mode[:mode.index("async def _poser_le_mode")]
    fin = corps[corps.index("# D15 : fermé, mais"):corps.index("# D15 : fermé, mais") + 700]
    assert not re.search(r"restaura|pizza|burger|cuisine|repas|salle|livraison|emporter|caisse|ticket|boisson|plat", morceau + fin, re.IGNORECASE)


_ = pytest
