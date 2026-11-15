"""[.mark] Mécanisme commun : le MOTEUR de recherche dans une liste fermée (module Restauration, lot 4).

Remplace le moteur minimal de ``recherche_liste.py`` (``poser_moteur``), même forme de retour : ``RETENU`` (un seul élément, sûr),
``AMBIGU`` (2 ou 3 choix et la question), ``INTROUVABLE`` (les plus proches). Local, sans appel réseau, moins de 50 ms.
ZÉRO FAUX SÛR est l'exigence : un élément n'est retenu que s'il est seul à tenir (``banc`` le mesure, ``recherche_liste_banc.py``).

Les couches, de la plus sûre à la plus lâche (le score est un nombre de 0 à 1 ; ``seuil_retenu`` par défaut 0,90) :

| Couche | Ce qu'elle voit | Score |
|---|---|---|
| exact | même texte après nettoyage (casse, accents, ponctuation, pluriel, petits mots) | 1,00 |
| contenu | tous les mots dits sont dans le nom (« coca » dans « coca cola ») | 0,90 à 0,99 selon la part du nom dite |
| contient | le nom entier est dans ce qui est dit, avec des mots en plus | 0,88 (proposition) |
| lettres | lettres en commun (``rapidfuzz``), fautes de transcription | jusqu'à 0,97 si très proche, sinon proposition |
| son | même son (``phonetic_fr``) | 0,91 si identique (nombre de mots égal), sinon proposition |
| sens | fournie de l'extérieur (``couche_sens``) | JAMAIS retenu : propose seulement (plafonné sous le seuil) |

Le contenant et la taille sont lus comme des OPTIONS (« canette de coca 33 cl » : élément « coca cola », contenant « canette »,
taille « 33cl ») et ne gênent pas la recherche du nom. Les mots de catégorie (donnés par l'appelant, tirés des données) sont
écartés sur une seconde lecture : jamais la seule.

Aucun mot propre à un métier ici : les mots de catégorie, les synonymes et les variantes viennent des données de la liste.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from api.db.bases_clients.recherche_liste import Element, normaliser

# Petits mots et formules de politesse : jamais un nom. (Après ``normaliser`` : sans accent, sans pluriel.)
PETITS_MOTS = frozenset(
    normaliser(m) for m in "de du des d la le les l un une au aux a et avec pour en s j je voudrais veux prends prendrai prendrais prendre vais donne donnez moi "
    "me mets mettez ajoute ajoutez ce cet cette ca il y plait vous si svp bonjour quantite alors aussi encore sinon".split()
)  # passés par ``normaliser`` : « voudrais » s'écrit comme la demande, sans le pluriel
CONTENANTS = frozenset("canette bouteille verre pot bol boite brique sachet fut carafe pichet bidon barquette flacon tasse".split())
_UNITES = {"cl": "cl", "ml": "ml", "l": "l", "litre": "l", "g": "g", "kg": "kg", "cm": "cm"}
_TAILLE = re.compile(r"\b(\d+(?: \d{1,2})?) ?(cl|ml|litre|l|kg|g|cm)\b")

NB_CANDIDATS = 3
PLANCHER_PROCHES = 0.5


@dataclass(frozen=True)
class Reglages:
    """Les réglages de construction (les seuils sont ceux du module au registre)."""

    seuil_retenu: float = 0.90
    seuil_ambigu: float = 0.72  # en dessous : ce n'est plus une proposition (INTROUVABLE)
    ecart_minimal: float = 0.03  # écart exigé entre le premier et le deuxième pour retenir (sauf un seul exact)
    couche_son: bool = True
    couche_sens: bool = False
    mots_de_categorie: tuple[str, ...] = ()


@dataclass(frozen=True)
class Forme:
    """Une façon d'écrire un élément (son nom ou un synonyme), préparée une fois."""

    texte: str
    jetons: tuple[str, ...]
    joint: str
    ensemble: frozenset[str]
    son: str


@dataclass(frozen=True)
class EntreeIndex:
    element: Element
    formes: tuple[Forme, ...]
    rangement: frozenset[str] = frozenset()  # les mots de son rangement
    noms: frozenset[str] = frozenset()  # les mots de tous ses noms


@dataclass(frozen=True)
class Index:
    """Les éléments d'une liste préparés pour chercher vite. Immuable : on en bâtit un autre quand la liste change."""

    entrees: tuple[EntreeIndex, ...]
    mots_de_categorie: frozenset[str] = frozenset()
    signature: tuple = ()
    # Mots qui ne se trouvent QUE dans des variantes (taille, format), jamais dans un nom : ils se lisent comme une option.
    mots_de_variantes: frozenset[str] = frozenset()


def _son(jetons: Sequence[str]) -> str:
    try:
        from api.services.communes.base import cle_phonetique

        return cle_phonetique(" ".join(jetons))
    except Exception:  # noqa: BLE001 -- la couche son manque, la recherche reste sûre : elle ne fait que proposer moins
        return ""


def _jetons(norme: str) -> tuple[str, ...]:
    return tuple(j for j in norme.split() if j not in PETITS_MOTS)


def preparer_forme(texte: str) -> Forme | None:
    jetons = _jetons(normaliser(texte))
    if not jetons:
        return None
    return Forme(texte=texte, jetons=jetons, joint=" ".join(jetons), ensemble=frozenset(jetons), son=_son(jetons))


def signature_des_elements(elements: Sequence[Element]) -> tuple:
    return tuple((e.id, e.libelle, e.synonymes, e.categorie, e.variantes) for e in elements)


def construire_index(elements: Sequence[Element], mots_de_categorie: Sequence[str] = ()) -> Index:
    entrees = []
    for e in elements:
        formes = tuple(f for f in (preparer_forme(t) for t in (e.libelle, *e.synonymes)) if f is not None)
        entrees.append(EntreeIndex(e, formes, frozenset(_jetons(normaliser(e.categorie))), frozenset(j for f in formes for j in f.jetons)))
    categories = frozenset(j for m in mots_de_categorie for j in _jetons(normaliser(m)))
    des_noms = {j for en in entrees for f in en.formes for j in f.jetons}
    des_variantes = {j for e in elements for v in e.variantes for j in _jetons(normaliser(v)) if j.isalpha() and len(j) >= 3}
    return Index(tuple(entrees), categories, signature_des_elements(elements), frozenset(des_variantes - des_noms - CONTENANTS))


# --------------------------------------------------------------------------- lecture de ce qui est dit


@dataclass(frozen=True)
class Demande:
    complete: tuple[str, ...]  # tout ce qui est dit, sans les petits mots
    coeur: tuple[str, ...]  # sans contenant, taille ni mot de catégorie
    options: dict = field(default_factory=dict)  # {"contenant": "canette", "taille": "33cl"}
    que_categorie: bool = False  # ce qui est dit ne nomme qu'un rangement (un mot de rangement), pas un élément

    def lectures(self, avec_son: bool) -> tuple[tuple[tuple[str, ...], str], ...]:
        """Les deux façons de lire ce qui est dit, avec leur son (calculé UNE fois par recherche)."""
        return tuple((j, _son(j) if avec_son else "") for j in dict.fromkeys((self.complete, self.coeur)))


def lire_la_demande(texte: str, mots_de_categorie: frozenset[str] = frozenset(), mots_de_variantes: frozenset[str] = frozenset()) -> Demande:
    norme = normaliser(texte or "")
    options: dict[str, str] = {}
    trouve = _TAILLE.search(norme)
    if trouve:
        options["taille"] = trouve.group(1).replace(" ", ".") + _UNITES[trouve.group(2)]
        norme = (norme[: trouve.start()] + " " + norme[trouve.end():]).strip()
    jetons = _jetons(norme)
    for j in jetons:
        if j in CONTENANTS and "contenant" not in options:
            options["contenant"] = j
    for j in jetons:
        if j in mots_de_variantes and "taille" not in options:
            options["taille"] = j  # « mega » : une variante dite, lue comme la taille
    taille_sup = {j for j in jetons if j in CONTENANTS or j in mots_de_variantes}
    sans_options = tuple(j for j in jetons if j not in taille_sup)
    sans_categorie = tuple(j for j in sans_options if j not in mots_de_categorie)
    # Les jetons de la taille retirée de la phrase ne comptent pas : « 33 cl » n'est pas un nom.
    complete = jetons + (tuple(re.findall(r"[a-z0-9]+", trouve.group(0))) if trouve else ())
    coeur = sans_categorie or sans_options or jetons
    que_categorie = bool(sans_options) and not sans_categorie
    return Demande(complete=complete, coeur=coeur, options=options, que_categorie=que_categorie)


# --------------------------------------------------------------------------- score d'une forme


def _score(jetons: tuple[str, ...], son_dit: str, forme: Forme) -> tuple[float, str]:
    if not jetons:
        return 0.0, "rien"
    joint = " ".join(jetons)
    if joint == forme.joint:
        return 1.0, "exact"
    dits = frozenset(jetons)
    if dits <= forme.ensemble:
        part = sum(len(j) for j in dits) / max(1, sum(len(j) for j in forme.ensemble))
        return 0.90 + 0.09 * part, "contenu"
    meilleur, nom = 0.0, "rien"
    if forme.ensemble <= dits and len(forme.joint) >= 4:
        meilleur, nom = 0.88, "contient"
    triee = fuzz.token_sort_ratio(joint, forme.joint) / 100.0
    lettres = triee * 0.97 if (triee >= 0.93 and min(len(joint), len(forme.joint)) >= 5) else triee * 0.9
    if lettres > meilleur:
        meilleur, nom = lettres, "lettres"
    if son_dit and forme.son:
        if son_dit == forme.son and len(son_dit) >= 3 and len(jetons) == len(forme.jetons):
            if 0.91 > meilleur:
                meilleur, nom = 0.91, "son"
        else:
            proche = fuzz.ratio(son_dit, forme.son) / 100.0 * 0.88
            if proche > meilleur:
                meilleur, nom = proche, "son"
    return meilleur, nom


def _meilleur(entree: EntreeIndex, lectures) -> tuple[float, str, frozenset[str], float]:
    """Le meilleur score, sa couche, les mots du nom qui l'a donné, et le score de la LECTURE COMPLÈTE seule (tout ce qui est dit)."""
    meilleur, nom, ensemble, complet = 0.0, "rien", frozenset(), 0.0
    for rang_de_lecture, (jetons, son_dit) in enumerate(lectures):
        for forme in entree.formes:
            s, n = _score(jetons, son_dit, forme)
            if rang_de_lecture == 0 and s > complet:
                complet = s
            if s > meilleur:
                meilleur, nom, ensemble = s, n, forme.ensemble
    return meilleur, nom, ensemble, complet


# --------------------------------------------------------------------------- la recherche


CoucheSens = Callable[[str, Sequence[Element]], Sequence[tuple[str, float]]]


def _candidat(e: Element, score: float, couche: str) -> dict:
    c = {"id": e.id, "libelle": e.libelle, "score": round(score, 3), "couche": couche}
    if e.categorie:
        c["categorie"] = e.categorie
    return c


def _variante(element: Element, options: dict) -> str | None:
    """La variante de l'élément (taille, contenant) qui porte ce qui a été dit, s'il y en a une seule."""
    voulus = {j for j in (options.get("contenant"), options.get("taille")) if j}
    if not voulus or not element.variantes:
        return None
    portent = []
    for v in element.variantes:
        collee = re.sub(r"(\d+)\s+(cl|ml|l|g|kg|cm)\b", r"\1\2", normaliser(v)).split()
        if all(x in collee for x in voulus):
            portent.append(v)
    return portent[0] if len(portent) == 1 else None


def _meme_rangement(a: Element, b: Element) -> bool:
    return not (a.categorie and b.categorie and a.categorie != b.categorie)


def question_de(candidats: Sequence[dict]) -> str:
    noms = [c["libelle"] + (f" ({c['categorie']})" if c.get("categorie") and sum(1 for x in candidats if x["libelle"] == c["libelle"]) > 1 else "") for c in candidats]
    if len(noms) == 1:
        return f"Vous voulez dire : {noms[0]} ?"
    return "Vous voulez dire : " + ", ".join(noms[:-1]) + f" ou {noms[-1]} ?"


def chercher_dans_l_index(
    index: Index, texte: str, reglages: Reglages = Reglages(), *, exclus: frozenset[str] = frozenset(), sens: CoucheSens | None = None
) -> dict:
    """``{statut, retenu, candidats, options, question, couche}``. ``exclus`` : éléments retirés (marqués indisponibles)."""
    demande = lire_la_demande(
        texte, index.mots_de_categorie | frozenset(j for m in reglages.mots_de_categorie for j in _jetons(normaliser(m))), index.mots_de_variantes
    )
    vide = {"statut": "INTROUVABLE", "retenu": None, "candidats": [], "options": demande.options, "question": None, "couche": None}
    if not demande.coeur:
        return vide
    notes: list[tuple[float, str, Element]] = []
    lectures = demande.lectures(reglages.couche_son)
    ensembles: dict[str, frozenset[str]] = {}
    complets: dict[str, float] = {}
    # Un mot de rangement DIT (« tarte ») qui n'est ni dans le rangement de l'élément ni dans son nom le disqualifie pour la rétention :
    # « une tarte aux pommes » ne retient pas le seul élément « pommes » d'un autre rangement.
    dits_de_rangement = frozenset(demande.complete) & (index.mots_de_categorie | frozenset(j for m in reglages.mots_de_categorie for j in _jetons(normaliser(m))))
    for entree in index.entrees:
        if entree.element.id in exclus:
            continue
        s, n, ensemble, complet = _meilleur(entree, lectures)
        if dits_de_rangement and entree.rangement and not dits_de_rangement <= (entree.rangement | entree.noms) and s > 0.85:
            s, n, complet = 0.85, "autre_rangement", min(complet, 0.85)
        ensembles[entree.element.id] = ensemble
        complets[entree.element.id] = complet
        notes.append((s, n, entree.element))
    if reglages.couche_sens and sens is not None:
        # Le sens PROPOSE seulement : jamais au-dessus du seuil de rétention, quoi qu'il dise.
        plafond = min(reglages.seuil_retenu - 0.01, 0.89)
        connus = {e.id: e for _, _, e in notes}
        for ident, score in sens(texte, [e for _, _, e in notes]):
            if ident in connus:
                notes.append((min(max(score, 0.0), plafond), "sens", connus[ident]))
    meilleurs: dict[str, tuple[float, str, Element]] = {}
    for s, n, e in notes:
        if e.id not in meilleurs or s > meilleurs[e.id][0]:
            meilleurs[e.id] = (s, n, e)
    rang = sorted(meilleurs.values(), key=lambda t: -t[0])
    if not rang:
        return vide
    premier = rang[0]
    parfaits = [t for t in rang if t[0] >= 1.0]
    if demande.que_categorie and not parfaits:
        # « un mot de rangement » : un rangement n'est pas un élément ; seul un élément qui porte exactement ce nom peut être retenu.
        # ``que_rangement`` dit à l'appelant qu'il faut demander LEQUEL (jamais en proposer trois au hasard).
        return {**vide, "que_rangement": True}
    retenu = None
    if len(parfaits) == 1:
        # Un seul nom exact l'emporte, SAUF si un autre élément d'un AUTRE rangement contient ce nom (« pesto » : l'un est une entrée, l'autre
        # des pâtes) : l'appelant a pu vouloir l'un ou l'autre, on pose la question.
        autres = [t for t in rang if t is not parfaits[0] and complets[t[2].id] >= reglages.seuil_retenu]
        if all(_meme_rangement(parfaits[0][2], t[2]) for t in autres):
            retenu = parfaits[0]
    elif len(parfaits) == 0 and premier[0] >= reglages.seuil_retenu and premier[1] != "sens":
        deuxieme = rang[1][0] if len(rang) > 1 else 0.0
        if premier[0] - deuxieme >= reglages.ecart_minimal and deuxieme < reglages.seuil_retenu:
            retenu = premier
        else:
            # Le NOM DE BASE : tous les éléments qui contiennent ce qui est dit sont des variantes d'un seul d'entre eux (leurs mots
            # contiennent TOUS ses mots) : « coca » retient « coca cola », pas « coca cola zero » ; « fanta » reste ambigu.
            hauts = [t for t in rang if t[0] >= reglages.seuil_retenu]
            if all(t[1] == "contenu" for t in hauts):
                bases = [t for t in hauts if all(ensembles[t[2].id] < ensembles[x[2].id] for x in hauts if x is not t)]
                if len(bases) == 1 and len(hauts) > 1 and all(_meme_rangement(bases[0][2], t[2]) for t in hauts):
                    retenu = (bases[0][0], "contenu_base", bases[0][2])
    if retenu is not None:
        e = retenu[2]
        options = dict(demande.options)
        variante = _variante(e, options)
        if variante:
            options["variante"] = variante
        return {"statut": "RETENU", "retenu": e.id, "candidats": [_candidat(e, retenu[0], retenu[1])], "options": options, "question": None, "couche": retenu[1]}
    proches = [(s, n, e) for s, n, e in rang if s >= reglages.seuil_ambigu][:NB_CANDIDATS]
    if proches:
        choix = [_candidat(e, s, n) for s, n, e in proches]
        return {"statut": "AMBIGU", "retenu": None, "candidats": choix, "options": demande.options, "question": question_de(choix), "couche": proches[0][1]}
    plus_proches = [_candidat(e, s, n) for s, n, e in rang if s >= PLANCHER_PROCHES][:NB_CANDIDATS]
    return {**vide, "candidats": plus_proches}


# --------------------------------------------------------------------------- le moteur par défaut (branché par ``poser_moteur``)

_CACHE: dict[tuple, Index] = {}
TAILLE_DU_CACHE = 8


def index_de(elements: Sequence[Element], mots_de_categorie: Sequence[str] = ()) -> Index:
    """Un index par liste distincte (petit cache : une recherche sans version connue ne reconstruit pas à chaque phrase)."""
    cle = (signature_des_elements(elements), tuple(mots_de_categorie))
    if cle not in _CACHE:
        if len(_CACHE) >= TAILLE_DU_CACHE:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[cle] = construire_index(elements, mots_de_categorie)
    return _CACHE[cle]


def moteur_par_defaut(elements: Sequence[Element], texte: str) -> dict:
    return chercher_dans_l_index(index_de(elements), texte)


def installer() -> None:
    """Remplace le moteur minimal de ``recherche_liste`` par celui-ci (même forme de retour)."""
    from api.db.bases_clients import recherche_liste

    recherche_liste.poser_moteur(moteur_par_defaut)


installer()
