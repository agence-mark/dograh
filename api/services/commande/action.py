"""[.mark] Mécanisme commun : les sept outils de la commande, joués comme les autres actions internes (deadline, estampille, résultat utile).

Le connecteur interne ``commande`` (``integrations/connectors/actions/commande.py``) rend ici : ``executer(action, arguments, ctx, delai_s)``.
Le panier vit dans la fiche de l'appel (``ctx.fiche``), la source du catalogue est ouverte pour UN geste (``source.ouvrir``), le moteur fait le
travail (``moteur.py``) et son ``Resultat`` fermé devient le retour de l'outil : ``{statut, faits, suggestion, manque}``.

- Les arguments du modèle sont coupés à ce que l'action déclare ; la base, l'établissement et l'organisation ne viennent jamais du modèle.
- Un module coupé (``commande_sur_catalogue`` faux) : aucun geste, un refus fermé.
- Une panne du catalogue ou de la base ne casse jamais l'appel : ``INDISPONIBLE``, et le contenu de la commande en cours est joint au message
  laissé à l'équipe (W24, ``_noter``).
- Après une commande enregistrée, la suivante repart d'un panier neuf (le client, le mode et la zone restent).
"""

from __future__ import annotations

from dataclasses import is_dataclass, replace
from datetime import date, datetime
from typing import Any

from loguru import logger

from api.db.bases_clients.horloge import horloge
from api.schemas.apres_appel import numero_e164
from api.services.apres_appel.rappels import CLE_RAPPEL, ORIGINE_COMMANDE
from api.services.integrations.connectors import etat_par_tache
from api.services.restauration import mesures as mesures_du_module
from api.services.commande import moteur, panier as P, source as registre_des_sources
from api.services.commande.reglages import reglages_de_la_commande
from api.services.commande.resultat import Resultat, avec_le_fait_du_numero_affiche, numero_est_dit, question_apres_enregistrement, question_du_numero_affiche

# Les gestes qui changent le panier : après une commande enregistrée, ils repartent d'un panier neuf.
GESTES_QUI_CHANGENT = frozenset({"choisir_mode", "ajouter", "modifier", "retirer", "vider_commande", "verifier_adresse"})
CLE_TACHES_FINIES = "commandes_terminees"  # le nombre de commandes déjà passées dans l'appel : la tâche en cours est la suivante
MODELE_DE_LA_TACHE = etat_par_tache.Modele(champs=(), compteurs=("refus",))
SOURCE_DE_L_OUTIL = "source"  # clé du réglage de l'outil qui nomme sa source ; vide : ``classeur``


def _jsonable(valeur: Any) -> Any:
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    if isinstance(valeur, dict):
        return {str(k): _jsonable(v) for k, v in valeur.items()}
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in valeur]
    return valeur


def _retour(r: Resultat, **plus: Any) -> dict[str, Any]:
    sortie = {"statut": r.statut, "faits": _jsonable(r.faits), "suggestion": r.suggestion, **plus}
    if r.manque:
        sortie["manque"] = r.manque
    return sortie


def _texte(arguments: dict[str, Any], cle: str) -> str | None:
    valeur = arguments.get(cle)
    return str(valeur).strip() or None if valeur is not None else None


def _entier(valeur: Any) -> int | None:
    """Une quantité dite : ``3``, ``3.0`` ; jamais un booléen, jamais une fraction."""
    if isinstance(valeur, bool):
        return None
    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        return None
    return int(nombre) if nombre.is_integer() else None


def _precisions(a: dict[str, Any]) -> dict[str, str]:
    """Le choix, le retrait, la note et les moitiés dits avec les articles (``ajouter`` passé par ``choisir_mode``) : jamais perdus en route."""
    return {cle: v for cle in ("choix", "sans", "note", "moities") if (v := _texte(a, cle))}


async def _geste(source, p: dict[str, Any], regles: moteur.Reglages, nom: str, a: dict[str, Any], ctx) -> Resultat:
    if nom == "choisir_mode":
        r = await moteur.choisir_mode(source, p, regles, _texte(a, "mode"), _texte(a, "heure"))
        articles = _texte(a, "articles")
        if articles and r.statut in ("OK", "FERME_PLANIFIABLE") and r.manque in (None, "articles", "zone"):
            # Le mode et les articles dits dans la même phrase : un seul geste (le modèle n'enchaîne pas toujours les deux appels).
            # M116 (appel 2598) : la zone qui manque encore ne fait plus perdre les articles : ``ajouter`` les garde (SA-33) et
            # pose la même question de la zone ; ils sont pris dès que l'adresse est vérifiée.
            ajout = await moteur.ajouter(source, p, regles, articles=articles, **_precisions(a))
            if ajout.manque == "zone":
                # Gardés : le résultat du mode tel quel (sa question de la zone), avec le panier qui dit ce qui attend.
                return Resultat(r.statut, {**r.faits, **ajout.faits}, r.suggestion, r.manque)
            if r.statut == "FERME_PLANIFIABLE" and ajout.statut == "OK":
                # D15 : la fermeture et le créneau proposé ne se perdent pas quand les articles suivent dans le même geste.
                return Resultat("FERME_PLANIFIABLE", {**ajout.faits, "a_planifier": True}, f"{r.faits['fermeture']} {ajout.suggestion}".strip(), ajout.manque)
            return ajout
        if articles and not p.get("mode") and r.statut not in ("OK", "FERME_PLANIFIABLE"):
            # SA-52 (appel 2602) : le mode refusé (pas offert, mal dit) ne fait pas perdre les articles dits avec lui : gardés (SA-33),
            # pris dès qu'un mode est posé ; la question du mode reste la même.
            moteur._garder_le_dit(p, {"articles": articles, **_precisions(a)})
            return moteur._avec(r, p)
        return r
    if nom == "ajouter" and _texte(a, "mode") and moteur._mode_dit(source, _texte(a, "mode")) not in (None, p.get("mode")):
        # 2571 : le mode dit dans la même phrase arrive parfois par ``ajouter`` (le modèle ne choisit pas toujours ``choisir_mode``) : un seul
        # geste, comme ``choisir_mode`` accepte déjà les articles. Mécanisme commun : le préalable dit est posé, puis les articles suivent.
        return await _geste(source, p, regles, "choisir_mode", a, ctx)
    if nom == "ajouter":
        await moteur.garder_l_heure(source, p, _texte(a, "heure"))  # D15 : une heure dite dès le premier tour est gardée jusqu'à finaliser
        return await moteur.ajouter(
            source, p, regles, articles=_texte(a, "articles"), choix=_texte(a, "choix"), sans=_texte(a, "sans"), note=_texte(a, "note"), moities=_texte(a, "moities"),
        )
    if nom == "modifier":
        quantite = _entier(a["quantite"]) if "quantite" in a else None
        if "quantite" in a and quantite is None:
            return Resultat("ARGUMENT_INVALIDE", {}, "Combien exactement ?", "quantite")
        return await moteur.modifier(
            source, p, regles, ligne=_texte(a, "ligne"), quantite=quantite, choix=_texte(a, "choix"), sans=_texte(a, "sans"), note=_texte(a, "note"), moities=_texte(a, "moities"),
        )
    if nom == "retirer":
        return await moteur.retirer(source, p, regles, ligne=_texte(a, "ligne"))
    if nom == "vider_commande":
        return await moteur.vider_commande(source, p, regles)
    if nom == "etat_ouverture":
        return await moteur.etat_ouverture(source, p, regles, _texte(a, "mode"))
    if nom == "heure_annoncee":
        return await moteur.heure_annoncee(source, p, regles, _texte(a, "mode"))
    if nom == "verifier_adresse":
        return await moteur.verifier_adresse(source, p, regles, _texte(a, "adresse"))
    if nom == "resoudre_une_date":
        return await moteur.resoudre_une_date(source, p, regles, _texte(a, "texte"), _texte(a, "heure"))
    if nom == "remises_disponibles":
        return await moteur.remises_disponibles(source, p, regles, demande=a.get("demande") is True, presse=a.get("presse") is True, refus=a.get("refus") is True, appel_id=str(ctx.run_id) if ctx.run_id else None)
    if nom == "voir_produit":
        return await moteur.voir_produit(source, p, regles, _texte(a, "produit"), _texte(a, "a_eviter"))
    if nom == "reconnaitre_le_client":
        return await moteur.reconnaitre_le_client(source, p, regles, confirmer_consignes=a.get("confirmer_consignes") is True)
    if nom == "retrouver_commande":
        return await moteur.retrouver_commande(
            source, p, regles, moteur.Appelant(numero_e164((ctx.appel or {}).get("caller_number")), str(ctx.run_id) if ctx.run_id else None), _texte(a, "numero")
        )
    if nom == "envoyer_un_message":
        return await moteur.envoyer_un_message(
            source, p, regles, moteur.Appelant(numero_e164((ctx.appel or {}).get("caller_number")), str(ctx.run_id) if ctx.run_id else None), _texte(a, "quoi"), ctx.organization_id
        )
    if nom == "voir_commande":
        return await moteur.voir_commande(source, p, regles)
    if nom == "finaliser":
        appelant = moteur.Appelant(numero_e164((ctx.appel or {}).get("caller_number")), str(ctx.run_id) if ctx.run_id else None)
        return await moteur.finaliser(
            source, p, regles, appelant,
            prenom=_texte(a, "prenom"), telephone=_texte(a, "telephone"), second_numero=_texte(a, "second_numero"), second_qui=_texte(a, "second_qui"),
            second_pourquoi=_texte(a, "second_pourquoi"), moyen=_texte(a, "moyen"), part=a.get("part"), moyen_reste=_texte(a, "moyen_reste"),
            rendu_sur=a.get("rendu_sur"), note=_texte(a, "note"), consigne=_texte(a, "consigne"), confirmer=a.get("confirmer") is True,
            heure_voulue=_texte(a, "heure"), articles=_texte(a, "articles"), en_plus=a.get("en_plus") if isinstance(a.get("en_plus"), bool) else None,
        )
    raise ValueError(f"Geste de commande inconnu : {nom!r}")


PHRASE_DE_PANNE = "Je n'arrive pas à enregistrer la commande à l'instant : je la transmets à l'équipe, qui vous rappelle pour la prendre."


def _joindre_la_commande_au_message_de_l_equipe(p: dict[str, Any], ctx: Any) -> bool:
    """W24 : une panne en pleine commande ne perd rien. Le contenu de la commande en cours est écrit dans la fiche comme demande de rappel
    (l'après-appel en fait le message laissé à l'équipe), une seule entrée « commande » par appel, remplacée à chaque panne."""
    if not p["lignes"] or not isinstance(ctx.fiche, dict):
        return False
    entree = {
        "origine": ORIGINE_COMMANDE, "mode": "rappel", "numero": numero_e164((ctx.appel or {}).get("caller_number")) or None,
        "objet": moteur.contenu_dit(p), "souhait": None, "le": horloge(ctx.organization_id).maintenant().isoformat(),
    }
    liste = ctx.fiche.setdefault(CLE_RAPPEL, [])
    if not isinstance(liste, list):
        liste = ctx.fiche[CLE_RAPPEL] = []
    for i, ancienne in enumerate(liste):
        if isinstance(ancienne, dict) and ancienne.get("origine") == ORIGINE_COMMANDE:
            liste[i] = entree
            return True
    liste.append(entree)
    return True


async def _dire_au_flux(source: Any, geste: str, avant: int, p: dict[str, Any], r: Resultat, ctx: Any) -> None:
    """Ce que le portail montre en direct : le panier qui change, la commande créée. Jamais une panne de l'appel (la source écrit au journal)."""
    hook = getattr(source, "apres_le_geste", None)
    if hook is None:
        return
    try:
        await hook(geste, avant, p, r, ctx)
    except Exception as erreur:  # noqa: BLE001 -- R1 : au journal ; un flux qui ne part pas ne casse jamais l'appel, le portail relit la base
        logger.error(f"[.mark] Order tool {geste}: live feed not written: {erreur!r}")


async def executer(action: Any, arguments: dict[str, Any], ctx: Any, delai_s: float) -> dict[str, Any]:
    """Un geste de la commande. Ne lève pas pour une panne du catalogue : ``INDISPONIBLE`` (R1 : au journal), la commande en cours jointe à l'équipe."""
    regles = reglages_de_la_commande(ctx.configurations)
    if regles is None:
        return {"statut": "INDISPONIBLE", "faits": {}, "suggestion": ""}
    # M98 : la question du numéro qui s'affiche, réglée à l'écran (phrases du code), à l'endroit de l'appel.
    if is_dataclass(regles):
        # M108 : la question qui finit la confirmation d'un enregistrement, réglée de même.
        regles = replace(regles, question_numero_affiche=question_du_numero_affiche(ctx), question_apres_enregistrement=question_apres_enregistrement(ctx))
    p = P.du_dossier(ctx.fiche)
    if p.get("enregistree") and action.nom in GESTES_QUI_CHANGENT:
        p = P.repartir_de_zero(ctx.fiche)
        if isinstance(ctx.fiche, dict):
            ctx.fiche[CLE_TACHES_FINIES] = int(ctx.fiche.get(CLE_TACHES_FINIES) or 0) + 1
    # Lot 7 (W21) : l'état de la tâche « cette commande » : remis à zéro quand la suivante commence (le panier a ses propres champs ; ici, ce que mesurent les outils).
    etat_de_la_tache = etat_par_tache.commencer(ctx.fiche, MODELE_DE_LA_TACHE, f"commande-{int((ctx.fiche or {}).get(CLE_TACHES_FINIES) or 0) + 1}")
    affiche = numero_e164((ctx.appel or {}).get("caller_number"))
    if affiche and isinstance(p.get("client"), dict):
        p["client"].setdefault("telephone_affiche", affiche)  # le numéro qui s'affiche : lu par une remise qui reconnaît le client (lot 7)
    avant = p["version"]
    try:
        from api.services.restauration.recherche_reglages import reglages_de_la_recherche

        async with registre_des_sources.ouvrir(
            (ctx.reglages or {}).get(SOURCE_DE_L_OUTIL), ctx, reglages_de_recherche=reglages_de_la_recherche(ctx.configurations)
        ) as source:
            r = await _geste(source, p, regles, action.nom, arguments, ctx)
            await _dire_au_flux(source, action.nom, avant, p, r, ctx)
    except Exception as erreur:  # noqa: BLE001 -- R1 : au journal, l'outil dit « indisponible », l'appel continue
        logger.error(f"[.mark] Order tool {action.nom} failed: {erreur!r}")
        transmise = _joindre_la_commande_au_message_de_l_equipe(p, ctx)
        panne = {
            "statut": "INDISPONIBLE", "faits": {"panier": P.resume(p), "transmise_a_l_equipe": transmise},
            "suggestion": PHRASE_DE_PANNE if transmise else "",
        }
        mesures_du_module.de_la_commande(ctx.fiche, action.nom, panne)
        return panne
    plus: dict[str, Any] = {}
    if action.nom == "finaliser" and (r.manque == "relecture" or r.statut in ("ENREGISTREE", "TRANSMISE") or numero_est_dit(r.faits)):
        # W17 : la relecture, puis la confirmation finale (heure et total) sont DITES PAR LE CODE : le modèle ne les prononce pas, il ne peut
        # ni y ajouter ni y retirer un article. Le conseil de l'outil (réglable dans sa fiche, T-01) ; les autres retours restent reformulés.
        plus["_restitution"] = "dit_par_le_code"
    retour = avec_le_fait_du_numero_affiche(_retour(r, **plus), affiche)  # M110 : le modèle sait qu'un numéro s'affiche
    mesures_du_module.de_la_commande(ctx.fiche, action.nom, retour)
    if mesures_du_module.est_un_refus(retour):
        etat_par_tache.compter(etat_de_la_tache, "refus")
    return retour
