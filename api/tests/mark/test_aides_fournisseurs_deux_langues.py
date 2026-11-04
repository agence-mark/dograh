"""[.mark] V4 : chaque champ d'un fournisseur dit son aide en français ET en anglais.

La question : un champ qui a une description anglaise de l'amont montre-t-il aussi sa phrase française (``mark_aide``) ? Une nouvelle
phrase de l'amont, absente du dictionnaire, fait échouer ce test : elle doit être traduite avant la montée de version.
"""

from api.services.configuration.aides_fr import AIDES_FR
from api.services.configuration.registry import REGISTRY


def _champs():
    for type_service, fournisseurs in REGISTRY.items():
        for nom, classe in fournisseurs.items():
            for champ, propriete in classe.model_json_schema().get("properties", {}).items():
                yield f"{getattr(type_service, 'value', type_service)}/{nom}/{champ}", propriete


def test_chaque_champ_decrit_a_son_aide_en_francais():
    sans = [cle for cle, p in _champs() if p.get("description") and not (p.get("mark_aide") or {}).get("fr")]
    assert sans == []


def test_l_aide_francaise_est_une_autre_phrase_que_l_anglaise():
    memes = [cle for cle, p in _champs() if p.get("mark_aide") and p["mark_aide"]["fr"] == p["mark_aide"]["en"]]
    assert memes == []


def test_le_dictionnaire_n_a_aucune_phrase_orpheline():
    decrites = {p["description"] for _c, p in _champs() if p.get("description")}
    # Une phrase du dictionnaire que plus aucun champ ne porte est un reste à retirer.
    from api.services.configuration.aides_fr import _cle

    portees = {_cle(d) for d in decrites}
    orphelines = [en for en in AIDES_FR if _cle(en) not in portees]
    assert orphelines == []
