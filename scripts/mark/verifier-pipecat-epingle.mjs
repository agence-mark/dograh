#!/usr/bin/env node
/**
 * verifier-pipecat-epingle.mjs — Pipecat est-il au même commit des deux côtés ?
 *
 * [.mark] Lancé par la CI (`.github/workflows/mark-garde-fous.yml`) et à la main,
 * depuis la racine du fork :
 *   node scripts/mark/verifier-pipecat-epingle.mjs
 *   node scripts/mark/verifier-pipecat-epingle.mjs --ref origin/mark/deploiement
 *
 * Sortie 0 = les deux concordent. Sortie 1 = ils diffèrent, ou l'un est introuvable.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * POURQUOI CE SCRIPT EXISTE (réflexe R2, labo `remise-a-niveau-amont/`)
 * ─────────────────────────────────────────────────────────────────────────────
 * Pipecat existe DEUX fois dans le fork :
 *   • le sous-module `pipecat/`, que git met à jour à chaque fusion de l'amont,
 *     et sur lequel tournent les tests du poste et de la CI ;
 *   • le commit écrit EN DUR dans `api/Dockerfile`, que l'image de production
 *     installe réellement.
 * Si seul le premier bouge, tout est vert sur le poste et en CI, et l'API
 * tombe en production : le code de l'amont exige la nouvelle version
 * (analyse d'écart du 25/09/2026 : `should_interrupt`, `user_turn_controller`
 * n'existent qu'à partir de `49ba358`). Rien d'autre ne le vérifie.
 *
 * Il lit les objets git du commit visé (`--ref`, défaut HEAD) : il ne touche
 * jamais l'arbre de travail et peut tourner pendant une suite de tests.
 */

import { execFileSync } from "node:child_process";

function git(args) {
  return execFileSync("git", args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
}

const i = process.argv.indexOf("--ref");
const ref = i > -1 ? process.argv[i + 1] : "HEAD";

let sousModule;
try {
  // « 160000 commit <sha>\tpipecat » : le commit que le dépôt épingle.
  const ligne = git(["ls-tree", ref, "pipecat"]);
  sousModule = ligne.match(/^160000 commit ([0-9a-f]{40})\tpipecat$/)?.[1];
} catch {
  sousModule = undefined;
}

let dockerfile;
try {
  dockerfile = git(["show", `${ref}:api/Dockerfile`]);
} catch {
  dockerfile = null;
}

const epingles = dockerfile
  ? [...dockerfile.matchAll(/github\.com\/dograh-hq\/pipecat\.git@([0-9a-f]{7,40})/g)].map(
      (m) => m[1],
    )
  : [];

console.log(`Commit vérifié      : ${ref}`);
console.log(`Sous-module pipecat : ${sousModule ?? "INTROUVABLE"}`);
console.log(
  `api/Dockerfile      : ${epingles.length ? epingles.join(", ") : "AUCUN commit Pipecat trouvé"}`,
);

const problemes = [];
if (!sousModule) problemes.push("le sous-module `pipecat` est introuvable à ce commit");
if (!dockerfile) problemes.push("`api/Dockerfile` est introuvable à ce commit");
else if (!epingles.length)
  problemes.push(
    "aucune installation `dograh-hq/pipecat.git@<commit>` dans `api/Dockerfile` : la forme a changé, relire le fichier",
  );
if (sousModule) {
  for (const e of epingles) {
    if (!sousModule.startsWith(e) && !e.startsWith(sousModule)) {
      problemes.push(
        `api/Dockerfile installe Pipecat ${e}, le sous-module est à ${sousModule.slice(0, 12)}`,
      );
    }
  }
}

if (problemes.length) {
  console.log("\n❌ Pipecat n'est PAS au même commit des deux côtés :");
  for (const p of problemes) console.log(`   • ${p}`);
  console.log(
    "\n   La production installerait une autre version que celle testée. Aligner le Dockerfile\n" +
      "   sur le sous-module (réflexe R2, labo `remise-a-niveau-amont/reflexes-de-securite.md`).",
  );
  process.exit(1);
}
console.log("\n✅ Pipecat au même commit dans le sous-module et dans api/Dockerfile.");
