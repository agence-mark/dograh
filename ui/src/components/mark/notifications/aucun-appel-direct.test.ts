// @vitest-environment node
/**
 * [.mark] Les notifications passent par UN module (`notifier`, `15-notifications.md`).
 *
 * La question de ce fichier, et seulement celle-ci : un fichier de `ui/src` (hors le module et les tests) importe-t-il
 * `sonner` ou appelle-t-il `toast(` / `toast.xxx(` directement ? Si oui, sa notification échappe aux règles de durée,
 * de pile, de regroupement, de bouton et de « Détails » : le test échoue en le nommant.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

import { describe, expect, it } from "vitest";

const RACINE = join(__dirname, "..", "..", "..");

/**
 * Fichiers du lot K1 (cadre, accès, Réglages de l'organisation, Équipe et rôles), codés en parallèle : la fenêtre
 * principale les fait passer à `notifier` après la fusion de K1, puis VIDE cette liste.
 */
const PAS_ENCORE_PASSES = new Set([
    "components/ui/sonner.tsx", // le Toaster de sonner, monté dans app/layout.tsx tant que ces fichiers l'utilisent
    "app/api-keys/page.tsx",
    "app/auth/signup/page.tsx",
    "app/connexion/FormulaireConnexion.tsx",
    "app/invitation/PageInvitation.tsx",
    "app/profil/PageProfil.tsx",
    "components/CallEventsSection.tsx",
    "components/layout/SidebarOrganizationSwitcher.tsx",
    "components/layout/SidebarTeamSwitcher.tsx",
    "components/mark/equipe/VueJournal.tsx",
    "components/mark/equipe/VueMembres.tsx",
    "components/mark/equipe/VueRoles.tsx",
    "components/mark/integrations/OngletIdentifiants.tsx",
    "components/mark/integrations/OngletLogiciels.tsx",
    "components/mark/parametres-organisation/BlocInstallationMark.tsx",
    "components/mark/parametres-organisation/BlocSecoursPanne.tsx",
    "components/mark/parametres-organisation/BoutonAppliquerATous.tsx",
    "components/mark/parametres-organisation/ModaleEtablissements.tsx",
    "components/mark/parametres-organisation/ModalePhrases.tsx",
    "components/mark/parametres-organisation/ModaleReprise.tsx",
    "components/mark/parametres-organisation/preferences.ts",
    "components/mark/parametres-organisation/SectionConservationAppels.tsx",
    "components/mark/parametres-organisation/SectionListesValeurs.tsx",
    "components/mark/parametres-organisation/SectionObjets.tsx",
    "components/mark/parametres-organisation/ThemeApresAppel.tsx",
    "components/mark/parametres-organisation/ThemeDonneesClient.tsx",
    "components/mark/parametres-organisation/ThemeEquipe.tsx",
    "components/mark/parametres-organisation/ThemeRendezVous.tsx",
    "components/mark/parametres-organisation/ThemeVerification.tsx",
    "components/mark/studio/selecteur-espace.tsx",
    "components/MCPSection.tsx",
    "components/OrganizationPreferencesSection.tsx",
    "components/TelemetrySection.tsx",
]);

function fichiers(dossier: string, sortie: string[] = []): string[] {
    for (const nom of readdirSync(dossier)) {
        const chemin = join(dossier, nom);
        if (statSync(chemin).isDirectory()) {
            if (nom === "client" || nom === "node_modules") continue;
            fichiers(chemin, sortie);
        } else if (/\.(ts|tsx)$/.test(nom) && !/\.test\.(ts|tsx)$/.test(nom)) {
            sortie.push(chemin);
        }
    }
    return sortie;
}

const sansCommentaires = (s: string) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

const APPEL_DIRECT = /from\s+["']sonner["']|\btoast\s*\(|\btoast\.(success|error|warning|info|message|promise|loading|custom|dismiss)\s*\(/;

describe("aucun appel direct à sonner ou à toast", () => {
    const concernes = fichiers(RACINE)
        .map((f) => ({ f, rel: relative(RACINE, f).split(sep).join("/") }))
        .filter(({ rel }) => !rel.startsWith("components/mark/notifications/"));

    it("seul le module des notifications affiche une notification passagère", () => {
        const fautifs = concernes
            .filter(({ f, rel }) => !PAS_ENCORE_PASSES.has(rel) && APPEL_DIRECT.test(sansCommentaires(readFileSync(f, "utf8"))))
            .map(({ rel }) => rel);
        expect(fautifs).toEqual([]);
    });

    it("la liste des fichiers pas encore passés ne garde que des fichiers qui appellent encore sonner", () => {
        const perimes = [...PAS_ENCORE_PASSES].filter((rel) => {
            const trouve = concernes.find((c) => c.rel === rel);
            return !trouve || !APPEL_DIRECT.test(sansCommentaires(readFileSync(trouve.f, "utf8")));
        });
        expect(perimes).toEqual([]);
    });
});
