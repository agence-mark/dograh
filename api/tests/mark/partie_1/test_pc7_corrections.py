"""[.mark] Chantier Partie 1 : les corrections du point de contrôle du lot 7 (SA-C), une par défaut trouvé au clavier.

Chacune a été vue rouge sur ``dbd209f1`` (le code joué au point de contrôle) avant sa correction.
"""

from __future__ import annotations

import re
from pathlib import Path

API = Path(__file__).resolve().parents[3]


def test_l_image_ecrit_la_pile_d_un_plantage_natif():
    """Défaut 1 (19/11, 16:05 et 16:09 UTC) : deux segfaults du serveur sans aucune pile Python. L'image allume ``faulthandler``
    pour chaque processus Python (uvicorn, arq, ari) : la prochaine fois, la pile de chaque fil est écrite dans les journaux."""
    dockerfile = (API / "Dockerfile").read_text(encoding="utf-8")
    image_finale = dockerfile.split("AS runner", 1)[1]
    assert re.search(r"^ENV PYTHONFAULTHANDLER=1\s*$", image_finale, re.M)


def test_au_clavier_la_reservation_du_labo_est_jouee_pour_de_vrai(monkeypatch):
    """Défaut 2 (« [rejeu] fiche simulé : rien n'est parti ») : la réservation n'avait pas de ``sans_tiers``, sa fiche restait simulée en
    essai et l'agent ne pouvait rien réserver au clavier. Le classeur (la base du client dans le fork) ne parle à aucun client pour
    l'organisation Labo, comme la caisse de démo ; chez un client c'est son vrai cahier : simulé. Une source qui ne dit rien : simulée."""
    import asyncio
    from types import SimpleNamespace

    from api.services.integrations.connectors.catalogue import connecteur
    from api.services.reservation import source as registre
    from api.services.restauration.caisse_demo import garde

    async def labo():
        return 7

    monkeypatch.setattr(garde, "id_du_labo", labo)
    reservation = connecteur("reservation")
    assert reservation.sans_tiers is not None and connecteur("commande").sans_tiers is not None

    def lu(organisation, reglages=None):
        return asyncio.run(reservation.sans_tiers(SimpleNamespace(organization_id=organisation, reglages=reglages or {})))

    assert lu(7) is True
    assert lu(8) is False and lu(None) is False
    assert lu(7, {"source": "classeur"}) is True
    monkeypatch.setitem(registre._SOURCES, "logiciel_du_client", registre._SOURCES["classeur"])
    assert lu(7, {"source": "logiciel_du_client"}) is False


def test_le_moteur_donne_les_reglages_de_l_outil_a_la_question(monkeypatch):
    """La source d'une réservation se lit dans le réglage de SON outil : la question posée au geste les porte."""
    import asyncio
    from types import SimpleNamespace

    from api.services.integrations.connectors import outil

    vus = []

    async def sans_tiers(ctx):
        vus.append(ctx.reglages)
        return True

    monkeypatch.setattr(outil, "connecteur_interne", lambda tool: SimpleNamespace(sans_tiers=sans_tiers))
    monkeypatch.setattr(outil, "configurations_de_l_etape", lambda manager: {})

    async def org():
        return 1

    manager = SimpleNamespace(_engine=SimpleNamespace(), get_organization_id=org)
    tool = SimpleNamespace(definition={"config": {"connecteur": "reservation", "action": "fiche", "reglages": {"source": "classeur"}}})
    assert asyncio.run(outil.sans_tiers_de(manager, tool)()) is True
    assert vus == [{"source": "classeur"}]


async def test_aucun_tour_muet_quand_le_modele_ne_rend_rien(essai_de):
    """Défaut 3 (``pc7-conv2-hors-zone``, tour 1, appel 28) : la fiche rend le hors zone et la proposition offerte ; le second passage du
    modèle ne rend rien (4 jetons, relance sans flux vide aussi) : le flux vérifié ne contrôlait qu'un texte, rien n'était dit. Sur une étape
    qui porte la fiche, le silence du modèle au bout des passes est remplacé par la phrase du code (``repli_dit_par_le_code``)."""
    from types import SimpleNamespace

    from api.services.actions_communes import parole as PAROLE
    from api.services.pipecat.reponse_avalee import RepliqueVerifiee
    from api.services.workflow import parole_de_la_fiche as PF

    e = await essai_de("casa-italia")
    e.dit("Deux reines normales, livrées au 8 rue Solférino à Compiègne")
    e.montrer()
    r = await e.fiche(ajouter=[{"article": "pizza reine", "quantite": 2, "variante": "Normale"}], mode_de_retrait="livraison",
                      adresse="8 Rue Solférino", commune="Compiègne", _montrer=False)
    assert (r.get("faits") or {}).get("fait_bloquant", {}).get("statut_du_module") == "HORS_ZONE", r
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "C'est entendu. Livraison ou retrait ?"})
    assert d.mode == PAROLE.SECOND_PASSAGE, d

    async def vide():
        if False:
            yield None

    async def jamais(_retenue):
        raise AssertionError("aucune relance : le silence est déjà au bout des passes")

    v = PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=e.fiche_de_l_appel))
    flux = RepliqueVerifiee(vide(), lambda t: v.controler(t), jamais, None, lambda t: v.controler_la_relance(t),
                            lambda: v.controler_le_silence())
    dit = "".join(m.choices[0].delta.content or "" for m in [m async for m in flux])
    assert dit.strip(), dit
    # Point de contrôle du lot 7, suite (coordinateur) : la personne apprend qu'on ne la livre pas. Le fait bloquant se dit d'abord (la phrase du
    # module : la raison et les communes livrées), puis ce qu'on propose (l'autre mode) ; jamais la proposition de vente en plus seule.
    hors_zone = next(x for x in r["resultats"] if x.get("statut_du_module") == "HORS_ZONE")
    assert dit.startswith("Nous ne livrons pas à Compiègne."), dit
    assert all(c in dit for c in hors_zone["faits"]["communes_livrees"]), dit
    assert dit.endswith("À emporter ?"), dit
    assert "propose" not in dit, dit


async def test_le_fait_bloquant_d_une_fiche_d_avant_n_est_jamais_redit(essai_de):
    """La phrase du fait bloquant vaut pour le tour de sa fiche : au tour suivant, le repli revient à la question en attente."""
    from api.services.actions_communes import repli as R
    from api.services.workflow import parole_de_la_fiche as PF

    e = await essai_de("casa-italia")
    await e.tour("Deux reines normales, livrées au 8 rue Solférino à Compiègne", ajouter=[{"article": "pizza reine", "quantite": 2, "variante": "Normale"}],
                 mode_de_retrait="livraison", adresse="8 Rue Solférino", commune="Compiègne")
    assert R.phrase_du_fait_bloquant(e.fiche_de_l_appel)
    e.dit("Ah bon")
    p = PF.dossier_de_la_parole(e.fiche_de_l_appel)
    assert R.phrase_du_fait_bloquant(e.fiche_de_l_appel) is None
    assert R.repli_dit_par_le_code(p, None, e.fiche_de_l_appel) == R.repli_dit_par_le_code(p), p.get("question")
    r = await e.tour("à emporter alors", mode_de_retrait="emporter")
    assert R.phrase_du_fait_bloquant(e.fiche_de_l_appel) is None, r


def test_le_moteur_branche_le_silence_sur_le_flux_verifie():
    code = (API / "services" / "pipecat" / "reponse_avalee.py").read_text(encoding="utf-8")
    assert "RepliqueVerifiee(repris, controle, relancer_la_replique, avant_outil, la_relance, le_silence)" in code


def test_l_image_donne_ses_autorites_de_certification():
    """Défaut 1, cause trouvée (pile de faulthandler, 19/11 16:46 UTC) : deux fils d'anyio dans ``truststore._openssl._configure_context`` en même
    temps, qui recharge les certificats dans le contexte TLS partagé à chaque poignée de main. L'image donne le fichier des autorités."""
    dockerfile = (API / "Dockerfile").read_text(encoding="utf-8")
    image_finale = dockerfile.split("AS runner", 1)[1]
    assert re.search(r"^ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates\.crt\s*$", image_finale, re.M)


def test_avec_le_fichier_des_autorites_aucun_client_ne_prend_truststore(monkeypatch):
    """Avec ``SSL_CERT_FILE``, le client d'openai (httpx2, httpcore2) crée un contexte TLS standard, ses certificats chargés une fois ; sans elle, un
    ``truststore.SSLContext`` (celui qui a planté)."""
    import ssl

    import certifi
    import httpcore2
    import truststore
    from httpx2._config import create_ssl_context

    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    assert isinstance(create_ssl_context(), truststore.SSLContext)  # la forme qui a planté, sans la variable
    monkeypatch.setenv("SSL_CERT_FILE", certifi.where())
    for contexte in (create_ssl_context(), httpcore2.default_ssl_context()):
        assert isinstance(contexte, ssl.SSLContext) and not isinstance(contexte, truststore.SSLContext), type(contexte)
        assert contexte.cert_store_stats()["x509_ca"] > 0
