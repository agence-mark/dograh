"use client";

/**
 * [.mark] The five themes of the Platform Settings page (convention § 2):
 * Organization, Business, Listening, Integrations, Developers.
 *
 * Organization, Business and Integrations save with their theme button, which
 * stays ENABLED untouched like the cards they come from (E6: the PUT replaces
 * the whole row, saving untouched was a gesture of its own). Listening and
 * Developers keep the buttons of what they contain (the trade vocabulary, MCP
 * and Telemetry, reused as they are).
 */
import { Building2, Code, Ear, ExternalLink, type LucideIcon, Plug, Settings, SlidersHorizontal } from "lucide-react";
import { useEffect, useId, useState } from "react";
import TimezoneSelect, { type ITimezoneOption } from "react-timezone-select";

import type { AdresseEtablissement, OrganizationPreferences } from "@/client/types.gen";
import { DispositionMappingDialog } from "@/components/DispositionMappingDialog";
import { MCPSection } from "@/components/MCPSection";
import { TelemetrySection } from "@/components/TelemetrySection";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

import { ChampAdresseEtablissement } from "../ChampAdresseEtablissement";
import { ChampReglage } from "../ecran/ChampReglage";
import { Intertitre } from "../ecran/Intertitre";
import { type ErreurNommee, Theme } from "../ecran/Theme";
import { allerAuReglage } from "../ecran/useThemesOuverts";
import { type Texte, useLangue } from "../langue/langue";
import { texteAdresse } from "../SectionAdresseEtablissement";
import {
    ANNONCE_ENREGISTREE,
    ChampsAnnonceOuverture,
    type EtatAnnonceOuverture,
    EtatLectureAnnonce,
} from "../SectionAnnonceOuverture";
import { SectionLexiqueMetier } from "../SectionLexiqueMetier";
import type { EtatPreferences } from "./preferences";
import type { ThemeOrganisation } from "./references/cas-organisation";

export const THEMES_ORGANISATION: Array<{ id: ThemeOrganisation; titre: Texte; icone: LucideIcon }> = [
    { id: "organisation", titre: { en: "Organization", fr: "Organisation" }, icone: Settings },
    { id: "etablissement", titre: { en: "Business", fr: "Établissement" }, icone: Building2 },
    { id: "ecoute", titre: { en: "Listening", fr: "Écoute" }, icone: Ear },
    { id: "integrations", titre: { en: "Integrations", fr: "Intégrations" }, icone: Plug },
    { id: "developpeurs", titre: { en: "Developers", fr: "Développeurs" }, icone: Code },
];

const titre = (id: ThemeOrganisation) => THEMES_ORGANISATION.find((theme) => theme.id === id)!;

export interface ProprietesThemeOrganisation {
    ouvert: boolean;
    onBasculer: () => void;
    ouvrir: () => void;
    /** Tells the page this theme's dots (the navigation shows them too). */
    signaler: (id: ThemeOrganisation, modifie: boolean, enErreur: boolean) => void;
}

const CHARGEMENT: Texte = { en: "Loading...", fr: "Chargement..." };

const differe = (a: unknown, b: unknown) => JSON.stringify(a) !== JSON.stringify(b);

/** Reports the dots to the page, and clears them when the theme goes away. */
const useSignaler = (
    id: ThemeOrganisation,
    modifie: boolean,
    enErreur: boolean,
    signaler: ProprietesThemeOrganisation["signaler"],
) => {
    useEffect(() => signaler(id, modifie, enErreur), [id, modifie, enErreur, signaler]);
    useEffect(() => () => signaler(id, false, false), [id, signaler]);
};

/** A draft of some fields of the row, following the row when it is saved. */
const useBrouillonPreferences = <K extends keyof OrganizationPreferences>(preferences: EtatPreferences, cles: readonly K[]) => {
    const extraire = () => Object.fromEntries(cles.map((cle) => [cle, preferences.enregistrees[cle]])) as Pick<OrganizationPreferences, K>;
    const enregistre = extraire();
    const [brouillon, setBrouillon] = useState(enregistre);
    const cleEnregistre = JSON.stringify(enregistre);
    // The row changes when it is read, and when any theme saves it: the fields
    // of this theme follow what the server holds (unchanged by another theme).
    useEffect(() => {
        setBrouillon(JSON.parse(cleEnregistre));
    }, [cleEnregistre]);
    return { enregistre, brouillon, setBrouillon };
};

// --------------------------------------------------------------------------- //
// 1. Organization: test number, timezone
// --------------------------------------------------------------------------- //

const valeurFuseau = (tz: ITimezoneOption | string): string => (typeof tz === "string" ? tz : tz.value);

// Dograh's styles for the timezone picker, copied from their (unused) card.
const stylesFuseau = {
    control: (base: Record<string, unknown>, state: { isFocused: boolean }) => ({
        ...base,
        minHeight: "36px",
        fontSize: "14px",
        backgroundColor: "var(--background)",
        borderColor: state.isFocused ? "var(--ring)" : "var(--border)",
        boxShadow: state.isFocused ? "0 0 0 2px color-mix(in srgb, var(--ring) 20%, transparent)" : "none",
        "&:hover": { borderColor: "var(--border)" },
    }),
    menu: (base: Record<string, unknown>) => ({
        ...base,
        zIndex: 9999,
        backgroundColor: "var(--popover)",
        border: "1px solid var(--border)",
        boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)",
    }),
    menuList: (base: Record<string, unknown>) => ({ ...base, backgroundColor: "var(--popover)", padding: 0 }),
    option: (base: Record<string, unknown>, state: { isFocused: boolean; isSelected: boolean }) => ({
        ...base,
        backgroundColor: state.isSelected || state.isFocused ? "var(--accent)" : "var(--popover)",
        color: "var(--foreground)",
        cursor: "pointer",
        "&:active": { backgroundColor: "var(--accent)" },
    }),
    singleValue: (base: Record<string, unknown>) => ({ ...base, color: "var(--foreground)" }),
    input: (base: Record<string, unknown>) => ({ ...base, color: "var(--foreground)" }),
    placeholder: (base: Record<string, unknown>) => ({ ...base, color: "var(--muted-foreground)" }),
    indicatorSeparator: (base: Record<string, unknown>) => ({ ...base, backgroundColor: "var(--border)" }),
    dropdownIndicator: (base: Record<string, unknown>) => ({
        ...base,
        color: "var(--muted-foreground)",
        "&:hover": { color: "var(--foreground)" },
    }),
};

const PREFERENCES_ENREGISTREES: Texte = { en: "Preferences saved", fr: "Préférences enregistrées" };
const CLES_ORGANISATION = ["test_phone_number", "timezone"] as const;

export const ThemeOrganisationGenerale = ({
    preferences,
    ouvert,
    onBasculer,
    signaler,
}: ProprietesThemeOrganisation & { preferences: EtatPreferences }) => {
    const { t } = useLangue();
    const idFuseau = useId();
    const { enregistre, brouillon, setBrouillon } = useBrouillonPreferences(preferences, CLES_ORGANISATION);
    const modifie = differe(brouillon, enregistre);
    useSignaler("organisation", modifie, false, signaler);

    return (
        <Theme
            id="organisation"
            icone={Settings}
            titre={titre("organisation").titre}
            description={{
                en: "Organization-wide defaults used by testing and scheduling flows.",
                fr: "Réglages communs utilisés par les tests et la planification.",
            }}
            resume={[brouillon.timezone, brouillon.test_phone_number || t({ en: "no test number", fr: "pas de numéro de test" })]}
            ouvert={ouvert}
            onBasculer={onBasculer}
            modifie={modifie}
            erreurs={[]}
            enregistrement={{
                onEnregistrer: () => void preferences.enregistrer(brouillon, t(PREFERENCES_ENREGISTREES)),
                enCours: preferences.enCours,
                actifSansModification: true,
            }}
        >
            {preferences.chargement ? (
                <p className="text-sm text-muted-foreground">{t(CHARGEMENT)}</p>
            ) : (
                <Intertitre id="organisation-general" titre={{ en: "General", fr: "Général" }}>
                    <ChampReglage
                        cle="test_phone_number"
                        idControle="settings-test-phone-number"
                        libelle={{ en: "Test Phone Number", fr: "Numéro de téléphone de test" }}
                    >
                        <Input
                            id="settings-test-phone-number"
                            value={brouillon.test_phone_number || ""}
                            onChange={(event) => setBrouillon((avant) => ({ ...avant, test_phone_number: event.target.value }))}
                            placeholder="+15551234567"
                        />
                    </ChampReglage>
                    <ChampReglage cle="timezone" libelle={{ en: "Timezone", fr: "Fuseau horaire" }}>
                        <TimezoneSelect
                            instanceId={idFuseau}
                            value={brouillon.timezone || "UTC"}
                            onChange={(tz) => setBrouillon((avant) => ({ ...avant, timezone: valeurFuseau(tz) }))}
                            styles={stylesFuseau}
                        />
                    </ChampReglage>
                </Intertitre>
            )}
        </Theme>
    );
};

// --------------------------------------------------------------------------- //
// 2. Business: address, closed-business announcement
// --------------------------------------------------------------------------- //

const ADRESSE: Texte = { en: "Business address", fr: "Adresse de l'entreprise" };
const COMMUNE_A_CHOISIR: Texte = {
    en: "Choose the town for this postal code before saving.",
    fr: "Choisissez la commune de ce code postal avant d'enregistrer.",
};
const LECTURE_ANNONCE: Texte = {
    en: "The saved announcement could not be read: it cannot be saved, or it would be overwritten.",
    fr: "L'annonce enregistrée n'a pas pu être lue : elle ne peut pas être enregistrée, elle serait écrasée.",
};

export const ThemeEtablissementOrganisation = ({
    preferences,
    annonce,
    ouvert,
    onBasculer,
    ouvrir,
    signaler,
}: ProprietesThemeOrganisation & { preferences: EtatPreferences; annonce: EtatAnnonceOuverture }) => {
    const { t } = useLangue();
    const adresseEnregistree = preferences.enregistrees.adresse_etablissement ?? null;
    const [adresse, setAdresse] = useState<AdresseEtablissement | null>(adresseEnregistree);
    const [adresseIncomplete, setAdresseIncomplete] = useState(false);
    const [refusAdresse, setRefusAdresse] = useState<string | null>(null);
    const cleAdresse = JSON.stringify(adresseEnregistree);
    // The address draft follows the stored one whenever it changes on the server.
    useEffect(() => {
        setAdresse(JSON.parse(cleAdresse));
        setAdresseIncomplete(false);
    }, [cleAdresse]);

    const adresseModifiee = adresseIncomplete || differe(adresse, adresseEnregistree);
    const annonceModifiee = differe(annonce.reglages, annonce.enregistre);
    const modifie = adresseModifiee || annonceModifiee;

    const afficher = (cle: string) => {
        ouvrir();
        allerAuReglage(cle);
    };
    const erreurs: ErreurNommee[] = [
        ...(adresseIncomplete
            ? [{ cle: "adresse_etablissement", libelle: t(ADRESSE), message: t(COMMUNE_A_CHOISIR), afficher: () => afficher("adresse_etablissement") }]
            : []),
        // ⛔ Saving the announcement REPLACES it whole: a change typed while the
        // saved one is unread would overwrite it. Untouched, the theme saves
        // the address alone, as the old card allowed.
        ...(!annonce.chargement && !annonce.lu && annonceModifiee
            ? [{ cle: "annonce_fermeture", libelle: t({ en: "Closed-business announcement", fr: "Annonce de fermeture" }), message: t(LECTURE_ANNONCE), afficher: () => afficher("annonce_fermeture") }]
            : []),
    ];
    useSignaler("etablissement", modifie, erreurs.length > 0, signaler);

    const enregistrer = async () => {
        // The parts changed are saved; untouched, every part is saved, as each
        // old card's button did on its own.
        const toutes = !modifie;
        if (adresseModifiee || toutes) {
            const resultat = await preferences.enregistrer({ adresse_etablissement: adresse }, t(PREFERENCES_ENREGISTREES));
            if (resultat.ok) {
                setAdresseIncomplete(false);
                setRefusAdresse(null);
            } else {
                setRefusAdresse(resultat.refusAdresse);
                return;
            }
        }
        if ((annonceModifiee || toutes) && annonce.lu) await annonce.enregistrer(t(ANNONCE_ENREGISTREE));
    };

    const force = annonce.reglages.etat_force ?? null;

    return (
        <Theme
            id="etablissement"
            icone={Building2}
            titre={titre("etablissement").titre}
            description={{
                en: "Business address and the announcement when it is closed.",
                fr: "Adresse de l'entreprise et annonce quand elle est fermée.",
            }}
            resume={[
                adresseEnregistree ? texteAdresse(adresseEnregistree) : t({ en: "No address", fr: "Aucune adresse" }),
                force === null
                    ? t({ en: "State computed from hours", fr: "État calculé depuis les horaires" })
                    : t({ en: "State forced", fr: "État forcé" }),
            ]}
            ouvert={ouvert}
            onBasculer={onBasculer}
            modifie={modifie}
            erreurs={erreurs}
            enregistrement={{
                onEnregistrer: () => void enregistrer(),
                enCours: preferences.enCours || annonce.enregistrement,
                actifSansModification: true,
            }}
        >
            <Intertitre id="etablissement-adresse" titre={{ en: "Address", fr: "Adresse" }}>
                {preferences.chargement ? (
                    <p className="text-sm text-muted-foreground">{t(CHARGEMENT)}</p>
                ) : (
                    <ChampReglage
                        cle="adresse_etablissement"
                        libelle={ADRESSE}
                        aides={[
                            {
                                en: "Helps recognise the towns callers name. Given to agents as {{adresse_etablissement}}; the street is not used to recognise towns.",
                                fr: "Aide à reconnaître les communes citées. Donnée aux agents comme {{adresse_etablissement}} ; la rue ne sert pas à reconnaître les communes.",
                            },
                        ]}
                        disposition="colonne"
                        note={adresseIncomplete ? COMMUNE_A_CHOISIR : undefined}
                    >
                        <ChampAdresseEtablissement
                            id="settings-business-address"
                            enregistree={adresseEnregistree}
                            erreur={refusAdresse}
                            desactive={preferences.enCours}
                            onChange={(valeur, incomplete) => {
                                setAdresse(valeur);
                                setAdresseIncomplete(incomplete);
                                setRefusAdresse(null);
                            }}
                        />
                    </ChampReglage>
                )}
            </Intertitre>

            <Intertitre
                id="etablissement-annonce"
                titre={{ en: "Closed-business announcement", fr: "Annonce de fermeture" }}
                description={{
                    en: "What every agent of this organization says when it picks up while the business is closed or on a break, and the state you can force by hand until a date.",
                    fr: "Ce que disent tous les agents de l'organisation au décroché quand l'entreprise est fermée ou en pause, et l'état que vous pouvez forcer à la main jusqu'à une date.",
                }}
            >
                {annonce.chargement ? (
                    <p className="text-sm text-muted-foreground">{t(CHARGEMENT)}</p>
                ) : (
                    <>
                        <ChampsAnnonceOuverture annonce={annonce} />
                        <EtatLectureAnnonce annonce={annonce} />
                    </>
                )}
            </Intertitre>
        </Theme>
    );
};

// --------------------------------------------------------------------------- //
// 3. Listening: the trade vocabulary, reused as it is (its own buttons)
// --------------------------------------------------------------------------- //

export const ThemeEcouteOrganisation = ({ ouvert, onBasculer }: ProprietesThemeOrganisation) => (
    <Theme
        id="ecoute"
        icone={Ear}
        titre={titre("ecoute").titre}
        description={{
            en: "The names and words of this business: recognised before the model reads them, listened for by the transcription, and pronounced the way you write them.",
            fr: "Les noms et les mots de l'entreprise : reconnus avant que le modèle ne les lise, écoutés par la transcription, et prononcés comme vous les écrivez.",
        }}
        resume={[]}
        ouvert={ouvert}
        onBasculer={onBasculer}
        modifie={false}
        erreurs={[]}
    >
        <Intertitre id="ecoute-lexique" titre={{ en: "Trade vocabulary", fr: "Lexique métier" }}>
            <SectionLexiqueMetier />
        </Intertitre>
    </Theme>
);

// --------------------------------------------------------------------------- //
// 4. Integrations: external PBX, disposition mapping
// --------------------------------------------------------------------------- //

const CLES_INTEGRATIONS = ["external_pbx_integrations_enabled", "disposition_mapping_enabled"] as const;

export const ThemeIntegrations = ({
    preferences,
    ouvert,
    onBasculer,
    signaler,
}: ProprietesThemeOrganisation & { preferences: EtatPreferences }) => {
    const { t } = useLangue();
    const [correspondanceOuverte, setCorrespondanceOuverte] = useState(false);
    const { enregistre, brouillon, setBrouillon } = useBrouillonPreferences(preferences, CLES_INTEGRATIONS);
    const modifie = differe(brouillon, enregistre);
    useSignaler("integrations", modifie, false, signaler);

    const correspondance = preferences.enregistrees.disposition_mapping ?? {};
    const nombre = Object.keys(correspondance).length;
    const texteNombre =
        nombre === 0
            ? t({ en: "No overrides yet", fr: "Aucune correspondance" })
            : t({
                  en: `${nombre} disposition${nombre === 1 ? "" : "s"} mapped`,
                  fr: `${nombre} issue${nombre === 1 ? "" : "s"} reliée${nombre === 1 ? "" : "s"}`,
              });

    return (
        <Theme
            id="integrations"
            icone={Plug}
            titre={titre("integrations").titre}
            description={{
                en: "External phone system and disposition codes sent to your tools.",
                fr: "Standard externe et codes d'issue envoyés vers vos outils.",
            }}
            resume={[
                brouillon.external_pbx_integrations_enabled
                    ? t({ en: "External PBX on", fr: "Standard externe actif" })
                    : t({ en: "No external PBX", fr: "Pas de standard externe" }),
                brouillon.disposition_mapping_enabled ? t({ en: "Custom disposition codes", fr: "Codes d'issue personnalisés" }) : null,
            ]}
            ouvert={ouvert}
            onBasculer={onBasculer}
            modifie={modifie}
            erreurs={[]}
            enregistrement={{
                onEnregistrer: () => void preferences.enregistrer(brouillon, t(PREFERENCES_ENREGISTREES)),
                enCours: preferences.enCours,
                actifSansModification: true,
            }}
        >
            {preferences.chargement ? (
                <p className="text-sm text-muted-foreground">{t(CHARGEMENT)}</p>
            ) : (
                <>
                    <Intertitre id="integrations-standard" titre={{ en: "External PBX", fr: "Standard externe" }}>
                        <ChampReglage
                            cle="external_pbx_integrations_enabled"
                            idControle="settings-external-pbx-integrations"
                            libelle={{ en: "External PBX integrations", fr: "Intégrations de standard externe" }}
                            aides={[
                                {
                                    en: "Show and enable advanced external-PBX configuration for Asterisk, transfer tools, and workflows. Existing configuration is preserved when this is disabled.",
                                    fr: "Affiche et active la configuration avancée de standard externe pour Asterisk, les outils de transfert et les agents. La configuration existante est conservée quand c'est éteint.",
                                },
                            ]}
                        >
                            <Switch
                                id="settings-external-pbx-integrations"
                                checked={brouillon.external_pbx_integrations_enabled ?? false}
                                onCheckedChange={(checked) =>
                                    setBrouillon((avant) => ({ ...avant, external_pbx_integrations_enabled: checked }))
                                }
                            />
                        </ChampReglage>
                    </Intertitre>

                    <Intertitre id="integrations-correspondance" titre={{ en: "Disposition mapping", fr: "Correspondance des issues" }}>
                        <ChampReglage
                            cle="disposition_mapping_enabled"
                            idControle="settings-disposition-mapping"
                            libelle={{ en: "Disposition mapping", fr: "Utiliser vos propres codes d'issue" }}
                            aides={[
                                {
                                    en: "Report call outcomes using your own disposition codes instead of Dograh's. Applies to webhooks, run filters, reports, and external PBX write-backs. Configuration is preserved when this is disabled.",
                                    fr: "Rapporte les issues d'appel avec vos codes au lieu de ceux de Dograh. S'applique aux webhooks, aux filtres, aux rapports et aux écritures vers le standard externe. La configuration est conservée quand c'est éteint.",
                                },
                            ]}
                        >
                            <Switch
                                id="settings-disposition-mapping"
                                checked={brouillon.disposition_mapping_enabled ?? false}
                                onCheckedChange={(checked) =>
                                    setBrouillon((avant) => ({ ...avant, disposition_mapping_enabled: checked }))
                                }
                            />
                        </ChampReglage>
                        {brouillon.disposition_mapping_enabled && (
                            <div className="flex items-center gap-3" id="reglage-disposition_mapping" data-reglage="disposition_mapping">
                                <Button type="button" variant="outline" size="sm" onClick={() => setCorrespondanceOuverte(true)}>
                                    <SlidersHorizontal className="mr-2 h-3.5 w-3.5" />
                                    {t({ en: "Configure mapping", fr: "Configurer la correspondance" })}
                                </Button>
                                <span className="text-xs text-muted-foreground">{texteNombre}</span>
                                <code data-cle-technique className="text-[11px] text-muted-foreground">
                                    disposition_mapping
                                </code>
                            </div>
                        )}
                    </Intertitre>

                    {/* The mapping list saves at once, as it did: the row as stored,
                        this theme's switches as typed, the new list. */}
                    <DispositionMappingDialog
                        open={correspondanceOuverte}
                        onOpenChange={setCorrespondanceOuverte}
                        mapping={correspondance}
                        onSave={async (disposition_mapping) =>
                            (
                                await preferences.enregistrer(
                                    { ...brouillon, disposition_mapping },
                                    t({ en: "Disposition mapping saved", fr: "Correspondance des issues enregistrée" }),
                                )
                            ).ok
                        }
                    />
                </>
            )}
        </Theme>
    );
};

// --------------------------------------------------------------------------- //
// 5. Developers: MCP server, telemetry, reused as they are (their own buttons)
// --------------------------------------------------------------------------- //

const EnSavoirPlus = ({ href }: { href: string }) => {
    const { t } = useLangue();
    return (
        <a href={href} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 underline">
            {t({ en: "Learn more", fr: "En savoir plus" })} <ExternalLink className="h-3 w-3" />
        </a>
    );
};

export const ThemeDeveloppeurs = ({ ouvert, onBasculer }: ProprietesThemeOrganisation) => {
    const { t } = useLangue();
    return (
        <Theme
            id="developpeurs"
            icone={Code}
            titre={titre("developpeurs").titre}
            description={{ en: "MCP server and call tracing (Langfuse).", fr: "Serveur MCP et traçage des appels (Langfuse)." }}
            resume={[]}
            ouvert={ouvert}
            onBasculer={onBasculer}
            modifie={false}
            erreurs={[]}
        >
            <Intertitre id="developpeurs-mcp" titre={{ en: "MCP Server", fr: "Serveur MCP" }}>
                <p className="text-sm text-muted-foreground">
                    {t({
                        en: "Let AI agents access your Dograh workspace and documentation via the Model Context Protocol.",
                        fr: "Permet à des agents IA d'accéder à votre espace Dograh et à sa documentation par le protocole MCP.",
                    })}{" "}
                    <EnSavoirPlus href="https://docs.dograh.com/integrations/mcp" />
                </p>
                <MCPSection />
            </Intertitre>
            <Intertitre id="developpeurs-telemetrie" titre={{ en: "Telemetry", fr: "Traçage des appels (Langfuse)" }}>
                <p className="text-sm text-muted-foreground">
                    {t({
                        en: "Configure Langfuse tracing for your voice agent calls.",
                        fr: "Configurez le traçage Langfuse des appels de vos agents vocaux.",
                    })}{" "}
                    <EnSavoirPlus href="https://docs.dograh.com/configurations/tracing" />
                </p>
                <TelemetrySection />
            </Intertitre>
        </Theme>
    );
};
