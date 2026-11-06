"use client";

/**
 * [.mark] Partie 3, N3b (décision 20, maquette `export-import-agent.tsx`) : l'agent entier en fichiers lisibles, et leur import.
 *
 * Deux fenêtres centrées (saisie courte, comme la maquette) :
 *  - « Exporter en fichiers » : le contenu à cocher (graphe, prompts, réglages, outils épinglés, blocs, tests), puis l'archive de
 *    fichiers YAML et Markdown à télécharger. Aucune clé n'en sort ;
 *  - « Importer des fichiers » : on choisit le dossier, l'aperçu dit fichier par fichier ce qui changerait dans le brouillon
 *    (ajouté, modifié, inchangé, retiré), puis « Importer dans le brouillon ». Rien n'est publié ; relancer le même import ne change
 *    rien. L'aperçu et l'import sont ceux du serveur (`/agent-fichiers`), jamais recalculés ici.
 * Distinct de « Exporter vers un client » (copie d'un agent du Labo dans une autre organisation).
 */
import { FileText, FolderOpen } from "lucide-react";
import { useRef, useState } from "react";

import { exporterEnFichiersApiV1AgentFichiersWorkflowIdExportGet, importerDesFichiersApiV1AgentFichiersWorkflowIdImportPost } from "@/client/sdk.gen";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { echecAffiche } from "@/components/mark/notifications/echec-affiche";
import { Info, PointEtat } from "@/components/mark/studio/marques";
import { Cellule, Ligne, Tableau } from "@/components/mark/studio/tableau";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";

export const CONTENUS: Array<{ id: string; nom: Texte; fichier: string; info: Texte }> = [
    { id: "graphe", nom: { en: "Graph", fr: "Graphe" }, fichier: "graphe.yaml", info: { en: "Steps, links and their conditions.", fr: "Étapes, liaisons et leurs conditions." } },
    { id: "prompts", nom: { en: "Prompts", fr: "Prompts" }, fichier: "prompts/*.md", info: { en: "One file per step, the general prompt included.", fr: "Un fichier par étape, plus le prompt général." } },
    { id: "reglages", nom: { en: "Settings", fr: "Réglages" }, fichier: "reglages.yaml", info: { en: "The agent's settings and variables, with no key and no secret.", fr: "Les réglages et les variables de l'agent, sans aucune clé ni secret." } },
    { id: "outils", nom: { en: "Pinned tools", fr: "Outils épinglés" }, fichier: "outils.yaml", info: { en: "Each tool with the exact version pinned by the exported version.", fr: "Chaque outil avec la version exacte épinglée par la version exportée." } },
    { id: "blocs", nom: { en: "Blocks", fr: "Blocs" }, fichier: "blocs/*.md", info: { en: "The blocks the prompts cite, as read-only references: they live in the library.", fr: "Les blocs que citent les prompts, en références en lecture seule : ils vivent dans la bibliothèque." } },
    { id: "tests", nom: { en: "Tests", fr: "Tests" }, fichier: "tests/*.yaml", info: { en: "The scenarios, characters and behaviours of the test suite.", fr: "Les scénarios, personnages et comportements de la suite de tests." } },
];

const T = {
    titreExport: { en: "Export as files", fr: "Exporter en fichiers" },
    infoExport: {
        en: "A folder of readable files, to version at the client's and to replay from its CI. No key leaves. Format: YAML and Markdown files.",
        fr: "Un dossier de fichiers lisibles, à versionner chez le client et à relancer par sa CI. Aucune clé n'en sort. Format : fichiers YAML et Markdown.",
    },
    choisirContenu: { en: "Choose the content", fr: "Choisir le contenu" },
    auMoinsUn: { en: "Tick at least one item.", fr: "Cochez au moins un élément." },
    annuler: { en: "Cancel", fr: "Annuler" },
    exporter: { en: "Export", fr: "Exporter" },
    exportEnCours: { en: "Exporting...", fr: "Export..." },
    exporte: { en: "Files exported.", fr: "Fichiers exportés." },
    echecExport: { en: "Export failed. Try again.", fr: "L'export n'a pas abouti. Réessayez." },
    titreImport: { en: "Import files", fr: "Importer des fichiers" },
    infoImport: {
        en: "The import arrives in a draft of the open branch: nothing changes online until you publish. Running the same import again creates no duplicate.",
        fr: "L'import arrive dans un brouillon de la branche ouverte : rien ne change en ligne tant que vous ne publiez pas. Relancer le même import ne crée aucun doublon.",
    },
    choisirDossier: { en: "Choose the agent's folder", fr: "Choisir le dossier de l'agent" },
    boutonDossier: { en: "Choose a folder", fr: "Choisir un dossier" },
    aucunFichier: { en: "No recognised file in this folder.", fr: "Aucun fichier reconnu dans ce dossier." },
    fichier: { en: "File", fr: "Fichier" },
    effet: { en: "Effect", fr: "Effet" },
    difference: { en: "Difference", fr: "Différence" },
    retour: { en: "Back", fr: "Retour" },
    importer: { en: "Import into the draft", fr: "Importer dans le brouillon" },
    importEnCours: { en: "Importing...", fr: "Import..." },
    echecApercu: { en: "The folder could not be read. Check that it is an exported agent.", fr: "Le dossier n'a pas pu être lu. Vérifiez que c'est un agent exporté." },
    echecImport: { en: "Import failed. Nothing was written. Try again.", fr: "L'import n'a pas abouti. Rien n'a été écrit. Réessayez." },
    rien: { en: "Nothing changes: the draft already has these files.", fr: "Rien ne change : le brouillon a déjà ces fichiers." },
};

const EFFETS: Record<string, { etat: "fini" | "publie" | "attente" | "brouillon"; nom: Texte }> = {
    inchange: { etat: "fini", nom: { en: "unchanged", fr: "inchangé" } },
    ajoute: { etat: "publie", nom: { en: "added", fr: "ajouté" } },
    modifie: { etat: "attente", nom: { en: "changed", fr: "modifié" } },
    retire: { etat: "brouillon", nom: { en: "kept (not in the folder)", fr: "gardé (absent du dossier)" } },
};

const nomDeDossier = (nom: string) => nom.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "agent";

export function FenetreExportFichiers({ agentId, nom, fermer }: { agentId: number; nom: string; fermer: () => void }) {
    const { t } = useLangue();
    const [coches, setCoches] = useState<string[]>(CONTENUS.map((c) => c.id));
    const [envoi, setEnvoi] = useState(false);
    const [erreur, setErreur] = useState<string | null>(null);

    const exporter = async () => {
        setEnvoi(true);
        setErreur(null);
        const r = await exporterEnFichiersApiV1AgentFichiersWorkflowIdExportGet({
            path: { workflow_id: agentId },
            query: { format: "zip", contenus: coches.join(",") },
            parseAs: "blob",
        });
        setEnvoi(false);
        if (r.error || !(r.data instanceof Blob)) return setErreur(echecAffiche(r.error, T.echecExport));
        const url = URL.createObjectURL(r.data);
        const lien = document.createElement("a");
        lien.href = url;
        lien.download = `${nomDeDossier(nom)}.zip`;
        document.body.appendChild(lien);
        lien.click();
        document.body.removeChild(lien);
        URL.revokeObjectURL(url);
        notifier.succes(T.exporte);
        fermer();
    };

    return (
        <Dialog open onOpenChange={(o) => !o && fermer()}>
            <DialogContent className="sm:max-w-lg" data-testid="fenetre-export-fichiers">
                <DialogTitle className="flex items-center gap-2">
                    {t(T.titreExport)}
                    <Info>{t(T.infoExport)}</Info>
                </DialogTitle>
                <DialogDescription className="sr-only">{t(T.choisirContenu)}</DialogDescription>
                <ul className="divide-y text-sm">
                    {CONTENUS.map((c) => (
                        <li key={c.id}>
                            <label className="flex cursor-pointer items-center gap-3 py-2.5">
                                <Checkbox
                                    checked={coches.includes(c.id)}
                                    aria-label={t(c.nom)}
                                    onCheckedChange={(v) => setCoches((x) => (v === true ? [...x, c.id] : x.filter((y) => y !== c.id)))}
                                />
                                <span className="flex flex-1 items-center gap-1.5">
                                    {t(c.nom)}
                                    <Info>{t(c.info)}</Info>
                                </span>
                                <code className="text-xs text-muted-foreground">{c.fichier}</code>
                            </label>
                        </li>
                    ))}
                </ul>
                <p className="text-xs text-muted-foreground">
                    {coches.length ? `${coches.length} / ${CONTENUS.length}` : t(T.auMoinsUn)}
                </p>
                {erreur && (
                    <p role="alert" className="text-sm text-destructive">
                        {erreur}
                    </p>
                )}
                <div className="flex justify-end gap-2">
                    <Button variant="outline" onClick={fermer}>
                        {t(T.annuler)}
                    </Button>
                    <Button disabled={!coches.length || envoi} onClick={() => void exporter()}>
                        {envoi ? t(T.exportEnCours) : t(T.exporter)}
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}

type Ligne = { fichier: string; effet: string; detail?: string | null };

/** Les fichiers d'un dossier choisi : chemin relatif au dossier (le premier segment est le nom du dossier), texte lu ici. */
export async function lireLeDossier(liste: FileList): Promise<Record<string, string>> {
    const fichiers: Record<string, string> = {};
    for (const f of Array.from(liste)) {
        const relatif = (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name;
        const chemin = relatif.includes("/") ? relatif.split("/").slice(1).join("/") : relatif;
        if (/\.(yaml|md)$/.test(chemin)) fichiers[chemin] = await f.text();
    }
    return fichiers;
}

export function FenetreImportFichiers({ agentId, fermer, apres }: { agentId: number; fermer: () => void; apres?: () => void }) {
    const { t } = useLangue();
    const choix = useRef<HTMLInputElement>(null);
    const [dossier, setDossier] = useState<{ nom: string; fichiers: Record<string, string>; lignes: Ligne[] } | null>(null);
    const [aucun, setAucun] = useState(false);
    const [envoi, setEnvoi] = useState(false);
    const [erreur, setErreur] = useState<string | null>(null);

    const choisi = async (liste: FileList | null) => {
        setAucun(false);
        setErreur(null);
        if (!liste || liste.length === 0) return;
        const fichiers = await lireLeDossier(liste);
        const premier = (liste[0] as File & { webkitRelativePath?: string }).webkitRelativePath ?? "";
        if (!Object.keys(fichiers).length) return setAucun(true);
        const r = await importerDesFichiersApiV1AgentFichiersWorkflowIdImportPost({ path: { workflow_id: agentId }, body: { fichiers, appliquer: false } });
        if (r.error || !r.data) return setErreur(echecAffiche(r.error, T.echecApercu));
        setDossier({ nom: premier.split("/")[0] || "", fichiers, lignes: r.data.fichiers });
    };

    const importer = async () => {
        if (!dossier) return;
        setEnvoi(true);
        setErreur(null);
        const r = await importerDesFichiersApiV1AgentFichiersWorkflowIdImportPost({ path: { workflow_id: agentId }, body: { fichiers: dossier.fichiers, appliquer: true } });
        setEnvoi(false);
        if (r.error || !r.data) return setErreur(echecAffiche(r.error, T.echecImport));
        const changes = r.data.fichiers.filter((l) => l.effet === "ajoute" || l.effet === "modifie").length;
        notifier.succes({ fr: `${changes} fichier(s) importé(s) dans le brouillon.`, en: `${changes} file(s) imported into the draft.` });
        const avertis = (r.data.avertissements ?? []).length;
        if (avertis)
            notifier.avertissement({
                fr: `${avertis} point(s) à vérifier : un outil ou un bloc du dossier est absent ici.`,
                en: `${avertis} point(s) to check: a tool or a block of the folder is missing here.`,
            });
        apres?.();
        fermer();
    };

    const changes = dossier ? dossier.lignes.filter((l) => l.effet === "ajoute" || l.effet === "modifie").length : 0;
    return (
        <Dialog open onOpenChange={(o) => !o && fermer()}>
            <DialogContent className="sm:max-w-xl" data-testid="fenetre-import-fichiers">
                <DialogTitle className="flex items-center gap-2">
                    {t(T.titreImport)}
                    <Info>{t(T.infoImport)}</Info>
                </DialogTitle>
                <DialogDescription className="sr-only">{t(T.choisirDossier)}</DialogDescription>
                {/* Un champ de fichier caché, un bouton visible (convention de l'écran) ; `webkitdirectory` ouvre un dossier. */}
                <input
                    ref={choix}
                    type="file"
                    className="hidden"
                    data-testid="choix-du-dossier"
                    aria-label={t(T.boutonDossier)}
                    multiple
                    // @ts-expect-error -- attribut non standard mais pris en charge par les navigateurs
                    webkitdirectory=""
                    onChange={(e) => void choisi(e.target.files)}
                />
                {!dossier ? (
                    <div className="flex flex-col items-center gap-3 py-8 text-center">
                        <FolderOpen className="size-8" strokeWidth={1.75} />
                        <p className="text-base font-semibold">{t(T.choisirDossier)}</p>
                        <Button variant="outline" onClick={() => choix.current?.click()}>
                            {t(T.boutonDossier)}
                        </Button>
                        {aucun && <p className="text-xs text-destructive">{t(T.aucunFichier)}</p>}
                        {erreur && (
                            <p role="alert" className="text-xs text-destructive">
                                {erreur}
                            </p>
                        )}
                    </div>
                ) : (
                    <div>
                        <p className="flex items-center gap-2 pb-1 text-sm text-muted-foreground">
                            <FileText className="size-4" /> {dossier.nom}/ · {changes === 0 ? t(T.rien) : `${changes}`}
                        </p>
                        <div className="max-h-[50vh] overflow-auto">
                            <Tableau colonnes={[{ titre: t(T.fichier) }, { titre: t(T.effet) }, { titre: t(T.difference) }]}>
                                {dossier.lignes.map((l) => {
                                    const effet = EFFETS[l.effet] ?? EFFETS.inchange;
                                    return (
                                        <Ligne key={l.fichier}>
                                            <Cellule principale>{l.fichier}</Cellule>
                                            <Cellule>
                                                <PointEtat etat={effet.etat}>{t(effet.nom)}</PointEtat>
                                            </Cellule>
                                            <Cellule className="text-xs">{l.detail ?? ""}</Cellule>
                                        </Ligne>
                                    );
                                })}
                            </Tableau>
                        </div>
                        {erreur && (
                            <p role="alert" className="pt-2 text-sm text-destructive">
                                {erreur}
                            </p>
                        )}
                    </div>
                )}
                <div className="flex justify-end gap-2">
                    <Button variant="outline" onClick={dossier ? () => setDossier(null) : fermer}>
                        {dossier ? t(T.retour) : t(T.annuler)}
                    </Button>
                    {dossier && (
                        <Button disabled={envoi || changes === 0} onClick={() => void importer()}>
                            {envoi ? t(T.importEnCours) : t(T.importer)}
                        </Button>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
}
