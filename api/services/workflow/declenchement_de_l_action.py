"""[.mark] Lot 6 de correctifs-apres-banc-commun (K8, D-4) : les quatre façons de déclencher l'outil d'action d'une étape.

Le bon choix dépend du modèle (run 1497, 1518 : le modèle annonce l'action sans l'appeler ; rejeu Scaleway du
run 1518 : 0/5 libre, 5/5 avec l'appel obligatoire). Menu « Déclenchement de l'action » dans la fenêtre de
l'étape (``declenchement_de_l_action`` des données de l'étape), défaut **Libre** = comportement d'avant, octet
pour octet (rien n'est branché) :

- **Libre** : rien de plus.
- **Relance** : l'étape a ses champs déclarés, la garde est complète, l'outil est offert, aucun travail n'est en
  cours, rien n'a été fait pour cette demande, et la réplique du modèle n'a ni question ni appel : elle est
  retenue, le modèle est relancé UNE fois avec l'appel obligatoire (``LLMContext.set_tool_choice``, Pipecat).
  C'est aussi le cas de « Je réserve le rendez-vous » dit sans appel (run 1519, constat K8 du lot 5).
- **Obligatoire** : mêmes conditions ; le tour part directement avec l'appel obligatoire.
- **Automatique** : mêmes conditions, mais l'étape peut ne déclarer aucun champ (le tour d'entrée suffit) : le
  CODE lance lui-même le travail de fond (``TravailDeLAgent.confier``), avec la demande type de l'étape
  (``{{champ}}`` remplacé par la valeur de la fiche) puis les valeurs de la fiche (K11, ``joindre_la_fiche``). Le
  modèle annonce ensuite le résultat à son arrivée.

Règle de l'humain : aucune position ne s'arme pendant un travail en cours, ni après un appel de l'outil pour la
même demande (l'**empreinte** : les valeurs des champs attendus de l'étape, hors champs que l'action écrit) ;
une donnée corrigée change l'empreinte et rouvre la garde, **sauf quand une écriture est en vigueur dans l'appel**
(lot B, B3 : plus rien ne s'arme, le modèle gère le changement avec ses outils) ; « Automatique » laisse toujours la conversation
reprendre après le résultat (autre date, annulation : le modèle garde tous ses outils, et ses propres appels ne
sont jamais interceptés). ``tool_choice`` n'est posé que pour un tour, puis remis comme avant.

Les conditions des champs (lot 7) sont celles de la garde : un champ dont la condition n'est pas tenue n'est pas
attendu et n'entre pas dans l'empreinte. Aucun mot de métier : l'outil est celui de l'étape (le travail de fond,
ou l'unique action de l'étape ; plusieurs actions sans travail de fond = rien n'est armé, journalisé).

⛔ Ne lève jamais : dans le doute, rien n'est armé et l'étape se comporte comme en « Libre ».
"""

from __future__ import annotations

import json
import re
from contextvars import ContextVar
from typing import Any, Mapping

from loguru import logger

from api.services.pipecat.reponse_avalee import ATTRIBUT_DECLENCHEUR

LIBRE = "libre"
RELANCE = "relance"
OBLIGATOIRE = "obligatoire"
AUTOMATIQUE = "automatique"
POSITIONS = (LIBRE, RELANCE, OBLIGATOIRE, AUTOMATIQUE)

RAISON_RELANCE = "declenchement_relance"
CLE_DECLENCHEMENTS = "mark_declenchements"
CLE_ACTIONS_EN_PREPARATION = "mark_actions_en_preparation"
ATTRIBUT_ACTIONS_DE_L_ETAPE = "mark_actions_de_l_etape"
_MARQUE_TOURS = "_mark_declenchement_des_tours"

# Générique, aucun métier : la demande du mode automatique quand l'étape n'a pas écrit de demande type. Les valeurs
# de la fiche sont jointes derrière (K11).
DEMANDE_PAR_DEFAUT = "Fais l'action de cette étape avec les valeurs de la fiche de l'appel."
_CHAMP_DANS_LA_DEMANDE = re.compile(r"\{\{\s*([^{}\s]+)\s*\}\}")

# Les marques de porte écrites DANS la réplique (porte parlée) : une réplique qui prend sa porte n'est pas relancée.
_MARQUES_DE_PORTE = ("→", "•")


def position_de(noeud: Any) -> str:
    """La position choisie pour l'étape ; tout ce qui n'est pas une position connue vaut « libre »."""
    valeur = getattr(noeud, "declenchement_de_l_action", None)
    return valeur if valeur in (RELANCE, OBLIGATOIRE, AUTOMATIQUE) else LIBRE


# ---------------------------------------------------------------------------------------------------------
# L'outil d'action de l'étape
# ---------------------------------------------------------------------------------------------------------


def noter_une_action_offerte(moteur: Any, nom_outil: str) -> None:
    """L'enveloppe des actions dit au moteur qu'une action de l'étape en préparation vient d'être enregistrée."""
    try:
        en_cours = getattr(moteur, CLE_ACTIONS_EN_PREPARATION, None)
        if isinstance(en_cours, set):
            en_cours.add(nom_outil)
    except Exception:  # noqa: BLE001
        pass


def commencer_la_liste_des_actions(moteur: Any) -> None:
    try:
        setattr(moteur, CLE_ACTIONS_EN_PREPARATION, set())
    except Exception:  # noqa: BLE001
        pass


def actions_offertes(moteur: Any) -> frozenset:
    try:
        en_cours = getattr(moteur, CLE_ACTIONS_EN_PREPARATION, None)
        return frozenset(en_cours) if isinstance(en_cours, set) else frozenset()
    except Exception:  # noqa: BLE001
        return frozenset()


def action_de_l_etape(actions: frozenset, etape_du_fond: bool, moteur: Any = None) -> str | None:
    """L'outil que la position déclenche : le travail de fond de l'étape (``confier``), sinon l'unique action
    d'ÉCRITURE de l'étape (lot 11, F-1 et revue 7 : une recherche ou une annulation à côté ne l'éteignent plus),
    sinon l'unique action de l'étape. Ambigu : ``None`` (on ne choisit pas pour l'étape)."""
    if etape_du_fond:
        from api.services.travail.reglages import NOM_OUTIL

        return NOM_OUTIL
    if moteur is not None:
        try:
            from api.services.workflow.verite_des_actions import outils_d_ecriture

            ecritures = outils_d_ecriture(moteur)
            qui_ecrivent = sorted(a for a in actions if _normaliser(a) in ecritures)
            if len(qui_ecrivent) == 1:
                return qui_ecrivent[0]
            if len(qui_ecrivent) > 1:
                return None
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[declenchement] actions d'écriture illisibles : {erreur!r}")
    if len(actions) == 1:
        return next(iter(actions))
    return None


def _normaliser(nom: Any) -> str:
    from api.services.workflow.enveloppe_des_actions import _normaliser as normaliser

    return normaliser(nom)


# ---------------------------------------------------------------------------------------------------------
# L'empreinte d'une demande et ce qui a déjà été fait
# ---------------------------------------------------------------------------------------------------------


def _signature(valeur: Any) -> Any:
    if isinstance(valeur, str):
        return " ".join(valeur.split()).casefold()
    if isinstance(valeur, Mapping):
        return {str(k): _signature(v) for k, v in sorted(valeur.items(), key=lambda kv: str(kv[0]))}
    if isinstance(valeur, (list, tuple, set)):
        return [_signature(v) for v in valeur]
    return valeur


def empreinte(moteur: Any, noeud: Any) -> str:
    """Ce que la demande est, pour cette étape : les valeurs des champs attendus de l'étape (conditions comprises),
    hors champs que l'action écrit elle-même (sinon son propre résultat rouvrirait la garde). Une donnée corrigée
    change l'empreinte. Étape sans champ : l'empreinte vide (une seule demande par étape)."""
    try:
        from api.services.workflow.champs_conditionnels import champs_actifs

        reglages = getattr(moteur, "_fiche", None)
        fiche = getattr(moteur, "_gathered_context", None)
        if not isinstance(fiche, dict):
            fiche = {}
        ecrits_par_l_action = {
            c.nom
            for c in tuple(getattr(reglages, "champs", None) or ())
            if getattr(c, "rempli_par_outil", None) or getattr(c, "annule_par_outil", None)
        }
        valeurs = [
            [nom, _signature(fiche.get(nom))] for nom in champs_actifs(noeud, fiche) if nom not in ecrits_par_l_action
        ]
        return json.dumps(valeurs, ensure_ascii=False, sort_keys=True, default=str)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[declenchement] empreinte illisible : {erreur!r}")
        return "?"


def _fait(moteur: Any) -> set:
    fait = getattr(moteur, CLE_DECLENCHEMENTS, None)
    if isinstance(fait, set):
        return fait
    fait = set()
    try:
        setattr(moteur, CLE_DECLENCHEMENTS, fait)
    except Exception:  # noqa: BLE001
        pass
    return fait


def noter_le_declenchement(moteur: Any, noeud: Any, outil: str) -> None:
    """L'outil de l'étape vient d'être appelé (par le modèle ou par le code) pour la demande d'après sa fiche
    d'aujourd'hui : aucune position ne se réarme pour cette demande. ⛔ Ne lève jamais."""
    try:
        _fait(moteur).add((getattr(noeud, "id", None), _normaliser(outil), empreinte(moteur, noeud)))
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[declenchement] appel non noté : {erreur!r}")


def noter_l_appel(moteur: Any, agent: Any, nom_outil: str) -> None:
    """Appelé par l'enveloppe des actions et par « confier » quand le modèle appelle l'outil lui-même. Étape en
    « Libre » : rien (aucun coût, aucun état)."""
    try:
        noeud = getattr(agent, "current_node", None)
        if noeud is None or position_de(noeud) == LIBRE:
            return
        noter_le_declenchement(moteur, noeud, nom_outil)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[declenchement] appel non noté : {erreur!r}")


# ---------------------------------------------------------------------------------------------------------
# Le déclencheur d'une étape
# ---------------------------------------------------------------------------------------------------------


class Declencheur:
    """La position d'une étape et ce qu'il faut pour savoir si elle s'arme, posé sur le cerveau de l'agent
    (``ATTRIBUT_DECLENCHEUR``) par ``brancher_le_declenchement``."""

    def __init__(self, moteur: Any, agent: Any, noeud: Any, position: str, outil: str):
        self.moteur = moteur
        self.agent = agent
        self.noeud = noeud
        self.position = position
        self.outil = outil
        # Décision d'Evan (26/10) : ce que la requête de CE tour dit au modèle quand B2 n'a pas relancé la demande
        # confiée par le code (position Automatique) ; lue puis effacée par l'enveloppe des tours.
        self.notice_du_tour: str | None = None

    # -- les conditions ------------------------------------------------------------------------

    def _etape_courante(self) -> bool:
        courant = getattr(self.agent, "current_node", None)
        if courant is None:
            return False
        if courant is self.noeud:
            return True
        return getattr(courant, "id", None) is not None and getattr(courant, "id", None) == getattr(self.noeud, "id", 0)

    def _deja_fait(self) -> bool:
        return (getattr(self.noeud, "id", None), _normaliser(self.outil), empreinte(self.moteur, self.noeud)) in _fait(
            self.moteur
        )

    async def armer(self) -> bool:
        """Toutes les conditions sont-elles réunies pour déclencher l'outil à cet instant ? Relance et obligatoire
        veulent des champs déclarés ; l'automatique peut s'en passer (le tour d'entrée suffit). ⛔ Ne lève jamais."""
        try:
            if self.position == LIBRE or not self._etape_courante():
                return False
            if self.position != AUTOMATIQUE and not tuple(getattr(self.noeud, "champs_etape", None) or ()):
                return False
            disposed = getattr(self.moteur, "is_call_disposed", None)
            if callable(disposed) and disposed():
                return False
            from api.services.travail.agent import ligne_du_travail

            if ligne_du_travail(self.moteur) is not None:
                return False
            if self._deja_fait():
                return False
            # Lot B (B3) : une écriture est en vigueur (une réservation faite, pas défaite) : rien ne s'arme, quoi que
            # le greffier note ensuite (run 1950 : « Oui, j'attends » noté changeait l'empreinte et relançait la recherche). Après une annulation réussie, l'écriture n'est plus en vigueur : un
            # changement de date repart. Le modèle garde tous ses outils.
            # Revue du 26/10 (R-4, décision d'Evan) : seulement une écriture partie de CETTE étape (de cet agent) ; une
            # autre étape ou un autre collègue peut encore déclencher sa propre action.
            from api.services.travail.demande_identique import identifiant_de_l_etape
            from api.services.workflow.verite_des_actions import ecriture_en_vigueur

            if ecriture_en_vigueur(self.moteur, identifiant_de_l_etape(self.noeud, self.agent)) is not None:
                return False
            from api.services.workflow.enveloppe_des_actions import (
                garde_du_noeud_apres_les_notes,
            )

            # Lot 11 (F-14) : l'attente du greffier, seulement quand il ne manque plus qu'un champ.
            return await garde_du_noeud_apres_les_notes(self.moteur, self.noeud, dernier_seulement=True) is None
        except Exception as erreur:  # noqa: BLE001 -- dans le doute, rien n'est armé
            logger.warning(f"[declenchement] conditions illisibles : {erreur!r}")
            return False

    # -- relance ----------------------------------------------------------------------------------

    async def controler_la_replique(self, texte: str) -> Any | None:
        """Position « relance » : la réplique de texte seul, sans question ni porte, retenue quand tout est prêt."""
        try:
            if self.position != RELANCE or "?" in texte or any(m in texte for m in _MARQUES_DE_PORTE):
                return None
            if not await self.armer():
                return None
            from api.services.workflow.verite_des_actions import Retenue

            logger.info(f"[declenchement] réplique sans appel retenue : relance avec {self.outil} obligatoire")
            return Retenue(RAISON_RELANCE, self.outil, "", outil=self.outil)
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[declenchement] réplique non contrôlée : {erreur!r}")
            return None

    # -- obligatoire et automatique, avant le tour ---------------------------------------------------

    async def avant_le_tour(self, context: Any):
        """Appelé avant chaque requête de conversation. Obligatoire : pose l'appel obligatoire pour ce tour et rend
        de quoi le remettre ; automatique : lance le travail. ``None`` : rien n'a changé."""
        if self.position == OBLIGATOIRE:
            if not hasattr(context, "set_tool_choice"):
                return None
            paroles = paroles_de_l_appelant(context)
            # Lot 11 (F-7) : une question de la personne a sa réponse ; le forçage reprend au tour suivant.
            if paroles and "?" in paroles[-1]:
                logger.info("[declenchement] la personne pose une question : tour libre")
                return None
            # Lot 11 (F-1, revue 3) : jamais deux forçages pour la même parole de la personne.
            if getattr(self, "_parole_forcee", None) == len(paroles):
                return None
            if not await self.armer():
                return None
            avant = getattr(context, "tool_choice", None)
            context.set_tool_choice(choix_de_l_outil(self.outil))
            self._parole_forcee = len(paroles)
            logger.info(f"[declenchement] tour avec {self.outil} obligatoire")

            def remettre() -> None:
                # Lot 11 (revue 10) : le choix d'avant, quel qu'il soit.
                context.set_tool_choice(avant)

            return remettre
        if self.position == AUTOMATIQUE:
            await self.lancer_automatiquement()
        return None

    async def lancer_automatiquement(self) -> bool:
        """Position « automatique » : le code confie lui-même le travail de fond. ⛔ Ne lève jamais."""
        try:
            from api.services.travail.reglages import NOM_OUTIL

            travail = getattr(self.agent, "travail", None)
            if self.outil != NOM_OUTIL or travail is None:
                logger.warning(
                    "[declenchement] mode automatique sans travail en arrière-plan à cette étape : rien n'est lancé"
                )
                return False
            if not await self.armer():
                return False
            from api.services.travail.demande import joindre_la_fiche

            reglages = getattr(self.moteur, "_fiche", None)
            fiche = getattr(self.moteur, "_gathered_context", None)
            fiche = fiche if isinstance(fiche, dict) else {}
            demande = demande_type_remplie(getattr(self.noeud, "demande_type", None), fiche)
            demande = joindre_la_fiche(demande, reglages, fiche)
            noter_le_declenchement(self.moteur, self.noeud, self.outil)
            resultat = await travail.confier(demande)
            from api.services.travail.demande_identique import notice_du_retour

            self.notice_du_tour = notice_du_retour(resultat)
            entree = getattr(travail, "_entree_courante", None)
            # Lot B (B2) : une demande identique non relancée ne marque pas la trace d'avant.
            if isinstance(entree, dict) and isinstance(resultat, dict) and resultat.get("statut") == "lancé":
                if not resultat.get("deja_en_cours"):
                    entree["declenche_par"] = AUTOMATIQUE
            logger.info(f"[declenchement] travail lancé par le code : {resultat}")
            return True
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[declenchement] lancement automatique en échec : {erreur!r}")
            return False


def paroles_de_l_appelant(context: Any) -> list[str]:
    """Les paroles de la personne dans la conversation, dans l'ordre (texte seul). ⛔ Ne lève jamais."""
    try:
        from api.services.workflow.verite_des_actions import _contenu

        return [
            _contenu(m)
            for m in (getattr(context, "messages", None) or [])
            if isinstance(m, Mapping) and m.get("role") == "user"
        ]
    except Exception:  # noqa: BLE001
        return []


def choix_de_l_outil(nom: str) -> dict:
    """L'appel obligatoire d'une fonction (format commun de ``LLMContext.set_tool_choice``)."""
    return {"type": "function", "function": {"name": nom}}


def demande_type_remplie(demande_type: Any, fiche: Mapping[str, Any] | None) -> str:
    """La demande type de l'étape, chaque ``{{champ}}`` remplacé par la valeur de la fiche (vide s'il n'en a pas).
    Sans demande type : la demande par défaut."""
    texte = demande_type.strip() if isinstance(demande_type, str) else ""
    if not texte:
        return DEMANDE_PAR_DEFAUT

    def valeur(m: re.Match) -> str:
        v = (fiche or {}).get(m.group(1))
        if v is None:
            return ""
        if isinstance(v, (list, tuple, set)):
            return ", ".join(str(x) for x in v)
        return " ".join(str(v).split())

    return _CHAMP_DANS_LA_DEMANDE.sub(valeur, texte)


# ---------------------------------------------------------------------------------------------------------
# Le branchement
# ---------------------------------------------------------------------------------------------------------


def _brancher_les_tours(llm: Any) -> bool:
    """Enveloppe, une fois par cerveau, la requête de conversation : avant chaque tour, le déclencheur de l'étape
    (s'il y en a un) peut poser l'appel obligatoire ou lancer le travail ; l'appel obligatoire est remis juste
    après la création de la requête. Rien n'est enveloppé pour un agent dont aucune étape n'en a besoin."""
    if getattr(llm, _MARQUE_TOURS, False):
        return True
    if not hasattr(llm, "get_chat_completions"):
        return False
    obtenir = llm.get_chat_completions
    # La notice de B2 en Automatique, pour la requête de ce tour seulement (comme la notice du garde-fou d'impasse).
    notice_en_cours: ContextVar[str | None] = ContextVar("notice_du_declenchement", default=None)

    async def get_chat_completions(context):
        declencheur = getattr(llm, ATTRIBUT_DECLENCHEUR, None)
        remettre = None
        notice = None
        if declencheur is not None:
            try:
                remettre = await declencheur.avant_le_tour(context)
                notice, declencheur.notice_du_tour = getattr(declencheur, "notice_du_tour", None), None
            except Exception as erreur:  # noqa: BLE001 -- jamais à la place du tour
                logger.warning(f"[declenchement] tour non préparé : {erreur!r}")
        jeton = notice_en_cours.set(notice)
        try:
            return await obtenir(context)
        finally:
            notice_en_cours.reset(jeton)
            if remettre is not None:
                try:
                    remettre()
                except Exception as erreur:  # noqa: BLE001
                    logger.warning(f"[declenchement] choix d'outil non remis : {erreur!r}")

    construire = getattr(llm, "build_chat_completion_params", None)
    if construire is not None:

        def build_chat_completion_params(params_from_context):
            params = construire(params_from_context)
            notice = notice_en_cours.get()
            if notice:
                try:
                    from api.services.workflow.fiche_au_fil_de_leau import inserer_l_etat

                    cle = "messages" if "messages" in params else "input"
                    params[cle] = inserer_l_etat(list(params[cle]), notice)
                except Exception as erreur:  # noqa: BLE001
                    logger.error(f"[declenchement] notice non montrée : {erreur!r}")
            return params

        llm.build_chat_completion_params = build_chat_completion_params
    llm.get_chat_completions = get_chat_completions
    setattr(llm, _MARQUE_TOURS, True)
    return True


def brancher_le_declenchement(moteur: Any, agent: Any, noeud: Any, outil: str | None) -> str:
    """Pose (ou retire) le déclencheur de l'étape sur le cerveau de ``agent``. Rend la position armée. Étape en
    « Libre » (le défaut) sur un cerveau qui n'a jamais eu de déclencheur : AUCUN geste. ⛔ Ne lève jamais."""
    try:
        llm = getattr(agent, "llm", None)
        if llm is None:
            return LIBRE
        position = position_de(noeud)
        if position != LIBRE and outil is None:
            logger.warning(
                f"[declenchement] étape « {getattr(noeud, 'name', '?')} » en {position} : "
                "aucune action unique à déclencher (plusieurs actions, ou aucune) : rien n'est armé"
            )
            position = LIBRE
        if position == LIBRE:
            if getattr(llm, ATTRIBUT_DECLENCHEUR, None) is not None:
                setattr(llm, ATTRIBUT_DECLENCHEUR, None)
            return LIBRE
        setattr(llm, ATTRIBUT_DECLENCHEUR, Declencheur(moteur, agent, noeud, position, outil))
        if position in (OBLIGATOIRE, AUTOMATIQUE):
            _brancher_les_tours(llm)
        return position
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[declenchement] déclenchement non branché : {erreur!r}")
        return LIBRE
