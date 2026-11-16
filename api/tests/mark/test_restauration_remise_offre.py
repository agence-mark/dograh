"""[.mark] Module Restauration, lot 26 (M38) : les offres de remise dites par l'agent et leur acceptation (migration 034).

| Test | Ce qu'il prouve |
|---|---|
| dite | une offre dite est notée ; redite dans le même appel, rien de plus (rejouable) ; sans appel connu, chaque mention compte |
| acceptée | seules les offres dites dans cet appel passent à « acceptée » ; une remise appliquée sans avoir été dite ne compte pas ; sans appel, rien |
| cloisonnement | la remise d'un autre établissement n'est jamais notée |
| écran | ``remises_pour_l_ecran`` rend ``dite`` et ``acceptee`` de chaque remise |
"""

from __future__ import annotations

from api.db.bases_clients.restauration_remise_ecran import remises_pour_l_ecran
from api.db.bases_clients.restauration_remise_offre import compter_les_offres, noter_l_acceptation, noter_une_offre_dite
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401


async def _remise(c, site, nom):
    return await c.fetchval("INSERT INTO mark.resto_remise (site_id, nom, mecanisme, etat) VALUES ($1, $2, 'pourcentage', 'active') RETURNING id", site, nom)


async def test_une_offre_dite_est_notee_une_fois_par_appel(commerce):  # noqa: F811
    c, a = commerce.c, commerce.a
    r = await _remise(c, a, "R1")
    assert await noter_une_offre_dite(c, a, r, "appel-1") is True
    assert await noter_une_offre_dite(c, a, r, "appel-1") is False  # rejouable sans effet double
    assert await noter_une_offre_dite(c, a, r, "appel-2") is True
    assert await noter_une_offre_dite(c, a, r) is True and await noter_une_offre_dite(c, a, r, "  ") is True  # sans appel connu : chaque mention compte
    assert (await compter_les_offres(c, a))[r] == (4, 0)


async def test_seules_les_offres_dites_dans_l_appel_sont_acceptees(commerce):  # noqa: F811
    c, a = commerce.c, commerce.a
    r1, r2 = await _remise(c, a, "R1"), await _remise(c, a, "R2")
    await noter_une_offre_dite(c, a, r1, "appel-1")
    await noter_une_offre_dite(c, a, r1, "appel-2")
    assert await noter_l_acceptation(c, a, "appel-1", [r1, r2]) == 1  # r2 n'a pas été dite : pas comptée
    assert await noter_l_acceptation(c, a, "appel-1", [r1]) == 0  # déjà acceptée : rien de plus
    assert await noter_l_acceptation(c, a, None, [r1]) == 0  # sans appel connu : rien
    assert await noter_l_acceptation(c, a, "appel-1", []) == 0
    assert await compter_les_offres(c, a) == {r1: (2, 1)}


async def test_la_remise_d_un_autre_etablissement_n_est_jamais_notee(commerce):  # noqa: F811
    c = commerce.c
    b = await c.fetchval("SELECT id FROM mark.site WHERE id <> $1 LIMIT 1", commerce.a)
    r_b = await _remise(c, b, "RB")
    assert await noter_une_offre_dite(c, commerce.a, r_b, "appel-1") is False
    assert await compter_les_offres(c, commerce.a) == {} and await compter_les_offres(c, b) == {}


async def test_l_ecran_rend_dite_et_acceptee(commerce):  # noqa: F811
    c, a = commerce.c, commerce.a
    r = await _remise(c, a, "R1")
    sans = await _remise(c, a, "R2")
    await noter_une_offre_dite(c, a, r, "appel-1")
    await noter_une_offre_dite(c, a, r, "appel-2")
    await noter_l_acceptation(c, a, "appel-2", [r])
    lignes = {x["id"]: x for x in await remises_pour_l_ecran(c, a)}
    assert (lignes[r]["dite"], lignes[r]["acceptee"]) == (2, 1)
    assert (lignes[sans]["dite"], lignes[sans]["acceptee"]) == (0, 0)
