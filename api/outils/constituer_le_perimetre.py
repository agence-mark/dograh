"""[.mark] Constitue ``perimetre_partie_1.json`` : les fichiers et fonctions écrits ou grossis par la Partie 1 (``git diff`` 2e289ce8^..7bdfd515),
plus la longueur d'avant de ``run_pipeline`` et du tour au clavier (lue à ``2e289ce8^``). Rejouable : ``python -m api.outils.constituer_le_perimetre``
depuis la racine du dépôt. Le fichier produit n'est ensuite figé que par le coordinateur."""

from __future__ import annotations

import json
import subprocess

from api.outils import inventaire_rustines as I

AVANT, APRES = "2e289ce8^", "7bdfd515"
# cle: (fichier, nom d'avant la Partie 1, nom à la base). Le corps de ``_run_pipeline_impl`` et du tour au clavier ont été renommés.
LONGUEURS_SUIVIES = {
    "run_pipeline": ("services/pipecat/run_pipeline.py", "_run_pipeline_impl", "_run_pipeline_corps"),
    "tour_au_clavier": ("services/workflow/text_chat_runner.py", "execute_text_chat_pending_turn", "_executer_le_tour"),
}


def _source_a(commit: str, chemin: str) -> str | None:
    r = subprocess.run(["git", "show", f"{commit}:api/{chemin}"], cwd=I.RACINE_DEPOT, capture_output=True, text=True, encoding="utf-8")
    return r.stdout if r.returncode == 0 else None


def main() -> None:
    ajoutees = I.lignes_ajoutees(AVANT, APRES)
    fichiers, fonctions = [], {}
    for chemin, lignes in sorted(ajoutees.items()):
        fichier = I.RACINE_API / chemin
        if not fichier.exists() or not lignes:
            continue
        touchees = I.fonctions_touchees(fichier.read_text(encoding="utf-8"), lignes)
        fichiers.append(chemin)
        if touchees:
            fonctions[chemin] = touchees
    longueurs = {}
    for cle, (chemin, nom_avant, nom) in LONGUEURS_SUIVIES.items():
        avant = _source_a(AVANT, chemin)
        apres = _source_a(APRES, chemin)
        longueurs[cle] = {
            "fichier": chemin, "fonction": nom, "fonction_d_avant": nom_avant,
            "avant": (I.fonctions_du_fichier(avant).get(nom_avant) if avant else None),
            "a_la_base": (I.fonctions_du_fichier(apres).get(nom) if apres else None),
        }
    sortie = {"periode": f"{AVANT}..{APRES}", "fichiers": fichiers, "fonctions": fonctions, "longueurs_d_avant": longueurs}
    (I.RACINE_API / "outils" / "perimetre_partie_1.json").write_text(json.dumps(sortie, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(len(fichiers), "fichiers,", sum(len(v) for v in fonctions.values()), "fonctions,", longueurs)


if __name__ == "__main__":
    main()
