"""[.mark] Garantie : une adresse mail dictée est lue, en mots comme épelée (plan courriel-dicte, lot 1).

Question du labo : **l'adresse que la personne dicte arrive-t-elle, juste, jusqu'au modèle ?**
Sur les 1 142 runs du 13/10, quatre adresses dictées ; « Evan point jourde arobase Gmail
point com » (run 324) n'était pas lue : aucune lettre n'y est épelée.

| Section | Ce qu'elle tient |
|---|---|
| 1 | Les **adresses réelles** du lot 0 (runs 324, 330, 386, 805), telles que la transcription les a écrites |
| 2 | **D1** : une adresse dite en mots est lue ; un domaine dit en plusieurs mots est recollé depuis la liste unique ; les formes de l'arobase |
| 3 | ⛔ **Rien d'inventé** : sans domaine complet, sans arobase, ou dans une phrase ordinaire, rien n'est lu |
| 4 | **D3** : un domaine proche d'un connu est signalé, jamais remplacé (note, trace, indice du greffier, contrôle) |
| 5 | **R1** : la vraie route, du texte de l'appelant à la note et à la trace |

⛔ Rouge avant d'être vert : le run 324 rendait ``[]`` avec le lecteur d'avant (témoin du lot 0,
`Labo-agent-vocal/plans/courriel-dicte/corpus.md`).
"""

from __future__ import annotations

from datetime import date

import pytest

from api.services.epellation.domaines import (
    DOMAINES,
    DOMAINES_COURANTS,
    domaine_proche,
    formes_dites,
)
from api.services.epellation.lecture import lire
from api.services.epellation.mention import MARQUE, phrase_de_mention
from api.services.fiche.controle import controler
from api.services.pipecat.lecture_appelant import lire_texte
from api.services.pipecat.verification_communes import CLE_TRACE_EPELLATIONS
from api.services.workflow.indices_des_modules import _traces_du_tour


def _lu(phrase: str) -> list[str]:
    return [e.epele for e in lire(phrase)]


# --- 1. Les adresses réelles (lot 0) ---------------------------------------


@pytest.mark.parametrize(
    "phrase,attendu",
    [
        # run 324 : dite entièrement en mots, « Gmail » en un mot, avec majuscule.
        (
            "Oui, c'est Evan point jourde arobase Gmail point com.",
            ["evan.jourde@gmail.com"],
        ),
        # run 330 : lettres épelées au milieu.
        (
            "Oui, c'est Evan point v d k arobase outlook point f r.",
            ["evan.vdk@outlook.fr"],
        ),
        # run 805 : au milieu d'une phrase, « tiret » et un nom en deux mots.
        (
            (
                "Oui, est-ce que vous pouvez aussi envoyer le devis par mail? Alors c'est contact "
                "arobase boulangerie tiret le moine point f r."
            ),
            ["contact@boulangerie-lemoine.fr"],
        ),
        # run 386 : l'arobase a disparu à la transcription. ⛔ Rien d'inventé.
        ("Alors oui, c'est camaradegmail point com.", []),
    ],
)
def test_les_adresses_des_vrais_appels(phrase, attendu):
    assert _lu(phrase) == attendu


# --- 2. D1 : en mots, domaines recollés, formes de l'arobase -----------------


@pytest.mark.parametrize(
    "phrase,attendu",
    [
        ("c'est marie arobase hot mail point fr", "marie@hotmail.fr"),
        ("c'est paul arobase g mail point com", "paul@gmail.com"),
        ("c'est paul arobase gé mail point com", "paul@gmail.com"),
        ("jean arobase la poste point net", "jean@laposte.net"),
        # Revue n° 3 : « neuf » est un nombre ET un domaine de la liste.
        ("c'est evan arobase neuf point f r", "evan@neuf.fr"),
        ("c'est e v a n arobase neuf point f r", "evan@neuf.fr"),
        ("lucie arobase i cloud point com", "lucie@icloud.com"),
        ("c'est sophie arrobase orange point f r", "sophie@orange.fr"),
        ("c'est sophie arobas wanadoo point f r", "sophie@wanadoo.fr"),
        ("c'est paul at g mail point com et mon numéro", "paul@gmail.com"),
        ("jean a commercial orange point f r", "jean@orange.fr"),
        (
            "m a r i e tiret bas d u p o n t arobase example point com",
            "marie_dupont@example.com",
        ),
        # Un nom de lettre entre deux lettres seules est une lettre.
        ("evan point v de k arobase free point f r", "evan.vdk@free.fr"),
    ],
)
def test_une_adresse_dite_en_mots_est_lue(phrase, attendu):
    assert _lu(phrase) == [attendu]


@pytest.mark.parametrize(
    "phrase,attendu",
    [
        # Les mots de la phrase arrêtent l'adresse à gauche…
        ("je suis evan arobase gmail point com", "evan@gmail.com"),
        ("vous pouvez écrire à evan arobase gmail point com", "evan@gmail.com"),
        # … et après l'extension, seul un autre « point » continue.
        ("evan arobase gmail point com merci beaucoup", "evan@gmail.com"),
        ("evan arobase gmail point f r voilà", "evan@gmail.fr"),
        ("evan arobase gmail point com, et mon numéro", "evan@gmail.com"),
        (
            "jean arobase mairie tiret creil point gouv point f r",
            "jean@mairie-creil.gouv.fr",
        ),
    ],
)
def test_ladresse_sarrete_ou_elle_finit(phrase, attendu):
    assert _lu(phrase) == [attendu]


@pytest.mark.parametrize(
    "phrase,adresse,doute",
    [
        ("c'est hélène arobase gmail point com", "helene@gmail.com", "accents retirés"),
        (
            "jean pierre arobase gmail point com",
            "jeanpierre@gmail.com",
            "« jean pierre »",
        ),
    ],
)
def test_une_supposition_est_a_faire_confirmer(phrase, adresse, doute):
    """Revue du 13/10 : accents retirés, mots recollés sans séparateur = une supposition.
    La note ne dit plus « exactement », elle fait confirmer."""
    (lue,) = lire(phrase)
    assert lue.epele == adresse
    assert any(doute in d for d in lue.doutes)
    note = phrase_de_mention(lue)
    assert "fais-la confirmer" in note and "exactement" not in note


# --- 3 bis. Les chiffres de l'adresse (Evan, 13/10 : « un module parfait ») -----------


@pytest.mark.parametrize(
    "phrase,adresse,a_confirmer",
    [
        ("c'est jean75 arobase gmail point com", "jean75@gmail.com", False),
        ("c'est j e a n 7 5 arobase gmail point com", "jean75@gmail.com", False),
        (
            "jean point dupont 1975 arobase gmail point com",
            "jean.dupont1975@gmail.com",
            True,
        ),
        ("c'est jean 75 arobase gmail point com", "jean75@gmail.com", True),
        # Un nombre dit en mots s'écrit en chiffres : une lecture, donc à faire confirmer.
        (
            "c'est jean soixante quinze arobase gmail point com",
            "jean75@gmail.com",
            True,
        ),
        (
            "c'est jean soixante-quinze arobase gmail point com",
            "jean75@gmail.com",
            True,
        ),
        (
            "jean point dupont deux mille arobase orange point f r",
            "jean.dupont2000@orange.fr",
            True,
        ),
        ("jean 75 point v d k arobase gmail point com", "jean75.vdk@gmail.com", True),
        # « deux t » dans une adresse est une répétition, pas un nombre.
        ("c'est b o deux t e arobase free point f r", "botte@free.fr", False),
    ],
)
def test_les_chiffres_de_ladresse_sont_lus(phrase, adresse, a_confirmer):
    (lue,) = lire(phrase)
    assert lue.epele == adresse
    assert bool(lue.doutes) is a_confirmer


@pytest.mark.parametrize(
    "phrase",
    [
        "06 12 34 56 78 jean arobase gmail point com",
        "mon numéro c'est le 06 12 34 56 78, et mon mail jean arobase gmail point com",
    ],
)
def test_un_numero_de_telephone_nentre_jamais_dans_ladresse(phrase):
    assert _lu(phrase) == ["jean@gmail.com"]


def test_une_adresse_est_lue_une_seule_fois_et_pointe_sur_ce_qui_a_ete_dit():
    phrase = "Oui, c'est Evan point jourde arobase Gmail point com."
    (lue,) = lire(phrase)
    assert lue.courriel
    assert (
        phrase[lue.debut : lue.fin]
        == lue.entendu
        == "Evan point jourde arobase Gmail point com"
    )


# --- 3. ⛔ Rien d'inventé ----------------------------------------------------


@pytest.mark.parametrize(
    "phrase",
    [
        # Sans domaine complet, dite en mots : un début, pas une adresse.
        "evan arobase gmail",
        "mon adresse c'est evan arobase",
        # Les formes faibles de l'arobase sont des mots ordinaires.
        "c'est paul at home",
        "je travaille at the office",
        "il y a un agent a commercial ici",
        # Phrases ordinaires.
        "il est à la maison",
        "je vous envoie ça par mail",
        "mon adresse mail, je ne l'ai pas",
        "Non non, je n'ai pas l'adresse mail.",
        "c'est un point important, on en reparle",
        # Revue du 13/10 : des mots qui décrivent l'adresse ne la font pas.
        "c'est mon prénom point mon nom arobase gmail point com",
        "le nom de la boîte arobase gmail point com",
        # Revue du 13/10 : « at » seulement devant un domaine de la liste.
        "j'ai un compte at home point net",
    ],
)
def test_rien_nest_lu_sans_adresse(phrase):
    assert lire(phrase) == []


# --- 4. D3 : la liste unique, le domaine proche signalé ----------------------


def test_la_liste_des_domaines_est_unique_et_sert_aussi_au_controle():
    """D3 : une seule source. Le contrôle de fin d'appel n'a plus sa liste à lui."""
    from api.services.fiche import controle

    assert not hasattr(controle, "DOMAINES_COURANTS")
    assert DOMAINES_COURANTS == tuple(DOMAINES)
    assert len(DOMAINES) >= 30
    assert {"gmail.com", "hotmail.fr", "orange.fr", "laposte.net", "icloud.com"} <= set(
        DOMAINES
    )


def test_chaque_forme_dite_recolle_le_nom_de_son_domaine():
    formes = formes_dites()
    assert formes[("hot", "mail")] == "hotmail"
    assert formes[("la", "poste")] == "laposte"
    assert formes[("i", "cloud")] == "icloud"
    # ⛔ « voilà » ferme une phrase, ce n'est jamais un domaine.
    assert ("voilà",) not in formes


@pytest.mark.parametrize(
    "domaine,proche",
    [
        ("gmial.com", "gmail.com"),
        ("hotmal.fr", "hotmail.fr"),
        ("gmail.com", None),
        ("boulangerie-lemoine.fr", None),
        ("", None),
    ],
)
def test_le_domaine_proche(domaine, proche):
    assert domaine_proche(domaine) == proche


def test_un_domaine_douteux_est_signale_jamais_remplace():
    (lue,) = lire("c'est evan arobase gmial point com")
    assert lue.epele == "evan@gmial.com"
    assert lue.domaine_proche == "gmail.com"
    note = phrase_de_mention(lue)
    assert note == (
        f"{MARQUE} : la personne a donné l'adresse mail « evan@gmial.com ». Note exactement cette "
        "adresse. Le domaine « gmial.com » ressemble à « gmail.com » : fais confirmer le domaine à "
        "la personne, sans le corriger toi-même.]"
    )


def test_la_note_dune_adresse_sans_doute():
    (lue,) = lire("Oui, c'est Evan point jourde arobase Gmail point com.")
    assert phrase_de_mention(lue) == (
        f"{MARQUE} : la personne a donné l'adresse mail « evan.jourde@gmail.com ». "
        "Note exactement cette adresse.]"
    )


def test_lindice_du_greffier_dune_adresse_supposee():
    fiche = {
        CLE_TRACE_EPELLATIONS: [
            {
                "tour": 4,
                "epele": "jeanpierre@gmail.com",
                "courriel": True,
                "doutes": ["« jean pierre » écrit sans séparateur"],
            }
        ]
    }
    assert _traces_du_tour(fiche, 4) == [
        "épelé = jeanpierre@gmail.com (à faire confirmer : « jean pierre » écrit sans séparateur)"
    ]


def test_lindice_du_greffier_porte_le_doute():
    fiche = {
        CLE_TRACE_EPELLATIONS: [
            {
                "tour": 3,
                "epele": "evan@gmial.com",
                "courriel": True,
                "domaine_proche": "gmail.com",
            }
        ]
    }
    assert _traces_du_tour(fiche, 3) == [
        "épelé = evan@gmial.com (domaine à faire confirmer, proche de gmail.com)"
    ]


def test_le_controle_de_fin_dappel_garde_son_verdict():
    noms = {"courriel": ("mail*",)}
    jour = date(2026, 10, 13)
    douteux = controler({"mail": "evan@gmial.com"}, noms=noms, jour_appel=jour)
    assert [p["code"] for p in douteux["problemes"]] == ["courriel_domaine_douteux"]
    assert douteux["problemes"][0]["detail"] == "gmial.com, peut-être gmail.com"
    # Un domaine de la liste élargie n'est jamais douteux.
    assert (
        controler({"mail": "jean@laposte.net"}, noms=noms, jour_appel=jour)["statut"]
        == "complete"
    )


# --- 5. R1 : la vraie route ------------------------------------------------


class _Registre:
    def __init__(self):
        self.entrees: dict[str, list] = {}

    def __call__(self, entree: dict, cle: str) -> None:
        self.entrees.setdefault(cle, []).append(entree)

    def lire(self, cle: str) -> list:
        return self.entrees.get(cle, [])


async def _par_la_route(texte: str, registre: _Registre) -> str:
    from types import SimpleNamespace

    from api.schemas.organization_preferences import AdresseEtablissement

    return await lire_texte(
        texte,
        conversion=True,
        verification=True,
        langue_francaise=True,
        adresse=AdresseEtablissement(
            code_postal="60740", code_insee="60589", commune="Saint-Maximin"
        ),
        noeud=SimpleNamespace(
            name="coordonnees", extraction_variables=[SimpleNamespace(name="mail")]
        ),
        consigner=registre,
        voies=True,
        epellation=True,
    )


async def test_par_la_vraie_route_ladresse_dite_en_mots_arrive_au_modele_et_a_la_trace():
    """🔴 R1 : s'il s'éteint, ce test rougit. Le texte de l'appelant reste intact, la note
    dit l'adresse, la trace la porte (le greffier la lit là)."""
    registre = _Registre()
    texte = "Oui, c'est Evan point jourde arobase Gmail point com."
    lu = await _par_la_route(texte, registre)
    assert lu.startswith(texte)
    assert "« evan.jourde@gmail.com »" in lu
    (trace,) = registre.lire(CLE_TRACE_EPELLATIONS)
    assert trace["epele"] == "evan.jourde@gmail.com"
    assert trace["courriel"] is True
    assert "domaine_proche" not in trace


async def test_par_la_vraie_route_le_domaine_douteux_est_dans_la_note_et_la_trace():
    registre = _Registre()
    lu = await _par_la_route("c'est evan arobase gmial point com", registre)
    assert "ressemble à « gmail.com »" in lu
    (trace,) = registre.lire(CLE_TRACE_EPELLATIONS)
    assert trace["domaine_proche"] == "gmail.com"


@pytest.mark.parametrize(
    "texte,adresse",
    [
        ("c'est evan arobase neuf point f r", "evan@neuf.fr"),
        ("c'est jean soixante quinze arobase gmail point com", "jean75@gmail.com"),
    ],
)
async def test_par_la_vraie_route_aucun_autre_module_ne_touche_ladresse(texte, adresse):
    """🔴 Evan, 13/10 : « un module parfait qui ne rend pas défectueux nos autres modules ».
    Les nombres réécrivaient « neuf point f r » en « 9 point f r » à côté d'une note qui
    disait ``neuf.fr`` : l'adresse est mise à l'abri, puis rendue telle que dite."""
    lu = await _par_la_route(texte, _Registre())
    assert lu.startswith(texte)
    assert f"« {adresse} »" in lu


async def test_par_la_vraie_route_le_numero_dit_avant_ladresse_reste_converti():
    texte = "mon numéro c'est le zéro six douze trente-quatre cinquante-six soixante-dix-huit et mon mail jean arobase gmail point com"
    lu = await _par_la_route(texte, _Registre())
    assert lu.startswith(
        "mon numéro c'est le 06 12 34 56 78 et mon mail jean arobase gmail point com"
    )
    assert "« jean@gmail.com »" in lu


async def test_par_la_vraie_route_une_adresse_ne_fait_jamais_chercher_une_rue():
    """« point » est un type de voie (rond-point) : une adresse dite en mots ne doit pas
    faire demander d'épeler une rue."""
    from api.services.voies.mention import MARQUE as MARQUE_VOIE

    lu = await _par_la_route(
        "c'est contact arobase boulangerie tiret le moine point f r", _Registre()
    )
    assert MARQUE_VOIE not in lu
