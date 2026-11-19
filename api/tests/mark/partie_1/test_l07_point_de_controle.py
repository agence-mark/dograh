"""[.mark] Chantier Partie 1, lot 7 : les défauts du point de contrôle (parties pc7c du 19/11), corrigés à la source.

| Ligne | Défaut | Test |
|---|---|---|
| L07-30 | R-a : « samedi soir » perd son moment quand le modèle relit le jour avec sa date ; les créneaux du midi sont proposés | la lecture garde le soir |
| L07-31 | R-a : une réponse sans question en attente (le modèle recopie un « manque » comme identifiant) faisait refuser TOUTE la fiche, l'heure dite comprise | seule la réponse est refusée, l'heure est prise |
| L07-32 | R-a : une heure dite hors des créneaux est refusée avec sa raison et l'heure voisine proposée, jamais redemandée | refus avec propositions |
| L07-33 | R-c : le nom et le jour dits avec une recherche servent à retrouver, jamais à ouvrir une réservation | pas de brouillon |
| L07-34 | R-b, R-c : l'appelant au numéro connu est retrouvé par son numéro, même avec une réponse sans question | retrouvée, puis annulée |
"""

from __future__ import annotations

from api.db.bases_clients.restauration_reservation import creer_reservation
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_reservation import SAMEDI_20H, TEL, salle  # noqa: F401

SAMEDI = "samedi quatorze novembre"


async def _midi_et_soir(salle) -> None:
    """Casa Italia : un service du midi ET un du soir (la salle du test n'a que le soir)."""
    await salle.c.execute("INSERT INTO mark.resto_service (site_id, nom, jours, debut, fin, pas_minutes) VALUES ($1, 'Midi', '{1,2,3,4,5,6,7}', '11:00', '14:00', 60)", salle.a)


async def _avant(salle, **plus):
    r = await creer_reservation(salle.c, salle.a, {"debut": SAMEDI_20H, "couverts": 2, "prenom": "Martin", "telephone": TEL, "appel_id": "avant", **plus})
    assert r.statut == "ENREGISTREE", r
    return r.faits["numero"]


# --------------------------------------------------------------------------- L07-30 : R-a, « samedi soir » garde son moment à la lecture


async def test_samedi_soir_ne_propose_que_le_soir(salle, monkeypatch):
    await _midi_et_soir(salle)
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour("quatre personnes samedi soir", personnes=4, jour="samedi soir")
    assert r["manque"] == "heure", r
    lu = await essai.lecture(sujet="places_libres", jour=SAMEDI, personnes=4)       # le modèle relit le jour avec sa date, comme au banc
    dites = lu["faits"]["horaires_libres"]
    assert dites and not any(h in dites for h in ("onze heures", "douze heures", "treize heures", "midi")), lu
    assert "dix-neuf heures" in dites, lu


# --------------------------------------------------------------------------- L07-31 : R-a, une réponse sans question refusée seule


async def test_reponse_sans_question_refusee_seule_l_heure_est_prise(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    await essai.tour("quatre personnes samedi soir", personnes=4, jour="samedi soir")
    r = await essai.tour("vers 20 heures", heure="vingt heures", reponse={"question_id": "heure", "sens": "autre", "valeurs": ["vingt heures"]})
    assert r["raison"] == "question_inconnue" and r["cases_refusees"] == ["reponse"], r      # elle seule
    assert essai.etat["brouillon"].get("heure"), r                                          # l'heure dite est prise
    assert r.get("manque") != "heure", r                                                    # jamais redemandée


# --------------------------------------------------------------------------- L07-32 : R-a, hors des créneaux


async def test_heure_hors_des_creneaux_refusee_avec_sa_raison_et_l_heure_voisine(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour("quatre personnes samedi à vingt-trois heures au nom d'Alice", personnes=4, jour="samedi", heure="vingt-trois heures", nom="Alice")
    assert r["statut"] == "PARTIEL" and r["raison"] == "complet_a_cette_heure", r
    assert r["faits"].get("horaires_libres"), r                                              # l'heure voisine libre est proposée
    assert r.get("manque") != "heure", r


# --------------------------------------------------------------------------- L07-33 : R-c, nom et jour pour retrouver


async def test_nom_et_jour_avec_une_recherche_n_ouvrent_pas_de_reservation(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch, appelant=None)                               # numéro masqué
    r = await essai.tour("annuler ma réservation", retrouver_une_reservation_enregistree={})
    assert r["manque"] == "nom_et_jour_de_la_reservation" and r["texte_a_dire"] == "À quel nom et pour quel jour était votre réservation ?", r
    r = await essai.tour("au nom de Martin, pour jeudi", jour="jeudi", nom="Martin", retrouver_une_reservation_enregistree={"jour": "jeudi", "nom": "Martin"})
    assert not essai.etat.get("brouillon"), r                                                 # aucune réservation commencée
    assert [x["operation"] for x in r["resultats"]] == ["retrouver_une_reservation_enregistree"], r


# --------------------------------------------------------------------------- L07-34 : R-b, R-c, le numéro de l'appel d'abord


async def test_le_numero_de_l_appel_retrouve_avant_de_demander_le_nom(salle, monkeypatch):
    numero = await _avant(salle)
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour("déplacer ma réservation", reponse={"question_id": "personnes", "sens": "autre", "valeurs": ["déplacer"]}, retrouver_une_reservation_enregistree={"nom": "non dit"})
    assert essai.etat["cible"] == numero, r                                                    # retrouvée par le numéro, même avec une réponse sans question
    r = await essai.tour("annuler", annuler_une_reservation_enregistree=True)
    assert r["question"]["type"] == "annulation", r


# --------------------------------------------------------------------------- L07-35 : R-d, où en est ma commande


async def test_suivi_par_le_numero_de_l_appel(essai_de):
    from api.services.commande import porte
    from api.tests.mark.partie_1.test_l03_porte import _jusqu_a_la_relecture

    e = await essai_de()
    q = await _jusqu_a_la_relecture(e)
    r = await e.tour("oui c'est bon, au nom de Martin, en carte", reponse={"question_id": q["id"], "sens": "accepte"}, prenom="Martin", moyen_de_paiement="carte_bancaire")
    assert r["statut"] == "ENREGISTREE", r
    e.dit("où en est ma commande de tout à l'heure")
    r = await porte.executer_la_fiche_du_service({"retrouver_une_commande_enregistree": {}, "a_dire": "x"}, e.ctx)
    lu = r["resultats"][0]
    assert lu["statut_du_module"] == "OK" and lu["faits"]["numero_court"] and "manque" not in r, r         # lue par le numéro de l'appel, rien n'est redemandé


async def test_suivi_sans_numero_dit_ce_qui_manque_au_modele(essai_de):
    from api.services.commande import porte

    e = await essai_de()
    e.ctx.appel = {}                                                                                        # numéro masqué
    e.dit("où en est ma commande de tout à l'heure")
    r = await porte.executer_la_fiche_du_service({"retrouver_une_commande_enregistree": {}, "a_dire": "x"}, e.ctx)
    assert r["statut"] == "A_PRECISER" and r["manque"] == "reference" and r["texte_a_dire"] == "Quel est le numéro de la commande ?", r
    assert "panier" not in str(r), r                                                                        # le suivi ne montre pas un panier vide
