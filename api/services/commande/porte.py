"""[.mark] La porte d'entrée de la commande (chantier Partie 1) : ce que le connecteur ``commande`` exécute.

- ``lire`` (lot 2, E16) : la lecture, qui n'écrit jamais rien (``services/commande/lire.py``) ;
- ``fiche`` : la fiche à cases, exécutée case par case dans l'ordre du banc (lot 3, ``executer_la_fiche``).

La source (le catalogue) est ouverte une fois par appel d'outil, comme avant ; une panne du catalogue ne lève pas : ``INDISPONIBLE`` au journal (R1).
"""

from __future__ import annotations

from dataclasses import is_dataclass, replace
from types import SimpleNamespace
from typing import Any

from loguru import logger

from api.db.bases_clients.horloge import horloge
from api.schemas.apres_appel import numero_e164
from api.services.actions_communes import barrieres as B
from api.services.actions_communes.arguments import en_json
from api.services.actions_communes.cases_liees import cases_ecartees
from api.services.actions_communes.enveloppe import Enveloppe
from api.services.actions_communes.forme import valeur_dite_par_elle
from api.services.actions_communes.idempotence import cle_d_idempotence, deja_executee
from api.services.actions_communes.plafonds import plafond_d_operations
from api.services.actions_communes.types import ConsigneLivreur
from api.services.apres_appel.rappels import CLE_RAPPEL, ORIGINE_COMMANDE
from api.services.commande import contrat, etat_pour_le_modele, moteur
from api.services.commande import panier as P
from api.services.commande import source as registre_des_sources
from api.services.commande.lire import lire
from api.services.commande.reglages import reglages_de_la_commande
from api.services.commande.resultat import (
    Resultat,
    question_apres_enregistrement,
    question_du_numero_affiche,
)
from api.services.commande.source import Source
from api.services.integrations.connectors.outil import nom_vu
from api.services.restauration import mesures as mesures_du_module

SOURCE_DE_L_OUTIL = "source"  # clé du réglage de l'outil qui nomme sa source ; vide : ``classeur`` (reprise de ``action.py``)


def _regles(ctx: Any):
    regles = reglages_de_la_commande(ctx.configurations)
    if regles is not None and is_dataclass(regles):
        regles = replace(regles, question_numero_affiche=question_du_numero_affiche(ctx), question_apres_enregistrement=question_apres_enregistrement(ctx))
    return regles


# --------------------------------------------------------------------------- la fiche de la commande (lot 3)

# L'ordre d'exécution des cases (``banc-b5/contrat_b5.py`` ``fiche_vers_items``, aux noms de la version finale ; vérifié contre le guichet de
# ``banc-b13/commande_b13.py`` ``executer_fiche``) : vider et annuler, réponse, retraits, changements, ajouts, informations, c'est tout.
ORDRE_DES_CASES = (
    "vider_le_panier", "annuler_la_commande", "reponse", "retirer_article", "changer_quantite", "ajouter",
    "mode_de_retrait", "adresse", "commune", "consigne_livreur", "heure", "moyen_de_paiement", "rendu_sur", "telephone", "prenom", "note_generale",
    "code_de_remise", "reduction_annoncee", "c_est_tout",
)
INFORMATIONS = ("mode_de_retrait", "adresse", "commune", "consigne_livreur", "heure", "moyen_de_paiement", "rendu_sur", "telephone", "prenom", "note_generale",
                "code_de_remise", "reduction_annoncee")
CLE_DES_PAROLES = "paroles_de_la_personne"
CLE_DIT_PAR_LE_CODE = "dit_par_le_code"
MOYENS_DE_LA_FICHE = {"carte_bancaire": "carte", "especes": "especes", "titre_restaurant": "titre_restaurant", "carte_bancaire_a_la_livraison": "carte_livraison"}
TYPES_DE_QUESTION = {"CHOIX_OBLIGATOIRE": "variante", "AMBIGU": "ambiguite"}
MANQUES_DE_QUESTION = {"relecture": "relecture", "vente_en_plus": "proposition"}


def ordre_des_cases(fiche: dict[str, Any]) -> list[str]:
    """Les cases remplies de la fiche, dans l'ordre du code (jamais celui du modèle)."""
    return [c for c in ORDRE_DES_CASES if fiche.get(c) not in (None, "", [], False)]


def _schema_de_la_fiche(ctx: Any) -> dict[str, Any]:
    from api.services.integrations.connectors.actions.commande import COMMANDE
    from api.services.integrations.connectors.outil import _propriete

    return {p.nom: _propriete(p, getattr(ctx, "appel", None) or {}) for p in COMMANDE.action("fiche").parametres}


def _cases_montrees(ctx: Any) -> list[str] | None:
    from api.services.workflow.cases_selon_l_etat import CLE_DES_CASES_MONTREES

    montrees = (getattr(ctx, "fiche", None) or {}).get(CLE_DES_CASES_MONTREES) or {}
    for nom in ("fiche", nom_vu(getattr(ctx, "fiche", None), "fiche")):
        if isinstance(montrees.get(nom), list):
            return montrees[nom]
    return None


def _question_de(r: Resultat, numero: int, tour: int) -> dict[str, Any] | None:
    """La question que pose un retour du moteur, numérotée par le code (E5) ; ``None`` quand le retour ne pose rien."""
    type_ = TYPES_DE_QUESTION.get(r.statut) or MANQUES_DE_QUESTION.get(r.manque or "")
    if type_ is None:
        return None
    q = {"id": f"Q-{numero}", "type": type_, "texte": r.suggestion, "nee_au_tour": tour}
    proposition = (r.faits or {}).get("proposition")
    if type_ == "proposition" and isinstance(proposition, dict):
        q.update({"article_propose": proposition.get("nom"), "offerte": bool(proposition.get("offre")), "offre": proposition.get("offre")})
    if isinstance((r.faits or {}).get("candidats"), list):
        q["choix"] = [str(c) for c in r.faits["candidats"]][:4]
    return q


def _resultat_public(operation: str, r: Resultat) -> dict[str, Any]:
    faits = en_json({k: v for k, v in (r.faits or {}).items() if k != "panier"})
    return {"operation": operation, "statut_du_module": r.statut, **({"manque": r.manque} if r.manque else {}), "faits": faits}


async def repondre_a_la_question(source: Source, p: dict[str, Any], regles: moteur.Reglages, appelant: moteur.Appelant, question: dict, sens: str | None,
                                 valeurs: list[str] | None) -> Resultat:
    """La réponse rangée par son identifiant (E5) et sa case fermée (E6), selon le type de la question ; le corps des règles est réécrit au lot 4."""
    texte = ", ".join(str(v) for v in valeurs or [] if str(v).strip()) or None
    if question["type"] == "relecture":
        if sens == "accepte":
            p["relecture_acceptee"] = True
            return Resultat("OK", {"recapitulatif": "accepte"}, "")
        p["relecture_acceptee"] = False
        return Resultat("OK", {"recapitulatif": sens or "autre"}, "")
    if question["type"] == "proposition":
        if sens == "autre":
            return Resultat("OK", {"rien_ajoute": True, "question_gardee": True}, "")  # B8 point 1 : « autre » ne prend ni ne refuse
        if p.get("vente_en_plus_tot") and isinstance(p.get("proposition_en_plus"), dict):
            # La proposition faite juste après le premier article (appel 2631, repris de ``action.vers_la_question_en_attente``) : le oui l'ajoute et
            # la commande continue (« autre chose ? »), jamais un saut vers la fin ; le non la retire. Elle ne vaut qu'une fois.
            proposee = p.pop("proposition_en_plus")
            p["vente_en_plus_tot"] = False
            if sens != "accepte":
                return Resultat("OK", {"rien_ajoute": True}, "")
            return await ajouter_un_article(source, p, regles, {"article": proposee["nom"], "quantite": 1})
        return await moteur.finaliser(source, p, regles, appelant, en_plus=sens == "accepte")
    if sens == "refuse" and not texte:
        return Resultat("OK", {"rien_ajoute": True}, "")
    choix = texte or (question.get("choix") or [None])[0] if sens == "accepte" else texte
    return await moteur._repondre(source, p, regles, choix=choix, sans=None, note=None, moities=None)


async def ajouter_un_article(source: Source, p: dict[str, Any], regles: moteur.Reglages, article: dict[str, Any]) -> Resultat:
    """Un article de la case ``ajouter``, structuré (sans phrase à redécouper) : nom, quantité, variante, retraits, suppléments, composition, moitiés."""
    nom = str(article.get("article") or "").strip()
    variante = str(article.get("variante") or "").strip()
    if variante == "autre":
        variante = ""
    texte = f"{nom} {variante}".strip()
    choix = ", ".join([*(article.get("supplements") or []), *(article.get("composition") or [])]) or (variante or None)
    sans = ", ".join(str(s) for s in article.get("sans") or []) or None
    moities = ", ".join(str(m) for m in article.get("moities") or []) or None
    quantite = article.get("quantite") if isinstance(article.get("quantite"), int) and not isinstance(article.get("quantite"), bool) else 1
    prealable = await moteur._prealables(source, p, regles)
    if prealable is not None:
        # SA-33 : sans mode ni zone, l'article est GARDÉ tel que dit et pris dès qu'ils sont posés (jamais perdu, jamais doublé).
        moteur._garder_le_dit(p, {"articles": f"{quantite} {texte}", "choix": choix, "sans": sans, "note": article.get("precision_article"), "moities": moities})
        return Resultat("OK", {"garde": texte, "quantite": quantite}, "")
    return await moteur._un_article(source, p, regles, quantite, texte, choix=choix, sans=sans, note=article.get("precision_article"), moities=moities, tout_seul=True)


async def vente_en_plus_apres_le_premier_article(source: Source, p: dict[str, Any], regles: moteur.Reglages, r: Resultat) -> Resultat | None:
    """Juste après le premier article pris, la vente en plus : UN article précis, une seule fois par commande (note de Pierre, méthode Domino's ;
    déplacée telle quelle de ``action.apres_le_geste_conduit``, sinon perdue avec lui). Le corps de la proposition est réécrit au lot 4."""
    if r.statut != "OK" or not regles.vente_en_plus or p.get("vente_en_plus_faite") or not p.get("lignes") or P.a_completer(p):
        return None
    chiffre = await moteur._chiffrer(source, p, regles)
    if chiffre.statut != "OK":
        return None
    p["vente_en_plus_faite"] = True
    proposition = await moteur._vente_en_plus(source, p, regles, chiffre)
    if proposition is None:
        return None
    p["vente_en_plus_tot"] = True
    return Resultat("OK", {**r.faits, **proposition.faits}, proposition.suggestion, "vente_en_plus")


async def poser_le_mode(source: Source, p: dict[str, Any], regles: moteur.Reglages, mode: str | None, adresse: str | None, commune: str | None) -> Resultat | None:
    """Le mode, l'adresse et la commune posés par la MÊME opération (S3) : jamais une adresse sans son mode, jamais l'adresse avalée ailleurs."""
    r = None
    if mode:
        r = await moteur.choisir_mode(source, p, regles, mode)
    if adresse and not commune:
        # la rue dite après la commune (« à Chantilly », puis « au 9 avenue du Bouteiller ») : la commune déjà posée reste celle de l'adresse
        commune = (p.get("adresse") or {}).get("commune") if isinstance(p.get("adresse"), dict) else None
    if adresse or commune:
        r = await moteur.verifier_adresse(source, p, regles, ", ".join(x for x in (adresse, commune) if x))
    return r


async def executer_la_fiche(fiche_du_modele: dict[str, Any], contexte: Any) -> dict[str, Any]:
    """La fiche du modèle exécutée par le code, dans son ordre ; rend l'enveloppe (statut, résultats, question numérotée, refus et ``a_faire``)."""
    ctx = contexte
    source, p, regles = ctx.source, ctx.panier, ctx.regles
    fiche = fiche_du_modele
    # 1. La fiche entière : lisible, cases montrées dans ce tour (D52), bons types, réponse attendue, bonne question.
    entier = B.fiche_illisible(fiche)
    if entier is None:
        fiche = {k: v for k, v in fiche.items() if v is not None}
        montrees = _cases_montrees(ctx)
        if montrees is None:
            entier = B.refus("cases_pas_ouvertes", ["*"], a_faire="rien n'est changé : les cases de ce tour ne sont pas connues")
        else:
            question = p.get("question") if isinstance(p.get("question"), dict) else None
            posee = contrat.question_posee(question, (ctx.fiche or {}).get(contrat.CLE_DU_TOUR, 0))
            entier = (B.case_sans_objet(fiche, montrees) or B.format(fiche, _schema_de_la_fiche(ctx))
                      or B.reponse_manquante(fiche, question, posee) or B.question_inconnue(fiche, question))
    if entier is not None:
        return Enveloppe("REJETEE", raison=entier["raison"], a_faire=entier["a_faire"], plus={"refus": [entier], "cases_refusees": entier["cases"],
                                                                                              "fiche_appliquee": False}).vers_json()
    # 2. Rejouée à l'identique dans ce tour : rien ne change (E11).
    tour = (ctx.fiche or {}).get(contrat.CLE_DU_TOUR, 0)
    if deja_executee(p, cle_d_idempotence(tour, "fiche", fiche)):
        return Enveloppe("FAIT", faits={"deja_fait": True}, plus={"fiche_appliquee": False, "rien_ajoute": True}).vers_json()
    # 3. Les barrières d'une case, puis le filet des cases liées (D8).
    refus: list[dict] = []
    plafond = plafond_d_operations(fiche)
    if plafond is not None:
        refus.append(plafond)
    paroles = list((ctx.fiche or {}).get(CLE_DES_PAROLES) or [])
    dit = list((ctx.fiche or {}).get(CLE_DIT_PAR_LE_CODE) or [])
    for case, choix in (("mode_de_retrait", list(source.modes)), ("moyen_de_paiement", list(MOYENS_DE_LA_FICHE))):
        if fiche.get(case) not in (None, ""):
            valeur, r = B.valeur_hors_liste(case, fiche[case], [*choix, contrat.AUTRE])
            if r is not None or valeur == contrat.AUTRE:
                refus.append(r or B.refus("valeur_hors_liste", [case], choix=choix))
            else:
                fiche[case] = valeur
    if p.get("enregistree") and fiche.get("c_est_tout") is True:
        refus.append(B.refus("deja_fait", ["c_est_tout"], a_faire="rien n'est changé : la commande de cet appel est déjà enregistrée"))
    libres = B.valeur_pas_dans_ses_mots(fiche, paroles, dit)
    if libres is not None:
        refus.append(libres)
    reponse = fiche.get("reponse") if isinstance(fiche.get("reponse"), dict) else None
    accepte_ici = bool(reponse and reponse.get("sens") == "accepte" and (p.get("question") or {}).get("type") == "relecture")
    fin = B.recapitulatif_pas_accepte(fiche, contrat.CASES_DE_FIN, bool(p.get("relecture_acceptee")), accepte_ici)
    if fin is not None:
        refus.append(fin)
    ecartees = cases_ecartees(c for r in refus for c in r["cases"])
    # 4. Les cases dans l'ordre du code, chacune par son opération nommée.
    resultats: list[dict] = []
    executees: list[str] = []
    dernier: Resultat | None = None
    appelant = moteur.Appelant(numero_e164((ctx.appel or {}).get("caller_number")), str(ctx.run_id) if getattr(ctx, "run_id", None) else None)
    question_avant = p.get("question") if isinstance(p.get("question"), dict) else None
    p["question"] = None if reponse else question_avant
    informations_faites = False
    gardee = False
    for case in ordre_des_cases(fiche):
        if case in ecartees or "*" in ecartees:
            continue
        if case in INFORMATIONS:
            if informations_faites:
                continue
            informations_faites = True
            r = await _poser_les_informations(source, p, regles, appelant, fiche, ecartees)
            operation = "informations"
        elif case == "vider_le_panier":
            r, operation = await moteur.vider_commande(source, p, regles), case
        elif case == "annuler_la_commande":
            r, operation = await annuler(source, p, regles), case
        elif case == "reponse" and ({"vider_le_panier", "annuler_la_commande"} & set(executees)):
            # la question en attente portait sur le panier que cette même fiche vient de vider ou d'annuler : la réponse n'a plus d'objet
            refus.append(B.refus("question_inconnue", ["reponse"], a_faire="rien n'est changé pour reponse : la question en attente a disparu avec le panier"))
            continue
        elif case == "reponse":
            r, operation = await repondre_a_la_question(source, p, regles, appelant, question_avant or {}, reponse.get("sens"), reponse.get("valeurs")), case
            gardee = bool((r.faits or {}).get("question_gardee"))
            if (question_avant or {}).get("type") in ("variante", "ambiguite"):
                # l'article complété par la réponse est pris : la vente en plus suit, comme après un ajout
                resultats.append(_resultat_public(operation, r))
                proposition = await vente_en_plus_apres_le_premier_article(source, p, regles, r)
                r, operation = (proposition, "proposition") if proposition is not None else (r, None)
                if operation is None:
                    dernier = r
                    executees.append(case)
                    continue
        elif case == "retirer_article":
            for n in fiche["retirer_article"]:
                r = await moteur.retirer(source, p, regles, ligne=str(n))
                resultats.append(_resultat_public(case, r))
            dernier, operation = r, None
        elif case == "changer_quantite":
            for c in fiche["changer_quantite"]:
                choix = ", ".join([*(c.get("supplements") or []), *(c.get("composition") or [])]) or (c.get("variante") if c.get("variante") not in (None, "autre") else None)
                r = await moteur.modifier(source, p, regles, ligne=str(c.get("ligne")), quantite=c.get("quantite"), choix=choix,
                                          sans=", ".join(c.get("sans") or []) or None, note=c.get("precision_article"))
                resultats.append(_resultat_public(case, r))
            dernier, operation = r, None
        elif case == "ajouter":
            for article in fiche["ajouter"]:
                r = await ajouter_un_article(source, p, regles, article)
                resultats.append(_resultat_public(case, r))
            if r.statut == "OK" and "garde" not in (r.faits or {}):
                # l'état du panier après les ajouts (chiffrage, minimum de la zone), comme ``moteur.ajouter`` le rend après sa phrase
                etat = await moteur._etat_apres_ajout(source, p, regles, dict(r.faits or {}))
                r = Resultat(etat.statut, etat.faits, etat.suggestion, etat.manque)
                resultats[-1] = _resultat_public(case, r)
            proposition = await vente_en_plus_apres_le_premier_article(source, p, regles, r)
            if proposition is not None:
                resultats.append(_resultat_public("proposition", proposition))
                r = proposition
            dernier, operation = r, None
        elif case == "c_est_tout":
            r, operation = await recapituler(source, p, regles, appelant), case
        else:
            continue
        if operation is not None:
            resultats.append(_resultat_public(operation, r))
            dernier = r
        executees.append(case)
    if dernier is not None and dernier.statut in ("OK", "RETENU") and not dernier.manque and not p.get("question") and "c_est_tout" not in executees:
        # les articles gardés faute de mode ou d'adresse sont pris quand la même fiche les pose : la vente en plus suit ce premier article pris
        proposition = await vente_en_plus_apres_le_premier_article(source, p, regles, Resultat("OK", {}, ""))
        if proposition is not None:
            resultats.append(_resultat_public("proposition", proposition))
            dernier = proposition
    if p.get("relecture_acceptee") and not p.get("enregistree") and not p.get("annulee") and "reponse" in executees and dernier is not None:
        dernier = await recapituler(source, p, regles, appelant, confirmer=True)
        resultats.append(_resultat_public("enregistrer", dernier))
    # 5. La prochaine question, numérotée (E5) ; une question née dans ce tour cache sa case (B8 point 1).
    q = _question_de(dernier, int(p.get("prochain_q") or 1), tour) if dernier is not None else None
    if dernier is not None and dernier.statut in STATUTS_ENREGISTRES:
        ctx.enregistrement = dernier  # le résultat brut (dates comprises), lu par le flux du portail et le SMS
    if q is not None and not p.get("question"):
        p["prochain_q"] = int(p.get("prochain_q") or 1) + 1
        p["question"] = q
    elif p.get("question") is None and question_avant and (not reponse or gardee):
        p["question"] = question_avant  # « autre » ne prend ni ne refuse : la question reste posée, sous le même identifiant (B8 point 1)
    return _enveloppe_de_la_fiche(p, resultats, executees, refus, ecartees, dernier)


def _enveloppe_de_la_fiche(p, resultats, executees, refus, ecartees, dernier) -> dict[str, Any]:
    from api.services.actions_communes.enveloppe import Question

    q = p.get("question")
    question = Question(q["id"], q["type"], q.get("texte") or "") if isinstance(q, dict) else None
    bloquant = dernier is not None and dernier.statut in ("INCOMPLETE", "INTROUVABLE", "HORS_ZONE", "RUPTURE", "HORS_CARTE") and dernier.manque not in ("relecture",)
    statut = "PARTIEL" if refus or bloquant else ("ENREGISTREE" if dernier is not None and dernier.statut in STATUTS_ENREGISTRES else ("ANNULEE" if p.get("annulee") else "FAIT"))
    if question is not None and statut == "FAIT" and q.get("type") in ("variante", "ambiguite"):
        statut = "A_PRECISER"
    plus: dict[str, Any] = {"fiche_appliquee": bool(executees), "cases_executees": executees}
    if refus:
        plus["refus"] = refus
        plus["cases_refusees"] = sorted({c for r in refus for c in r["cases"]})
        plus["cases_non_executees_car_liees"] = sorted(ecartees - set(plus["cases_refusees"]) - {"*"})
    faits: dict[str, Any] = {"panier": en_json(P.resume(p))}
    if bloquant:
        faits["fait_bloquant"] = {"statut_du_module": dernier.statut, "manque": dernier.manque}
    premier = refus[0] if refus else None
    return Enveloppe(statut, resultats=resultats, faits=faits, question=question, raison=premier["raison"] if premier else None,
                     a_faire=premier["a_faire"] if premier else None, plus=plus).vers_json()


async def _poser_les_informations(source, p, regles, appelant, fiche, ecartees) -> Resultat:
    """Les informations de la fiche : mode, adresse et commune ensemble (S3), consigne, heure, puis la fin (moyen, billet, téléphone, prénom)."""
    garde = lambda k: fiche.get(k) if k not in ecartees else None
    r = await poser_le_mode(source, p, regles, garde("mode_de_retrait"), garde("adresse"), garde("commune"))
    if garde("consigne_livreur"):
        p["consigne_livreur"] = ConsigneLivreur(texte=str(fiche["consigne_livreur"]), source="modele").texte
    if garde("heure"):
        await moteur.garder_l_heure(source, p, str(fiche["heure"]))
    if garde("note_generale"):
        p["note"] = str(fiche["note_generale"])[: moteur.LONGUEUR_NOTE]
    fin = {k: garde(k) for k in contrat.CASES_DE_FIN if garde(k) not in (None, "")}
    if fin:
        p.setdefault("fin_dite", {}).update({k: (MOYENS_DE_LA_FICHE.get(v, v) if k == "moyen_de_paiement" else v) for k, v in fin.items()})
        if p.get("relecture_acceptee") and not p.get("enregistree"):
            r = await recapituler(source, p, regles, appelant, confirmer=True)
    return r or Resultat("OK", {}, "")


async def recapituler(source: Source, p: dict[str, Any], regles: moteur.Reglages, appelant: moteur.Appelant, confirmer: bool = False) -> Resultat:
    """« c'est tout » : la commande menée à son récapitulatif (puis à l'enregistrement après son accord), un manque à la fois ; le corps est réécrit
    au lot 4 en fonctions nommées, la signature reste."""
    fin = p.get("fin_dite") or {}
    return await moteur.finaliser(source, p, regles, appelant, confirmer=confirmer, prenom=fin.get("prenom"), telephone=fin.get("telephone"),
                                  moyen=fin.get("moyen_de_paiement"), rendu_sur=fin.get("rendu_sur"))


async def annuler(source: Source, p: dict[str, Any], regles: moteur.Reglages) -> Resultat:
    """Elle ne veut plus de la commande en cours : rien n'est enregistré, aucun panier n'est laissé ouvert (A04, E9)."""
    await moteur.vider_commande(source, p, regles)
    p["annulee"] = True
    p["question"] = None
    return Resultat("OK", {"annulee": True}, "")


async def executer_la_fiche_du_service(fiche_du_modele: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """La fiche du service (lot 3, étape 9) : retrouver une commande d'un appel précédent (par le numéro qui appelle, ou par un numéro dit ;
    un téléphone dicté seulement avec le numéro de la commande, D60 ; jamais un numéro qu'elle n'a pas dit, B7 point 8) et laisser un message à
    l'équipe, UNE fois par appel (E30)."""
    from api.services.integrations.connectors.actions.service import (
        retrouver_par_telephone_dicte_exige_le_numero,
    )
    from api.services.service_client.action import _ecrire_la_demande

    entier = B.fiche_illisible(fiche_du_modele)
    if entier is not None:
        return Enveloppe("REJETEE", raison=entier["raison"], a_faire=entier["a_faire"], plus={"refus": [entier]}).vers_json()
    fiche = ctx.fiche if isinstance(ctx.fiche, dict) else {}
    affiche = numero_e164((ctx.appel or {}).get("caller_number"))
    paroles = list(fiche.get(CLE_DES_PAROLES) or [])
    resultats: list[dict] = []
    refus: list[dict] = []
    demande = fiche_du_modele.get("retrouver_une_commande_enregistree")
    if isinstance(demande, dict):
        numero_dit = str(demande.get("numero_de_commande") or "").strip() or None
        telephone = str(demande.get("telephone") or "").strip() or None
        inventes = [c for c, v in (("telephone", telephone), ("numero_de_commande", numero_dit)) if v and not valeur_dite_par_elle(v, c if c == "telephone" else "prenom", paroles)]
        if inventes:
            refus.append(B.refus("valeur_pas_dans_ses_mots", ["retrouver_une_commande_enregistree"], valeurs={c: "" for c in inventes},
                                 a_faire="rien n'est changé : un numéro se prend seulement s'il est dit"))
        else:
            exige = retrouver_par_telephone_dicte_exige_le_numero(fiche_du_modele, affiche, f"Q-{int(fiche.get('service_prochain_q') or 1)}")
            if exige is not None:
                fiche["service_prochain_q"] = int(fiche.get("service_prochain_q") or 1) + 1
                return exige
            regles = _regles(ctx)
            p = P.du_dossier(ctx.fiche)
            appelant = moteur.Appelant(affiche, str(ctx.run_id) if getattr(ctx, "run_id", None) else None)
            from api.services.restauration.recherche_reglages import (
                reglages_de_la_recherche,
            )

            async with registre_des_sources.ouvrir((ctx.reglages or {}).get(SOURCE_DE_L_OUTIL), ctx, reglages_de_recherche=reglages_de_la_recherche(ctx.configurations)) as source:
                r = await moteur.retrouver_commande(source, p, regles, appelant, numero_dit)
            resultats.append({"operation": "retrouver_une_commande_enregistree", "statut_du_module": r.statut, "faits": en_json(r.faits)})
    message = fiche_du_modele.get("laisser_un_message")
    if isinstance(message, dict) and str(message.get("objet") or "").strip():
        if fiche.get(CLE_MESSAGE_LAISSE):
            refus.append(B.refus("message_deja_laisse_dans_cet_appel", ["laisser_un_message"], a_faire="rien n'est changé : un seul message par appel"))
        elif _ecrire_la_demande(ctx, str(message["objet"]).strip()[:500], "urgente" if message.get("urgent") is True else "normale", None):
            fiche[CLE_MESSAGE_LAISSE] = True
            resultats.append({"operation": "laisser_un_message", "statut_du_module": "OK", "faits": {"urgent": message.get("urgent") is True}})
    statut = "PARTIEL" if refus and resultats else ("REJETEE" if refus else "FAIT")
    premier = refus[0] if refus else None
    return Enveloppe(statut, resultats=resultats, raison=premier["raison"] if premier else None, a_faire=premier["a_faire"] if premier else None,
                     plus={"refus": refus} if refus else {}).vers_json()


CLE_MESSAGE_LAISSE = "service_message_laisse"
STATUTS_ENREGISTRES = ("ENREGISTREE", "TRANSMISE")


def _joindre_la_commande_au_message_de_l_equipe(p: dict[str, Any], ctx: Any) -> bool:
    """W24 (A35, sain, déplacé tel quel de ``action.py``) : une panne en pleine commande ne perd rien. Le contenu de la commande en cours est écrit
    dans la fiche comme demande de rappel (l'après-appel en fait le message laissé à l'équipe), une seule entrée « commande » par appel, remplacée à
    chaque panne."""
    if not p["lignes"] or not isinstance(ctx.fiche, dict):
        return False
    entree = {
        "origine": ORIGINE_COMMANDE, "mode": "rappel", "numero": numero_e164((ctx.appel or {}).get("caller_number")) or None,
        "objet": moteur.contenu_dit(p), "souhait": None, "le": horloge(getattr(ctx, "organization_id", None)).maintenant().isoformat(),
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


async def _dire_au_flux(source: Any, avant: int, p: dict[str, Any], enregistrement: Resultat | None, ctx: Any) -> None:
    """Ce que le portail montre en direct (reprise de ``action.py``) : le panier qui change, la commande créée. Jamais une panne de l'appel."""
    hook = getattr(source, "apres_le_geste", None)
    if hook is None:
        return
    try:
        if enregistrement is not None:
            await hook("finaliser", avant, p, enregistrement, ctx)
        else:
            await hook("fiche", avant, p, Resultat("OK", {}, ""), ctx)
    except Exception as erreur:  # noqa: BLE001 -- R1 : au journal ; un flux qui ne part pas ne casse jamais l'appel, le portail relit la base
        logger.error(f"[.mark] commande : flux du direct non écrit : {erreur!r}")


def _mesurer(fiche_de_l_appel: Any, retour: dict[str, Any], mode: str | None) -> None:
    """Les mesures du module (W13), d'après le statut de chaque opération (le Dashboard les lit)."""
    for r in retour.get("resultats") or []:
        mesures_du_module.de_la_commande(fiche_de_l_appel, r.get("operation") or "fiche", {"statut": r.get("statut_du_module"), "faits": {**(r.get("faits") or {}), "mode": mode}})


async def executer(action: Any, arguments: dict[str, Any], ctx: Any, delai_s: float) -> dict[str, Any]:
    regles = _regles(ctx)
    if regles is None:
        return Enveloppe("REJETEE", raison="rien_a_faire").vers_json()
    p = P.du_dossier(ctx.fiche)
    try:
        from api.services.restauration.recherche_reglages import (
            reglages_de_la_recherche,
        )

        async with registre_des_sources.ouvrir(
            (ctx.reglages or {}).get(SOURCE_DE_L_OUTIL), ctx, reglages_de_recherche=reglages_de_la_recherche(ctx.configurations)
        ) as source_ouverte:
            source = etat_pour_le_modele.SourceQuiRetient(source_ouverte)
            if action.nom == "lire":
                return await lire(source, p, regles, dict(arguments or {}), str(ctx.run_id) if getattr(ctx, "run_id", None) else None)
            if action.nom == "fiche":
                avant = p["version"]
                contexte = SimpleNamespace(source=source, panier=p, regles=regles, fiche=ctx.fiche, appel=ctx.appel, run_id=getattr(ctx, "run_id", None),
                                           enregistrement=None)
                retour = await executer_la_fiche(dict(arguments or {}), contexte)
                etat_pour_le_modele.retenir(p, source)
                await _dire_au_flux(source, avant, p, contexte.enregistrement, ctx)
                _mesurer(ctx.fiche, retour, p.get("mode"))
                return retour
    except Exception as erreur:  # noqa: BLE001 -- R1 : au journal, l'appel continue, la commande en cours part à l'équipe (A35)
        logger.error(f"[.mark] commande {action.nom} en échec : {erreur!r}")
        transmise = _joindre_la_commande_au_message_de_l_equipe(p, ctx)
        mesures_du_module.de_la_commande(ctx.fiche, action.nom, {"statut": "INDISPONIBLE", "faits": {}})
        return Enveloppe("REJETEE", raison="rien_a_faire", faits={"indisponible": True, "transmise_a_l_equipe": transmise}).vers_json()
    return Enveloppe("REJETEE", raison="operation_inconnue").vers_json()
