"""[.mark] Chantier Partie 1, lot 3, étape 12 (D67) : égalité banc et fork à la vraie porte, sans requête (le test : ``test_l03_porte.py``).

Les réponses du modèle enregistrées en B12 (version finale, commande, répétition 0 : ``reponses_b12/commande.json``, copiées de
``banc-b12/resultats/conv-leger-commande-entier-final.jsonl``) sont servies telles quelles à la vraie porte (``porte.executer``), sur la carte de
Casa Italia du banc A ; après chaque tour, le panier obtenu (lignes, mode, commande enregistrée) et le refus rendu (oui ou non) sont comparés à ceux
que le banc a enregistrés. Aucun appel à un fournisseur de modèle (garde du dossier). Les phrases dites sont comparées au lot 6.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ICI = Path(__file__).parent
REPONSES = json.loads((ICI / "reponses_b12" / "commande.json").read_text(encoding="utf-8"))
CONVERSATIONS = [c["conversation"] for c in REPONSES["conversations"]]

# Les écarts au banc qui viennent de la cuisine (``moteur.py``), pas de la porte : chacun a sa ligne dans ``a-trancher.md`` et son lot.
ECARTS_DE_LA_CUISINE = {
    "conv2-hors-zone": "ordre imposé : sans zone retenue (hors zone), les articles restent gardés, pas en lignes ; la vente en plus ne suit pas (lot 4)",
    "conv3-taille": "changer_quantite(variante Mega) rend OK sans changer la ligne (C8, moteur.modifier ; lot 4)",
    "conv5-consigne": "« 4 rue de Beauvais » + Chantilly : la commune lue est Beauvais, l'adresse est introuvable (C6, verifier_adresse ; lot 4)",
    "conv8-apres-enregistrement": "changer_quantite(variante Mega) après l'enregistrement ne change pas la ligne (C8 ; lot 4)",
}


def _sans_presentation(ligne: str) -> str:
    """Le banc écrit la déclinaison unique et l'offre dans le nom (« Coca-Cola 33 cl offerte ») ; le fork les porte à part (prix, offre)."""
    return re.sub(r"\s+(\d+\s*cl|offerte?)\b", "", ligne).strip()


def _lignes(e) -> list[str]:
    return sorted(f"{l['quantite']} x {l['nom']}" for l in e.p["lignes"])


async def ecarts_de_la_conversation(e, conversation: dict) -> list[str]:
    """Joue les fiches enregistrées d'une conversation à la vraie porte ; rend les écarts au banc, tour par tour."""
    ecarts = []
    for i, tour in enumerate(conversation["tours"]):
        e.dit(tour["dit"])
        refuse = False
        for appel in tour["appels"]:
            if appel["nom"] != "fiche":
                continue
            retour = await e.fiche(**appel["args"])
            refuse = refuse or bool(retour.get("refus"))
        annulee = bool(e.p.get("annulee"))
        obtenu = {"lignes": [] if annulee else [_sans_presentation(x) for x in _lignes(e)], "refus": refuse, "mode": e.p.get("mode"),
                  "enregistree": bool(e.p.get("enregistree")), "annulee": annulee}
        attendu = {"lignes": [] if tour["annulee"] else sorted(_sans_presentation(x) for x in tour["lignes"]), "refus": tour["refus"] > 0, "mode": tour["mode"],
                   "enregistree": tour["enregistree"], "annulee": tour["annulee"]}
        if obtenu != attendu:
            ecarts.append(f"{conversation['conversation']} tour {i} « {tour['dit'][:50]} » : banc {attendu} / fork {obtenu}")
    return ecarts
