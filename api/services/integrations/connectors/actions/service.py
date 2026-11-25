"""[.mark] Le connecteur interne « Service » (chantier Partie 1, lot 2 : la fiche du service de la version finale, B9 § 1 « Service »).

Aucun logiciel, aucun Nango : les actions tournent dans le fork. Deux actions :

- ``fiche`` : ce qu'elle vient de dire pour sa demande au service (retrouver une commande d'un appel précédent, laisser un message à l'équipe), avec
  ta phrase ; les cases, leurs noms et leurs textes sont ceux de la version finale, lus dans les textes versés du gabarit ; son exécutant est la
  porte du lot 3 (``retrouver_commande``, le message à l'équipe une fois par appel) ;
- ``infos_pratiques`` : une information pratique écrite par l'établissement, par sujet (lue par l'accueil ; ``services/service_client/action.py``).

Règle nommée de D60, ``retrouver_par_telephone_dicte_exige_le_numero`` : un téléphone DICTÉ (autre que le numéro qui appelle) ne retrouve une commande
qu'avec son numéro de commande ; le numéro qui appelle reste suffisant seul.
"""

from __future__ import annotations

import re
from typing import Any

from api.services.actions_communes.enveloppe import Enveloppe, Question
from api.services.gabarits.restauration.textes import outil
from api.services.integrations.connectors.catalogue import Action, Connecteur, Parametre, declarer
from api.services.service_client import action as service


def _jamais(*_args, **_kwargs):
    raise RuntimeError("Une action interne ne passe jamais par le relais.")


async def _executer(action, arguments, ctx, delai_s):
    if action.nom == "fiche":
        from api.services.commande.porte import executer_la_fiche_du_service

        return await executer_la_fiche_du_service(dict(arguments or {}), ctx)
    from api.services.commande.porte import OUTILS_DE_L_ACCUEIL

    if action.nom in OUTILS_DE_L_ACCUEIL:
        from api.services.commande.porte import executer as executer_de_la_commande

        return await executer_de_la_commande(action, arguments, ctx, delai_s)
    return await service.executer(action, arguments, ctx, delai_s)


def _depuis_le_schema(nom: str, s: dict[str, Any], requis: bool = False) -> Parametre:
    return Parametre(
        nom=nom, type=s.get("type", "string"), description=s.get("description", ""), obligatoire=requis, choix=tuple(s.get("enum") or ()),
        proprietes=tuple(_depuis_le_schema(k, v, k in (s.get("required") or ())) for k, v in (s.get("properties") or {}).items()),
        obligatoires=tuple(s.get("required") or ()),
    )


def _fiche_versee() -> dict[str, Any]:
    return outil("service", "fiche")


def _outil_de_l_accueil(nom: str) -> dict[str, Any]:
    return outil("accueil", nom)


def _action_de_l_accueil(nom: str) -> Action:
    """Un outil de l'accueil déclaré tel que les textes prouvés l'écrivent (description et cases) ; son exécutant est la porte de la commande."""
    f = _outil_de_l_accueil(nom)
    p = f["parameters"]
    requis = set(p.get("required") or ())
    return Action(
        nom=nom, description=f["description"], parametres=tuple(_depuis_le_schema(k, v, k in requis) for k, v in (p.get("properties") or {}).items()),
        ecrit=False, local=True, preparer=_jamais, resultat=_jamais,
    )


def _parametres_de_la_fiche() -> tuple[Parametre, ...]:
    p = _fiche_versee()["parameters"]
    requis = set(p.get("required") or ())
    return tuple(_depuis_le_schema(k, v, k in requis) for k, v in p["properties"].items())


def _chiffres(texte: Any) -> str:
    return re.sub(r"\D", "", str(texte or ""))


def _meme_numero(dicte: str, qui_appelle: str | None) -> bool:
    """« 06 12 34 56 78 » et « +33612345678 » : le même numéro (les neuf derniers chiffres)."""
    a, b = _chiffres(dicte), _chiffres(qui_appelle)
    return bool(a and b and a[-9:] == b[-9:])


def retrouver_par_telephone_dicte_exige_le_numero(fiche_du_modele: dict[str, Any], numero_qui_appelle: str | None, prochaine_question: str = "Q-1") -> dict | None:
    """D60 : ``None`` quand la recherche peut se faire ; sinon le refus (raison ``numero_de_commande_exige``, la question du numéro). Un téléphone
    dicté qui n'est pas le numéro qui appelle ne retrouve une commande qu'avec son numéro de commande (cloisonnement : on ne lit jamais la commande
    d'un autre sur un simple numéro dit)."""
    demande = fiche_du_modele.get("retrouver_une_commande_enregistree")
    if not isinstance(demande, dict):
        return None
    dicte = str(demande.get("telephone") or "").strip()
    if not dicte or _meme_numero(dicte, numero_qui_appelle) or str(demande.get("numero_de_commande") or "").strip():
        return None
    return Enveloppe(
        "A_PRECISER", raison="numero_de_commande_exige", explication="un numéro dicté ne suffit pas sans le numéro de la commande",
        question=Question(prochaine_question, "ambiguite", "Quel est le numéro de la commande ?"),
        a_faire="demande-lui le numéro de la commande",
    ).vers_json()


def _dossier_de_la_parole(_fiche: dict) -> dict:
    """P4 (lot 19 bis) : le service n'a pas de panier ; sa parole n'est jamais jugée sur le dossier de la commande."""
    return {}


def _objet_en_cours(_dossier: dict) -> bool:
    return False


def _texte_du_manque(_dossier: dict, _fiche: dict) -> str | None:
    return None


def _valeur_du_manque(_dossier: dict, _fiche: dict) -> str | None:
    return None


SERVICE = declarer(
    Connecteur(
        nom="service",
        porte_la_fiche="fiche",
        dossier_de_la_parole=_dossier_de_la_parole,
        objet_en_cours=_objet_en_cours,
        texte_du_manque=_texte_du_manque,
        valeur_du_manque=_valeur_du_manque,
        libelle="Service (interne)",
        integration="interne",
        interne=True,
        executer_interne=_executer,
        actions=(
            Action(
                nom="fiche",
                description=_fiche_versee()["description"],
                parametres=_parametres_de_la_fiche(),
                ecrit=False,
                local=True,
                # SA-49 (M115, appel 2597) : un message annoncé et jamais laissé ne se rattrape pas après l'appel.
                doit_aboutir=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="infos_pratiques",
                description=_outil_de_l_accueil("infos_pratiques")["description"],
                parametres=(Parametre("sujet", choix=tuple(_outil_de_l_accueil("infos_pratiques")["parameters"]["properties"]["sujet"]["enum"])),),
                ecrit=False,
                local=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            *(_action_de_l_accueil(n) for n in ("ouverture_en_ce_moment", "heure_annoncee", "remises_disponibles", "envoyer_un_sms")),
        ),
    )
)
