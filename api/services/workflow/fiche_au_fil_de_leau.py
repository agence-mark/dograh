"""[.mark] La fiche au fil de l'eau (plan 2026-09-23, `Labo-agent-vocal/plans/`).

Un outil, `noter_information`, que le modèle appelle à n'importe quelle étape
pour écrire ou corriger un champ de la fiche de l'appel.

Tout le dispositif vit ici, hors du moteur, pour que la prochaine montée de
version de Dograh ne rencontre que des points d'accroche courts (D39) :

- ``ReglagesFiche`` : l'interrupteur et les champs, lus dans la configuration
  de l'agent. ``None`` quand l'interrupteur est éteint : l'outil n'existe pas (D12).
- ``ecrire_dans_la_fiche`` : LE point d'écriture unique (D35). L'outil l'appelle ;
  le balayage de fin d'appel et un futur « greffier » l'appelleront. Les contrôles
  vivent ici et nulle part ailleurs, sinon deux copies divergent en silence.
- ``brancher_noter_information`` : le schéma de l'outil (D3) et son gestionnaire.
- ``montrer_la_fiche`` : l'état de la fiche (ce qui est noté) ajouté à chaque
  requête de conversation, juste avant la dernière parole de l'appelant (D14,
  D43), sans la liste de ce qui manque (A7).

🔑 Une seule relance du modèle par tour, dans tous les ordres (D40, T1.5).
Le regroupement de Pipecat NE SUFFIT PAS : il ne compte comme « en cours » qu'une
fonction déjà signalée à l'agrégateur, et la note, instantanée, finit avant que
la porte le soit -- Pipecat relance alors deux fois (prouvé par T1.4, 24/09).
``SuiviDesTours`` relève donc la composition du tour AVANT que la moindre
fonction ne démarre : dans un tour qui contient une note, seul le DERNIER
résultat du tour relance le modèle, note ou porte. Une note seule relance donc
(Mistral ne parle jamais en appelant un outil : sans relance, l'agent resterait
muet). Avec une autre fonction dans le tour, ou sans note : Pipecat, inchangé.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.frames.frames import FunctionCallResultProperties
from pipecat.services.llm_service import FunctionCallParams

from api.schemas.fiche_agent import (
    ChampFiche,
    OrigineChamp,
    cle_dit,
    cle_insee,
    verifier_champs,
)
from api.services.workflow.dates_relatives import lire_date
from api.services.workflow.dto import ExtractionVariableDTO

NOM_OUTIL = "noter_information"
CLE_INTERRUPTEUR = "fiche_au_fil_de_leau"
CLE_CHAMPS = "fiche_champs"
CLE_ETAT = "fiche_etat"
CLE_JOURNAL = "fiche_journal"
# Les traces que les modules écrivent déjà dans la fiche de l'appel (lecture_appelant).
TRACE_COMMUNES = "communes_verifiees"
TRACE_VOIES = "voies_verifiees"
TRACE_EPELLATIONS = "epellations_lues"
TRACE_NOMBRES = "nombres_lus"

CONSIGNE_A_CONFIRMER = (
    "Noté, mais pas vérifié : fais confirmer cette information à la personne."
)
CONSIGNE_AMBIGU = (
    "Noté, mais plusieurs possibilités : demande à la personne laquelle est la bonne."
)
# Run 828 : la personne dit « Ponce-Alpes-Maxence », le module tranche Pont-Sainte-
# Maxence, la fiche l'écrit juste... et l'agent redit « Ponce-Alpes-Maxence » : depuis
# que les notes entre crochets ont disparu (D13), rien ne lui donnait l'écriture
# retenue. Le résultat de l'outil la lui rend.
# A6 (runs 830 à 837) : « quand tu redis… » s'est lu comme « redis-la » : commune
# redite six fois sur dix, refaite confirmer deux fois. La consigne dit d'abord de
# NE PAS la redire, et seulement ensuite comment l'écrire si c'est nécessaire.
CONSIGNE_ECRITURE_RETENUE = (
    "Noté sous son écriture officielle. Tu ne la redis pas et tu ne la fais pas "
    "confirmer ; si tu dois la redire plus tard, utilise cette écriture."
)
# A3 (runs 831, 835) : les descriptions des champs, lues avant par la seule
# extraction, sont sous les yeux du modèle qui parle depuis que l'outil existe ;
# « code, étage, animal » s'y est lu comme une liste de questions (« Y a-t-il un
# animal ? »), alors que le prompt de l'étape interdisait toute question d'accès.
NOTE_DESCRIPTIONS = (
    "Les descriptions des champs disent seulement ce que chaque champ contient : "
    "elles sont à lire uniquement, ce ne sont jamais des questions à poser. Ce que "
    "tu demandes à la personne, c'est le prompt de l'étape qui le dit."
)

# A5 (runs 831, 837) : un refus rendu sans consigne a poussé le modèle à faire
# confirmer SA version (« c'est bien en 2025 ? ») jusqu'à l'entendre dite : quatre
# tours pour une année au run 837, « ça casse le naturel » (Evan).
CONSIGNE_NON_DIT = (
    "Pas noté : {champs} n'a pas été dit tel quel par la personne. Note ses mots "
    "exacts ; ne lui fais pas confirmer ta version et ne repose pas la question."
)

# Écrite au mot au lot 0 (outil Dograh `e42be297`, 20 appels), reprise telle
# quelle (plan, « Description de l'outil »). ⛔ Ne pas la retoucher sans essai.
# A3 (runs 831, 835) : la dernière phrase est ajoutée ; le banc de sortie l'essaie.
DESCRIPTION_OUTIL = (
    "Note dans la fiche de l'appel une information que la personne vient de "
    "donner, ou corrige une information déjà notée. Appelle cet outil à chaque "
    "fois que la personne donne ou corrige une information, à n'importe quel "
    "moment de l'appel et quelle que soit l'étape. Il ne fait changer d'étape en "
    "aucun cas : si une sortie d'étape s'applique aussi, appelle les deux dans le "
    "même tour. Remplis uniquement les champs que la personne vient de donner, "
    "laisse les autres vides. Écris la valeur telle que la personne l'a dite, "
    "sans rien compléter ni inventer. Exemples : la personne dit « c'est à Creil, "
    "60100 » → commune = « Creil », code_postal = « 60100 ». La personne dit "
    "« non pardon, c'est au 14 rue de la République, pas au 12 » → "
    "adresse_intervention = « 14 rue de la République ». La personne dit « c'est "
    "un Godin, il fume dès que je l'allume » → marque_appareil = « Godin », "
    "symptome = « il fume dès que je l'allume ». La personne dit « je suis Mme "
    "Lefèvre, L E F E V R E » → nom = « LEFEVRE ». Après l'appel de l'outil, "
    "poursuis la conversation normalement. " + NOTE_DESCRIPTIONS
)


@dataclass(frozen=True)
class ReglagesFiche:
    champs: tuple[ChampFiche, ...]

    @property
    def par_nom(self) -> dict[str, ChampFiche]:
        return {champ.nom: champ for champ in self.champs}

    @classmethod
    def depuis(
        cls, run_configs: dict | None, *, is_realtime: bool = False
    ) -> ReglagesFiche | None:
        """Les réglages de l'appel, ou ``None`` : interrupteur éteint (le défaut),
        mode temps réel, ou aucun champ lisible. ``None`` = comportement d'avant."""
        run_configs = run_configs or {}
        if is_realtime or not run_configs.get(CLE_INTERRUPTEUR):
            return None
        champs: list[ChampFiche] = []
        for brut in run_configs.get(CLE_CHAMPS) or []:
            try:
                champs.append(ChampFiche.model_validate(brut))
            except Exception as erreur:  # noqa: BLE001 -- un champ illisible ne coûte pas l'appel
                logger.warning(f"[fiche] champ illisible ignoré : {brut!r} ({erreur})")
        try:
            verifier_champs(champs)
        except ValueError as erreur:
            logger.warning(f"[fiche] fiche refusée, outil non proposé : {erreur}")
            return None
        if not champs:
            logger.warning(
                "[fiche] interrupteur allumé mais aucun champ : outil non proposé"
            )
            return None
        return cls(champs=tuple(champs))


# --- Le contrôle de citation (D5, précisé par D41) ---------------------------


def _mots(texte: str) -> list[str]:
    sans_accents = "".join(
        c
        for c in unicodedata.normalize("NFKD", str(texte))
        if not unicodedata.combining(c)
    )
    return re.findall(r"[a-z0-9]+", sans_accents.lower())


def _suites(mots: list[str]) -> list[str]:
    """Les mots courts consécutifs recollés : une épellation (« l e f e v r e »)
    ou des chiffres dits par paquets (« 06 12 34 56 78 », « 60 100 »)."""
    suites: list[str] = []
    courant: list[str] = []
    for mot in mots + [""]:
        if mot and (len(mot) <= 2 or mot.isdigit()):
            courant.append(mot)
            continue
        if len(courant) >= 2:
            suites.append("".join(courant))
        courant = []
    return suites


def est_cite(valeur: Any, paroles: Iterable[str]) -> bool:
    """Chaque mot de la valeur a-t-il été dit par l'appelant, à un moment de
    l'appel, tel que le modèle l'a lu ? Accents et casse ignorés (D41)."""
    mots_valeur = _mots(str(valeur))
    if not mots_valeur:
        return False
    dits: set[str] = set()
    suites: list[str] = []
    for parole in paroles:
        mots = _mots(parole)
        dits.update(mots)
        suites.extend(_suites(mots))
    return all(
        mot in dits or (len(mot) >= 2 and any(mot in suite for suite in suites))
        for mot in mots_valeur
    )


def paroles_de_l_appelant(messages: Iterable[dict]) -> list[str]:
    """Ce que l'appelant a dit, tel que le modèle l'a lu (après la réécriture
    des modules, jamais la transcription brute : D24)."""
    paroles: list[str] = []
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        contenu = message.get("content")
        if isinstance(contenu, str):
            paroles.append(contenu)
        elif isinstance(contenu, list):
            paroles.extend(
                partie.get("text", "")
                for partie in contenu
                if isinstance(partie, dict) and partie.get("type") == "text"
            )
    return paroles


# --- Ce que les modules ont déjà trouvé (D23, D42) ---------------------------
#
# ⛔ L'outil ne ré-analyse rien : il reprend les traces que les modules ont
# écrites sur les phrases entières de l'appelant (« Chantilly, 60560 » tranché
# par le code postal, même si le modèle ne note que « Chantilly »).


@dataclass(frozen=True)
class Lecture:
    valeur: Any
    sure: bool
    suite: str | None = None  # "a_confirmer" | "ambigu"
    options: tuple[str, ...] = ()
    code_insee: str | None = None


def _memes_mots(a: Any, b: Any) -> bool:
    mots = _mots(str(a or ""))
    return bool(mots) and mots == _mots(str(b or ""))


def _entrees(fiche: dict, cle: str) -> list[dict]:
    """Les traces d'un module, la plus récente d'abord."""
    return [t for t in reversed(fiche.get(cle) or []) if isinstance(t, dict)]


def _suite(options: tuple[str, ...]) -> str:
    return "ambigu" if len(options) > 1 else "a_confirmer"


def lire_epellation(valeur: Any, fiche: dict) -> str | None:
    """Le mot épelé que le code a lu, si la valeur est cette épellation."""
    compacte = "".join(_mots(str(valeur)))
    for trace in _entrees(fiche, TRACE_EPELLATIONS):
        epele = trace.get("epele")
        if not epele:
            continue
        if compacte and compacte in (
            "".join(_mots(trace.get("entendu") or "")),
            "".join(_mots(epele)),
        ):
            return epele
    return None


def _option_commune(proposition: dict) -> str:
    nom, dep = proposition.get("nom") or "", proposition.get("departement")
    return f"{nom} ({dep})" if dep else nom


def lire_commune(valeur: Any, fiche: dict) -> Lecture:
    for trace in _entrees(fiche, TRACE_COMMUNES):
        retenue = trace.get("commune_retenue") or {}
        propositions = [
            p for p in trace.get("propositions") or [] if isinstance(p, dict)
        ]
        noms = [retenue.get("nom"), *(p.get("nom") for p in propositions)]
        if not (
            _memes_mots(valeur, trace.get("entendu"))
            or any(_memes_mots(valeur, nom) for nom in noms)
        ):
            continue
        if trace.get("statut") == "sure" and retenue.get("nom"):
            return Lecture(retenue["nom"], True, code_insee=retenue.get("code_insee"))
        options = tuple(_option_commune(p) for p in propositions)
        choisie = next(
            (p for p in propositions if _memes_mots(valeur, p.get("nom"))), None
        )
        return Lecture(
            choisie["nom"] if choisie else valeur, False, _suite(options), options
        )
    # D37 : aucune trace du module pour cette valeur.
    return Lecture(valeur, False, "a_confirmer")


_MOT = re.compile(r"[^\W_]+")
_NUMERO = {"bis", "ter", "quater"}


def _trouver(valeur: str, phrase: str) -> tuple[int, int] | None:
    """La portée (début, fin) des mots de ``phrase`` dans ``valeur``, accents
    et casse ignorés. Le numéro en tête de ``phrase`` est essayé avec et sans."""
    mots = list(_MOT.finditer(valeur))
    formes = ["".join(_mots(m.group())) for m in mots]
    cible = _mots(phrase)
    essais = [cible]
    sans_numero = cible
    while sans_numero and (sans_numero[0].isdigit() or sans_numero[0] in _NUMERO):
        sans_numero = sans_numero[1:]
    if sans_numero != cible:
        essais.append(sans_numero)
    for essai in essais:
        n = len(essai)
        for i in range(len(formes) - n + 1) if n else ():
            if formes[i : i + n] == essai:
                return mots[i].start(), mots[i + n - 1].end()
    return None


def _avec_le_type_de_voie(
    valeur: str, portee: tuple[int, int], nom_officiel: str
) -> tuple[int, int]:
    """Le module note la rue entendue SANS son type (« danton ») : la portée
    s'étend aux mots qui la précèdent quand ils ouvrent le nom officiel
    (« rue » de « Rue Danton »), sinon on écrirait « 6 rue Rue Danton »."""
    tete = _mots(nom_officiel)
    avant = list(_MOT.finditer(valeur[: portee[0]]))
    for n in range(min(len(avant), len(tete)), 0, -1):
        mots = avant[-n:]
        if ["".join(_mots(m.group())) for m in mots] == tete[:n]:
            return mots[0].start(), portee[1]
    return portee


def _remplacer(valeur: str, portee: tuple[int, int], par: str) -> str:
    return f"{valeur[: portee[0]]}{par}{valeur[portee[1] :]}"


def lire_rue(valeur: Any, fiche: dict) -> Lecture:
    texte = str(valeur)
    for trace in _entrees(fiche, TRACE_VOIES):
        retenue = trace.get("voie_retenue")
        propositions = tuple(
            p.get("nom")
            for p in trace.get("propositions") or []
            if isinstance(p, dict) and p.get("nom")
        )
        portee = _trouver(texte, trace.get("entendu") or "")
        choisie = None
        if portee is None:
            for nom in (retenue, *propositions):
                if nom and (portee := _trouver(texte, nom)) is not None:
                    choisie = nom
                    break
        if portee is None:
            continue
        if trace.get("statut") == "sure" and retenue:
            portee = _avec_le_type_de_voie(texte, portee, retenue)
            return Lecture(_remplacer(texte, portee, retenue), True)
        nouvelle = _remplacer(texte, portee, choisie) if choisie else texte
        return Lecture(nouvelle, False, _suite(propositions), propositions)
    return Lecture(texte, False, "a_confirmer")


# --- Le point d'écriture unique (D35) ----------------------------------------


@dataclass(frozen=True)
class Verdict:
    champ: str
    statut: str  # "ecrit" | "refuse" | "ignore"
    raison: str | None = None
    valeur: Any = None
    suite: str | None = None  # "a_confirmer" | "ambigu" : faire confirmer
    options: tuple[str, ...] = ()


def _est_vide(valeur: Any) -> bool:
    return valeur is None or (isinstance(valeur, str) and not valeur.strip())


def ecrire_dans_la_fiche(
    fiche: dict,
    reglages: ReglagesFiche,
    champ: str,
    valeur: Any,
    *,
    sure: bool = True,
    source: str = "outil",
    paroles: Iterable[str] = (),
    seulement_si_vide: bool = False,
    jour: datetime | None = None,
) -> Verdict:
    """Écrit un champ dans la fiche de l'appel, ou dit pourquoi non.

    Chaque champ est traité seul. Chaque écriture et chaque refus sont
    consignés, avec leur raison, dans le journal de la fiche et les logs.

    Contrôle « a-t-il été dit ? » en deux régimes (D24) : un champ lu par un
    module (commune, rue) doit correspondre à ce que le module a trouvé, sinon il
    est écrit NON SÛR et à faire confirmer (D37) ; un champ sans module doit
    figurer dans ce que l'appelant a dit (D41). Une épellation lue par le code
    est écrite telle qu'épelée, pour tout champ dicté. Un champ de date (D46)
    reçoit la date calculée à partir des mots dits, qui sont gardés à côté.
    """
    definition = reglages.par_nom.get(champ)
    if isinstance(valeur, str):
        valeur = valeur.strip()
    paroles = list(paroles)
    lecture: Lecture | None = None
    dit: str | None = None

    if definition is None:
        verdict = Verdict(champ, "refuse", "champ_inconnu")
    elif _est_vide(valeur):
        verdict = Verdict(champ, "ignore", "valeur_vide")
    else:
        epele = (
            lire_epellation(valeur, fiche)
            if definition.origine == OrigineChamp.dicte
            else None
        )
        if epele:
            valeur = epele
        if definition.lecteur_effectif == "commune":
            lecture = lire_commune(valeur, fiche)
        elif definition.lecteur_effectif == "rue":
            lecture = lire_rue(valeur, fiche)
        if lecture is not None:
            valeur, sure = lecture.valeur, sure and lecture.sure
        if definition.lecteur_effectif == "date" and not epele:
            date = lire_date(str(valeur), paroles, jour)
            # « 2025 » trouvé dans ses paroles, ou « l'année dernière » dit tel quel.
            if date and (date.depuis_les_paroles or est_cite(valeur, paroles)):
                valeur, dit = date.valeur, date.dit
        if (
            lecture is None
            and not epele
            and dit is None
            and definition.origine == OrigineChamp.dicte
            # Revue du 25/09 : un oui/non n'est jamais « dit » tel quel (la
            # personne ne prononce pas « true ») ; il se juge comme un déduit.
            and definition.type != "boolean"
            and not est_cite(valeur, paroles)
        ):
            verdict = Verdict(champ, "refuse", "non_dit", valeur)
        else:
            verdict = _ecrire(
                fiche, champ, valeur, sure, source, seulement_si_vide, lecture
            )
            if verdict.statut == "ecrit" and definition.lecteur_effectif == "date":
                extraites = fiche.setdefault("extracted_variables", {})
                if dit is not None:
                    fiche[cle_dit(champ)] = extraites[cle_dit(champ)] = dit
                else:
                    # Une date écrite telle que dite ne garde pas les mots d'une autre.
                    fiche.pop(cle_dit(champ), None)
                    extraites.pop(cle_dit(champ), None)

    fiche.setdefault(CLE_JOURNAL, []).append(
        {
            "champ": champ,
            "valeur": valeur,
            "statut": verdict.statut,
            "raison": verdict.raison,
            "source": source,
            "sure": sure,
            **({"suite": verdict.suite} if verdict.suite else {}),
            **({"dit": dit} if dit is not None else {}),
        }
    )
    # Relevé par la revue du 25/09 : la valeur (nom, téléphone, adresse de
    # l'appelant) ne part pas dans les journaux de Railway en `info`. Le journal
    # de la fiche, rangé avec l'appel, suffit à la traçabilité ; la valeur ne
    # s'écrit qu'en `debug`, comme les valeurs extraites de l'amont.
    logger.info(
        f"[fiche] {source} {champ} -> {verdict.statut}"
        + (f" ({verdict.raison})" if verdict.raison else "")
        + (f" [{verdict.suite}]" if verdict.suite else "")
    )
    logger.debug(f"[fiche] {source} {champ}={valeur!r}")
    return verdict


def _ecrire(
    fiche: dict,
    champ: str,
    valeur: Any,
    sure: bool,
    source: str,
    seulement_si_vide: bool,
    lecture: Lecture | None,
) -> Verdict:
    etat = fiche.setdefault(CLE_ETAT, {})
    precedent = etat.get(champ)
    if seulement_si_vide and not _est_vide(fiche.get(champ)):
        return Verdict(champ, "ignore", "deja_rempli", valeur)
    if precedent and precedent.get("sure") and not sure:
        # D6 : une valeur non sûre n'écrase jamais une valeur sûre.
        return Verdict(champ, "refuse", "non_sure_sur_sure", valeur)
    extraites = fiche.setdefault("extracted_variables", {})
    fiche[champ] = extraites[champ] = valeur
    etat[champ] = {"sure": sure, "source": source}
    if lecture is not None and lecture.code_insee and sure:
        fiche[cle_insee(champ)] = extraites[cle_insee(champ)] = lecture.code_insee
    elif lecture is not None:
        # Une commune non sûre ne garde pas le code d'une autre.
        fiche.pop(cle_insee(champ), None)
        extraites.pop(cle_insee(champ), None)
    return Verdict(
        champ,
        "ecrit",
        valeur=valeur,
        suite=None if sure else (lecture.suite if lecture else None),
        options=lecture.options if lecture and not sure else (),
    )


# --- Le balayage de fin d'appel (D11) ----------------------------------------

# A4 (runs 828 à 837, 10 sur 10) : le balayage remplissait les champs déduits de
# ce qui ne leur correspond pas (`symptome` = « il fonctionne normalement », ou la
# phrase d'appel recopiée ; `type_logement` inventé). Un champ déduit n'a pas de
# contrôle de citation (D4) : la consigne est seule à le tenir, plus la règle de
# code ci-dessous contre la recopie d'un autre champ.
CONSIGNE_BALAYAGE = (
    "Remplis une variable seulement si la personne a donné, pendant l'appel, "
    "l'information que la variable décrit. Une phrase qui dit le contraire ou "
    "qui parle d'autre chose ne la remplit pas : « tout fonctionne » ne décrit "
    "aucun problème. Ne mets jamais la même phrase dans deux variables. Recopie "
    "ses mots, sans rien compléter ni déduire. Dans le doute, ne mets pas la "
    "variable."
)


def _recopie_d_un_autre_champ(
    reglages: ReglagesFiche, fiche: dict, champ: str, valeur: Any
) -> str | None:
    """A4 : le champ déjà rempli dont cette valeur n'est qu'une recopie (tous ses
    mots y figurent), ou ``None``. Run 837 : `symptome` = le verbatim de la demande."""
    mots = set(_mots(str(valeur)))
    if not mots:
        return None
    for autre in reglages.champs:
        if autre.nom == champ or _est_vide(fiche.get(autre.nom)):
            continue
        if mots <= set(_mots(str(fiche[autre.nom]))):
            return autre.nom
    return None


def _marquer_les_numeros_en_conflit(reglages: ReglagesFiche, fiche: dict) -> None:
    """A8 : en fin d'appel, un numéro qui diffère encore du dernier numéro dicté
    devient NON SÛR, et le journal dit pourquoi. Le balayage n'écrase jamais un
    champ rempli (D11) : c'est au magasin de trancher, pas au code."""
    for champ, dernier in numeros_en_conflit(reglages, fiche):
        etat = fiche.setdefault(CLE_ETAT, {}).setdefault(champ, {})
        etat["sure"] = False
        fiche.setdefault(CLE_JOURNAL, []).append(
            {
                "champ": champ,
                "valeur": fiche.get(champ),
                "statut": "a_verifier",
                "raison": "autre_numero_dicte_en_dernier",
                "dernier_dicte": dernier,
                "source": "balayage",
                "sure": False,
            }
        )
        logger.warning(
            f"[fiche] {champ} diffère du dernier numéro dicté : marqué à vérifier"
        )


async def balayer_la_fiche(
    reglages: ReglagesFiche,
    extraire: Callable[[list[ExtractionVariableDTO], str], Any],
    fiche: dict,
    messages: Iterable[dict],
) -> dict:
    """Le filet contre l'oubli d'appeler l'outil : relit la conversation pour les
    SEULS champs restés vides, et les écrit par le point d'écriture unique, donc
    avec les mêmes contrôles (D35). N'écrase jamais ce que l'outil a écrit."""
    _marquer_les_numeros_en_conflit(reglages, fiche)
    vides = [c for c in reglages.champs if _est_vide(fiche.get(c.nom))]
    if not vides:
        return {}
    trouve = await extraire(
        [
            ExtractionVariableDTO(
                name=c.nom, type=c.type, prompt=c.description or c.nom
            )
            for c in vides
        ],
        CONSIGNE_BALAYAGE,
    )
    if not isinstance(trouve, dict):
        return {}
    paroles = paroles_de_l_appelant(messages)
    ecrits = {}
    for champ in vides:
        if champ.nom not in trouve:
            continue
        copie = (
            _recopie_d_un_autre_champ(reglages, fiche, champ.nom, trouve[champ.nom])
            if champ.origine == OrigineChamp.deduit
            else None
        )
        if copie:
            fiche.setdefault(CLE_JOURNAL, []).append(
                {
                    "champ": champ.nom,
                    "valeur": trouve[champ.nom],
                    "statut": "refuse",
                    "raison": f"recopie_de_{copie}",
                    "source": "balayage",
                    "sure": True,
                }
            )
            logger.info(f"[fiche] balayage {champ.nom} refusé : recopie de {copie}")
            continue
        verdict = ecrire_dans_la_fiche(
            fiche,
            reglages,
            champ.nom,
            trouve[champ.nom],
            source="balayage",
            paroles=paroles,
            seulement_si_vide=True,
        )
        if verdict.statut == "ecrit":
            ecrits[champ.nom] = verdict.valeur
    return ecrits


# --- Une seule relance par tour ----------------------------------------------


@dataclass
class _Tour:
    restants: set[str]
    avec_autre: bool
    avec_porte: bool = False
    question_posee: bool = False


class SuiviDesTours:
    """La composition de chaque tour de fonctions qui contient une note,
    relevée à son départ."""

    def __init__(self, est_porte: Callable[[str], bool]):
        self._est_porte = est_porte
        self._tours: dict[str, _Tour] = {}
        # Tout identifiant déjà vu, pour toujours : Mistral redétecte un appel
        # déjà joué dans la réponse suivante (filtre de son service), et `relance`
        # l'a déjà retiré de `_tours`. Sans ce registre, [note redétectée, porte]
        # formait un tour neuf dont la note ne répondrait jamais : la porte ne
        # relançait pas, agent muet (relevé par la revue du 25/09).
        self._vus: set[str] = set()
        # A1 : le texte que la réponse en cours a déjà envoyé à la voix, et les
        # appels dont la réponse contenait une question.
        self.texte_de_la_reponse = ""
        self._apres_une_question: set[str] = set()

    def reponse_commencee(self) -> None:
        self.texte_de_la_reponse = ""

    def appels_emis(self, appels: Iterable[Any]) -> None:
        """La réponse du modèle s'achève sur ces appels : a-t-elle posé une
        question à voix haute avant eux ?"""
        if "?" in self.texte_de_la_reponse:
            self._apres_une_question.update(a.tool_call_id for a in appels)
        self.texte_de_la_reponse = ""

    def enregistrer(self, appels: Iterable[Any]) -> None:
        # Mistral redétecte les appels déjà joués (filtre du service) : un
        # identifiant déjà connu garde son tour.
        nouveaux = [a for a in appels if a.tool_call_id not in self._vus]
        self._vus.update(a.tool_call_id for a in nouveaux)
        if not any(a.function_name == NOM_OUTIL for a in nouveaux):
            return
        tour = _Tour(
            restants={a.tool_call_id for a in nouveaux},
            avec_autre=any(
                a.function_name != NOM_OUTIL and not self._est_porte(a.function_name)
                for a in nouveaux
            ),
            avec_porte=any(self._est_porte(a.function_name) for a in nouveaux),
            question_posee=any(
                a.tool_call_id in self._apres_une_question for a in nouveaux
            ),
        )
        self._apres_une_question.difference_update(a.tool_call_id for a in nouveaux)
        for appel in nouveaux:
            self._tours[appel.tool_call_id] = tour

    def relance(self, tool_call_id: str) -> bool | None:
        """``True`` pour le dernier résultat du tour, ``False`` pour les autres,
        ``None`` hors d'un tour à note (le comportement de Pipecat, inchangé).

        Pipecat, quand plusieurs résultats se suivent, ne relance que sur le
        dernier arrivé : c'est donc lui, note ou porte, qui doit porter la relance.
        """
        tour = self._tours.pop(tool_call_id, None)
        if tour is None or tour.avec_autre:
            return None
        tour.restants.discard(tool_call_id)
        if tour.question_posee and not tour.avec_porte:
            # A1 (runs 832, 837) : le modèle a posé sa question ET noté dans la
            # même réponse. Relancé, il reparlait sans attendre la réponse : deux
            # questions d'affilée, une porte prise avant la réponse. On attend.
            return False
        return not tour.restants


# Les méthodes du service du modèle que la fiche enveloppe (dont trois privées,
# propres à la copie de Pipecat de Dograh). Une montée de Pipecat qui en renomme
# une coupe une correction en silence : un test les vérifie sur le vrai service.
ACCROCHES_A1 = ("_process_context", "_push_llm_text", "_run_or_defer_function_calls")
ACCROCHES = (
    "run_function_calls",
    "get_chat_completions",
    "build_chat_completion_params",
    "_function_is_node_transition",
    *ACCROCHES_A1,
)


def suivre_les_tours(llm: Any) -> SuiviDesTours:
    """Branche le suivi sur le service du modèle, AVANT l'exécution des fonctions.

    ⚠️ L'événement ``on_function_calls_started`` de Pipecat part dans une tâche à
    part : il peut arriver après les fonctions. D'où l'enveloppe synchrone.
    """

    def est_porte(nom: str) -> bool:
        return bool(llm._function_is_node_transition(nom))

    suivi = SuiviDesTours(est_porte)
    lancer = llm.run_function_calls

    async def run_function_calls(function_calls):
        suivi.enregistrer(function_calls or [])
        return await lancer(function_calls)

    llm.run_function_calls = run_function_calls

    # A1 : ce que la réponse a dit avant ses appels. Trois points d'accroche du
    # service OpenAI de Pipecat, dont Mistral hérite ; absents (autre
    # fournisseur, ou montée de Pipecat qui les a renommés), rien n'est su et la
    # relance reste celle de D40 -- et on le DIT, pour ne pas le découvrir en appel.
    # ⚠️ Tenu par `test_les_points_d_accroche_existent_chez_mistral`.
    if not all(hasattr(llm, nom) for nom in ACCROCHES_A1):
        logger.warning(
            f"[fiche] {type(llm).__name__} sans {', '.join(ACCROCHES_A1)} : "
            "l'agent pourra reparler après une question posée en notant (A1)"
        )
    else:
        traiter = llm._process_context
        pousser = llm._push_llm_text
        emettre = llm._run_or_defer_function_calls

        async def _process_context(context):
            suivi.reponse_commencee()
            return await traiter(context)

        async def _push_llm_text(text):
            suivi.texte_de_la_reponse += text
            return await pousser(text)

        async def _run_or_defer_function_calls(function_calls, **kwargs):
            suivi.appels_emis(function_calls or [])
            return await emettre(function_calls, **kwargs)

        llm._process_context = _process_context
        llm._push_llm_text = _push_llm_text
        llm._run_or_defer_function_calls = _run_or_defer_function_calls
    return suivi


# --- L'outil -----------------------------------------------------------------


def schema_outil(reglages: ReglagesFiche) -> FunctionSchema:
    """Un paramètre facultatif par champ de la fiche (D3)."""
    return FunctionSchema(
        name=NOM_OUTIL,
        description=DESCRIPTION_OUTIL,
        properties={
            champ.nom: {
                "type": champ.type,
                "description": champ.description or champ.nom,
            }
            for champ in reglages.champs
        },
        required=[],
    )


def creer_gestionnaire(
    reglages: ReglagesFiche,
    fiche: Callable[[], dict],
    messages: Callable[[], Iterable[dict]],
    suivi: SuiviDesTours | None = None,
):
    async def noter_information(params: FunctionCallParams) -> None:
        try:
            paroles = paroles_de_l_appelant(messages())
            ecrits: list[str] = []
            retenus: dict[str, Any] = {}
            refuses: list[dict] = []
            a_confirmer: list[dict] = []
            # Plusieurs notes d'un même tour : appliquées dans l'ordre d'arrivée,
            # chaque champ seul.
            for champ, valeur in dict(params.arguments or {}).items():
                verdict = ecrire_dans_la_fiche(
                    fiche(), reglages, champ, valeur, paroles=paroles
                )
                if verdict.statut == "ecrit":
                    ecrits.append(champ)
                    if _mots(str(verdict.valeur)) != _mots(str(valeur)):
                        # Le module a changé l'écriture (commune, rue, épellation).
                        retenus[champ] = verdict.valeur
                    if verdict.suite:
                        a_confirmer.append(
                            {
                                "champ": champ,
                                "valeur": verdict.valeur,
                                **(
                                    {"options": list(verdict.options)}
                                    if verdict.options
                                    else {}
                                ),
                            }
                        )
                elif verdict.statut == "refuse":
                    refuses.append({"champ": champ, "raison": verdict.raison})
            resultat: dict = {"statut": "note" if ecrits else "rien_note"}
            # A2 (run 832) : une consigne ne remplace plus l'autre. Commune
            # retenue ET adresse à confirmer dans la même note : les deux.
            consignes: list[str] = []
            if ecrits:
                resultat["ecrits"] = ecrits
            if a_confirmer:
                # D7 : c'est le modèle, relancé, qui pose la question.
                ambigu = any("options" in c for c in a_confirmer)
                resultat["statut"] = "ambigu" if ambigu else "a_confirmer"
                resultat["a_confirmer"] = a_confirmer
                consignes.append(CONSIGNE_AMBIGU if ambigu else CONSIGNE_A_CONFIRMER)
            if retenus:
                resultat["ecriture_retenue"] = retenus
                consignes.append(
                    f"Pour {', '.join(retenus)} : {CONSIGNE_ECRITURE_RETENUE}"
                    if a_confirmer
                    else CONSIGNE_ECRITURE_RETENUE
                )
            non_dits = [r["champ"] for r in refuses if r["raison"] == "non_dit"]
            if non_dits:
                consignes.append(CONSIGNE_NON_DIT.format(champs=", ".join(non_dits)))
            if consignes:
                resultat["consigne"] = " ".join(consignes)
            if refuses:
                resultat["refuses"] = refuses
        except Exception as erreur:  # noqa: BLE001 -- une note ne coûte jamais l'appel
            logger.error(f"[fiche] {NOM_OUTIL} a échoué : {erreur}")
            resultat = {"statut": "erreur"}
        # Une seule relance par tour : voir l'en-tête du module.
        relance = suivi.relance(params.tool_call_id) if suivi else None
        await params.result_callback(
            resultat,
            properties=None
            if relance is None
            else FunctionCallResultProperties(run_llm=relance),
        )

    return noter_information


def brancher_noter_information(
    reglages: ReglagesFiche,
    llm: Any,
    fiche: Callable[[], dict],
    messages: Callable[[], Iterable[dict]],
    suivi: SuiviDesTours | None = None,
) -> FunctionSchema:
    """Enregistre le gestionnaire auprès du modèle et rend le schéma à proposer."""
    llm.register_function(
        NOM_OUTIL, creer_gestionnaire(reglages, fiche, messages, suivi)
    )
    return schema_outil(reglages)


# --- Montrer la fiche au modèle (D14, D43) -----------------------------------

ENTETE_ETAT = (
    "[Fiche de l'appel : pour toi seulement, tu ne la lis jamais à voix haute. "
    "Elle se remplit par noter_information.]"
)
LONGUEUR_MAX_VALEUR = 120


def _abregee(valeur: Any) -> str:
    texte = " ".join(str(valeur).split())
    if len(texte) > LONGUEUR_MAX_VALEUR:
        texte = texte[: LONGUEUR_MAX_VALEUR - 1].rstrip() + "…"
    return f"« {texte} »"


# Un numéro de téléphone français tel que la fiche l'écrit : 0 puis 9 chiffres,
# espaces ou points permis. Une référence « F0612345678 » n'en est pas un.
_TELEPHONE = re.compile(r"0[1-9](?:[ .]?\d){8}")


def _chiffres(valeur: Any) -> str:
    return "".join(c for c in str(valeur) if c.isdigit())


def _par_paires(chiffres: str) -> str:
    return " ".join(chiffres[i : i + 2] for i in range(0, len(chiffres), 2))


def numeros_en_conflit(reglages: ReglagesFiche, fiche: dict) -> list[tuple[str, str]]:
    """A8 (run 837) : les champs qui gardent un numéro de téléphone différent du
    DERNIER numéro que la personne a dicté, selon le module des nombres :
    [(champ, dernier numéro dicté)].

    Au run 837, la personne corrige « soixante-huit » en « soixante-dix-huit »,
    l'agent relit le bon numéro… et ne le note jamais : la fiche sort fausse.

    Resserré par la revue du 25/09 : seul compte un champ qui tient un numéro
    de téléphone, et qui est UN numéro dicté plus tôt. Deux champs téléphone
    remplis (fixe et portable) : on ne sait pas lequel corriger, rien n'est dit.
    Une référence ou une facture à dix chiffres n'est pas un téléphone.
    """
    dictes = [
        _chiffres(t.get("ecrit"))
        for t in fiche.get(TRACE_NOMBRES) or []
        if t.get("type") == "telephone"
    ]
    dictes = [d for d in dictes if len(d) == 10]
    if not dictes:
        return []
    dernier, anciens = dictes[-1], set(dictes[:-1])
    telephones = [
        (champ.nom, _chiffres(fiche[champ.nom]))
        for champ in reglages.champs
        if _TELEPHONE.fullmatch(str(fiche.get(champ.nom) or "").strip())
    ]
    if len(telephones) != 1:
        return []
    champ, chiffres = telephones[0]
    if chiffres != dernier and chiffres in anciens:
        return [(champ, dernier)]
    return []


def etat_de_la_fiche(reglages: ReglagesFiche, fiche: dict) -> str | None:
    """Ce que le modèle a déjà, sûr ou à faire confirmer, dans l'ordre des
    champs de la fiche. ``None`` tant que rien n'est noté.

    ⛔ Pas de liste de ce qui manque (A7, run 835) : sous les yeux de l'accueil,
    « Manque : numero_dicte, commune… » s'est lu comme une liste de questions,
    et l'accueil a mené tout l'appel. Ce qu'une étape demande reste à son prompt.
    """
    etat = fiche.get(CLE_ETAT) or {}
    notes, a_confirmer = [], []
    for champ in reglages.champs:
        valeur = fiche.get(champ.nom)
        if _est_vide(valeur):
            continue
        ligne = f"{champ.nom} = {_abregee(valeur)}"
        # Une valeur sans état n'a pas été écrite par la fiche : on ne la dit
        # pas sûre.
        if (etat.get(champ.nom) or {}).get("sure"):
            notes.append(ligne)
        else:
            a_confirmer.append(ligne)
    if not (notes or a_confirmer):
        return None
    lignes = [ENTETE_ETAT]
    if notes:
        lignes.append("Noté : " + " ; ".join(notes))
    if a_confirmer:
        lignes.append("À confirmer : " + " ; ".join(a_confirmer))
    for champ, dernier in numeros_en_conflit(reglages, fiche):
        lignes.append(
            f"Attention : le dernier numéro dicté par la personne est "
            f"{_par_paires(dernier)}, la fiche a un autre numéro dans {champ}. "
            "Si c'est une correction, note le nouveau numéro."
        )
    return "\n".join(lignes)


def inserer_l_etat(messages: list, texte: str) -> list:
    """D43 : juste avant la dernière parole de l'appelant, dans une COPIE de la
    liste. Sans parole de l'appelant (l'accueil), rien n'est ajouté."""
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            return [*messages[:i], {"role": "user", "content": texte}, *messages[i:]]
    return messages


def montrer_la_fiche(
    llm: Any, reglages: ReglagesFiche, fiche: Callable[[], dict]
) -> bool:
    """Ajoute l'état de la fiche à chaque requête de CONVERSATION du modèle.

    🔑 Rien n'entre dans l'historique ni dans le prompt système (D14, T6.2) :
    l'état est calculé à la requête, sur la fiche du moment (T6.1), puis oublié.
    Le début de la requête ne change donc pas, et le cache le sert toujours.

    ⚠️ Les relectures hors conversation (balayage, extraction) passent par le
    même constructeur de requête sur le même objet : seule une requête née de
    ``get_chat_completions`` est marquée, par une variable de contexte propre à
    la tâche en cours.
    """
    if not (
        hasattr(llm, "get_chat_completions")
        and hasattr(llm, "build_chat_completion_params")
    ):
        logger.warning(
            "[fiche] service sans requête de conversation : fiche non montrée"
        )
        return False
    en_conversation: ContextVar[bool] = ContextVar(
        "fiche_en_conversation", default=False
    )
    obtenir = llm.get_chat_completions
    construire = llm.build_chat_completion_params

    async def get_chat_completions(context):
        jeton = en_conversation.set(True)
        try:
            return await obtenir(context)
        finally:
            en_conversation.reset(jeton)

    def build_chat_completion_params(params_from_context):
        params = construire(params_from_context)
        if en_conversation.get():
            try:
                texte = etat_de_la_fiche(reglages, fiche())
                if texte:
                    params["messages"] = inserer_l_etat(list(params["messages"]), texte)
            except Exception as erreur:  # noqa: BLE001 -- l'état ne coûte jamais l'appel
                logger.error(f"[fiche] état non montré : {erreur}")
        return params

    llm.get_chat_completions = get_chat_completions
    llm.build_chat_completion_params = build_chat_completion_params
    return True
