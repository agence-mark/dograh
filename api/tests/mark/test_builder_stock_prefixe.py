"""[.mark] Builder, revue R4 : ``stock.lister`` filtre par préfixe DANS LA BASE (``key LIKE``), sur la vraie base de test.

| Test | Ce qu'il prouve |
|---|---|
| préfixe | seules les clés du préfixe reviennent, triées |
| caractères spéciaux | ``_`` et ``%`` du préfixe sont des caractères, pas des jokers |
| organisation | les clés d'une autre organisation ne reviennent jamais |
| bibliothèque | la liste d'une famille compte les agents en UNE lecture (plus une par élément) |
"""

from __future__ import annotations

from api.services.builder import stock


async def _organisations(db_session):
    user, _ = await db_session.get_or_create_user_by_provider_id("stock_user")
    a, _ = await db_session.get_or_create_organization_by_provider_id("stock_org_a", user.id)
    b, _ = await db_session.get_or_create_organization_by_provider_id("stock_org_b", user.id)
    return a.id, b.id


async def test_seules_les_cles_du_prefixe_reviennent_triees_et_cloisonnees(db_session):
    a, b = await _organisations(db_session)
    for cle in ("MARK_T:2", "MARK_T:1", "MARK_TX:9", "AUTRE:1"):
        await db_session.upsert_configuration(a, cle, {"v": cle})
    await db_session.upsert_configuration(b, "MARK_T:1", {"v": "autre organisation"})
    trouvees = await stock.lister(a, "MARK_T:")
    assert [cle for cle, _ in trouvees] == ["MARK_T:1", "MARK_T:2"]
    assert [valeur["v"] for _, valeur in await stock.lister(b, "MARK_T:")] == ["autre organisation"]


async def test_le_souligne_et_le_pour_cent_du_prefixe_sont_des_caracteres_pas_des_jokers(db_session):
    a, _ = await _organisations(db_session)
    for cle in ("MARK_BIBLIO:x", "MARKXBIBLIO:y", "A%B:1", "AZZB:2", "A\B:3", "AZB:4"):
        await db_session.upsert_configuration(a, cle, {"v": 1})
    assert [c for c, _ in await stock.lister(a, "MARK_BIBLIO:")] == ["MARK_BIBLIO:x"]  # « _ » ne vaut pas « X »
    assert [c for c, _ in await stock.lister(a, "A%B:")] == ["A%B:1"]  # « % » ne vaut pas « ZZ »
    assert [c for c, _ in await stock.lister(a, "A\B:")] == ["A\B:3"]  # l'échappement lui-même est un caractère


async def test_la_liste_de_la_bibliotheque_compte_les_agents_en_une_seule_lecture(monde, monkeypatch):
    from api.services.builder.bibliotheque import service

    lectures = []
    vrai_lister = stock.lister

    async def lister(organisation, prefixe):
        lectures.append(prefixe)
        return await vrai_lister(organisation, prefixe)

    monkeypatch.setattr(service.stock, "lister", lister)
    monkeypatch.setattr(service, "organisation_bibliotheque", lambda: 1)
    assert await service._nombres_d_agents() == {}
    assert lectures == [service.PREFIXE_USAGE]
