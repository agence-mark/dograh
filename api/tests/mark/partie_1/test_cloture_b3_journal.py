"""[.mark] Clôture de la Partie 1, lot B3 : le journal de ce que le code a dit (audit du code M5), une seule mémoire.

* Un refus redit (hors zone, minimum) : la phrase entière la première fois ; ensuite le code ne la redit pas et le modèle propose une issue ; au
  deuxième échec, la sortie (un message à l'équipe). Dans un même tour, une seule fois (C7, H6, DF7).
* La relecture n'est validée que si la personne l'a entendue : changée après le « oui », elle repart, se pose et se dit (C3 b, RC10).
"""

from __future__ import annotations

from api.services.actions_communes import journal_du_dit as J
from api.services.commande.porte import CLE_TEXTES_DU_CODE

COMPIEGNE = {"adresse": "8 rue Solférino", "commune": "Compiègne"}


def _prefixe(e) -> str | None:
    return (e.fiche_de_l_appel.get(CLE_TEXTES_DU_CODE) or {}).get("prefixe")


async def test_un_refus_redit_issue_puis_sortie(essai_de):
    e = await essai_de()
    await e.tour("en livraison", mode_de_retrait="livraison")
    r1 = await e.tour("au 8 rue Solférino à Compiègne", **COMPIEGNE)
    assert _prefixe(e) and "Compiègne" in _prefixe(e), r1
    r2 = await e.tour("si, à Compiègne", **COMPIEGNE)
    assert not _prefixe(e) and J.A_FAIRE_ISSUE in (r2.get("a_faire") or ""), r2
    r3 = await e.tour("Compiègne je vous dis", **COMPIEGNE)
    assert not _prefixe(e) and J.A_FAIRE_SORTIE in (r3.get("a_faire") or ""), r3


async def test_un_refus_n_est_dit_qu_une_fois_dans_le_tour(essai_de):
    e = await essai_de()
    await e.tour("en livraison", mode_de_retrait="livraison")
    await e.tour("au 8 rue Solférino à Compiègne", **COMPIEGNE)
    assert _prefixe(e)
    r = await e.fiche(**COMPIEGNE)  # une seconde fiche dans le même tour (le second passage refait la même)
    assert not _prefixe(e) and J.A_FAIRE_ISSUE not in (r.get("a_faire") or ""), r


async def test_la_relecture_changee_apres_le_oui_repart_et_se_dit(essai_de):
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    q = e.p["question"]
    await e.tour("non", reponse={"question_id": q["id"], "sens": "refuse"})
    await e.tour("c'est tout", c_est_tout=True)
    q = e.p["question"]
    await e.tour("oui par carte", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="carte_bancaire")
    assert e.p["question"]["type"] == "numero_affiche"
    await e.tour("pour dix-neuf heures", heure="dix-neuf heures")
    q = e.p["question"]
    assert q["type"] == "relecture" and e.p["etape"] != "accordee", e.p  # l'accord valait pour l'ancienne relecture
    dit = (e.fiche_de_l_appel.get(CLE_TEXTES_DU_CODE) or {}).get("avant") or ""
    assert "dix-neuf heures" in dit and dit.endswith("C'est bon ?"), dit
    await e.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    assert e.p["etape"] == "accordee", e.p  # le « oui » à la relecture entendue la valide
