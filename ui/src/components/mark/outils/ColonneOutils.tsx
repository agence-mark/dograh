"use client";

/**
 * [.mark] Module Restauration, lot 13 (F9) : la colonne de gauche de l'écran Outils (Tous les outils, Dossiers et sous-dossiers,
 * Kits d'outils, Simulateurs au Labo seulement), la vue d'un kit et « Régler le kit » (panneau de droite).
 * S'appuie sur les routes du lot 11 ; les kits sont réservés à l'équipe au Labo : ailleurs, la section reste vide.
 */
import { Boxes, ChevronRight, Folder, FolderPlus, LayoutGrid, MoreHorizontal, Plus, Store, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";

import type { ToolResponse } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { useLangue } from "../langue/langue";
import { notifier } from "../notifications";
import { Confirmer } from "../restauration/commun";
import { Champs, FenetreOnglets, LigneChamp, Section } from "../studio/fenetre-onglets";
import { Liste } from "../studio/liste";
import { Marque } from "../studio/marques";
import { Cellule, Ligne, Tableau } from "../studio/tableau";
import {
    ajouterAuKit, appliquerLeKit, creerUnDossier, creerUnKit, type Dossier, type Kit, modifierUnKit, renommerUnDossier,
    retirerDuKit, supprimerUnDossier, supprimerUnKit,
} from "./donnees-outils";

export type Vue = { sorte: "tous" } | { sorte: "dossier"; id: number } | { sorte: "kit"; id: number } | { sorte: "simulateurs" };

const ECHEC = { fr: "Action non faite. Réessayez.", en: "Action not done. Try again." };

export function ColonneOutils({
    vue, choisir, dossiers, kits, laboSimulateurs, relire,
}: {
    vue: Vue;
    choisir: (v: Vue) => void;
    dossiers: Dossier[];
    kits: Kit[] | null;
    laboSimulateurs: boolean;
    relire: () => void;
}) {
    const { t } = useLangue();
    const [nouveau, setNouveau] = useState<{ sorte: "dossier" | "kit"; parent: number | null } | null>(null);
    const [nom, setNom] = useState("");
    const [renomme, setRenomme] = useState<Dossier | null>(null);
    const [supprime, setSupprime] = useState<Dossier | null>(null);

    const enfants = (parent: number | null) => dossiers.filter((d) => d.parent_id === parent);
    const item = (actif: boolean, onClick: () => void, icone: React.ReactNode, libelle: React.ReactNode, profondeur = 0, droite?: React.ReactNode) => (
        <div className="group flex items-center" style={{ paddingLeft: profondeur * 12 }}>
            <button
                type="button"
                onClick={onClick}
                className={`flex min-w-0 flex-1 cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted ${actif ? "bg-muted font-medium" : ""}`}
            >
                {icone}
                <span className="truncate">{libelle}</span>
            </button>
            {droite}
        </div>
    );
    const arbre = (parent: number | null, profondeur: number): React.ReactNode =>
        enfants(parent).map((d) => (
            <div key={d.id}>
                {item(
                    vue.sorte === "dossier" && vue.id === d.id,
                    () => choisir({ sorte: "dossier", id: d.id }),
                    profondeur > 0 ? <ChevronRight className="size-3.5 text-muted-foreground" /> : <Folder className="size-4 text-muted-foreground" />,
                    <>{d.name} <span className="tabular-nums text-muted-foreground">{d.tool_count}</span></>,
                    profondeur,
                    <span className="flex opacity-0 group-hover:opacity-100 focus-within:opacity-100">
                        <button type="button" className="cursor-pointer rounded p-1 text-muted-foreground hover:text-foreground" aria-label={t({ en: `Sub-folder of ${d.name}`, fr: `Sous-dossier de ${d.name}` })} onClick={() => { setNom(""); setNouveau({ sorte: "dossier", parent: d.id }); }}>
                            <FolderPlus className="size-3.5" />
                        </button>
                        <button type="button" className="cursor-pointer rounded p-1 text-muted-foreground hover:text-foreground" aria-label={t({ en: `Rename ${d.name}`, fr: `Renommer ${d.name}` })} onClick={() => { setNom(d.name); setRenomme(d); }}>
                            <MoreHorizontal className="size-3.5" />
                        </button>
                        <button type="button" className="cursor-pointer rounded p-1 text-muted-foreground hover:text-destructive" aria-label={t({ en: `Delete ${d.name}`, fr: `Supprimer ${d.name}` })} onClick={() => setSupprime(d)}>
                            <Trash2 className="size-3.5" />
                        </button>
                    </span>,
                )}
                {arbre(d.id, profondeur + 1)}
            </div>
        ));

    const valider = async () => {
        const n = nom.trim();
        if (!n) return;
        if (renomme) {
            const r = await renommerUnDossier(renomme.id, n);
            if (r.error) return notifier.echec(ECHEC);
            setRenomme(null);
        } else if (nouveau?.sorte === "dossier") {
            const r = await creerUnDossier(n, nouveau.parent);
            if (r.error) return notifier.echec(ECHEC);
            setNouveau(null);
        } else if (nouveau?.sorte === "kit") {
            const r = await creerUnKit(n);
            if (r.error || !r.data) return notifier.echec(ECHEC);
            setNouveau(null);
            choisir({ sorte: "kit", id: r.data.id });
        }
        notifier.succes({ fr: "Enregistré.", en: "Saved." });
        relire();
    };
    const titre = (libelle: string, action?: React.ReactNode) => (
        <div className="flex items-center justify-between px-2 pt-4 pb-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">
            {libelle}
            {action}
        </div>
    );

    return (
        <nav aria-label={t({ en: "Tool folders", fr: "Rangement des outils" })} className="w-56 shrink-0 space-y-0.5" data-colonne-outils>
            {item(vue.sorte === "tous", () => choisir({ sorte: "tous" }), <LayoutGrid className="size-4 text-muted-foreground" />, t({ en: "All tools", fr: "Tous les outils" }))}
            {titre(
                t({ en: "Folders", fr: "Dossiers" }),
                <button type="button" className="cursor-pointer text-muted-foreground hover:text-foreground" aria-label={t({ en: "New folder", fr: "Nouveau dossier" })} onClick={() => { setNom(""); setNouveau({ sorte: "dossier", parent: null }); }}>
                    <Plus className="size-3.5" />
                </button>,
            )}
            {dossiers.length === 0 && <p className="px-2 py-1 text-xs text-muted-foreground">{t({ en: "No folder yet.", fr: "Aucun dossier." })}</p>}
            {arbre(null, 0)}
            {kits !== null && (
                <>
                    {titre(
                        t({ en: "Tool kits", fr: "Kits d'outils" }),
                        <button type="button" className="cursor-pointer text-muted-foreground hover:text-foreground" aria-label={t({ en: "New kit", fr: "Nouveau kit" })} onClick={() => { setNom(""); setNouveau({ sorte: "kit", parent: null }); }}>
                            <Plus className="size-3.5" />
                        </button>,
                    )}
                    {kits.length === 0 && <p className="px-2 py-1 text-xs text-muted-foreground">{t({ en: "No kit yet.", fr: "Aucun kit." })}</p>}
                    {kits.map((k) => (
                        <div key={k.id}>
                            {item(vue.sorte === "kit" && vue.id === k.id, () => choisir({ sorte: "kit", id: k.id }), <Boxes className="size-4 text-muted-foreground" />, <>{k.name} <span className="tabular-nums text-muted-foreground">{k.items.length}</span></>)}
                        </div>
                    ))}
                </>
            )}
            {laboSimulateurs && (
                <>
                    {titre(t({ en: "Simulators", fr: "Simulateurs" }))}
                    {item(vue.sorte === "simulateurs", () => choisir({ sorte: "simulateurs" }), <Store className="size-4 text-muted-foreground" />, t({ en: "Till / POS", fr: "Caisse / POS" }))}
                </>
            )}
            {(nouveau || renomme) && (
                <div className="flex items-center gap-1 px-2 pt-2">
                    <Input
                        autoFocus
                        value={nom}
                        maxLength={100}
                        onChange={(e) => setNom(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === "Enter") void valider();
                            if (e.key === "Escape") { setNouveau(null); setRenomme(null); }
                        }}
                        aria-label={t({ en: "Name", fr: "Nom" })}
                        placeholder={nouveau?.sorte === "kit" ? t({ en: "Kit name", fr: "Nom du kit" }) : t({ en: "Folder name", fr: "Nom du dossier" })}
                        className="h-8"
                    />
                    <Button size="sm" className="cursor-pointer" onClick={() => void valider()}>{t({ en: "OK", fr: "OK" })}</Button>
                </div>
            )}
            {supprime && (
                <Confirmer
                    titre={t({ en: "Delete this folder?", fr: "Supprimer ce dossier ?" })}
                    texte={t({ en: "Its tools are not deleted: they go back to « All tools ».", fr: "Ses outils ne sont pas supprimés : ils retournent dans « Tous les outils »." })}
                    bouton={t({ en: "Delete folder", fr: "Supprimer le dossier" })}
                    fermer={() => setSupprime(null)}
                    valider={() => {
                        const d = supprime;
                        setSupprime(null);
                        void supprimerUnDossier(d.id).then((r) => {
                            if (r.error) return notifier.echec(ECHEC);
                            if (vue.sorte === "dossier" && vue.id === d.id) choisir({ sorte: "tous" });
                            notifier.succes({ fr: "Dossier supprimé.", en: "Folder deleted." });
                            relire();
                        });
                    }}
                />
            )}
        </nav>
    );
}

/** La vue d'un kit : mêmes rangées que la liste des outils, et « Régler le kit » à droite. */
export function VueKit({ kit, outils, dossiers, relire, apresSuppression }: { kit: Kit; outils: ToolResponse[]; dossiers: Dossier[]; relire: () => void; apresSuppression: () => void }) {
    const { t } = useLangue();
    const [regle, setRegle] = useState(false);
    return (
        <div className="min-w-0 flex-1 space-y-3">
            <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                    <h2 className="truncate text-lg font-medium">{kit.name}</h2>
                    {kit.description && <p className="truncate text-sm text-muted-foreground">{kit.description}</p>}
                </div>
                <Button variant="outline" className="cursor-pointer" onClick={() => setRegle(true)}>{t({ en: "Set up the kit", fr: "Régler le kit" })}</Button>
            </div>
            {kit.items.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">{t({ en: "No tool in this kit. Add one from a tool's « ⋯ » menu.", fr: "Aucun outil dans ce kit. Ajoutez-en un depuis le menu « ⋯ » d'un outil." })}</p>
            ) : (
                <Tableau colonnes={[{ titre: t({ en: "Tool", fr: "Outil" }) }, { titre: t({ en: "Type", fr: "Type" }), secondaire: 2 }, { titre: t({ en: "Version", fr: "Version" }), droite: true }]}>
                    {kit.items.map((i) => (
                        <Ligne key={i.id} onClick={() => setRegle(true)}>
                            <td className="py-3">
                                <span className="block font-medium">{i.name}</span>
                                {i.description && <span className="block max-w-80 truncate text-xs text-muted-foreground">{i.description}</span>}
                            </td>
                            <Cellule>{i.category}</Cellule>
                            <Cellule droite>v{i.version}</Cellule>
                        </Ligne>
                    ))}
                </Tableau>
            )}
            {regle && <PanneauKit kit={kit} outils={outils} dossiers={dossiers} fermer={() => setRegle(false)} relire={relire} apresSuppression={apresSuppression} />}
        </div>
    );
}

function PanneauKit({ kit, outils, dossiers, fermer, relire, apresSuppression }: { kit: Kit; outils: ToolResponse[]; dossiers: Dossier[]; fermer: () => void; relire: () => void; apresSuppression: () => void }) {
    const { t } = useLangue();
    const [nom, setNom] = useState(kit.name);
    const [description, setDescription] = useState(kit.description ?? "");
    const [ajout, setAjout] = useState("");
    const [cible, setCible] = useState("");
    const [sup, setSup] = useState(false);
    const dejaDans = useMemo(() => new Set(kit.items.map((i) => i.name)), [kit.items]);
    const ajoutables = outils.filter((o) => o.status === "active" && !dejaDans.has(o.name));
    const fait = (r: { error?: unknown }, ok: { fr: string; en: string }) => {
        if (r.error) return notifier.echec(ECHEC);
        notifier.succes(ok);
        relire();
    };
    return (
        <FenetreOnglets
            fermer={fermer}
            titre={kit.name}
            sous={`${kit.items.length} ${t({ en: "tools", fr: "outils" })}`}
            valider={t({ en: "Save", fr: "Enregistrer" })}
            modifie={nom !== kit.name || description !== (kit.description ?? "")}
            onValider={() => {
                void modifierUnKit(kit.id, { name: nom.trim() || kit.name, description: description.trim() || null }).then((r) => {
                    fait(r, { fr: "Kit enregistré.", en: "Kit saved." });
                    if (!r.error) fermer();
                });
            }}
            pied={<Button variant="ghost" size="sm" className="cursor-pointer text-destructive" onClick={() => setSup(true)}><Trash2 className="size-3.5" /> {t({ en: "Delete kit", fr: "Supprimer le kit" })}</Button>}
        >
            <Section titre={t({ en: "Kit", fr: "Kit" })}>
                <Champs>
                    <LigneChamp libelle={t({ en: "Name", fr: "Nom" })}><Input value={nom} maxLength={100} onChange={(e) => setNom(e.target.value)} className="h-8 w-64" /></LigneChamp>
                    <LigneChamp libelle={t({ en: "Description", fr: "Description" })}><Input value={description} maxLength={500} onChange={(e) => setDescription(e.target.value)} className="h-8 w-64" /></LigneChamp>
                </Champs>
            </Section>
            <Section titre={t({ en: "Tools in the kit", fr: "Outils du kit" })} info={t({ en: "The kit keeps its own copy of each tool, without what belongs to the organization.", fr: "Le kit garde sa propre copie de chaque outil, sans ce qui appartient à l'organisation." })}>
                {kit.items.length === 0 && <p className="py-2 text-sm text-muted-foreground">{t({ en: "No tools.", fr: "Aucun outil." })}</p>}
                <div className="divide-y">
                    {kit.items.map((i) => (
                        <div key={i.id} className="flex items-center gap-3 py-2.5">
                            <span className="min-w-0 flex-1 truncate text-sm font-medium">{i.name}</span>
                            <Marque ton="neutre">v{i.version}</Marque>
                            <button type="button" className="cursor-pointer text-muted-foreground hover:text-foreground" aria-label={t({ en: `Remove ${i.name}`, fr: `Retirer ${i.name}` })} onClick={() => void retirerDuKit(kit.id, i.id).then((r) => fait(r, { fr: "Outil retiré du kit.", en: "Tool removed from the kit." }))}>
                                <X className="size-4" />
                            </button>
                        </div>
                    ))}
                </div>
                <div className="flex items-center gap-2 pt-3">
                    <Liste className="w-64" libelle={t({ en: "Tool to add", fr: "Outil à ajouter" })} valeur={ajout} vide={t({ en: "Choose a tool", fr: "Choisir un outil" })} changer={setAjout} options={ajoutables.map((o) => ({ valeur: o.tool_uuid, libelle: o.name }))} />
                    <Button size="sm" variant="outline" className="cursor-pointer" disabled={!ajout} onClick={() => void ajouterAuKit(kit.id, ajout).then((r) => { setAjout(""); fait(r, { fr: "Outil ajouté au kit.", en: "Tool added to the kit." }); })}>
                        <Plus className="size-3.5" /> {t({ en: "Add", fr: "Ajouter" })}
                    </Button>
                </div>
            </Section>
            <Section titre={t({ en: "Apply to the organization", fr: "Appliquer à l'organisation" })} info={t({ en: "Creates the kit's tools here (those already present are kept), in the folder chosen.", fr: "Crée ici les outils du kit (ceux déjà présents sont gardés), dans le dossier choisi." })}>
                <div className="flex items-center gap-2">
                    <Liste className="w-64" libelle={t({ en: "Folder", fr: "Dossier" })} valeur={cible} vide={t({ en: "No folder", fr: "Sans dossier" })} changer={setCible} options={dossiers.map((d) => ({ valeur: String(d.id), libelle: d.name }))} />
                    <Button size="sm" className="cursor-pointer" onClick={() => void appliquerLeKit(kit.id, cible ? Number(cible) : null).then((r) => fait(r, { fr: `Kit appliqué (${r.data?.crees.length ?? 0} créés, ${r.data?.deja_presents ?? 0} déjà là).`, en: `Kit applied (${r.data?.crees.length ?? 0} created, ${r.data?.deja_presents ?? 0} already there).` }))}>
                        {t({ en: "Apply", fr: "Appliquer" })}
                    </Button>
                </div>
            </Section>
            {sup && (
                <Confirmer
                    titre={t({ en: "Delete this kit?", fr: "Supprimer ce kit ?" })}
                    texte={t({ en: "The tools already created from it keep working, without the kit's updates.", fr: "Les outils déjà créés à partir de lui continuent de fonctionner, sans les mises à jour du kit." })}
                    bouton={t({ en: "Delete kit", fr: "Supprimer le kit" })}
                    fermer={() => setSup(false)}
                    valider={() => void supprimerUnKit(kit.id).then((r) => { setSup(false); fait(r, { fr: "Kit supprimé.", en: "Kit deleted." }); if (!r.error) { fermer(); apresSuppression(); } })}
                />
            )}
        </FenetreOnglets>
    );
}
