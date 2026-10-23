"""[.mark] Chantier fiabilite-orchestration : l'enveloppe des actions (outils HTTP, MCP, connecteurs).

Toute action qu'un agent ou le cerveau de fond appelle passe par cette enveloppe, posée au moment
où ``CustomToolManager`` enregistre son gestionnaire. Elle ne change rien à l'action ; elle lit son
résultat pour :

- **lot 1 (R3, G2)** : écrire les champs de la fiche « remplis par l'outil » (``rempli_par_outil``)
  depuis le résultat de cet outil, et seulement de lui. La valeur : la clé du même nom dans la
  réponse, sinon son statut, sinon la première valeur permise du champ, sinon « oui ». Un échec
  n'écrit rien. La réponse d'un outil HTTP est lue dans son emballage (``data``), jamais l'emballage
  lui-même (chantier ``fiche-lit-la-reponse-de-l-outil``, run 1475). Les contrôles restent ceux du point d'écriture unique (liste fermée comprise).

- **lot 4 bis (F21)** puis **correctifs-apres-banc-v4 (lot 4)** : une action du tour qui dépasse le délai
  de la règle « un outil travaille » fait dire sa phrase par la veille générique du diseur (redites,
  plafonds, sortie de la règle) ; le délai court depuis le lancement de l'action (une attente du
  système) et jamais pendant que l'appelant parle. La règle peut viser cet outil par son nom. Une action
  du cerveau de fond ne la déclenche jamais (le motif « le travail de fond travaille » s'en charge).

- **correctifs-apres-banc-v4 (lot 4)** : un résultat qui dit une panne (erreur de l'outil après ses
  essais, service qui répond « échec ») passe par la règle « un outil échoue » : la phrase, le compteur
  dans l'appel, la sortie de la règle (noter, transférer, raccrocher), puis un compte rendu en français
  dans le résultat que lit le modèle. Un outil sans règle posée ne dit rien de plus qu'avant (le défaut
  du catalogue ne parle que pour un connecteur, qui disait déjà sa phrase).

Les portes, passations, transferts et la fin d'appel n'y passent jamais : ce ne sont pas des actions.
⛔ Ne lève jamais : l'action rend toujours son résultat, l'enveloppe ne fait que regarder.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

# « missing » (connecteur à qui il manque un paramètre) et « incomplet » (garde de l'étape) : rien n'est fait,
# donc rien à écrire (relecture du 20/10).
_ERREURS = frozenset(
    {"error", "erreur", "echec", "échec", "failed", "failure", "ko", "missing", "incomplet"}
)
# Les vraies pannes (la règle « un outil échoue ») : « missing » et « incomplet » ne sont pas des pannes,
# rien n'a été tenté (un paramètre manque, la garde de l'étape retient l'outil).
_PANNES = _ERREURS - {"missing", "incomplet"}


def _normaliser(nom: Any) -> str:
    from api.services.workflow.tools.custom_tool import custom_tool_function_name

    return custom_tool_function_name(str(nom or ""))


def _lire(resultat: Any) -> Any:
    if isinstance(resultat, str):
        try:
            return json.loads(resultat)
        except (TypeError, ValueError):
            return resultat
    return resultat


def _reponse(lu: Any) -> Any:
    """La réponse du service derrière l'action. Un outil HTTP de Dograh l'emballe :
    ``{"status": "success", "status_code": 200, "data": <réponse>}`` (``execute_http_tool``) ; le
    ``status`` de l'emballage dit que l'appel HTTP est passé, pas ce que le service a répondu
    (run 1475 : « success » écrit à la place de « confirme », refusé hors liste). Sans emballage :
    le résultat tel quel."""
    if isinstance(lu, dict) and "status_code" in lu and "data" in lu:
        return _lire(lu["data"])
    return lu


def _dit_un_echec(lu: Any) -> bool:
    if isinstance(lu, dict):
        if lu.get("error") not in (None, "", False):
            return True
        for cle in ("statut", "status"):
            valeur = lu.get(cle)
            if isinstance(valeur, str) and valeur.strip().casefold() in _ERREURS:
                return True
    return False


def est_un_echec(resultat: Any) -> bool:
    """L'emballage en échec (HTTP en erreur), ou la réponse du service en échec (rendue en 200)."""
    lu = _lire(resultat)
    return _dit_un_echec(lu) or _dit_un_echec(_reponse(lu))


def _dit_une_panne(lu: Any) -> bool:
    if isinstance(lu, dict):
        if lu.get("error") not in (None, "", False):
            return True
        for cle in ("statut", "status"):
            valeur = lu.get(cle)
            if isinstance(valeur, str) and valeur.strip().casefold() in _PANNES:
                return True
    return False


def est_une_panne(resultat: Any) -> bool:
    """Le résultat dit une vraie panne (outil en erreur après ses essais, service qui répond un échec),
    non un paramètre manquant ni une étape incomplète. Sert la règle « un outil échoue »."""
    lu = _lire(resultat)
    return _dit_une_panne(lu) or _dit_une_panne(_reponse(lu))


def valeur_pour_le_champ(champ: Any, resultat: Any) -> Any:
    """La valeur qu'un résultat d'outil réussi écrit dans ``champ`` (voir l'en-tête), lue dans la
    réponse du service, jamais dans l'emballage d'un outil HTTP. ``None`` : rien à écrire.

    Une réponse HTTP n'écrit que ce qu'elle dit (la clé du champ, sinon son statut) : jamais la
    première valeur permise par défaut. Un service qui répond « lancé » avant d'avoir agi (webhook
    à réponse immédiate) n'écrit donc jamais « confirme » (relecture du 20/10)."""
    brut = _lire(resultat)
    lu = _reponse(brut)
    if isinstance(lu, dict):
        if lu.get(champ.nom) not in (None, ""):
            return lu[champ.nom]
        for cle in ("statut", "status"):
            if isinstance(lu.get(cle), str) and lu[cle].strip():
                return lu[cle].strip()
    if lu is not brut:
        return None
    if champ.valeurs:
        return champ.valeurs[0]
    return "oui"


def valeur_d_annulation(champ: Any, resultat: Any) -> Any:
    """Lot 8 (K16) : la valeur qu'un résultat d'outil d'annulation réussi écrit dans ``champ`` : ce que la
    réponse du service dit (la clé du champ, sinon son statut), JAMAIS une valeur par défaut (la première valeur
    permise est celle de la réservation). ``None`` : rien à écrire."""
    lu = _reponse(_lire(resultat))
    if isinstance(lu, dict):
        if lu.get(champ.nom) not in (None, ""):
            return lu[champ.nom]
        for cle in ("statut", "status"):
            if isinstance(lu.get(cle), str) and lu[cle].strip():
                return lu[cle].strip()
    return None


def champs_annules_par(moteur: Any, nom_outil: str) -> list[Any]:
    """Les champs de la fiche que ``nom_outil`` défait (``annule_par_outil``). ⛔ Ne lève jamais."""
    try:
        reglages = getattr(moteur, "_fiche", None)
        cible = _normaliser(nom_outil)
        return [
            c
            for c in tuple(getattr(reglages, "champs", None) or ())
            if getattr(c, "annule_par_outil", None) and _normaliser(c.annule_par_outil) == cible
        ]
    except Exception:  # noqa: BLE001
        return []


def remplir_par_l_action(moteur: Any, nom_outil: str, resultat: Any) -> list[str]:
    """Écrit les champs que ``nom_outil`` remplit (``rempli_par_outil``) ou défait (``annule_par_outil``, lot 8).
    Rend les noms des champs écrits. ⛔ Ne lève jamais."""
    ecrits: list[str] = []
    try:
        reglages = getattr(moteur, "_fiche", None)
        fiche = getattr(moteur, "_gathered_context", None)
        if reglages is None or not isinstance(fiche, dict):
            return ecrits
        cible = _normaliser(nom_outil)
        champs = [
            c
            for c in reglages.champs
            if c.rempli_par_outil and _normaliser(c.rempli_par_outil) == cible
        ]
        annules = champs_annules_par(moteur, nom_outil)
        if not champs and not annules:
            return ecrits
        if est_un_echec(resultat):
            logger.info(f"[fiche] {nom_outil} en échec : {', '.join(c.nom for c in champs + annules)} non écrits")
            return ecrits
        from api.services.workflow.fiche_au_fil_de_leau import (
            SOURCE_ACTION,
            ecrire_dans_la_fiche,
        )

        for champ in champs + [c for c in annules if c not in champs]:
            valeur = (
                valeur_pour_le_champ(champ, resultat)
                if champ in champs
                else valeur_d_annulation(champ, resultat)
            )
            if valeur is None:
                logger.info(f"[fiche] {champ.nom} par {nom_outil} : rien dans la réponse, non écrit")
                continue
            verdict = ecrire_dans_la_fiche(
                fiche, reglages, champ.nom, valeur, source=SOURCE_ACTION
            )
            if verdict.statut == "ecrit":
                ecrits.append(champ.nom)
            logger.info(f"[fiche] {champ.nom} par {nom_outil} : {verdict.statut} ({verdict.raison})")
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[fiche] résultat de {nom_outil} non lu pour la fiche : {erreur!r}")
    return ecrits


# Lot 8 (K16, D-1) : l'issue réelle d'une annulation, dite au modèle. Génériques, aucun mot de métier.
ISSUE_ANNULE = "annule"
ISSUE_ECHEC = "echec"
ISSUE_NON_CONFIRME = "non_confirme"
CONSIGNE_ANNULATION = {
    ISSUE_ANNULE: "L'annulation est faite : dis-le à l'appelant, sans rien ajouter qui n'est pas dans le résultat.",
    ISSUE_ECHEC: (
        "L'annulation a échoué : elle n'a PAS eu lieu. Dis-le franchement à l'appelant (ne dis jamais que c'est "
        "annulé ou noté) et propose de prendre sa demande pour un rappel."
    ),
    ISSUE_NON_CONFIRME: (
        "Le service n'a pas confirmé l'annulation : ne dis pas que c'est annulé, dis que tu n'as pas la "
        "confirmation et propose de prendre sa demande pour un rappel."
    ),
}


def avec_l_issue_d_annulation(resultat: Any, ecrits: list[str]) -> Any:
    """Le résultat d'un outil d'annulation, avec son issue réelle (``issue``) et la consigne qui la dit au modèle.
    ``annule`` : le service l'a confirmée (un champ de la fiche écrit) ; ``echec`` : elle a échoué ; sinon
    ``non_confirme``. Un résultat qui n'est pas un dictionnaire est emballé dans ``resultat``. ⛔ Ne lève jamais."""
    try:
        issue = ISSUE_ECHEC if est_un_echec(resultat) else (ISSUE_ANNULE if ecrits else ISSUE_NON_CONFIRME)
        lu = _lire(resultat)
        en_texte = isinstance(resultat, str) and isinstance(lu, dict)
        if not isinstance(lu, dict):
            lu = {"resultat": resultat}
        ajoute = {**lu, "issue": issue, "consigne": CONSIGNE_ANNULATION[issue]}
        return json.dumps(ajoute, ensure_ascii=False, default=str) if en_texte else ajoute
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[fiche] issue d'annulation non écrite : {erreur!r}")
        return resultat


STATUT_INCOMPLET = "incomplet"


def garde_de_l_etape(moteur: Any, agent: Any) -> dict | None:
    """Lot 2 (F9, C3 ; run 1468 : action lancée avec des champs encore « à venir ») : l'étape de
    ``agent`` déclare la liste de ses champs, la case « connu et attendu » est allumée, et des
    champs manquent encore : l'outil ne s'exécute pas, il rend ``{"statut": "incomplet", "manque":
    [...]}`` (le modèle le lit et demande). Sans liste, sans fiche, case éteinte, ou rien ne
    manque : ``None`` (l'outil s'exécute comme avant). ⛔ Ne lève jamais."""
    return garde_du_noeud(moteur, getattr(agent, "current_node", None))


def garde_du_noeud(moteur: Any, noeud: Any) -> dict | None:
    """La garde de l'étape ``noeud`` (voir ``garde_de_l_etape``). Lot 7 de correctifs-apres-banc-commun : un
    champ dont la condition sur la fiche n'est pas tenue n'est pas attendu. Lot 6 : le déclenchement de l'outil
    d'action lit la même garde. ⛔ Ne lève jamais."""
    try:
        reglages = getattr(moteur, "_fiche", None)
        fiche = getattr(moteur, "_gathered_context", None)
        if reglages is None or not isinstance(fiche, dict) or not tuple(getattr(noeud, "champs_etape", None) or ()):
            return None
        from api.services.workflow.champs_conditionnels import champs_actifs

        champs_etape = champs_actifs(noeud, fiche)
        if not getattr(reglages, "etiquettes", False):
            return None
        from api.services.fiche.traces import valeurs_des_traces
        from api.services.groupe.notes import champs_attendus, nom_lisible

        manque = champs_attendus(reglages, fiche, champs_etape, valeurs_des_traces(reglages, fiche))
        if not manque:
            return None
        return {"statut": STATUT_INCOMPLET, "manque": [nom_lisible(n) for n in manque]}
    except Exception as erreur:  # noqa: BLE001 -- dans le doute, l'outil s'exécute comme avant
        logger.warning(f"[fiche] garde de l'étape illisible : {erreur!r}")
        return None


# K2 (run 1492 et 1510 : « manque nom, prénom, adresse » juste après les avoir dits) : la garde lisait la
# fiche pendant que la passe du greffier du même tour tournait encore. Au plus ce délai.
DELAI_DES_NOTES_DE_LA_GARDE = 1.5


async def garde_de_l_etape_apres_les_notes(moteur: Any, agent: Any) -> dict | None:
    """K2 : comme ``garde_de_l_etape``, mais avant de rendre « incomplet » elle laisse finir les passes
    en cours (greffier, post-scriptum : ``moteur.notes_en_cours``, 1,5 s au plus) puis relit la fiche.
    Aucun coût quand rien ne manque, ni quand aucune passe ne tourne. ⛔ Ne lève jamais."""
    return await garde_du_noeud_apres_les_notes(moteur, getattr(agent, "current_node", None))


async def garde_du_noeud_apres_les_notes(moteur: Any, noeud: Any) -> dict | None:
    """``garde_de_l_etape_apres_les_notes`` pour l'étape ``noeud`` (lot 6 : le déclenchement de l'outil d'action
    lit la même garde, avec la même attente). ⛔ Ne lève jamais."""
    refus = garde_du_noeud(moteur, noeud)
    if refus is None:
        return None
    try:
        from api.services.workflow.fiche_au_fil_de_leau import attendre_les_notes

        en_cours = getattr(moteur, "notes_en_cours", None)
        if not en_cours or all(t.done() for t in en_cours):
            return refus
        await attendre_les_notes(en_cours, DELAI_DES_NOTES_DE_LA_GARDE)
    except Exception as erreur:  # noqa: BLE001 -- dans le doute, la garde garde son verdict
        logger.warning(f"[fiche] passes en cours non attendues par la garde : {erreur!r}")
        return refus
    return garde_du_noeud(moteur, noeud)


Gestionnaire = Callable[[Any], Awaitable[None]]


def envelopper_l_action(
    moteur: Any,
    nom_outil: str,
    gestionnaire: Gestionnaire,
    agent: Any = None,
    *,
    garde: bool = True,
) -> Gestionnaire:
    """Le gestionnaire de l'action, enveloppé : la garde de l'étape d'``agent`` (lot 2), puis son
    résultat lu avant de partir au modèle (lot 1). ``garde=False`` : une action qui agit sur
    l'appel (une action interne qui peut transférer), jamais gardée."""

    if garde and agent is not None:
        # Lot 6 de correctifs-apres-banc-commun : le moteur sait quelles actions l'étape en préparation offre.
        from api.services.workflow.declenchement_de_l_action import noter_une_action_offerte

        noter_une_action_offerte(moteur, nom_outil)

    async def enveloppe(params: Any) -> None:
        if garde and agent is not None:
            refus = await garde_de_l_etape_apres_les_notes(moteur, agent)
            if refus is not None:
                logger.info(f"[fiche] {nom_outil} retenu : {refus['manque']} manquent")
                await params.result_callback(refus)
                return
        # Lot 5 de correctifs-apres-banc-commun (K7, V4) : la vérité des actions.
        arguments = getattr(params, "arguments", None)
        if garde and agent is not None:
            from api.services.workflow import verite_des_actions as verite

            refus = verite.garde_de_reservation(moteur, agent, nom_outil, arguments)
            if refus is not None:
                await params.result_callback(refus)
                return
            connu = verite.resultat_deja_confirme(moteur, agent, nom_outil, arguments)
            if connu is not None:
                await params.result_callback(connu)
                return
        if garde and agent is not None:
            # Lot 6 : l'outil de l'étape est appelé (par le modèle) pour cette demande : aucune position ne se réarme.
            from api.services.workflow.declenchement_de_l_action import noter_l_appel

            noter_l_appel(moteur, agent, nom_outil)
        rendre = params.result_callback
        fini = asyncio.Event()
        veille = _veiller_l_outil(moteur, nom_outil, agent, params, fini)

        async def result_callback(resultat: Any, *args: Any, **kwargs: Any) -> None:
            proprietes = kwargs.get("properties")
            # Un résultat intermédiaire (``is_final=False``) n'est pas encore la réponse de l'outil.
            if getattr(proprietes, "is_final", True) is not False:
                fini.set()
                ecrits = remplir_par_l_action(moteur, nom_outil, resultat)
                try:
                    from api.services.workflow.verite_des_actions import noter_l_action

                    fiche = getattr(moteur, "_gathered_context", None)
                    noter_l_action(
                        moteur,
                        nom_outil,
                        arguments,
                        resultat,
                        {n: fiche.get(n) for n in ecrits} if isinstance(fiche, dict) else {},
                    )
                except Exception as erreur:  # noqa: BLE001 -- le journal ne coûte jamais l'action
                    logger.debug(f"[verite] journal des actions : {erreur!r}")
                resultat, kwargs, issue = await _signaler_la_panne(
                    moteur, nom_outil, agent, params, resultat, kwargs
                )
                if champs_annules_par(moteur, nom_outil):
                    # Lot 8 (K16) : une annulation dit son issue réelle au modèle (faite, échouée, non confirmée).
                    resultat = avec_l_issue_d_annulation(resultat, ecrits)
                await rendre(resultat, *args, **kwargs)
                if issue is not None:
                    # L'action finale (transférer, raccrocher) part APRÈS la remise du résultat.
                    from api.services.phrases.sorties import lancer_apres

                    lancer_apres(moteur, issue)
                return
            await rendre(resultat, *args, **kwargs)

        try:
            params.result_callback = result_callback
        except Exception as erreur:  # noqa: BLE001 -- paramètres figés : l'action passe telle quelle
            logger.debug(f"[fiche] résultat de {nom_outil} non lu : {erreur!r}")
        try:
            await gestionnaire(params)
        finally:
            fini.set()
            # Une veille qui n'a encore rien dit est coupée ; une phrase commencée finit (ses redites
            # s'arrêtent d'elles-mêmes : l'outil n'est plus en cours).
            if veille is not None:
                from api.services.phrases.diseur import DiseurDePhrases

                DiseurDePhrases.arreter_la_veille(veille)

    return enveloppe


def _action_du_agent(agent: Any, moteur: Any, params: Any) -> Any | None:
    """L'agent qui porte cette action, ``None`` si elle vient du cerveau de fond (qui a son propre motif)."""
    cible = agent if agent is not None else getattr(moteur, "active_agent", None)
    appelant = getattr(params, "llm", None)
    if appelant is not None and appelant is not getattr(cible, "llm", None):
        return None
    return cible


def _veiller_l_outil(
    moteur: Any, nom_outil: str, agent: Any, params: Any, fini: asyncio.Event
) -> asyncio.Task | None:
    """F21 : la veille de « un outil travaille » pour cet appel d'outil (veille générique du diseur :
    délai, redites, plafonds, sortie). ``None`` : règle éteinte, pas de diseur, ou action du cerveau de
    fond. ⛔ Ne lève jamais."""
    try:
        from api.services.phrases.catalogue import OUTIL_TARDE
        from api.services.phrases.diseur import DiseurDePhrases

        diseur = getattr(moteur, "phrases", None)
        if not isinstance(diseur, DiseurDePhrases):
            return None
        cible = _action_du_agent(agent, moteur, params)
        if cible is None:
            return None
        phrase = diseur.phrase(OUTIL_TARDE, cible, outil=nom_outil)
        if phrase is None or not phrase.dite:
            return None
        return diseur.lancer_la_veille(
            OUTIL_TARDE,
            lambda: not fini.is_set(),
            nom="phrase:outil_tarde",
            agent=cible,
            outil=nom_outil,
            phrase=phrase,
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[phrases] veille de l'outil illisible : {erreur!r}")
        return None


def _avec_le_compte_rendu(resultat: Any, compte: str) -> Any:
    """Le compte rendu standard dans le résultat que lit le modèle (jamais un message à part)."""
    if not compte:
        return resultat
    if isinstance(resultat, dict):
        return {**resultat, "compte_rendu": compte}
    if isinstance(resultat, str):
        return f"{resultat}\n{compte}"
    return resultat


async def _signaler_la_panne(
    moteur: Any, nom_outil: str, agent: Any, params: Any, resultat: Any, kwargs: dict
) -> tuple[Any, dict, Any]:
    """Le résultat dit une panne : la règle « un outil échoue » (phrase, compteur, sortie), puis le
    compte rendu dans le résultat. La phrase entre dans l'historique APRÈS le résultat de l'outil (la
    case de l'appel en cours est complétée par ce résultat, la phrase vient derrière) : mesuré au lot 0,
    0/10 répétition. Une sortie qui a pris l'appel en main (transfert lancé, appel raccroché) : le modèle
    n'est pas relancé. ⛔ Ne lève jamais : sans règle posée, le résultat part tel quel."""
    try:
        from api.services.phrases.catalogue import MOTIFS, OUTIL_ECHOUE
        from api.services.phrases.compte_rendu import compte_rendu
        from api.services.phrases.diseur import DiseurDePhrases

        diseur = getattr(moteur, "phrases", None)
        if not isinstance(diseur, DiseurDePhrases) or not est_une_panne(resultat):
            return resultat, kwargs, None
        cible = _action_du_agent(agent, moteur, params)
        if cible is None:
            return resultat, kwargs, None
        probleme = await diseur.signaler_un_probleme(
            OUTIL_ECHOUE, cible, outil=nom_outil, seulement_si_posee=True
        )
        if probleme.dit is None and probleme.issue is None:
            return resultat, kwargs, None
        issue = probleme.issue
        compte = compte_rendu(
            MOTIFS[OUTIL_ECHOUE].fait_fr,
            dit=probleme.dit,
            notes=probleme.notes,
            interdits=issue.interdit if issue is not None else (),
        )
        resultat = _avec_le_compte_rendu(resultat, compte)
        if issue is not None and issue.prise_en_main:
            from pipecat.frames.frames import FunctionCallResultProperties

            kwargs = {**kwargs, "properties": FunctionCallResultProperties(run_llm=False)}
        return resultat, kwargs, issue
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[phrases] panne de {nom_outil} non signalée : {erreur!r}")
    return resultat, kwargs, None
