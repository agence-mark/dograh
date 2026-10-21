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
from api.services.integrations.connectors.champs_requis import Patience, resoudre
from api.services.integrations.connectors.catalogue import trouver
from api.services.integrations.connectors.execution import (
    ActionInconnue,
    arguments_permis,
    estampiller,
    executer,
    mettre_de_cote,
)

TYPES = {"string": "string", "number": "number", "boolean": "boolean"}


async def _signaler_le_repli(engine: Any, propre: Any, nom_de_fonction: str | None = None):
    """La règle « un outil échoue » pour ce connecteur : sa phrase (celle du connecteur, s'il en a une, à
    la place des variantes), le compteur d'incidents dans l'appel, la sortie réglée. Rend le
    ``Probleme`` du diseur, ``None`` s'il n'y a pas de diseur. ⛔ Ne lève jamais."""
    try:
        from api.services.phrases.catalogue import OUTIL_ECHOUE
        from api.services.phrases.diseur import DiseurDePhrases

        diseur = getattr(engine, "phrases", None)
        if not isinstance(diseur, DiseurDePhrases):
            return None
        return await diseur.signaler_un_probleme(
            OUTIL_ECHOUE,
            outil=nom_de_fonction,
            texte=propre if isinstance(propre, str) else None,
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[phrases] échec du connecteur non signalé : {erreur!r}")
        return None


async def _dire_le_repli(engine: Any, propre: Any) -> str | None:
    """Dit la phrase « un outil échoue » et rend son texte (``None`` : rien de dit)."""
    probleme = await _signaler_le_repli(engine, propre)
    return probleme.dit if probleme is not None else None


# The key of an internal action's result that holds a sentence the code says itself.
CLE_A_DIRE = "_dire"
# ... and what it notes in the record for the after-call (record key -> one entry).
CLE_A_NOTER = "_noter"


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
            nom_de_fonction,
            config,
            organization_id,
            appel=getattr(engine, "_call_context_vars", None) or {},
            run_id=getattr(engine, "_workflow_run_id", None),
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
    if interne is not None and interne.gestionnaire_interne is not None:
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
        # Lot D d'agent-leger-greffier (D6) : la phrase de patience, seulement au-delà du seuil.
        patience = Patience(engine, config)
        patience.demarrer()
        try:
            trouve = trouver(config.get("connecteur", ""), config.get("action", ""))
            if trouve is None:
                raise ActionInconnue(str(config))
            _, action = trouve
            arguments = arguments_permis(action, params.arguments)
            # Lot D : les champs que l'action lit, cherchés avant elle (fiche, traces, greffier).
            complements, absents = await resoudre(engine, config)
            if absents:
                patience.arreter()
                estampiller(
                    fiche,
                    {
                        "outil": nom_de_fonction,
                        "connecteur": config.get("connecteur"),
                        "action": config.get("action"),
                        "statut": "champs_manquants",
                        "duree_ms": None,
                        "message": ", ".join(absents),
                    },
                )
                await params.result_callback({"status": "missing", "ask_for": absents})
                return
            anticipee = None
            if isinstance(fiche, dict):
                a = anticipation.pour_la_fiche(fiche, creer=False)
                anticipee = a.prendre(nom_de_fonction, arguments, fiche) if a else None
            appel = getattr(engine, "_call_context_vars", None) or {}
            numero = appel.get("caller_number")
            resultat = await executer(
                organization_id,
                config,
                arguments,
                fiche,
                numero,
                anticipee,
                appel=appel,
                run_id=getattr(engine, "_workflow_run_id", None),
                complements=complements,
            )
        except Exception as erreur:  # noqa: BLE001 -- R1: stamped, spoken, never silent
            logger.error(
                f"[.mark] Integration tool '{nom_de_fonction}' failed: {erreur!r}"
            )
            resultat = None
        finally:
            patience.arreter()
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
            donnees = dict(resultat.donnees)
            # l-agent-collegue (L5): an internal action may hand the code a sentence to SAY
            # (a fallback of the planner): said here, never left to the model.
            a_dire = donnees.pop(CLE_A_DIRE, None) if interne is not None else None
            notes = donnees.pop(CLE_A_NOTER, None) if interne is not None else None
            if isinstance(notes, dict) and isinstance(fiche, dict):
                # Noted when the result is DELIVERED (an anticipated result notes nothing
                # before the model takes it).
                for cle_fiche, entree in notes.items():
                    fiche.setdefault(cle_fiche, []).append(entree)
            if isinstance(a_dire, str) and a_dire.strip():
                await engine.queue_text_message(a_dire, mute_user=True)
                donnees["said_to_caller"] = a_dire
            await params.result_callback(donnees)
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
        # Fiabilite-orchestration, lot 4 bis : la règle « un connecteur échoue » (thème Phrases) ;
        # la phrase propre au connecteur, s'il en a une, est dite à la place des variantes.
        # Règle éteinte : rien n'est dit, le modèle lit l'échec et répond.
        probleme = await _signaler_le_repli(engine, config.get("phrase_repli"), nom_de_fonction)
        phrase = probleme.dit if probleme is not None else None
        trouve = trouver(config.get("connecteur", ""), config.get("action", ""))
        # An internal action is never retried after the call: its own fallback (a call-back
        # request) is decided during the call (l-agent-collegue, P8).
        if trouve is not None and trouve[1].ecrit and interne is None:
            mettre_de_cote(fiche, config, arguments_permis(trouve[1], params.arguments))
        # correctifs-apres-banc-v4 (lot 4, 4.10) : après une phrase du code, le modèle reçoit le compte
        # rendu en français (le fait, la phrase entendue, ce qui est noté, ce qui n'est plus possible) à la
        # place de la consigne anglaise d'avant ; la phrase est déjà dans l'historique.
        if probleme is not None and (phrase or probleme.issue is not None):
            from api.services.phrases.catalogue import MOTIFS, OUTIL_ECHOUE
            from api.services.phrases.compte_rendu import compte_rendu

            issue = probleme.issue
            retour: dict[str, Any] = {
                "status": "passed_on",
                "compte_rendu": compte_rendu(
                    MOTIFS[OUTIL_ECHOUE].fait_fr,
                    dit=phrase,
                    notes=probleme.notes,
                    interdits=issue.interdit if issue is not None else (),
                ),
            }
            if phrase:
                retour["said_to_caller"] = phrase
            if issue is not None and issue.prise_en_main:
                from pipecat.frames.frames import FunctionCallResultProperties

                await params.result_callback(
                    retour, properties=FunctionCallResultProperties(run_llm=False)
                )
            else:
                await params.result_callback(retour)
            return
        await params.result_callback(
            {
                "status": "passed_on",
                "instruction": "The request could not be done now and was passed on: tell the caller someone will call back to confirm, then go on with the call.",
            }
        )

    return gestionnaire
