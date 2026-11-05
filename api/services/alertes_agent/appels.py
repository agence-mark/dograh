"""[.mark] Partie 3, L3e : les alertes sur les VRAIS appels (audit 12 § 3). Une période contre celle de même durée qui la précède.

Cinq signaux, tous lus dans ce que l'après-appel a déjà rangé (``annotations['boucle']`` et le verdict du juge) : aucun appel à un
modèle, aucune dépense, jamais d'essai (les appels d'essai n'entrent pas dans ces annotations).

* ``hausse_rates`` : part des appels jugés qui ont au moins un critère raté ou non vérifiable ;
* ``hausse_transferts`` : part des appels terminés par un transfert ;
* ``hausse_garde_fous`` : part des appels où un garde-fou de sécurité s'est déclenché ;
* ``hausse_pannes`` : part des appels passés en repli de panne ;
* ``hausse_latence`` : latence médiane des appels (seulement quand elle est mesurée des deux côtés).

Une alerte part quand la mesure de la période courante monte d'au moins ``hausse`` % contre la précédente, avec au moins
``appels_min`` appels de chaque côté et ``cas_min`` appels concernés (sinon c'est du bruit). Une période précédente à zéro compte
comme une hausse infinie. L'alerte porte la liste des appels concernés (``appels``, plafonnée) : « Voir les appels ».

Idempotent : l'identifiant d'une alerte est celui du bloc de ``jours`` jours où l'on se trouve (``cle``) ; la tâche de nuit qui la
recalcule met à jour ses chiffres, elle ne la lève pas deux fois. ⛔ Ne lève jamais plus que la lecture des appels.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Any

from api.db import db_client
from api.services.alertes_agent import types

APPELS_MAX = 50  # les appels concernés gardés dans l'alerte (la liste complète est dans la page des appels)


def _bilan(annotations: Any) -> dict[str, Any]:
    if not isinstance(annotations, dict):
        return {}
    indicateurs = (annotations.get("boucle") or {}).get("indicateurs")
    return indicateurs if isinstance(indicateurs, dict) and indicateurs else {}


def _juge(annotations: Any) -> list[dict[str, Any]] | None:
    juge = annotations.get("juge") if isinstance(annotations, dict) else None
    if not isinstance(juge, dict) or juge.get("etat") != "juge":
        return None
    verdicts = juge.get("verdicts")
    return [v for v in verdicts if isinstance(v, dict)] if isinstance(verdicts, list) and verdicts else None


# Un signal = une fonction qui lit UN appel et rend ``None`` (appel non mesurable pour ce signal), ``True`` ou ``False`` (concerné ?).
def _rate(annotations: Any) -> bool | None:
    verdicts = _juge(annotations)
    return None if verdicts is None else any(v.get("verdict") != "reussi" for v in verdicts)


def _transfert(annotations: Any) -> bool | None:
    bilan = _bilan(annotations)
    return bool(bilan.get("transfert")) if bilan else None


def _garde_fou(annotations: Any) -> bool | None:
    bilan = _bilan(annotations)
    return (int(bilan.get("garde_fous") or 0) > 0) if bilan else None


def _panne(annotations: Any) -> bool | None:
    bilan = _bilan(annotations)
    return bool(bilan.get("panne")) if bilan else None


def _latence(annotations: Any) -> float | None:
    valeur = _bilan(annotations).get("latence_mediane")
    return float(valeur) if isinstance(valeur, (int, float)) and not isinstance(valeur, bool) else None


PARTS = {
    types.HAUSSE_RATES: _rate,
    types.HAUSSE_TRANSFERTS: _transfert,
    types.HAUSSE_GARDE_FOUS: _garde_fou,
    types.HAUSSE_PANNES: _panne,
}


def _hausse_pct(avant: float, apres: float) -> float:
    if avant <= 0:
        return float("inf") if apres > 0 else 0.0
    return (apres - avant) / avant * 100


def cle_de_la_periode(maintenant: datetime, jours: int) -> str:
    """Le bloc de ``jours`` jours où l'on se trouve : la même alerte revue la nuit suivante garde sa clé."""
    return f"p{int(maintenant.timestamp() // 86400) // max(1, jours)}"


def separer(lignes: list[dict[str, Any]], jours: int, maintenant: datetime) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(période courante, période précédente), sur ``cree_le``. Une ligne sans date lisible est écartée."""
    debut = maintenant - timedelta(days=jours)
    avant_debut = maintenant - timedelta(days=2 * jours)
    courante, precedente = [], []
    for ligne in lignes:
        quand = ligne.get("cree_le")
        if not isinstance(quand, datetime):
            continue
        quand = quand if quand.tzinfo else quand.replace(tzinfo=UTC)
        if quand >= debut:
            courante.append(ligne)
        elif quand >= avant_debut:
            precedente.append(ligne)
    return courante, precedente


def comparer(code: str, lignes: list[dict[str, Any]], seuils: dict[str, float], maintenant: datetime | None = None) -> dict[str, Any] | None:
    """``{"cle", "mesures", "appels", "periode_jours"}`` quand le signal ``code`` monte assez, sinon ``None``. Pur."""
    maintenant = maintenant or datetime.now(UTC)
    jours = int(seuils["jours"])
    courante, precedente = separer(lignes, jours, maintenant)
    minimum = seuils["appels_min"]
    if code == types.HAUSSE_LATENCE:
        mesure = _comparer_latence(courante, precedente, seuils, minimum)
    elif code in PARTS:
        mesure = _comparer_part(code, courante, precedente, seuils, minimum)
    else:
        return None
    if mesure is None:
        return None
    mesures, appels = mesure
    return {
        "version": None,
        "contre": None,
        "cle": cle_de_la_periode(maintenant, jours),
        "periode_jours": jours,
        "mesures": mesures,
        "appels": appels[:APPELS_MAX],
        "appels_concernes": len(appels),
    }


def _comparer_part(code, courante, precedente, seuils, minimum):
    lire = PARTS[code]
    maintenant_ = [(l, lire(l["annotations"])) for l in courante]
    avant_ = [lire(l["annotations"]) for l in precedente]
    maintenant_ = [(l, v) for l, v in maintenant_ if v is not None]
    avant_ = [v for v in avant_ if v is not None]
    if len(maintenant_) < minimum or len(avant_) < minimum:
        return None
    concernes = [l["run_id"] for l, v in maintenant_ if v]
    part_apres, part_avant = len(concernes) / len(maintenant_), sum(avant_) / len(avant_)
    if len(concernes) < seuils["cas_min"] or _hausse_pct(part_avant, part_apres) < seuils["hausse"] - 1e-9:
        return None
    return (
        [
            {
                "nom": code,
                "avant": round(part_avant, 4),
                "apres": round(part_apres, 4),
                "ecart": round(part_apres - part_avant, 4),
                "appels_avant": len(avant_),
                "appels_apres": len(maintenant_),
            }
        ],
        concernes,
    )


def _comparer_latence(courante, precedente, seuils, minimum):
    maintenant_ = [(l, _latence(l["annotations"])) for l in courante]
    maintenant_ = [(l, v) for l, v in maintenant_ if v is not None]
    avant_ = [v for v in (_latence(l["annotations"]) for l in precedente) if v is not None]
    if len(maintenant_) < minimum or len(avant_) < minimum:
        return None
    med_avant, med_apres = median(avant_), median(v for _, v in maintenant_)
    limite = med_avant * (1 + seuils["hausse"] / 100)
    concernes = [l["run_id"] for l, v in maintenant_ if v > limite]
    if len(concernes) < seuils["cas_min"] or _hausse_pct(med_avant, med_apres) < seuils["hausse"] - 1e-9:
        return None
    return (
        [
            {
                "nom": types.HAUSSE_LATENCE,
                "avant": round(med_avant, 2),
                "apres": round(med_apres, 2),
                "ecart": round(med_apres - med_avant, 2),
                "appels_avant": len(avant_),
                "appels_apres": len(maintenant_),
            }
        ],
        concernes,
    )


def resume(code: str, comparaison: dict[str, Any]) -> str:
    """Une phrase lisible (en français) pour la page, le bandeau et le mail."""
    m = comparaison["mesures"][0]
    duree = comparaison["periode_jours"]
    periode = "sur 24 h" if duree == 1 else f"sur {duree} jours"
    if code == types.HAUSSE_LATENCE:
        corps = f"latence médiane {m['avant']:.2f} s → {m['apres']:.2f} s"
    else:
        etiquette = {
            types.HAUSSE_RATES: "appels jugés avec un critère raté",
            types.HAUSSE_TRANSFERTS: "appels transférés",
            types.HAUSSE_GARDE_FOUS: "appels avec un garde-fou déclenché",
            types.HAUSSE_PANNES: "appels touchés par une panne",
        }[code]
        corps = f"{etiquette} {m['avant'] * 100:.0f} % → {m['apres'] * 100:.0f} %"
    return f"{corps} {periode} ({comparaison['appels_concernes']} appel(s) concerné(s))."


class LectureDesAppels:
    """Une seule lecture des appels par évaluation et par durée : cinq signaux ne font pas cinq requêtes (aucune cascade)."""

    def __init__(self, organisation_id: int, workflow_id: int):
        self._organisation_id, self._workflow_id = organisation_id, workflow_id
        self._lues: dict[int, list[dict[str, Any]]] = {}

    async def lignes(self, jours: int) -> list[dict[str, Any]]:
        if jours not in self._lues:
            self._lues[jours] = await db_client.runs_pour_la_qualite(self._organisation_id, jours=2 * jours, workflow_id=self._workflow_id)
        return self._lues[jours]


def un_calcul(code: str):
    async def calcul(_organisation_id: int, _workflow_id: int, seuils: dict[str, float], lecture: LectureDesAppels) -> dict[str, Any] | None:
        lignes = await lecture.lignes(int(seuils["jours"]))
        comparaison = comparer(code, lignes, seuils)
        if comparaison is not None:
            comparaison["resume"] = resume(code, comparaison)
            comparaison["workflow_nom"] = lignes[0]["workflow_nom"] if lignes else ""
        return comparaison

    return calcul
