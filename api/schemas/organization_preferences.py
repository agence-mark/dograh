from pydantic import BaseModel, Field, field_validator

# A mapping is hand-maintained in the settings modal, so these ceilings exist to
# keep a malformed or pasted payload out of the org configuration row rather
# than to constrain any real deployment.
MAX_DISPOSITION_MAPPING_ENTRIES = 200
MAX_DISPOSITION_CODE_LENGTH = 64


class AdresseEtablissement(BaseModel):
    """[.mark] The business's address: organization-wide, overridable per agent.

    Given to agents as ``{{adresse_etablissement}}``. The town recognition
    (``api/services/communes/``) reads only the postal code and the commune,
    never the street.

    ⛔ Only the FORMAT is checked here. That the commune exists and carries
    this postal code is checked by the save routes, against the national list:
    this model is also read when a call is set up, and a refusal there must
    never cost the call (same rule as the opening hours).
    """

    code_postal: str = Field(pattern=r"^\d{5}$", description="Postal code, 5 digits.")
    code_insee: str = Field(
        pattern=r"^[0-9][0-9AB][0-9]{3}$",
        description="INSEE code of the commune chosen in the postal code's list.",
    )
    commune: str = Field(min_length=1, max_length=100, description="Official name of the commune.")
    voie: str | None = Field(
        default=None,
        max_length=200,
        description="Street number and name. Optional; not used to recognise towns.",
    )

    @field_validator("voie", mode="before")
    @classmethod
    def _voie_vide_a_none(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class OrganizationPreferences(BaseModel):
    test_phone_number: str | None = None
    timezone: str | None = None
    adresse_etablissement: AdresseEtablissement | None = Field(
        default=None,
        description=(
            "[.mark] The business's address. Helps recognise the towns callers "
            "name, and is given to agents as {{adresse_etablissement}}."
        ),
    )
    external_pbx_integrations_enabled: bool = False
    disposition_mapping_enabled: bool = False
    disposition_mapping: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Dograh disposition -> the code this organization uses for it. "
            "Applied when writing `gathered_context.mapped_call_disposition`, "
            "so webhooks, run filters, reports and external-PBX write-backs all "
            "read the organization's own vocabulary. Dispositions absent from "
            "the mapping pass through unchanged."
        ),
    )

    @field_validator("disposition_mapping", mode="before")
    @classmethod
    def _normalize_disposition_mapping(cls, value):
        """Drop the rows that carry no information, and reject unusable ones.

        The settings modal seeds every known disposition with itself, so most of
        what it submits is identity rows. Storing those would freeze the mapping
        against the platform's disposition catalog: a disposition added later
        would be absent from the stored config and pass through anyway, which is
        exactly what an identity row means. Keeping only the overrides makes the
        stored config the set of decisions someone actually made.
        """
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("disposition_mapping must be an object")

        normalized: dict[str, str] = {}
        for raw_key, raw_value in value.items():
            if not isinstance(raw_key, str) or not isinstance(raw_value, str):
                raise ValueError("disposition_mapping keys and values must be strings")
            source = raw_key.strip()
            target = raw_value.strip()
            if not source or not target or source == target:
                continue
            if (
                len(source) > MAX_DISPOSITION_CODE_LENGTH
                or len(target) > MAX_DISPOSITION_CODE_LENGTH
            ):
                raise ValueError(
                    "disposition codes must be at most "
                    f"{MAX_DISPOSITION_CODE_LENGTH} characters"
                )
            normalized[source] = target

        if len(normalized) > MAX_DISPOSITION_MAPPING_ENTRIES:
            raise ValueError(
                "disposition_mapping accepts at most "
                f"{MAX_DISPOSITION_MAPPING_ENTRIES} entries"
            )
        return normalized
