"""[.mark] D4 (chantier correctifs-modules, 28/09) : la FORCE d'une commune lue.

Fiche allumée, le module des communes lit toutes les phrases, à tout moment de
l'appel : une adresse donnée à l'accueil se note. Ce qui change avec le contexte,
c'est la force de ce qu'il trouve :

① ``lieu`` : un signe de lieu dans le tour (un code postal dit, « j'habite »,
  « je suis à », « sur la commune de », un type de voie, ou la question d'adresse
  que l'agent vient de poser) → le verdict du module, comme avant ;
② ``nom`` : aucun signe, mais le nom d'une commune écrit exactement → une
  recommandation : jamais sûre d'elle-même, retenue sans question si l'outil
  note cette commune ;
③ ``son`` : aucun signe, une simple ressemblance (« depuis » → Deuillet,
  « granulés » → Grandrû) → jamais sûre, trace gardée.

Jamais « sûre » sans code postal compatible ou signe de lieu.

⛔ Les signes sont des mots de la LANGUE, jamais d'un métier : ce module vaut pour
n'importe quel client et n'importe quel secteur.
"""

from __future__ import annotations

from dataclasses import replace

from api.services.communes.analyse import A_CONFIRMER, SURE, Detection
from api.services.communes.base import BaseCommunes, normaliser

LIEU = "lieu"
NOM = "nom"
SON = "son"

# Ce que dit une personne qui donne son lieu, en mots normalisés.
_MOTS_DE_LIEU = frozenset(
    """habite habites habitons habitez habitent habitais habitait domicile domicilie domiciliee
    adresse commune ville village localite situe situee""".split()
)
_SUITES_DE_LIEU = (
    ("suis", "a"), ("sommes", "a"), ("code", "postal"), ("vis", "a"), ("vivons", "a"), ("lieu", "dit"),
)
# Les types de voie qui ne sont que des types (« route », « cours », « passage »
# sont aussi des mots courants : « en route », « au cours de »).
_TYPES_DE_VOIE = frozenset(
    "rue avenue boulevard chemin allee impasse place quai square residence lotissement ruelle sentier".split()
)
_TYPES_DE_VOIE |= {t + "s" for t in _TYPES_DE_VOIE}
# Ce que demande un agent qui vient de poser la question du lieu.
_MOTS_DE_QUESTION = frozenset(
    "adresse commune ville village localite habitez domicile situe situee".split()
)


def _suites(mots: list[str]) -> set[tuple[str, str]]:
    return set(zip(mots, mots[1:]))


def signe_de_lieu(texte: str, question_avant: str | None = None, code_postal_dit: bool = False) -> bool:
    """Le tour porte-t-il un signe de lieu ? ``texte`` : tout ce que la personne a
    dit dans ce tour ; ``question_avant`` : la dernière réplique de l'agent."""
    if code_postal_dit:
        return True
    mots = normaliser(texte or "").split()
    if (_MOTS_DE_LIEU | _TYPES_DE_VOIE) & set(mots):
        return True
    if _suites(mots) & set(_SUITES_DE_LIEU):
        return True
    if question_avant:
        demandes = normaliser(question_avant).split()
        if _MOTS_DE_QUESTION & set(demandes) or ("code", "postal") in _suites(demandes):
            return True
    return False


def _ecrite_exactement(detection: Detection, base: BaseCommunes) -> bool:
    entendu = normaliser(detection.entendu or "")
    return any(
        entendu and entendu == base.norms[base.par_insee[l.commune.insee]]
        for l in detection.lectures
    )


def appliquer_la_force(
    detections: list[Detection],
    base: BaseCommunes,
    signe: bool,
    codes_connus: set[str] | frozenset[str] = frozenset(),
) -> list[Detection]:
    """Chaque détection avec sa force ; sans signe de lieu, jamais sûre, sauf si sa
    commune porte un code postal connu (dit à ce tour ou retenu plus tôt)."""
    resultat = []
    for d in detections:
        if signe or d.code_postal_entendu:
            resultat.append(replace(d, force=LIEU))
            continue
        force = NOM if _ecrite_exactement(d, base) else SON
        compatible = bool(
            d.lectures and codes_connus and set(d.lectures[0].commune.cps) & set(codes_connus)
        )
        statut = d.statut if (d.statut != SURE or compatible) else A_CONFIRMER
        resultat.append(replace(d, force=force, statut=statut))
    return resultat
