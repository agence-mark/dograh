"""[.mark] U8 (F) : le corrigé d'un test, son « état final attendu » regroupé, et la règle de construction.

Un test n'est pas seulement des critères épars : il dit ce que la conversation doit LAISSER derrière elle. Le corrigé le regroupe en
un objet que l'écran montre d'un bloc, et que le code compile en critères (jugés par le code, jamais par le modèle) :

* ``issue``    : l'issue d'appel attendue (critère ``issue``) ;
* ``actions``  : les outils qui doivent avoir été appelés (un critère ``outil`` chacun) ;
* ``champs``   : les champs de la fiche et leur valeur juste (critère ``champs_justes``) ;
* ``rien_d_autre`` : vrai par défaut ; aucun outil en dehors de ``actions`` (critère ``rien_d_autre``).

Règle de construction d'un test de conversation : un scénario, un personnage, un ou deux comportements (jamais plus : on saurait
plus lequel a fait échouer), un état final (le corrigé), rejoué N × 3. ``construction`` dit ce qui manque, sans rien bloquer, sauf
les comportements en trop qui sont refusés. ⛔ Zéro vocabulaire métier : les noms d'outils et de champs viennent de l'agent.
"""

from __future__ import annotations

from typing import Any

from api.services.tests_rejouables.modele import ErreurTestRejouable

COMPORTEMENTS_MAX = 2
ACTIONS_MAX = 20


def valider(corrige: Any) -> dict[str, Any]:
    """Le corrigé propre, ou ``ErreurTestRejouable`` avec la raison."""
    if not isinstance(corrige, dict):
        raise ErreurTestRejouable("the expected end state is an object {issue, actions, champs, rien_d_autre}")
    actions = [str(a).strip() for a in corrige.get("actions") or [] if str(a).strip()]
    champs = corrige.get("champs") or {}
    if not isinstance(champs, dict):
        raise ErreurTestRejouable("expected end state: « champs » is an object (field -> value)")
    propre: dict[str, Any] = {
        "issue": str(corrige.get("issue") or "").strip()[:120] or None,
        "actions": list(dict.fromkeys(actions))[:ACTIONS_MAX],
        "champs": {str(k).strip()[:80]: str(v)[:200] for k, v in list(champs.items())[:20] if str(k).strip()},
        "rien_d_autre": corrige.get("rien_d_autre", True) is not False,
    }
    if not (propre["issue"] or propre["actions"] or propre["champs"]):
        raise ErreurTestRejouable("an expected end state names at least an outcome, an action or a field")
    return propre


def en_criteres(corrige: dict[str, Any]) -> list[dict[str, Any]]:
    """Les critères que le corrigé compile (déjà validé)."""
    criteres: list[dict[str, Any]] = []
    if corrige.get("issue"):
        criteres.append({"type": "issue", "attendue": corrige["issue"]})
    criteres += [{"type": "outil", "nom": a} for a in corrige.get("actions") or []]
    if corrige.get("champs"):
        criteres.append({"type": "champs_justes", "champs": dict(corrige["champs"])})
    if corrige.get("rien_d_autre", True):
        criteres.append({"type": "rien_d_autre", "permis": list(corrige.get("actions") or [])})
    return criteres


def fusionner(criteres: list[dict[str, Any]], corrige: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Les critères écrits à la main, puis ceux du corrigé (un critère identique n'est pas posé deux fois)."""
    if not corrige:
        return criteres
    deja = {repr(sorted(c.items(), key=lambda kv: kv[0])) for c in criteres}
    ajoutes = [c for c in en_criteres(corrige) if repr(sorted(c.items(), key=lambda kv: kv[0])) not in deja]
    return [*criteres, *ajoutes]


def comportements_valides(comportements: Any) -> list[str]:
    liste = [" ".join(str(c).split())[:200] for c in comportements or [] if str(c).strip()]
    if len(liste) > COMPORTEMENTS_MAX:
        raise ErreurTestRejouable(f"a test plays one or two behaviours at most ({COMPORTEMENTS_MAX}): more and we cannot tell which one failed")
    return liste


def construction(test: dict[str, Any]) -> dict[str, Any]:
    """Ce qui manque à un test de conversation pour suivre la règle ; un test d'une réplique n'a pas de règle de construction."""
    if not test.get("scenario"):
        return {"applicable": False, "conforme": True, "manque": []}
    scenario = test["scenario"] if isinstance(test["scenario"], dict) else {}
    manque = []
    if not str(scenario.get("but") or "").strip():
        manque.append("scenario")
    if not scenario.get("personnage"):
        manque.append("personnage")
    if not test.get("comportements"):
        manque.append("comportement")
    if not test.get("corrige"):
        manque.append("corrige")
    return {"applicable": True, "conforme": not manque, "manque": manque}
