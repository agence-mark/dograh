"""[.mark] Module Restauration, lot 4 : le LEXIQUE de transcription rempli depuis la carte (module Lexique existant).

Les noms difficiles à transcrire (« Capre e Miel », « Margherita ») entrent dans le lexique de l'organisation (``LexiqueMetier``) :
la transcription les écoute, la correction les rétablit avant que le modèle lise. Le lexique existant n'est JAMAIS modifié : un nom déjà
présent (n'importe laquelle de ses graphies) n'est pas touché (même règle que l'import d'un modèle, ``fusionner_import``).

DANS LA LIMITE DU FOURNISSEUR : le fournisseur de transcription déclare un plafond (``plafond_du_lexique``) ; seuls les noms qui
tiennent dans ce plafond, avec ce que l'organisation écoute déjà, sont cochés « à écouter ». Les autres entrent dans le lexique
(ils gardent la correction et la prononciation) mais ne sont pas envoyés. Sans plafond déclaré : rien n'est coché, comme à l'appel.

Les prioritaires (l'étoile de la carte) passent d'abord ; ensuite l'ordre de la carte.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from api.db.bases_clients.recherche_liste import Element
from api.schemas.lexique_metier import MAX_LONGUEUR_TERME, MAX_TERMES, LexiqueMetier, TermeLexique
from api.services.configuration.plafond_lexique import PlafondLexique
from api.services.lexique.ecoute import construire_liste_ecoutee
from api.services.lexique.stockage import enregistrer_lexique, lire_lexique_strict

CATEGORIE = "Carte"


@dataclass(frozen=True)
class ResultatLexique:
    lexique: LexiqueMetier
    ajoutes: int
    deja_presents: int
    a_ecouter: int  # parmi les ajoutés : cochés « à écouter » (tiennent dans le plafond)
    non_ecoutes: int  # ajoutés mais pas envoyés à la transcription (hors plafond)
    ecartes: int  # trop longs ou sans lettre : jamais écrits


def termes_de_la_liste(elements: Sequence[Element], prioritaires: Iterable[str] = ()) -> list[TermeLexique]:
    """Un terme par élément (nom officiel, synonymes actifs en variantes), les prioritaires d'abord."""
    prioritaires = set(prioritaires)
    ordre = [e for e in elements if e.id in prioritaires] + [e for e in elements if e.id not in prioritaires]
    termes: list[TermeLexique] = []
    for e in ordre:
        if not e.libelle or len(e.libelle) > MAX_LONGUEUR_TERME:
            continue
        variantes = [s for s in e.synonymes if s and len(s) <= MAX_LONGUEUR_TERME][:10]
        try:
            termes.append(TermeLexique(terme=e.libelle, variantes=variantes, nature="nom_propre", categorie=CATEGORIE, a_ecouter=False))
        except ValueError:
            continue  # un nom sans lettre ni chiffre : rien à reconnaître
    return termes


def construire_lexique(
    existant: LexiqueMetier, elements: Sequence[Element], plafond: PlafondLexique | None, prioritaires: Iterable[str] = ()
) -> ResultatLexique:
    voulus = termes_de_la_liste(elements, prioritaires)
    ecartes = len(elements) - len(voulus)
    presentes: set[str] = set()
    for t in existant.termes:
        presentes |= t.formes_normalisees()
    ajoutes: list[TermeLexique] = []
    deja = 0
    for t in voulus:
        formes = t.formes_normalisees()
        if formes & presentes:
            deja += 1
            continue
        if len(existant.termes) + len(ajoutes) >= MAX_TERMES:
            ecartes += 1
            continue
        ajoutes.append(t)
        presentes |= formes
    # On coche dans l'ordre tant que la liste ENVOYÉE (ce que l'organisation écoute déjà + ces noms) tient dans le plafond.
    termes = list(existant.termes) + ajoutes
    coches = 0
    if plafond is not None:
        base = len(existant.termes)
        for rang in range(len(ajoutes)):
            essai = termes[:]
            essai[base + rang] = essai[base + rang].model_copy(update={"a_ecouter": True})
            if construire_liste_ecoutee(None, LexiqueMetier(termes=essai, seuil_mots_courants=existant.seuil_mots_courants), plafond).non_envoyes:
                continue  # celui-là ne tient pas : on essaie le suivant (un long nom ne coûte pas les courts derrière)
            termes = essai
            coches += 1
    fusion = LexiqueMetier.model_validate(
        {"modeles_importes": [m.model_dump() for m in existant.modeles_importes], "termes": [t.model_dump() for t in termes], "seuil_mots_courants": existant.seuil_mots_courants}
    )
    return ResultatLexique(fusion, len(ajoutes), deja, coches, len(ajoutes) - coches, ecartes)


async def remplir_le_lexique(
    organization_id: int, elements: Sequence[Element], plafond: PlafondLexique | None, prioritaires: Iterable[str] = ()
) -> ResultatLexique:
    """Lit le lexique de l'organisation (strict : illisible = on n'écrase rien), y verse les noms de la liste, l'écrit."""
    resultat = construire_lexique(await lire_lexique_strict(organization_id), elements, plafond, prioritaires)
    if resultat.ajoutes:
        await enregistrer_lexique(organization_id, resultat.lexique)
    return resultat
