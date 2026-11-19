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
    from api.services.commande import panier

    p = fiche.get(panier.CLE) if isinstance(fiche, dict) else None
    if isinstance(p, dict) and p.get("lignes") and not p.get("enregistree") and not p.get("annulee"):
        return {"outil": "fiche", "attend_une_reponse": bool(p.get("question"))}
    return None


def _etat_pour_le_modele(fiche: dict, appel: dict) -> str | None:
    """L'état de la commande, tenu par le code, donné au modèle à chaque requête de l'étape (format de la version finale, lot 2 étape 8)."""
    from api.services.commande.etat_pour_le_modele import texte

    return texte(fiche, appel)


COMMANDE = declarer(
    Connecteur(
        nom="commande",
        action_ouverte=_action_ouverte,
        etat_pour_le_modele=_etat_pour_le_modele,
        cases_visibles=contrat.cases_visibles,
        forme_selon_l_etat=contrat.forme_selon_l_etat,
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
