"""[.mark] Chantier Partie 1, lot 5 (D13, L05-12) : le DÉCOUPAGE d'un tour, ce qui vient de nous et ce qui vient du fournisseur. Sert au lot 20.

    decouper(run) -> [{tour, fin_de_parole_ms, modele_ms, passages, code_ms, voix_ms, nous_ms, fournisseur_ms}]

Lit un run tel que Dograh le garde (``logs.realtime_feedback_events`` et la fiche de l'appel ``gathered_context``) :

- **fin de parole** : du dernier mot de l'appelant (transcription finale) au départ de la première requête du tour (le chronomètre du run,
  ``analyse_run/mesures.chronometre_du_run``, ``finDeTour``) ;
- **modèle** : du départ de la première requête au premier mot de la passe qui parle (``premierMot - finDeTour``), et le nombre de passages ;
- **code** : le temps de chaque fiche exécutée dans ce tour, base comprise (``porte.CLE_MESURES_DU_CODE``, noté par la porte) ;
- **voix** : du texte remis à la voix au premier son (``premierSon - voix``).

Nous contre le fournisseur (D13) : ``nous_ms`` = le code, plus le temps des passages en trop (chaque passage au-delà du premier est un choix de
notre contrat) ; ``fournisseur_ms`` = le reste du temps du modèle. Une lenteur ponctuelle du fournisseur se prouve en rejouant la même requête
(banc B7, point 7) : ce découpage le montre, il ne le juge pas.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from api.services.analyse_run.mesures import chronometre_du_run
from api.services.commande.porte import CLE_MESURES_DU_CODE

POSTES = ("tour", "fin_de_parole_ms", "modele_ms", "passages", "code_ms", "voix_ms", "nous_ms", "fournisseur_ms")
TRACE_D_ESSAI = Path(__file__).parent / "donnees" / "trace_tour_essai.json"


def _ms(secondes: Any) -> float | None:
    return round(secondes * 1000, 1) if isinstance(secondes, (int, float)) else None


def decouper(run: dict) -> list[dict[str, Any]]:
    chrono = chronometre_du_run(run)
    fiche = run.get("gathered_context") or {}
    code_par_tour: dict[Any, float] = {}
    for m in fiche.get(CLE_MESURES_DU_CODE) or []:
        code_par_tour[m.get("tour")] = code_par_tour.get(m.get("tour"), 0.0) + float(m.get("ms") or 0)
    sortie = []
    for t in chrono["tours"]:
        numero = int(t["tour"]) if t["tour"] == t["tour"] else None  # nan : tour sans numéro
        fin = _ms(t["finDeTour"])
        modele = _ms(t["premierMot"] - t["finDeTour"]) if t["premierMot"] is not None and t["finDeTour"] is not None else None
        voix = _ms(t["premierSon"] - t["voix"]) if t["premierSon"] is not None and t["voix"] is not None else None
        code = code_par_tour.get(numero)
        passages = int(t["passes"])
        en_trop = (modele or 0) * (passages - 1) / passages if passages > 1 and modele else 0.0
        sortie.append({
            "tour": numero, "fin_de_parole_ms": fin, "modele_ms": modele, "passages": passages, "code_ms": code, "voix_ms": voix,
            "nous_ms": round((code or 0) + en_trop, 1), "fournisseur_ms": round((modele or 0) - en_trop, 1) if modele is not None else None,
        })
    return sortie


def trace_d_essai() -> dict:
    """Un run enregistré au format de Dograh (événements du direct et fiche de l'appel), écrit d'après ``chronometre_du_run`` et la porte."""
    return json.loads(TRACE_D_ESSAI.read_text(encoding="utf-8"))
