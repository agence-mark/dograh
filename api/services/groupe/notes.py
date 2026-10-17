"""[.mark] Lot 2 d'orchestrateur-trois-cerveaux (D2, D3) : les notes de passation, aller et retour.

Ce qui voyage d'un agent à l'autre à une passation est écrit **par le code**, depuis la fiche de
l'appel, jamais par un modèle (plus de résumé rédigé) :

- **à l'aller**, sur la première étape du collègue appelé : le motif de départ, ce qui est déjà
  connu, la consigne de ne rien redemander de connu ;
- **au retour**, sur l'étape de retour de l'accueil : le collègue, le motif de départ, ce qui a
  été fait, ce qui est en attente, ce qui est déjà connu.

La note va dans le **prompt système de l'étape** (jamais dans l'historique, où elle serait lue comme
une parole de l'appelant), sans crochets (le filtre des crochets agit sur ce que dit le modèle),
titre en ``#``. Elle est **recalculée depuis la fiche** à chaque construction du prompt : au clavier,
où chaque tour refait le moteur, la note est donc la même qu'au téléphone.

Aucune phrase de métier : les libellés ci-dessous sont les libellés de la note, communs à tous les
agents. Toutes les fonctions sont pures et ne lèvent jamais (au pire : pas de note).
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from loguru import logger

from api.services.fiche.demandes import (
    champs_de_la_demande_en_cours,
    demandes_closes,
    dernier_specialise,
    portees_de,
    texte_court,
    DEMANDE,
)

# La clé de la fiche où le moteur range, par agent appelé, les noms de ses champs (la fiche de
# l'appel est fusionnée : sans cette trace, on ne saurait plus lesquels sont ceux du collègue).
CLE_CHAMPS_DES_AGENTS = "champs_des_agents"

# Les libellés de la note (données du code, pas du métier). Jamais de crochets.
TITRE_RETOUR = "# Retour du collègue « {nom} »"
TITRE_RETOUR_SANS_NOM = "# Retour du collègue"
TITRE_ALLER = "# Passation depuis l'accueil"
LIBELLE_MOTIF = "Motif de départ : "
LIBELLE_FAIT = "Fait : "
LIBELLE_ATTENTE = "En attente : "
LIBELLE_CONNU = "Déjà connu : "
RIEN = "rien"
MOTIF_NON_NOTE = "non noté"
FAIT_ETAPES = "étapes traversées : "
FAIT_CHAMPS = "champs remplis : "
CONSIGNE_RETOUR = (
    "L'appelant a une autre demande : traite-la, passe-la, ou conclus si c'est fini."
)
CONSIGNE_ALLER = (
    "Tu reprends la conversation là où elle en est : tout ce qui a été dit compte, "
    "tu ne redemandes rien de connu."
)


def _vide(valeur: Any) -> bool:
    if valeur is None:
        return True
    if isinstance(valeur, str):
        return not valeur.strip()
    if isinstance(valeur, (list, tuple, set, dict)):
        return len(valeur) == 0
    return False


def nom_lisible(nom: Any) -> str:
    """``code_postal`` -> ``code postal`` ; une seule ligne, jamais de crochets."""
    texte = " ".join(str(nom or "").replace("_", " ").split())
    return texte.replace("[", "(").replace("]", ")")


def _liste(noms: Iterable[Any]) -> str:
    return ", ".join(n for n in (nom_lisible(x) for x in noms) if n)


def noms_des_champs_remplis(reglages: Any, gathered: Mapping[str, Any] | None) -> list[str]:
    """Les noms des champs de la fiche que la vue à plat montre remplis, dans l'ordre de la fiche.
    Jamais la valeur. Sans fiche : rien."""
    try:
        champs = tuple(getattr(reglages, "champs", None) or ())
        return [c.nom for c in champs if not _vide((gathered or {}).get(c.nom))]
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[notes] champs remplis illisibles : {erreur!r}")
        return []


def ligne_deja_connu(
    reglages: Any,
    gathered: Mapping[str, Any] | None,
    champs_etape: Iterable[str] = (),
    deja_lus: Iterable[str] = (),
) -> str | None:
    """``Déjà connu : nom, prénom, commune.`` : la ligne courte collée à la question en cours (D4).

    Le complément exact des champs manquants du souffle de l'étape : parmi les champs que l'étape
    demande, ceux qui sont remplis ; une étape qui n'en déclare aucun montre tous les champs
    remplis de la fiche. ``deja_lus`` : ce qu'un module a lu au tour même (compte comme obtenu).
    Jamais la valeur. ``None`` si rien n'est connu. ⛔ Ne lève jamais."""
    try:
        champs = tuple(getattr(reglages, "champs", None) or ())
        connus = {c.nom for c in champs}
        de_l_etape = [n for n in champs_etape if n in connus]
        lus = set(deja_lus or ())
        base = de_l_etape or [c.nom for c in champs]
        noms = [n for n in base if not _vide((gathered or {}).get(n)) or n in lus]
        return f"{LIBELLE_CONNU}{_liste(noms)}." if noms else None
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[notes] ligne « déjà connu » illisible : {erreur!r}")
        return None


def noter_les_champs_de_l_agent(gathered: dict, agent_id: Any, reglages_agent: Any) -> None:
    """Le moteur range les noms des champs de l'agent appelé dans la fiche de l'appel, à la
    fusion. Seulement s'il en a (fiche allumée). ⛔ Ne lève jamais."""
    try:
        if agent_id is None or reglages_agent is None:
            return
        noms = [c.nom for c in getattr(reglages_agent, "champs", None) or ()]
        if noms:
            gathered.setdefault(CLE_CHAMPS_DES_AGENTS, {})[str(agent_id)] = noms
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[notes] champs de l'agent non notés : {erreur!r}")


def _passations_du_collegue(gathered: Mapping[str, Any], collegue_id: Any) -> list[dict]:
    return [
        e
        for e in (gathered.get("passations") or [])
        if isinstance(e, dict)
        and not e.get("refusee")
        and e.get("issue", "completed") == "completed"
        and e.get("vers") == collegue_id
        and e.get("raison") != "retour"
    ]


def _etapes_du_collegue(gathered: Mapping[str, Any], collegue_id: Any) -> list[str]:
    """Les étapes de sa DERNIÈRE visite (la suite d'entrées de ``parcours_etapes`` à lui), sans la
    dernière : c'est l'étape de retour, par où il a rendu la main."""
    entrees = [e for e in (gathered.get("parcours_etapes") or []) if isinstance(e, dict)]
    fin = next(
        (i for i in range(len(entrees) - 1, -1, -1) if entrees[i].get("agent_id") == collegue_id),
        None,
    )
    if fin is None:
        return []
    debut = fin
    while debut > 0 and entrees[debut - 1].get("agent_id") == collegue_id:
        debut -= 1
    noms = [str(e.get("etape")) for e in entrees[debut : fin + 1] if e.get("etape")]
    return noms[:-1] if len(noms) > 1 else []


def _nom_du_collegue(gathered: Mapping[str, Any], collegue_id: Any, noms: Mapping[Any, Any] | None):
    for e in reversed(gathered.get("parcours_etapes") or []):
        if isinstance(e, dict) and e.get("agent_id") == collegue_id and e.get("agent"):
            return str(e["agent"])
    nom = (noms or {}).get(collegue_id)
    return str(nom) if nom else None


def _motif(
    gathered: Mapping[str, Any], champ_motif: str | None, collegue_id: Any, outil: str | None
) -> str | None:
    """Le champ « motif » de la fiche (réglé par l'organisation, jamais un nom en dur), sinon le
    motif de la dernière demande close de ce collègue, sinon le nom de l'outil de passation."""
    if champ_motif:
        valeur = texte_court(gathered.get(champ_motif))
        if valeur:
            return valeur
        for bloc in reversed(demandes_closes(gathered)):
            if bloc.get("agent_id") == collegue_id and bloc.get("motif"):
                return str(bloc["motif"])
    return nom_lisible(outil) or None if outil else None


def note_de_retour(
    reglages: Any,
    gathered: Mapping[str, Any] | None,
    *,
    principal_id: Any,
    champ_motif: str | None = None,
    noms: Mapping[Any, Any] | None = None,
) -> str | None:
    """La note de l'étape de retour de l'accueil (§ 2.1 du plan). ``None`` si aucun collègue n'a
    encore pris la main dans cet appel. ⛔ Ne lève jamais."""
    try:
        gathered = gathered or {}
        collegue_id = dernier_specialise(gathered, principal_id)
        if collegue_id is None:
            return None
        nom = _nom_du_collegue(gathered, collegue_id, noms)
        passations = _passations_du_collegue(gathered, collegue_id)
        outil = passations[-1].get("raison") if passations else None
        motif = _motif(gathered, champ_motif, collegue_id, outil) or MOTIF_NON_NOTE

        faits = []
        etapes = _etapes_du_collegue(gathered, collegue_id)
        if etapes:
            faits.append(FAIT_ETAPES + " › ".join(nom_lisible(e) for e in etapes))
        remplis = (
            [c.nom for c in champs_de_la_demande_en_cours(reglages, gathered)]
            if reglages is not None
            else []
        )
        if remplis:
            faits.append(FAIT_CHAMPS + _liste(remplis))

        en_attente: list[str] = []
        if reglages is not None:
            portees = portees_de(reglages)
            propres = (gathered.get(CLE_CHAMPS_DES_AGENTS) or {}).get(str(collegue_id))
            en_attente = [
                c.nom
                for c in reglages.champs
                if portees.get(c.nom) == DEMANDE
                and _vide(gathered.get(c.nom))
                and (not propres or c.nom in propres)
            ]
        connus = noms_des_champs_remplis(reglages, gathered)

        titre = TITRE_RETOUR.format(nom=nom) if nom else TITRE_RETOUR_SANS_NOM
        return "\n".join(
            [
                titre,
                f"{LIBELLE_MOTIF}{motif}",
                f"{LIBELLE_FAIT}{' ; '.join(faits) if faits else RIEN}",
                f"{LIBELLE_ATTENTE}{_liste(en_attente) if en_attente else RIEN}",
                f"{LIBELLE_CONNU}{_liste(connus) if connus else RIEN}",
                CONSIGNE_RETOUR,
            ]
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[notes] note de retour non écrite : {erreur!r}")
        return None


def note_d_aller(
    reglages: Any,
    gathered: Mapping[str, Any] | None,
    *,
    outil: str | None,
    champ_motif: str | None = None,
) -> str | None:
    """La note de la première étape du collègue appelé (§ 2.1). ``outil`` : le nom de l'outil de
    passation appelé. ⛔ Ne lève jamais."""
    try:
        gathered = gathered or {}
        valeur = texte_court(gathered.get(champ_motif)) if champ_motif else None
        nom_outil = nom_lisible(outil)
        if valeur and nom_outil:
            motif = f"{nom_outil} ({valeur})"
        else:
            motif = valeur or nom_outil or MOTIF_NON_NOTE
        connus = noms_des_champs_remplis(reglages, gathered)
        return "\n".join(
            [
                TITRE_ALLER,
                f"{LIBELLE_MOTIF}{motif}",
                f"{LIBELLE_CONNU}{_liste(connus) if connus else RIEN}",
                CONSIGNE_ALLER,
            ]
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[notes] note d'aller non écrite : {erreur!r}")
        return None


def outil_de_passation_vers(gathered: Mapping[str, Any] | None, agent_id: Any) -> str | None:
    """Le nom de l'outil de la dernière passation aboutie vers cet agent (au clavier, où chaque tour
    refait le moteur : la note d'aller se recalcule depuis la fiche). ⛔ Ne lève jamais."""
    try:
        faites = _passations_du_collegue(gathered or {}, agent_id)
        return str(faites[-1].get("raison")) if faites and faites[-1].get("raison") else None
    except Exception:  # noqa: BLE001
        return None
