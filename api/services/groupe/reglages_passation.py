"""[.mark] Chantier agents-specialises, lot 6 : les réglages de la passation (A5, A6, A7).

Quatre réglages, lus sur les réglages de l'APPEL (ceux du principal, ``engine.reglages_appel``) :

- ``prechauffage_agents`` : charger à l'avance, au décroché, ce que la construction d'un agent
  appelé lit en base (sans ouvrir aucune connexion de voix ni de modèle) ;
- ``passation_sans_resume_jusqua`` : sous ce nombre de messages de conversation, l'agent appelé
  reçoit l'historique tel quel, sans appel au modèle de résumé ;
- ``un_seul_renvoi_par_appel`` : après un renvoi vers un humain échoué, aucun autre renvoi ;
- ``attente`` : le son d'attente, où il s'applique, et la phrase pont (un filet dit par l'agent qui
  passe la main quand la passation dure plus de ``delai_phrase_pont_s``).

⛔ Zéro perte : les défauts du plan (40 messages, préchauffage vrai, renvoi unique vrai) ne valent
que DANS UN GROUPE (``est_un_groupe``) ; un agent seul sans réglage posé garde le comportement
d'avant. Un réglage posé explicitement vaut partout. Aucun mot de métier : des clés de réglages.

Toutes les fonctions sont pures et ne lèvent jamais : un réglage illisible vaut « absent ».
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from loguru import logger

from api.services.groupe.passations import est_un_groupe

CLE_PRECHAUFFAGE = "prechauffage_agents"
CLE_SANS_RESUME = "passation_sans_resume_jusqua"
CLE_RENVOI_UNIQUE = "un_seul_renvoi_par_appel"
CLE_ATTENTE = "attente"

SANS_RESUME_DEFAUT = 40
DUREE_MIN_DEFAUT_S = 1.2
DELAI_PHRASE_PONT_DEFAUT_S = 2.0
SON_AUCUN = "aucun"

# Ce que l'agent dit quand un transfert vers un humain a déjà échoué dans l'appel (A7). Constante
# générique : aucun mot de métier, l'agent la lit dans le bloc de fin de son étape.
LIGNE_RENVOI_DEJA_ECHOUE = (
    "Un transfert a déjà échoué dans cet appel : tu ne proposes pas de mise en relation, "
    "tu prends la demande toi-même."
)


def _booleen(valeur: Any) -> bool | None:
    return valeur if isinstance(valeur, bool) else None


def prechauffage_actif(reglages: Mapping[str, Any] | None) -> bool:
    """Vrai par défaut dans un groupe, faux pour un agent seul ; le réglage posé l'emporte."""
    try:
        pose = _booleen((reglages or {}).get(CLE_PRECHAUFFAGE))
        return est_un_groupe(reglages) if pose is None else pose
    except Exception:  # noqa: BLE001
        return False


def renvoi_unique_actif(reglages: Mapping[str, Any] | None) -> bool:
    """Vrai par défaut dans un groupe, faux pour un agent seul ; le réglage posé l'emporte."""
    try:
        pose = _booleen((reglages or {}).get(CLE_RENVOI_UNIQUE))
        return est_un_groupe(reglages) if pose is None else pose
    except Exception:  # noqa: BLE001
        return False


def limite_sans_resume(reglages: Mapping[str, Any] | None) -> int | None:
    """Le nombre de messages sous lequel la passation rend l'historique sans résumé.
    ``None`` : jamais (comportement d'avant : résumé dès que la conversation dépasse la
    fenêtre gardée). 40 par défaut dans un groupe ; ``0`` posé = toujours un résumé."""
    try:
        brut = (reglages or {}).get(CLE_SANS_RESUME)
        if isinstance(brut, bool):
            brut = None
        if isinstance(brut, (int, float)):
            return max(0, int(brut))
        return SANS_RESUME_DEFAUT if est_un_groupe(reglages) else None
    except Exception:  # noqa: BLE001
        return None


def passation_courte(nb_messages: int, reglages: Mapping[str, Any] | None) -> bool:
    """La conversation compte-t-elle assez peu de messages pour être rendue sans résumé ?"""
    limite = limite_sans_resume(reglages)
    return limite is not None and nb_messages < limite


@dataclass(frozen=True)
class Attente:
    """Le réglage ``attente``. Tout est facultatif ; absent = la sonnerie d'aujourd'hui, 1,2 s,
    pour la passation entre agents et pour le transfert vers un humain."""

    # None = la sonnerie par défaut ; « aucun » = pas de son ; un objet = un fichier déposé.
    son: Any = None
    # None = la durée minimale d'aujourd'hui (TRANSFER_MIN_HOLD_SECONDS, 1,2 s).
    duree_min_s: float | None = None
    passation: bool = True
    transfert_humain: bool = True
    # La phrase pont (vide = désactivée) et le délai après lequel elle est dite si la passation
    # n'est pas commise.
    phrase_pont: str = ""
    delai_phrase_pont_s: float = DELAI_PHRASE_PONT_DEFAUT_S

    @property
    def sans_son(self) -> bool:
        return self.son == SON_AUCUN

    @property
    def fichier(self) -> tuple[str, str] | None:
        """``(storage_key, storage_backend)`` d'un son déposé, ``None`` sinon."""
        if isinstance(self.son, Mapping):
            cle, backend = self.son.get("storage_key"), self.son.get("storage_backend")
            if isinstance(cle, str) and cle and isinstance(backend, str) and backend:
                return cle, backend
        return None


def attente_de(reglages: Mapping[str, Any] | None) -> Attente:
    """Le réglage ``attente`` de l'appel. ⛔ Ne lève jamais (illisible = défaut)."""
    try:
        brut = (reglages or {}).get(CLE_ATTENTE)
        if not isinstance(brut, Mapping):
            return Attente()
        duree = brut.get("duree_min_s")
        duree = (
            max(0.0, float(duree))
            if isinstance(duree, (int, float)) and not isinstance(duree, bool)
            else None
        )
        passation = _booleen(brut.get("passation"))
        humain = _booleen(brut.get("transfert_humain"))
        phrase = brut.get("phrase_pont")
        delai = brut.get("delai_phrase_pont_s")
        delai = (
            max(0.0, float(delai))
            if isinstance(delai, (int, float))
            and not isinstance(delai, bool)
            and math.isfinite(delai)
            else DELAI_PHRASE_PONT_DEFAUT_S
        )
        return Attente(
            son=brut.get("son"),
            duree_min_s=duree,
            passation=True if passation is None else passation,
            transfert_humain=True if humain is None else humain,
            phrase_pont=phrase.strip() if isinstance(phrase, str) else "",
            delai_phrase_pont_s=delai,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[attente] réglage illisible, défaut gardé : {e!r}")
        return Attente()


async def chemin_du_son(attente: Attente, taux_echantillonnage: int) -> str | None:
    """Le fichier WAV du son déposé, mis en cache local au taux de la ligne ; ``None`` pour la
    sonnerie par défaut (aucun son déposé, ou téléchargement impossible : jamais d'attente muette
    à cause d'un fichier). ⛔ Ne lève jamais."""
    fichier = attente.fichier
    if fichier is None:
        return None
    try:
        from api.services.pipecat.audio_file_cache import get_cached_ambient_noise_path

        return await get_cached_ambient_noise_path(
            fichier[0], fichier[1], taux_echantillonnage
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[attente] son déposé illisible, sonnerie par défaut : {e!r}")
        return None
