"""[.mark] Module Restauration, lot 8 : les réservations dans le classeur (notre moteur de réservation par capacité, E-48).

``creer_reservation``, ``modifier_reservation``, ``annuler_reservation``, ``retrouver_reservation`` : hors des 17 fonctions du contrat
comptoir ↔ classeur (qui ne contient que ``disponibilites_capacite``), comme ``chiffrer_panier``. Toutes asynchrones, premier argument la
connexion du rôle d'écriture, puis ``etablissement_id`` (relu côté serveur, jamais d'un corps fourni par le modèle).

Règles (plan, lot 8) :

- les RÈGLES d'abord (date passée, délai minimal, jour trop lointain, hors de la grille d'un service, groupe trop grand, pause), puis la
  CAPACITÉ calculée depuis les réservations du jour (``capacite.placer``) ; la place est REVÉRIFIÉE à l'enregistrement, dans la transaction,
  sous un verrou par établissement et par jour (deux appels simultanés ne prennent jamais la même table) ;
- l'attribution des tables est automatique (la plus juste) ; la modification compte ses propres tables comme libres ;
- une réservation passée est FIGÉE (ni modifiée ni annulée) ; une annulée n'est plus modifiable ; annuler deux fois rend ``DEJA_FAIT`` ;
- un refus pour place rend les créneaux libres les plus proches (``faits.propositions``) ; jamais un texte de fournisseur ;
- l'heure vient de la source d'heure de l'organisation (D6).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import asyncpg

from api.db.bases_clients import capacite
from api.db.bases_clients.capacite import Occupation, Regles, Service, Unite
from api.db.bases_clients.dates_futures import jour_dit
from api.db.bases_clients.instantane import stable, vivant
from api.services.reservation import textes_de_secours as TS
from api.db.bases_clients.restauration_commande import E164, _heure_dite, _quand_dit
from api.db.bases_clients.restauration_commun import json_lu
from api.db.bases_clients.restauration_commun import Resultat, fuseau_de, maintenant, poser_session

LIMITE_DE_RESULTATS = 5
NOTE_MAX = 200
PRENOM_MAX = 60
# Les raisons de refus (``faits.detail``), dites au portail comme à l'agent : une liste fermée.
RAISONS = frozenset(
    {capacite.PASSE, capacite.TROP_TOT, capacite.TROP_LOIN, capacite.HORS_SERVICE, capacite.GROUPE_TROP_GRAND, capacite.FERME, capacite.COMPLET,
     "type_ferme", "plus_modifiable", "passee"}
)


def _refus(detail: str, **plus: Any) -> Resultat:
    faits = {"raison": "autre", "detail": detail, **plus}
    return Resultat("REFUSEE", faits, TS.refus_de_la_base(faits))


@dataclass(frozen=True)
class SalleDuJour:
    """Ce qui ne bouge pas d'un jour pendant un appel (lot 5, B05) : services, tables actives (et leurs noms), règle de réservation, plans du
    soir de ce jour. Les occupations (les réservations) et l'état vivant (pause du type, fermetures) sont lus à part, à leur moment."""

    services: list[Service]
    unites: list[Unite]
    noms: dict[int, str]
    regle: Any
    plans: tuple


async def salle_du_jour(connexion: asyncpg.Connection, etablissement_id: int, debut_jour: datetime, fin_jour: datetime) -> SalleDuJour:
    """La salle du jour, lue une fois par jour et par appel (lot 5, B05 ; le lot 7 en fait ``capacite_du_jour``)."""

    async def lire() -> SalleDuJour:
        services = [
            Service(s["nom"], list(s["jours"]), s["debut"].strftime("%H:%M"), s["fin"].strftime("%H:%M"), s["pas_minutes"])
            for s in await connexion.fetch("SELECT * FROM mark.resto_service WHERE site_id = $1 ORDER BY debut", etablissement_id)
        ]
        tables = await connexion.fetch("SELECT * FROM mark.resto_table WHERE site_id = $1 AND actif", etablissement_id)
        regle = await connexion.fetchrow("SELECT * FROM mark.resto_regle_reservation WHERE site_id = $1", etablissement_id)
        # M13 : le plan du soir de CE jour (tables rassemblées), par service ou pour toute la journée ; il ne touche pas au plan enregistré.
        plans = []
        for plan in await connexion.fetch(
            "SELECT p.assemblages, s.debut, s.fin FROM mark.resto_plan_soir p LEFT JOIN mark.resto_service s ON s.id = p.service_id AND s.site_id = p.site_id "
            "WHERE p.site_id = $1 AND p.jour = $2 AND (p.service_id IS NULL OR s.id IS NOT NULL)",
            etablissement_id, debut_jour.date(),
        ):
            fuseau = debut_jour.tzinfo
            du = datetime.combine(debut_jour.date(), plan["debut"], tzinfo=fuseau) if plan["debut"] else debut_jour
            au = datetime.combine(debut_jour.date(), plan["fin"], tzinfo=fuseau) if plan["fin"] else fin_jour
            plans.append((du, au, [list(g) for g in (json_lu(plan["assemblages"]) or []) if isinstance(g, list)]))
        unites = [Unite(t["id"], t["couverts_min"], t["couverts_max"], frozenset(t["assemblable_avec"])) for t in tables]
        return SalleDuJour(services, unites, {t["id"]: t["nom"] for t in tables}, regle, tuple(plans))

    return await stable(connexion, ("salle_du_jour", etablissement_id, debut_jour.date()), lire)


async def occupations_du_jour(
    connexion: asyncpg.Connection, etablissement_id: int, debut_jour: datetime, fin_jour: datetime, ignorer: uuid.UUID | None = None
) -> list[Occupation]:
    """Les réservations confirmées qui occupent ce jour (toujours lues à la base : deux appels réservent en même temps)."""
    return [
        Occupation(r["debut"], r["debut"] + timedelta(minutes=r["duree_minutes"]), r["couverts"], frozenset(r["table_ids"]))
        for r in await connexion.fetch(
            "SELECT debut, duree_minutes, couverts, table_ids FROM mark.resto_reservation WHERE site_id = $1 AND statut = 'confirmee' AND debut < $3 "
            "AND debut + duree_minutes * interval '1 minute' > $2 AND ($4::uuid IS NULL OR numero <> $4)",
            etablissement_id, debut_jour, fin_jour, ignorer,
        )
    ]


async def type_et_fermetures_du_jour(connexion: asyncpg.Connection, etablissement_id: int, debut_jour: datetime, fin_jour: datetime) -> tuple[Any, list]:
    """Le réglage du type « réservation » et les fermetures qui touchent ce jour, depuis l'état vivant (une requête par geste)."""
    etat = await vivant(connexion, etablissement_id, await maintenant(connexion))
    fermetures = [(f["du"], f["au"]) for f in etat.fermetures if f["du"] < fin_jour and f["au"] > debut_jour]
    return etat.types.get("reservation"), fermetures


async def _salle(connexion: asyncpg.Connection, etablissement_id: int, debut_jour: datetime, fin_jour: datetime, ignorer: uuid.UUID | None = None):
    """Tout ce qu'il faut pour placer sur la journée : ``(services, unites, occupations, regles, type_ouvert, noms_des_tables)``."""
    salle = await salle_du_jour(connexion, etablissement_id, debut_jour, fin_jour)
    occupations = await occupations_du_jour(connexion, etablissement_id, debut_jour, fin_jour, ignorer)
    type_, fermetures = await type_et_fermetures_du_jour(connexion, etablissement_id, debut_jour, fin_jour)
    regle = salle.regle
    regles = Regles(
        plans_du_soir=salle.plans,
        delai_minimal=regle["delai_minimal"] if regle else 0,
        jours_a_l_avance=regle["jours_a_l_avance"] if regle else None,
        effectif_max=regle["couverts_max_groupe"] if regle else None,
        effectif_max_par_creneau=regle["couverts_max_creneau"] if regle else None,
        effectif_simultane=regle["couverts_simultanes"] if regle else None,
        pause_jusqu_a=type_["pause_jusqu_a"] if type_ else None,
        fermetures=fermetures,
    )
    return salle.services, salle.unites, occupations, regles, (type_ is None or type_["ouvert"]), salle.noms


async def services_de_reservation(connexion: asyncpg.Connection, etablissement_id: int) -> list[dict[str, Any]]:
    """Les services où l'on réserve (nom, jours, début, fin), lus une fois par appel : ce que ``lire`` dit des horaires de réservation (lot 7)."""

    async def lire() -> list[dict[str, Any]]:
        return [
            {"nom": s["nom"], "jours": list(s["jours"]), "debut": s["debut"], "fin": s["fin"]}
            for s in await connexion.fetch("SELECT nom, jours, debut, fin FROM mark.resto_service WHERE site_id = $1 ORDER BY debut", etablissement_id)
        ]

    return await stable(connexion, ("services_de_reservation", etablissement_id), lire)


async def duree_du_groupe(connexion: asyncpg.Connection, etablissement_id: int, couverts: int) -> int | None:
    """La durée d'une réservation pour ce nombre de personnes (la règle par taille de groupe), règles lues une fois par appel."""

    async def lire() -> list:
        return list(await connexion.fetch(
            "SELECT couverts_min, couverts_max, duree_minutes FROM mark.resto_duree_groupe WHERE site_id = $1 ORDER BY couverts_min", etablissement_id
        ))

    regles = await stable(connexion, ("durees_de_groupe", etablissement_id), lire)
    return next((r["duree_minutes"] for r in regles if r["couverts_min"] <= couverts <= r["couverts_max"]), None)





def _jour_borne(debut: datetime, fuseau: ZoneInfo) -> tuple[datetime, datetime]:
    local = debut.astimezone(fuseau)
    d0 = datetime(local.year, local.month, local.day, tzinfo=fuseau)
    return d0, d0 + timedelta(days=1)


async def _verrouiller(connexion: asyncpg.Connection, etablissement_id: int, jours: set[date]) -> None:
    """Un verrou par jour, pris dans l'ordre (jamais d'attente croisée), tenu jusqu'à la fin de la transaction."""
    for jour in sorted(jours):
        await connexion.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"resto_reservation:{etablissement_id}:{jour.isoformat()}")


def _fait(r: asyncpg.Record, noms: dict[int, str], fuseau: ZoneInfo, maintenant_: datetime) -> dict[str, Any]:
    fin = r["debut"] + timedelta(minutes=r["duree_minutes"])
    return {
        "numero": str(r["numero"]), "debut": r["debut"], "fin": fin, "duree_minutes": r["duree_minutes"], "couverts": r["couverts"],
        "prenom": r["prenom"], "statut": r["statut"], "tables": [noms.get(i, str(i)) for i in r["table_ids"]], "note": r["note"],
        "quand_dit": _quand_dit(r["debut"], maintenant_, fuseau), "jour_dit": jour_dit(r["debut"].astimezone(fuseau).date()),
        "heure_dite": _heure_dite(r["debut"], fuseau),  # C6 n° 8 : l'heure seule, exigée de la phrase du modèle qui demande l'annulation (P2)
    }


async def _propositions(
    connexion: asyncpg.Connection, etablissement_id: int, debut: datetime, couverts: int, duree: int, fuseau: ZoneInfo, maintenant_: datetime,
    ignorer: uuid.UUID | None = None, salle: tuple | None = None,
) -> list[dict]:
    """Les créneaux libres du jour les plus proches de l'heure voulue (au plus trois), ``{debut, fin}``. ``salle`` : la salle du même jour déjà lue
    par le geste (B04 : jamais relue pour proposer)."""
    d0, d1 = _jour_borne(debut, fuseau)
    services, unites, occupations, regles, _, _ = salle or await _salle(connexion, etablissement_id, d0, d1, ignorer)
    libres = capacite.creneaux_libres(debut.astimezone(fuseau).date(), couverts, duree, unites, occupations, services, fuseau, maintenant_, regles)
    return [{"debut": c["debut"], "fin": c["fin"], "quand_dit": _quand_dit(c["debut"], maintenant_, fuseau)} for c in capacite.les_plus_proches(debut, libres, 3)]


def _avec_propositions(refus: Resultat, propositions: list[dict]) -> Resultat:
    if not propositions:
        return refus
    faits = {**refus.faits, "propositions": propositions}
    return Resultat(refus.statut, faits, TS.refus_de_la_base(faits), refus.manque)


async def capacite_du_jour(
    connexion: asyncpg.Connection, etablissement_id: int, jour: date, couverts: int, duree_minutes: int | None = None, ignorer: uuid.UUID | None = None
) -> Resultat:
    """LA capacité d'un jour (lot 7, B03) : les créneaux où ``couverts`` personnes tiennent, ce jour, du plus tôt au plus tard (``capacite.py``). Une seule
    fonction, lue par la recherche des places, la relecture et l'enregistrement : même salle (``_salle``, plans du soir compris), mêmes règles, même
    réponse. La durée vient de l'argument, sinon de la règle de durée par taille de groupe ; sans l'une ni l'autre : ``INCOMPLETE`` (``duree``).
    ``ignorer`` : une réservation dont les tables comptent comme libres (son propre changement). Tables assemblables deux à deux ; réservations sans
    table : elles prennent de la capacité totale."""
    if not isinstance(couverts, int) or couverts < 1:
        return Resultat("ARGUMENT_INVALIDE", manque="couverts")
    fuseau = ZoneInfo(await fuseau_de(connexion, etablissement_id))
    maintenant_ = await maintenant(connexion)
    if duree_minutes is None:
        duree_minutes = await duree_du_groupe(connexion, etablissement_id, couverts)
    if not duree_minutes:
        return Resultat("INCOMPLETE", manque="duree")
    debut_jour = datetime(jour.year, jour.month, jour.day, tzinfo=fuseau)
    fin_jour = datetime.combine(jour + timedelta(days=1), datetime.min.time(), tzinfo=fuseau)
    services, unites, occupations, regles, ouvert, _ = await _salle(connexion, etablissement_id, debut_jour, fin_jour, ignorer)
    if not ouvert:
        return Resultat("OK", {"creneaux": [], "duree_minutes": duree_minutes, "raison": "type_ferme"})
    if capacite.capacite_manquante(unites, regles):
        return Resultat("INCOMPLETE", {}, "", "capacite")
    if regles.effectif_max is not None and couverts > regles.effectif_max:
        return _refus("groupe_trop_grand", maximum=regles.effectif_max)
    libres = capacite.creneaux_libres(jour, couverts, duree_minutes, unites, occupations, services, fuseau, maintenant_, regles)
    return Resultat("OK", {"creneaux": libres, "duree_minutes": duree_minutes, "complet": not libres})


async def groupe_trop_grand(connexion: asyncpg.Connection, etablissement_id: int, couverts: int) -> Resultat | None:
    """Le plus grand groupe que l'agent prend (règle de l'établissement) : ``REFUSEE`` (``groupe_trop_grand``, ``maximum``, la suite : l'équipe) dès que le
    nombre est dit, avant le jour et l'heure ; ``None`` quand le groupe passe ou qu'aucun maximum n'est réglé. Lu une fois par appel (``stable``)."""

    async def lire() -> int | None:
        return await connexion.fetchval("SELECT couverts_max_groupe FROM mark.resto_regle_reservation WHERE site_id = $1", etablissement_id)

    maximum = await stable(connexion, ("groupe_max", etablissement_id), lire)
    if maximum is None or not isinstance(couverts, int) or couverts <= maximum:
        return None
    return _refus("groupe_trop_grand", maximum=maximum, a_faire="dis-lui qu'un groupe de cette taille se règle avec l'équipe et propose de laisser un message à l'équipe")


async def creer_reservation(
    connexion: asyncpg.Connection, etablissement_id: int, brouillon: dict[str, Any], *, source: str = "agent", auteur: str | None = None
) -> Resultat:
    """Enregistre une réservation. ``brouillon`` : ``debut`` (aware), ``couverts``, ``prenom``, ``telephone`` (E.164 ; exigé de l'agent, facultatif
    du portail), ``note?``, ``appel_id?``, ``duree_minutes?`` (sinon la durée du groupe). Rend ``ENREGISTREE`` (``faits.numero``, ``debut``,
    ``tables``), ``INCOMPLETE`` (UN manque à la fois), ``REFUSEE`` (``faits.detail`` : une raison de ``RAISONS`` ; ``propositions`` pour une place)
    ou ``DEJA_FAIT`` (même appel, même numéro, même heure, mêmes personnes : le même numéro de réservation)."""
    cree_par = {"agent": "agent", "portail": "portail", "caisse": "caisse"}.get(source)
    if cree_par is None:
        return Resultat("ARGUMENT_INVALIDE", manque="source")
    couverts, debut = brouillon.get("couverts"), brouillon.get("debut")
    prenom, telephone = (brouillon.get("prenom") or "").strip(), brouillon.get("telephone")
    if not isinstance(couverts, int) or isinstance(couverts, bool) or couverts < 1:
        return Resultat("INCOMPLETE", {}, TS.combien_de_personnes({}), "couverts")
    if not isinstance(debut, datetime) or debut.tzinfo is None:
        return Resultat("INCOMPLETE", {}, TS.quel_jour_et_quelle_heure({}), "debut")
    if not prenom:
        return Resultat("INCOMPLETE", {}, TS.a_quel_nom_je_mets_la_reservation({}), "prenom")
    if len(prenom) > PRENOM_MAX:
        return Resultat("ARGUMENT_INVALIDE", {}, TS.nom_trop_long({}), "prenom")
    if telephone is not None and not (isinstance(telephone, str) and E164.match(telephone)):
        faits = {"numero_illisible": True}
        return Resultat("ARGUMENT_INVALIDE", faits, TS.numero_illisible(faits), "telephone")
    if telephone is None and cree_par == "agent":
        return Resultat("INCOMPLETE", {}, TS.quel_numero({}), "telephone")
    note = (brouillon.get("note") or "").strip() or None
    if note and len(note) > NOTE_MAX:
        return Resultat("ARGUMENT_INVALIDE", {}, TS.note_trop_longue({}), "note")
    fuseau = ZoneInfo(await fuseau_de(connexion, etablissement_id))
    maintenant_ = await maintenant(connexion)
    duree = brouillon.get("duree_minutes") or await duree_du_groupe(connexion, etablissement_id, couverts)
    if not duree:
        return Resultat("INCOMPLETE", {}, "", "duree")
    d0, d1 = _jour_borne(debut, fuseau)
    async with connexion.transaction():
        await poser_session(connexion, source, auteur or f"reservation:{source}")
        await _verrouiller(connexion, etablissement_id, {debut.astimezone(fuseau).date()})
        salle = await _salle(connexion, etablissement_id, d0, d1)
        services, unites, occupations, regles, ouvert, noms = salle
        if not ouvert:
            return _refus("type_ferme")
        if capacite.capacite_manquante(unites, regles):
            return Resultat("INCOMPLETE", {}, "", "capacite")
        doublon = await connexion.fetchrow(
            "SELECT * FROM mark.resto_reservation WHERE site_id = $1 AND statut = 'confirmee' AND debut = $2 AND couverts = $3 "
            "AND telephone IS NOT DISTINCT FROM $4 AND ($5::text IS NULL OR appel_id = $5)",
            etablissement_id, debut, couverts, telephone, brouillon.get("appel_id"),
        )
        if doublon is not None:
            faits = _fait(doublon, noms, fuseau, maintenant_)
            return Resultat("DEJA_FAIT", faits, TS.deja_reservee(faits))
        raison, tables = capacite.placer(debut, duree, couverts, unites, occupations, services, fuseau, maintenant_, regles)
        if raison != "ok":
            refus = _refus(raison, maximum=regles.effectif_max) if raison == capacite.GROUPE_TROP_GRAND else _refus(raison)
            propositions = (
                await _propositions(connexion, etablissement_id, debut, couverts, duree, fuseau, maintenant_, salle=salle)
                if raison in (capacite.COMPLET, capacite.HORS_SERVICE) else []
            )
            return _avec_propositions(refus, propositions)
        numero = uuid.uuid4()
        ligne = await connexion.fetchrow(
            "INSERT INTO mark.resto_reservation (numero, site_id, debut, duree_minutes, couverts, telephone, prenom, table_ids, note, cree_par, appel_id, cree_le, maj_le) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $12) RETURNING *",
            numero, etablissement_id, debut, duree, couverts, telephone, prenom, list(tables), note, cree_par, brouillon.get("appel_id"), maintenant_,
        )
    faits = _fait(ligne, noms, fuseau, maintenant_)
    return Resultat("ENREGISTREE", faits, TS.reservation_enregistree(faits))  # C6 n° 9 : un texte de secours ; le modèle dit le fait accompli


async def modifier_reservation(
    connexion: asyncpg.Connection, etablissement_id: int, numero: str | uuid.UUID, changements: dict[str, Any], *, source: str = "agent", auteur: str | None = None
) -> Resultat:
    """Change l'heure (``debut``), le nombre de personnes (``couverts``), le nom (``prenom``) ou la ``note``. Une modification d'heure ou de
    personnes revérifie les règles et la capacité, les tables de la réservation comptant comme libres ; le reste ne touche pas à la place.
    ``OK`` (``faits`` de la réservation), ``DEJA_FAIT`` (rien ne change), ``INTROUVABLE`` (pas une réservation de CET établissement),
    ``REFUSEE`` (``plus_modifiable`` : annulée, honorée ou absente ; ``passee`` : figée ; une raison de place avec ses propositions)."""
    if source not in ("agent", "portail", "caisse"):
        return Resultat("ARGUMENT_INVALIDE", manque="source")
    try:
        numero = uuid.UUID(str(numero))
    except ValueError:
        return Resultat("ARGUMENT_INVALIDE", manque="numero")
    fuseau = ZoneInfo(await fuseau_de(connexion, etablissement_id))
    maintenant_ = await maintenant(connexion)
    async with connexion.transaction():
        await poser_session(connexion, source, auteur or f"reservation:{source}")
        # Lot 5 (B10) : UNE lecture, sous verrou de ligne ; puis les verrous des jours (une ligne verrouillée ne change plus pendant l'attente)
        r = await connexion.fetchrow("SELECT * FROM mark.resto_reservation WHERE numero = $1 AND site_id = $2 FOR UPDATE", numero, etablissement_id)
        if r is None:
            return Resultat("INTROUVABLE", {"numero": str(numero)})
        nouveau_debut = changements.get("debut", r["debut"])
        await _verrouiller(connexion, etablissement_id, {r["debut"].astimezone(fuseau).date(), nouveau_debut.astimezone(fuseau).date()} if isinstance(nouveau_debut, datetime) else {r["debut"].astimezone(fuseau).date()})
        noms = (await salle_du_jour(connexion, etablissement_id, *_jour_borne(r["debut"], fuseau))).noms
        if r["statut"] != "confirmee":
            return _refus("plus_modifiable", statut=r["statut"])
        if r["debut"] <= maintenant_:
            return _refus("passee")
        couverts = changements.get("couverts", r["couverts"])
        prenom = (changements["prenom"].strip() if isinstance(changements.get("prenom"), str) else r["prenom"]) or r["prenom"]
        note = (changements["note"].strip() or None) if isinstance(changements.get("note"), str) else r["note"]
        if not isinstance(couverts, int) or isinstance(couverts, bool) or couverts < 1:
            return Resultat("ARGUMENT_INVALIDE", {}, TS.combien_de_personnes({}), "couverts")
        if not isinstance(nouveau_debut, datetime) or nouveau_debut.tzinfo is None:
            return Resultat("ARGUMENT_INVALIDE", {}, TS.quel_jour_et_quelle_heure({}), "debut")
        if len(prenom) > PRENOM_MAX or (note and len(note) > NOTE_MAX):
            return Resultat("ARGUMENT_INVALIDE", manque="prenom" if len(prenom) > PRENOM_MAX else "note")
        place_change = nouveau_debut != r["debut"] or couverts != r["couverts"]
        if (nouveau_debut, couverts, prenom, note) == (r["debut"], r["couverts"], r["prenom"], r["note"]):
            faits = _fait(r, noms, fuseau, maintenant_)
            return Resultat("DEJA_FAIT", faits, TS.deja_comme_cela(faits))
        tables, duree = list(r["table_ids"]), r["duree_minutes"]
        if place_change:
            duree = await duree_du_groupe(connexion, etablissement_id, couverts) if couverts != r["couverts"] else r["duree_minutes"]
            if not duree:
                return Resultat("INCOMPLETE", {}, "", "duree")
            d0, d1 = _jour_borne(nouveau_debut, fuseau)
            salle = await _salle(connexion, etablissement_id, d0, d1, ignorer=numero)
            services, unites, occupations, regles, ouvert, noms = salle
            if not ouvert:
                return _refus("type_ferme")
            if capacite.capacite_manquante(unites, regles):
                return Resultat("INCOMPLETE", {}, "", "capacite")
            raison, attribuees = capacite.placer(nouveau_debut, duree, couverts, unites, occupations, services, fuseau, maintenant_, regles)
            if raison != "ok":
                propositions = (
                    await _propositions(connexion, etablissement_id, nouveau_debut, couverts, duree, fuseau, maintenant_, ignorer=numero, salle=salle)
                    if raison in (capacite.COMPLET, capacite.HORS_SERVICE) else []
                )
                return _avec_propositions(_refus(raison), propositions)
            tables = list(attribuees)
        ligne = await connexion.fetchrow(
            "UPDATE mark.resto_reservation SET debut = $3, duree_minutes = $4, couverts = $5, prenom = $6, note = $7, table_ids = $8 "
            "WHERE numero = $1 AND site_id = $2 RETURNING *",
            numero, etablissement_id, nouveau_debut, duree, couverts, prenom, note, tables,
        )
    faits = _fait(ligne, noms, fuseau, maintenant_)
    return Resultat("OK", faits, TS.reservation_modifiee(faits))  # C6 n° 9 : un texte de secours (nombres en lettres) ; le modèle dit le fait accompli


async def annuler_reservation(
    connexion: asyncpg.Connection, etablissement_id: int, numero: str | uuid.UUID, *, source: str = "agent", auteur: str | None = None
) -> Resultat:
    """Annule une réservation à venir. ``OK``, ``DEJA_FAIT`` (déjà annulée : le second geste identique n'écrase rien), ``INTROUVABLE``
    (pas une réservation de CET établissement), ``REFUSEE`` (``passee`` : figée ; ``plus_modifiable`` : honorée ou absente). L'annulation en
    deux temps (demander, puis confirmer) est celle des outils de l'agent ; le portail confirme à l'écran."""
    if source not in ("agent", "portail", "caisse"):
        return Resultat("ARGUMENT_INVALIDE", manque="source")
    try:
        numero = uuid.UUID(str(numero))
    except ValueError:
        return Resultat("ARGUMENT_INVALIDE", manque="numero")
    fuseau = ZoneInfo(await fuseau_de(connexion, etablissement_id))
    maintenant_ = await maintenant(connexion)
    async with connexion.transaction():
        await poser_session(connexion, source, auteur or f"reservation:{source}")
        r = await connexion.fetchrow("SELECT * FROM mark.resto_reservation WHERE numero = $1 AND site_id = $2 FOR UPDATE", numero, etablissement_id)
        if r is None:
            return Resultat("INTROUVABLE", {"numero": str(numero)})
        noms: dict[int, str] = {}
        if r["statut"] == "annulee":
            faits = _fait(r, noms, fuseau, maintenant_)
            return Resultat("DEJA_FAIT", faits, TS.deja_annulee(faits))
        if r["statut"] != "confirmee":
            return _refus("plus_modifiable", statut=r["statut"])
        if r["debut"] <= maintenant_:
            return _refus("passee")
        ligne = await connexion.fetchrow("UPDATE mark.resto_reservation SET statut = 'annulee' WHERE numero = $1 AND site_id = $2 RETURNING *", numero, etablissement_id)
    faits = _fait(ligne, noms, fuseau, maintenant_)
    return Resultat("OK", faits, TS.reservation_annulee(faits))  # C6 n° 9 : un texte de secours ; le modèle dit le fait accompli


async def telephone_de_la_reservation(connexion: asyncpg.Connection, etablissement_id: int, numero: str | uuid.UUID) -> str | None:
    """Le numéro de CETTE réservation de CET établissement (pour le SMS d'après-action), ``None`` sinon. Jamais rendu au modèle."""
    try:
        numero = uuid.UUID(str(numero))
    except ValueError:
        return None
    return await connexion.fetchval("SELECT telephone FROM mark.resto_reservation WHERE numero = $1 AND site_id = $2", numero, etablissement_id)


async def retrouver_reservation(
    connexion: asyncpg.Connection, etablissement_id: int, *, numero: str | uuid.UUID | None = None, telephone: str | None = None,
    prenom: str | None = None, jour: date | None = None, a_venir: bool = True,
) -> Resultat:
    """Retrouve les réservations CONFIRMÉES de CET établissement : par numéro, ou par téléphone, ou par prénom et jour. Jamais celles d'un autre.
    ``OK`` avec ``faits.reservations`` (au plus ``LIMITE_DE_RESULTATS``, les plus proches d'abord) ou ``INTROUVABLE``. Sans critère :
    ``INCOMPLETE``. ``a_venir`` : seulement celles qui ne sont pas passées."""
    fuseau = ZoneInfo(await fuseau_de(connexion, etablissement_id))
    maintenant_ = await maintenant(connexion)
    if numero is not None:
        try:
            numero = uuid.UUID(str(numero))
        except ValueError:
            return Resultat("INTROUVABLE", {"reservations": []})
    elif not (telephone or (prenom and jour)):
        return Resultat("INCOMPLETE", {}, TS.sous_quel_nom_et_quel_jour({}), "reference")
    elif telephone is not None and not E164.match(str(telephone)):
        return Resultat("INTROUVABLE", {"reservations": []})
    debut_jour = datetime(jour.year, jour.month, jour.day, tzinfo=fuseau) if jour else None
    lignes = await connexion.fetch(
        "SELECT * FROM mark.resto_reservation WHERE site_id = $1 AND statut = 'confirmee' AND ($2::uuid IS NULL OR numero = $2) "
        "AND ($3::text IS NULL OR telephone = $3) AND ($4::text IS NULL OR lower(prenom) = lower($4)) "
        "AND ($5::timestamptz IS NULL OR (debut >= $5 AND debut < $5 + interval '1 day')) AND ($6::timestamptz IS NULL OR debut > $6) "
        "ORDER BY debut LIMIT $7",
        etablissement_id, numero, telephone, prenom.strip() if prenom else None, debut_jour, maintenant_ if a_venir else None, LIMITE_DE_RESULTATS,
    )
    if not lignes:
        faits = {"reservations": []}
        return Resultat("INTROUVABLE", faits, TS.pas_de_reservation(faits))
    noms = {t["id"]: t["nom"] for t in await connexion.fetch("SELECT id, nom FROM mark.resto_table WHERE site_id = $1", etablissement_id)}
    faits = {"reservations": [_fait(r, noms, fuseau, maintenant_) for r in lignes]}
    return Resultat("OK", faits, TS.une_reservation(faits) if len(lignes) == 1 else TS.plusieurs_reservations(faits))
