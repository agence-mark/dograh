"""[.mark] The summary of a call (A3): a few lines that say what happened, next to the
record's fields and never in their place.

A smaller Mistral model (``mistral-small-latest`` by default, set on screen), on the
CLIENT's key chosen in « Keys »: Mistral's rate limit is per model, the summary never
eats the agent's quota. The prompt is the lab's version 6
(``Labo-agent-vocal/agents/nuances-de-feu/08-synthese-appel.md``) made generic: the
assistant's and the company's names are settings, the fields not to repeat are the
record's own.

The base address of the API is ``MARK_MISTRAL_API_URL`` (default: Mistral's), so the
same code reaches Mistral on another host (the Scaleway migration) or a local stand-in.
"""

from __future__ import annotations

import os

import httpx

from api.schemas.apres_appel import ReglagesSynthese

URL_PAR_DEFAUT = "https://api.mistral.ai/v1"
VARIABLE_URL = "MARK_MISTRAL_API_URL"
DELAI_S = 30.0

CONSIGNE_GENERIQUE = """Tu résumes un appel téléphonique reçu par {assistant}{entreprise}, pour la personne qui va traiter la demande.

Écris UN SEUL paragraphe de trois à cinq phrases, en français, au passé. Tu ne vas jamais à la ligne. Uniquement des phrases : ni liste, ni titre, ni mise en forme.
Chaque phrase fait au plus vingt-cinq mots et se termine par un point. Tu n'emploies pas de point-virgule.

Tu commences directement par ce que la personne voulait. Tu ne racontes ni l'accueil, ni les formules d'ouverture, ni les questions de routine : elles sont les mêmes à chaque appel et n'apprennent rien au lecteur.

Ton résumé apporte ce qui ne figure nulle part ailleurs dans la fiche :
comment la demande s'est présentée et ce que {assistant_court} a répondu ;
ce que {assistant_court} a annoncé ou promis à la personne ;
ce qui est resté sans réponse, ou ce que {assistant_court} n'a pas su traiter ;
ce que la personne a dit et qui n'entre dans aucune case de la fiche ;
s'il y a eu transfert vers un humain, pourquoi.

Tu appelles l'assistant vocal « {assistant_court} ». Tu désignes la personne qui appelle par « la personne », jamais par son nom et jamais par un mot qui suppose son genre. Tu écris en texte brut ; une citation se met entre guillemets français, sans autre signe. Aucune de tes phrases ne sert uniquement à répéter une information que la fiche porte déjà : {champs}.

Tu ne décris jamais l'état d'esprit de la personne, ni son ton, ni son attitude : tu n'as reçu que du texte et tu ne peux rien en percevoir. Si ce qu'elle ressent compte, c'est parce qu'elle l'a dit, et alors tu rapportes ses mots. Tu t'en tiens aux faits de l'appel : tu ne conseilles pas et tu ne recommandes aucune action.

Tu ne dis pas pourquoi l'appel s'est terminé. Une conversation qui s'arrête ne t'apprend pas si la personne a raccroché, si la ligne a coupé, ou si elle attendait encore. Tu rapportes seulement où en était l'échange à la fin.

Si l'appel est trop court pour être résumé, écris une seule phrase qui dit ce qui s'est passé."""


def nouveau_client(**options) -> httpx.AsyncClient:
    """The HTTP client of the summary (a test gives its stand-in here)."""
    return httpx.AsyncClient(**options)


class SyntheseImpossible(RuntimeError):
    """The model did not answer, or answered nothing usable. Message safe to show."""


def consigne(reglages: ReglagesSynthese, noms_des_champs: list[str]) -> str:
    if reglages.consigne and reglages.consigne.strip():
        return reglages.consigne.strip()
    nom = (reglages.nom_assistant or "").strip()
    return CONSIGNE_GENERIQUE.format(
        assistant=nom or "l'assistant vocal",
        assistant_court=nom or "l'assistant",
        entreprise=f", l'assistant vocal de {reglages.nom_entreprise.strip()}"
        if nom and (reglages.nom_entreprise or "").strip()
        else (
            f" de {reglages.nom_entreprise.strip()}"
            if (reglages.nom_entreprise or "").strip()
            else ""
        ),
        champs=", ".join(noms_des_champs)
        if noms_des_champs
        else "les champs de la fiche",
    )


def message_utilisateur(lignes: list[dict], fiche: dict) -> str:
    conversation = "\n".join(
        f"{'Assistant' if l.get('speaker') == 'agent' else 'Personne'} : {l.get('text')}"
        for l in lignes
        if l.get("text")
    )
    champs = "\n".join(
        f"- {nom} : {valeur}"
        for nom, valeur in fiche.items()
        if valeur not in (None, "")
    )
    return f"La fiche :\n{champs or '(vide)'}\n\nLa conversation :\n{conversation or '(aucune parole)'}"


async def resumer(
    cle: str,
    reglages: ReglagesSynthese,
    lignes: list[dict],
    fiche: dict,
    client: httpx.AsyncClient | None = None,
) -> tuple[str, dict]:
    """``(summary, usage)``. ⛔ The key is never put in an error message."""
    if not any(l.get("text") for l in lignes):
        raise SyntheseImpossible("No words in the conversation: nothing to summarise.")
    corps = {
        "model": reglages.modele,
        "temperature": 0.2,
        "max_tokens": 400,
        "messages": [
            {"role": "system", "content": consigne(reglages, list(fiche))},
            {"role": "user", "content": message_utilisateur(lignes, fiche)},
        ],
    }
    url = os.environ.get(VARIABLE_URL, "").strip().rstrip("/") or URL_PAR_DEFAUT
    propre = client is None
    client = client or nouveau_client(timeout=DELAI_S)
    try:
        reponse = await client.post(
            f"{url}/chat/completions",
            json=corps,
            headers={"Authorization": f"Bearer {cle}"},
        )
    except httpx.HTTPError as erreur:
        raise SyntheseImpossible(
            f"The summary model does not answer ({type(erreur).__name__})."
        ) from None
    finally:
        if propre:
            await client.aclose()
    if reponse.status_code != 200:
        raise SyntheseImpossible(
            f"The summary model refused the request (HTTP {reponse.status_code})."
        )
    try:
        donnees = reponse.json()
        texte = (donnees["choices"][0]["message"]["content"] or "").strip()
    except Exception:  # noqa: BLE001
        raise SyntheseImpossible("The summary model's answer is unreadable.") from None
    if not texte:
        raise SyntheseImpossible("The summary model answered nothing.")
    return " ".join(texte.split()), donnees.get("usage") or {}
