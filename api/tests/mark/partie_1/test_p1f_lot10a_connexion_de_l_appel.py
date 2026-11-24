"""[.mark] Plan final Partie 1, lot 10 (A10) : la connexion à la base de l'appel se rouvre à CHAQUE coupure, et quand elle reste bloquée dans une transaction.

Avant : rouverte UNE fois par appel, puis la panne définitive (« coupée deux fois ») : un appel de dix minutes qui voit la base redémarrer deux fois perdait tous ses outils. Une connexion
restée dans une transaction ouverte (un geste interrompu) servait le geste suivant telle quelle, sans que rien ne le dise. Maintenant : chaque coupure est suivie d'une réouverture ; la panne n'est
que celle de la réouverture elle-même (base injoignable).
"""

from __future__ import annotations

import pytest

from api.db.bases_clients.connexion import BaseClientIndisponible
from api.services.restauration import source_commande
from api.services.restauration.appel_et_memoire import memoire_de_l_appel as M
from api.tests.mark.partie_1.test_l05_latence import appel_suivi  # noqa: F401


async def _geste(ctx) -> None:
    async with source_commande.ouvrir_la_source(ctx) as s:
        assert (await s.etat("emporter"))["ouvert"] in (True, False)


async def test_chaque_coupure_est_suivie_d_une_reouverture_sans_limite(appel_suivi):  # noqa: F811
    monde, ctx, ouvertes = await appel_suivi()
    await _geste(ctx)
    for coupure in range(1, 4):
        ouvertes[-1].terminate()
        await _geste(ctx)  # avant : la deuxième coupure levait ``BaseClientIndisponible``
        assert len(ouvertes) == 1 + coupure
    await M.fermer(ctx.run_id)


async def test_une_connexion_restee_dans_une_transaction_est_rouverte(appel_suivi):  # noqa: F811
    monde, ctx, ouvertes = await appel_suivi()
    await _geste(ctx)
    await ouvertes[0].execute("BEGIN")  # un geste interrompu a laissé la transaction ouverte
    assert ouvertes[0].is_in_transaction()
    await _geste(ctx)
    assert len(ouvertes) == 2 and ouvertes[0].is_closed() and not ouvertes[1].is_in_transaction()  # avant : le même geste continuait dans la transaction orpheline
    await M.fermer(ctx.run_id)


async def test_la_panne_est_celle_de_la_reouverture_elle_meme(appel_suivi, monkeypatch):  # noqa: F811
    monde, ctx, ouvertes = await appel_suivi()
    await _geste(ctx)
    ouvertes[0].terminate()

    async def injoignable(nom_base):
        raise BaseClientIndisponible("la base ne répond pas")

    monkeypatch.setattr(M, "CONNECTER", injoignable)
    with pytest.raises(BaseClientIndisponible):
        await _geste(ctx)
