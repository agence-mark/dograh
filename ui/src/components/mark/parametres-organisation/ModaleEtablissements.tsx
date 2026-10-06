"use client";

/**
 * [.mark] The establishments of the organization (chantier l-agent-travaille, L1, E1 to E4).
 *
 * A list to edit, so a modal (E4) working on a copy: « Cancel » / « Save ». It saves itself
 * (its own PUT), so it is not part of the theme's draft. Each establishment: its name, the
 * Telephony numbers that lead to it (E3, none = « to attach »), its second number and its
 * transfer number, then the three values it may override. An inherited value is shown greyed,
 * with « Customize for this establishment »; clearing it goes back to the inherited value (E2).
 *
 * What the call reads is resolved by the server, never here: this screen only shows where a
 * value comes from.
 */
import { Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import {
    getEtablissementsApiV1OrganizationsEtablissementsGet,
    getNumerosApiV1OrganizationsEtablissementsNumerosGet,
    getPhrasesApiV1OrganizationsPhrasesGet,
    saveEtablissementsApiV1OrganizationsEtablissementsPut,
} from "@/client/sdk.gen";
import type {
    AdresseEtablissement,
    Etablissement,
    NumeroDeLorganisation,
    Phrase,
    ReglagesAnnonceOuverture,
} from "@/client/types.gen";
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
import { Textarea } from "@/components/ui/textarea";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

import { ChampAdresseEtablissement } from "../ChampAdresseEtablissement";
import { type Texte, useLangue } from "../langue/langue";
import { texteAdresse } from "../SectionAdresseEtablissement";
import { EXEMPLE_HORAIRES } from "../SectionHorairesOuverture";

export const ETABLISSEMENTS_ENREGISTRES: Texte = { en: "Establishments saved", fr: "Établissements enregistrés" };

/** « Magasin de Creil » -> « magasin-de-creil », unique in the list. */
export function identifiantPour(nom: string, pris: string[]): string {
    const base =
        nom
            .normalize("NFD")
            .replace(/[̀-ͯ]/g, "")
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "-")
            .replace(/^-+|-+$/g, "")
            .slice(0, 34) || "etablissement";
    let id = base;
    for (let n = 2; pris.includes(id); n += 1) id = `${base}-${n}`;
    return id;
}

const nouveau = (pris: string[], t: (x: Texte) => string): Etablissement => {
    const nom = t({ en: "New establishment", fr: "Nouvel établissement" });
    return { id: identifiantPour(nom, pris), nom, numeros: [] };
};

/** The PUT body: empty strings are « inherited » (null), as the server reads them. */
const nettoyer = (e: Etablissement): Etablissement => {
    const vide = (v: string | null | undefined) => (v && v.trim() ? v.trim() : null);
    return {
        id: e.id,
        nom: e.nom.trim(),
        numeros: e.numeros ?? [],
        second_numero: vide(e.second_numero),
        numero_transfert: vide(e.numero_transfert),
        adresse: e.adresse ?? null,
        horaires_ouverture: vide(e.horaires_ouverture),
        annonce_fermeture: vide(e.annonce_fermeture),
        annonce_pause: vide(e.annonce_pause),
        phrases: Object.fromEntries(
            Object.entries(e.phrases ?? {})
                .filter(([, v]) => v && v.trim())
                .map(([k, v]) => [k, v.trim()]),
        ),
        termes_lexique: e.termes_lexique ?? [],
    };
};

/** One term per line -> the establishment's terms, keeping a term already there as it was. */
export const termesDepuisTexte = (texte: string, avant: Etablissement["termes_lexique"]) => {
    const connus = new Map((avant ?? []).map((x) => [x.terme, x]));
    const vus = new Set<string>();
    const termes: NonNullable<Etablissement["termes_lexique"]> = [];
    for (const ligne of texte.split("\n")) {
        const terme = ligne.trim();
        if (!terme || vus.has(terme)) continue;
        vus.add(terme);
        termes.push(connus.get(terme) ?? { terme, variantes: [], type: "nom", a_ecouter: false, propose: false });
    }
    return termes;
};

export const charge_utile_etablissements = (liste: Etablissement[]) => ({
    format: "etablissements-mark" as const,
    version: 1 as const,
    etablissements: liste.map(nettoyer),
});

/** The saved establishments, for the theme's summary; read once auth is ready, re-read on demand. */
export function useResumeEtablissements() {
    const { user, loading: authLoading } = useAuth();
    const [liste, setListe] = useState<Etablissement[] | null>(null);
    const [illisible, setIllisible] = useState(false);
    const dejaLu = useRef(false);
    const relire = useCallback(async () => {
        const reponse = await getEtablissementsApiV1OrganizationsEtablissementsGet();
        setIllisible(Boolean(reponse.error));
        setListe(reponse.data?.etablissements ?? (reponse.error ? null : []));
    }, []);
    useEffect(() => {
        if (authLoading || !user || dejaLu.current) return;
        dejaLu.current = true;
        void relire();
    }, [authLoading, user, relire]);
    return { liste, illisible, relire };
}

interface ProprietesModale {
    ouverte: boolean;
    onFermer: (enregistre: boolean) => void;
    adresseOrganisation: AdresseEtablissement | null;
    annonceOrganisation: ReglagesAnnonceOuverture;
}

/** A field that may be inherited: greyed value + « Customize », or the field + « Back to inherited ». */
const ChampHerite = ({
    id,
    libelle,
    aide,
    herite,
    origine,
    personnalise,
    onPersonnaliser,
    onHeriter,
    children,
}: {
    id: string;
    libelle: Texte;
    aide: Texte;
    herite: string | null;
    origine: Texte;
    personnalise: boolean;
    onPersonnaliser: () => void;
    onHeriter: () => void;
    children: React.ReactNode;
}) => {
    const { t } = useLangue();
    return (
        <div className="space-y-1" data-testid={`champ-${id}`}>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="text-sm font-medium">{t(libelle)}</span>
                <code className="text-xs text-muted-foreground">{id}</code>
            </div>
            {personnalise ? (
                <>
                    {children}
                    <Button variant="ghost" size="sm" onClick={onHeriter} data-testid={`heriter-${id}`}>
                        {t({ en: "Back to the inherited value", fr: "Revenir à la valeur héritée" })}
                    </Button>
                </>
            ) : (
                <div className="rounded border border-dashed border-border p-2 text-sm text-muted-foreground" data-testid={`herite-${id}`}>
                    <p className="whitespace-pre-line">
                        {herite || t({ en: "Nothing (no value)", fr: "Rien (aucune valeur)" })}
                    </p>
                    <p className="mt-1 text-xs">{t(origine)}</p>
                    <Button variant="outline" size="sm" className="mt-2" onClick={onPersonnaliser} data-testid={`personnaliser-${id}`}>
                        {t({ en: "Customize for this establishment", fr: "Personnaliser pour cet établissement" })}
                    </Button>
                </div>
            )}
            <p className="text-xs text-muted-foreground">{t(aide)}</p>
        </div>
    );
};

export function ModaleEtablissements({ ouverte, onFermer, adresseOrganisation, annonceOrganisation }: ProprietesModale) {
    const { t } = useLangue();
    const [liste, setListe] = useState<Etablissement[] | null>(null);
    const [numeros, setNumeros] = useState<NumeroDeLorganisation[]>([]);
    const [phrasesEtablissement, setPhrasesEtablissement] = useState<Phrase[]>([]);
    // The terms as typed: a line being written is kept until it is left.
    const [termesSaisis, setTermesSaisis] = useState<Record<string, string>>({});
    const [choisi, setChoisi] = useState(0);
    const [erreur, setErreur] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);
    const [adresseIncomplete, setAdresseIncomplete] = useState(false);
    // Fields opened with « Customize » while still empty: shown as fields, not as inherited.
    const [ouverts, setOuverts] = useState<Record<string, boolean>>({});
    // The identifiers already saved never change (a call, a stamp, a future base row refer to
    // them); a NEW establishment's identifier follows its name until it is saved.
    const [idsEnregistres, setIdsEnregistres] = useState<string[]>([]);

    useEffect(() => {
        if (!ouverte) return;
        setListe(null);
        setErreur(null);
        setChoisi(0);
        setOuverts({});
        void (async () => {
            const [catalogue, telephonie, phrases] = await Promise.all([
                getEtablissementsApiV1OrganizationsEtablissementsGet(),
                getNumerosApiV1OrganizationsEtablissementsNumerosGet(),
                getPhrasesApiV1OrganizationsPhrasesGet(),
            ]);
            setPhrasesEtablissement((phrases.data?.phrases ?? []).filter((p) => p.niveau === "etablissement"));
            if (catalogue.error || !catalogue.data) {
                // ⛔ Unreadable: nothing to edit, or the save would replace what is there.
                setErreur(detailFromError(catalogue.error, "Establishments unreadable"));
                return;
            }
            setListe(catalogue.data.etablissements ?? []);
            setIdsEnregistres((catalogue.data.etablissements ?? []).map((e) => e.id));
            setNumeros(telephonie.data ?? []);
        })();
    }, [ouverte]);

    const courant = liste && liste.length > 0 ? liste[Math.min(choisi, liste.length - 1)] : null;
    const modifier = (champ: Partial<Etablissement>) =>
        setListe((avant) => (avant ? avant.map((e, i) => (i === Math.min(choisi, avant.length - 1) ? { ...e, ...champ } : e)) : avant));

    const numerosPris = useMemo(() => {
        const pris = new Map<string, string>();
        (liste ?? []).forEach((e, i) => {
            if (i !== choisi) (e.numeros ?? []).forEach((n) => pris.set(n, e.nom));
        });
        return pris;
    }, [liste, choisi]);

    const ajouter = () => {
        setListe((avant) => {
            const suite = [...(avant ?? []), nouveau((avant ?? []).map((e) => e.id), t)];
            setChoisi(suite.length - 1);
            return suite;
        });
        setOuverts({});
    };
    const retirer = (rang: number) => {
        setListe((avant) => (avant ? avant.filter((_e, i) => i !== rang) : avant));
        setChoisi(0);
    };

    const ouvert = (cle: keyof Etablissement) => Boolean(courant && (courant[cle] || ouverts[`${courant.id}:${String(cle)}`]));
    const personnaliser = (cle: keyof Etablissement) => courant && setOuverts((a) => ({ ...a, [`${courant.id}:${String(cle)}`]: true }));
    const heriter = (cle: keyof Etablissement) => {
        if (!courant) return;
        setOuverts((a) => ({ ...a, [`${courant.id}:${String(cle)}`]: false }));
        modifier({ [cle]: null } as Partial<Etablissement>);
        if (cle === "adresse") setAdresseIncomplete(false);
    };

    const fautes: string[] = [];
    (liste ?? []).forEach((e) => {
        if (!e.nom.trim()) fautes.push(t({ en: "An establishment has no name.", fr: "Un établissement n'a pas de nom." }));
    });
    if (adresseIncomplete)
        fautes.push(t({ en: "Choose the town for this postal code before saving.", fr: "Choisissez la commune de ce code postal avant d'enregistrer." }));

    const enregistrer = async () => {
        if (!liste) return;
        setEnCours(true);
        setErreur(null);
        const reponse = await saveEtablissementsApiV1OrganizationsEtablissementsPut({ body: charge_utile_etablissements(liste) });
        setEnCours(false);
        if (reponse.error) {
            setErreur(detailFromError(reponse.error, "Establishments not saved"));
            return;
        }
        toast.success(t(ETABLISSEMENTS_ENREGISTRES));
        onFermer(true);
    };

    return (
        <Dialog open={ouverte} onOpenChange={(o) => (o ? null : onFermer(false))}>
            <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-5xl" data-testid="modale-etablissements">
                <DialogHeader>
                    <DialogTitle>{t({ en: "Establishments", fr: "Établissements" })}</DialogTitle>
                    <DialogDescription>
                        {t({
                            en: "Each establishment is reached through its own numbers: a call to one of them reads that establishment's hours, address and sentences. An empty field is inherited: the agent's own value first, then the organization's.",
                            fr: "Chaque établissement est joint par ses propres numéros : un appel vers l'un d'eux lit les horaires, l'adresse et les phrases de cet établissement. Un champ vide est hérité : la valeur de l'agent d'abord, puis celle de l'organisation.",
                        })}
                    </DialogDescription>
                </DialogHeader>
                {erreur && (
                    <p className="text-sm text-destructive" role="alert" data-testid="erreur-etablissements">
                        {erreur}
                    </p>
                )}
                {liste === null ? (
                    !erreur && <p className="text-sm text-muted-foreground">{t({ en: "Loading…", fr: "Chargement…" })}</p>
                ) : (
                    <div className="grid gap-4 md:grid-cols-[14rem_1fr]">
                        <div className="space-y-2">
                            <ul className="space-y-1" data-testid="liste-etablissements">
                                {liste.map((e, i) => (
                                    <li key={`${e.id}-${i}`} className="flex items-center gap-1">
                                        <button
                                            type="button"
                                            onClick={() => setChoisi(i)}
                                            className={`min-w-0 flex-1 truncate rounded px-2 py-1 text-left text-sm ${i === choisi ? "bg-accent font-medium" : "hover:bg-accent/50"}`}
                                        >
                                            {e.nom || t({ en: "(no name)", fr: "(sans nom)" })}
                                            {(e.numeros ?? []).length === 0 && (
                                                <span className="ml-1 text-xs text-muted-foreground">{t({ en: "· to attach", fr: "· à rattacher" })}</span>
                                            )}
                                        </button>
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            aria-label={t({ en: "Remove this establishment", fr: "Retirer cet établissement" })}
                                            onClick={() => retirer(i)}
                                        >
                                            <Trash2 className="h-4 w-4" />
                                        </Button>
                                    </li>
                                ))}
                            </ul>
                            {liste.length === 0 && (
                                <p className="text-sm text-muted-foreground">
                                    {t({
                                        en: "No establishment: every call behaves as before.",
                                        fr: "Aucun établissement : chaque appel se comporte comme avant.",
                                    })}
                                </p>
                            )}
                            <Button variant="outline" size="sm" onClick={ajouter} data-testid="ajouter-etablissement">
                                <Plus className="mr-1 h-4 w-4" />
                                {t({ en: "Add an establishment", fr: "Ajouter un établissement" })}
                            </Button>
                        </div>

                        {courant && (
                            <div className="min-w-0 space-y-4" data-testid="fiche-etablissement">
                                <div className="space-y-1">
                                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                                        <label htmlFor="etablissement-nom" className="text-sm font-medium">
                                            {t({ en: "Name", fr: "Nom" })}
                                        </label>
                                        <code className="text-xs text-muted-foreground">{courant.id}</code>
                                    </div>
                                    <Input
                                        id="etablissement-nom"
                                        value={courant.nom}
                                        maxLength={100}
                                        onChange={(e) => {
                                            const nom = e.target.value;
                                            if (idsEnregistres.includes(courant.id)) {
                                                modifier({ nom });
                                                return;
                                            }
                                            const autres = (liste ?? []).filter((x) => x !== courant).map((x) => x.id);
                                            modifier({ nom, id: identifiantPour(nom, autres) });
                                        }}
                                    />
                                    <p className="text-xs text-muted-foreground">
                                        {t({ en: "Given to the agents as {{etablissement}}.", fr: "Donné aux agents comme {{etablissement}}." })}
                                    </p>
                                </div>

                                <fieldset className="space-y-1">
                                    <legend className="text-sm font-medium">{t({ en: "Numbers that lead here", fr: "Numéros qui mènent ici" })}</legend>
                                    {numeros.length === 0 ? (
                                        <p className="text-sm text-muted-foreground">
                                            {t({
                                                en: "No number in Telephony yet: the establishment stays « to attach ».",
                                                fr: "Aucun numéro dans Telephony pour l'instant : l'établissement reste « à rattacher ».",
                                            })}
                                        </p>
                                    ) : (
                                        numeros.map((n) => {
                                            const ailleurs = numerosPris.get(n.numero);
                                            const coche = (courant.numeros ?? []).includes(n.numero);
                                            return (
                                                <label key={n.numero} className="flex flex-wrap items-center gap-2 text-sm">
                                                    <input
                                                        type="checkbox"
                                                        checked={coche}
                                                        disabled={Boolean(ailleurs)}
                                                        onChange={() =>
                                                            modifier({
                                                                numeros: coche
                                                                    ? (courant.numeros ?? []).filter((x) => x !== n.numero)
                                                                    : [...(courant.numeros ?? []), n.numero],
                                                            })
                                                        }
                                                    />
                                                    <span className="font-mono">{n.numero}</span>
                                                    {n.libelle && <span className="text-muted-foreground">{n.libelle}</span>}
                                                    {n.agent && <span className="text-xs text-muted-foreground">→ {n.agent}</span>}
                                                    {ailleurs && (
                                                        <span className="text-xs text-muted-foreground">
                                                            {t({ en: "already used by", fr: "déjà pris par" })} {ailleurs}
                                                        </span>
                                                    )}
                                                </label>
                                            );
                                        })
                                    )}
                                    <p className="text-xs text-muted-foreground">
                                        {t({
                                            en: "A called number leads to one establishment only. A number of no establishment: its calls behave as before.",
                                            fr: "Un numéro appelé mène à un seul établissement. Un numéro d'aucun établissement : ses appels se comportent comme avant.",
                                        })}
                                    </p>
                                </fieldset>

                                <div className="grid gap-3 sm:grid-cols-2">
                                    <div className="space-y-1">
                                        <label htmlFor="etablissement-second-numero" className="text-sm font-medium">
                                            {t({ en: "Second number", fr: "Second numéro" })}
                                        </label>
                                        <Input
                                            id="etablissement-second-numero"
                                            value={courant.second_numero ?? ""}
                                            placeholder="+33344000000"
                                            onChange={(e) => modifier({ second_numero: e.target.value })}
                                        />
                                        <p className="text-xs text-muted-foreground">
                                            {t({ en: "Reached when the agent cannot answer.", fr: "Joint quand l'agent ne peut pas répondre." })}
                                        </p>
                                    </div>
                                    <div className="space-y-1">
                                        <label htmlFor="etablissement-numero-transfert" className="text-sm font-medium">
                                            {t({ en: "Transfer number", fr: "Numéro de transfert" })}
                                        </label>
                                        <Input
                                            id="etablissement-numero-transfert"
                                            value={courant.numero_transfert ?? ""}
                                            placeholder="+33344000000"
                                            onChange={(e) => modifier({ numero_transfert: e.target.value })}
                                        />
                                        <p className="text-xs text-muted-foreground">
                                            {t({
                                                en: "Given to the agents as {{numero_transfert}}: write it in the transfer tool's destination.",
                                                fr: "Donné aux agents comme {{numero_transfert}} : à écrire dans la destination de l'outil de transfert.",
                                            })}
                                        </p>
                                    </div>
                                </div>

                                <ChampHerite
                                    id="adresse"
                                    libelle={{ en: "Address", fr: "Adresse" }}
                                    aide={{
                                        en: "Given to the agents as {{adresse_etablissement}}; helps recognise the towns callers name.",
                                        fr: "Donnée aux agents comme {{adresse_etablissement}} ; aide à reconnaître les communes citées.",
                                    }}
                                    herite={adresseOrganisation ? texteAdresse(adresseOrganisation) : null}
                                    origine={{ en: "Inherited from the organization", fr: "Hérité de l'organisation" }}
                                    personnalise={ouvert("adresse")}
                                    onPersonnaliser={() => personnaliser("adresse")}
                                    onHeriter={() => heriter("adresse")}
                                >
                                    <ChampAdresseEtablissement
                                        key={courant.id}
                                        id={`etablissement-adresse-${courant.id}`}
                                        enregistree={courant.adresse ?? null}
                                        onChange={(valeur, incomplete) => {
                                            setAdresseIncomplete(incomplete);
                                            if (!incomplete) modifier({ adresse: valeur });
                                        }}
                                    />
                                </ChampHerite>

                                <ChampHerite
                                    id="horaires_ouverture"
                                    libelle={{ en: "Opening hours and closures", fr: "Horaires d'ouverture et fermetures" }}
                                    aide={{
                                        en: "Same format as an agent's hours; a closure is a dated line (« 24/12/2026 : fermé »). An agent that has its own hours keeps them.",
                                        fr: "Même format que les horaires d'un agent ; une fermeture est une ligne datée (« 24/12/2026 : fermé »). Un agent qui a ses propres horaires les garde.",
                                    }}
                                    herite={null}
                                    origine={{ en: "Inherited: each agent's own hours", fr: "Hérité : les horaires de chaque agent" }}
                                    personnalise={ouvert("horaires_ouverture")}
                                    onPersonnaliser={() => personnaliser("horaires_ouverture")}
                                    onHeriter={() => heriter("horaires_ouverture")}
                                >
                                    <Textarea
                                        id="etablissement-horaires"
                                        rows={8}
                                        className="font-mono text-xs"
                                        placeholder={EXEMPLE_HORAIRES}
                                        value={courant.horaires_ouverture ?? ""}
                                        onChange={(e) => modifier({ horaires_ouverture: e.target.value })}
                                    />
                                </ChampHerite>

                                {phrasesEtablissement.map((p) => {
                                    const cle = `phrase:${p.variable}`;
                                    const propre = (courant.phrases ?? {})[p.variable];
                                    return (
                                        <ChampHerite
                                            key={cle}
                                            id={p.variable}
                                            libelle={{ en: p.description || p.variable, fr: p.description || p.variable }}
                                            aide={{
                                                en: `A sentence of the catalogue placed at the establishment's level, given to the agents as {{${p.variable}}}.`,
                                                fr: `Une phrase du catalogue placée au niveau de l'établissement, donnée aux agents comme {{${p.variable}}}.`,
                                            }}
                                            herite={p.contenu ?? null}
                                            origine={{ en: "Inherited from the organization", fr: "Hérité de l'organisation" }}
                                            personnalise={Boolean(propre) || Boolean(ouverts[`${courant.id}:${cle}`])}
                                            onPersonnaliser={() => setOuverts((a) => ({ ...a, [`${courant.id}:${cle}`]: true }))}
                                            onHeriter={() => {
                                                setOuverts((a) => ({ ...a, [`${courant.id}:${cle}`]: false }));
                                                const reste = { ...(courant.phrases ?? {}) };
                                                delete reste[p.variable];
                                                modifier({ phrases: reste });
                                            }}
                                        >
                                            <Textarea
                                                id={`etablissement-phrase-${p.variable}`}
                                                rows={2}
                                                maxLength={1000}
                                                value={propre ?? ""}
                                                onChange={(e) => modifier({ phrases: { ...(courant.phrases ?? {}), [p.variable]: e.target.value } })}
                                            />
                                        </ChampHerite>
                                    );
                                })}

                                <div className="space-y-1">
                                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                                        <label htmlFor="etablissement-termes" className="text-sm font-medium">
                                            {t({ en: "Terms added to the trade vocabulary", fr: "Termes ajoutés au lexique métier" })}
                                        </label>
                                        <code className="text-xs text-muted-foreground">termes_lexique</code>
                                    </div>
                                    <Textarea
                                        id="etablissement-termes"
                                        rows={3}
                                        placeholder={t({ en: "One brand or name per line", fr: "Une marque ou un nom par ligne" })}
                                        value={termesSaisis[courant.id] ?? (courant.termes_lexique ?? []).map((x) => x.terme).join("\n")}
                                        onChange={(e) => {
                                            const texte = e.target.value;
                                            setTermesSaisis((a) => ({ ...a, [courant.id]: texte }));
                                            modifier({ termes_lexique: termesDepuisTexte(texte, courant.termes_lexique) });
                                        }}
                                    />
                                    <p className="text-xs text-muted-foreground">
                                        {t({
                                            en: "Recognised like the organization's names on this establishment's calls; a spelling already in the organization's vocabulary is ignored.",
                                            fr: "Reconnus comme les noms de l'organisation sur les appels de cet établissement ; une orthographe déjà dans le lexique de l'organisation est ignorée.",
                                        })}
                                    </p>
                                </div>

                                {(["annonce_fermeture", "annonce_pause"] as const).map((cle) => (
                                    <ChampHerite
                                        key={cle}
                                        id={cle}
                                        libelle={
                                            cle === "annonce_fermeture"
                                                ? { en: "Closing sentence", fr: "Phrase de fermeture" }
                                                : { en: "Break sentence", fr: "Phrase de pause" }
                                        }
                                        aide={{
                                            en: "Said at pick-up. « {reouverture} » is the spoken reopening; what is in brackets disappears when it is unknown.",
                                            fr: "Dite au décroché. « {reouverture} » est la réouverture dite ; ce qui est entre crochets disparaît quand elle est inconnue.",
                                        }}
                                        herite={annonceOrganisation[cle] ?? null}
                                        origine={{ en: "Inherited from the organization", fr: "Hérité de l'organisation" }}
                                        personnalise={ouvert(cle)}
                                        onPersonnaliser={() => personnaliser(cle)}
                                        onHeriter={() => heriter(cle)}
                                    >
                                        <Textarea
                                            id={`etablissement-${cle}`}
                                            rows={2}
                                            maxLength={300}
                                            value={courant[cle] ?? ""}
                                            onChange={(e) => modifier({ [cle]: e.target.value })}
                                        />
                                    </ChampHerite>
                                ))}
                            </div>
                        )}
                        {fautes.length > 0 && (
                            <ul className="text-sm text-destructive md:col-span-2" data-testid="fautes-etablissements">
                                {fautes.map((f, i) => (
                                    <li key={i}>{f}</li>
                                ))}
                            </ul>
                        )}
                    </div>
                )}
                <DialogFooter>
                    <Button variant="outline" onClick={() => onFermer(false)}>
                        {t({ en: "Cancel", fr: "Annuler" })}
                    </Button>
                    <Button onClick={() => void enregistrer()} disabled={enCours || liste === null || fautes.length > 0} data-testid="enregistrer-etablissements">
                        {t({ en: "Save", fr: "Enregistrer" })}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
