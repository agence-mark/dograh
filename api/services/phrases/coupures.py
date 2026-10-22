"""[.mark] Chantier voix-soniox, D20 : les phrases du code coupées par l'appelant, comptées au mot près.

Le défaut (note ``coupure-phrases-du-code``, 21/10) : une phrase du code jouée depuis son enregistrement arrive
**en entier** dans l'historique du modèle avant que le son parte (``play_audio`` : un seul texte, puis le son), et
le compte rendu de l'outil dit « L'appelant a entendu : « <la phrase entière> ». Ne la répète pas. » dès la mise
en file, avant même que la lecture commence. Coupée par l'appelant, la phrase est donc comptée entendue deux fois,
ordre de ne pas la redire à l'appui : le modèle croit avoir promis le rappel et n'y revient pas.

Ce module garde le minutage des mots de chaque phrase (``Son.mots``, relevé à la fabrique, ``sons.py``) et, à la
requête suivante, dit au modèle **ce qui a été réellement joué** :

1. **dans la COPIE des messages** envoyée au modèle (jamais l'historique, même procédé que
   ``ordre_outil_puis_parole``) ;
2. la ligne du compte rendu « L'appelant a entendu » est **réécrite** (jamais retirée : mesure 13 du 21/10, sans
   elle 30/30 répétitions, avec elle 0/30) : la part jouée, ou « L'appelant n'a rien entendu de la phrase. » ;
3. la réplique de l'agent qui porte la phrase est ramenée au dernier mot joué, comme Pipecat le fait pour la voix
   normale ; coupée avant le premier mot, elle disparaît (ou, juste derrière un résultat d'outil, devient une ligne
   entre crochets : un message de l'appelant ne doit jamais suivre directement un résultat, voir
   ``ordre_outil_puis_parole``).

Le compte rendu reste rendu **tout de suite** (un outil est annulé quand la personne coupe) : seule la copie change,
à la requête qui suit.

La part jouée = les mots dont le début est antérieur à l'instant de la coupure, mesuré depuis l'instant où la sortie
a laissé passer le début de la lecture (``SpeechPlayback.started_at`` / ``ended_at``) : même horloge, même
précision que les mots de la voix normale (pas une confirmation de lecture de Twilio : les ``mark`` ne sont pas
codés). **Pas de repli au prorata du temps** : sans minutage (voix qui n'en donne pas, phrase dite par la voix de
l'appel), la part jouée est dite **inconnue** et la copie le dit (« on ne sait pas jusqu'où »).

Aucun vocabulaire métier. Un appel sans phrase coupée : la requête part à l'octet comme avant. ⛔ Ne lève jamais.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from loguru import logger

from api.services.phrases.compte_rendu import ligne_entendue

ETAT_TOUT = "tout"  # coupée après le dernier mot (ou jouée en entier) : rien ne change
ETAT_DEBUT = "debut"  # coupée au milieu : seule la part jouée compte
ETAT_RIEN = "rien"  # coupée avant le premier mot
ETAT_INCONNU = "inconnu"  # coupée, sans minutage : on ne sait pas jusqu'où

LIGNE_RIEN = "L'appelant n'a rien entendu de la phrase."
# La réplique d'une phrase non entendue, quand elle suit directement un résultat d'outil : un message de
# l'appelant ne doit jamais suivre un résultat (400 chez Mistral via Scaleway, run 1469). Entre crochets et
# courte : le filtre du texte du cerveau la retire de la voix si le modèle la recopie.
REPLIQUE_RIEN = "[La phrase n'a pas été entendue.]"
# Les phrases gardées par appel (une phrase du code se dit rarement plus de quelques fois).
MAX_PHRASES = 60


def ligne_pour(etat: str, texte: str, joue: str) -> str:
    """La ligne qui remplace « L'appelant a entendu » d'une phrase coupée. Un constat, jamais un ordre."""
    if etat == ETAT_RIEN:
        return LIGNE_RIEN
    if etat == ETAT_DEBUT:
        return f"L'appelant a été coupé pendant la phrase : il n'a entendu que « {joue} »."
    return (
        f"L'appelant a été coupé pendant la phrase : « {texte.strip()} ». "
        "On ne sait pas jusqu'où il l'a entendue."
    )


@dataclass(frozen=True)
class Partie:
    """Ce qui a été joué d'une phrase : l'état et, au milieu (``debut``), le texte joué."""

    etat: str
    joue: str = ""


def _prefixe(texte: str, mots_joues: list[str]) -> str:
    """Le début de ``texte`` qui couvre ``mots_joues`` (dans l'ordre, sans tenir compte de la casse). Un mot
    introuvable (la voix a dit autre chose que le texte) : les mots joués eux-mêmes, mis bout à bout."""
    curseur = 0
    fin = 0
    for mot in mots_joues:
        propre = mot.strip()
        if not propre:
            continue
        motif = r"(?<!\w)" + re.escape(propre) + (r"(?!\w)" if propre[-1].isalnum() else "")
        trouve = re.compile(motif, re.IGNORECASE).search(texte, curseur)
        if trouve is None:
            return " ".join(m.strip() for m in mots_joues if m.strip())
        curseur = fin = trouve.end()
    return texte[:fin].rstrip()


def partie_jouee(
    texte: str, mots: tuple[tuple[str, float], ...], ecoule_s: float | None
) -> Partie:
    """La part jouée de ``texte`` quand la lecture a été coupée ``ecoule_s`` secondes après son début.

    ``ecoule_s`` ``None`` : la lecture n'avait pas commencé (rien n'est sorti). ``mots`` vide : aucun minutage,
    jamais d'estimation au temps. Un mot est joué si son début est antérieur ou égal à la coupure."""
    if ecoule_s is None:
        return Partie(ETAT_RIEN)
    if not mots:
        return Partie(ETAT_INCONNU)
    joues = [mot for mot, debut in mots if debut <= ecoule_s]
    if not joues:
        return Partie(ETAT_RIEN)
    if len(joues) >= len(mots):
        return Partie(ETAT_TOUT)
    joue = _prefixe(texte, joues)
    return Partie(ETAT_DEBUT, joue) if joue else Partie(ETAT_RIEN)


@dataclass(frozen=True)
class Coupure:
    texte: str
    partie: Partie


@dataclass
class Entree:
    """Une phrase dite : son texte, son minutage, sa lecture, et où elle a laissé une trace dans ce que lit le
    modèle (la réplique de l'historique, la ligne du compte rendu d'un résultat d'outil)."""

    texte: str
    mots: tuple[tuple[str, float], ...]
    parole: Any
    historique: bool = True
    compte_rendu: bool = False


class RegistreDesCoupures:
    """Les phrases du code dites dans l'appel (texte, minutage, lecture), lues à la requête suivante du modèle
    pour savoir lesquelles ont été coupées et jusqu'où. Un par appel (``moteur.phrases.coupures``). Chaque phrase
    garde SA place : une même phrase dite deux fois n'est réécrite que là où elle a été coupée."""

    def __init__(self) -> None:
        self._dites: list[Entree] = []

    def noter(
        self, texte: str, mots: Iterable[tuple[str, float]] | None, parole: Any, historique: bool = True
    ) -> None:
        """Une phrase du code part à la voix. ``mots`` : son minutage (vide si inconnu). ``historique`` : son
        texte entre dans l'historique du modèle. ⛔ Ne lève jamais."""
        try:
            if not isinstance(texte, str) or not texte.strip() or parole is None:
                return
            self._dites.append(Entree(texte, tuple(mots or ()), parole, bool(historique)))
            del self._dites[:-MAX_PHRASES]
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[coupures] phrase non notée : {erreur!r}")

    def marquer_compte_rendu(self, parole: Any) -> None:
        """Cette lecture est citée par la ligne « L'appelant a entendu » d'un résultat d'outil."""
        for entree in self._dites:
            if entree.parole is parole:
                entree.compte_rendu = True

    @staticmethod
    def _coupee(parole: Any) -> bool:
        return getattr(getattr(parole, "outcome", None), "name", None) == "INTERRUPTED"

    @staticmethod
    def _ecoule(parole: Any) -> float | None:
        debut = getattr(parole, "started_at", None)
        fin = getattr(parole, "ended_at", None)
        if not isinstance(debut, (int, float)) or not isinstance(fin, (int, float)):
            return None
        return max(0.0, float(fin) - float(debut))

    def _coupure_de(self, entree: Entree) -> Coupure | None:
        if not self._coupee(entree.parole):
            return None
        partie = partie_jouee(entree.texte, entree.mots, self._ecoule(entree.parole))
        return None if partie.etat == ETAT_TOUT else Coupure(entree.texte, partie)

    def par_texte(self) -> dict[str, list[tuple[Entree, Coupure | None]]]:
        """Pour chaque texte dont au moins une lecture a été coupée : toutes ses lectures, dans l'ordre où
        elles ont été dites, chacune avec sa coupure (``None`` : entendue, ou coupée après le dernier mot)."""
        resultat: dict[str, list[tuple[Entree, Coupure | None]]] = {}
        for entree in self._dites:
            resultat.setdefault(entree.texte, []).append((entree, self._coupure_de(entree)))
        return {t: v for t, v in resultat.items() if any(c is not None for _, c in v)}

    def coupees(self) -> list[Coupure]:
        """Les phrases coupées dont la part jouée n'est pas « tout »."""
        return [c for v in self.par_texte().values() for _, c in v if c is not None]


# -- la réécriture de la copie ---------------------------------------------------------------


def _echappe(texte: str) -> str:
    """Le texte tel qu'il s'écrit au milieu d'une chaîne JSON (le résultat d'un outil est du JSON)."""
    return json.dumps(texte, ensure_ascii=False)[1:-1]


def _remplacer_le_dernier(contenu: str, ancien: str, nouveau: str) -> str | None:
    i = contenu.rfind(ancien)
    if i < 0:
        return None
    return (contenu[:i] + nouveau + contenu[i + len(ancien):]).strip()


def _dans_le_texte(contenu: Any, fonction) -> Any:
    """``fonction`` appliquée au texte d'un contenu (chaîne, ou liste de morceaux ``{"text": …}``) ; ``None``
    d'un morceau = inchangé. Rend le contenu neuf, ou le même objet si rien n'a changé."""
    if isinstance(contenu, str):
        neuf = fonction(contenu)
        return contenu if neuf is None else neuf
    if isinstance(contenu, list):
        morceaux = []
        change = False
        for morceau in contenu:
            if isinstance(morceau, dict) and isinstance(morceau.get("text"), str):
                neuf = fonction(morceau["text"])
                if neuf is not None and neuf != morceau["text"]:
                    morceau = {**morceau, "text": neuf}
                    change = True
            morceaux.append(morceau)
        return morceaux if change else contenu
    return contenu


def _texte_vide(contenu: Any) -> bool:
    if isinstance(contenu, str):
        return not contenu.strip()
    if isinstance(contenu, list):
        return not any(
            isinstance(m, dict) and isinstance(m.get("text"), str) and m["text"].strip()
            for m in contenu
        )
    return False


def _est_un_resultat(message: Any) -> bool:
    return isinstance(message, dict) and (
        message.get("role") == "tool" or message.get("type") == "function_call_output"
    )


def _est_une_parole(message: Any) -> bool:
    return (
        isinstance(message, dict)
        and message.get("role") == "assistant"
        and not message.get("tool_calls")
        and message.get("type") != "function_call"
    )


def _reecrire_un_resultat(contenu: str, coupure: Coupure) -> str | None:
    """La ligne « L'appelant a entendu » de cette phrase remplacée (jamais retirée), puis ce que le résultat
    garde de la phrase entière (``said_to_caller``) ramené à la part jouée."""
    texte, partie = coupure.texte, coupure.partie
    neuf = contenu
    ancienne = ligne_entendue(texte)
    nouvelle = ligne_pour(partie.etat, texte, partie.joue)
    for vieux, jeune in ((ancienne, nouvelle), (_echappe(ancienne), _echappe(nouvelle))):
        if vieux in neuf:
            neuf = neuf.replace(vieux, jeune)
    if partie.etat in (ETAT_DEBUT, ETAT_RIEN):
        reste = partie.joue if partie.etat == ETAT_DEBUT else ""
        for vieux, jeune in ((texte, reste), (_echappe(texte), _echappe(reste))):
            if vieux and vieux in neuf:
                neuf = neuf.replace(vieux, jeune)
    return None if neuf == contenu else neuf


def _texte_du_contenu(contenu: Any) -> str:
    if isinstance(contenu, str):
        return contenu
    if isinstance(contenu, list):
        return "\n".join(m["text"] for m in contenu if isinstance(m, dict) and isinstance(m.get("text"), str))
    return ""


def _assigner(places: list[int], lectures: list[Coupure | None]) -> dict[int, Coupure]:
    """Rattache chaque place trouvée dans la requête à SA lecture, en comptant depuis la fin : ce qui manque
    à la requête (historique compacté, phrase sans trace) manque d'abord parmi les plus anciennes."""
    resultat: dict[int, Coupure] = {}
    for k in range(1, min(len(places), len(lectures)) + 1):
        if lectures[-k] is not None:
            resultat[places[-k]] = lectures[-k]
    return resultat


def reecrire_les_messages(messages: list, par_texte: dict[str, list[tuple[Entree, Coupure | None]]]) -> list:
    """Une copie de ``messages`` où chaque phrase coupée dit ce qui a été joué, et seulement elle : la même
    phrase entendue en entier ailleurs dans l'appel reste telle quelle. ``messages`` et ses messages ne sont
    jamais modifiés ; sans correspondance, le même objet est rendu."""
    repliques: dict[int, list[Coupure]] = {}
    resultats: dict[int, list[Coupure]] = {}
    for texte, lectures in par_texte.items():
        variantes = (texte, _echappe(texte), ligne_entendue(texte), _echappe(ligne_entendue(texte)))
        places_repliques, places_resultats = [], []
        for i, message in enumerate(messages):
            if _est_une_parole(message) and texte in _texte_du_contenu(message.get("content")):
                places_repliques.append(i)
            elif _est_un_resultat(message):
                cle = "content" if "content" in message else "output"
                if any(v in _texte_du_contenu(message.get(cle)) for v in variantes):
                    places_resultats.append(i)
        for i, c in _assigner(places_repliques, [c for e, c in lectures if e.historique]).items():
            repliques.setdefault(i, []).append(c)
        for i, c in _assigner(places_resultats, [c for e, c in lectures if e.compte_rendu]).items():
            resultats.setdefault(i, []).append(c)
    sortie: list = []
    change = False
    for i, message in enumerate(messages):
        neuf = message
        if i in resultats:
            for cle in ("content", "output"):
                if cle in message:
                    contenu = message[cle]
                    for coupure in resultats[i]:
                        contenu = _dans_le_texte(contenu, lambda t, c=coupure: _reecrire_un_resultat(t, c))
                    if contenu is not message[cle]:
                        neuf = {**neuf, cle: contenu}
        elif i in repliques:
            contenu = message.get("content")
            for coupure in repliques[i]:
                if coupure.partie.etat not in (ETAT_DEBUT, ETAT_RIEN):
                    continue  # inconnue : l'historique est celui de Pipecat, on n'y touche pas
                joue = coupure.partie.joue if coupure.partie.etat == ETAT_DEBUT else ""
                contenu = _dans_le_texte(
                    contenu, lambda t, c=coupure, j=joue: _remplacer_le_dernier(t, c.texte, j)
                )
            if contenu is not message.get("content"):
                if _texte_vide(contenu):
                    if sortie and _est_un_resultat(sortie[-1]):
                        neuf = {**message, "content": REPLIQUE_RIEN}
                    else:
                        change = True
                        continue  # coupée avant le premier mot : rien dans l'historique, comme pour la voix
                else:
                    neuf = {**message, "content": contenu}
        if neuf is not message:
            change = True
        sortie.append(neuf)
    return sortie if change else messages


def reecrire_les_coupures(params: Any, registre: RegistreDesCoupures | None) -> Any:
    """Les paramètres d'une requête de conversation (``messages`` ou ``input``) avec les phrases coupées
    réécrites. Sans phrase coupée : ``params`` rendu tel quel. ⛔ Ne lève jamais."""
    try:
        if not isinstance(params, dict) or registre is None:
            return params
        par_texte = registre.par_texte()
        if not par_texte:
            return params
        for cle in ("messages", "input"):
            if isinstance(params.get(cle), list):
                params[cle] = reecrire_les_messages(params[cle], par_texte)
        return params
    except Exception as erreur:  # noqa: BLE001 -- dans le doute, la requête part comme avant
        logger.warning(f"[coupures] phrases coupées non réécrites : {erreur!r}")
        return params


_MARQUE = "_mark_coupures_branchees"


def brancher_les_coupures(engine: Any, llm: Any) -> bool:
    """Le service de conversation ``llm`` réécrit les phrases coupées de l'appel dans chaque requête. Une
    fois par service. À poser AVANT la trace du modèle (qui photographie la requête telle qu'elle part).
    Faux sans diseur, sans service ou sans constructeur de requête. ⛔ Ne lève jamais."""
    try:
        diseur = (getattr(engine, "__dict__", None) or {}).get("phrases")
        registre = getattr(diseur, "coupures", None)
        if not isinstance(registre, RegistreDesCoupures) or llm is None:
            return False
        if not hasattr(llm, "build_chat_completion_params") or getattr(llm, _MARQUE, False) is True:
            return False
        construire = llm.build_chat_completion_params

        def build_chat_completion_params(params_from_context):
            return reecrire_les_coupures(construire(params_from_context), registre)

        llm.build_chat_completion_params = build_chat_completion_params
        setattr(llm, _MARQUE, True)
        return True
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[coupures] réécriture non branchée : {erreur!r}")
        return False
