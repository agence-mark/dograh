"""[.mark] Builder partie 3, lot R : ce que l'outil dit au modèle et ce qu'il lui renvoie, pour la voix.

Quatre gestes, tous au même endroit, aucun mot de métier :

- **C4, l'échec en mots de voix** : tout échec d'outil porte ``a_dire_au_client``, ce que le modèle répond au client
  (jamais le texte technique, jamais « c'est fait »). Réglable par outil (``consigne_en_cas_d_echec``). Ne fait que
  rendre le texte plus juste pour le modèle : allumé partout.
- **C6, la consigne de parole** : un résultat réussi peut porter ``consigne_de_parole`` (texte fixe de l'outil, ou
  consigne que le service lui-même renvoie). Éteint par défaut. Jamais sur un échec : la vérité des actions reste la règle.
- **C7, le résumé pour la voix** : les N premiers éléments d'une liste, les chaînes coupées, les champs lourds retirés.
  Éteint par défaut (``resume_pour_la_voix``).
- **C8, les champs appliqués et ignorés** : une écriture réussie dit ce que le logiciel a retenu et ce qu'il a laissé.
  D'après la réponse du logiciel quand il le dit, sinon d'après ce qui a été envoyé. ``champs_appliques`` à ``False``
  l'éteint.

⛔ Ne lève jamais : dans le doute, le résultat passe tel qu'il est.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

# --- C4 -------------------------------------------------------------------------------------------------------
# Des mots de voix : ce que l'on dit à quelqu'un au téléphone. Ni « bug », ni « erreur », ni « système »,
# ni « connexion » (test).
CONSIGNES_D_ECHEC = {
    "indisponible": (
        "Dis au client, simplement et avec naturel, que tu n'y arrives pas à l'instant. Propose de réessayer dans un "
        "moment ou de faire rappeler la personne. N'annonce rien comme fait. Ne lis jamais le détail technique."
    ),
    "delai": (
        "La réponse tarde. Dis au client que cela prend plus de temps que prévu et propose de patienter un instant ou "
        "d'être rappelé. N'annonce rien comme fait. Ne lis jamais le détail technique."
    ),
    "refuse": (
        "Ce n'est pas possible tel que demandé. Dis-le simplement au client, sans détail technique, et propose un autre "
        "choix (une autre date, une autre option) ou un rappel. N'annonce rien comme fait."
    ),
    "a_corriger": (
        "Une des informations envoyées n'est pas acceptée. Redemande-la au client avec des mots simples, puis rappelle "
        "l'outil. Ne dis pas que quelque chose a échoué."
    ),
    "deja_dit": (
        "Tu viens de le dire au client. N'ajoute aucun détail technique ; propose la suite (réessayer plus tard ou un "
        "rappel). N'annonce rien comme fait."
    ),
}
NATURES = frozenset(CONSIGNES_D_ECHEC)


def _est_un_echec(resultat: Any) -> bool:
    return isinstance(resultat, dict) and (
        resultat.get("status") == "error" or resultat.get("error") not in (None, "", False)
    )


def nature_de_l_echec(resultat: dict[str, Any]) -> str:
    """``a_corriger`` si l'outil l'a dit, ``refuse`` sur un 4xx, ``delai`` sur un délai dépassé, sinon ``indisponible``."""
    nature = resultat.get("nature")
    if nature in NATURES:
        return nature
    code = resultat.get("status_code")
    if isinstance(code, int) and 400 <= code < 500:
        return "refuse"
    texte = str(resultat.get("error") or "").casefold()
    if "timed out" in texte or "deadline" in texte or "délai" in texte:
        return "delai"
    return "indisponible"


def echec_pour_la_voix(resultat: Any, config: dict[str, Any] | None = None) -> Any:
    """Ajoute ``a_dire_au_client`` à un échec. Un résultat qui n'est pas un échec, ou qui le dit déjà, passe tel quel."""
    try:
        if not _est_un_echec(resultat) or resultat.get("a_dire_au_client"):
            return resultat
        propre = str((config or {}).get("consigne_en_cas_d_echec") or "").strip()
        if propre:
            texte = propre
        elif resultat.get("said_to_caller"):
            texte = CONSIGNES_D_ECHEC["deja_dit"]
        else:
            texte = CONSIGNES_D_ECHEC[nature_de_l_echec(resultat)]
        return {**resultat, "a_dire_au_client": texte}
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[voix] consigne d'échec non posée : {erreur!r}")
        return resultat


def echec_simple(config: dict[str, Any] | None = None, *, nature: str = "indisponible", detail: str = "") -> dict[str, Any]:
    """Un échec fabriqué par le moteur (exception du gestionnaire) : déjà en mots de voix."""
    return echec_pour_la_voix({"status": "error", "error": detail or "unavailable", "nature": nature}, config)


# --- C6 -------------------------------------------------------------------------------------------------------
CLE_CONSIGNE = "consigne_de_parole"
LONGUEUR_MAX_CONSIGNE = 600


def avec_consigne_de_parole(resultat: Any, config: dict[str, Any] | None) -> Any:
    """Sur un résultat réussi seulement : pose ``consigne_de_parole`` (le texte fixe de l'outil, sinon, si
    ``consigne_de_parole_du_service`` est allumé, celle que le service renvoie dans sa réponse). Éteint par défaut."""
    try:
        config = config or {}
        if not isinstance(resultat, dict) or _est_un_echec(resultat):
            return resultat
        fixe = str(config.get(CLE_CONSIGNE) or "").strip()
        donnees = resultat.get("data")
        du_service = None
        sortie = dict(resultat)
        if config.get("consigne_de_parole_du_service") is True:
            for hote_nom, hote in (("data", donnees), ("", resultat)):
                if isinstance(hote, dict) and isinstance(hote.get(CLE_CONSIGNE), str) and hote[CLE_CONSIGNE].strip():
                    du_service = hote[CLE_CONSIGNE].strip()
                    if hote_nom == "data":
                        sortie["data"] = {k: v for k, v in donnees.items() if k != CLE_CONSIGNE}
                    break
        texte = du_service or fixe
        if not texte:
            return resultat
        sortie[CLE_CONSIGNE] = texte[:LONGUEUR_MAX_CONSIGNE]
        return sortie
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[voix] consigne de parole non posée : {erreur!r}")
        return resultat


# --- C7 -------------------------------------------------------------------------------------------------------
ELEMENTS_PAR_DEFAUT = 3
CARACTERES_PAR_DEFAUT = 1200


def _reglage_entier(config: dict[str, Any], cle: str, defaut: int, bas: int, haut: int) -> int:
    try:
        return max(bas, min(haut, int(config.get(cle) if config.get(cle) is not None else defaut)))
    except (TypeError, ValueError):
        return defaut


def _resumer(valeur: Any, n: int, car: int, retires: frozenset[str], trace: dict[str, int]) -> Any:
    if isinstance(valeur, str):
        if len(valeur) > car:
            trace["chaines_coupees"] += 1
            return valeur[:car].rstrip() + "…"
        return valeur
    if isinstance(valeur, list):
        gardes = valeur[:n]
        if len(valeur) > n:
            trace["elements_ecartes"] += len(valeur) - n
        return [_resumer(v, n, car, retires, trace) for v in gardes]
    if isinstance(valeur, dict):
        sortie: dict[str, Any] = {}
        for cle, v in valeur.items():
            if str(cle) in retires:
                trace["champs_retires"] += 1
                continue
            sortie[cle] = _resumer(v, n, car, retires, trace)
            if isinstance(v, list) and len(v) > n:
                sortie[f"{cle}_total"] = len(v)
        return sortie
    return valeur


def resume_pour_la_voix(resultat: Any, config: dict[str, Any] | None) -> Any:
    """Réduit ``data`` avant le modèle : N premiers éléments des listes (3), chaînes coupées (1 200 caractères), champs
    lourds retirés. Le nombre total d'une liste coupée reste dit (``<clé>_total``, ou ``total`` pour une liste seule).
    Éteint par défaut. Un échec n'est pas résumé. Posé APRÈS la copie dans la fiche : la fiche garde tout."""
    try:
        config = config or {}
        if config.get("resume_pour_la_voix") is not True:
            return resultat
        if not isinstance(resultat, dict) or _est_un_echec(resultat) or "data" not in resultat:
            return resultat
        n = _reglage_entier(config, "resume_max_elements", ELEMENTS_PAR_DEFAUT, 1, 50)
        car = _reglage_entier(config, "resume_max_caracteres", CARACTERES_PAR_DEFAUT, 50, 20000)
        retires = frozenset(str(c) for c in (config.get("resume_champs_retires") or []))
        trace = {"elements_ecartes": 0, "chaines_coupees": 0, "champs_retires": 0}
        donnees = resultat["data"]
        resume = _resumer(donnees, n, car, retires, trace)
        if isinstance(donnees, list) and len(donnees) > n:
            resume = {"total": len(donnees), "elements": resume}
        sortie = {**resultat, "data": resume}
        if any(trace.values()):
            sortie["resume_pour_la_voix"] = trace
        return sortie
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[voix] résumé non fait : {erreur!r}")
        return resultat


# --- C8 -------------------------------------------------------------------------------------------------------
METHODES_D_ECRITURE = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_LISTES_APPLIQUES = ("champs_appliques", "applied_fields")
_LISTES_IGNORES = ("champs_ignores", "ignored_fields")
_OBJETS_ECHO = ("data", "record", "fields", "resource", "item", "result", "attributes")


def _liste_de_noms(hote: Any, noms: tuple[str, ...]) -> list[str] | None:
    if not isinstance(hote, dict):
        return None
    for nom in noms:
        valeur = hote.get(nom)
        if isinstance(valeur, list):
            return [str(v) for v in valeur]
    return None


def _objet_en_echo(donnees: Any, envoyes: list[str]) -> dict[str, Any] | None:
    """L'objet de la réponse qui reprend au moins un des champs envoyés (le logiciel renvoie ce qu'il a enregistré)."""
    candidats: list[Any] = [donnees]
    if isinstance(donnees, dict):
        candidats += [donnees.get(cle) for cle in _OBJETS_ECHO]
    for candidat in candidats:
        if isinstance(candidat, dict) and any(champ in candidat for champ in envoyes):
            return candidat
    return None


def champs_appliques_et_ignores(envoye: Any, donnees: Any) -> dict[str, Any] | None:
    """(appliqués, ignorés, source) pour ce qui a été envoyé. ``None`` : rien d'envoyé sous forme de champs."""
    if not isinstance(envoye, dict) or not envoye:
        return None
    noms = [str(c) for c in envoye]
    appliques = _liste_de_noms(donnees, _LISTES_APPLIQUES)
    ignores = _liste_de_noms(donnees, _LISTES_IGNORES)
    if appliques is not None or ignores is not None:
        if appliques is None:
            appliques = [c for c in noms if c not in (ignores or [])]
        if ignores is None:
            ignores = [c for c in noms if c not in appliques]
        return {"champs_appliques": appliques, "champs_ignores": ignores, "champs_source": "reponse"}
    echo = _objet_en_echo(donnees, noms)
    if echo is not None:
        return {
            "champs_appliques": [c for c in noms if c in echo],
            "champs_ignores": [c for c in noms if c not in echo],
            "champs_source": "reponse",
        }
    return {"champs_appliques": noms, "champs_ignores": [], "champs_source": "envoi"}


def avec_les_champs_appliques(
    resultat: Any, config: dict[str, Any] | None, methode: str, envoye: Any
) -> Any:
    """Une écriture réussie dit ce qui est appliqué et ce qui est ignoré. Un outil qui lit n'est pas touché."""
    try:
        config = config or {}
        if config.get("champs_appliques") is False or str(methode).upper() not in METHODES_D_ECRITURE:
            return resultat
        if not isinstance(resultat, dict) or _est_un_echec(resultat) or resultat.get("status") != "success":
            return resultat
        dit = champs_appliques_et_ignores(envoye, resultat.get("data"))
        return {**resultat, **dit} if dit else resultat
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[voix] champs appliqués non calculés : {erreur!r}")
        return resultat
