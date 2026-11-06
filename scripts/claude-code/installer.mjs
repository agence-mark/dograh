#!/usr/bin/env node
// [.mark] U12 (D7) : la commande d'installation des hooks. LIVRÉE, JAMAIS LANCÉE par le chantier : c'est Evan qui l'exécute.
//
//   node scripts/claude-code/installer.mjs                        affiche le bloc `hooks` à poser (n'écrit rien)
//   node scripts/claude-code/installer.mjs --ecrire <fichier>      fusionne le bloc dans ce fichier de réglages Claude Code
//                                                                  (ex. ~/.claude/settings.json), sans toucher à ses autres hooks
//   node scripts/claude-code/installer.mjs --retirer <fichier>     retire nos hooks de ce fichier
//
// Il faut aussi MARK_MIROIR_DOSSIERS (revue M4) : la liste des dossiers dont les sessions sont miroitées, séparés par « ; » sous Windows
// ou « : » ailleurs. Vide : RIEN ne part (les hooks ne partent jamais pour une session Claude Code hors de ces dossiers).
// Il faut ensuite deux variables d'environnement (jamais dans le fichier de réglages) : MARK_FORK_URL (ex. https://.../api/v1) et
// MARK_MCP_KEY (la clé MCP de la personne). Puis allumer « Miroir de mes conversations Claude Code » dans Réglages › Sources.
// Idempotent : relancé, il ne double rien (nos entrées se reconnaissent à leur marque `mark-fork-miroir`).
import { existsSync, readFileSync, writeFileSync, copyFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const MARQUE = "mark-fork-miroir";
const ICI = dirname(fileURLToPath(import.meta.url));

function commande(script) {
    // `# marque` : un commentaire de shell qui reconnaît nos entrées sans rien changer à la commande.
    return `node "${join(ICI, script).replaceAll("\\", "/")}" # ${MARQUE}`;
}

/** Les réglages affichés : les hooks, et la liste des dossiers autorisés à remplir (revue M4, vide = rien ne part). */
export function blocAffiche() {
    return { hooks: blocDesHooks(), env: { MARK_MIROIR_DOSSIERS: "" } };
}

/** Le bloc `hooks` à poser. */
export function blocDesHooks() {
    const unHook = (script) => ({ type: "command", command: commande(script) });
    return {
        UserPromptSubmit: [{ hooks: [unHook("miroir.mjs")] }],
        PostToolUse: [{ matcher: "mcp__dograh__.*", hooks: [unHook("miroir.mjs")] }],
        Stop: [{ hooks: [unHook("miroir.mjs")] }],
        SessionStart: [{ hooks: [unHook("ouverture.mjs")] }],
    };
}

const estLeNotre = (entree) => (entree.hooks ?? []).some((h) => String(h.command ?? "").includes(MARQUE));

/** Fusionne nos hooks dans des réglages (objet) : retire d'abord les nôtres, puis ajoute. Les autres hooks restent. */
export function fusionner(reglages, bloc = blocDesHooks()) {
    const sortie = { ...reglages, hooks: { ...(reglages.hooks ?? {}) } };
    for (const [evenement, entrees] of Object.entries(bloc)) {
        sortie.hooks[evenement] = [...(sortie.hooks[evenement] ?? []).filter((e) => !estLeNotre(e)), ...entrees];
    }
    return sortie;
}

export function retirer(reglages) {
    const hooks = {};
    for (const [evenement, entrees] of Object.entries(reglages.hooks ?? {})) {
        const reste = entrees.filter((e) => !estLeNotre(e));
        if (reste.length) hooks[evenement] = reste;
    }
    const sortie = { ...reglages, hooks };
    if (!Object.keys(hooks).length) delete sortie.hooks;
    return sortie;
}

function lire(fichier) {
    return existsSync(fichier) ? JSON.parse(readFileSync(fichier, "utf8") || "{}") : {};
}

function ecrire(fichier, reglages) {
    if (existsSync(fichier)) copyFileSync(fichier, `${fichier}.avant-mark`);
    writeFileSync(fichier, `${JSON.stringify(reglages, null, 2)}\n`);
}

function principal(argv) {
    const [option, fichier] = argv;
    if (option === "--ecrire" && fichier) {
        ecrire(fichier, fusionner(lire(fichier)));
        console.log(`Hooks posés dans ${fichier} (copie : ${fichier}.avant-mark). Pensez à MARK_FORK_URL, MARK_MCP_KEY et MARK_MIROIR_DOSSIERS (les dossiers miroités ; vide = rien ne part).`);
    } else if (option === "--retirer" && fichier) {
        ecrire(fichier, retirer(lire(fichier)));
        console.log(`Hooks .mark retirés de ${fichier} (copie : ${fichier}.avant-mark).`);
    } else {
        console.log(JSON.stringify(blocAffiche(), null, 2));
    }
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) principal(process.argv.slice(2));
