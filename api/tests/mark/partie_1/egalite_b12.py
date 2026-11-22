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
ECARTS_DE_LA_CUISINE: dict[str, str] = {
    # Clôture B1 (registre des questions) : ces fiches de B12 ont été écrites par le modèle CONTRE l'ancien contrat ; elles citent une question close
    # (conv5 : la proposition du Coca, tombée quand le Coca est entré au panier, RC9) ou l'ancien numéro d'une relecture reposée (conv3 : Q-3, le
    # registre garde Q-2, RC9). La règle nouvelle n'écarte que la case ``reponse`` (jamais le reste) : le panier et la fin sont justes, le drapeau
    # « refus » diffère. À réécrire en tests de règle au lot B6 (audit des tests § 2, groupe des égalités B12).
    "conv3-taille": "B1 : fiche B12 qui cite l'ancien numéro de la relecture reposée (Q-3 ; le registre garde Q-2)",
    "conv5-consigne": "B1 : fiche B12 qui répond à la proposition déjà close (Coca entré au panier)",
    # DC3 (Evan, 22/11) : la proposition se ferme au premier tour sans « oui » ; ces fiches B12 y répondent un tour plus tard (« oui je prends le coca
    # offert », « pas de coca ») : la réponse à une question close n'écarte que sa case ; l'article se demande par son nom
    "conv2-hors-zone": "DC3 : fiche B12 qui répond à la proposition close au tour d'avant (changement de mode sans « oui »)",
    "conv4-allergie": "DC3 : fiche B12 qui répond à la proposition close au tour d'avant (question sur l'allergie sans « oui »)",
}
ECARTS_DE_LA_PAROLE: dict[str, str] = {"conv3-taille": ECARTS_DE_LA_CUISINE["conv3-taille"], "conv2-hors-zone": ECARTS_DE_LA_CUISINE["conv2-hors-zone"]}

# Les statuts du module que le banc range en refus (son ``REFUSE`` et son ``INTROUVABLE``).
REFUS_DU_MODULE = frozenset({"HORS_ZONE", "INTROUVABLE", "RUPTURE", "HORS_CARTE", "INTERDIT"})


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
            # le banc compte un refus de la fiche ET un refus du module (``REFUSE``, ``INTROUVABLE`` : ``appel_b12._executer_commande``) ;
            # au fork, le refus du module est le statut métier d'un résultat (hors zone, rupture…), la fiche restant appliquée
            refuse = refuse or bool(retour.get("refus")) or any(r.get("statut_du_module") in REFUS_DU_MODULE for r in retour.get("resultats") or [])
        annulee = bool(e.p.get("annulee"))
        obtenu = {"lignes": [] if annulee else [_sans_presentation(x) for x in _lignes(e)], "refus": refuse, "mode": e.p.get("mode"),
                  "enregistree": bool(e.p.get("enregistree")), "annulee": annulee}
        attendu = {"lignes": [] if tour["annulee"] else sorted(_sans_presentation(x) for x in tour["lignes"]), "refus": tour["refus"] > 0, "mode": tour["mode"],
                   "enregistree": tour["enregistree"], "annulee": tour["annulee"]}
        if obtenu != attendu:
            ecarts.append(f"{conversation['conversation']} tour {i} « {tour['dit'][:50]} » : banc {attendu} / fork {obtenu}")
    return ecarts
