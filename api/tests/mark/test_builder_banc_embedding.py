"""[.mark] builder-agent-vocal, lot 6 : le banc de recherche de la base de connaissances (comparaison de deux modèles d'embedding).

Vecteurs factices déterministes, mini-corpus générique fictif : aucun appel réel. Ce qui doit tenir : le taux « bon passage dans les 3
premiers » et le rang de chaque question, le classement par similarité cosinus, la comparaison de deux modèles, le découpage de la base,
le modèle exclu refusé, la mauvaise dimension refusée, la clé jamais affichée ni écrite.
"""

from __future__ import annotations

import hashlib
import json
import re

import pytest

from api.scripts.mark import banc_embedding as cli
from api.services.builder import banc_embedding as banc
from api.services.builder.banc_embedding import ConfigModele, ErreurBanc, Morceau, Question
from api.services.gen_ai.documents_locaux import decouper

CLE_OPENAI = "sk-cle-factice-OPENAI-0123456789"
CLE_SCALEWAY = "scw-cle-factice-SCALEWAY-0123456789"
ENVIRONNEMENT = {"OPENAI_API_KEY": CLE_OPENAI, "SCALEWAY_API_KEY": CLE_SCALEWAY}

DOCUMENT = """Les ouvertures de la boutique

La boutique ouvre du lundi au vendredi de neuf heures à dix-huit heures, et le samedi matin seulement.

La livraison des colis

Les colis partent le jour même avant midi. Un colis arrive en deux jours ouvrés en moyenne.

Le retour d'un produit

Un produit se rend sous trente jours avec sa facture. Le remboursement se fait sur le moyen de paiement utilisé.
"""
QUESTIONS = [
    {"question": "Vous ouvrez à quelle heure le samedi ?", "passage_attendu": "le samedi matin seulement"},
    {"question": "Ça arrive en combien de temps un colis ?", "passage_attendu": "deux jours ouvrés"},
    {"question": "Un produit se rend avec la facture sous trente jours ?", "passage_attendu": "sous trente jours avec sa facture"},
]


def mot(m: str) -> str:
    return re.sub(r"[^a-zàâçéèêëîïôûùüÿ]", "", m.lower())


def vecteur_par_mots(texte: str, graine: str = "") -> list[float]:
    """Un sac de mots haché sur 1 536 dimensions : deterministe, et deux textes qui partagent des mots se ressemblent."""
    v = [0.0] * 1536
    for m in map(mot, texte.split()):
        if len(m) > 3:
            v[int(hashlib.sha256((graine + m).encode()).hexdigest(), 16) % 1536] += 1.0
    return v


class ServiceFactice:
    def __init__(self, graine="", brouille=False, dimension=1536):
        self.graine, self.brouille, self.dimension = graine, brouille, dimension
        self.appels: list[list[str]] = []

    def _vec(self, t: str) -> list[float]:
        # Un modèle « mauvais » : le texte est remplacé par un hachage sans rapport avec les mots (rien ne se ressemble).
        v = vecteur_par_mots(hashlib.md5(t.encode()).hexdigest() if self.brouille else t, self.graine)
        return v[: self.dimension] if self.dimension != 1536 else v

    async def embed_texts(self, textes):
        self.appels.append(list(textes))
        return [self._vec(t) for t in textes]

    async def embed_query(self, q):
        return self._vec(q)


def fabrique(par_modele: dict[str, ServiceFactice]):
    async def f(config: ConfigModele, cle: str):
        return par_modele[config.modele]

    return f


def corpus_prepare(max_tokens=24):
    return banc.preparer({"boutique.md": DOCUMENT}, QUESTIONS, max_tokens)


# --- le découpage et le corpus --------------------------------------------------------------------------------------------


def test_le_decoupage_est_celui_de_la_base():
    morceaux, _ = corpus_prepare()
    assert [m.texte for m in morceaux] == decouper(DOCUMENT.strip(), 24) and len(morceaux) >= 3
    assert [m.identifiant for m in morceaux][:2] == ["boutique.md#0", "boutique.md#1"]


def test_le_passage_attendu_est_un_extrait_exact_ou_un_identifiant_de_morceau():
    morceaux, questions = corpus_prepare()
    assert questions[0].attendus and all("samedi matin" in morceaux[k].texte for k in questions[0].attendus)
    par_identifiant = banc.preparer({"boutique.md": DOCUMENT}, [{"question": "q ?", "passage_attendu": "boutique.md#1"}], 24)[1][0]
    assert par_identifiant.attendus == {1}
    assert banc.preparer({"boutique.md": DOCUMENT}, [{"question": "q ?", "passage_attendu": "  LE SAMEDI   matin SEULEMENT "}], 24)[1][0].attendus


@pytest.mark.parametrize(
    "questions",
    [
        [{"question": "q ?", "passage_attendu": "ceci n'est nulle part"}],
        [{"question": "q ?", "passage_attendu": "boutique.md#99"}],
        [{"question": "", "passage_attendu": "samedi"}],
        [{"question": "q ?"}],
        [],
        "pas une liste",
    ],
)
def test_un_corpus_incorrect_est_refuse_avant_tout_calcul(questions):
    with pytest.raises(ErreurBanc):
        banc.preparer({"boutique.md": DOCUMENT}, questions, 24)


def test_lire_le_corpus_depuis_un_fichier_relatif_a_son_dossier(tmp_path):
    (tmp_path / "boutique.md").write_text(DOCUMENT, encoding="utf-8")
    (tmp_path / "corpus.json").write_text(json.dumps({"version": 1, "documents": ["boutique.md"], "questions": QUESTIONS}), encoding="utf-8")
    morceaux, questions = banc.lire_le_corpus(tmp_path / "corpus.json", 24)
    assert len(questions) == 3 and morceaux
    (tmp_path / "mauvais.json").write_text(json.dumps({"version": 2, "documents": ["boutique.md"], "questions": QUESTIONS}), encoding="utf-8")
    (tmp_path / "absent.json").write_text(json.dumps({"version": 1, "documents": ["nulle-part.md"], "questions": QUESTIONS}), encoding="utf-8")
    for fichier in ("mauvais.json", "absent.json", "inexistant.json"):
        with pytest.raises(ErreurBanc):
            banc.lire_le_corpus(tmp_path / fichier, 24)


# --- le calcul : taux, rang, classement ----------------------------------------------------------------------------------------


def test_le_classement_est_par_similarite_cosinus_et_le_rang_se_compte_depuis_1():
    a, b, c, d = [1.0, 0, 0], [0.9, 0.1, 0], [0, 1.0, 0], [0, 0, 1.0]
    assert banc.classer([1.0, 0, 0], [c, b, d, a]) == [3, 1, 0, 2]
    assert banc.similarite(a, a) == pytest.approx(1.0) and banc.similarite(a, c) == 0.0 and banc.similarite([0, 0, 0], a) == 0.0
    morceaux = [Morceau("d", k, f"m{k}") for k in range(4)]
    vecteurs = [c, b, d, a]
    questions = [Question("q1", {3}), Question("q2", {2}), Question("q3", {0}), Question("q4", {1, 3})]
    r = banc.evaluer(morceaux, questions, vecteurs, [[1.0, 0, 0]] * 4)
    # ordre pour chaque question : [3, 1, 0, 2] -> q1 rang 1, q2 rang 4, q3 rang 3, q4 rang 1 (le meilleur des deux attendus)
    assert [x["rang"] for x in r["rangs"]] == [1, 4, 3, 1]
    assert [x["dans_les_3"] for x in r["rangs"]] == [True, False, True, True]
    assert (r["bons"], r["total"], r["taux_dans_les_3"]) == (3, 4, 0.75)
    assert [x["question"] for x in r["ratees"]] == ["q2"] and r["ratees"][0]["premiers"] == ["d#3", "d#1", "d#0"]


async def test_un_modele_qui_comprend_le_texte_trouve_les_bons_passages():
    morceaux, questions = corpus_prepare()
    r = await banc.banc_d_un_modele(ConfigModele("bon"), morceaux, questions, fabrique=fabrique({"bon": ServiceFactice()}), environnement=ENVIRONNEMENT)
    assert r["taux_dans_les_3"] == 1.0 and r["dimension"] == 1536 and all(x["rang"] is not None and x["rang"] <= 3 for x in r["rangs"])


async def test_les_textes_partent_par_lots_au_service():
    morceaux, questions = banc.preparer({"boutique.md": DOCUMENT * 40}, QUESTIONS, 24)
    service = ServiceFactice()
    await banc.banc_d_un_modele(ConfigModele("bon"), morceaux, questions, fabrique=fabrique({"bon": service}), environnement=ENVIRONNEMENT)
    assert max(len(lot) for lot in service.appels) <= banc.LOT_DE_TEXTES and len(service.appels) >= 2


async def test_la_comparaison_de_deux_modeles_dit_le_meilleur_et_les_questions_qui_different():
    morceaux, questions = corpus_prepare()
    # Le « mauvais » modèle brouille les textes : sur 3 morceaux ou plus, le bon passage tombe hors du podium pour au moins une question.
    morceaux = morceaux + [Morceau("autre.md", k, f"texte {k} sans rapport avec la boutique {k * 7}") for k in range(8)]
    sortie = await banc.comparer(
        [ConfigModele("bon"), ConfigModele("mauvais", variable_cle="SCALEWAY_API_KEY")],
        morceaux,
        questions,
        fabrique=fabrique({"bon": ServiceFactice(), "mauvais": ServiceFactice(brouille=True)}),
        environnement=ENVIRONNEMENT,
    )
    bon, mauvais = sortie["modeles"]
    assert bon["taux_dans_les_3"] == 1.0 and mauvais["taux_dans_les_3"] < 1.0
    c = sortie["comparaison"]
    assert c["meilleur"] == "bon" and c["ecart_de_taux"] == pytest.approx(1.0 - mauvais["taux_dans_les_3"], abs=1e-4)
    assert set(c["questions_ou_ils_different"]) == {r["question"] for r in mauvais["ratees"]}
    assert sortie["questions"] == 3 and sortie["morceaux"] == len(morceaux)
    texte = banc.resume(sortie)
    assert "bon : 3/3" in texte and "Meilleur : bon" in texte and "ratée (rang" in texte


async def test_deux_modeles_a_egalite_ne_designent_personne():
    morceaux, questions = corpus_prepare()
    sortie = await banc.comparer([ConfigModele("a"), ConfigModele("b")], morceaux, questions, fabrique=fabrique({"a": ServiceFactice("x"), "b": ServiceFactice("y")}), environnement=ENVIRONNEMENT)
    assert sortie["comparaison"]["meilleur"] is None and "Égalité." in banc.resume(sortie)


async def test_un_ou_deux_modeles_seulement():
    morceaux, questions = corpus_prepare()
    for n in (0, 3):
        with pytest.raises(ErreurBanc):
            await banc.comparer([ConfigModele(f"m{i}") for i in range(n)], morceaux, questions, fabrique=fabrique({}), environnement=ENVIRONNEMENT)
    seul = await banc.comparer([ConfigModele("a")], morceaux, questions, fabrique=fabrique({"a": ServiceFactice()}), environnement=ENVIRONNEMENT)
    assert seul["comparaison"] == {}


async def test_une_mauvaise_dimension_est_refusee_parce_que_la_base_range_1536():
    morceaux, questions = corpus_prepare()
    with pytest.raises(ErreurBanc, match="1536"):
        await banc.banc_d_un_modele(ConfigModele("court"), morceaux, questions, fabrique=fabrique({"court": ServiceFactice(dimension=1024)}), environnement=ENVIRONNEMENT)


# --- les modèles : le défaut, le connu, l'exclu ----------------------------------------------------------------------------------


def test_les_modeles_visés_sont_connus_et_le_defaut_est_openai():
    defaut = banc.lire_le_modele("")
    assert (defaut.modele, defaut.adresse, defaut.variable_cle) == ("text-embedding-3-small", None, "OPENAI_API_KEY")
    qwen = banc.lire_le_modele("qwen3-embedding-8b")
    assert (qwen.adresse, qwen.variable_cle, qwen.fournisseur) == ("https://api.scaleway.ai/v1", "SCALEWAY_API_KEY", "openai")
    perso = banc.lire_le_modele("autre-modele@https://exemple.test/v1#MA_CLE")
    assert (perso.modele, perso.adresse, perso.variable_cle) == ("autre-modele", "https://exemple.test/v1", "MA_CLE")


def test_le_modele_exclu_est_refuse_proprement_avec_la_raison():
    with pytest.raises(ErreurBanc, match="refused.*1536"):
        banc.lire_le_modele("bge-multilingual-gemma2")
    with pytest.raises(ErreurBanc, match="refused"):
        banc.lire_le_modele("bge-multilingual-gemma2@https://api.scaleway.ai/v1")


# --- la clé ne s'affiche jamais ---------------------------------------------------------------------------------------------------


async def test_une_cle_absente_est_dite_par_le_nom_de_sa_variable_sans_rien_d_autre():
    morceaux, questions = corpus_prepare()
    with pytest.raises(ErreurBanc) as e:
        await banc.banc_d_un_modele(ConfigModele("qwen3-embedding-8b", variable_cle="SCALEWAY_API_KEY"), morceaux, questions, fabrique=fabrique({}), environnement={})
    assert "SCALEWAY_API_KEY" in str(e.value)


async def test_une_erreur_du_fournisseur_qui_contient_la_cle_est_masquee():
    class Fautif:
        async def embed_texts(self, textes):
            raise RuntimeError(f"401 Unauthorized for key {CLE_OPENAI}")

    async def f(config, cle):
        return Fautif()

    morceaux, questions = corpus_prepare()
    with pytest.raises(ErreurBanc) as e:
        await banc.banc_d_un_modele(ConfigModele("text-embedding-3-small"), morceaux, questions, fabrique=f, environnement=ENVIRONNEMENT)
    assert CLE_OPENAI not in str(e.value) and "***" in str(e.value)


async def test_la_sortie_ne_porte_jamais_la_cle_seulement_le_nom_de_sa_variable():
    morceaux, questions = corpus_prepare()
    sortie = await banc.comparer(
        [banc.lire_le_modele("text-embedding-3-small"), banc.lire_le_modele("qwen3-embedding-8b")],
        morceaux,
        questions,
        fabrique=fabrique({"text-embedding-3-small": ServiceFactice(), "qwen3-embedding-8b": ServiceFactice("q")}),
        environnement=ENVIRONNEMENT,
    )
    brut = json.dumps(sortie) + banc.resume(sortie)
    assert CLE_OPENAI not in brut and CLE_SCALEWAY not in brut
    assert [m["variable_cle"] for m in sortie["modeles"]] == ["OPENAI_API_KEY", "SCALEWAY_API_KEY"]


# --- la fabrique réelle de la base, et la ligne de commande ----------------------------------------------------------------------------


@pytest.fixture
def fabrique_de_la_base(monkeypatch):
    """La fabrique d'embedding de la base est remplacée : on voit ce qu'on lui demande, aucun client réseau n'est créé."""
    from api.services.gen_ai.embedding import factory

    demandes: list[dict] = []

    async def faux(**kwargs):
        demandes.append(kwargs)
        return ServiceFactice("q" if kwargs["model"].startswith("qwen") else "")

    monkeypatch.setattr(factory, "build_embedding_service", faux)
    return demandes


async def test_le_banc_utilise_la_fabrique_de_la_base_avec_l_adresse_et_la_cle_du_modele(fabrique_de_la_base):
    morceaux, questions = corpus_prepare()
    await banc.comparer(
        [banc.lire_le_modele("text-embedding-3-small"), banc.lire_le_modele("qwen3-embedding-8b")], morceaux, questions, environnement=ENVIRONNEMENT
    )
    openai, qwen = fabrique_de_la_base
    assert (openai["model"], openai["base_url"], openai["api_key"], openai["provider"]) == ("text-embedding-3-small", None, CLE_OPENAI, "openai")
    assert (qwen["model"], qwen["base_url"], qwen["api_key"]) == ("qwen3-embedding-8b", "https://api.scaleway.ai/v1", CLE_SCALEWAY)


def test_la_fabrique_de_la_base_demande_1536_dimensions_a_un_fournisseur_compatible_hors_openai():
    from api.services.gen_ai.embedding.factory import dimensions_demandees

    assert dimensions_demandees("openai", "https://api.scaleway.ai/v1") == 1536 and dimensions_demandees("openai", None) is None


def ecrire_le_corpus(dossier):
    (dossier / "boutique.md").write_text(DOCUMENT, encoding="utf-8")
    fichier = dossier / "corpus.json"
    fichier.write_text(json.dumps({"version": 1, "documents": ["boutique.md"], "questions": QUESTIONS}), encoding="utf-8")
    return fichier


def test_la_ligne_de_commande_ecrit_le_json_et_le_resume_sans_la_cle(tmp_path, monkeypatch, capsys, fabrique_de_la_base):
    for nom, valeur in ENVIRONNEMENT.items():
        monkeypatch.setenv(nom, valeur)
    sortie = tmp_path / "resultat.json"
    code = cli.main(["--corpus", str(ecrire_le_corpus(tmp_path)), "--modele", "text-embedding-3-small", "--modele", "qwen3-embedding-8b", "--max-tokens", "24", "--sortie", str(sortie)])
    affiche = capsys.readouterr()
    assert code == 0 and "text-embedding-3-small : 3/3" in affiche.out and "qwen3-embedding-8b" in affiche.out
    ecrit = json.loads(sortie.read_text(encoding="utf-8"))
    assert [m["modele"] for m in ecrit["modeles"]] == ["text-embedding-3-small", "qwen3-embedding-8b"]
    assert CLE_OPENAI not in affiche.out + affiche.err + sortie.read_text(encoding="utf-8") and CLE_SCALEWAY not in affiche.out + affiche.err + sortie.read_text(encoding="utf-8")


def test_la_ligne_de_commande_refuse_le_modele_exclu_avec_le_code_2(tmp_path, capsys, fabrique_de_la_base):
    code = cli.main(["--corpus", str(ecrire_le_corpus(tmp_path)), "--modele", "bge-multilingual-gemma2"])
    assert code == 2 and "refused" in capsys.readouterr().err and fabrique_de_la_base == []


def test_la_ligne_de_commande_refuse_une_cle_absente_sans_rien_appeler(tmp_path, monkeypatch, capsys, fabrique_de_la_base):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    code = cli.main(["--corpus", str(ecrire_le_corpus(tmp_path)), "--max-tokens", "24"])
    assert code == 2 and "OPENAI_API_KEY" in capsys.readouterr().err and fabrique_de_la_base == []
