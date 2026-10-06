"""[.mark] Le greffier : un second modèle tient la fiche à côté de l'agent, qui parle seulement.

Plan `Labo-agent-vocal/plans/mode-prise-de-notes/`, partie 2 (lots 10 et 11). En mode greffier,
l'agent n'a ni outil de note ni post-scriptum (``consigne_du_mode`` lui dit que la fiche est tenue
à côté de lui). Après chaque réponse de l'agent, le greffier relit **toute** la conversation et la
fiche, et rend la fiche entière en JSON ; seuls les champs **nouveaux ou changés** passent par
``noter(…, source="greffier")`` : les mêmes contrôles que l'outil et le post-scriptum (méthode du
rejeu du 02/10, `agents/nuances-de-feu/essais/2026-10-01-benchmark-small-4/`).

Ce que le module garantit :

- **D9, jamais avant l'agent** : le greffier part à la fin de la réponse de l'agent (sa requête est
  finie) ; **une seule passe en vol** ; une demande arrivée pendant une passe est gardée, une seule,
  et rejouée à la fin de la passe sur la conversation de ce moment-là : **la plus récente gagne**,
  les demandes intermédiaires sont sautées (elles sont comprises dans la relecture complète).
- **Un 429 saute le tour** : journalisé, tracé, la passe suivante relit tout l'appel.
- ⛔ **Il ne coûte jamais l'appel** : il ne bloque ni l'audio, ni la voix, ni l'agent ; une erreur,
  une réponse illisible ou un module en panne sont tracés, rien de plus. La passe de fin reste le filet.
- **Son coût se lit à part** : chaque passe trace ses jetons (`greffier_passes`), et son service
  porte ``usage_context="greffier"``.
- **Sa clé** vient de son bloc ``greffier_llm`` (rangée comme une clé de Dograh, décision d'Evan du
  04/10) ; vide, c'est celle de la conversation. Elle n'est jamais estampillée ni tracée.

⛔ Aucun mot de métier ici : ce que la fiche contient vient des champs déclarés par agent, et ce qui
est propre à un métier va dans la consigne réglable à l'écran (``greffier_consigne``, D10).
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Iterable
from dataclasses import replace
from typing import Any

from loguru import logger

from api.services.pipecat.post_scriptum import lire_la_note
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_ETAT,
    CLE_TOUR,
    MODE_GREFFIER,
    MODE_OUTIL,
    NOTE_DESCRIPTIONS,
    Notices,
    ReglagesFiche,
    _est_vide,
    _propriete,
    derniere_question,
    noter,
    paroles_de_l_appelant,
)
from pipecat.frames.frames import Frame, LLMFullResponseEndFrame
from pipecat.processors.aggregators.llm_context import LLMContext
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


def consigne_du_greffier(reglages: ReglagesFiche, consigne: str | None) -> str:
    """Le prompt système du greffier : la consigne de l'agent (ou la générique),
    puis les champs et le format, ajoutés par le code."""
    champs = "\n".join(
        f"- {champ.nom} : {_propriete(champ)['description']}"
        for champ in reglages.champs
    )
    base = consigne.strip() if consigne and consigne.strip() else CONSIGNE_GENERIQUE
    return "\n\n".join(
        [
            base.rstrip(),
            FORMAT_DE_LA_REPONSE.format(
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


def message_du_greffier(
    reglages: ReglagesFiche,
    fiche: dict,
    messages: Iterable[dict],
    refus: Iterable[dict] = (),
) -> str:
    """Ce que le greffier lit à chaque passe : la fiche actuelle (valeur, sûre
    ou à confirmer), ce que sa passe précédente s'est vu refuser, la
    conversation entière numérotée, la dernière réplique."""
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
        texte = _texte(message.get("content")).strip()
        if not texte:
            continue
        qui = "Personne" if role == "user" else "Agent"
        conversation.append(f"{len(conversation) + 1}. {qui} : {texte}")
    paroles = paroles_de_l_appelant(messages)
    refuses = [
        f"- {r.get('champ')} : {RAISONS_DU_REFUS.get(r.get('raison'), r.get('raison'))}"
        for r in refus
    ]
    blocs = ["# La fiche actuelle\n" + ("\n".join(lignes_fiche) or "(vide)")]
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
    return {
        "jetons_entree": getattr(usage, "prompt_tokens", None),
        "jetons_sortie": getattr(usage, "completion_tokens", None),
    }


async def interroger(
    service: Any, systeme: str, message: str
) -> tuple[str | None, dict]:
    """Une requête au modèle du greffier, en JSON, avec ses jetons. Par le client
    du fournisseur et les paramètres du service (``run_inference`` de Pipecat ne
    rend ni le format JSON ni les jetons) ; sans ce client : ``run_inference``."""
    contexte = LLMContext(messages=[{"role": "user", "content": message}])
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
        params["response_format"] = {"type": "json_object"}
        reponse = await service._client.chat.completions.create(**params)
        return reponse.choices[0].message.content, _jetons(
            getattr(reponse, "usage", None)
        )
    return await service.run_inference(contexte, system_instruction=systeme), {}


def est_un_429(erreur: BaseException) -> bool:
    """Le fournisseur refuse pour cause de quota (D9)."""
    statut = getattr(erreur, "status_code", None) or getattr(
        getattr(erreur, "response", None), "status_code", None
    )
    return statut == 429 or "429" in str(erreur) or "rate limit" in str(erreur).lower()


def champs_a_noter(reglages: ReglagesFiche, fiche: dict, rendue: dict) -> dict:
    """Les champs nouveaux ou changés de la fiche rendue par le greffier : un
    champ inconnu, vide ou identique à la fiche n'est pas renvoyé à ``noter``."""
    par_nom = reglages.par_nom
    a_noter = {}
    for nom, valeur in rendue.items():
        if nom not in par_nom or _est_vide(valeur):
            continue
        if fiche.get(nom) == valeur:
            continue
        a_noter[nom] = valeur
    return a_noter


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
    ):
        self._service = service
        self._reglages = reglages
        self._fiche = fiche
        self._messages = messages
        self._notices = notices
        self._notes_en_cours = notes_en_cours
        self._systeme = consigne_du_greffier(reglages, consigne)
        self._delai = delai
        self._en_vol: asyncio.Task | None = None
        self._encore = False
        # Ce que la passe précédente s'est vu refuser : dit à la suivante.
        self._refus: list[dict] = []
        # Fin de l'appel (revue du 04/10) : plus de passe, et une passe encore
        # en vol n'écrit plus (la passe de fin est passée, la fiche est partie).
        self._clos = False

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
        tache = asyncio.get_running_loop().create_task(self._tourner())
        self._en_vol = tache
        self._notes_en_cours.add(tache)
        tache.add_done_callback(self._notes_en_cours.discard)

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
            message = message_du_greffier(self._reglages, fiche, lus, self._refus)
            texte, jetons = await asyncio.wait_for(
                interroger(self._service, self._systeme, message), self._delai
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
        if self._clos:
            logger.info("[fiche] passe du greffier finie après l'appel : rien écrit")
            self._tracer(TARDIVE, [], debut, **jetons)
            return
        rendue = lire_la_note(texte or "")
        if rendue is None:
            logger.warning("[fiche] greffier illisible : rien noté à cette passe")
            self._tracer(ILLISIBLE, [], debut, **jetons)
            return
        a_noter: dict = {}
        try:
            a_noter = champs_a_noter(self._reglages, self._fiche(), rendue)
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
                ECHEC, sorted(a_noter), debut, erreur=type(erreur).__name__, **jetons
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
        self._tracer(ECRIT if a_noter else RIEN, sorted(a_noter), debut, **jetons)

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


class DeclencheurDuGreffier(FrameProcessor):
    """Placé après le modèle de l'agent : à la fin de chaque réponse, une passe
    du greffier (D9 : jamais avant la requête de l'agent). Laisse tout passer."""

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
    laquelle son bloc s'applique comme une surcharge de modèle. Sans modèle dans
    le bloc et chez Mistral : ``mistral-large-2512`` (D8). Clé vide : celle de
    la conversation (même fournisseur)."""
    from api.services.cles_reference import est_reference
    from api.services.configuration.resolve import resolve_effective_config

    surcharge = {
        cle: valeur
        for cle, valeur in (bloc or {}).items()
        if valeur is not None and valeur != ""
    }
    # Revue du lot 0 bis (06/10) : ce bloc s'applique APRÈS la résolution des clés de la
    # bibliothèque ; une référence y partirait telle quelle chez le fournisseur. Refusée en le
    # disant : l'appelant repasse en mode outil (repli déjà prévu), jamais une clé fausse envoyée.
    if est_reference(surcharge.get("api_key")):
        raise ValueError(
            "The scribe's own key cannot be a key of the key library yet: type it, "
            "or leave it empty to use the conversation's key."
        )
    fournisseur = surcharge.get("provider") or getattr(
        getattr(user_config, "llm", None), "provider", None
    )
    if (
        "model" not in surcharge
        and str(getattr(fournisseur, "value", fournisseur)).lower() == "mistral"
    ):
        surcharge["model"] = MODELE_PAR_DEFAUT_MISTRAL
    configuration = resolve_effective_config(
        user_config, {"llm": surcharge} if surcharge else None
    )
    # Revue du 04/10 : les réglages de génération réglés pour la VOIX (plafond de
    # jetons, pénalités, graine) tronqueraient ou pénaliseraient la fiche JSON du
    # greffier, et ne se voient pas dans sa modale : remis à leur défaut, sauf
    # s'ils sont posés dans son bloc. La température, elle, est à l'écran.
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


def greffier_du_moteur(
    engine: Any, service: Any, consigne: str | None
) -> DeclencheurDuGreffier | None:
    """Le déclencheur du greffier, branché sur le moteur de l'appel : sa fiche,
    sa conversation, ses notices, ses notes en cours. ``None`` hors mode
    greffier ou sans service. Une seule fabrique pour le téléphone et le clavier."""
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
    )
    # Le moteur le clôt à la passe de fin (revue du 04/10).
    engine.greffier = greffier
    return DeclencheurDuGreffier(greffier)


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
