"""[.mark] Builder partie 3, N2 (sous-lot 1) : les réglages de l'ORGANISATION qui n'avaient pas d'accès du builder (audit 11 § 4).

Panne (adresses de secours), après l'appel (synthèse, mail, récapitulatif, webhook), vérification de l'appelant, planificateur,
fenêtre du run, conservation des appels. Pour chacun : une LECTURE et une écriture ``<bloc>_regler`` qui ne change QUE les sous-réglages
envoyés (fusionnés dans les réglages en place, sous-réglages imbriqués compris) : l'écran enregistre le bloc entier, le builder ne doit
jamais écraser ce qu'il n'a pas dit (audit 11 § 4, « écriture trop large »). Le geste est celui de l'écran : la fonction de la route
(mêmes contrôles, mêmes bornes), avec la personne du chat.

* Les secrets : une référence masquée (``CLE_MASQUEE``) reprend la valeur en place, jamais écrite ; une valeur de secret en clair est
  refusée par la garde des secrets avant d'arriver ici (``garde_secrets.py``).
* Annuler : l'état d'avant (le bloc entier) est rangé dans la ligne du journal et remis par la même route d'écran.
* Écran seulement (``mcp=False``), famille « entreprise » en écriture, « lecture » en lecture ; la permission de rôle est celle de la route
  (``atelier.regler`` pour la conservation des appels et la fenêtre du run).
"""

from __future__ import annotations

import copy
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from api.services.builder.actions.entreprise import _ecran, _inscrire
from api.services.builder.actions.registre import Contexte, ErreurAction
from api.services.builder.reglages_agent import CLE_MASQUEE


class _Rien(BaseModel):
    pass


def fusionner(en_place: dict[str, Any], envoye: dict[str, Any]) -> dict[str, Any]:
    """Les sous-réglages envoyés sont posés dans ceux en place ; un bloc imbriqué est fusionné, une liste remplacée. Une référence masquée
    ne remplace jamais la valeur en place."""
    sortie = copy.deepcopy(en_place)
    for cle, valeur in envoye.items():
        if valeur == CLE_MASQUEE:
            continue
        if isinstance(valeur, dict) and isinstance(sortie.get(cle), dict):
            sortie[cle] = fusionner(sortie[cle], valeur)
        else:
            sortie[cle] = copy.deepcopy(valeur)
    return sortie


@dataclass(frozen=True)
class Bloc:
    nom: str
    description: str
    modele: Callable[[], type[BaseModel]]
    lire: Callable[[Contexte], Awaitable[BaseModel]]
    ecrire: Callable[[Contexte, BaseModel], Awaitable[Any]]
    permission: str | None = None  # celle de la route, quand ce n'est pas « agents.modifier »


# --- accès à la fonction de la route, comme l'écran ---------------------------------------------------------------------------------------


async def _panne_lire(c: Contexte) -> BaseModel:
    from api.services.panne.routes import get_panne

    return (await get_panne(c.user)).reglages


async def _panne_ecrire(c: Contexte, r: BaseModel) -> Any:
    from api.services.panne.routes import put_panne

    return await put_panne(r, c.user)


async def _apres_appel_lire(c: Contexte) -> BaseModel:
    from api.routes.apres_appel import get_apres_appel

    return (await get_apres_appel(c.user)).reglages


async def _apres_appel_ecrire(c: Contexte, r: BaseModel) -> Any:
    from api.routes.apres_appel import put_apres_appel

    return await put_apres_appel(r, c.user)


async def _verification_lire(c: Contexte) -> BaseModel:
    from api.routes.verification import get_verification_appelant

    return await get_verification_appelant(c.user)


async def _verification_ecrire(c: Contexte, r: BaseModel) -> Any:
    from api.routes.verification import put_verification_appelant

    return await put_verification_appelant(r, c.user)


async def _planificateur_moteur_lire(c: Contexte) -> BaseModel:
    from api.routes.planificateur_moteur import get_planificateur_moteur

    return await get_planificateur_moteur(c.user)


async def _planificateur_moteur_ecrire(c: Contexte, r: BaseModel) -> Any:
    from api.routes.planificateur_moteur import put_planificateur_moteur

    return await put_planificateur_moteur(r, c.user)


async def _planificateur_lire(c: Contexte) -> BaseModel:
    from api.routes.base_client import get_planificateur

    return await get_planificateur(c.user)


async def _planificateur_ecrire(c: Contexte, r: BaseModel) -> Any:
    from api.routes.base_client import put_planificateur

    return await put_planificateur(r, c.user)


async def _fenetre_lire(c: Contexte) -> BaseModel:
    from api.routes.fenetre_du_run import get_reglages_fenetre_du_run

    return await get_reglages_fenetre_du_run(c.user)


async def _fenetre_ecrire(c: Contexte, r: BaseModel) -> Any:
    from api.routes.fenetre_du_run import save_reglages_fenetre_du_run

    return await save_reglages_fenetre_du_run(r, c.user)


async def _conservation_lire(c: Contexte) -> BaseModel:
    from api.routes.conservation_appels import get_conservation_des_appels

    return (await get_conservation_des_appels(c.user)).reglages


async def _conservation_ecrire(c: Contexte, r: BaseModel) -> Any:
    from api.routes.conservation_appels import put_conservation_des_appels

    return await put_conservation_des_appels(r, c.user)


def _m(chemin: str, nom: str) -> Callable[[], type[BaseModel]]:
    def charger() -> type[BaseModel]:
        import importlib

        return getattr(importlib.import_module(chemin), nom)

    return charger


BLOCS: tuple[Bloc, ...] = (
    Bloc("panne_organisation", "the outage fallback of the organisation (the addresses of the two emergency instructions)", _m("api.schemas.panne", "ReglagesPanne"), _panne_lire, _panne_ecrire),
    Bloc(
        "apres_appel_organisation",
        "what happens after a call, at the organisation (the summary's model and instruction, the mail server, the recap, the webhook; keys are chosen by reference, never typed)",
        _m("api.schemas.apres_appel", "ReglagesApresAppel"),
        _apres_appel_lire,
        _apres_appel_ecrire,
    ),
    Bloc("verification_appelant", "the verification of the caller (the software and the levels by kind of record)", _m("api.schemas.verification", "ReglagesVerification"), _verification_lire, _verification_ecrire),
    Bloc("planificateur", "the appointment planner of the client's database", _m("api.schemas.planificateur", "Planificateur"), _planificateur_lire, _planificateur_ecrire),
    Bloc(
        "planificateur_moteur",
        "the limits of the appointment planner's engine (advanced: addresses placed, timeouts, memory)",
        _m("api.schemas.planificateur", "ReglagesMoteurPlanificateur"),
        _planificateur_moteur_lire,
        _planificateur_moteur_ecrire,
    ),
    Bloc("fenetre_du_run", "the window of a run (what a person reads on the page of a call)", _m("api.schemas.fenetre_du_run", "ReglagesFenetreDuRun"), _fenetre_lire, _fenetre_ecrire, "atelier.regler"),
    Bloc("conservation_appels", "the retention of the calls (what is kept and for how long)", _m("api.schemas.conservation_appels", "ReglagesConservationAppels"), _conservation_lire, _conservation_ecrire, "atelier.regler"),
)

ACCES: dict[str, Bloc] = {b.nom: b for b in BLOCS}  # lu à chaque appel : un test remplace l'accès à la route sans refaire l'inscription
PERMISSIONS_DES_BLOCS: dict[str, str] = {f"{b.nom}_regler": b.permission for b in BLOCS if b.permission}
NOMS_LECTURE = tuple(f"{b.nom}_lire" for b in BLOCS)
NOMS_ECRITURE = tuple(f"{b.nom}_regler" for b in BLOCS)


class _Valeurs(BaseModel):
    valeurs: dict[str, Any]


def _inscrire_bloc(b0: Bloc) -> None:
    def courant() -> Bloc:
        return ACCES[b0.nom]

    async def lire(contexte: Contexte, p: _Rien) -> dict[str, Any]:
        b = courant()
        return {"ok": True, **(await b.lire(contexte)).model_dump(mode="json")}

    async def avant(contexte: Contexte, arguments: dict[str, Any]) -> dict[str, Any]:
        b = courant()
        return (await b.lire(contexte)).model_dump(mode="json")

    async def regler(contexte: Contexte, p: _Valeurs) -> dict[str, Any]:
        b = courant()
        en_place = (await b.lire(contexte)).model_dump(mode="json")
        try:
            instance = b.modele().model_validate(fusionner(en_place, p.valeurs))
        except ValidationError as erreur:
            premiere = erreur.errors()[0]
            raise ErreurAction(f"Refused by the screen's checks: {'.'.join(str(x) for x in premiere['loc'])}: {str(premiere['msg'])[:200]}", "refus_ecran") from None
        await _ecran(b.ecrire(contexte, instance))
        return {"ok": True, **instance.model_dump(mode="json")}

    async def remettre(contexte: Contexte, etat: dict[str, Any]) -> None:
        b = courant()
        await _ecran(b.ecrire(contexte, b.modele().model_validate(etat)))

    _inscrire(f"{b0.nom}_lire", f"Read {b0.description}.", _Rien, lire, ecriture=False)
    _inscrire(
        f"{b0.nom}_regler",
        f"Change {b0.description}: send ONLY the settings to change (sub-settings included); the others keep their value.",
        _Valeurs,
        regler,
        ecriture=True,
        avant=avant,
        defaire=remettre,
    )


for _bloc in BLOCS:
    _inscrire_bloc(_bloc)
