"""[.mark] La mise sous même forme et la seule fonction « elle l'a dit » (chantier Partie 1, lot 3 ; D57 ; complément de Pierre, point 10).

Règle de VALEUR, jamais de sens. Portée de ``banc-b6/forme_b6.py`` (``forme``, ``heures``, ``dans_ses_mots``) et de ``banc-b13/valeurs_b13.py``
(``valeurs``), réunies sous UN nom, celui du glossaire : ``valeur_dite_par_elle(valeur, case, paroles, dit_par_le_code)``. Le nom
``dans_ses_mots`` n'existe pas dans le fork (doublon supprimé).

- une valeur libre (prénom, adresse, commune, consigne, heure) se retrouve dans ce qu'elle a dit, les deux textes sous la même forme : casse,
  accents, ponctuation, abréviations de voirie, nombres en lettres et en chiffres, heures (« sept heures » couvre « 19:00 ») ; ou dans ce que le
  code a dit dans l'appel (parade B6 au refus à tort « Martin ») ;
- un téléphone : ses chiffres, dictés un par un ou par paires, se retrouvent dans l'ordre ;
- un billet (``rendu_sur``) : la même valeur dite EN ARGENT (« un billet de cinquante » couvre 50 ; « deux reines » ne couvre jamais deux euros) ;
- un nombre (``CASE_D_UN_NOMBRE``, lot 6, barrière des chiffres de la parole) : la même valeur dite sous n'importe quel genre (« vers vingt heures »
  couvre « 20 heures »).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from api.services.actions_communes.petits_mots import ARTICLES

ABREV = {"st": "saint", "ste": "sainte", "av": "avenue", "bd": "boulevard", "bld": "boulevard", "pl": "place", "r": "rue", "che": "chemin", "imp": "impasse", "fbg": "faubourg"}
VIDES = ARTICLES | {"au", "aux", "a", "d", "et", "c", "est", "pour", "en"}
UNITES = {"zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11,
          "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16}
DIZAINES = {"vingt": 20, "vingts": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60}
MOYENS_DITS = {"titre", "titres", "espece", "especes", "carte", "cb", "cheque", "cheques", "cash", "liquide"}
ARGENT = {"euro", "euros", "€", "centime", "centimes"}
CASES_DE_TEXTE = ("prenom", "adresse", "commune", "consigne_livreur", "heure")
CASE_DU_TELEPHONE = "telephone"
CASE_DE_L_ARGENT = "rendu_sur"
CASES_DE_L_ARGENT = (CASE_DE_L_ARGENT, "part")  # C2 bis : la part d'un règlement partagé se dit en argent comme le billet
FIN_DE_PHRASE = "||"  # T17 : un point, « ! » ou « ? » sépare deux nombres comme ``SEPARATEUR`` mais n'est jamais la virgule des centimes (``lecture_a_virgule_decimale``)
SEPARATEUR = "|"  # C6 : la ponctuation qui sépare deux nombres dans les mots d'une valeur (``_mots_de_valeur``)
CASE_D_UN_NOMBRE = "nombre"  # lot 6 : une valeur de la phrase du modèle qui n'est pas de l'argent (heure, nombre de personnes)


def norm(texte: object) -> str:
    s = unicodedata.normalize("NFD", str(texte or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[-_'’,.!?]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _nombres(mots: list[str]) -> list[str]:
    """Les nombres dits en lettres deviennent des chiffres : « vingt et un » = 21, « soixante-dix-huit » = 78, « quatre-vingt-douze » = 92."""
    out, i = [], 0
    while i < len(mots):
        m = mots[i]
        if m == "quatre" and i + 1 < len(mots) and mots[i + 1] in ("vingt", "vingts"):
            v, j = 80, i + 2
            if j < len(mots) and mots[j] in UNITES and UNITES[mots[j]] <= 16:
                v += UNITES[mots[j]]
                j += 1
                if mots[j - 1] == "dix" and j < len(mots) and mots[j] in ("sept", "huit", "neuf"):
                    v += UNITES[mots[j]]
                    j += 1
            out.append(str(v))
            i = j
            continue
        if m == "dix" and i + 1 < len(mots) and mots[i + 1] in ("sept", "huit", "neuf"):
            out.append(str(10 + UNITES[mots[i + 1]]))
            i += 2
            continue
        if m in DIZAINES:
            v, j = DIZAINES[m], i + 1
            if j < len(mots) and mots[j] == "et" and j + 1 < len(mots) and mots[j + 1] in ("un", "une", "onze"):
                v += UNITES[mots[j + 1]]
                j += 2
            elif m == "soixante" and j < len(mots) and mots[j] in UNITES and 10 <= UNITES[mots[j]] <= 16:
                v += UNITES[mots[j]]
                j += 1
                if mots[j - 1] == "dix" and j < len(mots) and mots[j] in ("sept", "huit", "neuf"):
                    v += UNITES[mots[j]]
                    j += 1
            elif j < len(mots) and mots[j] in UNITES and UNITES[mots[j]] < 10:
                v += UNITES[mots[j]]
                j += 1
            out.append(str(v))
            i = j
            continue
        out.append(str(UNITES[m]) if m in UNITES else m)
        i += 1
    return out


def forme(texte: object) -> list[str]:
    """Les mots d'un texte sous la même forme (forme_b6.forme)."""
    t = norm(texte)
    t = re.sub(r"(\d{1,2})\s*[:h]\s*(\d{2})", r"\1 h \2", t)
    t = re.sub(r"(\d{1,2})\s*h\b", r"\1 h", t)
    mots = [ABREV.get(m, m) for m in t.split()]
    mots = [("h" if m in ("heure", "heures") else m) for m in _nombres(mots)]
    return [m for m in mots if m not in VIDES]


def heures(mots: list[str]) -> set[tuple[int, int]]:
    out: set[tuple[int, int]] = set()
    for i, m in enumerate(mots):
        if m.isdigit() and i + 1 < len(mots) and mots[i + 1] == "h":
            h = int(m)
            mn = int(mots[i + 2]) if i + 2 < len(mots) and mots[i + 2].isdigit() else 0
            out |= {(h, mn), ((h + 12) % 24, mn), ((h - 12) % 24, mn)}
    return out


def _mots_de_valeur(texte: object, fins_de_phrase: bool = False) -> list[str]:
    # Pierre 12 (C2) : le signe « € » est gardé AVANT la mise sous forme ASCII, qui le supprimait (« 25 € » se lisait « 25 » sans unité d'argent, refusé)
    s = unicodedata.normalize("NFD", str(texte or "").replace("€", " euros ")).encode("ascii", "ignore").decode().lower().replace("€", " € ")
    # T17 : ce seul ``re.sub`` couvre aussi le cas général (un chiffre, la virgule, un chiffre : « 24,05 ») ; « 24,5 € » est 24,50 € (un seul chiffre après la virgule, devant une unité d'argent : les dixièmes), pas 24,05 ; hors argent la lecture ne change pas (« 1,5 kg »)
    s = re.sub(r"(\d)[,.](\d)((?!\d)(?=\s*(?:euros?|centimes?)\b))?", lambda m: f"{m[1]} virgule {m[2]}" + ("" if m[3] is None else "0"), s)
    # C6 : une ponctuation entre deux nombres les sépare (« pour quatre, vingt heures » : 4 puis 20, jamais 80) ; elle reste un mot (``SEPARATEUR``), qui n'est pas un nombre
    return re.sub(r"[^a-z0-9€| ]", " ", s.translate(_PONCTUATION_EN_SEPARATEUR_ET_FINS if fins_de_phrase else _PONCTUATION_EN_SEPARATEUR)).split()


_PONCTUATION_EN_SEPARATEUR = str.maketrans({c: f" {SEPARATEUR} " for c in ",;.!?"})  # chaque signe devient le mot ``SEPARATEUR`` (``_mots_de_valeur``)
_PONCTUATION_EN_SEPARATEUR_ET_FINS = str.maketrans({**{c: f" {SEPARATEUR} " for c in ",;"}, **{c: f" {FIN_DE_PHRASE} " for c in ".!?"}})  # idem, mais « . ! ? » deviennent ``FIN_DE_PHRASE``


def _est_nombre(w: str) -> bool:
    return w.isdigit() or w in UNITES or w in DIZAINES or w in ("cent", "cents", "mille", "virgule")


def _valeur(mots: list[str]) -> str:
    if all(w.isdigit() for w in mots):
        return "".join(mots) if len(mots) > 1 else str(int(mots[0]))
    total, courant = 0, 0
    for i, w in enumerate(mots):
        if i and w in ("vingt", "vingts") and mots[i - 1] == "quatre":
            courant += 76  # « quatre vingts » : le 4 déjà compté et les 20 de « vingts » font 80 (sinon 24)
        elif w.isdigit():
            courant += int(w)
        elif w in UNITES:
            courant += UNITES[w]
        elif w in DIZAINES:
            courant += DIZAINES[w]
        elif w in ("cent", "cents"):
            courant = (courant or 1) * 100
        elif w == "mille":
            total += (courant or 1) * 1000
            courant = 0
        elif w == "virgule":
            total, courant = (total + courant) * 100, 0
    return str(total + courant)


def lire_un_nombre(mots: list[str]) -> int | None:
    """C5 : le nombre entier que ces mots disent (« mille deux cents », « quatre vingt dix », chiffres compris) ; ``None`` s'il y a autre chose qu'un nombre. La seule norme de lecture des
    nombres dits (méthode § 12.2) : la même que celle de « elle l'a dit » et de la garde des chiffres."""
    if not mots or not all(w.isdigit() or (_est_nombre(w) and w != "virgule") for w in mots):
        return None
    return int(_valeur(list(mots)))


def _avec_les_centimes(mots: list[str]) -> list[str]:
    """T17 : un nombre dit juste après l'unité d'argent est les centimes (« vingt-quatre euros cinquante » = 24,50 € = « 24 virgule 50 »), jamais une somme de plus aux euros
    (avant : 74). Le mot ``virgule`` s'insère entre les euros et les centimes ; l'unité, « et » et une virgule déjà dite ne changent rien."""
    out, vu_l_unite, virgule = [], False, "virgule" in mots
    for x in mots:
        if x in ARGENT:
            vu_l_unite = bool(out)
        elif x != "et":
            if vu_l_unite and not virgule:
                out.append("virgule")
                virgule = True
            out.append(x)
    return out


def lecture_a_virgule_decimale(texte: object) -> str | None:
    """T17 (reprise R1) : la lecture où chaque virgule qui sépare deux nombres, le second suivi d'une unité d'argent, est la virgule des centimes (« vingt-quatre, cinquante euros » = 24,50 €,
    jamais 74 ; « vingt, cinquante-quatre euros » = 20,54 €, donc pas 24,50 €). Le texte en mots, ``virgule`` à la place de chaque ponctuation retenue, les autres ponctuations restent
    ``SEPARATEUR`` (un point ne colle pas deux nombres, et n'est jamais la virgule des centimes : seules « , » et « ; » le sont) ; ``None`` s'il n'y a pas de tel cas."""
    w = _mots_de_valeur(texte, fins_de_phrase=True)
    centimes = set()
    for s in range(1, len(w) - 1):
        if w[s] != SEPARATEUR or not _est_nombre(w[s - 1]) or w[s - 1] == "virgule":
            continue
        e = s + 1
        while e < len(w) and _est_nombre(w[e]) and w[e] != "virgule":
            e += 1
        if e > s + 1 and e < len(w) and w[e] in ARGENT:
            centimes.add(s)
    return " ".join("virgule" if i in centimes else (SEPARATEUR if m == FIN_DE_PHRASE else m) for i, m in enumerate(w)) if centimes else None


def valeurs_et_places(texte: object) -> tuple[list[tuple[int, int, str, str]], list[str]]:
    """Les valeurs d'un texte avec leur place (``valeurs_b12.valeurs``) : ``([(début, fin, valeur, genre)], mots)``, ``fin`` comprenant l'unité
    d'argent qui suit ; genre « argent » (suivie d'une unité d'argent, ou après « billet de ») ou « nombre »."""
    w = _mots_de_valeur(texte)
    out, i = [], 0
    while i < len(w):
        if _est_nombre(w[i]) and w[i] != "virgule":
            j = i
            while j + 1 < len(w) and (_est_nombre(w[j + 1]) or (w[j + 1] == "et" and j + 2 < len(w) and _est_nombre(w[j + 2]))):
                j += 1
            k, argent = j, False
            while k + 1 < len(w) and w[k + 1] in ARGENT:
                argent = True
                k += 1
                if k + 1 < len(w) and _est_nombre(w[k + 1]):
                    k += 1
                    while k + 1 < len(w) and _est_nombre(w[k + 1]):
                        k += 1
            if not argent and k + 2 < len(w) and w[k + 1] == "en" and w[k + 2] in MOYENS_DITS:
                argent = True  # Pierre 12 (C2) : « 25 en titres », « 50 en espèces » : un montant en argent, sans le mot « euros »
            if i >= 2 and w[i - 2] == "billet" and w[i - 1] == "de":
                argent = True
            num = _avec_les_centimes(w[i:k + 1])
            if num and not (len(num) == 1 and num[0] in ("un", "une") and not argent):
                out.append((i, k, _valeur(num), "argent" if argent else "nombre"))
            i = k + 1
        else:
            i += 1
    return out, w


def valeurs(texte: object) -> list[tuple[str, str]]:
    """Les valeurs d'un texte (valeurs_b13.valeurs) : [(valeur, genre)], genre « argent » (suivie d'une unité d'argent, ou après « billet de »)
    ou « nombre »."""
    return [(v, g) for _, _, v, g in valeurs_et_places(texte)[0]]


def _chiffres_dits(textes: Iterable[str]) -> str:
    """Les chiffres dits, dans l'ordre (un téléphone dicté un par un ou par paires : « zéro six, douze, trente-quatre »)."""
    flux = []
    for t in textes:
        for m in _nombres(norm(t).split()):
            if m.isdigit():
                flux.append(m)
    return "".join(flux)


def _texte_dit(valeur: str, textes: list[str]) -> bool:
    dit = forme(" ".join(textes))
    v = forme(valeur)
    hv = heures(v)
    if hv:
        if not (hv & heures(dit)):
            return False
        v = [m for m in v if not (m.isdigit() or m == "h")]
    ensemble = set(dit)
    return all(m in ensemble for m in v)


def valeur_dite_par_elle(valeur: object, case: str, paroles: Iterable[str], dit_par_le_code: Iterable[str] = ()) -> bool:
    """Vrai si la valeur de cette case se retrouve dans ce qu'elle a dit dans l'appel (ou, pour un texte, dans ce que le code a dit)."""
    paroles = [str(p) for p in paroles or () if p]
    if valeur is None or (isinstance(valeur, str) and not valeur.strip()):
        return True
    if case == CASE_DU_TELEPHONE:
        chiffres = re.sub(r"\D", "", str(valeur))
        if len(chiffres) < 4:
            return False
        dits = _chiffres_dits(paroles)
        return chiffres[-9:] in dits
    if case in CASES_DE_L_ARGENT:
        try:
            v = str(round(float(valeur)))
        except (TypeError, ValueError):
            return False
        return any((v, "argent") in valeurs(p) for p in paroles)
    if case == CASE_D_UN_NOMBRE:
        return any(str(valeur) == v for p in paroles for v, _ in valeurs(p))
    textes = paroles + [str(t) for t in dit_par_le_code or () if t]
    return _texte_dit(str(valeur), textes)
