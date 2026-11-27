"""[.mark] Lot 8, T31 : la fiche « identique au tour d'avant » (PE-1, décision (c) de Pierre 26/11 ~17 h) se lit sur la fiche DITE, cases écartées comprises.

Une case que le tour ne montre pas (le règlement, le numéro, le prénom avant la relecture) est écartée seule (B4) ; elle reste dite. La fiche qui la porte n'est donc pas
« mot pour mot » celle du tour d'avant : elle s'applique. Client « Une margherita. » … « Encore une margherita, par carte, 06 12 34 56 78, c'est Léa. » / avant : une seule
margherita, et le modèle demande « une deuxième, ou la même ? » alors que la personne a dit autre chose / après : deux margheritas, le règlement écarté est redemandé à son tour.
Même lecture pour une réponse écartée seule (B1, un « oui » au mauvais numéro). Et la fiche refaite dans le même tour, refusée comme identique, reste « celle du tour d'avant » au tour
suivant (E0 → G1 · G33 · G32 : sinon « je répète » ajoute une troisième regina sans rien demander)."""

from __future__ import annotations

from collections import Counter

import pytest

from api.tests.mark.partie_1 import combinaisons as C
from api.tests.mark.partie_1.aides_de_la_commande import a_emporter

MARGHERITA = {"article": "margherita", "quantite": 1, "variante": "Normale"}
FIN = {"moyen_de_paiement": "carte_bancaire", "telephone": "0612345678", "prenom": "Léa"}
DIT = "encore une margherita normale, par carte, zéro six douze trente-quatre cinquante-six soixante-dix-huit, c'est Léa"
RAISON = "fiche_identique_au_tour_d_avant"


def _margheritas(e) -> int:
    return sum(Counter({l["nom"].casefold(): l["quantite"] for l in e.p["lignes"]}).values())


def _raisons(r: dict) -> set[str]:
    return {str(x) for x in [r.get("raison"), *((x or {}).get("raison") for x in r.get("refus") or [])] if x}


async def test_la_fiche_avec_des_cases_ecartees_n_est_pas_celle_du_tour_d_avant(essai_de):
    """E7 → G6+G19 des combinaisons longues : la margherita redite avec le règlement, le numéro et le prénom (écartés, pas encore montrés) entre ; aucune question « la même ? »."""
    e = await essai_de()
    await a_emporter(e)
    await e.tour("une margherita normale", ajouter=[MARGHERITA])
    assert _margheritas(e) == 1
    r = await e.tour(DIT, ajouter=[MARGHERITA], **FIN)
    assert RAISON not in _raisons(r) and _margheritas(e) == 2, r


async def test_la_fiche_avec_une_reponse_au_mauvais_numero_n_est_pas_celle_du_tour_d_avant(essai_de):
    """E7 → G6+G27 : la margherita redite avec un « oui » à une question qui n'existe pas (réponse écartée seule, B1) est une autre fiche : elle s'applique."""
    e = await essai_de()
    await a_emporter(e)
    await e.tour("une margherita normale", ajouter=[MARGHERITA])
    r = await e.tour("oui, et encore une margherita normale", ajouter=[MARGHERITA], reponse={"question_id": "Q-99", "sens": "accepte"})
    assert RAISON not in _raisons(r) and _margheritas(e) == 2, r


@pytest.mark.parametrize(("etat", "suite"), [("E7", ("G6+G19",)), ("E7", ("G6+G27",)), ("E10", ("G6+G19",)), ("E7", ("G19+G6",)), ("E0", ("G1", "G33", "G32"))])
async def test_les_cas_rouges_des_combinaisons_longues(faire_monde, monkeypatch, etat, suite):
    """Les cas exacts des trois combinaisons longues rouges (``test_fusions_de_deux[E7]``, ``[E10]``, ``test_suites_tirees`` réduite), rejoués seuls."""
    monde = await faire_monde("casa-italia")
    r = await C.jouer(monde, monkeypatch, etat, suite)
    assert r.atteint and not r.fautes, r.fautes


async def test_la_fiche_refaite_sans_ses_cases_ecartees_reste_la_meme_au_tour_d_apres(essai_de):
    """Le cas voisin (R2 de PE-1) : la fiche refaite dans le MÊME tour sans les cases écartées (la margherita seule) est celle que le modèle redit au tour d'après : la question
    « une deuxième, ou la même ? », jamais une seconde margherita sans rien demander ; et la fiche refaite n'en ajoute pas une dans le tour."""
    e = await essai_de()
    await a_emporter(e)
    await e.tour(DIT.replace("encore ", ""), ajouter=[MARGHERITA], **FIN)
    assert _margheritas(e) == 1
    await e.fiche(ajouter=[MARGHERITA])
    assert _margheritas(e) == 1
    r = await e.tour("je répète, une margherita normale", ajouter=[MARGHERITA])
    assert RAISON in _raisons(r) and _margheritas(e) == 1, r


async def test_r1_la_fiche_refaite_apres_un_ajout_du_tour_ne_pose_pas_la_question(essai_de):
    """Reprise R1 de l'audit T31 : le tour d'avant a déjà pris une margherita, ce tour-ci en prend une autre avec des cases écartées ; la fiche refaite dans le MÊME tour (la margherita
    seule) ne pose pas « une deuxième, ou la même ? » (l'article vient d'être pris) : sa case est déjà faite, rien n'est ajouté. Le tour d'après, « je répète » pose la question une
    seule fois ; « une de plus » passe ensuite. Client « Une margherita. » … « Encore une margherita, par carte, c'est Léa. » / « Je répète. » / modèle « Une troisième, ou la
    même ? » / « Une de plus. » → trois margheritas."""
    e = await essai_de()
    await a_emporter(e)
    await e.tour("une margherita normale", ajouter=[MARGHERITA])
    await e.tour(DIT, ajouter=[MARGHERITA], **FIN)
    assert _margheritas(e) == 2
    r = await e.fiche(ajouter=[MARGHERITA])
    assert RAISON not in _raisons(r) and _margheritas(e) == 2, r
    r = await e.tour("je répète, une margherita normale", ajouter=[MARGHERITA])
    assert RAISON in _raisons(r) and _margheritas(e) == 2, r
    r = await e.tour("une de plus", ajouter=[MARGHERITA])
    assert RAISON not in _raisons(r) and _margheritas(e) == 3, r
