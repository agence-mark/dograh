"""[.mark] La fiche de l'agent : les champs que l'outil `noter_information` écrit.

Plan « la fiche au fil de l'eau », lot 1 (D22) : le minimum -- nom du champ, type,
dicté ou déduit, indice. Rangée dans `workflow_configurations` (colonne JSON) :
aucune migration de base (D32).
"""

import re
import unicodedata
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# PB3 : les bornes d'une liste fermée de valeurs (reprises par l'écran).
MAX_VALEURS = 20
MAX_LONGUEUR_VALEUR = 40
# C1 : la borne haute du nombre de chiffres déclarable (reprise par l'écran).
MAX_CHIFFRES = 30


class OrigineChamp(str, Enum):
    """D4 : un champ DICTÉ subit le contrôle de citation, un champ DÉDUIT non."""

    dicte = "dicte"
    deduit = "deduit"


class ChampFiche(BaseModel):
    nom: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9_]{0,63}$",
        description="snake_case name of the field, also the tool parameter name.",
    )
    # Mêmes valeurs que `VariableType` des variables d'extraction, sans importer
    # la couche workflow depuis les schémas.
    type: Literal["string", "number", "boolean"] = "string"
    origine: OrigineChamp = Field(
        default=OrigineChamp.dicte,
        description=(
            "Dictated: the value must have been said by the caller (name, town, "
            "street, number, brand). Deduced: the model sums it up (reason, urgency)."
        ),
    )
    description: str = Field(
        default="",
        max_length=500,
        description="Hint given to the model for this parameter.",
    )
    # D42 : quel module lit ce champ. Vide = déduit du nom (``lecteur_effectif``).
    # ⛔ Gardé VIDE en base, jamais remplacé par sa valeur déduite : l'écran
    # comparerait ce qu'il a envoyé à ce qu'il relit et se croirait modifié, et
    # un champ renommé garderait le lecteur de son ancien nom (constaté le 24/09).
    lecteur: Literal["commune", "rue", "date", "lexique", "aucun"] | None = Field(
        default=None,
        description=(
            "Which reader checks the value: town (official name and INSEE code), "
            "street (official street name), date (a relative date such as 'last "
            "year' computed on the day of the call, the caller's words kept), "
            "trade vocabulary (a name of the organization's vocabulary, sure only "
            "when recognised), or none. Empty: from the field name."
        ),
    )

    # PB3 (patch du banc, 25/09) : une liste fermée de valeurs. Le champ n'accepte
    # qu'une d'elles, écrite sous la forme déclarée, d'où que vienne la valeur ;
    # et un champ déduit qui en déclare une est exempté de l'ancrage (PB2).
    # Vide = aucune liste. Rangée dans le JSON de l'agent : aucune migration.
    valeurs: list[str] | None = Field(
        default=None,
        description=(
            "Allowed values: the field only accepts one of them (case and accents "
            "ignored), written as declared. Empty: any value."
        ),
    )

    # D7 (chantier correctifs-modules, 28/09) : un champ où chaque note s'ajoute
    # à ce qu'il tient déjà, sans rien écraser (un 2e motif, un symptôme complété :
    # run 879). Exempt du contrôle « dit tel quel ». Faux par défaut : aucun
    # changement pour un agent qui ne le déclare pas.
    cumulatif: bool = Field(
        default=False,
        description=(
            "Cumulative: each note is added to what the field already holds, "
            "nothing is overwritten; not checked against the caller's exact words."
        ),
    )

    # Plan postscriptum-note-d-abord (piste de latence) : le code recopie les mots
    # exacts de la réplique où le modèle note ce champ ; le modèle n'écrit que « = »
    # (recopier une phrase entière dans la note coûte ≈ 1 s à la première réplique).
    # Faux par défaut : aucun changement pour un agent qui ne le déclare pas.
    copie_de_la_parole: bool = Field(
        default=False,
        description=(
            "Copied from the caller's words: when the model notes this field, the "
            "code writes the caller's exact words of that reply; the model only "
            "writes '='. Saves the model copying a whole sentence."
        ),
    )

    # C1 (chantier correctifs-banc-34, 29/09, run 887) : le nombre de chiffres que
    # la valeur doit compter, espaces et signes ignorés. Vide = aucun contrôle (le
    # défaut) : rien ne change pour un agent qui ne le déclare pas.
    chiffres: int | None = Field(
        default=None,
        ge=1,
        le=MAX_CHIFFRES,
        description=(
            "Digits: how many digits the value must hold (spaces and signs "
            "ignored); a value with more or fewer is refused and the caller is "
            "asked for it again in full. Empty: no check."
        ),
    )

    # D3 (chantier correctifs-second-banc-34, 30/09, runs 900 à 903) : la passe de fin
    # d'appel remplissait `autre` et `symptome` de recopies (la marque, le budget,
    # l'épellation, deux répliques recollées). Décoché, seul l'outil l'écrit, pendant
    # l'appel. Coché par défaut : rien ne change pour un agent qui ne le déclare pas.
    rempli_en_fin_d_appel: bool = Field(
        default=True,
        description=(
            "Filled at the end of the call: if the agent did not note the field during "
            "the call, the end-of-call pass may fill it from the conversation. Off: only "
            "the agent writes it, while the caller is speaking."
        ),
    )

    # [.mark] Chantier agents-specialises, lot 17 : la portée du champ dans un appel à
    # plusieurs demandes. « appel » : commun à tout l'appel (ce qui concerne l'appelant) ;
    # « demande » : propre à une demande (il se clôt avec elle). ⛔ Gardé VIDE en base, jamais
    # remplacé par sa valeur calculée (même règle que ``lecteur`` : l'écran compare ce qu'il
    # envoie à ce qu'il relit). Vide = ``portee_par_defaut`` (services/fiche/demandes.py),
    # calculée par les réglages génériques de l'agent. Sans passation vers un spécialisé
    # (agent seul, appel à une demande) la portée n'agit sur rien.
    portee: Literal["appel", "demande"] | None = Field(
        default=None,
        description=(
            "Scope in a call with several requests: whole call (what concerns the "
            "caller: shared by every request) or this request (closed with it when "
            "another specialist takes over). Empty: computed from the agent's "
            "settings (town and street readers, field recognition)."
        ),
    )

    # [.mark] Chantier fiabilite-orchestration, lot 1 (R3, G2 ; runs 1463, 1466, 1468) : le greffier
    # écrivait ``rendez_vous = confirme`` d'après l'annonce de l'agent. Un champ qui déclare l'outil
    # qui le remplit n'est écrit QUE par le résultat de cet outil : jamais par le modèle, le
    # greffier ni le balayage. Vide (le défaut) : rien ne change.
    rempli_par_outil: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "Filled by a tool: the name of the tool whose result writes this field (the "
            "value of the same key in its answer, else its status, else the first allowed "
            "value). The model, the clerk and the end-of-call pass never write it. Empty: off."
        ),
    )

    # [.mark] correctifs-apres-banc-commun, lot 8 (K16, D-1) : l'outil qui DÉFAIT ce que ``rempli_par_outil``
    # a fait (annuler un rendez-vous). Son résultat réussi écrit le champ (la clé du même nom dans sa réponse,
    # sinon son statut : jamais une valeur par défaut) ; un échec n'écrit rien. Cet outil passe toujours : ni
    # la garde de réservation ni la réservation identique (vérité des actions) ne le retiennent. Vide : éteint.
    annule_par_outil: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "Undone by a tool: the name of the tool that cancels what the filling tool did. Its "
            "successful result writes this field (the value of the same key in its answer, else its "
            "status); a failure writes nothing, and the agent is told the real outcome. It is never "
            "held back by the booking guard. Empty: off."
        ),
    )

    # [.mark] correctifs-apres-banc-v4, lot 2 (6.3, question n° 382) : un refus de la personne est noté
    # « refusé » et la garde de l'étape le compte comme traité (sinon l'agent redemande à chaque
    # tour). Ce champ-ci fait exception : refusé, il reste manquant. Faux par défaut : un champ qui ne
    # le déclare pas se comporte comme un refus ordinaire. La case d'écran vient au lot 5.
    obligatoire_sans_exception: bool = Field(
        default=False,
        description=(
            "Required without exception: a refusal by the caller does not count as an answer, "
            "the field stays missing for the step's guard. Off: a refused field counts as handled."
        ),
    )

    @field_validator("rempli_par_outil", "annule_par_outil")
    @classmethod
    def _outil_lisible(cls, nom: str | None) -> str | None:
        nom = (nom or "").strip()
        if not nom:
            return None
        if not re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", nom):
            raise ValueError("a tool name holds letters, digits, '_' and '-' only")
        return nom

    @property
    def rempli_par_un_outil(self) -> bool:
        return bool(self.rempli_par_outil)

    @field_validator("valeurs")
    @classmethod
    def _valeurs_lisibles(cls, valeurs: list[str] | None) -> list[str] | None:
        if valeurs is None:
            return None
        propres: list[str] = []
        vues: set[str] = set()
        for brute in valeurs:
            valeur = (brute or "").strip()
            # Revue du 25/09 : « Panne, panne » est une seule valeur (la fiche
            # compare sans casse ni accents) ; la première écriture est gardée.
            forme = "".join(
                c
                for c in unicodedata.normalize("NFKD", valeur.casefold())
                if not unicodedata.combining(c)
            )
            if valeur and forme not in vues:
                vues.add(forme)
                propres.append(valeur)
        if len(propres) > MAX_VALEURS:
            raise ValueError(f"at most {MAX_VALEURS} allowed values")
        for valeur in propres:
            if len(valeur) > MAX_LONGUEUR_VALEUR:
                raise ValueError(
                    f"allowed value '{valeur[:20]}…' is longer than "
                    f"{MAX_LONGUEUR_VALEUR} characters"
                )
        return propres or None

    @property
    def lecteur_effectif(self) -> str:
        return self.lecteur or lecteur_par_defaut(self.nom)


def lecteur_par_defaut(nom: str) -> str:
    """D42 : ``commune*`` -> commune ; ``adresse*`` et ``rue*`` -> rue ; D46 :
    ``*date*``, ``dernier_*`` et ``annee*`` -> date ; C10 (PB12) : ``marque*``
    -> lexique ; sinon aucun."""
    if nom.startswith("commune"):
        return "commune"
    if nom.startswith("marque"):
        return "lexique"
    if nom.startswith(("adresse", "rue")):
        return "rue"
    if "date" in nom or nom.startswith(("dernier_", "annee")):
        return "date"
    return "aucun"


def est_un_champ_de_nom(champ: "ChampFiche") -> bool:
    """Q6 (plan « le lexique », 26/09) : un champ qui porte le nom d'une personne,
    reconnu par son nom (``nom``, ``nom_*``, ``prenom*``) comme le lecteur l'est
    (D42), et lu par aucun module. ⚠️ Pas ``nom*`` : ``nombre_appareils`` n'est pas
    un nom (contre-relecture du 26/09)."""
    nom = champ.nom
    return champ.lecteur_effectif == "aucun" and (
        nom == "nom" or nom.startswith("nom_") or nom.startswith("prenom")
    )


def cle_insee(nom: str) -> str:
    """Où le code INSEE d'une commune sûre est écrit, à côté de son nom."""
    return f"{nom}_insee"


def cle_dit(nom: str) -> str:
    """D46 : où les mots de la personne sont gardés, à côté de la date calculée."""
    return f"{nom}_dit"


# Clés que le moteur et les modules écrivent eux-mêmes dans la fiche de l'appel.
# Un champ de ce nom les écraserait : refusé à l'enregistrement. ⚠️ Tenue à jour
# par un test qui la compare aux clés réelles du moteur et des modules.
NOMS_RESERVES = frozenset(
    {
        # moteur (`_ENGINE_OWNED_CONTEXT_KEYS` et clés d'état)
        "call_disposition",
        "mapped_call_disposition",
        "call_status",
        "call_tags",
        "answer_supervisor",
        # [.mark] lot 3 de cloture-code (amont b10e829f) : les résultats des outils
        "tool_results",
        "extracted_variables",
        "nodes_visited",
        "agent_visits",
        # [.mark] agents-specialises (lots 2, 5, 7) : les traces du groupe
        "parcours",
        "parcours_etapes",
        "porte_reecrite",
        "passations",
        "transferts_humains",
        # [.mark] agents-specialises (lot 17) : les demandes closes d'un appel à plusieurs demandes
        "demandes",
        "demande_au_retour",
        # traces des modules
        "communes_verifiees",
        # chantier postscriptum-et-communes, lot 1 : les communes lues sur le nom de la personne
        "communes_ecartees",
        # plan mode-prise-de-notes : la trace de chaque post-scriptum et de chaque passe du greffier
        "post_scriptums",
        "greffier_passes",
        # chantier greffier-conversation, lot A : les portes écrites dans la réponse (greffier)
        "portes_lues",
        # chantier greffier-conversation, lot E : le transfert lancé par le code
        "transferts_garantis",
        "voies_verifiees",
        "epellations_lues",
        "nombres_lus",
        "lexique_reconnu",
        "lexique_metier",
        # la fiche elle-même
        "fiche_etat",
        "fiche_journal",
        "tour_appelant",
        # [.mark] l-agent-travaille, L5 : les traces des connecteurs
        "connecteurs",
        "connecteurs_differes",
        # [.mark] l-agent-collegue : les traces de l'équipe, du hub, du planificateur et de la
        # vérification de l'appelant (L2 à L6, R-3)
        "equipe_gestes",
        "equipe_assignation",
        "hub_rendez_vous",
        "planificateur",
        "planificateur_rappel",
        "verification_appelant",
        "dossier_lu",
        # [.mark] orchestrateur-trois-cerveaux, lot 4 : la trace du cerveau de fond (oubliée alors,
        # ajoutée par fiabilite-orchestration) ; fiabilite-orchestration : les phrases du code.
        "travaux",
        "phrases_du_code",
        # fiabilite-orchestration, lot 9 : connexions au modèle et liaison audio relevées par appel.
        "mark_connexions_modele",
        "mark_reseau",
        # actions-sures-et-parite-clavier, lot F : le journal des actions de l'appel, gardé avec la fiche.
        "mark_journal_des_actions",
        # passages-fiables : les retenues de la vérité des actions (file de tri) ; le rejeu d'un test et ses outils simulés.
        "retenues_verite",
        "rejeu_sortants_simules",
        "outils_simules",
        # passages-fiables : les traces du décideur et de l'arbitre, l'attente accordée, les signalements et les alertes.
        "passages_par_le_code",
        "arbitre",
        "desaccords_arbitre",
        "attentes_accordees",
        "signalements",
        "alertes",
        "alertes_mail",
    }
)


def verifier_champs(champs: list[ChampFiche]) -> list[ChampFiche]:
    """Refuse un nom réservé ou un nom en double (422 à l'enregistrement)."""
    vus: set[str] = set()
    insee = {cle_insee(c.nom) for c in champs if c.lecteur_effectif == "commune"}
    dits = {cle_dit(c.nom) for c in champs if c.lecteur_effectif == "date"}
    for champ in champs:
        if champ.nom in insee:
            raise ValueError(
                f"fiche field name '{champ.nom}' is where a town's INSEE code is written"
            )
        if champ.nom in dits:
            raise ValueError(
                f"fiche field name '{champ.nom}' is where the caller's words for a "
                "date are kept"
            )
        if champ.nom in NOMS_RESERVES:
            raise ValueError(f"fiche field name '{champ.nom}' is reserved")
        if champ.nom in vus:
            raise ValueError(f"fiche field name '{champ.nom}' is used twice")
        vus.add(champ.nom)
    return champs
