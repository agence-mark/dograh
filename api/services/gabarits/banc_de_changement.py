"""[.mark] Changer de modèle = un banc, jamais un chantier (D38, lot 0 élément L00-16).

  python -m api.services.gabarits.banc_de_changement --modele <identifiant> [--a-vide]

Rend le tableau « candidat contre témoin » aux seuils du § 1 du plan, précédé d'une liste à cocher sans requête. À vide (lot 0), rien n'est
joué : le tableau dit ce qui serait joué et les valeurs du témoin. Le vrai jeu est au lot 20 : banc A (sans modèle, doit rester vert),
banc B (bon outil, arguments, constance), conversations entières deux fois, latence sans voix ; il passe par les outils du banc rebranché
sur le fork (lot 6, D68), qui écrivent leurs résultats sous le nom du modèle candidat.
"""

from __future__ import annotations

import argparse
import json
import sys

from api.services.gabarits.restauration.textes import TEMOIN, version_pour

# Avant tout banc, sans requête : ce qui disqualifie un modèle d'office (mémoire `llm-scaleway-seulement-gemma-4`, D12)
LISTE_A_COCHER = (
    ("hebergement_en_france", "Hébergé en France (ou dans l'Union), données en France"),
    ("appels_d_outils", "Appels d'outils tenus par le fournisseur (protocole OpenAI)"),
    ("fiche_a_cases", "Fiche à cases acceptée : un objet aux cases typées, toutes facultatives"),
    ("prix_connu", "Prix officiel par million de jetons connu et renseigné"),
)

# Les épreuves et leurs seuils (§ 1 du plan, D20, D39, D42, D69)
EPREUVES = (
    ("banc_a", "Banc A (sans modèle), toutes les cartes", "vert en entier"),
    ("bon_outil", "Banc B : bon outil", ">= 95 %"),
    ("bons_arguments", "Banc B : bons arguments", ">= 90 %"),
    ("constance", "Banc B : constance selon la formulation", ">= 90 %"),
    ("conversations_finale", "Conversations entières, mesure finale, deux jeux", ">= 90 %, 0 erreur grave, 0 fait inventé"),
    ("passes_par_tour", "Passes par tour", "mesurées (témoin B12 : 1,51 et 1,54)"),
    ("latence_fiche", "Exécution d'une fiche", "<= 50 ms"),
)
TEMOIN_VALEURS = {"banc_a": "vert (lot 20)", "bon_outil": "95,5 % (B9)", "conversations_finale": "92 % en moyenne (B8 à B12)",
                  "passes_par_tour": "1,51 / 1,54 (B12)", "latence_fiche": "mesurée au lot 5"}


def jouer(modele: str, a_vide: bool = True, coches: dict[str, bool] | None = None) -> dict:
    coches = coches or {}
    liste = [{"cle": k, "libelle": l, "coche": bool(coches.get(k))} for k, l in LISTE_A_COCHER]
    if not a_vide:
        raise NotImplementedError("le vrai jeu se lance au lot 20, par le banc rebranché sur le fork (D68)")
    lignes = [{"epreuve": k, "libelle": l, "seuil": s, "temoin": TEMOIN_VALEURS.get(k, "—"), "candidat": "non joué (à vide)"}
              for k, l, s in EPREUVES]
    return {"candidat": modele, "temoin": TEMOIN, "textes_du_candidat": version_pour(modele), "a_vide": a_vide,
            "liste_a_cocher": liste, "epreuves": lignes, "requetes": 0}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modele", required=True)
    ap.add_argument("--a-vide", action="store_true")
    a = ap.parse_args(argv)
    print(json.dumps(jouer(a.modele, a_vide=a.a_vide or True), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
