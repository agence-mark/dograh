"""[.mark] Le Hub « Relation clients » : accès aux tables de ``models_relation`` (U3 septies, E78).

Chaque lecture et chaque écriture est bornée à l'organisation (R0). ``avec_internes`` décide si les notes internes
sont rendues : l'API du client ne le met JAMAIS à vrai.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Iterable

from sqlalchemy import func, or_, select, update

from api.db.base_client import BaseDBClient
from api.db.models_relation import (
    MarkRelationEntreeModel,
    MarkRelationFilModel,
    MarkRelationMessageModel,
    MarkRelationNoteModel,
    MarkRelationTemoignageModel,
)

ETATS_FIL = ("nouveau", "en_cours", "repondu", "clos")
ETATS_DEMANDE = ("nouvelle", "proposee", "a_coder", "refusee")
COTES = ("client", "mark", "interne")


def _fil(f: MarkRelationFilModel) -> dict[str, Any]:
    return {
        "id": f.id,
        "organization_id": f.organization_id,
        "sorte": f.sorte,
        "sujet": f.sujet,
        "etat": f.etat,
        "suivi_par": f.suivi_par,
        "suivi_nom": f.suivi_nom,
        "lu_par_mark": f.lu_par_mark,
        "logiciel": f.logiciel,
        "catalogue": f.catalogue,
        "etat_demande": f.etat_demande,
        "cree_le": f.cree_le,
        "modifie_le": f.modifie_le,
    }


def _message(m: MarkRelationMessageModel) -> dict[str, Any]:
    return {"id": m.id, "cote": m.cote, "auteur": m.auteur, "texte": m.texte, "cree_le": m.cree_le}


class RelationClient(BaseDBClient):
    # ------------------------------------------------------------------ fils et messages
    async def creer_fil_relation(
        self,
        organization_id: int,
        *,
        sorte: str,
        sujet: str,
        auteur: str,
        texte: str,
        logiciel: str | None = None,
        catalogue: str | None = None,
    ) -> dict[str, Any]:
        """Un fil écrit par le client (le premier message est du côté client)."""
        async with self.async_session() as session:
            fil = MarkRelationFilModel(
                organization_id=organization_id,
                sorte=sorte,
                sujet=sujet[:200],
                etat="nouveau",
                logiciel=(logiciel or None) and logiciel[:120],
                catalogue=(catalogue or None) and catalogue[:120],
                etat_demande="nouvelle" if sorte == "demande_logiciel" else None,
            )
            session.add(fil)
            await session.flush()
            session.add(
                MarkRelationMessageModel(
                    fil_id=fil.id,
                    organization_id=organization_id,
                    cote="client",
                    auteur=auteur[:160],
                    texte=texte,
                )
            )
            await session.commit()
            await session.refresh(fil)
            return _fil(fil)

    async def ajouter_message_relation(
        self, organization_id: int, fil_id: int, *, cote: str, auteur: str, texte: str
    ) -> dict[str, Any] | None:
        """Ajoute un message au fil de CETTE organisation ; ``None`` si le fil n'est pas la sienne (ou est clos pour le client)."""
        async with self.async_session() as session:
            fil = (
                await session.execute(
                    select(MarkRelationFilModel)
                    .where(
                        MarkRelationFilModel.id == fil_id,
                        MarkRelationFilModel.organization_id == organization_id,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if fil is None:
                return None
            message = MarkRelationMessageModel(
                fil_id=fil.id,
                organization_id=organization_id,
                cote=cote,
                auteur=auteur[:160],
                texte=texte,
            )
            session.add(message)
            if cote == "client":
                fil.etat = "nouveau"
                fil.lu_par_mark = False
            elif cote == "mark":
                fil.etat = "repondu"
                fil.lu_par_mark = True
            fil.modifie_le = datetime.now(UTC)
            await session.commit()
            await session.refresh(message)
            return _message(message)

    async def lire_fil_relation(
        self, organization_id: int, fil_id: int, *, avec_internes: bool
    ) -> dict[str, Any] | None:
        async with self.async_session() as session:
            fil = (
                await session.execute(
                    select(MarkRelationFilModel)
                    .where(
                        MarkRelationFilModel.id == fil_id,
                        MarkRelationFilModel.organization_id == organization_id,
                    )
                    .execution_options(populate_existing=True)
                )
            ).scalar_one_or_none()
            if fil is None:
                return None
            requete = select(MarkRelationMessageModel).where(
                MarkRelationMessageModel.fil_id == fil.id,
                MarkRelationMessageModel.organization_id == organization_id,
            )
            if not avec_internes:
                requete = requete.where(MarkRelationMessageModel.cote != "interne")
            messages = (await session.execute(requete.order_by(MarkRelationMessageModel.id))).scalars().all()
            return {**_fil(fil), "messages": [_message(m) for m in messages]}

    async def lister_fils_relation(
        self,
        organisations: Iterable[int],
        *,
        etat: str | None = None,
        sorte: str | None = None,
        suivi_par: int | None = None,
        a_traiter: bool = False,
        recherche: str | None = None,
        limite: int = 200,
        avec_internes: bool = False,
    ) -> list[dict[str, Any]]:
        """Les fils des organisations données, le plus récent d'abord, avec leur dernier message."""
        ids = sorted(set(organisations))
        if not ids:
            return []
        async with self.async_session() as session:
            requete = select(MarkRelationFilModel).where(MarkRelationFilModel.organization_id.in_(ids))
            if etat:
                requete = requete.where(MarkRelationFilModel.etat == etat)
            if sorte:
                requete = requete.where(MarkRelationFilModel.sorte == sorte)
            if suivi_par is not None:
                requete = requete.where(MarkRelationFilModel.suivi_par == suivi_par)
            if a_traiter:
                requete = requete.where(MarkRelationFilModel.etat.in_(("nouveau", "en_cours")))
            if recherche:
                motif = f"%{recherche.strip()[:80]}%"
                requete = requete.where(
                    or_(
                        MarkRelationFilModel.sujet.ilike(motif),
                        MarkRelationFilModel.logiciel.ilike(motif),
                    )
                )
            fils = (
                await session.execute(
                    requete.order_by(MarkRelationFilModel.modifie_le.desc(), MarkRelationFilModel.id.desc()).limit(
                        limite
                    )
                )
            ).scalars().all()
            sortie = []
            for f in fils:
                demande = select(MarkRelationMessageModel).where(
                    MarkRelationMessageModel.fil_id == f.id,
                    MarkRelationMessageModel.organization_id == f.organization_id,
                )
                if not avec_internes:
                    demande = demande.where(MarkRelationMessageModel.cote != "interne")
                dernier = (
                    await session.execute(demande.order_by(MarkRelationMessageModel.id.desc()).limit(1))
                ).scalar_one_or_none()
                sortie.append({**_fil(f), "dernier": _message(dernier) if dernier else None})
            return sortie

    async def modifier_fil_relation(
        self, organization_id: int, fil_id: int, champs: dict[str, Any]
    ) -> bool:
        """Modifie l'état, le suivi, la lecture ou l'état de la demande d'un fil de CETTE organisation."""
        permis = {"etat", "suivi_par", "suivi_nom", "lu_par_mark", "etat_demande", "catalogue"}
        valeurs = {k: v for k, v in champs.items() if k in permis}
        if not valeurs:
            return False
        async with self.async_session() as session:
            resultat = await session.execute(
                update(MarkRelationFilModel)
                .where(
                    MarkRelationFilModel.id == fil_id,
                    MarkRelationFilModel.organization_id == organization_id,
                )
                .values(**valeurs, modifie_le=datetime.now(UTC))
            )
            await session.commit()
            return resultat.rowcount > 0

    async def compter_fils_relation(self, organisations: Iterable[int]) -> dict[int, dict[str, int]]:
        """Par organisation : fils ouverts, non lus, demandes nouvelles."""
        ids = sorted(set(organisations))
        if not ids:
            return {}
        async with self.async_session() as session:
            lignes = (
                await session.execute(
                    select(
                        MarkRelationFilModel.organization_id,
                        func.count().filter(MarkRelationFilModel.etat != "clos"),
                        func.count().filter(MarkRelationFilModel.lu_par_mark.is_(False), MarkRelationFilModel.etat != "clos"),
                        func.count().filter(MarkRelationFilModel.etat_demande == "nouvelle"),
                    )
                    .where(MarkRelationFilModel.organization_id.in_(ids))
                    .group_by(MarkRelationFilModel.organization_id)
                )
            ).all()
            return {o: {"ouverts": a, "non_lus": b, "demandes_nouvelles": c} for o, a, b, c in lignes}

    # ------------------------------------------------------------------ notes sur un client
    async def lister_notes_relation(self, organization_id: int) -> list[dict[str, Any]]:
        async with self.async_session() as session:
            notes = (
                await session.execute(
                    select(MarkRelationNoteModel)
                    .where(MarkRelationNoteModel.organization_id == organization_id)
                    .order_by(MarkRelationNoteModel.id.desc())
                )
            ).scalars().all()
            return [{"id": n.id, "auteur": n.auteur, "texte": n.texte, "cree_le": n.cree_le} for n in notes]

    async def ajouter_note_relation(self, organization_id: int, auteur: str, texte: str) -> dict[str, Any]:
        async with self.async_session() as session:
            note = MarkRelationNoteModel(organization_id=organization_id, auteur=auteur[:160], texte=texte)
            session.add(note)
            await session.commit()
            await session.refresh(note)
            return {"id": note.id, "auteur": note.auteur, "texte": note.texte, "cree_le": note.cree_le}

    async def supprimer_note_relation(self, organization_id: int, note_id: int) -> bool:
        async with self.async_session() as session:
            note = (
                await session.execute(
                    select(MarkRelationNoteModel).where(
                        MarkRelationNoteModel.id == note_id,
                        MarkRelationNoteModel.organization_id == organization_id,
                    )
                )
            ).scalar_one_or_none()
            if note is None:
                return False
            await session.delete(note)
            await session.commit()
            return True

    # ------------------------------------------------------------------ témoignages
    async def lister_temoignages_relation(self, organisations: Iterable[int]) -> list[dict[str, Any]]:
        ids = sorted(set(organisations))
        if not ids:
            return []
        async with self.async_session() as session:
            lignes = (
                await session.execute(
                    select(MarkRelationTemoignageModel)
                    .where(MarkRelationTemoignageModel.organization_id.in_(ids))
                    .order_by(MarkRelationTemoignageModel.id.desc())
                )
            ).scalars().all()
            return [
                {
                    "id": t.id,
                    "organization_id": t.organization_id,
                    "texte": t.texte,
                    "auteur": t.auteur,
                    "accord": t.accord,
                }
                for t in lignes
            ]

    async def ajouter_temoignage_relation(
        self, organization_id: int, texte: str, auteur: str, accord: bool
    ) -> dict[str, Any]:
        async with self.async_session() as session:
            t = MarkRelationTemoignageModel(
                organization_id=organization_id, texte=texte, auteur=auteur[:160], accord=accord
            )
            session.add(t)
            await session.commit()
            await session.refresh(t)
            return {"id": t.id, "organization_id": t.organization_id, "texte": t.texte, "auteur": t.auteur, "accord": t.accord}

    async def regler_accord_temoignage_relation(self, organization_id: int, temoignage_id: int, accord: bool) -> bool:
        async with self.async_session() as session:
            resultat = await session.execute(
                update(MarkRelationTemoignageModel)
                .where(
                    MarkRelationTemoignageModel.id == temoignage_id,
                    MarkRelationTemoignageModel.organization_id == organization_id,
                )
                .values(accord=accord)
            )
            await session.commit()
            return resultat.rowcount > 0

    async def supprimer_temoignage_relation(self, organization_id: int, temoignage_id: int) -> bool:
        async with self.async_session() as session:
            t = (
                await session.execute(
                    select(MarkRelationTemoignageModel).where(
                        MarkRelationTemoignageModel.id == temoignage_id,
                        MarkRelationTemoignageModel.organization_id == organization_id,
                    )
                )
            ).scalar_one_or_none()
            if t is None:
                return False
            await session.delete(t)
            await session.commit()
            return True

    # ------------------------------------------------------------------ entrées dans les portails
    async def creer_entree_relation(
        self,
        organization_id: int,
        user_id: int | None,
        auteur: str,
        motif: str | None,
        empreinte: str,
        expire_le: datetime,
    ) -> dict[str, Any]:
        async with self.async_session() as session:
            e = MarkRelationEntreeModel(
                organization_id=organization_id,
                user_id=user_id,
                auteur=auteur[:160],
                motif=(motif or None) and motif[:200],
                empreinte_jeton=empreinte,
                expire_le=expire_le,
            )
            session.add(e)
            await session.commit()
            await session.refresh(e)
            return {"id": e.id, "expire_le": e.expire_le}

    async def consommer_entree_relation(
        self, organization_id: int, empreinte: str, maintenant: datetime
    ) -> dict[str, Any] | None:
        """Consomme le lien : d'UNE organisation, jamais utilisé, pas expiré. Atomique : un seul appel y arrive."""
        async with self.async_session() as session:
            resultat = await session.execute(
                update(MarkRelationEntreeModel)
                .where(
                    MarkRelationEntreeModel.empreinte_jeton == empreinte,
                    MarkRelationEntreeModel.organization_id == organization_id,
                    MarkRelationEntreeModel.utilise_le.is_(None),
                    MarkRelationEntreeModel.expire_le > maintenant,
                )
                .values(utilise_le=maintenant)
                .returning(
                    MarkRelationEntreeModel.id,
                    MarkRelationEntreeModel.auteur,
                    MarkRelationEntreeModel.motif,
                )
            )
            ligne = resultat.first()
            await session.commit()
            return {"id": ligne[0], "auteur": ligne[1], "motif": ligne[2]} if ligne else None

    async def lister_entrees_relation(
        self, organisations: Iterable[int], limite: int = 200
    ) -> list[dict[str, Any]]:
        ids = sorted(set(organisations))
        if not ids:
            return []
        async with self.async_session() as session:
            lignes = (
                await session.execute(
                    select(MarkRelationEntreeModel)
                    .where(MarkRelationEntreeModel.organization_id.in_(ids))
                    .order_by(MarkRelationEntreeModel.id.desc())
                    .limit(limite)
                )
            ).scalars().all()
            return [
                {
                    "id": e.id,
                    "organization_id": e.organization_id,
                    "auteur": e.auteur,
                    "motif": e.motif,
                    "cree_le": e.cree_le,
                    "utilise_le": e.utilise_le,
                }
                for e in lignes
            ]
