"""Lot 20, D70 : le plafond des appels simultanés d'une série de l'appelant simulé est à 5."""

import pytest
from pydantic import ValidationError

from api.schemas.appel_simule import ReglagesAppelantSimule


def test_plafond_simultanes_cinq():
    assert ReglagesAppelantSimule(simultanes=5).simultanes == 5
    with pytest.raises(ValidationError):
        ReglagesAppelantSimule(simultanes=6)
