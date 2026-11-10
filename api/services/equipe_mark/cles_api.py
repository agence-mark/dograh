"""[.mark] Clôture, lot A (D21) : les clés d'API portées par un rôle.

* À la création, on choisit le rôle de la clé. **Jamais plus de droits que son créateur** : chaque permission du rôle (hors gestes de l'équipe,
  qu'une clé n'a jamais) doit être portée par le créateur, sinon 403. Au fil du temps la borne se recalcule à chaque appel
  (``droits_effectifs.permissions_de_la_cle``) : un créateur qui perd un droit le fait perdre à sa clé.
* Rôle modifiable (même contrôle), clé suspendable (rétablie en un clic) et révocable (archivée, définitif).
* Une clé d'API ne crée jamais une clé (``cles.gerer`` est fermée aux clés) : on ne se fabrique pas de droits en chaîne.
"""

from __future__ import annotations

from api.db import db_client
from api.services.equipe_mark.droits_effectifs import avec_les_permissions_impliquees
from api.services.equipe_mark.equipe import ErreurEquipe
from api.services.equipe_mark.permissions import PERMISSIONS_JAMAIS_PAR_CLE_A_ROLE


async def verifier_le_role_de_la_cle(createur, role_id: int) -> dict:
    """Le rôle (dict) si le créateur peut le donner à une clé, sinon ``ErreurEquipe`` (404 inconnu, 403 trop de droits)."""
    role = await db_client.obtenir_role(role_id)
    if role is None:
        raise ErreurEquipe(404, "Role not found")
    acces = await db_client.acces_du_compte(createur.id)
    if acces is None:
        raise ErreurEquipe(403, "Only a member of the team can give a role to an API key")
    portees = avec_les_permissions_impliquees(acces.permissions)
    en_trop = sorted(p for p in role["permissions"] if p not in PERMISSIONS_JAMAIS_PAR_CLE_A_ROLE and p not in portees)
    if en_trop:
        raise ErreurEquipe(403, f"A key never has more rights than its creator: {', '.join(en_trop)}")
    return role


async def regenerer_la_cle_du_portail(user, nom: str):
    """Clôture, lot A : « Régénérer la clé du portail ». La nouvelle clé est créée D'ABORD (sans rôle : la liste fermée du portail), puis les
    anciennes clés de ce nom sont révoquées : jamais un instant sans clé valide si la création échoue. Rend (clé, valeur en clair, ids révoqués)."""
    organisation = user.selected_organization_id
    anciennes = [c for c in await db_client.get_api_keys_by_organization(organisation, include_archived=False) if c.name == nom]
    nouvelle, valeur = await db_client.create_api_key(organisation, nom, user.id)
    revoquees = []
    for ancienne in anciennes:
        if await db_client.archive_api_key(ancienne.id):
            revoquees.append(ancienne.id)
    return nouvelle, valeur, revoquees
