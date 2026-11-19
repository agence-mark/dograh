"""[.mark] Le contrat de la réservation : la forme de la fiche à cases et ses cases selon l'état (chantier Partie 1, lot 7 ; E20, E26, D48).

Même mécanisme que ``commande/contrat.py`` (lot 2). Les TEXTES (noms, descriptions, structure de chaque case) sont lus dans les textes versés du
gabarit (``gabarits/restauration/textes/<version>/outils.json``, rendus de la réservation du banc final, versés par ``verser_textes.py``) ; ce module
tient les RÈGLES, chacune une fonction nommée et testée (reprises de ``banc-b13/appel_b13.py`` ``_outils``, branche réservation) :

- ``annuler_la_reservation`` (renoncer à la réservation commencée) seulement quand une réservation est commencée ; ``annuler_une_reservation_enregistree``
  seulement quand une réservation existe et n'est pas annulée ; jamais les deux (``cases_d_annulation``) ;
- ``retrouver_une_reservation_enregistree`` cachée dès qu'une réservation est commencée, enregistrée, retrouvée, ou qu'un choix attend
  (``retrouver_cachee``) ;
- ``reponse`` : visible sans question, OBLIGATOIRE quand une question était déjà posée à la personne, cachée quand le code l'a créée dans ce tour
  (``reponse_selon_la_question``, B8 point 1).

Aucun mot de métier dans les règles. Le fork ne connaît que les noms vus par le modèle (méthode § 3, règle 1) : jamais la table interne du banc.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from api.services.actions_communes.schema_des_cases import parametres_de_la_fiche as _parametres_de_la_fiche
from api.services.actions_communes.schema_des_cases import parametres_de_la_lecture as _parametres_de_la_lecture
from api.services.actions_communes.schema_des_cases import schema_complet
from api.services.commande.contrat import CLE_DU_TOUR, question_posee
from api.services.gabarits.restauration.textes import CARTE_TEMOIN, rendu, variantes
from api.services.integrations.connectors.catalogue import Parametre
from api.services.reservation import moteur

ETAPE = "reservation"
TYPE_CHOIX = "choix"
CASES_DE_LA_RESERVATION = ("annuler_la_reservation", "annuler_une_reservation_enregistree", "retrouver_une_reservation_enregistree")


@dataclass(frozen=True)
class VueDeLaReservation:
    """Ce que les règles des cases lisent de l'état de l'appel : jamais le brouillon entier, seulement ces faits."""

    commencee: bool = False  # une réservation est commencée (un morceau dit), pas enregistrée ni retrouvée
    existante: bool = False  # une réservation de l'appel ou retrouvée, pas annulée
    objet: bool = False  # une réservation enregistrée dans l'appel ou retrouvée (annulée comprise)
    question: dict | None = None  # {"type": ..., "posee": bool}

    @classmethod
    def depuis_un_dict(cls, d: dict[str, Any]) -> VueDeLaReservation:
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


def vue_de_l_appel(fiche: dict) -> VueDeLaReservation:
    """La vue de l'état d'après la fiche de l'appel (``reservation_etat``) et le tour de la personne."""
    e = moteur.etat_du_dossier(fiche) if isinstance(fiche, dict) else {}
    q = e.get("question")
    return VueDeLaReservation(
        commencee=moteur.reservation_commencee(e), existante=moteur.reservation_existante(e), objet=bool(e.get("cible") or e.get("derniere")),
        question=({"type": q.get("type"), "posee": question_posee(q, (fiche or {}).get(CLE_DU_TOUR, 0))} if isinstance(q, dict) else None),
    )


# --------------------------------------------------------------------------- le schéma complet, lu dans les textes versés


def schema_complet_de_la_fiche(version: str | None = None) -> dict[str, Any]:
    return schema_complet(ETAPE, version)


def parametres_de_la_fiche(version: str | None = None) -> tuple[Parametre, ...]:
    return _parametres_de_la_fiche(ETAPE, None, version)


def parametres_de_la_lecture(version: str | None = None) -> tuple[Parametre, ...]:
    return _parametres_de_la_lecture(ETAPE, version)


def description_de(nom_outil: str) -> str:
    return next(o["function"] for o in rendu(ETAPE, "vide", CARTE_TEMOIN) if o["function"]["name"] == nom_outil)["description"]


# --------------------------------------------------------------------------- les règles des cases, chacune nommée


def tous_les_chemins() -> frozenset[str]:
    from api.services.workflow.cases_selon_l_etat import chemins_du_schema

    return frozenset(chemins_du_schema(schema_complet_de_la_fiche()))


def cases_d_annulation(vue: VueDeLaReservation) -> set[str]:
    """Les cases d'annulation qui ont un objet : jamais les deux d'un même objet ensemble (méthode § 3, règle 2)."""
    return ({"annuler_la_reservation"} if vue.commencee else set()) | ({"annuler_une_reservation_enregistree"} if vue.existante else set())


def retrouver_cachee(vue: VueDeLaReservation) -> bool:
    """Retrouver une réservation d'un appel précédent n'a plus d'objet quand une réservation est commencée, enregistrée, retrouvée, ou qu'un choix attend."""
    return bool(vue.objet or vue.commencee or (vue.question and vue.question.get("type") == TYPE_CHOIX))


def reponse_selon_la_question(vue: VueDeLaReservation) -> str:
    """« libre » sans question ; « absente » pour une question née dans ce tour ; « obligatoire » pour une question déjà posée (B8 point 1)."""
    if not vue.question:
        return "libre"
    return "obligatoire" if vue.question.get("posee") else "absente"


def cases_cachees(vue: VueDeLaReservation) -> set[str]:
    cachees = {"annuler_la_reservation", "annuler_une_reservation_enregistree"} - cases_d_annulation(vue)
    if retrouver_cachee(vue):
        cachees.add("retrouver_une_reservation_enregistree")
    if reponse_selon_la_question(vue) == "absente":
        cachees.add("reponse")
    return cachees


def cases_visibles_de_la_vue(vue: VueDeLaReservation) -> frozenset[str]:
    cachees = cases_cachees(vue)
    return frozenset(c for c in tous_les_chemins() if not any(c == h or c.startswith((h + ".", h + "[]")) for h in cachees))


def forme_de_la_vue(vue: VueDeLaReservation) -> dict[str, Any]:
    """Ce qui change avec l'état : ``reponse`` et ``a_dire`` requises quand une question déjà posée attend, avec le texte de ``reponse`` (variantes
    versées)."""
    if reponse_selon_la_question(vue) != "obligatoire":
        return {"requises": {}, "descriptions": {}}
    return {"requises": {"": ["reponse", "a_dire"]}, "descriptions": {"reponse": variantes()["reponse.obligatoire"]}}


def cases_visibles(fiche: dict) -> frozenset[str]:
    """Pour le connecteur (``Connecteur.cases_visibles``) : les chemins des cases qui ont un objet maintenant."""
    return cases_visibles_de_la_vue(vue_de_l_appel(fiche))


def forme_selon_l_etat(fiche: dict) -> dict[str, Any]:
    return forme_de_la_vue(vue_de_l_appel(fiche))
