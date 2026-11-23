"""[.mark] Module Restauration, lot 26, M10 : une commande CRÉÉE DANS LA CAISSE (sans notre numéro) entre au classeur, source « caisse », sans appel, et n'est jamais renvoyée.

La caisse est un transport ENREGISTRÉ (réponse 21 de HubRise, sans ``private_ref``).

| Test | Ce qu'il prouve |
|---|---|
| enregistrée | le message d'une commande inconnue la crée : source caisse, sans appel, lignes avec leurs suppléments, total de la caisse, statut de la caisse, journal « caisse », événement ``commande.creee`` |
| rejeu | le même message ou un autre message pour la même commande ne la double pas ; un statut plus loin la fait avancer par le chemin fermé |
| jamais renvoyée | l'envoi et la reprise l'écartent : la caisse n'est pas appelée |
| cloisonnement | une commande qui porte un numéro inconnu ici, ou dont le mode est inconnu, n'écrit rien |
"""

from __future__ import annotations

import uuid

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import restauration_liaison as lia
from api.services.restauration.caisse.prises import hubrise_reception as hr
from api.services.restauration.caisse.prises import hubrise_traduction as ht
from api.services.restauration.caisse.prises.envoi import envoyer_une_commande
from api.tests.mark.equipe_commun import sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import seconde_base  # noqa: F401
from api.tests.mark.test_restauration_caisse_routes import _caisse_enregistree, _evenements, application_configuree  # noqa: F401
from api.tests.mark.test_restauration_hubrise_reception import _etablissement_branche, _message, _ordre


def _de_la_caisse(ref: str = "caisse-1", **plus) -> dict:
    return _ordre("21-commande-acceptee.json", **{"id": ref, "private_ref": None, **plus})


async def _lignes(base: str, sql: str, *args):
    c = await schema.connecter(base)
    try:
        return await c.fetch(sql, *args)
    finally:
        await c.close()


async def test_une_commande_creee_dans_la_caisse_entre_au_classeur_sans_appel(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    pdv = "pdv-caisse-" + uuid.uuid4().hex[:6]
    cas, etab = await _etablissement_branche(db_session, seconde_base, pdv)
    caisse = _caisse_enregistree(pdv=pdv, ordres={"caisse-1": _de_la_caisse()})
    r = await hr.traiter_le_message(None, _message("m-k-1", location_id=pdv, order_id="caisse-1"), transport=caisse)
    assert r == {"statut": "traite", "effet": "commande_de_la_caisse"}
    (c,) = await _lignes(cas.base_a, "SELECT * FROM mark.resto_commande WHERE site_id = $1", etab)
    assert (c["cree_par"], c["appel_id"], c["statut"], c["mode"], c["ref_fournisseur"], c["cle_doublon"]) == ("caisse", None, "acceptee", "emporter", "caisse-1", "caisse:caisse-1")
    liaison = await schema.connecter(cas.base_a)
    try:
        assert await lia.ref_de_la_commande_de_la_caisse(liaison, etab, c["numero"]) == "caisse-1"  # Pierre 13 : l'annulation la retrouve par SON identifiant
    finally:
        await liaison.close()
    assert (c["sous_total"], c["frais"], c["total"], c["telephone"]) == (1900, 0, 1900, None)  # 12,50 + 1,50 de supplément + 2 x 2,50 : le total de la caisse
    lignes = await _lignes(cas.base_a, "SELECT * FROM mark.resto_commande_ligne WHERE numero = $1 ORDER BY rang", c["numero"])
    assert [(l["code_caisse"], l["prix_unitaire"], l["quantite"], l["note"], list(l["retires"])) for l in lignes] == [
        ("REINE-S", 1400, 1, "Bien cuite", ["Sans olives"]), ("COCA-33", 250, 2, None, [])]
    journal = await _lignes(cas.base_a, "SELECT source FROM mark.resto_journal WHERE objet = 'resto_commande' AND ligne_id = $1 AND operation = 'insert'", str(c["numero"]))
    assert [j["source"] for j in journal] == ["caisse"]
    creees = [d for t, d in await _evenements(cas.a, etab) if t == "commande.creee"]
    assert [(d["numero"], d["mode"], d["total"]) for d in creees] == [(str(c["numero"]), "emporter", 1900)]
    # le Rush et Commandes lisent la même table : la commande y est avec sa source
    assert await _lignes(cas.base_a, "SELECT 1 FROM mark.resto_commande WHERE site_id = $1 AND cree_par = 'caisse' AND statut NOT IN ('annulee', 'refusee', 'echec')", etab)


async def test_rejouee_elle_n_est_pas_doublee_et_un_statut_plus_loin_la_fait_avancer(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    pdv = "pdv-rejeu-" + uuid.uuid4().hex[:6]
    cas, etab = await _etablissement_branche(db_session, seconde_base, pdv)
    caisse = _caisse_enregistree(pdv=pdv, ordres={"caisse-1": _de_la_caisse()})
    await hr.traiter_le_message(None, _message("m-r-1", location_id=pdv, order_id="caisse-1"), transport=caisse)
    assert (await hr.traiter_le_message(None, _message("m-r-1", location_id=pdv, order_id="caisse-1"), transport=caisse))["statut"] == "deja_vu"
    # un autre message pour la même commande, la caisse la dit maintenant « en préparation »
    plus_loin = _caisse_enregistree(pdv=pdv, ordres={"caisse-1": _de_la_caisse(status="in_preparation")})
    assert (await hr.traiter_le_message(None, _message("m-r-2", location_id=pdv, order_id="caisse-1"), transport=plus_loin))["effet"] == "statut"
    lignes = await _lignes(cas.base_a, "SELECT statut FROM mark.resto_commande WHERE site_id = $1", etab)
    assert [l["statut"] for l in lignes] == ["en_preparation"]
    assert len([1 for t, _ in await _evenements(cas.a, etab) if t == "commande.creee"]) == 1
    # enregistrer deux fois la même commande directement : une seule
    c = await schema.connecter(cas.base_a)
    try:
        assert await lia.enregistrer_commande_de_la_caisse(c, etab, "caisse-1", ht.commande_de_hubrise(_de_la_caisse()), "recue") is None
    finally:
        await c.close()


async def test_une_commande_de_la_caisse_n_est_jamais_renvoyee_a_la_caisse(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    pdv = "pdv-jamais-" + uuid.uuid4().hex[:6]
    cas, etab = await _etablissement_branche(db_session, seconde_base, pdv)
    caisse = _caisse_enregistree(pdv=pdv, ordres={"caisse-1": _de_la_caisse(status="new")})
    await hr.traiter_le_message(None, _message("m-j-1", location_id=pdv, order_id="caisse-1"), transport=caisse)
    c = await schema.connecter(cas.base_a)
    try:
        numero = await c.fetchval("SELECT numero FROM mark.resto_commande WHERE site_id = $1", etab)
        # même au statut où une commande à nous serait reprise, elle ne l'est pas
        await c.execute("UPDATE mark.resto_commande SET statut = 'envoyee', maj_le = maj_le - interval '2 hours' WHERE numero = $1", numero)
        assert await lia.commandes_a_reprendre(c, etab) == []

        class Prise:
            nom = "essai"
            capacites = None

            async def envoyer_commande(self, commande):  # pragma: no cover - ne doit jamais être appelée
                raise AssertionError("une commande de la caisse a été renvoyée à la caisse")

            async def chercher_commande(self, numero):  # pragma: no cover
                raise AssertionError("une commande de la caisse a été cherchée pour être renvoyée")

        assert (await envoyer_une_commande(c, etab, Prise(), numero)).issue == "fait"
    finally:
        await c.close()


async def test_un_numero_inconnu_ici_ou_un_mode_inconnu_n_ecrit_rien(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    pdv = "pdv-clos-" + uuid.uuid4().hex[:6]
    cas, etab = await _etablissement_branche(db_session, seconde_base, pdv)
    etrangere = _caisse_enregistree(pdv=pdv, ordres={"x-1": _de_la_caisse("x-1", private_ref=str(uuid.uuid4()))})
    assert (await hr.traiter_le_message(None, _message("m-c-1", location_id=pdv, order_id="x-1"), transport=etrangere))["effet"] == "commande_inconnue"
    sans_mode = _caisse_enregistree(pdv=pdv, ordres={"x-2": _de_la_caisse("x-2", service_type="inconnu")})
    assert (await hr.traiter_le_message(None, _message("m-c-2", location_id=pdv, order_id="x-2"), transport=sans_mode))["effet"] == "commande_de_la_caisse_sans_mode"
    assert await _lignes(cas.base_a, "SELECT 1 FROM mark.resto_commande WHERE site_id = $1", etab) == []
