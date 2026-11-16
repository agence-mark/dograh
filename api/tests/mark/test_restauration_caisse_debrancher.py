"""[.mark] Module Restauration, lot 13 (M6) : débrancher et resynchroniser une caisse.

| Test | Ce qu'il prouve |
|---|---|
| sans caisse | 401 sans clé ; 409 sans liaison (débrancher et resynchroniser) ; 404 pour un établissement d'une autre organisation, rien n'est écrit |
| débrancher | la liaison, l'état de la caisse et la référence du jeton partent ; le jeton du coffre est désactivé ; le point de vente est libéré (un autre établissement peut le prendre) ; la carte lue est gardée ; événement ``caisse.liaison`` |
| resynchroniser | la caisse est relue (état changé chez elle, repris ici) ; une caisse en panne : la liaison dit « erreur » et le bilan porte le code, jamais le texte |
"""

from __future__ import annotations

import pytest

from api.db import db_client
from api.db.bases_clients import connexion as schema
from api.db.bases_clients import restauration
from api.db.bases_clients import restauration_liaison as lia
from api.services.restauration import caisse as service_caisse
from api.services.restauration.prises import hubrise_liaison as hl
from api.tests.mark.equipe_commun import client_http, sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import _cle, seconde_base  # noqa: F401
from api.tests.mark.test_restauration_caisse_routes import (  # noqa: F401
    RACINE,
    _brancher,
    _caisse_enregistree,
    _etablissements_propres,
    _evenements,
    application_configuree,
)
from api.tests.mark.test_restauration_flux import _deux_organisations_avec_des_etablissements


async def test_sans_caisse_ou_hors_organisation_rien_n_est_fait(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    etab = cas.sites_a[0]
    async with client_http() as c:
        assert (await c.delete(f"{RACINE}/{etab}/caisse")).status_code == 401
        assert (await c.post(f"{RACINE}/{etab}/caisse/resynchroniser")).status_code == 401
        assert (await c.delete(f"{RACINE}/{etab}/caisse", headers=_cle(cas.cle_a))).status_code == 409
        assert (await c.post(f"{RACINE}/{etab}/caisse/resynchroniser", headers=_cle(cas.cle_a))).status_code == 409
        chez_b = max(cas.sites_a + cas.sites_b) + 1000
        assert (await c.delete(f"{RACINE}/{chez_b}/caisse", headers=_cle(cas.cle_a))).status_code == 404
        assert (await c.post(f"{RACINE}/{chez_b}/caisse/resynchroniser", headers=_cle(cas.cle_a))).status_code == 404


async def test_debrancher_retire_la_liaison_le_jeton_et_garde_la_carte(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas = await _etablissements_propres(db_session, seconde_base)
    etab = cas.sites_a[0]
    caisse = _caisse_enregistree(pdv="pdv-debranche-" + str(cas.a))
    await _brancher(cas, etab, cas.a, cas.base_a, caisse, cas.admin.id)
    base = await schema.connecter(cas.base_a)
    try:
        reference = await lia.acces(base, etab)
        assert reference and await restauration.etat_caisse(base, etab) is not None
        produits_avant = len((await restauration.carte_du_restaurant(base, etab))["produits"])
    finally:
        await base.close()
    async with client_http() as c:
        assert (await c.delete(f"{RACINE}/{etab}/caisse", headers=_cle(cas.cle_a))).json() == {"ok": True}
        assert (await c.delete(f"{RACINE}/{etab}/caisse", headers=_cle(cas.cle_a))).status_code == 409  # déjà débranchée
        fiche = (await c.get(f"{RACINE}/{etab}/caisse", headers=_cle(cas.cle_a))).json()
    assert (fiche["prise"], fiche["etat"], fiche["etat_caisse"]) == ("portail", "aucune", None)
    base = await schema.connecter(cas.base_a)
    try:
        assert await lia.liaison(base, etab) is None and await lia.acces(base, etab) is None
        assert len((await restauration.carte_du_restaurant(base, etab))["produits"]) == produits_avant > 0  # rien n'est supprimé
    finally:
        await base.close()
    assert await db_client.get_credential_by_uuid(reference, cas.a) is None or not (await db_client.get_credential_by_uuid(reference, cas.a)).is_active
    assert await db_client.retrouver_le_point_de_vente("hubrise", "pdv-debranche-" + str(cas.a)) is None
    assert ("caisse.liaison", {"etat": "rompue"}) in await _evenements(cas.a, etab)


async def test_resynchroniser_relit_la_caisse_et_dit_l_erreur_par_un_code(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas = await _etablissements_propres(db_session, seconde_base)
    etab = cas.sites_a[0]
    caisse = _caisse_enregistree(pdv="pdv-resynchro-" + str(cas.a))
    await _brancher(cas, etab, cas.a, cas.base_a, caisse, cas.admin.id)
    base = await schema.connecter(cas.base_a)
    try:
        await lia.poser_etat_de_la_caisse(base, etab, {"mode": "normal", "minutes_en_plus": 0, "reprise": None, "temps_preparation": 10})
        bilan = await service_caisse.resynchroniser(base, cas.a, etab, nom_base=cas.base_a, transport=caisse)
        assert bilan is not None and bilan["erreur"] is None
        assert (await restauration.etat_caisse(base, etab))["minutes_en_plus"] == 15  # l'état de la caisse est repris
        assert (await lia.liaison(base, etab))["etat"] == "ok"
        en_panne = _caisse_enregistree(callback="jeton_faux", pdv="pdv-resynchro-" + str(cas.a))
        bilan = await service_caisse.resynchroniser(base, cas.a, etab, nom_base=cas.base_a, transport=en_panne)
        assert bilan["erreur"] == "jeton_refuse"
        liaison = await lia.liaison(base, etab)
        assert (liaison["etat"], liaison["derniere_erreur"]) == ("rompue", "jeton_refuse")
    finally:
        await base.close()
