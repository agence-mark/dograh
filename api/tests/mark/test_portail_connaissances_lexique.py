"""[.mark] Builder partie 2, U10 points 7 et 8 : la base de connaissances et le lexique ouverts au portail.

| Test | Ce qu'il prouve |
|---|---|
| clé de stockage | `process-document` refuse la clé d'une AUTRE organisation, une clé qui remonte, une clé hors dossier |
| remplacement | un nouveau fichier prend la place sous le MÊME document (identifiant, uuid), l'ancienne version reste servie, le nom et la clé changent |
| remplacement refusé | clé d'une autre organisation, format inconnu, document occupé (409), mise en file impossible (tout est remis) |
| « utilisé par » | un agent publié qui porte l'uuid consulte le document ; les autres non ; la route le rend pour l'organisation |
| autre organisation (base de connaissances) | chaque route répond 404 / 422 avec la clé d'une autre organisation, rien ne bouge chez la première ; la liste de B est vide |
| autre organisation (lexique) | lire, enregistrer, budget et import : refus avec la clé d'une autre organisation, le lexique de A est intact ; avec la sienne ça passe |
"""

from unittest.mock import AsyncMock, patch

import pytest

from api.services import knowledge_base_portail as portail
from api.tests.mark.equipe_commun import (
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")

API = "/api/v1"


async def _acces(db_session, nom, organisations, *, permissions=("agents.modifier",)):
    role = await db_session.creer_role(
        nom=f"Portail-{nom}",
        labo_ouvert=True,
        tous_les_clients=False,
        permissions=list(permissions),
        organisations=list(organisations),
    )
    user, jeton = await creer_compte(db_session, f"{nom}@example.com", organisations=organisations)
    await db_session.poser_membre(user.id, role)
    return user, jeton


async def _document(db_session, organisation, user, *, statut="completed", nom="tarifs.pdf", uuid="doc-aaaa-0001"):
    cree = await db_session.create_document(
        organization_id=organisation,
        created_by=user.id,
        filename=nom,
        file_size_bytes=10,
        file_hash=f"hash-{uuid}",
        mime_type="application/pdf",
        custom_metadata={"s3_key": f"knowledge_base/{organisation}/{uuid}/{nom}"},
        document_uuid=uuid,
        retrieval_mode="full_document",
    )
    await db_session.update_document_full_text(cree.id, "Version 1 des tarifs")
    await db_session.update_document_status(cree.id, statut)
    return cree


# ----------------------------------------------------------------------------- la clé de stockage
@pytest.mark.parametrize(
    "cle, valide",
    [
        ("knowledge_base/7/abc/tarifs.pdf", True),
        ("knowledge_base/8/abc/tarifs.pdf", False),  # une autre organisation
        ("knowledge_base/7/../8/abc/tarifs.pdf", False),
        ("knowledge_base/7/abc/../x.pdf", False),
        ("knowledge_base/7/abc", False),
        ("knowledge_base/7/abc/sous/tarifs.pdf", False),
        ("autre/7/abc/tarifs.pdf", False),
        ("knowledge_base/70/abc/tarifs.pdf", False),
        ("knowledge_base\\7\\abc\\tarifs.pdf", False),
        ("", False),
    ],
)
def test_cle_de_stockage(cle, valide):
    assert portail.cle_stockage_valide(cle, 7) is valide


async def test_process_document_refuse_la_cle_d_une_autre_organisation(db_session):
    org_a = await creer_organisation(db_session, "kb-a1")
    org_b = await creer_organisation(db_session, "kb-b1")
    _, jeton_b = await _acces(db_session, "kbb1", [org_b])
    async with client_http() as c:
        r = await c.post(
            f"{API}/knowledge-base/process-document",
            headers=entetes(jeton_b, org_b),
            json={"document_uuid": "u-1", "s3_key": f"knowledge_base/{org_a}/u-1/secret.pdf"},
        )
    assert r.status_code == 422
    assert await db_session.get_document_by_uuid("u-1", org_b) is None
    assert await db_session.get_document_by_uuid("u-1", org_a) is None


# ----------------------------------------------------------------------------- le remplacement
async def test_un_remplacement_garde_le_document_et_sert_l_ancienne_version(db_session):
    org = await creer_organisation(db_session, "kb-a2")
    user, jeton = await _acces(db_session, "kba2", [org])
    avant = await _document(db_session, org, user)
    mise_en_file = AsyncMock()
    async with client_http() as c:
        with patch.object(portail, "enqueue_document_processing", mise_en_file):
            r = await c.post(
                f"{API}/knowledge-base/documents/{avant.document_uuid}/remplacer",
                headers=entetes(jeton, org),
                json={"s3_key": f"knowledge_base/{org}/nouveau-1/tarifs-2027.docx"},
            )
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["id"] == avant.id and corps["document_uuid"] == avant.document_uuid
    assert corps["filename"] == "tarifs-2027.docx" and corps["processing_status"] == "pending"
    apres = await db_session.get_document_by_uuid(avant.document_uuid, org)
    assert apres.custom_metadata["s3_key"] == f"knowledge_base/{org}/nouveau-1/tarifs-2027.docx"
    assert apres.full_text == "Version 1 des tarifs"  # l'ancienne version reste servie
    mise_en_file.assert_awaited_once()
    assert mise_en_file.await_args.kwargs["document_id"] == avant.id
    assert mise_en_file.await_args.kwargs["s3_key"].endswith("tarifs-2027.docx")


async def test_un_remplacement_refuse_ne_change_rien(db_session):
    org_a = await creer_organisation(db_session, "kb-a3")
    org_b = await creer_organisation(db_session, "kb-b3")
    user, jeton = await _acces(db_session, "kba3", [org_a])
    _, jeton_b = await _acces(db_session, "kbb3", [org_b])
    doc = await _document(db_session, org_a, user, uuid="doc-aaaa-0003")
    url = f"{API}/knowledge-base/documents/{doc.document_uuid}/remplacer"
    mise_en_file = AsyncMock()
    async with client_http() as c:
        with patch.object(portail, "enqueue_document_processing", mise_en_file):
            autre_org = await c.post(
                url, headers=entetes(jeton_b, org_b), json={"s3_key": f"knowledge_base/{org_b}/n/x.pdf"}
            )
            cle_etrangere = await c.post(
                url, headers=entetes(jeton, org_a), json={"s3_key": f"knowledge_base/{org_b}/n/x.pdf"}
            )
            format_inconnu = await c.post(
                url, headers=entetes(jeton, org_a), json={"s3_key": f"knowledge_base/{org_a}/n/photo.png"}
            )
            await db_session.update_document_status(doc.id, "processing")
            occupe = await c.post(
                url, headers=entetes(jeton, org_a), json={"s3_key": f"knowledge_base/{org_a}/n/x.pdf"}
            )
    assert autre_org.status_code == 404
    assert cle_etrangere.status_code == 422
    assert format_inconnu.status_code == 422
    assert occupe.status_code == 409
    mise_en_file.assert_not_awaited()
    intact = await db_session.get_document_by_uuid(doc.document_uuid, org_a)
    assert intact.filename == "tarifs.pdf" and intact.processing_status == "processing"


async def test_mise_en_file_impossible_remet_le_document_comme_avant(db_session):
    org = await creer_organisation(db_session, "kb-a4")
    user, jeton = await _acces(db_session, "kba4", [org])
    doc = await _document(db_session, org, user, uuid="doc-aaaa-0004")
    async with client_http() as c:
        with patch.object(portail, "enqueue_document_processing", AsyncMock(side_effect=RuntimeError("file"))):
            r = await c.post(
                f"{API}/knowledge-base/documents/{doc.document_uuid}/remplacer",
                headers=entetes(jeton, org),
                json={"s3_key": f"knowledge_base/{org}/n/x.pdf"},
            )
    assert r.status_code == 500
    remis = await db_session.get_document_by_uuid(doc.document_uuid, org)
    assert remis.filename == "tarifs.pdf" and remis.processing_status == "completed"
    assert remis.custom_metadata["s3_key"] == f"knowledge_base/{org}/doc-aaaa-0004/tarifs.pdf"


# ----------------------------------------------------------------------------- « utilisé par »
def test_utilise_par_calcule_sur_les_agents_publies():
    agents = [(1, "Accueil", '{"document_uuids": ["doc-1"]}'), (2, "Standard", '{"x": 1}'), (3, "Les deux", "doc-1 doc-2")]
    sortie = portail.agents_qui_consultent(["doc-1", "doc-2", "doc-3"], agents)
    assert [a.nom for a in sortie["doc-1"]] == ["Accueil", "Les deux"]
    assert [a.nom for a in sortie["doc-2"]] == ["Les deux"]
    assert sortie["doc-3"] == []


async def test_la_route_utilisation_ne_rend_que_les_documents_de_l_organisation(db_session):
    org_a = await creer_organisation(db_session, "kb-a5")
    org_b = await creer_organisation(db_session, "kb-b5")
    user_a, jeton_a = await _acces(db_session, "kba5", [org_a])
    user_b, jeton_b = await _acces(db_session, "kbb5", [org_b])
    await _document(db_session, org_a, user_a, uuid="doc-aaaa-0005")
    await _document(db_session, org_b, user_b, uuid="doc-bbbb-0005")
    publies = AsyncMock(return_value=[(11, "Accueil A", '{"document_uuids": ["doc-aaaa-0005", "doc-bbbb-0005"]}')])
    async with client_http() as c:
        with patch("api.services.objets_agent.utilisation._agents_publies", publies):
            ra = await c.get(f"{API}/knowledge-base/utilisation", headers=entetes(jeton_a, org_a))
            rb = await c.get(f"{API}/knowledge-base/utilisation", headers=entetes(jeton_b, org_b))
    assert ra.json() == {"documents": [{"document_uuid": "doc-aaaa-0005", "agents": [{"id": 11, "nom": "Accueil A"}]}]}
    assert [d["document_uuid"] for d in rb.json()["documents"]] == ["doc-bbbb-0005"]
    publies.assert_any_await(org_a)
    publies.assert_any_await(org_b)


# ----------------------------------------------------------------------------- autre organisation
async def test_chaque_route_de_la_base_refuse_la_cle_d_une_autre_organisation(db_session):
    org_a = await creer_organisation(db_session, "kb-a6")
    org_b = await creer_organisation(db_session, "kb-b6")
    user_a, _ = await _acces(db_session, "kba6", [org_a])
    _, jeton_b = await _acces(db_session, "kbb6", [org_b])
    doc = await _document(db_session, org_a, user_a, uuid="doc-aaaa-0006")
    h = entetes(jeton_b, org_b)
    base = f"{API}/knowledge-base/documents/{doc.document_uuid}"
    async with client_http() as c:
        reponses = {
            "lire": await c.get(base, headers=h),
            "contenu": await c.get(f"{base}/content", headers=h),
            "enregistrer": await c.put(f"{base}/content", headers=h, json={"content": "pris", "expected_file_hash": doc.file_hash}),
            "remplacer": await c.post(f"{base}/remplacer", headers=h, json={"s3_key": f"knowledge_base/{org_b}/n/x.pdf"}),
            "supprimer": await c.delete(base, headers=h),
        }
        liste_b = (await c.get(f"{API}/knowledge-base/documents", headers=h)).json()
        # L'en-tête de l'organisation A, où le compte B n'est pas membre : refusé par la porte d'accès.
        porte = await c.get(f"{API}/knowledge-base/documents", headers=entetes(jeton_b, org_a))
    mauvaises = {nom: r.status_code for nom, r in reponses.items() if r.status_code != 404}
    assert not mauvaises, mauvaises
    assert liste_b["documents"] == []
    assert porte.status_code == 403
    intact = await db_session.get_document_by_uuid(doc.document_uuid, org_a)
    assert intact is not None and intact.full_text == "Version 1 des tarifs" and intact.filename == "tarifs.pdf"


async def test_les_routes_du_lexique_refusent_la_cle_d_une_autre_organisation(db_session):
    org_a = await creer_organisation(db_session, "lx-a")
    org_b = await creer_organisation(db_session, "lx-b")
    _, jeton_a = await _acces(db_session, "lxa", [org_a])
    _, jeton_b = await _acces(db_session, "lxb", [org_b])
    lexique = {"termes": [{"terme": "Gazoleen", "variantes": ["Gazoléen"], "a_ecouter": True}]}
    ha, hb = entetes(jeton_a, org_a), entetes(jeton_b, org_b)
    async with client_http() as c:
        pose = await c.put(f"{API}/organizations/lexique", headers=ha, json=lexique)
        assert pose.status_code == 200, pose.text
        # B, qui n'est pas membre de A : refus à la porte pour chaque route, sur l'organisation de A.
        refus = {
            "lire": await c.get(f"{API}/organizations/lexique", headers=entetes(jeton_b, org_a)),
            "enregistrer": await c.put(f"{API}/organizations/lexique", headers=entetes(jeton_b, org_a), json={"termes": []}),
            "budget": await c.post(f"{API}/organizations/lexique/budget", headers=entetes(jeton_b, org_a), json=lexique),
            "import": await c.post(f"{API}/organizations/lexique/import", headers=entetes(jeton_b, org_a), json=lexique),
        }
        # B avec sa propre organisation : voit SON lexique (vide), jamais celui de A ; enregistrer n'écrase pas A.
        chez_b = (await c.get(f"{API}/organizations/lexique", headers=hb)).json()
        ecrit_b = await c.put(f"{API}/organizations/lexique", headers=hb, json={"termes": []})
        chez_a = (await c.get(f"{API}/organizations/lexique", headers=ha)).json()
    assert {nom: r.status_code for nom, r in refus.items()} == {"lire": 403, "enregistrer": 403, "budget": 403, "import": 403}
    assert chez_b["termes"] == [] and ecrit_b.status_code == 200
    assert [t["terme"] for t in chez_a["termes"]] == ["Gazoleen"]
