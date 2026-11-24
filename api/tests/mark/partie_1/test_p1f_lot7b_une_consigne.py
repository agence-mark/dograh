"""[.mark] Lot 7b, ligne 28 : une seule fonction écrit les consignes du retour (``consignes.une_consigne``), par rang ; aucune consigne due n'est jetée.

Règle écrite (lot 7a, ligne 28, corrigée par la fiche 7b) : allergie > sortie > issue > refus à dire > question > rien changé > reste ; la sortie remplace les consignes de refus,
d'issue et de question, jamais celle de l'allergie.
"""

from __future__ import annotations

import re
from pathlib import Path

from api.services.actions_communes import consignes as C
from api.services.actions_communes import du as DU
from api.services.actions_communes import journal_du_dit as J
from api.services.restauration.carte_et_allergenes import allergie_de_la_commande as ALLERGIE

API = Path(__file__).resolve().parents[3]
ALLERGIE_DITE = ALLERGIE.A_FAIRE_DE_L_ALLERGIE


def test_au_troisieme_refus_la_sortie_ne_jette_jamais_l_allergie():
    """Client « Je suis allergique aux noix ; un tiramisu et une pizza au homard » : au 3e refus de suite, la consigne d'allergie reste avec la sortie."""
    retour = {"a_faire": "rien n'est changé : refais la fiche sans pizza"}
    DU.assembler(retour, DU.Du(consignes=((C.ALLERGIE, ALLERGIE_DITE),)),
                 DU.Du(consignes=((C.ISSUE, J.A_FAIRE_ISSUE), (C.REFUS_A_DIRE, "dis-lui le refus"), (C.QUESTION, "puis pose la question"), (C.SORTIE, J.A_FAIRE_SORTIE))))
    consigne = retour["a_faire"]
    assert ALLERGIE_DITE in consigne and J.A_FAIRE_SORTIE in consigne, consigne
    assert consigne.index(ALLERGIE_DITE) < consigne.index(J.A_FAIRE_SORTIE)
    for remplacee in (J.A_FAIRE_ISSUE, "dis-lui le refus", "puis pose la question"):
        assert remplacee not in consigne, consigne
    assert "refais la fiche sans pizza" in consigne  # le reste n'est pas jeté


def test_la_boucle_pose_la_sortie_par_une_consigne_et_sans_collage():
    retour = {"a_faire": "base"}
    DU.assembler(retour, DU.Du(boucle=True, consignes=((C.ALLERGIE, ALLERGIE_DITE), (C.ISSUE, J.A_FAIRE_ISSUE))))
    assert retour["a_faire"] == C.SEPARATEUR.join((ALLERGIE_DITE, J.A_FAIRE_SORTIE, "base")), retour["a_faire"]


def test_les_consignes_sont_rangees_par_rang_sans_doublon():
    assert C.une_consigne(((C.RESTE, "e"), (C.QUESTION, "d"), (C.ALLERGIE, "a"), (C.QUESTION, "d"), (C.ISSUE, "c"))) == "a ; c ; d ; e"
    assert C.une_consigne(()) is None


def test_aucun_collage_de_consignes_par_point_virgule_dans_les_poseurs():
    for chemin in ("services/actions_communes/du.py", "services/commande/porte.py", "services/restauration/carte_et_allergenes/allergie_de_la_commande.py",
                   "services/actions_communes/barrieres.py", "services/reservation/porte.py"):
        assert '" ; ".join' not in (API / chemin).read_text(encoding="utf-8"), chemin


async def test_le_refus_et_l_allergie_donnent_leurs_deux_consignes_dans_l_ordre(essai_de):
    from api.tests.mark.partie_1.aides_briques import brique

    e = await brique(essai_de, "INF6")
    await e.tour("un gâteau aux noix", ajouter=[{"article": "gâteau aux noix", "quantite": 1}])
    e.fiche_de_l_appel["allergie"] = "noix"
    r = await e.tour("un tiramisu et une pizza au homard", note_generale="allergique aux noix",
                     ajouter=[{"article": "tiramisu", "quantite": 1}, {"article": "pizza au homard", "quantite": 1}])
    consigne = str(r.get("a_faire"))
    assert consigne.startswith(ALLERGIE_DITE) and len(consigne) > len(ALLERGIE_DITE) + 20, consigne  # l'allergie d'abord, puis la consigne du refus
