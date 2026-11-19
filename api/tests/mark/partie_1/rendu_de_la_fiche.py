"""[.mark] Chantier Partie 1, lot 8 (D66) : le RENDU de la fiche du modèle pour une carte chargée, comparé avec et sans les données d'une brique.

Une brique **change la fiche du modèle** quand, la carte de la brique chargée, ce que le modèle voit diffère de la même carte sans elle : les cases visibles,
les listes fermées, la question que la cuisine rend pour chaque article (déclinaison, puis chaque choix obligatoire), le fait que la lecture d'un article rend.
Le rendu ne lit que la carte CHARGÉE au décroché (``charger_pour_l_appel``) : aucune requête pendant le calcul d'une question.
"""

from __future__ import annotations

import copy
from typing import Any

from api.db.bases_clients import restauration
from api.services.commande import contrat, moteur
from api.services.commande.briques import prx5, registre


async def rendu_de_la_fiche(essai, avec_le_prix: bool = False) -> dict[str, Any]:
    """``{objets, cases, listes, questions, lectures}`` pour la carte que l'essai a chargée."""
    listes, objets = await essai.source.charger_pour_l_appel()
    vue = contrat.VueDeLaCommande(mode="emporter", lignes=1, objets_de_la_carte=objets)
    carte = await restauration.carte_du_restaurant(essai.monde.c, essai.monde.a)
    questions: dict[str, Any] = {}
    lectures: dict[str, Any] = {}
    for p in [*carte["produits"], *carte["formules"]]:  # lot 11 : les formules aussi (leurs étapes sont des questions)
        article = await essai.source.article(p["id"], "emporter")
        parcours = [{"n": 1, "code": None, "choix": [], "retires": []}]
        parcours += [{"n": 1, "code": d["code"], "choix": [], "retires": []} for d in article["declinaisons"] if d["vendable"]]
        questions[p["nom"]] = [moteur._question(article, copy.deepcopy(ligne)) for ligne in parcours]
        if article.get("formule"):  # lot 11 : chaque étape d'une formule est une question que le modèle pose un jour (ses choix, son nombre)
            questions[p["nom"]].append([(g["nom"], g["min"], g["max"], sorted(o["nom"] for o in g["options"] if o["vendable"])) for g in article["groupes"]])
        lectures[p["nom"]] = {cle: article.get(cle) for cle in ("du_moment", "texte_du_jour", "servi_avec", "contenu", "justificatif", "condition")}
        if avec_le_prix:  # lot 12 : le fait ``prix`` de la lecture est celui de PRX5 ; les autres briques ne se comparent pas sur lui
            lectures[p["nom"]]["prix"] = prx5.brique_prx5_jamais_le_prix_de_depart_comme_final(article)
    return {"objets": objets, "cases": sorted(contrat.cases_visibles_de_la_vue(vue)), "listes": listes, "questions": questions, "lectures": lectures}


async def la_brique_change_la_fiche(code: str, avec, sans) -> bool:
    """Le rendu avec la carte de la brique diffère-t-il du rendu sans ses données ?"""
    return (await rendu_de_la_fiche(avec, code == "PRX5")) != (await rendu_de_la_fiche(sans, code == "PRX5"))


def sans_la_brique(code: str, carte: dict) -> dict:
    """La carte sans les données de la brique (la fonction que le registre déclare)."""
    brique = registre.BRIQUES[code]
    assert brique.sans_la_brique is not None, f"{code} ne dit pas comment se retirer de sa carte"
    return brique.sans_la_brique(copy.deepcopy(carte))
