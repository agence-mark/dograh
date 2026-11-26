"""[.mark] Lot 8a : ce que la restauration fait quand le moteur d'appel joue les crochets des modules (``services/modules/crochets.py``).

Le moteur (voix et clavier) ne nomme plus la restauration : il joue les crochets déclarés au registre (``modules/registre.RESTAURATION``).

- ``inscrire`` (au démarrage de l'API ET de l'ouvrier) : branche l'allergie et la lecture d'un article sur le moteur commun de la commande ;
- ``au_decroche`` : ``CONTEXTE`` l'ouverture lue (horaires et état de la caisse) ; ``CANAL`` le direct des appels (lot 21) ; ``MONTAGE`` le chargement de l'appel
  (lot 5 : jamais attendu à la voix, la phrase d'accueil ne l'attend pas ; attendu, borné, au clavier qui n'a pas de phrase d'accueil) ;
- ``fin_du_tour`` (clavier) : l'appel gardé entre deux tours, fermé à la fin de la partie ;
- ``fin_de_l_appel`` : la commande de l'appel envoyée en caisse si elle a été accordée (§ 17, ``caisse/envoi_a_la_fin``), le direct fermé (``appel.fini``), puis la connexion
  de l'appel à la base du client. Sans effet double si rejouée.
"""

from __future__ import annotations

from loguru import logger

from api.services.modules.crochets import CANAL, CONTEXTE, MONTAGE, Decroche, FinDeLAppel, FinDeTour
from api.services.restauration.appel_et_memoire import memoire_de_l_appel
from api.services.restauration.appel_et_memoire.direct_appel import DirectDeLAppel, preparer_le_direct
from api.services.restauration.appel_et_memoire.etiquettes import injecter_l_ouverture_de_la_caisse
from api.services.restauration.caisse.envoi_a_la_fin import envoyer_la_commande_de_l_appel

# Le direct de chaque appel à la voix (clé : l'identifiant de l'exécution), de son décroché à sa fin ; vidé par ``fin_de_l_appel``.
_DIRECTS: dict[str, DirectDeLAppel] = {}


def inscrire() -> None:
    from api.services.commande.moteur.socle import enregistrer_metier
    from api.services.restauration.carte_et_allergenes import allergie_de_la_commande as allergie
    from api.services.restauration.carte_et_allergenes import voir_un_article

    enregistrer_metier(
        prealable=allergie.allergie_sans_reponse,
        faits_a_donner=allergie.poser_les_faits_de_l_allergie,
        noter_les_faits_donnes=allergie.noter_les_faits_a_dire,
        voir_un_article=voir_un_article.voir_produit,
    )


async def au_decroche(d: Decroche) -> None:
    if d.moment == CONTEXTE:
        d.contexte = await injecter_l_ouverture_de_la_caisse(d.contexte, d.run_configs, d.organization_id, d.workflow_id, d.reglages_annonce, d.direction)
    elif d.moment == CANAL:
        direct = await preparer_le_direct(
            organisation_id=d.organization_id,
            workflow_id=d.workflow_id,
            workflow_run_id=d.run_id,
            run_configs=d.run_configs,
            cle_etablissement=d.cle_de_l_etablissement,
            contexte=d.contexte,
        )
        if direct is not None:
            d.canal = direct.composer(d.canal)
            direct.commencer()
            _DIRECTS[str(d.run_id)] = direct
    elif d.moment == MONTAGE:
        if d.au_clavier:
            await memoire_de_l_appel.charger_au_clavier(d.organization_id, d.run_id, d.run_configs, d.contexte, d.fiche)
        else:
            memoire_de_l_appel.charger_au_decroche(d.organization_id, d.run_id, d.run_configs, d.contexte, d.fiche)
    else:
        logger.error(f"[.mark] Pick-up hook: unknown moment {d.moment!r}")


async def fin_du_tour(f: FinDeTour) -> None:
    await memoire_de_l_appel.fin_du_tour_au_clavier(f.run_id, termine=f.termine)


async def fin_de_l_appel(f: FinDeLAppel) -> None:
    direct = _DIRECTS.pop(str(f.run_id), None)
    try:
        await envoyer_la_commande_de_l_appel(f.organization_id, f.run_id, f.fiche)  # ne lève jamais
        if direct is not None:
            await direct.fermer(f.fiche)
    finally:
        await memoire_de_l_appel.fermer(f.run_id)
