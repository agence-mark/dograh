"""[.mark] Clôture de la Partie 1 (Evan, 23/11) : deux appels simultanés sur le même restaurant ne se gênent pas.

Vrais appels en parallèle (``asyncio.gather``), deux ``run_id`` distincts, même établissement, CHACUN sa connexion à la base, sa fiche et sa mémoire d'appel (un ``Essai`` par appel,
routé par son contexte : la source ouverte pour un appel est toujours la sienne). Les points d'enregistrement sont tenus par une barrière : les deux appels y arrivent ensemble.

| # | Ce qui est prouvé | Ce que le test protège (vu rouge quand on le retire) |
|---|---|---|
| 1 | deux commandes finalisées au même instant : deux numéros courts distincts, deux paniers intacts, aucun article de l'une dans l'autre | le compteur du jour de ``resto_compteur_jour`` (un seul ``INSERT … ON CONFLICT DO UPDATE``) |
| 2 | deux réservations pour la dernière place du créneau : une seule enregistrée, l'autre reçoit « complet », dit par le code | le verrou du jour de ``creer_reservation`` (``pg_advisory_xact_lock``) |
| 3 | le même client (même numéro) commande au même instant sur deux appels : l'anti-doublon ne fond pas deux paniers différents | la clé d'anti-doublon (``_cle_doublon`` : l'appel et le panier) |
| 4 | un article passe en rupture pendant qu'un autre appel l'a au panier : la rupture est vue avant l'enregistrement | ``ruptures_du_restaurant(..., relire=True)`` à l'enregistrement |

Chaque scénario rend la LISTE de ses défauts (vide = juste) ; ``test_*`` exige la liste vide, ``test_*_vu_rouge`` retire la protection et exige qu'elle ne le soit plus.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import restauration as RESTAURATION
from api.db.bases_clients import restauration_commande as RC
from api.db.bases_clients.restauration_carte import poser_rupture
from api.db.bases_clients.restauration_commande import commande_complete
from api.services.actions_communes.repli import phrase_du_fait_bloquant
from api.services.commande import porte as PORTE_COMMANDE
from api.services.reservation import porte as PORTE_RESERVATION
from api.services.restauration import source_reservation as SOURCE_RESERVATION
from api.tests.mark.banc_a.commun import Monde
from api.tests.mark.partie_1 import combinaisons as C
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation
from api.tests.mark.test_restauration_reservation import salle  # noqa: F401

DELAI = 20.0  # une barrière qui n'est jamais franchie ne bloque pas la suite : le test échoue au lieu de pendre


class Connexion:
    """La connexion d'un appel, qui peut perdre UNE protection (la preuve « vu rouge ») : ``saute`` = des requêtes ``execute`` ignorées, ``remplace`` = ``fetchval`` rendu fixe."""

    def __init__(self, c, saute: tuple[str, ...] = (), remplace: dict[str, object] | None = None):
        self._c, self._saute, self._remplace = c, saute, remplace or {}

    def __getattr__(self, nom):
        return getattr(self._c, nom)

    async def execute(self, requete, *a, **k):
        if any(m in requete for m in self._saute):
            return None
        return await self._c.execute(requete, *a, **k)

    async def fetchval(self, requete, *a, **k):
        for morceau, valeur in self._remplace.items():
            if morceau in requete:
                return valeur
        return await self._c.fetchval(requete, *a, **k)


def _brancher_la_commande(monkeypatch, essais) -> None:
    """Chaque appel ouvre SA source (celle de sa connexion) : la source est cherchée par le contexte de l'appel, jamais partagée."""
    par_contexte = {id(e.ctx): e for e in essais}

    @asynccontextmanager
    async def ouvrir(nom, ctx, **options):
        e = par_contexte[id(ctx)]
        if e.instantane is None:
            await e.charger()
        e.instantane.nouveau_geste()
        await e.source.charger_les_modes()
        yield e.source

    monkeypatch.setattr(PORTE_COMMANDE.registre_des_sources, "ouvrir", ouvrir)


def _barriere_de_l_enregistrement(monkeypatch, n: int = 2) -> None:
    """Les ``n`` appels arrivent à l'enregistrement ENSEMBLE (les contrôles à blanc d'un changement ne comptent pas)."""
    barriere = asyncio.Barrier(n)
    vraie = RESTAURATION.enregistrer_commande

    async def enregistrer(*a, **k):
        if not k.get("a_blanc"):
            await asyncio.wait_for(barriere.wait(), DELAI)
        return await vraie(*a, **k)

    monkeypatch.setattr(RESTAURATION, "enregistrer_commande", enregistrer)


async def _deux_appels(faire_monde, monkeypatch, *, saute=(), remplace=None):
    """Deux ``Partie`` (donc deux ``Essai``) sur le même établissement de Casa Italia, chacune sur sa connexion, deux ``run_id`` distincts."""
    monde = await faire_monde("casa-italia")
    c2 = await schema.connecter(monde.base)
    mondes = [Monde(Connexion(c, saute, remplace), monde.a, monde.base, monde.slug, monde.carte, monde.minimum) for c in (monde.c, c2)]
    parties = [C.Partie(m, monkeypatch) for m in mondes]
    for i, p in enumerate(parties):
        p.e.ctx.run_id = 9001 + i
    _brancher_la_commande(monkeypatch, [p.e for p in parties])
    return monde, c2, parties


def _recette_regina(monkeypatch) -> None:
    monkeypatch.setitem(C.RECETTES, "E16R", ["mode:emporter", "regina", "G24", "G20", "relu_par_carte", "G23", "prenom"])
    monkeypatch.setitem(C.ATTEINT, "E16R", C.ATTEINT["E16"])


# --------------------------------------------------------------------------- 1. deux commandes finalisées au même instant


async def _deux_commandes_au_meme_instant(faire_monde, monkeypatch, *, sabotage: bool = False) -> list[str]:
    _recette_regina(monkeypatch)
    monde, c2, (p1, p2) = await _deux_appels(faire_monde, monkeypatch, remplace={"resto_compteur_jour": 1} if sabotage else None)
    try:
        _barriere_de_l_enregistrement(monkeypatch)
        atteints = await asyncio.gather(p1.recette("E16"), p2.recette("E16R"))
        fautes = [] if all(atteints) else [f"les deux commandes ne sont pas enregistrées : {atteints}"]
        if fautes:
            return fautes
        e1, e2 = p1.p["enregistree"], p2.p["enregistree"]
        if e1["numero_court"] == e2["numero_court"] or e1["numero"] == e2["numero"]:
            fautes.append(f"deux commandes, un même numéro : {e1['numero_court']} / {e2['numero_court']}")
        b1, b2 = await commande_complete(monde.c, monde.a, e1["numero"]), await commande_complete(monde.c, monde.a, e2["numero"])
        for nom, base, voulu, p in (("la première", b1, "PIZ-MARGHERITA-NORMALE", p1), ("la seconde", b2, "PIZ-REGINA-NORMALE", p2)):
            codes = [(l["code_caisse"], l["quantite"]) for l in (base or {}).get("lignes") or []]
            if codes != [(voulu, 1)]:
                fautes.append(f"{nom} commande en base a les lignes {codes} au lieu de {[(voulu, 1)]}")
        if C.lignes_de(p1.p) != C.Counter({C.MARGHERITA: 1}) or C.lignes_de(p2.p) != C.Counter({C.REGINA: 1}):
            fautes.append(f"un panier a changé : {dict(C.lignes_de(p1.p))} / {dict(C.lignes_de(p2.p))}")
        nombre = await monde.c.fetchval("SELECT count(*) FROM mark.resto_commande WHERE site_id = $1", monde.a)
        if nombre != 2:
            fautes.append(f"{nombre} commandes en base au lieu de 2")
        return fautes
    finally:
        await c2.close()


async def test_deux_commandes_finalisees_au_meme_instant_ont_deux_numeros_et_deux_paniers_intacts(faire_monde, monkeypatch):
    fautes = await _deux_commandes_au_meme_instant(faire_monde, monkeypatch)
    assert not fautes, fautes


async def test_deux_commandes_au_meme_instant_vu_rouge_sans_le_compteur_du_jour(faire_monde, monkeypatch):
    fautes = await _deux_commandes_au_meme_instant(faire_monde, monkeypatch, sabotage=True)
    assert any("même numéro" in f for f in fautes), fautes


# --------------------------------------------------------------------------- 2. la dernière place d'un créneau


async def _deux_reservations_pour_la_derniere_place(salle, monkeypatch, *, sabotage: bool = False) -> list[str]:  # noqa: F811
    from api.tests.mark.test_restauration_reservation import SAMEDI_20H  # noqa: F401

    await salle.c.execute("DELETE FROM mark.resto_table WHERE site_id = $1 AND nom <> 'T4'", salle.a)  # une seule table de 4 à 6 : une seule place à 20 h
    c2 = await schema.connecter(salle.base)
    try:
        saute = ("pg_advisory_xact_lock",) if sabotage else ()
        salles = [SimpleNamespace(**{**vars(salle), "c": Connexion(c, saute)}) for c in (salle.c, c2)]
        essais = [EssaiReservation(s, monkeypatch, appelant=f"+3361200000{i}") for i, s in enumerate(salles, start=1)]
        par_contexte = {id(e.ctx): e for e in essais}

        @asynccontextmanager
        async def ouvrir(nom, ctx, **options):
            yield par_contexte[id(ctx)].source

        monkeypatch.setattr(PORTE_RESERVATION.registre_des_sources, "ouvrir", ouvrir)
        barriere, vraie = asyncio.Barrier(2), SOURCE_RESERVATION.creer_reservation

        async def creer(*a, **k):
            await asyncio.wait_for(barriere.wait(), DELAI)
            return await vraie(*a, **k)

        monkeypatch.setattr(SOURCE_RESERVATION, "creer_reservation", creer)
        relectures = await asyncio.gather(*(e.tour("quatre personnes samedi à vingt heures au nom d'Alice", personnes=4, jour="samedi", heure="vingt heures", nom="Alice") for e in essais))
        fautes = [f"relecture non atteinte : {r}" for r in relectures if (r.get("question") or {}).get("type") != "recapitulatif"]
        if fautes:
            return fautes
        retours = await asyncio.gather(*(e.tour("oui c'est bon", reponse={"question_id": r["question"]["id"], "sens": "accepte"}) for e, r in zip(essais, relectures)))
        enregistrees = [r for r in retours if r.get("statut") == "ENREGISTREE"]
        if len(enregistrees) != 1:
            fautes.append(f"{len(enregistrees)} réservations enregistrées pour la dernière place (statuts {[r.get('statut') for r in retours]})")
        nombre = await salle.c.fetchval("SELECT count(*) FROM mark.resto_reservation WHERE site_id = $1", salle.a)
        if nombre != 1:
            fautes.append(f"{nombre} réservations en base pour la dernière place")
        for e, r in zip(essais, retours):
            if r.get("statut") != "ENREGISTREE":
                # Q1 (7b-B) : le modèle dit le refus complet, le code ne dit plus rien d'avance ; R = A (7b-C3) : il le tient en fait bloquant, que le repli dit si le modèle se tait deux fois
                dit = phrase_du_fait_bloquant(e.fiche_de_l_appel) or ""
                if r.get("raison") != "complet_a_cette_heure" or "complet" not in dit.casefold():
                    fautes.append(f"l'appel refusé ne porte pas le refus « complet » (fait bloquant : « {dit} », retour {r.get('statut')}/{r.get('raison')})")
        return fautes
    finally:
        await c2.close()


async def test_deux_reservations_pour_la_derniere_place_une_seule_est_enregistree(salle, monkeypatch):  # noqa: F811
    fautes = await _deux_reservations_pour_la_derniere_place(salle, monkeypatch)
    assert not fautes, fautes


async def test_deux_reservations_pour_la_derniere_place_vu_rouge_sans_le_verrou_du_jour(salle, monkeypatch):  # noqa: F811
    fautes = await _deux_reservations_pour_la_derniere_place(salle, monkeypatch, sabotage=True)
    assert any("réservations" in f for f in fautes), fautes


# --------------------------------------------------------------------------- 3. le même client, deux appels, deux paniers


async def _meme_client_deux_paniers(faire_monde, monkeypatch, *, sabotage: bool = False) -> list[str]:
    _recette_regina(monkeypatch)
    if sabotage:
        monkeypatch.setattr(RC, "_cle_doublon", lambda brouillon, calculees: f"{brouillon['client']['telephone']}|{brouillon['mode']}")  # l'anti-doublon ne regarde plus le panier ni l'appel
    monde, c2, (p1, p2) = await _deux_appels(faire_monde, monkeypatch)
    try:
        p2.e.ctx.appel["caller_number"] = p1.e.ctx.appel["caller_number"]  # le MÊME client
        _barriere_de_l_enregistrement(monkeypatch)
        atteints = await asyncio.gather(p1.recette("E16"), p2.recette("E16R"))
        fautes = [] if all(atteints) else [f"l'anti-doublon a fondu les deux paniers : {atteints}"]
        if fautes:
            return fautes
        lignes = await monde.c.fetch(
            "SELECT c.numero_court, l.code_caisse, l.quantite FROM mark.resto_commande c JOIN mark.resto_commande_ligne l ON l.numero = c.numero WHERE c.site_id = $1 ORDER BY c.numero_court", monde.a)
        codes = sorted(l["code_caisse"] for l in lignes)
        if codes != ["PIZ-MARGHERITA-NORMALE", "PIZ-REGINA-NORMALE"] or len({l["numero_court"] for l in lignes}) != 2:
            fautes.append(f"le même client, deux paniers différents : lignes en base {[(l['numero_court'], l['code_caisse']) for l in lignes]}")
        return fautes
    finally:
        await c2.close()


async def test_le_meme_client_sur_deux_appels_garde_ses_deux_paniers(faire_monde, monkeypatch):
    fautes = await _meme_client_deux_paniers(faire_monde, monkeypatch)
    assert not fautes, fautes


async def test_le_meme_client_sur_deux_appels_vu_rouge_quand_l_anti_doublon_fond_les_paniers(faire_monde, monkeypatch):
    fautes = await _meme_client_deux_paniers(faire_monde, monkeypatch, sabotage=True)
    assert fautes, "sans la clé d'anti-doublon par panier, le test doit échouer"


# --------------------------------------------------------------------------- 4. une rupture pendant qu'un autre appel a l'article au panier


async def _rupture_pendant_l_appel(faire_monde, monkeypatch, *, sabotage: bool = False) -> list[str]:
    if sabotage:
        vraie = RC.ruptures_du_restaurant

        async def sans_relire(connexion, etablissement_id, moment=None, *, relire=False):
            return await vraie(connexion, etablissement_id, moment, relire=False)  # la rupture posée pendant l'appel n'est plus relue

        monkeypatch.setattr(RC, "ruptures_du_restaurant", sans_relire)
    monde, c2, (p1, p2) = await _deux_appels(faire_monde, monkeypatch)
    try:
        # L'appel 1 a la margherita au panier, relue et acceptée, l'enregistrement est la prochaine étape ; l'appel 2 est un autre appel du restaurant, en cours lui aussi.
        assert await p1.recette("E15") and await p2.recette("E7")  # E15 : relue, acceptée, le prénom manque encore : le dire enregistre
        poste = await poser_rupture(c2, monde.a, "PIZ-MARGHERITA-NORMALE", False, None, "caisse")  # la rupture, posée par une autre connexion pendant l'appel 1
        assert poste.statut == "OK", poste
        o = await p1._executer("prenom", "Léa", {"prenom": "Léa"}, C._inchange)  # le prénom : l'enregistrement
        fautes = []
        if o is None or p1.p.get("enregistree"):
            fautes.append("la commande a été enregistrée alors que l'article est en rupture")
        nombre = await monde.c.fetchval("SELECT count(*) FROM mark.resto_commande WHERE site_id = $1", monde.a)
        if nombre:
            fautes.append(f"{nombre} commande(s) en base alors que l'article est en rupture")
        dit = (o.dit_par_le_code + " " + str((o.retour or {}).get("a_faire") or "") + " " + str((o.retour or {}).get("raison") or "")) if o else ""
        if not fautes and not dit.strip():
            fautes.append("la rupture est refusée sans rien dire (ni le code, ni le retour)")
        return fautes
    finally:
        await c2.close()


async def test_une_rupture_posee_pendant_l_appel_est_vue_avant_l_enregistrement(faire_monde, monkeypatch):
    fautes = await _rupture_pendant_l_appel(faire_monde, monkeypatch)
    assert not fautes, fautes


async def test_une_rupture_pendant_l_appel_vu_rouge_quand_elle_n_est_plus_relue(faire_monde, monkeypatch):
    fautes = await _rupture_pendant_l_appel(faire_monde, monkeypatch, sabotage=True)
    assert any("enregistrée" in f or "en base" in f for f in fautes), fautes
