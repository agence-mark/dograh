"use client";

/**
 * [.mark] The appointments and the zone of ONE fiche (chantier agents-specialises, lot 11 = lot 4 of
 * the fiche plan, M2: « réglages des rendez-vous et zone desservie » in the fiche).
 *
 * Drawn inside the modal of the establishments, as two groups (E1: subtitles, never menus). The values
 * are those of `Planificateur.par_etablissement[fiche]`, written in the client's database; no storage
 * moves. An agent that chose a fiche inherits NOTHING from the organization (C3), so an empty field
 * shows the common default, in grey, as what the call will use. The appointment TYPES stay in the theme
 * « Appointments » (C6, unchanged), where they are edited as a list.
 *
 * The controls, bounds, labels and help are the ones of the theme « Appointments »
 * (`reglages-rendez-vous.ts`): one list for both screens.
 */
import type { ReglagesPlanificateur } from "@/client/types.gen";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

import { bornesDe, ChampReglage } from "../ecran/ChampReglage";
import { Intertitre } from "../ecran/Intertitre";
import { type Texte, useLangue } from "../langue/langue";
import { CHOIX, type Cle, FENETRE, type Nombre, NOMBRES, NOMBRES_TRAJETS, OUI_NON, texteValeur } from "./reglages-rendez-vous";

/** The technical name shown in grey: where the value is stored. */
const cleDe = (cle: Cle) => `par_etablissement.${cle}`;

export function FicheRendezVous({
    id,
    reglages,
    defauts,
    onPoser,
}: {
    /** The fiche's identifier (for the ids of the controls). */
    id: string;
    reglages: ReglagesPlanificateur;
    /** The common defaults, read from the planner (shown as what an empty field means). */
    defauts: ReglagesPlanificateur;
    onPoser: (cle: Cle, valeur: unknown) => void;
}) {
    const { t } = useLangue();
    const idControle = (cle: Cle) => `fiche-rdv-${id}-${cle}`;
    const defaut = (cle: Cle) => `${t({ en: "default", fr: "défaut" })} : ${texteValeur(defauts[cle], t)}`;
    const modeIci = (reglages.repartition ?? defauts.repartition) as string | null | undefined;
    const sansEffet: Texte = {
        en: "No effect here: this fiche does not distribute in turn.",
        fr: "Sans effet ici : cette fiche ne répartit pas au tour de rôle.",
    };

    const nombre = (f: Nombre) => (
        <ChampReglage
            key={f.cle}
            cle={cleDe(f.cle)}
            idControle={idControle(f.cle)}
            libelle={f.libelle}
            aides={[f.aide]}
            bornes={bornesDe(f.min, f.max)}
            note={f.cle === FENETRE.cle && modeIci !== "tour_de_role" ? sansEffet : null}
        >
            <Input
                id={idControle(f.cle)}
                type="number"
                min={f.min}
                max={f.max}
                step={f.pas ?? 1}
                placeholder={defaut(f.cle)}
                value={(reglages[f.cle] as number | null | undefined) ?? ""}
                onChange={(e) => onPoser(f.cle, e.target.value === "" ? null : Number(e.target.value))}
            />
        </ChampReglage>
    );
    const ouiNon = (f: (typeof OUI_NON)[number]) => (
        <ChampReglage key={f.cle} cle={cleDe(f.cle)} idControle={idControle(f.cle)} libelle={f.libelle} aides={[f.aide]}>
            <select
                id={idControle(f.cle)}
                className="rounded border border-border bg-background px-2 py-1 text-sm"
                value={reglages[f.cle] === null || reglages[f.cle] === undefined ? "" : String(reglages[f.cle])}
                onChange={(e) => onPoser(f.cle, e.target.value === "" ? null : e.target.value === "true")}
            >
                <option value="">{`${t({ en: "Default", fr: "Défaut" })} (${texteValeur(defauts[f.cle], t)})`}</option>
                <option value="true">{t({ en: "Yes", fr: "Oui" })}</option>
                <option value="false">{t({ en: "No", fr: "Non" })}</option>
            </select>
        </ChampReglage>
    );
    const choix = (f: (typeof CHOIX)[number]) => (
        <ChampReglage key={f.cle} cle={cleDe(f.cle)} idControle={idControle(f.cle)} libelle={f.libelle} aides={[f.aide]}>
            <select
                id={idControle(f.cle)}
                className="rounded border border-border bg-background px-2 py-1 text-sm"
                value={(reglages[f.cle] as string | null | undefined) ?? ""}
                onChange={(e) => onPoser(f.cle, e.target.value || null)}
            >
                <option value="">{`${t({ en: "Default", fr: "Défaut" })} (${t(f.options.find((o) => o.valeur === defauts[f.cle])?.texte ?? { en: "—", fr: "—" })})`}</option>
                {f.options.map((o) => (
                    <option key={o.valeur} value={o.valeur}>
                        {t(o.texte)}
                    </option>
                ))}
            </select>
        </ChampReglage>
    );

    return (
        <>
            <Intertitre
                id="fiche-rendez-vous"
                titre={{ en: "Appointments", fr: "Rendez-vous" }}
                description={{
                    en: "The planner's rules for this fiche. An empty field is the common default: nothing is inherited from the organization. The appointment types are edited in the theme « Appointments ».",
                    fr: "Les règles du planificateur pour cette fiche. Un champ vide est le défaut commun : rien n'est hérité de l'organisation. Les types de rendez-vous se modifient dans le thème « Rendez-vous ».",
                }}
            >
                {NOMBRES.map(nombre)}
                <ChampReglage
                    cle={cleDe("plages")}
                    idControle={idControle("plages")}
                    libelle={{ en: "Booking ranges", fr: "Plages de rendez-vous" }}
                    aides={[
                        {
                            en: "Same format as the opening hours (one line per day). Empty: the fiche's opening hours.",
                            fr: "Même format que les horaires d'ouverture (une ligne par jour). Vide : les horaires d'ouverture de la fiche.",
                        },
                    ]}
                    bornes={bornesDe(undefined, 4000)}
                >
                    <Textarea
                        id={idControle("plages")}
                        rows={4}
                        maxLength={4000}
                        className="font-mono text-xs"
                        placeholder={t({ en: "the fiche's hours", fr: "les horaires de la fiche" })}
                        value={reglages.plages ?? ""}
                        onChange={(e) => onPoser("plages", e.target.value || null)}
                    />
                </ChampReglage>
                {choix(CHOIX[2])}
                {choix(CHOIX[0])}
                {nombre(FENETRE)}
                {ouiNon(OUI_NON[1])}
                {choix(CHOIX[1])}
            </Intertitre>

            <Intertitre
                id="fiche-zone"
                titre={{ en: "Zone and journeys", fr: "Zone et trajets" }}
                description={{
                    en: "Where this fiche's people go, and how the journeys are counted. Empty: no radius, no list.",
                    fr: "Où se rendent les personnes de cette fiche, et comment les trajets sont comptés. Vide : ni rayon, ni liste.",
                }}
            >
                {ouiNon(OUI_NON[0])}
                {NOMBRES_TRAJETS.map(nombre)}
                <ChampReglage
                    cle={cleDe("zone_communes")}
                    idControle={idControle("zone_communes")}
                    libelle={{ en: "Zone served: communes (INSEE codes)", fr: "Zone desservie : communes (codes INSEE)" }}
                    aides={[{ en: "Separated by commas. Empty: no list.", fr: "Séparés par des virgules. Vide : pas de liste." }]}
                    bornes={bornesDe(undefined, 500)}
                >
                    <Input
                        id={idControle("zone_communes")}
                        placeholder={defaut("zone_communes")}
                        value={(reglages.zone_communes ?? []).join(", ")}
                        onChange={(e) => {
                            const codes = e.target.value.split(/[,\s]+/).map((c) => c.trim().toUpperCase()).filter(Boolean);
                            onPoser("zone_communes", codes.length ? codes : null);
                        }}
                    />
                </ChampReglage>
            </Intertitre>
        </>
    );
}
