"""[.mark] L'enveloppe de retour unique d'une fiche (chantier Partie 1, lot 2, étape 7 ; méthode § 3, « le retour du code au modèle »).

Toujours la même forme : un statut en liste fermée, les résultats (un par opération), les faits, la prochaine question numérotée (``Q-n``), la raison,
les choix et ``a_faire`` en cas de refus. Le code ne montre JAMAIS au modèle une phrase qu'il dit lui-même : il dit seulement qu'il la dit
(``prix_dit_par_le_code_apres_ta_phrase``, ``dit_avant_ta_phrase`` à ``true`` ; B10 § 1 point 4, B11 § 1 point 2).

Chaque raison de refus est rangée « fiche » (``REFUS_DE_LA_FICHE`` : la forme de la fiche, ou une valeur qui ne vient pas d'elle ; B12 § 2,
décision 1) ou « métier » (``RAISONS_DU_METIER`` : hors zone, rupture, horaire plein, minimum…). Ce que la parole fait d'un refus de la fiche est
au lot 6. Aucun mot de métier dans les noms : les raisons du métier sont des faits du module, jamais une consigne.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

STATUTS = ("FAIT", "PARTIEL", "A_PRECISER", "INTROUVABLE", "LU", "ENREGISTREE", "ANNULEE", "REJETEE")

CLES = (
    "statut", "resultats", "faits", "manque", "texte_a_dire", "question", "a_faire", "raison", "explication", "choix", "refus", "fiche_appliquee",
    "cases_executees", "cases_refusees", "cases_non_executees_car_liees", "rien_ajoute", "deja_dit_par_le_code", "regle_dite_par_le_code",
)

# B12 § 2, décision 1 (liste fermée, recopiée de `banc-b13/appel_b13.py:354`), plus ``choix_hors_liste`` quand les mots de la valeur ne sont pas
# dans sa phrase du tour.
REFUS_DE_LA_FICHE = frozenset({
    "arguments_illisibles", "article_aussi_choix_d_une_etape", "article_deja_choix_de_la_formule", "case_sans_objet", "cases_pas_ouvertes", "fiche_vide",
    "format", "format_illisible", "operation_inconnue", "outil_inconnu", "question_inconnue", "recapitulatif_pas_accepte", "reponse_hors_liste",
    "reponse_manquante", "valeur_hors_liste", "valeur_pas_dans_ses_mots", "choix_hors_liste",
})

# Les refus du métier : la phrase du modèle qui dit la raison reste dite (B12, décision 1). Une raison nouvelle d'un module entre ici ou dans
# ``REFUS_DE_LA_FICHE`` dans le même commit (``test_chaque_raison_rangee_fiche_ou_metier``).
RAISONS_DU_METIER = frozenset({
    "hors_zone", "rupture", "complet_a_cette_heure", "horaire_ferme", "minimum_non_atteint", "hors_sous_ensemble", "article_introuvable", "code_inconnu",
    "groupe_trop_grand", "plafond_d_operations", "quantite_inferieure_a_un", "deja_fait", "message_deja_laisse_dans_cet_appel", "numero_masque",
    "numero_incomplet", "numero_de_commande_exige",
    # Chantier Partie 1, lot 7 : les refus de la réservation (détail du classeur : ``db/bases_clients/capacite.py``, ``restauration_reservation.py``)
    "passe", "trop_tot", "trop_loin", "hors_service", "ferme", "type_ferme", "passee", "plus_modifiable", "annulation_a_confirmer", "choix_non_compris", "choix_non_compris_deux_fois", "choix_manquant",
    "choix_de_plusieurs_etapes", "plusieurs_choix", "deja_une_reservation_dans_cet_appel", "rien_a_faire", "commande_introuvable", "capacite_non_reglee",
    # lot 12 (PRX1, PRX8, PRX9) : hors de sa plage à ce moment, au-delà du maximum par commande, avant le délai minimal, sous le minimum de personnes
    "indisponible_a_ce_moment", "quantite_au_dela_du_maximum", "delai_minimal_non_respecte", "personnes_minimales_non_atteintes",
    # lot 13 (QTE1, QTE2) : un article qui ne se vend pas au poids, un poids à dire ou illisible, une quantité hors du lot de vente
    "pas_vendu_au_poids", "poids_a_dire", "poids_illisible", "multiple_du_lot",
    # lot 11 (formules) : un choix sans la déclinaison de la taille (FOR6), un mode que la formule n'a pas (FOR7), deux alternatives mêlées (FOR12), un nombre de
    # personnes que la carte n'a pas (FOR10)
    "choix_sans_la_taille", "mode_non_permis", "alternatives_melangees", "personnes_hors_liste",
})

assert not REFUS_DE_LA_FICHE & RAISONS_DU_METIER, "une raison est rangée « fiche » OU « métier », jamais les deux"

FORMAT_QUESTION = re.compile(r"^Q-[1-9]\d*$")
REPONSES_FERMEES = ("accepte", "refuse", "autre")
# Les phrases que le code dit lui-même et que le retour ne montre jamais (seulement le drapeau qui dit qu'il les dit).
DRAPEAUX_DE_PAROLE_DU_CODE = ("prix_dit_par_le_code_apres_ta_phrase", "dit_avant_ta_phrase")
CLES_INTERDITES = ("phrase_du_code", "texte_du_prix", "phrase_de_la_regle", "chiffre_dit")


class EnveloppeInvalide(ValueError):
    """Un retour qui ne respecte pas l'enveloppe : un bug du code, jamais montré au modèle."""


def rangee(raison: str) -> str | None:
    """« fiche », « metier », ou ``None`` pour une raison que personne n'a rangée."""
    if raison in REFUS_DE_LA_FICHE:
        return "fiche"
    if raison in RAISONS_DU_METIER:
        return "metier"
    return None


@dataclass
class Question:
    """La prochaine question, numérotée par le code ; c'est le modèle qui la pose (interdit n° 5 du brief)."""

    id: str
    type: str
    texte: str
    reponses: tuple[str, ...] = REPONSES_FERMEES

    def __post_init__(self) -> None:
        if not FORMAT_QUESTION.match(self.id):
            raise EnveloppeInvalide(f"identifiant de question {self.id!r} : « Q-n » attendu (E5)")
        if not self.reponses:
            raise EnveloppeInvalide("une question rend ses réponses possibles")

    def vers_json(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.type, "texte": self.texte, "reponses": list(self.reponses)}


@dataclass
class Enveloppe:
    statut: str
    resultats: list[dict[str, Any]] = field(default_factory=list)
    faits: dict[str, Any] = field(default_factory=dict)
    question: Question | None = None
    raison: str | None = None
    choix: list[Any] | None = None
    a_faire: str | None = None
    explication: str | None = None
    plus: dict[str, Any] = field(default_factory=dict)  # les autres clés de ``CLES`` (cases exécutées, refusées, liées…)

    def vers_json(self) -> dict[str, Any]:
        sortie: dict[str, Any] = {"statut": self.statut, "resultats": self.resultats, "faits": self.faits}
        if self.question is not None:
            sortie["question"] = self.question.vers_json()
        for cle in ("raison", "choix", "a_faire", "explication"):
            if getattr(self, cle) is not None:
                sortie[cle] = getattr(self, cle)
        sortie.update(self.plus)
        verifier(sortie)
        return sortie


def verifier(retour: dict[str, Any]) -> None:
    """Lève ``EnveloppeInvalide`` si le retour sort de l'enveloppe : statut hors liste, clé inconnue, question mal numérotée, raison non rangée,
    phrase du code montrée au modèle."""
    if retour.get("statut") not in STATUTS:
        raise EnveloppeInvalide(f"statut {retour.get('statut')!r} hors de {STATUTS}")
    inconnues = set(retour) - set(CLES) - set(DRAPEAUX_DE_PAROLE_DU_CODE)
    if inconnues:
        raise EnveloppeInvalide(f"clés hors de l'enveloppe : {sorted(inconnues)}")
    q = retour.get("question")
    if q is not None:
        Question(**{k: (tuple(v) if k == "reponses" else v) for k, v in q.items()})
    for drapeau in DRAPEAUX_DE_PAROLE_DU_CODE:
        if drapeau in retour and retour[drapeau] is not True:
            raise EnveloppeInvalide(f"{drapeau} vaut true ou n'est pas là : la phrase elle-même n'est jamais dans le retour")
    _sans_phrase_du_code(retour)
    for raison in _raisons(retour):
        if rangee(raison) is None:
            raise EnveloppeInvalide(f"raison {raison!r} rangée ni « fiche » ni « métier »")


def _sans_phrase_du_code(x: Any) -> None:
    if isinstance(x, dict):
        for k, v in x.items():
            if k in CLES_INTERDITES:
                raise EnveloppeInvalide(f"le retour montre une phrase du code ({k})")
            _sans_phrase_du_code(v)
    elif isinstance(x, list):
        for v in x:
            _sans_phrase_du_code(v)


def _raisons(x: Any) -> list[str]:
    """Les raisons de refus du retour : la sienne et celles de ses résultats et refus ; jamais les faits (un fait du module peut avoir sa
    propre « raison », qui n'est pas un refus : une remise qui n'a rien à dire)."""
    out: list[str] = []
    if isinstance(x, dict):
        for k, v in x.items():
            if k == "faits":
                continue
            if k == "raison" and isinstance(v, str):
                out.append(v)
            else:
                out += _raisons(v)
    elif isinstance(x, list):
        for v in x:
            out += _raisons(v)
    return out
