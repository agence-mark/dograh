#!/usr/bin/env node
/**
 * [.mark] verifier-contraintes.mjs — chaque dépendance directe de l'image est-elle figée ?
 *
 * Usage, depuis la racine du fork : node scripts/mark/verifier-contraintes.mjs
 * Sortie 0 = toutes figées. Sortie 1 = au moins une absente de api/constraints.txt.
 *
 * Pourquoi (réflexe R5, relecture du 25/09/2026) : `api/constraints.txt` ne fige que
 * ce qu'il contient. Un paquet ajouté à `api/requirements.txt` sans régénérer le
 * fichier (`bash scripts/mark/generer-contraintes.sh`) arriverait à la version du
 * jour, lui et ses dépendances, sans que rien ne le dise. Lancé par la CI
 * (`.github/workflows/mark-garde-fous.yml`), bloquant.
 */

import fs from "node:fs";

const normaliser = (nom) => nom.toLowerCase().replace(/[-_.]+/g, "-");

function noms(fichier, { contraintes = false } = {}) {
  const resultat = new Set();
  for (let ligne of fs.readFileSync(fichier, "utf8").split(/\r?\n/)) {
    ligne = ligne.replace(/#.*$/, "").trim();
    if (!ligne || ligne.startsWith("-")) continue; // options (-r, -c, --index-url…)
    // « nom[extra] @ url », « nom==1.2 ; marqueur », « nom>=1 »
    const nom = ligne.match(/^([A-Za-z0-9][A-Za-z0-9._-]*)/)?.[1];
    if (!nom) continue;
    if (contraintes && !/==|\s@\s/.test(ligne)) continue; // une contrainte non exacte ne fige rien
    resultat.add(normaliser(nom));
  }
  return resultat;
}

const directes = noms("api/requirements.txt");
const figees = noms("api/constraints.txt", { contraintes: true });
const manquantes = [...directes].filter((n) => !figees.has(n)).sort();

if (manquantes.length) {
  console.log("❌ Dépendances de api/requirements.txt absentes de api/constraints.txt :");
  for (const n of manquantes) console.log(`   • ${n}`);
  console.log("\n   Régénérer : bash scripts/mark/generer-contraintes.sh (réflexe R5).");
  process.exit(1);
}
console.log(`✅ Les ${directes.size} dépendances directes de l'image sont figées dans api/constraints.txt.`);
