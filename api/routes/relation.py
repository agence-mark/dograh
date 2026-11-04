"""[.mark] Le Hub « Relation clients » (U3 septies, E78) : la vue de .mark sur tous ses clients.

Réservé aux membres de l'équipe, par une SESSION : une clé d'API (le portail) reçoit 403 sur chaque route d'ici, quelle
que soit son organisation. Chaque route nomme le client dans l'adresse et le contrôle contre ce que le rôle du compte
ouvre ; un client non ouvert est un 404. Les notes internes, les notes sur un client et les témoignages vivent ici
seulement : le portail ne les lit jamais (``relation_portail.py``).

Les signalements sur un appel et les pannes restent dans « À améliorer » du client (une chose, une place) : le Hub n'en
garde pas la copie.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from api.db import db_client
from api.db.models import UserModel
from api.services.auth.depends import get_user
from api.services.equipe_mark.acces import journaliser
from api.services.relation import hub

router = APIRouter(prefix="/relation", tags=["relation"])

# Revue serveur M9 : les bases des clients se lisent cinq à la fois, chacune avec son délai (une base lente ne bloque pas la page).
LECTURES_EN_PARALLELE = 5
DELAI_LECTURE_BASE_S = 5.0

Etat = Literal["nouveau", "en_cours", "repondu", "clos"]
EtatDemande = Literal["nouvelle", "proposee", "a_coder", "refusee"]


async def membre(
    user: UserModel = Depends(get_user),
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> UserModel:
    await hub.exiger_equipe(user, x_api_key)
    return user


# ---------------------------------------------------------------------- formes
class MessageOut(BaseModel):
    id: int
    cote: Literal["client", "mark", "interne"]
    auteur: str
    texte: str
    cree_le: datetime


class FilOut(BaseModel):
    id: int
    organization_id: int
    client: str
    sorte: str
    sujet: str
    etat: str
    suivi_par: int | None
    suivi_nom: str | None
    lu_par_mark: bool
    logiciel: str | None
    catalogue: str | None
    etat_demande: str | None
    cree_le: datetime
    modifie_le: datetime
    dernier: MessageOut | None = None
    messages: list[MessageOut] | None = None


class MessageIn(BaseModel):
    cote: Literal["mark", "interne"]
    texte: str = Field(min_length=1, max_length=8000)


class MembreASuivre(BaseModel):
    id: int
    nom: str


class FilPatch(BaseModel):
    etat: Etat | None = None
    suivi: Literal["moi", "personne"] | None = None
    # V4 : confier le suivi à un membre de l'équipe (comme la liste « Suivi par » de la maquette). Un identifiant inconnu est refusé.
    suivi_par: int | None = Field(default=None, ge=1)
    lu: bool | None = None
    etat_demande: EtatDemande | None = None
    catalogue: str | None = Field(default=None, max_length=120)


class NoteIn(BaseModel):
    texte: str = Field(min_length=1, max_length=4000)


class NoteOut(BaseModel):
    id: int
    auteur: str
    texte: str
    cree_le: datetime


class TemoignageIn(BaseModel):
    texte: str = Field(min_length=1, max_length=2000)
    auteur: str = Field(min_length=1, max_length=160)
    accord: bool = False


class TemoignagePatch(BaseModel):
    accord: bool


class TemoignageOut(BaseModel):
    id: int
    organization_id: int
    texte: str
    auteur: str
    accord: bool


class EntreeIn(BaseModel):
    motif: str | None = Field(default=None, max_length=200)


class EntreeCreee(BaseModel):
    entree_id: int
    jeton: str
    expire_le: datetime
    valable_secondes: int


class EntreeOut(BaseModel):
    id: int
    organization_id: int
    client: str
    auteur: str
    motif: str | None
    cree_le: datetime
    utilise_le: datetime | None
    # V4 : la sortie dite par le portail, et la durée de la visite (``None`` tant que le portail ne l'a pas dite).
    fin_le: datetime | None = None
    duree_secondes: int | None = None


class ClientOut(BaseModel):
    id: int
    nom: str
    ouverts: int
    non_lus: int
    demandes_nouvelles: int
    # Ce que l'accueil et la liste des clients montrent (lus en groupe, jamais une requête par client).
    etat: Literal["actif", "installation"] = "installation"
    agents: int = 0
    appels_7j: int = 0
    note: float | None = None
    signalements: int = 0
    pannes: int = 0


class AvisClient(BaseModel):
    organization_id: int
    client: str
    note: float | None
    avis: int
    temoignages: list[TemoignageOut]


def _fil_sortie(f: dict, noms: dict[int, str]) -> FilOut:
    return FilOut(**{**f, "client": noms.get(f["organization_id"], "")})


# ---------------------------------------------------------------------- clients et accueil
@router.get("/clients", response_model=list[ClientOut])
async def lister_clients(user: UserModel = Depends(membre)) -> list[ClientOut]:
    noms = await hub.clients_ouverts(user)
    comptes, stats = await asyncio.gather(
        db_client.compter_fils_relation(noms), db_client.statistiques_des_clients_relation(noms)
    )
    vide = {"ouverts": 0, "non_lus": 0, "demandes_nouvelles": 0}
    return [
        ClientOut(
            id=i,
            nom=n,
            **comptes.get(i, vide),
            etat="actif" if stats[i]["agents_publies"] else "installation",
            agents=stats[i]["agents"],
            appels_7j=stats[i]["appels_7j"],
            note=stats[i]["note"],
            signalements=stats[i]["signalements"],
            pannes=stats[i]["pannes"],
        )
        for i, n in sorted(noms.items(), key=lambda p: p[1].lower())
    ]


class ChiffresClient(BaseModel):
    """Partie 3, lot 15 (O-1) : la bande de chiffres de l'accueil d'un client. ``None`` = aucun appel noté, jamais un zéro inventé."""

    appels_7j: int
    note_juge: float | None
    agents_publies: int


@router.get("/clients/{organization_id}/chiffres", response_model=ChiffresClient)
async def chiffres_d_un_client(organization_id: int, user: UserModel = Depends(membre)) -> ChiffresClient:
    """Appels des 7 derniers jours et note moyenne du juge de CE client (le client doit être ouvert à l'appelant, sinon 404)."""
    nom = await hub.client_ouvert(user, organization_id)
    ligne = (await db_client.statistiques_des_clients_relation({organization_id: nom}))[organization_id]
    return ChiffresClient(appels_7j=ligne["appels_7j"], note_juge=ligne["note"], agents_publies=ligne["agents_publies"])


@router.get("/file", response_model=list[FilOut])
async def ma_file(user: UserModel = Depends(membre)) -> list[FilOut]:
    """« Ma file » : tout ce qui attend (fils nouveaux ou en cours, demandes comprises), le plus récent d'abord."""
    noms = await hub.clients_ouverts(user)
    fils = await db_client.lister_fils_relation(noms, a_traiter=True, avec_internes=True)
    return [_fil_sortie(f, noms) for f in fils]


# ---------------------------------------------------------------------- fils
@router.get("/fils", response_model=list[FilOut])
async def lister_fils(
    etat: Etat | None = None,
    sorte: Literal["message", "demande_logiciel"] | None = None,
    suivi: Literal["moi"] | None = None,
    a_traiter: bool = False,
    client: int | None = None,
    q: str | None = Query(default=None, max_length=80),
    user: UserModel = Depends(membre),
) -> list[FilOut]:
    noms = await hub.clients_ouverts(user)
    if client is not None:
        if client not in noms:
            raise HTTPException(status_code=404, detail="Client not found")
        organisations = [client]
    else:
        organisations = list(noms)
    fils = await db_client.lister_fils_relation(
        organisations,
        etat=etat,
        sorte=sorte,
        suivi_par=user.id if suivi == "moi" else None,
        a_traiter=a_traiter,
        recherche=q,
        avec_internes=True,
    )
    return [_fil_sortie(f, noms) for f in fils]


@router.get("/clients/{organization_id}/fils/{fil_id}", response_model=FilOut)
async def lire_fil(organization_id: int, fil_id: int, user: UserModel = Depends(membre)) -> FilOut:
    nom = await hub.client_ouvert(user, organization_id)
    fil = await db_client.lire_fil_relation(organization_id, fil_id, avec_internes=True)
    if fil is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if not fil["lu_par_mark"]:
        await db_client.modifier_fil_relation(organization_id, fil_id, {"lu_par_mark": True})
        fil["lu_par_mark"] = True
    return FilOut(**{**fil, "client": nom})


@router.post("/clients/{organization_id}/fils/{fil_id}/messages", response_model=MessageOut, status_code=201)
async def repondre(
    organization_id: int, fil_id: int, corps: MessageIn, user: UserModel = Depends(membre)
) -> MessageOut:
    """Répondre au client (``mark``, il le lit dans le portail) ou écrire une note interne (``interne``, jamais sortie)."""
    await hub.client_ouvert(user, organization_id)
    message = await db_client.ajouter_message_relation(
        organization_id, fil_id, cote=corps.cote, auteur=await hub.nom_du_membre(user), texte=corps.texte.strip()
    )
    if message is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    # Revue serveur, mineur 8 : un geste d'écriture du Hub est écrit au journal (qui, quoi, quel client) ; jamais le texte.
    await journaliser(user, "relation.message", organization_id, {"fil_id": fil_id, "cote": corps.cote})
    return MessageOut(**message)


@router.get("/membres", response_model=list[MembreASuivre])
async def membres_a_qui_confier_un_fil(
    client: int | None = Query(None, description="The client of the thread: only the members whose role opens it."),
    user: UserModel = Depends(membre),
) -> list[MembreASuivre]:
    """Les membres de l'équipe .mark (id et nom) : la liste « Suivi par » d'un fil. Réservée à l'équipe, jamais une adresse.
    Avec ``client`` : seulement ceux dont le rôle ouvre ce client (le client doit être ouvert à l'appelant, sinon 404)."""
    if client is not None:
        await hub.client_ouvert(user, client)
    return [MembreASuivre(**m) for m in await hub.membres_a_suivre(client)]


@router.patch("/clients/{organization_id}/fils/{fil_id}", status_code=204)
async def modifier_fil(
    organization_id: int, fil_id: int, corps: FilPatch, user: UserModel = Depends(membre)
) -> None:
    await hub.client_ouvert(user, organization_id)
    champs: dict = {}
    if corps.etat is not None:
        champs["etat"] = corps.etat
    if corps.lu is not None:
        champs["lu_par_mark"] = corps.lu
    if corps.suivi_par is not None:
        choisi = next((m for m in await hub.membres_a_suivre(organization_id) if m["id"] == corps.suivi_par), None)
        if choisi is None:
            raise HTTPException(status_code=422, detail="Unknown team member")
        champs.update(suivi_par=choisi["id"], suivi_nom=choisi["nom"])
    elif corps.suivi == "moi":
        champs.update(suivi_par=user.id, suivi_nom=await hub.nom_du_membre(user))
    elif corps.suivi == "personne":
        champs.update(suivi_par=None, suivi_nom=None)
    if corps.etat_demande is not None:
        champs["etat_demande"] = corps.etat_demande
    if corps.catalogue is not None:
        champs["catalogue"] = corps.catalogue or None
    if not champs:
        raise HTTPException(status_code=422, detail="Nothing to change")
    if not await db_client.modifier_fil_relation(organization_id, fil_id, champs):
        raise HTTPException(status_code=404, detail="Thread not found")
    await journaliser(user, "relation.fil_modifie", organization_id, {"fil_id": fil_id, "champs": sorted(champs)})


# ---------------------------------------------------------------------- notes sur un client
@router.get("/clients/{organization_id}/notes", response_model=list[NoteOut])
async def lister_notes(organization_id: int, user: UserModel = Depends(membre)) -> list[NoteOut]:
    await hub.client_ouvert(user, organization_id)
    return [NoteOut(**n) for n in await db_client.lister_notes_relation(organization_id)]


@router.post("/clients/{organization_id}/notes", response_model=NoteOut, status_code=201)
async def ajouter_note(organization_id: int, corps: NoteIn, user: UserModel = Depends(membre)) -> NoteOut:
    await hub.client_ouvert(user, organization_id)
    note = await db_client.ajouter_note_relation(organization_id, await hub.nom_du_membre(user), corps.texte.strip())
    await journaliser(user, "relation.note_ajoutee", organization_id)
    return NoteOut(**note)


@router.delete("/clients/{organization_id}/notes/{note_id}", status_code=204)
async def supprimer_note(organization_id: int, note_id: int, user: UserModel = Depends(membre)) -> None:
    await hub.client_ouvert(user, organization_id)
    if not await db_client.supprimer_note_relation(organization_id, note_id):
        raise HTTPException(status_code=404, detail="Note not found")
    await journaliser(user, "relation.note_supprimee", organization_id, {"note_id": note_id})


# ---------------------------------------------------------------------- avis et témoignages
@router.get("/avis", response_model=list[AvisClient])
async def avis_et_temoignages(user: UserModel = Depends(membre)) -> list[AvisClient]:
    noms = await hub.clients_ouverts(user)
    temoignages = await db_client.lister_temoignages_relation(noms)
    trie = sorted(noms.items(), key=lambda p: p[1].lower())
    porte = asyncio.Semaphore(LECTURES_EN_PARALLELE)

    async def lire(organisation: int) -> dict:
        async with porte:
            try:
                return await asyncio.wait_for(hub.stats_avis(organisation), timeout=DELAI_LECTURE_BASE_S)
            except Exception:  # noqa: BLE001 : une base lente ou en panne n'a pas d'avis à afficher, la page s'ouvre quand même
                return {"note": None, "avis": 0}

    lues = await asyncio.gather(*(lire(i) for i, _ in trie))
    sortie = []
    for (i, nom), stats in zip(trie, lues, strict=True):
        sortie.append(
            AvisClient(
                organization_id=i,
                client=nom,
                note=stats["note"],
                avis=stats["avis"],
                temoignages=[TemoignageOut(**t) for t in temoignages if t["organization_id"] == i],
            )
        )
    return sortie


@router.post("/clients/{organization_id}/temoignages", response_model=TemoignageOut, status_code=201)
async def ajouter_temoignage(
    organization_id: int, corps: TemoignageIn, user: UserModel = Depends(membre)
) -> TemoignageOut:
    await hub.client_ouvert(user, organization_id)
    temoignage = await db_client.ajouter_temoignage_relation(
        organization_id, corps.texte.strip(), corps.auteur.strip(), corps.accord
    )
    await journaliser(user, "relation.temoignage_ajoute", organization_id, {"accord": corps.accord})
    return TemoignageOut(**temoignage)


@router.patch("/clients/{organization_id}/temoignages/{temoignage_id}", status_code=204)
async def regler_accord(
    organization_id: int, temoignage_id: int, corps: TemoignagePatch, user: UserModel = Depends(membre)
) -> None:
    await hub.client_ouvert(user, organization_id)
    if not await db_client.regler_accord_temoignage_relation(organization_id, temoignage_id, corps.accord):
        raise HTTPException(status_code=404, detail="Testimonial not found")
    await journaliser(
        user, "relation.temoignage_accord", organization_id, {"temoignage_id": temoignage_id, "accord": corps.accord}
    )


@router.delete("/clients/{organization_id}/temoignages/{temoignage_id}", status_code=204)
async def supprimer_temoignage(organization_id: int, temoignage_id: int, user: UserModel = Depends(membre)) -> None:
    await hub.client_ouvert(user, organization_id)
    if not await db_client.supprimer_temoignage_relation(organization_id, temoignage_id):
        raise HTTPException(status_code=404, detail="Testimonial not found")
    await journaliser(user, "relation.temoignage_supprime", organization_id, {"temoignage_id": temoignage_id})


# ---------------------------------------------------------------------- entrées dans les portails
@router.get("/entrees", response_model=list[EntreeOut])
async def lister_entrees(user: UserModel = Depends(membre)) -> list[EntreeOut]:
    noms = await hub.clients_ouverts(user)
    return [
        EntreeOut(**{**e, "client": noms.get(e["organization_id"], "")})
        for e in await db_client.lister_entrees_relation(noms)
    ]


@router.post("/clients/{organization_id}/entree", response_model=EntreeCreee, status_code=201)
async def ouvrir_son_portail(
    organization_id: int, corps: EntreeIn, user: UserModel = Depends(membre)
) -> EntreeCreee:
    """« Ouvrir son portail » : un lien signé d'une minute, à usage unique, pour ce client et ce membre.

    Le jeton n'est rendu qu'ici, une fois ; seule son empreinte est gardée. Le portail le présente à
    ``POST /organizations/relation/entree/verifier`` avec la clé de ce client.
    """
    await hub.client_ouvert(user, organization_id)
    return EntreeCreee(**await hub.creer_lien(user, organization_id, corps.motif))
