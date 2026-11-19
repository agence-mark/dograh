"""[.mark] Module Restauration, lot 2 : les clients, la recherche dans la carte, la capacité (contrat § 4).

``client_par_numero``, ``ecrire_consigne_client``, ``chercher_dans_la_liste``, ``disponibilites_capacite``.
La logique de recherche et de capacité est dans les mécanismes communs (``recherche_liste.py``, ``capacite.py``) ;
ce fichier ne fait que lire le classeur de CET établissement et les leur donner.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import asyncpg

from api.db.bases_clients import recherche_liste, recherche_liste_moteur  # noqa: F401 -- importer le moteur le branche (lot 4)
from api.db.bases_clients.connexion import nom_de_la_base
from api.db.bases_clients.capacite import Regles, creneaux_libres
from api.db.bases_clients.instantane import stable
from api.db.bases_clients.recherche_liste import Element
from api.db.bases_clients.recherche_liste_index import GESTIONNAIRE
from api.db.bases_clients.recherche_liste_moteur import Reglages
from api.db.bases_clients.restauration_carte import carte_du_restaurant, version_carte
from api.db.bases_clients.restauration_commande import E164
from api.db.bases_clients.restauration_commun import Resultat, cle_du_client, fuseau_de, maintenant, poser_session
from api.db.bases_clients.restauration_reservation import duree_du_groupe, occupations_du_jour, salle_du_jour, type_et_fermetures_du_jour
from api.db.bases_clients.restauration_reglage import _ligne_de_reglage

MAX_CONSIGNES = 10
LONGUEUR_CONSIGNE = 200
# T-16 : l'allergie ne vit que dans la commande, jamais sur la fiche du client.
_ALLERGIE = re.compile(r"allerg|intol[eé]ran|c[œo]liaque|anaphyla", re.IGNORECASE)


def _client(r: asyncpg.Record) -> dict:
    return {
        "id": r["id"], "telephone": r["telephone"], "prenom": r["prenom"],
        "adresses": json.loads(r["adresses"]) if isinstance(r["adresses"], str) else r["adresses"],
        "consignes": [c["texte"] for c in (json.loads(r["consignes"]) if isinstance(r["consignes"], str) else r["consignes"])],
        "derniere_commande_id": str(r["derniere_commande_id"]) if r["derniere_commande_id"] else None,
        "nb_commandes": r["nb_commandes"],
    }


def _ajouter_mois(depuis: datetime, mois: int) -> datetime:
    mois_total = depuis.month - 1 + mois
    annee, mois_ = depuis.year + mois_total // 12, mois_total % 12 + 1
    jour = min(depuis.day, [31, 29 if annee % 4 == 0 and (annee % 100 or annee % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mois_ - 1])
    return depuis.replace(year=annee, month=mois_, day=jour)


async def client_par_numero(
    connexion: asyncpg.Connection,
    etablissement_id: int,
    telephone: str,
    *,
    repli_prise: Callable[[str], Awaitable[dict | None]] | None = None,
) -> dict | None:
    """La fiche du client de CET établissement, ou ``None``. Une fiche plus vieille que la durée de conservation de
    l'établissement (T-15, 12 mois par défaut) n'est plus rendue. ``repli_prise`` : si la caisse lit les clients
    (T-12, éteint par défaut), elle est interrogée quand la fiche manque."""
    if not isinstance(telephone, str) or not E164.match(telephone):
        return None
    async def lire() -> asyncpg.Record | None:
        return await connexion.fetchrow("SELECT * FROM mark.resto_client WHERE site_id = $1 AND telephone = $2", etablissement_id, telephone)

    r = await stable(connexion, cle_du_client(etablissement_id, telephone), lire)  # lot 5 : lue une fois par appel, oubliée à l'enregistrement
    if r is not None:
        reglage = await _ligne_de_reglage(connexion, etablissement_id)
        mois = (reglage["conservation_client_mois"] if reglage is not None else None) or 12
        derniere = r["derniere_commande_le"] or r["cree_le"]
        if _ajouter_mois(derniere, mois) > await maintenant(connexion):
            return _client(r)
        r = None
    if repli_prise is not None:
        return await repli_prise(telephone)
    return None


async def derniere_commande_du_client(connexion: asyncpg.Connection, etablissement_id: int, telephone: str) -> dict | None:
    """[.mark] Lot 26 (M22) : ce que le client reconnu a pris la dernière fois, lu dans le classeur de CET établissement : ``{mode, lignes: [{nom, quantite,
    retires, categorie}]}`` ou ``None`` (fiche absente ou périmée, commande refusée, annulée ou en échec, aucune ligne). ``categorie`` : le nom de la
    catégorie de l'article à la carte d'aujourd'hui (``None`` s'il n'y est plus). Hors des 17 fonctions du contrat : lecture seule."""
    fiche = await client_par_numero(connexion, etablissement_id, telephone)
    if not fiche or not fiche["derniere_commande_id"]:
        return None
    commande = await connexion.fetchrow(
        "SELECT numero, mode FROM mark.resto_commande WHERE site_id = $1 AND numero = $2::uuid AND statut NOT IN ('refusee', 'annulee', 'echec')",
        etablissement_id, fiche["derniere_commande_id"],
    )
    if commande is None:
        return None
    lignes = await connexion.fetch(
        "SELECT l.nom, l.quantite, l.retires, (SELECT c.nom FROM mark.resto_declinaison d JOIN mark.resto_produit p ON p.ref = d.produit_ref "
        "AND p.site_id IS NOT DISTINCT FROM d.site_id JOIN mark.resto_categorie c ON c.ref = p.categorie_ref AND (c.site_id IS NULL OR c.site_id = $1) "
        "WHERE d.code_caisse = l.code_caisse AND (d.site_id IS NULL OR d.site_id = $1) ORDER BY d.site_id NULLS LAST LIMIT 1) AS categorie "
        "FROM mark.resto_commande_ligne l WHERE l.site_id = $1 AND l.numero = $2 AND l.note IS DISTINCT FROM 'offert' ORDER BY l.rang",
        etablissement_id, commande["numero"],
    )
    if not lignes:
        return None
    return {"mode": commande["mode"], "lignes": [{"nom": l["nom"], "quantite": l["quantite"], "retires": list(l["retires"]), "categorie": l["categorie"]} for l in lignes]}


async def ecrire_consigne_client(connexion: asyncpg.Connection, etablissement_id: int, telephone: str, consigne: str) -> Resultat:
    """Ajoute une consigne habituelle à la fiche (écrite par ``finaliser``, relue à l'appel suivant). La fiche est créée
    si le numéro est neuf. Jamais deux fois la même consigne ; les ``MAX_CONSIGNES`` plus récentes sont gardées. Une
    allergie n'est PAS une consigne (T-16) : elle se note sur la commande."""
    if not isinstance(telephone, str) or not E164.match(telephone):
        return Resultat("ARGUMENT_INVALIDE", manque="telephone")
    texte = (consigne or "").strip()
    if not texte or len(texte) > LONGUEUR_CONSIGNE:
        return Resultat("ARGUMENT_INVALIDE", manque="consigne")
    if _ALLERGIE.search(texte):
        return Resultat("ARGUMENT_INVALIDE", {"raison": "allergie"}, "L'allergie se note sur la commande, pas sur la fiche.", "consigne")
    maintenant_ = await maintenant(connexion)
    await fuseau_de(connexion, etablissement_id)
    async with connexion.transaction():
        await poser_session(connexion, "agent", "consigne")
        await connexion.execute(
            "INSERT INTO mark.resto_client (site_id, telephone, cree_le, maj_le) VALUES ($1, $2, $3, $3) ON CONFLICT (site_id, telephone) DO NOTHING",
            etablissement_id, telephone, maintenant_,
        )
        r = await connexion.fetchrow("SELECT consignes FROM mark.resto_client WHERE site_id = $1 AND telephone = $2 FOR UPDATE", etablissement_id, telephone)
        existantes = json.loads(r["consignes"]) if isinstance(r["consignes"], str) else list(r["consignes"])
        if any(c["texte"].casefold() == texte.casefold() for c in existantes):
            return Resultat("DEJA_FAIT", {"consignes": [c["texte"] for c in existantes]})
        existantes.append({"texte": texte, "le": maintenant_.isoformat()})
        existantes = existantes[-MAX_CONSIGNES:]
        await connexion.execute(
            "UPDATE mark.resto_client SET consignes = $3::jsonb, maj_le = $4 WHERE site_id = $1 AND telephone = $2",
            etablissement_id, telephone, json.dumps(existantes), maintenant_,
        )
    return Resultat("OK", {"consignes": [c["texte"] for c in existantes]})


def elements_de_la_carte(carte: dict) -> tuple[list[Element], list[str]]:
    rangement = {c["id"]: c["nom"] for c in carte["categories"]}
    elements = [
        Element(p["id"], p["nom"], tuple(p["synonymes"]), rangement.get(p.get("categorie_id"), ""), tuple(d["nom"] for d in p.get("declinaisons") or []), p.get("numero") or "")
        for p in carte["produits"]
    ]
    elements += [Element(f["id"], f["nom"], (), rangement.get(f.get("categorie_id"), ""), (), f.get("numero") or "") for f in carte["formules"]]
    return elements, list(rangement.values())


NB_EXEMPLES = 3


def rangements_dits(elements: list[Element], texte: str) -> list[dict]:
    """SA-55 : les rangements (dans l'ordre de la liste) dont le nom porte tous les mots de rangement dits, chacun avec ses premiers
    éléments (``NB_EXEMPLES`` au plus : jamais toute la liste)."""
    forme = recherche_liste_moteur.preparer_forme(texte)
    if forme is None:
        return []
    noms = {e.categorie: (recherche_liste_moteur.preparer_forme(e.categorie) or forme).ensemble for e in elements if e.categorie}
    dits = forme.ensemble & frozenset(j for ensemble in noms.values() for j in ensemble)
    par_rangement: dict[str, list[str]] = {}
    for e in elements:
        if e.categorie and dits and dits <= noms[e.categorie]:
            par_rangement.setdefault(e.categorie, []).append(e.libelle)
    return [{"nom": nom, "exemples": libelles[:NB_EXEMPLES]} for nom, libelles in par_rangement.items()]


async def index_de_la_carte(connexion: asyncpg.Connection, etablissement_id: int):
    """L'index versionné de la carte (D10), refait seulement quand la version de la carte change ; pendant un appel, la version est celle de la
    carte chargée (lot 5) : aucune requête une fois l'index prêt. Le chargement de l'appel le prépare au décroché."""
    cle = (nom_de_la_base(connexion), "carte", etablissement_id)  # lot 5 (B06) : le nom de la base, connu de la connexion
    version = await version_carte(connexion, etablissement_id)
    if not GESTIONNAIRE.a_jour(cle, version):
        carte = await carte_du_restaurant(connexion, etablissement_id)
        elements, categories = elements_de_la_carte(carte)
        await GESTIONNAIRE.preparer_async(cle, carte["version"], elements, categories)
    return GESTIONNAIRE.etat(cle)


async def chercher_dans_la_liste(
    connexion: asyncpg.Connection, liste: str, texte: str, etablissement_id: int, *, reglages: Reglages | None = None
) -> Resultat:
    """Cherche ``texte`` dans une liste fermée de CET établissement. Liste servie ici : ``carte`` (produits, avec leurs
    synonymes relus ; formules). ``RETENU`` (``faits.retenu`` = l'identifiant, ``faits.options`` = contenant et taille lus),
    ``AMBIGU`` (``faits.candidats``, la question en suggestion) ou ``INTROUVABLE`` (les plus proches). Le moteur est celui du
    lot 4 (``recherche_liste_moteur``) ; son index est VERSIONNÉ (D10) : refait seulement quand la version de la carte change en
    base, et activé seulement si le banc rend zéro faux sûr (``recherche_liste_index``). Une autre liste : ``INTROUVABLE`` avec
    ``raison = liste_inconnue`` (les listes des autres modules s'ajoutent ici). ``reglages`` : les seuils et couches de l'agent
    (``services/restauration/recherche_reglages.py``) ; à défaut, ceux du module."""
    if liste != "carte":
        return Resultat("INTROUVABLE", {"raison": "liste_inconnue", "liste": liste, "candidats": []})
    if recherche_liste._moteur is not recherche_liste_moteur.moteur_par_defaut:
        # Un moteur posé par ``poser_moteur`` (essai, autre moteur) : même forme de retour, rien d'autre n'est exigé.
        carte = await carte_du_restaurant(connexion, etablissement_id)
        elements, _ = elements_de_la_carte(carte)
        trouve, version = recherche_liste.chercher(elements, texte), carte["version"]
    else:
        etat = await index_de_la_carte(connexion, etablissement_id)
        trouve = recherche_liste_moteur.chercher_dans_l_index(etat.index, texte, reglages or Reglages(), exclus=etat.exclus)
        elements = [e.element for e in etat.index.entrees if e.element.id not in etat.exclus]
        version = etat.version  # la version de l'index qui a répondu (l'ancienne si le nouvel index a été refusé)
    faits = {"retenu": trouve["retenu"], "candidats": trouve["candidats"], "options": trouve.get("options", {}), "version": version}
    if trouve.get("raison"):
        faits["raison"] = trouve["raison"]  # « numero_inconnu » : le numéro dit n'existe pas dans la carte
    if trouve.get("que_rangement"):
        # SA-55 (appel 2606) : ce qui est dit ne nomme qu'un rangement (« des pizzas ») : les rangements qu'il désigne, pour demander LEQUEL.
        faits["que_rangement"], faits["rangements"] = True, rangements_dits(elements, texte)
    if trouve["statut"] == "AMBIGU":
        question = trouve.get("question") or "Vous voulez dire : " + " ou ".join(c["libelle"] for c in trouve["candidats"]) + " ?"
        return Resultat("AMBIGU", faits, question)
    return Resultat(trouve["statut"], faits)


async def disponibilites_capacite(
    connexion: asyncpg.Connection, etablissement_id: int, jour: date, couverts: int, duree_minutes: int | None = None
) -> Resultat:
    """Les créneaux où ``couverts`` personnes tiennent, ce jour, du plus tôt au plus tard (``capacite.py``). La durée vient
    de l'argument, sinon de la règle de durée par taille de groupe ; sans l'une ni l'autre : ``INCOMPLETE`` (``duree``).
    Tables assemblables deux à deux ; réservations sans table : elles prennent de la capacité totale."""
    if not isinstance(couverts, int) or couverts < 1:
        return Resultat("ARGUMENT_INVALIDE", manque="couverts")
    fuseau = ZoneInfo(await fuseau_de(connexion, etablissement_id))
    maintenant_ = await maintenant(connexion)
    if duree_minutes is None:
        duree_minutes = await duree_du_groupe(connexion, etablissement_id, couverts)
    if not duree_minutes:
        return Resultat("INCOMPLETE", manque="duree")
    debut_jour = datetime(jour.year, jour.month, jour.day, tzinfo=fuseau)
    fin_jour = datetime.combine(jour + timedelta(days=1), datetime.min.time(), tzinfo=fuseau)
    # Lot 5 (B05) : la salle du jour lue une fois par appel ; les réservations du jour et l'état vivant (pause, fermetures) à leur moment
    salle = await salle_du_jour(connexion, etablissement_id, debut_jour, fin_jour)
    services, unites, regle = salle.services, salle.unites, salle.regle
    occupations = await occupations_du_jour(connexion, etablissement_id, debut_jour, fin_jour)
    type_, fermetures = await type_et_fermetures_du_jour(connexion, etablissement_id, debut_jour, fin_jour)
    if type_ is not None and not type_["ouvert"]:
        return Resultat("OK", {"creneaux": [], "duree_minutes": duree_minutes, "raison": "type_ferme"})
    regles = Regles(
        delai_minimal=regle["delai_minimal"] if regle else 0,
        jours_a_l_avance=regle["jours_a_l_avance"] if regle else None,
        effectif_max=regle["couverts_max_groupe"] if regle else None,
        effectif_max_par_creneau=regle["couverts_max_creneau"] if regle else None,
        pause_jusqu_a=type_["pause_jusqu_a"] if type_ else None,
        fermetures=fermetures,
    )
    if regles.effectif_max is not None and couverts > regles.effectif_max:
        return Resultat("REFUSEE", {"raison": "autre", "detail": "groupe_trop_grand", "maximum": regles.effectif_max}, "Pour un groupe de cette taille, il faut appeler le restaurant.")
    libres = creneaux_libres(jour, couverts, duree_minutes, unites, occupations, services, fuseau, maintenant_, regles)
    return Resultat("OK", {"creneaux": libres, "duree_minutes": duree_minutes, "complet": not libres})
