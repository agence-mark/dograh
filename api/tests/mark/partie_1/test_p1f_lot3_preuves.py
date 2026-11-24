"""[.mark] Plan final Partie 1, lot 3, reprise 5 : des tests de COMPORTEMENT à la place de ceux qui lisaient le code source (R2, R6, R7), et la preuve que RC17 sonne
quand une fiche mène la commande à sa fin deux fois."""

from __future__ import annotations

import subprocess
import sys

import pytest

from api.outils import inventaire_rustines as I
from api.services.commande import moteur
from api.tests.mark.partie_1 import combinaisons as C

API = I.RACINE_API


# --------------------------------------------------------------------------- RC17 : la règle sonne vraiment

def test_rc17_vu_rouge_sur_une_fiche_qui_mene_deux_fois_la_commande_a_sa_fin():
    """La règle jugée seule : une observation à deux fins est une faute RC17, une à une fin n'en est pas une."""
    base = dict(geste="G20", avant={}, apres={}, retour={}, textes={}, decision=None, attendu=C.Counter(), fiche={"c_est_tout": True})
    assert [f[0] for f in C.rc17_un_seul_finaliser(C.Observation(**base, finaliser_appels=2))] == ["RC17"]
    assert C.rc17_un_seul_finaliser(C.Observation(**base, finaliser_appels=1)) == []


async def test_rc17_sonne_dans_le_test_des_combinaisons_quand_la_fin_est_menee_deux_fois(faire_monde, monkeypatch):
    """Le mécanisme branché de bout en bout : la fin de la fiche est jouée DEUX fois (second appel forcé), le test des combinaisons voit la faute RC17 sur « c'est tout » ;
    sans ce second appel, le même geste ne donne aucune faute RC17."""
    from api.services.commande import porte

    monde = await faire_monde("casa-italia")
    propre = await C.jouer(monde, monkeypatch, "E4", ("G20",))
    assert propre.atteint and not [f for f in propre.fautes if f[1] == "RC17"], propre.fautes

    original = porte.mener_a_la_fin

    async def deux_fois(*a, **k):
        await original(*a, **k)
        return await original(*a, **k)

    with monkeypatch.context() as m:
        m.setattr(porte, "mener_a_la_fin", deux_fois)
        doublee = await C.jouer(monde, monkeypatch, "E4", ("G20",))
    assert any(f[1] == "RC17" for f in doublee.fautes), doublee.fautes


# --------------------------------------------------------------------------- R7 : pas de cycle d'import, une façade publique

@pytest.mark.parametrize("module", ["prealables", "articles", "mode_et_adresse", "socle", "enregistrement"])
def test_chaque_module_du_moteur_s_importe_seul_dans_un_processus_neuf(module):
    """R7 (comportement) : importé en premier dans un processus neuf, chaque module du moteur s'importe sans cycle ni global rempli par un autre."""
    code = f"import sys; sys.path.insert(0, {str(API.parent)!r}); import api.services.commande.moteur.{module}"
    suite = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=120)
    assert suite.returncode == 0, suite.stderr[-800:]


def test_la_facade_du_moteur_ne_montre_aucun_nom_prive():
    """R7 (comportement) : ce que la façade ``moteur`` expose n'a aucun nom privé."""
    prives = [n for n in vars(moteur) if n.startswith("_") and not n.startswith("__")]
    assert not prives, prives


# --------------------------------------------------------------------------- R6 : la question du règlement n'est posée qu'une fois, par ``regler``

async def test_la_question_du_reglement_n_est_dite_qu_une_fois_a_la_fin(essai_de):
    """R6 (comportement) : « oui » à la relecture sans moyen de paiement : le manque « paiement » est celui de ``regler`` ; la fin ne l'écrit pas une seconde fois sous un autre texte."""
    import json

    from .test_l04_cuisine import _a_emporter, _jusqu_au_recapitulatif, _premier_article

    e = await essai_de()
    await _a_emporter(e)
    await _premier_article(e)
    q = await _jusqu_au_recapitulatif(e)
    await e.tour("oui c'est bon", reponse={"question_id": q["id"], "sens": "accepte"})
    retour = json.dumps(e.retours[-1], ensure_ascii=False, default=str)
    assert retour.count("Vous réglez comment") <= 1, retour[:1500]
    manques = [x.get("manque") for x in e.retours[-1].get("resultats") or []]
    assert manques.count("paiement") <= 1, manques


# --------------------------------------------------------------------------- reprise 6 : l'objet d'une question est fixé à sa naissance

def test_l_objet_d_une_question_est_fixe_a_sa_naissance_et_lu_sans_rien_changer():
    """Lire l'objet d'une question pas encore née ne compte rien ; la naissance (``nommer``) le calcule UNE fois et le pose dans la question ; ensuite il est lu, jamais recalculé."""
    from api.services.commande import registre as RQ

    p: dict = {}
    q = {"type": "ambiguite", "texte": "salmone ?", "article_dit": {"article": "salmone", "quantite": 1}}
    RQ.objet(q, p), RQ.objet(q, p)
    assert not p.get("hesitations_nees") and "objet" not in q  # lire ne change rien
    cle = RQ.nommer(q, p)
    assert q["objet"] == cle == "ambiguite:1" and p["hesitations_nees"] == 1
    assert RQ.nommer(q, p) == cle and RQ.objet(q, p) == cle and p["hesitations_nees"] == 1  # une seule naissance
    p["hesitations_nees"] = 7  # le compteur a beau bouger, l'objet de la question née ne change pas
    assert RQ.objet(q, p) == cle
