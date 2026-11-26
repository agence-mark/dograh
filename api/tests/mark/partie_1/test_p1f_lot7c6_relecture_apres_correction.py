"""[.mark] Lot 7b-C6, commit 4 (décision d'Evan 25/11 9 h 30) : la relecture après une correction passe au modèle.

Avant : code « La Margherita passe à quatre. Cela fait maintenant quarante euros. C'est bon ? ».
Après : modèle « Quatre Margherita alors. » + code « Ça fait maintenant quarante euros, c'est bon ? » (motif ``total_apres_correction``). Ce qui a changé est donné en FAITS
(``{"geste", "nom", "quantite"}``), jamais en phrases ; la note d'une moitié est une note de ticket, pas une phrase du code.
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from api.services.commande import porte as PORTE
from api.services.commande.moteur import reglement as R
from api.services.mots_dits import montant_en_lettres
from api.services.phrases.catalogue import MOTIFS, TOTAL_APRES_CORRECTION
from api.tests.mark.partie_1.aides_de_la_commande import trois_margherita_jusqu_a_la_relecture


def _l(n, nom, quantite, cle="a"):
    return {"n": n, "cle": [cle], "nom": nom, "quantite": quantite}


def test_ce_qui_a_change_est_une_liste_de_faits_sans_phrase():
    avant = [_l(1, "Margherita", 3), _l(2, "Regina", 1), _l(3, "Calzone", 1)]
    apres = [_l(1, "Margherita", 4), _l(2, "Regina", 1, cle="b"), _l(4, "Tiramisu", 2)]
    assert R._ce_qui_a_change(avant, apres) == [
        {"geste": R.QUANTITE, "nom": "Margherita", "quantite": 4},
        {"geste": R.CHANGEE, "nom": "Regina", "quantite": 1},
        {"geste": R.AJOUTEE, "nom": "Tiramisu", "quantite": 2},
        {"geste": R.RETIREE, "nom": "Calzone", "quantite": 1},
    ]


def test_sans_numero_de_ligne_la_comparaison_par_contenu_rend_les_memes_faits():
    avant = [{"cle": ["a"], "nom": "Margherita", "quantite": 3}, {"cle": ["c"], "nom": "Calzone", "quantite": 1}]
    apres = [{"cle": ["a"], "nom": "Margherita", "quantite": 2}]
    assert R._ce_qui_a_change(avant, apres) == [
        {"geste": R.QUANTITE, "nom": "Margherita", "quantite": 2}, {"geste": R.RETIREE, "nom": "Calzone", "quantite": 1}]


async def test_la_relecture_apres_une_correction_donne_ce_qui_a_change_et_le_code_dit_le_nouveau_total(essai_de):
    e, _ = await trois_margherita_jusqu_a_la_relecture(essai_de)
    q = CONV.question_de(e.p)
    await e.dit("non, mettez-en une de plus").fiche(ajouter=[{"article": "regina", "quantite": 1, "variante": "Normale"}], reponse={"question_id": q["id"], "sens": "refuse"})
    r = None
    for _ in range(3):
        q = CONV.question_de(e.p) or {}
        if q.get("type") == "relecture" and e.p["relecture"].get("motif_du_total") == TOTAL_APRES_CORRECTION:
            break
        r = await e.dit("c'est tout").fiche(c_est_tout=True, **({"reponse": {"question_id": q["id"], "sens": "refuse"}} if q and q.get("type") != "relecture" else {}))
    assert e.p["relecture"].get("motif_du_total") == TOTAL_APRES_CORRECTION, (e.p["relecture"], r and r["resultats"])
    textes = e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {}
    total = montant_en_lettres(e.p["relecture"]["total"])
    assert textes.get("suffixe") in [v.replace("{total}", total) for v in MOTIFS[TOTAL_APRES_CORRECTION].variantes_defaut], textes
    changes = [c for retour in e.retours for x in retour.get("resultats") or [] for c in (x.get("faits") or {}).get("ce_qui_a_change") or []]
    assert changes and all(isinstance(c, dict) and c.get("geste") for c in changes), changes
    assert "Cela fait maintenant" not in str(e.retours[-1]) and "passe à" not in str(e.retours[-1]), e.retours[-1]
