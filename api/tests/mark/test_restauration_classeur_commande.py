"""[.mark] Module Restauration, lot 2 : les commandes dans le classeur (enregistrer, recalculer, refuser, statuts, retrouver).

Jeu d'essai : la carte de référence (pizzeria + burger). Vraie base, rôle ``_ecriture``, heure fixée au jeudi 12 h
(source d'heure de l'organisation).

| Test | Ce qu'il prouve |
|---|---|
| enregistrer | une commande valide : total recalculé depuis la carte (le total et les prix du modèle ignorés), numéro unique, numéro court du jour, heure annoncée, lignes écrites, fiche du client créée, envoi déclenché une fois |
| un manque à la fois | chaque manque est demandé seul, dans l'ordre, avec son nom |
| choix et retraits | choix obligatoire, maximum, supplément chiffré, option inconnue, retrait non permis |
| rupture | une déclinaison ou une option en rupture refuse la commande ; une rupture finie ne bloque plus |
| ouverture | fermé hors horaires, en pause, livraison terminée : refus fermé avec la reprise |
| livraison | zone d'un autre établissement, minimum, frais et gratuité, délai de zone dans l'heure annoncée |
| paiement | moyen non accepté, plafond du titre-restaurant, règlement qui ne couvre pas le total |
| remises | pourcentage et seuil chiffrés chez nous ; inconnue ou non chiffrée refusée ; exclusives non cumulées |
| anti-doublon | même appel + même panier = même numéro, aussi à deux connexions en même temps |
| planifiée | refusée par défaut ; permise : heure voulue gardée ; relevée avec son chiffre d'affaires |
| statuts | chemin fermé, ``DEJA_FAIT``, ``INTERDIT``, tentatives, deux gestes simultanés, journal, cloisonnement |
| retrouver | par numéro, numéro court, téléphone et jour ; jamais celui d'un autre établissement |
"""

from __future__ import annotations

import asyncio
import copy
import json
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import horloge
from api.db.bases_clients.restauration_carte import importer_carte, poser_rupture
from api.db.bases_clients.restauration_commande import (
    TRANSITIONS,
    changer_statut,
    commandes_planifiees,
    enregistrer_commande,
    statut_commande,
)
from api.db.bases_clients.restauration_remise import remises_applicables
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import CARTE, JEUDI_MIDI

PARIS = ZoneInfo("Europe/Paris")
TEL = "+33612345678"


@pytest.fixture
async def commerce(base_prete):
    c = await schema.connecter(base_prete)
    try:
        await c.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ('Entreprise')")
        ids = {}
        for cle in ("a", "b"):
            ids[cle] = await c.fetchval(
                "INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) SELECT id, $1, $1, 'Europe/Paris' FROM mark.entreprise RETURNING id", cle
            )
        a = ids["a"]
        for jour in range(1, 8):
            for ouverture, fermeture in (("11:00", "14:00"), ("18:00", "22:30")):
                await c.execute("INSERT INTO mark.horaire (site_id, jour, ouverture, fermeture) VALUES ($1, $2, $3::text::time, $4::text::time)", a, jour, ouverture, fermeture)
        await c.execute(
            "INSERT INTO mark.resto_reglage (site_id, prefixe_numero_court, moyens_paiement, plafond_titre_restaurant) "
            "VALUES ($1, 'C', '{carte,especes,titre_restaurant}', 2500)", a
        )
        await c.execute("INSERT INTO mark.resto_reglage_type (site_id, type, delai_annonce) VALUES ($1, 'emporter', 20)", a)
        await c.execute("INSERT INTO mark.resto_reglage_type (site_id, type) VALUES ($1, 'livraison')", a)
        zones = {}
        for nom, minimum, frais, gratuite, delai in (("Senlis", 0, 300, 3000, 30), ("Proches", 1500, 0, None, 40)):
            zones[nom] = await c.fetchval(
                "INSERT INTO mark.resto_zone (site_id, nom, forme, communes, minimum, frais, gratuite_des, delai) VALUES ($1, $2, 'communes', '{x}', $3, $4, $5, $6) RETURNING id",
                a, nom, minimum, frais, gratuite, delai,
            )
        zone_b = await c.fetchval("INSERT INTO mark.resto_zone (site_id, nom, forme, communes) VALUES ($1, 'Autre', 'communes', '{y}') RETURNING id", ids["b"])
        with horloge.remplacer(base_prete, JEUDI_MIDI):
            await importer_carte(c, a, CARTE, "caisse")
            # Lot 8 (E17, D49) : le genre et le nom commun d'un produit sont une donnée de la surcouche (écrite par une personne), plus un mot deviné dans le code :
            # la carte de référence les porte ici, comme le ferait le restaurateur (sinon « un Regina », jamais « une Regina »)
            for ref, genre, commun in (("P-PIZZAS-TOMATE-REGINA", "f", False), ("P-PIZZAS-TOMATE-MARGHE", "f", False), ("P-DESSERTS-TIRAMISU", "m", True),
                                       ("P-DESSERTS-MOUSSE-AU-C", "f", True), ("P-BOISSONS-EAU", "f", True)):
                await c.execute(
                    "INSERT INTO mark.resto_surcouche (site_id, objet, ref, genre, nom_commun) VALUES ($1, 'produit', $2, $3, $4) "
                    "ON CONFLICT (site_id, objet, ref) DO UPDATE SET genre = EXCLUDED.genre, nom_commun = EXCLUDED.nom_commun", a, ref, genre, commun,
                )
            yield SimpleNamespace(c=c, a=a, b=ids["b"], base=base_prete, zones=zones, zone_b=zone_b)
    finally:
        await c.close()


def brouillon(**plus) -> dict:
    base = {
        "mode": "emporter",
        "client": {"telephone": TEL, "prenom": "Alice"},
        "lignes": [{"code_caisse": "PIZ-MARGHERITA-NORMALE", "quantite": 2}, {"code_caisse": "BOI-COCA-COLA-33-CL"}],
        "paiement": {"moyens": [{"moyen": "carte", "montant": 2380}]},
        "appel_id": "appel-1",
    }
    return {**copy.deepcopy(base), **plus}


async def enregistrer(commerce, b=None, jeton="relu-1", **options):
    return await enregistrer_commande(commerce.c, commerce.a, b if b is not None else brouillon(), jeton, **options)


# --------------------------------------------------------------------------- #
# enregistrer_commande
# --------------------------------------------------------------------------- #


async def test_une_commande_valide_est_recalculee_enregistree_et_son_envoi_declenche_une_fois(commerce):
    c = commerce.c
    envoyees = []

    async def envoi(numero):
        envoyees.append(numero)

    # le modèle donne un total et des prix faux : ils ne sont jamais pris
    b = brouillon()
    b["total"] = 1
    r = await enregistrer(commerce, b, declencher_envoi=envoi)
    assert r.statut == "ENREGISTREE", r
    assert r.faits["total"] == 2380 and r.faits["numero_court"] == "C1"
    assert r.faits["heure_annoncee"] == JEUDI_MIDI + timedelta(minutes=20)
    assert (r.suggestion, r.faits["mode"], r.faits["quand_dit"]) == ("", "emporter", "dans vingt minutes")  # lot 6 : l'annonce suit le format réglé (durée par défaut) ; C7 B9 : au fait
    assert envoyees == [uuid.UUID(r.faits["numero"])]
    ligne = await c.fetchrow("SELECT * FROM mark.resto_commande WHERE numero = $1", uuid.UUID(r.faits["numero"]))
    assert (ligne["statut"], ligne["mode"], ligne["sous_total"], ligne["frais"], ligne["total"], ligne["telephone"], ligne["cree_par"]) == ("nouvelle", "emporter", 2380, 0, 2380, TEL, "agent")
    lignes = await c.fetch("SELECT * FROM mark.resto_commande_ligne WHERE numero = $1 ORDER BY rang", ligne["numero"])
    assert [(l["code_caisse"], l["prix_unitaire"], l["quantite"]) for l in lignes] == [("PIZ-MARGHERITA-NORMALE", 1090, 2), ("BOI-COCA-COLA-33-CL", 200, 1)]
    client = await c.fetchrow("SELECT * FROM mark.resto_client WHERE site_id = $1 AND telephone = $2", commerce.a, TEL)
    assert (client["prenom"], client["nb_commandes"], client["derniere_commande_id"]) == ("Alice", 1, ligne["numero"])
    # une seconde commande (autre appel) : numéro court suivant, nombre de commandes du client suivant
    r2 = await enregistrer(commerce, brouillon(appel_id="appel-2"))
    assert r2.faits["numero_court"] == "C2" and r2.faits["numero"] != r.faits["numero"]
    assert (await c.fetchval("SELECT nb_commandes FROM mark.resto_client WHERE site_id = $1", commerce.a)) == 2
    # le journal dit la source
    j = await c.fetchrow("SELECT source FROM mark.resto_journal WHERE objet = 'resto_commande' AND operation = 'insert' ORDER BY id DESC LIMIT 1")
    assert j["source"] == "agent"


async def test_chaque_manque_est_demande_seul_dans_l_ordre(commerce):
    async def manque(b, jeton="relu"):
        return await enregistrer(commerce, b, jeton)

    assert (await manque({})).statut == "ARGUMENT_INVALIDE"
    r = await manque({"mode": "livraison"})
    assert (r.statut, r.manque) == ("INCOMPLETE", "lignes")
    r = await manque({"mode": "livraison", "lignes": brouillon()["lignes"]})
    assert r.manque == "telephone"
    r = await manque({"mode": "livraison", "lignes": brouillon()["lignes"], "client": {"telephone": "0612345678"}})
    assert r.manque == "telephone"  # pas du E.164
    plein = brouillon(mode="livraison")
    assert (await manque(plein)).manque == "adresse"
    plein["adresse"] = {"voie": "1 rue X", "commune": "Senlis"}
    assert (await manque(plein)).manque == "zone"
    plein["zone_id"] = commerce.zones["Senlis"]
    assert (await manque(plein, jeton=None)).manque == "relecture"
    assert (await manque(plein, jeton="  ")).manque == "relecture"
    sans_paiement = brouillon()
    del sans_paiement["paiement"]
    r = await manque(sans_paiement)
    assert (r.statut, r.manque) == ("INCOMPLETE", "paiement")
    assert await commerce.c.fetchval("SELECT count(*) FROM mark.resto_commande") == 0  # rien n'est écrit tant que c'est incomplet


async def test_choix_obligatoire_maximum_supplement_et_retraits(commerce):
    burger = {"code_caisse": "BUR-CHE", "quantite": 1}
    paiement = lambda montant: {"moyens": [{"moyen": "carte", "montant": montant}]}  # noqa: E731
    r = await enregistrer(commerce, brouillon(lignes=[burger], paiement=paiement(650)))
    assert (r.statut, r.faits["groupe"]) == ("CHOIX_OBLIGATOIRE", "G-SAUCE")
    avec_sauce = {**burger, "choix": [{"option_code": "SAU-KET"}]}
    r = await enregistrer(commerce, brouillon(lignes=[avec_sauce], paiement=paiement(650)))
    assert r.statut == "ENREGISTREE" and r.faits["total"] == 650
    suppl = {**burger, "choix": [{"option_code": "SAU-KET"}, {"option_code": "SUP-FRO", "quantite": 2}]}
    r = await enregistrer(commerce, brouillon(lignes=[suppl], paiement=paiement(850), appel_id="a-suppl"))
    assert r.statut == "ENREGISTREE" and r.faits["total"] == 850  # 650 + 2 x 100
    trop = {**burger, "choix": [{"option_code": "SAU-KET"}, {"option_code": "SUP-FRO", "quantite": 3}]}
    assert (await enregistrer(commerce, brouillon(lignes=[trop], paiement=paiement(950)))).statut == "MAXIMUM_ATTEINT"
    deux_sauces = {**burger, "choix": [{"option_code": "SAU-KET"}, {"option_code": "SAU-BLA"}]}
    assert (await enregistrer(commerce, brouillon(lignes=[deux_sauces], paiement=paiement(650)))).statut == "MAXIMUM_ATTEINT"
    inconnue = {**burger, "choix": [{"option_code": "SAU-KET"}, {"option_code": "SUP-MOZ"}]}  # un supplément de pizza
    assert (await enregistrer(commerce, brouillon(lignes=[inconnue], paiement=paiement(800)))).statut == "HORS_CARTE"
    assert (await enregistrer(commerce, brouillon(lignes=[{"code_caisse": "N-IMPORTE-QUOI"}], paiement=paiement(1)))).statut == "HORS_CARTE"
    retrait = {**avec_sauce, "retires": ["steak"]}  # le steak n'est pas retirable
    assert (await enregistrer(commerce, brouillon(lignes=[retrait], paiement=paiement(650)))).statut == "HORS_CARTE"
    sans_oignons = {**avec_sauce, "retires": ["oignons"]}  # les oignons le sont : gardés sur la ligne
    r = await enregistrer(commerce, brouillon(lignes=[sans_oignons], paiement=paiement(650), appel_id="oignons"))
    assert r.statut == "ENREGISTREE"
    assert list(await commerce.c.fetchval("SELECT retires FROM mark.resto_commande_ligne WHERE numero = $1", uuid.UUID(r.faits["numero"]))) == ["oignons"]
    assert (await enregistrer(commerce, brouillon(lignes=[{**burger, "quantite": 0}], paiement=paiement(0)))).statut == "ARGUMENT_INVALIDE"


async def test_une_rupture_refuse_la_commande_et_une_rupture_finie_ne_bloque_plus(commerce):
    code = "PIZ-MARGHERITA-NORMALE"
    await poser_rupture(commerce.c, commerce.a, code, False, JEUDI_MIDI + timedelta(hours=1), "caisse")
    r = await enregistrer(commerce)
    assert (r.statut, r.faits["code"]) == ("RUPTURE", code)
    await poser_rupture(commerce.c, commerce.a, "SAU-KET", False, None, "portail")
    burger = {"code_caisse": "BUR-CHE", "choix": [{"option_code": "SAU-KET"}]}
    assert (await enregistrer(commerce, brouillon(lignes=[burger], paiement={"moyens": [{"moyen": "carte", "montant": 650}]}))).statut == "RUPTURE"
    # le soir (la rupture de la pizza finit à 13 h), la même pizza passe : une rupture d'un autre moment ne bloque pas
    await commerce.c.execute("UPDATE mark.resto_reglage_type SET planifiee_permise = true, jours_a_l_avance = 3 WHERE site_id = $1 AND type = 'emporter'", commerce.a)
    soir = JEUDI_MIDI.replace(hour=19)
    r = await enregistrer(commerce, brouillon(heure_voulue=soir))
    assert r.statut == "ENREGISTREE" and r.faits["heure_annoncee"] == soir


async def test_ferme_en_pause_ou_livraison_terminee_avec_la_reprise(commerce):
    c, a = commerce.c, commerce.a
    with horloge.remplacer(commerce.base, JEUDI_MIDI.replace(hour=16)):
        r = await enregistrer(commerce)
        assert (r.statut, r.faits["raison"]) == ("FERME", "ferme_horaires")
        assert r.faits["prochaine_ouverture"] == JEUDI_MIDI.replace(hour=18)
    await c.execute("UPDATE mark.resto_reglage_type SET pause_jusqu_a = $2 WHERE site_id = $1 AND type = 'emporter'", a, JEUDI_MIDI + timedelta(minutes=30))
    r = await enregistrer(commerce)
    assert (r.statut, r.faits["raison"], r.faits["reprise"]) == ("PAUSE_TYPE", "pause_type", JEUDI_MIDI + timedelta(minutes=30))
    await c.execute("UPDATE mark.resto_reglage_type SET fin_par_jour = '{\"4\": \"11:30\"}' WHERE site_id = $1 AND type = 'livraison'", a)
    b = brouillon(mode="livraison", adresse={"commune": "Senlis"}, zone_id=commerce.zones["Senlis"])
    assert (await enregistrer(commerce, b)).statut == "LIVRAISON_TERMINEE"
    assert await c.fetchval("SELECT count(*) FROM mark.resto_commande") == 0


async def test_livraison_zone_minimum_frais_et_delai(commerce):
    c = commerce.c
    paiement = lambda m: {"moyens": [{"moyen": "carte", "montant": m}]}  # noqa: E731
    base = brouillon(mode="livraison", adresse={"commune": "Senlis"}, zone_id=commerce.zone_b)
    assert (await enregistrer(commerce, base)).statut == "HORS_ZONE"  # la zone d'un AUTRE établissement
    assert (await enregistrer(commerce, {**base, "zone_id": 999999})).statut == "HORS_ZONE"
    petit = {**base, "zone_id": commerce.zones["Proches"], "lignes": [{"code_caisse": "BOI-COCA-COLA-33-CL"}], "paiement": paiement(200)}
    r = await enregistrer(commerce, petit)
    assert (r.statut, r.faits["minimum"]) == ("MINIMUM_NON_ATTEINT", 1500)
    # Senlis : minimum 0, frais 3 euros, gratuits dès 30 euros ; 23,80 + 3,00 = 26,80
    r = await enregistrer(commerce, {**base, "zone_id": commerce.zones["Senlis"], "paiement": paiement(2680)})
    assert r.statut == "ENREGISTREE" and r.faits["total"] == 2680
    assert r.faits["heure_annoncee"] == JEUDI_MIDI + timedelta(minutes=30)  # le délai de la ZONE
    ligne = await c.fetchrow("SELECT frais, zone_id FROM mark.resto_commande WHERE numero = $1", uuid.UUID(r.faits["numero"]))
    assert (ligne["frais"], ligne["zone_id"]) == (300, commerce.zones["Senlis"])
    gros = {**base, "zone_id": commerce.zones["Senlis"], "appel_id": "gros", "paiement": paiement(3670),
            "lignes": [{"code_caisse": "PIZ-MARGHERITA-NORMALE", "quantite": 3}, {"code_caisse": "BOI-COCA-COLA-33-CL"}, {"code_caisse": "BOI-COCA-COLA-33-CL"}]}
    r = await enregistrer(commerce, gros)  # 32,70 + 4,00 = 36,70 : au-dessus de 30 euros, frais offerts
    assert (r.statut, r.faits["total"]) == ("ENREGISTREE", 3670), r


async def test_paiement_moyen_plafond_et_compte(commerce):
    paiement = lambda *moyens, **plus: {"moyens": [{"moyen": m, "montant": v} for m, v in moyens], **plus}  # noqa: E731
    r = await enregistrer(commerce, brouillon(paiement=paiement(("cheque", 2380))))
    assert (r.statut, r.faits["moyen"]) == ("MOYEN_NON_ACCEPTE", "cheque")
    assert (await enregistrer(commerce, brouillon(paiement=paiement(("titre_restaurant", 2380))))).statut == "ENREGISTREE"  # 23,80 < 25 : permis
    r = await enregistrer(commerce, brouillon(paiement=paiement(("carte", 1000)), appel_id="x"))
    assert (r.statut, r.manque) == ("INCOMPLETE", "paiement")
    mixte = brouillon(paiement=paiement(("titre_restaurant", 2300), ("carte", 81)), appel_id="mixte")
    assert (await enregistrer(commerce, mixte)).manque == "paiement"  # 2381 != 2380
    plafond = brouillon(lignes=[{"code_caisse": "PIZ-MARGHERITA-NORMALE", "quantite": 4}], paiement=paiement(("titre_restaurant", 4360)), appel_id="p")
    r = await enregistrer(commerce, plafond)
    assert (r.statut, r.faits["plafond"], r.faits["montant"]) == ("PLAFOND_TITRE_RESTAURANT", 2500, 4360)
    # règlement partagé entre une partie payée et un reste à régler au retrait
    reparti = brouillon(paiement=paiement(("carte", 1000), reste_par_moyen={"especes": 1380}), appel_id="r")
    assert (await enregistrer(commerce, reparti)).statut == "ENREGISTREE"


async def test_remises_chiffrees_chez_nous_refusees_si_inconnues_ou_non_chiffrees(commerce):
    c, a = commerce.c, commerce.a
    await c.execute("INSERT INTO mark.resto_remise (site_id, ref, nom, mecanisme, effet, etat, ref_caisse) VALUES ($1, 'DIX', 'Dix pour cent', 'pourcentage', '{\"pourcentage\": 10}', 'active', 'HR-1')", a)
    await c.execute("INSERT INTO mark.resto_remise (site_id, ref, nom, mecanisme, declencheur, effet, etat) VALUES ($1, 'SEUIL', 'Cinq euros', 'seuil_panier', '{\"minimum\": 5000}', '{\"montant\": 500}', 'active')", a)
    await c.execute("INSERT INTO mark.resto_remise (site_id, ref, nom, mecanisme, effet, etat, cumul) VALUES ($1, 'FIDE', 'Fidélité', 'fidelite', '{}', 'active', 'cumulable')", a)
    await c.execute("INSERT INTO mark.resto_remise (site_id, ref, nom, mecanisme, effet, etat) VALUES ($1, 'BROUILLON', 'Pas prête', 'montant', '{\"montant\": 100}', 'brouillon')", a)
    liste = await remises_applicables(c, a, {"mode": "emporter", "sous_total": 2380}, JEUDI_MIDI)
    par_ref = {r["ref"]: r for r in liste}
    assert set(par_ref) == {"DIX", "SEUIL", "FIDE"}  # le brouillon n'en fait pas partie
    assert par_ref["DIX"]["montant"] == 238 and par_ref["DIX"]["chiffree"]
    assert par_ref["SEUIL"]["montant"] is None  # sous le seuil
    assert par_ref["FIDE"]["chiffree"] is True and par_ref["FIDE"]["montant"] is None  # lot 7 : les douze sont chiffrés ; sans client reconnu, la fidélité ne s applique pas
    assert [r["ref"] for r in await remises_applicables(c, commerce.b, {"mode": "emporter", "sous_total": 2380}, JEUDI_MIDI)] == []  # l'autre établissement
    # la commande : 23,80 - 2,38 = 21,42 ; la ligne de remise garde nom, montant, référence de caisse
    r = await enregistrer(commerce, brouillon(remises=[{"ref": "DIX"}], paiement={"moyens": [{"moyen": "carte", "montant": 2142}]}))
    assert (r.statut, r.faits["total"]) == ("ENREGISTREE", 2142), r
    ligne = await c.fetchrow("SELECT remises, sous_total FROM mark.resto_commande WHERE numero = $1", uuid.UUID(r.faits["numero"]))
    assert json.loads(ligne["remises"]) == [{"nom": "Dix pour cent", "montant": 238, "ref_caisse": "HR-1", "taux_tva": 10000}] and ligne["sous_total"] == 2380
    # le montant donné par le modèle est ignoré
    r = await enregistrer(commerce, brouillon(remises=[{"ref": "DIX", "montant": 2000}], appel_id="m", paiement={"moyens": [{"moyen": "carte", "montant": 2142}]}))
    assert r.faits["total"] == 2142
    for refusee, raison in (({"ref": "INCONNUE"}, "remise_inconnue"), ({"ref": "FIDE"}, "remise_inconnue"), ({"ref": "SEUIL"}, "remise_inconnue"), ({"ref": "BROUILLON"}, "remise_inconnue")):
        r = await enregistrer(commerce, brouillon(remises=[refusee], appel_id="z"))
        assert (r.statut, r.faits["raison"]) == ("REFUSEE", raison), refusee
    await c.execute("INSERT INTO mark.resto_remise (site_id, ref, nom, mecanisme, effet, etat) VALUES ($1, 'CINQ', 'Cinq pour cent', 'pourcentage', '{\"pourcentage\": 5}', 'active')", a)
    r = await enregistrer(commerce, brouillon(remises=[{"ref": "DIX"}, {"ref": "CINQ"}], appel_id="deux"))
    assert (r.statut, r.faits["raison"]) == ("REFUSEE", "autre")  # deux exclusives ne se cumulent pas


async def test_meme_appel_meme_panier_meme_numero_meme_a_deux_connexions(commerce):
    r1 = await enregistrer(commerce)
    r2 = await enregistrer(commerce)
    assert (r1.statut, r2.statut) == ("ENREGISTREE", "DEJA_FAIT") and r1.faits["numero"] == r2.faits["numero"]
    assert r2.faits["numero_court"] == r1.faits["numero_court"]
    assert await commerce.c.fetchval("SELECT count(*) FROM mark.resto_commande") == 1
    # un autre panier du même appel est une autre commande
    autre = brouillon(lignes=[{"code_caisse": "BOI-COCA-COLA-33-CL"}], paiement={"moyens": [{"moyen": "carte", "montant": 200}]})
    assert (await enregistrer(commerce, autre)).statut == "ENREGISTREE"
    # deux connexions, en même temps, le même panier du même appel
    c2 = await schema.connecter(commerce.base)
    try:
        neuf = brouillon(appel_id="appel-course")
        rs = await asyncio.gather(
            enregistrer_commande(commerce.c, commerce.a, neuf, "j"), enregistrer_commande(c2, commerce.a, copy.deepcopy(neuf), "j")
        )
    finally:
        await c2.close()
    assert sorted(r.statut for r in rs) == ["DEJA_FAIT", "ENREGISTREE"]
    assert rs[0].faits["numero"] == rs[1].faits["numero"]
    assert await commerce.c.fetchval("SELECT count(*) FROM mark.resto_commande WHERE appel_id = 'appel-course'") == 1
    # le compteur du jour n'a pas sauté un numéro : 1, 2, 3 (la course n'a consommé qu'un numéro)
    assert sorted(await commerce.c.fetchval("SELECT array_agg(numero_court) FROM mark.resto_commande")) == ["C1", "C2", "C3"]
    # sans appel : le client, le mode, l'heure et le panier suffisent
    sans_appel = brouillon()
    del sans_appel["appel_id"]
    assert (await enregistrer(commerce, sans_appel)).statut == "ENREGISTREE"
    assert (await enregistrer(commerce, sans_appel)).statut == "DEJA_FAIT"


async def test_commande_planifiee_refusee_par_defaut_puis_permise_et_relevee(commerce):
    demain = JEUDI_MIDI + timedelta(days=1)
    r = await enregistrer(commerce, brouillon(heure_voulue=demain))
    assert (r.statut, r.manque) == ("ARGUMENT_INVALIDE", "heure_voulue")  # éteint par défaut
    c, a = commerce.c, commerce.a
    await c.execute("UPDATE mark.resto_reglage_type SET planifiee_permise = true, jours_a_l_avance = 2, delai_minimal = 60 WHERE site_id = $1 AND type = 'emporter'", a)
    r = await enregistrer(commerce, brouillon(heure_voulue=demain))
    assert r.statut == "ENREGISTREE" and r.faits["heure_annoncee"] == demain
    assert (await enregistrer(commerce, brouillon(heure_voulue=JEUDI_MIDI + timedelta(days=5), appel_id="loin"))).manque == "heure_voulue"
    assert (await enregistrer(commerce, brouillon(heure_voulue=JEUDI_MIDI + timedelta(minutes=30), appel_id="tot"))).manque == "heure_voulue"
    assert (await enregistrer(commerce, brouillon(heure_voulue=JEUDI_MIDI - timedelta(hours=1), appel_id="passe"))).manque == "heure_voulue"
    assert (await enregistrer(commerce, brouillon(heure_voulue=demain.replace(tzinfo=None), appel_id="naif"))).manque == "heure_voulue"
    # une planifiée tombant hors horaires est refusée : fermé à 16 h demain
    ferme = await enregistrer(commerce, brouillon(heure_voulue=demain.replace(hour=16), appel_id="ferme"))
    assert ferme.statut == "FERME"
    releve = await commandes_planifiees(c, a, demain.replace(hour=0), demain.replace(hour=23))
    assert (releve["nombre"], releve["chiffre_affaires"]) == (1, 2380)
    assert (await commandes_planifiees(c, commerce.b, demain.replace(hour=0), demain.replace(hour=23)))["nombre"] == 0
    await changer_statut(c, a, r.faits["numero"], "nouvelle", "annulee", "portail")
    assert (await commandes_planifiees(c, a, demain.replace(hour=0), demain.replace(hour=23)))["nombre"] == 0  # annulée : plus à venir
    with pytest.raises(ValueError):
        await commandes_planifiees(c, a, demain.replace(tzinfo=None), demain)


async def test_les_jours_a_l_avance_comptent_en_jours_du_lieu_et_le_refus_dit_jusqu_a_quand(commerce):
    """M91 (appel 2577) : « J+1 » = jusqu'à la fin de demain, jamais 24 heures glissantes ; le refus porte la limite (fait ``jusqu_a``, que le modèle dit : lot 7b-C7, A3)."""
    c, a = commerce.c, commerce.a
    await c.execute("UPDATE mark.resto_reglage_type SET planifiee_permise = true, jours_a_l_avance = 1, delai_minimal = 30 WHERE site_id = $1 AND type = 'emporter'", a)
    demain_soir = (JEUDI_MIDI + timedelta(days=1)).replace(hour=19, minute=30)          # plus de 24 heures après midi, mais demain
    r = await enregistrer(commerce, brouillon(heure_voulue=demain_soir, appel_id="demain-soir"))
    assert r.statut == "ENREGISTREE", r
    loin = await enregistrer(commerce, brouillon(heure_voulue=demain_soir + timedelta(days=1), appel_id="apres-demain"))
    assert (loin.manque, loin.suggestion, loin.faits) == ("heure_voulue", "", {"jusqu_a": "vendredi treize novembre"}), loin


# --------------------------------------------------------------------------- #
# Statuts et retrouver
# --------------------------------------------------------------------------- #


async def _une_commande(commerce, b=None, **plus):
    r = await enregistrer(commerce, b, **plus)
    assert r.statut == "ENREGISTREE", r
    return r.faits["numero"]


async def test_le_chemin_des_statuts_est_ferme_et_le_second_geste_ne_change_rien(commerce):
    c, a = commerce.c, commerce.a
    numero = await _une_commande(commerce)
    assert (await changer_statut(c, a, numero, "nouvelle", "envoyee", "agent")).statut == "OK"
    assert await c.fetchval("SELECT tentatives FROM mark.resto_commande WHERE numero = $1", uuid.UUID(numero)) == 1
    # le même geste rejoué : DEJA_FAIT, jamais d'écrasement
    deja = await changer_statut(c, a, numero, "nouvelle", "envoyee", "agent")
    assert deja.statut == "DEJA_FAIT" and deja.faits["statut_actuel"] == "envoyee"
    assert await c.fetchval("SELECT tentatives FROM mark.resto_commande WHERE numero = $1", uuid.UUID(numero)) == 1
    # un départ qui n'est pas le statut actuel : INTERDIT
    assert (await changer_statut(c, a, numero, "recue", "acceptee", "caisse")).statut == "INTERDIT"
    # une prise sans étape « reçue » : on saute vers l'avant, jamais en arrière
    assert (await changer_statut(c, a, numero, "envoyee", "acceptee", "caisse")).statut == "OK"
    assert (await changer_statut(c, a, numero, "acceptee", "recue", "caisse")).statut == "INTERDIT"
    for de, vers in (("acceptee", "en_preparation"), ("en_preparation", "prete"), ("prete", "terminee")):
        assert (await changer_statut(c, a, numero, de, vers, "portail")).statut == "OK"
    # terminée : plus rien n'en sort
    for vers in ("annulee", "refusee", "echec", "prete"):
        assert (await changer_statut(c, a, numero, "terminee", vers, "portail")).statut == "INTERDIT", vers
    assert await c.fetchval("SELECT statut FROM mark.resto_commande WHERE numero = $1", uuid.UUID(numero)) == "terminee"
    # le journal garde chaque pas, avec sa source
    pas = await c.fetch("SELECT apres, source FROM mark.resto_journal WHERE objet = 'resto_commande' AND operation = 'update' AND ligne_id = $1 ORDER BY id", numero)
    assert [(json.loads(p["apres"])["statut"], p["source"]) for p in pas] == [
        ("envoyee", "agent"), ("acceptee", "caisse"), ("en_preparation", "portail"), ("prete", "portail"), ("terminee", "portail")]
    # annulée : définitive ; échec : seul le renvoi en sort, et il compte une tentative
    n2 = await _une_commande(commerce, brouillon(appel_id="deux"))
    assert (await changer_statut(c, a, n2, "nouvelle", "echec", "agent")).statut == "OK"
    assert (await changer_statut(c, a, n2, "echec", "envoyee", "agent")).statut == "OK"
    assert await c.fetchval("SELECT tentatives FROM mark.resto_commande WHERE numero = $1", uuid.UUID(n2)) == 1
    assert (await changer_statut(c, a, n2, "envoyee", "annulee", "portail")).statut == "OK"
    assert (await changer_statut(c, a, n2, "annulee", "envoyee", "portail")).statut == "INTERDIT"
    assert (await changer_statut(c, a, n2, "envoyee", "annulee", "portail")).statut == "DEJA_FAIT"
    # arguments
    assert (await changer_statut(c, a, n2, "nouvelle", "n-importe-quoi", "agent")).statut == "ARGUMENT_INVALIDE"
    assert (await changer_statut(c, a, n2, "nouvelle", "envoyee", "inconnue")).statut == "ARGUMENT_INVALIDE"
    assert (await changer_statut(c, a, "pas-un-uuid", "nouvelle", "envoyee", "agent")).statut == "ARGUMENT_INVALIDE"
    # la table des transitions ne contient aucun retour en arrière
    ordre = ["retenue", "nouvelle", "envoyee", "recue", "acceptee", "en_preparation", "prete", "terminee"]  # § 17 : « retenue » (écrite au oui) précède l'envoi
    for de, permis in TRANSITIONS.items():
        for vers in permis & set(ordre):
            assert de == "echec" or ordre.index(vers) > ordre.index(de), (de, vers)


async def test_deux_gestes_simultanes_un_seul_passe_et_une_commande_d_un_autre_etablissement_est_introuvable(commerce):
    c, a = commerce.c, commerce.a
    numero = await _une_commande(commerce)
    c2 = await schema.connecter(commerce.base)
    try:
        rs = await asyncio.gather(
            changer_statut(c, a, numero, "nouvelle", "envoyee", "agent"), changer_statut(c2, a, numero, "nouvelle", "envoyee", "caisse")
        )
    finally:
        await c2.close()
    assert sorted(r.statut for r in rs) == ["DEJA_FAIT", "OK"]
    assert await c.fetchval("SELECT tentatives FROM mark.resto_commande WHERE numero = $1", uuid.UUID(numero)) == 1
    # cloisonnement : B ne change ni ne retrouve la commande de A
    assert (await changer_statut(c, commerce.b, numero, "envoyee", "recue", "caisse")).statut == "INTROUVABLE"
    assert (await changer_statut(c, commerce.b, numero, "nouvelle", "annulee", "caisse")).statut == "INTROUVABLE"
    assert (await statut_commande(c, commerce.b, numero=numero)).statut == "INTROUVABLE"
    assert (await statut_commande(c, commerce.b, telephone=TEL)).statut == "INTROUVABLE"
    assert await c.fetchval("SELECT statut FROM mark.resto_commande WHERE numero = $1", uuid.UUID(numero)) == "envoyee"


async def test_retrouver_une_commande_par_numero_numero_court_telephone_et_jour(commerce):
    c, a = commerce.c, commerce.a
    numero = await _une_commande(commerce)
    for cherche in ({"numero": numero}, {"numero": "C1"}, {"telephone": TEL}, {"telephone": TEL, "jour": JEUDI_MIDI.date()}):
        r = await statut_commande(c, a, **cherche)
        assert r.statut == "OK" and r.faits["commandes"][0]["numero"] == numero, cherche
        assert r.faits["commandes"][0]["statut"] == "nouvelle" and r.faits["commandes"][0]["total"] == 2380
    veille = (JEUDI_MIDI - timedelta(days=1)).date()
    assert (await statut_commande(c, a, telephone=TEL, jour=veille)).statut == "INTROUVABLE"
    assert (await statut_commande(c, a, numero="C99")).statut == "INTROUVABLE"
    assert (await statut_commande(c, a, numero=str(uuid.uuid4()))).statut == "INTROUVABLE"
    assert (await statut_commande(c, a)).statut == "ARGUMENT_INVALIDE"
    assert (await statut_commande(c, a, telephone="+33699999999")).statut == "INTROUVABLE"
    # deux commandes du même client le même jour : les plus récentes d'abord
    with horloge.remplacer(commerce.base, JEUDI_MIDI + timedelta(minutes=5)):
        n2 = await _une_commande(commerce, brouillon(appel_id="plus-tard"))
    r = await statut_commande(c, a, telephone=TEL)
    assert [x["numero"] for x in r.faits["commandes"]] == [n2, numero]
