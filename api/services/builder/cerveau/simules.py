"""[.mark] Builder, U6 : les cerveaux de l'appelant simulé et du juge, d'après les réglages du Labo (``ReglagesAppelantSimule``).

Fin de « le builder joue l'appelant » : un test du builder prend SON appelant et SON juge, chacun avec son fournisseur et sa clé
de la bibliothèque de clés (code agnostique : « fournisseur/modèle »). Une source « Claude Code » ne fait aucun appel ici : la
brique attend une session (``juge_a_faire`` / ``juge_lire`` / ``juge_ecrire``).

⛔ La clé n'est ni journalisée ni mise dans une erreur.
"""

from __future__ import annotations

from api.schemas.appel_simule import RoleSimule
from api.services.builder.cerveau import budget_roles
from api.services.builder.cerveau.appel import Cerveau, ErreurCerveau, fabriquer
from api.services.builder.cerveau.reglages import ADRESSE_PAR_DEFAUT, ReglagesCerveau

# Les fournisseurs que le code sait joindre sans qu'on lui dise l'adresse. Tout autre : format et adresse du réglage.
FOURNISSEURS: dict[str, tuple[str, str]] = {
    "mistral": ("openai", "https://api.mistral.ai/v1"),
    "openai": ("openai", ADRESSE_PAR_DEFAUT["openai"]),
    "anthropic": ("anthropic", ADRESSE_PAR_DEFAUT["anthropic"]),
    "gemini": ("openai", "https://generativelanguage.googleapis.com/v1beta/openai"),
}


def separer(modele: str) -> tuple[str, str]:
    """« mistral/mistral-small-latest » -> (« mistral », « mistral-small-latest ») ; sans préfixe : (« », modèle)."""
    fournisseur, _, nom = modele.partition("/")
    return (fournisseur.lower(), nom) if nom else ("", modele)


def reglages_du_role(role: RoleSimule, base: ReglagesCerveau) -> ReglagesCerveau:
    """Les réglages de cerveau d'un rôle : plafonds et prix du builder, fournisseur et modèle du rôle."""
    fournisseur, nom = separer(role.modele)
    format_, adresse = FOURNISSEURS.get(fournisseur, ("openai", ""))
    return base.model_copy(
        update={
            "source": role.source,
            "format": role.format or format_,
            "adresse": role.adresse or adresse,
            "modele": nom,
            "cle_ref": role.identifiant,
        }
    )


async def prix_du_role(organisation: int, role: RoleSimule, base: ReglagesCerveau) -> tuple[float, float]:
    """Les prix (entrée, sortie, par million de jetons) du MODÈLE DU RÔLE : sa ligne de la table des prix (avec ou sans préfixe du
    fournisseur), sinon ceux des réglages du cerveau. (0, 0) = inconnus."""
    from api.services.builder.cerveau import prix

    _, nom = separer(role.modele)
    table = await prix.lire(organisation)
    ligne = table.prix_de(nom) or table.prix_de(role.modele)
    if ligne is not None:
        return ligne.entree_par_million, ligne.sortie_par_million
    return base.prix_entree_par_million, base.prix_sortie_par_million


async def cerveau_du_role(organisation: int, role: RoleSimule, base: ReglagesCerveau) -> Cerveau | None:
    """Le cerveau du rôle, ou ``None`` : source Claude Code, clé non posée ou introuvable, ou rôle ÉTEINT (SE-23).

    Le cerveau rendu range sa dépense dans ``mark_depense_roles`` et refuse (``BudgetDuRole``) quand le budget du mois du rôle est
    atteint, avant tout appel au fournisseur."""
    if role.source != "cle_api" or not role.identifiant or not role.actif:
        return None
    from api.services.appel_simule.serie import cle_d_identifiant

    cle = await cle_d_identifiant(organisation, role.identifiant)
    if cle is None:
        return None
    try:
        cerveau = fabriquer(reglages_du_role(role, base), cle)
    except ErreurCerveau:
        return None
    if role.nom not in budget_roles.ROLES:
        return cerveau
    prix_entree, prix_sortie = await prix_du_role(organisation, role, base)
    return budget_roles.CerveauBudgete(
        cerveau, organisation=organisation, role=role.nom, budget=role.budget_mois, prix_entree=prix_entree, prix_sortie=prix_sortie
    )
