#!/usr/bin/env node
// [.mark] U12 (E104, point 4) : le hook du miroir. Un seul fichier pour trois évènements de Claude Code :
//   UserPromptSubmit (message envoyé) · PostToolUse (action d'un outil du MCP « dograh ») · Stop (fin de réponse).
// Il envoie à `POST <MARK_FORK_URL>/builder/miroir`, avec la clé MCP de la personne (`MARK_MCP_KEY`), les messages, les réponses et le
// NOM des actions avec un résumé de leurs arguments. Jamais le résultat brut d'un outil, jamais le contenu d'un fichier ; tout passe par
// le filtre (`filtre.mjs`) avant l'envoi, et le serveur refiltre.
//
// Règles : ne bloque JAMAIS Claude Code (délai de 3 s, toute erreur est avalée, code de sortie 0) ; n'affiche rien ; ne lit aucun .env ;
// la clé ne vient que de l'environnement et n'est jamais écrite. Sans MARK_FORK_URL ou MARK_MCP_KEY : ne fait rien.
// Revue serveur M4 : n'envoie QUE si le `cwd` de la session est dans un dossier de MARK_MIROIR_DOSSIERS (liste d'autorisés).
// L'interrupteur de la personne (Profil / Sources) est côté serveur : éteint, le serveur ne range rien.
import { readFileSync, statSync, openSync, readSync, closeSync } from "node:fs";
import { delimiter, isAbsolute, relative, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { borner, filtrer, resumeDesArguments } from "./filtre.mjs";

const PREFIXE_MCP = "mcp__dograh__";
const TEXTE_MAX = 8000;
const LECTURE_MAX_OCTETS = 400_000;
const DELAI_MS = 3000;

/** La dernière réponse de Claude : les blocs de texte après le dernier message de la personne (jamais les appels d'outils ni leurs résultats). */
export function dernierTexteDeClaude(lignesJsonl) {
    const entrees = [];
    for (const l of lignesJsonl) {
        try {
            entrees.push(JSON.parse(l));
        } catch {
            /* ligne coupée au début de la fenêtre lue */
        }
    }
    let debut = 0;
    entrees.forEach((e, i) => {
        const message = e.message ?? e;
        const role = message.role ?? e.type;
        const contenu = message.content;
        const estUnResultatDOutil = Array.isArray(contenu) && contenu.some((b) => b && b.type === "tool_result");
        if (role === "user" && !estUnResultatDOutil && !e.isMeta) debut = i + 1;
    });
    const textes = [];
    for (const e of entrees.slice(debut)) {
        const message = e.message ?? e;
        if ((message.role ?? e.type) !== "assistant") continue;
        const contenu = message.content;
        if (typeof contenu === "string") textes.push(contenu);
        else if (Array.isArray(contenu)) for (const b of contenu) if (b && b.type === "text" && b.text) textes.push(b.text);
    }
    return textes.join("\n\n").trim();
}

function lireLaFin(chemin) {
    const taille = statSync(chemin).size;
    const debut = Math.max(0, taille - LECTURE_MAX_OCTETS);
    const fd = openSync(chemin, "r");
    try {
        const tampon = Buffer.alloc(taille - debut);
        readSync(fd, tampon, 0, tampon.length, debut);
        return tampon.toString("utf8").split("\n").filter(Boolean);
    } finally {
        closeSync(fd);
    }
}

function entierOuNul(v) {
    return Number.isInteger(v) && v > 0 ? v : null;
}

/**
 * Revue serveur M4 : la session est-elle dans un dossier autorisé ? `dossiers` = la liste de `MARK_MIROIR_DOSSIERS` (séparateur du système :
 * `;` sous Windows, `:` ailleurs). Liste vide ou absente, ou `cwd` absent : NON (liste d'autorisés, jamais « tout sauf »). Un dossier
 * autorisé couvre ses sous-dossiers ; `..` ne sort pas du dossier.
 */
export function dansLesDossiers(cwd, dossiers) {
    if (!cwd || typeof cwd !== "string" || !dossiers) return false;
    const session = resolve(cwd);
    return String(dossiers)
        .split(delimiter)
        .map((d) => d.trim())
        .filter(Boolean)
        .some((d) => {
            const chemin = relative(resolve(d), session);
            return chemin === "" || (!chemin.startsWith("..") && !isAbsolute(chemin));
        });
}

/** Les évènements à envoyer pour un évènement de Claude Code (pur : testable sans réseau). */
export function evenementsDe(entree, lire = lireLaFin) {
    const nom = entree.hook_event_name;
    if (nom === "UserPromptSubmit") {
        const [texte] = filtrer(String(entree.prompt ?? ""));
        return { evenements: texte.trim() ? [{ type: "message", texte: borner(texte.trim(), TEXTE_MAX) }] : [], workflow_id: null };
    }
    if (nom === "PostToolUse") {
        const outil = String(entree.tool_name ?? "");
        if (!outil.startsWith(PREFIXE_MCP)) return { evenements: [], workflow_id: null };
        const reponse = entree.tool_response;
        const erreur = Boolean(reponse && (reponse.isError || reponse.is_error));
        const arguments_ = entree.tool_input ?? {};
        return {
            evenements: [{ type: "action", nom: outil.slice(PREFIXE_MCP.length), resume: resumeDesArguments(arguments_), ok: !erreur }],
            workflow_id: entierOuNul(arguments_.workflow_id) ?? entierOuNul(arguments_.agent),
        };
    }
    if (nom === "Stop") {
        let texte = typeof entree.last_assistant_message === "string" ? entree.last_assistant_message : "";
        if (!texte && entree.transcript_path) {
            try {
                texte = dernierTexteDeClaude(lire(entree.transcript_path));
            } catch {
                texte = "";
            }
        }
        const [propre] = filtrer(texte);
        const evenements = propre.trim() ? [{ type: "texte", texte: borner(propre.trim(), TEXTE_MAX) }] : [];
        evenements.push({ type: "fin" });
        return { evenements, workflow_id: null };
    }
    return { evenements: [], workflow_id: null };
}

export async function envoyer(entree, { url, cle, dossiers = process.env.MARK_MIROIR_DOSSIERS, fetchImpl = fetch, lire = lireLaFin }) {
    if (!dansLesDossiers(entree.cwd, dossiers)) return false; // M4 : hors des dossiers autorisés, rien ne part
    const { evenements, workflow_id } = evenementsDe(entree, lire);
    if (!evenements.length || !entree.session_id) return false;
    const corps = { session: String(entree.session_id).replace(/[^A-Za-z0-9_-]/g, "_").slice(0, 80), evenements };
    if (workflow_id) corps.workflow_id = workflow_id;
    const controle = new AbortController();
    const minuteur = setTimeout(() => controle.abort(), DELAI_MS);
    try {
        const reponse = await fetchImpl(`${url.replace(/\/+$/, "")}/builder/miroir`, {
            method: "POST",
            headers: { "content-type": "application/json", "x-api-key": cle },
            body: JSON.stringify(corps),
            signal: controle.signal,
        });
        return reponse.ok;
    } catch {
        return false;
    } finally {
        clearTimeout(minuteur);
    }
}

async function principal() {
    const url = process.env.MARK_FORK_URL;
    const cle = process.env.MARK_MCP_KEY;
    if (!url || !cle) return;
    let brut = "";
    for await (const morceau of process.stdin) brut += morceau;
    let entree;
    try {
        entree = JSON.parse(brut);
    } catch {
        return;
    }
    await envoyer(entree, { url, cle });
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
    principal().then(
        () => process.exit(0),
        () => process.exit(0),
    );
}
