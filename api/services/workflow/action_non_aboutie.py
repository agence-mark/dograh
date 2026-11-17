"""[.mark] Lot SA-22 (C18) : une action commencée et pas aboutie bloque la fin de l'appel, une fois.

Un garde-fou au sens du registre (``reference/29-garde-fous.md``, section B) : il détecte un **mécanisme** et répond par un
**geste mécanique**, sans comprendre l'agent ni parler un mot de métier.

- **Il détecte** : pendant l'appel, un outil marqué « doit aboutir avant la fin » a été appelé et son DERNIER résultat n'est
  pas un succès, ou il est encore en cours (appelé dans le même tour que la fin, résultat pas revenu).
- **Il détecte aussi** une ACTION OUVERTE : un connecteur déclare ce qu'il a commencé dans l'appel et pas fini (``Connecteur.action_ouverte``) ;
  la fin est refusée une fois de la même façon, et le résultat nomme l'outil qui la finit (``outils_a_appeler``).
- **Il fait** : quand l'agent demande la fin (une porte vers un nœud de fin, l'outil « fin d'appel »), le code refuse UNE
  fois et rend au modèle un résultat neutre (« une action n'a pas abouti : termine-la ou dis ce qu'il en est »). Au second
  essai la fin passe : jamais un appel coincé (G2). Un appel sain ne déclenche rien (G1).
- **Il prévient** (option, éteinte par défaut) : si la fin passe quand même avec une action non aboutie, une alerte de
  l'appel est écrite (le mécanisme d'alerte existant : page « Alertes », mail regroupé si la case de l'agent est allumée).

Réglages : l'interrupteur de l'agent ``moteur_fin_apres_action_non_aboutie`` (allumé par défaut : silencieux tant que tout
va bien), l'option ``garde_prevenir_action_non_aboutie`` (éteinte par défaut), et la case par outil
``doit_aboutir_avant_la_fin`` dans la définition de l'outil (``config``, aucune migration) : vide = cochée sur un outil qui
ÉCRIT (``outils_mark.essai.ecrit`` : HTTP hors GET, action de logiciel que le catalogue dit écrire, MCP), décochée sur un
outil qui lit.

« Abouti » = le résultat de l'outil, comme la vérité des actions le lit déjà (``resultat_reussi`` : ni échec, ni refus),
plus les statuts de non-aboutissement (``refusee``, ``incomplete``…). ``ENREGISTREE``, ``DEJA_FAIT``, ``OK`` et
``TRANSMISE`` sont des succès sans que le mot figure ici.

⛔ Zéro vocabulaire métier. ⛔ Ne lève jamais : dans le doute, la fin passe (comme avant).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from loguru import logger

from api.services.groupe.reglages_effectifs import reglages_de_l_agent
from api.services.interventions_du_moteur import CLE_FIN_APRES_ACTION_NON_ABOUTIE, intervention_du_moteur

CLE_PREVENIR = "garde_prevenir_action_non_aboutie"
# La case par outil, dans ``definition.config`` de l'outil (``True`` / ``False`` ; absente : le défaut dit plus haut).
CLE_DE_L_OUTIL = "doit_aboutir_avant_la_fin"
# Posés sur le moteur : les noms d'outils (normalisés) qui doivent aboutir ; les appels en cours ; (fiche) le refus déjà fait.
ATTRIBUT_OUTILS = "_mark_outils_a_faire_aboutir"
ATTRIBUT_EN_COURS = "_mark_actions_en_cours"
CLE_FICHE_REFUS = "fin_refusee_action_non_aboutie"
CLE_FICHE_PREVENU = "fin_prevenue_action_non_aboutie"

# Un résultat qui dit « pas fait » en plus de ceux que ``resultat_reussi`` connaît (échec, refus, indisponible).
STATUTS_NON_ABOUTIS = frozenset(
    {"refusee", "refusée", "refused", "refuse", "refusé", "incomplete", "incomplet", "missing", "non_abouti", "non_aboutie"}
)

STATUT_REFUS = "action_non_aboutie"
MESSAGE_OUVERTE = (
    "Une action est restée ouverte : termine-la avant de finir l'appel, ou dis à l'appelant ce qu'il en est, puis termine l'appel. "
    "N'annonce rien comme fait."
)
MESSAGE_REFUS = (
    "Une action n'a pas abouti : termine-la, ou dis à l'appelant ce qu'il en est, puis termine l'appel. "
    "N'annonce rien comme fait."
)


def outil_doit_aboutir(outil: Any) -> bool:
    """La case de l'outil : posée (``True`` / ``False``) dans sa config, elle décide ; vide, l'outil qui écrit est coché.
    ⛔ Ne lève jamais (dans le doute : non coché, la fin passe)."""
    try:
        config = ((getattr(outil, "definition", None) or {}).get("config")) or {}
        valeur = config.get(CLE_DE_L_OUTIL)
        if isinstance(valeur, bool):
            return valeur
        # SA-49 (M115) : une action du catalogue peut se déclarer « doit aboutir » sans écrire chez un tiers (``Action.doit_aboutir``).
        if config.get("connecteur") and config.get("action"):
            from api.services.integrations.connectors.catalogue import trouver

            trouve = trouver(str(config.get("connecteur")), str(config.get("action")))
            if trouve is not None and isinstance(getattr(trouve[1], "doit_aboutir", None), bool):
                return trouve[1].doit_aboutir
        from api.services.outils_mark.essai import ecrit

        return bool(ecrit(outil))
    except Exception:  # noqa: BLE001
        return False


def outils_qui_doivent_aboutir(moteur: Any) -> frozenset:
    """Les noms (normalisés) des outils inscrits « doit aboutir » pour l'appel. ⛔ Ne lève jamais."""
    inscrits = getattr(moteur, ATTRIBUT_OUTILS, None)
    return frozenset(inscrits) if isinstance(inscrits, set) else frozenset()


# ---------------------------------------------------------------------------------------------------------
# SA-49 (M115, appel 2597) : l'action DÉCLARÉE de l'étape en cours, jamais appelée
# ---------------------------------------------------------------------------------------------------------
# Une étape qui déclare son action (« Déclenchement de l'action » autre que Libre, et un outil d'action unique) : on y est entré, son outil n'a
# jamais été appelé dans l'appel, et l'agent demande la fin. Le modèle avait dit « je laisse un message » sans appeler l'outil : la fin passait, le
# message n'existait pas. Tenue dans la fiche (au clavier, le moteur est refait à chaque réplique), remplacée à chaque étape qui n'est pas une fin.
CLE_FICHE_ATTENDUE = "action_attendue_de_l_etape"


def poser_l_action_attendue(moteur: Any, outil: str | None) -> None:
    """À la mise en place d'une étape qui n'est pas une fin : son action déclarée (``None`` : aucune). ⛔ Ne lève jamais."""
    try:
        fiche = getattr(moteur, "_gathered_context", None)
        if not isinstance(fiche, dict):
            return
        if outil:
            fiche[CLE_FICHE_ATTENDUE] = str(outil)
        else:
            fiche.pop(CLE_FICHE_ATTENDUE, None)
    except Exception:  # noqa: BLE001
        pass


def action_attendue(moteur: Any) -> str | None:
    """L'action déclarée de l'étape en cours, ou ``None``. ⛔ Ne lève jamais."""
    try:
        fiche = getattr(moteur, "_gathered_context", None)
        valeur = fiche.get(CLE_FICHE_ATTENDUE) if isinstance(fiche, dict) else None
        return valeur if isinstance(valeur, str) and valeur.strip() else None
    except Exception:  # noqa: BLE001
        return None


def action_deja_appelee(moteur: Any, outil: str) -> bool:
    """L'outil a-t-il été appelé dans l'appel (son résultat est au journal, ou il est en cours) ? ⛔ Ne lève jamais (``True`` dans le doute)."""
    try:
        from api.services.workflow.enveloppe_des_actions import _normaliser
        from api.services.workflow.verite_des_actions import journal_de

        nom = _normaliser(outil)
        if any(_normaliser(vue.nom) == nom for vue in journal_de(moteur)):
            return True
        return int(_en_cours(moteur).get(nom, 0)) > 0
    except Exception:  # noqa: BLE001
        return True


def action_attendue_jamais_appelee(moteur: Any) -> str | None:
    outil = action_attendue(moteur)
    return outil if outil and not action_deja_appelee(moteur, outil) else None


def inscrire_l_outil(moteur: Any, nom_fonction: str, outil: Any) -> None:
    """À l'enregistrement des outils de l'étape : retient (ou oublie) le nom de fonction de l'outil. ⛔ Ne lève jamais."""
    try:
        from api.services.workflow.enveloppe_des_actions import _normaliser

        nom = _normaliser(nom_fonction)
        inscrits = getattr(moteur, ATTRIBUT_OUTILS, None)
        if not isinstance(inscrits, set):
            inscrits = set()
            setattr(moteur, ATTRIBUT_OUTILS, inscrits)
        if outil_doit_aboutir(outil):
            inscrits.add(nom)
        else:
            inscrits.discard(nom)
    except Exception as erreur:  # noqa: BLE001
        logger.debug(f"[fin] outil non inscrit : {erreur!r}")


def _en_cours(moteur: Any) -> dict:
    en_cours = getattr(moteur, ATTRIBUT_EN_COURS, None)
    if not isinstance(en_cours, dict):
        en_cours = {}
        try:
            setattr(moteur, ATTRIBUT_EN_COURS, en_cours)
        except Exception:  # noqa: BLE001
            pass
    return en_cours


def noter_l_appel_en_cours(moteur: Any, nom_outil: str, delta: int) -> None:
    """L'enveloppe des actions : un appel part (``+1``), son résultat final est revenu ou l'appel a fini (``-1``).
    ⛔ Ne lève jamais."""
    try:
        from api.services.workflow.enveloppe_des_actions import _normaliser

        nom = _normaliser(nom_outil)
        en_cours = _en_cours(moteur)
        en_cours[nom] = max(0, int(en_cours.get(nom, 0)) + delta)
    except Exception:  # noqa: BLE001
        pass


def a_abouti(resultat: Any) -> bool:
    """Le résultat d'un outil dit-il que l'action est faite ? Comme la vérité des actions, sans les statuts « pas fait »."""
    try:
        from api.services.workflow.verite_des_actions import _statut_du, resultat_reussi

        if not resultat_reussi(resultat):
            return False
        statut = _statut_du(resultat)
        return statut is None or statut not in STATUTS_NON_ABOUTIS
    except Exception:  # noqa: BLE001
        return True


def actions_non_abouties(moteur: Any) -> list[str]:
    """Les outils « doit aboutir » dont le dernier résultat n'est pas un succès, ou dont l'appel est encore en cours.
    Un outil jamais appelé n'est pas concerné. ⛔ Ne lève jamais (liste vide dans le doute)."""
    try:
        from api.services.workflow.enveloppe_des_actions import _normaliser
        from api.services.workflow.verite_des_actions import journal_de

        inscrits = getattr(moteur, ATTRIBUT_OUTILS, None)
        if not isinstance(inscrits, set) or not inscrits:
            return []
        derniers: dict[str, Any] = {}
        for vue in journal_de(moteur):
            derniers[_normaliser(vue.nom)] = vue
        non_abouties: list[str] = []
        for nom, vue in derniers.items():
            if nom in inscrits and not a_abouti(vue.resultat):
                non_abouties.append(nom)
        for nom, compte in _en_cours(moteur).items():
            if compte > 0 and nom in inscrits and nom not in non_abouties:
                non_abouties.append(nom)
        return non_abouties
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[fin] actions non abouties non lues : {erreur!r}")
        return []


def actions_ouvertes(moteur: Any) -> list[dict]:
    """Les actions commencées dans l'appel et pas finies, selon les connecteurs (``Connecteur.action_ouverte`` lit la fiche de l'appel ; c'est le
    connecteur qui dit ce qui est ouvert, ce mécanisme ne le sait pas). Chaque entrée : ``{"connecteur", "outil"}`` (l'action qui la finit). ⛔ Ne lève jamais."""
    try:
        fiche = getattr(moteur, "_gathered_context", None)
        if not isinstance(fiche, dict):
            return []
        from api.services.integrations.connectors.catalogue import connecteurs

        ouvertes: list[dict] = []
        for c in connecteurs():
            if c.action_ouverte is None:
                continue
            try:
                trouvee = c.action_ouverte(fiche)
            except Exception as erreur:  # noqa: BLE001
                logger.debug(f"[fin] action ouverte illisible ({c.nom}) : {erreur!r}")
                continue
            if isinstance(trouvee, Mapping):
                ouvertes.append({"connecteur": c.nom, "outil": str(trouvee.get("outil") or "")})
        return ouvertes
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[fin] actions ouvertes non lues : {erreur!r}")
        return []


def _option_posee(moteur: Any, cle: str) -> bool:
    """Une option éteinte par défaut : ``True`` posé seulement, sur l'agent qui a la main, sinon sur l'appel."""
    try:
        agent = getattr(moteur, "active_agent", None)
        reglages = reglages_de_l_agent(moteur, agent)
        return isinstance(reglages, Mapping) and reglages.get(cle) is True
    except Exception:  # noqa: BLE001
        return False


def _prevenir(moteur: Any, noms: list[str]) -> None:
    """L'appel finit avec une action non aboutie : une alerte de l'appel, une seule fois. ⛔ Ne lève jamais."""
    try:
        fiche = getattr(moteur, "_gathered_context", None)
        if not isinstance(fiche, dict) or fiche.get(CLE_FICHE_PREVENU):
            return
        fiche[CLE_FICHE_PREVENU] = True
        from api.services.tri import alertes, donnees

        alertes.alerter(
            moteur,
            donnees.ALERTE_OUTIL_EN_ECHEC,
            detail="l'appel a fini avec une action non aboutie",
            outil=", ".join(noms),
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[fin] alerte non écrite : {erreur!r}")


def verifier_la_fin(moteur: Any, *, refuser: bool = True) -> dict | None:
    """L'agent demande la fin de l'appel. Rend le résultat neutre à renvoyer au modèle (la fin est refusée, UNE fois par
    appel), ou ``None`` : la fin passe. ``refuser=False`` : ne refuse jamais, prévient seulement (une porte écrite dans la
    réponse, déjà dite à la voix : rien à répondre au modèle). ⛔ Ne lève jamais."""
    try:
        non_abouties = actions_non_abouties(moteur)
        ouvertes = actions_ouvertes(moteur)
        outils_a_finir = [o["outil"] for o in ouvertes if o["outil"]]
        noms = non_abouties + [o["connecteur"] for o in ouvertes if o["connecteur"] not in non_abouties]
        # SA-49 (M115) : l'action déclarée de l'étape, jamais appelée, est une action ouverte (le résultat nomme son outil).
        attendue = action_attendue_jamais_appelee(moteur)
        if attendue and attendue not in noms:
            noms.append(attendue)
            if attendue not in outils_a_finir:
                outils_a_finir.append(attendue)
        if not noms:
            return None
        fiche = getattr(moteur, "_gathered_context", None)
        if (
            refuser
            and intervention_du_moteur(moteur, CLE_FIN_APRES_ACTION_NON_ABOUTIE)
            and isinstance(fiche, dict)
            and not fiche.get(CLE_FICHE_REFUS)
        ):
            fiche[CLE_FICHE_REFUS] = True
            logger.info(f"[fin] fin refusée une fois : action non aboutie ({', '.join(noms)})")
            retour = {"status": STATUT_REFUS, "message": MESSAGE_REFUS if non_abouties else MESSAGE_OUVERTE, "actions": noms}
            if outils_a_finir:
                retour["outils_a_appeler"] = outils_a_finir  # le résultat nomme l'outil qui finit l'action
            return retour
        if _option_posee(moteur, CLE_PREVENIR):
            _prevenir(moteur, noms)
        return None
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[fin] fin non contrôlée : {erreur!r}")
        return None
