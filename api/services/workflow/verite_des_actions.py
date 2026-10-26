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
# Lot 11 (F-1, revue 4) : « 1/2 » est une fraction, pas le 1er février. Une date à barre a son année, ou son mois
# sur deux chiffres (« 3/11 », « 03/02 »).
_BARRE = re.compile(r"(?<![\d/])(?:(\d{1,2})/(\d{1,2})/\d{2,4}|(\d{1,2})/(\d{2}))(?![\d/])")
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
            jour, mois = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
            if _valide(int(mois), int(jour)):
                trouvees.add((int(mois), int(jour)))
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


# Lot 11 (F-1, revue 4 ; F-8) : les jours de la semaine, de la langue (pas du métier).
JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
_JOUR_DIT = re.compile(r"\b(" + "|".join(JOURS) + r")\b", re.IGNORECASE)
_JOUR_ET_DATE = re.compile(
    r"\b(" + "|".join(JOURS) + r")\s+(\d{1,2})(?:er)?\s+(" + "|".join(MOIS) + r")\b", re.IGNORECASE
)
_RELATIFS = {"aujourd'hui": 0, "aujourd’hui": 0, "demain": 1, "après-demain": 2, "apres-demain": 2}
# Assez loin pour « jeudi en huit » ou « la semaine d'après » : trois semaines.
_JOURS_DE_SEMAINE_VUS = 3


def _date_reelle(date: Date, maintenant: datetime) -> datetime | None:
    """La date (mois, jour) la plus proche à venir (cette année, ou l'an prochain si elle est passée)."""
    for annee in (maintenant.year, maintenant.year + 1):
        try:
            reelle = datetime(annee, date[0], date[1], tzinfo=maintenant.tzinfo)
        except ValueError:
            continue
        if reelle.date() >= maintenant.date() or annee > maintenant.year:
            return reelle
    return None


def dates_relatives_dites(texte: Any, maintenant: datetime | None = None) -> set[Date]:
    """Les dates que la personne désigne sans les écrire : « demain », « après-demain », un jour de la semaine
    (ses prochaines occurrences, sur trois semaines : « mardi », « mardi prochain »). ⛔ Ne lève jamais."""
    try:
        if not isinstance(texte, str) or not texte:
            return set()
        from datetime import timedelta

        maintenant = maintenant or datetime.now(FUSEAU)
        trouvees: set[Date] = set()
        bas = texte.casefold()
        for mot, ecart in _RELATIFS.items():
            if re.search(rf"(?<![\w-]){re.escape(mot)}(?![\w-])", bas):
                d = maintenant + timedelta(days=ecart)
                trouvees.add((d.month, d.day))
        for m in _JOUR_DIT.finditer(bas):
            cible = JOURS.index(m.group(1).casefold())
            ecart = (cible - maintenant.weekday()) % 7
            for semaine in range(_JOURS_DE_SEMAINE_VUS):
                d = maintenant + timedelta(days=ecart + 7 * semaine)
                trouvees.add((d.month, d.day))
        return trouvees
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[verite] dates relatives illisibles : {erreur!r}")
        return set()


def jours_faux(texte: Any, maintenant: datetime | None = None) -> list[tuple[str, str]]:
    """F-8 : les « lundi 27 octobre » dont le jour ne colle pas à la date : ``[(dit, juste)]`` (« lundi 27 octobre »,
    « mardi 27 octobre »). ⛔ Ne lève jamais."""
    try:
        if not isinstance(texte, str):
            return []
        maintenant = maintenant or datetime.now(FUSEAU)
        faux: list[tuple[str, str]] = []
        for m in _JOUR_ET_DATE.finditer(texte):
            date = (MOIS[m.group(3).casefold()], int(m.group(2)))
            if not _valide(*date):
                continue
            reelle = _date_reelle(date, maintenant)
            if reelle is None:
                continue
            juste = JOURS[reelle.weekday()]
            if juste != m.group(1).casefold():
                faux.append((m.group(0), f"{juste} {date[1]} {NOMS_DES_MOIS[date[0]]}"))
        return faux
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[verite] jours illisibles : {erreur!r}")
        return []


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
    # Revue du 26/10 (R-4) : l'étape (agent:nœud) d'où l'action est partie ; ``None`` : inconnue.
    etape: str | None = None


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


def etape_de_l_action(agent: Any) -> str | None:
    """L'étape d'où part une action : celle de ``agent``, ou, pour le fond, celle de l'agent qui lui a confié le
    travail (même clé que la demande identique, ``agent:nœud``). ⛔ Ne lève jamais."""
    try:
        from api.services.travail.demande_identique import identifiant_de_l_etape

        if getattr(agent, "current_node", None) is None and getattr(agent, "agent_qui_confie", None) is not None:
            agent = agent.agent_qui_confie
        noeud = getattr(agent, "current_node", None)
        return identifiant_de_l_etape(noeud, agent) if noeud is not None else None
    except Exception:  # noqa: BLE001
        return None


def noter_l_action(
    moteur: Any, nom: str, arguments: Any, resultat: Any, ecrits: Mapping[str, Any], etape: str | None = None
) -> None:
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
                etape=etape,
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


def outils_d_annulation(moteur: Any) -> frozenset:
    """Lot 8 (K16) : les noms (normalisés) des actions qui défont un champ (``annule_par_outil``). Elles passent
    TOUJOURS : ni la garde de réservation ni la réservation identique ne les retiennent (l'appelant peut annuler)."""
    try:
        from api.services.workflow.enveloppe_des_actions import _normaliser

        reglages = getattr(moteur, "_fiche", None)
        return frozenset(
            _normaliser(c.annule_par_outil)
            for c in tuple(getattr(reglages, "champs", None) or ())
            if getattr(c, "annule_par_outil", None)
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


def _est_une_annulation(annulations: frozenset, nom: str) -> bool:
    """Une annulation réussie défait la réservation connue même si son résultat cite une date (lot 8)."""
    try:
        from api.services.workflow.enveloppe_des_actions import _normaliser

        return _normaliser(nom) in annulations
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
        annulations = outils_d_annulation(moteur)
        for suite in journal[dernier + 1 :]:
            if suite.nom != nom_outil and suite.reussie and (not suite.dates or _est_une_annulation(annulations, suite.nom)):
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

# Les participes passés qui disent « c'est fait » : la liste PAR DÉFAUT (D-23, F-3). Elle se règle à l'écran, par
# agent (``verite_formulations_d_action``, lue par ``ReglagesFiche.formulations_d_action``) ; vide = cette liste.
# Aucun nom de chose : « est pris/réservé/confirmé… » vaut pour tout ce qu'une action peut faire. Volontairement
# absents : « noté », « enregistré », « transmis » (la fiche s'en charge, sans outil d'action).
PARTICIPES_D_ACTION = (
    "pris", "réservé", "confirmé", "programmé", "planifié", "fixé", "validé", "annulé", "déplacé",
    "modifié", "envoyé",
)
# Lot 11 (F-3, revue 2) : un participe suivi de ce qui décrit un ÉTAT, pas une action qui vient d'être faite :
# « pris en charge / en compte », « fixé à 240 », « validé depuis 2019 », « prévu pour 3 personnes ».
_ETAT_ET_NON_ACTION = r"(?!\s+(?:en\s+(?:charge|compte)|à\s+\d|depuis\b|pour\s+\d|par\s+(?:an|mois|semaine)\b))"


def _regle_de_l_action_faite(participes: tuple[str, ...]) -> re.Pattern:
    tous = "|".join(re.escape(p) for p in participes if p)
    sans_pris = "|".join(re.escape(p) for p in participes if p and p.casefold() != "pris")
    morceaux = [
        (
            r"\b(?:est|sont|c['’]est|a\s+été|ont\s+été|était)\s+(?:bien\s+|déjà\s+|maintenant\s+|donc\s+|à\s+présent\s+)?"
            rf"(?:{tous})(?:e|es|s)?\b{_ETAT_ET_NON_ACTION}"
        )
    ]
    if sans_pris:
        morceaux.append(rf"\b(?:j['’]ai|nous\s+avons|on\s+a)\s+(?:bien\s+|déjà\s+)?(?:{sans_pris})\b{_ETAT_ET_NON_ACTION}")
    return re.compile("(?:" + "|".join(morceaux) + ")", re.IGNORECASE)


_REGLES: dict[tuple[str, ...], re.Pattern] = {}


def regle_de_l_action_faite(participes: Any = None) -> re.Pattern | None:
    """La règle de « c'est fait » pour cette liste de participes (défaut : ``PARTICIPES_D_ACTION``). ``None`` : liste
    illisible (rien n'est contrôlé)."""
    try:
        liste = tuple(
            " ".join(str(p).split()).casefold() for p in (participes or PARTICIPES_D_ACTION) if str(p).strip()
        ) or PARTICIPES_D_ACTION
        regle = _REGLES.get(liste)
        if regle is None:
            regle = _regle_de_l_action_faite(liste)
            _REGLES[liste] = regle
        return regle
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[verite] formulations illisibles : {erreur!r}")
        return None


_ACTION_FAITE = regle_de_l_action_faite()

CONSIGNE_DATE = (
    "Ta réponse a été retenue : elle donnait une date qu'aucun résultat d'outil, aucune parole de la personne ne "
    "donne. Ne donne aucune date que tu n'as pas reçue : appelle l'outil qui la cherche, ou dis que tu vérifies."
)
# Lot 11 (F-3) : sans ordre d'appeler un outil (une passation ou une fin ne doit pas être appelée pour « obéir »).
CONSIGNE_ACTION = (
    "Ta réponse a été retenue : elle disait qu'une action est faite alors qu'aucun outil ne l'a faite. Ne dis pas "
    "que c'est fait : dis ce que tu fais ou ce qui reste à faire."
)
CONSIGNE_JOUR = "Ta réponse a été retenue : le jour ne correspond pas à la date. Le bon jour est : {justes}."
RAISON_DATE = "date_non_trouvee"
RAISON_ACTION = "action_sans_resultat"
RAISON_JOUR = "jour_faux"


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
            contenu = _contenu(message)
            connues |= dates_dans(contenu)
            # Lot 11 (F-1, revue 4) : « mardi prochain », « demain » dits par la PERSONNE seulement (un prompt cite des
            # jours d'ouverture : les compter rendrait connues toutes les dates de trois semaines).
            if message.get("role") == "user":
                connues |= dates_relatives_dites(contenu, maintenant)
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


def annulation_reussie(moteur: Any) -> bool:
    """Lot 8 : une action d'annulation (``annule_par_outil``) a-t-elle réussi dans l'appel ?"""
    try:
        from api.services.workflow.enveloppe_des_actions import _normaliser

        annulations = outils_d_annulation(moteur)
        return any(v.reussie and _normaliser(v.nom) in annulations for v in journal_de(moteur))
    except Exception:  # noqa: BLE001
        return True


def ecriture_en_vigueur(moteur: Any, etape: str | None = None) -> ActionVue | None:
    """Lot 11 (F-4) : la dernière action d'écriture réussie de l'appel, si aucune annulation réussie ne l'a défaite
    depuis. ``None`` : rien n'est écrit (ou tout a été défait). Revue du 26/10 (R-4) : ``etape`` donnée, seules
    comptent les écritures parties de cette étape (ou d'une étape inconnue, par prudence). ⛔ Ne lève jamais."""
    try:
        from api.services.workflow.enveloppe_des_actions import _normaliser

        ecritures = outils_d_ecriture(moteur)
        annulations = outils_d_annulation(moteur)
        en_vigueur = None
        for vue in journal_de(moteur):
            if not vue.reussie:
                continue
            nom = _normaliser(vue.nom)
            if nom in ecritures:
                if etape is None or vue.etape is None or vue.etape == etape:
                    en_vigueur = vue
            elif nom in annulations:
                en_vigueur = None
        return en_vigueur
    except Exception:  # noqa: BLE001
        return None


def ecriture_ou_annulation_depuis(moteur: Any, rang: int) -> bool:
    """Lot B (B2) : une action d'écriture ou d'annulation a-t-elle réussi dans l'appel depuis le rang ``rang`` du
    journal ? Périme le résultat connu d'une demande au fond. ⛔ Ne lève jamais (``False`` dans le doute)."""
    try:
        from api.services.workflow.enveloppe_des_actions import _normaliser

        changent = outils_d_ecriture(moteur) | outils_d_annulation(moteur)
        return any(v.reussie and _normaliser(v.nom) in changent for v in journal_de(moteur)[max(rang, 0) :])
    except Exception:  # noqa: BLE001
        return False


def _dit_annule(formulation: str) -> bool:
    return "annul" in (formulation or "").casefold()


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
            # Lot 11 (F-8) : « lundi 27 octobre » quand le 27 octobre est un mardi.
            faux = jours_faux(texte)
            if faux:
                return Retenue(
                    RAISON_JOUR,
                    ", ".join(dit for dit, _ in faux),
                    CONSIGNE_JOUR.format(justes=", ".join(juste for _, juste in faux)),
                )
            regle = regle_de_l_action_faite(getattr(getattr(self.moteur, "_fiche", None), "formulations_d_action", None))
            if regle is None:
                return None
            for phrase in _phrases(texte):
                if phrase.rstrip().endswith("?"):
                    continue
                m = regle.search(phrase)
                if m and not self.moteur_a_agi():
                    return Retenue(RAISON_ACTION, m.group(0), CONSIGNE_ACTION)
                # Lot 8 (K16) : « c'est annulé » n'est dit que si l'outil d'annulation l'a fait (l'agenda peut
                # avoir réservé, l'annulation avoir échoué ou n'avoir jamais été appelée).
                if m and _dit_annule(m.group(0)) and outils_d_annulation(self.moteur) and not annulation_reussie(self.moteur):
                    from api.services.workflow.enveloppe_des_actions import (
                        CONSIGNE_ANNULATION,
                        ISSUE_ECHEC,
                    )

                    return Retenue(RAISON_ACTION, m.group(0), CONSIGNE_ANNULATION[ISSUE_ECHEC])
            return None
        except Exception as erreur:  # noqa: BLE001 -- dans le doute, la réplique passe
            logger.warning(f"[verite] réplique non contrôlée : {erreur!r}")
            return None

    def moteur_a_agi(self) -> bool:
        return une_action_a_reussi(self.moteur)


def etape_qui_ecrit(moteur: Any, actions: Any, etape_du_fond: bool) -> bool:
    """Lot 11 (F-2, revue 1) : l'étape écrit-elle quelque chose ? Elle confie le travail au fond, ou elle porte une
    action d'écriture (``rempli_par_outil``) ou d'annulation (``annule_par_outil``). Les passations, transferts et
    fins ne comptent pas."""
    try:
        if etape_du_fond:
            return True
        from api.services.workflow.enveloppe_des_actions import _normaliser

        qui_ecrivent = outils_d_ecriture(moteur) | outils_d_annulation(moteur)
        return any(_normaliser(a) in qui_ecrivent for a in (actions or ()))
    except Exception:  # noqa: BLE001
        return False


def case_de_l_etape(noeud: Any, ecrit: bool) -> bool:
    """F-2 : la case de l'étape. Cochée à l'écran (``True``) ou décochée (``False``) : c'est elle qui décide. Jamais
    touchée (vide) : allumée seulement sur une étape qui écrit."""
    valeur = getattr(noeud, "verite_des_actions", None)
    if valeur is True or valeur is False:
        return valeur
    return bool(ecrit)


def brancher_la_verite_des_actions(moteur: Any, agent: Any, noeud: Any, offre_une_action: bool) -> bool:
    """Pose (ou retire) le contrôle des répliques sur le cerveau de ``agent`` pour son étape. ``offre_une_action`` :
    l'étape écrit (``etape_qui_ecrit``) ; la case de l'étape décide (``case_de_l_etape``). ⛔ Ne lève jamais."""
    try:
        from api.services.pipecat.reponse_avalee import ATTRIBUT_VERITE

        llm = getattr(agent, "llm", None)
        if llm is None:
            return False
        actif = not getattr(noeud, "is_end", False) and case_de_l_etape(noeud, bool(offre_une_action))
        setattr(llm, ATTRIBUT_VERITE, VerificateurDeReplique(moteur, agent) if actif else None)
        return actif
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[verite] contrôle des répliques non branché : {erreur!r}")
        return False
