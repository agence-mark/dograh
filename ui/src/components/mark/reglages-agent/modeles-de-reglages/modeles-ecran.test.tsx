/**
 * [.mark] Les modeles de reglages, rendus (cloture-code-avant-migration, lot 5 ; plan modeles-de-reglages).
 *
 * | Test | La garantie |
 * |---|---|
 * | liste | chaque modele montre son nom, sa date, son origine, ses sections et son nombre de reglages ; la mention de l'agent |
 * | creer | le nom et l'agent partent au serveur ; sans nom, ou page non enregistree, le bouton est ferme et le dit (M11) |
 * | appliquer | toutes les sections du modele sont cochees d'office (M2) ; l'apercu a blanc nomme les fournisseurs sans cle (M3) ; decocher relit l'apercu ; la charge utile part avec les sections cochees ; la page se recharge |
 * | renommer, supprimer | le nom part ; la suppression se confirme |
 * | importer, exporter | le fichier part tel quel ; un refus du serveur est montre avec le nom du reglage |
 * | modale | centree, a en-tete fixe, jamais un panneau lateral ; textes en deux langues |
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../../langue/langue";
import { BoutonModeles, TITRES_DES_SECTIONS } from "./ModaleModeles";

const m = vi.hoisted(() => {
    const etat = {
        liste: { modeles: [] as unknown[], sections: [] as string[] },
        mention: null as unknown,
        apercu: { ecrit: false, sections: [], posees: [], retirees: [], non_appliquees: [], fournisseurs_sans_cle: [] } as Record<string, unknown>,
        refusImport: null as unknown,
        appels: [] as Array<{ nom: string; options: unknown }>,
        enregistrer: (nom: string, reponse: (options: unknown) => unknown) =>
            vi.fn(async (options: unknown) => {
                etat.appels.push({ nom, options });
                return reponse(options);
            }),
    };
    return etat;
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/client/sdk.gen", async (importOriginal) => (await import("../../sdk-factice")).sdkFactice(await importOriginal(), {
    listerLesModelesApiV1OrganizationsModelesDeReglagesGet: m.enregistrer("lister", () => ({ data: m.liste })),
    mentionDeLagentApiV1OrganizationsModelesDeReglagesAgentWorkflowIdGet: m.enregistrer("mention", () => ({ data: { mention: m.mention } })),
    creerUnModeleApiV1OrganizationsModelesDeReglagesPost: m.enregistrer("creer", () => ({ data: {} })),
    importerUnModeleApiV1OrganizationsModelesDeReglagesImportPost: m.enregistrer("importer", () =>
        m.refusImport ? { error: m.refusImport } : { data: {} },
    ),
    renommerUnModeleApiV1OrganizationsModelesDeReglagesModeleIdPatch: m.enregistrer("renommer", () => ({ data: {} })),
    supprimerUnModeleApiV1OrganizationsModelesDeReglagesModeleIdDelete: m.enregistrer("supprimer", () => ({ data: undefined })),
    exporterUnModeleApiV1OrganizationsModelesDeReglagesModeleIdExportGet: m.enregistrer("exporter", () => ({
        data: { format: "modele-de-reglages-mark", version_du_format: 1, nom: "Reference", valeurs: { turn_start_min_words: 4 } },
    })),
    appliquerUnModeleApiV1OrganizationsModelesDeReglagesModeleIdAppliquerPost: m.enregistrer("appliquer", (options) => {
        const corps = (options as { body: { a_blanc: boolean } }).body;
        return { data: { ...m.apercu, ecrit: !corps.a_blanc } };
    }),
}));

const SECTIONS = Object.keys(TITRES_DES_SECTIONS);
const MODELE = {
    id: "abc123",
    nom: "Reference",
    cree_le: "2026-10-22T10:00:00Z",
    origine: { workflow_id: 3, agent_nom: "Agent de test", version_number: 4, version_status: "published" },
    sections: ["briques", "tour", "voix"],
    nombre_de_reglages: 14,
};

const appelsDe = (nom: string) => m.appels.filter((a) => a.nom === nom).map((a) => a.options as Record<string, unknown>);

const ouvrirLaModale = async (props: { modifie?: boolean; apres?: () => void } = {}) => {
    render(
        <FournisseurLangue>
            <BoutonModeles workflowId={7} modifie={props.modifie ?? false} apresApplication={props.apres ?? (() => {})} />
        </FournisseurLangue>,
    );
    fireEvent.click(document.querySelector("[data-bouton-modeles]") as HTMLElement);
    await waitFor(() => expect(document.querySelector('[data-modale-phrase="modeles-de-reglages"]')).not.toBeNull());
};

beforeEach(() => {
    m.liste = { modeles: [MODELE], sections: SECTIONS };
    m.mention = null;
    m.apercu = { ecrit: false, sections: [], posees: ["turn_start_min_words", "vad_stop_secs"], retirees: ["relance_apres_outil"], non_appliquees: [], fournisseurs_sans_cle: [] };
    m.refusImport = null;
    m.appels = [];
    window.localStorage.setItem("mark.langue", "en");
});
afterEach(() => {
    cleanup();
    window.localStorage.clear();
});

describe("[.mark] settings templates on screen", () => {
    it("every section of the screen has a title in both languages, and the server's sections are all named", () => {
        expect(SECTIONS).toEqual(["agent", "briques", "ecoute", "modules", "tour", "voix", "rythme", "donnees", "etablissement"]);
        for (const titre of Object.values(TITRES_DES_SECTIONS)) {
            expect(titre.en.trim()).not.toBe("");
            expect(titre.fr.trim()).not.toBe("");
        }
    });

    it("sits in the fixed header's button and opens a CENTRED modal, never a side panel", async () => {
        await ouvrirLaModale();
        const modale = document.querySelector('[data-modale-phrase="modeles-de-reglages"]') as HTMLElement;
        expect(modale.getAttribute("role")).toBe("dialog");
        expect(modale.className).toContain("overflow-hidden");
        expect(modale.className).not.toMatch(/\b(right-0|inset-y-0|slide-in-from-right)\b/);
        expect(document.querySelector("[data-notice-modeles]")).not.toBeNull();
    });

    it("lists each template with its name, date, origin, sections and number of settings, and the agent's mention", async () => {
        m.mention = { modele_id: "abc123", nom: "Reference", applique_le: "2026-10-23T09:00:00Z", sections: ["tour"] };
        await ouvrirLaModale();
        const carte = await waitFor(() => {
            const c = document.querySelector('[data-modele="abc123"]') as HTMLElement;
            expect(c).not.toBeNull();
            return c;
        });
        expect(carte.textContent).toContain("Reference");
        expect(carte.textContent).toContain("Agent de test");
        expect(carte.textContent).toContain("v4");
        expect(carte.textContent).toContain("published");
        expect(carte.textContent).toContain("14 settings");
        expect(carte.textContent).toContain("Services");
        expect(carte.textContent).toContain("Turn taking");
        await waitFor(() => expect(document.querySelector("[data-mention-modele]")?.textContent).toContain("Reference"));
        expect(document.querySelector("[data-mention-modele]")?.textContent).toContain("Turn taking");
    });

    it("says there is no template yet, and speaks French by default", async () => {
        m.liste = { modeles: [], sections: SECTIONS };
        window.localStorage.removeItem("mark.langue");
        await ouvrirLaModale();
        await waitFor(() => expect(document.querySelector("[data-aucun-modele]")?.textContent).toBe("Aucun modèle pour l'instant."));
        expect(screen.getByText("Modèles de réglages", { selector: '[data-slot="dialog-title"]' })).toBeTruthy();
    });

    it("creates a template from the agent's active settings: the name and the agent leave", async () => {
        await ouvrirLaModale();
        const bouton = document.querySelector("[data-creer-modele]") as HTMLButtonElement;
        expect(bouton.disabled, "no name, no gesture").toBe(true);
        fireEvent.change(screen.getByLabelText("Name of the template"), { target: { value: "  Nouveau  " } });
        expect(bouton.disabled).toBe(false);
        fireEvent.click(bouton);
        await waitFor(() => expect(appelsDe("creer")).toHaveLength(1));
        expect(appelsDe("creer")[0].body).toEqual({ nom: "  Nouveau  ", workflow_id: 7 });
    });

    it("closes the gestures and says why while the page has unsaved changes (M11)", async () => {
        await ouvrirLaModale({ modifie: true });
        expect(document.querySelector("[data-non-enregistre]")).not.toBeNull();
        fireEvent.change(screen.getByLabelText("Name of the template"), { target: { value: "x" } });
        expect((document.querySelector("[data-creer-modele]") as HTMLButtonElement).disabled).toBe(true);
        fireEvent.click(await screen.findByText("Apply", { selector: "[data-appliquer-modele]" }));
        await waitFor(() => expect(document.querySelector("[data-valider-application]")).not.toBeNull());
        expect((document.querySelector("[data-valider-application]") as HTMLButtonElement).disabled).toBe(true);
    });

    it("applies by section: all of the template's sections ticked, a dry run first, then the ticked sections leave and the page reloads", async () => {
        const apres = vi.fn();
        await ouvrirLaModale({ apres });
        fireEvent.click(await screen.findByText("Apply", { selector: "[data-appliquer-modele]" }));
        await waitFor(() => expect(document.querySelector('[data-section="tour"]')).not.toBeNull());

        // Ticked by default: exactly the sections the template holds; the others are shut and say so.
        for (const section of SECTIONS) {
            const case_ = document.querySelector(`[data-section="${section}"]`) as HTMLElement;
            const portee = MODELE.sections.includes(section);
            expect(case_.getAttribute("data-state"), section).toBe(portee ? "checked" : "unchecked");
            expect(case_.hasAttribute("disabled"), section).toBe(!portee);
        }
        expect(screen.getAllByText(/not in this template/)).toHaveLength(SECTIONS.length - MODELE.sections.length);

        // The dry run is played for the ticked sections and nothing is written.
        await waitFor(() => expect(appelsDe("appliquer")).toHaveLength(1));
        expect(appelsDe("appliquer")[0].body).toEqual({ workflow_id: 7, sections: ["briques", "tour", "voix"], a_blanc: true });
        await waitFor(() => expect(document.querySelector("[data-apercu-application]")?.textContent).toContain("2 settings take the template's value"));
        expect(document.querySelector("[data-apercu-application]")?.textContent).toContain("1 go back to their default");

        // Un-ticking a section reads the preview again.
        fireEvent.click(document.querySelector('[data-section="voix"]') as HTMLElement);
        await waitFor(() => expect(appelsDe("appliquer")).toHaveLength(2));
        expect((appelsDe("appliquer")[1].body as { sections: string[] }).sections).toEqual(["briques", "tour"]);

        fireEvent.click(document.querySelector("[data-valider-application]") as HTMLElement);
        await waitFor(() => expect(apres).toHaveBeenCalledTimes(1));
        const dernier = appelsDe("appliquer").at(-1)!;
        expect(dernier.body).toEqual({ workflow_id: 7, sections: ["briques", "tour"], a_blanc: false });
        expect((dernier.path as { modele_id: string }).modele_id).toBe("abc123");
    });

    it("names, before applying, the providers the agent and its organization have no key for (M3)", async () => {
        m.apercu = {
            ...m.apercu,
            non_appliquees: [{ cle: "model_configuration_v2_override", raison: "cle-manquante" }],
            fournisseurs_sans_cle: ["soniox"],
        };
        await ouvrirLaModale();
        fireEvent.click(await screen.findByText("Apply", { selector: "[data-appliquer-modele]" }));
        const avertissement = await waitFor(() => {
            const a = document.querySelector('[data-sans-cle="soniox"]') as HTMLElement;
            expect(a).not.toBeNull();
            return a;
        });
        expect(avertissement.textContent).toContain("No key for soniox");
        expect(document.querySelector('[data-non-appliquee="model_configuration_v2_override"]')).not.toBeNull();
        // Not blocking: the rest of the template can still be applied.
        expect((document.querySelector("[data-valider-application]") as HTMLButtonElement).disabled).toBe(false);
    });

    it("shows the server's refusal of a preview and keeps the button shut", async () => {
        const sdk = await import("@/client/sdk.gen");
        vi.mocked(sdk.appliquerUnModeleApiV1OrganizationsModelesDeReglagesModeleIdAppliquerPost).mockImplementationOnce((async () => ({
            error: { detail: "The agent's settings would not be accepted with this template: invalid." },
        })) as never);
        await ouvrirLaModale();
        fireEvent.click(await screen.findByText("Apply", { selector: "[data-appliquer-modele]" }));
        await waitFor(() => expect(document.querySelector("[data-refus-application]")?.textContent).toContain("would not be accepted"));
        expect((document.querySelector("[data-valider-application]") as HTMLButtonElement).disabled).toBe(true);
    });

    it("renames, and deletes only after a confirmation", async () => {
        await ouvrirLaModale();
        const carte = await waitFor(() => {
            const c = document.querySelector('[data-modele="abc123"]') as HTMLElement;
            expect(c).not.toBeNull();
            return c;
        });
        fireEvent.click(within(carte).getByLabelText("Rename"));
        fireEvent.change(screen.getByLabelText("New name"), { target: { value: "Autre nom" } });
        fireEvent.click(screen.getByText("Rename", { selector: "button:not([aria-label])" }));
        await waitFor(() => expect(appelsDe("renommer")).toHaveLength(1));
        expect(appelsDe("renommer")[0].body).toEqual({ nom: "Autre nom" });

        fireEvent.click(within(carte).getByLabelText("Delete"));
        expect(appelsDe("supprimer"), "one click does not delete").toHaveLength(0);
        fireEvent.click(document.querySelector("[data-confirmer-suppression]") as HTMLElement);
        await waitFor(() => expect(appelsDe("supprimer")).toHaveLength(1));
        expect((appelsDe("supprimer")[0].path as { modele_id: string }).modele_id).toBe("abc123");
    });

    it("exports the file of a template", async () => {
        const creer = vi.fn(() => "blob:fichier");
        vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: creer, revokeObjectURL: vi.fn() }));
        await ouvrirLaModale();
        const carte = await waitFor(() => {
            const c = document.querySelector('[data-modele="abc123"]') as HTMLElement;
            expect(c).not.toBeNull();
            return c;
        });
        fireEvent.click(within(carte).getByLabelText("Export"));
        await waitFor(() => expect(appelsDe("exporter")).toHaveLength(1));
        await waitFor(() => expect(creer).toHaveBeenCalledTimes(1));
        vi.unstubAllGlobals();
    });

    it("sends an imported file as it is, and shows the server's refusal with the setting's name", async () => {
        const fichier = { format: "modele-de-reglages-mark", version_du_format: 1, nom: "Importe", valeurs: { reglage_inconnu: 1 } };
        m.refusImport = { detail: [{ msg: "Setting « reglage_inconnu » refused: this server does not know it.", loc: ["body", "valeurs", "reglage_inconnu"] }] };
        const { toast } = await import("sonner");
        await ouvrirLaModale();
        const champ = document.querySelector("[data-import-modele]") as HTMLInputElement;
        fireEvent.change(champ, { target: { files: [new File([JSON.stringify(fichier)], "modele.json", { type: "application/json" })] } });
        await waitFor(() => expect(appelsDe("importer")).toHaveLength(1));
        expect(appelsDe("importer")[0].body).toEqual(fichier);
        await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringContaining("reglage_inconnu")));
    });

    it("refuses a file that is not JSON without asking the server", async () => {
        const { toast } = await import("sonner");
        await ouvrirLaModale();
        const champ = document.querySelector("[data-import-modele]") as HTMLInputElement;
        fireEvent.change(champ, { target: { files: [new File(["pas du json"], "x.json")] } });
        await waitFor(() => expect(toast.error).toHaveBeenCalled());
        expect(appelsDe("importer")).toHaveLength(0);
    });
});
