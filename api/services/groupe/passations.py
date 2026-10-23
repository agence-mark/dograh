"""[.mark] Chantier agents-specialises (lot 2) : les règles d'un groupe d'agents.

Un **groupe** = un agent principal et ses agents spécialisés. Le lien est porté dans les
réglages JSON de chaque agent (``workflow_configurations``) : ``agents_specialises`` sur le
principal, ``agent_principal_id`` sur chaque spécialisé. Rien ici ne connaît un métier :
des identifiants d'agents, des noms de champs de la fiche et des phrases venues de la
configuration.

Quatre règles, toutes pures (aucun accès à la base, aucune levée) :

- **retour au principal** (A1) : une étape marquée ``retour_au_principal`` chez un agent qui a
  un ``agent_principal_id`` renvoie l'appel au principal, par le code ;
- **phrases de fin figées** (A17) : un nœud de fin qui porte ``fins`` dit la première phrase
  dont la condition sur la fiche est vraie, la dernière ligne sans condition étant le défaut ;
- **plafond de passations** (A18) : au plus ``passations_max_par_appel`` passations réussies
  par appel (défaut 6), jamais vers soi-même, jamais de renvoi immédiat vers le spécialisé
  qui vient de rendre la main pour la même raison ;
- **trace** ``passations`` dans la fiche de l'appel : de, vers, raison, refusée ou non.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from loguru import logger

CLE_AGENT_PRINCIPAL = "agent_principal_id"
CLE_AGENTS_SPECIALISES = "agents_specialises"
CLE_PLAFOND = "passations_max_par_appel"
PLAFOND_DEFAUT = 6
TRACE_PASSATIONS = "passations"
RAISON_RETOUR = "retour"

# Le marqueur d'étape et la liste des fins (données des nœuds, lot 2 ; écran au lot 12).
MARQUEUR_RETOUR = "retour_au_principal"
CLE_FINS = "fins"
# Lot 2 d'orchestrateur-trois-cerveaux (D1) : l'étape de l'ACCUEIL où le code ramène l'appel quand
# un collègue rend la main. Un marqueur distinct de ``retour_au_principal`` : celui-ci renvoie
# l'appel AU principal (côté collègue), celui-là reçoit l'appel (côté accueil).
MARQUEUR_ETAPE_DE_RETOUR = "etape_de_retour"
# Ce que porte le prompt (et la condition) d'une étape posée par le code : jamais un prompt
# rédigé seul (Evan, 15/10). Tant qu'une étape de retour le porte encore, elle n'est pas choisie.
A_REDIGER = "À rédiger avec Evan."

# A18 : la ligne générique donnée à l'agent quand le plafond est atteint (sans mot de métier).
LIGNE_PLAFOND = (
    "Tu ne passes plus la main dans cet appel : tu prends la demande toi-même."
)
MESSAGE_REFUS = {
    "soi_meme": "Tu es déjà cet agent : continue toi-même.",
    "meme_agent": (
        "Cet agent vient de traiter cette demande et t'a rendu la main : "
        "tu prends la suite toi-même."
    ),
    "plafond": LIGNE_PLAFOND,
    "hors_groupe": (
        "Cet agent ne fait pas partie de ton groupe : la passation est impossible. "
        "Continue toi-même."
    ),
}


def _entier(valeur: Any) -> int | None:
    if isinstance(valeur, bool):
        return None
    if isinstance(valeur, int):
        return valeur
    if isinstance(valeur, str) and valeur.strip().isdigit():
        return int(valeur.strip())
    return None


def agent_principal_de(reglages: Mapping[str, Any] | None) -> int | None:
    """L'identifiant du principal d'un spécialisé, ``None`` pour un agent seul."""
    try:
        return _entier((reglages or {}).get(CLE_AGENT_PRINCIPAL))
    except Exception:  # noqa: BLE001
        return None


def plafond_de(reglages_appel: Mapping[str, Any] | None) -> int:
    """Le plafond de passations réglé sur le principal (défaut 6, jamais négatif)."""
    try:
        valeur = _entier((reglages_appel or {}).get(CLE_PLAFOND))
        return PLAFOND_DEFAUT if valeur is None else max(0, valeur)
    except Exception:  # noqa: BLE001
        return PLAFOND_DEFAUT


def passations_de(gathered: Mapping[str, Any] | None) -> list[dict]:
    try:
        trace = (gathered or {}).get(TRACE_PASSATIONS) or []
        return [e for e in trace if isinstance(e, dict)]
    except Exception:  # noqa: BLE001
        return []


def passations_reussies(gathered: Mapping[str, Any] | None) -> int:
    """Les passations parties et abouties (les refus et les échecs ne comptent pas)."""
    return sum(
        1
        for e in passations_de(gathered)
        if not e.get("refusee") and e.get("issue", "completed") == "completed"
    )


def est_un_groupe(reglages_appel: Mapping[str, Any] | None) -> bool:
    """L'appel est-il porté par le principal d'un groupe ? Un agent seul garde le
    comportement de l'amont (passations sans plafond)."""
    try:
        r = reglages_appel or {}
        return CLE_AGENTS_SPECIALISES in r or CLE_PLAFOND in r
    except Exception:  # noqa: BLE001
        return False


def plafond_atteint(
    gathered: Mapping[str, Any] | None, reglages_appel: Mapping[str, Any] | None
) -> bool:
    """Vrai seulement dans un groupe qui a déjà passé la main au moins une fois."""
    if not est_un_groupe(reglages_appel):
        return False
    faites = passations_reussies(gathered)
    return faites > 0 and faites >= plafond_de(reglages_appel)


def hors_du_groupe(reglages_source: Mapping[str, Any] | None, vers: int | None) -> bool:
    """Garde-fou du 16/10 (repère du banc branché sur les spécialisés d'un autre accueil) : un
    principal ne passe la main qu'aux spécialisés de SA liste ``agents_specialises``. Un agent
    sans liste (agent seul, spécialisé) n'est pas concerné. ⛔ Ne lève jamais (doute = permis)."""
    try:
        r = reglages_source or {}
        if CLE_AGENTS_SPECIALISES not in r or vers is None:
            return False
        liste = r.get(CLE_AGENTS_SPECIALISES) or []
        ids = {_entier(i) for i in (liste if isinstance(liste, (list, tuple)) else [])}
        return vers not in ids
    except Exception:  # noqa: BLE001
        return False


def refus_de_passation(
    gathered: Mapping[str, Any] | None,
    reglages_appel: Mapping[str, Any] | None,
    *,
    de: int | None,
    vers: int | None,
    raison: str | None,
    reglages_source: Mapping[str, Any] | None = None,
) -> str | None:
    """Pourquoi une passation demandée est refusée (``None`` : elle peut partir).

    ``soi_meme`` : la cible est l'agent qui parle. ``plafond`` : le plafond de l'appel est
    atteint (dans un groupe seulement). ``meme_agent`` : la cible est le spécialisé qui vient de rendre la main, et la
    passation qui l'avait appelé portait la même raison. ⛔ Ne lève jamais (refus = None)."""
    try:
        if de is not None and vers is not None and de == vers:
            return "soi_meme"
        if hors_du_groupe(reglages_source, vers):
            return "hors_groupe"
        if est_un_groupe(reglages_appel) and passations_reussies(
            gathered
        ) >= plafond_de(reglages_appel):
            return "plafond"
        faites = [
            e
            for e in passations_de(gathered)
            if not e.get("refusee") and e.get("issue", "completed") == "completed"
        ]
        if len(faites) >= 2:
            dernier, avant = faites[-1], faites[-2]
            if (
                dernier.get("raison") == RAISON_RETOUR
                and dernier.get("de") == vers
                and avant.get("vers") == vers
                and avant.get("raison") == raison
            ):
                return "meme_agent"
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[groupe] règle de passation illisible : {e!r}")
        return None


def tracer_passation(gathered: dict, **entree: Any) -> None:
    """Une ligne de la trace ``passations``. ⛔ Ne lève jamais."""
    try:
        gathered.setdefault(TRACE_PASSATIONS, []).append(
            {k: v for k, v in entree.items() if v is not None}
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[groupe] trace de passation non écrite : {e!r}")


def est_une_etape_de_retour(noeud: Any) -> bool:
    try:
        return bool(getattr(getattr(noeud, "data", None), MARQUEUR_RETOUR, False))
    except Exception:  # noqa: BLE001
        return False


def est_une_etape_de_retour_de_l_accueil(noeud: Any) -> bool:
    """L'étape où l'accueil reçoit l'appel quand un collègue rend la main (D1). ⛔ Ne lève jamais."""
    try:
        return bool(getattr(getattr(noeud, "data", None), MARQUEUR_ETAPE_DE_RETOUR, False))
    except Exception:  # noqa: BLE001
        return False


def est_a_rediger(texte: Any) -> bool:
    """Le texte est encore celui que le code a posé en attendant celui d'Evan (vide compris). Les blocs
    que le code ajoute lui-même à l'enregistrement (la carte du parcours, « Tu es ici ») ne comptent pas
    comme du texte rédigé."""
    if not isinstance(texte, str):
        return True
    from api.services.workflow.schema_du_parcours import retirer

    propre = (retirer(texte) or "").strip()
    return not propre or propre == A_REDIGER


def _texte_en_attente(texte: Any) -> bool:
    """Le texte est exactement celui que le code a posé (``A_REDIGER``), blocs du code retirés. ⛔ Un
    texte vide n'en est pas un ici : une sortie sans condition d'un agent existant reste offerte."""
    if not isinstance(texte, str):
        return False
    from api.services.workflow.schema_du_parcours import retirer

    return (retirer(texte) or "").strip() == A_REDIGER


def sortie_en_attente(condition: Any, cible: Any) -> bool:
    """Relecture du lot 6 d'orchestrateur-trois-cerveaux : une sortie posée par le code (gabarit d'un
    collègue, complétion d'un groupe) dont la condition, ou l'étape d'arrivée, porte encore le texte
    « à rédiger » n'est pas offerte au modèle (ni porte en fonction, ni porte écrite, ni filet de fin),
    comme l'étape de retour encore vide. Elle le devient dès que le texte est rédigé."""
    return _texte_en_attente(condition) or _texte_en_attente(getattr(cible, "prompt", None))


def etape_de_retour_du_graphe(graphe: Any) -> Any:
    """L'étape de retour de l'accueil dans ce graphe, ``None`` s'il n'en a pas ou si son prompt est
    encore « à rédiger » (zéro perte : le retour retombe alors sur l'étape de départ, comme avant).
    ⛔ Ne lève jamais."""
    try:
        for noeud in graphe.nodes.values():
            if (
                est_une_etape_de_retour_de_l_accueil(noeud)
                and not noeud.is_end
                and not est_a_rediger(getattr(noeud, "prompt", None))
            ):
                return noeud
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[groupe] étape de retour de l'accueil illisible : {e!r}")
        return None


def fins_du_noeud(noeud: Any) -> list[dict]:
    try:
        fins = getattr(getattr(noeud, "data", None), CLE_FINS, None) or []
        return [
            f if isinstance(f, dict) else f.model_dump() for f in fins if f is not None
        ]
    except Exception:  # noqa: BLE001
        return []


def _vide(valeur: Any) -> bool:
    if valeur is None:
        return True
    if isinstance(valeur, str):
        return not valeur.strip()
    if isinstance(valeur, (list, tuple, set, dict)):
        return len(valeur) == 0
    return False


def _egal(valeur: Any, attendu: Any) -> bool:
    if isinstance(valeur, (list, tuple, set)):
        return any(_egal(v, attendu) for v in valeur)
    return str(valeur).strip().casefold() == str(attendu).strip().casefold()


def condition_tenue(champ: Any, vaut: Any, gathered: Mapping[str, Any] | None) -> bool:
    """La condition d'une ligne sur la fiche : sans champ, vraie ; avec un champ seul, vraie si le champ est
    rempli ; avec ``vaut``, vraie si le champ vaut cette valeur (casse ignorée ; un champ à plusieurs valeurs la
    contient). La même forme pour les phrases de fin figées et pour les champs conditionnels d'une étape
    (lot 7 de correctifs-apres-banc-commun). ⛔ Ne lève jamais (dans le doute : fausse)."""
    try:
        nom = (champ or "").strip() if isinstance(champ, str) else ""
        if not nom:
            return True
        valeur = (gathered or {}).get(nom)
        if vaut is None or (isinstance(vaut, str) and not vaut.strip()):
            return not _vide(valeur)
        return not _vide(valeur) and _egal(valeur, vaut)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[groupe] condition illisible : {e!r}")
        return False


def choisir_la_fin(
    fins: Iterable[Mapping[str, Any]], gathered: Mapping[str, Any]
) -> str | None:
    """La phrase de la première ligne dont la condition est vraie.

    Une ligne : ``{"champ": nom, "vaut": valeur facultative, "phrase": texte}``. Sans champ,
    la ligne est vraie (c'est la phrase par défaut). Avec un champ seul : vraie si le champ de
    la fiche est rempli. Avec ``vaut`` : vraie si le champ vaut cette valeur (casse ignorée ;
    un champ à plusieurs valeurs la contient). ``None`` si aucune ligne n'est vraie.
    ⛔ Ne lève jamais."""
    try:
        for ligne in fins:
            phrase = (ligne.get("phrase") or "").strip()
            if not phrase:
                continue
            if condition_tenue(ligne.get("champ"), ligne.get("vaut"), gathered):
                return phrase
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[groupe] phrases de fin illisibles : {e!r}")
        return None


# D1 (rejeu du 16/10, S6 run 1394) : l'agent qui passe la main a parlé dans le même tour ; la
# conversation finit par un message de l'assistant, que certains fournisseurs refusent en dernier
# (Mistral : 400). L'agent appelé qui doit parler reçoit cette note, jamais dite à voix haute.
NOTE_DE_PASSATION = "[Passation : l'appelant vient de t'être transmis ; tu prends la parole.]"


# Lot 4 d'orchestrateur-trois-cerveaux (D8) : le résultat du travail de fond, souffle au cerveau de
# conversation. Un message de l'appelant en apparence, écrit par le CODE : il porte ce préfixe, et
# il est exclu partout où la note de passation l'est (historiques de passation, paroles de
# l'appelant, indices, greffier). Jamais dit à voix haute tel quel.
PREFIXE_RESULTAT_DU_TRAVAIL = "[Résultat du travail :"


def est_un_resultat_de_travail(message: Any) -> bool:
    """Le résultat du travail de fond écrit par le code, jamais une parole de l'appelant."""
    if not isinstance(message, dict):
        return False
    contenu = message.get("content")
    return isinstance(contenu, str) and contenu.startswith(PREFIXE_RESULTAT_DU_TRAVAIL)


def est_la_note_de_passation(message: Any) -> bool:
    """La note du code, jamais une parole de l'appelant (retour, résumé, agent suivant).
    Lot 4 d'orchestrateur-trois-cerveaux : le résultat du travail de fond est une note du code
    de même nature, exclue de la même façon."""
    return (
        isinstance(message, dict) and message.get("content") == NOTE_DE_PASSATION
    ) or est_un_resultat_de_travail(message)


def finit_par_l_assistant(messages: Iterable[Any]) -> bool:
    """Le tout dernier message (hors consignes système) est-il de l'assistant ?"""
    try:
        for message in reversed(list(messages)):
            if isinstance(message, dict) and message.get("role") != "system":
                return message.get("role") == "assistant"
        return False
    except Exception:  # noqa: BLE001
        return False


def l_appelant_a_parle_en_dernier(messages: Iterable[Any]) -> bool:
    """Le dernier message de conversation (hors outils et consignes) est-il de l'appelant ?

    Décide si l'agent qui reprend la main doit parler tout de suite (l'appelant attend une
    réponse) ou attendre en silence (la dernière réplique, par exemple « autre chose ? »,
    vient d'être dite par l'agent précédent)."""
    try:
        for message in reversed(list(messages)):
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            if role in ("tool", "function", "system"):
                continue
            if message.get("tool_calls") or message.get("function_call"):
                continue
            if not message.get("content") or est_la_note_de_passation(message):
                continue
            return role == "user"
        return False
    except Exception:  # noqa: BLE001
        return False


def porte_reecrite_vers_le_retour(graphe: Any, node: Any, nom: str) -> Any:
    """[.mark] Lot 7 (K1, n° 352) : une porte écrite qui n'est pas une sortie de l'étape en cours
    (``node``) et qui porte le nom d'une AUTRE étape du graphe est réécrite vers l'étape « retour
    au principal », si l'étape en cours a une sortie vers elle : rend cette arête. ``None`` sinon
    (ignorée comme avant ; chez le principal, aucune étape de retour). ⛔ Ne lève jamais."""
    try:
        from api.services.workflow.workflow_graph import transition_tool_name

        if not any(
            n.id != node.id and transition_tool_name(n.name) == nom
            for n in graphe.nodes.values()
        ):
            return None
        return next(
            (
                e
                for e in node.out_edges
                if est_une_etape_de_retour(graphe.nodes[e.target])
                and not graphe.nodes[e.target].is_end
            ),
            None,
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"[porte] réécriture vers le retour illisible : {e!r}")
        return None


# --- [.mark] Correctifs après le banc commun, lot 1 (K1, K4) ---------------------------------------

# K1 : le paramètre obligatoire de chaque outil de passation, repris dans la note remise au collègue.
PARAMETRE_DEMANDE = "demande"
DESCRIPTION_DEMANDE = "La demande de l'appelant, en une phrase."
LONGUEUR_MAX_DEMANDE = 300


def est_un_outil_de_passation(outil: Any) -> bool:
    """L'outil mène-t-il la main à un autre agent (``transfer_agent``) ? Lu sur la définition, puis
    sur la catégorie. ⛔ Ne lève jamais."""
    try:
        definition = getattr(outil, "definition", None) or {}
        if isinstance(definition, Mapping) and definition.get("type") == "transfer_agent":
            return True
        return getattr(outil, "category", None) == "transfer_agent"
    except Exception:  # noqa: BLE001
        return False


def demande_de(arguments: Any) -> str | None:
    """La demande de l'appelant donnée à l'outil de passation : une ligne, sans crochets (la note
    n'est jamais lue comme une parole de l'appelant), bornée. ``None`` si absente ou illisible
    (la passation part quand même). ⛔ Ne lève jamais."""
    try:
        if not isinstance(arguments, Mapping):
            return None
        brute = arguments.get(PARAMETRE_DEMANDE)
        if not isinstance(brute, str):
            return None
        texte = " ".join(brute.replace("[", "(").replace("]", ")").split())
        return texte[:LONGUEUR_MAX_DEMANDE] or None
    except Exception:  # noqa: BLE001
        return None


def porte_ecrite_est_une_fin(graphe: Any, nom: str) -> bool:
    """K4 : la porte écrite ``nom`` est-elle le nom d'un nœud de fin du graphe ? (Le collègue a écrit
    ``fin`` alors que son étape n'a pas cette porte : le code la réécrit en ``retour``.) ⛔ Ne lève jamais."""
    try:
        from api.services.workflow.workflow_graph import transition_tool_name

        return any(n.is_end and transition_tool_name(n.name) == nom for n in graphe.nodes.values())
    except Exception:  # noqa: BLE001
        return False


def sortie_de_fin_de_l_etape(noeud: Any, graphe: Any) -> Any:
    """K4 : l'arête de l'étape qui mène à un nœud de fin et qui est offerte (ni « à rédiger »). ``None``
    sinon. ⛔ Ne lève jamais."""
    try:
        if noeud is None or getattr(noeud, "is_end", False):
            return None
        return next(
            (
                e
                for e in noeud.out_edges
                if graphe.nodes[e.target].is_end
                and not sortie_en_attente(getattr(e, "condition", None), graphe.nodes[e.target])
            ),
            None,
        )
    except Exception:  # noqa: BLE001
        return None
