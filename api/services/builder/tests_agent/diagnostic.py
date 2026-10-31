"""[.mark] Builder, lot 6 : classer l'échec AVANT toute correction (B39).

Un échec vient de l'agent, du test ou de l'exécution. Rien n'est changé sans accord : le classement est rendu avec
``accord_requis`` et le builder le DIT à la personne avant d'opérer (voir ``correction.CONSIGNE_DE_CORRECTION``).

* **exécution** : l'essai a levé une erreur (moteur, modèle, session) : le test n'a pas pu être joué, il ne dit rien de l'agent ;
* **test** : le critère vise une étape ou un outil que l'agent n'a pas, un texte vide ou trop court, ou un test sans critère réel ;
* **agent** : tout le reste (le test a tourné, le critère est sensé, la réponse est autre).

Pur : le graphe est lu par ses noms. ⛔ Zéro vocabulaire métier.
"""

from __future__ import annotations

from typing import Any

from api.services.builder.tests_agent.verdict import CRITERE_NEUTRE, normaliser

LONGUEUR_MIN_D_UN_TEXTE = 3


def noms_de_etapes(graphe: dict[str, Any]) -> set[str]:
    sortie: set[str] = set()
    for n in graphe.get("nodes") or []:
        if isinstance(n, dict):
            sortie.add(normaliser(n.get("id")))
            sortie.add(normaliser((n.get("data") or {}).get("name")))
    return sortie - {""}


def classer(
    critere: dict[str, Any] | None,
    *,
    erreur: str | None,
    etapes_de_l_agent: set[str],
    outils_de_l_agent: set[str],
) -> dict[str, Any]:
    """La cause d'un échec : ``{"cause", "raison", "accord_requis": True}``."""
    if erreur:
        return _r("execution", f"The test could not be played ({erreur[:120]}): it says nothing about the agent.")
    if critere is None or critere == CRITERE_NEUTRE:
        return _r("test", "The test has no real criterion.")
    genre = critere.get("type")
    if genre == "etape" and normaliser(critere.get("attendue")) not in etapes_de_l_agent:
        return _r("test", f"The expected step « {critere.get('attendue')} » does not exist in this agent.")
    if genre == "outil" and critere.get("nom") not in outils_de_l_agent:
        return _r("test", f"The tool « {critere.get('nom')} » is not one of this agent's tools.")
    if genre in ("texte_present", "texte_absent") and len(normaliser(critere.get("texte"))) < LONGUEUR_MIN_D_UN_TEXTE:
        return _r("test", "The searched text is too short to mean anything.")
    return _r("agent", "The test ran and its criterion makes sense: the agent answered otherwise.")


def _r(cause: str, raison: str) -> dict[str, Any]:
    return {"cause": cause, "raison": raison, "accord_requis": True}
