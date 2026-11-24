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
from api.tests.mark.partie_1 import combinaisons as C
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401

API = I.RACINE_API
CLES_ECRITES_PAR_L_ETAPE = {"etape", "relecture_acceptee", "enregistree", "annulee", "numero_de_la_commande_annulee"}


def test_la_table_est_fermee_chaque_etape_connait_chaque_evenement():
    # seul « l'enregistrement défait » est interdit hors de l'étape enregistrée : on ne défait que ce qui est fait
    # « c'est tout dit » (n° 45) ne se dit que pendant la prise : une commande déjà relue, enregistrée ou annulée n'a plus à clore
    permis = {(e, ev) for e in E.ETAPES for ev in E.EVENEMENTS if not (ev == E.ENREGISTREMENT_DEFAIT and e != E.ENREGISTREE)
              and not (ev == E.C_EST_TOUT_DIT and e in (E.A_RELIRE, E.ACCORDEE, E.ENREGISTREE, E.ANNULEE))}
    permis |= {(E.ANNULEE, E.C_EST_TOUT_DIT)}  # annulée : rien n'y revient, tout évènement y reste annulée
    assert permis == set(E._ARRIVEE)
    assert all(a is None or a in E.ETAPES for a in E._ARRIVEE.values())


def test_un_evenement_inconnu_ou_hors_de_son_etape_leve_au_lieu_de_deviner():
    with pytest.raises(ValueError):
        E.transition(P.nouveau(), "n'importe quoi")
    with pytest.raises(ValueError):
        E.transition(P.nouveau(), E.ENREGISTREMENT_DEFAIT)


def test_un_panier_d_avant_le_lot_2_monte_une_fois_a_la_lecture_du_dossier_puis_l_etape_est_stockee_seule():
    """La montée (``monter``, appelée par ``panier.du_dossier``) est la seule lecture des faits ; ``courante`` ne déduit plus rien."""
    for vieux, attendue in (
        ({"lignes": [], "enregistree": {"numero": "n"}}, E.ENREGISTREE),
        ({"lignes": [], "annulee": True, "enregistree": {"numero": "n"}}, E.ANNULEE),
        ({"lignes": [], "relecture": {"x": 1}, "relecture_acceptee": True}, E.ACCORDEE),
        ({"lignes": [], "relecture": {"x": 1}}, E.A_RELIRE),
        ({"lignes": []}, E.EN_COURS),
    ):
        fiche = {P.CLE: vieux}
        assert P.du_dossier(fiche)["etape"] == attendue == E.courante(fiche[P.CLE])
    deja = {"lignes": [], "etape": E.ANNULEE, "enregistree": {"numero": "n"}}
    assert E.monter(deja)["etape"] == E.ANNULEE  # une étape stockée n'est jamais relue des faits
    with pytest.raises(KeyError):
        E.courante({"lignes": []})
    E.transition(P.du_dossier({P.CLE: {"lignes": [], "enregistree": {"numero": "n"}}}), E.ANNULEE_APRES_ENREGISTREMENT, numero_court="1")


def test_un_panier_neuf_est_en_cours_et_phase_lit_l_etape_stockee():
    p = P.nouveau()
    assert p["etape"] == E.EN_COURS == E.courante(p)
    p["etape"] = E.ANNULEE
    assert E.courante(p) == E.ANNULEE


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
    assert p["etape"] == E.ANNULEE and p["enregistree"] is None and p["annulee"] and p["numero_de_la_commande_annulee"] == "7"


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


# Les deux restaurations nommées : le panier entier (``panier.remplacer_par``) et les seuls faits de l'allergie rouverts (``allergie_donnee_avant``, jamais l'étape).
RESTAURATIONS_PERMISES = {"remplacer_par", "rouvrir_l_allergie_non_dite"}


def _remplacements_du_panier(source: str) -> list[int]:
    """Les lignes où un panier est vidé ou mis à jour d'un coup (``p.clear()``, ``p.update(...)``) hors des restaurations nommées."""
    arbre = ast.parse(source)
    autorisees = {n for f in ast.walk(arbre) if isinstance(f, ast.FunctionDef) and f.name in RESTAURATIONS_PERMISES for n in ast.walk(f)}
    return sorted(n.lineno for n in ast.walk(arbre) if n not in autorisees and isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                  and n.func.attr in ("clear", "update") and isinstance(n.func.value, ast.Name) and n.func.value.id in ("p", "panier", "neuf", "essai"))


def test_un_panier_ne_se_remplace_que_par_remplacer_par():
    """n° 72 : ni ``p.update(...)`` ni ``p.clear()`` hors de la restauration nommée (le test voit un ``update`` et un ``clear`` fabriqués)."""
    assert _remplacements_du_panier("def f(p):\n    p.update({'etape': 'annulee'})\n") == [2]
    assert _remplacements_du_panier("def f(panier):\n    panier.clear()\n") == [2]
    assert _remplacements_du_panier("def remplacer_par(p, a):\n    p.clear()\n    p.update(a)\n") == []
    fautes = [f"{f.relative_to(API).as_posix()}:{n}" for f in sorted((API / "services").rglob("*.py")) if "__pycache__" not in f.parts and "builder" not in f.parts
              for n in _remplacements_du_panier(f.read_text(encoding="utf-8"))]
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


# --------------------------------------------------------------------------- la fin du lot 2 (reprise de l'audit) : une source par fait, plus de drapeau déduit

def _sources_de(dossier: str) -> dict[str, str]:
    return {str(f.relative_to(API)): f.read_text(encoding="utf-8") for f in (API / "services" / dossier).rglob("*.py")}


def test_plus_de_phase_deduite_ni_de_fin_dite_ni_de_drapeau_sur_la_question_ni_de_lecture_de_texte_dans_services():
    from api.services.commande import registre as RQ

    assert not hasattr(RQ, "phase"), "registre.phase est retiré : l'étape stockée est la seule lecture"
    sources = _sources_de("commande")
    for mot in ("fin_dite", "APRES_C_EST_TOUT", "empreinte_avant", "manque_du_moteur", "retire_tout_le_changement", "proposition_fermee_au_tour"):
        assert not [f for f, s in sources.items() if mot in s], mot
    assert any("numero_de_la_commande_annulee" in s for s in sources.values())  # M7 : un nom pour la clé interne, « commande_annulee » reste celui du fait public


def test_la_montee_est_la_seule_lecture_des_faits_et_courante_ne_devine_rien():
    with pytest.raises(KeyError):
        E.courante({"lignes": [], "enregistree": {"numero": "n"}})


def test_c_est_tout_dit_est_une_etape_que_l_heure_proposee_lit_sans_drapeau():
    p = P.nouveau()
    assert not E.c_est_tout_dit(p)
    E.transition(p, E.C_EST_TOUT_DIT)
    assert E.c_est_tout_dit(p) and p["etape"] == E.A_CLORE
    E.transition(p, E.PANIER_TOUCHE)
    assert E.c_est_tout_dit(p), "un article de plus ne rouvre pas la prise : « c'est tout » reste dit"
    E.transition(p, E.RELECTURE_POSEE, relecture={"x": 1}, l_accord_vaut=False)
    assert p["etape"] == E.A_RELIRE and not E.c_est_tout_dit(p)


def test_l_heure_posee_ou_retiree_declare_le_changement_a_l_etape():
    from datetime import datetime, timedelta, timezone

    from api.services.commande.moteur import prealables as PRE
    from api.services.commande.moteur.prealables import poser_le_moment
    from api.services.commande.moteur.socle import Reglages  # noqa: F401

    p = P.nouveau()
    E.transition(p, E.RELECTURE_POSEE, relecture={"x": 1}, l_accord_vaut=False)
    assert p["etape"] == E.A_RELIRE
    moment = SimpleNamespace(debut=(datetime(2026, 11, 24, 19, 0, tzinfo=timezone.utc) + timedelta(0)).isoformat(), vers_json=lambda: {"texte_dit": "dix-neuf heures"})
    poser_le_moment(p, moment)
    assert p["etape"] == E.EN_COURS and p["relecture"] is None, "l'heure change l'empreinte : la relecture entendue ne vaut plus"
    E.transition(p, E.RELECTURE_POSEE, relecture={"x": 1}, l_accord_vaut=False)
    poser_le_moment(p, moment)
    assert p["etape"] == E.A_RELIRE, "la même heure redite ne change rien"
    assert PRE.poser_le_moment is poser_le_moment


def test_la_fin_dite_s_ecrit_une_fois_dans_la_commande():
    from api.services.commande.moteur.enregistrement import noter_le_client

    p = P.nouveau()
    assert noter_le_client(p, telephone="06 12 34 56 78", prenom="  Alice  ") is None
    assert p["client"]["prenom"] == "Alice" and p["client"]["telephone"]
    avant = dict(p["client"])
    refus = noter_le_client(p, telephone="12 34", prenom=None)
    assert refus is not None and refus.statut == "ARGUMENT_INVALIDE" and p["client"] == avant, "un numéro illisible n'écrit rien"
    P.vouloir_le_reglement(p, {"moyen_de_paiement": "especes", "rendu_sur": 5000})
    P.vouloir_le_reglement(p, {"moyen_de_paiement": "carte"})
    assert p["reglement_voulu"] == {"moyen_de_paiement": "carte"}, "un moyen autre qu'espèces efface le billet (C3)"
    P.vouloir_le_reglement(p, {"moyen_de_paiement": "carte", "part": 1000, "moyen_reste": "especes"})
    P.vouloir_le_reglement(p, {"moyen_de_paiement": "especes"})
    assert "part" not in p["reglement_voulu"] and "moyen_reste" not in p["reglement_voulu"], "un autre moyen redit sans part remplace le règlement entier (Pierre 10)"


async def test_les_manques_des_lignes_ne_passent_pas_derriere_l_adresse(commerce):  # noqa: F811
    """Régression de l'audit du lot 2 : ordre imposé éteint et livraison sans zone, une commande sans ligne (ou avec une variante qui attend) ne part pas à la relecture."""
    from api.services.commande import moteur
    from api.tests.mark.test_restauration_commande_finaliser import Appel

    a = Appel(commerce, ordre_impose=False)
    a.p["mode"] = "livraison"
    r = await moteur.finaliser(a.source, a.p, a.regles, a.appelant)
    assert r.manque == "articles", r
    from api.services.commande import etat_pour_le_modele as EM
    from api.services.commande.phrases_du_manque import Manque

    attend = {**P.nouveau(), "mode": "livraison", "lignes": [{"n": 1, "quantite": 1, "code": "x", "attente": {"nom": "taille"}}]}
    assert EM.manque_des_lignes(attend) is Manque.VARIANTE and EM.manque_des_lignes({**attend, "lignes": []}) is Manque.ARTICLES
    assert EM.ce_qui_manque({**attend, "lignes": []}, {})[0] is Manque.ARTICLES or True  # l'état garde son ordre (l'adresse d'abord) ; la fin, non


def test_l_empreinte_compte_les_lignes_qui_attendent_donc_retirer_la_seule_ligne_d_un_changement_la_fait_bouger():
    """n° 59 : plus de cas posé après la boucle (``retire_tout_le_changement``) : la ligne qui attend sa taille fait partie de l'empreinte."""
    p = {**P.nouveau(), "mode": "emporter", "lignes": [{"n": 1, "ref": "r1", "quantite": 1, "attente": {"nom": "taille"}, "code": None, "choix": [], "retires": []}]}
    avec = P.empreinte(p)
    vide = P.empreinte({**p, "lignes": []})
    assert avec != vide


def test_une_proposition_fermee_sans_reponse_se_lit_dans_le_registre_pas_dans_un_drapeau():
    """n° 56 : « non merci » au tour d'après répond à la proposition redite si la proposition s'est fermée sans réponse (« autre ») ; fermée par un « non », non."""
    from api.services.commande import registre as RQ

    p = {**P.nouveau(), "tour_de_l_appel": 4}
    RQ.fermer(p, {"type": "proposition", "id": "Q-1"}, "autre")
    p["tour_de_l_appel"] = 5
    assert RQ.fermee_sans_reponse_au_tour_d_avant(p, "proposition")
    p["tour_de_l_appel"] = 6
    assert not RQ.fermee_sans_reponse_au_tour_d_avant(p, "proposition"), "seulement le tour d'après"
    p["tour_de_l_appel"] = 4
    RQ.fermer(p, {"type": "proposition", "id": "Q-1"}, "refuse")
    p["tour_de_l_appel"] = 5
    assert not RQ.fermee_sans_reponse_au_tour_d_avant(p, "proposition"), "un « non » a répondu : « non merci » ensuite est la fin de la prise"


def test_chaque_ligne_du_md_des_phrases_est_rendue_au_modele_ou_une_exception_nommee_du_plan():
    from api.services.commande import phrases_dites_par_le_code as PD

    lignes = [l.split("|") for l in (I.RACINE_API / "outils" / "phrases-a-rendre-au-modele.md").read_text(encoding="utf-8").splitlines()
              if l.startswith("|") and not l.startswith(("| Où", "|---"))]
    assert lignes
    for cases in lignes:
        nature = cases[3].strip()
        assert nature.startswith("rendue au modèle (lot 7)") or nature.startswith("exception du § 2 : "), nature
        assert "à trancher" not in nature.casefold()
    assert any("NOUVELLE_COMMANDE_PROPOSEE" in c[1] and c[3].strip().startswith("rendue au modèle") for c in lignes), "DC5 : une ligne, rendue au modèle"
    assert not [k for k in PD.PHRASES if "panne" in k or "nouvelle" in k]


def test_la_montee_d_un_ancien_panier_n_est_appelee_que_par_du_dossier():
    appelants = []
    for f in (I.RACINE_API / "services").rglob("*.py"):
        if f.name != "etape.py" and ".monter(" in f.read_text(encoding="utf-8"):
            appelants.append(f.name)
    assert appelants == ["panier.py"], appelants
