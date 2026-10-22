"use client";

/**
 * [.mark] Chantier cloture-code-avant-migration, lot F7 (D106 à D117) : la MODALE d'un objet de l'agent, ouverte
 * par sa carte ou par « Ajouter un objet » (section « Objets » du thème Établissements). Modale CENTRÉE
 * (`CadreModale` du thème Phrases : en-tête fixe, corps qui défile, pied figé), jamais un panneau latéral.
 *
 * Elle travaille sur une COPIE : « Enregistrer » envoie l'objet entier à `POST`/`PUT /organizations/objets`, la base
 * du client le valide (type, ligne vide, plafond) et son refus est montré tel quel ; « Annuler » jette la copie.
 * ⛔ Aucun texte sans champ réel : chaque case est un champ de `ObjetEnvoye`, chaque nom un nom de la base.
 */
import { Lock, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import {
    deleteObjetApiV1OrganizationsObjetsObjetIdDelete,
    postObjetApiV1OrganizationsObjetsPost,
    putObjetApiV1OrganizationsObjetsObjetIdPut,
} from "@/client/sdk.gen";
import type { ColonneObjet, LigneObjet, ObjetAgent, ObjetEnvoye } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { detailFromError } from "@/lib/apiError";

import { type Texte, useLangue } from "../langue/langue";
import { CadreModale, L } from "../reglages-agent/phrases/cadre";

/** Les champs d'un objet montrés par la modale (l'inventaire d'organisation les compare au client généré). */
export const CHAMPS_OBJET = ["nom", "libelle", "description", "forme", "type", "valeur", "etablissement", "colonnes", "lignes"] as const;

type TypeObjet = NonNullable<ObjetEnvoye["type"]>;
const TYPES: TypeObjet[] = ["texte", "nombre", "montant", "oui_non", "date"];
const LIBELLE_TYPE: Record<TypeObjet, Texte> = {
    texte: { en: "Text", fr: "Texte" },
    nombre: { en: "Number", fr: "Nombre" },
    montant: { en: "Amount", fr: "Montant" },
    oui_non: { en: "Yes / no", fr: "Oui / non" },
    date: { en: "Date", fr: "Date" },
};
const TOUS = "__tous__";
const MOTIF_NOM = /^[a-z][a-z0-9_]{0,62}$/;

/** Le texte que reçoit l'agent : la même règle que `api/services/objets_agent/rendu.py` et `objet_agent_texte` (SQL). */
export const rendreObjet = (objet: Pick<ObjetEnvoye, "forme" | "valeur" | "colonnes" | "lignes">): string => {
    if (objet.forme === "valeur") return objet.valeur ?? "";
    const rang = (e: { ordre?: number; id?: number | null }) => [e.ordre ?? 0, e.id ?? Number.MAX_SAFE_INTEGER];
    const trier = <E extends { ordre?: number; id?: number | null }>(liste: E[]) =>
        [...liste].sort((a, b) => rang(a)[0] - rang(b)[0] || rang(a)[1] - rang(b)[1]);
    const colonnes = trier(objet.colonnes ?? []);
    if (colonnes.length === 0) return "";
    const entete = colonnes.map((c) => c.libelle).join(" | ");
    const lignes = trier(objet.lignes ?? []).map((l) => colonnes.map((c) => l.valeurs?.[c.libelle] ?? "").join(" | "));
    return [entete, ...lignes].join("\n");
};

const vide = (): ObjetEnvoye => ({ nom: "", libelle: "", description: "", forme: "valeur", type: "texte", valeur: "", etablissement: null, colonnes: [], lignes: [] });

const copieDe = (objet: ObjetAgent | null): ObjetEnvoye =>
    objet
        ? {
              nom: objet.nom,
              libelle: objet.libelle,
              description: objet.description ?? "",
              forme: objet.forme,
              type: objet.type ?? null,
              valeur: objet.valeur ?? "",
              etablissement: objet.etablissement ?? null,
              colonnes: (objet.colonnes ?? []).map((c) => ({ ...c })),
              lignes: (objet.lignes ?? []).map((l) => ({ ...l, valeurs: { ...(l.valeurs ?? {}) } })),
          }
        : vide();

export const ModaleObjet = ({
    objet,
    plafond,
    etablissements,
    onFermer,
}: {
    /** `null` : un objet neuf. */
    objet: ObjetAgent | null;
    plafond: number;
    etablissements: Array<{ id: string; nom: string }>;
    /** `true` : quelque chose a été enregistré ou supprimé (la section relit). */
    onFermer: (change: boolean) => void;
}) => {
    const { t } = useLangue();
    const [brouillon, setBrouillon] = useState<ObjetEnvoye>(() => copieDe(objet));
    const [erreur, setErreur] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);
    const taille = useMemo(() => rendreObjet(brouillon).length, [brouillon]);
    const poser = (partie: Partial<ObjetEnvoye>) => setBrouillon((avant) => ({ ...avant, ...partie }));
    const colonnes = brouillon.colonnes ?? [];
    const lignes = brouillon.lignes ?? [];

    const fautes: string[] = [];
    if (!MOTIF_NOM.test(brouillon.nom)) fautes.push(t({ en: "Technical name: lower case, digits, underscores, starting with a letter.", fr: "Nom technique : minuscules, chiffres, soulignés, en commençant par une lettre." }));
    if (!brouillon.libelle.trim()) fautes.push(t({ en: "The label is empty.", fr: "Le libellé est vide." }));
    if (brouillon.forme === "liste" && new Set(colonnes.map((c) => c.libelle.trim())).size !== colonnes.length)
        fautes.push(t({ en: "Two columns have the same label.", fr: "Deux colonnes ont le même libellé." }));
    if (colonnes.some((c) => !c.libelle.trim())) fautes.push(t({ en: "A column has no label.", fr: "Une colonne n'a pas de libellé." }));
    if (taille > plafond) fautes.push(t({ en: `The agent would receive ${taille} characters, over the ceiling of ${plafond}.`, fr: `L'agent recevrait ${taille} caractères, au-delà du plafond de ${plafond}.` }));

    const renommerColonne = (i: number, libelle: string) => {
        const ancien = colonnes[i].libelle;
        poser({
            colonnes: colonnes.map((c, j) => (j === i ? { ...c, libelle } : c)),
            lignes: lignes.map((l) => {
                const valeurs = { ...(l.valeurs ?? {}) };
                if (ancien in valeurs) {
                    valeurs[libelle] = valeurs[ancien];
                    delete valeurs[ancien];
                }
                return { ...l, valeurs };
            }),
        });
    };
    const retirerColonne = (i: number) => {
        const libelle = colonnes[i].libelle;
        poser({
            colonnes: colonnes.filter((_, j) => j !== i),
            lignes: lignes.map((l) => {
                const valeurs = { ...(l.valeurs ?? {}) };
                delete valeurs[libelle];
                return { ...l, valeurs };
            }),
        });
    };
    const ajouterColonne = () => {
        let n = colonnes.length + 1;
        while (colonnes.some((c) => c.libelle === `${t({ en: "Column", fr: "Colonne" })} ${n}`)) n += 1;
        const colonne: ColonneObjet = { libelle: `${t({ en: "Column", fr: "Colonne" })} ${n}`, type: "texte", ordre: colonnes.length + 1, pose_par: "mark" };
        poser({ colonnes: [...colonnes, colonne] });
    };
    const cellule = (i: number, libelle: string, valeur: string) =>
        poser({ lignes: lignes.map((l, j) => (j === i ? { ...l, valeurs: { ...(l.valeurs ?? {}), [libelle]: valeur } } : l)) });
    const ajouterLigne = () => poser({ lignes: [...lignes, { ordre: lignes.length + 1, valeurs: {} } as LigneObjet] });

    const envoi = (): ObjetEnvoye => ({
        ...brouillon,
        description: brouillon.description?.trim() ? brouillon.description : null,
        type: brouillon.forme === "valeur" ? brouillon.type ?? "texte" : null,
        valeur: brouillon.forme === "valeur" ? brouillon.valeur ?? "" : null,
        colonnes: brouillon.forme === "liste" ? colonnes.map((c, i) => ({ ...c, ordre: i + 1 })) : [],
        lignes: brouillon.forme === "liste" ? lignes.map((l, i) => ({ ...l, ordre: i + 1 })) : [],
    });

    const enregistrer = async () => {
        if (fautes.length > 0 || enCours) return;
        setEnCours(true);
        setErreur(null);
        try {
            const reponse = objet
                ? await putObjetApiV1OrganizationsObjetsObjetIdPut({ path: { objet_id: objet.id }, body: envoi() })
                : await postObjetApiV1OrganizationsObjetsPost({ body: envoi() });
            if (reponse.error) {
                setErreur(detailFromError(reponse.error, "Object refused"));
                return;
            }
            onFermer(true);
        } catch {
            setErreur("Objects: the server did not answer");
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
                setErreur(detailFromError(reponse.error, "Object not deleted"));
                return;
            }
            onFermer(true);
        } finally {
            setEnCours(false);
        }
    };

    return (
        <CadreModale
            identifiant="objet"
            titre={objet ? objet.libelle : t({ en: "New object", fr: "Nouvel objet" })}
            description={t({
                en: "The agent receives it as {{technical name}}, in every prompt and sentence that names it. The client keeps its content up to date in the portal.",
                fr: "L'agent le reçoit en {{nom technique}}, dans chaque prompt et chaque phrase qui le nomme. Le client en tient le contenu à jour dans le portail.",
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
            <div className="space-y-4">
                <L label={t({ en: "Technical name", fr: "Nom technique" })} nom="nom" aide={t({ en: "What the prompts write between {{ }}.", fr: "Ce que les prompts écrivent entre {{ }}." })}>
                    <span data-reglage="nom" className="w-full">
                        <Input id="objet-nom" aria-label={t({ en: "Technical name", fr: "Nom technique" })} value={brouillon.nom} onChange={(e) => poser({ nom: e.target.value })} className="font-mono" />
                    </span>
                </L>
                <L label={t({ en: "Label", fr: "Libellé" })} nom="libelle">
                    <span data-reglage="libelle" className="w-full">
                        <Input id="objet-libelle" aria-label={t({ en: "Label", fr: "Libellé" })} value={brouillon.libelle} onChange={(e) => poser({ libelle: e.target.value })} />
                    </span>
                </L>
                <L label={t({ en: "Description", fr: "Description" })} nom="description" aide={t({ en: "Shown to the client, to say what it is for.", fr: "Montrée au client, pour dire à quoi il sert." })}>
                    <span data-reglage="description" className="w-full">
                        <Textarea id="objet-description" aria-label={t({ en: "Description", fr: "Description" })} value={brouillon.description ?? ""} onChange={(e) => poser({ description: e.target.value })} rows={2} />
                    </span>
                </L>
                <L label={t({ en: "Scope", fr: "Portée" })} nom="etablissement">
                    <span data-reglage="etablissement">
                        <Select value={brouillon.etablissement ?? TOUS} onValueChange={(v: string) => poser({ etablissement: v === TOUS ? null : v })}>
                            <SelectTrigger id="objet-etablissement" className="w-64" aria-label={t({ en: "Scope", fr: "Portée" })}>
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
                <L label={t({ en: "Form", fr: "Forme" })} nom="forme" aide={objet ? t({ en: "The form of a saved object does not change.", fr: "La forme d'un objet enregistré ne change pas." }) : undefined}>
                    <span data-reglage="forme">
                        <Select value={brouillon.forme} disabled={Boolean(objet)} onValueChange={(v: string) => poser({ forme: v as ObjetEnvoye["forme"] })}>
                            <SelectTrigger id="objet-forme" className="w-64" aria-label={t({ en: "Form", fr: "Forme" })}>
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="valeur">{t({ en: "Single value", fr: "Valeur simple" })}</SelectItem>
                                <SelectItem value="liste">{t({ en: "List (columns and lines)", fr: "Liste (colonnes et lignes)" })}</SelectItem>
                            </SelectContent>
                        </Select>
                    </span>
                </L>
                {brouillon.forme === "valeur" ? (
                    <>
                        <L label={t({ en: "Type", fr: "Type" })} nom="type">
                            <span data-reglage="type">
                                <Select value={brouillon.type ?? "texte"} onValueChange={(v: string) => poser({ type: v as TypeObjet })}>
                                    <SelectTrigger id="objet-type" className="w-64" aria-label={t({ en: "Type", fr: "Type" })}>
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {TYPES.map((ty) => (
                                            <SelectItem key={ty} value={ty}>
                                                {t(LIBELLE_TYPE[ty])}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </span>
                        </L>
                        <L label={t({ en: "Value", fr: "Valeur" })} nom="valeur" aide={brouillon.type === "oui_non" ? t({ en: "« oui » or « non ».", fr: "« oui » ou « non »." }) : brouillon.type === "date" ? t({ en: "YYYY-MM-DD.", fr: "AAAA-MM-JJ." }) : undefined}>
                            <span data-reglage="valeur" className="w-full">
                                <Input id="objet-valeur" aria-label={t({ en: "Value", fr: "Valeur" })} value={brouillon.valeur ?? ""} onChange={(e) => poser({ valeur: e.target.value })} />
                            </span>
                        </L>
                    </>
                ) : (
                    <>
                        <div className="space-y-2" data-reglage="colonnes">
                            <p className="text-sm font-medium">{t({ en: "Columns", fr: "Colonnes" })}</p>
                            {colonnes.map((c, i) => (
                                <div key={c.id ?? `n${i}`} className="flex items-center gap-2" data-colonne={c.libelle}>
                                    {c.pose_par === "mark" ? (
                                        <Lock className="h-3.5 w-3.5 text-muted-foreground" aria-label={t({ en: "Set by .mark: the client neither deletes nor renames it", fr: "Posée par .mark : le client ne la supprime ni ne la renomme" })} />
                                    ) : (
                                        <span className="w-3.5" />
                                    )}
                                    <Input aria-label={`${t({ en: "Column", fr: "Colonne" })} ${i + 1}`} value={c.libelle} onChange={(e) => renommerColonne(i, e.target.value)} className="h-9" />
                                    <Select value={c.type ?? "texte"} onValueChange={(v: string) => poser({ colonnes: colonnes.map((x, j) => (j === i ? { ...x, type: v as TypeObjet } : x)) })}>
                                        <SelectTrigger className="h-9 w-40" aria-label={`${t({ en: "Type", fr: "Type" })} ${i + 1}`}>
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {TYPES.map((ty) => (
                                                <SelectItem key={ty} value={ty}>
                                                    {t(LIBELLE_TYPE[ty])}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                    <Button variant="ghost" size="icon" aria-label={`${t({ en: "Remove the column", fr: "Retirer la colonne" })} ${c.libelle}`} onClick={() => retirerColonne(i)}>
                                        <Trash2 className="h-4 w-4" />
                                    </Button>
                                </div>
                            ))}
                            <Button variant="ghost" size="sm" onClick={ajouterColonne} data-testid="ajouter-colonne">
                                <Plus className="h-3.5 w-3.5" /> {t({ en: "Add a column", fr: "Ajouter une colonne" })}
                            </Button>
                        </div>
                        <div className="space-y-2" data-reglage="lignes">
                            <p className="text-sm font-medium">{t({ en: "Lines", fr: "Lignes" })}</p>
                            {lignes.map((l, i) => (
                                <div key={l.id ?? `n${i}`} className="flex items-center gap-2" data-ligne-objet={i}>
                                    {colonnes.map((c) => (
                                        <Input key={c.libelle} aria-label={`${c.libelle} ${i + 1}`} value={l.valeurs?.[c.libelle] ?? ""} onChange={(e) => cellule(i, c.libelle, e.target.value)} className="h-9" />
                                    ))}
                                    <Button variant="ghost" size="icon" aria-label={`${t({ en: "Remove line", fr: "Retirer la ligne" })} ${i + 1}`} onClick={() => poser({ lignes: lignes.filter((_, j) => j !== i) })}>
                                        <Trash2 className="h-4 w-4" />
                                    </Button>
                                </div>
                            ))}
                            <Button variant="ghost" size="sm" disabled={colonnes.length === 0} onClick={ajouterLigne} data-testid="ajouter-ligne">
                                <Plus className="h-3.5 w-3.5" /> {t({ en: "Add a line", fr: "Ajouter une ligne" })}
                            </Button>
                        </div>
                    </>
                )}
                <JaugeObjet taille={taille} plafond={plafond} />
                {(fautes.length > 0 || erreur) && (
                    <div className="space-y-1 text-sm text-destructive" role="alert" data-testid="erreur-objet">
                        {fautes.map((f) => (
                            <p key={f}>{f}</p>
                        ))}
                        {erreur && <p>{erreur}</p>}
                    </div>
                )}
            </div>
        </CadreModale>
    );
};

/** La taille du texte envoyé à l'agent face au plafond (D112). */
export const JaugeObjet = ({ taille, plafond }: { taille: number; plafond: number }) => {
    const { t } = useLangue();
    const part = Math.min(100, Math.round((taille / Math.max(1, plafond)) * 100));
    return (
        <div className="space-y-1" data-jauge={taille > plafond ? "depasse" : "ok"}>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <div className={`h-full ${taille > plafond ? "bg-destructive" : "bg-primary"}`} style={{ width: `${part}%` }} />
            </div>
            <p className="text-xs text-muted-foreground">
                {t({ en: `${taille} / ${plafond} characters sent to the agent`, fr: `${taille} / ${plafond} caractères envoyés à l'agent` })}
            </p>
        </div>
    );
};
