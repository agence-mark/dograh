"""[.mark] Lot 8, 8c-2 (109) : la porte du SERVICE (ce que le connecteur « Service » exécute), séparée de la porte de la commande (``commande/porte.py``).

- ``executer_la_fiche_du_service`` : la fiche du service (lot 3, étape 9) : retrouver une commande d'un appel précédent, laisser un message à l'équipe (une fois par appel) ;
- ``executer_un_outil_de_l_accueil`` : les quatre outils de l'accueil (lectures et envoi d'un message), appelés par ``porte._executer`` avec la source ouverte ;
- ``executer`` : l'entrée du connecteur pour ces outils (elle passe par ``porte.executer``, qui ouvre la source et garde la panne au journal).

Le connecteur « Service » n'importe que ce module ; la source s'ouvre par ``porte.ouvrir_la_source`` (ce module n'importe pas la restauration). Contenu déplacé tel quel de ``porte.py``.
"""

from __future__ import annotations

from typing import Any

from api.schemas.apres_appel import numero_e164
from api.services.actions_communes import barrieres as B
from api.services.actions_communes.enveloppe import Enveloppe
from api.services.actions_communes.forme import valeur_dite_par_elle
from api.services.commande import moteur
from api.services.commande import panier as P
from api.services.commande.lire import lecture_sur_une_copie
from api.services.commande.moteur.socle import CLE_STATUT_LU, STATUTS_PERDUS
from api.services.commande.porte import (
    A_FAIRE_DE_LA_COMMANDE_PERDUE,
    CLE_DES_PAROLES,
    faits_publics_de_la_commande,
    ouvrir_la_source,
    poser_l_issue,
    regles_de_la_commande,
)
from api.services.commande.porte import executer as executer_de_la_commande


async def executer(action: Any, arguments: dict[str, Any], ctx: Any, delai_s: float) -> dict[str, Any]:
    """Un outil de l'accueil exécuté par la porte de la commande (``OUTILS_DE_L_ACCUEIL``), pour le connecteur « Service »."""
    return await executer_de_la_commande(action, arguments, ctx, delai_s)


def _laisser_un_message(message: Any, fiche: dict[str, Any], ctx: Any, resultats: list[dict], refus: list[dict]) -> None:
    """Le message à l'équipe, UNE fois par appel (E30) : la demande est écrite, l'issue de l'appel et sa mesure posées (lot 6, C10 ; sens repris de
    test_message_et_redites_m102_m113 et test_restauration_service_client, comme l'ancienne action ``laisser_un_message``). Un second message est refusé."""
    from api.services.service_client.action import _ecrire_la_demande

    if not (isinstance(message, dict) and str(message.get("objet") or "").strip()):
        return
    if fiche.get(CLE_MESSAGE_LAISSE):
        refus.append(B.refus("message_deja_laisse_dans_cet_appel", ["laisser_un_message"], reste="un seul message par appel"))
    elif _ecrire_la_demande(ctx, str(message["objet"]).strip()[:500], urgence := ("urgente" if _message_urgent(message, fiche) else "normale"), None):
        fiche[CLE_MESSAGE_LAISSE] = True
        resultats.append({"operation": "laisser_un_message", "statut_du_module": "OK", "faits": {"urgent": urgence == "urgente"}})
        poser_l_issue(ctx, "message_a_transmettre")
        from api.services.integrations.connectors import mesures as mesures_des_connecteurs

        mesures_des_connecteurs.ecrire(ctx.fiche, "service.message_laisse", "service.fiche", urgence)


async def executer_la_fiche_du_service(fiche_du_modele: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """La fiche du service (lot 3, étape 9) : retrouver une commande d'un appel précédent (par le numéro qui appelle, ou par un numéro dit ;
    un téléphone dicté seulement avec le numéro de la commande, D60 ; jamais un numéro qu'elle n'a pas dit, B7 point 8) et laisser un message à
    l'équipe, UNE fois par appel (E30)."""
    from api.services.integrations.connectors.actions.service import (
        retrouver_par_telephone_dicte_exige_le_numero,
    )

    entier = B.fiche_illisible(fiche_du_modele)
    if entier is not None:
        return Enveloppe("REJETEE", raison=entier["raison"], a_faire=entier["a_faire"], plus={"refus": [entier]}).vers_json()
    fiche = ctx.fiche if isinstance(ctx.fiche, dict) else {}
    affiche = numero_e164((ctx.appel or {}).get("caller_number"))
    paroles = list(fiche.get(CLE_DES_PAROLES) or [])
    resultats: list[dict] = []
    refus: list[dict] = []
    a_preciser: dict[str, str] = {}
    introuvable = ""
    perdue = ""  # une commande refusée ou en échec : l'offre du message, tenue par le modèle
    demande = fiche_du_modele.get("retrouver_une_commande_enregistree")
    if isinstance(demande, dict):
        numero_dit = str(demande.get("numero_de_commande") or "").strip() or None
        telephone = str(demande.get("telephone") or "").strip() or None
        inventes = [c for c, v in (("telephone", telephone), ("numero_de_commande", numero_dit)) if v and not valeur_dite_par_elle(v, c if c == "telephone" else "prenom", paroles)]
        if inventes:
            refus.append(B.refus("valeur_pas_dans_ses_mots", ["retrouver_une_commande_enregistree"], valeurs={c: "" for c in inventes},
                                 reste="un numéro se prend seulement s'il est dit"))
        else:
            exige = retrouver_par_telephone_dicte_exige_le_numero(fiche_du_modele, affiche, f"Q-{int(fiche.get('service_prochain_q') or 1)}")
            if exige is not None:
                fiche["service_prochain_q"] = int(fiche.get("service_prochain_q") or 1) + 1
                return exige
            regles = regles_de_la_commande(ctx)
            p = P.du_dossier(ctx.fiche)
            appelant = moteur.Appelant(affiche, str(ctx.run_id) if getattr(ctx, "run_id", None) else None)
            async with ouvrir_la_source(ctx) as source:
                r = await moteur.retrouver_commande(source, p, regles, appelant, numero_dit)
            # R-d : le suivi ne montre jamais le panier (un panier vide trompe) ; ce qui manque (le numéro de la commande) ou ce qui se choisit
            # (plusieurs commandes, F4 : leurs candidats, numéro court et heure dite) est rendu en faits, jamais un « FAIT » muet que le modèle comble de lui-même.
            # E-36 : le statut lu reste au code (``_faits_gardes``) ; le modèle n'a que la valeur fermée ``etat``.
            resultats.append({"operation": "retrouver_une_commande_enregistree", "statut_du_module": r.statut, "faits": faits_publics_de_la_commande(r)})
            if r.statut == "OK" and r.faits.get(CLE_STATUT_LU):
                fiche[CLE_COMMANDE_RETROUVEE] = r.faits[CLE_STATUT_LU]
                if r.faits[CLE_STATUT_LU] in STATUTS_PERDUS and not fiche.get(CLE_MESSAGE_LAISSE):  # 7b-C4 : un message déjà laissé dans l'appel n'est plus proposé (la porte le refuserait)
                    perdue = A_FAIRE_DE_LA_COMMANDE_PERDUE
            if r.statut in ("INCOMPLETE", "AMBIGU") and r.manque:
                a_preciser = {"manque": r.manque}  # 7b-C4 : la phrase du module n'est plus donnée au modèle ; C7 B4 : lu sur le manque, plus sur le texte
            elif r.statut == "INTROUVABLE":
                # P4 : le numéro de l'appel est connu et rien n'y est trouvé : le dire, puis chercher autrement ; jamais redemander ce numéro
                introuvable = "dis-lui qu'il n'y a pas de commande à ce numéro ; propose de chercher autrement (le numéro de la commande, ou un autre numéro) ; ne redemande pas le numéro de l'appel"
    _laisser_un_message(fiche_du_modele.get("laisser_un_message"), fiche, ctx, resultats, refus)
    statut = "PARTIEL" if refus and resultats else ("REJETEE" if refus else ("A_PRECISER" if a_preciser else ("INTROUVABLE" if introuvable else "FAIT")))
    premier = refus[0] if refus else None
    return Enveloppe(statut, resultats=resultats, raison=premier["raison"] if premier else None, a_faire=premier["a_faire"] if premier else (introuvable or perdue or None),
                     plus={**({"refus": refus} if refus else {}), **a_preciser}).vers_json()


CLE_MESSAGE_LAISSE = "service_message_laisse"
# B5 (audit des textes § 2.5, « urgent si la commande est en cours ») : le statut de la commande retrouvée dans cet appel, lu par le code ;
# un message laissé pendant qu'elle est en cours est urgent sans que le modèle ait à le juger.
CLE_COMMANDE_RETROUVEE = "service_commande_retrouvee_statut"
STATUTS_FINIS = frozenset({"terminee", "refusee", "annulee", "echec"})


def _message_urgent(message: dict, fiche: dict) -> bool:
    """Urgent : elle a dit que cela ne peut pas attendre (case du modèle), ou la commande retrouvée dans l'appel est en cours (le code)."""
    statut = fiche.get(CLE_COMMANDE_RETROUVEE)
    return message.get("urgent") is True or (bool(statut) and statut not in STATUTS_FINIS)


# Les quatre outils de l'accueil (textes prouvés, ``textes/gemma-4/outils.json``) : des lectures et un envoi du moteur, sans écriture dans le panier
# (règle nommée ``lecture_sur_une_copie``). Le connecteur « service » les déclare, la porte les exécute avec la source de l'agent (``porte.executer``, qui ouvre la source et appelle ``executer_un_outil_de_l_accueil``).
OUTILS_DE_L_ACCUEIL = ("ouverture_en_ce_moment", "heure_annoncee", "remises_disponibles", "envoyer_un_sms")


RAISON_DU_STATUT_DE_L_ACCUEIL = {
    "DEJA_FAIT": "deja_fait", "REFUSEE": "envoi_impossible", "INDISPONIBLE": "envoi_indisponible", "ARGUMENT_INVALIDE": "arguments_illisibles",
}


async def executer_un_outil_de_l_accueil(nom: str, source: Any, p: dict[str, Any], regles: Any, arguments: dict[str, Any], ctx: Any) -> dict[str, Any]:
    copie = lecture_sur_une_copie(p)
    mode = arguments.get("mode_de_retrait")
    mode = mode if mode in ("emporter", "livraison") else None
    appel_id = str(ctx.run_id) if getattr(ctx, "run_id", None) else None
    if nom == "ouverture_en_ce_moment":
        r = await moteur.etat_ouverture(source, copie, regles, mode)
    elif nom == "heure_annoncee":
        r = await moteur.heure_annoncee(source, copie, regles, mode)
    elif nom == "remises_disponibles":
        r = await moteur.remises_disponibles(source, copie, regles, demande=True, presse=False, refus=False, appel_id=appel_id)
    else:
        appelant = moteur.Appelant(numero_e164((ctx.appel or {}).get("caller_number")), appel_id)
        r = await moteur.envoyer_un_message(source, copie, regles, appelant, arguments.get("quoi"), getattr(ctx, "organization_id", None))
    faits = {k: v for k, v in (r.faits or {}).items() if k != "panier"}
    resultats = [{"operation": nom, "statut_du_module": r.statut}]
    if nom != "envoyer_un_sms":
        # Les trois lectures : le fait lu va au modèle tel quel (fermé, en pause, heure non calculée) ; seul un mode ou une zone qui manque se précise.
        if r.statut == "INCOMPLETE":
            return Enveloppe("A_PRECISER", resultats=resultats, faits=faits, plus={"manque": r.manque}).vers_json()
        return Enveloppe("LU", resultats=resultats, faits=faits).vers_json()
    if r.statut in ("OK", "RETENU", "TROUVE", "LU"):
        return Enveloppe("LU", resultats=resultats, faits=faits).vers_json()
    # ligne 87 : un statut de l'envoi hors de l'enveloppe (éteint, déjà parti, refusé) est dit au modèle, jamais une erreur levée (panne dite au client)
    return Enveloppe("REJETEE", resultats=resultats, faits=faits, raison=RAISON_DU_STATUT_DE_L_ACCUEIL.get(r.statut, "rien_a_faire")).vers_json()
