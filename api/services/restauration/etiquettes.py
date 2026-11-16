"""[.mark] Module Restauration, lot 11 (§ 3.3) : les valeurs des étiquettes posées au décroché.

Courtes, stables pendant l'appel, utiles à presque chaque appel, sans rien à calculer ni garantir (le total, un prix, un horaire d'annonce, un allergène
sont des OUTILS). Lues dans le classeur de l'établissement servi par l'appel, par la même source que le comptoir (``SourceClasseur``) : jamais une
requête ici. Chaque étiquette est indépendante : une qui échoue est absente, les autres sont posées. Le moteur (``services/modules/etiquettes.py``)
ne pose que les clés déclarées au registre et n'écrase jamais une valeur déjà posée.

⛔ Aucune donnée de carte : pas d'article, pas de prix d'article, pas d'ingrédient (test d'inventaire). Seule exception, demandée (lot 26, M22) :
``commande_derniere``, ce que CE client reconnu par son numéro a pris la dernière fois (lu dans son historique, jamais dans la carte, sans prix).
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.db.bases_clients.connexion import connecter
from api.services.mots_dits import montant_en_lettres, nom_dit
from api.db.bases_clients import restauration_client
from api.db.bases_clients.restauration_ecran import module_allume
from api.services.restauration.mots_du_metier import genre_et_commun
from api.db.bases_clients.restauration_zone import zones_de_l_etablissement
from api.services.restauration.appel import Lieu, identifiant_de_l_etablissement
from api.services.restauration.source_commande import SourceClasseur

# E-15 : l'agent ne passe la main que pour ces deux motifs. Dit une fois, au décroché.
MOTIFS_DE_PASSAGE = "une réclamation, ou un appel au sujet d'une commande déjà passée"


def _liste_dite(mots: list[str]) -> str:
    return mots[0] if len(mots) == 1 else (", ".join(mots[:-1]) + " et " + mots[-1] if mots else "")


def _euros(centimes: int) -> str:
    return montant_en_lettres(int(centimes))


def phrase_de_la_derniere_commande(derniere: dict[str, Any] | None, source: SourceClasseur) -> str:
    """« une Regina Normale et un Coca-Cola, à emporter » : ce que le client a pris la dernière fois, dit comme à l'oral (genre et nombre accordés).
    Aucun prix, aucune coordonnée. Vide quand il n'y a rien à dire."""
    if not derniere or not derniere.get("lignes"):
        return ""
    morceaux = []
    for l in derniere["lignes"]:
        genre, commun = genre_et_commun(l["nom"], l.get("categorie"))
        morceau = nom_dit(l["nom"], l["quantite"], genre=genre, commun=commun)
        if l.get("retires"):
            morceau += " sans " + _liste_dite(list(l["retires"]))
        morceaux.append(morceau)
    dit = _liste_dite(morceaux)
    return f"{dit}, {source.libelles_des_modes.get(derniere['mode'], derniere['mode'])}"


def phrase_des_zones(zones: list[dict[str, Any]]) -> str:
    """« Nous livrons Zone 1 et Zone 2. » : les noms que l'établissement a donnés à ses zones, jamais une liste de communes."""
    noms = [z["nom"] for z in zones if str(z.get("nom") or "").strip()]
    return f"Nous livrons {_liste_dite(noms)}." if noms else ""


def minimum_dit(zones: list[dict[str, Any]]) -> str:
    """Le plus petit minimum non nul parmi les zones ; vide quand aucune zone n'en demande."""
    minima = [int(z["minimum"]) for z in zones if int(z.get("minimum") or 0) > 0]
    return f"{_euros(min(minima))} en livraison" if minima else ""


async def valeurs(organization_id: int, workflow_id: int | None, appel: dict) -> dict[str, str]:
    from api.services.base_client.rattachement import nom_de_la_base
    from api.services.etablissements.appel import etablissement_de_lappel

    nom_base = await nom_de_la_base(organization_id)
    if not nom_base:
        return {}
    servi = await etablissement_de_lappel(organization_id, workflow_id, appel or {})
    connexion = await connecter(nom_base)
    sortie: dict[str, str] = {}
    try:
        if not await module_allume(connexion):
            return {}  # le module n'est pas ouvert chez ce client (réglage du portail, 030) : aucune étiquette, aucune autre lecture
        lieu = Lieu(nom_base, await identifiant_de_l_etablissement(connexion, servi.etablissement.id if servi else None), organization_id)
        source = SourceClasseur(connexion, lieu)
        sortie["equipe_motifs"] = MOTIFS_DE_PASSAGE

        async def _types() -> str:
            ouverts = [source.libelles_des_modes[m] for m in source.modes if (await source.etat(m))["ouvert"]]
            return _liste_dite(ouverts)

        async def _paiements() -> str:
            moyens = (await source.reglages()).get("moyens_paiement") or []
            return _liste_dite([source.libelles_des_moyens[m] for m in moyens if m in source.libelles_des_moyens])

        async def _client() -> str:
            numero = (appel or {}).get("caller_number")
            fiche = await source.client(numero) if isinstance(numero, str) else None
            return str((fiche or {}).get("prenom") or "")

        async def _derniere() -> str:
            numero = (appel or {}).get("caller_number")
            derniere = await restauration_client.derniere_commande_du_client(connexion, lieu.etablissement_id, numero) if isinstance(numero, str) else None
            return phrase_de_la_derniere_commande(derniere, source)

        zones = await zones_de_l_etablissement(connexion, lieu.etablissement_id)
        lectures = {
            "commande_types_ouverts": _types,
            "commande_paiements_acceptes": _paiements,
            "appel_client_reconnu": _client,
            "commande_derniere": _derniere,
        }
        for cle, lire in lectures.items():
            try:
                sortie[cle] = await lire()
            except Exception as erreur:  # noqa: BLE001 -- une étiquette qui échoue est absente, jamais l'appel
                logger.warning(f"[.mark] Label {cle} not read ({type(erreur).__name__}): {erreur}")
        sortie["livraison_phrase_des_zones"] = phrase_des_zones(zones)
        sortie["commande_minimum"] = minimum_dit(zones)
    finally:
        await connexion.close()
    return sortie
