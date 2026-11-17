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


# --- T-01 (module Restauration, lot 5) -----------------------------------------------------------------------
# Un outil qui propose une phrase (clé ``suggestion``, au premier niveau ou dans ``data``) : le réglage ``restitution`` de l'outil
# dit si le modèle la prononce MOT POUR MOT ou la REFORMULE avec les mêmes faits. Mécanisme commun, aucun mot de métier. Réglage
# vide : rien n'est ajouté (un outil qui ne l'a pas posé se comporte comme avant).
CLE_SUGGESTION = "suggestion"
CLE_RESTITUTION = "restitution"
CLE_TEXTE_A_DIRE = "texte_a_dire"
CLE_CONSIGNE_RESTITUTION = "consigne_de_restitution"
# W17 : « dit par le code » : le texte de l'outil part DIRECTEMENT à la voix (``dire_par_le_code``), le modèle ne le reçoit jamais comme
# un texte à dire : il reçoit la consigne de ne pas le répéter. Pour ce qui ne doit pas dépendre de ce que le modèle sait ou invente.
DIT_PAR_LE_CODE = "dit_par_le_code"
CLE_DEJA_DIT = "deja_dit_par_le_code"
RESTITUTIONS = ("mot_pour_mot", "reformule", DIT_PAR_LE_CODE)
CONSIGNES_DE_RESTITUTION = {
    DIT_PAR_LE_CODE: (
        "Ce texte a déjà été dit à la personne, mot pour mot : ne le répète pas et n'y ajoute rien. Attends sa réponse. "
        "Si elle conteste ou corrige, ne le défends pas : corrige avec l'outil, puis rappelle-le."
    ),
    "mot_pour_mot": "Dis ce texte tel quel, mot pour mot, sans rien changer ni ajouter, puis attends la réponse du client.",
    "reformule": (
        "Reformule ce texte avec tes mots, naturellement, en gardant exactement les mêmes faits (montants, heures, noms, quantités). "
        "N'ajoute aucun fait qui n'y est pas."
    ),
}


def avec_restitution(resultat: Any, config: dict[str, Any] | None, par_defaut: str | None = None) -> Any:
    """Pose ``restitution`` (le mode), ``texte_a_dire`` (la phrase proposée, intacte) et ``consigne_de_restitution`` sur un résultat
    réussi qui porte une ``suggestion``. ``par_defaut`` : ce que recommande l'outil quand son réglage est vide. Jamais sur un
    échec. Ne lève jamais : dans le doute, le résultat passe tel qu'il est."""
    try:
        mode = (config or {}).get(CLE_RESTITUTION) or par_defaut
        if mode not in RESTITUTIONS or not isinstance(resultat, dict) or _est_un_echec(resultat):
            return resultat
        hote = resultat
        texte = hote.get(CLE_SUGGESTION)
        if not isinstance(texte, str) or not texte.strip():
            donnees = resultat.get("data")
            if isinstance(donnees, dict) and isinstance(donnees.get(CLE_SUGGESTION), str) and donnees[CLE_SUGGESTION].strip():
                texte = donnees[CLE_SUGGESTION]
            else:
                return resultat
        return {
            **resultat,
            CLE_RESTITUTION: mode,
            CLE_TEXTE_A_DIRE: texte.strip(),
            CLE_CONSIGNE_RESTITUTION: CONSIGNES_DE_RESTITUTION[mode],
        }
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[voix] restitution non posée : {erreur!r}")
        return resultat


# --- SA-38 (M89, appel 2574) : un texte dit par le code est dit UNE fois par tour -------------------------------------------
# Le registre des phrases que le code a dites dans le tour EN COURS de la personne (``CLE_TOUR`` de la fiche), gardé sur le moteur
# (jamais dans la fiche : rien à noter, seulement à ne pas redire). Lu par l'outil suivant (un résultat qui reproposerait une phrase déjà
# dite ne la redit pas) et par le cerveau (``reponse_avalee.SansRediteDuCode`` : la réplique du modèle qui recommence par une phrase déjà
# dite en est retirée). Sans compteur de tours (agent sans fiche) : rien n'est retenu, le comportement d'avant.
ATTRIBUT_REGISTRE = "_mark_dits_par_le_code"
# L'attribut du service de conversation où le registre se lit (posé par ``noter_dit_par_le_code``).
ATTRIBUT_LECTEUR_DU_SERVICE = "mark_dits_par_le_code"
_FIN_DE_PHRASE = r"(?<=[.!?…])[\"'»\)]?\s+"


def phrases_de(texte: Any) -> list[str]:
    """Les phrases d'un texte (coupées après « . ! ? … »), sans les vides."""
    import re

    if not isinstance(texte, str):
        return []
    return [p.strip() for p in re.split(_FIN_DE_PHRASE, texte.strip()) if p and p.strip()]


def empreinte_de_phrase(phrase: str) -> str:
    """Ce qui fait la phrase pour l'oreille : lettres et chiffres, en minuscules (ponctuation, blancs et apostrophes ignorés)."""
    return "".join(c for c in str(phrase).casefold() if c.isalnum())


def _tour_de(moteur: Any) -> int | None:
    try:
        from api.services.workflow.fiche_au_fil_de_leau import CLE_TOUR

        fiche = getattr(moteur, "_gathered_context", None)
        tour = fiche.get(CLE_TOUR) if isinstance(fiche, dict) else None
        return tour if isinstance(tour, int) and not isinstance(tour, bool) else None
    except Exception:  # noqa: BLE001
        return None


def dits_par_le_code_du_tour(moteur: Any) -> list[str]:
    """Les textes que le code a dits dans le tour en cours de la personne (``[]`` : aucun, ou pas de compteur de tours)."""
    try:
        tour = _tour_de(moteur)
        registre = getattr(moteur, ATTRIBUT_REGISTRE, None)
        if tour is None or not isinstance(registre, dict) or registre.get("tour") != tour:
            return []
        return list(registre.get("textes") or [])
    except Exception:  # noqa: BLE001
        return []


def noter_dit_par_le_code(moteur: Any, texte: str) -> None:
    """Retient ``texte`` comme dit par le code dans ce tour, et pose la lecture du registre sur le service de conversation de l'agent
    actif (le cerveau y lit ce qu'il ne doit pas redire). ⛔ Ne lève jamais."""
    try:
        tour = _tour_de(moteur)
        if tour is None:
            return
        registre = getattr(moteur, ATTRIBUT_REGISTRE, None)
        if not isinstance(registre, dict) or registre.get("tour") != tour:
            registre = {"tour": tour, "textes": []}
            setattr(moteur, ATTRIBUT_REGISTRE, registre)
        registre["textes"].append(texte)
        for agent in (getattr(moteur, "active_agent", None), getattr(moteur, "pending_agent", None)):
            llm = getattr(agent, "llm", None)
            if llm is not None:
                setattr(llm, ATTRIBUT_LECTEUR_DU_SERVICE, lambda: dits_par_le_code_du_tour(moteur))
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[voix] texte dit par le code non retenu : {erreur!r}")


# M108 : la question que le code a posée dans le tour EN COURS de la personne (gardée sur le moteur, jamais dans la fiche). Tant que la
# personne n'a pas parlé (même tour), elle attend sa réponse : la fin de l'appel ne part pas (``workflow/fin_apres_question_du_code``).
ATTRIBUT_QUESTION_DU_CODE = "_mark_question_du_code_au_tour"


def noter_une_question_du_code(moteur: Any) -> None:
    """Le code vient de finir sur une question à la personne, dans ce tour. ⛔ Ne lève jamais."""
    try:
        tour = _tour_de(moteur)
        if tour is not None:
            setattr(moteur, ATTRIBUT_QUESTION_DU_CODE, tour)
    except Exception:  # noqa: BLE001
        pass


def question_du_code_en_attente(moteur: Any) -> bool:
    """Le code a posé une question dans le tour en cours et la personne n'a pas encore répondu. ⛔ Ne lève jamais (``False`` dans le doute)."""
    try:
        tour = _tour_de(moteur)
        return tour is not None and getattr(moteur, ATTRIBUT_QUESTION_DU_CODE, None) == tour
    except Exception:  # noqa: BLE001
        return False


def finit_par_une_question(texte: Any) -> bool:
    """Le texte se termine-t-il par une question (« ? » en dernier signe, guillemets et blancs de fin ignorés) ?"""
    if not isinstance(texte, str):
        return False
    return texte.rstrip().rstrip("\"'»)").rstrip().endswith("?")


def _phrases_nouvelles(texte: str, deja: list[str]) -> list[str]:
    """Les phrases de ``texte`` que le code n'a pas encore dites dans ce tour."""
    vues = {empreinte_de_phrase(p) for d in deja for p in phrases_de(d)}
    vues.discard("")
    return [p for p in phrases_de(texte) if empreinte_de_phrase(p) not in vues]


def _sans_le_texte(resultat: dict[str, Any]) -> dict[str, Any]:
    """Le résultat sans son texte à dire (ni ``suggestion`` ni ``texte_a_dire``, ni dans ``data``), avec la consigne « déjà dit »."""
    sortie = {c: v for c, v in resultat.items() if c not in (CLE_SUGGESTION, CLE_TEXTE_A_DIRE)}
    donnees = sortie.get("data")
    if isinstance(donnees, dict) and CLE_SUGGESTION in donnees:
        sortie["data"] = {c: v for c, v in donnees.items() if c != CLE_SUGGESTION}
    sortie[CLE_CONSIGNE_RESTITUTION] = CONSIGNES_DE_RESTITUTION[DIT_PAR_LE_CODE]
    sortie[CLE_DEJA_DIT] = True
    return sortie


def _texte_propose(resultat: dict[str, Any]) -> str | None:
    donnees = resultat.get("data") if isinstance(resultat.get("data"), dict) else {}
    for texte in (resultat.get(CLE_TEXTE_A_DIRE), resultat.get(CLE_SUGGESTION), donnees.get(CLE_SUGGESTION)):
        if isinstance(texte, str) and texte.strip():
            return texte.strip()
    return None


def deja_dit_dans_le_tour(moteur: Any, resultat: Any) -> Any:
    """SA-38 (M89) : un résultat réussi dont TOUT le texte proposé a déjà été dit par le code dans ce tour (le même outil rappelé, ou un
    outil qui repropose la question déjà posée) ne le repropose pas : le modèle reçoit le résultat sans le texte et la consigne « déjà
    dit ». Un texte en partie neuf passe tel quel. ⛔ Ne lève jamais."""
    try:
        if not isinstance(resultat, dict) or _est_un_echec(resultat) or resultat.get(CLE_DEJA_DIT):
            return resultat
        deja = dits_par_le_code_du_tour(moteur)
        texte = _texte_propose(resultat) if deja else None
        if not texte or _phrases_nouvelles(texte, deja):
            return resultat
        logger.info("[voix] texte de l'outil déjà dit par le code dans ce tour : pas reproposé")
        return _sans_le_texte(resultat)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[voix] redite de l'outil non vérifiée : {erreur!r}")
        return resultat


async def dire_par_le_code(moteur: Any, resultat: Any) -> Any:
    """``dire_par_le_code_et_rendre_la_parole`` sans l'indication de tour de parole."""
    sortie, _rend_la_parole = await dire_par_le_code_et_rendre_la_parole(moteur, resultat)
    return sortie


async def dire_par_le_code_et_rendre_la_parole(moteur: Any, resultat: Any) -> tuple[Any, bool]:
    """Rend ``(résultat pour le modèle, la parole revient à la personne)``. Le second est vrai quand le texte que le code vient de dire
    pour ce résultat se termine par une question (SA-40, M92) : le tour de l'agent s'arrête là, l'appelant de cette fonction ne demande
    aucune génération au modèle. ⛔ Ne lève jamais.

    W17 : un résultat en mode ``dit_par_le_code`` voit son texte envoyé à la voix par le code, sans passer par le modèle.

    Le texte entre dans l'historique comme une réplique de l'agent (``append_to_context``), la transcription et le journal de l'appel
    (``persist_to_logs``), et reste coupable par l'appelant comme toute réplique (``mute_user`` faux). Au clavier, la même file de parole
    le rend comme une réplique de l'agent. Le modèle reçoit le résultat SANS le texte (ni ``suggestion`` ni ``texte_a_dire``) et la
    consigne de ne pas le redire. Si la voix ne peut pas le dire (pas de voix, appel fermé, échec), le texte reste au modèle, en
    « mot pour mot » : jamais un texte perdu. Jamais sur un échec. ⛔ Ne lève jamais.

    SA-38 (M89) : dans un tour, une phrase déjà dite par le code ne l'est pas une seconde fois (``deja_dit_dans_le_tour``) : seules les
    phrases neuves partent à la voix, et un texte tout entier déjà dit ne part pas."""
    try:
        resultat = deja_dit_dans_le_tour(moteur, resultat)
        if not isinstance(resultat, dict) or resultat.get(CLE_RESTITUTION) != DIT_PAR_LE_CODE or _est_un_echec(resultat):
            return resultat, False
        texte = resultat.get(CLE_TEXTE_A_DIRE)
        if not isinstance(texte, str) or not texte.strip():
            return resultat, False
        deja = dits_par_le_code_du_tour(moteur)
        if deja:
            texte = " ".join(_phrases_nouvelles(texte, deja)) or texte
        parole = None
        try:
            parole = await moteur.queue_speech(texte, append_to_context=True, persist_to_logs=True, mute_user=False)
            dit = getattr(getattr(parole, "outcome", None), "name", None) not in ("FAILED", "SKIPPED", "CLOSED")
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[voix] texte du code non envoyé à la voix : {erreur!r}")
            dit = False
        if not dit:
            return {**resultat, CLE_RESTITUTION: "mot_pour_mot", CLE_CONSIGNE_RESTITUTION: CONSIGNES_DE_RESTITUTION["mot_pour_mot"]}, False
        try:
            moteur.phrases.coupures.noter(texte, (), parole, True)  # l'interruption se traite comme pour toute phrase du code
        except Exception:  # noqa: BLE001, S110 -- pas de diseur (moteur de fond) : rien à noter
            pass
        noter_dit_par_le_code(moteur, texte)
        rend_la_parole = finit_par_une_question(texte)
        if rend_la_parole:
            noter_une_question_du_code(moteur)  # M108 : la fin de l'appel attend la réponse de la personne
            logger.info("[voix] le texte du code finit par une question : la parole revient à la personne, le modèle n'est pas relancé")
        return _sans_le_texte(resultat), rend_la_parole
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[voix] dit par le code non fait : {erreur!r}")
        return resultat, False


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
