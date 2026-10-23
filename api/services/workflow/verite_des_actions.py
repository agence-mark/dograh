"""[.mark] Lot 5 de correctifs-apres-banc-commun : la vérité des actions (K7, V4).

Trois gestes, tous rattachés à l'enveloppe des actions et au flux du cerveau, aucun mot de métier :

- **Garde de réservation (K7)** : une action « d'écriture » (un outil nommé par le champ ``rempli_par_outil``
  d'un champ de la fiche) appelée avec une date qu'aucun résultat d'une autre action de l'appel n'a donnée
  n'est pas exécutée : elle rend ``incomplet`` (« cherche d'abord ce jour »). Tant qu'aucune date n'a été
  trouvée dans l'appel, la garde se tait (une réservation sans recherche reste possible, zéro perte).
  La recherche, elle, passe toujours : l'appelant peut changer de jour.
- **Réplique retenue (K7 étendu)** : une réplique du modèle qui dit une date qu'aucun outil, aucune parole de
  l'appelant ni aucune consigne ne donne, ou qui annonce une action faite (« c'est réservé ») sans résultat
  d'outil qui la fonde, est retenue ; le modèle est relancé UNE fois avec la consigne de ce qu'il a fait. La
  relance est rendue telle quelle, quoi qu'elle dise (jamais deux relances). Voir ``reponse_avalee.RepliqueVerifiee``.
- **Réservation identique (V4)** : une action d'écriture déjà confirmée avec les MÊMES arguments rend le
  résultat connu sans rappeler l'outil. Une autre date, une donnée corrigée (autres arguments), une annulation
  (autre action réussie depuis, ou champ de la fiche changé) passent toujours.

Case par étape : ``verite_des_actions`` (données de l'étape), allumée par défaut sur une étape qui offre un outil
d'action ; seul ``False`` l'éteint. La case commande les trois gestes.

⛔ Ne lève jamais : dans le doute, l'action s'exécute et la réplique passe, comme avant.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from loguru import logger

CLE_JOURNAL = "mark_journal_des_actions"
MAX_JOURNAL = 200
FUSEAU = ZoneInfo("Europe/Paris")

# Les statuts d'un résultat d'outil qui disent « pas fait » en plus de ceux de l'enveloppe.
_REFUS = frozenset({"refused", "refuse", "refusé", "unavailable", "indisponible", "denied"})

# ---------------------------------------------------------------------------------------------------------
# Les dates : (mois, jour). Le nom des mois est de la langue, pas du métier.
# ---------------------------------------------------------------------------------------------------------

MOIS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "décembre": 12, "decembre": 12,
}
NOMS_DES_MOIS = {
    1: "janvier", 2: "février", 3: "mars", 4: "avril", 5: "mai", 6: "juin", 7: "juillet",
    8: "août", 9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre",
}
_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_BARRE = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?:/\d{2,4})?(?![\d/])")
_MOIS_DIT = re.compile(r"\b(" + "|".join(MOIS) + r")\b", re.IGNORECASE)
# Les jours qui précèdent un mois : « le 3 », « 3 et 7 », « du 3 au 7 », « le 3 et le 7 », « 1er ».
_JOURS_AVANT = re.compile(
    r"((?:\d{1,2}(?:er)?(?:\s*(?:,|et|ou|au|à|-)\s*(?:le\s+)?|\s+(?:et|ou)\s+le\s+))*\d{1,2}(?:er)?)\s*(?:de\s+)?$",
    re.IGNORECASE,
)

Date = tuple[int, int]


def _valide(mois: int, jour: int) -> bool:
    return 1 <= mois <= 12 and 1 <= jour <= 31


def dates_dans(texte: Any) -> set[Date]:
    """Les dates (mois, jour) écrites dans ``texte`` (ISO, « 3/11 », « le 3 et le 7 novembre »). Le jour de la
    semaine seul n'est pas une date. ⛔ Ne lève jamais."""
    try:
        if not isinstance(texte, str):
            texte = json.dumps(texte, ensure_ascii=False, default=str)
        trouvees: set[Date] = set()
        for m in _ISO.finditer(texte):
            if _valide(int(m.group(2)), int(m.group(3))):
                trouvees.add((int(m.group(2)), int(m.group(3))))
        for m in _BARRE.finditer(texte):
            if _valide(int(m.group(2)), int(m.group(1))):
                trouvees.add((int(m.group(2)), int(m.group(1))))
        for m in _MOIS_DIT.finditer(texte):
            mois = MOIS[m.group(1).casefold()]
            avant = texte[max(0, m.start() - 60) : m.start()]
            jours = _JOURS_AVANT.search(avant)
            if jours is None:
                continue
            for j in re.findall(r"\d{1,2}", jours.group(1)):
                if _valide(mois, int(j)):
                    trouvees.add((mois, int(j)))
        return trouvees
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[verite] dates illisibles : {erreur!r}")
        return set()


def libelle_de_la_date(date: Date) -> str:
    return f"{date[1]} {NOMS_DES_MOIS.get(date[0], date[0])}"


# ---------------------------------------------------------------------------------------------------------
# Le journal des actions de l'appel (rempli par l'enveloppe, lu par la garde, le V4 et la réplique)
# ---------------------------------------------------------------------------------------------------------


@dataclass
class ActionVue:
    nom: str
    arguments: dict
    resultat: Any
    reussie: bool
    dates: frozenset = frozenset()
    ecrits: dict = field(default_factory=dict)


def journal_de(moteur: Any) -> list:
    """Le journal des actions de l'appel (créé au besoin, sur le vrai moteur même vu à travers le moteur muet du
    fond). Une liste jetable si le moteur ne se laisse pas écrire."""
    journal = getattr(moteur, CLE_JOURNAL, None)
    if isinstance(journal, list):
        return journal
    journal = []
    try:
        setattr(moteur, CLE_JOURNAL, journal)
    except Exception:  # noqa: BLE001
        pass
    return journal


def _lire(resultat: Any) -> Any:
    if isinstance(resultat, str):
        try:
            return json.loads(resultat)
        except (TypeError, ValueError):
            return resultat
    return resultat


def resultat_reussi(resultat: Any) -> bool:
    """Le résultat dit-il que l'action est faite ? Ni échec, ni « incomplet », ni refus."""
    try:
        from api.services.workflow.enveloppe_des_actions import _reponse, est_un_echec

        if est_un_echec(resultat):
            return False
        lu = _lire(resultat)
        for niveau in (lu, _reponse(lu)):
            if isinstance(niveau, dict):
                for cle in ("statut", "status"):
                    valeur = niveau.get(cle)
                    if isinstance(valeur, str) and valeur.strip().casefold() in _REFUS:
                        return False
        return True
    except Exception:  # noqa: BLE001
        return False


def noter_l_action(moteur: Any, nom: str, arguments: Any, resultat: Any, ecrits: Mapping[str, Any]) -> None:
    """L'enveloppe note le résultat final d'une action. ⛔ Ne lève jamais."""
    try:
        journal = journal_de(moteur)
        journal.append(
            ActionVue(
                nom=nom,
                arguments=dict(arguments) if isinstance(arguments, Mapping) else {},
                resultat=resultat,
                reussie=resultat_reussi(resultat),
                dates=frozenset(dates_dans(resultat)),
                ecrits=dict(ecrits),
            )
        )
        del journal[:-MAX_JOURNAL]
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[verite] action {nom} non notée : {erreur!r}")


# ---------------------------------------------------------------------------------------------------------
# La case de l'étape et les actions d'écriture
# ---------------------------------------------------------------------------------------------------------


def case_allumee(agent: Any) -> bool:
    """La case « vérité des actions » de l'étape de ``agent`` (ou de l'agent qui a confié le travail au fond)
    n'est pas éteinte. Seul ``False`` l'éteint."""
    try:
        noeud = getattr(agent, "current_node", None)
        if noeud is None:
            noeud = getattr(getattr(agent, "agent_qui_confie", None), "current_node", None)
        return getattr(noeud, "verite_des_actions", None) is not False
    except Exception:  # noqa: BLE001
        return True


def outils_d_ecriture(moteur: Any) -> frozenset:
    """Les noms (normalisés) des actions qui remplissent un champ de la fiche (``rempli_par_outil``)."""
    try:
        from api.services.workflow.enveloppe_des_actions import _normaliser

        reglages = getattr(moteur, "_fiche", None)
        return frozenset(
            _normaliser(c.rempli_par_outil)
            for c in tuple(getattr(reglages, "champs", None) or ())
            if getattr(c, "rempli_par_outil", None)
        )
    except Exception:  # noqa: BLE001
        return frozenset()


def _est_une_ecriture(moteur: Any, nom: str) -> bool:
    try:
        from api.services.workflow.enveloppe_des_actions import _normaliser

        return _normaliser(nom) in outils_d_ecriture(moteur)
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------------------------------------
# K7 : la garde de réservation
# ---------------------------------------------------------------------------------------------------------

CONSIGNE_CHERCHER = (
    "Cette date n'a pas été donnée par la recherche : cherche d'abord ce jour, puis réserve une date "
    "qu'elle a donnée."
)


def garde_de_reservation(moteur: Any, agent: Any, nom_outil: str, arguments: Any) -> dict | None:
    """K7 : ``{"statut": "incomplet", ...}`` si une action d'écriture reçoit une date que les résultats des
    autres actions de l'appel n'ont pas donnée. ``None`` : l'action s'exécute. ⛔ Ne lève jamais."""
    try:
        if not case_allumee(agent) or not _est_une_ecriture(moteur, nom_outil):
            return None
        demandees = dates_dans(arguments if isinstance(arguments, Mapping) else {})
        if not demandees:
            return None
        trouvees: set[Date] = set()
        for vue in journal_de(moteur):
            if vue.nom != nom_outil and vue.reussie:
                trouvees |= vue.dates
        if not trouvees:
            return None
        inconnues = sorted(demandees - trouvees)
        if not inconnues:
            return None
        logger.info(f"[verite] {nom_outil} retenu : {', '.join(map(libelle_de_la_date, inconnues))} non trouvées")
        return {
            "statut": "incomplet",
            "manque": [f"une date donnée par la recherche ({libelle_de_la_date(d)} ne l'est pas)" for d in inconnues],
            "consigne": CONSIGNE_CHERCHER,
        }
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[verite] garde de réservation illisible : {erreur!r}")
        return None


# ---------------------------------------------------------------------------------------------------------
# V4 : la réservation identique
# ---------------------------------------------------------------------------------------------------------


def _normalise(valeur: Any) -> Any:
    if isinstance(valeur, str):
        return " ".join(valeur.split()).casefold()
    if isinstance(valeur, Mapping):
        return {str(k): _normalise(v) for k, v in sorted(valeur.items(), key=lambda kv: str(kv[0]))}
    if isinstance(valeur, (list, tuple)):
        return [_normalise(v) for v in valeur]
    return valeur


def memes_arguments(a: Any, b: Any) -> bool:
    try:
        return _normalise(a) == _normalise(b)
    except Exception:  # noqa: BLE001
        return False


def resultat_deja_confirme(moteur: Any, agent: Any, nom_outil: str, arguments: Any) -> Any | None:
    """V4 : le résultat de la même action d'écriture, déjà réussie avec les mêmes arguments, si rien depuis ne
    l'a défaite (une autre action réussie qui n'est pas une simple recherche de dates, ou le champ de la fiche
    qu'elle avait écrit qui a changé). ``None`` : l'action s'exécute. ⛔ Ne lève jamais."""
    try:
        if not case_allumee(agent) or not _est_une_ecriture(moteur, nom_outil):
            return None
        journal = journal_de(moteur)
        dernier = None
        for i in range(len(journal) - 1, -1, -1):
            if journal[i].nom == nom_outil and journal[i].reussie:
                dernier = i
                break
        if dernier is None:
            return None
        vue = journal[dernier]
        if not memes_arguments(vue.arguments, arguments if isinstance(arguments, Mapping) else {}):
            return None
        for suite in journal[dernier + 1 :]:
            if suite.nom != nom_outil and suite.reussie and not suite.dates:
                return None
        fiche = getattr(moteur, "_gathered_context", None)
        if isinstance(fiche, dict):
            for champ, valeur in vue.ecrits.items():
                if fiche.get(champ) != valeur:
                    return None
        logger.info(f"[verite] {nom_outil} déjà confirmé avec les mêmes arguments : résultat connu rendu")
        resultat = _lire(vue.resultat)
        if isinstance(resultat, dict):
            return {**resultat, "deja_confirme": True}
        return vue.resultat
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[verite] réservation identique illisible : {erreur!r}")
        return None


# ---------------------------------------------------------------------------------------------------------
# K7 étendu : la réplique retenue
# ---------------------------------------------------------------------------------------------------------

# Les participes passés qui disent « c'est fait » (la LISTE DE FORMULATIONS de D-23 : une donnée, un seul endroit).
# Aucun nom de chose : « est pris/réservé/confirmé… » vaut pour tout ce qu'une action peut faire. Volontairement
# absents : « noté », « enregistré », « transmis » (la fiche s'en charge, sans outil d'action).
PARTICIPES_D_ACTION = (
    "pris", "réservé", "confirmé", "programmé", "planifié", "fixé", "validé", "annulé", "déplacé",
    "modifié", "envoyé",
)
_PARTICIPES = "|".join(re.escape(p) for p in PARTICIPES_D_ACTION)
_ACTION_FAITE = re.compile(
    r"(?:\b(?:est|sont|c['’]est|a\s+été|ont\s+été|était)\s+(?:bien\s+|déjà\s+|maintenant\s+|donc\s+|à\s+présent\s+)?"
    rf"(?:{_PARTICIPES})(?:e|es|s)?\b"
    r"|\b(?:j['’]ai|nous\s+avons|on\s+a)\s+(?:bien\s+|déjà\s+)?"
    rf"(?:{_PARTICIPES.replace('pris|', '')})\b)",
    re.IGNORECASE,
)

CONSIGNE_DATE = (
    "Ta réponse a été retenue : elle donnait une date qu'aucun résultat d'outil, aucune parole de la personne ne "
    "donne. Ne donne aucune date que tu n'as pas reçue : appelle l'outil qui la cherche, ou dis que tu vérifies."
)
CONSIGNE_ACTION = (
    "Ta réponse a été retenue : elle annonçait une action faite alors qu'aucun outil ne l'a faite. Appelle l'outil "
    "qui la fait, ou ne dis pas qu'elle est faite."
)
RAISON_DATE = "date_non_trouvee"
RAISON_ACTION = "action_sans_resultat"


@dataclass(frozen=True)
class Retenue:
    raison: str
    detail: str
    consigne: str
    # Lot 6 (K8) : l'outil à appeler obligatoirement à la relance (position « relance » du déclenchement de l'action).
    outil: str | None = None


def _contenu(message: Any) -> str:
    contenu = message.get("content") if isinstance(message, Mapping) else None
    if isinstance(contenu, str):
        return contenu
    if isinstance(contenu, list):
        return " ".join(
            p.get("text", "") for p in contenu if isinstance(p, Mapping) and isinstance(p.get("text"), str)
        )
    return ""


def dates_connues(moteur: Any, messages: Any) -> set[Date]:
    """Les dates qu'une réplique a le droit de dire : celles des résultats d'actions, de tout message qui n'est
    pas une réplique de l'agent (parole de la personne, résultat d'outil ou de travail, consigne), de la fiche, et
    celle d'aujourd'hui."""
    connues: set[Date] = set()
    maintenant = datetime.now(FUSEAU)
    connues.add((maintenant.month, maintenant.day))
    for vue in journal_de(moteur):
        connues |= set(vue.dates)
    for message in messages or []:
        if isinstance(message, Mapping) and message.get("role") != "assistant":
            connues |= dates_dans(_contenu(message))
    fiche = getattr(moteur, "_gathered_context", None)
    if isinstance(fiche, dict):
        connues |= dates_dans({k: v for k, v in fiche.items() if isinstance(v, (str, int, float))})
    return connues


def une_action_a_reussi(moteur: Any) -> bool:
    """Un résultat d'outil fonde-t-il « c'est fait » ? Une action d'écriture réussie, ou une action réussie qui
    ne se contente pas de lister des dates (une recherche ne fonde pas « c'est réservé »)."""
    try:
        ecritures = outils_d_ecriture(moteur)
        from api.services.workflow.enveloppe_des_actions import _normaliser

        for vue in journal_de(moteur):
            if not vue.reussie:
                continue
            if _normaliser(vue.nom) in ecritures or not vue.dates:
                return True
        return False
    except Exception:  # noqa: BLE001
        return True


def _phrases(texte: str) -> list[str]:
    return [p for p in re.split(r"(?<=[.!?…])\s+|\n+", texte) if p.strip()]


class VerificateurDeReplique:
    """Contrôle une réplique complète (texte seul) avant qu'elle parte à la voix. Branché sur le cerveau de
    l'agent (``brancher_la_verite_des_actions``), lu par ``reponse_avalee.RepliqueVerifiee``."""

    def __init__(self, moteur: Any, agent: Any):
        self.moteur = moteur
        self.agent = agent

    def controler(self, texte: str, messages: Any = None) -> Retenue | None:
        try:
            if not case_allumee(self.agent):
                return None
            dites = dates_dans(texte)
            if dites:
                inconnues = sorted(dites - dates_connues(self.moteur, messages))
                if inconnues:
                    return Retenue(
                        RAISON_DATE, ", ".join(libelle_de_la_date(d) for d in inconnues), CONSIGNE_DATE
                    )
            for phrase in _phrases(texte):
                if phrase.rstrip().endswith("?"):
                    continue
                m = _ACTION_FAITE.search(phrase)
                if m and not self.moteur_a_agi():
                    return Retenue(RAISON_ACTION, m.group(0), CONSIGNE_ACTION)
            return None
        except Exception as erreur:  # noqa: BLE001 -- dans le doute, la réplique passe
            logger.warning(f"[verite] réplique non contrôlée : {erreur!r}")
            return None

    def moteur_a_agi(self) -> bool:
        return une_action_a_reussi(self.moteur)


def brancher_la_verite_des_actions(moteur: Any, agent: Any, noeud: Any, offre_une_action: bool) -> bool:
    """Pose (ou retire) le contrôle des répliques sur le cerveau de ``agent`` pour son étape. Actif seulement si
    l'étape offre un outil d'action et que sa case n'est pas éteinte. ⛔ Ne lève jamais."""
    try:
        from api.services.pipecat.reponse_avalee import ATTRIBUT_VERITE

        llm = getattr(agent, "llm", None)
        if llm is None:
            return False
        actif = bool(offre_une_action) and getattr(noeud, "verite_des_actions", None) is not False
        setattr(llm, ATTRIBUT_VERITE, VerificateurDeReplique(moteur, agent) if actif else None)
        return actif
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[verite] contrôle des répliques non branché : {erreur!r}")
        return False
