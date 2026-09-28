"""[.mark] Chantier correctifs-modules, lot 1 : l'outil de la fiche.

Plan : ``Labo-agent-vocal/plans/correctifs-modules/2026-09-28-plan-correctifs-modules.md``.
Chaque test appelle le VRAI gestionnaire de ``noter_information`` (``creer_gestionnaire``)
comme le modèle l'appelle, sur une fiche où les traces des modules sont écrites comme les
modules les écrivent.

| Test | Décision | Preuve (runs) |
|---|---|---|
| un oui lève la confirmation | D6 | 869, 871, 873, 879, 881 |
| un non ne lève rien | D6 (sens inverse) | — |
| l'option renvoyée avec son complément est l'option proposée | D6 | 881 |
| la normalisation (pluriel, nombres) passe le contrôle « dit tel quel » | D8 | 870 |
| une valeur confirmée renvoyée n'est jamais redemandée | D8 | 870, 879 |
| l'épellation lue par le module prime sur l'écriture du modèle | lot 1 | 863, 879 |
| le champ cumulatif ajoute sans écraser | D7 | 879 |
| les valeurs d'une liste fermée sont montrées au modèle | lot 1 | 863, 866 à 868 |
"""

from types import SimpleNamespace

import pytest

from api.schemas.fiche_agent import ChampFiche
from api.schemas.lexique_metier import LexiqueMetier
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_ETAT,
    CLE_TOUR,
    ReglagesFiche,
    creer_gestionnaire,
    schema_outil,
)

LEXIQUE = LexiqueMetier.model_validate(
    {"termes": [{"terme": "Edilkamin", "type": "nom"}, {"terme": "Nordica", "type": "nom"}]}
)


def _reglages(*champs: dict, lexique=LEXIQUE) -> ReglagesFiche:
    return ReglagesFiche.depuis(
        {"fiche_au_fil_de_leau": True, "fiche_champs": list(champs)}, lexique=lexique
    )


class Appel:
    """Une fiche, les messages que le modèle a lus, et le vrai gestionnaire de l'outil."""

    def __init__(self, reglages: ReglagesFiche):
        self.fiche: dict = {}
        self.messages: list[dict] = []
        self._outil = creer_gestionnaire(reglages, lambda: self.fiche, lambda: self.messages)
        self._n = 0

    def dit(self, parole: str, agent_avant: str | None = None) -> None:
        """Un nouveau tour de l'appelant, compté comme le compte la lecture de l'appelant."""
        if agent_avant:
            self.messages.append({"role": "assistant", "content": agent_avant})
        self.messages.append({"role": "user", "content": parole})
        self.fiche[CLE_TOUR] = int(self.fiche.get(CLE_TOUR) or 0) + 1

    def trace(self, cle: str, **entree) -> None:
        self.fiche.setdefault(cle, []).append({**entree, "tour": self.fiche.get(CLE_TOUR)})

    async def note(self, **arguments) -> dict:
        self._n += 1
        recu = {}

        async def rappel(resultat, properties=None):
            recu["r"] = resultat

        await self._outil(
            SimpleNamespace(arguments=arguments, tool_call_id=f"n{self._n}", result_callback=rappel)
        )
        return recu["r"]

    def sure(self, champ: str) -> bool:
        return bool(((self.fiche.get(CLE_ETAT) or {}).get(champ) or {}).get("sure"))


def _a_faire_confirmer(resultat: dict) -> set[str]:
    return {c["champ"] for c in (resultat.get("a_confirmer") or []) + (resultat.get("a_proposer") or [])}


MARQUE = {"nom": "marque", "origine": "dicte", "lecteur": "lexique"}
COMMUNE = {"nom": "commune", "origine": "dicte"}
ADRESSE = {"nom": "adresse", "origine": "dicte", "lecteur": "aucun"}
NOM = {"nom": "nom", "origine": "dicte"}


# --- D6 : le « oui » lève la confirmation -------------------------------------


async def _marque_a_confirmer() -> Appel:
    """Une marque hors du lexique : notée, elle est à faire confirmer (depuis D3,
    une marque RECOMMANDÉE par le lexique est retenue sans question)."""
    appel = Appel(_reglages(MARQUE))
    appel.dit("j'ai un appareil Zorvex")
    r = await appel.note(marque="Zorvex")
    assert _a_faire_confirmer(r) == {"marque"} and not appel.sure("marque")
    return appel


@pytest.mark.asyncio
async def test_un_oui_leve_la_confirmation_d_une_valeur_renvoyee_a_l_identique():
    appel = await _marque_a_confirmer()
    appel.dit("Oui, c'est ça.", agent_avant="C'est bien de la marque Zorvex ?")
    r = await appel.note(marque="Zorvex")
    assert not _a_faire_confirmer(r), r
    assert appel.sure("marque") and appel.fiche["marque"] == "Zorvex"


@pytest.mark.asyncio
async def test_un_non_ne_leve_rien():
    appel = await _marque_a_confirmer()
    appel.dit("Non, pas du tout.", agent_avant="C'est bien de la marque Zorvex ?")
    r = await appel.note(marque="Zorvex")
    assert not appel.sure("marque"), r


@pytest.mark.asyncio
async def test_un_oui_sur_une_autre_valeur_ne_leve_rien():
    appel = await _marque_a_confirmer()
    appel.dit("Oui, c'est une Nordica en fait.")
    await appel.note(marque="Zorvex")
    assert not appel.sure("marque")


@pytest.mark.asyncio
async def test_l_option_renvoyee_avec_son_complement_est_l_option_proposee():
    appel = Appel(_reglages(COMMUNE))
    appel.dit("j'habite à ponce")
    appel.trace(
        "communes_verifiees",
        entendu="ponce",
        statut="a_confirmer",
        commune_retenue=None,
        propositions=[
            {"nom": "Pont-Sainte-Maxence", "code_insee": "60509", "departement": "Oise", "codes_postaux": ["60700"]},
            {"nom": "Ponthion", "code_insee": "51441", "departement": "Marne", "codes_postaux": ["51300"]},
        ],
    )
    r = await appel.note(commune="ponce")
    assert _a_faire_confirmer(r) == {"commune"}
    appel.dit("Oui, c'est bien ça.", agent_avant="C'est bien Pont-Sainte-Maxence, dans l'Oise ?")
    r = await appel.note(commune="Pont-Sainte-Maxence (Oise)")
    assert not _a_faire_confirmer(r), r
    assert appel.fiche["commune"] == "Pont-Sainte-Maxence" and appel.sure("commune")
    assert appel.fiche["commune_insee"] == "60509"


# --- D8 : le contrôle « dit tel quel » après normalisation ---------------------


@pytest.mark.asyncio
async def test_la_normalisation_passe_le_controle_dit_tel_quel():
    appel = Appel(_reglages(ADRESSE))
    appel.dit("c'est au 2 places Victor Hugo")
    r = await appel.note(adresse="2 place Victor Hugo")
    assert r["statut"] == "note", r
    assert appel.fiche["adresse"] == "2 place Victor Hugo"


@pytest.mark.asyncio
async def test_la_normalisation_des_nombres_passe_le_controle_dit_tel_quel():
    appel = Appel(_reglages(ADRESSE))
    appel.dit("c'est au deux places Victor Hugo")
    r = await appel.note(adresse="2 place Victor Hugo")
    assert r["statut"] == "note", r


@pytest.mark.asyncio
async def test_une_valeur_confirmee_renvoyee_n_est_jamais_redemandee():
    appel = Appel(_reglages({"nom": "adresse", "origine": "dicte"}))
    appel.dit("c'est au 6 rue Danton")
    appel.trace("voies_verifiees", entendu="6 rue Danton", statut="sure", voie_retenue="Rue Danton", propositions=[])
    await appel.note(adresse="6 rue Danton")
    assert appel.sure("adresse")
    appel.dit("voilà, et c'est tout")
    r = await appel.note(adresse="6 Rue Danton")
    assert not _a_faire_confirmer(r) and not r.get("refuses"), r
    assert appel.sure("adresse")


# --- L'épellation lue par le module prime -------------------------------------


@pytest.mark.asyncio
async def test_l_epellation_lue_prime_sur_l_ecriture_du_modele():
    appel = Appel(_reglages(NOM))
    appel.dit("c'est Delacres, d e l a deux t r e")
    appel.trace("epellations_lues", entendu="d e l a deux t r e", epele="Delattre")
    r = await appel.note(nom="DELACRES")
    assert appel.fiche["nom"] == "Delattre", (appel.fiche, r)


@pytest.mark.asyncio
async def test_l_epellation_lue_prime_quand_le_modele_colle_deux_mots():
    appel = Appel(_reglages(NOM))
    appel.dit("fort f a u r e")
    appel.trace("epellations_lues", entendu="f a u r e", epele="Faure")
    await appel.note(nom="FORTEFAURE")
    assert appel.fiche["nom"] == "Faure"


@pytest.mark.asyncio
async def test_l_epellation_ne_touche_pas_une_reference_avec_des_chiffres():
    appel = Appel(_reglages({"nom": "reference", "origine": "dicte"}))
    appel.dit("c'est la f a 20457")
    appel.trace("epellations_lues", entendu="f a", epele="Fa")
    await appel.note(reference="FA20457")
    assert appel.fiche["reference"] == "FA20457"


@pytest.mark.asyncio
async def test_l_epellation_d_un_tour_passe_ne_s_impose_pas():
    appel = Appel(_reglages(NOM))
    appel.dit("d e l a deux t r e")
    appel.trace("epellations_lues", entendu="d e l a deux t r e", epele="Delattre")
    await appel.note(nom="Delattre")
    appel.dit("en fait c'est Delacroix, mon nom d'usage")
    await appel.note(nom="Delacroix")
    assert appel.fiche["nom"] == "Delacroix"


@pytest.mark.asyncio
async def test_l_epellation_d_un_nom_ne_remplace_pas_le_prenom_voisin():
    """Revue du 28/09 : « Martine Martin, M A R T I N » écrivait le prénom MARTIN.
    Le mot épelé est dit en entier : il confirme ce mot-là, pas le prénom."""
    appel = Appel(_reglages({"nom": "prenom", "origine": "dicte"}, NOM))
    appel.dit("Martine Martin, m a r t i n")
    appel.trace("epellations_lues", entendu="m a r t i n", epele="Martin")
    await appel.note(prenom="Martine", nom="Martin")
    assert (appel.fiche["prenom"], appel.fiche["nom"]) == ("Martine", "Martin")


@pytest.mark.asyncio
async def test_l_epellation_ne_remplace_pas_une_valeur_de_plusieurs_mots():
    appel = Appel(_reglages(NOM))
    appel.dit("Jean Martin, m a r t i n")
    appel.trace("epellations_lues", entendu="m a r t i n", epele="Martin")
    await appel.note(nom="Jean Martin")
    assert appel.fiche["nom"] == "Jean Martin"


# --- D7 : le champ cumulatif --------------------------------------------------


MOTIF = {"nom": "motif", "origine": "deduit", "cumulatif": True}


@pytest.mark.asyncio
async def test_le_champ_cumulatif_ajoute_sans_ecraser():
    appel = Appel(_reglages(MOTIF))
    appel.dit("c'est pour un entretien")
    await appel.note(motif="entretien de l'appareil")
    appel.dit("et aussi une question sur une facture")
    await appel.note(motif="question sur une facture")
    assert "entretien de l'appareil" in appel.fiche["motif"]
    assert "question sur une facture" in appel.fiche["motif"]


@pytest.mark.asyncio
async def test_le_champ_cumulatif_reecrit_en_entier_ne_se_double_pas():
    appel = Appel(_reglages(MOTIF))
    appel.dit("c'est pour un entretien")
    await appel.note(motif="entretien")
    appel.dit("et une facture")
    await appel.note(motif="entretien, puis une question sur une facture")
    assert appel.fiche["motif"] == "entretien, puis une question sur une facture"


@pytest.mark.asyncio
async def test_un_champ_dicte_cumulatif_est_exempt_du_controle_dit_tel_quel():
    appel = Appel(_reglages({"nom": "symptome", "origine": "dicte", "cumulatif": True}))
    appel.dit("il fume un peu")
    r = await appel.note(symptome="fumée à l'allumage")
    assert r["statut"] == "note", r


def test_un_champ_non_cumulatif_par_defaut():
    assert ChampFiche(nom="motif").cumulatif is False


# --- Les valeurs d'une liste fermée, montrées à qui écrit ----------------------


def test_les_valeurs_d_une_liste_fermee_sont_montrees_dans_le_schema_de_l_outil():
    reglages = _reglages({"nom": "urgence", "origine": "deduit", "description": "Le degré", "valeurs": ["danger", "normal"]})
    propriete = schema_outil(reglages).properties["urgence"]
    assert propriete["enum"] == ["danger", "normal"]
    assert "danger" in propriete["description"] and "normal" in propriete["description"]


def test_une_liste_fermee_sur_un_nombre_ne_porte_pas_d_enum():
    """Revue du 28/09 : ``enum`` (des chaînes) sur un champ nombre rendait le schéma
    de l'outil incohérent. La description garde les valeurs permises."""
    proprietes = schema_outil(
        _reglages({"nom": "pieces", "origine": "dicte", "type": "number", "valeurs": ["1", "2"]})
    ).properties
    assert "enum" not in proprietes["pieces"]
    assert "Valeurs permises : 1, 2." in proprietes["pieces"]["description"]
