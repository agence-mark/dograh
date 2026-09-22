"""[.mark] Garantie : la rue dite par l'appelant est retrouvée, ou déclarée introuvable — jamais inventée.

Question du labo : **l'adresse notée est-elle la bonne rue ?** Sur les runs,
« rue Danton » s'écrivait « rue d'antan », « Rue John-Fitzgerald Kennedy »
devenait « rue Jones-phyrole-Canédie ». Le code cherche la rue dite parmi celles
de la commune retenue, et rend un verdict.

🔴 **La garantie qui prime sur toutes les autres : zéro fausse sûre.** Annoncer
« utilise ce nom » pour une rue que l'appelant n'a pas dite met une mauvaise
adresse dans la fiche, et l'agent la répète sans hésiter. Le reste — combien de
rues trouvées du premier coup — vient après.

| Section | Ce qu'elle tient |
|---|---|
| 1 | L'index de test : vrai contenu, vraies clés, vrai chemin de lecture |
| 2 | 🔴 **Zéro fausse sûre** sur les 438 cas des deux corpus |
| 3 | Ce qui est retrouvé, et ce qui ne l'est pas — chiffré, pas promis |
| 4 | Les règles payées par un défaut mesuré (fenêtres, pluriels, types) |
| 5 | Le numéro (Q5), jamais dit au modèle |
| 6 | La mention : texte exact, épellation UNE fois (Q4), idempotence |
| 7 | Les invariants comptés, dans les deux sens |

⛔ L'index complet (111 Mo, 109 départements) n'est **pas** dans ces tests : ils
tournent sur les communes du corpus, extraites du vrai index avec les mêmes
clés (`api/scripts/mark/extraire_index_de_test.py`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.services.communes.base import normaliser
from api.services.communes.sons import simplifier, sons
from api.services.voies import base as base_voies
from api.services.voies.analyse import (
    A_CONFIRMER,
    INTROUVABLE,
    SURE,
    Detection,
    Proposition,
    analyser,
    est_type,
    sans_type,
)
from api.services.voies.mention import (
    deja_mentionne,
    mentionner_voie,
    phrase_de_mention,
)

DONNEES = Path(__file__).parent / "donnees"
CORPUS = json.loads((DONNEES / "voies_corpus_2026-09-22.json").read_text(encoding="utf-8"))
EXPORT_TEST = "test-2026-09-16"


@pytest.fixture(autouse=True)
def index_de_test(monkeypatch, tmp_path):
    """Les tests lisent l'index de test PAR LE CHEMIN RÉEL, décompression comprise."""
    monkeypatch.setattr(base_voies, "DOSSIER_BASE", DONNEES / "voies")
    monkeypatch.setattr(base_voies, "EXPORT", EXPORT_TEST)
    monkeypatch.setattr(base_voies, "DOSSIER_TRAVAIL", tmp_path / "voies")
    base_voies.voies_de.cache_clear()
    yield
    base_voies.voies_de.cache_clear()


def _detecter(cas: dict) -> Detection:
    return analyser(cas["phrase"], base_voies.voies_de(cas["insee"]), cas.get("commune"))


def _meme(a: str, b: str) -> bool:
    return normaliser(a) == normaliser(b)


# --- 1. L'index de test ---------------------------------------------------


def test_lindex_de_test_porte_bien_les_communes_du_corpus():
    attendues = {cas["insee"] for cas in CORPUS}
    vides = [insee for insee in sorted(attendues) if len(base_voies.voies_de(insee)) == 0]
    assert vides == []
    assert len(attendues) == 224


def test_une_commune_se_lit_par_le_chemin_reel_decompression_comprise():
    """⛔ Le test ne lit pas un SQLite posé à côté : il passe par la
    décompression du fichier départemental, comme en appel."""
    voies = base_voies.voies_de("60057")  # Beauvais
    assert len(voies) > 500
    assert any(_meme(nom, "Rue Vincent de Beauvais") for nom in voies.noms)
    # Les clés sont STOCKÉES, pas recalculées à la lecture.
    assert all(cle for cle in voies.cles_sonores)


def test_les_cles_stockees_sont_celles_que_le_code_recalcule():
    """🔑 Le seul mécanisme qui voit une divergence entre l'index et le lecteur.

    Le 22/09, le script de génération et la recherche n'avaient pas la même
    liste de types : « Cour d'Alger » gardait son type dans sa clé, « Rue
    d'Alger » non, et la mauvaise des deux sortait SÛRE. Aucun autre test ne
    pouvait le voir. Même garde que `test_base_communes.py` pour les communes.
    """
    from api.services.communes.base import cle_phonetique, cle_sonore

    voies = base_voies.voies_de("75056")  # Paris, 5 871 voies
    for rang, nom in enumerate(voies.noms):
        coeur = sans_type(normaliser(nom))
        assert voies.cles_sonores[rang] == cle_sonore(coeur), nom
        assert voies.cles_phonetiques[rang] == cle_phonetique(coeur), nom
    # ⛔ La colonne des SONS aussi : un décalage d'un rang à la génération
    # donnerait à chaque rue le son d'une autre, et c'est précisément ce qui
    # fabrique une fausse sûre par le son. Les deux gardes ci-dessus ne le
    # voyaient pas (trou signalé par la relecture du 22/09).
    assert len(voies.sons) == len(voies.noms)
    prononces = sons([sans_type(normaliser(nom)) for nom in voies.noms[:200]])
    if prononces:  # espeak absent : la garde ne s'applique pas
        for rang, son in enumerate(prononces):
            assert voies.sons[rang] == simplifier(son), voies.noms[rang]


# --- 2. 🔴 Zéro fausse sûre -----------------------------------------------


def test_aucune_rue_fausse_nest_annoncee_sure():
    """🔴 LA garantie du module, sur les 438 cas des deux corpus."""
    fausses = []
    for cas in CORPUS:
        detection = _detecter(cas)
        if detection.statut != SURE:
            continue
        if not cas["attendu"] or not _meme(detection.retenue, cas["attendu"]):
            fausses.append((cas["phrase"], detection.retenue, cas["attendu"]))
    assert fausses == []


def test_une_rue_inexistante_nest_jamais_annoncee_sure():
    """Les 63 rues inventées : « introuvable » ou « à confirmer », jamais sûre."""
    inventees = [cas for cas in CORPUS if cas["famille"] == "inventee"]
    assert len(inventees) == 63
    assert all(_detecter(cas).statut != SURE for cas in inventees)


def test_une_phrase_sans_adresse_ne_propose_aucune_rue():
    """⛔ « C'est la maison au bout du chemin » ne doit rien faire noter."""
    sans_adresse = [
        cas for cas in CORPUS
        if cas["famille"] == "reel" and not cas["attendu"]
        and "maison au bout" in cas["phrase"]
    ]
    assert sans_adresse, "le corpus doit porter ces phrases"
    assert all(_detecter(cas).statut != SURE for cas in sans_adresse)


# --- 2 bis. 🔴 Le silence sur ce qui n'est pas une adresse ----------------


def test_une_phrase_ordinaire_ne_dit_jamais_rien():
    """🔴 Le défaut BLOQUANT trouvé par la relecture indépendante du 22/09.

    Sans ancrage, **112 des 120 phrases ordinaires** de ce corpus produisaient
    « « accord » ne correspond à aucune rue de la commune. Fais épeler le nom de
    la rue. » — à chaque tour de l'étape d'adresse, ce qui est exactement la
    boucle que Q4 interdit. L'agent aurait demandé d'épeler une rue à un
    appelant qui venait de dire « oui d'accord ».

    Ces 120 phrases sont RÉELLES, tirées des runs : des phrases inventées
    seraient trop polies pour attraper quoi que ce soit.
    """
    ordinaires = [cas for cas in CORPUS if cas["famille"] == "ordinaire"]
    assert len(ordinaires) == 120
    bavardes = [
        (cas["phrase"], _detecter(cas).entendu)
        for cas in ordinaires
        if _detecter(cas).entendu
    ]
    assert bavardes == []


@pytest.mark.parametrize("insee,commune", [
    ("60509", "Pont-Sainte-Maxence"),   # 221 voies
    ("75056", "Paris"),                 # 5 871 voies
    ("13055", "Marseille"),             # 6 434 voies
])
def test_les_phrases_ordinaires_se_taisent_aussi_dans_les_grandes_villes(insee, commune):
    """🔑 Le corpus négatif doit tourner contre la commune où les collisions
    sont les plus probables, pas seulement contre une petite (contre-relecture
    du 22/09).

    Une première version épargnait les verdicts « sûre » pour garder les
    réponses courtes (« Victor Hugo »). Éprouvée contre Paris, cette porte a
    laissé passer trois noms de VILLE : « Strasbourg » devenait « Boulevard de
    Strasbourg », « sans lis » devenait « Rue de Senlis », « À Saint-Laurent »
    devenait « Rue Saint-Laurent » — exactement ce qu'un appelant répond à une
    étape d'adresse. L'exception a été supprimée.
    """
    voies = base_voies.voies_de(insee)
    ordinaires = [cas for cas in CORPUS if cas["famille"] == "ordinaire"]
    sures = [
        cas["phrase"] for cas in ordinaires
        if analyser(cas["phrase"], voies, commune).statut == SURE
    ]
    assert sures == []


@pytest.mark.parametrize(
    "phrase",
    [
        "oui d'accord",
        "c'est bon pour moi",
        "je suis disponible jeudi",
        "attendez je regarde",
        "je vous l'ai déjà dit, c'est un Ventura",   # « dit » n'est pas un type
        "c'est le bâtiment b au deuxième étage",     # « bâtiment » non plus
        "un vieux conduit de cheminée",              # « vieux » non plus
    ],
)
def test_aucune_epellation_nest_reclamee_sur_une_phrase_ordinaire(phrase):
    voies = base_voies.voies_de("60509")  # Pont-Sainte-Maxence
    assert analyser(phrase, voies, "Pont-Sainte-Maxence").entendu == ""


def test_une_adresse_reste_verifiee_malgre_la_regle_dancrage():
    """⛔ Le silence ne doit pas avaler les vraies adresses."""
    voies = base_voies.voies_de("60509")
    assert analyser("c'est au 6 rue Danton", voies, "Pont-Sainte-Maxence").statut == SURE
    assert analyser("6 Danton", voies, "Pont-Sainte-Maxence").propositions


def test_une_reponse_sans_type_ni_numero_nest_pas_verifiee_et_cest_voulu():
    """⚠️ Le coût assumé de l'ancrage, écrit noir sur blanc.

    « Victor Hugo » répondu à « quelle rue ? » n'est plus vérifié : ni type, ni
    numéro. Une version antérieure l'épargnait en laissant passer les verdicts
    « sûre » — et cette porte laissait entrer trois noms de VILLE à Paris
    (« Strasbourg » → « Boulevard de Strasbourg »). Coût mesuré de la fermeture :
    0 des 27 rues réelles des runs, 9 des 300 du banc sonore.

    Ce test dit l'état actuel, pas une vérité éternelle : le jour où un essai au
    casque montre que les appelants répondent souvent sans type, il change.
    """
    voies = base_voies.voies_de("60509")
    assert analyser("Victor Hugo", voies, "Pont-Sainte-Maxence").entendu == ""


def test_la_mention_cite_le_passage_entendu_pas_le_premier_mot():
    """⛔ « « accord » », « « n » peut être Rue Danton » : le modèle lisait le
    premier mot de la phrase, jamais ce qui avait été entendu."""
    voies = base_voies.voies_de("60509")
    detection = analyser("c'est au 6 rue Danton", voies, "Pont-Sainte-Maxence")
    assert detection.entendu == "danton"


@pytest.mark.parametrize(
    "insee,commune,phrase,attendue",
    [
        ("59350", "Lille", "12 rue Alain de Lille à Lille", "Rue Alain de Lille"),
        ("60057", "Beauvais", "12 rue Vincent de Beauvais à Beauvais", "Rue Vincent de Beauvais"),
    ],
)
def test_une_rue_qui_porte_le_nom_de_sa_commune_est_quand_meme_trouvee(
    insee, commune, phrase, attendue
):
    """🔴 Le défaut trouvé par la contre-relecture du 22/09.

    Une première correction retirait du passage comparé **tous** les noms de
    ville entendus, pour qu'une ville commençant par un type de voie
    (« **Pont**-Sainte-Maxence ») n'ancre plus la phrase. Elle effaçait du même
    coup le nom de la RUE quand la rue porte un nom de ville — et la famille est
    large et très française : rue de Paris, avenue de Strasbourg, rue d'Amiens,
    place de Verdun. « 12 rue de Creil à Creil » ne laissait **rien** à comparer,
    en silence.

    Les noms de ville ne sont plus masqués que pour décider de l'ancrage ; le
    passage comparé, lui, est coupé au « à » qui introduit la ville — et
    seulement quand ce qui suit est bien une ville entendue, sinon « Rue aux
    Fleurs » se ferait tronquer.
    """
    detection = analyser(
        phrase, base_voies.voies_de(insee), commune, autres_communes=(commune,)
    )
    assert detection.statut == SURE
    assert _meme(detection.retenue, attendue)


def test_une_voie_dont_le_nom_contient_a_plus_une_ville_est_trouvee():
    """🔴 La BAN est pleine de vieilles routes nommées d'après leurs deux bouts :
    « Chemin Vicinal Ordinaire n°4 de Warluis à Montreuil-sur-Thérain », et
    566 noms du même genre sur quatre départements. Couper au « à » les
    amputait. Les deux lectures — coupée et entière — sont donc comparées, et
    la meilleure gagne (contre-relecture du 22/09).
    """
    # « Route Rd 60a des Pennes a Bouc », aux Pennes-Mirabeau : le mot qui suit
    # le marqueur ("bouc") n'est pas la commune, donc rien n'est coupé et le nom
    # entier est comparé.
    detection = analyser(
        "c'est la route des Pennes a Bouc",
        base_voies.voies_de("13019"),
        "Les Pennes-Mirabeau",
        autres_communes=("Les Pennes-Mirabeau",),
    )
    assert detection.propositions
    assert "Bouc" in detection.propositions[0].nom


def test_une_voie_qui_porte_le_nom_de_sa_commune_nest_jamais_sure():
    """🔴 Les lieux-dits portent le nom de leur commune dans la BAN
    (« Neuilly En Thelle » à Neuilly-en-Thelle). Un appelant qui dit seulement
    où il habite se voyait répondre « utilise ce nom » sur une rue qu'il n'avait
    pas nommée — d'autant plus vite que la conversion des nombres avait mangé un
    mot (« rue des Quatre Vents » → « rue des 4 Vents » → « vents » seul).
    Elle reste proposable, jamais sûre.
    """
    detection = analyser(
        "j'habite rue des 4 Vents à Neuilly-en-Thelle",
        base_voies.voies_de("60450"),
        "Neuilly-en-Thelle",
    )
    assert detection.statut != SURE


def test_un_marqueur_de_lieu_qui_nest_pas_suivi_dune_ville_ne_coupe_rien():
    """« Rue aux Fleurs » : « aux » appartient au nom, pas à la ville."""
    from api.services.voies.analyse import _fenetres

    fenetres, _, _ = _fenetres(normaliser("12 rue aux Fleurs à Creil"), "Creil", ("Creil",))
    assert any("fleurs" in f for f in fenetres)


def test_un_lieu_dit_reste_une_adresse(monkeypatch):
    """Q3 a fait entrer les lieux-dits exprès : l'Oise rurale en est pleine, et
    « au lieu-dit les Granges » ne porte aucun type de voie. Le retrait de
    « dit » de la liste des types ne doit pas les avoir emportés avec lui —
    c'est la paire « lieu dit » qui ancre désormais."""
    voies = base_voies.voies_de("23096")  # Creuse, très rurale
    detection = analyser("au lieu dit les Granges", voies, None)
    assert detection.statut != INTROUVABLE
    assert detection.propositions


# --- 3. Ce qui est retrouvé, chiffré --------------------------------------


def test_toutes_les_rues_reelles_des_runs_sont_retrouvees():
    """27 phrases des runs visent une vraie rue : aucune n'est perdue."""
    attendues = [cas for cas in CORPUS if cas["famille"] == "reel" and cas["attendu"]]
    assert len(attendues) == 27
    perdues = []
    for cas in attendues:
        detection = _detecter(cas)
        tete = detection.propositions[0].nom if detection.propositions else ""
        if not tete or not _meme(tete, cas["attendu"]):
            perdues.append((cas["phrase"], tete, cas["attendu"]))
    assert perdues == []


def test_la_rue_deformee_par_la_transcription_est_rattrapee():
    """Le cas le plus dur du corpus réel : « rue Jones-phyrole-Canédie » à Creil."""
    cas = next(c for c in CORPUS if "Jones-phyrole" in c["phrase"])
    detection = _detecter(cas)
    assert detection.propositions
    assert _meme(detection.propositions[0].nom, "Rue John Kennedy")


def test_le_corpus_sonore_reste_au_niveau_mesure_le_22_09():
    """⛔ Un plancher, pas une promesse. 300 rues réelles dites en 8 kHz puis
    transcrites : un banc PLUS DUR que le casque, qui sert à comparer deux
    versions du lecteur, pas à annoncer un taux au client.

    Mesuré le 22/09, règle d'ancrage comprise : 191 retrouvées (128 sûres,
    63 en tête d'un « à confirmer »). ⚠️ C'était 234 avant l'ancrage : les 43
    de différence ne sont pas perdues pour l'appel, elles sont **non vérifiées**,
    comme avant le chantier. L'arbitrage est assumé — une question absurde posée
    à un appelant coûte plus cher qu'un rattrapage manqué.
    """
    sonores = [cas for cas in CORPUS if cas["famille"] == "sonore"]
    assert len(sonores) == 300
    trouvees = 0
    for cas in sonores:
        detection = _detecter(cas)
        tete = detection.propositions[0].nom if detection.propositions else ""
        if tete and _meme(tete, cas["attendu"]):
            trouvees += 1
    assert trouvees >= 185, f"{trouvees} retrouvées, 191 le 22/09"


# --- 4. Les règles payées par un défaut mesuré ----------------------------


def test_une_fenetre_partielle_ne_suffit_pas_a_etre_sure():
    """« allée des Mésanges Dorées » n'existe pas à Bury ; « Rue des Mésanges »
    si. Sans la pénalité sur les mots laissés de côté, la seconde sortait SÛRE
    (15 fausses sûres sur 156 cas tenaient à ce seul défaut)."""
    detection = analyser(
        "j'habite allée des Mésanges Dorées à Bury", base_voies.voies_de("60116"), "Bury"
    )
    assert detection.statut != SURE


@pytest.mark.parametrize("mot", ["rue", "rues", "impasse", "impasses", "places", "chemins"])
def test_les_pluriels_sont_des_types_de_voie(mot):
    """⛔ « 79 rues de la mairie » : la faute la plus fréquente de la
    transcription, et sans elle rien ne s'ancre."""
    assert est_type(mot)


def test_une_voie_dont_le_nom_est_un_type_garde_son_nom():
    """« Grande Rue » est un nom de voie, pas un type suivi d'un nom."""
    assert sans_type(normaliser("Grande Rue")) == "grande rue"
    assert sans_type(normaliser("Rue de la République")) == "republique"


def test_la_commune_est_retiree_du_passage_compare():
    """« rue des Tilleuls à Beauvais » se comparait « tilleuls a beauvais »."""
    voies = base_voies.voies_de("60057")
    avec = analyser("12 rue Vincent de Beauvais à Beauvais", voies, "Beauvais")
    assert avec.propositions
    assert _meme(avec.propositions[0].nom, "Rue Vincent de Beauvais")


# --- 5. Le numéro (Q5) ----------------------------------------------------


def test_le_numero_dit_est_verifie_sur_la_voie_retenue():
    voies = base_voies.voies_de("60057")
    rang = next(r for r, nom in enumerate(voies.noms) if voies.numeros[r])
    numero = min(voies.numeros[rang])
    detection = analyser(f"{numero} {voies.noms[rang]}", voies, None)
    assert detection.propositions
    assert detection.propositions[0].numero_present is True


def test_sans_numero_dit_le_champ_reste_vide():
    voies = base_voies.voies_de("60057")
    detection = analyser("rue Vincent de Beauvais", voies, None)
    assert detection.propositions
    assert detection.propositions[0].numero_present is None


def test_la_mention_ne_parle_jamais_du_numero():
    """Q5 : une base incomplète ne doit pas faire répéter l'appelant."""
    detection = Detection(SURE, "rue machin", (Proposition("Rue Danton", 99.0, False),))
    phrase = phrase_de_mention(detection)
    assert "numéro" not in phrase.lower()
    assert "numero" not in phrase.lower()


# --- 6. La mention --------------------------------------------------------


def test_le_texte_de_la_mention_sure():
    detection = Detection(SURE, "rue d'antan", (Proposition("Rue Danton", 95.0),))
    assert phrase_de_mention(detection) == (
        "[Vérification de la rue : « rue d'antan » correspond à Rue Danton. "
        "Utilise ce nom sans le faire répéter.]"
    )


def test_le_texte_de_la_mention_introuvable_fait_epeler_une_fois():
    """Q4 : une seule épellation, jamais de boucle — une base n'est jamais
    complète, et faire répéter son adresse à un appelant est pire que de noter
    une rue que la base ignore."""
    detection = Detection(INTROUVABLE, "rue du Lavoira")
    phrase = phrase_de_mention(detection)
    assert "ne correspond à aucune rue de la commune" in phrase
    assert "une seule fois" in phrase
    assert phrase.count("épeler") == 1


def test_le_texte_de_la_mention_a_confirmer_propose_puis_fait_epeler():
    detection = Detection(
        A_CONFIRMER, "rue de bray",
        (Proposition("Rue de Bray", 88.0), Proposition("Rue du Bray", 86.0)),
    )
    phrase = phrase_de_mention(detection)
    assert "Demande d'abord si c'est Rue de Bray" in phrase
    assert "propose Rue du Bray" in phrase
    assert "une seule fois" in phrase


def test_la_mention_ne_touche_pas_au_texte_de_lappelant():
    texte = "c'est au 6 rue d'antan"
    detection = Detection(SURE, "rue d'antan", (Proposition("Rue Danton", 95.0),))
    annote = mentionner_voie(texte, detection)
    assert annote.startswith(texte)
    assert deja_mentionne(annote)
    assert not deja_mentionne(texte)


def test_sans_rien_entendu_le_texte_est_rendu_intact():
    texte = "bonjour, je voudrais un rendez-vous"
    assert mentionner_voie(texte, Detection(INTROUVABLE, "")) is texte
    assert mentionner_voie(texte, None) is texte


# --- 7. Les invariants, dans les deux sens --------------------------------


def test_une_voie_sure_est_toujours_une_voie_de_la_commune():
    """Sens direct : ce qui est annoncé sûr existe dans la commune de l'appel."""
    for cas in CORPUS:
        detection = _detecter(cas)
        if detection.statut != SURE:
            continue
        noms = base_voies.voies_de(cas["insee"]).noms
        assert detection.retenue in noms


def test_une_mention_suppose_toujours_une_detection_et_reciproquement():
    """Sens inverse ET comptage : sans le compte, un lecteur qui rendrait
    « introuvable » partout passerait toutes les gardes ci-dessus."""
    avec_mention = sures = 0
    for cas in CORPUS:
        detection = _detecter(cas)
        annote = mentionner_voie(cas["phrase"], detection)
        porte_mention = deja_mentionne(annote)
        # Une mention est écrite si et seulement si quelque chose a été entendu.
        assert porte_mention == bool(detection.entendu)
        avec_mention += porte_mention
        sures += detection.statut == SURE
    # Et ces totaux ne sont pas zéro.
    # ⚠️ Bien plus bas qu'avant l'ancrage, et c'est le but : les phrases
    # ordinaires du corpus se taisent maintenant toutes.
    assert avec_mention >= 300
    assert sures >= 140
