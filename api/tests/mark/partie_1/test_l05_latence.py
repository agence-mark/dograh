"""[.mark] Chantier Partie 1, lot 5 : la latence du code (E23, D13, D53, D58, D61 points 3 et 9).

Les essais passent par la vraie porte et la vraie source, sur les cartes figées du banc A, sans modèle. Le compte des requêtes est celui de la
connexion tracée (``releve_latence.ConnexionTracee``) ; l'appel est chargé comme au décroché (``Essai.charger``, ``memoire_de_l_appel``).
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import time
from datetime import timedelta
from types import SimpleNamespace

import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients.connexion import BaseClientIndisponible
from api.db.bases_clients.instantane import Instantane
from api.db.bases_clients.restauration_carte import carte_du_restaurant, poser_rupture
from api.db.bases_clients.restauration_commun import maintenant
from api.services.restauration import memoire_de_l_appel as M
from api.services.restauration import source_commande, source_reservation
from api.services.restauration.appel import Lieu
from api.services.restauration.prises.prise_essai import PriseTest
from api.services.restauration.source_commande import SourceClasseur
from api.services.restauration.source_reservation import SourceReservation
from api.tests.mark.banc_a.commun import Appel
from api.tests.mark.partie_1.releve_latence import ConnexionTracee, premier_article, relever
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI

CARTES = ("casa-italia", "etoile-d-or", "kebab-demo", "lusitalia")
TABLES_DE_LA_SALLE = ("mark.resto_service", "mark.resto_table ", "mark.resto_regle_reservation", "mark.resto_plan_soir")


async def appel_trace(faire_monde, monkeypatch, slug: str, monde=None) -> tuple[Appel, ConnexionTracee]:
    monde = monde or await faire_monde(slug)
    a = Appel(monde, monkeypatch)
    trace = ConnexionTracee(monde.c)
    a.source = SourceClasseur(trace, Lieu(monde.base, monde.a, 1), nom_prise="test", prise=PriseTest())
    return a, trace


def lues(trace: ConnexionTracee, morceau: str) -> int:
    return sum(n for texte, n in trace.textes.items() if morceau in texte)


async def jusqu_a_la_relecture(a: Appel) -> None:
    nom, variante = premier_article(a.monde)
    await a.tour("à emporter", mode_de_retrait="emporter")
    await a.tour(f"une {nom}", ajouter=[{"article": nom, "quantite": 1, "variante": variante}])
    for _ in range(3):
        q = a.p.get("question") or {}
        if q.get("type") == "relecture":
            return
        await a.tour("c'est tout", c_est_tout=True, **({"reponse": {"question_id": q["id"], "sens": "refuse"}} if q.get("id") else {}))


# --------------------------------------------------------------------------- le relevé « avant, après » (hors registre)


@pytest.mark.latence
@pytest.mark.parametrize("slug", CARTES)
async def test_releve_des_operations(faire_monde, monkeypatch, slug):
    """Le relevé du journal (pas un élément du registre) : écrit dans ``RELEVE_L05`` quand la variable est posée."""
    a, trace = await appel_trace(faire_monde, monkeypatch, slug)
    lignes = await relever(a, trace)
    if os.environ.get("RELEVE_L05"):
        with open(os.environ["RELEVE_L05"], "a", encoding="utf-8") as f:
            for l in lignes:
                f.write(json.dumps({"carte": slug, **l}, ensure_ascii=False) + "\n")
    assert lignes


# --------------------------------------------------------------------------- L05-01 à L05-03 : le chargement, une requête, 50 ms


async def test_chargement_en_requetes_fixes(faire_monde, monkeypatch):
    """L05-01 : le chargement fait le même nombre de requêtes sur une carte de 83 articles (Casa) et de 155 (Étoile d'Or)."""
    comptes = {}
    for slug in ("casa-italia", "etoile-d-or"):
        a, trace = await appel_trace(faire_monde, monkeypatch, slug)
        trace.remettre()
        await a.charger()
        comptes[slug] = trace.requetes
    assert comptes["casa-italia"] == comptes["etoile-d-or"], comptes
    assert comptes["casa-italia"] <= 25, comptes


@pytest.mark.parametrize("slug", CARTES)
async def test_fiche_sans_enregistrement_une_requete_au_plus(faire_monde, monkeypatch, slug):
    """L05-02 : ajouter, changer, répondre : une requête au plus (l'état vivant) une fois l'appel chargé."""
    a, trace = await appel_trace(faire_monde, monkeypatch, slug)
    await a.charger()
    nom, variante = premier_article(a.monde)
    vus = {}
    trace.remettre()
    await a.tour("à emporter", mode_de_retrait="emporter")
    vus["mode"] = (trace.requetes, dict(trace.textes))
    trace.remettre()
    await a.tour(f"une {nom}", ajouter=[{"article": nom, "quantite": 1, "variante": variante}])
    vus["ajouter"] = (trace.requetes, dict(trace.textes))
    q = a.p.get("question") or {}
    if q.get("id"):
        trace.remettre()
        await a.tour("non merci", reponse={"question_id": q["id"], "sens": "refuse"})
        vus["reponse"] = (trace.requetes, dict(trace.textes))
    trace.remettre()
    await a.tour("finalement deux", changer_quantite=[{"ligne": a.p["lignes"][0]["n"], "quantite": 2}])
    vus["changer"] = (trace.requetes, dict(trace.textes))
    assert all(n <= 1 for n, _ in vus.values()), vus


@pytest.mark.latence
@pytest.mark.parametrize("slug", CARTES)
async def test_fiche_cinquante_ms(faire_monde, monkeypatch, slug):
    """L05-03 (E23) : une fiche en 50 ms au plus, base comprise : médiane de 20 rejeux, sur chacune des quatre cartes. Local seulement (D61)."""
    a, _ = await appel_trace(faire_monde, monkeypatch, slug)
    await a.charger()
    nom, variante = premier_article(a.monde)
    await a.tour("à emporter", mode_de_retrait="emporter")
    temps = []
    for i in range(20):
        debut = time.perf_counter()
        await a.tour(f"une {nom}", ajouter=[{"article": nom, "quantite": 1, "variante": variante}])
        temps.append((time.perf_counter() - debut) * 1000)
        q = a.p.get("question") or {}
        if q.get("type") == "proposition":
            await a.tour("non merci", reponse={"question_id": q["id"], "sens": "refuse"})
    assert statistics.median(temps) <= 50, f"{slug} : médiane {statistics.median(temps):.1f} ms ({[round(t) for t in temps]})"


# --------------------------------------------------------------------------- L05-04, L05-05, L05-18 : ce qui change pendant l'appel


async def test_rupture_relue_a_l_enregistrement(faire_monde, monkeypatch):
    """L05-04 : une rupture posée pendant l'appel (après le chargement) refuse l'enregistrement."""
    a, _ = await appel_trace(faire_monde, monkeypatch, "casa-italia")
    await a.charger()
    await jusqu_a_la_relecture(a)
    code = a.p["lignes"][0]["code"]
    assert (await poser_rupture(a.monde.c, a.monde.a, code, False, None, "caisse")).statut == "OK"
    q = a.p["question"]
    r = await a.tour("oui, par carte", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="carte_bancaire")
    for dit, cases in (("zéro six douze trente-quatre cinquante-six soixante-dix-huit", {"telephone": "0612345678"}), ("Léa", {"prenom": "Léa"})):
        if a.p.get("enregistree") or "RUPTURE" in json.dumps(r, ensure_ascii=False):
            break
        r = await a.tour(dit, **cases)
    if (a.p.get("question") or {}).get("type") == "numero_dicte" and "RUPTURE" not in json.dumps(r, ensure_ascii=False):  # DC10 : son « oui »
        r = await a.tour("oui", reponse={"question_id": a.p["question"]["id"], "sens": "accepte"})
    assert not a.p.get("enregistree"), r
    assert "RUPTURE" in json.dumps(r, ensure_ascii=False), r


async def test_pause_relue_pendant_l_appel(faire_monde, monkeypatch):
    """L05-05 : une pause posée pendant l'appel est vue à la fiche suivante (l'état vivant est relu à chaque geste)."""
    a, _ = await appel_trace(faire_monde, monkeypatch, "casa-italia")
    await a.charger()
    nom, variante = premier_article(a.monde)
    r = await a.tour("à emporter", mode_de_retrait="emporter")
    assert "PAUSE" not in json.dumps(r, ensure_ascii=False)
    await a.monde.c.execute(
        "UPDATE mark.resto_reglage_type SET pause_jusqu_a = $2 WHERE site_id = $1 AND type = 'emporter'", a.monde.a, JEUDI_MIDI + timedelta(minutes=30)
    )
    r = await a.tour("à emporter oui", mode_de_retrait="emporter")
    ouverture = (a.p.get("connu") or {}).get("ouverture", {}).get("emporter", {})
    assert "PAUSE_TYPE" in json.dumps(r, ensure_ascii=False) or ouverture.get("ouvert") is False, (r, ouverture)


async def test_prix_change_pendant_l_appel_pris_a_l_appel_suivant(faire_monde, monkeypatch):
    """L05-18 (D61, point 3) : un prix changé en caisse pendant l'appel ne change pas l'appel en cours ; l'appel suivant prend le nouveau."""
    a, _ = await appel_trace(faire_monde, monkeypatch, "casa-italia")
    await a.charger()
    nom, variante = premier_article(a.monde)
    ref = a.monde.produit(nom)["ref"] if "ref" in a.monde.produit(nom) else None

    async def prix() -> int:
        carte = await carte_du_restaurant(a.source.c, a.monde.a, JEUDI_MIDI)
        produit = next(p for p in carte["produits"] if p["nom"] == nom and (ref is None or p["id"] == ref))
        return next(d["prix"] for d in produit["declinaisons"] if d["nom"] == variante)

    avant = await prix()
    await a.monde.c.execute(
        "UPDATE mark.resto_declinaison SET prix = prix + 100 WHERE produit_ref IN (SELECT ref FROM mark.resto_produit WHERE nom = $1) AND nom = $2", nom, variante
    )
    assert await prix() == avant  # l'appel en cours : la carte chargée fait foi
    suivant, _ = await appel_trace(faire_monde, monkeypatch, "casa-italia", monde=a.monde)
    await suivant.charger()
    a = suivant
    assert await prix() == avant + 100  # l'appel suivant : le nouveau prix


# --------------------------------------------------------------------------- L05-06 à L05-09 : la réservation et l'heure


async def _monter_la_salle(monde) -> None:
    c, site = monde.c, monde.a
    salle = await c.fetchval("INSERT INTO mark.resto_salle (site_id, nom) VALUES ($1, 'Salle') RETURNING id", site)
    for nom, mini, maxi in (("T1", 2, 4), ("T2", 2, 2)):
        await c.execute("INSERT INTO mark.resto_table (site_id, salle_id, nom, couverts_min, couverts_max) VALUES ($1, $2, $3, $4, $5)", site, salle, nom, mini, maxi)
    await c.execute("INSERT INTO mark.resto_service (site_id, nom, debut, fin, pas_minutes) VALUES ($1, 'midi', '12:00', '13:30', 30)", site)
    await c.execute("INSERT INTO mark.resto_duree_groupe (site_id, couverts_min, couverts_max, duree_minutes) VALUES ($1, 1, 4, 60)", site)
    await c.execute("INSERT INTO mark.resto_regle_reservation (site_id, delai_minimal, jours_a_l_avance) VALUES ($1, 0, 30)", site)


async def _reservation(faire_monde):
    monde = await faire_monde("casa-italia")
    await _monter_la_salle(monde)
    monde.c.instantane = Instantane(monde.a)
    trace = ConnexionTracee(monde.c)
    return monde, trace, SourceReservation(trace, Lieu(monde.base, monde.a, 1))


def _brouillon(heure: int, minute: int = 0) -> dict:
    debut = (JEUDI_MIDI + timedelta(days=1)).replace(hour=heure, minute=minute)
    return {"debut": debut, "personnes": 2, "prenom": "Léa", "telephone": "+33612345678"}


async def test_reservation_oui_sans_salle_relue(faire_monde):
    """L05-06 (B05) : les disponibilités puis le « oui » : la salle (services, tables, règle) est lue une fois pour l'appel."""
    monde, trace, source = await _reservation(faire_monde)
    trace.remettre()
    assert (await source.disponibilites((JEUDI_MIDI + timedelta(days=1)).date(), 2)).statut == "OK"
    r = await source.creer(_brouillon(12))
    assert r.statut == "ENREGISTREE", r
    assert lues(trace, "mark.resto_service") == 1 and lues(trace, "FROM mark.resto_table ") == 1, dict(trace.textes)


async def test_propositions_reutilisent_la_salle(faire_monde):
    """L05-07 (B04) : un refus complet propose d'autres créneaux sans relire la salle."""
    monde, trace, source = await _reservation(faire_monde)
    for _ in range(2):
        await source.creer(_brouillon(12))
        monde.c.instantane.nouveau_geste()
    autre = {**_brouillon(12), "telephone": "+33600000001", "prenom": "Max"}
    await source.creer(autre)
    monde.c.instantane.nouveau_geste()
    trace.remettre()
    r = await source.creer({**_brouillon(12), "telephone": "+33600000002", "prenom": "Zoé"})
    assert r.statut == "REFUSEE" and r.faits.get("propositions"), r
    assert all(lues(trace, t) == 0 for t in TABLES_DE_LA_SALLE), dict(trace.textes)
    assert lues(trace, "FROM mark.resto_reservation") == 2, dict(trace.textes)  # le doublon, puis les occupations : une fois chacune


async def test_maintenant_sans_requete(faire_monde):
    """L05-08 (B06) : l'heure de l'organisation se lit sans requête (la base est connue de la connexion)."""
    monde = await faire_monde("casa-italia")
    trace = ConnexionTracee(monde.c)
    assert (await maintenant(trace)) == JEUDI_MIDI
    assert trace.requetes == 0, dict(trace.textes)


async def test_modifier_une_lecture_verrouillee(faire_monde):
    """L05-09 (B10) : modifier lit la réservation une seule fois, sous verrou."""
    monde, trace, source = await _reservation(faire_monde)
    r = await source.creer(_brouillon(12))
    monde.c.instantane.nouveau_geste()
    trace.remettre()
    m = await source.modifier(r.faits["numero"], {"note": "près de la fenêtre"})
    assert m.statut == "OK", m
    assert lues(trace, "SELECT * FROM mark.resto_reservation WHERE numero") == 1, dict(trace.textes)


# --------------------------------------------------------------------------- L05-10, L05-14, L05-15 : une connexion par appel (D53, S15)


@pytest.fixture
def appel_suivi(faire_monde, monkeypatch):
    """Un appel suivi (``run_id``) sur la base du monde : les connexions ouvertes sont comptées, la fin d'appel les ferme."""

    async def faire(slug: str = "casa-italia"):
        monde = await faire_monde(slug)
        ouvertes: list = []

        async def connecter(nom_base: str):
            c = await schema.connecter(nom_base)
            ouvertes.append(c)
            return c

        async def base_et_cle(ctx):
            return monde.base, slug

        monkeypatch.setattr(M, "CONNECTER", connecter)
        monkeypatch.setattr(M, "base_et_cle_de_l_appel", base_et_cle)
        ctx = SimpleNamespace(run_id=f"essai-{id(monde)}", organization_id=None, appel={}, configurations={}, reglages={})
        return monde, ctx, ouvertes

    return faire


async def test_une_connexion_par_appel(appel_suivi):
    """L05-10 (S15) : la réservation ouvre une connexion par appel, partagée avec la commande, fermée à la fin de l'appel."""
    monde, ctx, ouvertes = await appel_suivi()
    for _ in range(3):
        async with source_reservation.ouvrir_la_source(ctx) as s:
            await s.disponibilites((JEUDI_MIDI + timedelta(days=1)).date(), 2)
    async with source_commande.ouvrir_la_source(ctx) as s:
        await s.etat("emporter")
    assert len(ouvertes) == 1 and not ouvertes[0].is_closed()
    await M.fermer(ctx.run_id)
    assert ouvertes[0].is_closed()


async def test_une_connexion_par_appel_commande(appel_suivi):
    """L05-14 (D53) : trois fiches de commande dans un appel : une seule connexion, fermée à la fin de l'appel."""
    monde, ctx, ouvertes = await appel_suivi()
    for _ in range(3):
        async with source_commande.ouvrir_la_source(ctx) as s:
            await s.etat("emporter")
    assert len(ouvertes) == 1 and not ouvertes[0].is_closed()
    await M.fermer(ctx.run_id)
    assert ouvertes[0].is_closed() and M.appel_ouvert(ctx.run_id) is None


async def test_connexion_rouverte_si_coupee(appel_suivi):
    """L05-15 (D53) : la base coupe la connexion entre deux fiches : rouverte une fois ; coupée encore : la panne."""
    monde, ctx, ouvertes = await appel_suivi()
    async with source_commande.ouvrir_la_source(ctx) as s:
        await s.etat("emporter")
    ouvertes[0].terminate()
    async with source_commande.ouvrir_la_source(ctx) as s:
        assert (await s.etat("emporter"))["ouvert"] in (True, False)
    assert len(ouvertes) == 2
    ouvertes[1].terminate()
    with pytest.raises(BaseClientIndisponible):
        async with source_commande.ouvrir_la_source(ctx) as s:
            pass
    await M.fermer(ctx.run_id)


# --------------------------------------------------------------------------- L05-11, L05-16, L05-17 : le chargement au décroché (D58)


async def test_chargement_en_parallele_de_l_accueil(appel_suivi, monkeypatch):
    """L05-11 : lancer le chargement rend la main tout de suite (la phrase d'accueil ne l'attend pas) ; il finit ensuite."""
    monde, ctx, _ = await appel_suivi()
    vrai = SourceClasseur.charger_pour_l_appel

    async def lent(self):
        await asyncio.sleep(0.3)
        return await vrai(self)

    monkeypatch.setattr(SourceClasseur, "charger_pour_l_appel", lent)
    contexte: dict = {}
    debut = time.perf_counter()
    tache = M.lancer_le_chargement(ctx, monde.base, contexte=contexte, fiche_de_l_appel={})
    assert (time.perf_counter() - debut) < 0.05 and not tache.done()
    await tache
    assert contexte.get("commande_modes"), contexte
    await M.fermer(ctx.run_id)


async def test_fiche_attend_le_chargement(appel_suivi, monkeypatch):
    """L05-16 (D58) : une fiche arrivée avant la fin du chargement attend le court délai et sert depuis la mémoire."""
    monde, ctx, _ = await appel_suivi()
    # le délai de D58 (300 ms) est un réglage ; ici il est large pour que la preuve ne dépende pas de la vitesse de la première connexion (nettoyeur 3)
    ctx.configurations = {**(getattr(ctx, "configurations", None) or {}), M.CLE_ATTENTE: 5000}
    vrai = SourceClasseur.charger_pour_l_appel

    async def un_peu_lent(self):
        await asyncio.sleep(0.1)
        return await vrai(self)

    monkeypatch.setattr(SourceClasseur, "charger_pour_l_appel", un_peu_lent)
    tache = M.lancer_le_chargement(ctx, monde.base, contexte={}, fiche_de_l_appel={})
    async with source_commande.ouvrir_la_source(ctx) as s:
        assert tache.done()
        assert ("tables_de_la_carte", monde.a) in s.c.instantane.stables
    await M.fermer(ctx.run_id)


async def test_chargement_en_echec_repli(appel_suivi, monkeypatch):
    """L05-17 (D58) : chargement en échec, ou trop long : la fiche lit la base directement, rien n'est refusé."""
    monde, ctx, _ = await appel_suivi()

    async def en_panne(self):
        raise RuntimeError("panne du chargement")

    monkeypatch.setattr(SourceClasseur, "charger_pour_l_appel", en_panne)
    M.lancer_le_chargement(ctx, monde.base, contexte={}, fiche_de_l_appel={})
    async with source_commande.ouvrir_la_source(ctx) as s:
        r = await s.chercher(premier_article(monde)[0])
        assert r.statut in ("RETENU", "AMBIGU"), r
    await M.fermer(ctx.run_id)

    monde2, ctx2, _ = await appel_suivi("etoile-d-or")

    async def trop_long(self):
        await asyncio.sleep(2)

    monkeypatch.setattr(SourceClasseur, "charger_pour_l_appel", trop_long)
    ctx2.configurations = {M.CLE_ATTENTE: 50}
    tache = M.lancer_le_chargement(ctx2, monde2.base, contexte={}, fiche_de_l_appel={})
    debut = time.perf_counter()
    async with source_commande.ouvrir_la_source(ctx2) as s:
        assert (time.perf_counter() - debut) < 1.0 and not tache.done()
        assert (await s.chercher(premier_article(monde2)[0])).statut in ("RETENU", "AMBIGU")
    await M.fermer(ctx2.run_id)


# --------------------------------------------------------------------------- L05-12 : le découpage du tour


def test_decoupage_du_tour():
    """L05-12 : ``mesure_du_tour`` rend, par tour, les cinq postes (fin de parole, modèle, code, base, voix) sur une trace enregistrée."""
    from api.tests.mark.partie_1 import mesure_du_tour

    tours = mesure_du_tour.decouper(mesure_du_tour.trace_d_essai())
    assert tours, tours
    for t in tours:
        assert set(mesure_du_tour.POSTES) <= set(t), t
    assert any(t["modele_ms"] > 0 for t in tours) and any(t["code_ms"] is not None for t in tours)
