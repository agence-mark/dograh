"""[.mark] The tool type ``integration`` inside the engine's dispatcher (plan connecteurs-agent step 3).

Called from ``pipecat_engine_custom_tools.py`` (two branches, like the ``mcp`` type): the schema
the model sees (the action's declared parameters, never the organization) and the handler.

The handler (D6 to D8, D17, D18):
- the organization is the ENGINE's;
- the waiting phrase is said while the action runs;
- the action runs within its deadline (the anticipated result is taken if the parameters match);
- ok → the useful result to the model; deadline or error → the fallback phrase is SAID (never
  a blank), the model is told the request was passed on, and an action that writes is put aside
  for the after-call;
- every run is stamped in the record (``connecteurs``).

R1: never swallowed in silence; a failure is logged, stamped and spoken.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema

from api.services.integrations.connectors import anticipation
from api.services.integrations.connectors.catalogue import trouver
from api.services.integrations.connectors.execution import (
    PHRASE_REPLI_DEFAUT,
    ActionInconnue,
    arguments_permis,
    estampiller,
    executer,
    mettre_de_cote,
)

TYPES = {"string": "string", "number": "number", "boolean": "boolean"}


def config_de(tool: Any) -> dict:
    return (
        ((getattr(tool, "definition", None) or {}).get("config") or {}) if tool else {}
    )


def _propriete(p, contexte: dict | None) -> dict:
    propriete = {"type": TYPES.get(p.type, "string"), "description": p.description}
    # l-agent-collegue (C7): a closed list, fixed or built at pick-up in the call context.
    liste = list(p.choix)
    if p.liste_du_contexte:
        valeurs = (contexte or {}).get(p.liste_du_contexte)
        liste = [str(v) for v in valeurs] if isinstance(valeurs, list) else []
    if liste:
        propriete["enum"] = liste
    return propriete


def schema(
    tool: Any, nom_de_fonction: str, contexte: dict | None = None
) -> FunctionSchema | None:
    """The function the model sees: the action's description and declared parameters.
    ``contexte``: the call's context, where a closed list built at pick-up is read."""
    config = config_de(tool)
    trouve = trouver(config.get("connecteur", ""), config.get("action", ""))
    if trouve is None:
        logger.error(
            f"[.mark] Integration tool '{getattr(tool, 'name', '?')}': unknown action {config}"
        )
        return None
    _, action = trouve
    return FunctionSchema(
        name=nom_de_fonction,
        description=(getattr(tool, "description", None) or action.description),
        properties={p.nom: _propriete(p, contexte) for p in action.parametres},
        required=[p.nom for p in action.parametres if p.obligatoire],
    )


def inscrire_l_anticipation(
    engine: Any, tool: Any, nom_de_fonction: str, organization_id: int
) -> None:
    config = config_de(tool)
    if not config.get("anticipable"):
        return
    fiche = getattr(engine, "_gathered_context", None)
    if isinstance(fiche, dict):
        anticipation.pour_la_fiche(fiche).inscrire(
            nom_de_fonction, config, organization_id
        )


def connecteur_interne(tool: Any):
    """The internal connector of this tool (l-agent-collegue), or None."""
    from api.services.integrations.connectors.catalogue import connecteur

    c = connecteur(config_de(tool).get("connecteur", ""))
    return c if c is not None and c.interne else None


def creer_gestionnaire(manager: Any, tool: Any, nom_de_fonction: str):
    """The handler of one integration tool. ``manager``: the engine's custom tool manager."""
    config = config_de(tool)
    interne = connecteur_interne(tool)
    if interne is not None:
        # l-agent-collegue: an internal action is played by its own handler, never the relay.
        return interne.gestionnaire_interne(manager, tool, nom_de_fonction)

    async def gestionnaire(params) -> None:
        engine = manager._engine
        fiche = getattr(engine, "_gathered_context", None)
        organization_id = await manager.get_organization_id()
        if not organization_id:
            logger.error("[.mark] Integration tool without an organization: refused")
            await params.result_callback({"status": "error", "error": "unavailable"})
            return
        try:
            trouve = trouver(config.get("connecteur", ""), config.get("action", ""))
            if trouve is None:
                raise ActionInconnue(str(config))
            _, action = trouve
            arguments = arguments_permis(action, params.arguments)
            if config.get("phrase_attente"):
                await engine.queue_text_message(
                    config["phrase_attente"], mute_user=True
                )
            anticipee = None
            if isinstance(fiche, dict):
                a = anticipation.pour_la_fiche(fiche, creer=False)
                anticipee = a.prendre(nom_de_fonction, arguments, fiche) if a else None
            numero = (getattr(engine, "_call_context_vars", None) or {}).get(
                "caller_number"
            )
            resultat = await executer(
                organization_id, config, arguments, fiche, numero, anticipee
            )
        except Exception as erreur:  # noqa: BLE001 -- R1: stamped, spoken, never silent
            logger.error(
                f"[.mark] Integration tool '{nom_de_fonction}' failed: {erreur!r}"
            )
            resultat = None
        estampiller(
            fiche,
            {
                "outil": nom_de_fonction,
                "connecteur": config.get("connecteur"),
                "action": config.get("action"),
                "statut": resultat.statut if resultat else "erreur",
                "duree_ms": resultat.duree_ms if resultat else None,
                "message": resultat.message if resultat else "internal error",
            },
        )
        if resultat is not None and resultat.statut == "ok":
            await params.result_callback(resultat.donnees)
            return
        if (
            resultat is not None
            and resultat.statut == "erreur"
            and resultat.donnees.get("manque")
        ):
            # A missing parameter: the model asks the caller, nothing is said for it.
            await params.result_callback(
                {"status": "missing", "ask_for": resultat.donnees["manque"]}
            )
            return
        phrase = config.get("phrase_repli") or PHRASE_REPLI_DEFAUT
        await engine.queue_text_message(phrase, mute_user=True)
        trouve = trouver(config.get("connecteur", ""), config.get("action", ""))
        if trouve is not None and trouve[1].ecrit:
            mettre_de_cote(fiche, config, arguments_permis(trouve[1], params.arguments))
        await params.result_callback(
            {
                "status": "passed_on",
                "said_to_caller": phrase,
                "instruction": "The request was passed on; do not repeat this sentence, go on with the call.",
            }
        )

    return gestionnaire
