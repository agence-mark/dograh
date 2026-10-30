"""[.mark] figeage-v12 (D4) : l'état de la fiche dans l'instruction système, à la place d'un message de la personne.

Cause prouvée au lot 0 (``Labo-agent-vocal/plans/figeage-v12/lot-0-causes.md``) : le code glissait l'état de la fiche comme
**un message de la personne** (``role: user``) juste avant sa dernière parole (``inserer_l_etat``). Small 3.2 ne s'en sert pas
pour choisir sa question : il redemandait ce que la fiche tenait déjà (16 cas sur 21 avec une requête pourtant juste). La même
fiche, posée là où vivent les consignes (la fin de l'instruction système), est respectée : 0 redemande sur 64 rejeux.

Case par agent ``fiche_dans_le_systeme`` (éteinte par défaut : comportement d'avant, à l'octet). Allumée, **à chaque requête de
conversation** le bloc est recalculé (même texte, même calcul, sur la fiche du moment) et rangé en dernier dans l'instruction
système du service, avec l'API que Pipecat offre pour ça : ``LLMService`` recompose ``system_instruction`` à partir de
son prompt de base et de ses ajouts (``_compose_system_instruction``), et TOUS les adaptateurs (``get_llm_invocation_params``)
la lisent. Rien ne dépend d'une famille de fournisseurs, et aucun message ``system`` n'est glissé au milieu de la
conversation (Mistral le refuse : 400 mesuré). Appelée par le processeur posé autour du cerveau, sur la trame
``LLMContextFrame`` (``pipecat/avant_la_requete.py``), téléphone et clavier.

⚠️ Le bloc change à chaque tour : le cache de préfixe ne couvre plus l'historique (sans effet aujourd'hui chez Scaleway, qui
ne renvoie aucun jeton en cache).

Zéro perte : si le bloc n'a pas pu être rangé (service sans composition, erreur), l'ancien chemin reste en place pour CETTE
requête (``llm._mark_fiche_en_systeme`` est faux, l'enveloppe de ``montrer_la_fiche`` insère l'état comme avant).

Aucun mot de métier. ⛔ Ne lève jamais.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

CLE_FICHE_DANS_LE_SYSTEME = "fiche_dans_le_systeme"
# Le texte du bloc rangé à la dernière requête, retrouvé pour le remplacer (jamais de bloc en double).
_BLOC_RANGE = "_mark_bloc_fiche_range"
# Vrai quand le bloc de CETTE requête est dans l'instruction système : l'enveloppe de ``montrer_la_fiche`` ne l'insère alors pas.
EN_SYSTEME = "_mark_fiche_en_systeme"
# Le constructeur du texte de l'état, posé sur le service par ``montrer_la_fiche`` (quelle que soit sa famille).
CONSTRUCTEUR = "_mark_etat_de_la_fiche"


def case_allumee(agent: Any, moteur: Any) -> bool:
    """La case « fiche dans l'instruction système » de l'agent : posée à ``True`` seulement. ⛔ Ne lève jamais."""
    try:
        reglages = getattr(agent, "reglages", None) or getattr(moteur, "reglages_appel", None) or {}
        return reglages.get(CLE_FICHE_DANS_LE_SYSTEME) is True
    except Exception:  # noqa: BLE001
        return False


def _retirer_le_bloc(llm: Any) -> None:
    """Retire le bloc rangé à la requête d'avant de la liste des ajouts de l'instruction système."""
    ancien = getattr(llm, _BLOC_RANGE, None)
    if ancien is None:
        return
    ajouts = getattr(llm, "_appended_system_instructions", None)
    if isinstance(ajouts, list):
        ajouts[:] = [a for a in ajouts if a != ancien]
    setattr(llm, _BLOC_RANGE, None)


def _recomposer(llm: Any) -> None:
    llm._compose_system_instruction()


def placer_la_fiche(moteur: Any, llm: Any, messages: list) -> bool:
    """Case allumée : range l'état de la fiche d'aujourd'hui en dernier dans l'instruction système de ``llm`` (le bloc
    d'avant est remplacé). Case éteinte, ou sans parole de la personne (l'accueil) : aucun bloc. Rend ``True`` si le bloc de
    cette requête est dans l'instruction système. ⛔ Ne lève jamais (en échec : ``False``, l'ancien chemin joue)."""
    try:
        agent = moteur.active_agent
        voulu = case_allumee(agent, moteur)
        construire = getattr(llm, CONSTRUCTEUR, None)
        if not voulu or construire is None:
            if getattr(llm, _BLOC_RANGE, None) is not None:
                _retirer_le_bloc(llm)
                _recomposer(llm)
            setattr(llm, EN_SYSTEME, False)
            return False
        if not isinstance(getattr(llm, "_appended_system_instructions", None), list):
            logger.warning("[fiche] service sans composition d'instruction système : l'état reste un message")
            setattr(llm, EN_SYSTEME, False)
            return False
        from api.services.groupe.passations import est_la_note_de_passation

        dicts = [m for m in messages if isinstance(m, dict)]
        a_une_parole = any(m.get("role") == "user" and not est_la_note_de_passation(m) for m in dicts)
        texte = construire(dicts) if a_une_parole else None
        _retirer_le_bloc(llm)
        if texte:
            llm._appended_system_instructions.append(texte)
            setattr(llm, _BLOC_RANGE, texte)
        _recomposer(llm)
        # Sans parole de la personne (l'accueil), l'ancien chemin n'ajoutait rien non plus : rien ne se perd.
        setattr(llm, EN_SYSTEME, True)
        return True
    except Exception as erreur:  # noqa: BLE001 -- l'état ne coûte jamais l'appel
        logger.error(f"[fiche] état non rangé dans l'instruction système : {erreur!r}")
        try:
            _retirer_le_bloc(llm)
            _recomposer(llm)
        except Exception:  # noqa: BLE001
            pass
        setattr(llm, EN_SYSTEME, False)
        return False
