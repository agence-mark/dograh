/**
 * [.mark] The Platform Settings page in 5 themes, rendered (chantier
 * reorganisation-ecran-reglages, step 5).
 *
 * What the payload references do not ask:
 *
 *   - every setting the inventory says is on screen IS found in its theme;
 *   - a postal code without its town is NAMED and blocks the Business theme (E7);
 *   - an announcement that could not be read is never overwritten, and does
 *     not stop the address from being saved;
 *   - a theme never sends what is being typed in another theme;
 *   - the page speaks French until the user chooses (D12).
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { INVENTAIRE_ANNONCE, INVENTAIRE_PREFERENCES } from "./inventaire-organisation";

const PREFERENCES = {
    test_phone_number: "+33344000000",
    timezone: "Europe/Paris",
    external_pbx_integrations_enabled: false,
    disposition_mapping_enabled: true,
    disposition_mapping: { voicemail: "AM" },
    adresse_etablissement: { code_postal: "60000", code_insee: "60057", commune: "Beauvais", voie: "4 rue des Artisans" },
};
const ANNONCE = {
    format: "annonce-ouverture-mark",
    version: 1,
    annonce_fermeture: "Nous sommes fermés[, nous rouvrons {reouverture}].",
    annonce_pause: "Nous sommes en pause[, nous revenons {reouverture}].",
    etat_force: "FERME",
    etat_force_jusqu_a: null,
};

const m = vi.hoisted(() => ({
    getPreferences: vi.fn(),
    getAnnonce: vi.fn(),
    savePreferences: vi.fn(),
    saveAnnonce: vi.fn(),
    getReglagesFenetreDuRun: vi.fn(),
    saveReglagesFenetreDuRun: vi.fn(),
    saveChoixTraducteurs: vi.fn(),
    lien: vi.fn(),
}));

// l-agent-collegue, L4: the calendar software of the hub (theme « Integrations »).
const TRADUCTEURS = [
    { systeme: "google_agenda", libelle: "Google Agenda", domaine: "agenda", integration: "google-calendar",
      reference_agenda: { en: "Calendar ID", fr: "Identifiant de l'agenda" }, operations: {} },
    { systeme: "outlook_agenda", libelle: "Microsoft Outlook (agenda)", domaine: "agenda", integration: "outlook",
      reference_agenda: { en: "Mailbox", fr: "Boîte aux lettres" }, operations: {} },
];

vi.mock("@/client/sdk.gen", async (importOriginal) => (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
    getPreferencesApiV1OrganizationsPreferencesGet: m.getPreferences,
    savePreferencesApiV1OrganizationsPreferencesPut: m.savePreferences,
    getAnnonceOuvertureApiV1OrganizationsAnnonceOuvertureGet: m.getAnnonce,
    saveAnnonceOuvertureApiV1OrganizationsAnnonceOuverturePut: m.saveAnnonce,
    getCommunesDuCodePostalApiV1OrganizationsCommunesGet: () =>
        Promise.resolve({ data: [{ code_insee: "60057", nom: "Beauvais" }, { code_insee: "60001", nom: "Autre" }] }),
    getLexiqueApiV1OrganizationsLexiqueGet: () => Promise.resolve({ data: { format: "lexique-mark", version: 1, termes: [] } }),
    saveLexiqueApiV1OrganizationsLexiquePut: vi.fn(),
    importLexiqueApiV1OrganizationsLexiqueImportPost: vi.fn(),
    getReglagesFenetreDuRunApiV1OrganizationsFenetreDuRunGet: m.getReglagesFenetreDuRun,
    saveReglagesFenetreDuRunApiV1OrganizationsFenetreDuRunPut: m.saveReglagesFenetreDuRun,
    getEtablissementsApiV1OrganizationsEtablissementsGet: () =>
        Promise.resolve({ data: { format: "etablissements-mark", version: 1, etablissements: [] } }),
    getNumerosApiV1OrganizationsEtablissementsNumerosGet: () => Promise.resolve({ data: [] }),
    saveEtablissementsApiV1OrganizationsEtablissementsPut: vi.fn(),
    getPhrasesApiV1OrganizationsPhrasesGet: () => Promise.resolve({ data: { format: "phrases-mark", version: 1, phrases: [] } }),
    savePhrasesApiV1OrganizationsPhrasesPut: vi.fn(),
    // [.mark] L3: the « Client data » theme reads its state; no database attached.
    getBaseClientApiV1OrganizationsBaseClientGet: () =>
        Promise.resolve({ data: { serveur_configure: true, version_attendue: 3, nom_base: null, joignable: false, refus: [], conservation: [] } }),
    putBaseClientApiV1OrganizationsBaseClientPut: vi.fn(),
    postCreerApiV1OrganizationsBaseClientCreerPost: vi.fn(),
    postMettreANiveauApiV1OrganizationsBaseClientMettreANiveauPost: vi.fn(),
    postResynchroniserApiV1OrganizationsBaseClientResynchroniserPost: vi.fn(),
    putConservationApiV1OrganizationsBaseClientConservationPut: vi.fn(),
    getEquipeApiV1OrganizationsEquipeGet: vi.fn(),
    putEquipeApiV1OrganizationsEquipePut: vi.fn(),
    getTraducteursApiV1ConnecteursTraducteursGet: () => Promise.resolve({ data: TRADUCTEURS }),
    getChoixTraducteursApiV1ConnecteursTraducteursChoixGet: () => Promise.resolve({ data: { agenda: null } }),
    putChoixTraducteursApiV1ConnecteursTraducteursChoixPut: m.saveChoixTraducteurs,
    getConnexionsApiV1ConnecteursConnexionsGet: () =>
        Promise.resolve({ data: { nango_configure: true, connexions: [{ integration: "google-calendar", connection_id: "cx" }] } }),
    getCatalogueApiV1ConnecteursCatalogueGet: () => Promise.resolve({ data: [] }),
    postLienApiV1ConnecteursLienPost: m.lien,
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/context/UserConfigContext", () => ({ useUserConfig: () => ({ refreshConfig: () => Promise.resolve() }) }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("react-timezone-select", () => ({
    default: ({ value, onChange }: { value: string; onChange: (v: string) => void }) => (
        <select id="settings-timezone" value={value} onChange={(e) => onChange(e.target.value)}>
            <option value="Europe/Paris">Europe/Paris</option>
            <option value="America/New_York">America/New_York</option>
        </select>
    ),
}));
vi.mock("@/components/DispositionMappingDialog", () => ({ DispositionMappingDialog: () => null }));
vi.mock("@/components/ui/dialog", () => ({
    Dialog: ({ open, children }: { open: boolean; children: ReactNode }) => (open ? <div>{children}</div> : null),
    DialogContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogDescription: ({ children }: { children: ReactNode }) => <p>{children}</p>,
    DialogFooter: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogHeader: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
}));
vi.mock("@/components/MCPSection", () => ({ MCPSection: () => <div data-testid="mcp" /> }));
vi.mock("@/components/TelemetrySection", () => ({ TelemetrySection: () => <div data-testid="telemetrie" /> }));
vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });

const { default: SettingsPage } = await import("@/app/settings/page");

const reinitialiser = () => {
    m.getPreferences.mockReset().mockImplementation(() => Promise.resolve({ data: structuredClone(PREFERENCES) }));
    m.getAnnonce.mockReset().mockImplementation(() => Promise.resolve({ data: structuredClone(ANNONCE) }));
    m.savePreferences.mockReset().mockImplementation(async ({ body }) => ({ data: body }));
    m.saveAnnonce.mockReset().mockImplementation(async ({ body }) => ({ data: body }));
    m.getReglagesFenetreDuRun.mockReset().mockImplementation(() =>
        Promise.resolve({
            data: {
                format: "fenetre-du-run-mark",
                version: 1,
                devise: "USD",
                lignes: [{ brique: "stt", modele: "flux-general-multi", par_minute: 0.0077, date_du_tarif: "2026-10-01" }],
            },
        }),
    );
    m.saveReglagesFenetreDuRun.mockReset().mockImplementation(async ({ body }) => ({ data: body }));
};
reinitialiser();
afterEach(() => {
    cleanup();
    reinitialiser();
    window.localStorage.clear();
});

const ouvrirLaPage = async (enveloppe?: (n: ReactNode) => ReactNode) => {
    render(<>{enveloppe ? enveloppe(<SettingsPage />) : <SettingsPage />}</>);
    await waitFor(() => expect(document.querySelectorAll("[data-theme]").length).toBe(9));
};

const ouvrirLeTheme = async (id: string) => {
    const entete = document.querySelector(`[data-theme="${id}"] > button[aria-expanded]`) as HTMLButtonElement;
    if (entete.getAttribute("aria-expanded") === "false") fireEvent.click(entete);
    await waitFor(() => {
        if (/Loading|Chargement/.test(document.getElementById(id)?.textContent ?? "")) throw new Error("still loading");
    });
    return document.getElementById(id) as HTMLElement;
};

const bouton = (nom: string) => screen.getByRole("button", { name: nom }) as HTMLButtonElement;

describe("[.mark] the Platform Settings page in themes", () => {
    it("draws every setting the inventory puts on screen, in its theme", async () => {
        await ouvrirLaPage();
        for (const [cle, entree] of Object.entries({ ...INVENTAIRE_PREFERENCES, ...INVENTAIRE_ANNONCE })) {
            if ("horsEcran" in entree) continue;
            const theme = await ouvrirLeTheme(entree.theme);
            if (cle === "etat_force_jusqu_a") {
                // Shown once a state is forced: it is, in the stored settings.
                expect(document.getElementById("etat_force")).not.toBeNull();
            }
            await waitFor(() => expect(theme.querySelector(`[data-reglage="${cle}"]`), `${cle} in ${entree.theme}`).not.toBeNull());
        }
        // Reused as they are, in their themes.
        expect((await ouvrirLeTheme("ecoute")).textContent).toMatch(/open vocabulary/i);
        const developpeurs = await ouvrirLeTheme("developpeurs");
        expect(developpeurs.querySelector('[data-testid="mcp"]')).not.toBeNull();
        expect(developpeurs.querySelector('[data-testid="telemetrie"]')).not.toBeNull();
    });

    it("[l-agent-travaille] the Establishments theme lists them and opens their modal (E4)", async () => {
        await ouvrirLaPage();
        const theme = await ouvrirLeTheme("etablissement");
        expect(theme.querySelector('[data-reglage="etablissements"]')).not.toBeNull();
        expect(theme.textContent).toContain("Establishments of the organization");
        fireEvent.click(screen.getByTestId("ouvrir-etablissements"));
        await waitFor(() => expect(screen.getByTestId("ajouter-etablissement")).toBeTruthy());
    });

    it("⛔ keeps the save asleep while the preferences are read (review of 26/09, M1)", async () => {
        // A PUT sent from the empty defaults would clear the whole row.
        m.getPreferences.mockReset().mockImplementation(() => new Promise(() => undefined));
        await ouvrirLaPage();
        for (const [theme, titre] of [["organisation", "Organization"], ["integrations", "Integrations"], ["etablissement", "Establishments"]]) {
            const entete = document.querySelector(`[data-theme="${theme}"] > button[aria-expanded]`) as HTMLButtonElement;
            fireEvent.click(entete);
            expect(bouton(`Save ${titre}`).disabled, theme).toBe(true);
        }
        expect(m.savePreferences).not.toHaveBeenCalled();
    });

    it("names a postal code without its town and blocks the Business theme", async () => {
        await ouvrirLaPage();
        await ouvrirLeTheme("etablissement");
        fireEvent.change(document.getElementById("settings-business-address-code-postal")!, { target: { value: "60300" } });
        const alerte = await screen.findByRole("alert");
        expect(alerte.textContent).toContain("adresse_etablissement");
        expect(alerte.textContent).toContain("Choose the town for this postal code before saving.");
        expect(bouton("Save Establishments").disabled).toBe(true);
        expect(document.querySelector('[data-navigation="etablissement"] [data-pastille="erreur"]')).not.toBeNull();
    });

    it("never overwrites an announcement it could not read, and still saves the address", async () => {
        m.getAnnonce.mockReset().mockResolvedValue({ error: { detail: "boom" } });
        await ouvrirLaPage();
        await ouvrirLeTheme("etablissement");
        expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();

        // Untouched: the address alone is saved.
        fireEvent.click(bouton("Save Establishments"));
        await waitFor(() => expect(m.savePreferences).toHaveBeenCalledTimes(1));
        expect(m.saveAnnonce).not.toHaveBeenCalled();

        // A sentence typed over the unread one: named, and nothing saved.
        fireEvent.change(document.getElementById("annonce_fermeture")!, { target: { value: "Fermé." } });
        await waitFor(() => expect(bouton("Save Establishments").disabled).toBe(true));
        expect(document.querySelector('[data-erreur="annonce_fermeture"]')).not.toBeNull();
        expect(m.saveAnnonce).not.toHaveBeenCalled();
    });

    it("saves only its own fields: what is typed in another theme stays a draft", async () => {
        await ouvrirLaPage();
        await ouvrirLeTheme("organisation");
        fireEvent.change(document.getElementById("settings-test-phone-number")!, { target: { value: "+33699999999" } });
        await ouvrirLeTheme("integrations");
        fireEvent.click(document.getElementById("settings-external-pbx-integrations")!);
        fireEvent.click(bouton("Save Integrations"));

        await waitFor(() => expect(m.savePreferences).toHaveBeenCalledTimes(1));
        const corps = m.savePreferences.mock.calls[0][0].body;
        expect(corps.external_pbx_integrations_enabled).toBe(true);
        expect(corps.test_phone_number).toBe("+33344000000");
        // The number typed in Organization is still there, still to save.
        expect((document.getElementById("settings-test-phone-number") as HTMLInputElement).value).toBe("+33699999999");
        expect(document.querySelector('[data-theme="organisation"] [data-pastille="modifie"]')).not.toBeNull();
        await waitFor(() => expect(document.querySelector('[data-theme="integrations"] [data-pastille="modifie"]')).toBeNull());
    });

    it("speaks French until the user chooses", async () => {
        await ouvrirLaPage((page) => <FournisseurLangue>{page}</FournisseurLangue>);
        expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Paramètres de la plateforme");
        expect(document.querySelector('[data-theme="etablissement"]')?.textContent).toContain("Établissements");
        const theme = await ouvrirLeTheme("etablissement");
        expect(theme.textContent).toContain("Quand l'entreprise est fermée");
        expect(bouton("Enregistrer Établissements")).toBeTruthy();
    });
});


describe("[.mark] the price table (langwatch-et-fenetre-du-run, L5 and L18)", () => {
    it("is in the Organization theme, opens in a modal, and sends exactly the table typed", async () => {
        await ouvrirLaPage();
        const theme = await ouvrirLeTheme("organisation");
        expect(theme.querySelector('[data-reglage="fenetre_du_run"]')).not.toBeNull();
        fireEvent.click(screen.getByRole("button", { name: "Edit prices and thresholds…" }));
        await waitFor(() => expect(screen.getAllByTestId("ligne-de-prix")).toHaveLength(1));
        // A new line is faulty until its model and prices are typed: Save stays asleep, the fault is named.
        fireEvent.click(screen.getByRole("button", { name: "Add a line" }));
        expect(screen.getByTestId("fautes-fenetre-du-run").textContent).toContain("Line 2: model missing");
        expect(bouton("Save").disabled).toBe(true);
        const nouvelle = screen.getAllByTestId("ligne-de-prix")[1];
        fireEvent.change(nouvelle.querySelector('input[aria-label="Model"]') as HTMLInputElement, {
            target: { value: " mistral-large-2512 " },
        });
        fireEvent.change(nouvelle.querySelector('input[aria-label="Rate date"]') as HTMLInputElement, {
            target: { value: "2026-10-01" },
        });
        for (const [libelle, valeur] of [["Input / 1M tokens", "2"], ["Output / 1M tokens", "6"]]) {
            fireEvent.change(nouvelle.querySelector(`input[aria-label="${libelle}"]`) as HTMLInputElement, {
                target: { value: valeur },
            });
        }
        await waitFor(() => expect(bouton("Save").disabled).toBe(false));
        fireEvent.click(bouton("Save"));
        await waitFor(() => expect(m.saveReglagesFenetreDuRun).toHaveBeenCalledTimes(1));
        expect(m.saveReglagesFenetreDuRun.mock.calls[0][0].body).toEqual({
            format: "fenetre-du-run-mark",
            version: 1,
            devise: "USD",
            lignes: [
                { brique: "stt", modele: "flux-general-multi", par_minute: 0.0077, date_du_tarif: "2026-10-01" },
                {
                    brique: "llm",
                    modele: "mistral-large-2512",
                    entree_par_million: 2,
                    sortie_par_million: 6,
                    date_du_tarif: "2026-10-01",
                },
            ],
            seuils: { silence_apres_outil_s: 5, tour_lent_s: 3 },
        });
        // The theme's own save is untouched by the modal (E4: the table saves itself).
        expect(m.savePreferences).not.toHaveBeenCalled();
    });

    it("drops a price of another component when the component of a line is changed", async () => {
        await ouvrirLaPage();
        await ouvrirLeTheme("organisation");
        fireEvent.click(screen.getByRole("button", { name: "Edit prices and thresholds…" }));
        await waitFor(() => expect(screen.getAllByTestId("ligne-de-prix")).toHaveLength(1));
        const ligne = screen.getAllByTestId("ligne-de-prix")[0];
        fireEvent.change(ligne.querySelector('select[aria-label="Component"]') as HTMLSelectElement, { target: { value: "tts" } });
        fireEvent.change(ligne.querySelector('input[aria-label="Per 1M characters"]') as HTMLInputElement, {
            target: { value: "30" },
        });
        await waitFor(() => expect(bouton("Save").disabled).toBe(false));
        fireEvent.click(bouton("Save"));
        await waitFor(() => expect(m.saveReglagesFenetreDuRun).toHaveBeenCalledTimes(1));
        expect(m.saveReglagesFenetreDuRun.mock.calls[0][0].body.lignes).toEqual([
            { brique: "tts", modele: "flux-general-multi", par_million_caracteres: 30, date_du_tarif: "2026-10-01" },
        ]);
    });
});


describe("[.mark] the incident thresholds (L6, L18)", () => {
    it("reads the saved thresholds, refuses one out of bounds, and sends the one typed", async () => {
        m.getReglagesFenetreDuRun.mockImplementation(() =>
            Promise.resolve({
                data: {
                    format: "fenetre-du-run-mark",
                    version: 1,
                    devise: "EUR",
                    lignes: [],
                    seuils: { silence_apres_outil_s: 4, tour_lent_s: 3 },
                },
            }),
        );
        await ouvrirLaPage();
        await ouvrirLeTheme("organisation");
        fireEvent.click(screen.getByRole("button", { name: "Edit prices and thresholds…" }));
        const silence = (await screen.findByLabelText(
            "Silence after a tool result that makes an incident",
        )) as HTMLInputElement;
        await waitFor(() => expect(silence.value).toBe("4"));
        fireEvent.change(silence, { target: { value: "0.5" } });
        expect(screen.getByTestId("fautes-fenetre-du-run").textContent).toContain("between 1 and 60 s");
        expect(bouton("Save").disabled).toBe(true);
        fireEvent.change(silence, { target: { value: "6" } });
        await waitFor(() => expect(bouton("Save").disabled).toBe(false));
        fireEvent.click(bouton("Save"));
        await waitFor(() => expect(m.saveReglagesFenetreDuRun).toHaveBeenCalledTimes(1));
        expect(m.saveReglagesFenetreDuRun.mock.calls[0][0].body).toEqual({
            format: "fenetre-du-run-mark",
            version: 1,
            devise: "EUR",
            lignes: [],
            seuils: { silence_apres_outil_s: 6, tour_lent_s: 3 },
        });
    });
});


describe("[.mark] l-agent-collegue L4: the calendar software in « Integrations »", () => {
    it("offers the translators, shows the connection of the one chosen and saves exactly it", async () => {
        m.saveChoixTraducteurs.mockReset().mockImplementation(async ({ body }) => ({ data: body }));
        m.lien.mockReset().mockResolvedValue({ data: { lien: "https://connect.example.org/o", expire_le: null } });
        await ouvrirLaPage();
        const theme = await ouvrirLeTheme("integrations");
        const menu = (await waitFor(() => {
            const el = theme.querySelector("#traducteur-agenda");
            if (!el) throw new Error("menu not drawn");
            return el;
        })) as HTMLSelectElement;
        expect(theme.querySelector('[data-reglage="agenda"]')).not.toBeNull();
        expect([...menu.options].map((o) => o.value)).toEqual(["", "google_agenda", "outlook_agenda"]);
        const enregistrer = screen.getByTestId("enregistrer-traducteur") as HTMLButtonElement;
        expect(enregistrer.disabled).toBe(true); // nothing changed
        fireEvent.change(menu, { target: { value: "outlook_agenda" } });
        expect(screen.getByTestId("etat-traducteur").textContent).toMatch(/Not connected/);
        fireEvent.click(screen.getByRole("button", { name: "Authorization link for the client" }));
        await waitFor(() => expect(m.lien).toHaveBeenCalledWith({ body: { connecteurs: ["outlook_agenda"] } }));
        fireEvent.change(menu, { target: { value: "google_agenda" } });
        expect(screen.getByTestId("etat-traducteur").textContent).toMatch(/Connected/);
        fireEvent.click(enregistrer);
        await waitFor(() => expect(m.saveChoixTraducteurs).toHaveBeenCalledWith({ body: { agenda: "google_agenda" } }));
        // Nothing of the theme's own row is sent by this block (it acts at once, E6).
        expect(m.savePreferences).not.toHaveBeenCalled();
    });
});
