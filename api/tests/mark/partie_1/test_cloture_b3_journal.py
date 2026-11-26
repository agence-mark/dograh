"""[.mark] Clôture de la Partie 1, lot B3 : le journal de ce que le code a dit (audit du code M5), une seule mémoire.

* Un refus redit (hors zone, minimum) : la phrase entière la première fois ; ensuite le code ne la redit pas et le modèle propose une issue ; au
  deuxième échec, la sortie (un message à l'équipe). Dans un même tour, une seule fois (C7, H6, DF7).
* La relecture n'est validée que si la personne l'a entendue : changée après le « oui », elle repart, se pose et se dit (C3 b, RC10).
"""

from __future__ import annotations

from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes import conversation as CONV
from api.services.commande import porte as PORTE

COMPIEGNE = {"adresse": "8 rue Solférino", "commune": "Compiègne"}


def _refus_a_dire(r) -> bool:
    """Le retour donne le refus au modèle (faits + consigne de le dire) ; le code ne dit rien (lot 7b, Q1)."""
    return PORTE.A_FAIRE_DES_REFUS_A_DIRE in (r.get("a_faire") or "") and bool((r.get("faits") or {}).get("refus_de_la_fiche"))


async def test_un_refus_redit_issue_puis_sortie(essai_de):
    e = await essai_de()
    await e.tour("en livraison", mode_de_retrait="livraison")
    r1 = await e.tour("au 8 rue Solférino à Compiègne", **COMPIEGNE)
    assert _refus_a_dire(r1) and "Compiègne" in str(r1["faits"]["refus_de_la_fiche"]), r1
    r2 = await e.tour("si, à Compiègne", **COMPIEGNE)
    assert not _refus_a_dire(r2) and J.A_FAIRE_ISSUE in (r2.get("a_faire") or ""), r2
    r3 = await e.tour("Compiègne je vous dis", **COMPIEGNE)
    assert not _refus_a_dire(r3) and J.A_FAIRE_SORTIE in (r3.get("a_faire") or ""), r3


async def test_un_refus_n_est_dit_qu_une_fois_dans_le_tour(essai_de):
    e = await essai_de()
    await e.tour("en livraison", mode_de_retrait="livraison")
    r1 = await e.tour("au 8 rue Solférino à Compiègne", **COMPIEGNE)
    assert _refus_a_dire(r1)
    r = await e.fiche(**COMPIEGNE)  # une seconde fiche dans le même tour (le second passage refait la même)
    assert not _refus_a_dire(r) and J.A_FAIRE_ISSUE not in (r.get("a_faire") or ""), r


async def test_la_relecture_changee_apres_le_oui_repart_et_se_dit(essai_de):
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    q = CONV.question_de(e.p)
    await e.tour("non", reponse={"question_id": q["id"], "sens": "refuse"})
    await e.tour("c'est tout", c_est_tout=True)
    q = CONV.question_de(e.p)
    await e.tour("oui par carte", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="carte_bancaire")
    assert CONV.question_de(e.p)["type"] == "numero_affiche"
    await e.tour("pour dix-neuf heures", heure="dix-neuf heures")
    q = CONV.question_de(e.p)
    assert q["type"] == "relecture" and e.p["etape"] != "accordee", e.p  # l'accord valait pour l'ancienne relecture
    # C6 n° 4 (décision d'Evan 25/11 9 h 30) : l'heure changée est un fait de ce qui a changé, que le modèle dit ; le code dit la phrase réglée du nouveau total, qui pose la question
    changes = [c for x in e.retours[-1]["resultats"] for c in (x.get("faits") or {}).get("ce_qui_a_change") or []]
    assert any(c.get("geste") == "heure" and "dix-neuf" in str(c.get("heure")) for c in changes), e.retours[-1]
    textes = e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {}
    assert not textes.get("avant") and str(textes.get("suffixe") or "").endswith("?"), textes
    await e.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    assert e.p["etape"] == "accordee", e.p  # le « oui » à la relecture entendue la valide
