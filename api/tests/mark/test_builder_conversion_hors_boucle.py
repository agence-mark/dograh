"""[.mark] Builder, revue R3 et constat C11 : la conversion d'un PDF ou d'un Word ne tourne jamais dans la boucle de l'API, et elle
tourne dans un PROCESSUS à part, arrêté au-delà du délai.

| Test | Ce qu'il prouve |
|---|---|
| boucle libre | pendant une conversion lente, la boucle continue de tourner (un battement passe) |
| délai du dépôt | un délai dépassé rend le fichier illisible EN LE DISANT (le dépôt ne plante pas) |
| délai de la tâche | la tâche de la base de connaissances échoue en le disant (« took more than ») |
| arrêt réel (C11) | au-delà du délai, le processus est arrêté : ce qu'il aurait écrit après n'arrive jamais |
| erreurs de l'enfant | une ``ValueError`` garde sa raison, une autre erreur devient ``RuntimeError`` sans son contenu |
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.builder.dossiers import extraction, processus
from api.tasks import knowledge_base_processing as tache
from api.tests.mark import conversion_lente


async def test_pendant_une_conversion_lente_la_boucle_continue_de_tourner():
    battements = []

    async def battre():
        for _ in range(5):
            battements.append(time.monotonic())
            await asyncio.sleep(0.02)

    with patch.object(extraction, "extraire", conversion_lente.lente_03):
        debut = time.monotonic()
        resultat, _ = await asyncio.gather(extraction.extraire_hors_boucle("a.pdf", b"x", 30), battre())
    assert resultat.pages and len(battements) == 5
    # sans processus séparé, les cinq battements attendraient la fin de la conversion (et le départ du processus)
    assert battements[-1] - debut < 0.3


async def test_un_delai_depasse_rend_le_fichier_illisible_en_le_disant():
    with patch.object(extraction, "extraire", conversion_lente.lente_05):
        resultat = await extraction.extraire_hors_boucle("a.pdf", b"x", 0.05)
    assert resultat.illisible and "took more than" in resultat.illisible and not resultat.pages


async def test_le_depot_d_un_fichier_utilise_la_lecture_hors_boucle(monkeypatch):
    from api.services.builder.dossiers import depot

    appels = []

    async def hors_boucle(nom, contenu):
        appels.append(nom)
        return extraction.Extraction(illisible="Reading the file took more than 1 seconds: split it.")

    monkeypatch.setattr(depot.extraction, "extraire_hors_boucle", hors_boucle)
    monkeypatch.setattr(depot, "lister", AsyncMock(return_value=[]))
    monkeypatch.setattr(depot, "ecrire_octets", AsyncMock())
    monkeypatch.setattr(depot, "_ajouter_a_l_index", AsyncMock())
    resultat = await depot.deposer_fichier(1, 2, "gros.pdf", b"%PDF", "evan")
    assert appels == ["gros.pdf"] and resultat["statut"] == "illisible" and "took more than" in resultat["raison"]


async def test_la_tache_de_la_base_de_connaissances_echoue_en_le_disant(monkeypatch):
    async def telecharger(_cle, destination):
        with open(destination, "wb") as f:
            f.write(b"%PDF-1.4 faux")
        return True

    db = MagicMock()
    for nom in ("update_document_status", "update_document_metadata", "replace_chunks_for_document", "get_document_by_hash"):
        setattr(db, nom, AsyncMock(return_value=None))
    db.get_document_by_id = AsyncMock(return_value=SimpleNamespace(organization_id=7))
    db.compute_file_hash = MagicMock(return_value="h")
    db.get_mime_type = MagicMock(return_value="application/pdf")
    embeddings = SimpleNamespace(embeddings=None)
    monkeypatch.setattr(tache, "DELAI_CONVERSION_S", 0.05)
    monkeypatch.setattr(tache, "traiter_un_document", conversion_lente.lente_document)
    with (
        patch.object(tache, "db_client", db),
        patch.object(tache.storage_fs, "adownload_file", telecharger),
        patch("api.services.configuration.ai_model_configuration.get_resolved_ai_model_configuration", AsyncMock(return_value=SimpleNamespace(effective=embeddings))),
        patch("api.services.cles_reference.resoudre_les_cles", AsyncMock(return_value=embeddings)),
    ):
        with pytest.raises(ValueError, match="took more than"):  # la tâche inscrit l'échec puis le relève, comme avant
            await tache.process_knowledge_base_document({}, 1, "org/7/cv.pdf", 7, "evan", retrieval_mode="chunked")
    dernier = db.update_document_status.await_args_list[-1]
    assert dernier.args[1] == "failed" and "took more than" in str(dernier.kwargs.get("error_message"))


def test_c11_au_dela_du_delai_le_processus_est_arrete_pour_de_bon(tmp_path):
    temoin = tmp_path / "temoin.txt"
    debut = time.monotonic()
    with pytest.raises(processus.DelaiDepasse):
        processus.executer_arretable(conversion_lente.ecrit_apres, str(temoin), 1.5, delai_s=0.3)
    time.sleep(2.0)  # un fil aurait fini et écrit le témoin ; un processus arrêté, jamais
    assert not temoin.exists() and time.monotonic() - debut < 6


def test_c11_l_enfant_rend_sa_valeur_et_ses_erreurs_sans_trace():
    assert processus.executer_arretable(conversion_lente.double, 21, delai_s=30) == 42
    with pytest.raises(ValueError, match="raison lisible"):
        processus.executer_arretable(conversion_lente.leve_une_valeur, delai_s=30)
    with pytest.raises(RuntimeError) as erreur:
        processus.executer_arretable(conversion_lente.leve_autre_chose, delai_s=30)
    assert "KeyError" in str(erreur.value) and "secret-interne" not in str(erreur.value)
