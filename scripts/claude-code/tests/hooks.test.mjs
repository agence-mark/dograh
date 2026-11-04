// [.mark] U12 (D7) : tests des hooks Claude Code (filtre, évènements envoyés, envoi, installation). Lancer :
//   node --test scripts/claude-code/tests/
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { delimiter, resolve } from "node:path";
import { filtrer, resumeDesArguments } from "../filtre.mjs";
import { blocAffiche, blocDesHooks, fusionner, retirer } from "../installer.mjs";
import { mettreEnForme } from "../ouverture.mjs";
import { dansLesDossiers, dernierTexteDeClaude, envoyer, evenementsDe } from "../miroir.mjs";

const ICI = dirname(fileURLToPath(import.meta.url));
// Les préfixes de clé y sont coupés par « {{J}} » (retiré ici) : aucun motif de clé en clair dans le dépôt (protection des pushs).
const VECTEURS = JSON.parse(readFileSync(join(ICI, "vecteurs-filtre.json"), "utf8").replaceAll("{{J}}", ""));

// --- le filtre -------------------------------------------------------------------------------------------------

for (const v of VECTEURS) {
    test(`filtre : ${v.nom}`, () => {
        const entree = v.repeter ? v.entree.replace(v.repeter.cle ?? Object.keys(v.repeter)[0], v.repeter[Object.keys(v.repeter)[0]].repeat(v.repeter.fois)) : v.entree;
        const [sortie] = filtrer(entree);
        for (const absent of v.absents) assert.ok(!sortie.includes(absent), `« ${absent} » est resté dans : ${sortie}`);
        for (const present of v.presents) assert.ok(sortie.includes(present), `« ${present} » a disparu de : ${sortie}`);
    });
}

test("filtre : un texte sans secret ne change pas et ne dit rien", () => {
    assert.deepEqual(filtrer("Bonjour, rejoue les tests."), ["Bonjour, rejoue les tests.", false]);
});

// --- ce que les hooks envoient -----------------------------------------------------------------------------------

const SECRET = "sk-ant-api03-ZZZZZZZZZZZZZZZZ";
const DOSSIER = resolve("/projets/agence");

test("message envoyé : le texte est filtré", () => {
    const { evenements } = evenementsDe({ hook_event_name: "UserPromptSubmit", prompt: `Corrige avec ${SECRET} stp` });
    assert.equal(evenements.length, 1);
    assert.equal(evenements[0].type, "message");
    assert.ok(!JSON.stringify(evenements).includes("ZZZZZZZZ"));
});

test("action du MCP : le nom et un résumé, jamais le résultat brut", () => {
    const { evenements, workflow_id } = evenementsDe({
        hook_event_name: "PostToolUse",
        tool_name: "mcp__dograh__brouillon_operation",
        tool_input: { workflow_id: 320, operations: [{ op: "x" }], note: "a".repeat(500) },
        tool_response: { content: [{ type: "text", text: `RESULTAT-BRUT ${SECRET}` }] },
    });
    assert.equal(workflow_id, 320);
    assert.equal(evenements[0].nom, "brouillon_operation");
    const brut = JSON.stringify(evenements);
    assert.ok(!brut.includes("RESULTAT-BRUT") && !brut.includes("ZZZZZZZZ"));
    assert.ok(evenements[0].resume.includes("[500 caractères]") && evenements[0].resume.includes("[1 éléments]"));
    assert.equal(evenements[0].ok, true);
});

test("action du MCP en erreur : ok est faux", () => {
    const { evenements } = evenementsDe({ hook_event_name: "PostToolUse", tool_name: "mcp__dograh__tests_rejouer", tool_input: {}, tool_response: { isError: true } });
    assert.equal(evenements[0].ok, false);
});

test("un autre outil (lecture d'un fichier, commande) n'envoie rien", () => {
    for (const tool_name of ["Read", "Bash", "Edit", "mcp__autre__chose"]) {
        const { evenements } = evenementsDe({ hook_event_name: "PostToolUse", tool_name, tool_input: { file_path: "C:/x/.env" }, tool_response: { content: "CLE=abc" } });
        assert.deepEqual(evenements, []);
    }
});

test("fin de réponse : le texte de Claude après le dernier message, sans appels d'outils ni résultats, filtré", () => {
    const l = (o) => JSON.stringify(o);
    const transcription = [
        l({ type: "user", message: { role: "user", content: "premier message" } }),
        l({ type: "assistant", message: { role: "assistant", content: [{ type: "text", text: "ancienne réponse" }] } }),
        l({ type: "user", message: { role: "user", content: "deuxième message" } }),
        l({ type: "assistant", message: { role: "assistant", content: [{ type: "text", text: "Je lis l'agent." }, { type: "tool_use", name: "Read", input: { file_path: ".env" } }] } }),
        l({ type: "user", message: { role: "user", content: [{ type: "tool_result", content: `CONTENU-DU-FICHIER ${SECRET}` }] } }),
        l({ type: "assistant", message: { role: "assistant", content: [{ type: "text", text: `Terminé, clé ${SECRET}.` }] } }),
    ];
    const { evenements } = evenementsDe({ hook_event_name: "Stop", transcript_path: "x" }, () => transcription);
    assert.deepEqual(evenements.map((e) => e.type), ["texte", "fin"]);
    const brut = JSON.stringify(evenements);
    assert.ok(brut.includes("Je lis l'agent.") && brut.includes("Terminé"));
    assert.ok(!brut.includes("ancienne") && !brut.includes("CONTENU-DU-FICHIER") && !brut.includes("ZZZZZZZZ"));
    assert.equal(dernierTexteDeClaude(["pas du json"]), "");
});

// --- l'envoi ----------------------------------------------------------------------------------------------------

test("envoi : adresse, clé en en-tête, session assainie, aucun secret dans le corps", async () => {
    let vu;
    const fetchImpl = async (adresse, options) => {
        vu = { adresse, options };
        return { ok: true };
    };
    const ok = await envoyer(
        { hook_event_name: "UserPromptSubmit", session_id: "abc 123/../x", prompt: `utilise ${SECRET}`, cwd: DOSSIER },
        { dossiers: DOSSIER, url: "https://fork.exemple.test/api/v1/", cle: "dgr_cle_de_test_0123456789", fetchImpl },
    );
    assert.equal(ok, true);
    assert.equal(vu.adresse, "https://fork.exemple.test/api/v1/builder/miroir");
    assert.equal(vu.options.headers["x-api-key"], "dgr_cle_de_test_0123456789");
    const corps = JSON.parse(vu.options.body);
    assert.match(corps.session, /^[A-Za-z0-9_-]+$/);
    assert.ok(!vu.options.body.includes("ZZZZZZZZ") && !vu.options.body.includes("dgr_cle_de_test"));
});

test("envoi : une panne réseau est avalée, rien sans session", async () => {
    const panne = async () => {
        throw new Error("réseau");
    };
    assert.equal(await envoyer({ hook_event_name: "UserPromptSubmit", session_id: "abcdef", prompt: "x", cwd: DOSSIER }, { dossiers: DOSSIER, url: "http://x", cle: "k", fetchImpl: panne }), false);
    assert.equal(await envoyer({ hook_event_name: "UserPromptSubmit", prompt: "x", cwd: DOSSIER }, { dossiers: DOSSIER, url: "http://x", cle: "k", fetchImpl: async () => ({ ok: true }) }), false);
});

test("résumé des arguments : un texte long devient sa longueur, un secret est retiré", () => {
    const r = resumeDesArguments({ cle: SECRET, texte: "b".repeat(200), n: 3 });
    assert.ok(!r.includes("ZZZZ") && r.includes("[200 caractères]") && r.includes("n=3"));
});

// --- l'installation et l'ouverture ---------------------------------------------------------------------------------

test("installation : fusion idempotente, les autres hooks restent, retrait propre", () => {
    const autres = { hooks: { Stop: [{ hooks: [{ type: "command", command: "echo fini" }] }] }, model: "x" };
    const une = fusionner(autres);
    const deux = fusionner(une);
    assert.deepEqual(une, deux);
    assert.equal(une.hooks.Stop.length, 2);
    assert.equal(une.model, "x");
    assert.deepEqual(Object.keys(blocDesHooks()).sort(), ["PostToolUse", "SessionStart", "Stop", "UserPromptSubmit"]);
    assert.equal(blocDesHooks().PostToolUse[0].matcher, "mcp__dograh__.*");
    assert.deepEqual(retirer(une), autres);
});

test("ouverture : une ligne seulement s'il y a du nouveau", () => {
    assert.equal(mettreEnForme({}), "");
    const texte = mettreEnForme({ a_ameliorer: { nouveaux: 2 }, tests_en_echec: { total: 1 }, appels_a_juger: { total: 5 }, chats_du_builder: { modifies: 0 } });
    assert.ok(texte.includes("2 nouveau") && texte.includes("1 test") && texte.includes("5 élément"));
});

// --- M4 : seulement les dossiers autorisés ---------------------------------------------------------------------------------

test("M4 : un dossier autorisé couvre ses sous-dossiers ; hors liste, liste vide ou cwd absent : non", () => {
    const liste = [resolve("/projets/agence"), resolve("/autre/projet")].join(delimiter);
    assert.equal(dansLesDossiers(resolve("/projets/agence"), liste), true);
    assert.equal(dansLesDossiers(resolve("/projets/agence/api/sous"), liste), true);
    assert.equal(dansLesDossiers(resolve("/autre/projet"), liste), true);
    assert.equal(dansLesDossiers(resolve("/projets/agence-voisine"), liste), false); // même début de nom, autre dossier
    assert.equal(dansLesDossiers(resolve("/projets/agence/../secret"), liste), false);
    assert.equal(dansLesDossiers(resolve("/ailleurs"), liste), false);
    assert.equal(dansLesDossiers(resolve("/projets/agence"), ""), false);
    assert.equal(dansLesDossiers(resolve("/projets/agence"), undefined), false);
    assert.equal(dansLesDossiers(undefined, liste), false);
});

test("M4 : une session hors des dossiers autorisés n'envoie rien (aucun appel réseau)", async () => {
    let appels = 0;
    const fetchImpl = async () => {
        appels += 1;
        return { ok: true };
    };
    const entree = { hook_event_name: "UserPromptSubmit", session_id: "abcdef", prompt: "bonjour" };
    const options = { url: "http://x", cle: "k", fetchImpl };
    assert.equal(await envoyer({ ...entree, cwd: resolve("/ailleurs") }, { ...options, dossiers: DOSSIER }), false);
    assert.equal(await envoyer({ ...entree, cwd: DOSSIER }, { ...options, dossiers: "" }), false);
    assert.equal(await envoyer(entree, { ...options, dossiers: DOSSIER }), false);
    assert.equal(appels, 0);
    assert.equal(await envoyer({ ...entree, cwd: DOSSIER }, { ...options, dossiers: DOSSIER }), true);
    assert.equal(appels, 1);
});

test("M4 : le bloc affiché par l'installateur porte la liste des dossiers (vide)", () => {
    assert.deepEqual(blocAffiche().env, { MARK_MIROIR_DOSSIERS: "" });
    assert.deepEqual(Object.keys(blocAffiche().hooks).sort(), ["PostToolUse", "SessionStart", "Stop", "UserPromptSubmit"]);
});
