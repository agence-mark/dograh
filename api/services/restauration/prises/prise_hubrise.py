"""[.mark] Module Restauration, lot 9 : la prise HUBRISE (les ``faire_*`` des gestes que sa fiche permet).

Tout ce que la prise écrit ou lit passe par les traducteurs purs de ``hubrise_traduction`` et par ``ClientHubrise`` ; la fiche (``fiches.HUBRISE``) décide
des gestes permis (``Prise`` les vérifie avant d'appeler ``faire_*``). Une prise SANS accès (celle que le registre rend sans contexte) lève
``PrisePasBranchee`` à tout geste : jamais un envoi simulé. ``sur_jeton_refuse`` est l'écouteur que le service de liaison pose : un 401 passe la liaison à
« rompue » (le flux dit ``caisse.liaison``). ``genre_de_code`` dit si un code de la carte est une déclinaison ou une option (le classeur le sait).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from loguru import logger

from api.services.restauration.prises import hubrise_traduction as ht
from api.services.restauration.prises.fiches import HUBRISE
from api.services.restauration.prises.hubrise_client import ClientHubrise, ErreurHubrise, JetonRefuse
from api.services.restauration.prises.prise import Prise, PrisePasBranchee, ResultatEnvoi, enregistrer_prise

NOM = "hubrise"
GenreDeCode = Callable[[str], Awaitable[str | None]]


class PriseHubrise(Prise):
    nom = NOM

    def __init__(
        self, client: ClientHubrise | None = None, *, sur_jeton_refuse: Callable[[], Awaitable[None]] | None = None, genre_de_code: GenreDeCode | None = None,
        formules: dict[str, dict] | None = None,
    ):
        super().__init__(HUBRISE)
        self._client, self._sur_jeton_refuse, self._genre_de_code, self._formules = client, sur_jeton_refuse, genre_de_code, formules

    @property
    def sans_tiers(self) -> bool:
        """Lot 6 : branchée sur la caisse de démo du Labo (client ``labo``, posé par la fabrique seulement sous la garde de la caisse de démo)."""
        return self._client is not None and self._client.labo

    def _acces(self) -> ClientHubrise:
        if self._client is None:
            raise PrisePasBranchee("La prise hubrise n'a pas d'accès : elle se branche par établissement (liaison).")
        return self._client

    async def _appel(self, methode: str, chemin: str, **plus: Any) -> Any:
        try:
            return await self._acces().requete(methode, chemin, **plus)
        except JetonRefuse:
            if self._sur_jeton_refuse is not None:
                await self._sur_jeton_refuse()
            raise

    # ---- commandes
    async def faire_envoyer(self, commande: dict[str, Any]) -> ResultatEnvoi:
        try:
            corps = ht.commande_vers_hubrise(commande, formules=self._formules)
        except ht.TraductionImpossible:
            return ResultatEnvoi("REFUSEE", raison="autre")  # une valeur que le format ne peut pas porter : jamais envoyée
        try:
            ordre = await self._appel("POST", "/location/orders", corps=corps)  # jamais rejoué ici : l'envoi cherche par notre numéro avant de renvoyer
        except JetonRefuse:
            return ResultatEnvoi("INDISPONIBLE", raison="caisse_injoignable")
        except ErreurHubrise as erreur:
            if erreur.http == 422:
                return ResultatEnvoi("REFUSEE", raison="autre")
            return ResultatEnvoi("INDISPONIBLE", raison="caisse_injoignable")
        try:
            lue = ht.commande_de_hubrise(ordre)
        except (ht.TraductionImpossible, AttributeError, KeyError, TypeError, ValueError):
            # Lot 19 bis (K2) : le POST a RÉUSSI, la commande est en caisse. Une réponse que notre lecture ne sait pas lire n'est jamais un échec (le restaurant la ressaisirait : deux commandes).
            logger.warning("[.mark] HubRise accepted the order but its answer could not be read: the order is kept as sent")
            brut = ordre if isinstance(ordre, dict) else {}
            return ResultatEnvoi("ENVOYEE", etape=ht.etape_de_statut(brut.get("status")), ref_fournisseur=brut.get("id"))
        # Lot 16 : ``expected_time`` est NOTRE heure, que la caisse renvoie telle quelle ; seule ``confirmed_time`` est « l'heure de la caisse » (elle l'a changée)
        return ResultatEnvoi("ENVOYEE", etape=lue["etape"], ref_fournisseur=lue["ref_fournisseur"], heure_annoncee=lue["heure_confirmee"])

    async def faire_chercher(self, numero: str) -> dict | None:
        trouvees = await self._appel("GET", "/location/orders", params={"private_ref": str(numero)})
        if not trouvees:
            return None
        return ht.commande_de_hubrise(trouvees[0])

    async def faire_annuler(self, numero: str) -> ResultatEnvoi:
        connue = await self.faire_chercher(numero)
        if connue is None:
            return ResultatEnvoi("REFUSEE", raison="autre")
        await self._appel("PATCH", f"/location/orders/{connue['ref_fournisseur']}", corps={"status": "cancelled"})
        return ResultatEnvoi("ENVOYEE", etape="annulee", ref_fournisseur=connue["ref_fournisseur"])

    async def relire_la_commande(self, ref_fournisseur: str) -> dict:
        """Une commande lue par SON identifiant de caisse (le message signé de la caisse ne porte que cet identifiant)."""
        return ht.commande_de_hubrise(await self._appel("GET", f"/location/orders/{ref_fournisseur}"))

    async def lister_les_commandes(self) -> list[dict]:
        """Mode passif (relève, 10 par minute au plus : l'appelant respecte les 30 s) : les commandes de la caisse, au format commun."""
        return [ht.commande_de_hubrise(o) for o in (await self._appel("GET", "/location/orders")) or []]

    # ---- carte, ruptures
    async def faire_lire_carte(self) -> dict:
        catalogue = self._acces().catalogue
        if not catalogue:
            raise ErreurHubrise("reponse_inattendue")
        return ht.carte_de_hubrise(await self._appel("GET", f"/catalogs/{catalogue}")).carte

    def _chemin_inventaire(self) -> str:
        acces = self._acces()
        if not (acces.catalogue and acces.point_de_vente):
            raise ErreurHubrise("reponse_inattendue")
        return f"/catalogs/{acces.catalogue}/locations/{acces.point_de_vente}/inventory"

    async def faire_lire_ruptures(self) -> list[dict]:
        return ht.ruptures_de_hubrise(await self._appel("GET", self._chemin_inventaire()) or [])

    async def faire_poser_rupture(self, code_caisse: str, disponible: bool, fin: datetime | None) -> None:
        genre = await self._genre_de_code(code_caisse) if self._genre_de_code else None
        if genre is None:
            raise ErreurHubrise("reponse_inattendue")  # un code que la carte ne connaît pas n'est jamais poussé
        # PATCH et non PUT : PUT ignore ``stock: null`` et remet à zéro tout ce qu'il ne cite pas (documentation inventories).
        await self._appel("PATCH", self._chemin_inventaire(), corps=[ht.rupture_vers_hubrise(code_caisse, genre, disponible, fin)])

    # ---- état du restaurant
    async def faire_lire_etat(self) -> dict | None:
        return ht.etat_de_hubrise(await self._appel("GET", "/location"))

    async def lire_le_point_de_vente(self) -> dict:
        """Le point de vente brut (état, temps de préparation, horaires) : la liaison en compare les horaires, sans jamais les écraser."""
        return await self._appel("GET", "/location")

    async def faire_poser_etat(self, etat: dict) -> None:
        await self._appel("PATCH", "/location", corps=ht.etat_vers_hubrise(etat))

    # ---- messages gardés par la caisse (mode passif, relecture)
    async def faire_lire_evenements(self) -> list[dict]:
        """``GET /callback/events`` : les messages non acquittés (sans état : la commande est RELUE par son identifiant). Une seule page par relève."""
        return [e for e in (await self._appel("GET", "/callback/events")) or [] if isinstance(e, dict)]

    async def faire_acquitter_evenement(self, identifiant: str) -> None:
        """``DELETE /callback/events/:id`` : sans acquittement, la caisse le rend à chaque relève (documentation callbacks)."""
        await self._appel("DELETE", f"/callback/events/{identifiant}")

    # ---- clients, remises
    async def faire_lire_client(self, telephone: str) -> dict | None:
        liste = self._acces().liste_clients
        if not liste:
            return None
        trouves = await self._appel("GET", f"/customer_lists/{liste}/customers", params={"phone": telephone})
        if not trouves:
            return None
        c = trouves[0]
        return {"telephone": c.get("phone"), "prenom": c.get("first_name"), "nom": c.get("last_name"), "adresse": c.get("address_1"), "ville": c.get("city")}

    async def faire_lire_remises(self) -> list[dict]:
        catalogue = self._acces().catalogue
        if not catalogue:
            return []
        donnees = ((await self._appel("GET", f"/catalogs/{catalogue}")) or {}).get("data", {})
        return [
            {"ref": d.get("ref"), "nom": d.get("name"), "effet": ht.EFFET_DE_HUBRISE.get(d.get("pricing_effect"), "inchange"), "valeur": d.get("pricing_value")}
            for d in donnees.get("discounts", [])
        ]


# La prise rendue SANS contexte par le registre : elle refuse tout geste (``PrisePasBranchee``). Le service de liaison construit la vraie, avec son accès.
enregistrer_prise(NOM, lambda: PriseHubrise())
