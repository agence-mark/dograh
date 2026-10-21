"""[.mark] Le greffier : un second modèle tient la fiche à côté de l'agent, qui parle seulement.

Plan `Labo-agent-vocal/plans/mode-prise-de-notes/`, partie 2 (lots 10 et 11). En mode greffier,
l'agent n'a ni outil de note ni post-scriptum (``consigne_du_mode`` lui dit que la fiche est tenue
à côté de lui). À chaque nouvelle réplique de la personne, le greffier relit **toute** la
conversation et la fiche, et rend la fiche entière en JSON ; seuls les champs **nouveaux ou changés** passent par
``noter(…, source="greffier")`` : les mêmes contrôles que l'outil et le post-scriptum (méthode du
rejeu du 02/10, `agents/nuances-de-feu/essais/2026-10-01-benchmark-small-4/`).

Ce que le module garantit :

- **Dès la fin de parole de la personne** (chantier greffier-conversation, lot B, C1 et D3 du 13/10,
  qui remplacent D9 « jamais avant l'agent ») : la passe part quand la parole de la personne part au
  modèle de l'agent, **en même temps** que sa requête, jamais en l'attendant (aucune latence
  ajoutée) ; **une passe par réplique**, la passe d'après la réponse a disparu (pas de coût en plus).
  Ainsi la fiche est à jour quand l'agent arrive dans l'étape suivante.
- **Une seule passe en vol** ; une demande arrivée pendant une passe est gardée, une seule, et
  rejouée à la fin de la passe sur la conversation de ce moment-là : **la plus récente gagne**, les
  demandes intermédiaires sont sautées (elles sont comprises dans la relecture complète).
- **Un 429 saute le tour** : journalisé, tracé, la passe suivante relit tout l'appel.
- ⛔ **Il ne coûte jamais l'appel** : il ne bloque ni l'audio, ni la voix, ni l'agent ; une erreur,
  une réponse illisible ou un module en panne sont tracés, rien de plus. La passe de fin reste le filet.
- **Son coût se lit à part** : chaque passe trace ses jetons (`greffier_passes`), et son service
  porte ``usage_context="greffier"``.
- **Sa clé** vient de son bloc ``greffier_llm`` (rangée comme une clé de Dograh, décision d'Evan du
  04/10) ; vide, c'est celle de la conversation. Elle n'est jamais estampillée ni tracée.

Lot 5 bis d'orchestrateur-trois-cerveaux (plan « format garanti du greffier », D1 à D11) :

- case « Guaranteed format » dans la modale du greffier (``greffier_llm.format_garanti``),
  **décochée par défaut** : rien ne change tant qu'elle ne l'est pas ;
- cochée, le greffier demande au fournisseur un JSON qui respecte le **schéma de la fiche**, généré
  à chaque appel depuis les champs de l'agent (``schema_de_la_fiche``, jamais écrit à la main), en
  ``response_format`` json_schema strict (chat completions) ou ``text.format`` (API Responses) ;
- **repli automatique** : refus du fournisseur (4xx sur le format) ou réponse hors schéma, la même
  requête repart une fois en mode JSON, et le couple fournisseur + modèle est retenu **en mémoire
  du processus** comme ne le prenant pas en charge (ré-essayé au redémarrage ; aucune table,
  aucune migration) ;
- chaque passe trace ``format`` (``json`` | ``garanti`` | ``repli``) et ``ecartes`` (les champs
  rendus puis écartés), dans les deux modes ; ``lire_la_note`` et ``champs_a_noter`` restent le filet.

⛔ Aucun mot de métier ici : ce que la fiche contient vient des champs déclarés par agent, et ce qui
est propre à un métier va dans la consigne réglable à l'écran (``greffier_consigne``, D10).
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import datetime
from typing import Any

from loguru import logger

from api.services.groupe.passations import est_un_resultat_de_travail
from api.services.pipecat.balises_expression import sans_balises
from api.services.pipecat.post_scriptum import lire_la_note
from api.services.workflow.dates_relatives import FUSEAU
from api.services.workflow.porte_parlee import FLECHE
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_ETAT,
    CLE_TOUR,
    MODE_GREFFIER,
    MODE_OUTIL,
    NOTE_DESCRIPTIONS,
    VALEUR_DE_REFUS,
    Notices,
    ReglagesFiche,
    _est_un_refus,
    _est_vide,
    _propriete,
    derniere_question,
    est_cite,
    est_un_oui,
    noter,
    paroles_de_l_appelant,
    valeur_de_la_liste,
)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.frames.frames import Frame, LLMFullResponseEndFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

# La trace de chaque passe du greffier, dans la fiche de l'appel.
TRACE_GREFFIER = "greffier_passes"
ECRIT, RIEN, ILLISIBLE, SAUTE, ECHEC = "ecrit", "rien", "illisible", "saute", "echec"
# Une passe revenue après la fin de l'appel : rien n'est écrit.
TARDIVE = "tardive"

# D8 : le modèle du greffier quand son bloc n'en dit rien et que le fournisseur
# est Mistral (rejeu du 02/10 : Large manque 7 données sur 15 appels, Small 11).
MODELE_PAR_DEFAUT_MISTRAL = "mistral-large-2512"
USAGE_GREFFIER = "greffier"
# Une passe ne s'éternise pas : au-delà, elle est abandonnée et tracée.
DELAI_D_UNE_PASSE = 30.0

# D10 : la consigne générique, préremplie à l'écran et modifiable agent par agent.
# Reprend la posture et les interdits du prompt v2 du 02/10, sans un mot de métier.
CONSIGNE_GENERIQUE = (
    "# Ton rôle\n"
    "Tu es le greffier d'un appel téléphonique. Une autre intelligence, l'agent, "
    "parle avec la personne. Toi, tu ne parles jamais : tu tiens la fiche de "
    "l'appel, qui est lue après l'appel.\n\n"
    "# Ta posture\n"
    "Tu es un secrétaire méticuleux et silencieux. Tu écris ce qui a été dit, "
    "exactement, au bon endroit. Une fiche juste mais incomplète vaut mieux "
    "qu'une fiche complète mais fausse. Dans le doute, tu n'écris pas.\n\n"
    "# Ce que tu fais à chaque passe\n"
    "1. Tu lis la dernière réplique de la personne, avec la question de l'agent "
    "juste avant : la question donne le sens de la réponse (un « oui » à une "
    "question de vérification confirme la valeur vérifiée).\n"
    "2. Tu relis la conversation entière et tu la compares à la fiche : une "
    "information dite plus tôt qui manque encore à la fiche, tu la notes maintenant.\n"
    "3. Quand la personne corrige une information, tu réécris le champ avec la "
    "correction.\n\n"
    "# Comment tu écris\n"
    "- Tu écris ce que la personne a dit, avec ses mots ; un nom épelé s'écrit "
    "avec les lettres épelées.\n"
    "- Un nombre dicté s'écrit en chiffres, en recomptant les nombres dits en "
    "lettres un par un.\n"
    "- Un champ qui résume (une raison, une demande) se rédige en une phrase "
    "courte, avec les mots de la personne.\n\n"
    "# Interdits\n"
    "- Tu n'inventes rien, tu ne complètes rien : rien de deviné à partir d'une "
    "autre information, aucun nombre complété.\n"
    "- Tu n'écris jamais ce que l'agent a dit, seulement ce que la personne a dit "
    "ou confirmé.\n"
    "- Tu n'écris pas une information dont tu n'as pas compris le sens : l'agent "
    "la fera répéter.\n"
)

# Lot 5 bis : la réponse quand le format est garanti (tous les champs présents, null = rien).
FORMAT_GARANTI_DE_LA_REPONSE = (
    "# Les champs de la fiche\n"
    "{champs}\n"
    "{note_descriptions}\n\n"
    "# Ta réponse\n"
    "Un seul objet JSON qui respecte le schéma demandé : la fiche entière telle qu'elle doit être "
    "maintenant, tous les champs présents. Un champ dont tu ne sais rien vaut null. Recopie tel "
    "quel ce qui est déjà juste dans la fiche : seuls les champs nouveaux ou changés sont écrits."
)

# Ce que le CODE ajoute toujours à la consigne, réglée ou non : les champs et le
# format de la réponse. Sans eux, le greffier ne peut rien écrire de lisible.
FORMAT_DE_LA_REPONSE = (
    "# Les champs de la fiche\n"
    "{champs}\n"
    "{note_descriptions}\n\n"
    "# Ta réponse\n"
    "Un seul objet JSON, rien d'autre : la fiche entière telle qu'elle doit être "
    "maintenant. Les clés sont des noms de champs ci-dessus ; un champ dont tu "
    "ne sais rien est absent. Recopie tel quel ce qui est déjà juste dans la "
    "fiche : seuls les champs nouveaux ou changés sont écrits."
)


# [.mark] Lot 7 (K4, n° 353, 355) : ce que le CODE ajoute toujours, réglée ou non (comme les champs
# et le format) : un refus, une adresse, le non-dit, les dates relatives. Aucun mot de métier.
REGLES_D_ECRITURE = (
    "# Règles d'écriture\n"
    "- Quand la personne refuse de donner une information, tu écris « refusé » dans le champ, "
    "jamais une valeur.\n"
    "- Une adresse e-mail s'écrit entière, recopiée comme elle a été dite ou épelée : tout ce qui "
    "précède l'arobase compte, points, tirets et chiffres compris ; jamais raccourcie à sa fin, "
    "jamais complétée.\n"
    "- Un champ dicté n'est jamais déduit d'une autre information : un nom ou un prénom ne se "
    "tire pas d'une adresse e-mail, il s'écrit seulement quand la personne l'a dit.\n"
    "- Un champ qui recopie les mots de la personne s'écrit une fois, à sa première formulation : "
    "une réplique de confirmation ou de précision ne le remplace pas.\n"
    "- Rien de non dit ne s'écrit : sans parole de la personne, le champ reste absent.\n"
    "- Une date relative (« l'an dernier », « le mois dernier ») s'écrit telle que dite : le "
    "code la calcule avec la date de l'appel donnée en tête de ta lecture."
)


def consigne_du_greffier(
    reglages: ReglagesFiche, consigne: str | None, format_garanti: bool = False
) -> str:
    """Le prompt système du greffier : la consigne de l'agent (ou la générique),
    puis les champs et le format, ajoutés par le code. ``format_garanti`` (lot 5 bis) : la
    réponse porte tous les champs, ``null`` = rien."""
    champs = "\n".join(
        f"- {champ.nom} : {_propriete(champ)['description']}"
        for champ in reglages.champs_notes
    )
    base = consigne.strip() if consigne and consigne.strip() else CONSIGNE_GENERIQUE
    return "\n\n".join(
        [
            base.rstrip(),
            REGLES_D_ECRITURE,
            (FORMAT_GARANTI_DE_LA_REPONSE if format_garanti else FORMAT_DE_LA_REPONSE).format(
                champs=champs, note_descriptions=NOTE_DESCRIPTIONS
            ),
        ]
    )


def _texte(contenu: Any) -> str:
    if isinstance(contenu, str):
        return contenu
    if isinstance(contenu, list):
        return " ".join(
            part.get("text", "")
            for part in contenu
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return ""


_JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
_MOIS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)


def date_du_jour(maintenant: datetime | None = None) -> str:
    """[.mark] D3 de repliques-coupees : la date de l'appel, au fuseau de Paris, côté
    serveur (« Nous sommes le mercredi 14 octobre 2026. »). Sans elle, le greffier
    écrivait « octobre 2022 » pour « l'an dernier », refusé par le code à chaque tour
    (run 1175). Le calcul reste au modèle : on ne lui donne que le jour."""
    jour = (maintenant or datetime.now(FUSEAU)).astimezone(FUSEAU)
    quantieme = "1er" if jour.day == 1 else str(jour.day)
    return (
        f"Nous sommes le {_JOURS[jour.weekday()]} {quantieme} "
        f"{_MOIS[jour.month - 1]} {jour.year}."
    )


def message_du_greffier(
    reglages: ReglagesFiche,
    fiche: dict,
    messages: Iterable[dict],
    refus: Iterable[dict] = (),
    *,
    aujourd_hui: str | None = None,
) -> str:
    """Ce que le greffier lit à chaque passe : la date de l'appel (D3 de
    repliques-coupees), la fiche actuelle (valeur, sûre ou à confirmer), ce que
    sa passe précédente s'est vu refuser, la conversation entière numérotée, la
    dernière réplique."""
    etat = fiche.get(CLE_ETAT) or {}
    lignes_fiche = []
    for champ in reglages.champs:
        valeur = fiche.get(champ.nom)
        if _est_vide(valeur):
            continue
        sure = (etat.get(champ.nom) or {}).get("sure")
        lignes_fiche.append(
            f"- {champ.nom} = {json.dumps(valeur, ensure_ascii=False)}"
            + ("" if sure else " (à confirmer)")
        )
    conversation = []
    for message in messages:
        role = message.get("role")
        if role not in ("user", "assistant"):
            continue
        # Lot 4 d'orchestrateur-trois-cerveaux : le résultat du travail de fond n'a été dit par
        # personne ; le greffier n'écrit que ce que la personne a dit ou confirmé.
        if est_un_resultat_de_travail(message):
            continue
        texte = _texte(message.get("content")).strip()
        if role == "assistant":
            # [.mark] Voix-soniox, lot 5 bis (D11) : la fiche ne lit aucune balise d'expression
            # (l'historique du modele, lui, la garde telle qu'ecrite).
            texte = sans_balises(texte)
            # Lot A de greffier-conversation : une ligne de porte (« → ») n'est jamais
            # relue, même si elle avait échappé au lecteur de portes.
            texte = "\n".join(
                ligne
                for ligne in texte.splitlines()
                if not ligne.lstrip().startswith(FLECHE)
            ).strip()
        if not texte:
            continue
        qui = "Personne" if role == "user" else "Agent"
        conversation.append(f"{len(conversation) + 1}. {qui} : {texte}")
    paroles = paroles_de_l_appelant(messages)
    refuses = [
        f"- {r.get('champ')} : {RAISONS_DU_REFUS.get(r.get('raison'), r.get('raison'))}"
        for r in refus
    ]
    blocs = ["# Aujourd'hui\n" + aujourd_hui] if aujourd_hui else []
    blocs.append("# La fiche actuelle\n" + ("\n".join(lignes_fiche) or "(vide)"))
    if refuses:
        blocs.append(
            "# Refusé à ta passe précédente (ne le renvoie pas tel quel)\n"
            + "\n".join(refuses)
        )
    return "\n\n".join(
        [
            *blocs,
            "# La conversation\n" + ("\n".join(conversation) or "(rien encore)"),
            "# La dernière réplique de la personne\n"
            + (paroles[-1] if paroles else "(aucune)"),
        ]
    )


# Les raisons de refus du point d'écriture, dites au greffier (les autres passent telles quelles).
RAISONS_DU_REFUS = {
    "non_dit": "pas dit tel quel par la personne : écris ses mots exacts",
    "nombre_de_chiffres": "il manque ou il y a trop de chiffres",
}


def _jetons(usage: Any) -> dict:
    if usage is None:
        return {}
    # Chat completions compte « prompt » et « completion » ; l'API Responses, « input » et « output ».
    entree = getattr(usage, "prompt_tokens", None)
    sortie = getattr(usage, "completion_tokens", None)
    return {
        "jetons_entree": entree if entree is not None else getattr(usage, "input_tokens", None),
        "jetons_sortie": sortie if sortie is not None else getattr(usage, "output_tokens", None),
    }


# Lot 5 bis (D9) : le format de la passe, tracé.
FORMAT_JSON, FORMAT_GARANTI, FORMAT_REPLI = "json", "garanti", "repli"
NOM_DU_SCHEMA = "fiche"
# Lot 5 bis (D7) : les couples (API, adresse, modèle) dont le fournisseur a refusé le format garanti
# ou répondu hors schéma. En mémoire du processus : pas de table, ré-essayé au redémarrage.
NE_GARANTISSENT_PAS: set[tuple[str, str, str]] = set()


def _cle_du_couple(service: Any) -> tuple[str, str, str]:
    """(API, adresse, modèle) du service du greffier : de quoi retenir qu'il ne garantit pas."""
    api = "responses" if getattr(service, "mark_api", None) == "responses" else "chat"
    adresse = str(getattr(getattr(service, "_client", None), "base_url", "") or "")
    modele = getattr(getattr(service, "_settings", None), "model", None)
    return api, adresse, modele if isinstance(modele, str) else ""


def _a_un_client(service: Any) -> bool:
    """Le service a le client au format OpenAI (chat completions ou Responses) : le format
    garanti ne s'envoie que par lui (D5)."""
    if getattr(service, "mark_api", None) == "responses":
        return True
    return hasattr(service, "build_chat_completion_params") and hasattr(service, "_client")


async def interroger(
    service: Any, systeme: str, message: str, schema: dict | None = None
) -> tuple[str | None, dict]:
    """Une requête au modèle du greffier, en JSON, avec ses jetons. Par le client
    du fournisseur et les paramètres du service (``run_inference`` de Pipecat ne
    rend ni le format JSON ni les jetons) ; sans ce client : ``run_inference``.

    Lot 5 bis : avec ``schema``, le format demandé est le JSON Schema strict de la fiche
    (``response_format`` json_schema en chat completions, ``text.format`` en API Responses) au
    lieu du mode JSON. Sans client au format OpenAI, ``schema`` est sans effet."""
    contexte = LLMContext(messages=[{"role": "user", "content": message}])
    if getattr(service, "mark_api", None) == "responses":
        # Lot 1 d'orchestrateur-trois-cerveaux : le greffier réglé sur l'API Responses. Même
        # requête, sans flux, en JSON ; le format garanti du lot 5 bis passe par ``text.format``.
        invocation = service.get_llm_adapter().get_llm_invocation_params(
            contexte, system_instruction=systeme
        )
        params = service.build_chat_completion_params(invocation)
        params["stream"] = False
        params["text"] = {
            "format": (
                {"type": "json_schema", "name": NOM_DU_SCHEMA, "schema": schema, "strict": True}
                if schema is not None
                else {"type": "json_object"}
            )
        }
        reponse = await service._client.responses.create(**params)
        return reponse.output_text, _jetons(getattr(reponse, "usage", None))
    if hasattr(service, "build_chat_completion_params") and hasattr(service, "_client"):
        adaptateur = service.get_llm_adapter()
        invocation = adaptateur.get_llm_invocation_params(
            contexte,
            system_instruction=systeme,
            convert_developer_to_user=not getattr(
                service, "supports_developer_role", True
            ),
        )
        params = service.build_chat_completion_params(invocation)
        params["stream"] = False
        params.pop("stream_options", None)
        params["response_format"] = (
            {
                "type": "json_schema",
                "json_schema": {"name": NOM_DU_SCHEMA, "schema": schema, "strict": True},
            }
            if schema is not None
            else {"type": "json_object"}
        )
        reponse = await service._client.chat.completions.create(**params)
        return reponse.choices[0].message.content, _jetons(
            getattr(reponse, "usage", None)
        )
    return await service.run_inference(contexte, system_instruction=systeme), {}


def _refus_du_format(erreur: BaseException) -> bool:
    """Lot 5 bis (D7) : le fournisseur refuse la requête à cause de son format (4xx sur le
    paramètre : 400, 404, 415, 422). Un 429 (quota) ou une erreur d'accès ne sont jamais un refus
    du format : elles remontent comme avant."""
    statut = getattr(erreur, "status_code", None) or getattr(
        getattr(erreur, "response", None), "status_code", None
    )
    return statut in (400, 404, 415, 422)


_MOTS_DU_FORMAT = ("schema", "response_format", "text.format", "json", "strict", "format")


def _refus_qui_vise_le_format(erreur: BaseException) -> bool:
    """Relecture du lot 6 : un refus dont le message cite le format (schéma, ``response_format``,
    ``text.format``…) dit que le couple ne le prend pas en charge. Un autre 400 (contexte trop long,
    paramètre voisin) n'est pas retenu : la passe se replie seule, la suivante retente. Le message
    n'est lu que pour ces mots, jamais écrit au journal (il peut citer une clé)."""
    message = str(getattr(erreur, "message", "") or erreur).lower()
    return any(mot in message for mot in _MOTS_DU_FORMAT)


def _somme_des_jetons(*lots: dict) -> dict:
    total: dict = {}
    for lot in lots:
        for cle, valeur in (lot or {}).items():
            if isinstance(valeur, (int, float)):
                total[cle] = (total.get(cle) or 0) + valeur
            elif cle not in total:
                total[cle] = valeur
    return total


async def interroger_au_format(
    service: Any,
    systeme: str,
    message: str,
    schema: dict | None,
    reglages: ReglagesFiche,
) -> tuple[str | None, dict, str]:
    """Lot 5 bis (D5, D7) : la requête du greffier, au format garanti si ``schema`` est donné,
    avec son repli. Rend (texte, jetons, format) où format est ``json`` (le mode d'avant),
    ``garanti`` (le schéma a tenu) ou ``repli`` (le schéma a échoué, la même requête est repartie en
    mode JSON ; les jetons des deux requêtes sont comptés).

    Sans schéma, sans client au format OpenAI ou pour un couple retenu comme ne garantissant pas :
    le mode JSON d'avant, une seule requête."""
    if schema is None or not _a_un_client(service):
        texte, jetons = await interroger(service, systeme, message)
        return texte, jetons, FORMAT_JSON
    cle = _cle_du_couple(service)
    if cle in NE_GARANTISSENT_PAS:
        texte, jetons = await interroger(service, systeme, message)
        return texte, jetons, FORMAT_JSON
    try:
        texte, jetons = await interroger(service, systeme, message, schema=schema)
    except Exception as erreur:  # noqa: BLE001 -- seul un refus du format se rattrape
        if not _refus_du_format(erreur):
            raise
        if _refus_qui_vise_le_format(erreur):
            NE_GARANTISSENT_PAS.add(cle)
        # Le nom de l'erreur seulement : le texte d'une erreur de fournisseur peut citer la clé.
        logger.warning(
            f"[fiche] format garanti refusé par le fournisseur ({type(erreur).__name__}) : "
            "mode JSON, couple retenu pour ce processus"
        )
        texte, jetons = await interroger(service, systeme, message)
        return texte, jetons, FORMAT_REPLI
    rendue = lire_la_note(texte or "")
    if rendue is None or hors_schema(rendue, reglages):
        NE_GARANTISSENT_PAS.add(cle)
        logger.warning(
            "[fiche] réponse hors du schéma garanti : mode JSON, couple retenu pour ce processus"
        )
        texte2, jetons2 = await interroger(service, systeme, message)
        return texte2, _somme_des_jetons(jetons, jetons2), FORMAT_REPLI
    return texte, jetons, FORMAT_GARANTI


def est_un_429(erreur: BaseException) -> bool:
    """Le fournisseur refuse pour cause de quota (D9)."""
    statut = getattr(erreur, "status_code", None) or getattr(
        getattr(erreur, "response", None), "status_code", None
    )
    return statut == 429 or "429" in str(erreur) or "rate limit" in str(erreur).lower()


def champs_a_noter(
    reglages: ReglagesFiche,
    fiche: dict,
    rendue: dict,
    oui: bool = False,
    question: str | None = None,
) -> dict:
    """Les champs nouveaux ou changés de la fiche rendue par le greffier : un
    champ inconnu, vide ou identique à la fiche n'est pas renvoyé à ``noter``.

    courriel-confirmation (relecture n° 1) : sauf un champ identique encore à
    confirmer, quand la personne vient de dire oui à une question qui REDIT sa valeur.
    Sans lui, le oui ne le rendait jamais sûr (D6 ne joue que sur une note) et l'agent
    redemandait. Relecture n° 2 : un oui à une autre question (« être rappelé
    demain ? ») ne confirme jamais une valeur que l'agent n'a pas relue."""
    par_nom = reglages.par_nom
    etat = fiche.get(CLE_ETAT) or {}
    a_noter = {}
    for nom, valeur in rendue.items():
        if nom not in par_nom or _est_vide(valeur):
            continue
        if par_nom[nom].copie_de_la_parole and not _est_vide(fiche.get(nom)):
            # B3 : un champ qui recopie les mots de la personne s'écrit une fois (la première
            # formulation) ; une réplique de confirmation ne le remplace pas.
            continue
        if fiche.get(nom) == valeur and not (
            oui
            and question
            and not (etat.get(nom) or {}).get("sure")
            and est_cite(valeur, [question])
        ):
            continue
        a_noter[nom] = valeur
    # D2 (rejeu du 16/10, S6 run 1394) : une personne refuse UNE information à la fois. Un refus
    # sur plusieurs champs dans la même passe (« refusé » partout, 20 champs) n'est jamais un
    # refus dit : tous ces refus sont écartés, le reste de la passe est gardé.
    refus = [nom for nom, valeur in a_noter.items() if _est_un_refus(valeur, par_nom[nom])]
    if len(refus) > 1:
        logger.warning(f"[greffier] refus sur {len(refus)} champs dans une passe : écartés")
        for nom in refus:
            a_noter.pop(nom, None)
    return a_noter


def schema_de_la_fiche(reglages: ReglagesFiche) -> dict:
    """Lot 5 bis (D4, D6) : le JSON Schema de la réponse du greffier, **généré** à chaque appel depuis
    les champs de l'agent (jamais écrit à la main, aucun nom de métier ici). Tous les champs sont
    requis et ``additionalProperties`` est faux (le mode strict des API au format OpenAI) ;
    chaque champ vaut son type **ou** ``null`` (= rien à noter). Une liste fermée de valeurs devient
    un ``enum`` (``null`` en plus), sauf pour un champ cumulatif, qui s'écrit « a ; b »."""
    proprietes: dict = {}
    # fiabilite-orchestration, lot 1 (G2) : un champ rempli par un outil n'est jamais proposé.
    for champ in reglages.champs_notes:
        base: dict = {"type": champ.type}
        if champ.valeurs and champ.type == "string" and not champ.cumulatif:
            # K4 révisé (21/10) : le refus de la personne est permis sur une liste fermée aussi.
            base["enum"] = [*champ.valeurs, VALEUR_DE_REFUS]
        proprietes[champ.nom] = {"anyOf": [base, {"type": "null"}]}
    return {
        "type": "object",
        "properties": proprietes,
        "required": [champ.nom for champ in reglages.champs_notes],
        "additionalProperties": False,
    }


def _du_bon_type(champ: Any, valeur: Any) -> bool:
    if valeur is None:
        return True
    if champ.type == "boolean":
        return isinstance(valeur, bool)
    if champ.type == "number":
        return isinstance(valeur, (int, float)) and not isinstance(valeur, bool)
    if not isinstance(valeur, str):
        return False
    if champ.valeurs and not champ.cumulatif:
        # Même lecture que l'écriture dans la fiche (casse, accents, ponctuation) : une valeur que
        # ``ecrire_dans_la_fiche`` ramène à la liste n'est pas hors schéma (relecture du lot 6).
        return valeur_de_la_liste(valeur, champ.valeurs) is not None
    return True


def hors_schema(rendue: dict, reglages: ReglagesFiche) -> bool:
    """Lot 5 bis (D7) : la réponse porte une clé hors de la fiche, ou une valeur d'un type (ou d'une
    liste fermée) que le schéma n'admet pas. Un champ absent n'est pas hors schéma : il est lu
    comme rien (le filet d'avant)."""
    par_nom = reglages.par_nom
    for nom, valeur in rendue.items():
        if nom not in par_nom or not _du_bon_type(par_nom[nom], valeur):
            return True
    return False


def champs_a_noter_et_ecartes(
    reglages: ReglagesFiche,
    fiche: dict,
    rendue: dict,
    oui: bool = False,
    question: str | None = None,
) -> tuple[dict, list[str]]:
    """Lot 5 bis (D9) : ``champs_a_noter`` et, à côté, les noms des champs rendus puis **écartés** :
    inconnus de la fiche, vides non nuls (``null`` est « rien », pas un écart), refusés ensemble (D2
    du 16/10) ou d'une copie de la parole déjà écrite. Un champ identique à la fiche n'est pas un
    écart. ⛔ Zéro perte (relecture du lot 6) : une valeur d'un type inattendu est **transmise comme
    avant** (``ecrire_dans_la_fiche`` la ramène à la bonne forme quand il le peut) ; le plan du 16/10
    (D9) demande de tracer les écartés, jamais d'en écarter davantage."""
    par_nom = reglages.par_nom
    ecartes: list[str] = []
    gardes: dict = {}
    for nom, valeur in rendue.items():
        if nom not in par_nom:
            ecartes.append(nom)
        elif valeur is None:
            continue
        elif _est_vide(valeur):
            ecartes.append(nom)
        else:
            gardes[nom] = valeur
    a_noter = champs_a_noter(reglages, fiche, gardes, oui, question)
    for nom, valeur in gardes.items():
        if nom in a_noter or fiche.get(nom) == valeur:
            continue
        ecartes.append(nom)  # écarté par ``champs_a_noter`` (refus groupé, copie déjà écrite)
    return a_noter, sorted(set(ecartes))


class Greffier:
    """Les passes du greffier d'un appel : une seule en vol, la plus récente gagne."""

    def __init__(
        self,
        *,
        service: Any,
        reglages: ReglagesFiche,
        fiche: Callable[[], dict],
        messages: Callable[[], Iterable[dict]],
        notices: Notices | None,
        notes_en_cours: set[asyncio.Task],
        consigne: str | None = None,
        delai: float = DELAI_D_UNE_PASSE,
        verser_le_cout: Callable[[int | None, int | None], None] | None = None,
        format_garanti: bool = False,
    ):
        # Lot 4 d'orchestrateur-trois-cerveaux (D12) : les jetons de chaque passe payée sont
        # versés au collecteur de coût de l'appel (None : comme avant, rien n'est versé).
        self._verser_le_cout = verser_le_cout
        self._service = service
        self._reglages = reglages
        self._fiche = fiche
        self._messages = messages
        self._notices = notices
        self._notes_en_cours = notes_en_cours
        # Lot 5 bis (D1, D2) : décoché = le mode JSON d'avant, à l'octet.
        self._format_garanti = bool(format_garanti)
        self._systeme = consigne_du_greffier(reglages, consigne, self._format_garanti)
        self._delai = delai
        self._en_vol: asyncio.Task | None = None
        self._encore = False
        # Ce que la passe précédente s'est vu refuser : dit à la suivante.
        self._refus: list[dict] = []
        # Fin de l'appel (revue du 04/10) : plus de passe, et une passe encore
        # en vol n'écrit plus (la passe de fin est passée, la fiche est partie).
        self._clos = False
        # Lot B de greffier-conversation : la réplique de la personne qui a déjà
        # déclenché une passe, celle que lit la passe en vol, celle déjà relue.
        self._replique_vue: tuple | None = None
        self._replique_en_vol: tuple | None = None
        self._replique_lue: tuple | None = None

    def clore(self) -> None:
        """La fin de l'appel : aucune passe ne part ni n'écrit plus."""
        self._clos = True
        self._encore = False

    def declencher(self) -> None:
        """Demande une passe. Pendant une passe, la demande est gardée (une seule)
        et rejouée à sa fin, sur la conversation de ce moment-là."""
        if self._clos:
            return
        if self._en_vol is not None and not self._en_vol.done():
            self._encore = True
            return
        self._encore = False
        # Ce que la passe va lire, connu dès maintenant : un rattrapage demandé avant
        # qu'elle ne démarre l'attend au lieu d'en demander une autre (revue du 13/10).
        try:
            self._replique_en_vol = _derniere_replique(self._messages())
        except Exception:  # noqa: BLE001 -- la passe relira de toute façon
            self._replique_en_vol = None
        tache = asyncio.get_running_loop().create_task(self._tourner())
        self._en_vol = tache
        self._notes_en_cours.add(tache)
        tache.add_done_callback(self._notes_en_cours.discard)

    def nouvelle_replique(self, messages: Iterable[dict]) -> bool:
        """Lot B de greffier-conversation (C1) : la conversation de l'appel vient de
        recevoir un message de la personne. Une réplique pas encore vue déclenche une
        passe ; la même réplique revue n'en déclenche aucune. Rend ``True`` si une passe
        est demandée."""
        marque = _derniere_replique(messages)
        if marque is None or marque == self._replique_vue:
            return False
        self._replique_vue = marque
        self.declencher()
        return True

    async def rattraper(self, delai: float) -> bool:
        """Lot D d'agent-leger-greffier : une action a besoin d'un champ que la personne
        vient peut-être de dire. Depuis le lot B de greffier-conversation, la passe sur
        cette réplique est déjà partie à la fin de sa parole : déjà relue, rien à
        attendre ; en vol, elle est attendue sans en demander une autre ; sinon une passe
        est demandée sur la conversation de maintenant. Attend ``delai`` secondes au plus.
        ``True`` si la fiche a relu la dernière réplique à temps. Ne lève jamais ; la passe
        continue après le délai (elle écrira pour la suite)."""
        if self._clos or delai <= 0:
            return False
        try:
            maintenant = _derniere_replique(self._messages())
            en_vol = self._en_vol is not None and not self._en_vol.done()
            if (
                maintenant is not None
                and not en_vol
                and maintenant == self._replique_lue
            ):
                return True
            if not (en_vol and maintenant == self._replique_en_vol):
                self.declencher()
            tache = self._en_vol
            if tache is None:
                return False
            await asyncio.wait_for(asyncio.shield(tache), timeout=delai)
            return True
        except (TimeoutError, asyncio.TimeoutError):
            return False
        except Exception as erreur:  # noqa: BLE001 -- jamais l'appel
            logger.warning(f"[fiche] rattrapage du greffier en échec : {erreur!r}")
            return False

    async def _tourner(self) -> None:
        while True:
            await self.une_passe()
            if not self._encore or self._clos:
                return
            self._encore = False

    async def une_passe(self) -> None:
        """Une passe : relire, demander la fiche entière, écrire ce qui change.
        ⛔ Ne lève jamais."""
        debut = time.monotonic()
        try:
            fiche = self._fiche()
            lus = list(self._messages())
            self._replique_en_vol = _derniere_replique(lus)
            message = message_du_greffier(
                self._reglages, fiche, lus, self._refus, aujourd_hui=date_du_jour()
            )
            texte, jetons, format_ = await asyncio.wait_for(
                self._demander(message), self._delai
            )
        except Exception as erreur:  # noqa: BLE001 -- le greffier ne coûte jamais l'appel
            if est_un_429(erreur):
                logger.warning("[fiche] greffier en 429 : tour sauté, relu au suivant")
                self._tracer(SAUTE, [], debut)
            else:
                # Le nom de l'erreur seulement : le texte d'une erreur de
                # fournisseur peut citer la clé.
                logger.error(
                    f"[fiche] passe du greffier en échec : {type(erreur).__name__}"
                )
                self._tracer(ECHEC, [], debut, erreur=type(erreur).__name__)
            return
        self._verser(jetons)
        if self._clos:
            logger.info("[fiche] passe du greffier finie après l'appel : rien écrit")
            self._tracer(TARDIVE, [], debut, format=format_, **jetons)
            return
        rendue = lire_la_note(texte or "")
        if rendue is None:
            logger.warning("[fiche] greffier illisible : rien noté à cette passe")
            self._tracer(ILLISIBLE, [], debut, format=format_, **jetons)
            return
        a_noter: dict = {}
        ecartes: list[str] = []
        try:
            replique = _derniere_replique(lus)
            a_noter, ecartes = champs_a_noter_et_ecartes(
                self._reglages,
                self._fiche(),
                rendue,
                oui=bool(replique and est_un_oui(replique[1])),
                question=derniere_question(lus),
            )
            note = None
            if a_noter:
                note = await noter(
                    self._fiche,
                    self._reglages,
                    a_noter,
                    paroles=paroles_de_l_appelant(lus),
                    question=derniere_question(lus),
                    source=MODE_GREFFIER,
                )
        except Exception as erreur:  # noqa: BLE001 -- une note ne coûte jamais l'appel
            logger.error(f"[fiche] note du greffier en échec : {erreur!r}")
            self._tracer(
                ECHEC,
                sorted(a_noter),
                debut,
                erreur=type(erreur).__name__,
                format=format_,
                ecartes=ecartes,
                **jetons,
            )
            return
        self._refus = list(note.refuses) if note is not None else []
        if self._notices is not None:
            # Une passe sans rien à écrire efface les notices de la précédente.
            # Les refus vont au greffier (ci-dessus), jamais à l'agent : il n'a
            # rien noté, une consigne de rédacteur l'égarerait.
            self._notices.retenir(
                replace(note, refuses=[]) if note is not None else None
            )
        self._replique_lue = _derniere_replique(lus)
        # Lot 5 bis (D9) : le format de la passe et les champs écartés, dans les deux modes.
        self._tracer(
            ECRIT if a_noter else RIEN,
            sorted(a_noter),
            debut,
            format=format_,
            ecartes=ecartes,
            **jetons,
        )

    async def _demander(self, message: str) -> tuple[str | None, dict, str]:
        """La requête de la passe : le format garanti si la case est cochée (avec son repli),
        sinon le mode JSON d'avant par ``interroger`` seul."""
        if not self._format_garanti:
            texte, jetons = await interroger(self._service, self._systeme, message)
            return texte, jetons, FORMAT_JSON
        return await interroger_au_format(
            self._service,
            self._systeme,
            message,
            schema_de_la_fiche(self._reglages),
            self._reglages,
        )

    def _verser(self, jetons: dict) -> None:
        """Les jetons d'une passe payée vont au coût de l'appel. ⛔ Ne lève jamais."""
        if self._verser_le_cout is None or not jetons:
            return
        try:
            self._verser_le_cout(
                jetons.get("jetons_entree"), jetons.get("jetons_sortie")
            )
        except Exception as erreur:  # noqa: BLE001 -- le coût ne coûte jamais l'appel
            logger.warning(f"[fiche] jetons du greffier non versés : {erreur!r}")

    def _tracer(self, etat: str, champs: list[str], debut: float, **detail) -> None:
        try:
            fiche = self._fiche()
            fiche.setdefault(TRACE_GREFFIER, []).append(
                {
                    "tour": fiche.get(CLE_TOUR),
                    "etat": etat,
                    "champs": champs,
                    "duree_ms": round((time.monotonic() - debut) * 1000),
                    **detail,
                }
            )
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[fiche] trace du greffier non écrite : {erreur!r}")


def _derniere_replique(messages: Iterable[dict]) -> tuple | None:
    """La dernière réplique de la personne : (son rang parmi ses répliques, son texte),
    ou ``None`` s'il n'y en a pas. Le rang distingue deux « oui » de suite."""
    rang, texte = 0, None
    for message in messages:
        if message.get("role") == "user" and not est_un_resultat_de_travail(message):
            rang += 1
            texte = _texte(message.get("content"))
    return None if texte is None else (rang, texte)


def declencher_a_la_conversation(context: Any, greffier: Greffier) -> bool:
    """Lot B de greffier-conversation (C1, D3) : quand une réplique CONFIRMÉE de la personne
    entre dans la conversation de l'appel (l'agrégateur de la personne l'y écrit juste avant
    de demander la réponse de l'agent ; le clavier, juste avant le modèle), le greffier part,
    en même temps que l'agent, jamais en l'attendant.

    Revue du 13/10 : pas à la requête du modèle. Avec une fin de tour anticipée, la requête
    porte une copie PROVISOIRE de la conversation, et à la confirmation aucune requête ne
    repart : le greffier aurait marqué la réplique vue sans jamais la lire.
    ``False`` : pas de conversation, rien n'est branché."""
    ajouter = getattr(context, "add_message", None)
    ajouter_plusieurs = getattr(context, "add_messages", None)
    if ajouter is None or ajouter_plusieurs is None:
        logger.warning("[fiche] conversation illisible : greffier non branché")
        return False

    def apres(messages: Iterable[dict]) -> None:
        try:
            if any(
                isinstance(m, dict)
                and m.get("role") == "user"
                and not est_un_resultat_de_travail(m)
                for m in messages
            ):
                greffier.nouvelle_replique(context.get_messages())
        except Exception as erreur:  # noqa: BLE001 -- jamais l'appel
            logger.error(f"[fiche] greffier non déclenché : {erreur!r}")

    def add_message(message, *args, **kwargs):
        resultat = ajouter(message, *args, **kwargs)
        apres([message])
        return resultat

    def add_messages(messages, *args, **kwargs):
        messages = list(messages)
        resultat = ajouter_plusieurs(messages, *args, **kwargs)
        apres(messages)
        return resultat

    context.add_message = add_message
    context.add_messages = add_messages
    return True


class DeclencheurDuGreffier(FrameProcessor):
    """Le repli du lot B : sans conversation où s'accrocher, l'ancien déclenchement, à la
    fin de chaque réponse de l'agent, plutôt qu'un greffier qui ne part jamais."""

    def __init__(self, greffier: Greffier, **kwargs):
        super().__init__(**kwargs)
        self._greffier = greffier

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
        if isinstance(frame, LLMFullResponseEndFrame):
            try:
                self._greffier.declencher()
            except Exception as erreur:  # noqa: BLE001 -- jamais l'appel
                logger.error(f"[fiche] greffier non déclenché : {erreur!r}")


# --- Le service ---------------------------------------------------------------


# Ce que le greffier n'hérite pas de la conversation (revue du 04/10).
REGLAGES_NON_HERITES = (
    "max_tokens",
    "frequency_penalty",
    "presence_penalty",
    "seed",
    "top_p",
)


def configuration_du_greffier(user_config: Any, bloc: dict | None) -> Any:
    """La configuration de modèle du greffier : celle de la conversation, à
    laquelle son bloc s'applique comme une surcharge de modèle. Clé vide : celle de
    la conversation (même fournisseur).

    Lot 4 d'orchestrateur-trois-cerveaux (D10) : un greffier SANS bloc réglé prend le cerveau de
    conversation de l'agent, tel quel (plus de Mistral Large en dur). Un bloc réglé (même sans
    modèle) qui nomme Mistral sans modèle garde ``mistral-large-2512`` (D8), comme avant : les
    agents dont le greffier est réglé explicitement ne changent pas."""
    return configuration_d_un_cerveau_annexe(
        user_config,
        bloc,
        objet="clerk",
        modele_par_defaut_mistral=MODELE_PAR_DEFAUT_MISTRAL,
        nom_du_reglage="Set up the clerk",
    )


def configuration_d_un_cerveau_annexe(
    user_config: Any,
    bloc: dict | None,
    *,
    objet: str,
    modele_par_defaut_mistral: str | None = None,
    nom_du_reglage: str = "",
) -> Any:
    """[.mark] La configuration de modèle d'un cerveau annexe (le greffier, le cerveau de
    fond) : celle de la conversation, à laquelle son bloc s'applique comme une surcharge de
    modèle. Un bloc vide ou sans valeur = le cerveau de conversation, exactement.

    ``modele_par_defaut_mistral`` : le modèle posé quand le bloc EST réglé, nomme (ou hérite de)
    Mistral et ne dit pas de modèle ; jamais appliqué à un bloc vide.
    """
    from api.services.cles_reference import est_reference
    from api.services.configuration.resolve import resolve_effective_config

    surcharge = {
        cle: valeur
        for cle, valeur in (bloc or {}).items()
        if valeur is not None and valeur != "" and cle != "format_garanti"
    }
    # Revue du lot 0 bis (06/10) : ce bloc s'applique APRÈS la résolution des clés de la
    # bibliothèque. Depuis le lot C d'agent-leger-greffier, la référence du bloc est résolue
    # avant (``resoudre_le_bloc_du_greffier``) ; une référence ENCORE là est introuvable ou
    # d'un autre fournisseur : refusée en le disant, l'appelant repasse en mode outil (repli
    # déjà prévu), jamais une référence envoyée au fournisseur comme si c'était une clé.
    if est_reference(surcharge.get("api_key")):
        raise ValueError(
            f"The {objet}'s key chosen in the key library was deleted or belongs to "
            f"another provider: pick another in « {nom_du_reglage} »."
        )
    fournisseur = surcharge.get("provider") or getattr(
        getattr(user_config, "llm", None), "provider", None
    )
    if (
        surcharge
        and modele_par_defaut_mistral
        and "model" not in surcharge
        and str(getattr(fournisseur, "value", fournisseur)).lower() == "mistral"
    ):
        surcharge["model"] = modele_par_defaut_mistral
    configuration = resolve_effective_config(
        user_config, {"llm": surcharge} if surcharge else None
    )
    # Revue du 04/10 : les réglages de génération réglés pour la VOIX (plafond de
    # jetons, pénalités, graine) tronqueraient ou pénaliseraient la fiche JSON du
    # greffier, et ne se voient pas dans sa modale : remis à leur défaut, sauf
    # s'ils sont posés dans son bloc. La température, elle, est à l'écran.
    # Même chose pour le cerveau de fond : un plafond de 120 jetons réglé pour la voix
    # tronquerait son résultat.
    llm = configuration.llm
    champs = getattr(type(llm), "model_fields", {})
    remis = {
        nom: champs[nom].default
        for nom in REGLAGES_NON_HERITES
        if nom in champs and nom not in surcharge
    }
    if remis:
        configuration.llm = llm.model_copy(update=remis)
    return configuration


async def resoudre_le_bloc_du_greffier(
    run_configs: dict | None, organization_id: int | None
) -> dict | None:
    """[.mark] Lot C d'agent-leger-greffier : le bloc ``greffier_llm`` dont la clé est
    une référence de la bibliothèque (``mark-cle:<uuid>``), rendu avec la vraie clé,
    lue dans l'organisation de l'appel et seulement si elle est du même fournisseur
    que le greffier (``resoudre_les_cles``, la règle de la conversation). Une copie :
    ``run_configs`` n'est jamais modifié (il est estampillé ailleurs, la clé n'y entre
    pas). Sans référence, rendu tel quel, sans lecture de la base. Ne lève jamais :
    une référence introuvable reste, et ``configuration_du_greffier`` refuse alors
    (appel joué en mode outil)."""
    return await resoudre_le_bloc_annexe(
        run_configs, organization_id, "greffier_llm", "clerk"
    )


async def resoudre_le_bloc_annexe(
    run_configs: dict | None, organization_id: int | None, cle_du_bloc: str, usage: str
) -> dict | None:
    """[.mark] Le bloc de modèle d'un cerveau annexe (``greffier_llm``, ``travail_llm``) dont la
    clé est une référence de la bibliothèque, avec la vraie clé. Voir
    ``resoudre_le_bloc_du_greffier`` : même règle, ``usage`` nomme le cerveau dans les journaux."""
    from api.services.cles_reference import cle_d_une_reference, est_reference

    bloc = (run_configs or {}).get(cle_du_bloc)
    if not isinstance(bloc, dict) or not est_reference(bloc.get("api_key")):
        return run_configs
    try:
        # Lot 10 de fiabilite-orchestration : le bloc dit où il vise (``base_url``) ; sans, il vise
        # l'adresse de son fournisseur, et une clé qui a une adresse ne part pas (l'adresse manque).
        cible = {"adresse_cible": bloc["base_url"]} if "base_url" in bloc else {}
        cle = await cle_d_une_reference(
            bloc["api_key"], bloc.get("provider"), organization_id, usage, **cible
        )
    except Exception as erreur:  # noqa: BLE001 -- jamais l'appel
        logger.error(f"[fiche] clé ({usage}) non résolue : {type(erreur).__name__}")
        return run_configs
    if cle is None:
        return run_configs
    return {**run_configs, cle_du_bloc: {**bloc, "api_key": cle}}


def service_du_greffier(
    reglages: ReglagesFiche | None,
    run_configs: dict | None,
    user_config: Any,
    *,
    correlation_id: str | None = None,
) -> tuple[Any, dict | None]:
    """Le service de modèle du greffier et son estampille (fournisseur, modèle :
    jamais la clé), ou ``(None, None)`` hors mode greffier. Construit AVANT le
    moteur : s'il échoue, l'appelant rejoue l'appel en mode outil
    (``replace(reglages, mode=MODE_OUTIL)``), jamais un appel sans fiche.

    Lève si le service ne se construit pas."""
    if reglages is None or reglages.mode != MODE_GREFFIER:
        return None, None
    from api.services.pipecat.service_factory import create_llm_service

    configuration = configuration_du_greffier(
        user_config, (run_configs or {}).get("greffier_llm")
    )
    service = create_llm_service(
        configuration, correlation_id=correlation_id, usage_context=USAGE_GREFFIER
    )
    return service, {
        "provider": configuration.llm.provider,
        "model": configuration.llm.model,
    }


def versement_du_cout(engine: Any, nom: str, service: Any):
    """[.mark] Lot 4 d'orchestrateur-trois-cerveaux (D12) : de quoi verser les jetons d'un cerveau
    annexe (le greffier, le cerveau de fond) au collecteur de coût de l'appel, sous le nom ``nom``
    et le modèle de son service. Le collecteur est lu à chaque versement (il est posé par le
    circuit d'appel après le moteur) ; absent, rien n'est versé."""
    modele = getattr(getattr(service, "_settings", None), "model", None)

    def verser(entree: int | None, sortie: int | None) -> None:
        collecteur = getattr(engine, "collecteur_de_cout", None)
        if collecteur is not None:
            collecteur.verser_llm(
                nom, modele if isinstance(modele, str) else "", entree, sortie
            )

    return verser


def format_garanti_du_bloc(run_configs: dict | None) -> bool:
    """Lot 5 bis (D11) : la case « Guaranteed format » du greffier (``greffier_llm.format_garanti``),
    décochée si absente ou autre chose qu'un vrai booléen."""
    bloc = (run_configs or {}).get("greffier_llm")
    return isinstance(bloc, dict) and bloc.get("format_garanti") is True


def greffier_du_moteur(
    engine: Any, service: Any, consigne: str | None, format_garanti: bool = False
) -> FrameProcessor | None:
    """Le greffier de l'appel, branché sur le moteur : sa fiche, sa conversation, ses
    notices, ses notes en cours, et (lot B de greffier-conversation) la conversation
    où la réplique de la personne entre et le déclenche. Rend le processeur à placer après le modèle :
    le lecteur de portes, case « portes dans la réponse » allumée (lot A), sinon
    ``None`` (rien à placer). ``None`` aussi hors mode greffier ou sans service.
    Une seule fabrique pour le téléphone et le clavier."""
    reglages = engine.fiche
    if service is None or reglages is None or reglages.mode != MODE_GREFFIER:
        return None
    greffier = Greffier(
        service=service,
        reglages=reglages,
        fiche=lambda: engine._gathered_context,
        messages=lambda: engine.context.get_messages() if engine.context else [],
        notices=engine.notices_fiche,
        notes_en_cours=engine.notes_en_cours,
        consigne=consigne,
        verser_le_cout=versement_du_cout(engine, USAGE_GREFFIER, service),
        format_garanti=format_garanti,
    )
    # Le moteur le clôt à la passe de fin (revue du 04/10).
    engine.greffier = greffier
    # La conversation de l'appel : la réplique confirmée de la personne y entre.
    branche = declencher_a_la_conversation(engine.context, greffier)
    from api.services.pipecat.lecteur_de_portes import lecteur_de_portes_du_moteur

    lecteur = lecteur_de_portes_du_moteur(engine)
    if branche:
        return lecteur
    # Repli : l'ancien déclenchement, après le lecteur s'il y en a un.
    declencheur = DeclencheurDuGreffier(greffier)
    return Pipeline([lecteur, declencheur]) if lecteur is not None else declencheur


CLE_ESTAMPILLE = "greffier_modele"


def preparer_le_greffier(
    reglages: ReglagesFiche | None,
    run_configs: dict | None,
    user_config: Any,
    runtime_configuration: dict,
    *,
    correlation_id: str | None = None,
) -> tuple[ReglagesFiche | None, Any]:
    """Avant le moteur, au téléphone comme au clavier : le service du greffier
    et son estampille (``greffier_modele`` : fournisseur et modèle, jamais la
    clé). Si son service ne se construit pas, l'appel est joué en mode OUTIL
    (le défaut, l'agent note lui-même) : jamais un appel sans fiche. Rend les
    réglages joués et le service (``None`` hors greffier)."""
    try:
        service, estampille = service_du_greffier(
            reglages, run_configs, user_config, correlation_id=correlation_id
        )
    except Exception as erreur:  # noqa: BLE001 -- l'appel part en mode outil
        logger.error(
            f"[fiche] modèle du greffier impossible à construire, appel joué en "
            f"mode outil : {type(erreur).__name__}"
        )
        return replace(reglages, mode=MODE_OUTIL), None
    if estampille is not None:
        runtime_configuration[CLE_ESTAMPILLE] = estampille
    return reglages, service
