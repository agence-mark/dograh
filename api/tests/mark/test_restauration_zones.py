"""[.mark] Module Restauration, lot 6, étape 3 : les zones (communes, rayon, exclues) et la vérification d'une adresse dite.

| Test | Ce qu'il prouve |
|---|---|
| mécanisme pur | communes autour d'un point par distance ; zone par liste ou par rayon ; exclues ; la première zone dans l'ordre gagne ; sans coordonnées jamais « dans le rayon » |
| verdict | une seule commune sûre = RETENU ou HORS_ZONE ; à confirmer ou deux communes = AMBIGU sans zone ; aucune = INTROUVABLE |
| par la base | ``verifier_adresse`` lit les zones de CET établissement seulement ; sans zone réglée, hors zone ; texte vide refusé |
| banc de dictées | zéro faux sûr : une dictée n'est jamais « retenue » dans une zone qui n'est pas la sienne |
| vocabulaire | aucun mot de restaurant dans le mécanisme commun |
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from api.db.bases_clients import zones_de_service as zs
from api.db.bases_clients.restauration_zone import centre_de_l_etablissement, communes_autour_de_l_etablissement, verifier_adresse
from api.services.communes.analyse import A_CONFIRMER, SURE
from api.services.communes.base import charger_base
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401

SENLIS, CHANTILLY, BEAUVAIS = "60612", "60141", "60057"


@pytest.fixture(scope="module")
def base_communes():
    return charger_base()


@pytest.fixture(scope="module")
def centre(base_communes):
    return base_communes.coordonnees(SENLIS)


def _zone(id_, forme="rayon", *, communes=(), rayon=None, exclues=(), ordre=0):
    return zs.Zone(id_, f"Z{id_}", forme, tuple(communes), rayon, tuple(exclues), ordre)


# --------------------------------------------------------------------------- #
# Mécanisme pur
# --------------------------------------------------------------------------- #


def test_les_communes_autour_d_un_point_sont_triees_par_distance_et_bornees(base_communes, centre):
    proches = zs.communes_autour(base_communes, *centre, 8)
    assert proches[0].insee == SENLIS and len(proches) > 5
    noms_10 = {c.insee for c in zs.communes_autour(base_communes, *centre, 12)}
    assert {c.insee for c in proches} <= noms_10 and CHANTILLY in noms_10
    assert BEAUVAIS not in {c.insee for c in zs.communes_autour(base_communes, *centre, 20)}  # Beauvais est bien plus loin
    assert zs.communes_autour(base_communes, *centre, 0.01)[0].insee == SENLIS


def test_une_zone_par_liste_ou_par_rayon_et_les_exclues_gagnent(base_communes, centre):
    senlis, chantilly, beauvais = (base_communes.commune(i) for i in (SENLIS, CHANTILLY, BEAUVAIS))
    liste = _zone(1, "communes", communes=[SENLIS])
    assert zs.commune_dans_la_zone(liste, senlis, centre) and not zs.commune_dans_la_zone(liste, chantilly, centre)
    rayon = _zone(2, rayon=12.0)
    assert zs.commune_dans_la_zone(rayon, senlis, centre) and zs.commune_dans_la_zone(rayon, chantilly, centre)
    assert not zs.commune_dans_la_zone(rayon, beauvais, centre)
    assert not zs.commune_dans_la_zone(_zone(3, rayon=12.0, exclues=[CHANTILLY]), chantilly, centre)  # exclue : jamais dedans
    assert not zs.commune_dans_la_zone(_zone(4, "communes", communes=[SENLIS], exclues=[SENLIS]), senlis, centre)


def test_sans_centre_ou_sans_coordonnees_jamais_dans_le_rayon(base_communes, centre):
    senlis = base_communes.commune(SENLIS)
    assert not zs.commune_dans_la_zone(_zone(1, rayon=50.0), senlis, None)  # centre inconnu
    sans_coord = zs.Commune("99999", "Nulle part", ("99999",), 1, "99", None, None)
    assert not zs.commune_dans_la_zone(_zone(1, rayon=5000.0), sans_coord, centre)


def test_la_premiere_zone_dans_l_ordre_gagne(base_communes, centre):
    chantilly = base_communes.commune(CHANTILLY)
    large = _zone(1, rayon=30.0, ordre=2)
    precise = _zone(2, "communes", communes=[CHANTILLY], ordre=1)
    assert zs.zone_de_la_commune([large, precise], chantilly, centre).id == 2
    assert zs.zone_de_la_commune([large], base_communes.commune(BEAUVAIS), centre) is None  # Beauvais est hors des 30 km
    assert zs.zone_de_la_commune([], chantilly, centre) is None


class _Lecture:
    def __init__(self, commune):
        self.commune = commune


class _Detection:
    def __init__(self, statut, communes):
        self.statut, self.lectures = statut, tuple(_Lecture(c) for c in communes)


def test_le_verdict_ne_donne_une_zone_que_pour_une_seule_commune_sure(base_communes, centre):
    s, c, b = (base_communes.commune(i) for i in (SENLIS, CHANTILLY, BEAUVAIS))
    zones = [_zone(1, "communes", communes=[SENLIS])]
    assert zs.verdict_de_l_adresse(zones, [], centre, SURE).statut == zs.INTROUVABLE
    ok = zs.verdict_de_l_adresse(zones, [_Detection(SURE, [s])], centre, SURE)
    assert (ok.statut, ok.zone.id, ok.commune.insee) == (zs.RETENU, 1, SENLIS)
    assert zs.verdict_de_l_adresse(zones, [_Detection(SURE, [c])], centre, SURE).statut == zs.HORS_ZONE
    flou = zs.verdict_de_l_adresse(zones, [_Detection(A_CONFIRMER, [s, c])], centre, SURE)
    assert flou.statut == zs.AMBIGU and flou.zone is None and [x.zone is not None for x in flou.candidats] == [True, False]
    deux = zs.verdict_de_l_adresse(zones, [_Detection(SURE, [s]), _Detection(SURE, [b])], centre, SURE)
    assert deux.statut == zs.AMBIGU and deux.zone is None  # deux communes entendues : on ne choisit pas


# --------------------------------------------------------------------------- #
# Par la base
# --------------------------------------------------------------------------- #


async def _regler(commerce_):  # noqa: F811
    c, a = commerce_.c, commerce_.a
    await c.execute("UPDATE mark.site SET adresse_insee = $2 WHERE id = $1", a, SENLIS)
    await c.execute("DELETE FROM mark.resto_zone WHERE site_id = $1", a)
    ids = {}
    for nom, forme, communes, rayon, exclues, ordre in (
        ("Chantilly", "communes", [CHANTILLY], None, [], 0),
        ("Centre", "rayon", [], 8, [], 1),
    ):
        ids[nom] = await c.fetchval(
            "INSERT INTO mark.resto_zone (site_id, nom, forme, communes, rayon_km, exclues, frais, delai, ordre) VALUES ($1,$2,$3,$4,$5,$6,200,30,$7) RETURNING id",
            a, nom, forme, communes, rayon, exclues, ordre,
        )
    return ids


async def test_l_adresse_dite_donne_la_zone_de_l_etablissement(commerce):  # noqa: F811
    ids = await _regler(commerce)
    r = await verifier_adresse(commerce.c, commerce.a, "12 rue de la République à Senlis")
    assert (r.statut, r.faits["zone"]["id"], r.faits["zone"]["delai"], r.faits["commune"]["insee"]) == ("RETENU", ids["Centre"], 30, SENLIS)
    r = await verifier_adresse(commerce.c, commerce.a, "je suis à Chantilly")
    assert (r.statut, r.faits["zone"]["id"]) == ("RETENU", ids["Chantilly"])  # l'ordre : la zone nommée avant le rayon
    r = await verifier_adresse(commerce.c, commerce.a, "7 rue Victor Hugo, Compiègne")
    assert r.statut == "HORS_ZONE" and r.faits["commune"]["nom"] == "Compiègne" and r.suggestion == ""
    assert (await verifier_adresse(commerce.c, commerce.a, "rue de Paris")).statut == "INTROUVABLE"
    assert (await verifier_adresse(commerce.c, commerce.a, "  ")).statut == "ARGUMENT_INVALIDE"


async def test_les_zones_d_un_autre_etablissement_ne_servent_jamais(commerce):  # noqa: F811
    await _regler(commerce)
    # l'autre établissement n'a qu'une zone sans lien avec Senlis (et pas de centre) : jamais une zone de l'établissement A
    r = await verifier_adresse(commerce.c, commerce.b, "12 rue de la République à Senlis")
    assert r.statut in {"HORS_ZONE", "AMBIGU"} and "zone" not in r.faits
    r = await verifier_adresse(commerce.c, commerce.a, "12 rue de la République à Senlis")
    assert r.statut == "RETENU"
    await commerce.c.execute("DELETE FROM mark.resto_zone WHERE site_id = $1", commerce.a)
    assert (await verifier_adresse(commerce.c, commerce.a, "12 rue de la République à Senlis")).faits == {"raison": "aucune_zone"}


async def test_les_communes_autour_de_l_etablissement_pour_regler_une_zone(commerce):  # noqa: F811
    await _regler(commerce)
    proches = await communes_autour_de_l_etablissement(commerce.c, commerce.a, 5)
    assert proches[0]["insee"] == SENLIS and all(set(p) == {"insee", "nom", "code_postal"} for p in proches)
    assert await communes_autour_de_l_etablissement(commerce.c, commerce.b, 5) == []  # sans commune connue : rien, pas d'erreur
    assert await centre_de_l_etablissement(commerce.c, commerce.b, charger_base()) is None


# --------------------------------------------------------------------------- #
# Banc de dictées : zéro faux sûr
# --------------------------------------------------------------------------- #

# (dictée, ce qui est permis) : « retenu:<insee> » = seul RETENU permis, avec cette commune ; « jamais_retenu » = RETENU interdit.
BANC = [
    ("12 rue de la République à Senlis", "retenu:" + SENLIS),
    ("Senlis", "retenu:" + SENLIS),
    ("12 rue de la gare Sanlis", "retenu:" + SENLIS),
    ("60300 Senlis", "retenu:" + SENLIS),
    ("je suis à Chantilly", "retenu:" + CHANTILLY),
    ("3 avenue de Creil à Senlis", "retenu:" + SENLIS),  # la rue porte un nom de commune : la commune est Senlis
    ("l'adresse c'est 12 rue des lilas", "jamais_retenu"),  # aucune commune dite
    ("rue de Paris", "jamais_retenu"),
    ("le 5 rue du Moulin", "jamais_retenu"),
    ("Boves", "jamais_retenu"),  # à confirmer
    ("Compiègne", "jamais_retenu"),  # hors zone
    ("Beauvais", "jamais_retenu"),
    ("Paris", "jamais_retenu"),
    ("chez moi", "jamais_retenu"),
    ("quarante-deux", "jamais_retenu"),
]


async def test_banc_de_dictees_zero_faux_sur(commerce):  # noqa: F811
    await _regler(commerce)
    faux = []
    for dictee, permis in BANC:
        r = await verifier_adresse(commerce.c, commerce.a, dictee)
        if r.statut == "RETENU":
            if permis != f"retenu:{r.faits['commune']['insee']}":
                faux.append((dictee, r.faits["commune"]["nom"]))
        elif permis.startswith("retenu:"):
            assert r.statut in {"AMBIGU", "INTROUVABLE"}, (dictee, r.statut)  # un doute se confirme, jamais un faux « hors zone » sûr
    assert faux == [], f"faux sûrs : {faux}"
    assert sum(1 for _d, p in BANC if p.startswith("retenu:")) >= 5


# --------------------------------------------------------------------------- #
# Vocabulaire
# --------------------------------------------------------------------------- #


def test_aucun_mot_de_restaurant_dans_le_mecanisme_des_zones():
    from api.tests.mark.test_restauration_contrat_classeur import MECANISMES_COMMUNS, MOTS_INTERDITS, RACINE

    assert "db/bases_clients/zones_de_service.py" in MECANISMES_COMMUNS
    corps = (RACINE / "db/bases_clients/zones_de_service.py").read_text(encoding="utf-8")
    assert {m.group(0).lower() for m in MOTS_INTERDITS.finditer(corps)} <= {"restaura"}


_ = (re, Path)
