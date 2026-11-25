"""[.mark] Clôture de la Partie 1, lot A2 : les tests qui figeaient un défaut (TF1, TF2 de l'audit des rustines), inversés en tests de règle.

Ils sont rouges tant que le mécanisme du lot B qui les tient n'est pas posé (``xfail`` strict : quand le lot B les rend verts, ``xfail`` doit être
retiré, sinon la suite rougit). Un changement dit pendant une question est pris (R2, défaut C1) ; un changement d'une commande enregistrée dit son
nouveau total par le code (R4, défaut H18).
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from api.services.commande.porte import CLE_TEXTES_DU_CODE

from .aides_de_la_commande import (
    jusqu_a_l_enregistrement_de_la_proposition as _jusqu_a_l_enregistrement,
)
from .aides_de_la_commande import jusqu_a_la_proposition as _jusqu_a_la_proposition


async def test_un_changement_dit_pendant_une_proposition_est_pris(essai_de):
    """TF1 (`test_l20_changement_pendant_une_question.py::test_une_autre_question_que_la_relecture_garde_sa_regle`, supprimé) exigeait l'inverse.
    E7 → G29 : « en fait deux » pendant « un Coca ? », sans ``reponse`` : la quantité passe à deux (DC3 : la proposition tombe, sans « oui »)."""
    e = await essai_de()
    await _jusqu_a_la_proposition(e)
    r = await e.tour("en fait mettez-en deux", changer_quantite=[{"ligne": 1, "quantite": 2}])
    assert [l["quantite"] for l in e.p["lignes"]] == [2], r
    assert (CONV.question_de(e.p) or {}).get("type") != "proposition", r


async def test_un_changement_d_une_commande_enregistree_dit_son_nouveau_total(essai_de):
    """TF2 (`porte.textes_du_code`, ``deja_enregistree`` : « un changement d'une commande enregistrée n'est pas une nouvelle confirmation »).
    E18 : la commande enregistrée passe de 10,90 € à 21,80 € ; le code le dit lui-même, jamais la phrase écrite avant le changement."""
    e = await essai_de()
    await _jusqu_a_l_enregistrement(e)
    r = await e.tour("en fait deux", changer_quantite=[{"ligne": 1, "quantite": 2}])
    assert r["statut"] == "ENREGISTREE", r
    dit = " ".join((e.fiche_de_l_appel.get(CLE_TEXTES_DU_CODE) or {}).values())
    assert "vingt et un euros quatre-vingts" in dit, (dit, r)
