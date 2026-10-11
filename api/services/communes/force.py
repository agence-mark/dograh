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


# [.mark] Chantier postscriptum-et-communes, lot 1 (11/10) : le nom de la personne.
# Ce que dit une personne qui donne son nom, ou un agent qui le demande (« nom », « prénom »,
# « comment vous appelez-vous », « je m'appelle »). ⛔ Mots de la langue, jamais d'un métier.
_MOTS_DU_NOM = frozenset("nom noms prenom prenoms appelle appelez appelles appelons appellent".split())
_CIVILITES = frozenset("monsieur madame mademoiselle m mme mlle mr".split())
# Ce qui, juste avant les mots, en fait un lieu malgré tout : « Dupont, à Creil » garde Creil.
# ⚠️ Pas « de », « du », « des » : ce sont aussi des particules de nom (« De Launay »).
_PREPOSITIONS_DE_LIEU = frozenset("a au aux sur en vers pres chez".split())
# Même plancher d'orthographe que le filtre du nom (L6) : deux mots courts qui partagent un son
# ne sont pas le même nom.
_PLANCHER_ORTHOGRAPHE = 60


def _meme_nom(entendu: str, noms: tuple[str, ...] | list[str]) -> bool:
    """Les mots entendus sont-ils le nom de la personne, écrit pareil ou dit au même son ?"""
    cible = normaliser(entendu or "").replace(" ", "")
    if len(cible) < 3:
        return False
    candidats: set[str] = set()
    for nom in noms:
        norm = normaliser(str(nom or ""))
        if not norm:
            continue
        candidats.add(norm.replace(" ", ""))
        candidats.update(m for m in norm.split() if len(m) >= 3)
    if cible in candidats:
        return True
    try:
        from rapidfuzz import fuzz

        from api.services.communes.base import cle_phonetique, cle_sonore

        son, son_maison = cle_phonetique(cible), cle_sonore(cible)
        for candidat in candidats:
            if fuzz.ratio(cible, candidat) < _PLANCHER_ORTHOGRAPHE:
                continue
            if cle_phonetique(candidat) == son or (son_maison and cle_sonore(candidat) == son_maison):
                return True
    except Exception:  # noqa: BLE001 -- sans module de son, le nom exact seulement
        return False
    return False


def _le_nom_est_demande_ou_donne(mots: list[str], debut: int, question_avant: str | None) -> bool:
    """La dernière question de l'agent demandait le nom, ou la personne le donne à ce tour
    (« je m'appelle », « mon nom c'est », une civilité juste avant les mots)."""
    if debut > 0 and mots[debut - 1] in _CIVILITES:
        return True
    if _MOTS_DU_NOM & set(mots[: max(debut, 0)]):
        return True
    return bool(question_avant and _MOTS_DU_NOM & set(normaliser(question_avant).split()))


def ecarter_le_nom(
    detections: list[Detection],
    texte: str,
    question_avant: str | None = None,
    noms_connus: tuple[str, ...] | list[str] = (),
) -> tuple[list[Detection], list[Detection]]:
    """(gardées, écartées) : une commune lue SANS signe de lieu (force « nom » ou « son ») n'est
    ni proposée ni mise à confirmer quand ses mots sont le nom de la personne.

    Run 1048 et rejeu 1088 (11/10) : « Delaunay », réponse à « Quel est votre nom ? », sortait
    Launay (Eure) à confirmer. Deux cas : ① les mots sont le nom déjà noté à la fiche, écrit pareil
    ou dit au même son (comme le filtre du nom, L6) ; ② une simple ressemblance (force « son »),
    quand l'agent venait de demander le nom ou que la personne le donne à ce tour, et que les mots
    ne suivent pas une préposition de lieu (« Dupont, à Creil » garde Creil). ⚠️ Pas une commune
    écrite exactement (force « nom ») : elle reste une recommandation, retenue seulement si l'outil
    la note comme commune (D4 ②, « Chantilly. »). Un signe de lieu (force « lieu ») ou un code postal dit l'emportent
    toujours : ni rayon ni perte (décision d'Evan du 17/09).
    """
    mots = normaliser(texte or "").split()
    gardees: list[Detection] = []
    ecartees: list[Detection] = []
    for d in detections:
        if d.force not in (NOM, SON) or d.code_postal_entendu:
            gardees.append(d)
            continue
        apres_une_preposition = 0 < d.debut <= len(mots) and mots[d.debut - 1] in _PREPOSITIONS_DE_LIEU
        if _meme_nom(d.entendu, noms_connus) or (
            d.force == SON
            and not apres_une_preposition
            and d.debut >= 0
            and _le_nom_est_demande_ou_donne(mots, d.debut, question_avant)
        ):
            ecartees.append(d)
        else:
            gardees.append(d)
    return gardees, ecartees


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
