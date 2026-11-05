"""[.mark] Partie 3, sous-lot 21 : les conditions complètes d'une porte (étude ``05-etude-conditions-du-graphe.md``).

La condition d'une porte (``ConditionDePorteDTO``) s'ÉTEND, jamais une seconde structure. Avant : « étape complète » ou
« champ de la fiche = valeur ». En plus, tout éteint par défaut (un champ absent = la lecture d'avant, au bit près) :

- des **règles** (``regles``), lues « toutes » ou « au moins une » (``combien``) ; chaque règle a une source, un champ, une
  comparaison et une valeur. Sources : la fiche de l'appel, l'étape (complète), le résultat d'un outil de l'appel, l'heure
  et le jour (Paris), l'établissement servi, une variable de l'appel (contexte d'avant l'appel) ;
- **toujours** : la porte passe dès que le code regarde (l'étape est finie) ;
- **sinon** : la porte que le code prend quand, après la parole de l'appelant, aucune autre porte de l'étape ne passe
  (ni condition, ni arbitre). Une seule par étape : la première de l'écran.

Le code compare des noms fournis par la donnée de l'agent : aucun mot de métier ici. Une donnée absente, illisible ou
« à confirmer » rend la règle FAUSSE (dans le doute : fausse), sauf « est vide » sur un champ vraiment vide et « n'a pas
répondu » sur un outil jamais appelé. ⛔ Rien ici ne lève : une condition illisible est fausse, l'appel continue.

Lu seulement là où le code lit déjà la condition sur la fiche (``passage_sur_la_fiche``, ``porte_fermee_par_la_fiche``) :
une étape en mode ``agent`` ne lit rien, comme avant. Quand la fiche décide, une condition fausse ferme la porte au modèle
(RA-B, audit 01 A2).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Iterable, Mapping

from loguru import logger

# Les sources d'une règle (identifiants du JSON ; l'écran les nomme).
FICHE, ETAPE, OUTIL, HEURE, ETABLISSEMENT, VARIABLE = "fiche", "etape", "outil", "heure", "etablissement", "variable"
SOURCES = (FICHE, ETAPE, OUTIL, HEURE, ETABLISSEMENT, VARIABLE)

# Les comparaisons.
EST, N_EST_PAS, CONTIENT = "est", "n_est_pas", "contient"
EST_REMPLI, EST_VIDE = "est_rempli", "est_vide"
PLUS_GRAND, PLUS_PETIT = "plus_grand", "plus_petit"
EST_VRAI, EST_FAUX = "est_vrai", "est_faux"
AVANT, APRES = "avant", "apres"
A_REUSSI, A_ECHOUE, A_REPONDU, N_A_PAS_REPONDU = "a_reussi", "a_echoue", "a_repondu", "n_a_pas_repondu"
EST_COMPLETE, N_EST_PAS_COMPLETE = "est_complete", "n_est_pas_complete"

COMPARAISONS_PAR_SOURCE: dict[str, tuple[str, ...]] = {
    FICHE: (EST, N_EST_PAS, CONTIENT, EST_REMPLI, EST_VIDE, PLUS_GRAND, PLUS_PETIT),
    VARIABLE: (EST, N_EST_PAS, CONTIENT, EST_REMPLI, EST_VIDE, PLUS_GRAND, PLUS_PETIT),
    ETAPE: (EST_COMPLETE, N_EST_PAS_COMPLETE),
    OUTIL: (A_REUSSI, A_ECHOUE, A_REPONDU, N_A_PAS_REPONDU),
    HEURE: (AVANT, APRES, EST, N_EST_PAS),
    ETABLISSEMENT: (EST_VRAI, EST_FAUX, EST, N_EST_PAS, CONTIENT, EST_REMPLI, EST_VIDE),
}
COMPARAISONS = tuple(dict.fromkeys(c for cs in COMPARAISONS_PAR_SOURCE.values() for c in cs))

# Les champs fixes des sources qui ne lisent pas la donnée de l'agent.
CHAMPS_HEURE = ("heure", "jour")
CHAMPS_ETABLISSEMENT = ("ouvert", "etat", "nom")

TOUTES, AU_MOINS_UNE = "toutes", "au_moins_une"
COMBIEN = (TOUTES, AU_MOINS_UNE)

# Les types de lecture d'une porte (la trace ``passages_par_le_code`` les garde).
T_ETAPE_COMPLETE, T_CHAMP, T_REGLES, T_TOUJOURS, T_SINON = "etape_complete", "champ", "regles", "toujours", "sinon"

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


def _attr(objet: Any, nom: str) -> Any:
    if isinstance(objet, Mapping):
        return objet.get(nom)
    return getattr(objet, nom, None)


def _texte(valeur: Any) -> str:
    return valeur.strip() if isinstance(valeur, str) else ""


def _regle_lue(regle: Any) -> dict | None:
    source = _texte(_attr(regle, "source"))
    comparaison = _texte(_attr(regle, "comparaison"))
    if source not in SOURCES or comparaison not in COMPARAISONS_PAR_SOURCE[source]:
        return None
    champ = _texte(_attr(regle, "champ"))
    if source != ETAPE and not champ:
        return None
    return {"source": source, "champ": champ, "comparaison": comparaison, "valeur": _texte(_attr(regle, "valeur"))}


def lecture_de(condition: Any) -> dict | None:
    """La lecture d'une condition de porte, ou ``None`` (pas de condition). Sans champ nouveau, exactement la lecture
    d'avant : ``{type: etape_complete}`` ou ``{type: champ, champ, vaut}``. ⛔ Ne lève jamais."""
    try:
        if condition is None:
            return None
        if _attr(condition, "sinon") is True:
            return {"type": T_SINON}
        if _attr(condition, "toujours") is True:
            return {"type": T_TOUJOURS}
        ancien: list[dict] = []
        if _attr(condition, "etape_complete") is True:
            ancien.append({"source": ETAPE, "champ": "", "comparaison": EST_COMPLETE, "valeur": ""})
        champ = _texte(_attr(condition, "champ"))
        if champ:
            vaut = _texte(_attr(condition, "vaut"))
            ancien.append({"source": FICHE, "champ": champ, "comparaison": EST if vaut else EST_REMPLI, "valeur": vaut})
        regles_brutes = _attr(condition, "regles") or []
        regles = [r for r in (_regle_lue(x) for x in regles_brutes) if r is not None]
        if not regles_brutes:
            # La forme d'avant, inchangée (la trace aussi).
            if _attr(condition, "etape_complete") is True:
                return {"type": T_ETAPE_COMPLETE}
            if champ:
                return {"type": T_CHAMP, "champ": champ, "vaut": _texte(_attr(condition, "vaut"))}
            return None
        if len(regles) != len(regles_brutes):
            # Une règle illisible : la condition entière est fausse (jamais une règle oubliée en silence).
            return {"type": T_REGLES, "combien": TOUTES, "regles": [], "illisible": True}
        combien = _texte(_attr(condition, "combien")) or TOUTES
        return {"type": T_REGLES, "combien": combien if combien in COMBIEN else TOUTES, "regles": ancien + regles}
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[porte] condition illisible : {erreur!r}")
        return {"type": T_REGLES, "combien": TOUTES, "regles": [], "illisible": True}


# ---------------------------------------------------------------------------------------------------------
# Évaluer
# ---------------------------------------------------------------------------------------------------------


def _vide(valeur: Any) -> bool:
    if valeur is None:
        return True
    if isinstance(valeur, str):
        return not valeur.strip()
    if isinstance(valeur, (list, tuple, set, dict)):
        return len(valeur) == 0
    return False


def _plie(valeur: Any) -> str:
    return str(valeur).strip().casefold()


def _egal(valeur: Any, attendu: str) -> bool:
    if isinstance(valeur, (list, tuple, set)):
        return any(_egal(v, attendu) for v in valeur)
    return _plie(valeur) == _plie(attendu)


def _nombre(valeur: Any) -> float | None:
    if isinstance(valeur, bool):
        return None
    if isinstance(valeur, (int, float)):
        return float(valeur)
    if isinstance(valeur, str):
        try:
            return float(valeur.strip().replace(" ", "").replace(",", "."))
        except ValueError:
            return None
    return None


def comparer(valeur: Any, comparaison: str, attendu: str) -> bool:
    """Une valeur connue comparée (fiche, variable, établissement). Absente : seule « est vide » est vraie."""
    if comparaison == EST_VIDE:
        return _vide(valeur)
    if _vide(valeur):
        return False
    if comparaison == EST_REMPLI:
        return True
    if comparaison == EST:
        return _egal(valeur, attendu) if attendu else False
    if comparaison == N_EST_PAS:
        return (not _egal(valeur, attendu)) if attendu else False
    if comparaison == CONTIENT:
        if not attendu:
            return False
        if isinstance(valeur, (list, tuple, set)):
            return any(_plie(attendu) in _plie(v) for v in valeur)
        return _plie(attendu) in _plie(valeur)
    if comparaison in (PLUS_GRAND, PLUS_PETIT):
        a, b = _nombre(valeur), _nombre(attendu)
        if a is None or b is None:
            return False
        return a > b if comparaison == PLUS_GRAND else a < b
    if comparaison in (EST_VRAI, EST_FAUX):
        texte = _plie(valeur)
        vrai = valeur is True or texte in ("true", "vrai", "oui", "1")
        faux = valeur is False or texte in ("false", "faux", "non", "0")
        return vrai if comparaison == EST_VRAI else faux
    return False


def _maintenant() -> datetime:
    """L'instant de la lecture, heure de Paris (même fuseau que l'état d'ouverture)."""
    from api.services.pipecat.etat_ouverture import PARIS

    return datetime.now(PARIS)


_HEURE = re.compile(r"^\s*(\d{1,2})\s*(?:[:hH]\s*(\d{2})?)?\s*$")


def _minutes(texte: str) -> int | None:
    m = _HEURE.match(texte or "")
    if not m:
        return None
    heures, minutes = int(m.group(1)), int(m.group(2) or 0)
    if heures > 24 or minutes > 59:
        return None
    return heures * 60 + minutes


def _liste(attendu: str) -> list[str]:
    return [x.strip().casefold() for x in (attendu or "").split(",") if x.strip()]


def _regle_heure(champ: str, comparaison: str, attendu: str) -> bool:
    instant = _maintenant()
    if champ == "heure":
        cible = _minutes(attendu)
        if cible is None:
            return False
        maintenant = instant.hour * 60 + instant.minute
        return {
            AVANT: maintenant < cible,
            APRES: maintenant >= cible,
            EST: maintenant == cible,
            N_EST_PAS: maintenant != cible,
        }.get(comparaison, False)
    if champ == "jour":
        jours = _liste(attendu)
        if not jours or comparaison not in (EST, N_EST_PAS):
            return False
        aujourd_hui = JOURS[instant.weekday()]
        return (aujourd_hui in jours) if comparaison == EST else (aujourd_hui not in jours)
    return False


def _contexte_de_l_appel(moteur: Any) -> Mapping[str, Any]:
    contexte = getattr(moteur, "_call_context_vars", None)
    return contexte if isinstance(contexte, Mapping) else {}


def _regle_etablissement(moteur: Any, champ: str, comparaison: str, attendu: str) -> bool:
    from api.services.annonce.constantes import OUVERT
    from api.services.etablissements.appel import CLE_NOM
    from api.services.pipecat.etat_ouverture import CLE_ETAT

    contexte = _contexte_de_l_appel(moteur)
    if champ == "ouvert":
        etat = contexte.get(CLE_ETAT)
        if _vide(etat) or comparaison not in (EST_VRAI, EST_FAUX):
            return False  # agent sans horaires : on ne sait pas, la règle est fausse
        return (etat == OUVERT) if comparaison == EST_VRAI else (etat != OUVERT)
    if champ == "etat":
        return comparer(contexte.get(CLE_ETAT), comparaison, attendu)
    if champ == "nom":
        return comparer(contexte.get(CLE_NOM), comparaison, attendu)
    return False


def _reussi(enregistrement: Mapping[str, Any]) -> bool:
    if enregistrement.get("status") != "completed":
        return False
    resultat = enregistrement.get("result")
    if isinstance(resultat, Mapping):
        statut = _plie(resultat.get("status") or "")
        if statut in ("error", "erreur", "failed", "echec", "échec"):
            return False
        if resultat.get("success") is False or resultat.get("ok") is False:
            return False
    return True


def _regle_outil(moteur: Any, champ: str, comparaison: str) -> bool:
    from api.services.pipecat.trace_modele import RESULTATS_DES_OUTILS

    fiche = getattr(moteur, "_gathered_context", None)
    resultats = (fiche or {}).get(RESULTATS_DES_OUTILS) if isinstance(fiche, Mapping) else None
    derniers = [r for r in (resultats or []) if isinstance(r, Mapping) and r.get("function_name") == champ]
    if comparaison == N_A_PAS_REPONDU:
        return not derniers
    if not derniers:
        return False
    if comparaison == A_REPONDU:
        return True
    dernier = derniers[-1]
    return _reussi(dernier) if comparaison == A_REUSSI else not _reussi(dernier)


def _regle_fiche(moteur: Any, champ: str, comparaison: str, attendu: str) -> bool:
    from api.services.workflow.fiche_au_fil_de_leau import CLE_ETAT

    fiche = getattr(moteur, "_gathered_context", None)
    fiche = fiche if isinstance(fiche, Mapping) else {}
    etat = (fiche.get(CLE_ETAT) or {}).get(champ)
    if isinstance(etat, Mapping) and etat.get("sure") is False:
        return False  # encore « à confirmer » : on ne sait pas
    return comparer(fiche.get(champ), comparaison, attendu)


def regle_vraie(moteur: Any, noeud: Any, regle: Mapping[str, Any]) -> bool:
    """Une règle lue (``lecture_de``). ⛔ Ne lève jamais (dans le doute : fausse)."""
    try:
        source, champ, comparaison = regle["source"], regle.get("champ", ""), regle["comparaison"]
        attendu = regle.get("valeur", "")
        if source == ETAPE:
            from api.services.workflow.passage_sur_la_fiche import etape_complete

            complete = etape_complete(moteur, noeud)
            return complete if comparaison == EST_COMPLETE else not complete
        if source == FICHE:
            return _regle_fiche(moteur, champ, comparaison, attendu)
        if source == VARIABLE:
            return comparer(_contexte_de_l_appel(moteur).get(champ), comparaison, attendu)
        if source == HEURE:
            return _regle_heure(champ, comparaison, attendu)
        if source == ETABLISSEMENT:
            return _regle_etablissement(moteur, champ, comparaison, attendu)
        if source == OUTIL:
            return _regle_outil(moteur, champ, comparaison)
        return False
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[porte] règle illisible, fausse : {erreur!r}")
        return False


def condition_vraie(moteur: Any, noeud: Any, lecture: Mapping[str, Any]) -> bool:
    """Une lecture de porte (hors « sinon », décidée par l'étape entière) est-elle vraie ? ⛔ Ne lève jamais."""
    try:
        genre = lecture.get("type")
        if genre == T_TOUJOURS:
            return True
        if genre == T_ETAPE_COMPLETE:
            from api.services.workflow.passage_sur_la_fiche import etape_complete

            return etape_complete(moteur, noeud)
        if genre == T_CHAMP:
            from api.services.workflow.passage_sur_la_fiche import _champ_vaut

            return _champ_vaut(moteur, lecture["champ"], lecture.get("vaut"))
        if genre == T_REGLES:
            regles: Iterable[Mapping[str, Any]] = lecture.get("regles") or []
            regles = list(regles)
            if not regles or lecture.get("illisible"):
                return False
            if lecture.get("combien") == AU_MOINS_UNE:
                return any(regle_vraie(moteur, noeud, r) for r in regles)
            return all(regle_vraie(moteur, noeud, r) for r in regles)
        return False
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[porte] condition illisible, fausse : {erreur!r}")
        return False
