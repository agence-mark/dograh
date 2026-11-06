"""[.mark] Partie 3, sous-lot 9 (§ 5 du plan) : les neuf étapes de « Nouveau client » et les phrases de leurs échecs.

L'ordre est celui du plan ; il ne change pas. Une étape « passable » peut être laissée de côté (elle est dite au
récapitulatif) ; les autres sont nécessaires à un client qui fonctionne. Une étape qui DÉPENSE exige une confirmation
explicite, montant estimé affiché.

Les phrases d'échec sont rangées par code (``derniere_erreur`` garde le code, jamais le texte d'un serveur ou d'un
fournisseur) ; l'écran les montre en français ou en anglais.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Etape:
    numero: int
    cle: str
    titre: dict[str, str]
    passable: bool = False
    depense: bool = False


ETAPES: tuple[Etape, ...] = (
    Etape(1, "organisation", {"fr": "Le client et son organisation", "en": "The client and its organization"}),
    Etape(2, "base", {"fr": "La base du client", "en": "The client database"}, passable=True),
    Etape(3, "etablissements", {"fr": "Établissements et horaires", "en": "Establishments and opening hours"}, passable=True),
    Etape(4, "equipe", {"fr": "Équipe et sujets", "en": "Team and subjects"}, passable=True),
    Etape(5, "logiciels", {"fr": "Logiciels proposés", "en": "Proposed software"}, passable=True),
    Etape(6, "agent", {"fr": "L'agent, depuis une recette", "en": "The agent, from a recipe"}),
    Etape(7, "cle_portail", {"fr": "Clé d'API et fiche du portail", "en": "API key and portal record"}, passable=True),
    Etape(8, "appels_simules", {"fr": "Appels simulés", "en": "Simulated calls"}, passable=True, depense=True),
    Etape(9, "recapitulatif", {"fr": "Récapitulatif", "en": "Summary"}),
)

PAR_NUMERO = {e.numero: e for e in ETAPES}


def etape(numero: int) -> Etape:
    return PAR_NUMERO[numero]


# Une phrase par échec : ce qui s'est passé, et quoi faire. Jamais le texte brut d'un serveur.
PHRASES: dict[str, dict[str, str]] = {
    "inconnue": {
        "fr": "L'étape n'a pas abouti. Réessayez ; si cela recommence, passez par l'écran du client.",
        "en": "The step did not complete. Try again; if it happens again, use the client's screen.",
    },
    "nom_pris": {
        "fr": "Un client porte déjà cet identifiant. Choisissez-en un autre.",
        "en": "A client already uses this identifier. Choose another one.",
    },
    "deja_ouverte": {
        "fr": "Ce client a déjà une installation ouverte : reprenez-la.",
        "en": "This client already has an installation in progress: resume it.",
    },
    "en_cours": {
        "fr": "Cette étape est déjà en cours. Attendez sa fin, puis rechargez.",
        "en": "This step is already running. Wait for it to finish, then reload.",
    },
    "ordre": {
        "fr": "Les étapes se font dans l'ordre : terminez ou passez celle d'avant.",
        "en": "Steps run in order: finish or skip the previous one first.",
    },
    "non_passable": {
        "fr": "Cette étape ne se passe pas : le client en a besoin.",
        "en": "This step cannot be skipped: the client needs it.",
    },
    "confirmation_requise": {
        "fr": "Cette étape dépense : confirmez le montant estimé avant de la lancer.",
        "en": "This step spends money: confirm the estimated amount before running it.",
    },
    "par_une_personne": {
        "fr": "La clé du client se crée par une personne de l'équipe, jamais par une clé d'API.",
        "en": "The client's key is created by a team member, never by an API key.",
    },
    "base_nom_requis": {
        "fr": "Donnez un nom à la base (lettres minuscules, chiffres, tirets bas).",
        "en": "Give the database a name (lower case letters, digits, underscores).",
    },
    "base_prise": {
        "fr": "Cette base existe déjà ou est rattachée à un autre client. Choisissez un autre nom, ou rattachez-la.",
        "en": "This database already exists or belongs to another client. Choose another name, or attach it.",
    },
    "base_refusee": {
        "fr": "La base n'a pas pu être créée ou rattachée (nom invalide ou base sans schéma .mark). Vérifiez le nom.",
        "en": "The database could not be created or attached (invalid name or no .mark schema). Check the name.",
    },
    "base_injoignable": {
        "fr": "Le serveur des bases ne répond pas. Rien n'a été changé ; réessayez dans un instant.",
        "en": "The database server does not answer. Nothing changed; try again in a moment.",
    },
    "base_requise": {
        "fr": "Cette étape vit dans la base du client : rattachez d'abord une base (étape 2).",
        "en": "This step lives in the client database: attach a database first (step 2).",
    },
    "etablissement_requis": {
        "fr": "Ajoutez au moins un établissement, avec son nom.",
        "en": "Add at least one establishment, with its name.",
    },
    "etablissements_refuses": {
        "fr": "Les établissements n'ont pas été enregistrés (une valeur est refusée). Corrigez-les dans l'écran Établissements.",
        "en": "The establishments were not saved (a value was refused). Fix them in the Establishments screen.",
    },
    "personne_requise": {
        "fr": "Ajoutez au moins une personne, avec son prénom.",
        "en": "Add at least one person, with a first name.",
    },
    "equipe_refusee": {
        "fr": "L'équipe n'a pas été enregistrée (une valeur est refusée). Corrigez-la dans l'écran Équipe.",
        "en": "The team was not saved (a value was refused). Fix it in the Team screen.",
    },
    "logiciel_requis": {
        "fr": "Choisissez au moins un logiciel, ou passez l'étape.",
        "en": "Pick at least one software, or skip the step.",
    },
    "logiciel_refuse": {
        "fr": "Un logiciel n'a pas pu être proposé (logiciel inconnu ou compte invalide). Vérifiez la liste.",
        "en": "A software could not be proposed (unknown software or invalid account). Check the list.",
    },
    "agent_requis": {
        "fr": "Créez l'agent dans la fenêtre « Nouvel agent », ou retenez celui qui existe déjà.",
        "en": "Create the agent in the « New agent » window, or keep the one that already exists.",
    },
    "agent_introuvable": {
        "fr": "Cet agent n'appartient pas à ce client. Créez-le depuis cette fenêtre.",
        "en": "This agent does not belong to this client. Create it from this window.",
    },
    "cle_refusee": {
        "fr": "La clé du client n'a pas été créée. Réessayez ; elle sera montrée une seule fois.",
        "en": "The client's key was not created. Try again; it will be shown only once.",
    },
    "portail_refuse": {
        "fr": "La connexion du portail à la base n'a pas été créée (base à mettre à niveau ?). La clé, elle, est créée.",
        "en": "The portal's database connection was not created (database to upgrade?). The key itself is created.",
    },
    "aucun_scenario": {
        "fr": "L'agent n'a encore aucun scénario d'appel simulé. Ajoutez-en dans Tests, ou passez l'étape.",
        "en": "The agent has no simulated-call scenario yet. Add some in Tests, or skip the step.",
    },
    "serie_refusee": {
        "fr": "La série d'appels simulés est refusée (réglages de l'appelant simulé, prix ou série déjà en cours). Voyez les Tests.",
        "en": "The simulated-call series was refused (simulated caller settings, prices or a series already running). See Tests.",
    },
    "installation_introuvable": {
        "fr": "Aucune installation ouverte pour ce client.",
        "en": "No installation in progress for this client.",
    },
}


def phrase(code: str | None) -> dict[str, str] | None:
    if not code:
        return None
    return PHRASES.get(code, PHRASES["inconnue"])
