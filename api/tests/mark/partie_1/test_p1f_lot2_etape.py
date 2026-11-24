"""[.mark] Plan final Partie 1, lot 2 : l'étape de la commande (mécanisme É). Un seul module l'écrit, par transitions, d'une table fermée.

Preuves : la table est fermée ; chaque transition fait ce que l'ancienne déduction faisait ; plus aucun autre module n'écrit l'étape ni les faits qu'elle
résume ; la règle RC16 du test des combinaisons (étape stockée = ce que disent les faits, après chaque geste) voit un écart.
"""

from __future__ import annotations

import ast
from types import SimpleNamespace

import pytest

from api.outils import inventaire_rustines as I
from api.services.commande import etape as E
from api.services.commande import panier as P
from api.services.commande import registre as RQ
from api.tests.mark.partie_1 import combinaisons as C

API = I.RACINE_API
CLES_ECRITES_PAR_L_ETAPE = {"etape", "relecture_acceptee", "enregistree", "annulee", "commande_annulee"}


def test_la_table_est_fermee_chaque_etape_connait_chaque_evenement():
    # seul « l'enregistrement défait » est interdit hors de l'étape enregistrée : on ne défait que ce qui est fait
    permis = {(e, ev) for e in E.ETAPES for ev in E.EVENEMENTS if not (ev == E.ENREGISTREMENT_DEFAIT and e != E.ENREGISTREE)}
    assert permis == set(E._ARRIVEE)
    assert all(a is None or a in E.ETAPES for a in E._ARRIVEE.values())


def test_un_evenement_inconnu_ou_hors_de_son_etape_leve_au_lieu_de_deviner():
    with pytest.raises(ValueError):
        E.transition(P.nouveau(), "n'importe quoi")
    with pytest.raises(ValueError):
        E.transition(P.nouveau(), E.ENREGISTREMENT_DEFAIT)


def test_un_panier_d_avant_le_lot_2_se_lit_de_ses_faits_puis_la_premiere_transition_le_stocke():
    ancien = {"lignes": [], "enregistree": {"numero": "n"}}
    assert E.courante(ancien) == E.ENREGISTREE and E.enregistree(ancien) and E.finie(ancien)
    assert E.courante({"annulee": True, "enregistree": {"numero": "n"}}) == E.ANNULEE
    assert E.courante({"relecture": {"x": 1}, "relecture_acceptee": True}) == E.ACCORDEE
    assert E.courante({"relecture": {"x": 1}}) == E.A_RELIRE and E.courante({}) == E.EN_COURS
    E.transition(ancien, E.ANNULEE_APRES_ENREGISTREMENT, numero_court="1")
    assert ancien["etape"] == E.ANNULEE


def test_un_panier_neuf_est_en_cours_et_phase_lit_l_etape_stockee():
    p = P.nouveau()
    assert p["etape"] == E.EN_COURS == RQ.phase(p)
    p["etape"] = E.ANNULEE
    assert RQ.phase(p) == RQ.ANNULEE


def test_le_parcours_d_une_commande_relecture_accord_enregistrement():
    p = P.nouveau()
    E.transition(p, E.RELECTURE_POSEE, relecture={"empreinte": "x"}, l_accord_vaut=False)
    assert p["etape"] == E.A_RELIRE and not E.accord(p)
    E.transition(p, E.ACCORD_DONNE)
    assert p["etape"] == E.ACCORDEE and E.accord(p)
    E.transition(p, E.RELECTURE_POSEE, relecture={"empreinte": "x"}, l_accord_vaut=True)
    assert p["etape"] == E.ACCORDEE, "la même relecture entendue garde l'accord"
    E.transition(p, E.RELECTURE_POSEE, relecture={"empreinte": "y"}, l_accord_vaut=False)
    assert p["etape"] == E.A_RELIRE and not E.accord(p), "une relecture qui repart ne vaut plus l'accord d'avant (RC10)"
    E.transition(p, E.ACCORD_DONNE)
    E.transition(p, E.ENREGISTREE_EN_CAISSE, faits={"numero": "1"})
    assert p["etape"] == E.ENREGISTREE and p["enregistree"] == {"numero": "1"}


def test_un_panier_change_efface_la_relecture_et_l_accord():
    p = P.nouveau()
    E.transition(p, E.RELECTURE_POSEE, relecture={"a": 1}, l_accord_vaut=False)
    E.transition(p, E.ACCORD_DONNE)
    P.toucher(p)
    assert p["etape"] == E.EN_COURS and p["relecture"] is None and not E.accord(p)


def test_changer_une_commande_enregistree_la_defait_puis_revient_a_ce_que_disent_les_faits():
    p = P.nouveau()
    E.transition(p, E.ACCORD_DONNE)
    E.transition(p, E.ENREGISTREE_EN_CAISSE, faits={"numero": "1"})
    E.transition(p, E.ENREGISTREMENT_DEFAIT)
    assert p["etape"] == E.ACCORDEE and p["enregistree"] is None
    E.transition(p, E.ENREGISTREE_EN_CAISSE, faits={"numero": "2"})
    E.transition(p, E.ANNULEE_APRES_ENREGISTREMENT, numero_court="7")
    assert p["etape"] == E.ANNULEE and p["enregistree"] is None and p["annulee"] and p["commande_annulee"] == "7"


def test_une_commande_annulee_ne_revient_pas_et_l_allergie_fait_repartir_la_relecture():
    p = P.nouveau()
    E.transition(p, E.ANNULEE_EN_COURS)
    for ev in (E.PANIER_TOUCHE, E.ACCORD_DONNE, E.ENREGISTREE_EN_CAISSE):
        E.transition(p, ev, faits={})
        assert p["etape"] == E.ANNULEE
    q = P.nouveau()
    E.transition(q, E.RELECTURE_POSEE, relecture={"a": 1}, l_accord_vaut=False)
    E.transition(q, E.ACCORD_DONNE)
    E.transition(q, E.ALLERGIE_A_DONNER)
    assert q["etape"] == E.EN_COURS and q["relecture"] is None and not E.accord(q)


def test_la_regle_rc16_voit_une_etape_stockee_qui_ment():
    ok = {"etape": "a_relire", "relecture": {"x": 1}}
    assert C.rc16_etape(SimpleNamespace(apres=ok)) == []
    assert C.rc16_etape(SimpleNamespace(apres={**ok, "etape": "accordee"}))[0][0] == "RC16"
    assert C.rc16_etape(SimpleNamespace(apres={"relecture": None}))[0][0] == "RC16"


def test_un_seul_module_ecrit_l_etape_et_les_faits_qu_elle_resume():
    """Inventaire : aucune écriture (``p["etape"] = …``, ``p["annulee"] = …``…) de ces clés hors de ``commande/etape.py``, ni ``setdefault``/``update`` qui les porte."""
    fautes = []
    for p in sorted((API / "services").rglob("*.py")):
        if p.name == "etape.py" or "__pycache__" in p.parts:
            continue
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            cibles = []
            if isinstance(n, ast.Assign):
                cibles = n.targets
            elif isinstance(n, (ast.AugAssign, ast.AnnAssign)):
                cibles = [n.target]
            for c in cibles:
                for t in (c.elts if isinstance(c, ast.Tuple) else [c]):
                    if isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant) and t.slice.value in CLES_ECRITES_PAR_L_ETAPE:
                        # un autre dictionnaire que le panier (le retour, l'état d'une vue) peut porter ces mots : seul ``p[...]`` est le panier
                        if isinstance(t.value, ast.Name) and t.value.id in ("p", "panier", "neuf", "essai"):
                            fautes.append(f"{p.relative_to(API).as_posix()}:{n.lineno} {t.slice.value}")
    assert not fautes, fautes


def test_aucun_module_ne_lit_le_drapeau_de_l_accord_sous_son_nom():
    fautes = []
    for p in sorted((API / "services").rglob("*.py")):
        if p.name in ("etape.py", "contrat.py") or "__pycache__" in p.parts or "builder" in p.parts:
            continue
        if "relecture_acceptee" in p.read_text(encoding="utf-8").replace("gabarits", ""):
            fautes.append(p.relative_to(API).as_posix())
    assert not fautes, fautes


def test_les_connecteurs_lisent_l_etape_et_gardent_la_forme_de_leurs_retours():
    """n° 108 : ``_etat_final`` rend toujours ``{"enregistree": bool, "articles", "mode"}`` (les tests générés stockés chez les clients le comparent) et
    ``_action_ouverte`` s'éteint à la fin de la commande, tous deux lus de l'étape."""
    from api.services.integrations.connectors.actions import commande as A

    p = P.nouveau()
    p["lignes"] = [{"nom": "Regina", "quantite": 2}]
    p["mode"] = "emporter"
    fiche = {P.CLE: p}
    assert A._action_ouverte(fiche) == {"outil": "fiche", "attend_une_reponse": False}
    assert A._etat_final(fiche) == {"enregistree": False, "articles": {"Regina": 2}, "mode": "emporter"}
    E.transition(p, E.ACCORD_DONNE)
    E.transition(p, E.ENREGISTREE_EN_CAISSE, faits={"numero": "1"})
    assert A._action_ouverte(fiche) is None and A._etat_final(fiche)["enregistree"] is True
    E.transition(p, E.ANNULEE_APRES_ENREGISTREMENT, numero_court="1")
    assert A._action_ouverte(fiche) is None and A._etat_final(fiche)["enregistree"] is False
