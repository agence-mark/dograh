"""[.mark] Banc A, familles C8 (taille) et C9 (heure).

| Test | Run, tour | Ce que le client voulait |
|---|---|---|
| c8_1 | 2653 t2 | « la Regina, mettez-la plutôt en mega » : la ligne devient Regina Mega (le code rend OK sans rien changer) |
| c8_2 | 2643 t2 | « une grande et une petite » : une Mega et une Normale, sans redemander la taille |
| c8_3 | 2645 t3 | « normales toutes les deux » (Calzone et 4 Formaggi) : deux Normale, pas de taille redemandée |
| c8_4 | 2667 t2 | « deux reines normales » (le modèle a ôté « normales » de ``articles``) : deux Regina Normale sans question |
| c8_5 | 2640 t7 | « une Neptune normale » (idem) : Neptune Normale sans question |
| c8_6 | 2664 t1 | « moitié margherita moitié calzone, en normale » : la taille réelle (Mega seulement) est DITE, jamais posée en silence |
| c9_1 | 2667 t5 | changer l'heure sans redonner le mode : le mode posé est gardé, pas redemandé |
| c9_2 | 2667 t8 | « alors midi » après « nous rouvrons jeudi à onze heures » : jeudi 19 midi, pas le jour même (horloge du 18/11 à 2 h 40) |
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from api.tests.mark.banc_a.commun import appel_de, faire_monde, base_essai, base_prete, jouer_reel, trace  # noqa: F401

pytestmark = pytest.mark.banc_a
NUIT_DU_18 = datetime(2026, 11, 18, 2, 40, tzinfo=ZoneInfo("Europe/Paris"))


async def test_c8_1_2653_changer_la_taille_d_une_ligne(appel_de):
    a = await appel_de()
    await a.rejouer(2653, jusqu_au_tour=2)
    assert a.quantite_de("Regina Mega") == 1 and a.quantite_de("Regina Normale") == 0, "modifier(choix mega) rend OK, la ligne reste Normale" + trace(a)


async def test_c8_2_2643_une_grande_et_une_petite(appel_de):
    a = await appel_de()
    await a.rejouer(2643, jusqu_au_tour=2)
    assert a.quantite_de("Margherita Mega") == 1 and a.quantite_de("Margherita Normale") == 1, "« une grande et une petite » non lu" + trace(a)


async def test_c8_3_2645_normales_toutes_les_deux(appel_de):
    a = await appel_de()
    await a.rejouer(2645, jusqu_au_tour=3)
    assert sorted(a.noms()) == ["4 Formaggi Normale", "Calzone Normale"], "« normales toutes les deux » non lu ou taille redemandée" + trace(a)


async def test_c8_4_2667_la_taille_dans_les_mots_quand_articles_l_a_perdue(appel_de):
    a = await appel_de()
    await a.rejouer(2667, jusqu_au_tour=1)
    r = await jouer_reel(a, 2667, 2)  # ajouter_au_panier {articles: "deux pizzas reines", mots: "Deux reines normales"}
    assert r["statut"] != "CHOIX_OBLIGATOIRE" and a.quantite_de("Regina Normale") == 2, "la taille dite (« normales ») est redemandée" + trace(a)


async def test_c8_5_2640_la_taille_dans_les_mots_neptune(appel_de):
    a = await appel_de()
    a.greffier(type_de_commande="en livraison", adresse_livraison="12 rue de la République", commune="Senlis")
    await a.rejouer(2640, jusqu_au_tour=6)
    r = await jouer_reel(a, 2640, 7)  # ajouter_au_panier {articles: "une pizza Neptune", mots: "Oui, une Neptune normale"}
    assert r["statut"] != "CHOIX_OBLIGATOIRE" and a.quantite_de("Neptune Normale") == 1, "la taille dite (« normale ») est redemandée" + trace(a)


async def test_c8_6_2664_la_moitie_moitie_dit_sa_taille(appel_de):
    a = await appel_de()
    r = await a.rejouer(2664, jusqu_au_tour=1)
    dit = (str(r.get("faits")) + " " + (r.get("suggestion") or "")).lower()
    assert "mega" in dit or a.quantite_de("Pizza moitié-moitié Normale") == 1, "demandée en normale, posée en Mega (seule taille) sans le dire" + trace(a)


@pytest.mark.parametrize("faire_monde", [NUIT_DU_18], indirect=True)
async def test_c9_1_2667_changer_l_heure_garde_le_mode_pose(appel_de):
    a = await appel_de()
    await a.rejouer(2667, jusqu_au_tour=4)
    r = await jouer_reel(a, 2667, 5)  # type_de_commande {heure: "trois heures du matin demain", mots: "...récupérer demain à 3 heures du matin"} sans mode
    assert a.p.get("mode") == "emporter" and r["statut"] != "ARGUMENT_INVALIDE", "le mode est posé, il est redemandé" + trace(a)


@pytest.mark.parametrize("faire_monde", [NUIT_DU_18], indirect=True)
async def test_c9_2_2667_midi_apres_la_reouverture_annoncee(appel_de):
    a = await appel_de()
    await a.rejouer(2667, jusqu_au_tour=8)
    heure = str(a.p.get("heure_voulue") or "")
    assert heure.startswith("2026-11-19"), f"« alors midi » enregistré le {heure!r} au lieu de jeudi 19" + trace(a)
