"""[.mark] Partie 3, lot 12 (SE-23, M-5 et M-6) : l'interrupteur, la dépense suivie et le budget du mois de l'appelant simulé et du juge.

Chaque rôle a son modèle, sa clé, son interrupteur (éteint par défaut) et son budget du mois (0 = aucun plafond, comme le plafond du
mois du builder de SA-1 dont il reprend le mois civil UTC, ``depense.debut_du_mois``). La dépense se range dans ``mark_depense_roles``
(une ligne par organisation, rôle et mois) à chaque tour du cerveau. Budget atteint : l'appel est REFUSÉ avant d'atteindre le
fournisseur (``BudgetDuRole``, une ``ErreurCerveau`` de code ``budget_mois``), avec une phrase qui dit le rôle, la dépense et le
budget. Un prix inconnu ne laisserait rien se compter : un budget posé exige alors le prix du modèle (table des prix).

⛔ Aucun secret ici : seulement des nombres et des noms de rôle.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from api.db import db_client
from api.services.builder.cerveau.appel import Cerveau, ErreurCerveau
from api.services.builder.depense import debut_du_mois

ROLES = ("appelant", "juge", "resume")
NOM_DU_ROLE = {"appelant": "simulated caller", "juge": "judge", "resume": "call summary"}
CODE_BUDGET = "budget_mois"


class BudgetDuRole(ErreurCerveau):
    def __init__(self, role: str, message: str, depense: float = 0.0, budget: float = 0.0):
        super().__init__(CODE_BUDGET, message)
        self.role = role
        self.depense = depense
        self.budget = budget


def mois_courant() -> date:
    return debut_du_mois().date()


async def depense_du_mois(organisation: int) -> dict[str, dict[str, Any]]:
    """Par rôle, ce qui a été dépensé ce mois-ci par CETTE organisation (zéros pour un rôle jamais joué)."""
    lue = await db_client.lire_depense_roles(organisation, mois_courant())
    return {r: lue.get(r, {"appels": 0, "jetons": 0, "cout": 0.0}) for r in ROLES}


def phrase_budget_atteint(role: str, depense: float, budget: float) -> str:
    return (
        f"The monthly budget of the {NOM_DU_ROLE[role]} is reached ({depense:.2f} of {budget:.2f}): "
        "raise it in the Labo settings > Simulated caller."
    )


async def verifier(organisation: int, role: str, budget: float, *, prix_connus: bool = True) -> None:
    """Refuse (``BudgetDuRole``) quand le budget du mois du rôle est atteint, ou quand il est posé sans prix pour compter."""
    if budget <= 0:
        return
    if not prix_connus:
        raise BudgetDuRole(
            role,
            f"The budget of the {NOM_DU_ROLE[role]} needs the model's prices: add them to the price table (Labo settings > Builder).",
            budget=budget,
        )
    depense = float((await depense_du_mois(organisation))[role]["cout"])
    if depense >= budget:
        raise BudgetDuRole(role, phrase_budget_atteint(role, depense, budget), depense, budget)


async def enregistrer(organisation: int, role: str, *, entree: int, sortie: int, prix_entree: float, prix_sortie: float) -> float:
    """Range un tour dans la dépense du mois ; rend son coût."""
    cout = round((entree * prix_entree + sortie * prix_sortie) / 1_000_000, 6)
    await db_client.ajouter_depense_role(
        organisation, role, mois_courant(), appels=1, jetons=max(entree, 0) + max(sortie, 0), cout=cout
    )
    return cout


class CerveauBudgete:
    """Enveloppe un cerveau de rôle : vérifie le budget avant chaque tour, range la dépense après chacun."""

    def __init__(self, cerveau: Cerveau, *, organisation: int, role: str, budget: float, prix_entree: float, prix_sortie: float):
        self._cerveau = cerveau
        self._organisation = organisation
        self.role = role
        self.budget = budget
        self._prix_entree = prix_entree
        self._prix_sortie = prix_sortie
        # RA-C : ce que CE cerveau a consommé depuis sa construction (un jugement = un cerveau), pour le dire sur le résultat.
        self.jetons = 0
        self.cout = 0.0

    async def tour(self, *, systeme: str, messages: list[dict[str, Any]], outils: list[dict[str, Any]]):
        await verifier(self._organisation, self.role, self.budget, prix_connus=bool(self._prix_entree or self._prix_sortie))
        async for evenement in self._cerveau.tour(systeme=systeme, messages=messages, outils=outils):
            if evenement.get("type") == "usage":
                entree, sortie = int(evenement.get("entree", 0) or 0), int(evenement.get("sortie", 0) or 0)
                cout = await enregistrer(
                    self._organisation, self.role, entree=entree, sortie=sortie, prix_entree=self._prix_entree, prix_sortie=self._prix_sortie
                )
                self.jetons += max(entree, 0) + max(sortie, 0)
                self.cout = round(self.cout + cout, 6)
            yield evenement
