"""[.mark] Module Restauration, lot 22 : le CŒUR du flux en direct (E-23, D2, D11).

UN SEUL FLUX, ÉMIS PAR LE FORK (D2) : tout ce que le portail et les écrans du fork montrent « en direct » (appel qui commence, tour
de parole, outil appelé, commande créée, statut, ticket, rupture, état de la caisse, réservation…) passe par ``emettre`` ; personne
d'autre n'écrit dans le flux. Le portail ÉCOUTE par la route ``GET /restauration/flux`` (``routes/restauration.py``) et RELIT la donnée
dans la base après l'événement : l'événement ne porte que des identifiants et ce qui sert l'affichage immédiat (contrat portail ↔
fork § 3, ``contrat-portail-fork.md``).

Un flux par ORGANISATION ET ÉTABLISSEMENT : une liste Redis (``XADD``) dont la clé porte les deux. Un événement n'est jamais écrit dans
une autre clé, et une lecture ne connaît que les clés qu'on lui donne (la route les vérifie contre la base de l'organisation) : le
cloisonnement tient par construction, pas par un filtre en aval. La liste est bornée (``MAX_EVENEMENTS``) et s'efface d'elle-même
(``DUREE_DE_VIE_S``). Un événement a un identifiant (celui de Redis, croissant) : la reprise par ``Last-Event-ID`` rejoue ce qui a été
manqué, sans perte ni doublon.

D11 : la TRANSCRIPTION n'est émise qu'une fois FINALE (``emettre_tour_final``) ; jamais le texte provisoire. ``appel.tour`` ne s'émet
pas par la voie générale. Le rôle tablette (Employé) ne reçoit jamais ``appel.tour`` (la transcription reste à l'équipe, T-16).

R1 : émettre ne casse jamais l'appelant (un flux en panne s'écrit au journal d'erreur, l'appel continue, le portail relit la base) ;
une lecture qui échoue se voit (événement ``flux.erreur`` au client).
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator, Callable
from datetime import date, datetime
from typing import Any

import redis.asyncio as aioredis
from loguru import logger

from api.constants import REDIS_URL
from api.db.bases_clients.horloge import horloge

MAX_EVENEMENTS = 1000  # par organisation et établissement : les plus récents
DUREE_DE_VIE_S = 6 * 3600
DELAI_ECRITURE_S = 1.0
BLOCAGE_LECTURE_MS = 5000  # une lecture attend au plus 5 s ; sans événement : un battement
NB_BATTEMENTS_MAX = 720  # puis le flux se referme de lui-même (une heure) : le client se reconnecte avec Last-Event-ID
LONGUEUR_TEXTE_MAX = 2000

MOTIFS_D_APPEL = ("Commande", "Réservation", "Question", "Réclamation", "Abandonné")
STATUTS_D_OUTIL = ("appele", "termine", "echec")
ROLES_DE_TOUR = ("agent", "appelant")
SOURCES_DE_STATUT = ("agent", "portail", "caisse")
ETATS_DE_COMMANDE = ("nouvelle", "envoyee", "recue", "acceptee", "en_preparation", "prete", "terminee", "refusee", "annulee", "echec")
MODES_DE_COMMANDE = ("emporter", "livraison", "sur_place")
TYPES_DE_TEMPS = ("emporter", "livraison", "sur_place", "reservation")
MODES_DE_CAISSE = ("normal", "deborde", "pause")
ETATS_DE_LIAISON = ("ok", "erreur", "rompue")
ROLES_D_ECOUTE = ("equipe", "tablette")

# type -> (champs obligatoires, champs facultatifs). C'est le contrat § 3 : un champ en plus ou en moins est refusé à l'émission.
TYPES: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "appel.commence": (frozenset({"appel_id", "agent_id", "telephone_masque"}), frozenset()),
    "appel.tour": (frozenset({"appel_id", "role", "texte"}), frozenset()),
    "appel.outil": (frozenset({"appel_id", "outil", "statut"}), frozenset()),
    "appel.fini": (frozenset({"appel_id", "motif"}), frozenset()),
    "commande.creee": (frozenset({"numero", "numero_court", "mode", "heure_annoncee", "total"}), frozenset()),
    "commande.panier": (frozenset({"appel_id", "version"}), frozenset()),
    "commande.statut": (frozenset({"numero", "de", "vers", "source"}), frozenset()),
    "commande.heure": (frozenset({"numero", "heure_annoncee"}), frozenset()),
    "ticket.imprime": (frozenset({"numero", "code"}), frozenset()),
    "ticket.erreur": (frozenset({"numero", "code"}), frozenset()),
    "rupture.changee": (frozenset({"code_caisse", "disponible"}), frozenset({"fin"})),
    "temps.change": (frozenset({"type"}), frozenset()),
    "caisse.etat": (frozenset({"mode"}), frozenset({"minutes_en_plus", "reprise"})),
    "caisse.liaison": (frozenset({"etat"}), frozenset()),
    "reservation.creee": (frozenset({"reservation_id"}), frozenset()),
    "reservation.changee": (frozenset({"reservation_id"}), frozenset()),
}
# Ce que le rôle tablette ne reçoit jamais.
INTERDITS_A_LA_TABLETTE = frozenset({"appel.tour"})

# Un numéro absent, masqué ou trop court : une valeur que ``verifier`` accepte, jamais un numéro.
NUMERO_INCONNU = "** ** **"
_MASQUE = re.compile(r"^\+?[0-9 ]{0,6}[*][*0-9 ]{2,}$")
_CURSEUR = re.compile(r"^[0-9]{1,18}-[0-9]{1,18}$")
_CURSEURS = re.compile(r"^([0-9]{1,12}:[0-9]{1,18}-[0-9]{1,18})(,[0-9]{1,12}:[0-9]{1,18}-[0-9]{1,18})*$")


class EvenementRefuse(ValueError):
    """Un événement qui n'est pas celui du contrat (type, champs, valeur fermée) : refusé à l'émission."""


def cle_du_flux(organisation_id: int, etablissement_id: int) -> str:
    """La clé d'un flux : l'organisation ET l'établissement. Rien d'autre ne s'écrit ni ne se lit dans cette clé."""
    if any(isinstance(x, bool) or not isinstance(x, int) or x < 1 for x in (organisation_id, etablissement_id)):
        raise EvenementRefuse("Organisation et établissement : des identifiants entiers positifs.")
    return f"mark:resto:flux:{organisation_id}:{etablissement_id}"


def masquer_telephone(telephone: str | None) -> str:
    """``+33612345678`` -> ``+33 6 ** ** ** 78`` : jamais le numéro entier dans le flux."""
    chiffres = re.sub(r"[^0-9]", "", telephone or "")
    if len(chiffres) < 6:
        return NUMERO_INCONNU
    return f"+{chiffres[:2]} {chiffres[2]} ** ** ** {chiffres[-2:]}"


def _valeur(v: Any) -> Any:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if v is None or isinstance(v, (bool, int, str)):
        return v
    raise EvenementRefuse(f"Valeur non permise dans un événement : {type(v).__name__}")


def verifier(type_: str, donnees: dict[str, Any]) -> dict[str, Any]:
    """Les données du contrat, ou ``EvenementRefuse``. Rend une copie (dates écrites en ISO)."""
    if type_ not in TYPES:
        raise EvenementRefuse(f"Type d'événement inconnu : {type_!r}")
    obligatoires, facultatifs = TYPES[type_]
    manque = obligatoires - donnees.keys()
    en_trop = donnees.keys() - obligatoires - facultatifs
    if manque or en_trop:
        raise EvenementRefuse(f"{type_} : champs manquants {sorted(manque)}, en trop {sorted(en_trop)}")
    d = {k: _valeur(v) for k, v in donnees.items()}
    fermees = {
        ("appel.tour", "role"): ROLES_DE_TOUR, ("appel.outil", "statut"): STATUTS_D_OUTIL, ("appel.fini", "motif"): MOTIFS_D_APPEL,
        ("commande.creee", "mode"): MODES_DE_COMMANDE, ("commande.statut", "de"): ETATS_DE_COMMANDE, ("commande.statut", "vers"): ETATS_DE_COMMANDE,
        ("commande.statut", "source"): SOURCES_DE_STATUT, ("temps.change", "type"): TYPES_DE_TEMPS, ("caisse.etat", "mode"): MODES_DE_CAISSE,
        ("caisse.liaison", "etat"): ETATS_DE_LIAISON,
    }
    for (t, champ), permis in fermees.items():
        if t == type_ and d[champ] not in permis:
            raise EvenementRefuse(f"{type_}.{champ} : {d[champ]!r} hors de la liste fermée")
    if type_ == "appel.commence" and not _MASQUE.match(str(d["telephone_masque"])):
        raise EvenementRefuse("appel.commence : le numéro doit être masqué (``masquer_telephone``), jamais en clair")
    if type_ == "appel.tour":
        texte = str(d["texte"]).strip()
        if not texte:
            raise EvenementRefuse("appel.tour : un tour sans texte n'est pas émis")
        d["texte"] = texte[:LONGUEUR_TEXTE_MAX]
    if type_ == "commande.creee" and (isinstance(d["total"], bool) or not isinstance(d["total"], int)):
        raise EvenementRefuse("commande.creee : le total est en centimes entiers")
    return d


# --------------------------------------------------------------------------- l'émetteur (le SEUL)

_redis: aioredis.Redis | None = None


async def _client() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = await aioredis.from_url(REDIS_URL, decode_responses=True, socket_timeout=DELAI_ECRITURE_S, socket_connect_timeout=DELAI_ECRITURE_S)
    return _redis


async def _client_de_lecture() -> aioredis.Redis:
    """Un client à part pour les lectures qui bloquent (son délai de socket dépasse le blocage)."""
    return await aioredis.from_url(
        REDIS_URL, decode_responses=True, socket_timeout=BLOCAGE_LECTURE_MS / 1000 + 5, socket_connect_timeout=DELAI_ECRITURE_S
    )


async def emettre(organisation_id: int, etablissement_id: int, type_: str, donnees: dict[str, Any], *, le: datetime | None = None) -> str | None:
    """Ajoute UN événement au flux de cet établissement. Rend son identifiant, ou ``None`` si le flux est en panne.

    Refuse (``EvenementRefuse``) ce qui n'est pas du contrat : c'est une erreur de programmation, jamais une panne. ``appel.tour`` ne
    passe PAS ici : ``emettre_tour_final``. ``le`` : l'heure de l'événement (source d'heure de l'organisation à défaut, D6)."""
    if type_ == "appel.tour":
        raise EvenementRefuse("appel.tour s'émet par emettre_tour_final : seule la transcription FINALE entre dans le flux (D11)")
    return await _ecrire(organisation_id, etablissement_id, type_, donnees, le)


async def emettre_tour_final(
    organisation_id: int, etablissement_id: int, appel_id: str | int, role: str, texte: str, *, final: bool, le: datetime | None = None
) -> str | None:
    """Un tour de parole. ``final`` doit être vrai : un texte provisoire n'est JAMAIS émis (D11, débit du direct) ; il est simplement
    ignoré (``None``), ce n'est pas une erreur : le pipeline envoie ses provisoires, le flux n'en garde aucun."""
    if not final or not (texte or "").strip():
        return None  # un texte provisoire, ou un silence : rien à montrer
    return await _ecrire(organisation_id, etablissement_id, "appel.tour", {"appel_id": str(appel_id), "role": role, "texte": texte}, le)


async def _ecrire(organisation_id: int, etablissement_id: int, type_: str, donnees: dict[str, Any], le: datetime | None) -> str | None:
    cle = cle_du_flux(organisation_id, etablissement_id)
    propres = verifier(type_, donnees)
    quand = (le or horloge(organisation_id).maintenant()).isoformat()
    try:
        redis = await _client()
        transaction = redis.pipeline(transaction=True)
        transaction.xadd(cle, {"type": type_, "le": quand, "donnees": json.dumps(propres, ensure_ascii=False, separators=(",", ":"))}, maxlen=MAX_EVENEMENTS, approximate=False)
        transaction.expire(cle, DUREE_DE_VIE_S)
        resultat = await asyncio.wait_for(transaction.execute(), DELAI_ECRITURE_S)
        return str(resultat[0])
    except Exception as erreur:  # noqa: BLE001 -- R1 : un flux en panne ne casse jamais l'appelant ; il se voit ici, le portail relit la base
        logger.error(f"[.mark] Live feed {type_} for organization {organisation_id} establishment {etablissement_id} not written: {erreur!r}")
        return None


# --------------------------------------------------------------------------- le panier d'un appel en cours (lot 15)

DUREE_DU_PANIER_S = 3 * 3600


def cle_du_panier(organisation_id: int, etablissement_id: int, appel_id: str | int) -> str:
    """La clé du panier d'un appel : l'organisation, l'établissement ET l'appel. Une lecture avec un autre établissement ne le trouve pas."""
    cle_du_flux(organisation_id, etablissement_id)  # mêmes contrôles d'identifiants
    appel = str(appel_id)
    if not re.fullmatch(r"[0-9]{1,18}", appel):
        raise EvenementRefuse("Appel : un identifiant entier.")
    return f"mark:resto:panier:{organisation_id}:{etablissement_id}:{appel}"


def _centimes(valeur: Any) -> int | None:
    """Un montant en centimes entiers, ou ``None`` (pas chiffré) : jamais un texte, jamais un nombre à virgule."""
    return valeur if isinstance(valeur, int) and not isinstance(valeur, bool) and 0 <= valeur <= 10**9 else None


def _sous_ligne(ligne: dict[str, Any]) -> str:
    """Sous le nom d'une ligne du panier en direct : sa taille, ses choix et ses retraits (« 40 cm, sauce barbecue, sans oignons »). Jamais la note libre
    (elle peut porter une donnée de l'appelant), jamais un prix."""
    morceaux: list[str] = []
    if ligne.get("taille"):
        morceaux.append(str(ligne["taille"]))
    morceaux += [str(c["nom"]) for c in ligne.get("choix") or [] if isinstance(c, dict) and c.get("nom")]
    morceaux += [f"sans {r}" for r in ligne.get("retires") or []]
    return ", ".join(morceaux)[:200]


async def poser_le_panier(organisation_id: int, etablissement_id: int, appel_id: str | int, panier: dict[str, Any]) -> None:
    """Garde ce que le portail montre d'une commande qui se remplit : le mode, les lignes (nom, quantité, prix de la ligne en centimes quand il est chiffré) et le
    total en centimes, rien d'autre (jamais le nom ni l'adresse de l'appelant). Le portail le relit à l'événement ``commande.panier``. Une panne ne casse jamais l'appel (R1)."""
    lignes = []
    for ligne in panier.get("lignes") or []:
        if not (isinstance(ligne, dict) and ligne.get("nom")):
            continue
        rendue = {"nom": str(ligne["nom"])[:120], "quantite": int(ligne.get("quantite") or 1), "prix": _centimes(ligne.get("prix"))}
        detail = _sous_ligne(ligne)
        if detail:
            rendue["sous_ligne"] = detail
        lignes.append(rendue)
    corps = {
        "version": int(panier.get("version") or 0), "mode": panier.get("mode") if panier.get("mode") in MODES_DE_COMMANDE else None, "lignes": lignes[:60],
        "total": _centimes(panier.get("total")),
    }
    zone = (panier.get("zone") or {}).get("nom") if isinstance(panier.get("zone"), dict) else None
    if zone:
        corps["zone"] = str(zone)[:80]  # le NOM de la zone de livraison, jamais l'adresse
    try:
        redis = await _client()
        await asyncio.wait_for(redis.set(cle_du_panier(organisation_id, etablissement_id, appel_id), json.dumps(corps, ensure_ascii=False, separators=(",", ":")), ex=DUREE_DU_PANIER_S), DELAI_ECRITURE_S)
    except Exception as erreur:  # noqa: BLE001 -- R1
        logger.error(f"[.mark] Live cart for organization {organisation_id} establishment {etablissement_id} not written: {erreur!r}")


async def lire_le_panier(organisation_id: int, etablissement_id: int, appel_id: str | int) -> dict[str, Any] | None:
    """Le panier posé pour cet appel dans CET établissement de CETTE organisation, ou ``None`` (inconnu, expiré, ou panne)."""
    try:
        redis = await _client()
        brut = await asyncio.wait_for(redis.get(cle_du_panier(organisation_id, etablissement_id, appel_id)), DELAI_ECRITURE_S)
    except EvenementRefuse:
        return None
    except Exception as erreur:  # noqa: BLE001 -- R1
        logger.error(f"[.mark] Live cart for organization {organisation_id} establishment {etablissement_id} not read: {erreur!r}")
        return None
    return json.loads(brut) if brut else None


# --------------------------------------------------------------------------- ce que le pipeline d'un appel dit -> le flux (final seulement)


def depuis_le_pipeline(evenement: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """Un événement du pipeline (``realtime_feedback_events``) traduit pour le flux, ou ``None`` : tout ce qui est provisoire
    (transcription partielle), technique (latence, erreur, mute) ou hors contrat n'y entre pas. Retourne ``(type, données sans appel_id)``;
    l'appelant ajoute ``appel_id``. D11 : seule la transcription finale de l'appelant, et le texte de l'agent (dit en entier)."""
    nature = evenement.get("type")
    charge = evenement.get("payload") or {}
    if nature == "rtf-user-transcription":
        if charge.get("final") is True and (charge.get("text") or "").strip():
            return "appel.tour", {"role": "appelant", "texte": charge["text"]}
        return None
    if nature == "rtf-bot-text":
        return ("appel.tour", {"role": "agent", "texte": charge["text"]}) if (charge.get("text") or "").strip() else None
    if nature == "rtf-function-call-start" and charge.get("function_name"):
        return "appel.outil", {"outil": str(charge["function_name"]), "statut": "appele"}
    if nature == "rtf-function-call-end" and charge.get("function_name"):
        return "appel.outil", {"outil": str(charge["function_name"]), "statut": "termine"}
    return None


# --------------------------------------------------------------------------- la lecture (reprise, cloisonnement, rôle tablette)


def encoder_curseurs(curseurs: dict[int, str]) -> str:
    return ",".join(f"{etab}:{pos}" for etab, pos in sorted(curseurs.items()))


def decoder_curseurs(valeur: str | None) -> dict[int, str]:
    """``Last-Event-ID`` -> ``{etablissement: position}``. Une valeur mal formée : ignorée (le flux repart du présent)."""
    if not valeur or not _CURSEURS.match(valeur.strip()):
        return {}
    sortie = {}
    for morceau in valeur.strip().split(","):
        etab, pos = morceau.split(":", 1)
        sortie[int(etab)] = pos
    return sortie


def laisse_passer(type_: str, role: str) -> bool:
    return not (role == "tablette" and type_ in INTERDITS_A_LA_TABLETTE)


def _evenement(organisation_id: int, etablissement_id: int, identifiant: str, champs: dict[str, str]) -> dict[str, Any]:
    return {
        "id": identifiant, "type": champs["type"], "organisation": organisation_id, "etablissement": etablissement_id,
        "le": champs["le"], "donnees": json.loads(champs["donnees"]),
    }


async def _derniere_position(redis: aioredis.Redis, cle: str) -> str:
    derniere = await redis.xrevrange(cle, count=1)
    return derniere[0][0] if derniere else "0-0"


async def _perte_depuis(redis: aioredis.Redis, cle: str, position: str) -> bool:
    """Des événements ont-ils été retirés (flux borné) depuis cette position ? Alors la reprise est incomplète : le client relit la base.
    Vrai quand des entrées ont été ajoutées puis retirées ET que la plus ancienne qui reste est plus récente que la position."""
    try:
        info = await redis.xinfo_stream(cle)
    except aioredis.ResponseError:  # la clé n'existe pas (rien à perdre)
        return False
    except Exception:  # Redis injoignable : la reprise se dit incomplète au lieu de se croire complète
        logger.exception("[.mark] Call feed: the stream position could not be checked")
        return True
    premier = info.get("recorded-first-entry-id") or "0-0"
    if int(info.get("entries-added", 0)) <= int(info.get("length", 0)):
        return False  # rien n'a jamais été retiré
    a, b = (int(x) for x in premier.split("-"))
    c, d = (int(x) for x in position.split("-"))
    return (a, b) > (c, d) and (c, d) != (a, b - 1)


def en_sse(evenement: dict[str, Any], curseur: str) -> str:
    """Le format ``text/event-stream`` : ``id`` = le curseur de reprise (tous les établissements écoutés), ``event`` = le type."""
    return f"id: {curseur}\nevent: {evenement['type']}\ndata: {json.dumps(evenement, ensure_ascii=False, separators=(',', ':'))}\n\n"


async def ecouter(
    organisation_id: int,
    etablissements: list[int],
    *,
    role: str = "equipe",
    reprise: str | None = None,
    est_deconnecte: Callable[[], Any] | None = None,
    nb_battements_max: int | None = None,
    client: aioredis.Redis | None = None,
) -> AsyncIterator[str]:
    """Le flux SSE de ces établissements DE CETTE organisation (la route les a vérifiés contre la base). Sans ``reprise`` : seulement ce
    qui arrive après la connexion ; avec ``reprise`` (``Last-Event-ID``) : ce qui a été manqué depuis, sans perte ni doublon. Se referme
    de lui-même après ``nb_battements_max`` battements : le client se reconnecte avec son dernier identifiant."""
    if role not in ROLES_D_ECOUTE:
        raise EvenementRefuse(f"Rôle d'écoute inconnu : {role!r}")
    nb_battements_max = NB_BATTEMENTS_MAX if nb_battements_max is None else nb_battements_max
    cles = {e: cle_du_flux(organisation_id, e) for e in dict.fromkeys(etablissements)}
    redis = client or await _client_de_lecture()
    try:
        anciens = decoder_curseurs(reprise)
        curseurs: dict[int, str] = {}
        for etab, cle in cles.items():
            if etab in anciens:
                curseurs[etab] = anciens[etab]
                if await _perte_depuis(redis, cle, anciens[etab]):
                    yield f"event: flux.reprise_impossible\ndata: {json.dumps({'etablissement': etab})}\n\n"
            else:
                curseurs[etab] = await _derniere_position(redis, cle)
        yield ": flux ouvert\n\n"
        battements = 0
        while battements < nb_battements_max:
            if est_deconnecte is not None and await est_deconnecte():
                return
            try:
                recu = await redis.xread({cle: curseurs[etab] for etab, cle in cles.items()}, block=BLOCAGE_LECTURE_MS)
            except Exception as erreur:  # noqa: BLE001 -- R1 : une lecture en panne se voit, le client se reconnecte et relit la base
                logger.error(f"[.mark] Live feed read failed for organization {organisation_id}: {erreur!r}")
                yield f"event: flux.erreur\ndata: {json.dumps({'erreur': 'indisponible'})}\n\n"
                return
            if not recu:
                battements += 1
                yield ": battement\n\n"
                continue
            par_cle = {cle: etab for etab, cle in cles.items()}
            for cle, entrees in recu:
                etab = par_cle[cle]
                for identifiant, champs in entrees:
                    curseurs[etab] = identifiant  # le curseur avance même sur ce qui est filtré : jamais rejoué
                    if not laisse_passer(champs.get("type", ""), role):
                        continue
                    yield en_sse(_evenement(organisation_id, etab, identifiant, champs), encoder_curseurs(curseurs))
    finally:
        if client is None:
            await redis.aclose()
