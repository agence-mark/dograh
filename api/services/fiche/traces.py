"""[.mark] Ce que les modules de lecture ont déjà établi, au tour même (lot D d'agent-leger-greffier).

En mode greffier, la fiche a un tour de retard : le greffier relit la conversation APRÈS la
réponse de l'agent. Les modules de lecture, eux, ont lu la parole de l'appelant AVANT le
modèle, et laissé leurs traces dans l'appel (``communes_verifiees``, ``nombres_lus``,
``epellations_lues``). Ce module en tire les valeurs SÛRES, champ par champ, pour deux
lecteurs : une action qui a besoin d'un champ maintenant (``connectors/champs_requis.py``)
et le balayage de fin d'appel (un champ resté vide).

Quel champ reçoit quoi se lit dans les réglages de l'agent, jamais dans un nom écrit ici :
le lecteur du champ (``commune``), la reconnaissance des champs (``variables_code_postal``,
``variables_telephone``), le nombre de chiffres déclaré (``chiffres``), un champ de nom.
⛔ Seulement ce qu'un module a marqué sûr ; une commune « à confirmer » n'est jamais prise.
Le numéro de téléphone n'a pas de statut chez le lecteur des nombres : il est pris complet
seulement (le nombre de chiffres déclaré, sinon 9 au moins).
⛔ Une épellation (revue du 10/10) : seulement au tour même, et seulement si la fiche a UN seul
champ de nom. Sinon un mot épelé remplirait le nom et le prénom à la fois, ou un nom avec une
rue épelée trois tours plus tôt.
"""

from __future__ import annotations

import re
from typing import Any

from api.schemas.fiche_agent import est_un_champ_de_nom
from api.services.pipecat.verification_communes import CLE_TOUR


def _correspond(nom: str, motifs: tuple[str, ...]) -> bool:
    nom = nom.strip().lower()
    for motif in motifs:
        motif = motif.strip().lower()
        if not motif:
            continue
        if motif.endswith("*") and nom.startswith(motif[:-1]):
            return True
        if nom == motif:
            return True
    return False


def _dernier(entrees: Any, garder) -> dict | None:
    for entree in reversed(entrees if isinstance(entrees, list) else []):
        if isinstance(entree, dict) and garder(entree):
            return entree
    return None


def _numero_complet(champ: Any, chiffres: str, motifs: dict) -> bool:
    """Un numéro lu va au champ qui déclare ce nombre de chiffres ; à un champ reconnu
    comme téléphone sans nombre déclaré, seulement complet (9 chiffres au moins)."""
    attendus = getattr(champ, "chiffres", None)
    if attendus:
        return attendus == len(chiffres)
    return _correspond(champ.nom, motifs.get("telephone", ())) and len(chiffres) >= 9


def valeurs_des_traces(reglages: Any, fiche: dict) -> dict[str, str]:
    """Champ de la fiche -> valeur sûre lue par un module. Ne lève jamais."""
    if not isinstance(fiche, dict) or reglages is None:
        return {}
    motifs: dict = getattr(reglages, "motifs_des_types", None) or {}
    sortie: dict[str, str] = {}
    try:
        commune = _dernier(
            fiche.get("communes_verifiees"),
            lambda e: (
                e.get("statut") == "sure"
                and isinstance(e.get("commune_retenue"), dict)
                and e["commune_retenue"].get("nom")
            ),
        )
        retenue = (commune or {}).get("commune_retenue") or {}
        codes_de_la_commune = list(retenue.get("codes_postaux") or [])
        code_postal = _dernier(
            fiche.get("nombres_lus"),
            lambda e: (
                e.get("type") == "code_postal"
                and e.get("statut") == "sure"
                and e.get("retenu")
            ),
        )
        telephone = _dernier(
            fiche.get("nombres_lus"), lambda e: e.get("type") == "telephone"
        )
        chiffres_tel = re.sub(r"\D", "", str((telephone or {}).get("ecrit") or ""))
        champs_de_nom = [c for c in reglages.champs if est_un_champ_de_nom(c)]
        tour = fiche.get(CLE_TOUR)
        epellation = (
            _dernier(
                fiche.get("epellations_lues"),
                lambda e: e.get("epele") and tour is not None and e.get("tour") == tour,
            )
            if len(champs_de_nom) == 1
            else None
        )
        for champ in reglages.champs:
            nom = champ.nom
            if commune and champ.lecteur_effectif == "commune":
                sortie[nom] = str(retenue["nom"])
            elif _correspond(nom, motifs.get("code_postal", ())) and (
                code_postal or len(codes_de_la_commune) == 1
            ):
                # Un code postal dit et sûr ; sinon celui de la commune sûre, s'il est unique.
                sortie[nom] = str(
                    code_postal["retenu"] if code_postal else codes_de_la_commune[0]
                )
            elif chiffres_tel and _numero_complet(champ, chiffres_tel, motifs):
                sortie[nom] = chiffres_tel
            elif epellation and est_un_champ_de_nom(champ):
                sortie[nom] = str(epellation["epele"])
    except Exception:  # noqa: BLE001 -- une trace illisible ne coûte rien
        return sortie
    return sortie
