"use client";

import { useEffect, useRef, useState } from "react";

import { getCommunesDuCodePostalApiV1OrganizationsCommunesGet } from "@/client/sdk.gen";
import type { AdresseEtablissement, CommuneDuCodePostal } from "@/client/types.gen";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { detailFromError } from "@/lib/apiError";

import { useLangue } from "./langue/langue";

/**
 * [.mark] The business address fields: postal code, town, street.
 *
 * Used twice: on the organization ("Platform Settings" → "Preferences") and on
 * the agent (to override it). Decision D3 of 2026-09-16:
 *
 * - the postal code is typed, and the towns that carry it are listed by the
 *   server (the official list embedded in the API, no outside call);
 * - the town is CHOSEN in that list, never typed: it is stored with its INSEE
 *   code, which is what the town recognition reads;
 * - the street is optional, and is not used to recognise towns.
 *
 * ⛔ An address with a postal code but no town chosen is INCOMPLETE, not
 * empty: the parent is told so and must not save it, otherwise a half-typed
 * address would silently clear the saved one.
 */

const CODE_POSTAL = /^\d{5}$/;

export interface ChampAdresseEtablissementProps {
    /** Prefix of the input ids, unique on the page. */
    id: string;
    /** The SAVED address. ⛔ Not the draft: a new value here resets the fields. */
    enregistree: AdresseEtablissement | null | undefined;
    /** `incomplete` is true while a postal code is typed but no town is chosen. */
    onChange: (valeur: AdresseEtablissement | null, incomplete: boolean) => void;
    /** A refusal from the server, shown under the fields. */
    erreur?: string | null;
    /**
     * ⛔ True while the parent saves: a postal code retyped during the save
     * would leave a draft the answer does not reset, and the next save could
     * clear the address while the screen shows it (counter-review of 2026-09-16).
     */
    desactive?: boolean;
}

export const ChampAdresseEtablissement = ({
    id,
    enregistree,
    onChange,
    erreur,
    desactive = false,
}: ChampAdresseEtablissementProps) => {
    const [codePostal, setCodePostal] = useState(enregistree?.code_postal ?? "");
    const [codeInsee, setCodeInsee] = useState(enregistree?.code_insee ?? "");
    const [voie, setVoie] = useState(enregistree?.voie ?? "");
    // Until the list is fetched, the saved town is its only entry: nothing is
    // requested before someone touches the postal code.
    const [communes, setCommunes] = useState<CommuneDuCodePostal[]>(
        enregistree ? [{ code_insee: enregistree.code_insee, nom: enregistree.commune }] : [],
    );
    const { t } = useLangue();
    const [chargement, setChargement] = useState(false);
    const [erreurListe, setErreurListe] = useState<string | null>(null);
    const derniereDemande = useRef<string | null>(null);

    const signaler = (cp: string, insee: string, rue: string, liste: CommuneDuCodePostal[]) => {
        if (!cp.trim() && !insee && !rue.trim()) {
            onChange(null, false);
            return;
        }
        const commune = liste.find((c) => c.code_insee === insee);
        if (!CODE_POSTAL.test(cp) || !commune) {
            onChange(null, true);
            return;
        }
        onChange(
            {
                code_postal: cp,
                code_insee: commune.code_insee,
                commune: commune.nom,
                voie: rue.trim() || null,
            },
            false,
        );
    };

    const chargerCommunes = async (cp: string) => {
        derniereDemande.current = cp;
        setChargement(true);
        setErreurListe(null);
        try {
            const reponse = await getCommunesDuCodePostalApiV1OrganizationsCommunesGet({
                query: { code_postal: cp },
            });
            if (derniereDemande.current !== cp) return;
            if (reponse.error) {
                setErreurListe(detailFromError(reponse.error, "Could not load the towns for this postal code."));
                setCommunes([]);
                return;
            }
            const liste = reponse.data ?? [];
            setCommunes(liste);
            // One town only: chosen for the user. Several: they choose.
            const choix = liste.length === 1 ? liste[0].code_insee : "";
            setCodeInsee(choix);
            if (liste.length === 0) {
                setErreurListe("No town has this postal code.");
            }
            signaler(cp, choix, voie, liste);
        } catch {
            if (derniereDemande.current === cp) {
                setErreurListe("Could not load the towns for this postal code.");
            }
        } finally {
            if (derniereDemande.current === cp) setChargement(false);
        }
    };

    // A new saved value (after a save or a reload) resets the fields.
    useEffect(() => {
        setCodePostal(enregistree?.code_postal ?? "");
        setCodeInsee(enregistree?.code_insee ?? "");
        setVoie(enregistree?.voie ?? "");
        setCommunes(enregistree ? [{ code_insee: enregistree.code_insee, nom: enregistree.commune }] : []);
        setErreurListe(null);
    }, [enregistree?.code_postal, enregistree?.code_insee, enregistree?.commune, enregistree?.voie]); // eslint-disable-line react-hooks/exhaustive-deps

    return (
        <div className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-[8rem_1fr]">
                <div className="space-y-1">
                    <Label htmlFor={`${id}-code-postal`} className="text-xs">
                        {t({ en: "Postal code", fr: "Code postal" })}
                    </Label>
                    <Input
                        id={`${id}-code-postal`}
                        inputMode="numeric"
                        disabled={desactive}
                        maxLength={5}
                        placeholder="60740"
                        value={codePostal}
                        onChange={(e) => {
                            const cp = e.target.value.replace(/\D/g, "").slice(0, 5);
                            setCodePostal(cp);
                            setCodeInsee("");
                            setCommunes([]);
                            setErreurListe(null);
                            signaler(cp, "", voie, []);
                            if (CODE_POSTAL.test(cp)) void chargerCommunes(cp);
                        }}
                    />
                </div>
                <div className="space-y-1">
                    <Label htmlFor={`${id}-commune`} className="text-xs">
                        {t({ en: "Town", fr: "Commune" })}
                    </Label>
                    <select
                        id={`${id}-commune`}
                        className="h-9 w-full rounded-md border bg-background px-2 text-sm disabled:opacity-50"
                        disabled={desactive || communes.length === 0}
                        value={codeInsee}
                        onChange={(e) => {
                            setCodeInsee(e.target.value);
                            signaler(codePostal, e.target.value, voie, communes);
                        }}
                    >
                        <option value="">
                            {chargement
                                ? t({ en: "Loading…", fr: "Chargement…" })
                                : communes.length === 0
                                  ? t({ en: "Type a postal code first", fr: "Saisissez d'abord un code postal" })
                                  : t({ en: "Choose the town", fr: "Choisissez la commune" })}
                        </option>
                        {communes.map((c) => (
                            <option key={c.code_insee} value={c.code_insee}>
                                {c.nom}
                            </option>
                        ))}
                    </select>
                </div>
            </div>
            <div className="space-y-1">
                <Label htmlFor={`${id}-voie`} className="text-xs">
                    {t({ en: "Street (optional)", fr: "Rue (facultatif)" })}
                </Label>
                <Input
                    id={`${id}-voie`}
                    maxLength={200}
                    disabled={desactive}
                    placeholder={t({ en: "12 rue de la Gare", fr: "12 rue de la Gare" })}
                    value={voie}
                    onChange={(e) => {
                        setVoie(e.target.value);
                        signaler(codePostal, codeInsee, e.target.value, communes);
                    }}
                />
            </div>
            {erreurListe && <p className="text-xs text-destructive">{erreurListe}</p>}
            {erreur && (
                <p role="alert" className="text-xs text-destructive">
                    {erreur}
                </p>
            )}
        </div>
    );
};
