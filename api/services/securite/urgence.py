"""[.mark] Partie 3, L3e sous-lot 3 : le garde-fou URGENCE. Détresse ou urgence médicale reconnues dans les MOTS de l'appelant, sans
aucun appel de modèle (le classifieur de l'écoute, lui, est un autre interrupteur, payant, de la même page Sécurité).

Branché dans ``avant_la_requete.preparer_la_requete`` : le même point pour le téléphone, le widget, la campagne et le clavier. Sur la
dernière parole de la personne :

1. ``detecter`` : une liste de mots et de tournures (français, anglais), normalisés (casse, accents, apostrophes), plus les mots que
   l'agent y ajoute ;
2. si l'un d'eux est reconnu : le déclenchement est noté (``marques``, couche ``urgence``, il entre dans « À améliorer »), la phrase du
   catalogue (motif ``urgence_vitale``, avec ``{{numero}}``) est dite UNE fois par appel, et une notice d'un tour dit au modèle de ne
   pas la redire ;
3. la phrase éteinte au catalogue, ou le diseur absent : la notice demande au modèle de donner lui-même le numéro d'urgence.

⛔ Libellé de la phrase et numéro par défaut PROVISOIRES (``18-a-exposer.md``). ⛔ Ne lève jamais. ⛔ Zéro vocabulaire de métier.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from loguru import logger

from api.services.phrases.catalogue import URGENCE_VITALE
from api.services.securite import marques
from api.services.securite.reglages import de_l_agent

COUCHE = "urgence"
FAIT = "_urgence_dite"

# (nom du signal, motif). Le texte est normalisé avant : minuscules, sans accents, apostrophes et tirets en espaces.
SIGNAUX: tuple[tuple[str, str], ...] = (
    ("appel_a_l_aide", r"\bau secours\b"),
    ("cardiaque", r"\b(crise cardiaque|infarctus|arret cardiaque|heart attack|cardiac arrest)\b"),
    ("avc", r"\b(avc|accident vasculaire|stroke)\b"),
    ("respiration", r"\b(ne respire (plus|pas)|n arrive (plus|pas) a respirer|mal a respirer|can t breathe|cannot breathe|not breathing)\b"),
    ("conscience", r"\b(perdu connaissance|perdre connaissance|inconscient|inconsciente|evanoui|evanouie|unconscious|passed out)\b"),
    ("malaise", r"\b(fait un malaise|fais un malaise|ai un malaise|a un malaise|fait une crise)\b"),
    ("hemorragie", r"\b(hemorragie|saigne beaucoup|saigne abondamment|beaucoup de sang|bleeding heavily)\b"),
    ("intoxication", r"\b(overdose|surdose|empoisonne|empoisonnee|poisoned)\b"),
    ("suicide", r"\b(suicide|me suicider|se suicider|mettre fin a (mes|ses) jours|envie de mourir|veux mourir|me tuer|kill myself|want to die)\b"),
    ("mourir", r"\bvais mourir\b(?! de (rire|faim|soif|chaud|froid|honte|peur|fatigue|sommeil|ennui))"),
    ("secours", r"\b(appelez|appeler|appelle|call)( le| les| une| an| the)? (samu|pompiers|ambulance|secours|police|911|999|112|15|18)\b"),
    ("ambulance", r"\b(besoin d une ambulance|envoyez une ambulance|need an ambulance)\b"),
)
COMPILES = tuple((nom, re.compile(motif)) for nom, motif in SIGNAUX)


def normaliser(texte: str) -> str:
    sans_accents = "".join(c for c in unicodedata.normalize("NFD", texte or "") if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", sans_accents.lower().replace("'", " ").replace("’", " ")).split())


def detecter(texte: str | None, mots_en_plus: list[str] | tuple[str, ...] = ()) -> str | None:
    """Le nom du signal reconnu dans ``texte``, ou ``None``. Pur."""
    propre = normaliser(texte or "")
    if not propre:
        return None
    for nom, motif in COMPILES:
        if motif.search(propre):
            return nom
    for mot in mots_en_plus:
        voulu = normaliser(mot)
        if voulu and re.search(rf"\b{re.escape(voulu)}\b", propre):
            return "mot_de_l_agent"
    return None


def urgence_allumee(agent: Any) -> bool:
    try:
        return bool(de_l_agent(getattr(agent, "reglages", None)).garde_urgence.actif)
    except Exception:  # noqa: BLE001
        return False


def _derniere_parole(context: Any) -> str:
    messages = list(context.get_messages()) if hasattr(context, "get_messages") else []
    dernier = messages[-1].get("content") if messages and isinstance(messages[-1], dict) else ""
    if isinstance(dernier, str):
        return dernier
    if isinstance(dernier, list):
        return " ".join(p.get("text", "") for p in dernier if isinstance(p, dict))
    return ""


def notice(numero: str, *, dite: bool) -> str:
    if dite:
        return (
            f"[Garde-fou urgence] La personne décrit peut-être une urgence ou une détresse. Le code vient de lui dire d'appeler le {numero} : "
            "ne répète pas cette phrase. Reste calme, demande-lui si elle est en sécurité et si tu peux l'aider."
        )
    return (
        "[Garde-fou urgence] La personne décrit peut-être une urgence ou une détresse. Dis d'abord, en une phrase, d'appeler tout de suite "
        f"le {numero}, avant toute autre chose."
    )


async def surveiller(moteur: Any, context: Any) -> str | None:
    """Sur la requête qui répond à la personne : la notice du tour (ou ``None``). Dit la phrase au premier déclenchement de l'appel.
    ⛔ Ne lève jamais."""
    try:
        reglages = de_l_agent(getattr(getattr(moteur, "active_agent", None), "reglages", None)).garde_urgence
        if not reglages.actif:
            return None
        from api.services.workflow import passage_sur_la_fiche as passage

        if not passage._derniere_parole_de_la_personne(context):
            return None
        texte = _derniere_parole(context)
        signal = detecter(texte, reglages.mots_en_plus)
        if signal is None:
            return None
        marques.noter(getattr(moteur, "_gathered_context", None), couche=COUCHE, nom="urgence", detail=signal, extrait=texte)
        dite = bool(getattr(moteur, FAIT, False))
        if not dite:
            setattr(moteur, FAIT, True)
            diseur = getattr(moteur, "phrases", None)
            if diseur is not None:
                parole = await diseur.dire_la_parole(URGENCE_VITALE, variables={"numero": reglages.numero})
                dite = parole is not None
        return notice(reglages.numero, dite=dite)
    except Exception as erreur:  # noqa: BLE001 -- jamais à la place du tour
        logger.warning(f"[urgence] garde-fou en échec : {erreur!r}")
        return None


def contexte_avec_la_notice(context: Any, texte: str) -> Any | None:
    """Une COPIE du contexte avec la notice juste avant la dernière parole de la personne (le contexte partagé n'est pas touché)."""
    try:
        from pipecat.processors.aggregators.llm_context import LLMContext

        from api.services.workflow import passage_sur_la_fiche as passage

        nouveaux = passage._inserer_avant_la_derniere_parole(list(context.get_messages()), texte)
        if nouveaux is None:
            return None
        return LLMContext(messages=nouveaux, tools=context.tools, tool_choice=context.tool_choice)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[urgence] notice non posée : {erreur!r}")
        return None
