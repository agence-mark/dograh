"""[.mark] Module Restauration, lot 10 : la SURVEILLANCE des tickets de l'imprimante (tâche planifiée, chaque minute).

L'imprimante interroge elle-même le serveur : rien ne nous prévient quand elle se tait, quand le papier manque ou quand la confirmation d'une impression se perd. Cette tâche, pour
chaque établissement qui a une imprimante :

1. remet en file un ticket ``recupere`` ou en ``erreur`` depuis plus de ``MINUTES_SANS_CONFIRMATION`` minutes (la confirmation s'est perdue, ou le papier est revenu), jusqu'à
   ``TENTATIVES_MAX`` fois : le repli prévu (la fiche dit « la confirmation de l'impression peut se perdre »). Risque connu et assumé : une confirmation perdue d'un ticket
   PAS en erreur peut le faire sortir deux fois, ce que la cuisine préfère à une commande jamais vue ;
2. alerte UNE fois (``alerte_le``) un ticket libéré, non imprimé, depuis plus de ``alerte_sans_reponse_min`` minutes (T-09, 3 par défaut, réglable) : événement ``ticket.erreur``
   (code ``non_imprime`` ou le dernier code de l'imprimante) et message aux personnes d'Équipe (``notifier``), commande jointe ;
3. dit la liaison « en erreur » quand l'imprimante ne s'est pas manifestée alors qu'un ticket l'attend ; ses interrogations la remettent « ok » (``imprimante_cloudprnt``).

Rejouable sans effet double : chaque geste est gardé par l'état du ticket. Une base ou un établissement en échec ne bloque pas les autres.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from api.db.bases_clients import restauration_liaison as liaison_db
from api.db.bases_clients.restauration_commande import commande_complete
from api.db.bases_clients.restauration_commun import maintenant
from api.services.restauration.appel_et_memoire import flux
from api.services.restauration.caisse.envoi_caisse import Secours, _secours_par_defaut, texte_du_secours
from api.services.restauration.caisse.rattrapage import liaisons_de_la_base, par_base
from api.services.restauration.caisse.synchro_caisse import dire_la_liaison

MINUTES_SANS_CONFIRMATION = 3
TENTATIVES_MAX = 3
MINUTES_SANS_NOUVELLES = 3  # une imprimante interroge toutes les 3 à 5 secondes : trois minutes de silence, c'est une panne


async def surveiller_les_tickets(_ctx=None, bases: list[tuple[int, str]] | None = None, *, secours: Secours | None = None) -> dict[str, Any]:
    secours = secours or _secours_par_defaut

    async def travail(connexion, organization_id: int, nom_base: str) -> dict[str, int]:
        bilan = {"remis_en_file": 0, "alertes": 0}
        for liaison in await liaisons_de_la_base(connexion):
            etab = liaison["etablissement_id"]
            imprimante = await liaison_db.imprimante(connexion, etab)
            if imprimante is None:
                continue
            bilan["remis_en_file"] += len(await liaison_db.remettre_en_file(connexion, etab, MINUTES_SANS_CONFIRMATION, TENTATIVES_MAX))
            for t in await liaison_db.tickets_non_imprimes(connexion, etab, liaison["alerte_sans_reponse_min"]):
                bilan["alertes"] += 1
                await flux.emettre(organization_id, etab, "ticket.erreur", {"numero": t["numero"], "code": t["code"]})
                commande = await commande_complete(connexion, etab, t["numero"])
                if commande is not None:
                    sujet, texte = texte_du_secours(commande, "ticket non imprimé : vérifier l'imprimante (papier, capot, alimentation, réseau)")
                    await secours(organization_id, sujet.replace("non transmise à la caisse / not sent to the till", "non imprimée / not printed"), texte)
            vue = imprimante["derniere_interrogation"]
            if await liaison_db.ticket_a_imprimer(connexion, etab) is not None and (vue is None or await maintenant(connexion) - vue > timedelta(minutes=MINUTES_SANS_NOUVELLES)):
                await dire_la_liaison(connexion, organization_id, etab, "erreur", "caisse_injoignable")
        return bilan

    return await par_base(bases, travail)
