"""[.mark] Le connecteur interne « Réservation » (chantier Partie 1, lot 7 : la réservation sur le même contrat que la commande, D18).

Aucun logiciel, aucun Nango : les actions tournent dans le fork et la capacité est une SOURCE (la base du client, par
``services/restauration/source_reservation.py``). Deux actions seulement (E1), comme la commande :

- ``fiche`` : ce qu'elle vient de dire pour sa réservation, une case par chose dite ; le code exécute chaque case remplie, dans son ordre, et rend un
  seul retour (l'enveloppe, ``actions_communes/enveloppe.py``) ; l'exécutant est la porte d'entrée (``services/reservation/porte.py``) ;
- ``lire`` : une lecture qui n'écrit jamais rien (E16).

Les noms, descriptions et cases sont ceux de la version finale du banc, lus dans les textes versés du gabarit (``services/reservation/contrat.py``),
jamais écrits ici ; les cases sans objet dans l'état de l'appel sont cachées (``cases_visibles``, E26). Les cinq outils d'avant (``disponibilites``,
``reserver``, ``modifier_reservation``, ``annuler_reservation``, ``retrouver_reservation``) n'existent plus.
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from api.services.integrations.connectors.catalogue import Action, Connecteur, declarer
from api.services.reservation import contrat


def _jamais(*_args, **_kwargs):
    raise RuntimeError("Une action interne ne passe jamais par le relais.")


async def _executer(action, arguments, ctx, delai_s):
    from api.services.reservation.porte import executer

    return await executer(action, arguments, ctx, delai_s)


def _source_de_la_capacite() -> None:
    import api.services.restauration.source_reservation  # noqa: F401  # la base du client s'inscrit à l'import


_source_de_la_capacite()


async def _sans_tiers(ctx) -> bool:
    """Point de contrôle du lot 7 : la source de l'outil (son réglage ``source``, à défaut le classeur) dit si elle écrit chez un client."""
    from api.services.reservation import source as registre_des_sources
    from api.services.reservation.porte import SOURCE_DE_L_OUTIL

    return await registre_des_sources.sans_tiers((getattr(ctx, "reglages", None) or {}).get(SOURCE_DE_L_OUTIL), ctx)


def _action_ouverte(fiche: dict) -> dict | None:
    """Une réservation commencée (un morceau dit, rien enregistré ni retrouvé) ou un récapitulatif en attente : l'action ouverte, à finir par la fiche."""
    from api.services.reservation.moteur import etat_du_dossier, reservation_commencee

    etat = etat_du_dossier(fiche) if isinstance(fiche, dict) else {}
    question = CONV.question_de(etat)
    if reservation_commencee(etat) or (question and question.get("type") == "recapitulatif"):
        return {"outil": "fiche", "attend_une_reponse": bool(question)}
    return None


def _etat_pour_le_modele(fiche: dict, appel: dict) -> str | None:
    """L'état de la réservation, tenu par le code, donné au modèle à chaque requête de l'étape."""
    from api.services.reservation.etat_pour_le_modele import texte

    return texte(fiche, appel)


def _etat_de_l_appel(fiche: dict) -> str:
    """La ligne de la réservation dans l'état de l'appel montré à l'accueil (lot 6, E25)."""
    from api.services.reservation.etat_pour_le_modele import ligne_de_l_appel

    return ligne_de_l_appel(fiche)


def _dossier_de_la_parole(fiche: dict) -> dict:
    from api.services.reservation.moteur import etat_du_dossier

    return etat_du_dossier(fiche)


def _objet_en_cours(dossier: dict) -> bool:
    from api.services.reservation.etat_pour_le_modele import objet_en_cours

    return objet_en_cours(dossier)


def _texte_du_manque(dossier: dict, _fiche: dict) -> str | None:
    from api.services.reservation.phrases_du_manque import texte_a_dire

    return texte_a_dire(dossier)


RESERVATION = declarer(
    Connecteur(
        nom="reservation",
        sans_tiers=_sans_tiers,
        action_ouverte=_action_ouverte,
        etat_pour_le_modele=_etat_pour_le_modele,
        etat_de_l_appel=_etat_de_l_appel,
        dossier_de_la_parole=_dossier_de_la_parole,
        objet_en_cours=_objet_en_cours,
        texte_du_manque=_texte_du_manque,
        cases_visibles=contrat.cases_visibles,
        porte_la_fiche="fiche",
        porte_la_lecture="lire",
        actions_a_cases=frozenset({"fiche"}),  # la lecture garde ses cases (sujet, jour, personnes), toujours
        forme_selon_l_etat=contrat.forme_selon_l_etat,
        libelle="Réservation (interne)",
        integration="interne",
        interne=True,
        executer_interne=_executer,
        actions=(
            Action(
                nom="fiche",
                description=contrat.description_de("fiche"),
                parametres=contrat.parametres_de_la_fiche(),
                serialise_avec="reservation",
                ecrit=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="lire",
                description=contrat.description_de("lire"),
                parametres=contrat.parametres_de_la_lecture(),
                ecrit=False,
                local=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
        ),
    )
)
