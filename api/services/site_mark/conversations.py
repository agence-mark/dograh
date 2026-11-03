"""[.mark] U10 / S3 : ce qu'une conversation du widget dit d'elle-même à la base du client.

Une conversation du widget est une VRAIE conversation (canal ``site``), jamais un « essai » : c'est ce qui la
distingue d'un test lancé depuis l'écran de Dograh (même moteur de navigateur, mais pas de widget). Le signe est posé
par le serveur à ``/init`` et nulle part ailleurs :

* l'annotation ``embed`` du run (``source = embed_widget``), écrite par ``/init`` (une page ne peut pas la poser) ;
* la clé réservée ``canal_mark = site`` du contexte du run (``CLES_MARK_INTERDITES`` : jamais acceptée d'une page).

La page (son chemin, sans paramètres ni ancre) vient du contexte de la page en liste blanche (``page_url``) ; le mode
(voix, écrit, voix puis écrit) vient de la modalité du run et de la liste ``modes`` que le champ de saisie pendant
l'appel (S5) ajoute à l'annotation quand le visiteur écrit en cours de voix.
"""

from __future__ import annotations

from typing import Any

from api.services.site_mark import chemins as lib_chemins
from api.services.site_mark.contexte_public import CANAL_SITE, CLE_CANAL
from api.services.site_mark.demarrage import CLE_ANNOTATION, SOURCE_WIDGET

MODE_VOIX = "voix"
MODE_ECRIT = "ecrit"
MODE_VOIX_PUIS_ECRIT = "voix_puis_ecrit"

# Conservation de ce que le widget garde sur le visiteur dans la base de Dograh (adresse IP, navigateur) : écrite
# ici, appliquée par la purge de nuit (``purger_sessions``). La conversation, elle, suit la conservation des appels.
CONSERVATION_SESSIONS_JOURS = 30


def _annotation(run) -> dict:
    annotations = getattr(run, "annotations", None)
    embed = annotations.get(CLE_ANNOTATION) if isinstance(annotations, dict) else None
    return embed if isinstance(embed, dict) else {}


def est_du_widget(run) -> bool:
    """Le run vient-il du widget public d'un site ? Faux pour un test de l'écran, un appel téléphonique, un simulé."""
    if _annotation(run).get("source") == SOURCE_WIDGET:
        return True
    initial = getattr(run, "initial_context", None)
    return isinstance(initial, dict) and initial.get(CLE_CANAL) == CANAL_SITE


def page_de(run) -> str | None:
    """Le chemin de la page où la conversation a eu lieu, ou ``None`` (page non transmise ou illisible)."""
    initial = getattr(run, "initial_context", None)
    brut = initial.get("page_url") if isinstance(initial, dict) else None
    if not isinstance(brut, str) or not brut.strip():
        return None
    try:
        return lib_chemins.normaliser(brut)
    except lib_chemins.CheminInvalide:
        return None


def mode_de(run) -> str:
    """``voix``, ``ecrit`` ou ``voix_puis_ecrit``."""
    embed = _annotation(run)
    modes = embed.get("modes")
    modes = [m for m in modes if isinstance(m, str)] if isinstance(modes, list) else []
    if embed.get("modality") == "text" or getattr(run, "mode", None) == "textchat":
        return MODE_ECRIT
    if MODE_ECRIT in modes:
        return MODE_VOIX_PUIS_ECRIT
    return MODE_VOIX


def avis_du_run(run) -> dict | None:
    """L'avis que le visiteur a laissé AVANT que la base du client ait reçu la conversation (gardé sur le run)."""
    avis = _annotation(run).get("avis")
    return avis if isinstance(avis, dict) and "etoiles" in avis else None


def avis_deja_donne(run) -> bool:
    """Le visiteur a déjà laissé son avis sur cette conversation (en attente ou déjà dans la base du client)."""
    return isinstance(_annotation(run).get("avis"), dict)


def champs_du_site(run) -> dict[str, Any]:
    """Les clés de l'envoi de ``recevoir_appel`` propres à une conversation du site ; ``{}`` pour tout autre appel."""
    if not est_du_widget(run):
        return {}
    champs: dict[str, Any] = {"canal": CANAL_SITE, "mode_site": mode_de(run)}
    page = page_de(run)
    if page:
        champs["page"] = page
    avis = avis_du_run(run)
    if avis:
        champs["avis"] = avis
    return champs
