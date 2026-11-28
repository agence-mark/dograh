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

from api.services.actions_communes import conversation as CONV
from api.services.commande import contrat
from api.services.integrations.connectors.catalogue import Action, Connecteur, declarer


def _jamais(*_args, **_kwargs):
    raise RuntimeError("Une action interne ne passe jamais par le relais.")


async def _executer(action, arguments, ctx, delai_s):
    from api.services.commande.porte import executer

    return await executer(action, arguments, ctx, delai_s)


def _action_ouverte(fiche: dict) -> dict | None:
    """Une commande commencée (un mode choisi ou au moins une ligne), jamais enregistrée ni annulée : l'action ouverte, à finir par la fiche.
    Au retour d'un détour, l'appel revient à l'agent qui la tient, même sans article. ``a_finir`` (fait brut) dit s'il y a déjà de quoi perdre
    (au moins une ligne) : la porte de fin et le refus de fin ne retiennent que les actions où ``a_finir`` n'est pas ``False``."""
    from api.services.commande import etape, panier

    p = panier.du_dossier(fiche) if isinstance(fiche, dict) and "lignes" in (fiche.get(panier.CLE) or {}) else None  # un panier d'avant le lot 2 monte à cette lecture, seule
    if isinstance(p, dict) and (p.get("lignes") or p.get("mode")) and not etape.finie(p):
        return {"outil": "fiche", "attend_une_reponse": bool(CONV.question_de(p)), "a_finir": bool(p.get("lignes"))}
    return None


def _etat_pour_le_modele(fiche: dict, appel: dict) -> str | None:
    """L'état de la commande, tenu par le code, donné au modèle à chaque requête de l'étape (format de la version finale, lot 2 étape 8)."""
    from api.services.commande.etat_pour_le_modele import texte

    return texte(fiche, appel)


def _etat_de_l_appel(fiche: dict) -> str | None:
    from api.services.commande.etat_pour_le_modele import ligne_de_l_appel

    return ligne_de_l_appel(fiche)


async def _sans_tiers(ctx) -> bool:
    """Lot 6 : la prise de l'établissement de l'appel ne parle à aucun client (caisse de démo du Labo, prise d'essai) : la source de l'outil (son réglage
    ``source``, à défaut le classeur) le dit ; la règle du classeur est celle de la restauration (``source_commande.sans_tiers``), inscrite au démarrage."""
    from api.services.commande import source as registre_des_sources
    from api.services.commande.porte import SOURCE_DE_L_OUTIL

    return await registre_des_sources.sans_tiers((getattr(ctx, "reglages", None) or {}).get(SOURCE_DE_L_OUTIL), ctx)


def _issue_de_fin(fiche: dict) -> str | None:
    from api.services.commande.porte import issue_de_fin_d_appel

    return issue_de_fin_d_appel(fiche)


def _etat_final(fiche: dict) -> dict:
    """D28 : la commande à la fin de l'appel, comparée à l'état attendu d'un scénario joué : enregistrée (arrivée par la prise) ou non, articles et
    quantités, mode."""
    from api.services.commande import etape, panier

    p = panier.du_dossier(fiche) if isinstance(fiche, dict) and "lignes" in (fiche.get(panier.CLE) or {}) else panier.nouveau()
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
        porte_la_fiche="fiche",
        porte_la_lecture="lire",
        actions_a_cases=frozenset({"fiche"}),  # lot 6 : la lecture garde ses cases (sujet, article), toujours
        forme_selon_l_etat=contrat.forme_selon_l_etat,
        etat_final=_etat_final,
        issue_de_fin=_issue_de_fin,
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
