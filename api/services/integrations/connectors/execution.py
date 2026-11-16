"""[.mark] Running an action of the catalogue (plan connecteurs-agent D6 to D9, D17, D18).

- The organization is the ENGINE's (D6), passed by the caller; the model's arguments are cut
  down to the parameters the action declares (an ``organization_id`` the model sends is
  dropped, like any other undeclared key).
- Synchronous during the call (D7): a waiting phrase, a deadline (5 s by default); past it or
  on an error, the fallback phrase, and an action that WRITES is put aside for the after-call
  (``connecteurs_differes`` in the record), retried by the after-call module ``connecteurs``
  (A1, A6: no n8n). Every run is stamped (``connecteurs`` in the record): action, duration,
  outcome, anticipated or not and the time saved (D18).
- The agent receives the useful result only (D8).
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from api.services.integrations.connectors import garde, mesures, nango, typage
from api.services.integrations.connectors.catalogue import (
    Action,
    Connecteur,
    ContexteAction,
    Parametre,
    trouver,
)
from api.services.integrations.connectors.modele_commun import depuis_la_fiche

CLE_ESTAMPILLE = "connecteurs"
CLE_DIFFERES = "connecteurs_differes"
DELAI_DEFAUT_MS = 5000


class ActionInconnue(ValueError):
    pass


@dataclass
class Resultat:
    statut: str  # ok | repli | erreur
    donnees: dict[str, Any] = field(default_factory=dict)
    duree_ms: int = 0
    message: str | None = None
    type_echec: str | None = None  # lot 7 (W21) : ``slot_taken`` | ``bad_request`` | ``not_found`` | ``outage`` | ``uncertain_outcome`` ; ``None`` : pas un échec


def _reparer(parametre: Parametre, valeur: Any) -> Any:
    """Le code répare les erreurs fréquentes du modèle au lieu de les refuser : un paramètre texte reçu en liste de textes (ou de nombres) est
    joint par « , » ; un nombre reçu en texte est converti ; un booléen reçu en texte aussi. Ce qui ne se répare pas sûrement est rendu tel quel."""
    if parametre.type == "string":
        if isinstance(valeur, (list, tuple)):
            morceaux = [str(v).strip() for v in valeur if isinstance(v, (str, int, float)) and not isinstance(v, bool) and str(v).strip()]
            return ", ".join(morceaux) if len(morceaux) == len(valeur) else valeur
        if isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
            return str(valeur)
    elif parametre.type == "number" and isinstance(valeur, str):
        try:
            nombre = float(valeur.strip().replace(",", "."))
        except ValueError:
            return valeur
        return int(nombre) if nombre.is_integer() else nombre
    elif parametre.type == "boolean" and isinstance(valeur, str):
        dit = valeur.strip().casefold()
        return True if dit in ("true", "vrai", "oui") else False if dit in ("false", "faux", "non") else valeur
    return valeur


def arguments_permis(
    action: Action, arguments: dict[str, Any] | None
) -> dict[str, Any]:
    """Only the declared parameters, never anything else the model sends (D6), with the frequent shape mistakes repaired (``_reparer``)."""
    declares = {p.nom: p for p in action.parametres}
    reparees = {k: _reparer(declares[k], v) for k, v in (arguments or {}).items() if k in declares}
    return {k: v for k, v in reparees.items() if v not in (None, "", [])}


def manquants(action: Action, arguments: dict[str, Any]) -> list[str]:
    return [
        p.nom for p in action.parametres if p.obligatoire and p.nom not in arguments
    ]


def contexte_de(
    action: Action,
    reglages: dict | None,
    fiche: dict | None,
    numero: str | None = None,
    *,
    organization_id: int | None = None,
    appel: dict | None = None,
    run_id: int | None = None,
    complements: dict | None = None,
    compte: str | None = None,
    configurations: dict | None = None,
) -> ContexteAction:
    extraites = (
        (fiche or {}).get("extracted_variables")
        if isinstance((fiche or {}).get("extracted_variables"), dict)
        else (fiche or {})
    )
    if complements:
        # Lot D d'agent-leger-greffier : les valeurs sûres des traces, pour CETTE action
        # seulement ; la fiche n'est pas touchée (le greffier l'écrit, avec ses contrôles).
        extraites = {**(extraites or {}), **complements}
    return ContexteAction(
        reglages={**action.reglages_par_defaut, **(reglages or {})},
        modele=depuis_la_fiche(extraites or {}, None, numero),
        organization_id=organization_id,
        appel=dict(appel or {}),
        run_id=run_id,
        fiche=fiche if isinstance(fiche, dict) else None,
        compte=compte or None,
        configurations=dict(configurations) if isinstance(configurations, dict) else None,
    )


async def appeler(
    organization_id: int,
    connecteur: Connecteur,
    action: Action,
    arguments: dict,
    ctx: ContexteAction,
    delai_s: float,
) -> dict:
    """One action, through the relay of THIS organization's connection. Raises on failure.

    l-agent-collegue (L5): an internal connector's action is computed in the fork
    (``executer_interne``), never sent to the relay; the organization is the engine's."""
    if connecteur.interne:
        if connecteur.executer_interne is None:
            raise RuntimeError("An internal action never goes through the relay.")
        if ctx.organization_id is None:
            ctx = dataclasses.replace(ctx, organization_id=organization_id)
        return await connecteur.executer_interne(action, arguments, ctx, delai_s)
    requetes = action.preparer(arguments, ctx)
    requetes = requetes if isinstance(requetes, list) else [requetes]
    reponse: Any = None
    for requete in requetes:
        reponse = await nango.relayer(
            organization_id,
            connecteur.integration,
            requete,
            delai=delai_s,
            base_url=connecteur.base_url,
            compte=ctx.compte,
        )
    if action.suite is not None:
        reponse = await action.suite(reponse, arguments, ctx)
    return action.resultat(reponse, arguments, ctx)


async def executer(
    organization_id: int,
    config: dict,
    arguments: dict | None,
    fiche: dict | None = None,
    numero: str | None = None,
    anticipee: asyncio.Future | None = None,
    appel: dict | None = None,
    run_id: int | None = None,
    complements: dict | None = None,
    configurations: dict | None = None,
) -> Resultat:
    """Run the tool's action within its deadline. Never raises: an error is a fallback."""
    trouve = trouver(config.get("connecteur", ""), config.get("action", ""))
    if trouve is None:
        raise ActionInconnue(
            f"Unknown action « {config.get('connecteur')}.{config.get('action')} »."
        )
    connecteur, action = trouve
    args = arguments_permis(action, arguments)
    # Lot 24 : les arguments validés par schéma (éteint par défaut) : jamais une erreur brute, l'outil demande à reformuler.
    if garde.allumee(configurations, garde.CLE_ARGUMENTS):
        invalides = garde.arguments_invalides(action, args)
        if invalides:
            garde.tracer("argument invalide", f"{connecteur.nom}.{action.nom}", ", ".join(invalides))
            return Resultat("erreur", {"manque": invalides}, message=f"Ask the caller to say again: {', '.join(invalides)}.")
    absents = manquants(action, args)
    if absents:
        return Resultat(
            "erreur",
            {"manque": absents},
            message=f"Ask the caller for: {', '.join(absents)}.",
        )
    # Lot 24 : le même appel qui a échoué deux fois de suite n'est plus lancé (éteint par défaut).
    cle_d_appel = garde.cle_de_l_appel(connecteur.nom, action.nom, args)
    if garde.allumee(configurations, garde.CLE_ECHEC_REPETE) and garde.echecs_de_suite(fiche, cle_d_appel) >= garde.ECHECS_PERMIS:
        garde.tracer("échec répété", f"{connecteur.nom}.{action.nom}")
        return Resultat("ok", garde.retour_d_echec_repete(None), 0)
    delai_s = max(
        0.5, min(float(config.get("delai_ms") or DELAI_DEFAUT_MS), 15000) / 1000
    )
    ctx = contexte_de(
        action,
        config.get("reglages"),
        fiche,
        numero,
        organization_id=organization_id,
        appel=appel,
        run_id=run_id,
        complements=complements,
        compte=config.get("compte"),
        configurations=configurations,
    )
    async def _jouer() -> Resultat:
        debut = time.monotonic()
        try:
            if anticipee is not None:
                donnees = await asyncio.wait_for(asyncio.shield(anticipee), timeout=delai_s)
            else:
                donnees = await asyncio.wait_for(
                    appeler(organization_id, connecteur, action, args, ctx, delai_s),
                    timeout=delai_s,
                )
            resultat = Resultat("ok", donnees, int((time.monotonic() - debut) * 1000))
            noter_au_hub(fiche, action, donnees, args, ctx)
            return resultat
        except (
            asyncio.TimeoutError,
            nango.NangoIndisponible,
            nango.ConnexionAbsente,
        ) as erreur:
            message = (
                "deadline passed"
                if isinstance(erreur, asyncio.TimeoutError)
                else str(erreur)
            )
        except Exception as erreur:  # noqa: BLE001 -- R1: logged, never swallowed in silence
            logger.error(
                f"[.mark] Connector action {connecteur.nom}.{action.nom} failed: {erreur!r}"
            )
            message = f"{type(erreur).__name__}"
        return Resultat("repli", {}, int((time.monotonic() - debut) * 1000), message)

    # Lot 24 : les écritures dans un même objet passent l'une après l'autre (éteint par défaut) ; l'échec répété est compté.
    async with garde.en_file(configurations, fiche, action):
        resultat = await _jouer()
        # Lot 7 (W21) : l'échec est typé ; UNE nouvelle tentative, seulement sur une lecture en panne, et seulement si le réglage est allumé (éteint par défaut).
        resultat.type_echec = typage.type_de_l_echec(resultat.statut, resultat.donnees, resultat.message, action.ecrit)
        if garde.allumee(configurations, garde.CLE_NOUVELLE_TENTATIVE) and typage.peut_rejouer(action.ecrit, resultat.type_echec):
            garde.tracer("nouvelle tentative", f"{connecteur.nom}.{action.nom}")
            resultat = await _jouer()
            resultat.type_echec = typage.type_de_l_echec(resultat.statut, resultat.donnees, resultat.message, action.ecrit)
    # Lot 7 (W13, W21) : ce que l'outil a mesuré (le type de l'échec, un délai dépassé).
    nom_complet = f"{connecteur.nom}.{action.nom}"
    if resultat.type_echec:
        mesures.ecrire(fiche, "outil.echec", nom_complet, resultat.type_echec)
    if resultat.message == "deadline passed":
        mesures.ecrire(fiche, "outil.delai_depasse", nom_complet)
    if garde.allumee(configurations, garde.CLE_ECHEC_REPETE):
        garde.noter_le_resultat(fiche, cle_d_appel, echec=garde.est_un_echec(resultat.statut, resultat.donnees))
    return resultat


def estampiller(fiche: dict | None, entree: dict) -> None:
    if isinstance(fiche, dict):
        fiche.setdefault(CLE_ESTAMPILLE, []).append(entree)


def mettre_de_cote(fiche: dict | None, config: dict, arguments: dict) -> None:
    """A writing action that fell back: retried after the call (module ``connecteurs``)."""
    if isinstance(fiche, dict):
        entree = {
            "connecteur": config.get("connecteur"),
            "action": config.get("action"),
            "reglages": config.get("reglages") or {},
            "arguments": arguments,
        }
        if config.get("compte"):  # F3 (E77): the account the tool keeps follows the retry
            entree["compte"] = config["compte"]
        fiche.setdefault(CLE_DIFFERES, []).append(entree)


CLE_HUB = "hub_rendez_vous"


def noter_au_hub(
    fiche: dict | None, action: Action, donnees: dict, arguments: dict, ctx: ContexteAction
) -> None:
    """l-agent-collegue (H6): what the action leaves for the hub, written after the call.
    Never raises: a note lost is logged, the call goes on."""
    if action.au_hub is None or not isinstance(fiche, dict):
        return
    try:
        entree = action.au_hub(donnees, arguments, ctx)
    except Exception as erreur:  # noqa: BLE001 -- R1: logged
        logger.error(f"[.mark] Hub note of {action.nom} not made: {erreur!r}")
        return
    if isinstance(entree, dict):
        fiche.setdefault(CLE_HUB, []).append(entree)
