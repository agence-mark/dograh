"""[.mark] Builder partie 3, lot P : le banc enregistré de la passation accueil → collègue (P1), et ce qu'il prouve.

Le banc (``banc_passation.py``) rejoue une passation avec le VRAI coordinateur et la VRAIE mesure découpée, sur une
horloge virtuelle : aucun appel réel, aucun modèle, aucune voix. Les délais sont ceux de ``Delais`` (hypothèses tirées
de VI.10). Un jeu = une table d'instants depuis la fin de parole de l'appelant.

| Groupe | Ce qu'il prouve |
|---|---|
| banc | deux jeux rendent les mêmes instants ; la voix de l'appel ne dit jamais deux paroles à la fois |
| passes (n° 371, A1) | combien de passes du modèle à la suite ; l'annonce est le message de l'outil, dite par le code : zéro passe |
| où part le temps | l'enchaînement d'aujourd'hui, étape par étape (les secondes de la fiche d'état ``SA-P-etat.md``) |
| A2 | ce que la passation refait à chaque fois pour un collègue de la réserve, ligne par ligne |
"""

from itertools import pairwise

from api.tests.mark.banc_passation import ANNONCE, Delais, jouer, tableau


def test_le_banc_est_deterministe_et_la_voix_ne_parle_jamais_deux_fois_a_la_fois():
    premier, second = jouer(), jouer()
    assert premier.instants == second.instants and premier.decoupe == second.decoupe
    assert premier.issue == "completed"
    segments = premier.segments_de_voix
    for (_a, _debut_a, fin_a), (_b, debut_b, _fin_b) in pairwise(segments):
        assert debut_b >= fin_a, f"deux paroles à la fois : {segments}"
    assert premier.ordre_de_la_voix == ["annonce de l'accueil", "réponse du collègue"]


def test_a1_l_annonce_est_dite_par_le_code_sans_passe_du_modele():
    """A1 (Evan, note Gradium § 5 ter) : l'annonce de l'accueil est le message de l'outil ``transfer_agent``, dit par le
    code (``queue_speech``) ; l'outil rend ``run_llm=False`` : aucune passe de l'accueil après l'appel d'outil."""
    avec, sans = jouer(annonce=ANNONCE), jouer(annonce=None)
    assert (
        avec.passes
        == sans.passes
        == ["l'accueil passe la main (outil, annonce comprise)", "le collègue parle"]
    )
    assert avec.passes_a_la_suite() == 2
    # Le cas de la question n° 371 : l'accueil note d'abord (sans greffier), agent seul (résumé par le modèle).
    ancien = jouer(Delais(passe_note=0.6), groupe=False)
    assert ancien.passes == [
        "l'accueil note",
        "l'accueil passe la main (outil, annonce comprise)",
        "résumé de la conversation",
        "le collègue parle",
    ]


def test_ou_part_le_temps_d_une_passation_vers_un_collegue_de_la_reserve():
    resultat = jouer()
    print("\n" + tableau(resultat))
    instants = resultat.instants
    assert instants["demande"] == 0.6
    assert (instants["annonce_debut"], instants["annonce_fin"]) == (0.69, 2.49)
    assert instants["premier_son_du_collegue"] == 4.28
    assert instants["demande_vers_premier_son"] == 3.68
    # Après l'annonce : 1,2 s de son d'attente, puis la requête du collègue, son premier mot, sa voix.
    assert instants["silence_apres_l_annonce"] == 1.79
    decoupe = resultat.decoupe
    assert decoupe["installation"] == "reserve" and decoupe["installation_s"] == 0.0
    assert decoupe["commit_s"] == decoupe["requete_collegue_s"] == 3.19
    assert decoupe["premier_mot_s"] == 3.59 and decoupe["voix_premier_octet_s"] == 3.68


def test_a2_ce_que_la_passation_refait_pour_un_collegue_de_la_reserve():
    """A2 (Evan) : pour un collègue de la réserve, rien n'est construit ni reconnecté à la passation, sauf les sessions
    MCP de ses outils, ouvertes à chaque passation alors qu'elles pourraient l'être à la mise en réserve."""
    resultat = jouer()
    gestes = [ligne.geste for ligne in resultat.lignes]
    assert "collègue pris dans la réserve" in gestes
    assert not any("construit (service de modèle" in geste for geste in gestes)
    au_decroche = [
        ligne.code for ligne in resultat.lignes if ligne.au_decroche_possible
    ]
    assert au_decroche == ["PipecatEngine._open_mcp_sessions"]
