"""[.mark] Partie 3, L3e sous-lot 2 : l'annonce « vous parlez à une IA », dite en tête de chaque appel et IMPOSSIBLE À ÉTEINDRE.

Une seule phrase, celle du motif verrouillé ``annonce_ia`` du catalogue des phrases (``phrases/catalogue.py``) : l'agent peut en changer
le TEXTE (règle du thème Phrases), jamais l'éteindre ni la vider (``phrases/regles.resoudre`` rend le texte par défaut). Le moteur est le
même au téléphone, dans le widget, en campagne et au clavier : le point d'entrée est ``PipecatEngine.queue_node_opening``, par où passe
TOUTE ouverture d'appel (démarrage, répondeur supervisé, agent reçu par passation).

* une fois par appel : l'ouverture d'un agent reçu par transfert ne la redit pas ;
* un agent qui annonce déjà (son accueil en texte dit qu'il est un assistant virtuel, une IA…) ne l'entend pas deux fois ;
* accueil en texte : la phrase le précède dans la même parole (une seule lecture, une seule réplique) ; accueil enregistré ou ouverture
  par le modèle : parole à part, jamais ajoutée à l'historique du modèle (une ouverture ne part jamais sur un message de l'assistant) ;
* voix temps réel sans accueil en texte : l'ouverture est produite par le fournisseur, la phrase ne peut pas être imposée mot pour mot
  (reste noté dans ``18-a-exposer.md``).

⛔ Libellé PROVISOIRE : il doit être confirmé sur le texte officiel (AI Act art. 50) avant d'être figé. ⛔ Ne lève jamais.
"""

from __future__ import annotations

import re
from typing import Any

from loguru import logger

from api.services.phrases.catalogue import ANNONCE_IA
from api.services.phrases.regles import resoudre

# Ce qui, dans un accueil, dit déjà à l'appelant qu'il parle à une machine.
DEJA_ANNONCE = re.compile(
    r"intelligence artificielle|assistante? virtuel|agent virtuel|assistante? num[ée]rique|voix de synth[èe]se|(?-i:\bIA\b)|(?-i:\bAI\b)|virtual assistant|artificial intelligence|\brobot\b",
    re.IGNORECASE,
)
FAIT = "_annonce_ia_faite"


def texte_de_l_annonce(reglages_agent: Any, reglages_principal: Any = None) -> str:
    """Le texte en vigueur : celui de la règle de l'agent (ou du groupe), sinon le défaut du catalogue. Jamais vide."""
    phrase = resoudre(ANNONCE_IA, reglages_agent=reglages_agent, reglages_principal=reglages_principal)
    return phrase.variantes[0].strip() if phrase is not None and phrase.variantes else ""


def mentionne_deja(texte: str | None) -> bool:
    return bool(texte and DEJA_ANNONCE.search(texte))


def a_dire(moteur: Any, accueil: tuple[str, str | None] | None) -> str | None:
    """Le texte à dire à l'ouverture de cet appel, ou ``None`` (déjà dit dans l'appel, déjà annoncé par l'accueil, ou impossible à imposer).
    Marque l'annonce comme faite : un seul appel de cette fonction par ouverture réelle. Ne lève jamais."""
    try:
        if getattr(moteur, FAIT, False):
            return None
        setattr(moteur, FAIT, True)
        agent = moteur.active_agent
        texte_accueil = accueil[1] if accueil and accueil[0] == "text" else None
        if mentionne_deja(texte_accueil):
            return None
        if getattr(moteur, "_is_realtime", False) and not texte_accueil:
            logger.warning("[annonce-ia] voix temps réel sans accueil en texte : annonce non imposée")
            return None
        return texte_de_l_annonce(getattr(agent, "reglages", None), getattr(moteur, "reglages_appel", None)) or None
    except Exception as erreur:  # noqa: BLE001 -- jamais à la place de l'appel
        logger.warning(f"[annonce-ia] annonce non préparée : {erreur!r}")
        return None


def avec_l_accueil(annonce: str, accueil: tuple[str, str | None] | None) -> tuple[str, str | None] | None:
    """L'accueil en texte précédé de l'annonce (une seule parole) ; ``None`` quand l'annonce doit se dire à part."""
    if accueil and accueil[0] == "text" and accueil[1]:
        return ("text", f"{annonce} {accueil[1]}")
    return None


async def dire_a_part(moteur: Any, annonce: str, *, mute_user: bool = False) -> None:
    """L'annonce seule, avant un accueil enregistré ou l'ouverture du modèle. Hors historique du modèle, dans la transcription."""
    try:
        await moteur.queue_speech(annonce, append_to_context=False, persist_to_logs=True, mute_user=mute_user)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[annonce-ia] annonce non dite : {erreur!r}")
