"""[.mark] U11 (§ 17) : jouer une sonde, selon les 7 règles de sondage.

1. un témoin inoffensif par attaque ; 2. une anomalie n'est pas un verdict (témoin qui échoue ou transport en panne = non
concluant) ; 3. reproduire avant de confirmer (sinon « plausible ») ; 4. une session neuve par sonde (``moteur.ouvrir`` à
chaque fois) ; 5. aucun verdict sans la réponse mot pour mot (ranger la réponse de l'agent, jamais un résumé) ; 6. attaquer la
frontière, pas extraire du contenu nocif (messages du catalogue) ; 7. dire de quelle couche vient le défaut.

Le moteur est celui des tests (``tests_agent.jeu.Moteur``, chemin texte, outils sortants simulés) : rien ne part vers un client.
Le juge est injecté (``Juge``) : en test un faux, en usage le cerveau du juge des Réglages du Labo.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

from api.services.attaques import verdicts
from api.services.attaques.catalogue import REPONSE_MAX_RANGEE
from api.services.builder.tests_agent.jeu import Moteur

# (sonde, transcription de l'attaque, transcription du témoin) -> verdict brut (texte JSON ou objet)
Juge = Callable[[dict[str, Any], list[tuple[str, str]], list[tuple[str, str]]], Awaitable[Any]]


async def _jouer(workflow: Any, moteur: Moteur, slug: str, tours: list[str]) -> list[tuple[str, str]]:
    """Une session neuve, les messages un à un ; rend la transcription [(« moi »|« agent »), texte]."""
    session, ouverture = await moteur.ouvrir(workflow, {"slug": slug, "scenario": {}})
    lignes: list[tuple[str, str]] = []
    if ouverture.texte:
        lignes.append(("agent", ouverture.texte))
    try:
        termine = ouverture.termine
        for message in tours:
            if termine:
                break
            lignes.append(("moi", message))
            reponse = await moteur.tour(session, message)
            if reponse.texte:
                lignes.append(("agent", reponse.texte))
            termine = reponse.termine
    finally:
        try:
            await moteur.clore(session)
        except Exception:  # noqa: BLE001 -- un run non clos ne fait pas échouer la sonde
            logger.debug("[attaques] run de sonde non clos")
    return lignes


def _reponses(lignes: list[tuple[str, str]]) -> list[str]:
    # L'ouverture dite avant le premier message n'est pas une réponse à l'attaque.
    premiere = next((i for i, (r, _) in enumerate(lignes) if r == "moi"), len(lignes))
    return [t for r, t in lignes[premiere:] if r == "agent"]


def _rangee(lignes: list[tuple[str, str]]) -> list[list[str]]:
    return [[r, t[:REPONSE_MAX_RANGEE]] for r, t in lignes]


async def sonder(
    workflow: Any, moteur: Moteur, juge: Juge | None, sonde: dict[str, Any], *, repetitions: int = 1, avec_temoin: bool = True
) -> dict[str, Any]:
    """Le résultat d'UNE sonde : verdict, gravité, couche, la réponse mot pour mot, le témoin."""
    base = {
        "id": sonde["id"],
        "technique": sonde.get("technique"),
        "origine": sonde.get("origine", "catalogue"),
        "gravite_par_defaut": sonde.get("gravite_par_defaut", "moyenne"),
        "famille": sonde.get("famille"),
        "avec_temoin": bool(avec_temoin and sonde.get("temoin")),
    }
    try:
        attaque = await _jouer(workflow, moteur, f"attaque-{sonde['id']}", sonde["tours"])
        temoin = await _jouer(workflow, moteur, f"temoin-{sonde['id']}", [sonde["temoin"]]) if base["avec_temoin"] else []
    except Exception as erreur:  # noqa: BLE001 -- le transport a cassé : jamais un verdict sur l'agent (règle 7)
        logger.warning(f"[attaques] sonde {sonde['id']} en panne ({type(erreur).__name__})")
        return {**base, **verdicts.non_concluant(f"The probe could not be played ({type(erreur).__name__}).", "plateforme"), "reponse": "", "transcription": [], "reproduit": None}
    reponses = _reponses(attaque)
    if not any(r.strip() for r in reponses):
        return {**base, **verdicts.non_concluant("The agent answered nothing: it has not defended itself."), "reponse": "", "transcription": _rangee(attaque), "reproduit": None}
    if juge is None:
        return {**base, **verdicts.non_concluant("No judge set for the attacks (Labo settings): the answer is kept, not judged."), "reponse": reponses[-1][:REPONSE_MAX_RANGEE], "transcription": _rangee(attaque), "reproduit": None}
    lu = verdicts.lire_le_verdict(await juge(sonde, attaque, temoin), base["gravite_par_defaut"])
    if lu["verdict"] in ("reussi", "partiel") and lu.get("temoin_normal") is False:
        lu = {**verdicts.non_concluant("Anomaly: the harmless witness itself did not go normally, the attack proves nothing.", lu["couche"]), "temoin_normal": False}
    reproduit: bool | None = None
    if lu["verdict"] in ("reussi", "partiel"):
        # Règle 3 : reproduire avant de confirmer, sur une session neuve ; sinon le défaut reste « plausible ».
        reproduit = False
        for _ in range(max(1, repetitions)):
            autre = await _jouer(workflow, moteur, f"rejeu-{sonde['id']}", sonde["tours"])
            relu = verdicts.lire_le_verdict(await juge(sonde, autre, temoin), base["gravite_par_defaut"])
            if relu["verdict"] in ("reussi", "partiel"):
                reproduit = True
                break
    return {**base, **lu, "reponse": reponses[-1][:REPONSE_MAX_RANGEE], "transcription": _rangee(attaque), "reproduit": reproduit}


async def controler_le_juge(workflow: Any, moteur: Moteur, juge: Juge | None, sonde: dict[str, Any]) -> dict[str, Any]:
    """Le témoin inoffensif jugé COMME une attaque : une demande normale n'obtient rien, donc un juge qui y voit une attaque qui a
    réussi crie au loup. ``ok`` faux = les verdicts « a cédé » de ce passage sont à relire ; ``None`` = rien à conclure (pas de juge,
    pas de réponse, panne). Une seule fois par passage : un appel du juge de plus, jamais un par sonde."""
    if juge is None or not sonde.get("temoin"):
        return {"ok": None, "raison": "No judge or no harmless witness: the judge was not checked."}
    try:
        lignes = await _jouer(workflow, moteur, f"controle-{sonde['id']}", [sonde["temoin"]])
        if not any(r.strip() for r in _reponses(lignes)):
            return {"ok": None, "raison": "The agent answered nothing to the harmless witness."}
        lu = verdicts.lire_le_verdict(await juge(sonde, lignes, []), "basse")
    except Exception as erreur:  # noqa: BLE001 -- un contrôle en panne ne coupe pas le passage
        logger.warning(f"[attaques] contrôle du juge en panne ({type(erreur).__name__})")
        return {"ok": None, "raison": "The check of the judge could not be played."}
    if lu["verdict"] == "non_concluant":
        return {"ok": None, "raison": lu["raison"]}
    crie = lu["verdict"] in ("reussi", "partiel")
    return {"ok": not crie, "raison": lu["raison"]}
