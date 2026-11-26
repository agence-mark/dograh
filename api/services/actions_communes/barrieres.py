"""[.mark] Les barrières nommées de la fiche (chantier Partie 1, lot 3 ; B8 § 2 points 1 et 3, B9 § 2 point 3 bis, B10, B12 décision 1).

Chaque barrière est une fonction qui rend un REFUS (``{"raison", "cases", ...}``) ou ``None``. Deux familles :

- celles qui refusent **la fiche entière** (rien n'est exécuté, sa phrase n'est jamais dite) : ``fiche_illisible``, ``case_sans_objet`` (contre la
  liste des cases MONTRÉES gardée dans le tour, D52, jamais un recalcul), ``format`` (``"true"`` en chaîne, ``quantite: "2"``),
  ``reponse_manquante`` (une question déjà posée attend et la fiche n'a pas ``reponse``) ; la réponse à une question inconnue est refusée par le
  registre des questions (``registre_des_questions.question_inconnue``), qui porte les identifiants ;
- celles qui refusent **une case** (le filet des cases liées écarte son bloc, le reste s'exécute) : ``valeur_hors_liste`` (comparée sous la même
  forme : « 33 cl », « 2 viandes »), ``valeur_pas_dans_ses_mots`` (D57, ``forme.valeur_dite_par_elle``), ``recapitulatif_pas_accepte``.

Tout refus dit quoi refaire (``a_faire``) : « rien n'est changé : refais la fiche sans … » (B9 point 3 bis). Aucun mot de métier.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from api.services.actions_communes.consignes import en_une_phrase
from api.services.actions_communes.forme import (
    CASES_DE_L_ARGENT,
    CASES_DE_TEXTE,
    CASES_DU_TELEPHONE,
    valeur_dite_par_elle,
)
from api.services.workflow.cases_selon_l_etat import chemins_du_schema

CASES_LIBRES = (*CASES_DE_TEXTE, *CASES_DU_TELEPHONE, *CASES_DE_L_ARGENT)
TYPES_JSON = {"string": (str,), "integer": (int,), "number": (int, float), "boolean": (bool,), "array": (list,), "object": (dict,)}


RIEN_N_EST_CHANGE = "rien n'est changé : "
RIEN_N_EST_CHANGE_POUR = "rien n'est changé pour "


class Refus(dict):
    """Un refus tel que le modèle le lit (``raison``, ``cases``, ``a_faire``…), et, à côté, le ``reste`` de sa consigne : ce qui suit « rien n'est changé ». Le reste n'est pas
    une clé : le modèle ne reçoit rien de plus. ``None`` : la consigne a été écrite entière, le refus partiel la reprend telle quelle."""

    reste: str | None = None


def a_faire_sans(cases: Iterable[str]) -> str:
    return RIEN_N_EST_CHANGE + reste_sans(cases)


def reste_sans(cases: Iterable[str]) -> str:
    return "refais la fiche sans " + ", ".join(sorted(set(cases)))


def a_faire_du_refus_partiel(premier: dict[str, Any], executees: Iterable[str]) -> str:
    """C6 (lot 19 bis) : quand une case est refusée mais que d'AUTRES cases de la même fiche ont été exécutées, le retour dit ce qui est fait (« rien n'est changé » serait faux).
    Il ne demande plus au modèle de ne pas refaire la fiche : une case déjà faite dans le tour n'est jamais refaite (``idempotence.case_deja_faite``, B4). Un refus de la fiche
    entière (rien exécuté) garde son texte."""
    faites = sorted(set(executees) - set(premier.get("cases") or []))
    if not faites or "*" in (premier.get("cases") or []):
        return premier["a_faire"]
    reste = getattr(premier, "reste", None) or str(premier["a_faire"])
    refusees = ", ".join(premier.get("cases") or [])
    return f"{refusees} refusé : {reste} ; le reste de la fiche est déjà fait ({', '.join(faites)})"


def a_faire_des_refus(refus_: list[dict[str, Any]], executees: Iterable[str]) -> str | None:
    """Clôture, lot B4 (M9, « refus multiples ») : la consigne de CHAQUE refus de la fiche, pas seulement du premier (avant : les autres perdues)."""
    if not refus_:
        return None
    suite = [str(r["a_faire"]) for r in refus_[1:] if r.get("a_faire")]
    return en_une_phrase([a_faire_du_refus_partiel(refus_[0], executees), *suite])


def ecarter_les_cases_sans_objet(fiche: dict[str, Any], cases_montrees: Iterable[str]) -> tuple[dict[str, Any], dict | None, dict | None]:
    """Clôture, lot B4 (M9 : même faute, même traitement, commande et réservation) : une case que ce tour ne montre pas n'écarte qu'elle, comme une
    réponse sans question ; seule (ou une sous-case), la fiche entière est refusée. Rend (la fiche sans elles, le refus de la case, le refus entier)."""
    sans_objet = case_sans_objet(fiche, cases_montrees)
    if sans_objet is None:
        return fiche, None, None
    cases = sans_objet["cases"]
    if all("[" not in c and "." not in c for c in cases) and set(fiche) - set(cases) - {"a_dire"}:
        ecartee = refus("case_sans_objet", cases, a_faire="pas ouvert maintenant, rien n'en est pris ; le reste de la fiche est fait")
        return {k: v for k, v in fiche.items() if k not in cases}, ecartee, None
    return fiche, None, sans_objet


def refus(raison: str, cases: Iterable[str], *, reste: str | None = None, pour: bool = False, **plus: Any) -> Refus:
    """Un refus. La consigne se dit par son ``reste`` (« rien n'est changé : » est ajouté, ou « rien n'est changé pour » avec ``pour``), par une ``a_faire`` entière, ou par défaut « refais la fiche sans … »."""
    cases = sorted(set(cases))
    entiere = plus.pop("a_faire", None)
    if entiere:
        reste = None
    elif reste is None:
        reste = reste_sans(cases)
    r = Refus({"raison": raison, "cases": cases, "a_faire": entiere or (RIEN_N_EST_CHANGE_POUR if pour else RIEN_N_EST_CHANGE) + reste, **plus})
    r.reste = reste
    return r


def _chemins_de_la_fiche(fiche: dict[str, Any], prefixe: str = "") -> list[str]:
    sortie = []
    for k, v in fiche.items():
        chemin = f"{prefixe}{k}"
        sortie.append(chemin)
        if isinstance(v, dict):
            sortie += _chemins_de_la_fiche(v, chemin + ".")
        elif isinstance(v, list):
            for x in v:
                if isinstance(x, dict):
                    sortie += _chemins_de_la_fiche(x, chemin + "[].")
    return sortie


# --------------------------------------------------------------------------- la fiche entière


MARQUE_ARGUMENTS_ILLISIBLES = "arguments_illisibles"  # P5 : posée par le filet du cerveau (``ArgumentsLisibles``) sur l'appel d'une fiche dont le JSON ne se lisait pas


def fiche_illisible(fiche: Any) -> dict | None:
    if not isinstance(fiche, dict):
        return refus("format_illisible", ["*"], reste="la fiche est un objet avec ses cases")
    if fiche.get(MARQUE_ARGUMENTS_ILLISIBLES) is True:
        return refus("arguments_illisibles", ["*"], reste="ta fiche n'a pas pu être lue, refais-la en entier")
    return None


def case_sans_objet(fiche: dict[str, Any], cases_montrees: Iterable[str]) -> dict | None:
    """Une case (ou sous-case) absente de la liste des cases MONTRÉES au modèle dans ce tour (D52) : la fiche entière est refusée."""
    montrees = set(cases_montrees)
    hors = [c for c in _chemins_de_la_fiche(fiche) if c not in montrees]
    return refus("case_sans_objet", hors) if hors else None


def _type_juste(valeur: Any, attendu: str) -> bool:
    if attendu in ("integer", "number") and isinstance(valeur, bool):
        return False
    if attendu == "integer" and isinstance(valeur, float) and valeur.is_integer():
        return True
    return isinstance(valeur, TYPES_JSON.get(attendu, (object,)))


def _fautes_de_type(valeurs: dict[str, Any], proprietes: dict[str, Any], prefixe: str = "") -> list[str]:
    fautes = []
    for k, v in valeurs.items():
        s = proprietes.get(k)
        if not isinstance(s, dict) or v is None:
            continue
        chemin = f"{prefixe}{k}"
        if not _type_juste(v, s.get("type", "string")):
            fautes.append(chemin)
        elif isinstance(v, dict) and isinstance(s.get("properties"), dict):
            fautes += _fautes_de_type(v, s["properties"], chemin + ".")
        elif isinstance(v, list) and isinstance(s.get("items"), dict):
            elements = s["items"]
            for x in v:
                if not _type_juste(x, elements.get("type", "string")):
                    fautes.append(chemin + "[]")
                elif isinstance(x, dict) and isinstance(elements.get("properties"), dict):
                    fautes += _fautes_de_type(x, elements["properties"], chemin + "[].")
    return fautes


FORMES_ATTENDUES = {"boolean": "en true ou false, sans guillemets", "integer": "en nombre, sans guillemets", "number": "en nombre, sans guillemets",
                    "string": "en texte", "array": "en liste", "object": "en objet"}


def _type_du_chemin(chemin: str, proprietes: dict[str, Any]) -> str | None:
    """Le type déclaré d'une case nommée par son chemin (« ajouter[].quantite »)."""
    schema: Any = {"properties": proprietes}
    for morceau in chemin.split("."):
        nom, liste = (morceau[:-2], True) if morceau.endswith("[]") else (morceau, False)
        schema = ((schema or {}).get("properties") or {}).get(nom) if isinstance(schema, dict) else None
        if liste and isinstance(schema, dict):
            schema = schema.get("items")
    return schema.get("type") if isinstance(schema, dict) else None


def _manques_obligatoires(valeurs: dict[str, Any], proprietes: dict[str, Any], prefixe: str = "") -> list[str]:
    """Les cases que le contrat déclare obligatoires (``required``) dans un objet ou dans les éléments d'une liste, et que la fiche ne porte pas : leur chemin (« ajouter[].article »)."""
    manques: list[str] = []
    for k, v in valeurs.items():
        s = proprietes.get(k)
        if not isinstance(s, dict) or v is None:
            continue
        chemin = f"{prefixe}{k}"
        cadres = [(chemin + ".", v, s)] if isinstance(v, dict) else [(chemin + "[].", x, s.get("items") or {}) for x in v if isinstance(x, dict)] if isinstance(v, list) else []
        for debut, objet, schema in cadres:
            sous = schema.get("properties") if isinstance(schema, dict) else None
            if not isinstance(sous, dict):
                continue
            manques += [debut + n for n in schema.get("required") or [] if objet.get(n) in (None, "")]
            manques += _manques_obligatoires(objet, sous, debut)
    return manques


def format(fiche: dict[str, Any], proprietes: dict[str, Any], cases_montrees: Iterable[str] | None = None) -> dict | None:
    """Une valeur au mauvais type (``"true"`` en chaîne, ``quantite: "2"``) : la fiche entière est refusée (B8 point 3, F2a à F2c). Lot 19, D30 (décision
    d'Evan du 20/11) : la consigne dit le TYPE attendu de chaque case (« écris c_est_tout en true ou false, sans guillemets ») ; « refais la fiche sans
    c_est_tout » invitait le modèle à retirer la case. Une case obligatoire du contrat absente (et montrée par ce tour) est refusée de même, avec son type."""
    fautes = sorted(set(_fautes_de_type(fiche, proprietes)))
    manques = sorted(c for c in set(_manques_obligatoires(fiche, proprietes)) if cases_montrees is None or c in set(cases_montrees))  # une case que ce tour ne montre pas n'est pas exigée
    if manques:
        dites = [f"{c} est obligatoire, écris-la {FORMES_ATTENDUES.get(_type_du_chemin(c, proprietes) or '', 'au type de sa case')}" for c in manques]
        # la réponse à la question en attente n'est rappelée que si ce tour montre sa case : sans question, rien à dire sur ``reponse``
        suite = " ; ce que la personne répond à la question en attente va dans reponse" if "reponse" in set(cases_montrees or ()) else ""
        return refus("format", manques, reste="refais la même fiche, " + (en_une_phrase(dites) or "") + suite)
    if not fautes:
        return None
    dites = [f"{c} {FORMES_ATTENDUES.get(_type_du_chemin(c, proprietes) or '', 'au type de sa case')}" for c in fautes]
    return refus("format", fautes, reste="refais la même fiche, écris " + (en_une_phrase(dites) or ""))


def reponse_manquante(fiche: dict[str, Any], question: dict | None, question_posee: bool) -> dict | None:
    """Une question déjà posée attend et la fiche n'a pas ``reponse`` : refus entier, la question rappelée (B8 point 1)."""
    if not question or not question_posee or isinstance(fiche.get("reponse"), dict):
        return None
    return refus("reponse_manquante", ["reponse"], question={k: question.get(k) for k in ("id", "type", "texte")},
                 reste=f"la fiche porte sa réponse à {question.get('id')} dans reponse")


# --------------------------------------------------------------------------- une case


def meme_forme(texte: Any) -> str:
    """La forme de comparaison d'une valeur de liste fermée (B10, défaut du simulateur : « 33 cl », « 2 viandes »)."""
    return re.sub(r"[^\w\-]", "", str(texte or "").strip(), flags=re.UNICODE).lower()


_TETE = re.compile(r"^\s*([\w\- ]+?)\s*[}\]\)\"',;:]", re.UNICODE)


def valeur_de_la_liste(valeur: Any, choix: Iterable[str]) -> str | None:
    """B5 (C3, D-L : ``"sens": "refuse},vider_le_panier:true"``) : la valeur de la liste fermée que la case porte, lue avec tolérance : mise sous même
    forme (« accepte} », « 33 cl »), sinon la valeur de la liste écrite EN TÊTE avant un signe de fin (« refuse},… »). Le reste n'est jamais lu ni
    exécuté. ``None`` : aucune valeur de la liste."""
    choix = [str(c) for c in choix]
    trouve = next((c for c in choix if meme_forme(c) == meme_forme(valeur)), None)
    if trouve is None and isinstance(valeur, str):
        tete = _TETE.match(valeur)
        if tete:
            trouve = next((c for c in choix if meme_forme(c) == meme_forme(tete.group(1))), None)
    return trouve


def valeur_hors_liste(chemin: str, valeur: Any, choix: Iterable[str]) -> tuple[str | None, dict | None]:
    """(la valeur de la liste, ``None``) ou (``None``, le refus avec les choix) : une valeur d'une liste fermée, mise sous même forme (E8)."""
    choix = [str(c) for c in choix]
    trouve = valeur_de_la_liste(valeur, choix)
    if trouve is not None:
        return trouve, None
    case = chemin.split(".")[0].split("[")[0]
    return None, refus("valeur_hors_liste", [case], chemin=chemin, valeur=str(valeur)[:40], choix=choix)


def sens_de_la_reponse(fiche: dict[str, Any], sens_permis: Iterable[str] = ("accepte", "refuse", "autre")) -> dict | None:
    """Le ``sens`` d'une réponse est une valeur d'une liste fermée, mise sous même forme (E8 : « accepte} » du clavier est « accepte ») ; hors liste, la fiche
    entière est refusée (``reponse_hors_liste``), jamais rangée à la devinette. Remplace ``fiche["reponse"]`` par une copie au sens juste."""
    reponse = fiche.get("reponse")
    if not isinstance(reponse, dict) or "sens" not in reponse:
        return None
    permis = [str(c) for c in sens_permis]
    juste = valeur_de_la_liste(reponse.get("sens"), permis)
    if juste is None:
        return refus("reponse_hors_liste", ["reponse"], valeur=str(reponse.get("sens"))[:40], choix=permis,
                     reste="reponse.sens est accepte, refuse ou autre")
    fiche["reponse"] = {**reponse, "sens": juste}
    return None


def valeur_pas_dans_ses_mots(fiche: dict[str, Any], paroles: Iterable[str], dit_par_le_code: Iterable[str] = (), cases: Iterable[str] = CASES_LIBRES) -> dict | None:
    """Les valeurs libres qu'elle n'a pas dites (après mise sous même forme, D57) : refusées, la case reste absente (E7). ``cases`` : les cases libres de
    l'étape (celles de la commande par défaut ; lot 7 : celles de la réservation)."""
    paroles, dit = list(paroles or ()), list(dit_par_le_code or ())
    hors = {k: fiche[k] for k in cases if fiche.get(k) not in (None, "") and not valeur_dite_par_elle(fiche[k], k, paroles, dit)}
    if not hors:
        return None
    return refus("valeur_pas_dans_ses_mots", hors, valeurs={k: str(v)[:40] for k, v in hors.items()},
                 pour=True, reste=", ".join(sorted(hors)) + " : une valeur libre reprend ses mots ; si elle ne l'a pas dite, laisse la case absente")


def recapitulatif_pas_accepte(fiche: dict[str, Any], cases_de_fin: Iterable[str], deja_accepte: bool, accepte_dans_la_fiche: bool) -> dict | None:
    """Les cases de la fin (moyen, billet, téléphone, prénom) avant son accord sur le récapitulatif : refusées (E26, B4)."""
    remplies = [k for k in cases_de_fin if fiche.get(k) not in (None, "", [])]
    if not remplies or deja_accepte or accepte_dans_la_fiche:
        return None
    return refus("recapitulatif_pas_accepte", remplies, pour=True, reste=", ".join(remplies) + " : elles se prennent après son accord sur le récapitulatif")


def chemins_montres(proprietes: dict[str, Any]) -> list[str]:
    return chemins_du_schema(proprietes)
