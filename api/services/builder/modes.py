"""[.mark] Builder partie 3, N1 (sous-lots 2 et 3) : les quatre modes du chat et la demande ponctuelle (05, « Les permissions du builder »).

Vérifié CÔTÉ SERVEUR à chaque action, dans l'unique chemin d'exécution (``registre.executer`` appelle ``decider``) :

1. **Le rôle borne tout** : la famille de l'action exige une permission (``familles_actions.PERMISSION_DE_LA_FAMILLE``) ; une personne qui
   ne l'a pas ne la fait pas faire au builder, quel que soit le mode (refus ``droits``, sans carte).
2. **Le mode du chat** (``conversation["mode"]``, « demander » par défaut, vaut pour CE chat seulement) dit ce qui passe sans demander :

   =============  ======================================================================================================================
   ``demander``   lire ; modifier le brouillon de l'agent ouvert
   ``agent``      « Tout permettre sur cet agent » : brouillon, réglages, publication et groupe, sur l'agent ouvert (et son groupe)
   ``tout``       « Tout permettre » : tout (les trois gardes tiennent ailleurs : secrets, plafond du mois, journal)
   ``plan``       lecture seule : le builder cherche et rédige un plan ; toute écriture est refusée (code ``mode_plan``)
   =============  ======================================================================================================================

3. **La demande ponctuelle** : ce qui ne passe pas reçoit une carte dans le fil (``autorisation_requise``) et le tour s'arrête. Rien n'est
   exécuté sans clic. « Autoriser une fois » vaut pour CET appel (mêmes arguments) ; « Autoriser pour ce chat » pour ce type d'action sur
   cet objet, jusqu'à la fin du chat (rangé dans la conversation : un autre chat ne le voit pas) ; « Refuser » transmet la raison au builder.

Hors chat (``conversation`` absente) à l'écran, c'est la personne qui agit elle-même par une route : sa permission y est déjà vérifiée.
La porte Claude Code n'a pas de mode de chat : elle garde ses actions d'aujourd'hui et n'a ni la publication, ni l'irréversible, ni les
appels réels.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from loguru import logger

from api.db import db_client
from api.services.builder.actions import familles_actions

MODES: tuple[str, ...] = ("demander", "agent", "tout", "plan")
MODE_PAR_DEFAUT = "demander"
DECISIONS: tuple[str, ...] = ("une_fois", "pour_ce_chat", "refuser")

# Ce qui passe sans demander, par mode (05, tableau des modes). ``agent`` : seulement sur l'agent ouvert (et son groupe).
SANS_DEMANDER: dict[str, frozenset[str]] = {
    "demander": frozenset({"lecture", "brouillon"}),
    "agent": frozenset({"lecture", "brouillon", "reglages", "publication", "autre_agent"}),
    "tout": frozenset(familles_actions.FAMILLES),
    "plan": frozenset({"lecture"}),
}
# Les familles qui exigent que la cible soit l'agent ouvert pour passer sans demander (sinon : carte).
SUR_L_AGENT_OUVERT: frozenset[str] = frozenset({"brouillon", "reglages", "publication", "autre_agent"})
# Fermées à la porte Claude Code tant qu'elle n'a pas de mode de chat (aucune de ses actions d'aujourd'hui n'y est).
HORS_PORTE_MCP: frozenset[str] = frozenset({"publication", "appels_reels", "irreversible"})
# RV (point 5) : les rejeux qui dépensent la clé de l'organisation (suite de tests, attaques) se décident à l'écran, avec une carte d'accord ; jamais
# par Claude Code, où la porte n'a pas de carte. Le reste de la famille « dépense » (``test_demarrer``, ``test_tour``, ``test_finir``) est l'appelant
# simulé joué PAR Claude Code (instructions du serveur MCP) : il reste à la porte.
DEPENSES_HORS_PORTE_MCP: frozenset[str] = frozenset({"tests_rejouer", "attaques_lancer", "attaques_rejouer"})
# RV (point 4) : ces actions portent sur un objet de l'ORGANISATION (un outil, un nouvel agent), jamais sur « l'agent ouvert » : hors de
# « Tout permettre », elles demandent une carte même si une famille passe sur l'agent ouvert.
OBJETS_D_ORGANISATION: frozenset[str] = frozenset({"create_workflow", "create_tool", "outil_modifier"})

DEMANDES_MAX = 200
ARGUMENTS_MONTRES_MAX = 1500
CODE_DEMANDE = "autorisation_requise"


def mode_de(conversation: dict[str, Any] | None) -> str:
    mode = (conversation or {}).get("mode")
    return mode if mode in MODES else MODE_PAR_DEFAUT


async def poser(user, fil, mode: str) -> str:
    """Pose le mode du chat ``fil`` (valeur déjà validée par la route) : rangé dans la conversation, noté dans le fil, « agent » et
    « tout » journalisés (qui, quel chat, quand). Rend le mode d'avant. Un seul chemin pour la route du mode et l'ouverture d'un chat."""
    from api.services.builder import fil as service_fil
    from api.services.equipe_mark.acces import journaliser

    historique = dict(fil.historique or {})
    avant = historique.get("mode") or MODE_PAR_DEFAUT
    historique["mode"] = mode
    await db_client.modifier_fil(user.selected_organization_id, fil.id, historique=historique)
    await service_fil.noter(fil.id, {"type": "mode", "mode": mode, "avant": avant})
    if mode in ("agent", "tout") and avant != mode:
        await journaliser(user, "builder.mode", user.selected_organization_id, {"fil": fil.id, "mode": mode, "agent": fil.workflow_id})
    return avant


def consigne(conversation: dict[str, Any] | None) -> str:
    """La ligne que le cerveau lit avant le message du jour : son mode, et ce qu'il fait d'une carte."""
    mode = mode_de(conversation)
    if mode == "plan":
        return (
            "## Mode du chat : Plan\nLecture seule. Cherche, lis, puis rédige un plan avec plan_mettre_a_jour et attends l'accord de la "
            "personne : aucune écriture n'est permise dans ce mode."
        )
    lignes = {
        "demander": "Demander : tu lis et tu modifies le brouillon de l'agent ouvert ; le reste demande l'accord de la personne.",
        "agent": "Tout permettre sur cet agent : brouillon, réglages, groupe et publication de l'agent ouvert passent ; le reste demande.",
        "tout": "Tout permettre : tout passe, dans les limites du rôle de la personne ; les secrets, le plafond du mois et le journal tiennent.",
    }
    return (
        f"## Mode du chat : {lignes[mode]}\nQuand une action rend « {CODE_DEMANDE} », une carte attend la personne : arrête-toi, ne "
        "contourne jamais une demande par une autre action."
    )


def empreinte(nom: str, arguments: dict[str, Any] | None) -> str:
    brut = json.dumps({"nom": nom, "arguments": arguments or {}}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()[:24]


def cible_agent(arguments: dict[str, Any] | None, contexte) -> int | None:
    demande = (arguments or {}).get("workflow_id")
    return demande if isinstance(demande, int) else contexte.workflow_id


def objet_de(nom: str, arguments: dict[str, Any] | None, contexte) -> str:
    """L'objet d'une autorisation « pour ce chat » : l'agent visé, sinon l'outil, l'élément de bibliothèque ou la proposition."""
    arguments = arguments or {}
    for cle in ("outil", "identifiant"):
        if arguments.get(cle) not in (None, ""):
            return f"{cle}:{arguments[cle]}"
    if arguments.get("famille") and arguments.get("slug"):
        return f"bibliotheque:{arguments['famille']}/{arguments['slug']}"
    agent = cible_agent(arguments, contexte)
    return f"agent:{agent}" if agent is not None else "organisation"


async def permissions_de(user) -> frozenset[str]:
    """Les permissions de la personne (rôle d'équipe) ou de la clé (table unique ``equipe_mark.droits_effectifs``, clôture lot A, D21). Une
    lecture qui échoue ferme (aucune permission) : on ne prête pas de droits sur une base lente."""
    if getattr(user, "par_cle_api", False):
        from api.services.equipe_mark import droits_effectifs

        return await droits_effectifs.permissions_de(user)
    try:
        acces = await db_client.acces_du_compte(user.id)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[builder] droits illisibles ({type(erreur).__name__}) : aucune écriture permise")
        return frozenset()
    return frozenset(acces.permissions) if acces is not None else frozenset()


async def _dans_le_groupe_de_l_agent_ouvert(contexte, cible: int | None) -> bool:
    """La cible est-elle un agent du groupe de l'agent ouvert ? Dans le doute : non (la carte demande)."""
    if cible is None or contexte.workflow_id is None:
        return False
    try:
        from api.services.groupe import groupe as service_groupe

        lu = await service_groupe.lire_groupe(contexte.workflow_id, contexte.organisation_id)
    except Exception:  # noqa: BLE001
        return False
    if not lu or lu.get("principal") is None:
        return False
    ids = {lu["principal"].get("id")} | {m.get("id") for m in lu.get("specialises") or []}
    return cible in ids


async def _passe_par_le_mode(mode: str, famille: str, arguments: dict[str, Any], contexte, nom: str = "") -> bool:
    if famille not in SANS_DEMANDER[mode]:
        return False
    if mode == "tout" or famille not in SUR_L_AGENT_OUVERT:
        return True
    if nom in OBJETS_D_ORGANISATION:
        return False
    cible = cible_agent(arguments, contexte)
    if cible == contexte.workflow_id:
        return True
    return mode == "agent" and await _dans_le_groupe_de_l_agent_ouvert(contexte, cible)


def _prendre_la_depense(conversation: dict[str, Any]) -> dict[str, Any] | None:
    """Une dépense annoncée (``depense_annoncer``) et accordée, pas encore utilisée, vaut autorisation pour la famille « dépense » : un accord ne
    vaut qu'une fois, et seulement si ni le mode ni une autorisation existante ne couvre déjà l'action. Marque utilisé le premier accord de dépense encore libre (un seul point, ici) et le rend (pour pouvoir le restituer)."""
    for d in (conversation.get("depenses") or {}).values():
        if d.get("statut") == "accordee" and not d.get("utilisee"):
            d["utilisee"] = True
            return d
    return None


def rendre_les_accords(contexte) -> None:
    """RV2 (M-2) : l'action est refusée APRÈS ``decider`` (sauvegarde, étiquettes, journal) : les accords pris pour elle ne sont pas perdus."""
    for accord in contexte.accords_pris:
        accord["utilisee"] = False
    contexte.accords_pris = []


def _autorisation_existante(conversation: dict[str, Any], nom: str, arguments: dict[str, Any], contexte) -> str | None:
    """L'autorisation donnée qui couvre cet appel (« pour_ce_chat » : ce type d'action sur cet objet ; « une_fois » : cet appel exact, une
    seule fois), ou ``None``. Une autorisation « une fois » est consommée ici."""
    demandes = conversation.get("autorisations") or {}
    objet = objet_de(nom, arguments, contexte)
    trace = empreinte(nom, arguments)
    for identifiant, d in demandes.items():
        if d.get("nom") != nom:
            continue
        if d.get("statut") == "pour_ce_chat" and d.get("objet") == objet:
            return "pour_ce_chat"
        if d.get("statut") == "une_fois" and not d.get("utilisee") and d.get("empreinte") == trace:
            d["utilisee"] = True
            contexte.accords_pris.append(d)  # RV2 (M-2) : rendue si l'action est refusée avant d'être jouée
            return "une_fois"
    return None


def _montrer(arguments: dict[str, Any]) -> dict[str, Any]:
    """Les arguments tels que la carte les montre (« après ») : bornés, jamais de valeur qui ressemble à un secret."""
    from api.services.builder.reglages_agent import masquer_les_cles

    montre = masquer_les_cles(arguments or {})
    brut = json.dumps(montre, ensure_ascii=False, default=str)
    if len(brut) > ARGUMENTS_MONTRES_MAX:
        return {"apercu": brut[:ARGUMENTS_MONTRES_MAX] + "…"}
    return montre


def _demander(conversation: dict[str, Any], action, famille: str, arguments: dict[str, Any], contexte) -> dict[str, Any]:
    demandes = conversation.setdefault("autorisations", {})
    if len(demandes) >= DEMANDES_MAX:
        return {"ok": False, "code": "demandes", "erreur": "Too many permission requests in this chat: start a new chat."}
    identifiant = f"a{len(demandes) + 1}"
    objet = objet_de(action.nom, arguments, contexte)
    demandes[identifiant] = {
        "nom": action.nom,
        "famille": famille,
        "objet": objet,
        "empreinte": empreinte(action.nom, arguments),
        "statut": "attente",
        "utilisee": False,
    }
    return {
        "ok": False,
        "code": CODE_DEMANDE,
        "demande": identifiant,
        "attente": "A card asks the person. Stop here: nothing is done before their answer.",
        "carte": {
            "type": "autorisation",
            "id": identifiant,
            "action": action.nom,
            "description": action.description,
            "famille": famille,
            "objet": objet,
            "apres": _montrer(arguments),
            "definitif": famille == "irreversible",
            "depense": famille == "depense",
            "statut": "attente",
        },
    }


async def decider(action, arguments: dict[str, Any], contexte) -> dict[str, Any] | None:
    """``None`` : l'action passe. Sinon le résultat à rendre au cerveau (refus, ou demande avec sa carte). Ne lève jamais."""
    from api.services.builder.actions.registre import PORTE_MCP

    famille = action.famille or "irreversible"
    contexte.autorisation = None
    contexte.accords_pris = []
    if contexte.porte == PORTE_MCP:
        # Décision d'Evan du 09/11 : publier, rejouer les tests payants et lancer des appels réels passent par MCP si la clé a l'interrupteur allumé
        # (ET le rôle qui porte la permission, vérifié avant, ET le créateur : ``registre._refus_de_la_cle_mcp``). Supprimer reste à l'écran.
        from api.services.equipe_mark import droits_mcp

        geste = droits_mcp.geste_de_l_action(action.nom, famille)
        if geste is not None and getattr(contexte.user, "cle_api_role_id", None) is not None:
            if geste not in getattr(contexte.user, "cle_api_mcp", frozenset()):
                return droits_mcp.refus_interrupteur_eteint(geste)
            if famille == "depense":
                contexte.accord_donne = True  # l'interrupteur tient lieu de carte d'accord ; les plafonds de dépense de l'action jouent comme à l'écran
            return None
        if famille in HORS_PORTE_MCP or action.nom in DEPENSES_HORS_PORTE_MCP:
            return {
                "ok": False,
                "code": "porte_mcp",
                "erreur": f"« {action.nom} » is done from the builder chat of the screen, with the person's permission, not through Claude Code.",
            }
        return None
    conversation = contexte.conversation
    if conversation is None:
        return None  # la personne agit elle-même par une route de l'écran : sa permission y est vérifiée
    permission = familles_actions.permission_de(action.nom, famille)
    if permission is not None:
        if contexte.permissions is None:
            contexte.permissions = await permissions_de(contexte.user)
        if permission not in contexte.permissions:
            return {
                "ok": False,
                "code": "droits",
                "erreur": f"The person using the builder does not have the permission « {permission} »: the builder never does more than they can. Tell them.",
            }
    mode = mode_de(conversation)
    if famille == "lecture":
        return None
    if mode == "plan":
        return {
            "ok": False,
            "code": "mode_plan",
            "erreur": "Plan mode: nothing is changed. Write the plan with plan_mettre_a_jour and wait for the person's agreement.",
        }
    # RV2 (M-1) : le mode ou une autorisation existante couvre l'action ? Alors l'accord de dépense n'est PAS consommé.
    autorisation = "mode" if await _passe_par_le_mode(mode, famille, arguments, contexte, action.nom) else _autorisation_existante(conversation, action.nom, arguments, contexte)
    if autorisation:
        contexte.autorisation = autorisation  # N1 (sous-lot 4) : le journal dit comment la permission a été donnée
        if famille == "depense":
            contexte.accord_donne = True  # l'accord de dépense est donné par le mode ou la carte (``consommer_un_accord``)
        return None
    if famille == "depense" and (accord := _prendre_la_depense(conversation)) is not None:
        contexte.accords_pris.append(accord)
        contexte.autorisation = "depense"
        contexte.accord_donne = True  # l'accord est déjà consommé : ``consommer_un_accord`` n'en prend pas un second
        return None
    return _demander(conversation, action, famille, arguments, contexte)
