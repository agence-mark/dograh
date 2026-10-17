"""[.mark] Chantier agents-specialises, lot 17 : la fiche à plusieurs demandes.

La fiche d'un appel est un seul formulaire (une case par champ), partagé par tous les agents.
Un appel qui porte deux demandes sur deux objets différents n'avait qu'une case par champ : le
second spécialiste écrasait la première demande ou redemandait tout.

Chaque champ a une **portée** (``ChampFiche.portee``) :

- ``appel`` : commun à tout l'appel, ce qui concerne l'appelant (coordonnées) ;
- ``demande`` : propre à une demande, clos avec elle.

**Vide = portée par défaut**, calculée par les réglages génériques de l'agent (lecteurs commune
et rue, nom d'une personne, reconnaissance des champs : téléphone, code postal, courriel, communes)
et jamais écrite en base. Aucun nom de champ, de motif ni de métier ici : tout vient de la
configuration.

Le moteur ouvre une demande à chaque passation vers un spécialisé qui n'est pas le premier à avoir
travaillé dans l'appel (``ouvrir_une_demande``) : la demande en cours est close dans ``demandes``,
ses champs « demande » quittent la vue à plat de la fiche (``fiche_etat`` et les variables
extraites), les champs « appel » restent. La vue à plat est lue telle quelle par tout ce qui existe
(greffier, ``noter_information``, mail, base) : rien ne change pour eux.

⛔ Un agent seul, un appel à une seule demande : ``demandes`` n'apparaît jamais, aucune clé n'est
écrite (zéro perte). Chaque fonction est pure et ne lève jamais.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from loguru import logger

from api.schemas.fiche_agent import ChampFiche, cle_dit, cle_insee, est_un_champ_de_nom

CLE_DEMANDES = "demandes"
# Revue du 16/10 : la demande du spécialisé, photographiée au retour au principal ; la clôture
# suivante se fait sur cette photo (ce que le principal note ensuite va à la nouvelle demande).
CLE_PHOTO = "demande_au_retour"
CLE_ETAT = "fiche_etat"
CLE_EXTRAITES = "extracted_variables"
APPEL = "appel"
DEMANDE = "demande"
PORTEES = (APPEL, DEMANDE)

# Les types reconnus par les réglages de l'agent (« Field recognition » et les communes) dont un
# champ est une coordonnée de l'appelant : valables pour toute la durée de l'appel.
TYPES_DE_COORDONNEES = ("commune", "telephone", "code_postal", "courriel")
LECTEURS_DE_COORDONNEES = ("commune", "rue")
RAISON_RETOUR = "retour"


def _vide(valeur: Any) -> bool:
    if valeur is None:
        return True
    if isinstance(valeur, str):
        return not valeur.strip()
    if isinstance(valeur, (list, tuple, set, dict)):
        return len(valeur) == 0
    return False


def _correspond(nom: str, motifs: Iterable[str]) -> bool:
    from api.services.fiche.controle import correspond

    return correspond(nom, tuple(motifs or ()))


def portee_par_defaut(champ: ChampFiche, motifs_des_types: Mapping[str, Any] | None) -> str:
    """La portée d'un champ qui n'en a pas choisi : ``appel`` quand les réglages de l'agent le
    reconnaissent comme une coordonnée (lecteur commune ou rue ; nom d'une personne ; noms
    réglés pour les communes, le téléphone, le code postal, le courriel), ``demande`` sinon.
    ⛔ Ne lève jamais (au pire : ``demande``)."""
    try:
        if champ.lecteur_effectif in LECTEURS_DE_COORDONNEES or est_un_champ_de_nom(champ):
            return APPEL
        motifs = motifs_des_types or {}
        if any(_correspond(champ.nom, motifs.get(t)) for t in TYPES_DE_COORDONNEES):
            return APPEL
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[demandes] portée par défaut illisible ({champ.nom}) : {erreur!r}")
    return DEMANDE


def portee_effective(champ: ChampFiche, motifs_des_types: Mapping[str, Any] | None) -> str:
    """La portée choisie à l'écran, sinon celle par défaut."""
    if champ.portee in PORTEES:
        return champ.portee
    return portee_par_defaut(champ, motifs_des_types)


def _champs(reglages: Any) -> tuple[ChampFiche, ...]:
    return tuple(getattr(reglages, "champs", None) or ())


def portees_de(reglages: Any) -> dict[str, str]:
    """Nom du champ -> portée, pour la fiche de l'appel."""
    motifs = getattr(reglages, "motifs_des_types", None) or {}
    return {c.nom: portee_effective(c, motifs) for c in _champs(reglages)}


def cles_du_champ(champ: ChampFiche) -> tuple[str, ...]:
    """Les clés que la fiche écrit pour ce champ : lui-même, le code INSEE d'une commune sûre,
    les mots de la personne pour une date. Elles voyagent avec lui."""
    cles = [champ.nom]
    if champ.lecteur_effectif == "commune":
        cles.append(cle_insee(champ.nom))
    if champ.lecteur_effectif == "date":
        cles.append(cle_dit(champ.nom))
    return tuple(cles)


def demandes_closes(gathered: Mapping[str, Any] | None) -> list[dict]:
    try:
        brut = (gathered or {}).get(CLE_DEMANDES) or []
        return [b for b in brut if isinstance(b, dict)]
    except Exception:  # noqa: BLE001
        return []


def texte_court(valeur: Any) -> str | None:
    """Une valeur de la fiche en une ligne (liste : valeurs jointes par « ; »)."""
    if _vide(valeur):
        return None
    if isinstance(valeur, (list, tuple)):
        morceaux = [str(v).strip() for v in valeur if not _vide(v)]
        return " ; ".join(morceaux) or None
    return " ".join(str(valeur).split())


def dernier_specialise(
    gathered: Mapping[str, Any] | None, principal_id: int | None
) -> int | None:
    """Le dernier agent spécialisé à avoir pris la main (passation partie et aboutie, hors
    retour au principal), ``None`` si aucun n'a encore travaillé dans cet appel."""
    try:
        trouve = None
        for entree in (gathered or {}).get("passations") or []:
            if not isinstance(entree, dict) or entree.get("refusee"):
                continue
            if entree.get("issue", "completed") != "completed":
                continue
            vers = entree.get("vers")
            if vers is None or vers == principal_id or entree.get("raison") == RAISON_RETOUR:
                continue
            trouve = vers
        return trouve
    except Exception:  # noqa: BLE001
        return None


def champs_de_la_demande_en_cours(reglages: Any, gathered: Mapping[str, Any]) -> list[ChampFiche]:
    """Les champs de portée « demande » que la demande en cours a remplis."""
    portees = portees_de(reglages)
    return [
        c
        for c in _champs(reglages)
        if portees.get(c.nom) == DEMANDE and not _vide(gathered.get(c.nom))
    ]


def photographier_la_demande(gathered: dict, reglages: Any) -> None:
    """Au retour au principal : la photo des champs « demande » remplis (valeurs à cet instant).
    Rien à photographier : la photo d'avant est retirée. ⛔ Ne lève jamais."""
    try:
        if reglages is None:
            return
        photo = {
            cle: gathered[cle]
            for champ in champs_de_la_demande_en_cours(reglages, gathered)
            for cle in cles_du_champ(champ)
            if cle in gathered and not _vide(gathered.get(cle))
        }
        if photo:
            gathered[CLE_PHOTO] = photo
        else:
            gathered.pop(CLE_PHOTO, None)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[demandes] photo de la demande au retour non prise : {erreur!r}")


def ouvrir_une_demande(
    gathered: dict,
    reglages: Any,
    *,
    vers_un_specialise: bool,
    principal_id: int | None,
    noms_des_agents: Mapping[Any, str | None] | None = None,
    champ_motif: str | None = None,
) -> dict | None:
    """Ouverture d'une demande, à la passation : rend le bloc clos, ou ``None`` (rien fait).

    Une demande se clôt quand l'appel passe à un spécialisé (jamais au retour au principal) et que
    la demande en cours est celle d'un spécialisé déjà passé : sans cela, la première passation
    couperait en deux l'unique demande d'un appel (la qualification du principal, puis le travail
    du spécialisé), et un appel à une demande ne produirait plus ce qu'il produit aujourd'hui.
    Aucun champ « demande » rempli : rien à clore. ⛔ Ne lève jamais."""
    try:
        if reglages is None or not vers_un_specialise:
            return None
        proprietaire = dernier_specialise(gathered, principal_id)
        if proprietaire is None:
            return None
        photo = gathered.get(CLE_PHOTO) if isinstance(gathered.get(CLE_PHOTO), dict) else None
        remplis = champs_de_la_demande_en_cours(reglages, gathered)
        if photo:
            # Revue du 16/10 : les champs de la photo, même réécrits depuis par le principal.
            remplis = [
                c
                for c in _champs(reglages)
                if portees_de(reglages).get(c.nom) == DEMANDE
                and any(cle in photo for cle in cles_du_champ(c))
            ]
        if not remplis:
            gathered.pop(CLE_PHOTO, None)
            return None
        portees = portees_de(reglages)
        etat = gathered.get(CLE_ETAT) if isinstance(gathered.get(CLE_ETAT), dict) else {}
        extraites = (
            gathered.get(CLE_EXTRAITES) if isinstance(gathered.get(CLE_EXTRAITES), dict) else {}
        )
        champs: dict[str, Any] = {}
        provenance: dict[str, Any] = {}
        for champ in remplis:
            for cle in cles_du_champ(champ):
                if photo is not None and cle in photo:
                    champs[cle] = photo[cle]
                elif photo is None and cle in gathered and not _vide(gathered.get(cle)):
                    champs[cle] = gathered[cle]
                if isinstance(etat.get(cle), dict):
                    provenance[cle] = dict(etat[cle])
        # Un champ propre à la demande sans valeur ne bouge pas ; une valeur lue ailleurs que dans la
        # vue à plat (variables extraites seulement) suit aussi son champ.
        for champ in remplis:
            for cle in cles_du_champ(champ):
                if cle not in champs and not _vide(extraites.get(cle)):
                    champs[cle] = extraites[cle]
        bloc: dict[str, Any] = {
            "ordre": len(demandes_closes(gathered)) + 1,
            "agent_id": proprietaire,
            "agent": (noms_des_agents or {}).get(proprietaire) or None,
            "motif": texte_court(champs.get(champ_motif)) if champ_motif else None,
            "motif_champ": champ_motif if champ_motif and champ_motif in champs else None,
            "champs": champs,
        }
        if provenance:
            bloc["etat"] = provenance
        # Les champs « appel » de l'appel, à l'heure de la clôture : ils accompagneront chaque
        # bloc dans l'envoi après l'appel (le sens de « appel » est celui des réglages d'alors).
        champs_par_nom = {c.nom: c for c in _champs(reglages)}
        bloc["appel"] = [
            cle
            for nom, p in portees.items()
            if p == APPEL
            for cle in cles_du_champ(champs_par_nom[nom])
        ]
        bloc = {k: v for k, v in bloc.items() if v is not None}
        for champ in remplis:
            for cle in cles_du_champ(champ):
                if photo is not None and cle in photo and gathered.get(cle) != photo[cle]:
                    # Réécrit par le principal depuis le retour : la valeur va à la nouvelle demande.
                    continue
                gathered.pop(cle, None)
                if isinstance(extraites, dict):
                    extraites.pop(cle, None)
                if isinstance(etat, dict):
                    etat.pop(cle, None)
        gathered.pop(CLE_PHOTO, None)
        gathered.setdefault(CLE_DEMANDES, []).append(bloc)
        logger.info(
            f"[demandes] demande {bloc['ordre']} close ({', '.join(champs)}) : "
            "l'appel passe à un spécialisé, la fiche repart d'une demande vide"
        )
        return bloc
    except Exception as erreur:  # noqa: BLE001 -- l'ouverture ne coûte jamais l'appel
        logger.error(f"[demandes] ouverture d'une demande en échec : {erreur!r}")
        return None


def lignes_pour_le_modele(gathered: Mapping[str, Any] | None) -> list[str]:
    """Une ligne par demande close, en lecture : le spécialisé ne les redemande pas et ne les
    écrit pas. Rien (liste vide) sans demande close."""
    lignes: list[str] = []
    for bloc in demandes_closes(gathered):
        morceaux = [bloc.get("motif")] if bloc.get("motif") else []
        for nom, valeur in (bloc.get("champs") or {}).items():
            texte = texte_court(valeur)
            if texte and nom != bloc.get("motif_champ"):
                morceaux.append(f"{nom} = « {texte} »")
        if morceaux:
            lignes.append(
                "Demande déjà traitée (à lire : ne la redemande pas et ne la réécris pas) : "
                + ", ".join(morceaux)
            )
    return lignes


def champs_hors_demandes_closes(reglages: Any, gathered: Mapping[str, Any] | None) -> Any:
    """Les réglages de la fiche pour le filet de fin d'appel : avec des demandes closes, il ne
    relit que les champs « appel » (la relecture de toute la conversation y retrouverait les
    valeurs des demandes closes). Sans demande close : les mêmes réglages, tels quels."""
    try:
        if not demandes_closes(gathered):
            return reglages
        import dataclasses

        portees = portees_de(reglages)
        garde = tuple(c for c in _champs(reglages) if portees.get(c.nom) == APPEL)
        return dataclasses.replace(reglages, champs=garde)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[demandes] filet de fin d'appel : réglages entiers gardés ({erreur!r})")
        return reglages
