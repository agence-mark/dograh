"""[.mark] Garantie : l'alphabet téléphonique est compris partout (plan courriel-dicte, D6, lot 1 bis).

« P comme Pascal, N pour Nathalie, C de Carine » : le mot confirme la lettre, il ne s'écrit pas.
Aucune phrase des 1 142 runs du 13/10 ne le contient : ce corpus est écrit à la main, d'après
les règles du plan, et rejoué sur les 2 944 phrases réelles sans qu'une lecture change.

| Section | Règle du plan |
|---|---|
| 1 | Les liens : « comme », « comme dans », « pour », « de », « c'est », la virgule, rien |
| 2 | Le mot de la liste fermée l'emporte sur une lettre qu'il ne confirme pas (P/B, M/N, F/S) |
| 3 | La lettre perdue : « comme Ursule » juste après une confirmation |
| 4 | « de » n'est plus la lettre D quand il relie une lettre à son mot |
| 5 | Partout : au milieu d'un nom, d'une rue, d'une adresse mail ; les accents |
| 6 | ⛔ Une phrase ordinaire n'est jamais lue ; un prénom redit après un nom épelé ne le change pas (revue du 13/10) |
| 7 | Le désaccord hors liste : la lettre est gardée, la note la fait confirmer |
| 8 | R1 : la vraie route |

⛔ Rouge avant d'être vert, mesuré sur le lecteur d'avant (fork `146773d8`) :
« B comme Pascal a n c h a u d » -> « Banchaud » ; « N pour Nathalie o e l » -> « Oel » ;
« C de Carine a r o n » -> « Aron » ; « P, Pascal, i e r r e » -> « Ierre » ;
« D, comme Désiré, u p o n t » -> « Upont » ; « p comme Pascal a u l arobase gmail point com »
-> « pcommepascalaul@gmail.com ».
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.schemas.organization_preferences import AdresseEtablissement
from api.services.epellation.lecture import MOTS_DE_CONFIRMATION, lire
from api.services.epellation.mention import MARQUE, phrase_de_mention
from api.services.pipecat.lecture_appelant import lire_texte
from api.services.pipecat.verification_communes import CLE_TRACE_EPELLATIONS
from api.services.workflow.indices_des_modules import _traces_du_tour


def _lu(phrase: str) -> list[str]:
    return [e.epele for e in lire(phrase)]


CORPUS = [
    # 1. Les liens.
    ("P comme Pascal, A comme Antoine, N comme Nicolas", ["Pan"]),
    ("P comme dans Pascal a n c h a u d", ["Panchaud"]),
    ("N pour Nathalie o e l", ["Noel"]),
    ("C de Carine a r o n", ["Caron"]),
    ("P c'est Pascal a r i s", ["Paris"]),
    ("P, Pascal, i e r r e", ["Pierre"]),
    ("P Pascal i e r r e", ["Pierre"]),
    ("D, comme Désiré, u p o n t", ["Dupont"]),
    ("F de framboise a b r e", ["Fabre"]),
    (
        (
            "P comme Pascal, A comme Antoine, N pour Nathalie, C de Carine, H comme Henri, "
            "A comme André, U comme Ursule, D comme Désiré"
        ),
        ["Panchaud"],
    ),
    ("F comme François, L comme Louis, A comme Anatole", ["Fla"]),
    # 2. Le mot de la liste l'emporte.
    ("B comme Pascal a n c h a u d", ["Panchaud"]),
    ("M comme Nicolas o r e a u", ["Noreau"]),
    ("N comme Marcel a r t i n", ["Martin"]),
    ("F comme Suzanne o r e l", ["Sorel"]),
    ("S comme François a b r e", ["Fabre"]),
    ("B comme dans Pascal i e r r e", ["Pierre"]),
    # Hors des paires P/B, M/N, F/S, le mot ne l'emporte pas : la suite s'arrête.
    ("T comme Désiré", []),
    # 3. La lettre perdue.
    (
        (
            "D comme Désiré, comme Ursule, P comme Pascal, O comme Oscar, N comme Nicolas, "
            "T comme Thomas"
        ),
        ["Dupont"],
    ),
    (
        "M comme Marcel, comme Anatole, R comme Raoul, T comme Thomas, I comme Irma, N",
        ["Martin"],
    ),
    # 4. « de ».
    ("C de Carine, A de Anatole, R de Raoul, O de Oscar, N de Nicolas", ["Caron"]),
    ("a b de c", ["Abdc"]),
    # 5. Partout, accents compris.
    ("É comme Émile, m i l e", ["Émile"]),
    ("E comme Émile t i e n n e", ["Etienne"]),
    ("d u p comme Pascal o n t", ["Dupont"]),
    ("l e f e b comme Berthe v r e", ["Lefebvre"]),
    ("c'est la rue d a n t comme Thomas o n", ["Danton"]),
    ("p comme Pascal a u l arobase gmail point com", ["paul@gmail.com"]),
    ("N pour Nathalie a t h arobase orange point f r", ["nath@orange.fr"]),
    (
        "c'est m comme Marcel a r c point d u p o n t arobase free point f r",
        ["marc.dupont@free.fr"],
    ),
    # 6. ⛔ Les phrases ordinaires.
    ("comme Pascal me l'a dit", []),
    ("pour Nathalie, c'est urgent", []),
    ("c'est pour Nicolas", []),
    ("il y a de la fumée", []),
    ("il y a pour Nathalie un colis", []),
    ("j'ai vu Pascal et Nathalie hier", []),
    ("a comme Anatole", []),
    ("de Carine", []),
    ("c'est de la part de Marie", []),
    ("f l a m a n t comme je vous l'ai dit", ["Flamant"]),
    ("f a b r e s, sans accent", ["Fabres"]),
    ("c'est avec un b, c'est l e f e b v r e", ["Lefebvre"]),
    ("je vous appelle comme convenu pour Thomas", []),
    # Revue du 13/10 (bloquant) : un prénom de la liste qui suit un nom épelé ne
    # remplace jamais sa dernière lettre (« Jeaj », « Duponn », « Totj » avant).
    ("j e a n, Jean", ["Jean"]),
    ("m a r i e, Marie", ["Marie"]),
    ("l o u i s, Louis", ["Louis"]),
    ("v i n c e n t comme Vincent", ["Vincent"]),
    ("r o b e r t de Robert", ["Robert"]),
    ("d u p o n t pour Nathalie", ["Dupont"]),
    ("t o t o pour Jean qui est malade", ["Toto"]),
    # Revue du 13/10 (mineur) : un nom redit, ou une phrase, après « comme » : aucun doute.
    ("d u p o n t comme Dupont", ["Dupont"]),
    ("f l a m a n t comme Martin me l'a dit", ["Flamant"]),
    # Revue n° 2 du 13/10 (bloquant) : derrière une virgule ou « pour », le prénom qui
    # suit le nom ne remplace jamais une lettre, même d'une paire confondue.
    ("m a r t i n, Michel", ["Martin"]),
    ("c'est m a r t i n pour Marie", ["Martin"]),
    ("j e a n, Marie Dupont", ["Jean"]),
    ("l o u i s, François", ["Louis"]),
    ("t h o m a s, Fabien", ["Thomas"]),
    ("j a c o b, Pierre", ["Jacob"]),
    # Evan, 13/10 : une lettre déjà dite, reconfirmée après une virgule, n'est pas
    # ajoutée (« Paulp » avant) ; sauf si le nom était déjà épelé en alphabet (Panchaud).
    ("p a u l, P comme Pierre", ["Paul"]),
    ("d u p o n t, D comme Désiré", ["Dupont"]),
    ("p a u l, p comme Pierre, l comme Louis", ["Paul"]),
    ("d u p o n, T comme Thomas", ["Dupont"]),
    # Relecture n° 4 : si l'épellation continue après la confirmation, la lettre est
    # une vraie lettre (une lettre doublée : « Bonne », pas « Bone »).
    ("b o n, N comme Nicolas, e", ["Bonne"]),
    ("d u p o, N comme Nicolas, t", ["Dupont"]),
    # Relecture n° 4 : « 2 t » écrit en chiffre vaut « deux t ».
    ("c'est d u p o n 2 t", ["Dupontt"]),
    # Revue n° 2 : « de » devant un mot d'épellation reste la lettre D.
    ("m a de double l e", ["Madlle"]),
]


def test_le_corpus_fait_au_moins_quarante_cas():
    assert len(CORPUS) >= 40


@pytest.mark.parametrize("phrase,attendu", CORPUS, ids=[c[0][:40] for c in CORPUS])
def test_lalphabet_telephonique(phrase, attendu):
    assert _lu(phrase) == attendu


def test_la_liste_fermee_est_sans_accent_et_porte_lalphabet_francais():
    """Comparée sans accent : un mot écrit avec accent dans la liste ne serait jamais trouvé."""
    assert all(mot == mot.lower() and mot.isascii() for mot in MOTS_DE_CONFIRMATION)
    assert {
        "anatole",
        "berthe",
        "celestin",
        "desire",
        "zoe",
        "pascal",
        "nathalie",
        "carine",
    } <= (MOTS_DE_CONFIRMATION)


# --- 7. Le désaccord hors de la liste -------------------------------------


def test_un_mot_hors_liste_qui_ne_confirme_pas_garde_la_lettre_et_la_fait_confirmer():
    (lue,) = lire("b o u comme Parapluie l e")
    assert lue.epele == "Boule"
    assert lue.doutes == ("U comme Parapluie",)
    assert phrase_de_mention(lue) == (
        f"{MARQUE} : la personne a épelé « Boule ». Note exactement ces lettres. Une lettre ne "
        "s'accorde pas avec son mot (« U comme Parapluie ») : fais confirmer cette lettre à la "
        "personne.]"
    )


def test_sans_desaccord_la_note_ne_change_pas():
    (lue,) = lire("P comme Pascal a n c h a u d")
    assert lue.doutes == ()
    assert phrase_de_mention(lue) == (
        f"{MARQUE} : la personne a épelé « Panchaud ». "
        "Note exactement ces lettres, sans les corriger et sans les faire répéter.]"
    )


def test_lindice_du_greffier_porte_la_lettre_a_confirmer():
    fiche = {
        CLE_TRACE_EPELLATIONS: [
            {"tour": 2, "epele": "Boule", "doutes": ["U comme Parapluie"]}
        ]
    }
    assert _traces_du_tour(fiche, 2) == [
        "épelé = Boule (lettre à faire confirmer : U comme Parapluie)"
    ]


# --- 8. R1 : la vraie route ------------------------------------------------


class _Registre:
    def __init__(self):
        self.entrees: dict[str, list] = {}

    def __call__(self, entree: dict, cle: str) -> None:
        self.entrees.setdefault(cle, []).append(entree)

    def lire(self, cle: str) -> list:
        return self.entrees.get(cle, [])


async def test_par_la_vraie_route_le_nom_epele_en_alphabet_arrive_au_modele():
    """🔴 R1 : du texte de l'appelant à la note et à la trace. Rien ne change pour l'agent :
    il reçoit la même note qu'aujourd'hui."""
    registre = _Registre()
    texte = (
        "c'est B comme Pascal, A comme Antoine, N pour Nathalie, C de Carine, h a u d"
    )
    lu = await lire_texte(
        texte,
        conversion=True,
        verification=True,
        langue_francaise=True,
        adresse=AdresseEtablissement(
            code_postal="60740", code_insee="60589", commune="Saint-Maximin"
        ),
        noeud=SimpleNamespace(
            name="accueil", extraction_variables=[SimpleNamespace(name="nom")]
        ),
        consigner=registre,
        voies=True,
        epellation=True,
    )
    assert lu.startswith(texte)
    assert "la personne a épelé « Panchaud »" in lu
    (trace,) = registre.lire(CLE_TRACE_EPELLATIONS)
    assert trace["epele"] == "Panchaud"
    assert "doutes" not in trace
