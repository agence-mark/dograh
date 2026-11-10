"""[.mark] Revue des correctifs d'écran : la borne de taille d'un envoi, et les fichiers en trop du logo.

| Test | Ce qu'il prouve |
|---|---|
| logo annoncé à 5 Mo | 413 `envoi_trop_lourd`, la route n'est jamais appelée |
| logo découpé (chunked) trop gros | 413 aussi, sans Content-Length annoncé |
| logo à la borne | la borne le laisse passer, la route le range |
| un document de 14 Mo | la borne du dépôt laisse passer ce que la route accepte (15 Mo) ; 16 Mo : 413 |
| inventaire | toute route qui déclare un `UploadFile` a une borne dans le tableau |
| deux poses simultanées | un seul fichier reste, celui que la référence désigne |
| pose dépassée par un autre processus | notre fichier est effacé |
| délai de lecture dépassé | aucun fichier temporaire ne reste quand la tâche de fond finit |
"""

import asyncio
import os
import re
import time

import pytest
from fastapi.routing import APIRoute

from api.app import app
from api.services.equipe_mark import borne_envoi, logo_espace
from api.services.equipe_mark.image_logo import OCTETS_MAX
from api.tests.mark.equipe_commun import (
    client_http,
    creer_organisation,
    sans_preparation_des_organisations,  # noqa: F401
)
from api.tests.mark.test_espaces_logo import _admin, _poser, fichiers, un_png  # noqa: F401

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")


@pytest.fixture
def route_jamais_appelee(monkeypatch):
    appels = []

    async def remplacer(*args, **kwargs):
        appels.append(args)
        raise AssertionError("la route ne devait pas être appelée")

    monkeypatch.setattr(logo_espace, "remplacer", remplacer)
    return appels


# --- la borne --------------------------------------------------------------------------------------------------


async def test_un_logo_annonce_a_5_mo_recoit_413_sans_appeler_la_route(route_jamais_appelee):
    async with client_http() as c:
        reponse = await c.put(
            "/api/v1/espaces/1/logo",
            files={"fichier": ("logo.png", b"\x00" * (5 * 1024 * 1024), "image/png")},
        )
    assert reponse.status_code == 413
    assert reponse.json() == {"detail": "envoi_trop_lourd"}
    assert route_jamais_appelee == []


async def test_un_envoi_decoupe_trop_gros_recoit_413(route_jamais_appelee):
    async def morceaux():
        yield (
            b'--x\r\nContent-Disposition: form-data; name="fichier"; filename="l.png"\r\n'
            b"Content-Type: image/png\r\n\r\n"
        )
        for _ in range(40):
            yield b"\x00" * 65_536  # 2,5 Mo en 40 morceaux, aucun Content-Length

    async with client_http() as c:
        reponse = await c.put(
            "/api/v1/espaces/1/logo",
            content=morceaux(),
            headers={"Content-Type": "multipart/form-data; boundary=x"},
        )
    assert reponse.status_code == 413
    assert reponse.json() == {"detail": "envoi_trop_lourd"}
    assert route_jamais_appelee == []


async def test_un_logo_a_la_borne_passe(db_session, fichiers):  # noqa: F811
    org = await creer_organisation(db_session, "borne-logo")
    jeton = await _admin(db_session, "borne-logo", org)
    png = un_png(256, 256)
    contenu = png + b"\x00" * (OCTETS_MAX - len(png))  # exactement 1 Mo
    assert len(contenu) == OCTETS_MAX
    async with client_http() as c:
        reponse = await _poser(c, jeton, org, contenu)
    assert reponse.status_code == 200


async def test_un_document_de_14_mo_passe_la_borne_et_16_mo_non():
    async with client_http() as c:
        passe = await c.post(
            "/api/v1/builder/bibliotheque/depot",
            data={"famille": "x"},
            files={"fichier": ("a.pdf", b"\x00" * (14 * 1024 * 1024), "application/pdf")},
        )
        refuse = await c.post(
            "/api/v1/builder/bibliotheque/depot",
            data={"famille": "x"},
            files={"fichier": ("a.pdf", b"\x00" * (16 * 1024 * 1024), "application/pdf")},
        )
    assert passe.status_code != 413  # la route répond (ici : refus d'accès sans session), la borne ne bloque pas
    assert refuse.status_code == 413 and refuse.json() == {"detail": "envoi_trop_lourd"}


def test_toute_route_a_fichier_a_sa_borne():
    manquantes = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        a_un_fichier = any(
            "UploadFile" in repr(p.field_info.annotation)
            for p in route.dependant.body_params
        )
        if not a_un_fichier:
            continue
        chemin = re.sub(r"\{[^}]+\}", "1", route.path)
        for methode in route.methods - {"HEAD", "OPTIONS"}:
            if borne_envoi.borne_de(methode, chemin) is None:
                manquantes.append(f"{methode} {route.path}")
    assert manquantes == []


# --- le logo : jamais de fichier en trop ---------------------------------------------------------------------


async def test_deux_poses_simultanees_ne_laissent_qu_un_fichier(db_session, fichiers, monkeypatch):  # noqa: F811
    org = await creer_organisation(db_session, "course-logo")
    ecrire = logo_espace.ecrire_octets

    async def ecrire_lentement(cle, donnees):
        await asyncio.sleep(0.01)  # laisse les deux poses s'entrelacer
        await ecrire(cle, donnees)

    monkeypatch.setattr(logo_espace, "ecrire_octets", ecrire_lentement)
    a, b = await asyncio.gather(
        logo_espace.remplacer(org, un_png(256, 256)), logo_espace.remplacer(org, un_png(300, 300))
    )
    reference = await logo_espace._lire_reference(org)
    assert reference["cle"] in (a["cle"], b["cle"])
    assert list(fichiers) == [reference["cle"]]


async def test_une_pose_depassee_par_un_autre_processus_efface_son_fichier(db_session, fichiers, monkeypatch):  # noqa: F811
    org = await creer_organisation(db_session, "course-autre-processus")
    vrai_upsert = logo_espace.db_client.upsert_configuration

    async def upsert_puis_autre(organization_id, cle, valeur, *args, **kwargs):
        resultat = await vrai_upsert(organization_id, cle, valeur, *args, **kwargs)
        fichiers["mark/logos/autre.png"] = b"x"  # l'autre processus range son fichier puis pose sa référence, juste après nous
        await vrai_upsert(organization_id, cle, {**valeur, "cle": "mark/logos/autre.png", "version": "autre"})
        return resultat

    monkeypatch.setattr(logo_espace.db_client, "upsert_configuration", upsert_puis_autre)
    await logo_espace.remplacer(org, un_png(256, 256))
    assert list(fichiers) == ["mark/logos/autre.png"]


async def test_un_delai_de_lecture_ne_laisse_aucun_fichier_temporaire(monkeypatch):
    chemins = []
    vrai_mkstemp = logo_espace.tempfile.mkstemp

    def mkstemp_note(*args, **kwargs):
        descripteur, chemin = vrai_mkstemp(*args, **kwargs)
        chemins.append(chemin)
        return descripteur, chemin

    def ecrire_tard(chemin):
        time.sleep(0.3)  # un fil du stockage : l'annulation de l'attente ne l'arrête pas
        with open(chemin, "wb") as f:
            f.write(b"tard")

    class StockageLent:
        async def adownload_file(self, cle, chemin):
            await asyncio.to_thread(ecrire_tard, chemin)
            return True

    monkeypatch.setattr(logo_espace.tempfile, "mkstemp", mkstemp_note)
    monkeypatch.setattr(logo_espace, "storage_fs", StockageLent())
    monkeypatch.setattr(logo_espace, "DELAI_STOCKAGE_S", 0.05)
    with pytest.raises(logo_espace.ErreurLogo) as e:
        await logo_espace.lire_octets("mark/logos/x.png")
    assert e.value.statut == 503
    await asyncio.sleep(0.6)  # la tâche de fond finit, le rappel efface
    assert len(chemins) == 1
    assert not os.path.exists(chemins[0])
