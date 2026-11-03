"use client";

/**
 * [.mark] U3 ter (E64, E66, E67) : le créateur de VARIABLE, qui remplace la fenêtre des objets.
 *
 * À gauche, « Quel genre de variable ? » (mot, nombre, oui ou non, date, liste, tableau), son nom (libellé, nom technique
 * calculé, description pour le client, qui la tient à jour) et sa valeur adaptée au genre. À droite, en direct :
 * l'étiquette, une phrase de prompt, le texte que reçoit l'agent avec la barre du plafond, ce que voit le client.
 *
 * Le genre se range dans les formes existantes des objets (`genres.ts`) : même plafond, même contrôle côté serveur
 * (`POST`/`PUT /organizations/objets`), son refus est montré tel quel. Un tableau se règle dans sa propre fenêtre
 * (`EditeurDeTableau`, E67), la même que celle du portail.
 */
import { Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import {
    deleteObjetApiV1OrganizationsObjetsObjetIdDelete,
    postObjetApiV1OrganizationsObjetsPost,
    putObjetApiV1OrganizationsObjetsObjetIdPut,
} from "@/client/sdk.gen";
import type { LigneObjet, ObjetAgent, ObjetEnvoye } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { detailFromError } from "@/lib/apiError";
import { cn } from "@/lib/utils";

import { type Texte, useLangue } from "../langue/langue";
import { CadreModale, L } from "../reglages-agent/phrases/cadre";
import { EditeurDeTableau, JaugeCaracteres, ResumeTableau } from "./EditeurDeTableau";
import { COLONNE_DE_LISTE, formeDuGenre, type Genre, genreDe, GENRES, nomTechnique, phraseDePrompt, TYPE_DU_GENRE } from "./genres";
import { type Tableau,texteRecu } from "./tableau-logique";
import { COULEUR_SOURCE } from "./texte-etiquettes";

const MOTIF_NOM = /^[a-z][a-z0-9_]{0,62}$/;
const TOUS = "__tous__";

const NOM_GENRE: Record<Genre, Texte> = {
    mot: { en: "Word or sentence", fr: "Mot ou phrase" },
    nombre: { en: "Number or amount", fr: "Nombre ou montant" },
    oui_non: { en: "Yes or no", fr: "Oui ou non" },
    date: { en: "Date", fr: "Date" },
    liste: { en: "List", fr: "Liste" },
    tableau: { en: "Table", fr: "Tableau" },
};

export interface Brouillon {
    genre: Genre;
    libelle: string;
    nom: string;
    nomPersonnalise: boolean;
    description: string;
    etablissement: string | null;
    valeur: string;
    montant: boolean;
    puces: string[];
    tableau: Tableau;
}

const depart = (objet: ObjetAgent | null): Brouillon => {
    if (!objet) {
        return { genre: "mot", libelle: "", nom: "", nomPersonnalise: false, description: "", etablissement: null, valeur: "", montant: false, puces: [""], tableau: { colonnes: [], lignes: [] } };
    }
    const genre = genreDe(objet);
    const colonnes = (objet.colonnes ?? []).map((c) => ({ ...c }));
    const lignes = (objet.lignes ?? []).map((l) => ({ ...l, valeurs: { ...(l.valeurs ?? {}) } }));
    return {
        genre,
        libelle: objet.libelle,
        nom: objet.nom,
        nomPersonnalise: true,
        description: objet.description ?? "",
        etablissement: objet.etablissement ?? null,
        valeur: objet.valeur ?? "",
        montant: objet.type === "montant",
        puces: genre === "liste" && colonnes[0] ? lignes.map((l) => l.valeurs?.[colonnes[0].libelle] ?? "") : [""],
        tableau: { colonnes, lignes },
    };
};

/** Ce qui part au serveur : le genre rangé dans la forme et le type existants. Pur, testé. */
export const objetEnvoye = (b: Brouillon, objet: ObjetAgent | null): ObjetEnvoye => {
    const base = { nom: b.nom, libelle: b.libelle, description: b.description.trim() ? b.description : null, etablissement: b.etablissement };
    const forme = formeDuGenre(b.genre);
    if (forme === "valeur") {
        const type = b.genre === "nombre" ? (b.montant ? "montant" : "nombre") : TYPE_DU_GENRE[b.genre as "mot" | "oui_non" | "date"];
        return { ...base, forme, type, valeur: b.valeur, colonnes: [], lignes: [] };
    }
    if (b.genre === "liste") {
        const existante = objet?.colonnes?.[0];
        const colonne = existante ? { ...existante } : { libelle: COLONNE_DE_LISTE, type: "texte" as const, ordre: 1, pose_par: "mark" as const };
        const lignes = b.puces
            .filter((p) => p.trim() !== "")
            .map((p, i) => ({ ...(objet?.lignes?.[i]?.id ? { id: objet.lignes[i].id } : {}), ordre: i + 1, valeurs: { [colonne.libelle]: p } }) as LigneObjet);
        return { ...base, forme, type: null, valeur: null, colonnes: [colonne], lignes };
    }
    return {
        ...base,
        forme,
        type: null,
        valeur: null,
        colonnes: b.tableau.colonnes.map((c, i) => ({ ...c, ordre: i + 1 })),
        lignes: b.tableau.lignes.map((l, i) => ({ ...l, ordre: i + 1 })),
    };
};

export const CreateurVariable = ({
    objet,
    plafond,
    etablissements,
    onFermer,
}: {
    /** `null` : une variable neuve. */
    objet: ObjetAgent | null;
    plafond: number;
    etablissements: Array<{ id: string; nom: string }>;
    /** `true` : quelque chose a été enregistré ou supprimé (la section relit). */
    onFermer: (change: boolean) => void;
}) => {
    const { t } = useLangue();
    const [b, setB] = useState<Brouillon>(() => depart(objet));
    const [erreur, setErreur] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);
    const [tableauOuvert, setTableauOuvert] = useState(false);
    const poser = (partie: Partial<Brouillon>) => setB((avant) => ({ ...avant, ...partie }));
    const boutonGenre = (g: Genre) => (
        <button
            key={g}
            type="button"
            data-genre={g}
            aria-pressed={b.genre === g}
            disabled={Boolean(objet) && formeDuGenre(g) !== formeDuGenre(b.genre)}
            onClick={() => poser({ genre: g })}
            className={cn("cursor-pointer rounded-md border px-3 py-1.5 text-sm hover:font-medium disabled:cursor-not-allowed disabled:opacity-40", b.genre === g && "border-primary bg-muted font-medium")}
        >
            {t(NOM_GENRE[g])}
        </button>
    );

    const envoye = useMemo(() => objetEnvoye(b, objet), [b, objet]);
    const recu = useMemo(() => texteRecu({ colonnes: envoye.colonnes ?? [], lignes: envoye.lignes ?? [] }), [envoye]);
    const texte = envoye.forme === "valeur" ? (envoye.valeur ?? "") : recu;
    const taille = texte.length;

    const fautes: string[] = [];
    if (!MOTIF_NOM.test(b.nom)) fautes.push(t({ en: "Technical name: lower case, digits, underscores, starting with a letter.", fr: "Nom technique : minuscules, chiffres, soulignés, en commençant par une lettre." }));
    if (!b.libelle.trim()) fautes.push(t({ en: "The label is empty.", fr: "Le libellé est vide." }));
    if (b.genre === "tableau" && b.tableau.colonnes.length === 0) fautes.push(t({ en: "A table needs at least one column.", fr: "Un tableau a besoin d'au moins une colonne." }));
    if (taille > plafond) fautes.push(t({ en: `The agent would receive ${taille} characters, over the ceiling of ${plafond}.`, fr: `L'agent recevrait ${taille} caractères, au-delà du plafond de ${plafond}.` }));

    const enregistrer = async () => {
        if (fautes.length > 0 || enCours) return;
        setEnCours(true);
        setErreur(null);
        try {
            const reponse = objet
                ? await putObjetApiV1OrganizationsObjetsObjetIdPut({ path: { objet_id: objet.id }, body: envoye })
                : await postObjetApiV1OrganizationsObjetsPost({ body: envoye });
            if (reponse.error) {
                setErreur(detailFromError(reponse.error, "Variable refused"));
                return;
            }
            onFermer(true);
        } catch {
            setErreur("Variables: the server did not answer");
        } finally {
            setEnCours(false);
        }
    };

    const supprimer = async () => {
        if (!objet || enCours) return;
        setEnCours(true);
        try {
            const reponse = await deleteObjetApiV1OrganizationsObjetsObjetIdDelete({ path: { objet_id: objet.id } });
            if (reponse.error) {
                setErreur(detailFromError(reponse.error, "Variable not deleted"));
                return;
            }
            onFermer(true);
        } finally {
            setEnCours(false);
        }
    };

    if (tableauOuvert) {
        return (
            <EditeurDeTableau
                tableau={b.tableau}
                plafond={plafond}
                onAnnuler={() => setTableauOuvert(false)}
                onValider={(tableau) => {
                    poser({ tableau });
                    setTableauOuvert(false);
                }}
            />
        );
    }

    return (
        <CadreModale
            identifiant="variable"
            titre={objet ? objet.libelle : t({ en: "New variable", fr: "Nouvelle variable" })}
            description={t({
                en: "The agent receives it as {{technical name}}, in every prompt and sentence that names it. The client keeps its content up to date in the portal.",
                fr: "L'agent la reçoit en {{nom technique}}, dans chaque prompt et chaque phrase qui la nomme. Le client en tient le contenu à jour dans le portail.",
            })}
            onFermer={() => onFermer(false)}
            pied={
                <>
                    <div>
                        {objet && (
                            <Button variant="ghost" className="text-destructive" disabled={enCours} onClick={() => void supprimer()} data-testid="supprimer-objet">
                                <Trash2 className="h-4 w-4" /> {t({ en: "Delete", fr: "Supprimer" })}
                            </Button>
                        )}
                    </div>
                    <div className="flex gap-2">
                        <Button variant="outline" onClick={() => onFermer(false)}>
                            {t({ en: "Cancel", fr: "Annuler" })}
                        </Button>
                        <Button disabled={enCours || fautes.length > 0} onClick={() => void enregistrer()} data-testid="enregistrer-objet">
                            {t({ en: "Save", fr: "Enregistrer" })}
                        </Button>
                    </div>
                </>
            }
        >
            <div className="grid gap-6 md:grid-cols-[1fr_280px]">
                <div className="space-y-4">
                    <div className="space-y-2" data-reglage="forme">
                        <p className="text-sm font-medium">{t({ en: "What kind of variable?", fr: "Quel genre de variable ?" })}</p>
                        <div className="flex flex-wrap gap-2">
                            <span className="flex flex-wrap gap-2" data-reglage="type">
                                {GENRES.filter((g) => formeDuGenre(g) === "valeur").map((g) => boutonGenre(g))}
                            </span>
                            {GENRES.filter((g) => formeDuGenre(g) === "liste").map((g) => boutonGenre(g))}
                        </div>
                    </div>
                    <L label={t({ en: "Label", fr: "Libellé" })} nom="libelle">
                        <span data-reglage="libelle" className="w-full">
                            <Input
                                id="objet-libelle"
                                aria-label={t({ en: "Label", fr: "Libellé" })}
                                value={b.libelle}
                                onChange={(e) => poser({ libelle: e.target.value, ...(b.nomPersonnalise || objet ? {} : { nom: nomTechnique(e.target.value) }) })}
                            />
                        </span>
                    </L>
                    <L label={t({ en: "Technical name", fr: "Nom technique" })} nom="nom" aide={t({ en: "What the prompts write between {{ }}. Worked out from the label.", fr: "Ce que les prompts écrivent entre {{ }}. Calculé depuis le libellé." })}>
                        <span data-reglage="nom" className="w-full">
                            <Input id="objet-nom" aria-label={t({ en: "Technical name", fr: "Nom technique" })} value={b.nom} onChange={(e) => poser({ nom: e.target.value, nomPersonnalise: true })} className="font-mono" />
                        </span>
                    </L>
                    <L label={t({ en: "Description", fr: "Description" })} nom="description" aide={t({ en: "Shown to the client, to say what it is for.", fr: "Montrée au client, pour dire à quoi elle sert." })}>
                        <span data-reglage="description" className="w-full">
                            <Textarea id="objet-description" aria-label={t({ en: "Description", fr: "Description" })} value={b.description} onChange={(e) => poser({ description: e.target.value })} rows={2} />
                        </span>
                    </L>
                    {(etablissements.length > 1 || b.etablissement) && (
                        <L label={t({ en: "Kept up to date by", fr: "Qui la tient à jour" })} nom="etablissement">
                            <span data-reglage="etablissement">
                                <Select value={b.etablissement ?? TOUS} onValueChange={(v: string) => poser({ etablissement: v === TOUS ? null : v })}>
                                    <SelectTrigger id="objet-etablissement" className="w-64" aria-label={t({ en: "Kept up to date by", fr: "Qui la tient à jour" })}>
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value={TOUS}>{t({ en: "All establishments", fr: "Tous les établissements" })}</SelectItem>
                                        {etablissements.map((e) => (
                                            <SelectItem key={e.id} value={e.id}>
                                                {e.nom}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </span>
                        </L>
                    )}
                    <div className="space-y-2" data-reglage="valeur">
                        <p className="text-sm font-medium">{t({ en: "Its value", fr: "Sa valeur" })}</p>
                        {(b.genre === "mot" || b.genre === "nombre" || b.genre === "date") && (
                            <div className="flex items-center gap-2">
                                <Input
                                    id="objet-valeur"
                                    aria-label={t({ en: "Value", fr: "Valeur" })}
                                    type={b.genre === "date" ? "date" : "text"}
                                    inputMode={b.genre === "nombre" ? "decimal" : undefined}
                                    value={b.valeur}
                                    onChange={(e) => poser({ valeur: e.target.value })}
                                />
                                {b.genre === "nombre" && (
                                    <label className="flex shrink-0 items-center gap-1 text-sm">
                                        <input type="checkbox" checked={b.montant} onChange={(e) => poser({ montant: e.target.checked })} data-testid="montant" />
                                        {t({ en: "Amount (EUR)", fr: "Montant (€)" })}
                                    </label>
                                )}
                            </div>
                        )}
                        {b.genre === "oui_non" && (
                            <Select value={b.valeur || "oui"} onValueChange={(v: string) => poser({ valeur: v })}>
                                <SelectTrigger className="w-40" aria-label={t({ en: "Value", fr: "Valeur" })}>
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="oui">oui</SelectItem>
                                    <SelectItem value="non">non</SelectItem>
                                </SelectContent>
                            </Select>
                        )}
                        {b.genre === "liste" && (
                            <div className="space-y-2" data-puces data-reglage="lignes">
                                <p className="text-xs text-muted-foreground" data-reglage="colonnes">
                                    {t({ en: "One column:", fr: "Une seule colonne :" })} {objet?.colonnes?.[0]?.libelle ?? COLONNE_DE_LISTE}
                                </p>
                                {b.puces.map((p, i) => (
                                    <div key={i} className="flex items-center gap-2">
                                        <span aria-hidden>•</span>
                                        <Input aria-label={`${t({ en: "Item", fr: "Élément" })} ${i + 1}`} value={p} onChange={(e) => poser({ puces: b.puces.map((x, j) => (j === i ? e.target.value : x)) })} className="h-9" />
                                        <Button variant="ghost" size="icon" aria-label={`${t({ en: "Remove item", fr: "Retirer l'élément" })} ${i + 1}`} onClick={() => poser({ puces: b.puces.filter((_, j) => j !== i) })}>
                                            <Trash2 className="h-4 w-4" />
                                        </Button>
                                    </div>
                                ))}
                                <Button variant="ghost" size="sm" onClick={() => poser({ puces: [...b.puces, ""] })} data-testid="ajouter-puce">
                                    <Plus className="h-3.5 w-3.5" /> {t({ en: "Add an item", fr: "Ajouter un élément" })}
                                </Button>
                            </div>
                        )}
                        {b.genre === "tableau" && <ResumeTableau tableau={b.tableau} plafond={plafond} onConfigurer={() => setTableauOuvert(true)} />}
                    </div>
                    {(fautes.length > 0 || erreur) && (
                        <div className="space-y-1 text-sm text-destructive" role="alert" data-testid="erreur-objet">
                            {fautes.map((f) => (
                                <p key={f}>{f}</p>
                            ))}
                            {erreur && <p>{erreur}</p>}
                        </div>
                    )}
                </div>
                <aside className="space-y-4 rounded-md bg-muted/40 p-3 text-sm" data-apercu-variable>
                    <div className="space-y-1">
                        <p className="text-xs font-medium text-muted-foreground">{t({ en: "The tag", fr: "L'étiquette" })}</p>
                        <span className="inline-block rounded px-1.5 text-xs leading-5 text-white" style={{ background: COULEUR_SOURCE.entreprise }} data-testid="apercu-etiquette">
                            {b.libelle || b.nom || "…"}
                        </span>
                    </div>
                    <div className="space-y-1">
                        <p className="text-xs font-medium text-muted-foreground">{t({ en: "A prompt sentence", fr: "Une phrase de prompt" })}</p>
                        <p className="whitespace-pre-wrap" data-testid="apercu-phrase">{t(phraseDePrompt(b.genre, b.nom))}</p>
                    </div>
                    <div className="space-y-1">
                        <p className="text-xs font-medium text-muted-foreground">{t({ en: "What the agent receives", fr: "Ce que reçoit l'agent" })}</p>
                        <p className="whitespace-pre-wrap font-mono text-xs" data-testid="apercu-recu">{texte || "—"}</p>
                        <JaugeCaracteres taille={taille} plafond={plafond} />
                    </div>
                    <div className="space-y-1">
                        <p className="text-xs font-medium text-muted-foreground">{t({ en: "What the client sees", fr: "Ce que voit le client" })}</p>
                        {envoye.forme === "liste" ? (
                            <p className="text-xs" data-testid="apercu-client">
                                {(envoye.lignes ?? []).slice(0, 5).map((l, i) => (
                                    <span key={i} className="block">
                                        {(envoye.colonnes ?? []).map((c) => l.valeurs?.[c.libelle] ?? "").join(" | ")}
                                    </span>
                                ))}
                                {(envoye.lignes ?? []).length > 5 && <span className="block text-muted-foreground">{t({ en: `… and ${(envoye.lignes ?? []).length - 5} more lines`, fr: `… et ${(envoye.lignes ?? []).length - 5} autres lignes` })}</span>}
                            </p>
                        ) : (
                            <p className="text-xs" data-testid="apercu-client">{b.valeur || "—"}</p>
                        )}
                    </div>
                </aside>
            </div>
        </CadreModale>
    );
};
