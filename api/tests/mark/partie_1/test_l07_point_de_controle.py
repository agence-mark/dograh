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
from api.tests.mark.test_restauration_reservation import PARIS, SAMEDI_20H, TEL, salle  # noqa: F401

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
    q = e.p.get("question") or {}
    assert q.get("type") == "numero_affiche", r  # C7 : le numéro qui s'affiche est une question numérotée
    r = await e.tour("oui, ce numéro", reponse={"question_id": q["id"], "sens": "accepte"})
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


# --------------------------------------------------------------------------- L07-36 : P1, l'acceptation d'un changement l'exécute, ou dit pourquoi elle ne peut pas


async def _reservee_a_quatre(essai):
    r = await essai.tour("quatre samedi à vingt heures au nom de Martin", personnes=4, jour="samedi", heure="vingt heures", nom="Martin")
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    assert r["statut"] == "ENREGISTREE", r


async def test_p1_le_oui_a_un_changement_le_fait_meme_avec_les_valeurs_redites(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    await _reservee_a_quatre(essai)
    r = await essai.tour("on sera cinq", nom="Martin", personnes=5)                                  # comme au banc : le nom est redit avec le changement
    assert r["question"]["type"] == "recap_modif", r
    r = await essai.tour("oui", nom="Martin", personnes=5, reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    assert not r.get("question"), r                                                                  # la question ne revient pas
    assert await salle.c.fetchval("SELECT couverts FROM mark.resto_reservation") == 5, r             # le changement est fait


async def test_p1_un_changement_refuse_a_l_acceptation_dit_sa_raison_et_ne_se_redemande_pas(salle, monkeypatch):
    await creer_reservation(salle.c, salle.a, {"debut": SAMEDI_20H, "couverts": 6, "prenom": "Autre", "telephone": "+33699999999", "appel_id": "autre"})   # la grande table est prise
    essai = EssaiReservation(salle, monkeypatch)
    await _reservee_a_quatre(essai)
    r = await essai.tour("on sera cinq", nom="Martin", personnes=5)
    assert r["question"]["type"] == "recap_modif", r
    r = await essai.tour("oui", nom="Martin", personnes=5, reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    assert r["raison"] == "complet_a_cette_heure" and not r.get("question"), r                       # la raison est dite, la même question ne revient pas
    assert await salle.c.fetchval("SELECT couverts FROM mark.resto_reservation WHERE prenom = 'Martin'") == 4


# --------------------------------------------------------------------------- L07-37 : P2, appel masqué : jamais la même question redemandée


async def test_p2_un_jour_ambigu_se_redemande_avec_sa_vraie_question(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch, appelant=None)
    r = await essai.tour("annuler ma réservation", retrouver_une_reservation_enregistree={})
    r = await essai.tour("pour jeudi", retrouver_une_reservation_enregistree={"jour": "jeudi"})                  # ni nom ni numéro : le jour ambigu se redemande
    assert r["manque"] == "jour" and r["texte_a_dire"] != "À quel nom et pour quel jour était votre réservation ?", r


async def test_p2_aucune_reservation_a_ce_nom_et_ce_jour_est_dit_puis_l_equipe_est_proposee(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch, appelant=None)
    r = await essai.tour("annuler, au nom de Martin pour vendredi", retrouver_une_reservation_enregistree={"jour": "vendredi", "nom": "Martin"})
    assert r["statut"] == "INTROUVABLE" and "pas de réservation" in r["a_faire"] and "autre" in r["a_faire"], r
    r = await essai.tour("au nom de Durand pour samedi", retrouver_une_reservation_enregistree={"jour": "samedi", "nom": "Durand"})
    assert r["statut"] == "INTROUVABLE" and "équipe" in r["a_faire"] and "une seule nouvelle recherche" not in r["a_faire"], r   # la deuxième fois : la suite, pas une troisième recherche


# --------------------------------------------------------------------------- L07-38 : P4, aucune commande à un numéro connu


async def test_p4_aucune_commande_a_ce_numero_le_dit_et_propose_de_chercher_autrement(essai_de):
    from api.services.commande import porte

    e = await essai_de()                                                                                  # numéro d'appel connu, aucune commande
    e.dit("où en est ma commande de tout à l'heure")
    r = await porte.executer_la_fiche_du_service({"retrouver_une_commande_enregistree": {}, "a_dire": "x"}, e.ctx)
    assert r["statut"] == "INTROUVABLE" and "pas de commande" in r["a_faire"] and "numéro de la commande" in r["a_faire"], r
    assert "ne redemande pas" in r["a_faire"], r                                                          # le numéro de l'appel est déjà connu


# --------------------------------------------------------------------------- L07-39 : pc7g, le chemin du clavier (la fiche telle que le modèle l'envoie)


async def test_pc7g_p1_le_oui_du_clavier_avec_un_sens_abime_fait_le_changement(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    await _reservee_a_quatre(essai)
    # T4 du clavier : le modèle redit l'heure et le jour avec ses mots à lui (refusés : pas dits), le nom et les personnes passent
    r = await essai.tour("Ah attendez, en fait on sera cinq", heure="vingt heures", jour="samedi quatorze novembre", nom="Martin", personnes=5)
    assert r["question"]["type"] == "recap_modif", r
    # T5 du clavier : « Oui » avec `"sens": "accepte}"` et les valeurs redites
    r = await essai.tour("Oui", nom="Martin", personnes=5, reponse={"question_id": r["question"]["id"], "sens": "accepte}"})
    assert not r.get("question") and await salle.c.fetchval("SELECT couverts FROM mark.resto_reservation") == 5, r


async def test_pc7g_un_sens_hors_liste_refuse_la_fiche_sans_rien_ranger(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    await _reservee_a_quatre(essai)
    r = await essai.tour("on sera cinq", nom="Martin", personnes=5)
    r = await essai.tour("peut-être", personnes=5, reponse={"question_id": r["question"]["id"], "sens": "bof"})
    assert r["raison"] == "reponse_hors_liste" and await salle.c.fetchval("SELECT couverts FROM mark.resto_reservation") == 4, r


async def test_pc7g_p2_appel_masque_jeudi_se_cherche_par_le_nom_les_deux_jeudis_possibles(salle, monkeypatch):
    from datetime import timedelta

    jeudi_prochain = SAMEDI_20H - timedelta(days=2) + timedelta(days=7)                                   # jeudi 19 novembre, 20 h
    r = await creer_reservation(salle.c, salle.a, {"debut": jeudi_prochain, "couverts": 2, "prenom": "Martin", "telephone": "+33699999999", "appel_id": "avant"})
    assert r.statut == "ENREGISTREE", r
    essai = EssaiReservation(salle, monkeypatch, appelant=None)                                           # numéro masqué
    await essai.tour("annuler ma réservation", retrouver_une_reservation_enregistree={})
    r = await essai.tour("Au nom de Martin, pour jeudi", nom="Martin", retrouver_une_reservation_enregistree={"jour": "jeudi", "nom": "Martin"})
    assert essai.etat.get("cible"), r                                                                     # trouvée sans numéro ni question de jour
    assert r.get("manque") != "jour" and "téléphone" not in str(r), r



# --------------------------------------------------------------------------- L07-40 : pc7h, capacité seule : la borne pile, le groupe trop grand dit d'emblée


async def _capacite_seule(salle, capacite=16, groupe_max=8):
    await salle.c.execute("DELETE FROM mark.resto_table WHERE site_id = $1", salle.a)
    await salle.c.execute("UPDATE mark.resto_regle_reservation SET couverts_simultanes = $2, couverts_max_groupe = $3 WHERE site_id = $1", salle.a, capacite, groupe_max)
    for i in range(3):
        r = await creer_reservation(salle.c, salle.a, {"debut": SAMEDI_20H, "couverts": 4, "prenom": f"Client{i}", "telephone": f"+3361111222{i}", "appel_id": f"a{i}"})
        assert r.statut == "ENREGISTREE", r


async def test_pc7h_n3_douze_presents_sur_seize_le_groupe_de_quatre_tient_pile(salle, monkeypatch):
    from api.db.bases_clients.restauration_reservation import capacite_du_jour
    from datetime import date

    await _capacite_seule(salle)
    heures = [c["debut"].astimezone(PARIS).strftime("%H:%M") for c in (await capacite_du_jour(salle.c, salle.a, date(2026, 11, 14), 4)).faits["creneaux"]]
    assert "20:00" in heures and "19:00" in heures, heures                                              # 12 + 4 = 16 tient
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour("quatre samedi à vingt heures au nom de Martin", personnes=4, jour="samedi", heure="vingt heures", nom="Martin")
    assert r["question"]["type"] == "recapitulatif", r


async def test_pc7h_cap_dix_le_groupe_trop_grand_tombe_des_que_le_nombre_est_dit(salle, monkeypatch):
    await _capacite_seule(salle)                                                                         # couverts_max_groupe = 8
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour("une table pour dix personnes samedi midi", personnes=10, jour="samedi midi")
    assert r["raison"] == "groupe_trop_grand" and r.get("manque") != "heure", r                          # avant l'heure, comme au clavier
    assert "équipe" in r["a_faire"], r                                                                   # la suite : l'équipe
    lu = await essai.lecture(sujet="places_libres", jour=SAMEDI, personnes=10)
    assert lu["raison"] == "groupe_trop_grand" and "équipe" in lu["a_faire"] and not lu["faits"].get("horaires_libres"), lu   # jamais « À quelle heure » ni des horaires pour dix


async def test_pc7h_n3_la_borne_est_pile_et_treize_presents_refusent_comme_au_clavier(salle, monkeypatch):
    from datetime import date

    from api.db.bases_clients.restauration_reservation import capacite_du_jour

    await _capacite_seule(salle)                                                                         # 12 présents à 20 h
    await creer_reservation(salle.c, salle.a, {"debut": SAMEDI_20H, "couverts": 1, "prenom": "Reste", "telephone": "+33611112299", "appel_id": "reste"})
    heures = [c["debut"].astimezone(PARIS).strftime("%H:%M") for c in (await capacite_du_jour(salle.c, salle.a, date(2026, 11, 14), 4)).faits["creneaux"]]
    # 13 + 4 = 17 > 16 : refusé dès que le repas (90 minutes) touche 20 h ; libre seulement une fois les repas de 20 h finis
    assert heures == ["21:30", "21:45"], heures
