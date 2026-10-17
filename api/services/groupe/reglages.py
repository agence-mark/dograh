"""[.mark] Chantier agents-specialises, lot 10 (A10) : les réglages d'un groupe d'agents.

Un **groupe** = un agent principal et ses agents spécialisés. Le principal règle l'appel ;
chaque spécialisé règle son graphe. Les réglages « communs » sont portés par le principal et
**recopiés** dans chaque spécialisé à chaque enregistrement du principal, pour qu'un
spécialisé essayé seul fonctionne comme dans le groupe.

⛔ La liste des clés communes est écrite **ici, en un seul endroit** (``CLES_COMMUNES``), lue par
la recopie (ce module) et par l'écran du groupe (lot 13 : un test vérifie que chaque clé exposée
à l'écran est dans ``CLES_COMMUNES`` ou ``CLES_PROPRES``).

Le cerveau est **détachable** (Evan, 16/10) : ``cerveau_propre: true`` sur un spécialisé garde
son propre cerveau, c'est-à-dire le modèle de langage de sa configuration de modèles
(``CHEMINS_CERVEAU``) et les réglages qui suivent le cerveau (``CLES_SUIVENT_LE_CERVEAU``).
La voix, elle, reste commune : une seule voix pour tout le groupe (lot 3 d'orchestrateur-trois-cerveaux, D7 : même hors groupe, une seule voix par appel ; `cerveau_propre` ne la change jamais).

Tout est pur (aucune base, aucune levée) ; aucun mot de métier : des noms de clés de réglages.
"""

from __future__ import annotations

import copy
from typing import Any, Iterable, Mapping

from loguru import logger

from api.services.groupe.passations import CLE_AGENT_PRINCIPAL, CLE_AGENTS_SPECIALISES

CLE_CERVEAU_PROPRE = "cerveau_propre"

# Les réglages du principal, propres au groupe (lot 6 pour le moteur, lot 12 pour l'écran).
CLE_PLAFOND_PASSATIONS = "passations_max_par_appel"
CLE_SANS_RESUME = "passation_sans_resume_jusqua"
CLE_PRECHAUFFAGE = "prechauffage_agents"
CLE_ATTENTE = "attente"
CLE_UN_SEUL_RENVOI = "un_seul_renvoi_par_appel"
CLE_TRANSFERT_HUMAIN = "transfert_humain"
CLES_DU_GROUPE = (
    CLE_PLAFOND_PASSATIONS,
    CLE_SANS_RESUME,
    CLE_PRECHAUFFAGE,
    CLE_ATTENTE,
    CLE_UN_SEUL_RENVOI,
    CLE_TRANSFERT_HUMAIN,
)

# Le lien entre un principal et ses spécialisés : jamais recopié (il est posé par les routes
# du groupe, chacun de son côté).
CLES_DE_LIEN = (CLE_AGENT_PRINCIPAL, CLE_AGENTS_SPECIALISES)

# Où vit le cerveau (le modèle de langage) dans la configuration de modèles. Le reste de ces
# objets (voix, transcription, embeddings) est commun.
CHEMINS_CERVEAU: tuple[tuple[str, ...], ...] = (
    ("model_overrides", "llm"),
    ("model_configuration_v2_override", "byok", "pipeline", "llm"),
    ("model_configuration_v2_override", "byok", "realtime", "llm"),
)

# Les réglages qui suivent le cerveau : recopiés du principal tant que le cerveau est rattaché,
# gardés par le spécialisé quand il a son propre cerveau.
CLES_SUIVENT_LE_CERVEAU = (
    "reflexion_de_relance",
    "trace_requetes_modele",
    "relance_apres_outil",
    # Lot 4 d'orchestrateur-trois-cerveaux (D13) : le cerveau de fond d'un agent est une brique
    # de SON cerveau (modèle, consigne, outils, délai). Un spécialisé au cerveau rattaché prend
    # ceux du principal ; avec « Cerveau propre », il garde les siens.
    "travail_actif",
    "travail_llm",
    "travail_consigne",
    "travail_outils",
    "travail_delai_max_s",
)

# Thème 1 (Agent), partie commune : les réglages du groupe et ceux qui suivent le cerveau.
# Thème 2 (Briques) : la configuration de modèles (voix et cerveau).
# Thèmes 3 à 8 : tout, sauf ce qui dépend de l'agent lui-même (voir CLES_PROPRES).
CLES_COMMUNES: tuple[str, ...] = (
    # 1 Agent (commun)
    *CLES_DU_GROUPE,
    "filet_de_fin",
    "reflexion_de_relance",
    "trace_requetes_modele",
    # 2 Briques
    "model_overrides",
    "model_configuration_v2_override",
    "mark_per_service_override",
    "travail_actif",
    "travail_llm",
    "travail_consigne",
    "travail_outils",
    "travail_delai_max_s",
    # 3 Écoute
    "conversion_nombres_transcription",
    "variables_reference",
    "verification_communes",
    "variables_commune",
    "controle_donnees",
    "variables_telephone",
    "variables_code_postal",
    "variables_courriel",
    "variables_date",
    "sons_communes",
    "verification_voies",
    "lecture_epellation",
    "lexique_metier",
    "sons_lexique",
    "dictionary",
    "audio_in_noise_filter",
    # 4 Tour de parole
    "turn_stop_strategy",
    "smart_turn_stop_secs",
    "user_speech_timeout",
    "stt_ttfs_p99_latency",
    "user_turn_stop_timeout",
    "turn_wait_for_transcript",
    "turn_start_strategy",
    "turn_start_min_words",
    "turn_start_use_interim",
    "mute_until_first_bot_complete",
    "mute_during_function_call",
    "relance_apres_outil",
    "mute_engine_callback",
    "mute_first_speech",
    "mute_always",
    "accueil_interruptible",
    "accueil_mots_minimum",
    "vad_confidence",
    "vad_start_secs",
    "vad_stop_secs",
    "vad_min_volume",
    "audio_idle_timeout",
    "smart_turn_pre_speech_ms",
    "smart_turn_max_duration_secs",
    "filter_incomplete_user_turns",
    "incomplete_short_timeout",
    "incomplete_long_timeout",
    # 5 Voix
    "tts_markdown_filter_enabled",
    "tts_text_aggregation_mode",
    "tts_push_silence_after_stop",
    "tts_silence_time_s",
    "interdire_nom_appelant",
    "interdire_civilite_appelant",
    "relecture_des_numeros",
    "tts_replacements",
    "ambient_noise_configuration",
    "tts_cache_enabled",
    # 6 Rythme de l'appel
    "max_user_idle_timeout",
    "user_idle_prompt",
    "user_idle_max_prompts",
    "user_idle_goodbye_prompt",
    "raccrochage_silence_agent_s",
    "max_call_duration",
    # 7 Données de l'appel
    "fiche_au_fil_de_leau",
    "fiche_mode_de_note",
    "portes_dans_la_reponse",
    "ordre_de_la_reponse",
    "indices_des_modules",
    "etiquettes_des_etapes",
    "fiche_deja_connu",
    "transfert_garanti",
    "phrase_sans_redemande",
    "greffier_llm",
    "greffier_consigne",
    "fiche_champs",
    "apres_appel",
    "equipe_connue",
    "verification_appelant",
    "call_dispositions",
    "transcript_configuration",
    "context_compaction_enabled",
    "external_pbx_field_mappings",
    "external_pbx_lead_headers",
    # 8 Établissement (commun : le repli de panne et la messagerie)
    "panne",
    "voicemail_detection",
)

# Ce qui reste à chaque agent : son graphe et ce qui ne vaut que pour lui. La fiche
# d'établissement et ses données propres (horaires, adresse) : un spécialisé lit celle de
# l'appel (thème 8 « celui de l'appel »), jamais une copie de celle du principal.
CLES_PROPRES: tuple[str, ...] = (
    "generer_schema_parcours",
    "text_chat_inactivity_timeout_seconds",
    "etablissement_id",
    "horaires_ouverture",
    "adresse_etablissement",
    CLE_CERVEAU_PROPRE,
    *CLES_DE_LIEN,
)


def _chemin(config: Mapping[str, Any] | None, chemin: tuple[str, ...]) -> Any:
    courant: Any = config
    for cle in chemin:
        if not isinstance(courant, Mapping) or cle not in courant:
            return None
        courant = courant[cle]
    return courant


def _poser(config: dict, chemin: tuple[str, ...], valeur: Any) -> bool:
    """Pose ``valeur`` au bout du chemin SANS créer de branche : un principal qui n'a pas
    cette branche (autre mode de modèles) n'en reçoit pas une inventée. Rend vrai si posé."""
    courant: Any = config
    for cle in chemin[:-1]:
        if not isinstance(courant, dict) or not isinstance(courant.get(cle), dict):
            return False
        courant = courant[cle]
    if not isinstance(courant, dict):
        return False
    courant[chemin[-1]] = copy.deepcopy(valeur)
    return True


def a_son_cerveau(reglages_specialise: Mapping[str, Any] | None) -> bool:
    """Le spécialisé a-t-il détaché son cerveau (case « Cerveau propre ») ?"""
    try:
        return (reglages_specialise or {}).get(CLE_CERVEAU_PROPRE) is True
    except Exception:  # noqa: BLE001
        return False


def recopier(
    reglages_principal: Mapping[str, Any] | None,
    reglages_specialise: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Les réglages d'un spécialisé après recopie de ceux du principal.

    - chaque clé commune est prise au principal (absente chez lui : retirée du spécialisé, le
      défaut revient) ;
    - les clés propres, et toute clé inconnue, restent celles du spécialisé ;
    - cerveau détaché (``cerveau_propre``) : le modèle de langage du spécialisé est regreffé
      dans la configuration de modèles recopiée, et les réglages qui suivent le cerveau
      restent les siens ;
    - idempotent : recopier deux fois donne le même résultat ;
    - pure : aucune des deux entrées n'est modifiée.
    """
    principal = dict(reglages_principal or {})
    specialise = dict(reglages_specialise or {})
    resultat = copy.deepcopy(specialise)
    propre = a_son_cerveau(specialise)

    for cle in CLES_COMMUNES:
        if propre and cle in CLES_SUIVENT_LE_CERVEAU:
            continue
        if cle in principal:
            resultat[cle] = copy.deepcopy(principal[cle])
        else:
            resultat.pop(cle, None)

    if propre:
        for chemin in CHEMINS_CERVEAU:
            cerveau = _chemin(specialise, chemin)
            if cerveau is None:
                continue
            if _poser(resultat, chemin, cerveau):
                continue
            if chemin[0] not in resultat and chemin[0] in specialise:
                # Revue du 16/10 : le principal n'a aucune configuration de modèles (il hérite de
                # l'organisation) ; le spécialisé garde la sienne telle quelle, jamais effacée.
                resultat[chemin[0]] = copy.deepcopy(specialise[chemin[0]])
            else:
                # Le principal a une autre branche de modèles (autre mode) : le cerveau propre
                # du spécialisé ne peut pas être regreffé, il prend celui du principal.
                logger.warning(
                    "groupe : cerveau propre non regreffé (branche absente chez le principal) : "
                    + ".".join(chemin)
                )
    return resultat


def cles_sans_classement(cles: Iterable[str]) -> list[str]:
    """Les clés données qui ne sont ni communes ni propres (pour le test de l'écran)."""
    connues = set(CLES_COMMUNES) | set(CLES_PROPRES)
    return sorted(c for c in cles if c not in connues)
