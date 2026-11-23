"""[.mark] Le contrat de la commande : la forme de la fiche à cases et ses cases selon l'état et la carte (chantier Partie 1, lot 2 ; E26, D48).

Les TEXTES (noms, descriptions, structure de chaque case) ne sont pas écrits ici : ils sont lus dans les textes versés du gabarit
(``gabarits/restauration/textes/<version>/outils.json``, copiés mot pour mot de la version finale du banc par ``verser_textes.py``). Ce module tient
les RÈGLES, chacune une fonction nommée et testée (reprises de ``banc-b13/commande_b13.py`` ``cases_ouvertes`` et ``props_v6``,
``appel_b13.py`` ``outils``, ``formule_b13.py`` ``forme_fiche``, ``briques_b13.py`` ``cases_de_la_carte``) :

- ``annuler_la_commande`` visible seulement quand une commande est commencée et pas enregistrée, ``annuler_une_commande_enregistree`` seulement
  après l'enregistrement (jamais les deux : ``cases_d_annulation``) ;
- moyen de paiement, billet, téléphone, prénom seulement quand le récapitulatif est en attente ou accepté (``cases_de_fin_ouvertes``) ; le billet
  seulement en espèces, ou le récapitulatif en attente (``billet_visible``) ;
- changer, retirer, vider seulement quand il y a des lignes (``cases_des_lignes``) ;
- ``reponse`` seulement quand une question attend, OBLIGATOIRE quand elle était déjà posée à la personne, cachée quand le code l'a créée dans ce
  tour (``reponse_selon_la_question``) ; une question d'étape cache ``sens`` et rend ``valeurs`` requise (``forme_de_la_question_d_etape``) ;
- les cases des briques n'existent que si la carte en a l'objet (``cases_de_la_carte``).

Le mode, le moyen de paiement et la variante sont des listes fermées construites au décroché (``liste_du_contexte``), « autre » compris.
Aucun mot de métier dans les règles : les libellés viennent de la carte et de l'établissement.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from api.services.actions_communes.schema_des_cases import parametre_de_la_case, schema_complet
from api.services.commande import panier as P
from api.services.gabarits.restauration.textes import CARTE_TEMOIN, rendu, variantes
from api.services.integrations.connectors.catalogue import Parametre

# Les listes fermées construites au décroché, lues dans le contexte de l'appel (``Parametre.liste_du_contexte``) ; chacune finit par « autre » (E27).
LISTE_DES_MODES = "commande_modes"
LISTE_DES_MOYENS = "commande_moyens"
LISTE_DES_VARIANTES = "commande_variantes"
AUTRE = "autre"
LISTES = {"mode_de_retrait": LISTE_DES_MODES, "moyen_de_paiement": LISTE_DES_MOYENS, "moyen_reste": LISTE_DES_MOYENS, "ajouter[].variante": LISTE_DES_VARIANTES,
          "changer_quantite[].variante": LISTE_DES_VARIANTES}

CASES_DE_FIN = ("moyen_de_paiement", "rendu_sur", "part", "moyen_reste", "telephone", "prenom")  # C2 bis : le règlement partagé (part, moyen_reste) s'ouvre avec le moyen
CASES_DES_LIGNES = ("changer_quantite", "retirer_article", "vider_le_panier")
CASES_QUI_CHANGENT_LA_COMMANDE = ("ajouter", *CASES_DES_LIGNES, "mode_de_retrait", "adresse", "commune", "heure")  # DC5 : rien de cela n'entre dans une commande annulée
CASES_DES_BRIQUES = {  # chemin -> l'objet de la carte qui l'ouvre (B9 § 1 bis)
    "ajouter[].composition": "choix", "changer_quantite[].composition": "choix", "ajouter[].poids": "poids", "ajouter[].personnes": "personnes",
    "code_de_remise": "code_de_remise", "reduction_annoncee": "code_de_remise",
}
TYPE_RECAPITULATIF = "relecture"
TYPE_PROPOSITION = "proposition"
TYPE_ETAPE = "etape"


# --------------------------------------------------------------------------- la vue de l'état


@dataclass(frozen=True)
class VueDeLaCommande:
    """Ce que les règles des cases lisent de l'état de l'appel : jamais le panier entier, seulement ces faits."""

    mode: str | None = None
    lignes: int = 0
    moyen: str | None = None
    question: dict | None = None  # {"type": ..., "posee": bool}
    relecture_acceptee: bool = False
    enregistree: bool = False
    annulee: bool = False
    ligne_de_formule: bool = False
    objets_de_la_carte: dict[str, bool] = field(default_factory=dict)

    @classmethod
    def depuis_un_dict(cls, d: dict[str, Any]) -> VueDeLaCommande:
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


CLE_DES_OBJETS = "commande_objets_de_la_carte"
CLE_DU_TOUR = "tour_de_la_personne"


def question_posee(question: dict | None, tour: int) -> bool:
    """Une question attend ET elle était déjà là quand la personne a parlé (B8 point 1) : née à un tour d'avant celui de la personne."""
    if not question:
        return False
    nee = question.get("nee_au_tour")
    return True if nee is None else int(nee) < int(tour)


def vue_de_l_appel(fiche: dict) -> VueDeLaCommande:
    """La vue de l'état d'après la fiche de l'appel : le panier (``commande_panier``), le tour de la personne, les objets de la carte chargée."""
    p = P.du_dossier(fiche) if isinstance(fiche, dict) else P.nouveau()
    q = p.get("question")
    moyen = P.moyen_du_paiement(p)  # C3 : la clé que ``regler`` écrit
    return VueDeLaCommande(
        mode=p.get("mode"),
        lignes=len(p.get("lignes") or []),
        moyen=moyen,
        question=({"type": q.get("type"), "posee": question_posee(q, (fiche or {}).get(CLE_DU_TOUR, 0))} if isinstance(q, dict) else None),
        relecture_acceptee=bool(p.get("relecture_acceptee")),
        enregistree=bool(p.get("enregistree")),
        annulee=bool(p.get("annulee")),
        ligne_de_formule=any(l.get("formule_id") or l.get("etapes") for l in p.get("lignes") or []),
        objets_de_la_carte=dict((fiche or {}).get(CLE_DES_OBJETS) or {}),
    )


# --------------------------------------------------------------------------- le schéma complet, lu dans les textes versés


def schema_complet_de_la_fiche(version: str | None = None) -> dict[str, Any]:
    """Toutes les cases de la fiche de la commande avec leur texte de base : l'union des rendus de la version finale sur toutes les cartes et
    tous les états (une case n'y paraît que dans les états où elle a un objet). Les textes qui changent avec l'état sont dans ``variantes``.
    Lecture commune à la réservation (lot 7) : ``actions_communes/schema_des_cases.py``."""
    return schema_complet("commande", version)


def _parametre(nom: str, s: dict[str, Any], chemin: str) -> Parametre:
    return parametre_de_la_case(nom, s, chemin, LISTES)


def parametres_de_la_fiche(version: str | None = None) -> tuple[Parametre, ...]:
    """Les cases de la fiche, déclarées comme ``Parametre`` : toutes facultatives sauf ``a_dire`` (``reponse`` le devient selon l'état)."""
    complet = schema_complet_de_la_fiche(version)
    sortie = []
    for nom, s in complet.items():
        p = _parametre(nom, s, nom)
        if nom == "a_dire":
            p = replace(p, obligatoire=True)
        sortie.append(p)
    return tuple(sortie)


def _base_de_l_outil(nom_outil: str) -> dict[str, Any]:
    return next(o["function"] for o in rendu("commande", "vide", CARTE_TEMOIN) if o["function"]["name"] == nom_outil)


def description_de(nom_outil: str) -> str:
    return _base_de_l_outil(nom_outil)["description"]


def parametres_de_la_lecture() -> tuple[Parametre, ...]:
    s = _base_de_l_outil("lire")["parameters"]
    requis = set(s.get("required") or ())
    return tuple(replace(_parametre(k, v, "lire." + k), obligatoire=k in requis) for k, v in s["properties"].items())


# --------------------------------------------------------------------------- les règles des cases, chacune nommée


def tous_les_chemins() -> frozenset[str]:
    from api.services.workflow.cases_selon_l_etat import chemins_du_schema

    return frozenset(chemins_du_schema(schema_complet_de_la_fiche()))


def recapitulatif_en_attente(vue: VueDeLaCommande) -> bool:
    return bool(vue.question and vue.question.get("type") == TYPE_RECAPITULATIF)


def cases_de_fin_ouvertes(vue: VueDeLaCommande) -> bool:
    """Moyen, billet, téléphone, prénom : seulement quand le récapitulatif est en attente ou accepté (E26, B4)."""
    return vue.relecture_acceptee or recapitulatif_en_attente(vue)


def billet_visible(vue: VueDeLaCommande) -> bool:
    """Le billet (``rendu_sur``) : en espèces, ou tant que le récapitulatif attend (le moyen se dit dans la même phrase)."""
    return vue.moyen == "especes" or recapitulatif_en_attente(vue)


def cases_d_annulation(vue: VueDeLaCommande) -> set[str]:
    """Les cases d'annulation qui ont un objet : jamais les deux d'un même objet ensemble (méthode § 3, règle 2)."""
    en_cours = bool((vue.lignes or vue.mode) and not vue.enregistree and not vue.annulee)
    enregistree = vue.enregistree and not vue.annulee
    return ({"annuler_la_commande"} if en_cours else set()) | ({"annuler_une_commande_enregistree"} if enregistree else set())


def reponse_selon_la_question(vue: VueDeLaCommande) -> str:
    """« absente » sans question ou pour une question née dans ce tour ; « obligatoire » pour une question déjà posée (B8 point 1)."""
    if not vue.question or not vue.question.get("posee"):
        return "absente"
    return "obligatoire"


def cases_de_la_carte(vue: VueDeLaCommande) -> set[str]:
    """Les cases des briques que la carte chargée n'a pas : à cacher (B9 § 1 bis)."""
    objets = vue.objets_de_la_carte or {}
    return {chemin for chemin, objet in CASES_DES_BRIQUES.items() if not objets.get(objet)}


def cases_cachees(vue: VueDeLaCommande) -> set[str]:
    cachees = set(cases_de_la_carte(vue))
    if not cases_de_fin_ouvertes(vue):
        cachees |= set(CASES_DE_FIN)
    elif not billet_visible(vue):
        cachees.add("rendu_sur")
    if not vue.lignes:
        cachees |= set(CASES_DES_LIGNES)
    cachees |= {"annuler_la_commande", "annuler_une_commande_enregistree"} - cases_d_annulation(vue)
    if reponse_selon_la_question(vue) == "absente":
        cachees.add("reponse")
    elif vue.question and vue.question.get("type") == TYPE_ETAPE:
        cachees.add("reponse.sens")
    return cachees


def cases_visibles_de_la_vue(vue: VueDeLaCommande) -> frozenset[str]:
    cachees = cases_cachees(vue)
    return frozenset(c for c in tous_les_chemins() if not any(c == h or c.startswith((h + ".", h + "[]")) for h in cachees))


def forme_de_la_vue(vue: VueDeLaCommande) -> dict[str, Any]:
    """Ce qui change avec l'état : les requis du premier niveau et de ``reponse``, les textes d'état (lus dans les variantes versées)."""
    v = variantes()
    descriptions: dict[str, str] = {}
    requises: dict[str, list[str]] = {}
    if reponse_selon_la_question(vue) == "obligatoire":
        requises[""] = ["reponse", "a_dire"]
        descriptions["reponse"] = v["reponse.obligatoire"]
        if vue.question.get("type") == TYPE_ETAPE:
            requises["reponse"] = ["question_id", "valeurs"]
            descriptions["reponse.valeurs"] = v["reponse.valeurs.etape"]
    if vue.question and vue.question.get("type") == TYPE_PROPOSITION:
        descriptions["c_est_tout"] = v["c_est_tout.proposition"]
    if vue.ligne_de_formule:
        descriptions["changer_quantite[].composition"] = v["changer_quantite[].composition.ligne_de_formule"]
    return {"requises": requises, "descriptions": descriptions}


def cases_visibles(fiche: dict) -> frozenset[str]:
    """Pour le connecteur (``Connecteur.cases_visibles``) : les chemins des cases qui ont un objet maintenant."""
    return cases_visibles_de_la_vue(vue_de_l_appel(fiche))


def forme_selon_l_etat(fiche: dict) -> dict[str, Any]:
    return forme_de_la_vue(vue_de_l_appel(fiche))


# --------------------------------------------------------------------------- les listes fermées, construites au décroché


def avec_autre(valeurs) -> list[str]:
    """Une liste fermée de valeurs connues, plus « autre » (E8, E27)."""
    sortie = [str(v) for v in valeurs if str(v) and str(v) != AUTRE]
    return sortie + [AUTRE]


def listes_du_contexte(modes_ouverts, moyens, variantes_de_la_carte) -> dict[str, list[str]]:
    """Les trois listes fermées de la fiche, à ranger dans le contexte de l'appel au décroché (le chargement de l'appel, lot 5)."""
    return {LISTE_DES_MODES: avec_autre(modes_ouverts), LISTE_DES_MOYENS: avec_autre(moyens), LISTE_DES_VARIANTES: avec_autre(variantes_de_la_carte)}
