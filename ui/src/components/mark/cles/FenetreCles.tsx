"use client";

/**
 * [.mark] The key library (chantier direct-et-passe-muette, lot 0, P15, P16; lot 0 bis, P18 to P23):
 * every provider key of the organization, by provider. Add one, use one, delete one that no
 * longer works.
 *
 * A key is typed once and never shown again. Deleting a key first says where it is still used;
 * the setting that pointed at it then says « key deleted ». A setting that points at a credential
 * saved before the library keeps it, shown as « outside the library ».
 *
 * `BibliothequeCles` is the library itself, shown in `FenetreCles` and on the « Keys » page of the
 * menu (P18). `SelecteurCle` is the drop-down a setting uses to pick a key of one provider, with
 * « Keys… » next to it. The providers are Dograh's own, served by the server (P19).
 */
import { useCallback, useEffect, useState } from "react";

import {
    ajouterUneCleApiV1ClesPost,
    fournisseursDesClesApiV1ClesFournisseursGet,
    identifiantDesigneApiV1ClesDesigneeUuidGet,
    listerLesClesApiV1ClesGet,
    supprimerUneCleApiV1ClesUuidDelete,
    usagesDUneCleApiV1ClesUuidUsagesGet,
} from "@/client";
import type { Cle, Designation, Usage } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { detailFromError } from "@/lib/apiError";

import { type Texte, useLangue } from "../langue/langue";

export type Fournisseur = Cle["fournisseur"];

// How a provider is written on screen; any other one shows as the server names it.
const NOMS: Record<string, string> = {
    mistral: "Mistral",
    elevenlabs: "ElevenLabs",
    deepgram: "Deepgram",
    soniox: "Soniox",
    openai: "OpenAI",
    openai_realtime: "OpenAI Realtime",
    google: "Google",
    google_vertex: "Google Vertex",
    cartesia: "Cartesia",
    groq: "Groq",
    openrouter: "OpenRouter",
    azure: "Azure OpenAI",
    azure_speech: "Azure Speech",
    assemblyai: "AssemblyAI",
    speechmatics: "Speechmatics",
    gladia: "Gladia",
    minimax: "MiniMax",
    xai: "xAI",
};
export const nomDu = (f: string) => NOMS[f] ?? f;

export const DESCRIPTION_BIBLIOTHEQUE: Texte = {
    en: "The provider keys of the organization, stored encrypted. A key is never shown again once saved. Delete a key that no longer works or was revoked.",
    fr: "Les clés de fournisseur de l'organisation, rangées chiffrées. Une clé n'est plus jamais affichée une fois enregistrée. Supprime une clé qui ne marche plus ou qui a été révoquée.",
};

/** The providers a key can serve: Dograh's own, as the server lists them (P19). */
export function useFournisseurs(): Fournisseur[] {
    const [fournisseurs, setFournisseurs] = useState<Fournisseur[]>([]);
    useEffect(() => {
        let annule = false;
        void fournisseursDesClesApiV1ClesFournisseursGet().then((reponse) => {
            if (!annule && !reponse.error) setFournisseurs((reponse.data as Fournisseur[] | undefined) ?? []);
        });
        return () => {
            annule = true;
        };
    }, []);
    return [...fournisseurs].sort((a, b) => nomDu(a).localeCompare(nomDu(b)));
}

/** Where a key still serves, in the screen's language. */
export function texteUsage(u: Usage): Texte {
    switch (u.ou) {
        case "reglages_modele":
            return { en: "Simulated caller settings · Mistral key", fr: "Réglages de l'appelant simulé · clé Mistral" };
        case "reglages_voix":
            return { en: "Simulated caller settings · ElevenLabs key", fr: "Réglages de l'appelant simulé · clé ElevenLabs" };
        case "outil":
            return { en: `Tool « ${u.nom ?? ""} »`, fr: `Outil « ${u.nom ?? ""} »` };
        case "agent":
            return { en: `Agent « ${u.nom ?? ""} » (current version)`, fr: `Agent « ${u.nom ?? ""} » (version courante)` };
        case "modeles_organisation":
            return { en: "Models of the organization", fr: "Modèles de l'organisation" };
        case "modeles_agent":
            return { en: `Agent « ${u.nom ?? ""} » · model settings`, fr: `Agent « ${u.nom ?? ""} » · réglages de modèle` };
    }
}

/** The keys of the organization, of one provider or all; read only when `actif`. */
export function useCles(fournisseur?: Fournisseur, actif = true) {
    const [cles, setCles] = useState<Cle[] | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);
    const recharger = useCallback(async () => {
        if (!actif) return;
        const reponse = await listerLesClesApiV1ClesGet({ query: fournisseur ? { fournisseur } : undefined });
        if (reponse.error) {
            setErreur(detailFromError(reponse.error, "Keys unreadable"));
            return;
        }
        setErreur(null);
        setCles((reponse.data as Cle[] | undefined) ?? []);
    }, [fournisseur, actif]);
    useEffect(() => {
        void recharger();
    }, [recharger]);
    return { cles, erreur, recharger };
}

function LigneCle({ cle, onUtiliser, onSupprimee }: { cle: Cle; onUtiliser?: () => void; onSupprimee: () => void }) {
    const { t } = useLangue();
    const [usages, setUsages] = useState<Usage[] | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);

    const demander = async () => {
        setErreur(null);
        const reponse = await usagesDUneCleApiV1ClesUuidUsagesGet({ path: { uuid: cle.uuid } });
        if (reponse.error) {
            setErreur(detailFromError(reponse.error, "Key usage unreadable"));
            return;
        }
        setUsages((reponse.data as Usage[] | undefined) ?? []);
    };
    const supprimer = async () => {
        setEnCours(true);
        const reponse = await supprimerUneCleApiV1ClesUuidDelete({ path: { uuid: cle.uuid } });
        setEnCours(false);
        if (reponse.error) {
            setErreur(detailFromError(reponse.error, "Key not deleted"));
            return;
        }
        onSupprimee();
    };

    return (
        <li className="space-y-2 rounded border border-border p-2" data-testid={`cle-${cle.uuid}`}>
            <div className="flex flex-wrap items-center gap-2">
                <span className="min-w-0 flex-1 truncate text-sm font-medium">{cle.nom}</span>
                <span className="text-xs text-muted-foreground">{nomDu(cle.fournisseur)}</span>
                {onUtiliser && (
                    <Button size="sm" variant="outline" onClick={onUtiliser}>
                        {t({ en: "Use", fr: "Utiliser" })}
                    </Button>
                )}
                {usages === null && (
                    <Button size="sm" variant="ghost" className="text-destructive" onClick={() => void demander()}>
                        {t({ en: "Delete…", fr: "Supprimer…" })}
                    </Button>
                )}
            </div>
            {usages !== null && (
                <div className="space-y-2 rounded bg-muted/50 p-2 text-xs" role="alertdialog" aria-label={t({ en: "Delete this key?", fr: "Supprimer cette clé ?" })}>
                    {usages.length === 0 ? (
                        <p>{t({ en: "This key is not used anywhere.", fr: "Cette clé ne sert nulle part." })}</p>
                    ) : (
                        <>
                            <p>
                                {t({
                                    en: "Still used here; these settings will say « key deleted » until you pick another:",
                                    fr: "Encore utilisée ici ; ces réglages diront « clé supprimée » jusqu'à ce que tu en choisisses une autre :",
                                })}
                            </p>
                            <ul className="list-disc pl-4">
                                {usages.map((u) => (
                                    <li key={`${u.ou}-${u.nom ?? ""}`}>{t(texteUsage(u))}</li>
                                ))}
                            </ul>
                        </>
                    )}
                    <div className="flex gap-2">
                        <Button size="sm" variant="outline" onClick={() => setUsages(null)}>
                            {t({ en: "Keep it", fr: "La garder" })}
                        </Button>
                        <Button size="sm" variant="destructive" disabled={enCours} onClick={() => void supprimer()}>
                            {t({ en: "Delete the key", fr: "Supprimer la clé" })}
                        </Button>
                    </div>
                </div>
            )}
            {erreur && (
                <p className="text-xs text-destructive" role="alert">
                    {erreur}
                </p>
            )}
        </li>
    );
}

/** The library itself: the keys (of one provider, or all), and a key to add. */
export function BibliothequeCles({
    fournisseur,
    onChoisir,
}: {
    /** Shown from a setting: this provider only, and a new key is picked at once. */
    fournisseur?: Fournisseur;
    onChoisir?: (uuid: string) => void | Promise<void>;
}) {
    const { t } = useLangue();
    const { cles, erreur, recharger } = useCles(fournisseur);
    const fournisseurs = useFournisseurs();
    const [saisi, setSaisi] = useState<Fournisseur | null>(null);
    const [nom, setNom] = useState("");
    const [valeur, setValeur] = useState("");
    const [faute, setFaute] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);
    const choisi: Fournisseur | undefined =
        fournisseur ?? saisi ?? fournisseurs.find((f) => f === "mistral") ?? fournisseurs[0];
    const options = fournisseur && !fournisseurs.includes(fournisseur) ? [fournisseur, ...fournisseurs] : fournisseurs;

    const pret = Boolean(choisi) && nom.trim().length > 0 && valeur.trim().length >= 8;
    const ajouter = async () => {
        if (!choisi) return;
        setEnCours(true);
        setFaute(null);
        const reponse = await ajouterUneCleApiV1ClesPost({ body: { fournisseur: choisi, nom, cle: valeur } });
        setEnCours(false);
        if (reponse.error) {
            setFaute(detailFromError(reponse.error, "Key not saved"));
            return;
        }
        const ajoutee = reponse.data as Cle;
        setNom("");
        setValeur("");
        await recharger();
        if (onChoisir) await onChoisir(ajoutee.uuid);
    };

    return (
        <div className="space-y-3">
            {erreur && (
                <p className="text-sm text-destructive" role="alert">
                    {erreur}
                </p>
            )}
            {cles === null && !erreur ? (
                <p className="text-sm text-muted-foreground">{t({ en: "Loading…", fr: "Chargement…" })}</p>
            ) : cles && cles.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t({ en: "No key yet.", fr: "Aucune clé pour l'instant." })}</p>
            ) : (
                <ul className="space-y-2">
                    {(cles ?? []).map((c) => (
                        <LigneCle
                            key={c.uuid}
                            cle={c}
                            onUtiliser={onChoisir ? () => void onChoisir(c.uuid) : undefined}
                            onSupprimee={() => void recharger()}
                        />
                    ))}
                </ul>
            )}

            <fieldset className="grid gap-2 rounded border border-border p-3 sm:grid-cols-2">
                <legend className="px-1 text-sm font-medium">{t({ en: "Add a key", fr: "Ajouter une clé" })}</legend>
                <label className="space-y-1 text-xs text-muted-foreground">
                    <span>{t({ en: "Provider", fr: "Fournisseur" })}</span>
                    <select
                        className="w-full rounded border border-border bg-background px-2 py-1 text-sm text-foreground"
                        value={choisi ?? ""}
                        disabled={Boolean(fournisseur)}
                        onChange={(e) => setSaisi(e.target.value as Fournisseur)}
                        aria-label={t({ en: "Provider", fr: "Fournisseur" })}
                    >
                        {options.map((f) => (
                            <option key={f} value={f}>
                                {nomDu(f)}
                            </option>
                        ))}
                    </select>
                </label>
                <label className="space-y-1 text-xs text-muted-foreground">
                    <span>{t({ en: "Name (e.g. Mistral · lab organization)", fr: "Nom (ex. Mistral · organisation du labo)" })}</span>
                    <Input
                        name="mark-nom-cle"
                        autoComplete="off"
                        data-1p-ignore
                        data-lpignore="true"
                        value={nom}
                        maxLength={80}
                        onChange={(e) => setNom(e.target.value)}
                        aria-label={t({ en: "Key name", fr: "Nom de la clé" })}
                    />
                </label>
                <label className="space-y-1 text-xs text-muted-foreground sm:col-span-2">
                    <span>{t({ en: "Key", fr: "Clé" })}</span>
                    {/* « new-password »: a browser never fills a saved login password here (seen
                        in production on 06/10: name and key filled with the Dograh login). */}
                    <Input
                        type="password"
                        name="mark-valeur-cle"
                        autoComplete="new-password"
                        data-1p-ignore
                        data-lpignore="true"
                        value={valeur}
                        onChange={(e) => setValeur(e.target.value)}
                        aria-label={t({ en: "Key value", fr: "Valeur de la clé" })}
                    />
                </label>
                {faute && (
                    <p className="text-xs text-destructive sm:col-span-2" role="alert">
                        {faute}
                    </p>
                )}
                <div className="sm:col-span-2">
                    <Button size="sm" disabled={!pret || enCours} onClick={() => void ajouter()}>
                        {onChoisir
                            ? t({ en: "Save and use", fr: "Enregistrer et utiliser" })
                            : t({ en: "Save the key", fr: "Enregistrer la clé" })}
                    </Button>
                </div>
            </fieldset>
        </div>
    );
}

export function FenetreCles({
    ouverte,
    onFermer,
    fournisseur,
    onChoisir,
}: {
    ouverte: boolean;
    onFermer: () => void;
    /** Opened from a setting: the library shows this provider and a new key is picked at once. */
    fournisseur?: Fournisseur;
    onChoisir?: (uuid: string) => void | Promise<void>;
}) {
    const { t } = useLangue();
    const titre: Texte = fournisseur
        ? { en: `Keys · ${nomDu(fournisseur)}`, fr: `Clés · ${nomDu(fournisseur)}` }
        : { en: "Keys", fr: "Clés" };

    return (
        <Dialog open={ouverte} onOpenChange={(o) => (o ? null : onFermer())}>
            <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl" data-testid="fenetre-cles">
                <DialogHeader>
                    <DialogTitle>{t(titre)}</DialogTitle>
                    <DialogDescription>{t(DESCRIPTION_BIBLIOTHEQUE)}</DialogDescription>
                </DialogHeader>
                <BibliothequeCles
                    fournisseur={fournisseur}
                    onChoisir={
                        onChoisir
                            ? async (uuid) => {
                                  await onChoisir(uuid);
                                  onFermer();
                              }
                            : undefined
                    }
                />
                <DialogFooter>
                    <Button variant="outline" onClick={onFermer}>
                        {t({ en: "Close", fr: "Fermer" })}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

/** A setting's key: a drop-down of the provider's keys, and « Keys… » to add or delete one. */
export function SelecteurCle({
    fournisseur,
    valeur,
    libelle,
    onChange,
}: {
    fournisseur: Fournisseur;
    valeur: string | null | undefined;
    libelle: Texte;
    onChange: (uuid: string | null) => void;
}) {
    const { t } = useLangue();
    const { cles, erreur, recharger } = useCles(fournisseur);
    const [bibliotheque, setBibliotheque] = useState(false);
    const horsListe = Boolean(valeur) && cles !== null && !cles.some((c) => c.uuid === valeur);
    const [designation, setDesignation] = useState<Designation | null>(null);
    useEffect(() => {
        setDesignation(null);
        if (!horsListe || !valeur) return;
        let annule = false;
        void identifiantDesigneApiV1ClesDesigneeUuidGet({ path: { uuid: valeur } }).then((reponse) => {
            if (!annule && !reponse.error) setDesignation(reponse.data as Designation);
        });
        return () => {
            annule = true;
        };
    }, [horsListe, valeur]);
    const perdue = horsListe && designation?.etat === "supprimee";
    const ancienne = horsListe && designation?.etat !== "supprimee" ? designation : null;

    return (
        <div className="space-y-1 text-xs text-muted-foreground">
            <span>{t(libelle)}</span>
            <div className="flex gap-2">
                <select
                    className="min-w-0 flex-1 rounded border border-border bg-background px-2 py-1 text-sm text-foreground"
                    value={perdue || (horsListe && !ancienne) ? "" : (valeur ?? "")}
                    onChange={(e) => onChange(e.target.value || null)}
                    aria-label={t(libelle)}
                >
                    <option value="">
                        {cles && cles.length === 0
                            ? t({ en: "— no key yet: add one with « Keys… » —", fr: "— aucune clé : ajoute-en une avec « Clés… » —" })
                            : t({ en: "— choose a key —", fr: "— choisir une clé —" })}
                    </option>
                    {(cles ?? []).map((c) => (
                        <option key={c.uuid} value={c.uuid}>
                            {c.nom}
                        </option>
                    ))}
                    {ancienne && valeur && (
                        <option value={valeur}>
                            {`${ancienne.nom ?? ""} ${t({ en: "(outside the library)", fr: "(hors bibliothèque)" })}`}
                        </option>
                    )}
                </select>
                <Button type="button" size="sm" variant="outline" onClick={() => setBibliotheque(true)}>
                    {t({ en: "Keys…", fr: "Clés…" })}
                </Button>
            </div>
            {perdue && (
                <p className="text-destructive" role="alert">
                    {t({ en: "Key deleted: pick another.", fr: "Clé supprimée : choisis-en une autre." })}
                </p>
            )}
            {erreur && (
                <p className="text-destructive" role="alert">
                    {erreur}
                </p>
            )}
            {bibliotheque && (
                <FenetreCles
                    ouverte
                    onFermer={() => {
                        setBibliotheque(false);
                        void recharger();
                    }}
                    fournisseur={fournisseur}
                    onChoisir={async (uuid) => {
                        await recharger();
                        onChange(uuid);
                    }}
                />
            )}
        </div>
    );
}
