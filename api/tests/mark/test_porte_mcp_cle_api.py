"""[.mark] Revue de contrôle, point 3 (B1) : la porte MCP marque l'accès « par clé d'API ».

| Test | Ce qu'il prouve |
|---|---|
| marquage | un appel MCP par clé rend un compte ``par_cle_api`` : plus de rôle d'équipe (``est_membre_de_l_equipe`` faux) |
| exemption | seule une clé du Labo (créée par un membre) écrit dans la bibliothèque par MCP ; une clé de client est refusée |
| routes HTTP | la même clé par une route HTTP n'a pas l'exemption (``par_porte_mcp`` remis à faux) |
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.mcp_server import auth
from api.services.builder.bibliotheque import droits
from api.services.builder.bibliotheque.service import ErreurBibliotheque

LABO = 7


def _compte(org):
    return SimpleNamespace(id=3, selected_organization_id=org)


async def _par_mcp(compte):
    with (
        patch.object(auth, "get_http_headers", return_value={"x-api-key": "cle-de-test"}),
        patch.object(auth, "_handle_api_key_auth", AsyncMock(return_value=compte)),
    ):
        return await auth.authenticate_mcp_request()


@pytest.fixture(autouse=True)
def _labo():
    with (
        patch.object(droits, "organisation_bibliotheque", return_value=LABO),
        patch.object(droits.db_client, "is_user_member_of_organization", AsyncMock(return_value=True), create=True),
    ):
        yield


async def test_la_porte_mcp_marque_l_acces_par_cle_et_retire_le_role_d_equipe():
    compte = await _par_mcp(_compte(LABO))
    assert compte.par_cle_api is True
    assert await droits.est_membre_de_l_equipe(compte) is False


async def test_exemption_explicite_seule_la_cle_du_labo_ecrit_dans_la_bibliotheque_par_mcp():
    await droits.exiger_l_equipe_au_labo(await _par_mcp(_compte(LABO)))  # ne lève pas
    with pytest.raises(ErreurBibliotheque) as e:
        await droits.exiger_l_equipe_au_labo(await _par_mcp(_compte(LABO + 1)))
    assert e.value.statut == 403


async def test_la_meme_cle_par_une_route_http_n_a_pas_l_exemption():
    from api.services.equipe_mark import acces

    compte = await _par_mcp(_compte(LABO))
    # Le même objet de compte sert une requête HTTP par clé : appliquer_acces remet le marquage à zéro.
    with patch.object(acces, "rafraichir_labo", create=True), patch("api.services.equipe_mark.espaces.rafraichir_labo", AsyncMock()), patch.object(
        acces, "acces_de", AsyncMock(return_value=None)
    ):
        connexion = SimpleNamespace(headers={}, url=SimpleNamespace(path="/api/v1/x"))
        try:
            await acces.appliquer_acces(connexion, compte, par_cle_api=True)
        except Exception:
            pass
    assert compte.par_porte_mcp is False
    with pytest.raises(ErreurBibliotheque):
        await droits.exiger_l_equipe_au_labo(compte)
