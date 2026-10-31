"""[.mark] Builder, lot 6 : les critères et le verdict PAR LE CODE (Q1, B40, B42), communs au clavier et à l'appel simulé.

Parité clavier / téléphone : le verdict se calcule sur une ``ObservationConversation``, et celle-ci se lit dans le JOURNAL
du run (``realtime_feedback_events`` + fiche), le même pour une session clavier et pour un appel simulé
(``observation_depuis_un_run``). Un test joué par l'un ou l'autre suit donc exactement les mêmes critères.

Critères (champ ``type``) : les quatre de ``tests_rejouables`` (``etape``, ``outil``, ``texte_present``, ``texte_absent``) et,
pour une conversation entière : ``issue``, ``appel_clos_par_l_agent``, ``mecanique_dite``, ``merci_en_tete``,
``coordonnees_prises``, ``sans_redite``, ``sans_rigidite``.

B40 : chaque critère raté rend aussi le ``rang`` de la RÉPLIQUE DE L'AGENT fautive (de 0) et la ``raison`` écrite pour elle.
B42 : un test obligatoire qui échoue suffit à refuser ; jamais la moyenne (voir ``execution``).

⛔ Zéro vocabulaire métier : les mots cherchés sont ceux du critère, jamais du code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from api.services.tests_rejouables.modele import (
    ErreurTestRejouable,
    Observation,
    evaluer,
    normaliser,
    valider_critere,
)

TYPES_DE_BASE = ("etape", "outil", "texte_present", "texte_absent")
TYPES_DE_CONVERSATION = (
    "issue",
    "appel_clos_par_l_agent",
    "mecanique_dite",
    "merci_en_tete",
    "coordonnees_prises",
    "sans_redite",
    "sans_rigidite",
)
TYPES = TYPES_DE_BASE + TYPES_DE_CONVERSATION
MAX_CRITERES = 12
# Le champ « critere » du format v1 est obligatoire : un test sans critère de base porte celui-ci, toujours vrai.
CRITERE_NEUTRE = {"type": "texte_absent", "texte": "§§aucun§§"}


@dataclass
class ObservationConversation(Observation):
    """Ce qu'une conversation entière (ou un tour) a produit. ``lignes`` : [("agent"|"moi", texte)] dans l'ordre."""

    lignes: list[tuple[str, str]] = field(default_factory=list)
    issue: str | None = None
    clos_par_l_agent: bool | None = None
    fiche: dict[str, Any] = field(default_factory=dict)

    def repliques_de_l_agent(self) -> list[str]:
        return [t for r, t in self.lignes if r == "agent"]

    def en_json(self) -> dict[str, Any]:
        return {
            **Observation.en_json(self),
            "lignes": [[r, t] for r, t in self.lignes],
            "issue": self.issue,
            "clos_par_l_agent": self.clos_par_l_agent,
        }


@dataclass
class ResultatCritere:
    critere: dict[str, Any]
    reussi: bool
    detail: str
    rang: int | None = None  # B40 : la réplique de l'agent fautive (de 0)
    raison: str | None = None

    def en_json(self) -> dict[str, Any]:
        return {"critere": self.critere, "reussi": self.reussi, "detail": self.detail, "rang": self.rang, "raison": self.raison}


# --- validation -------------------------------------------------------------------------------------------------------


def valider_criteres(criteres: Any) -> list[dict[str, Any]]:
    """Les critères, validés ; ``ErreurTestRejouable`` avec la raison. Au moins un, 12 au plus."""
    if not isinstance(criteres, list) or not criteres:
        raise ErreurTestRejouable("a test needs at least one criterion")
    if len(criteres) > MAX_CRITERES:
        raise ErreurTestRejouable(f"at most {MAX_CRITERES} criteria")
    propres = []
    for c in criteres:
        if not isinstance(c, dict):
            raise ErreurTestRejouable("a criterion is an object")
        genre = c.get("type")
        if genre in TYPES_DE_BASE:
            propres.append(valider_critere(c))
            continue
        if genre not in TYPES_DE_CONVERSATION:
            raise ErreurTestRejouable(f"unknown criterion type {genre!r} (expected: {', '.join(TYPES)})")
        if genre == "issue" and not str(c.get("attendue") or "").strip():
            raise ErreurTestRejouable("criterion « issue » : « attendue » is empty")
        if genre == "mecanique_dite" and not (isinstance(c.get("noms"), list) and c["noms"]):
            raise ErreurTestRejouable("criterion « mecanique_dite » : « noms » (the names that must never be said) is empty")
        if genre == "coordonnees_prises" and not (isinstance(c.get("champs"), list) and c["champs"]):
            raise ErreurTestRejouable("criterion « coordonnees_prises » : « champs » is empty")
        propres.append(c)
    return propres


# --- le relevé commun : redites, tics, rigidité (porté de la méthode du labo, générique) ---------------------------------------

SUJETS_GENERIQUES = {
    "nom": r"nom de famille|votre nom|epel",
    "prenom": r"prenom",
    "numero": r"numero de tel|votre numero|joindre|telephone",
    "commune": r"commune|ville",
    "code postal": r"code postal",
    "adresse": r"adresse|\brue\b",
    "reference": r"reference",
    "date": r"\bdate\b|quel jour|quand",
}
SENS_CONFIRMATION = r"c'est bien (ca|cela)|c'est correct|c'est exact|c'est juste"


def _phrases(texte: str) -> list[str]:
    return [p.strip() for p in re.split(r"(?<=[.!?])\s+", texte) if len(p.strip()) > 12]


def releve(lignes: list[tuple[str, str]]) -> dict[str, list[tuple[int, str]]]:
    """(rang de la réplique de l'agent, texte) pour chaque redite, tic et rigidité. Pur."""
    agent = [t for r, t in lignes if r == "agent"]
    sortie: dict[str, list[tuple[int, str]]] = {"redites": [], "tics": [], "rigidite": []}
    vues: list[tuple[int, str]] = []
    for i, t in enumerate(agent):
        for p in _phrases(t):
            n = re.sub(r"\W+", " ", normaliser(p)).strip()
            for j, q in vues:
                if j != i and SequenceMatcher(None, n, q).ratio() >= 0.85 and not re.search(SENS_CONFIRMATION, n):
                    sortie["redites"].append((i, f"repeats turn {j + 1}: « {p[:90]} »"))
                    break
            vues.append((i, n))
        if re.match(r"\s*merci\b(?! de votre appel)", normaliser(t)):
            sortie["tics"].append((i, f"starts with « Merci »: « {t[:60]} »"))
    demandes: dict[str, list[int]] = {}
    for i, t in enumerate(agent):
        if "?" not in t or re.search(SENS_CONFIRMATION, normaliser(t)):
            continue
        for sujet, motif in SUJETS_GENERIQUES.items():
            if re.search(motif, normaliser(t)):
                demandes.setdefault(sujet, []).append(i)
    indices_moi = [k for k, (r, _) in enumerate(lignes) if r == "moi"]
    pos_agent = [k for k, (r, _) in enumerate(lignes) if r == "agent"]
    for sujet, rangs in demandes.items():
        for a, b in zip(rangs, rangs[1:]):
            if any(pos_agent[a] < k < pos_agent[b] for k in indices_moi):
                sortie["rigidite"].append((b, f"asks « {sujet} » again after the caller answered"))
                break
    return sortie


# --- l'évaluation -------------------------------------------------------------------------------------------------------------


def _rang_de_la_ligne(lignes: list[tuple[str, str]], contient: str) -> int | None:
    cherche = normaliser(contient)
    for rang, texte in enumerate(t for r, t in lignes if r == "agent"):
        if cherche and cherche in normaliser(texte):
            return rang
    return None


def _derniere(obs: ObservationConversation) -> int | None:
    n = len(obs.repliques_de_l_agent())
    return n - 1 if n else None


def evaluer_un(critere: dict[str, Any], obs: ObservationConversation) -> ResultatCritere:
    genre = critere["type"]
    derniere = _derniere(obs)
    if genre in TYPES_DE_BASE:
        reussi, detail = evaluer(critere, obs)
        rang: int | None = None
        if not reussi:
            if genre == "texte_absent":
                rang = _rang_de_la_ligne(obs.lignes, critere["texte"])
            elif genre == "outil" and critere.get("appele", True) is False:
                rang = next((o.get("rang") for o in obs.outils if o.get("nom") == critere["nom"] and o.get("rang") is not None), derniere)
            else:
                rang = derniere
        raison = None if reussi else _raison_de_base(critere, detail)
        return ResultatCritere(critere, reussi, detail, rang, raison)
    if genre == "issue":
        reussi = normaliser(obs.issue) == normaliser(critere["attendue"])
        return _fin(critere, reussi, f"issue : {obs.issue or 'aucune'}", derniere, f"The call ended with « {obs.issue or 'no outcome'} », not « {critere['attendue']} ».")
    if genre == "appel_clos_par_l_agent":
        voulu = critere.get("attendu", True) is not False
        reussi = (obs.clos_par_l_agent is True) == voulu
        return _fin(critere, reussi, f"appel clos par l'agent : {obs.clos_par_l_agent}", derniere, "The agent did not close the call." if voulu else "The agent closed the call when it should not.")
    if genre == "mecanique_dite":
        for nom in critere["noms"]:
            rang = _rang_de_la_ligne(obs.lignes, str(nom))
            if rang is not None:
                return ResultatCritere(critere, False, f"dit : {nom}", rang, f"The agent said « {nom} » aloud: a tool name or a mechanic must stay silent.")
        return ResultatCritere(critere, True, "aucun nom d'outil ou de mécanique dit")
    if genre == "merci_en_tete":
        maxi = int(critere.get("max", 0))
        tetes = [i for i, t in enumerate(obs.repliques_de_l_agent()) if re.match(r"\s*merci\b(?! de votre appel)", normaliser(t))]
        if len(tetes) > maxi:
            return ResultatCritere(critere, False, f"{len(tetes)} réplique(s) commencent par « Merci »", tetes[maxi], "The reply starts with « Merci »: a tic.")
        return ResultatCritere(critere, True, f"{len(tetes)} réplique(s) commencent par « Merci »")
    if genre == "coordonnees_prises":
        manquants = [c for c in critere["champs"] if obs.fiche.get(c) in (None, "", [])]
        return _fin(critere, not manquants, f"champs pris : {len(critere['champs']) - len(manquants)}/{len(critere['champs'])}", derniere, f"Not taken: {', '.join(map(str, manquants))}.")
    rel = releve(obs.lignes)
    cle, libelle = ("redites", "redite") if genre == "sans_redite" else ("rigidite", "rigidité")
    if rel[cle]:
        rang, texte = rel[cle][0]
        return ResultatCritere(critere, False, f"{libelle} : {texte}", rang, f"The agent {texte}.")
    return ResultatCritere(critere, True, f"aucune {libelle}")


def _fin(critere: dict[str, Any], reussi: bool, detail: str, derniere: int | None, raison: str) -> ResultatCritere:
    return ResultatCritere(critere, reussi, detail, None if reussi else derniere, None if reussi else raison)


def _raison_de_base(critere: dict[str, Any], detail: str) -> str:
    genre = critere["type"]
    if genre == "texte_absent":
        return f"This reply says « {critere['texte']} », which it must not."
    if genre == "texte_present":
        return f"No reply says « {critere['texte']} »."
    if genre == "outil":
        return f"Tool « {critere['nom']} » {'was called but must not be' if critere.get('appele', True) is False else 'was not called as expected'} ({detail})."
    return f"The call did not reach the expected step « {critere.get('attendue')} » ({detail})."


def evaluer_criteres(criteres: list[dict[str, Any]], obs: ObservationConversation) -> list[ResultatCritere]:
    return [evaluer_un(c, obs) for c in criteres]


def reussi(resultats: list[ResultatCritere]) -> bool:
    return all(r.reussi for r in resultats)


def observation_depuis_un_essai(observe: dict[str, Any], texte_de_l_appelant: str | None = None) -> ObservationConversation:
    """Une ``Observation`` de ``tests_rejouables`` (un tour rejoué) relue comme une conversation d'un tour."""
    lignes: list[tuple[str, str]] = []
    if texte_de_l_appelant:
        lignes.append(("moi", texte_de_l_appelant))
    lignes.append(("agent", observe.get("texte") or ""))
    etape = observe.get("etape") or {}
    return ObservationConversation(
        texte=observe.get("texte") or "",
        outils=list(observe.get("outils") or []),
        etape_id=etape.get("id"),
        etape_nom=etape.get("nom"),
        etapes_traversees=list(observe.get("etapes_traversees") or []),
        simules=list(observe.get("simules") or []),
        lignes=lignes,
        issue=observe.get("issue"),
        clos_par_l_agent=observe.get("clos_par_l_agent"),
        fiche=dict(observe.get("fiche") or {}),
    )


# --- parité : l'observation se lit dans le journal du run (clavier ou appel simulé) ----------------------------------------------


def observation_depuis_un_run(
    journal: list[dict[str, Any]], contexte_final: dict[str, Any] | None, noeuds_de_fin: set[str] | None = None
) -> ObservationConversation:
    """Le même verdict pour un run clavier et un appel simulé : les deux écrivent ``realtime_feedback_events``."""
    from api.services.pipecat.realtime_feedback_events import realtime_feedback_event_sort_key

    contexte_final = contexte_final or {}
    lignes: list[tuple[str, str]] = []
    outils: list[dict[str, Any]] = []
    etapes: list[tuple[str | None, str]] = []
    for ev in sorted(journal or [], key=realtime_feedback_event_sort_key):
        genre, p = ev.get("type"), ev.get("payload") or {}
        if genre == "rtf-user-transcription" and p.get("final") and str(p.get("text") or "").strip():
            lignes.append(("moi", str(p["text"]).strip()))
        elif genre == "rtf-bot-text" and str(p.get("text") or "").strip():
            texte = str(p["text"]).strip()
            if lignes and lignes[-1][0] == "agent":
                lignes[-1] = ("agent", f"{lignes[-1][1]} {texte}")
            else:
                lignes.append(("agent", texte))
        elif genre == "rtf-function-call-start":
            rang = sum(1 for r, _ in lignes if r == "agent") - 1
            outils.append({"nom": p.get("function_name"), "arguments": p.get("arguments") or {}, "rang": max(rang, 0)})
        elif genre == "rtf-node-transition":
            etapes.append((p.get("node_id") or ev.get("node_id"), p.get("node_name") or ev.get("node_name") or ""))
    derniere_etape = etapes[-1] if etapes else (None, "")
    clos = None
    if noeuds_de_fin is not None and etapes:
        clos = str(derniere_etape[0]) in noeuds_de_fin
    return ObservationConversation(
        texte=" ".join(t for r, t in lignes if r == "agent"),
        outils=outils,
        etape_id=derniere_etape[0],
        etape_nom=derniere_etape[1] or None,
        etapes_traversees=[nom for _, nom in etapes],
        lignes=lignes,
        issue=contexte_final.get("call_disposition"),
        clos_par_l_agent=clos,
        fiche={k: v for k, v in contexte_final.items() if isinstance(k, str)},
    )
