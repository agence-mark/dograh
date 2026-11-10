/**
 * [.mark] Revue des correctifs d'écran (10/11) : les logos officiels des fournisseurs de modèles.
 * Chaque fournisseur du catalogue a un logo, ou retombe sur ses initiales ; chaque fichier listé existe, sans script ni lien.
 */
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { NOMS } from "@/components/mark/cles/FenetreCles";

import { LOGOS, logoDe } from "./logos";

const PUBLIC = join(process.cwd(), "public");
// Deux secrets ne sont pas des fournisseurs de modèles : jamais de logo.
const FOURNISSEURS = Object.keys(NOMS).filter((f) => f !== "smtp" && f !== "webhook");

describe("logos des fournisseurs", () => {
    it("chaque fournisseur du catalogue a son logo ou retombe sur ses initiales (null)", () => {
        for (const f of FOURNISSEURS) {
            const logo = logoDe(f);
            expect(logo === null || logo.startsWith("/logos/"), f).toBe(true);
        }
        expect(logoDe("smtp")).toBeNull();
        expect(logoDe("fournisseur-inconnu")).toBeNull();
        // Les fournisseurs que .mark utilise ont un logo versé.
        for (const f of ["mistral", "cartesia", "soniox", "openai", "deepgram", "elevenlabs", "google"]) expect(logoDe(f), f).not.toBeNull();
    });

    it("chaque fichier listé existe dans ui/public/logos", () => {
        for (const [cle, adresse] of Object.entries(LOGOS)) {
            expect(existsSync(join(PUBLIC, adresse)), `${cle} : ${adresse}`).toBe(true);
        }
    });

    it("un SVG versé ne contient ni script, ni lien externe, ni image embarquée", () => {
        // Les logos de logiciels versés avant ce chantier ne sont pas de son ressort : seuls ceux des fournisseurs sont contrôlés.
        for (const adresse of new Set(FOURNISSEURS.map((f) => LOGOS[f]).filter(Boolean))) {
            if (!adresse.endsWith(".svg")) continue;
            const svg = readFileSync(join(PUBLIC, adresse), "utf8");
            expect(svg, adresse).not.toMatch(/<script|<foreignObject|<image|\son\w+\s*=|(?:xlink:)?href\s*=|@import|url\(\s*["']?https?:/i);
        }
    });
});
