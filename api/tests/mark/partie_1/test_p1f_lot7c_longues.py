"""[.mark] Lot 7c : les rouges du passage des combinaisons longues sur la chaîne ``16fe7cc1``, un test court par cause (jamais la seule combinaison longue)."""

from __future__ import annotations

from api.services.actions_communes import table_de_parole as T
from api.services.actions_communes import conversation as CONV
from api.services.actions_communes.du import RIEN_CHANGE
from api.services.actions_communes.parole import A_DIRE_SEUL, QUESTION_DEJA_DONNEE, SUFFIXE, EtatDuTour
from api.services.phrases.catalogue import REPONSE_PERDUE

QUESTION_NEE = {"lignes": [{}], CONV.CLE: {CONV.CLE_QUESTION: {"id": "Q-1", "type": "heure_proposee", "nee_au_tour": 3, "texte": ""}}}


def _joue(retour: dict, phrase: str, textes: dict | None = None, **etat):
    e = EtatDuTour(tour=3, **etat)
    entrees = T.entrees_du_retour(retour, phrase, e, [], QUESTION_NEE, textes or {}, None, None)
    return T.decider(entrees)


def test_rc4_la_question_deja_donnee_et_une_fiche_qui_ne_change_rien_apres_la_relance_est_une_relance_ratee():
    """T12 (coordinateur 26/11 10 h 45) : la fiche rejouée qui ne change rien, une fois la relance du tour faite, est une relance ratée, même quand la question née dans ce tour a
    déjà été donnée au modèle. Client (fermé, « je vous la prépare pour dix-huit heures ? » posée) : le modèle rejoue deux fois la même fiche / avant : « C'est noté. » seul, rien
    n'est noté / après : la suite réglée gardée, sinon P3."""
    d = _joue({RIEN_CHANGE: True}, "C'est noté.", question_donnee="Q-1", relance_du_fait=True)
    assert (d.mode, d.a_dire, d.motif) == (A_DIRE_SEUL, None, REPONSE_PERDUE)
    d = _joue({RIEN_CHANGE: True}, "C'est noté.", {"suffixe": "Puis-je faire autre chose pour vous ?"}, question_donnee="Q-1", relance_du_fait=True)
    assert (d.mode, d.a_dire, d.motif) == (A_DIRE_SEUL, "Puis-je faire autre chose pour vous ?", SUFFIXE)


def test_rc4_la_question_deja_donnee_que_la_phrase_pose_reste_dite():
    """Le cas voisin ne bouge pas : la phrase du modèle pose la question déjà donnée, elle est dite (une question, en dernier)."""
    d = _joue({RIEN_CHANGE: True}, "On vous la prépare pour la réouverture, ça vous va ?", question_donnee="Q-1", relance_du_fait=True)
    assert (d.mode, d.motif) == (A_DIRE_SEUL, QUESTION_DEJA_DONNEE)


async def test_rc4_c_est_tout_redonne_l_heure_proposee_au_modele(faire_monde, monkeypatch):
    """n° 45 (aparté d'Evan 20/11) : « c'est tout » quand la relecture attend l'heure proposée la redonne dans ce tour ; depuis C7 B3 (la même question par sa structure, plus par son
    texte), elle ne renaissait plus. Client (fermé) « Une regina. » puis « C'est tout. » / avant : « C'est noté. » seul, l'heure n'est plus demandée / après : le modèle repasse avec la
    question de l'heure, née dans ce tour."""
    from api.services.actions_communes.parole import SECOND_PASSAGE
    from api.tests.mark.partie_1 import combinaisons as C

    monde = await faire_monde("casa-italia")
    with C.horloge.remplacer(monde.base, C.FERMETURE):
        partie = C.Partie(monde, monkeypatch)
        assert await partie.recette("E9")
        await partie.geste("G1")
        o = await partie.geste("G20")
    q = C.question(o.apres)
    assert q.get("type") == "heure_proposee" and q.get("nee_au_tour") == CONV.de(o.apres).get("tour_de_l_appel"), q
    assert o.decision.mode == SECOND_PASSAGE, o.decision


async def test_rc3_la_phrase_du_total_tourne_d_une_relecture_a_l_autre(faire_monde, monkeypatch):
    """C6 Q3 = A (Pierre, 25/11 17 h 25) : la phrase réglée du total tourne d'une relecture à l'autre. Elle tournait sur la parité de la version du panier : un remplacement (retirer
    puis ajouter, deux versions) redonnait la même variante. Client (relecture posée) « Remplacez-la par une regina. » deux fois / avant : « Ça fait maintenant douze euros
    quatre-vingt-dix, c'est bon ? » deux fois / après : la variante suivante au second tour."""
    from api.tests.mark.partie_1 import combinaisons as C

    monde = await faire_monde("casa-italia")
    partie = C.Partie(monde, monkeypatch)
    assert await partie.recette("E11")
    premiere, seconde = await partie.geste("G11"), await partie.geste("G11")
    assert premiere.dit_par_le_code and seconde.dit_par_le_code and premiere.dit_par_le_code != seconde.dit_par_le_code, (premiere.dit_par_le_code, seconde.dit_par_le_code)
    assert not C.rc3(partie, seconde)


async def test_rc10_la_relecture_ne_repart_pas_derriere_un_article_en_doute(faire_monde, monkeypatch):
    """RC10 (``registre.question_en_doute`` : tant qu'un article est en doute, la commande ne se relit pas ; ``_case_c_est_tout``). Client (relecture posée) « Une regina et une
    salmone. » / avant : la relecture repartait marquée posée, son total jamais dit (la question de la salmone passe d'abord) / après : la question de la salmone seule, la relecture
    se refait après sa réponse, à « c'est tout »."""
    from api.tests.mark.partie_1 import combinaisons as C

    monde = await faire_monde("casa-italia")
    partie = C.Partie(monde, monkeypatch)
    assert await partie.recette("E11")
    o = await partie.fusion(("G1", "G4"))
    assert C.question(o.apres).get("type") == "ambiguite", C.question(o.apres)
    assert not C.rc10(partie, o), C.rc10(partie, o)


def test_rc4_la_question_qui_attend_est_due_comme_le_manque():
    """C5 (décision d'Evan 25/11 8 h 45) : la phrase du modèle qui oublie la question en attente le fait repasser une fois par tour (``_du_a_reposer``), comme un manque.
    Client (fermé, « je vous la prépare pour dix-huit heures ? » posée à un tour d'avant) « En fait la mega. » / avant : « C'est noté. » seul, l'heure n'est plus demandée /
    après : le modèle repasse avec le retour et la question ; une fois la relance faite, sa phrase est dite seule."""
    from api.services.actions_communes.parole import MANQUE, SECOND_PASSAGE

    p = {"lignes": [{}], CONV.CLE: {CONV.CLE_QUESTION: {"id": "Q-1", "type": "heure_proposee", "nee_au_tour": 1, "texte": ""}}}
    e = EtatDuTour(tour=3)
    d = T.decider(T.entrees_du_retour({}, "C'est noté.", e, [], p, {}, None, None))
    assert (d.mode, d.motif) == (SECOND_PASSAGE, MANQUE) and e.relance_du_fait
    d = T.decider(T.entrees_du_retour({}, "C'est noté.", e, [], p, {}, None, None))
    assert (d.mode, d.a_dire) == (A_DIRE_SEUL, "C'est noté.")
    d = T.decider(T.entrees_du_retour({}, "C'est noté, on vous la prépare pour la réouverture ?", EtatDuTour(tour=3), [], p, {}, None, None))
    assert d.mode == A_DIRE_SEUL


async def test_rc2_une_commande_enregistree_passee_en_livraison_sans_adresse_ne_garde_rien_meme_avec_une_taille_a_donner(faire_monde, monkeypatch):
    """Pierre A2 et B4 (M2) : ce qui manque à la commande changée (l'adresse d'une livraison) se constate AVANT tout ; rien ne change, le panier redevient celui d'avant
    (``changer_commande_enregistree``). La porte sautait ce contrôle quand une ligne de la même fiche attendait sa taille. Client (commande enregistrée, une margherita) « Une regina, et
    finalement en livraison. » / avant : la regina entre (sa taille demandée) et le mode passe en livraison sans adresse, la caisse a toujours l'ancienne / après : rien ne change, le
    modèle dit qu'il manque l'adresse."""
    from api.tests.mark.partie_1 import combinaisons as C

    monde = await faire_monde("casa-italia")
    partie = C.Partie(monde, monkeypatch)
    assert await partie.recette("E16")
    o = await partie.fusion(("G2", "G15"))
    assert C.lignes_de(o.apres) == C.lignes_de(o.avant) and o.apres.get("mode") == o.avant.get("mode"), (dict(C.lignes_de(o.apres)), o.apres.get("mode"))
    assert not C.rc2(o), C.rc2(o)
    ops = {x.get("operation"): x for x in (o.retour or {}).get("resultats") or []}
    assert (ops.get("changer_la_commande_enregistree") or {}).get("faits", {}).get("raison") == "changement_incomplet", ops


async def test_rc2_une_taille_a_donner_sur_une_commande_enregistree_attend_toujours_sa_reponse(faire_monde, monkeypatch):
    """Le cas voisin ne bouge pas : sans manque, la ligne qui attend sa taille ne part pas en caisse avant sa réponse (la question de la taille est posée)."""
    from api.tests.mark.partie_1 import combinaisons as C

    monde = await faire_monde("casa-italia")
    partie = C.Partie(monde, monkeypatch)
    assert await partie.recette("E16")
    o = await partie.geste("G2")
    assert C.question(o.apres).get("type") == "variante" and C.lignes_de(o.apres)[C.REGINA] == 1 and not C.rc2(o) and not C.rc8(o)


SUITES_DU_REJEU = [("E1", ("G5+G28", "G32")), ("E7", ("G21", "G11+G27", "G32")), ("E6", ("G2", "G29+G11", "G32")), ("E8", ("G7+G3", "G32")), ("E1", ("G1", "G32", "G32")), ("E7", ("G5+G23", "G32"))]


async def test_rc2_le_juge_du_rejeu_suit_b1_b4_et_le_oui_a_la_proposition(faire_monde, monkeypatch):
    """Les suites tirées réduites (graine 20261122) : l'attente du juge pour « je répète » (G32) contredisait ses propres règles écrites. Lot 8 PE-1 (Q1/Q2 c, Pierre 26/11,
    ``bilan-point-d-etape-7b-c.md:268-276``) : la fiche qui ajoute, rejouée mot pour mot au tour d'après, n'est pas appliquée (le modèle demande si c'est un de plus) : le juge attend « rien
    ne change » pour ces fiches (``combinaisons._identique_au_tour_d_avant``) ; ``test_p1f_lot8_pe_fiche_repetee.py`` tient le code. Les deux dernières suites : ``("E1", ("G1", "G32", "G32"))`` : le rejeu refusé
    n'est pas « appliqué », le suivant (« un autre ») s'applique ; ``("E7", ("G5+G23", "G32"))`` : un « oui » qui visait la proposition posée, rejoué quand elle n'est plus posée, est
    écarté SEUL (B1), la fiche qui reste n'est plus celle d'avant et ses articles entrent."""
    from api.tests.mark.partie_1 import combinaisons as C

    monde = await faire_monde("casa-italia")
    fautes = []
    for etat, suite in SUITES_DU_REJEU:
        r = await C.jouer(monde, monkeypatch, etat, suite)
        assert r.atteint and r.joues == len(suite), (etat, suite, r)
        fautes += [f"{etat} {suite} {f}" for f in r.fautes]
    assert not fautes, fautes
