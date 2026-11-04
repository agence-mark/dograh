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

from datetime import UTC, datetime
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


# Revue serveur M6 : ce que Dograh garde de l'avis du visiteur. Une fois dans la base du client, plus que le fait qu'il a
# été donné ; sans base rattachée, jamais ses coordonnées ni son texte libre (rien ne les recevra).
CHAMPS_PERSONNELS_DE_L_AVIS = ("contact", "commentaire")


def avis_ecrit() -> dict:
    return {"ecrit": True, "le": datetime.now(UTC).isoformat()}


def avis_sans_donnees_personnelles(avis: dict) -> dict:
    return {k: v for k, v in avis.items() if k not in CHAMPS_PERSONNELS_DE_L_AVIS and k != CLE_GARDE_LE}


# Revue de contrôle, point 8 : un avis gardé EN ENTIER sur le run (base rattachée mais injoignable, ou conversation déjà versée)
# porte la date où il a été gardé ; la purge de nuit le réduit au bout de la durée de conservation du widget.
CLE_GARDE_LE = "garde_le"
# Revue de contrôle, point 9 : la place prise par ``reserver_avis`` expire, pour qu'un processus tué entre la réservation et
# l'écriture ne ferme pas l'avis au visiteur pour toujours.
DELAI_RESERVATION_AVIS_SECONDES = 300


def avis_garde_en_entier(avis: dict, maintenant: datetime | None = None) -> dict:
    return {**avis, CLE_GARDE_LE: (maintenant or datetime.now(UTC)).isoformat()}


def _date(texte: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(texte))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def reservation_expiree(avis: Any, maintenant: datetime | None = None) -> bool:
    """Vrai pour une place d'avis ``{"en_cours": True, "le": …}`` plus vieille que le délai (ou sans date : posée avant ce délai)."""
    if not isinstance(avis, dict) or avis.get("en_cours") is not True:
        return False
    depuis = _date(avis.get("le"))
    return depuis is None or ((maintenant or datetime.now(UTC)) - depuis).total_seconds() > DELAI_RESERVATION_AVIS_SECONDES


def avis_garde_trop_longtemps(avis: Any, avant: datetime) -> bool:
    """Vrai pour un avis gardé en entier depuis avant ``avant`` : à réduire."""
    if not isinstance(avis, dict) or CLE_GARDE_LE not in avis:
        return False
    garde = _date(avis[CLE_GARDE_LE])
    return garde is None or garde < avant


async def avis_entre_dans_la_base(run_id: int, organization_id: int) -> bool:
    """Après ``recevoir_appel`` : l'avis en attente sur le run est réduit au fait qu'il a été donné. Vrai s'il l'a été."""
    from api.db import db_client

    run = await db_client.get_workflow_run(run_id, organization_id=organization_id)
    if run is None or avis_du_run(run) is None:
        return False
    embed = dict(_annotation(run))
    embed["avis"] = avis_ecrit()
    await db_client.update_workflow_run(run.id, annotations={CLE_ANNOTATION: embed})
    return True


def avis_deja_donne(run) -> bool:
    """Le visiteur a déjà laissé son avis sur cette conversation (en attente ou déjà dans la base du client)."""
    avis = _annotation(run).get("avis")
    return isinstance(avis, dict) and not reservation_expiree(avis)


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
        champs["avis"] = {k: v for k, v in avis.items() if k != CLE_GARDE_LE}  # la date de garde reste chez Dograh
    return champs
