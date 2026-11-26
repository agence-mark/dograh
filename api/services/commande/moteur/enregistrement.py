"""[.mark] Moteur de la commande : l'enregistrement : le numéro et le prénom de la personne, la finalisation, l'enregistrement de la commande.

Le moteur est découpé par sujet (``moteur/__init__.py`` garde tous les noms publics) ; les gestes sont ceux de l'ancien ``moteur.py``, inchangés.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from api.services.commande import etape as ETAPE
from api.services.commande import panier as P
from api.services.commande.resultat import Resultat, avec_numero_affiche, avec_numeros_retenus
from api.services.commande.source import Source
from api.services.actions_communes import journal_du_dit as J
from api.services.commande.etat_pour_le_modele import manque_de_l_identite
from api.services.commande.phrases_du_manque import Manque
from api.services.commande.moteur.socle import prealable_du_metier, Appelant, CLE_NOTES_DU_GREFFIER, Reglages, _avec, _r
from api.services.commande.moteur.prealables import CLES_DE_L_ETAT, chiffrer_le_panier, _prealables, _zone_id, noter_la_fermeture, verifier_le_creneau
from api.services.commande.moteur.articles import _reprendre_les_dits, choix_obligatoire

from api.services.commande.moteur.reglement import _numero_dit, _relecture_deja_dite, poser_la_relecture, regler, relecture_entendue, rendu_de_monnaie
from api.services.commande.moteur.proposition import proposer_un_article_en_plus


# Le journal du dit pour le numéro (n° 44) : les refus de la personne, les demandes de nouveau numéro dites, les propositions du numéro affiché
CLE_NUMERO_REFUSE, CLE_NUMERO_DEMANDE, CLE_NUMERO_PROPOSE = "numero_refuse", "numero_demande", "numero_propose"
TYPE_DE_LA_QUESTION_DU_NUMERO = "numero_affiche"  # C7 : la question « je note le numéro qui s'affiche ? », numérotée comme les autres (règle 4 des cases)


def repondre_au_numero_affiche(p: dict[str, Any], sens: str | None, appelant: "Appelant") -> Resultat:
    """C7 : la réponse à la question du numéro qui s'affiche (``reponse`` citant sa question) : « accepte » le note dans le client, « refuse » est écrit au
    journal du dit (``numero_refuse``), « autre » laisse la question posée. Le numéro affiché n'est jamais gardé sans cette réponse (avant : une seconde
    ``finaliser`` de la même fiche valait pour un « oui »). La réponse écrit son effet dans la commande ou au journal, plus de drapeau posé ici et retiré au
    passage suivant (n° 44)."""
    if sens == "accepte":
        if appelant.telephone_affiche and not p["client"].get("telephone"):
            p["client"]["telephone"] = appelant.telephone_affiche
        return Resultat("OK", {"numero_affiche": "accepte"}, "")
    if sens == "refuse":
        J.noter(p, CLE_NUMERO_REFUSE)
        return Resultat("OK", {"numero_affiche": "refuse"}, "")
    return Resultat("OK", {"rien_ajoute": True}, "")


def noter_le_client(p: dict[str, Any], *, telephone: str | None, prenom: str | None, second_numero: str | None = None) -> Resultat | None:
    """n° 30 : le prénom et le numéro dits s'écrivent dans la commande (``client``) UNE fois, au tour où ils sont dits ; la fin ne les rejoue plus d'une seconde copie.
    PE-1 (Q7-3, Pierre 26/11) : le second numéro s'écrit de même (``client["second_numero"]``, joint au ticket et à la commande en base) ; illisible, il est refusé seul,
    rien n'est écrit pour lui, et le fait est le même que pour le numéro (``numero_illisible``, le modèle le redemande d'après le fait).
    ``None`` : écrit (ou rien de dit) ; sinon le refus d'un numéro illisible, rien n'est écrit pour lui."""
    client = p["client"]
    if prenom and prenom.strip():
        client["prenom"] = " ".join(prenom.split())[:60]
    numero = _numero_dit(telephone) if telephone else None
    second = _numero_dit(second_numero) if second_numero else None
    if numero:
        client["telephone"] = numero
    if second and second != client.get("telephone"):  # le même numéro dit deux fois n'est gardé, dit et envoyé qu'une fois
        client["second_numero"] = {"numero": second, "qui": None, "pourquoi": None}
    for dit, retenu, case in ((telephone, numero, "telephone"), (second_numero, second, "second_numero")):
        if dit and retenu is None:
            return _avec(_r("ARGUMENT_INVALIDE", {"numero_illisible": True}, "", case), p)
    return None


async def identifier(source: Source, p: dict[str, Any], regles: Reglages, appelant: Appelant, *, telephone: str | None, prenom: str | None) -> Resultat | None:
    """Lot 4 (M39) : le numéro (celui qui s'affiche est proposé une fois ; un numéro dicté est relu par le code), puis le prénom (celui de la fiche
    du client quand le numéro est connu). ``None`` : la personne est identifiée."""
    client = p["client"]
    illisible = noter_le_client(p, telephone=telephone, prenom=prenom)
    if illisible is not None:
        return illisible
    if client.get("telephone") and not client.get("prenom"):
        connu = await source.client(client["telephone"])  # les faits de la source : le prénom que le restaurant connaît pour ce numéro
        if connu and connu.get("prenom"):
            client["prenom"] = connu["prenom"]
    manque = manque_de_l_identite(p)  # G4 : le même manque que l'état montre au modèle ; ``identifier`` lui donne les faits, il ne décide pas à sa place
    if manque is Manque.TELEPHONE:
        if J.fois(p, CLE_NUMERO_REFUSE) > J.fois(p, CLE_NUMERO_DEMANDE):
            J.noter(p, CLE_NUMERO_DEMANDE)  # un refus, la demande d'un nouveau numéro, une seule fois ; si elle ne dicte rien, le numéro affiché lui est reproposé
            return _avec(_r("INCOMPLETE", {}, "", "telephone"), p)  # C6 n° 10 : le modèle demande le numéro (le manque), le code ne dit rien
        if appelant.telephone_affiche:
            if J.fois(p, CLE_NUMERO_PROPOSE) <= J.fois(p, CLE_NUMERO_REFUSE):
                J.noter(p, CLE_NUMERO_PROPOSE)  # une proposition « en cours » de plus que de refus : la question du registre est ouverte
            return _avec(_r("INCOMPLETE", {}, "", "confirmer_numero"), p)  # C6 n° 10 : le modèle propose le numéro qui s'affiche (la question née, par son type)
    if manque is Manque.TELEPHONE:
        return _avec(_r("INCOMPLETE", {}, "", "telephone"), p)  # C7 B5 : le modèle demande le numéro d'après le manque
    if manque is Manque.PRENOM:
        return _avec(_r("INCOMPLETE", {}, "", "prenom"), p)  # C7 B5 : le modèle demande le prénom d'après le manque
    return _relire_le_numero_dicte(p, regles, appelant)


def _relire_le_numero_dicte(p: dict[str, Any], regles: Reglages, appelant: Appelant) -> Resultat | None:
    """DC10 (Evan, 22/11) : un numéro DICTÉ (pas celui qui s'affiche) est relu par paires avant l'enregistrement et attend son « oui » ; réglable
    (motif ``numero_dicte_relu``), allumé par défaut ; éteint : enregistré dès qu'il est dit, comme avant. ``None`` : rien à relire."""
    from api.services.actions_communes.resultat import numero_en_lettres

    tel = (p.get("client") or {}).get("telephone")
    question = (regles.question_numero_dicte or "").strip()
    if not question or not tel or tel == appelant.telephone_affiche or p.get("numero_dicte_accepte") == tel:
        return None
    return _avec(_r("INCOMPLETE", {}, question.replace("{numero}", numero_en_lettres(tel)), "confirmer_numero_dicte"), p)


def repondre_au_numero_dicte(p: dict[str, Any], sens: str | None, appelant: Appelant | None = None) -> Resultat:
    """DC10 : la réponse à la relecture du numéro dicté : « accepte » le garde (``numero_dicte_accepte``), « refuse » l'efface de la commande et de ce qui a été
    dit pour la fin (il se redemande, ``numero_refuse``), « autre » laisse la question posée. La réponse écrit son effet dans la commande (n° 44)."""
    if sens == "accepte":
        p["numero_dicte_accepte"] = (p.get("client") or {}).get("telephone")
        return Resultat("OK", {"numero_dicte": sens}, "")
    if sens == "refuse":
        p["client"]["telephone"] = None
        J.noter(p, CLE_NUMERO_REFUSE)
        return Resultat("OK", {"numero_dicte": sens}, "")
    return Resultat("OK", {"rien_ajoute": True}, "")


CONSIGNE_AUCUNE = "aucune"


def demander_la_consigne_livreur(source: Source, p: dict[str, Any], r: Resultat) -> Resultat:
    """Lot 4 (C7) : un mode qui exige une adresse demande UNE fois une consigne pour le livreur, avec le récapitulatif (le fait
    ``consigne_livreur: a_demander`` dans son retour) ; elle ne bloque jamais l'enregistrement (B12, conversation 1 : la commande s'enregistre sans
    elle) ; « aucune » est une réponse (rien n'est noté). Une consigne déjà dite (avec l'adresse, ou par le greffier) n'est jamais redemandée."""
    # B6 (rustine 37) : demandée une fois par appel, au journal de ce qui est dit
    if not p.get("mode") or not source.exige_une_zone(p["mode"]) or p.get("consigne_livreur") or not J.une_fois(p, "consigne_livreur"):
        return r
    return Resultat(r.statut, {**r.faits, "consigne_livreur": "a_demander"}, r.suggestion, r.manque)


async def retenir_une_habitude(source: Source, telephone: str, texte: str) -> bool:
    """Lot 4 (M41) : une HABITUDE du client (« sonnez au 2e »), écrite sur sa fiche pour ses prochains appels ; jamais la consigne de cette commande.
    Rend vrai si elle est retenue ; une donnée que la fiche du client refuse (une donnée de santé) ne vit que dans la commande (faux)."""
    ecrite = await source.consigne(telephone, texte)
    return not (ecrite.statut == "ARGUMENT_INVALIDE" and ecrite.faits.get("raison") == "pour_la_commande")


def _consigne_du_livreur(p: dict[str, Any]) -> str | None:
    """Lot 16 : la consigne pour le livreur de CETTE commande (celle de la fiche, sinon celle que le greffier a notée), sans « aucune » : elle part à la caisse dans ``delivery_notes``."""
    consigne = str(p.get("consigne_livreur") or "").strip() or str((p.get(CLE_NOTES_DU_GREFFIER) or {}).get("consigne_livreur") or "").strip()
    return None if not consigne or consigne.casefold() == CONSIGNE_AUCUNE else consigne


def _note_de_la_commande(p: dict[str, Any]) -> str | None:
    """La note envoyée avec la commande (E22, rien n'écrase rien) : la note de la commande, la consigne pour le livreur de CETTE commande, puis
    ce que le greffier a noté et que la fiche ne dit pas déjà (``note.composer_la_note_de_commande``, lot 6)."""
    from api.services.commande.note import composer_la_note_de_commande

    morceaux = [{"texte": str(p["note"])}] if p.get("note") else []
    consigne = str(p.get("consigne_livreur") or "").strip()
    if consigne and consigne.casefold() != CONSIGNE_AUCUNE and all(consigne != m["texte"] for m in morceaux):
        morceaux.append({"texte": f"livreur : {consigne}"})
    note = composer_la_note_de_commande(morceaux, p.get(CLE_NOTES_DU_GREFFIER))
    return note  # la taille est tenue par la composition : l'allergie n'est jamais coupée (D23)


def _brouillon_de_la_commande(p: dict[str, Any], chiffre: Resultat, paiement: dict[str, Any], appelant: Appelant, regles: Reglages) -> dict[str, Any]:
    client = p["client"]
    return {
        "mode": p["mode"], "lignes": P.pour_le_chiffrage(p), "zone_id": _zone_id(p), "adresse": p.get("adresse"),
        "client": {"telephone": client["telephone"], "prenom": client.get("prenom"), "second_numero": client.get("second_numero")},
        "paiement": {"moyens": paiement["moyens"], "rendu_sur": paiement["rendu_sur"]}, "note": _note_de_la_commande(p), "consigne_livreur": _consigne_du_livreur(p),
        "heure_voulue": datetime.fromisoformat(p["heure_voulue"]) if p.get("heure_voulue") else None,
        "appel_id": appelant.appel_id, "cree_par": "agent",
        # Les remises que le chiffrage vient de calculer : l'enregistrement les recalcule et refuse tout écart (jamais un montant du modèle).
        "remises": [{"ref": r["ref"]} for r in chiffre.faits.get("remises") or []], "codes": list(p.get("codes_dits") or []),
    }


async def enregistrer(source: Source, p: dict[str, Any], regles: Reglages, appelant: Appelant, chiffre: Resultat, paiement: dict[str, Any]) -> Resultat:
    """Lot 4 (M39, M40) : l'enregistrement, une fois par appel (E30) ; le récapitulatif approuvé en est la preuve (son jeton). C6 n° 5 (décision d'Evan 25/11 9 h 30) : le résultat
    porte des faits (l'heure dite ``quand_dit``, le mode, le rendu de monnaie ``rendu``) ; le modèle dit la confirmation, la porte dit ensuite le rendu (motif réglé) et la question M108."""
    await _garder_l_habitude(source, p)
    jeton = (p.get("relecture") or {}).get("jeton") or uuid.uuid4().hex
    r = await source.enregistrer(_brouillon_de_la_commande(p, chiffre, paiement, appelant, regles), jeton)
    return _apres_l_ecriture(source, p, r, chiffre, paiement)


async def reecrire(source: Source, p: dict[str, Any], regles: Reglages, appelant: Appelant, chiffre: Resultat, paiement: dict[str, Any], numero: str) -> Resultat:
    """Lot 8b-1b (E4 ; § 17 l.404) : la commande ``numero`` de CET appel, changée après le « oui », est réécrite à sa place en base (même numéro) ; le résultat a les faits
    de l'enregistrement, l'étape reste « enregistrée » avec la nouvelle empreinte. Rien ne part en caisse : la fin de l'appel enverra cette version."""
    await _garder_l_habitude(source, p)
    jeton = (p.get("relecture") or {}).get("jeton") or uuid.uuid4().hex
    r = await source.reecrire_la_commande(numero, _brouillon_de_la_commande(p, chiffre, paiement, appelant, regles), jeton)
    return _apres_l_ecriture(source, p, r, chiffre, paiement)


async def _garder_l_habitude(source: Source, p: dict[str, Any]) -> None:
    """Une habitude dite (M41) est retenue sur la fiche du client ; refusée par la fiche (donnée de santé), elle va dans la note de la commande."""
    if p.get("habitude"):
        if not await retenir_une_habitude(source, p["client"]["telephone"], p["habitude"]):
            p["note"] = (f"{p['note']} ; {p['habitude']}" if p.get("note") else p["habitude"])[:300]
        p["habitude"] = None


def _apres_l_ecriture(source: Source, p: dict[str, Any], r: Resultat, chiffre: Resultat, paiement: dict[str, Any]) -> Resultat:
    """Ce que l'écriture rend devient l'étape et les faits de la commande : écrite (ou déjà faite), ses faits et l'empreinte du panier écrit ; la relecture à refaire ; un refus tel quel."""
    if r.statut in ("ENREGISTREE", "DEJA_FAIT"):
        faits = {**r.faits, "monnaie": paiement["monnaie"]}
        rendu = rendu_de_monnaie(paiement)
        if rendu:
            faits["rendu"] = rendu
        ETAPE.transition(p, ETAPE.ENREGISTREE_EN_CAISSE, faits=P.serialisable(faits), empreinte=P.empreinte(p), commande=P.commande_recue(p))
        statut = source.statut_de_l_enregistrement() if r.statut == "ENREGISTREE" else "DEJA_FAIT"
        return _avec(Resultat(statut, faits), p)  # aucune phrase : le modèle dit le fait accompli d'après ses faits, le journal en garde les faits
    if r.statut == "INCOMPLETE" and r.manque == "relecture":
        ETAPE.transition(p, ETAPE.ACCORD_RETIRE)  # la relecture repart : l'accord d'avant ne vaut plus
        return poser_la_relecture(source, p, chiffre)
    return _avec(r, p)


def question_de_la_ligne_en_attente(p: dict[str, Any]) -> Resultat | None:
    """File d'attente des questions (lot 20, appel 450) : la question d'une ligne qui attend son choix (une taille), lue dans l'ÉTAT du panier, jamais
    gardée à part : tant qu'une ligne attend, sa question existe, quel que soit le résultat qui a suivi dans la fiche. ``None`` : aucune ligne n'attend."""
    en_attente = P.a_completer(p)
    if not en_attente:
        return None
    q = en_attente[0]["attente"]
    return _avec(choix_obligatoire({"article": en_attente[0]["nom"], "article_de_la_carte": en_attente[0]["article_nom"], "question": q}), p)


async def finaliser(source: Source, p: dict[str, Any], regles: Reglages, appelant: Appelant, **gestes: Any) -> Resultat:
    """La fin, puis le numéro dicté et RETENU dans cet appel, porté en fait (``avec_numeros_retenus``) et dit par le code (motif ``numero_retenu``, C6 n° 10) : un numéro corrigé se
    relit tel que retenu, jamais de mémoire. Le numéro est celui que la commande garde (``client``, écrit au tour où il est dit, n° 30), quel que soit le geste qui l'a apporté. Le numéro
    qui s'affiche n'est jamais relu ; un numéro déjà dit n'est pas redit tant qu'il ne change pas.

    M98 : quand le numéro gardé est celui qui s'affiche, il est porté dans les faits (``numero_affiche_dit``) pour que l'agent puisse le dire si on
    le lui demande, sans être ajouté à la phrase."""
    if gestes.get("telephone"):
        # Un numéro dicté est jugé et RETENU dès qu'il est dit, à n'importe quelle étape de la fin (M78, M98) : refusé s'il est invalide, sinon gardé pour
        # être dit par le code, tel que retenu, avec la suite ; jamais attendu de l'étape où l'on demande le numéro.
        dicte = _numero_dit(gestes["telephone"])
        if dicte is None:
            faits = {"numero_illisible": True}
            return _avec(_r("ARGUMENT_INVALIDE", faits, "", "telephone"), p)
        if not p.get("enregistree"):
            p.setdefault("client", {})["telephone"] = dicte
    return _avec_les_numeros_retenus(await _finaliser(source, p, regles, appelant, **gestes), p, regles, appelant)


def _avec_les_numeros_retenus(r: Resultat, p: dict[str, Any], regles: Reglages, appelant: Appelant) -> Resultat:
    """Le résultat de la fin avec le numéro qui s'affiche en fait (M98), puis le numéro dicté et le second numéro RETENUS dans la commande (``client``) portés en faits pour que le code les dise,
    chacun une fois : jamais celui qui s'affiche, ni un numéro déjà dit, ni celui que la question réglée de la relecture (DC10) dira."""
    client = p["client"]
    if appelant.telephone_affiche and client.get("telephone") == appelant.telephone_affiche:
        r = avec_numero_affiche(r, appelant.telephone_affiche)
    tel = client.get("telephone")
    dit = tel if tel and tel != appelant.telephone_affiche and client.get("numero_dit") != tel else None
    second = (client.get("second_numero") or {}).get("numero")
    second_dit = second if second and client.get("second_numero_dit") != second else None  # PE-1 (Q7-3) : le second numéro retenu se dit une fois, comme le premier
    if r.statut in ("DEJA_FAIT", "TRANSMISE"):
        return r
    if dit and r.manque == "confirmer_numero_dicte":
        client["numero_dit"] = dit  # DC10 : la question de relecture dit le numéro ; il n'est pas redit après
        dit = None
    elif dit and (regles.question_numero_dicte or "").strip():
        dit = None  # DC10 allumé : la question de relecture du numéro le dira, une seule fois
    if dit is None and second_dit is None:
        return r
    if r.statut != "ENREGISTREE" and r.manque != "relecture":
        return r  # C6 n° 10 : le numéro retenu se dit avec une suite du code (le total de la relecture, la confirmation) ; sinon il attend (gardé dans la commande, ``client``)
    if dit:
        client["numero_dit"] = dit
    if second_dit:
        client["second_numero_dit"] = second_dit
    return avec_numeros_retenus(r, dit, second_dit)


async def _finaliser(
    source: Source, p: dict[str, Any], regles: Reglages, appelant: Appelant, *, confirmer: bool = False, prenom: str | None = None,
    telephone: str | None = None, moyen: str | None = None, rendu_sur: Any = None, part: Any = None, moyen_reste: str | None = None,
) -> Resultat:
    """Lot 4 (M38 à M40) : la fin nommée, une seule, dans l'ordre d'un commerçant (appel 2631, Evan, 18/11) : les articles complets, l'ouverture et
    le créneau, la proposition en plus (une fois), ``poser_la_relecture`` (avec ``demander_la_consigne_livreur``) et son accord, ``regler``, ``identifier``,
    ``enregistrer``. Un manque à la fois ; une commande incomplète n'est jamais enregistrée ; un panier changé après l'accord se relit (seulement ce
    qui a changé). Le total est celui de la source."""
    deja = p.get("enregistree")
    if deja and p["lignes"]:
        return _avec(Resultat("DEJA_FAIT", dict(deja)), p)
    manque = await _prealables(source, p, regles)
    if manque is not None:
        return manque
    await _reprendre_les_dits(source, p, regles)  # SA-33 : ce qui était gardé avant les préalables n'est jamais oublié à la fin
    # G4 : les manques des lignes (les articles, la variante) se décident par la fonction que l'état montre au modèle, ``manque_des_lignes`` : inconditionnelle,
    # jamais derrière l'adresse ou la zone ; les suivants demandent la source (ouverture, créneau, total) et restent ici dans l'ordre d'un commerçant
    from api.services.commande.etat_pour_le_modele import manque_de_la_relecture, manque_des_lignes

    des_lignes = manque_des_lignes(p)
    if des_lignes is Manque.ARTICLES:
        return _avec(_r("INCOMPLETE", {}, "", "articles"), p)
    if des_lignes is Manque.VARIANTE:
        attente = question_de_la_ligne_en_attente(p)
        if attente is not None:
            return attente
    chiffre = await chiffrer_le_panier(source, p, regles)
    if chiffre.statut != "OK":
        return _avec(chiffre, p)
    total = chiffre.faits["total"]
    etat = await source.etat(p["mode"])
    if not etat["ouvert"] and not p.get("heure_voulue"):
        faits_fermes = {k: etat.get(k) for k in CLES_DE_L_ETAT}
        if etat.get("planifiee_permise"):
            # D15 : fermé, mais le réglage du type permet de commander pour plus tard : l'heure voulue est LA question (une seule).
            p["a_planifier"] = True
            prochaine = etat.get("prochaine_ouverture")
            dire = getattr(source, "quand_dit", None)
            if isinstance(prochaine, datetime) and dire is not None:
                # Lot 19, aparté d'Evan (20/11) : « le plus naturel, c'est de proposer une commande pour le prochain service qui commence à telle heure,
                # et de faire confirmer par le client » : l'heure de la réouverture est proposée, la personne la confirme (question ``heure_proposee``).
                faits = {**faits_fermes, "a_planifier": True, "heure_proposee": prochaine.isoformat(), "heure_proposee_dite": await dire(prochaine)}
                noter_la_fermeture(p)
                return _avec(_r("FERME_PLANIFIABLE", faits, "", "heure_proposee"), p)
            faits = {**faits_fermes, "a_planifier": True}
            noter_la_fermeture(p)
            return _avec(_r("FERME_PLANIFIABLE", faits, "", "heure_voulue"), p)
        noter_la_fermeture(p)
        return _avec(_r(etat["statut"], faits_fermes, ""), p)
    refus = await verifier_le_creneau(source, p)
    if refus is not None:
        return refus
    proposition = await proposer_un_article_en_plus(source, p, regles, chiffre)
    if proposition is not None:
        return _avec(proposition, p)
    attente_allergie = await prealable_du_metier(source, p, regles)  # lot 15 : les faits d'une allergie connue sont donnés au modèle AVANT la relecture et l'enregistrement
    if attente_allergie is not None:
        return attente_allergie
    # 1. Le récapitulatif et son accord (``poser_la_relecture``, la seule relecture)
    # M2 (n° 46) : un seul accord (l'étape ACCORDEE), qui vaut pour la relecture entendue : celle de l'empreinte et du total d'aujourd'hui
    relue = p.get("relecture") or {}
    dit = bool(relue.get("recapitulatif") and relue.get("empreinte") == P.empreinte(p) and relue.get("total") == total)
    if manque_de_la_relecture(p) is not None or not dit:  # G4 : le manque que l'état montre au modèle (« d'autres articles » ou « son accord »)
        if dit and confirmer:
            ETAPE.transition(p, ETAPE.ACCORD_DONNE)
            confirmer = False  # le oui valait pour le récapitulatif, pas pour la suite
        elif dit and relecture_entendue(p):
            return _relecture_deja_dite(p, total)  # ``dit`` sans entendue : la phrase du total n'est jamais partie à la voix (fiche refusée, PE-1) : la relecture se repose, son total se dit
        else:
            return demander_la_consigne_livreur(source, p, poser_la_relecture(source, p, chiffre))
    # 2. Le règlement, 3. le numéro et le prénom, 4. l'enregistrement (la consigne pour le livreur est demandée avec le récapitulatif)
    paiement, refus = await regler(source, p, total, moyen=moyen, rendu_sur=rendu_sur, part=part, moyen_reste=moyen_reste)  # les faits du règlement : le dit, validé par la source
    if refus is not None:
        return refus  # la question ou le refus du règlement est celui de ``regler`` (sans moyen dit, il pose lui-même la question)
    manque = await identifier(source, p, regles, appelant, telephone=telephone, prenom=prenom)
    if manque is not None:
        return manque
    return await enregistrer(source, p, regles, appelant, chiffre, paiement)
