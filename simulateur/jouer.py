"""[.mark] Le lanceur de l'appelant simulé (chantier langwatch-et-fenetre-du-run, lot 3, L19).

Tourne dans le **second environnement Python** de l'image (``/opt/venv-simulateur``), jamais dans
celui de l'API : ``langwatch-scenario`` exige ``openai`` 2.x, l'API et Pipecat sont sur 3.x.
La tâche de fond de l'API le lance par sous-processus :

- **entrée** : un objet JSON sur l'entrée standard (adresse de l'entrée audio, scénario, modèles,
  voix) ; voir ``lire_l_entree`` ;
- **clés** : par l'environnement du sous-processus seulement (``SIMULATEUR_CLE_MODELE``,
  ``ELEVENLABS_API_KEY``), jamais en argument ni sur disque ;
- **sortie** : une ligne ``MARK_VERDICT <json>`` sur la sortie standard (Scenario y écrit aussi).

Rien ne part chez LangWatch : la tâche ne transmet aucune variable ``LANGWATCH_*``.
Ce fichier n'importe rien de l'API : il ne connaît que Scenario.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

MARQUE = "MARK_VERDICT "
CLE_MODELE = "SIMULATEUR_CLE_MODELE"


class EntreeInvalide(ValueError):
    pass


def _texte(valeur: Any, champ: str) -> str:
    if not isinstance(valeur, str) or not valeur.strip():
        raise EntreeInvalide(f"{champ} manquant")
    return valeur.strip()


def lire_l_entree(brut: str) -> dict:
    """Valide l'entrée et rend une forme sûre (pas de clé dedans : elles passent par l'environnement)."""
    try:
        entree = json.loads(brut)
    except json.JSONDecodeError as e:
        raise EntreeInvalide(f"JSON illisible : {e}") from e
    if not isinstance(entree, dict):
        raise EntreeInvalide("objet JSON attendu")
    scenario = entree.get("scenario") or {}
    appelant = entree.get("appelant") or {}
    juge = entree.get("juge") or {}
    criteres = [
        c.strip()
        for c in scenario.get("criteres") or []
        if isinstance(c, str) and c.strip()
    ]
    if not criteres:
        raise EntreeInvalide("scenario.criteres vide")
    return {
        "adresse": _texte(entree.get("adresse"), "adresse"),
        "nom": _texte(scenario.get("nom"), "scenario.nom"),
        "description": _texte(scenario.get("description"), "scenario.description"),
        "criteres": criteres,
        "tours_max": int(scenario.get("tours_max") or 12),
        "appelant": {
            "modele": _texte(appelant.get("modele"), "appelant.modele"),
            "consigne": _texte(appelant.get("consigne"), "appelant.consigne"),
            "voix": _texte(appelant.get("voix"), "appelant.voix"),
            "temperature": float(appelant.get("temperature") or 0.0),
            "coupe_la_parole": float(appelant.get("coupe_la_parole") or 0.0),
        },
        "juge": {
            "modele": _texte(juge.get("modele"), "juge.modele"),
            "consigne": juge.get("consigne") or None,
        },
    }


def _contenu(message: Any) -> str:
    contenu = message.get("content") if isinstance(message, dict) else None
    if isinstance(contenu, str):
        return contenu
    if isinstance(contenu, list):
        return " ".join(
            p.get("text", "")
            for p in contenu
            if isinstance(p, dict) and p.get("type") == "text"
        ).strip()
    return ""


def verdict(resultat: Any) -> dict:
    """La forme que lit l'API : verdict, critères, raisonnement, conversation en texte."""
    return {
        "success": bool(getattr(resultat, "success", False)),
        "reasoning": getattr(resultat, "reasoning", None),
        "passed_criteria": list(getattr(resultat, "passed_criteria", []) or []),
        "failed_criteria": list(getattr(resultat, "failed_criteria", []) or []),
        "total_time": getattr(resultat, "total_time", None),
        "agent_time": getattr(resultat, "agent_time", None),
        "messages": [
            {"role": m.get("role"), "content": _contenu(m)}
            for m in getattr(resultat, "messages", []) or []
            if isinstance(m, dict) and m.get("role") in ("user", "assistant")
        ],
    }


async def jouer(entree: dict) -> dict:
    import scenario
    from scenario import ElevenLabsSTTProvider, PipecatAgentAdapter

    cle = os.environ.get(CLE_MODELE) or None
    # La transcription de l'agent (pour l'appelant et le juge) passe par la même clé ElevenLabs
    # que la voix de l'appelant : aucune clé OpenAI.
    scenario.set_stt_provider(ElevenLabsSTTProvider())
    appelant = entree["appelant"]
    juge = entree["juge"]
    resultat = await scenario.run(
        name=entree["nom"],
        description=entree["description"],
        agents=[
            PipecatAgentAdapter(url=entree["adresse"]),
            scenario.UserSimulatorAgent(
                model=appelant["modele"],
                api_key=cle,
                system_prompt=appelant["consigne"],
                voice=appelant["voix"],
                temperature=appelant["temperature"],
                interrupt_probability=appelant["coupe_la_parole"],
            ),
            scenario.JudgeAgent(
                criteria=entree["criteres"],
                model=juge["modele"],
                api_key=cle,
                system_prompt=juge["consigne"],
            ),
        ],
        max_turns=entree["tours_max"],
        verbose=False,
    )
    return verdict(resultat)


def main() -> int:
    try:
        entree = lire_l_entree(sys.stdin.read())
    except EntreeInvalide as e:
        print(MARQUE + json.dumps({"error": f"invalid input: {e}"}), flush=True)
        return 2
    try:
        sortie = asyncio.run(jouer(entree))
    except Exception as e:  # le verdict doit toujours sortir, même en échec
        sortie = {"error": f"{type(e).__name__}: {e}"}
    print(MARQUE + json.dumps(sortie, ensure_ascii=False), flush=True)
    return 0 if "error" not in sortie else 1


if __name__ == "__main__":
    sys.exit(main())
