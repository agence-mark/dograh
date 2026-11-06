#!/usr/bin/env node
// [.mark] U12 (E104, point 3) : le hook d'ouverture de session de Claude Code. Il affiche ce qui a changé dans le fork depuis la dernière
// session : nouveaux points « À améliorer », tests en échec, appels à juger, chats du builder. La sortie standard d'un hook
// SessionStart est ajoutée au contexte de la session.
//
// Même fonction que l'outil MCP `fork_resume` (route `GET /builder/resume`), avec la clé MCP de la personne (`MARK_MCP_KEY`).
// Ne bloque jamais (délai de 4 s, toute erreur est avalée, sortie 0). Garde la date de la dernière session dans
// `~/.mark-claude-code/derniere-session.json` (une date, rien de secret). Sans MARK_FORK_URL ou MARK_MCP_KEY : ne fait rien.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const DELAI_MS = 4000;
const DOSSIER = join(homedir(), ".mark-claude-code");
const FICHIER = join(DOSSIER, "derniere-session.json");

export function lireLaDerniereSession(fichier = FICHIER) {
    try {
        const date = JSON.parse(readFileSync(fichier, "utf8")).date;
        return typeof date === "string" && !Number.isNaN(Date.parse(date)) ? date : null;
    } catch {
        return null;
    }
}

export function ecrireLaDerniereSession(date, fichier = FICHIER) {
    try {
        mkdirSync(DOSSIER, { recursive: true });
        writeFileSync(fichier, JSON.stringify({ date }));
    } catch {
        /* sans dossier d'écriture, la prochaine session relira les dernières 24 heures */
    }
}

/** Le texte affiché : quelques lignes, rien si rien n'a changé. */
export function mettreEnForme(r) {
    const lignes = [];
    const nouveaux = r.a_ameliorer?.nouveaux ?? 0;
    if (nouveaux) lignes.push(`${nouveaux} nouveau(x) point(s) « À améliorer »`);
    const echecs = r.tests_en_echec?.total ?? 0;
    if (echecs) lignes.push(`${echecs} test(s) en échec`);
    const aJuger = r.appels_a_juger?.total ?? 0;
    if (aJuger) lignes.push(`${aJuger} élément(s) à juger (juge_a_faire)`);
    const chats = r.chats_du_builder?.modifies ?? 0;
    if (chats) lignes.push(`${chats} chat(s) du builder modifié(s)`);
    return lignes.length ? `Depuis la dernière session, dans le fork .mark : ${lignes.join(" · ")}.` : "";
}

export async function lire({ url, cle, depuis, fetchImpl = fetch }) {
    const controle = new AbortController();
    const minuteur = setTimeout(() => controle.abort(), DELAI_MS);
    try {
        const adresse = `${url.replace(/\/+$/, "")}/builder/resume${depuis ? `?depuis=${encodeURIComponent(depuis)}` : ""}`;
        const reponse = await fetchImpl(adresse, { headers: { "x-api-key": cle }, signal: controle.signal });
        return reponse.ok ? await reponse.json() : null;
    } catch {
        return null;
    } finally {
        clearTimeout(minuteur);
    }
}

async function principal() {
    const url = process.env.MARK_FORK_URL;
    const cle = process.env.MARK_MCP_KEY;
    if (!url || !cle) return;
    const maintenant = new Date().toISOString();
    const resume = await lire({ url, cle, depuis: lireLaDerniereSession() });
    if (!resume) return;
    const texte = mettreEnForme(resume);
    if (texte) process.stdout.write(`${texte}\n`);
    ecrireLaDerniereSession(maintenant);
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
    principal().then(
        () => process.exit(0),
        () => process.exit(0),
    );
}
