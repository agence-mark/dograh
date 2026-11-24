"""[.mark] Le connecteur interne « Commande » (chantier Partie 1, lot 2 : le contrat de la version finale, fiche à cases).

Aucun logiciel, aucun Nango : les actions tournent dans le fork et le catalogue est une SOURCE (la base du client, par
``services/restauration/source_commande.py``). Deux actions seulement (E1) :

- ``fiche`` : ce qu'elle vient de dire pour sa commande, une case par chose dite ; le code exécute chaque case remplie, dans son ordre, et rend
  un seul retour (l'enveloppe, ``actions_communes/enveloppe.py``) ; l'exécutant est la porte d'entrée (``services/commande/porte.py``, lot 3) ;
- ``lire`` : une lecture qui n'écrit jamais rien (E16).

Les noms, descriptions et cases sont ceux de la version finale du banc, lus dans les textes versés du gabarit (``services/commande/contrat.py``),
jamais écrits ici ; les cases sans objet dans l'état de l'appel ou la carte sont cachées (``cases_visibles``, E26).
"""

from __future__ import annotations

from api.services.commande import contrat
from api.services.integrations.connectors.catalogue import Action, Connecteur, declarer


def _jamais(*_args, **_kwargs):
    raise RuntimeError("Une action interne ne passe jamais par le relais.")


async def _executer(action, arguments, ctx, delai_s):
    from api.services.commande.porte import executer

    return await executer(action, arguments, ctx, delai_s)


def _source_du_catalogue() -> None:
    # La base du client est la première source du catalogue : elle s'inscrit à l'import (les autres s'inscrivent de la même façon).
    import api.services.restauration.source_commande  # noqa: F401


_source_du_catalogue()


def _action_ouverte(fiche: dict) -> dict | None:
    """Un panier avec au moins une ligne, jamais enregistré ni annulé : l'action ouverte, à finir par la fiche."""
    from api.services.commande import etape, panier

    p = fiche.get(panier.CLE) if isinstance(fiche, dict) else None
    if isinstance(p, dict) and p.get("lignes") and not etape.finie(p):
        return {"outil": "fiche", "attend_une_reponse": bool(p.get("question"))}
    return None


def _etat_pour_le_modele(fiche: dict, appel: dict) -> str | None:
    """L'état de la commande, tenu par le code, donné au modèle à chaque requête de l'étape (format de la version finale, lot 2 étape 8)."""
    from api.services.commande.etat_pour_le_modele import texte

    return texte(fiche, appel)


def _etat_de_l_appel(fiche: dict) -> str | None:
    from api.services.commande.etat_pour_le_modele import ligne_de_l_appel

    return ligne_de_l_appel(fiche)


async def _sans_tiers(ctx) -> bool:
    """Lot 6 : la prise de l'établissement de l'appel ne parle à aucun client (caisse de démo du Labo, prise d'essai) : lue sur la prise."""
    from api.services.restauration.appel_et_memoire import memoire_de_l_appel
    from api.services.restauration.caisse.prises.prise import ContexteDePrise, PrisePortail, prise_de_l_etablissement

    async with memoire_de_l_appel.geste(ctx) as (connexion, lieu):
        prise = await prise_de_l_etablissement(ContexteDePrise(connexion, ctx.organization_id, lieu.etablissement_id, lieu.nom_base))
    if prise is None or getattr(prise, "nom", None) == PrisePortail.nom:
        # Lot 19 (restaurants installés par le gabarit au lot 18, sans caisse) : la prise du portail n'envoie rien, la commande reste au classeur, la
        # base du client ; au Labo, ce sont des restaurants de test : même règle que la réservation (``source_reservation.sans_tiers``) ; chez un
        # client, simulé (B42)
        from api.services.restauration.caisse.caisse_demo.garde import organisation_est_labo

        return await organisation_est_labo(getattr(ctx, "organization_id", None))
    return bool(getattr(prise, "sans_tiers", False))


def _etat_final(fiche: dict) -> dict:
    """D28 : la commande à la fin de l'appel, comparée à l'état attendu d'un scénario joué : enregistrée (arrivée par la prise) ou non, articles et
    quantités, mode."""
    from api.services.commande import etape, panier

    p = fiche.get(panier.CLE) if isinstance(fiche, dict) else None
    p = p if isinstance(p, dict) else {}
    articles: dict[str, int] = {}
    for ligne in p.get("lignes") or []:
        if isinstance(ligne, dict) and ligne.get("nom"):
            articles[str(ligne["nom"])] = articles.get(str(ligne["nom"]), 0) + int(ligne.get("quantite") or 1)
    return {"enregistree": etape.enregistree(p), "articles": articles, "mode": p.get("mode")}


COMMANDE = declarer(
    Connecteur(
        nom="commande",
        sans_tiers=_sans_tiers,
        action_ouverte=_action_ouverte,
        etat_pour_le_modele=_etat_pour_le_modele,
        etat_de_l_appel=_etat_de_l_appel,
        cases_visibles=contrat.cases_visibles,
        actions_a_cases=frozenset({"fiche"}),  # lot 6 : la lecture garde ses cases (sujet, article), toujours
        forme_selon_l_etat=contrat.forme_selon_l_etat,
        etat_final=_etat_final,
        libelle="Commande (interne)",
        integration="interne",
        interne=True,
        executer_interne=_executer,
        actions=(
            Action(
                nom="fiche",
                description=contrat.description_de("fiche"),
                parametres=contrat.parametres_de_la_fiche(),
                serialise_avec="panier",
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
