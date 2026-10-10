"use client";

/**
 * [.mark] The model of a SECOND brain (the clerk, chantier agent-leger-greffier, lot C, D9),
 * generated from the provider's schema like the Models screen: provider from the list, model
 * from its examples or typed, the provider's own settings in the same groups and labels
 * (`registry.py`, `mark_groupe` / `mark_libelle`), and the key typed or picked in the key library.
 *
 * It edits a block in the shape of a model override (`greffier_llm`): an empty field is
 * absent from the block, and then comes from the conversation model. ⛔ It knows no provider by
 * name: everything it shows comes from the schema the server sends.
 */
import { useEffect, useMemo, useState } from "react";

import { getDefaultConfigurationsApiV1UserConfigurationsDefaultsGet } from "@/client/sdk.gen";
import type { ProviderSchema } from "@/components/ServiceConfigurationForm";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useAuth } from "@/lib/auth";

import { ChampCleModele } from "../cles/ChampCleModele";
import { useLangue } from "../langue/langue";
import { grouperChamps, LibelleChamp, SousMenuFournisseur } from "./GroupesFournisseur";

export type BlocModele = Record<string, unknown>;
type Propriete = ProviderSchema["properties"][string];

// Shown apart, at the top: the rest is generated.
const EN_TETE = ["provider", "model", "api_key"];
const VIDE = "__comme_la_conversation__";

const sansNull = (p: Propriete | undefined): Propriete | undefined =>
    p?.anyOf?.find((o) => o.type && o.type !== "null") ?? p;
const enumDe = (p: Propriete | undefined) => sansNull(p)?.enum;
const estNombre = (p: Propriete | undefined) => ["number", "integer"].includes(sansNull(p)?.type ?? "");
const estBooleen = (p: Propriete | undefined) => sansNull(p)?.type === "boolean";

/** The block with one field set, or removed when emptied. */
export const poserDansLeBloc = (bloc: BlocModele, champ: string, valeur: unknown): BlocModele => {
    const suivant = { ...bloc };
    if (valeur === undefined || valeur === null || valeur === "") delete suivant[champ];
    else suivant[champ] = valeur;
    return suivant;
};

export function ChampsFournisseurLlm({
    bloc,
    onChange,
    schemas: schemasDonnes,
    idPrefixe = "greffier",
}: {
    bloc: BlocModele;
    onChange: (bloc: BlocModele) => void;
    /** For tests and callers that already hold them; otherwise read from the server. */
    schemas?: Record<string, ProviderSchema> | null;
    idPrefixe?: string;
}) {
    const { t, langue } = useLangue();
    const [schemasLus, setSchemasLus] = useState<Record<string, ProviderSchema> | null>(null);
    const { user, loading: authLoading } = useAuth();
    useEffect(() => {
        if (schemasDonnes || authLoading || !user) return;
        let actif = true;
        void getDefaultConfigurationsApiV1UserConfigurationsDefaultsGet().then((r) => {
            if (actif && r.data) setSchemasLus((r.data as unknown as { llm?: Record<string, ProviderSchema> }).llm ?? {});
        });
        return () => {
            actif = false;
        };
    }, [schemasDonnes, authLoading, user]);
    const schemas = schemasDonnes ?? schemasLus;
    const fournisseur = typeof bloc.provider === "string" ? bloc.provider : "";
    const schema = fournisseur ? schemas?.[fournisseur] : undefined;
    const poser = (champ: string, valeur: unknown) => onChange(poserDansLeBloc(bloc, champ, valeur));

    const champsGeneres = useMemo(
        () => Object.keys(schema?.properties ?? {}).filter((c) => !EN_TETE.includes(c)),
        [schema],
    );
    const groupes = grouperChamps(champsGeneres, (c) => schema?.properties[c]);
    const exemplesModele = sansNull(schema?.properties.model)?.examples ?? [];

    const champ = (nom: string) => {
        const p = schema?.properties[nom];
        const id = `${idPrefixe}_${nom}`;
        const valeur = bloc[nom];
        const indication = p?.default !== undefined && p?.default !== null ? String(p.default) : t({ en: "as the conversation", fr: "comme la conversation" });
        let saisie;
        if (enumDe(p)) {
            saisie = (
                <Select value={typeof valeur === "string" ? valeur : VIDE} onValueChange={(v) => poser(nom, v === VIDE ? undefined : v)}>
                    <SelectTrigger id={id}>
                        <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value={VIDE}>{t({ en: "Default", fr: "Par défaut" })}</SelectItem>
                        {enumDe(p)!.map((option) => (
                            <SelectItem key={option} value={option}>
                                {option}
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
            );
        } else if (estBooleen(p)) {
            saisie = <Switch id={id} checked={valeur === true} onCheckedChange={(v) => poser(nom, v ? true : undefined)} />;
        } else {
            saisie = (
                <Input
                    id={id}
                    inputMode={estNombre(p) ? "decimal" : undefined}
                    value={valeur === undefined || valeur === null ? "" : String(valeur)}
                    placeholder={indication}
                    onChange={(e) => {
                        const brut = e.target.value;
                        if (!estNombre(p) || brut.trim() === "") return poser(nom, brut.trim() === "" ? undefined : brut);
                        const nombre = Number(brut.replace(",", "."));
                        poser(nom, Number.isFinite(nombre) ? nombre : brut);
                    }}
                />
            );
        }
        return (
            <div key={nom} className="space-y-1" data-champ-fournisseur={nom}>
                <LibelleChamp champ={nom} libelle={p?.mark_libelle} htmlFor={id} />
                {saisie}
                {p?.description && <p className="text-xs text-muted-foreground">{p.description}</p>}
            </div>
        );
    };

    return (
        <div className="space-y-4" data-langue={langue}>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="space-y-1">
                    <label htmlFor={`${idPrefixe}_provider`} className="text-sm font-medium">
                        {t({ en: "Provider", fr: "Fournisseur" })}
                    </label>
                    <Select
                        value={fournisseur || VIDE}
                        onValueChange={(v) =>
                            // Another provider: its settings and key do not carry over.
                            onChange(v === VIDE ? {} : v === fournisseur ? bloc : { provider: v })
                        }
                    >
                        <SelectTrigger id={`${idPrefixe}_provider`}>
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value={VIDE}>{t({ en: "As the conversation", fr: "Comme la conversation" })}</SelectItem>
                            {Object.entries(schemas ?? {}).map(([cle, s]) => (
                                <SelectItem key={cle} value={cle}>
                                    {s.title ?? cle}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
                <div className="space-y-1">
                    <label htmlFor={`${idPrefixe}_model`} className="text-sm font-medium">
                        {t({ en: "Model", fr: "Modèle" })}
                    </label>
                    <Input
                        id={`${idPrefixe}_model`}
                        list={`${idPrefixe}_modeles`}
                        value={typeof bloc.model === "string" ? bloc.model : ""}
                        placeholder={t({ en: "as the conversation", fr: "comme la conversation" })}
                        onChange={(e) => poser("model", e.target.value.trim() || undefined)}
                    />
                    <datalist id={`${idPrefixe}_modeles`}>
                        {exemplesModele.map((m) => (
                            <option key={m} value={m} />
                        ))}
                    </datalist>
                </div>
            </div>
            {fournisseur && (
                <div className="space-y-1">
                    <label htmlFor={`${idPrefixe}_api_key`} className="text-sm font-medium">
                        {t({ en: "API key", fr: "Clé API" })}
                    </label>
                    <ChampCleModele
                        id={`${idPrefixe}_api_key`}
                        valeur={typeof bloc.api_key === "string" ? bloc.api_key : ""}
                        fournisseur={fournisseur}
                        placeholder={t({ en: "Empty: the conversation's key", fr: "Vide : la clé de la conversation" })}
                        onChange={(v) => poser("api_key", v.trim() || undefined)}
                    />
                    <p className="text-xs text-muted-foreground">
                        {t({
                            en: "A key of the library is named, never shown. Empty, the clerk uses the conversation's key and shares its rate limit.",
                            fr: "Une clé de la bibliothèque est nommée, jamais montrée. Vide, le greffier prend la clé de la conversation et partage son quota.",
                        })}
                    </p>
                </div>
            )}
            {fournisseur && !schema && schemas !== null && (
                <p className="text-xs text-destructive">
                    {t({ en: `Unknown provider: ${fournisseur}.`, fr: `Fournisseur inconnu : ${fournisseur}.` })}
                </p>
            )}
            {schema &&
                groupes.map((g) => (
                    <SousMenuFournisseur key={g.id} id={`${idPrefixe}.${g.id}`} nombre={g.champs.length}>
                        {g.champs.map(champ)}
                    </SousMenuFournisseur>
                ))}
        </div>
    );
}
