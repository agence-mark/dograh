"""[.mark] Chantier Partie 1, lot 14 : les briques offres (``services/commande/briques/off*.py``).

Une classe par brique (``TestOFF1`` à ``TestOFF4``), chacune avec sa règle, son aller-retour en caisse (``discounts``, ``price_off``, d'après la documentation HubRise) et son test de
rendu de la fiche (D66) ; plus la migration 044 (le code de remise), la preuve qu'une remise à code n'est jamais annoncée, et l'offre proposée une fois par appel (L14-01).
Un test = un essai à la fois.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes.du import CLE_DU
from api.db.bases_clients import remises_moteur as moteur
from api.db.bases_clients import restauration_commande as RC
from api.services.commande import contrat
from api.services.restauration.caisse.prises.hubrise_traduction import centimes, commande_vers_hubrise
from api.tests.mark.partie_1.aides_briques import brique, descendre_jusqu_a, fait, la_brique_change_la_fiche
from api.tests.mark.test_base_client import base_essai  # noqa: F401


async def _remise(e, ref: str, mecanisme: str, declencheur: dict, effet: dict, perimetre: dict, *, code: str | None = None, etat: str = "active", fin: datetime | None = None,
                  phrase: str | None = None, site: int | None = None) -> None:
    await e.monde.c.execute(
        "INSERT INTO mark.resto_remise (site_id, ref, nom, mecanisme, declencheur, effet, perimetre, etat, cumul, code, fin, phrase) "
        "VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb, $8, 'exclusive', $9, $10, $11)",
        site or e.monde.a, ref, f"Remise {ref}", mecanisme, json.dumps(declencheur), json.dumps(effet), json.dumps(perimetre), etat, code, fin, phrase,
    )


async def _essai_avec(essai_de, code_de_brique: str, *remises: tuple):
    """L'essai de la brique, ses remises posées AVANT le chargement de l'appel (le chargement les lit une fois)."""

    e = await essai_de(f"briques/{code_de_brique}")
    for r in remises:
        await _remise(e, *r[:5], **(r[5] if len(r) > 5 else {}))
    await e.charger()
    e.fiche_de_l_appel[contrat.CLE_DES_OBJETS] = (await e.source.charger_pour_l_appel())[1]
    await e.tour("à emporter", mode_de_retrait="emporter")
    return e


async def _lu(e):
    """La lecture du panier par le moteur (le résultat, avec la phrase que le code dit) : ce que ``lire(sujet=panier)`` rend, sans l'enveloppe."""
    from api.services.commande import moteur, porte

    return await moteur.voir_commande(e.source, e.p, porte._regles(e.ctx))


def _total_caisse(corps: dict) -> int:
    """Ce que HubRise recalcule : les articles et leurs options, moins les remises."""
    articles = sum((centimes(a["price"]) + sum(centimes(o["price"]) * int(o.get("quantity", 1)) for o in a.get("options") or [])) * int(a["quantity"]) for a in corps["items"])
    return articles - sum(centimes(d["price_off"]) for d in corps.get("discounts") or [])


def _lignes_de(*codes: str) -> list[dict]:
    return [{"code_caisse": c, "quantite": n, "choix": []} for c, n in codes]


# --------------------------------------------------------------------------- #
# La migration 044 : le code de remise, en ajout
# --------------------------------------------------------------------------- #


async def test_migration_044_montee_descente(base_prete):
    """Montée, descente, remontée : la colonne ``code`` et son index unique partiel (par établissement) ; les remises existantes sont les mêmes avant et après."""
    from api.db.bases_clients import connexion as schema

    async def presente(c) -> tuple[bool, bool]:
        colonne = bool(await c.fetchval("SELECT 1 FROM information_schema.columns WHERE table_schema='mark' AND table_name='resto_remise' AND column_name='code'"))
        index = bool(await c.fetchval("SELECT 1 FROM pg_indexes WHERE schemaname='mark' AND indexname='resto_remise_code_idx'"))
        return colonne, index

    c = await schema.connecter_proprietaire(base_prete)
    try:
        assert await presente(c) == (True, True)
        for _ in range(2):
            await descendre_jusqu_a(c, 44)
            assert await presente(c) == (False, False) and 44 not in [r["version"] for r in await c.fetch("SELECT version FROM mark.schema_version")]
            assert 44 in await schema.appliquer_migrations(c)
            assert await presente(c) == (True, True)
    finally:
        await c.close()


async def test_un_code_est_unique_dans_un_etablissement(essai_de):
    """Deux remises du même établissement ne partagent pas un code ; deux remises sans code se côtoient ; un autre établissement peut porter le même."""
    import asyncpg
    import pytest

    e = await essai_de("briques/OFF3")
    await _remise(e, "R1", "pourcentage", {}, {"pourcentage": 10}, {}, code="BIENVENUE")
    await _remise(e, "R2", "pourcentage", {}, {"pourcentage": 5}, {})
    await _remise(e, "R3", "pourcentage", {}, {"pourcentage": 5}, {})
    with pytest.raises(asyncpg.UniqueViolationError):
        await _remise(e, "R4", "pourcentage", {}, {"pourcentage": 10}, {}, code="BIENVENUE")
    with pytest.raises(asyncpg.CheckViolationError):
        await _remise(e, "R5", "pourcentage", {}, {"pourcentage": 10}, {}, code="pas bon")


# --------------------------------------------------------------------------- #
# L14-02 : OFF1, N achetés, M offerts
# --------------------------------------------------------------------------- #

BARQUETTES = ("P-BARQ-FRAMBOISE-UNIQUE", "P-BARQ-CITRON-UNIQUE", "P-BARQ-PISTACHE-UNIQUE")
OFFRE_BARQUETTES = ("OFFRE-BARQ", "x_achetes_y_offert", {"achetes": 3}, {"offerts": 1}, {"categories": ["barquettes"]})


class TestOFF1:
    def test_off1_par_paliers(self):
        """« Trois barquettes, la quatrième offerte » (A7) : sur quatre, la moins chère est offerte ; sur trois, rien ; le plafond de la remise limite les offerts."""
        from api.services.commande.briques.lot_offert import brique_off1_par_paliers

        prix = [790, 690, 890, 790]
        unites = [moteur.Unite(i, f"C{i}", p, categorie="barquettes") for i, p in enumerate(prix, start=1)]
        assert brique_off1_par_paliers(3, 1, unites) == {"montant": 690, "unites": [2]}
        assert brique_off1_par_paliers(3, 1, unites[:3]) == {}
        huit = [moteur.Unite(i, f"C{i}", 100 + i, categorie="barquettes") for i in range(1, 9)]
        assert brique_off1_par_paliers(3, 1, huit)["montant"] == 105 + 101 and brique_off1_par_paliers(3, 1, huit, plafond=1)["montant"] == 105

    async def test_off1_chiffre_la_remise_au_centime(self, essai_de):
        """Quatre barquettes (7,90 + 7,90 + 6,90 + 8,90 = 31,60 €) : la moins chère est offerte, 6,90 € de remise, total net 24,70 € ; à trois, aucune remise."""
        e = await _essai_avec(essai_de, "OFF1", OFFRE_BARQUETTES)
        c, a = e.monde.c, e.monde.a
        quatre = await RC.chiffrer_panier(c, a, "emporter", _lignes_de((BARQUETTES[0], 2), (BARQUETTES[1], 1), (BARQUETTES[2], 1)))
        assert quatre.statut == "OK" and quatre.faits["sous_total"] == 3160 and [(r["ref"], r["montant"]) for r in quatre.faits["remises"]] == [("OFFRE-BARQ", 690)], quatre
        assert quatre.faits["total"] == 2470
        trois = await RC.chiffrer_panier(c, a, "emporter", _lignes_de((BARQUETTES[0], 1), (BARQUETTES[1], 1), (BARQUETTES[2], 1)))
        assert trois.faits["remises"] == [] and trois.faits["total"] == 2370

    async def test_off1_aller_retour_caisse(self, essai_de):
        """La remise part à la caisse en ``discounts`` (``price_off`` calculé chez nous) et la caisse retrouve notre total."""
        e = await _essai_avec(essai_de, "OFF1", OFFRE_BARQUETTES)
        r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", _lignes_de((BARQUETTES[0], 2), (BARQUETTES[1], 1), (BARQUETTES[2], 1)))
        corps = commande_vers_hubrise({"numero": "n-1", "mode": "emporter", "client": {}, "lignes": r.faits["lignes"], "remises": r.faits["remises"]})
        assert corps["discounts"] == [{"name": "Remise OFFRE-BARQ", "price_off": "6.90 EUR"}] and _total_caisse(corps) == r.faits["total"]

    async def test_off1_fiche_du_modele(self, essai_de):
        """Une remise se règle au portail : la fiche du modèle ne change pas (déclaré non)."""
        assert await la_brique_change_la_fiche("OFF1", essai_de) is False


# --------------------------------------------------------------------------- #
# L14-03 : OFF2, la remise en pourcentage
# --------------------------------------------------------------------------- #

PLATS_CHAUDS = ("OFFRE-CHAUDS", "pourcentage", {}, {"pourcentage": 20}, {"categories": ["plats-chauds"]})


class TestOFF2:
    def test_off2_en_fin_de_calcul(self):
        """Vingt pour cent sur les plats chauds seulement : 12 € et 9,50 € de plats, un dessert à 4,50 € hors périmètre : 4,30 € de remise ; rien à réduire hors périmètre."""
        from api.services.commande.briques.remise_en_pourcentage import brique_off2_en_fin_de_calcul

        unites = [moteur.Unite(1, "L", 1200, categorie="plats-chauds"), moteur.Unite(2, "G", 950, categorie="plats-chauds"), moteur.Unite(3, "T", 450, categorie="desserts")]
        assert brique_off2_en_fin_de_calcul(20, unites, {"categories": ["plats-chauds"]}) == {"montant": 430, "unites": [1, 2]}
        assert brique_off2_en_fin_de_calcul(20, unites[2:], {"categories": ["plats-chauds"]}) == {}
        assert brique_off2_en_fin_de_calcul(20, unites, {"modes": ["livraison"]}, mode="emporter") == {}

    async def test_off2_montant_dit_par_le_code(self, essai_de):
        """Lasagnes, gratin et tiramisu : 21,50 € + 4,50 € ; la remise de 4,30 € est celle du code, le total net 21,70 € ; la lecture du panier la dit en lettres."""
        e = await _essai_avec(essai_de, "OFF2", PLATS_CHAUDS)
        r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", _lignes_de(("P-LASAGNES-UNIQUE", 1), ("P-GRATIN-UNIQUE", 1), ("P-TIRAMISU-UNIQUE", 1)))
        assert r.faits["total_remises"] == 430 and r.faits["total"] == 2170, r
        retour = await e.tour("une lasagne, un gratin et un tiramisu", ajouter=[{"article": "lasagnes", "quantite": 1}, {"article": "gratin", "quantite": 1}, {"article": "tiramisu", "quantite": 1}])
        lu = await _lu(e)
        # T7, C6 n° 11 (décision d'Evan 25/11 9 h 30) : la lecture rend le FAIT de la remise ; sa phrase n'est plus qu'un texte de secours (retiré par C7a), le modèle la dit
        assert lu.faits["total_remises"] == 430 and lu.faits["total"] == 2170, (fait(retour), lu)

    async def test_off2_aller_retour_caisse(self, essai_de):
        e = await _essai_avec(essai_de, "OFF2", PLATS_CHAUDS)
        r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", _lignes_de(("P-LASAGNES-UNIQUE", 1), ("P-GRATIN-UNIQUE", 1), ("P-TIRAMISU-UNIQUE", 1)))
        corps = commande_vers_hubrise({"numero": "n-1", "mode": "emporter", "client": {}, "lignes": r.faits["lignes"], "remises": r.faits["remises"]})
        assert corps["discounts"] == [{"name": "Remise OFFRE-CHAUDS", "price_off": "4.30 EUR"}] and _total_caisse(corps) == r.faits["total"]

    async def test_off2_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("OFF2", essai_de) is False


# --------------------------------------------------------------------------- #
# L14-04 : OFF3, le code de remise
# --------------------------------------------------------------------------- #

BIENVENUE = ("R-BIENVENUE", "pourcentage", {}, {"pourcentage": 10}, {}, {"code": "BIENVENUE", "phrase": "dix pour cent avec le code"})
PIZZA5 = ("R-PIZZA5", "montant", {}, {"montant": 500}, {}, {"code": "PIZZA5"})


class TestOFF3:
    def test_off3_verifier_le_code(self):
        """Le code dit est lu sous une seule forme (« pizza cinq » vaut PIZZA5, « bien venue » vaut BIENVENUE) ; un code que l'établissement n'a pas est ``code_inconnu`` ; jamais deviné."""
        from api.services.commande.briques.code_de_remise import brique_off3_verifier_le_code

        codes = [{"code": "BIENVENUE", "ref": "R1", "nom": "Bienvenue", "phrase": None}, {"code": "PIZZA5", "ref": "R2", "nom": "Pizza cinq", "phrase": None}]
        assert brique_off3_verifier_le_code("BIENVENUE", codes)["ref"] == "R1" and brique_off3_verifier_le_code("bien venue", codes)["ref"] == "R1"
        assert brique_off3_verifier_le_code("pizza cinq", codes)["code"] == "PIZZA5"
        assert brique_off3_verifier_le_code("BIENVENU", codes) == {"raison": "code_inconnu", "dit": "BIENVENU"}
        assert brique_off3_verifier_le_code("", codes)["raison"] == "code_inconnu" and brique_off3_verifier_le_code("BIENVENUE", [])["raison"] == "code_inconnu"

    async def test_off3_un_code_valide_chiffre_la_remise(self, essai_de):
        """« J'ai le code BIENVENUE » avec un panier de 23 € : la remise de 10 % est chiffrée par le code (2,30 €) et dite ; le total net suit ; sans le code, aucune remise."""
        e = await _essai_avec(essai_de, "OFF3", BIENVENUE)
        await e.tour("une margherita et une reine", ajouter=[{"article": "margherita", "quantite": 1}, {"article": "reine", "quantite": 1}])
        avant = await e.lecture(sujet="panier")
        assert '"remises": []' in fait(avant)
        r = await e.tour("j'ai le code BIENVENUE", code_de_remise="BIENVENUE")
        assert "code_inconnu" not in fait(r) and '"reduction": 230' in fait(r), fait(r)
        apres = await e.lecture(sujet="panier")
        assert '"total_remises": 230' in fait(apres) and '"total": 2070' in fait(apres), fait(apres)
        assert e.p["codes_dits"] == ["BIENVENUE"]

    async def test_off3_pizza_cinq_est_pizza5(self, essai_de):
        """Le code épelé en mots (« pizza cinq ») est le code PIZZA5."""
        e = await _essai_avec(essai_de, "OFF3", PIZZA5)
        await e.tour("une margherita", ajouter=[{"article": "margherita", "quantite": 1}])
        r = await e.tour("j'ai le code pizza cinq", code_de_remise="pizza cinq")
        assert e.p["codes_dits"] == ["PIZZA5"] and '"reduction": 500' in fait(r), fait(r)

    async def test_off3_code_faux_expire_ou_brouillon_meme_refus(self, essai_de):
        """Un code faux, celui d'une remise expirée, celui d'une remise brouillon et celui d'une remise d'un autre établissement : le même refus ``code_inconnu``, rien n'est posé."""
        hier = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
        e = await essai_de("briques/OFF3")
        await _remise(e, "R-EXPIREE", "pourcentage", {}, {"pourcentage": 10}, {}, code="EXPIREE", fin=hier)
        await _remise(e, "R-BROUILLON", "pourcentage", {}, {"pourcentage": 10}, {}, code="BROUILLON", etat="brouillon")
        autre = await e.monde.c.fetchval("INSERT INTO mark.entreprise (raison_sociale) VALUES ('Autre') RETURNING id")
        site = await e.monde.c.fetchval("INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) VALUES ($1, 'autre', 'autre', 'Europe/Paris') RETURNING id", autre)
        await _remise(e, "R-AUTRE", "pourcentage", {}, {"pourcentage": 10}, {}, code="AUTRE", site=site)
        await _remise(e, "R-OK", "pourcentage", {}, {"pourcentage": 10}, {}, code="BIENVENUE")
        await e.charger()
        e.fiche_de_l_appel[contrat.CLE_DES_OBJETS] = (await e.source.charger_pour_l_appel())[1]
        await e.tour("à emporter", mode_de_retrait="emporter")
        await e.tour("une margherita", ajouter=[{"article": "margherita", "quantite": 1}])
        refus = []
        for dit in ("FAUX", "EXPIREE", "BROUILLON", "AUTRE"):
            r = await e.tour(f"j'ai le code {dit}", code_de_remise=dit)
            refus.append(fait({k: v for k, v in r.items() if k != CLE_DU}))  # le constat du code (lot 7a) n'est jamais lu par le modèle : on compare ce que le modèle reçoit
            assert "code_inconnu" in refus[-1] and e.p["codes_dits"] == [], refus[-1]
        # le même refus pour les quatre ; la consigne du journal de ce qui est dit (B3 : issue, puis sortie) change d'un essai à l'autre, pas le refus
        sans_journal = [re.sub(r'"a_faire": "[^"]*"(, )?', "", x) for x in refus]
        uniques = {x.replace("FAUX", "X").replace("EXPIREE", "X").replace("BROUILLON", "X").replace("AUTRE", "X") for x in sans_journal}
        assert len(uniques) == 1, " || ".join(uniques)

    async def test_off3_un_code_dit_deux_fois_une_remise(self, essai_de):
        """Le même code dit deux fois : une seule remise, une seule fois dans les codes de l'appel."""
        e = await _essai_avec(essai_de, "OFF3", BIENVENUE)
        await e.tour("une margherita et une reine", ajouter=[{"article": "margherita", "quantite": 1}, {"article": "reine", "quantite": 1}])
        await e.tour("le code BIENVENUE", code_de_remise="BIENVENUE")
        await e.tour("je répète, le code BIENVENUE", code_de_remise="BIENVENUE")
        lu = await e.lecture(sujet="panier")
        assert e.p["codes_dits"] == ["BIENVENUE"] and '"total_remises": 230' in fait(lu), fait(lu)

    async def test_off3_la_remise_suit_le_panier(self, essai_de):
        """Le code dit AVANT le panier est noté (``appliquee`` faux, la remise s'appliquera) puis la remise se chiffre dès qu'il y a de quoi."""
        e = await _essai_avec(essai_de, "OFF3", BIENVENUE)
        r = await e.tour("j'ai le code BIENVENUE", code_de_remise="BIENVENUE")
        assert '"appliquee": false' in fait(r) and e.p["codes_dits"] == ["BIENVENUE"], fait(r)
        await e.tour("une margherita", ajouter=[{"article": "margherita", "quantite": 1}])
        lu = await e.lecture(sujet="panier")
        assert '"total_remises": 100' in fait(lu), fait(lu)

    async def test_off3_la_remise_du_code_est_dite_par_le_code_quand_elle_s_applique(self, essai_de):
        """Conversation OFF3-A : la remise donnée par le code est dite une fois, au moment où elle s'applique : le code d'abord puis les articles, ou les articles d'abord puis le code.
        C6 n° 11 (décision d'Evan 25/11 9 h 30, § 8 bis) : c'est un FAIT du retour (``remises_a_dire`` : nom, montant) que le modèle dit avec ses mots, vérifié par la barrière ; le
        code ne dit plus de phrase après la sienne."""
        from api.services.actions_communes.barriere_des_chiffres import chiffre_dans_la_phrase
        from api.services.actions_communes.du import faits_du_refus
        from api.services.commande import porte

        def suffixe(e):
            return (e.fiche_de_l_appel.get(porte.CLE_TEXTES_DU_CODE) or {}).get("suffixe")

        e = await _essai_avec(essai_de, "OFF3", ("R-BIENVENUE", "pourcentage", {}, {"pourcentage": 10}, {}, {"code": "BIENVENUE"}))
        r = await e.tour("j'ai le code BIENVENUE", code_de_remise="BIENVENUE")
        assert "remises_a_dire" not in r["faits"]  # le panier est vide : rien à dire encore
        r = await e.tour("une margherita et une reine", ajouter=[{"article": "margherita", "quantite": 1}, {"article": "reine", "quantite": 1}])
        assert [x["montant"] for x in r["faits"]["remises_a_dire"]] == [230] and not suffixe(e) and "prix_dit_par_le_code_apres_ta_phrase" not in r, (r["faits"], suffixe(e))
        assert not chiffre_dans_la_phrase("Votre code vous fait deux euros trente de moins.", faits=faits_du_refus(r))  # le montant passe la barrière
        r = await e.tour("et une autre margherita", ajouter=[{"article": "margherita", "quantite": 1}])
        assert "remises_a_dire" not in r["faits"]  # une seule fois
        autre = await _essai_avec(essai_de, "OFF3", ("R-BIENVENUE", "pourcentage", {}, {"pourcentage": 10}, {}, {"code": "BIENVENUE"}))
        await autre.tour("une margherita et une reine", ajouter=[{"article": "margherita", "quantite": 1}, {"article": "reine", "quantite": 1}])
        r = await autre.tour("le code BIENVENUE", code_de_remise="BIENVENUE")
        assert [x["montant"] for x in r["faits"]["remises_a_dire"]] == [230] and not suffixe(autre), r["faits"]

    async def test_off3_reduction_annoncee_le_modele_demande_le_code(self, essai_de):
        """« J'ai un code » sans le dire : le retour rend le fait et ``manque`` ``code_de_remise`` (la question vient du modèle) ; rien n'est posé."""
        e = await _essai_avec(essai_de, "OFF3", BIENVENUE)
        r = await e.tour("j'ai un code de réduction", reduction_annoncee=True)
        assert '"reduction_annoncee": true' in fait(r) and '"manque": "code_de_remise"' in fait(r) and e.p["codes_dits"] == [], fait(r)

    async def test_remise_a_code_jamais_annoncee(self, essai_de):
        """La remise à code n'est ni dans « qu'est-ce que vous avez », ni dans la liste des remises en cours, ni proposée en plus ; la même remise sans code, elle, l'est."""
        e = await _essai_avec(essai_de, "OFF3", BIENVENUE, ("R-OUVERTE", "pourcentage", {}, {"pourcentage": 5}, {}, {"phrase": "cinq pour cent sur tout"}))
        offres = await e.lecture(sujet="offres")
        assert "cinq pour cent" in fait(offres) and "BIENVENUE" not in fait(offres) and "dix pour cent avec le code" not in fait(offres), fait(offres)
        en_cours = await e.source.remises_en_cours()
        assert [r["ref"] for r in en_cours] == ["R-OUVERTE"]
        await e.tour("une margherita", ajouter=[{"article": "margherita", "quantite": 1}])
        a_portee = await e.source.offres_a_portee("emporter", [])
        assert a_portee == [] and "R-BIENVENUE" not in fait(e.retours[-1])

    async def test_off3_les_cases_n_existent_que_si_l_etablissement_a_un_code(self, essai_de):
        """Sans remise à code, la fiche ne montre ni ``code_de_remise`` ni ``reduction_annoncee`` ; avec une remise active sans code non plus ; avec une remise à code, oui."""
        sans = await essai_de("briques/OFF3")
        await _remise(sans, "R-OUVERTE", "pourcentage", {}, {"pourcentage": 5}, {})
        assert (await sans.source.charger_pour_l_appel())[1]["code_de_remise"] is False
        avec = await essai_de("briques/OFF3")
        await _remise(avec, "R-BIENVENUE", "pourcentage", {}, {"pourcentage": 10}, {}, code="BIENVENUE")
        assert (await avec.source.charger_pour_l_appel())[1]["code_de_remise"] is True

    async def test_off3_la_remise_a_code_part_a_la_caisse(self, essai_de):
        """Le code dit puis la commande enregistrée : la remise est recalculée chez nous avec le code (jamais le montant du modèle), la ligne de remise part en ``discounts``."""
        e = await _essai_avec(essai_de, "OFF3", BIENVENUE)
        c, a = e.monde.c, e.monde.a
        panier = _lignes_de(("P-MARGHERITA-UNIQUE", 1), ("P-REINE-UNIQUE", 1))
        chiffre = await RC.chiffrer_panier(c, a, "emporter", panier, codes=["BIENVENUE"])
        assert [r["ref"] for r in chiffre.faits["remises"]] == ["R-BIENVENUE"] and chiffre.faits["total"] == 2070
        sans_code = await RC.chiffrer_panier(c, a, "emporter", panier)
        assert sans_code.faits["remises"] == []
        brouillon = {"mode": "emporter", "client": {"telephone": "+33600000001"}, "lignes": panier, "remises": [{"ref": "R-BIENVENUE"}], "codes": ["BIENVENUE"],
                     "paiement": {"moyens": [{"moyen": "carte", "montant": 2070}], "reste_par_moyen": {}}}
        r = await RC.enregistrer_commande(c, a, brouillon, "jeton")
        assert r.statut == "ENREGISTREE" and r.faits["total"] == 2070, r
        refuse = await RC.enregistrer_commande(c, a, {**brouillon, "codes": []}, "jeton-2")
        assert refuse.statut == "REFUSEE", refuse  # la remise nommée sans son code dit ne s'applique pas

    async def test_off3_fiche_du_modele(self, essai_de):
        """Déclaré OUI : l'établissement a une remise à code, le modèle voit deux cases de plus ; sans, la fiche est celle d'avant."""
        from api.tests.mark.partie_1 import rendu_de_la_fiche as RF

        avec = await essai_de("briques/OFF3")
        await _remise(avec, "R-BIENVENUE", "pourcentage", {}, {"pourcentage": 10}, {}, code="BIENVENUE")
        sans = await essai_de("briques/OFF3")
        try:
            rendu_avec, rendu_sans = await RF.rendu_de_la_fiche(avec, "OFF3"), await RF.rendu_de_la_fiche(sans, "OFF3")
            assert rendu_avec != rendu_sans and {"code_de_remise", "reduction_annoncee"} <= set(rendu_avec["cases"]) - set(rendu_sans["cases"])
        finally:
            await avec.monde.c.close()
            await sans.monde.c.close()


# --------------------------------------------------------------------------- #
# L14-05 : OFF4, la livraison offerte
# --------------------------------------------------------------------------- #

ADRESSE = {"adresse": "5 rue Louis Boilet", "commune": "Pont-Sainte-Maxence"}


async def _essai_livraison(essai_de):
    """L'essai d'OFF4 dont la zone porte 3 € de frais et la gratuité dès 20 € (posés AVANT le chargement de l'appel, qui lit les zones une fois), à emporter pour commencer."""

    e = await essai_de("briques/OFF4")
    zone = await _zone_a_frais(e)
    await e.tour("à emporter", mode_de_retrait="emporter")
    return e, zone


async def _zone_a_frais(e, frais: int = 300, gratuite_des: int | None = 2000) -> int:
    await e.monde.c.execute("UPDATE mark.resto_zone SET frais = $2, gratuite_des = $3 WHERE site_id = $1", e.monde.a, frais, gratuite_des)
    return await e.monde.c.fetchval("SELECT id FROM mark.resto_zone WHERE site_id = $1", e.monde.a)


class TestOFF4:
    def test_off4_frais_retires(self):
        """Sous le seuil les frais restent ; au seuil et au-delà, zéro et ``livraison_offerte`` ; une zone sans frais n'offre rien ; sans seuil, rien n'est retiré."""
        from api.services.commande.briques.livraison_offerte import brique_off4_frais_retires

        zone = {"frais": 300, "gratuite_des": 2000}
        assert brique_off4_frais_retires(zone, 1999) == {"frais": 300, "livraison_offerte": False}
        assert brique_off4_frais_retires(zone, 2000) == {"frais": 0, "livraison_offerte": True}
        assert brique_off4_frais_retires({"frais": 0, "gratuite_des": 2000}, 3000) == {"frais": 0, "livraison_offerte": False}
        assert brique_off4_frais_retires({"frais": 300, "gratuite_des": None}, 9999) == {"frais": 300, "livraison_offerte": False}

    async def test_off4_au_dela_du_seuil_frais_a_zero_dit_par_le_code(self, essai_de):
        """Un burger (8,90 €) : 3 € de frais ; deux burgers (17,80 €) et un double (12,90 €) au-delà de 20 € : zéro ; à emporter, aucun frais ni livraison offerte."""
        e, zone = await _essai_livraison(essai_de)
        c, a = e.monde.c, e.monde.a
        sous = await RC.chiffrer_panier(c, a, "livraison", _lignes_de(("P-BURGER-UNIQUE", 1), ("P-DOUBLE-UNIQUE", 0 + 1)), zone)
        assert sous.faits["sous_total"] == 2180 and sous.faits["frais"] == 0 and sous.faits["livraison_offerte"] is True, sous
        petit = await RC.chiffrer_panier(c, a, "livraison", _lignes_de(("P-BURGER-UNIQUE", 1)), zone)
        assert petit.faits["frais"] == 300 and petit.faits["livraison_offerte"] is False and petit.faits["total"] == 1190
        emporter = await RC.chiffrer_panier(c, a, "emporter", _lignes_de(("P-BURGER-UNIQUE", 3)))
        assert emporter.faits["frais"] == 0 and emporter.faits["livraison_offerte"] is False

    async def test_off4_le_code_dit_la_livraison_offerte(self, essai_de):
        """La lecture du panier dit « La livraison est offerte » (le code, pas le modèle) au-delà du seuil, et rend les frais ; sous le seuil, elle ne le dit pas."""
        e, _ = await _essai_livraison(essai_de)
        await e.tour("en livraison au 5 rue Louis Boilet à Pont-Sainte-Maxence", mode_de_retrait="livraison", **ADRESSE)
        await e.tour("un burger", ajouter=[{"article": "burger maison", "quantite": 1}])
        petit = await _lu(e)
        # T7, C6 n° 11 (décision d'Evan 25/11 9 h 30) : la livraison offerte est un FAIT de la lecture (``livraison_offerte``, ``frais``), que le modèle dit ; plus la phrase du code
        assert petit.faits["frais"] == 300 and "livraison_offerte" not in petit.faits, petit
        await e.tour("et un double burger", ajouter=[{"article": "double burger", "quantite": 1}])
        grand = await _lu(e)
        assert grand.faits["livraison_offerte"] is True and grand.faits["frais"] == 0, grand

    async def test_off4_aller_retour_caisse(self, essai_de):
        """Au-delà du seuil la commande part sans frais de livraison (aucune charge ``delivery``) et la caisse retrouve notre total."""
        e, zone = await _essai_livraison(essai_de)
        r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "livraison", _lignes_de(("P-BURGER-UNIQUE", 1), ("P-DOUBLE-UNIQUE", 1)), zone)
        corps = commande_vers_hubrise({"numero": "n-1", "mode": "livraison", "client": {}, "lignes": r.faits["lignes"], "frais": r.faits["frais"]})
        assert _total_caisse(corps) + sum(centimes(ch["price"]) for ch in corps.get("charges") or []) == r.faits["total"]
        assert not corps.get("charges")

    async def test_off4_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("OFF4", essai_de) is False


# --------------------------------------------------------------------------- #
# L14-01 : l'offre proposée une fois par appel, en question numérotée
# --------------------------------------------------------------------------- #


async def test_offre_proposee_une_fois_par_appel(essai_de):
    """Un plat chaud acheté, un dessert offert (offre atteinte) : le code la propose UNE fois, en question numérotée de type ``proposition`` (réponses accepte, refuse, autre), avec le
    dessert précis ; refusée, elle ne revient plus aux ajouts suivants (une seule mention de remise dans l'appel). Le code seul décide quoi proposer et quand (D23)."""
    e = await essai_de("briques/OFF2")
    await _remise(e, "R-DESSERT", "x_achetes_y_offert", {"achetes": 1}, {"offerts": 1, "perimetre_offert": {"categories": ["desserts"]}}, {"categories": ["plats-chauds"]},
                  phrase="un plat chaud acheté, un dessert offert")
    await e.tour("à emporter", mode_de_retrait="emporter")
    r1 = await e.tour("une lasagne", ajouter=[{"article": "lasagnes", "quantite": 1}])
    q = r1.get("question")
    assert q and q["type"] == "proposition" and q["id"].startswith("Q-") and q["reponses"] == ["accepte", "refuse", "autre"], fait(r1)
    assert e.p["vente_en_plus_faite"] is True and e.p["mentions_de_remise"] == 1 and J.deja_dit(e.p, "remise:R-DESSERT")
    r2 = await e.tour("non merci", reponse={"question_id": q["id"], "sens": "refuse"})
    r3 = await e.tour("et un gratin", ajouter=[{"article": "gratin dauphinois", "quantite": 1}])
    assert not r2.get("question") and not r3.get("question") and e.p["mentions_de_remise"] == 1, (fait(r2), fait(r3))
