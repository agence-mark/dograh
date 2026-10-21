"""[.mark] Chantier fiabilite-orchestration (F18, F23) puis correctifs-apres-banc-v4 (lot 4) : la phrase
en vigueur pour un motif.

Huit rangs, du plus précis au plus général : **étape + outil**, **étape**, **agent + outil**, **agent**,
**groupe + outil**, **groupe** (les règles « groupe » du principal), l'**ancien réglage** repris (F17 : la
phrase pont et la mise en relation, réglées avant le chantier sur le principal, valent règle « groupe »
tant que le thème Phrases ne les a pas réécrites), puis le **défaut** du catalogue. Un spécialisé reprend
donc la phrase du principal tant qu'il n'a pas la sienne. La résolution dit le niveau d'où vient la
phrase (la carte l'affiche). Une étape se repère par son identifiant de nœud ; une règle d'avant,
écrite avec le nom seul, se relit par le nom. Un outil se repère par son nom de fonction.

⛔ Ne lève jamais : une règle illisible est ignorée (journalisée), le niveau suivant s'applique.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from api.schemas.phrases_du_code import (
    ALIAS_DE_MOTIFS,
    ORDRE_TOURNEES,
    PORTEE_AGENT,
    PORTEE_ETAPE,
    PORTEE_GROUPE,
    ReglePhrase,
    Sortie,
)
from api.services.phrases.catalogue import (
    MISE_EN_RELATION,
    MOTIFS,
    PASSATION_TARDE,
    Motif,
)

CLE_REGLES = "phrases_regles"

NIVEAU_ETAPE = "etape"
NIVEAU_AGENT = "agent"
NIVEAU_PRINCIPAL = "principal"
NIVEAU_DEFAUT = "defaut"


@dataclass(frozen=True)
class PhraseResolue:
    motif: Motif
    variantes: tuple[str, ...]
    delai_s: float | None
    active: bool
    niveau: str
    # Le délai vient d'une règle qui le pose (et non du défaut du catalogue) : la relance de
    # silence garde sinon le réglage de Rythme (lot 5).
    delai_pose: bool = False
    # -- correctifs-apres-banc-v4 : les cases nouvelles (défauts = le comportement d'avant) --
    ordre: str = ORDRE_TOURNEES
    redite_s: float | None = None
    # Par attente, la première comprise (1 = une seule fois, comme avant) ; ``max_pose`` : la règle
    # l'a posé (le silence garde sinon le réglage de Rythme).
    max_par_attente: int = 1
    max_pose: bool = False
    max_par_appel: int | None = None
    ensuite: Sortie = field(default_factory=Sortie)
    texte_de_l_agent: bool = False
    outils: tuple[str, ...] = ()
    # La clé de la règle d'où vient la phrase (compteur dans l'appel) ; ``None`` : le défaut.
    cle: tuple | None = None

    @property
    def dite(self) -> bool:
        return self.active and bool(self.variantes)

    @property
    def posee(self) -> bool:
        """Venue d'une règle réglée (ou de l'ancien réglage), non du défaut du catalogue."""
        return self.niveau != NIVEAU_DEFAUT

    @property
    def action_de_sortie(self) -> str:
        return self.ensuite.action or self.motif.sortie_defaut

    @property
    def sortie_posee(self) -> bool:
        """La règle règle sa sortie : sinon le comportement d'avant de chaque motif."""
        return self.ensuite.posee


def regles_de(reglages: Mapping[str, Any] | None) -> list[ReglePhrase]:
    """Les règles lisibles de ces réglages d'agent, dans leur ordre. ⛔ Ne lève jamais."""
    brutes = (reglages or {}).get(CLE_REGLES) if isinstance(reglages, Mapping) else None
    regles: list[ReglePhrase] = []
    for brute in brutes or []:
        try:
            regles.append(
                brute if isinstance(brute, ReglePhrase) else ReglePhrase.model_validate(brute)
            )
        except Exception as erreur:  # noqa: BLE001 -- une règle illisible ne coûte pas l'appel
            logger.warning(f"[phrases] règle illisible ignorée : {erreur!r}")
    return regles


def _depuis_la_regle(regle: ReglePhrase, motif: Motif, niveau: str) -> PhraseResolue:
    return PhraseResolue(
        motif=motif,
        variantes=tuple(regle.variantes),
        delai_s=(
            (regle.delai_s if regle.delai_s is not None else motif.delai_defaut_s)
            if motif.a_un_delai
            else None
        ),
        active=regle.active,
        niveau=niveau,
        delai_pose=bool(motif.a_un_delai and regle.delai_s is not None),
        ordre=regle.ordre,
        redite_s=regle.redite_s if motif.peut_redire else None,
        max_par_attente=(regle.max_par_attente or 1) if motif.peut_redire else 1,
        max_pose=bool(motif.peut_redire and regle.max_par_attente is not None),
        max_par_appel=regle.max_par_appel,
        ensuite=regle.ensuite,
        texte_de_l_agent=regle.texte_de_l_agent,
        outils=tuple(regle.outils),
        cle=regle.cle,
    )


def defaut_du_motif(motif: Motif) -> PhraseResolue:
    return PhraseResolue(
        motif=motif,
        variantes=motif.variantes_defaut,
        delai_s=motif.delai_defaut_s,
        active=motif.actif_par_defaut,
        niveau=NIVEAU_DEFAUT,
    )


def ancien_reglage(motif: Motif, reglages: Mapping[str, Any] | None) -> PhraseResolue | None:
    """F17, reprise : la phrase réglée avant le chantier, hors du thème Phrases (``attente.phrase_pont``
    et son délai, ``transfert_humain.phrase_mise_en_relation``), lue comme une règle « groupe » du
    principal. ``None`` : rien de posé. ⛔ Ne lève jamais."""
    try:
        if not isinstance(reglages, Mapping):
            return None
        if motif.id == PASSATION_TARDE:
            from api.services.groupe.reglages_passation import attente_de

            attente = attente_de(reglages)
            if not attente.phrase_pont:
                return None
            return PhraseResolue(
                motif=motif,
                variantes=(attente.phrase_pont,),
                delai_s=attente.delai_phrase_pont_s,
                active=True,
                niveau=NIVEAU_PRINCIPAL,
            )
        if motif.id == MISE_EN_RELATION:
            from api.services.groupe.reglages_passation import phrase_de_mise_en_relation

            texte = phrase_de_mise_en_relation(reglages)
            if not texte:
                return None
            return PhraseResolue(
                motif=motif, variantes=(texte,), delai_s=None, active=True, niveau=NIVEAU_PRINCIPAL
            )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[phrases] ancien réglage de {motif.id} illisible : {erreur!r}")
    return None


def _nom_d_outil(nom: Any) -> str:
    """Le nom de fonction d'un outil, comme le modèle le voit (une règle vise le nom de fonction)."""
    texte = str(nom or "").strip()
    if not texte:
        return ""
    try:
        from api.services.workflow.tools.custom_tool import custom_tool_function_name

        return custom_tool_function_name(texte)
    except Exception:  # noqa: BLE001 -- sans le normaliseur, le nom tel quel
        return texte


def _vise_l_outil(regle: ReglePhrase, outil: str | None) -> bool:
    """Une règle sans outil vaut pour tous ; une règle qui en nomme ne vaut que pour eux."""
    if not regle.outils:
        return True
    if not outil:
        return False
    return outil in {_nom_d_outil(nom) for nom in regle.outils} | set(regle.outils)


def _vise_l_etape(regle: ReglePhrase, etape: str | None, etape_id: str | None) -> bool:
    """Par l'identifiant du nœud quand la règle le porte (renommer l'étape garde ses règles), sinon
    par le nom (règle d'avant)."""
    if regle.portee != PORTEE_ETAPE:
        return False
    if regle.etape_id:
        return bool(etape_id) and regle.etape_id == etape_id
    return bool(etape) and regle.etape == etape


def _meilleure(regles: list[ReglePhrase], outil: str | None) -> ReglePhrase | None:
    """Parmi des règles du même endroit : celle qui nomme l'outil d'abord, sinon celle de tous."""
    if outil:
        for regle in regles:
            if regle.outils and _vise_l_outil(regle, outil):
                return regle
    for regle in regles:
        if not regle.outils:
            return regle
    return None


def resoudre(
    motif_id: str,
    *,
    reglages_agent: Mapping[str, Any] | None = None,
    reglages_principal: Mapping[str, Any] | None = None,
    etape: str | None = None,
    etape_id: str | None = None,
    outil: str | None = None,
) -> PhraseResolue | None:
    """La phrase en vigueur pour ``motif_id`` chez cet agent, à cette étape, pour cet outil. ``None`` :
    motif inconnu. ``reglages_principal`` peut être les réglages de l'agent lui-même (il est le
    principal, ou un agent seul) : ses règles « groupe » valent alors pour lui.

    Ordre : étape + outil, étape, agent + outil, agent, groupe + outil, groupe, ancien réglage, défaut.
    ``outil`` n'a d'effet que pour un motif qui permet de viser un outil."""
    motif_id = ALIAS_DE_MOTIFS.get(motif_id, motif_id)
    motif = MOTIFS.get(motif_id)
    if motif is None:
        return None
    outil = _nom_d_outil(outil) if (outil and motif.filtre_outil) else None
    try:
        propres = [r for r in regles_de(reglages_agent) if r.motif == motif_id]
        regle = _meilleure([r for r in propres if _vise_l_etape(r, etape, etape_id)], outil)
        if regle is not None:
            return _depuis_la_regle(regle, motif, NIVEAU_ETAPE)
        regle = _meilleure([r for r in propres if r.portee == PORTEE_AGENT], outil)
        if regle is not None:
            return _depuis_la_regle(regle, motif, NIVEAU_AGENT)
        # Une règle « groupe » posée sur un agent qui n'est pas le principal vaut pour lui seul.
        regle = _meilleure([r for r in propres if r.portee == PORTEE_GROUPE], outil)
        if regle is not None:
            return _depuis_la_regle(regle, motif, NIVEAU_AGENT)
        if reglages_principal is not None and reglages_principal is not reglages_agent:
            du_groupe = [
                r
                for r in regles_de(reglages_principal)
                if r.motif == motif_id and r.portee == PORTEE_GROUPE
            ]
            regle = _meilleure(du_groupe, outil)
            if regle is not None:
                return _depuis_la_regle(regle, motif, NIVEAU_PRINCIPAL)
        ancienne = ancien_reglage(
            motif, reglages_principal if reglages_principal is not None else reglages_agent
        )
        if ancienne is not None:
            return ancienne
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[phrases] résolution de {motif_id} illisible : {erreur!r}")
    return defaut_du_motif(motif)
