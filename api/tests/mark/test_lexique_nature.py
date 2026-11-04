"""[.mark] V4 : la nature d'un terme du lexique (Marque / Nom propre / Mot du métier), comme la maquette.

La question : la nature posée fixe-t-elle le type que le code lit (reconnu et corrigé, ou seulement écouté), et un terme d'avant ce
champ se lit-il comme avant ?
"""

import pytest
from pydantic import ValidationError

from api.schemas.lexique_metier import LexiqueMetier, TermeLexique


def test_une_marque_et_un_nom_propre_sont_des_noms_un_mot_du_metier_est_un_mot():
    assert TermeLexique(terme="Edilkamin", nature="marque").type == "nom"
    assert TermeLexique(terme="Dupont", nature="nom_propre").type == "nom"
    assert TermeLexique(terme="insert", nature="mot_du_metier").type == "mot"


def test_la_nature_l_emporte_sur_un_type_contradictoire():
    assert TermeLexique(terme="insert", type="nom", nature="mot_du_metier").type == "mot"
    assert TermeLexique(terme="Jotul", type="mot", nature="marque").type == "nom"


def test_un_terme_d_avant_le_champ_se_lit_comme_avant():
    ancien = TermeLexique.model_validate({"terme": "Jotul", "type": "mot"})
    assert ancien.nature is None and ancien.type == "mot"
    assert TermeLexique.model_validate({"terme": "Jotul"}).type == "nom"


def test_une_nature_inconnue_est_refusee():
    with pytest.raises(ValidationError):
        TermeLexique(terme="x", nature="sigle")


def test_la_nature_survit_a_l_aller_retour_du_lexique():
    lexique = LexiqueMetier(termes=[TermeLexique(terme="Edilkamin", nature="marque"), TermeLexique(terme="insert", nature="mot_du_metier")])
    relu = LexiqueMetier.model_validate(lexique.model_dump())
    assert [(t.nature, t.type) for t in relu.termes] == [("marque", "nom"), ("mot_du_metier", "mot")]
