"""[.mark] Builder partie 2, U7 (sous-lot 1) : la bibliothèque v2.

| Test | Ce qu'il prouve |
|---|---|
| fiches | chaque famille a sa fiche (départ versé, jamais remplacée), modifiable par l'équipe seulement ; lue par le builder |
| familles créées | une famille créée à l'écran est lue par le builder ; une famille du code ne se renomme ni ne se supprime ; suppression refusée si elle a des éléments |
| formes | un contenu hors schéma est refusé (personnage, scénario, phrases) ; une famille créée ne prend que du texte |
| sous-dossiers | créés, remplis, filtrés avec leurs descendants ; un dossier plein ne se supprime pas |
| étiquettes | posées, filtrées, renommées partout (refus si elle existe), supprimées sans supprimer un élément |
| parcourir | pagination (25), recherche dans le titre, les étiquettes et le contenu |
| dépôt | un Markdown / un Word déposé entre en Candidat avec son origine ; réimport = comparatif ; illisible, trop long ou structuré = refusé |
| propositions | une fiche ou une famille proposée par le builder attend une personne |
| droits | tout le monde lit, l'équipe .mark seule écrit |
"""

from __future__ import annotations

import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import builder as route
from api.services.auth.depends import get_user, get_user_with_selected_organization
from api.services.builder import versement
from api.services.builder.actions.registre import Contexte, executer
from api.services.builder.bibliotheque import fiches, propositions, service
from api.services.builder.bibliotheque.modele import Statut
from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, ORG_MARK, utilisateur

EQUIPE = utilisateur(1, ORG_CLIENT)
AUTRE = utilisateur(2, 8)
CONTEXTE = Contexte(user=EQUIPE, workflow_id=AGENT)
B = "/builder/bibliotheque"


def client_pour(user) -> TestClient:
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: user
    app.dependency_overrides[get_user] = lambda: user
    return TestClient(app)


@pytest.fixture
def c(monde):
    return client_pour(EQUIPE)


# --- les fiches de famille ----------------------------------------------------------------------------------------


def test_toutes_les_familles_du_code_ont_une_fiche_de_depart():
    from api.services.builder.bibliotheque.familles import FAMILLES

    depart = fiches.fiches_de_depart()
    assert set(FAMILLES) == set(depart)
    for slug, f in depart.items():
        assert f["description"] and f["quand"] and f["comment"], slug


def test_la_liste_des_familles_porte_la_fiche_et_dit_si_elle_est_du_code(c):
    familles = {f["slug"]: f for f in c.get(f"{B}/familles").json()}
    assert familles["moules-etape"]["du_code"] is True
    assert "moule" in familles["moules-etape"]["fiche"]["description"].lower()


def test_modifier_une_fiche_est_reserve_a_l_equipe_et_la_fiche_modifiee_est_lue(c, monde):
    nouvelle = {"description": "d", "quand": "q", "comment": "c"}
    assert client_pour(AUTRE).put(f"{B}/familles/moules-etape", json={"fiche": nouvelle}).status_code == 403
    assert c.put(f"{B}/familles/moules-etape", json={"fiche": nouvelle}).status_code == 200
    lue = {f["slug"]: f for f in c.get(f"{B}/familles").json()}["moules-etape"]
    assert lue["fiche"] == nouvelle and lue["libelle"] == "Moules d'étape"
    assert client_pour(AUTRE).get(f"{B}/familles").status_code == 200  # tout le monde lit


async def test_le_versement_ecrit_les_fiches_de_depart_et_ne_remplace_jamais_une_fiche_corrigee(monde, tmp_path):
    await fiches.ecrire("moules-etape", fiches.Fiche(description="corrigée par Evan"))
    rapport = await versement.verser(tmp_path)
    assert "moules-etape" not in rapport.fiches and len(rapport.fiches) == 33
    assert (await fiches.lire("moules-etape")).description == "corrigée par Evan"
    assert (await versement.verser(tmp_path)).fiches == []  # idempotent


async def test_le_builder_lit_la_fiche_avant_de_chercher_ou_d_ecrire(monde):
    await service.creer("moules-etape", "q", "Qualifier", {"texte": "t"}, "alice")
    sans_famille = await executer("bibliotheque_lister", {}, CONTEXTE)
    fiche = next(f for f in sans_famille["familles"] if f["slug"] == "moules-etape")["fiche"]
    assert fiche["comment"]
    avec = await executer("bibliotheque_lister", {"famille": "moules-etape"}, CONTEXTE)
    assert avec["fiche"] == fiche and [e["slug"] for e in avec["elements"]] == ["q"]
    lu = await executer("bibliotheque_lire", {"famille": "moules-etape", "slug": "q"}, CONTEXTE)
    assert lu["fiche_de_la_famille"] == fiche


# --- les familles créées à l'écran --------------------------------------------------------------------------------

NOUVELLE = {"slug": "metiers", "libelle": "Métiers", "groupe": "guide", "cible": "builder"}


async def test_une_famille_creee_a_l_ecran_est_lue_par_le_builder_et_par_le_mcp(c, monde):
    reponse = c.post(f"{B}/familles", json={**NOUVELLE, "fiche": {"description": "Fiches métier", "quand": "audit", "comment": "du texte"}})
    assert reponse.status_code == 201 and reponse.json()["du_code"] is False and reponse.json()["mode"] == "fournit"
    assert c.post(f"{B}/metiers", json={"slug": "chauffagiste", "titre": "Chauffagiste", "contenu": {"texte": "Un métier."}}).status_code == 201
    # Le builder (écran) : la famille et sa fiche, puis l'élément.
    rendu = await executer("bibliotheque_lister", {}, CONTEXTE)
    metiers = next(f for f in rendu["familles"] if f["slug"] == "metiers")
    assert metiers["fiche"]["description"] == "Fiches métier"
    lu = await executer("bibliotheque_lire", {"famille": "metiers", "slug": "chauffagiste"}, CONTEXTE)
    assert lu["contenu"] == {"texte": "Un métier."}
    # Claude Code (MCP) : même action, même résultat.
    via_mcp = await executer("bibliotheque_lire", {"famille": "metiers", "slug": "chauffagiste"}, Contexte(user=EQUIPE, porte="mcp"))
    assert via_mcp["contenu"] == lu["contenu"]
    # Appliquer une famille créée rend le contenu au builder (mode fournit).
    applique = await executer("bibliotheque_appliquer", {"famille": "metiers", "slug": "chauffagiste"}, CONTEXTE)
    assert applique["ok"] and applique["applique"] is False and applique["contenu"] == {"texte": "Un métier."}


def test_une_famille_creee_ne_prend_que_du_texte(c):
    c.post(f"{B}/familles", json=NOUVELLE)
    refus = c.post(f"{B}/metiers", json={"slug": "x", "titre": "X", "contenu": {"valeurs": {"a": 1}}})
    assert refus.status_code == 422


def test_une_famille_du_code_ne_se_renomme_ni_ne_se_supprime(c):
    assert c.put(f"{B}/familles/moules-etape", json={"libelle": "Autre nom"}).status_code == 403
    assert c.delete(f"{B}/familles/moules-etape").status_code == 403
    assert c.post(f"{B}/familles", json={**NOUVELLE, "slug": "moules-etape", "libelle": "Autre"}).status_code == 409
    assert c.post(f"{B}/familles", json={**NOUVELLE, "libelle": "Moules d'étape"}).status_code == 409  # même nom qu'une famille du code


def test_une_famille_se_renomme_et_ne_se_supprime_que_vide(c, monde):
    c.post(f"{B}/familles", json=NOUVELLE)
    assert c.put(f"{B}/familles/metiers", json={"libelle": "Savoir-faire"}).json()["libelle"] == "Savoir-faire"
    c.post(f"{B}/metiers", json={"slug": "x", "titre": "X", "contenu": {"texte": "t"}})
    assert c.delete(f"{B}/familles/metiers").status_code == 409
    assert c.get(f"{B}/metiers/x").status_code == 200  # rien n'a été perdu
    # L'élément part, la famille aussi.
    monde.configs.pop((ORG_MARK, "MARK_BIBLIO:metiers:x"))
    assert c.delete(f"{B}/familles/metiers").status_code == 204
    assert "metiers" not in {f["slug"] for f in c.get(f"{B}/familles").json()}


def test_une_famille_inconnue_reste_inconnue(c):
    assert c.get(f"{B}?famille=inventee").status_code == 404
    assert c.post(f"{B}/inventee", json={"slug": "x", "titre": "X", "contenu": {"texte": "t"}}).status_code == 404


# --- la forme du contenu ------------------------------------------------------------------------------------------


async def test_un_contenu_hors_schema_est_refuse_et_un_contenu_conforme_passe(monde):
    from api.services.builder.bibliotheque.service import ErreurBibliotheque

    with pytest.raises(ErreurBibliotheque, match="description"):
        await service.creer("personnages-appelant", "vide", "Vide", {"but": "x"}, "a")
    with pytest.raises(ErreurBibliotheque, match="regles"):
        await service.creer("phrases-du-code", "vide", "Vide", {"texte": "x"}, "a")
    with pytest.raises(ErreurBibliotheque, match="but"):
        await service.creer("scenarios-test", "vide", "Vide", {"personnage": "presse"}, "a")
    with pytest.raises(ErreurBibliotheque, match="termes"):
        await service.creer("lexiques", "vide", "Vide", {"termes": []}, "a")
    await service.creer("personnages-appelant", "presse", "Pressé", {"description": "Toujours pressé.", "comportements": ["coupe la parole"]}, "a")
    await service.creer("scenarios-test", "rdv", "RDV", {"but": "Prendre un rendez-vous", "personnage": "presse", "criteres": [{"type": "outil", "nom": "reserver"}]}, "a")
    # Une nouvelle version est contrôlée comme la première.
    with pytest.raises(ErreurBibliotheque):
        await service.ajouter_version("personnages-appelant", "presse", {"but": "sans description"}, "a")


# --- les sous-dossiers --------------------------------------------------------------------------------------------


def test_les_sous_dossiers_se_creent_se_remplissent_et_se_filtrent_avec_leurs_descendants(c):
    assert c.post(f"{B}/familles/moules-etape/dossiers", json={"chemin": "restauration"}).json() == ["restauration"]
    for slug, dossier in (("a", "restauration"), ("b", "restauration/rdv"), ("c", "")):
        c.post(f"{B}/moules-etape", json={"slug": slug, "titre": slug.upper(), "contenu": {"texte": slug}})
        if dossier:
            assert c.post(f"{B}/moules-etape/{slug}/rangement", json={"dossier": dossier}).json()["dossier"] == dossier
    assert c.get(f"{B}/familles/moules-etape/dossiers").json() == ["restauration", "restauration/rdv"]
    tous = c.get(f"{B}/parcourir", params={"famille": "moules-etape", "dossier": "restauration"}).json()
    assert {e["slug"] for e in tous["elements"]} == {"a", "b"} and tous["total"] == 2
    seul = c.get(f"{B}/parcourir", params={"famille": "moules-etape", "dossier": "restauration/rdv"}).json()
    assert [e["slug"] for e in seul["elements"]] == ["b"]
    # Ranger ne crée pas de version et ne touche pas au statut.
    element = c.get(f"{B}/moules-etape/a").json()
    assert len(element["versions"]) == 1 and element["versions"][0]["statut"] == "candidat"


def test_un_dossier_plein_ne_se_supprime_pas_un_dossier_vide_oui(c):
    c.post(f"{B}/moules-etape", json={"slug": "a", "titre": "A", "contenu": {"texte": "a"}})
    c.post(f"{B}/moules-etape/a/rangement", json={"dossier": "plein"})
    c.post(f"{B}/familles/moules-etape/dossiers", json={"chemin": "vide"})
    assert c.delete(f"{B}/familles/moules-etape/dossiers", params={"chemin": "plein"}).status_code == 409
    assert c.delete(f"{B}/familles/moules-etape/dossiers", params={"chemin": "vide"}).json() == ["plein"]
    c.post(f"{B}/moules-etape/a/rangement", json={"dossier": ""})
    assert c.get(f"{B}/moules-etape/a").json()["dossier"] == ""
    assert c.post(f"{B}/familles/moules-etape/dossiers", json={"chemin": "Pas Valide"}).status_code == 422


# --- les étiquettes -----------------------------------------------------------------------------------------------


def _deux_elements(c):
    for slug in ("a", "b"):
        c.post(f"{B}/moules-etape", json={"slug": slug, "titre": slug.upper(), "contenu": {"texte": slug}})
    c.post(f"{B}/moules-etape/a/rangement", json={"etiquettes": ["urgence", "artisan"]})
    c.post(f"{B}/moules-etape/b/rangement", json={"etiquettes": ["urgence"]})


def test_les_etiquettes_se_posent_se_filtrent_et_se_comptent(c):
    _deux_elements(c)
    assert {e["nom"]: e["elements"] for e in c.get(f"{B}/etiquettes").json()} == {"artisan": 1, "urgence": 2}
    les_deux = c.get(f"{B}/parcourir", params={"etiquette": ["urgence"]}).json()
    assert {e["slug"] for e in les_deux["elements"]} == {"a", "b"}
    toutes_posees = c.get(f"{B}/parcourir", params={"etiquette": ["urgence", "artisan"]}).json()
    assert [e["slug"] for e in toutes_posees["elements"]] == ["a"] and toutes_posees["elements"][0]["etiquettes"] == ["urgence", "artisan"]


def test_renommer_une_etiquette_s_applique_partout_et_est_refuse_si_elle_existe(c):
    _deux_elements(c)
    assert c.put(f"{B}/etiquettes", params={"ancien": "urgence"}, json={"nom": "artisan"}).status_code == 409
    liste = c.put(f"{B}/etiquettes", params={"ancien": "urgence"}, json={"nom": "panne"}).json()
    assert {e["nom"]: e["elements"] for e in liste} == {"artisan": 1, "panne": 2}
    assert c.get(f"{B}/moules-etape/a").json()["etiquettes"] == ["panne", "artisan"]
    assert c.get(f"{B}/moules-etape/b").json()["etiquettes"] == ["panne"]


def test_supprimer_une_etiquette_la_retire_de_ses_elements_sans_en_supprimer_un(c):
    _deux_elements(c)
    liste = c.delete(f"{B}/etiquettes", params={"nom": "urgence"}).json()
    assert [e["nom"] for e in liste] == ["artisan"]
    assert c.get(f"{B}/moules-etape/a").json()["etiquettes"] == ["artisan"]
    assert c.get(f"{B}/moules-etape/b").json()["etiquettes"] == []
    assert c.get(f"{B}/parcourir").json()["total"] == 2  # aucun élément supprimé
    assert c.delete(f"{B}/etiquettes", params={"nom": "inconnue"}).status_code == 404


async def test_le_builder_range_et_cherche(monde):
    await service.creer("moules-etape", "q", "Qualifier", {"texte": "poser la question du chauffage"}, "alice")
    ok = await executer("bibliotheque_ranger", {"famille": "moules-etape", "slug": "q", "dossier": "rdv", "etiquettes": ["urgence"]}, CONTEXTE)
    assert ok["ok"] and ok["dossier"] == "rdv" and ok["etiquettes"] == ["urgence"]
    trouve = await executer("bibliotheque_chercher", {"recherche": "chauffage", "etiquettes": ["urgence"]}, CONTEXTE)
    assert trouve["total"] == 1 and trouve["elements"][0]["extrait"]
    refus = await executer("bibliotheque_ranger", {"famille": "moules-etape", "slug": "q", "dossier": "x"}, Contexte(user=AUTRE, workflow_id=AGENT))
    assert refus.get("ok") is not True


# --- parcourir : pagination et recherche --------------------------------------------------------------------------


async def test_la_liste_est_paginee_par_25_et_se_cherche_dans_le_contenu(monde):
    for n in range(30):
        await service.creer("moules-etape", f"e{n:02d}", f"Moule {n:02d}", {"texte": "banal" if n else "tuyau de poêle"}, "a")
    total, page = await service.parcourir("moules-etape")
    assert total == 30 and len(page) == 25
    total, suite = await service.parcourir("moules-etape", decalage=25)
    assert total == 30 and len(suite) == 5 and not {e.slug for e in suite} & {e.slug for e in page}
    total, trouves = await service.parcourir(recherche="TUYAU")
    assert total == 1 and trouves[0].slug == "e00" and "tuyau" in trouves[0].extrait.lower()
    total, par_titre = await service.parcourir(recherche="moule 07")
    assert [e.slug for e in par_titre] == ["e07"] and par_titre[0].extrait is None
    assert (await service.parcourir(recherche="introuvable"))[0] == 0


# --- le dépôt d'un document ---------------------------------------------------------------------------------------


@pytest.fixture
def conversion_locale(monkeypatch):
    """La conversion réelle (``extraire``), jouée dans le processus du test : même résultat, sans lancer de processus."""
    from api.services.builder.dossiers import extraction

    async def en_place(nom, contenu, delai_s=None):
        return extraction.extraire(nom, contenu)

    monkeypatch.setattr(extraction, "extraire_hors_boucle", en_place)


def _word(*paragraphes: str) -> bytes:
    from docx import Document

    document = Document()
    for p in paragraphes:
        document.add_paragraph(p)
    flux = io.BytesIO()
    document.save(flux)
    return flux.getvalue()


def _pdf(texte: str) -> bytes:
    flux = f"BT /F1 12 Tf 72 720 Td ({texte}) Tj ET".encode("latin-1")
    objets = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(flux)).encode() + b" >>\nstream\n" + flux + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    sortie, decalages = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objets, start=1):
        decalages.append(len(sortie))
        sortie += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    debut_xref = len(sortie)
    sortie += f"xref\n0 {len(objets) + 1}\n0000000000 65535 f \n".encode()
    for d in decalages:
        sortie += f"{d:010d} 00000 n \n".encode()
    sortie += f"trailer\n<< /Size {len(objets) + 1} /Root 1 0 R >>\nstartxref\n{debut_xref}\n%%EOF".encode()
    return bytes(sortie)


def _deposer(c, nom, donnees, **champs):
    return c.post(f"{B}/depot", data={"famille": "regles-redaction", **champs}, files={"fichier": (nom, donnees)})


def test_un_markdown_depose_entre_en_candidat_avec_son_origine(c, conversion_locale):
    reponse = _deposer(c, "Règle des chiffres.md", "# Les chiffres\n\nUn numéro se dit par paires.".encode(), licence="interne", etiquettes="voix, chiffres", dossier="oral")
    assert reponse.status_code == 200, reponse.text
    element = reponse.json()["element"]
    assert reponse.json()["cree"] is True and element["slug"] == "regle-des-chiffres" and element["titre"] == "Règle des chiffres"
    version = element["versions"][0]
    assert version["statut"] == "candidat" and "par paires" in version["contenu"]["texte"]
    assert version["origine"]["source"] == "Règle des chiffres.md" and version["origine"]["licence"] == "interne"
    assert element["dossier"] == "oral" and element["etiquettes"] == ["voix", "chiffres"]


def test_un_word_et_un_pdf_sont_convertis_sur_place(c, conversion_locale):
    mot = _deposer(c, "audit.docx", _word("Premier paragraphe.", "Second paragraphe."))
    assert mot.status_code == 200, mot.text
    assert "Premier paragraphe." in mot.json()["element"]["versions"][0]["contenu"]["texte"]
    pdf = _deposer(c, "note.pdf", _pdf("Bonjour depuis un PDF"))
    assert pdf.status_code == 200, pdf.text
    assert "Bonjour depuis un PDF" in pdf.json()["element"]["versions"][0]["contenu"]["texte"]


def test_deposer_deux_fois_ajoute_une_version_seulement_si_le_texte_a_change(c, conversion_locale):
    assert _deposer(c, "r.md", b"un").json()["cree"] is True
    identique = _deposer(c, "r.md", b"un").json()
    assert identique["cree"] is False and len(identique["element"]["versions"]) == 1 and identique["comparatif"]["identique"] is True
    change = _deposer(c, "r.md", b"deux").json()
    assert len(change["element"]["versions"]) == 2 and change["element"]["versions"][-1]["statut"] == "candidat"
    assert change["comparatif"]["identique"] is False


def test_un_depot_illisible_trop_long_ou_destine_a_une_famille_structuree_est_refuse(c, conversion_locale):
    assert _deposer(c, "x.exe", b"MZ").status_code == 422
    assert _deposer(c, "vide.md", b"   ").status_code == 422
    long = _deposer(c, "long.md", ("mot " * 4000).encode())
    assert long.status_code == 422 and "split" in long.json()["detail"]
    structuree = c.post(f"{B}/depot", data={"famille": "personnages-appelant"}, files={"fichier": ("p.md", b"texte")})
    assert structuree.status_code == 422 and "structured" in structuree.json()["detail"]
    assert client_pour(AUTRE).post(f"{B}/depot", data={"famille": "regles-redaction"}, files={"fichier": ("a.md", b"a")}).status_code == 403
    assert c.get(f"{B}/parcourir").json()["total"] == 0  # rien n'est entré


# --- les propositions du builder ----------------------------------------------------------------------------------


async def test_une_fiche_ou_une_famille_proposee_par_le_builder_attend_une_personne(monde):
    p1 = await executer(
        "bibliotheque_proposer",
        {"type": "fiche", "famille": "moules-etape", "slug": "moules-etape", "justification": "plus clair", "contenu": {"description": "D", "quand": "Q", "comment": "C"}},
        CONTEXTE,
    )
    p2 = await executer(
        "bibliotheque_proposer",
        {"type": "famille", "famille": "metiers", "slug": "metiers", "justification": "il manque un rayon", "contenu": {"libelle": "Métiers", "groupe": "guide"}},
        CONTEXTE,
    )
    assert p1["ok"] and p2["ok"]
    assert (await fiches.lire("moules-etape")).description != "D"  # rien n'est écrit tant que personne n'a accepté
    from api.services.builder.bibliotheque import familles_libres

    assert "metiers" not in await familles_libres.libres()
    await propositions.accepter(p1["proposition"], "evan")
    await propositions.accepter(p2["proposition"], "evan")
    assert (await fiches.lire("moules-etape")).description == "D"
    assert "metiers" in await familles_libres.libres()
    # Le builder n'a pas de geste pour accepter.
    assert "bibliotheque_accepter_proposition" not in __import__("api.services.builder.actions", fromlist=["REGISTRE"]).REGISTRE


async def test_une_proposition_de_fiche_ou_de_famille_sans_contenu_est_refusee(monde):
    from api.services.builder.bibliotheque.service import ErreurBibliotheque

    with pytest.raises(ErreurBibliotheque):
        await propositions.creer("fiche", "moules-etape", "moules-etape", "j", "builder")
    with pytest.raises(ErreurBibliotheque):
        await propositions.creer("famille", "x", "nouvelle", "j", "builder", contenu={"groupe": "guide"})


# --- aucune écriture sans l'équipe --------------------------------------------------------------------------------


def test_tout_le_monde_lit_seule_l_equipe_ecrit(c):
    autre = client_pour(AUTRE)
    c.post(f"{B}/moules-etape", json={"slug": "a", "titre": "A", "contenu": {"texte": "a"}})
    for lecture in (f"{B}/familles", f"{B}/etiquettes", f"{B}/parcourir", f"{B}/familles/moules-etape/dossiers"):
        assert autre.get(lecture).status_code == 200, lecture
    ecritures = (
        autre.post(f"{B}/familles", json=NOUVELLE),
        autre.put(f"{B}/familles/moules-etape", json={"fiche": {"description": "x"}}),
        autre.delete(f"{B}/familles/metiers"),
        autre.post(f"{B}/familles/moules-etape/dossiers", json={"chemin": "x"}),
        autre.post(f"{B}/etiquettes", json={"nom": "x"}),
        autre.put(f"{B}/etiquettes", params={"ancien": "x"}, json={"nom": "y"}),
        autre.delete(f"{B}/etiquettes", params={"nom": "x"}),
        autre.post(f"{B}/moules-etape/a/rangement", json={"dossier": "x"}),
    )
    assert [r.status_code for r in ecritures] == [403] * len(ecritures)
    assert c.get(f"{B}/moules-etape/a").json()["dossier"] == ""  # rien n'a bougé


def test_une_famille_du_code_garde_son_statut_meme_rangee(c):
    c.post(f"{B}/moules-etape", json={"slug": "a", "titre": "A", "contenu": {"texte": "a"}})
    c.post(f"{B}/moules-etape/a/statut", json={"version": 1, "statut": "recette", "banc": {"description": "banc"}})
    c.post(f"{B}/moules-etape/a/rangement", json={"dossier": "x", "etiquettes": ["y"]})
    assert c.get(f"{B}/moules-etape/a").json()["versions"][0]["statut"] == Statut.RECETTE.value
