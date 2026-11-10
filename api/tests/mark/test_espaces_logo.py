"""[.mark] Correctifs d'écran, point 15 : le logo d'une organisation cliente.

| Test | Ce qu'il prouve |
|---|---|
| format refusé | SVG, GIF renommé en .png, faux PNG (extension et Content-Type menteurs) : refus 415, rien de rangé |
| trop lourd | plus de 1 Mo : 413, rien de rangé |
| dimensions | côté sous 128 ou au-dessus de 1024 : 422 |
| ratio | trop large ou trop haut (> 1,25) : 422 |
| succès | PNG, JPEG et WebP lus dans les octets, rangés, version rendue, image relue identique, journal écrit |
| remplacement | l'ancien fichier part, la version change |
| suppression | la référence ET le fichier sont retirés, la lecture rend 404 |
| droit | sans ``atelier.regler`` : 403 |
| autre organisation | l'espace d'une autre organisation : 404 (poser, retirer, lire), rien de rangé |
"""

import struct
import time
import zlib

import pytest

from api.services.equipe_mark import logo_espace
from api.services.equipe_mark.image_logo import OCTETS_MAX, ErreurLogo, lire_image
from api.tests.mark.equipe_commun import (
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")


# --- des images d'essai, écrites à la main (Pillow n'est pas une dépendance du projet) -----------------------------------


def un_png(largeur: int, hauteur: int) -> bytes:
    def morceau(nom: bytes, donnees: bytes) -> bytes:
        return struct.pack(">I", len(donnees)) + nom + donnees + struct.pack(">I", zlib.crc32(nom + donnees))

    lignes = b"".join(b"\x00" + b"\x20\x40\x80" * largeur for _ in range(hauteur))
    return (
        b"\x89PNG\r\n\x1a\n"
        + morceau(b"IHDR", struct.pack(">IIBBBBB", largeur, hauteur, 8, 2, 0, 0, 0))
        + morceau(b"IDAT", zlib.compress(lignes))
        + morceau(b"IEND", b"")
    )


def un_jpeg(largeur: int, hauteur: int) -> bytes:
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 17, 8, hauteur, largeur, 3) + b"\x01\x11\x00\x02\x11\x00\x03\x11\x00"
    return b"\xff\xd8" + app0 + sof + b"\xff\xd9"


def un_webp(largeur: int, hauteur: int) -> bytes:
    donnees = struct.pack("<I", 0) + (largeur - 1).to_bytes(3, "little") + (hauteur - 1).to_bytes(3, "little")
    corps = b"WEBP" + b"VP8X" + struct.pack("<I", len(donnees)) + donnees
    return b"RIFF" + struct.pack("<I", len(corps)) + corps


UN_GIF = b"GIF89a" + struct.pack("<HH", 512, 512) + b"\x00\x00\x00" + b";"
UN_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512"><script>alert(1)</script></svg>'


@pytest.fixture
def fichiers(monkeypatch):
    """Un stockage de fichiers en mémoire : les tests n'appellent jamais un vrai stockage."""
    rangés: dict[str, bytes] = {}

    async def ecrire(cle, donnees):
        rangés[cle] = donnees

    async def lire(cle):
        return rangés.get(cle)

    async def supprimer(cle):
        rangés.pop(cle, None)

    monkeypatch.setattr(logo_espace, "ecrire_octets", ecrire)
    monkeypatch.setattr(logo_espace, "lire_octets", lire)
    monkeypatch.setattr(logo_espace, "supprimer_octets", supprimer)
    return rangés


async def _admin(db, nom: str, org: int):
    _, jeton = await creer_compte(db, f"{nom}@example.com", role="Administrateur", organisations=[org])
    return jeton


async def _poser(c, jeton, org, contenu, nom="logo.png", type_="image/png"):
    return await c.put(
        f"/api/v1/espaces/{org}/logo", headers=entetes(jeton, org), files={"fichier": (nom, contenu, type_)}
    )


# --- les refus --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "contenu,nom,type_,code",
    [
        (UN_SVG, "logo.svg", "image/svg+xml", "logo_format"),
        (UN_SVG, "logo.png", "image/png", "logo_format"),  # un SVG déguisé
        (UN_GIF, "logo.png", "image/png", "logo_format"),  # un GIF renommé
        (b"ceci n'est pas une image" * 50, "logo.png", "image/png", "logo_format"),  # un faux PNG
        (b"\x89PNG\r\n\x1a\n" + b"pas un en-tete", "logo.png", "image/png", "logo_illisible"),  # signature vraie, contenu faux
    ],
)
async def test_un_format_refuse_ne_range_rien(db_session, fichiers, contenu, nom, type_, code):
    org = await creer_organisation(db_session, "logo-format")
    jeton = await _admin(db_session, "logo-format", org)
    async with client_http() as c:
        reponse = await _poser(c, jeton, org, contenu, nom, type_)
    assert reponse.status_code == 415
    assert reponse.json()["detail"] == code
    assert fichiers == {}
    assert await db_session.get_configuration(org, "MARK_LOGO") is None


async def test_un_logo_trop_lourd_est_refuse(db_session, fichiers):
    org = await creer_organisation(db_session, "logo-lourd")
    jeton = await _admin(db_session, "logo-lourd", org)
    lourd = un_png(512, 512) + b"\x00" * OCTETS_MAX  # PNG valide au début, plus de 1 Mo au total
    async with client_http() as c:
        reponse = await _poser(c, jeton, org, lourd)
    assert reponse.status_code == 413
    assert fichiers == {}


@pytest.mark.parametrize("largeur,hauteur", [(127, 127), (1025, 1025), (64, 512), (512, 2000)])
async def test_des_dimensions_hors_bornes_sont_refusees(db_session, fichiers, largeur, hauteur):
    org = await creer_organisation(db_session, f"logo-dim-{largeur}-{hauteur}")
    jeton = await _admin(db_session, f"logo-dim-{largeur}-{hauteur}", org)
    async with client_http() as c:
        reponse = await _poser(c, jeton, org, un_png(largeur, hauteur))
    assert reponse.status_code == 422
    assert reponse.json()["detail"] == "logo_dimensions"
    assert fichiers == {}


@pytest.mark.parametrize("largeur,hauteur", [(640, 400), (400, 640)])
async def test_un_ratio_hors_borne_est_refuse(db_session, fichiers, largeur, hauteur):
    org = await creer_organisation(db_session, f"logo-ratio-{largeur}")
    jeton = await _admin(db_session, f"logo-ratio-{largeur}", org)
    async with client_http() as c:
        reponse = await _poser(c, jeton, org, un_png(largeur, hauteur))
    assert reponse.status_code == 422
    assert reponse.json()["detail"] == "logo_ratio"
    assert fichiers == {}


# --- le succès, le remplacement, la suppression ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "fabrique,type_mime",
    [(un_png, "image/png"), (un_jpeg, "image/jpeg"), (un_webp, "image/webp")],
)
async def test_un_logo_valide_est_lu_dans_les_octets_range_et_relu(db_session, fichiers, fabrique, type_mime):
    org = await creer_organisation(db_session, f"logo-ok-{type_mime[-4:]}")
    jeton = await _admin(db_session, f"logo-ok-{type_mime[-4:]}", org)
    image = fabrique(512, 480)
    async with client_http() as c:
        # Le Content-Type et le nom envoyés sont faux exprès : seul le contenu compte.
        reponse = await _poser(c, jeton, org, image, nom="x.bin", type_="application/octet-stream")
        liste = await c.get("/api/v1/espaces", headers=entetes(jeton, org))
        relu = await c.get(f"/api/v1/espaces/{org}/logo", headers=entetes(jeton, org))
    assert reponse.status_code == 200
    version = reponse.json()["logo_version"]
    assert version
    assert next(e for e in liste.json()["espaces"] if e["id"] == org)["logo_version"] == version
    assert relu.status_code == 200 and relu.content == image
    assert relu.headers["content-type"] == type_mime
    assert relu.headers["x-content-type-options"] == "nosniff"
    config = (await db_session.get_configuration(org, "MARK_LOGO")).value
    assert config["type"] == type_mime and (config["largeur"], config["hauteur"]) == (512, 480)
    assert list(fichiers) == [config["cle"]] and config["cle"].startswith(f"mark/logos/{org}/")


async def test_le_remplacement_retire_l_ancien_fichier_et_change_la_version(db_session, fichiers):
    org = await creer_organisation(db_session, "logo-remplace")
    jeton = await _admin(db_session, "logo-remplace", org)
    async with client_http() as c:
        premier = await _poser(c, jeton, org, un_png(256, 256))
        second = await _poser(c, jeton, org, un_jpeg(300, 300), nom="a.jpg", type_="image/jpeg")
    assert premier.json()["logo_version"] != second.json()["logo_version"]
    assert len(fichiers) == 1
    assert (await db_session.get_configuration(org, "MARK_LOGO")).value["type"] == "image/jpeg"


async def test_la_suppression_retire_la_reference_et_le_fichier(db_session, fichiers):
    org = await creer_organisation(db_session, "logo-retire")
    jeton = await _admin(db_session, "logo-retire", org)
    async with client_http() as c:
        await _poser(c, jeton, org, un_png(256, 256))
        assert len(fichiers) == 1
        retire = await c.delete(f"/api/v1/espaces/{org}/logo", headers=entetes(jeton, org))
        relu = await c.get(f"/api/v1/espaces/{org}/logo", headers=entetes(jeton, org))
        liste = await c.get("/api/v1/espaces", headers=entetes(jeton, org))
    assert retire.status_code == 200 and retire.json()["logo_version"] is None
    assert fichiers == {}
    assert await db_session.get_configuration(org, "MARK_LOGO") is None
    assert relu.status_code == 404
    assert next(e for e in liste.json()["espaces"] if e["id"] == org)["logo_version"] is None


async def test_poser_et_retirer_sont_journalises(db_session, fichiers):
    org = await creer_organisation(db_session, "logo-journal")
    jeton = await _admin(db_session, "logo-journal", org)
    async with client_http() as c:
        await _poser(c, jeton, org, un_png(256, 256))
        await c.delete(f"/api/v1/espaces/{org}/logo", headers=entetes(jeton, org))
    lignes = [ligne for ligne in (await db_session.lister_journal(limit=50, offset=0, organization_id=org))[0] if ligne["action"] == "espace.logo"]
    assert sorted(ligne["detail"]["geste"] for ligne in lignes) == ["remplace", "retire"]


# --- les droits et le cloisonnement -------------------------------------------------------------------------------------


async def test_sans_la_permission_de_regler_le_logo_est_refuse(db_session, fichiers):
    org = await creer_organisation(db_session, "logo-droit")
    _, jeton = await creer_compte(db_session, "logo-droit@example.com", role="Membre", organisations=[org])
    async with client_http() as c:
        pose = await _poser(c, jeton, org, un_png(256, 256))
        retire = await c.delete(f"/api/v1/espaces/{org}/logo", headers=entetes(jeton, org))
    assert pose.status_code == 403 and retire.status_code == 403
    assert fichiers == {}


async def test_l_espace_d_une_autre_organisation_est_un_404(db_session, fichiers):
    ouvert = await creer_organisation(db_session, "logo-ouvert")
    ferme = await creer_organisation(db_session, "logo-ferme")
    role = await db_session.creer_role(
        nom="Regle-un-client-logo-test",
        labo_ouvert=False,
        tous_les_clients=False,
        permissions=["atelier.regler"],
        organisations=[ouvert],
    )
    user, jeton = await creer_compte(db_session, "logo-cloison@example.com", organisations=[ferme])
    await db_session.poser_membre(user.id, role)
    # L'autre organisation a un logo : le compte ne peut ni le lire, ni le remplacer, ni le retirer.
    await logo_espace.remplacer(ferme, un_png(256, 256))
    avant = dict(fichiers)
    ma = entetes(jeton, ouvert)
    async with client_http() as c:
        # Son espace dans l'en-tête, celui de l'autre dans l'adresse : le contrôle de la route répond 404 (jamais l'existence d'un logo).
        pose = await c.put(
            f"/api/v1/espaces/{ferme}/logo", headers=ma, files={"fichier": ("a.png", un_png(300, 300), "image/png")}
        )
        lecture = await c.get(f"/api/v1/espaces/{ferme}/logo", headers=ma)
        retire = await c.delete(f"/api/v1/espaces/{ferme}/logo", headers=ma)
        # L'espace de l'autre dans l'en-tête : la couche d'accès refuse avant la route (403, rien de rangé).
        en_tete = await _poser(c, jeton, ferme, un_png(300, 300))
        sien = await _poser(c, jeton, ouvert, un_png(300, 300))
    assert pose.status_code == lecture.status_code == retire.status_code == 404
    assert en_tete.status_code == 403
    assert sien.status_code == 200
    assert avant.items() <= fichiers.items()  # le logo de l'autre est intact


def test_le_type_est_lu_dans_les_octets_jamais_dans_le_nom():
    assert lire_image(un_png(200, 200)).format == "png"
    assert lire_image(un_jpeg(200, 200)).format == "jpeg"
    assert lire_image(un_webp(200, 200)).format == "webp"
    with pytest.raises(ErreurLogo) as e:
        lire_image(UN_GIF)
    assert e.value.statut == 415


async def test_un_stockage_qui_ne_repond_pas_rend_un_503_net_sans_rien_garder(db_session, monkeypatch):
    """Un appel externe a un délai : jamais d'attente infinie, et la référence n'est posée qu'une fois le fichier rangé."""
    import asyncio

    class StockageSourd:
        async def acreate_file_from_bytes(self, cle, donnees):
            await asyncio.sleep(30)

        async def adownload_file(self, cle, chemin):
            await asyncio.sleep(30)

        async def adelete_file(self, cle):
            await asyncio.sleep(30)

    monkeypatch.setattr(logo_espace, "storage_fs", StockageSourd())
    monkeypatch.setattr(logo_espace, "DELAI_STOCKAGE_S", 0.05)
    org = await creer_organisation(db_session, "logo-sourd")
    jeton = await _admin(db_session, "logo-sourd", org)
    debut = time.monotonic()
    async with client_http() as c:
        pose = await _poser(c, jeton, org, un_png(256, 256))
    assert time.monotonic() - debut < 5  # le délai a coupé l'attente (le stockage dort 30 s)
    assert pose.status_code == 503 and pose.json()["detail"] == "logo_stockage"
    assert await db_session.get_configuration(org, "MARK_LOGO") is None
    # Un logo référencé dont le fichier ne répond pas : 503 à la lecture, pas un 404 qui ferait croire qu'il n'y en a pas.
    await db_session.upsert_configuration(org, "MARK_LOGO", {"cle": "mark/logos/x.png", "version": "v", "type": "image/png"})
    async with client_http() as c:
        lecture = await c.get(f"/api/v1/espaces/{org}/logo", headers=entetes(jeton, org))
    assert lecture.status_code == 503
