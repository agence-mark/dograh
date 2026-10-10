"""[.mark] Un document texte entre-t-il dans la base de connaissances sans le service de l'éditeur ?

La question de ce fichier, et elle seule :

    Un fichier ``.txt`` ou ``.md`` est-il lu, découpé (par paragraphes, sous la taille réglée)
    et vectorisé PAR LA VRAIE TÂCHE D'INGESTION, sans aucun appel au MPS (coupé par notre
    patch n° 60) -- et un modèle d'embeddings compatible OpenAI hébergé ailleurs (Scaleway)
    est-il prié de rendre les 1 536 nombres que la base stocke ?

Pourquoi il existe
------------------
Chantier ``agent-leger-greffier``, lot C (10/10) : l'amont confie la conversion et le
découpage de tout document au MPS (``services.dograh.com``). Notre patch n° 60 coupant ces
appels, aucun document n'entrait dans la base de connaissances, dans aucun des deux modes.
Sonde Scaleway du 10/10 : ``qwen3-embedding-8b`` rend 4 096 nombres par défaut, 1 536 sur
demande ; ``bge-multilingual-gemma2`` refuse la demande (HTTP 400).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.gen_ai.documents_locaux import (
    decouper,
    est_un_texte,
    traiter_un_texte,
)
from api.services.gen_ai.embedding.factory import dimensions_demandees
from api.services.gen_ai.embedding.openai_service import OpenAIEmbeddingService
from api.tasks import knowledge_base_processing as tache

# Une FAQ d'un autre métier (garage) : le découpage ne connaît que les lignes vides.
FAQ = (
    "Q : Faut-il prendre rendez-vous pour une vidange ?\n"
    "R : Oui, la vidange se fait sur rendez-vous, du lundi au vendredi.\n\n"
    "Q : Le contrôle technique est-il fait sur place ?\n"
    "R : Non, nous vous orientons vers un centre agréé.\n\n"
    "Q : Prêtez-vous un véhicule pendant les réparations ?\n"
    "R : Un véhicule de courtoisie peut être prêté selon les disponibilités.\n"
)


def test_un_texte_se_reconnait_par_son_extension_ou_son_type():
    assert est_un_texte("faq.txt", None) and est_un_texte(
        "faq.md", "application/octet-stream"
    )
    assert est_un_texte("faq.bin", "text/plain")
    assert not est_un_texte("tarifs.pdf", "application/pdf")


def test_le_decoupage_ne_coupe_jamais_une_question_de_sa_reponse():
    morceaux = decouper(FAQ, max_tokens=25)
    assert len(morceaux) == 3
    assert all(m.startswith("Q :") and "\nR :" in m for m in morceaux)
    # Sous une taille large, les paragraphes se regroupent.
    assert len(decouper(FAQ, max_tokens=500)) == 1


def test_un_paragraphe_trop_long_est_coupe_aux_fins_de_phrase():
    """Revue du 10/10 : un fichier sans ligne vide donnait un seul morceau géant."""
    bloc = " ".join(f"Phrase numéro {i} du document." for i in range(200))
    morceaux = decouper(bloc, 50)
    assert len(morceaux) > 1
    assert all(len(m.split()) * 1.3 <= 50 * 4 + 10 for m in morceaux)
    assert all(m.endswith(".") for m in morceaux)
    assert " ".join(morceaux) == bloc


def test_un_texte_trop_gros_est_refuse_en_le_disant(tmp_path, monkeypatch):
    import api.services.gen_ai.documents_locaux as locaux

    monkeypatch.setattr(locaux, "TAILLE_MAX_OCTETS", 100)
    chemin = tmp_path / "gros.txt"
    chemin.write_text("x" * 101, encoding="utf-8")
    with pytest.raises(ValueError, match="too large"):
        traiter_un_texte(str(chemin), "chunked", 100)


def test_les_deux_modes_rendent_la_forme_du_mps(tmp_path):
    chemin = tmp_path / "faq.txt"
    chemin.write_text(FAQ, encoding="utf-8")
    entier = traiter_un_texte(str(chemin), "full_document", 128)
    assert entier["full_text"] == FAQ.strip() and entier["chunks"] == []
    morceaux = traiter_un_texte(str(chemin), "chunked", 25)["chunks"]
    assert [m["chunk_index"] for m in morceaux] == [0, 1, 2]
    assert {
        "chunk_text",
        "contextualized_text",
        "token_count",
        "chunk_metadata",
    } <= set(morceaux[0])


async def test_la_vraie_tache_ingere_un_texte_sans_appeler_le_mps(tmp_path):
    async def telecharger(_cle, destination):
        with open(destination, "w", encoding="utf-8") as f:
            f.write(FAQ)
        return True

    db = MagicMock()
    for nom in (
        "update_document_status",
        "update_document_metadata",
        "replace_chunks_for_document",
        "get_document_by_hash",
    ):
        setattr(db, nom, AsyncMock(return_value=None))
    db.get_document_by_id = AsyncMock(return_value=SimpleNamespace(organization_id=7))
    db.compute_file_hash = MagicMock(return_value="empreinte")
    db.get_mime_type = MagicMock(return_value="text/plain")
    embeddings = SimpleNamespace(
        embeddings=SimpleNamespace(
            api_key="cle",
            model="qwen3-embedding-8b",
            provider="openai",
            base_url="https://api.scaleway.ai/v1",
        )
    )
    vectoriseur = MagicMock()
    vectoriseur.embed_texts = AsyncMock(
        side_effect=lambda textes: [[0.0] * 1536 for _ in textes]
    )
    mps = MagicMock()
    mps.process_document = AsyncMock(side_effect=AssertionError("MPS appelé"))

    with (
        patch.object(tache, "db_client", db),
        patch.object(tache.storage_fs, "adownload_file", telecharger),
        patch.object(tache, "mps_service_key_client", mps),
        patch.object(
            tache, "build_embedding_service", AsyncMock(return_value=vectoriseur)
        ),
        patch(
            "api.services.configuration.ai_model_configuration.get_resolved_ai_model_configuration",
            AsyncMock(return_value=SimpleNamespace(effective=embeddings)),
        ),
        patch(
            "api.services.cles_reference.resoudre_les_cles",
            AsyncMock(return_value=embeddings),
        ),
    ):
        await tache.process_knowledge_base_document(
            {}, 1, "org/7/faq.txt", 7, "evan", max_tokens=25, retrieval_mode="chunked"
        )

    mps.process_document.assert_not_awaited()
    ranges = db.replace_chunks_for_document.await_args.kwargs["chunks"]
    assert len(ranges) == 3 and all(len(c.embedding) == 1536 for c in ranges)
    assert db.update_document_status.await_args_list[-1].args[1] == "completed"


@pytest.mark.parametrize(
    "fournisseur, adresse, attendu",
    [
        ("openai", "https://api.scaleway.ai/v1", 1536),
        ("openai", "https://api.openai.com/v1", None),
        ("openai", None, None),
        ("openrouter", "https://openrouter.ai/api/v1", None),
    ],
)
def test_seul_un_modele_compatible_heberge_ailleurs_est_prie_de_rendre_1536(
    fournisseur, adresse, attendu
):
    assert dimensions_demandees(fournisseur, adresse) == attendu


def test_la_taille_part_dans_la_requete_d_embeddings():
    service = OpenAIEmbeddingService(
        db_client=None,
        api_key="k",
        model_id="qwen3-embedding-8b",
        base_url="https://api.scaleway.ai/v1",
        dimensions=1536,
    )
    assert service._request_kwargs() == {"dimensions": 1536}
    assert OpenAIEmbeddingService(db_client=None, api_key="k")._request_kwargs() == {}
