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
from api.db.bases_clients.recherche_liste_numero import cle_ecrite, cles_dites

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
    # Clé de numéro (``recherche_liste_numero``) -> les éléments qui la portent. Vide : la liste n'est pas numérotée, la couche n'existe pas.
    par_numero: dict = field(default_factory=dict)


def _son(jetons: Sequence[str]) -> str:
    try:
        from api.services.communes.base import cle_phonetique

        return cle_phonetique(" ".join(jetons))
    except Exception:  # noqa: BLE001 -- la couche son manque, la recherche reste sûre : elle ne fait que proposer moins
        return ""


def _jetons(norme: str) -> tuple[str, ...]:
    return tuple(j for j in norme.split() if j not in PETITS_MOTS)


MOTS_QUI_ANNONCENT_UNE_TAILLE = frozenset({"taille", "format"})

# SA-52 (appel 2604) : « X deux couleurs » contre « X 2 couleurs ». Les nombres se lisent en chiffres DES DEUX CÔTÉS (le nom et ce
# qui est dit), avant le nettoyage (qui couperait le « x » de « deux »). « un », « une » ne valent 1 qu'au milieu d'un nom (après un mot qui
# n'est pas un petit mot de liaison : « X une couleur », « modèle h un ») ; en tête ou après « et », « avec »… ils restent des articles.
_AVANT_UN_ARTICLE = PETITS_MOTS | frozenset({"sans", "ou", "dont", "plus", "puis", "mai"})
_COLLE = re.compile(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])")


def nombres_en_chiffres(texte: str) -> str:
    """Le texte avec ses nombres dits en lettres écrits en chiffres (« deux » -> 2, « cent quatre-vingt » -> 180). ⛔ Ne lève jamais."""
    mots = (texte or "").split()
    for i in range(1, len(mots)):
        avant = normaliser(mots[i - 1])
        if mots[i].casefold() in ("un", "une") and avant and avant not in _AVANT_UN_ARTICLE and not mots[i - 1].endswith((",", ";", ":")):
            mots[i] = "1"
    texte = " ".join(mots)
    try:
        from text_to_num import alpha2digit

        return alpha2digit(texte, "fr", threshold=2)
    except Exception:  # noqa: BLE001 -- sans la bibliothèque : le texte tel quel, la recherche reste sûre
        return texte


# Point de contrôle du lot 7 (pc7k-f307b) : l'agent DIT les unités en lettres (``moteur._UNITES_EN_MOTS`` : « 33 centilitres ») et le modèle recopie ce qu'il
# entend ; la liste les écrit en abrégé (« 33 cl »). Après un nombre, l'unité en lettres prend sa forme courte, des deux côtés de la recherche.
_UNITE_EN_LETTRES = re.compile(r"(?<=\d) (centilitres?|millilitres?|litres?|kilogrammes?|kilos?|grammes?)(?![a-z0-9])")
_UNITE_COURTE = {"centilitre": "cl", "millilitre": "ml", "litre": "l", "kilogramme": "kg", "kilo": "kg", "gramme": "g"}


def norme_de_recherche(texte: str) -> str:
    """Le texte nettoyé (``normaliser``) avec ses nombres en chiffres, détachés des lettres (« R54 » = « r 54 », « 7Up » = « 7 up »), et l'unité dite en
    lettres après un nombre sous sa forme courte (« 33 centilitres » = « 33 cl », « 1,5 litre » = « 1,5 l »)."""
    norme = _COLLE.sub(" ", normaliser(nombres_en_chiffres(texte)))
    return _UNITE_EN_LETTRES.sub(lambda m: " " + _UNITE_COURTE[m.group(1).rstrip("s")], norme)


def preparer_forme(texte: str) -> Forme | None:
    jetons = _jetons(norme_de_recherche(texte))
    if not jetons:
        return None
    return Forme(texte=texte, jetons=jetons, joint=" ".join(jetons), ensemble=frozenset(jetons), son=_son(jetons))


def signature_des_elements(elements: Sequence[Element]) -> tuple:
    return tuple((e.id, e.libelle, e.synonymes, e.categorie, e.variantes, e.numero) for e in elements)


def construire_index(elements: Sequence[Element], mots_de_categorie: Sequence[str] = ()) -> Index:
    entrees = []
    for e in elements:
        formes = tuple(f for f in (preparer_forme(t) for t in (e.libelle, *e.synonymes)) if f is not None)
        entrees.append(EntreeIndex(e, formes, frozenset(_jetons(normaliser(e.categorie))), frozenset(j for f in formes for j in f.jetons)))
    categories = frozenset(j for m in mots_de_categorie for j in _jetons(normaliser(m)))
    des_noms = {j for en in entrees for f in en.formes for j in f.jetons}
    des_variantes = {j for e in elements for v in e.variantes for j in _jetons(normaliser(v)) if j.isalpha() and len(j) >= 3}
    par_numero: dict[str, list[Element]] = {}
    for e in elements:
        cle = cle_ecrite(e.numero)
        if cle:
            par_numero.setdefault(cle, []).append(e)
    return Index(
        tuple(entrees), categories, signature_des_elements(elements), frozenset(des_variantes - des_noms - CONTENANTS),
        {k: tuple(v) for k, v in par_numero.items()},
    )


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
    norme = norme_de_recherche(texte or "")
    options: dict[str, str] = {}
    trouve = _TAILLE.search(norme)
    if trouve:
        options["taille"] = trouve.group(1).replace(" ", ".") + _UNITES[trouve.group(2)]
        norme = (norme[: trouve.start()] + " " + norme[trouve.end():]).strip()
    jetons = _jetons(norme)
    if options or any(j in mots_de_variantes for j in jetons):
        # SA-18 : « Regina taille normale » : le mot « taille » qui annonce la variante n'est pas un mot du nom (il rendait « Regina » ambigu avec elle-même).
        jetons = tuple(j for j in jetons if j not in MOTS_QUI_ANNONCENT_UNE_TAILLE)
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
# La couche sens est FOURNIE de l'extérieur (un modèle : ce module n'appelle aucun tiers) ; tant qu'aucune n'est posée, rien ne se passe.
_COUCHE_SENS: CoucheSens | None = None


def poser_couche_sens(fonction: CoucheSens | None) -> None:
    global _COUCHE_SENS
    _COUCHE_SENS = fonction


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


def _par_numero(index: Index, texte: str, options: dict, exclus: frozenset[str]) -> dict | None:
    """La couche « numéro » (C2), AVANT les autres : une phrase qui n'est qu'un numéro (« le 46 », « j vingt-quatre ») se retrouve par
    correspondance EXACTE de sa clé. Un seul élément : RETENU ; plusieurs (le même numéro écrit deux fois) : AMBIGU ;
    aucun : INTROUVABLE, jamais l'élément le plus ressemblant. ``None`` : ce n'est pas un numéro, la recherche par le nom suit."""
    cles = cles_dites(texte)
    if not cles:
        return None
    # Les lectures sont rangées de la plus littérale (« n 12 » = N12) à la plus lâche (« n » dit pour « numéro ») : la première qui désigne
    # un élément de la liste l'emporte ; une lecture ne se mélange jamais à une autre.
    portes: list[Element] = []
    for cle in cles:
        portes = [e for e in index.par_numero.get(cle, ()) if e.id not in exclus]
        if portes:
            break
    base = {"retenu": None, "candidats": [], "options": options, "question": None, "couche": "numero"}
    if not portes:
        return {**base, "statut": "INTROUVABLE", "raison": "numero_inconnu"}
    candidats = [_candidat(e, 1.0, "numero") for e in portes[:NB_CANDIDATS]]
    if len(portes) == 1:
        return {**base, "statut": "RETENU", "retenu": portes[0].id, "candidats": candidats}
    return {**base, "statut": "AMBIGU", "candidats": candidats, "question": question_de(candidats)}


def chercher_dans_l_index(
    index: Index, texte: str, reglages: Reglages = Reglages(), *, exclus: frozenset[str] = frozenset(), sens: CoucheSens | None = None
) -> dict:
    """``{statut, retenu, candidats, options, question, couche}``. ``exclus`` : éléments retirés (marqués indisponibles)."""
    sens = sens if sens is not None else _COUCHE_SENS
    demande = lire_la_demande(
        texte, index.mots_de_categorie | frozenset(j for m in reglages.mots_de_categorie for j in _jetons(normaliser(m))), index.mots_de_variantes
    )
    vide = {"statut": "INTROUVABLE", "retenu": None, "candidats": [], "options": demande.options, "question": None, "couche": None}
    if index.par_numero:
        dit_un_numero = _par_numero(index, texte, demande.options, exclus)
        if dit_un_numero is not None:
            return dit_un_numero
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


# --------------------------------------------------------------------------- noms ambigus et synonymes proposés (calculés, jamais tapés)


def nom_nettoye(libelle: str) -> str:
    """Un nom tel que le moteur le compare (casse, accents, pluriel, petits mots)."""
    return " ".join(_jetons(normaliser(libelle)))


def noms_ambigus(elements: Sequence[Element]) -> dict[str, list[dict]]:
    """Les noms portés par PLUSIEURS éléments (après nettoyage), calculés depuis la liste : ``{nom: [{id, libelle, categorie}]}``.
    Le moteur ne retient jamais l'un d'eux au hasard ; la liste dit lesquels, pour l'écran et pour la relecture."""
    groupes: dict[str, list[dict]] = {}
    for e in elements:
        nom = nom_nettoye(e.libelle)
        if nom:
            groupes.setdefault(nom, []).append({"id": e.id, "libelle": e.libelle, "categorie": e.categorie})
    return {nom: porteurs for nom, porteurs in groupes.items() if len(porteurs) > 1}


_PARENTHESES = re.compile(r"\s*[\(\[][^)\]]*[\)\]]")


def proposer_synonymes(libelle: str, mots_de_categorie: Sequence[str] = (), autres_noms: frozenset[str] = frozenset()) -> list[str]:
    """Des synonymes PROPOSÉS pour un nom, tirés du nom lui-même : sans ce qui est entre parenthèses, la première partie d'un nom
    composé par un trait d'union, sans le mot de rangement qui le précède. Jamais un synonyme déjà porté par un autre élément
    (``autres_noms``, noms nettoyés) ni le nom lui-même. Marqués « à relire » par l'appelant : actifs seulement après relecture (T-14)."""
    propres = frozenset(j for m in mots_de_categorie for j in _jetons(normaliser(m)))
    base_nom = nom_nettoye(libelle)
    candidats: list[str] = []
    sans_parentheses = _PARENTHESES.sub("", libelle).strip()
    if sans_parentheses and sans_parentheses != libelle:
        candidats.append(sans_parentheses)
    if "-" in sans_parentheses:
        premier = sans_parentheses.split("-", 1)[0].strip()
        if len(premier) >= 4 and premier.lower() not in CONTENANTS:
            candidats.append(premier)
    jetons = sans_parentheses.split()
    if len(jetons) >= 2 and normaliser(jetons[0]) in propres:
        candidats.append(" ".join(jetons[1:]))
    sorties: list[str] = []
    vus = {base_nom}
    for c in candidats:
        nom = nom_nettoye(c)
        if nom and nom not in vus and nom not in autres_noms:
            vus.add(nom)
            sorties.append(c)
    return sorties
