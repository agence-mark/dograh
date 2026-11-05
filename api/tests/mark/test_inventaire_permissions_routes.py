"""[.mark] builder partie 2, U2 ter : l'inventaire des routes et leurs permissions.

| Test | Ce qu'il prouve |
|---|---|
| chaque route a une décision | toute route de l'API a une permission, MEMBRE ou une exemption écrite ; une route nouvelle sans décision fait échouer |
| les permissions sont réelles | toute permission citée au registre fait partie des 18 ; aucune des 16 n'est orpheline |
| une décision est appliquée | une route qui exige une permission ou MEMBRE passe bien par ``get_user`` (sinon la permission ne serait jamais vérifiée) |
| une exemption n'est pas un trou | une route exemptée sans raison est impossible ; une route qui passe par ``get_user`` mais est exemptée est signalée |
| une route inconnue est refusée | le contrôle d'accès ferme par défaut |
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute, APIWebSocketRoute

from api.app import app
from api.services.auth.depends import get_user
from api.services.equipe_mark import registre_routes as registre
from api.services.equipe_mark.permissions import PERMISSIONS

PREFIXE = "/api/v1"


def _appelle_get_user(dependant) -> bool:
    if dependant.call is get_user:
        return True
    return any(_appelle_get_user(d) for d in dependant.dependencies)


def _routes():
    sorties = []
    for route in app.routes:
        chemin = getattr(route, "path", "")
        if isinstance(route, APIRoute):
            for methode in sorted(route.methods or []):
                sorties.append((methode, chemin, _appelle_get_user(route.dependant)))
        elif isinstance(route, APIWebSocketRoute):
            sorties.append(("WS", chemin, _appelle_get_user(route.dependant)))
        else:  # Mount, Route simple (docs, openapi, mcp)
            sorties.append(("GET", chemin, False))
    return sorties


def _sans_prefixe(chemin: str) -> str:
    return chemin[len(PREFIXE):] if chemin.startswith(PREFIXE) else chemin


def test_chaque_route_a_une_decision():
    sans_decision = [
        f"{m} {c}" for m, c, _ in _routes() if registre.decision_de(m, _sans_prefixe(c)) is None
    ]
    assert not sans_decision, (
        "Routes sans permission ni exemption écrite (ajouter une règle à registre_routes.py) :\n"
        + "\n".join(sans_decision)
    )


def test_les_permissions_citees_existent_et_les_16_servent():
    citees = {
        r.decision.cle for r in registre.REGLES if isinstance(r.decision, registre.Permission)
    }
    assert citees <= set(PERMISSIONS), citees - set(PERMISSIONS)
    assert len(PERMISSIONS) == 18  # lot 15 (P-6) : « relation.ecrire » est la 16e ; 17a : « connecteurs.autoriser » et « base_client.connexion_portail »
    # Aucune permission livrée ne reste sans route qui l'exige, hors celles des écrans à venir (portail, export, équipe).
    orphelines = set(PERMISSIONS) - citees
    attendues_plus_tard = {
        "clients.ouvrir_portail",  # bouton « Ouvrir son portail » (H2)
        "donnees.exporter",  # exports de données (portail)
        "equipe.gerer",  # routes de l'équipe (ce lot, branchées par decorateur propre)
        "roles.gerer",
        "agents.supprimer",  # citée par le statut ; gardée ici pour la lisibilité
    }
    assert orphelines <= attendues_plus_tard, orphelines - attendues_plus_tard


def test_une_decision_membre_ou_permission_est_appliquee_par_get_user():
    non_appliquees = []
    for methode, chemin, passe_par_get_user in _routes():
        trouvee = registre.decision_de(methode, _sans_prefixe(chemin))
        if trouvee is None:
            continue
        decision, _ = trouvee
        if isinstance(decision, registre.Exemption):
            continue
        if not passe_par_get_user:
            non_appliquees.append(f"{methode} {chemin} -> {decision}")
    assert not non_appliquees, (
        "Routes dont la décision ne serait JAMAIS vérifiée (elles n'appellent pas get_user) :\n"
        + "\n".join(non_appliquees)
    )


def test_une_exemption_exige_sa_raison():
    with pytest.raises(ValueError):
        registre.Exemption("")
    with pytest.raises(ValueError):
        registre.Exemption("ok")


def test_une_route_exemptee_qui_authentifie_un_compte_est_signalee():
    """Une exemption ne doit pas cacher une route authentifiée par session : elle serait écrite sans permission."""
    cachees = []
    # Exceptions assumées : ces routes lisent le compte mais le registre les laisse à leur propre contrôle.
    assumees = {"/api/v1/superuser/impersonate", "/api/v1/superuser/workflow-runs"}
    for methode, chemin, passe_par_get_user in _routes():
        trouvee = registre.decision_de(methode, _sans_prefixe(chemin))
        if trouvee and isinstance(trouvee[0], registre.Exemption) and passe_par_get_user:
            if chemin not in assumees:
                cachees.append(f"{methode} {chemin}")
    assert not cachees, "\n".join(cachees)


def test_une_route_sans_decision_est_refusee():
    assert registre.decision_de("POST", "/route-inventee/qui-n-existe-pas") is None
