"""[.mark] Builder partie 3, SA-L3a (sous-lot 2, audit 04 § 3 et 11 § 5.4, décisions 05 § 2 et § 15) : les réglages « sans effet ».

Un réglage allumé qui ne change rien à l'appel, ou une sortie qui ne mène nulle part, est dit AVANT la publication, là où il se
règle, avec sa correction en un clic. Tout ici est PUR : la définition du graphe et les réglages de l'agent entrent, des constats
sortent. Aucun mot de métier : les étapes, les champs et les noms sont des données.

| Cas (``cle``)              | Contrôle (``controle``) | Quand                                                                                                   |
|----------------------------|-------------------------|---------------------------------------------------------------------------------------------------------|
| ``condition_sur_le_modele``| ``sans_effet``          | une liaison porte une condition sur la fiche, mais l'étape de départ laisse le modèle décider           |
| ``collecte_sans_fiche``    | ``sans_effet``          | l'étape passe par la fiche (collecte, choix, libre) et la fiche n'est pas active                        |
| ``portes_sans_fiche``      | ``sans_effet``          | « portes dans la réponse » allumé et la fiche n'est pas active                                          |
| ``temps_reel_chaine``      | ``sans_effet``          | temps réel avec des fonctions de la chaîne allumées (fiche, greffier, portes écrites, passages par code) |
| ``retour_double``          | ``sans_effet``          | plus d'une étape marquée « étape de retour »                                                            |
| ``retour_non_redige``      | ``sans_effet``          | l'étape de retour est encore « à rédiger » : le code ne l'utilise pas                                   |
| ``annonce_jamais_dite``    | ``sans_effet``          | des horaires sont réglés et l'accueil ne porte pas l'annonce d'ouverture                                |
| ``cumul_de_phrases``       | ``sans_effet``          | une phrase de transition ET la première réplique de l'étape d'arrivée se suivent                        |
| ``impasse_sans_issue``     | ``sortie_d_impasse``    | la sortie d'impasse est allumée et son « Ensuite » ne mène nulle part (bloque par défaut, 05 § 2)       |
| ``deux_webhooks``          | ``deux_webhooks``       | un webhook de Dograh actif ET le module webhook .mark choisi par l'agent                                |

Les corrections sont des identifiants (``Correction.id``) : ``appliquer`` les joue sur une COPIE de la définition et des
réglages, et rend ce qui change. Le serveur n'applique qu'une correction que le constat propose (jamais un identifiant libre).
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

CONTROLE_SANS_EFFET = "sans_effet"
CONTROLE_IMPASSE = "sortie_d_impasse"
CONTROLE_WEBHOOKS = "deux_webhooks"
CONTROLES_DES_CONSTATS = (CONTROLE_SANS_EFFET, CONTROLE_IMPASSE, CONTROLE_WEBHOOKS)

CLE_FICHE = "fiche_au_fil_de_leau"
CLE_CHAMPS = "fiche_champs"
CLE_PORTES = "portes_dans_la_reponse"
CLE_MODE_DE_NOTE = "fiche_mode_de_note"
CLE_IMPASSE = "moteur_sortie_d_impasse"
CLE_HORAIRES = "horaires_ouverture"
CLE_APRES_APPEL = "apres_appel"
JETON_ANNONCE = "annonce_ouverture"
VARIABLE_ANNONCE = "{{initial_context.annonce_ouverture}}"

QUI_AGENT = "agent"


@dataclass
class Correction:
    id: str
    noeud_id: str | None = None
    liaison_id: str | None = None
    # Le nom de l'étape qu'elle vise, pour que l'écran l'écrive (« Garder « Rappel » »).
    nom: str | None = None


@dataclass
class Constat:
    cle: str
    controle: str
    noeud_id: str | None = None
    liaison_id: str | None = None
    # Les noms que le texte de l'écran cite (étape, liaison, fonctions allumées).
    noms: list[str] = field(default_factory=list)
    corrections: list[Correction] = field(default_factory=list)

    def en_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def identifiant(self) -> str:
        return ":".join(p for p in (self.cle, self.noeud_id, self.liaison_id) if p)

    def message(self) -> str:
        """La phrase anglaise des garde-fous (le texte bilingue de l'écran vient de ``cle``)."""
        return MESSAGES.get(self.cle, self.cle) + (f" ({', '.join(self.noms)})" if self.noms else "")


MESSAGES = {
    "condition_sur_le_modele": "A rule on the record is written on a link whose step lets the model decide: it never plays.",
    "collecte_sans_fiche": "The step passes through the record, and the record is not filled during the call: it never passes.",
    "portes_sans_fiche": "Transitions are written in the reply, and the record is off: the code cannot read them.",
    "temps_reel_chaine": "Realtime mode, with functions of the chain on: they have no effect.",
    "retour_double": "Two steps are marked as the return step: the code does not know where to bring the call back.",
    "retour_non_redige": "The return step is not written yet: the code ignores it.",
    "annonce_jamais_dite": "Opening hours are set, and the start does not carry the opening announcement: it is never said.",
    "cumul_de_phrases": "A transition sentence and the first reply of the arrival step follow each other.",
    "impasse_sans_issue": "The dead-end exit is on, and its « Then » leads nowhere.",
    "deux_webhooks": "Two webhooks are on after the call: Dograh's and the .mark module.",
}


# --- lecture de la définition ----------------------------------------------------------------------------------------------


def _noeuds(definition: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    noeuds = (definition or {}).get("nodes")
    return [n for n in noeuds if isinstance(n, dict)] if isinstance(noeuds, list) else []


def _liaisons(definition: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    liaisons = (definition or {}).get("edges")
    return [e for e in liaisons if isinstance(e, dict)] if isinstance(liaisons, list) else []


def _donnees(element: Mapping[str, Any]) -> dict[str, Any]:
    donnees = element.get("data")
    return donnees if isinstance(donnees, dict) else {}


def _nom(noeud: Mapping[str, Any]) -> str:
    return str(_donnees(noeud).get("name") or noeud.get("id") or "")


def _est_le_depart(noeud: Mapping[str, Any]) -> bool:
    return noeud.get("type") == "startCall" or _donnees(noeud).get("is_start") is True


def _est_une_fin(noeud: Mapping[str, Any]) -> bool:
    return noeud.get("type") == "endCall" or _donnees(noeud).get("is_end") is True


def _qui_decide(noeud: Mapping[str, Any]) -> str:
    valeur = _donnees(noeud).get("qui_decide_du_passage")
    return valeur if valeur in ("collecte", "choix", "libre") else QUI_AGENT


def _condition_ecrite(liaison: Mapping[str, Any]) -> bool:
    condition = _donnees(liaison).get("condition_sur_la_fiche")
    if not isinstance(condition, Mapping):
        return False
    return bool(condition.get("etape_complete")) or bool(str(condition.get("champ") or "").strip())


def fiche_active(configurations: Mapping[str, Any] | None) -> bool:
    """Le code lit la fiche : l'interrupteur est allumé ET elle a au moins un champ (``ReglagesFiche.depuis``)."""
    c = configurations or {}
    return bool(c.get(CLE_FICHE)) and bool(c.get(CLE_CHAMPS))


def _etape_de_retour_redigee(noeud: Mapping[str, Any]) -> bool:
    from api.services.groupe.passations import est_a_rediger

    return not est_a_rediger(_donnees(noeud).get("prompt"))


# --- les constats ------------------------------------------------------------------------------------------------------------


def _condition_sur_le_modele(definition: Mapping[str, Any]) -> list[Constat]:
    noeuds = {n.get("id"): n for n in _noeuds(definition)}
    constats: list[Constat] = []
    for liaison in _liaisons(definition):
        source = noeuds.get(liaison.get("source"))
        if source is None or not _condition_ecrite(liaison) or _qui_decide(source) != QUI_AGENT:
            continue
        constats.append(
            Constat(
                "condition_sur_le_modele",
                CONTROLE_SANS_EFFET,
                noeud_id=source.get("id"),
                liaison_id=liaison.get("id"),
                noms=[_nom(source), str(_donnees(liaison).get("label") or "")],
                corrections=[
                    Correction("faire_decider_la_fiche", noeud_id=source.get("id"), nom=_nom(source)),
                    Correction("retirer_la_condition", liaison_id=liaison.get("id")),
                ],
            )
        )
    return constats


def _collecte_sans_fiche(definition: Mapping[str, Any], configurations: Mapping[str, Any], temps_reel: bool) -> list[Constat]:
    if temps_reel or fiche_active(configurations):
        return []  # le temps réel a son propre cas ; une fiche active lit tout
    peut_allumer = bool(configurations.get(CLE_CHAMPS))
    constats: list[Constat] = []
    for noeud in _noeuds(definition):
        if _qui_decide(noeud) == QUI_AGENT:
            continue
        corrections = [Correction("allumer_la_fiche")] if peut_allumer else []
        corrections.append(Correction("faire_decider_le_modele", noeud_id=noeud.get("id"), nom=_nom(noeud)))
        constats.append(
            Constat("collecte_sans_fiche", CONTROLE_SANS_EFFET, noeud_id=noeud.get("id"), noms=[_nom(noeud)], corrections=corrections)
        )
    return constats


def _portes_sans_fiche(configurations: Mapping[str, Any], temps_reel: bool) -> list[Constat]:
    if temps_reel or not configurations.get(CLE_PORTES) or fiche_active(configurations):
        return []
    corrections = [Correction("allumer_la_fiche")] if configurations.get(CLE_CHAMPS) else []
    corrections.append(Correction("rappeler_la_porte"))
    return [Constat("portes_sans_fiche", CONTROLE_SANS_EFFET, corrections=corrections)]


def _temps_reel_chaine(definition: Mapping[str, Any], configurations: Mapping[str, Any], temps_reel: bool) -> list[Constat]:
    if not temps_reel:
        return []
    allumees: list[str] = []
    if configurations.get(CLE_FICHE):
        allumees.append(CLE_FICHE)
    if configurations.get(CLE_PORTES):
        allumees.append(CLE_PORTES)
    if configurations.get(CLE_MODE_DE_NOTE) == "greffier":
        allumees.append("greffier")
    if any(_qui_decide(n) != QUI_AGENT or _donnees(n).get("arbitre") is True for n in _noeuds(definition)):
        allumees.append("passages")
    if not allumees:
        return []
    return [Constat("temps_reel_chaine", CONTROLE_SANS_EFFET, noms=allumees, corrections=[Correction("eteindre_la_chaine")])]


def _retours(definition: Mapping[str, Any]) -> list[Constat]:
    marques = [n for n in _noeuds(definition) if _donnees(n).get("etape_de_retour") is True and not _est_une_fin(n)]
    constats: list[Constat] = []
    if len(marques) > 1:
        constats.append(
            Constat(
                "retour_double",
                CONTROLE_SANS_EFFET,
                noms=[_nom(n) for n in marques],
                corrections=[Correction("garder_le_retour", noeud_id=n.get("id"), nom=_nom(n)) for n in marques[:2]],
            )
        )
    for noeud in marques:
        if not _etape_de_retour_redigee(noeud):
            constats.append(
                Constat(
                    "retour_non_redige",
                    CONTROLE_SANS_EFFET,
                    noeud_id=noeud.get("id"),
                    noms=[_nom(noeud)],
                    corrections=[Correction("retirer_le_retour", noeud_id=noeud.get("id"), nom=_nom(noeud))],
                )
            )
    return constats


def _annonce_jamais_dite(definition: Mapping[str, Any], configurations: Mapping[str, Any]) -> list[Constat]:
    horaires = configurations.get(CLE_HORAIRES)
    if not horaires:
        return []
    depart = next((n for n in _noeuds(definition) if _est_le_depart(n)), None)
    if depart is None:
        return []
    donnees = _donnees(depart)
    textes = f"{donnees.get('greeting') or ''}\n{donnees.get('prompt') or ''}"
    if JETON_ANNONCE in textes:
        return []
    # La phrase d'accueil enregistrée (audio) ne porte pas de variable : la correction ne s'offre que pour un texte.
    corrections = (
        [Correction("ajouter_l_annonce", noeud_id=depart.get("id"), nom=_nom(depart))]
        if donnees.get("greeting_type") in (None, "", "text") and str(donnees.get("greeting") or "").strip()
        else []
    )
    return [Constat("annonce_jamais_dite", CONTROLE_SANS_EFFET, noeud_id=depart.get("id"), noms=[_nom(depart)], corrections=corrections)]


def _cumul_de_phrases(definition: Mapping[str, Any]) -> list[Constat]:
    noeuds = {n.get("id"): n for n in _noeuds(definition)}
    constats: list[Constat] = []
    for liaison in _liaisons(definition):
        donnees = _donnees(liaison)
        dite = str(donnees.get("transition_speech") or "").strip() and donnees.get("transition_speech_type") in (None, "", "text")
        arrivee = noeuds.get(liaison.get("target"))
        if not dite or arrivee is None:
            continue
        if not str(_donnees(arrivee).get("premiere_replique") or "").strip():
            continue
        constats.append(
            Constat(
                "cumul_de_phrases",
                CONTROLE_SANS_EFFET,
                noeud_id=arrivee.get("id"),
                liaison_id=liaison.get("id"),
                noms=[_nom(arrivee), str(donnees.get("label") or "")],
                corrections=[Correction("retirer_la_phrase_de_transition", liaison_id=liaison.get("id"))],
            )
        )
    return constats


def _impasse(
    definition: Mapping[str, Any], configurations: Mapping[str, Any], *, specialiste: bool
) -> list[Constat]:
    """La sortie d'impasse est allumée, la phrase du motif est dite, et son « Ensuite » ne mène nulle part (05 § 2).

    Un collègue rend la main à son principal (il mène quelque part). Un agent seul ou un accueil : raccrocher et transférer
    mènent quelque part ; « le modèle garde la main » non ; « rendre la main » et « aller à une étape » mènent à l'étape de retour
    rédigée, ou à l'étape choisie quand elle existe dans le graphe et n'est pas une fin."""
    if configurations.get(CLE_IMPASSE) is False or specialiste:
        return []
    from api.services.phrases.catalogue import IMPASSE
    from api.services.phrases.regles import resoudre

    phrase = resoudre(IMPASSE, reglages_agent=configurations, reglages_principal=configurations)
    if phrase is None or not phrase.active:
        return []  # le motif éteint : le code ne dit rien et ne change pas d'étape, le modèle garde la main par choix
    action = phrase.action_de_sortie
    if action in ("raccrocher", "transferer"):
        return []
    noeuds = {n.get("id"): n for n in _noeuds(definition)}
    if action == "aller_a_une_etape":
        cible = noeuds.get(str(phrase.ensuite.destination or "").strip())
        if cible is not None and not _est_une_fin(cible):
            return []
    if action in ("rendre_la_main", "aller_a_une_etape"):
        if any(
            _donnees(n).get("etape_de_retour") is True and not _est_une_fin(n) and _etape_de_retour_redigee(n)
            for n in noeuds.values()
        ):
            return []
    depart = next((n for n in noeuds.values() if _est_le_depart(n)), None)
    corrections = []
    if depart is not None:
        corrections.append(Correction("renvoyer_a_l_accueil", noeud_id=depart.get("id"), nom=_nom(depart)))
    corrections.append(Correction("eteindre_la_sortie_d_impasse"))
    return [Constat("impasse_sans_issue", CONTROLE_IMPASSE, noms=[], corrections=corrections)]


def _deux_webhooks(definition: Mapping[str, Any], configurations: Mapping[str, Any], webhook_mark_pret: bool) -> list[Constat]:
    """Un nœud webhook de Dograh actif ET le module webhook .mark choisi par l'agent (et réglé dans l'organisation)."""
    modules = (configurations.get(CLE_APRES_APPEL) or {}).get("modules") if isinstance(configurations.get(CLE_APRES_APPEL), Mapping) else None
    if not webhook_mark_pret or "webhook" not in (modules or []):
        return []
    actifs = [n for n in _noeuds(definition) if n.get("type") == "webhook" and _donnees(n).get("enabled", True) is not False]
    if not actifs:
        return []
    corrections = [Correction("desactiver_le_webhook_de_dograh", noeud_id=n.get("id"), nom=_nom(n)) for n in actifs[:1]]
    corrections.append(Correction("retirer_le_module_webhook"))
    return [Constat("deux_webhooks", CONTROLE_WEBHOOKS, noeud_id=actifs[0].get("id"), noms=[_nom(n) for n in actifs], corrections=corrections)]


def evaluer(
    definition: Mapping[str, Any] | None,
    configurations: Mapping[str, Any] | None,
    *,
    temps_reel: bool = False,
    specialiste: bool = False,
    webhook_mark_pret: bool = False,
) -> list[Constat]:
    """Tous les constats de l'agent. Pure, ne lève jamais : un graphe ou un réglage illisible ne produit aucun constat."""
    definition = definition or {}
    configurations = configurations or {}
    constats: list[Constat] = []
    for calcul in (
        lambda: _condition_sur_le_modele(definition),
        lambda: _collecte_sans_fiche(definition, configurations, temps_reel),
        lambda: _portes_sans_fiche(configurations, temps_reel),
        lambda: _temps_reel_chaine(definition, configurations, temps_reel),
        lambda: _retours(definition),
        lambda: _annonce_jamais_dite(definition, configurations),
        lambda: _cumul_de_phrases(definition),
        lambda: _impasse(definition, configurations, specialiste=specialiste),
        lambda: _deux_webhooks(definition, configurations, webhook_mark_pret),
    ):
        try:
            constats.extend(calcul())
        except Exception:  # noqa: BLE001 -- un cas illisible ne fait pas tomber les autres
            continue
    return constats


# --- les corrections en un clic ----------------------------------------------------------------------------------------------


class CorrectionRefusee(Exception):
    pass


def _noeud_de(definition: dict[str, Any], identifiant: str | None) -> dict[str, Any]:
    noeud = next((n for n in _noeuds(definition) if n.get("id") == identifiant), None)
    if noeud is None:
        raise CorrectionRefusee("The step is not in the draft any more.")
    if not isinstance(noeud.get("data"), dict):
        noeud["data"] = {}
    return noeud


def _liaison_de(definition: dict[str, Any], identifiant: str | None) -> dict[str, Any]:
    liaison = next((e for e in _liaisons(definition) if e.get("id") == identifiant), None)
    if liaison is None:
        raise CorrectionRefusee("The link is not in the draft any more.")
    if not isinstance(liaison.get("data"), dict):
        liaison["data"] = {}
    return liaison


def appliquer(
    correction: Correction, definition: Mapping[str, Any], configurations: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Joue la correction sur des COPIES. Rend ``(définition, réglages_a_ecrire)`` : la définition entière, et seulement les
    clés de réglage qui changent. Les corrections qui passent par une règle de phrase (``renvoyer_a_l_accueil``) sont jouées par le
    service (elles ont besoin de l'organisation) : elles ne changent ici ni la définition ni les réglages."""
    nouvelle = copy.deepcopy(dict(definition))
    ecrits: dict[str, Any] = {}
    c = correction.id
    if c == "faire_decider_la_fiche":
        _noeud_de(nouvelle, correction.noeud_id)["data"]["qui_decide_du_passage"] = "choix"
    elif c == "faire_decider_le_modele":
        donnees = _noeud_de(nouvelle, correction.noeud_id)["data"]
        donnees.pop("qui_decide_du_passage", None)
        donnees.pop("moment_du_passage", None)
        donnees.pop("arbitre", None)
    elif c == "retirer_la_condition":
        _liaison_de(nouvelle, correction.liaison_id)["data"].pop("condition_sur_la_fiche", None)
    elif c == "retirer_la_phrase_de_transition":
        donnees = _liaison_de(nouvelle, correction.liaison_id)["data"]
        for cle in ("transition_speech", "transition_speech_type", "transition_speech_recording_id"):
            donnees.pop(cle, None)
    elif c == "allumer_la_fiche":
        ecrits[CLE_FICHE] = True
    elif c == "rappeler_la_porte":
        ecrits[CLE_PORTES] = False
    elif c == "eteindre_la_chaine":
        ecrits.update({CLE_FICHE: False, CLE_PORTES: False})
        if configurations.get(CLE_MODE_DE_NOTE) == "greffier":
            ecrits[CLE_MODE_DE_NOTE] = "outil"
        for noeud in _noeuds(nouvelle):
            donnees = _donnees(noeud)
            for cle in ("qui_decide_du_passage", "moment_du_passage", "arbitre"):
                donnees.pop(cle, None)
    elif c == "garder_le_retour":
        for noeud in _noeuds(nouvelle):
            if noeud.get("id") != correction.noeud_id and _donnees(noeud).get("etape_de_retour") is True:
                _donnees(noeud)["etape_de_retour"] = False
    elif c == "retirer_le_retour":
        _noeud_de(nouvelle, correction.noeud_id)["data"]["etape_de_retour"] = False
    elif c == "ajouter_l_annonce":
        donnees = _noeud_de(nouvelle, correction.noeud_id)["data"]
        if JETON_ANNONCE not in str(donnees.get("greeting") or ""):
            donnees["greeting"] = f"{VARIABLE_ANNONCE}{donnees.get('greeting') or ''}"
    elif c == "desactiver_le_webhook_de_dograh":
        _noeud_de(nouvelle, correction.noeud_id)["data"]["enabled"] = False
    elif c == "retirer_le_module_webhook":
        brut = configurations.get(CLE_APRES_APPEL)
        bloc = dict(brut) if isinstance(brut, Mapping) else {}
        bloc["modules"] = [m for m in (bloc.get("modules") or []) if m != "webhook"]
        ecrits[CLE_APRES_APPEL] = bloc
    elif c == "eteindre_la_sortie_d_impasse":
        ecrits[CLE_IMPASSE] = False
    elif c == "renvoyer_a_l_accueil":
        pass  # règle de phrase : jouée par le service
    else:
        raise CorrectionRefusee("Unknown fix.")
    return nouvelle, ecrits
