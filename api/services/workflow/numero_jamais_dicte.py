"""[.mark] passages-fiables (lot C1, registre XXIX.4) : un numéro que la personne n'a jamais dicté n'est pas dit.

Runs 2146 (« 06 06 06 06 06 ») et 2121 (« 51 42 36 78 ») : l'agent a donné un numéro inventé. Une réplique de l'agent qui
contient une suite de huit chiffres ou plus (espaces et points ignorés) absente de tout ce que l'agent a le droit de
connaître est RETENUE, au même endroit que la vérité des actions (``RepliqueVerifiee``) : le modèle est relancé UNE fois
avec une consigne générique (le numéro n'a jamais été dicté, demander à la personne de le dicter).

Ce que l'agent a le droit de connaître (aucune seconde lecture des chiffres : ``numeros_dictes`` et ``_chiffres`` de
``relecture_numeros`` sont réutilisés, R5) :
- les paroles de la personne, et tout message qui n'est pas une réplique de l'agent (résultat d'outil, consigne : même
  règle que les dates, ``dates_connues``) ;
- les numéros que le module des nombres a lus dans sa parole ;
- les valeurs de la fiche venues d'elle (jamais un champ rempli par un outil) ;
- les numéros de l'appel connus du code (``caller_number`` et ``called_number``) ; au clavier il n'y en a pas.

⛔ Zéro vocabulaire métier. ⛔ Ne lève jamais : dans le doute, la réplique passe. Option par agent
(``numero_jamais_dicte``), éteinte par défaut ; seulement avec le cerveau compatible OpenAI.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from loguru import logger

from api.services.pipecat.relecture_numeros import CLE_NOMBRES_LUS, _chiffres, numeros_dictes
from api.services.workflow.verite_des_actions import Retenue, _contenu

CLE_NUMERO_JAMAIS_DICTE = "numero_jamais_dicte"
# La trace lue plus tard (lot G) : les répliques retenues, dans la fiche de l'appel.
CLE_TRACE = "repliques_numero_retenues"
RAISON_NUMERO = "numero_jamais_dicte"
# Une suite de chiffres de la forme d'un numéro : huit chiffres ou plus.
CHIFFRES_MIN = 8

CONSIGNE_NUMERO = (
    "Ta réponse a été retenue : elle donnait un numéro (une suite de chiffres) que la personne n'a jamais dicté et "
    "qu'aucun résultat d'outil ne donne. Ne donne aucun numéro que tu n'as pas reçu : demande à la personne de le dicter."
)

# Entre deux chiffres d'un même numéro : un espace (insécable compris) ou un point. Jamais un tiret ni une virgule.
_SUITE = re.compile(r"\d(?:[ .  ]?\d)*")


def _est_une_date(chiffres: str) -> bool:
    """Huit chiffres qui se lisent jour mois année (ou année mois jour) : une date écrite, non un numéro."""
    if len(chiffres) != 8:
        return False
    for jour, mois, annee in ((chiffres[:2], chiffres[2:4], chiffres[4:]), (chiffres[6:], chiffres[4:6], chiffres[:4])):
        if 1 <= int(jour) <= 31 and 1 <= int(mois) <= 12 and annee[:2] in ("19", "20"):
            return True
    return False


def suites_de_chiffres(texte: str) -> list[str]:
    """Les suites de ``CHIFFRES_MIN`` chiffres ou plus d'un texte, réduites à leurs chiffres (une date écrite n'en est pas une)."""
    return [
        c
        for m in _SUITE.finditer(texte or "")
        if len(c := _chiffres(m.group(0))) >= CHIFFRES_MIN and not _est_une_date(c)
    ]


def _formes(chiffres: str) -> set[str]:
    """Un numéro peut se dire avec ou sans l'indicatif (« 06… » ou « +33 6… »)."""
    formes = {chiffres}
    if chiffres.startswith("33") and len(chiffres) >= 10:
        formes.add("0" + chiffres[2:])
    if chiffres.startswith("0") and len(chiffres) >= 9:
        formes.add("33" + chiffres[1:])
    return formes


def _suites_de(texte: str) -> list[str]:
    return [c for m in _SUITE.finditer(texte or "") if (c := _chiffres(m.group(0)))]


def chiffres_connus(moteur: Any, messages: Any) -> list[str]:
    """Toutes les chaînes de chiffres que l'agent a le droit de reprendre. ⛔ Ne lève jamais."""
    connus: list[str] = []
    try:
        paroles: list[str] = []
        for message in messages or []:
            if not isinstance(message, Mapping) or message.get("role") == "assistant":
                continue
            suites = _suites_de(_contenu(message))
            connus.extend(suites)
            if message.get("role") == "user":
                paroles.extend(suites)
        # Un numéro dicté en plusieurs fois (deux tours) est connu d'un seul tenant.
        if paroles:
            connus.append("".join(paroles))
        contexte = getattr(moteur, "_gathered_context", None)
        if isinstance(contexte, dict):
            connus.extend(numeros_dictes(contexte))
            for trace in contexte.get(CLE_NOMBRES_LUS) or []:
                if isinstance(trace, Mapping):
                    connus.extend(_suites_de(str(trace.get("ecrit") or "")))
            fiche = getattr(moteur, "_fiche", None)
            for champ in tuple(getattr(fiche, "champs", None) or ()):
                if getattr(champ, "rempli_par_outil", None):
                    continue  # venu d'un outil, non de la personne : ce que l'outil a rendu est déjà dans les messages
                valeur = contexte.get(getattr(champ, "nom", None))
                if isinstance(valeur, (str, int)) and not isinstance(valeur, bool):
                    connus.extend(_suites_de(str(valeur)))
        appel = getattr(moteur, "_call_context_vars", None)
        if isinstance(appel, Mapping):
            for cle in ("caller_number", "called_number"):
                if c := _chiffres(str(appel.get(cle) or "")):
                    connus.append(c)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[numero] chiffres connus illisibles : {erreur!r}")
    return connus


def numero_inconnu(texte: str, connus: list[str]) -> str | None:
    """Le premier numéro de ``texte`` que ``connus`` ne contient pas (en entier, sous l'une de ses deux formes)."""
    formes_connues: set[str] = set()
    for c in connus:
        formes_connues |= _formes(c)
    for suite in suites_de_chiffres(texte):
        if not any(f in connu for f in _formes(suite) for connu in formes_connues):
            return suite
    return None


class VerificateurDeNumero:
    """Contrôle une réplique complète avant la voix. Branché sur le cerveau de l'agent (``brancher_le_numero_jamais_dicte``),
    lu par ``reponse_avalee.RepliqueVerifiee``. Même interface que ``VerificateurDeReplique``."""

    def __init__(self, moteur: Any, agent: Any):
        self.moteur = moteur
        self.agent = agent

    def controler(self, texte: str, messages: Any = None) -> Retenue | None:
        try:
            if len(_chiffres(texte)) < CHIFFRES_MIN:
                return None
            inconnu = numero_inconnu(texte, chiffres_connus(self.moteur, messages))
            if inconnu is None:
                return None
            self._tracer(texte, inconnu)
            return Retenue(RAISON_NUMERO, inconnu, CONSIGNE_NUMERO)
        except Exception as erreur:  # noqa: BLE001 -- dans le doute, la réplique passe
            logger.warning(f"[numero] réplique non contrôlée : {erreur!r}")
            return None

    def _tracer(self, texte: str, numero: str) -> None:
        """La réplique retenue, dans la fiche de l'appel (lue plus tard par l'analyse). ⛔ Ne lève jamais."""
        try:
            contexte = getattr(self.moteur, "_gathered_context", None)
            if not isinstance(contexte, dict):
                return
            noeud = getattr(self.agent, "current_node", None)
            contexte.setdefault(CLE_TRACE, []).append(
                {
                    "raison": RAISON_NUMERO,
                    "numero": numero,
                    "replique": (texte or "")[:600],
                    "etape": getattr(noeud, "name", None),
                }
            )
        except Exception:  # noqa: BLE001
            pass


def case_allumee(agent: Any, moteur: Any) -> bool:
    """La case « Numéro jamais dicté » de l'agent : posée à ``True`` seulement. Éteinte par défaut."""
    try:
        reglages = getattr(agent, "reglages", None) or getattr(moteur, "reglages_appel", None) or {}
        return reglages.get(CLE_NUMERO_JAMAIS_DICTE) is True
    except Exception:  # noqa: BLE001
        return False


def brancher_le_numero_jamais_dicte(moteur: Any, agent: Any, noeud: Any) -> bool:
    """Pose (ou retire) le contrôle sur le cerveau de ``agent`` pour son étape : case allumée, étape qui n'est pas une fin,
    même sans action. ⛔ Ne lève jamais."""
    try:
        from api.services.pipecat.reponse_avalee import ATTRIBUT_NUMERO

        llm = getattr(agent, "llm", None)
        if llm is None:
            return False
        actif = not getattr(noeud, "is_end", False) and case_allumee(agent, moteur)
        setattr(llm, ATTRIBUT_NUMERO, VerificateurDeNumero(moteur, agent) if actif else None)
        return actif
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[numero] contrôle du numéro non branché : {erreur!r}")
        return False
