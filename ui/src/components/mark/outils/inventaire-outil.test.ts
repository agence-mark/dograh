/**
 * [.mark] N2 : chaque réglage d'un outil a son écran dans la FENÊTRE de l'outil (ou dans l'écran de son propre type), ou figure ici
 * avec sa raison.
 *
 * Les clés sont lues dans `api/schemas/tool.py` (les classes de configuration de chaque type), jamais dans une liste tenue à la main : un
 * réglage que le serveur ajoute sans écran fait échouer ce test. Le pendant côté builder est `outil_modifier` (une seule action, la
 * définition complète) : `api/tests/mark/test_builder_inventaire_reglages.py`.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const racine = join(process.cwd(), "..");
const lire = (chemin: string) => readFileSync(join(racine, chemin), "utf8");

const SOURCES_ECRAN = [
    "ui/src/components/mark/outils/OngletsDeType.tsx",
    "ui/src/components/mark/outils/OngletsHttp.tsx",
    "ui/src/components/mark/outils/OngletComportement.tsx",
    "ui/src/components/mark/outils/EssaisOutilHttp.tsx",
    "ui/src/components/mark/outils/essais-outil.ts",
    "ui/src/components/mark/outils/FenetreOutil.tsx",
    "ui/src/components/mark/connecteurs/ConfigOutilIntegration.tsx",
    // Le serveur MCP a son propre écran (Intégrations › Serveurs MCP) : transport, délais, outils un à un.
    "ui/src/components/mark/integrations/OngletServeursMcp.tsx",
].map(lire).join("\n");

/** Les classes de configuration par type d'outil, avec les classes dont elles héritent. */
const CLASSES = ["ComportementOutil", "HttpApiConfig", "EndCallConfig", "HttpTransferResolverConfig", "ContextDestinationMappingConfig", "TransferCallConfig", "McpToolConfig", "TransferAgentConfig", "IntegrationToolConfig"];

const champsDe = (python: string, classe: string): string[] => {
    const i = python.indexOf(`class ${classe}(`);
    if (i < 0) throw new Error(`class ${classe} not found: the schema moved, update this test.`);
    const reste = python.slice(i + 1);
    const j = reste.search(/\nclass /);
    const bloc = reste.slice(0, j < 0 ? undefined : j);
    return [...bloc.matchAll(/^ {4}([a-zA-Z_][a-zA-Z0-9_]*): /gm)].map((m) => m[1]);
};

/** Un réglage du serveur sans écran dans la fenêtre, avec sa raison. */
const SANS_ECRAN: Record<string, string> = {
    "TransferCallConfig.parameters": "ancien emplacement des arguments du résolveur : le résolveur les porte (``resolver.parameters``), lus à sa place par le serveur",
    "ContextDestinationMappingConfig.context_path": "ancienne forme d'une seule règle ; remplacée par ``rules`` (acceptée pour compatibilité, jamais écrite)",
    "ContextDestinationMappingConfig.routes": "ancienne forme d'une seule règle ; remplacée par ``rules`` (acceptée pour compatibilité, jamais écrite)",
    "McpToolConfig.discovered_tools": "cache du catalogue du serveur, rempli par le serveur : jamais saisi",
    "ComportementOutil.dernier_essai": "écrit par le serveur après un essai",
    "ComportementOutil.premier_essai": "écrit par la validation d'une personne (onglet Essai)",
    "IntegrationToolConfig.dernier_essai": "écrit par le serveur après un essai",
    "IntegrationToolConfig.premier_essai": "écrit par la validation d'une personne (onglet Essai)",
    "McpToolConfig.reglages_outils": "réglé outil par outil dans Intégrations › Serveurs MCP (autorisé, confirmer, désactivé)",
    "McpToolConfig.timeout_secs": "réglé dans Intégrations › Serveurs MCP",
    "McpToolConfig.sse_read_timeout_secs": "réglé dans Intégrations › Serveurs MCP",
    "McpToolConfig.transport": "réglé dans Intégrations › Serveurs MCP",
    "IntegrationToolConfig.compte": "choisi dans l'onglet Général (compte branché)",
};

describe("[.mark] chaque réglage d'un outil a son écran", () => {
    const python = lire("api/schemas/tool.py");
    for (const classe of CLASSES) {
        it(`${classe} : chaque champ est sur un écran ou exempté avec sa raison`, () => {
            const sans = champsDe(python, classe).filter((c) => !new RegExp(`\\b${c}\\b`).test(SOURCES_ECRAN) && !SANS_ECRAN[`${classe}.${c}`]);
            expect(sans, `Réglages d'outil sans écran ni exemption écrite : ${sans.join(", ")}`).toEqual([]);
        });
    }

    it("une exemption cite un champ qui existe encore et dit sa raison", () => {
        for (const [cle, raison] of Object.entries(SANS_ECRAN)) {
            const [classe, champ] = cle.split(".");
            expect(champsDe(python, classe), cle).toContain(champ);
            expect(raison.length).toBeGreaterThan(10);
        }
    });
});
