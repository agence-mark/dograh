"""[.mark] Lot 8, 8-T14 : la question d'étape d'une formule tombe avec sa ligne (audit 7c, R3 ; registre T14).

``registre.TYPE_DE_L_ETAPE`` valait « etape_formule » alors que la question née d'une étape a le type « etape » (``formule_a_etapes.TYPE_DE_LA_QUESTION``) :
aucune question n'avait ce type, donc ``condition`` restait vraie et ``objet``, ``ORDRE`` et RC10 sautaient l'étape. Chaque cas part du scénario dit par la
personne, sur la vraie porte (``combinaisons.Partie``) ; la constante rallume cinq comportements du registre, un cas par comportement.
"""

from __future__ import annotations

import copy

from api.services.actions_communes import conversation as CONV
from api.services.commande import registre as REG
from api.services.commande.briques import formule_a_etapes
from api.tests.mark.partie_1 import combinaisons as C

ETAPE = formule_a_etapes.TYPE_DE_LA_QUESTION
MENU = "F-MENU-ENTREPRISE"  # la formule à étapes de Casa Italia (pizza, boisson)


async def _partie(faire_monde, monkeypatch, etat: str, *gestes: str) -> C.Partie:
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    assert await partie.recette(etat), f"{etat} non atteint"
    for code in gestes:
        assert await partie.geste(code) is not None, f"{code} sans objet dans cet état"
    return partie


async def test_e8_puis_g7_enlever_le_menu_fait_tomber_la_question_d_etape(faire_monde, monkeypatch):
    """« Un menu entreprise. » (question : quelle pizza ?) puis « Enlevez-le. » : la question tombe avec le menu."""
    partie = await _partie(faire_monde, monkeypatch, "E8")
    assert C.question(partie.p).get("type") == ETAPE
    await partie.geste("G7")
    assert not partie.p.get("lignes")
    assert C.question(partie.p).get("type") != ETAPE, C.question(partie.p)
    assert REG.question_en_doute(partie.p) is None


async def test_ordre_la_taille_d_un_article_se_finit_avant_l_etape_et_l_etape_revient_ensuite(faire_monde, monkeypatch):
    """E8 puis « une regina » : la taille de la regina est posée d'abord ; la regina enlevée, la question du menu revient, sous son numéro."""
    partie = await _partie(faire_monde, monkeypatch, "E8", "G2")
    assert C.question(partie.p).get("type") == "variante"
    ouvertes = [q for q in (CONV.de(partie.p).get(REG.CLE_DES_QUESTIONS) or {}).values() if isinstance(q, dict) and q.get("type") == ETAPE]
    assert ouvertes and all(REG.condition(partie.p, q) for q in ouvertes)  # l'étape attend, elle n'est pas perdue
    await partie.e.fiche(retirer_article=[2])
    assert C.question(partie.p).get("type") == ETAPE


async def test_objet_la_question_d_etape_est_attachee_a_la_ligne_du_menu(faire_monde, monkeypatch):
    partie = await _partie(faire_monde, monkeypatch, "E8")
    assert C.question(partie.p).get("objet") == f"{ETAPE}:{MENU}"


async def test_rc9_reposee_la_question_d_etape_garde_son_numero(faire_monde, monkeypatch):
    partie = await _partie(faire_monde, monkeypatch, "E8")
    avant = C.question(partie.p)
    assert CONV.de(partie.p)[REG.CLE_DES_NUMEROS].get(f"{ETAPE}:{MENU}") == int(avant["id"].removeprefix("Q-"))  # le numéro est attaché à la ligne du menu
    await partie.geste("G25")  # « euh » : rien de répondu, la question est reposée
    assert C.question(partie.p).get("id") == avant["id"]


async def test_rc9_la_question_d_etape_tombe_avec_sa_ligne_pas_avec_celle_d_un_autre(faire_monde, monkeypatch):
    """E8, « une regina » (sa taille est posée), « enlevez la première » (le menu) : la question du menu tombe, celle de la regina reste."""
    partie = await _partie(faire_monde, monkeypatch, "E8", "G2", "G7")
    assert C.question(partie.p).get("type") == "variante"
    assert not any(REG.condition(partie.p, q) for q in (CONV.de(partie.p).get(REG.CLE_DES_QUESTIONS) or {}).values() if isinstance(q, dict) and q.get("type") == ETAPE)


async def test_une_commande_enregistree_qu_on_change_garde_la_question_d_etape_de_la_ligne_ajoutee(faire_monde, monkeypatch):
    """E10 : enregistrée, la commande se change encore ; le menu ajouté après l'enregistrement attend son choix, et tombe s'il est retiré (audit 7c, R3)."""
    partie = await _partie(faire_monde, monkeypatch, "E8")
    p = copy.deepcopy(partie.p)
    p["etape"] = "enregistree"
    q = C.question(p)
    assert REG.condition(p, q)
    p["lignes"] = []
    assert not REG.condition(p, q)


async def test_rc10_pas_de_relecture_tant_que_l_etape_du_menu_attend(faire_monde, monkeypatch):
    """Un menu à choisir et une regina prête, « c'est tout » : la question du menu passe avant la relecture."""
    partie = await _partie(faire_monde, monkeypatch, "E8", "G1", "G20")
    assert C.question(partie.p).get("type") == ETAPE
    assert (REG.question_en_doute(partie.p) or {}).get("type") == ETAPE
