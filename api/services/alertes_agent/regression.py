"""[.mark] Sous-lot 6 : une version fait-elle moins bien que la précédente ? (pur, aucune lecture de base)

Entrée : les lignes « agent × version » de la page Qualité (``boucle.qualite._versions``) d'UN agent. On compare la version la plus
récente à celle juste avant, sur deux mesures des VRAIS appels (jamais les essais) :

* la **note du juge** (sur 5) : une baisse d'au moins ``baisse_note`` points ;
* la **part d'appels avec impasse** : une hausse d'au moins ``hausse_impasses`` (0,05 = 5 points).

Une comparaison n'a de sens qu'avec assez d'appels des DEUX côtés (``appels_min``) : en dessous, on ne dit rien (le bruit n'est pas
une régression). Chaque mesure est jugée à part, avec son propre nombre d'appels (jugés pour la note, mesurés pour les impasses).
"""

from __future__ import annotations

from typing import Any


def comparer(lignes: list[dict[str, Any]], seuils: dict[str, float]) -> dict[str, Any] | None:
    """``{"version", "contre", "mesures": [...]}`` quand la plus récente est moins bonne que la précédente, sinon ``None``."""
    par_version = {int(ligne["version"]): ligne for ligne in lignes if ligne.get("version") is not None}
    if len(par_version) < 2:
        return None
    apres_n, avant_n = sorted(par_version, reverse=True)[:2]
    apres, avant = par_version[apres_n], par_version[avant_n]
    minimum = seuils["appels_min"]
    mesures: list[dict[str, Any]] = []
    if (
        apres.get("note") is not None
        and avant.get("note") is not None
        and apres.get("juges", 0) >= minimum
        and avant.get("juges", 0) >= minimum
        and avant["note"] - apres["note"] >= seuils["baisse_note"] - 1e-9
    ):
        mesures.append(
            {
                "nom": "note_du_juge",
                "avant": avant["note"],
                "apres": apres["note"],
                "ecart": round(apres["note"] - avant["note"], 2),
                "appels_avant": avant["juges"],
                "appels_apres": apres["juges"],
            }
        )
    if (
        apres.get("part_impasse") is not None
        and avant.get("part_impasse") is not None
        and apres.get("appels_mesures", 0) >= minimum
        and avant.get("appels_mesures", 0) >= minimum
        and apres["part_impasse"] - avant["part_impasse"] >= seuils["hausse_impasses"] - 1e-9
    ):
        mesures.append(
            {
                "nom": "impasses",
                "avant": avant["part_impasse"],
                "apres": apres["part_impasse"],
                "ecart": round(apres["part_impasse"] - avant["part_impasse"], 4),
                "appels_avant": avant["appels_mesures"],
                "appels_apres": apres["appels_mesures"],
            }
        )
    if not mesures:
        return None
    return {"version": apres_n, "contre": avant_n, "mesures": mesures}


def resume(comparaison: dict[str, Any]) -> str:
    """Une phrase lisible (en français) pour la réplique du problème et le mail."""
    morceaux = []
    for m in comparaison["mesures"]:
        if m["nom"] == "note_du_juge":
            morceaux.append(f"note du juge {m['avant']:.1f} → {m['apres']:.1f} sur 5")
        else:
            morceaux.append(f"appels avec impasse {m['avant'] * 100:.0f} % → {m['apres'] * 100:.0f} %")
    return f"Version {comparaison['version']} contre version {comparaison['contre']} : " + " ; ".join(morceaux) + "."
