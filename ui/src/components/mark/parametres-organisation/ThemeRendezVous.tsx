"use client";

/**
 * [.mark] Theme « Appointments » (chantier l-agent-collegue, L5, P2, P3, P7, P8, P10; new theme
 * decided by Evan in the plan, 07/10; R-7: the fairness window of the « In turn » distribution).
 *
 * The planner's rules, written in the client's database (``reglage_planificateur``,
 * ``type_rendez_vous``): the starting values (the organization's level), then each establishment's.
 * [.mark] cloture-code, F-8 (Evan, 22/10): an establishment has its own complete rules, nothing is
 * inherited; an empty field is the common default (shown in the field, greyed). The starting values
 * prefill a NEW establishment and serve the calls that serve no establishment. The appointment types
 * are a list, so a modal (E4) on a copy (« Cancel » / « Apply »); the theme's « Save » sends the
 * whole planner (E6). Without a client database the theme says so: the rules live there.
 */
import { CalendarClock, Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import {
    getEquipeApiV1OrganizationsEquipeGet,
    getEtablissementsApiV1OrganizationsEtablissementsGet,
    getPlanificateurApiV1OrganizationsPlanificateurGet,
    putPlanificateurApiV1OrganizationsPlanificateurPut,
} from "@/client/sdk.gen";
import type { Etablissement, Planificateur, ReglagesPlanificateur, Sujet, TypeRendezVous } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

import { bornesDe, ChampReglage } from "../ecran/ChampReglage";
import { Intertitre } from "../ecran/Intertitre";
import { type ErreurNommee, Theme } from "../ecran/Theme";
import { type Texte, useLangue } from "../langue/langue";
import {
    CHOIX,
    type Cle,
    FENETRE,
    type Nombre,
    NOMBRES,
    NOMBRES_TRAJETS,
    OUI_NON,
    texteValeur,
} from "./reglages-rendez-vous";
import { type ProprietesThemeOrganisation, useSignaler } from "./ThemesOrganisation";

export const TITRE_RENDEZ_VOUS: Texte = { en: "Appointments", fr: "Rendez-vous" };
const ORGANISATION = "";

/** What the payload sends: empty strings and NaN become null (= the common default). */
export const charge_utile_planificateur = (p: Planificateur): Planificateur => {
    const propre = (r: ReglagesPlanificateur | undefined): ReglagesPlanificateur =>
        Object.fromEntries(
            Object.entries(r ?? {}).map(([k, v]) => [k, v === "" || (typeof v === "number" && Number.isNaN(v)) ? null : v]),
        ) as ReglagesPlanificateur;
    return {
        reglages: propre(p.reglages),
        par_etablissement: Object.fromEntries(Object.entries(p.par_etablissement ?? {}).map(([k, v]) => [k, propre(v)])),
        types: (p.types ?? []).map((x) => ({ ...x, libelle: x.libelle.trim(), sujet: x.sujet || null, etablissement: x.etablissement || null })),
    };
};

function ModaleTypes({
    ouverte,
    types,
    niveau,
    sujets,
    onFermer,
}: {
    ouverte: boolean;
    types: TypeRendezVous[];
    niveau: string | null;
    sujets: Sujet[];
    onFermer: (types: TypeRendezVous[] | null) => void;
}) {
    const { t } = useLangue();
    const [copie, setCopie] = useState<TypeRendezVous[]>([]);
    useEffect(() => {
        if (ouverte) setCopie(types.map((x) => ({ ...x })));
    }, [ouverte, types]);
    const ici = copie.map((x, i) => [x, i] as const).filter(([x]) => (x.etablissement ?? null) === niveau);
    const modifier = (i: number, champ: Partial<TypeRendezVous>) => setCopie((a) => a.map((x, j) => (j === i ? { ...x, ...champ } : x)));
    const fautes: string[] = [];
    ici.forEach(([x]) => {
        if (!x.libelle.trim()) fautes.push(t({ en: "A type has no name.", fr: "Un type n'a pas de nom." }));
        if (!(x.duree_min >= 5 && x.duree_min <= 1440)) fautes.push(t({ en: `${x.libelle || x.code}: length between 5 and 1,440 minutes.`, fr: `${x.libelle || x.code} : durée entre 5 et 1 440 minutes.` }));
    });
    return (
        <Dialog open={ouverte} onOpenChange={(o) => (o ? null : onFermer(null))}>
            <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-4xl" data-testid="modale-types-rdv">
                <DialogHeader>
                    <DialogTitle>{t({ en: "Appointment types", fr: "Types de rendez-vous" })}</DialogTitle>
                    <DialogDescription>
                        {niveau
                            ? t({ en: "This establishment's types: it offers these alone. The subject says who does it (« Team and routing »); empty: the whole team.", fr: "Les types de cet établissement : il propose ceux-là seuls. Le sujet dit qui le fait (« Équipe et routage ») ; vide : toute l'équipe." })
                            : t({ en: "The starting types: copied into a new establishment, and offered on the calls that serve no establishment. The subject says who does it (« Team and routing »); empty: the whole team.", fr: "Les types de départ : recopiés dans un nouvel établissement, et proposés aux appels qui ne servent aucun établissement. Le sujet dit qui le fait (« Équipe et routage ») ; vide : toute l'équipe." })}
                    </DialogDescription>
                </DialogHeader>
                <div className="space-y-2">
                    {ici.map(([x, i]) => (
                        <div key={i} className="grid gap-2 rounded border border-border p-2 sm:grid-cols-6" data-testid={`type-rdv-${x.code}`}>
                            <Input aria-label={t({ en: "Code", fr: "Code" })} value={x.code} className="font-mono text-xs" onChange={(e) => modifier(i, { code: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_") })} />
                            <Input aria-label={t({ en: "Name", fr: "Libellé" })} placeholder={t({ en: "Name", fr: "Libellé" })} value={x.libelle} className="sm:col-span-2" onChange={(e) => modifier(i, { libelle: e.target.value })} />
                            <label className="space-y-0.5 text-xs text-muted-foreground">
                                <span>{t({ en: "Length (min)", fr: "Durée (min)" })}</span>
                                <Input aria-label={t({ en: "Length (min)", fr: "Durée (min)" })} type="number" min={5} max={1440} value={x.duree_min} onChange={(e) => modifier(i, { duree_min: Number(e.target.value) })} />
                            </label>
                            <select aria-label={t({ en: "Subject", fr: "Sujet" })} className="rounded border border-border bg-background px-2 py-1 text-sm sm:col-span-2" value={x.sujet ?? ""} onChange={(e) => modifier(i, { sujet: e.target.value || null })}>
                                <option value="">{t({ en: "The whole team", fr: "Toute l'équipe" })}</option>
                                {sujets.map((s) => (
                                    <option key={s.code} value={s.code}>
                                        {s.libelle}
                                    </option>
                                ))}
                            </select>
                            <label className="space-y-0.5 text-xs text-muted-foreground">
                                <span>{t({ en: "Margin before (min)", fr: "Marge avant (min)" })}</span>
                                <Input aria-label={t({ en: "Margin before (min)", fr: "Marge avant (min)" })} type="number" min={0} max={480} value={x.marge_avant_min ?? 0} onChange={(e) => modifier(i, { marge_avant_min: Number(e.target.value) })} />
                            </label>
                            <label className="space-y-0.5 text-xs text-muted-foreground">
                                <span>{t({ en: "Margin after (min)", fr: "Marge après (min)" })}</span>
                                <Input aria-label={t({ en: "Margin after (min)", fr: "Marge après (min)" })} type="number" min={0} max={480} value={x.marge_apres_min ?? 0} onChange={(e) => modifier(i, { marge_apres_min: Number(e.target.value) })} />
                            </label>
                            <label className="flex items-center gap-2 text-sm">
                                <input type="checkbox" checked={x.actif ?? true} onChange={(e) => modifier(i, { actif: e.target.checked })} />
                                {t({ en: "Offered", fr: "Proposé" })}
                            </label>
                            <Button variant="ghost" size="sm" aria-label={t({ en: "Remove", fr: "Retirer" })} onClick={() => setCopie((a) => a.filter((_, j) => j !== i))}>
                                <Trash2 className="h-4 w-4" />
                            </Button>
                        </div>
                    ))}
                    <Button
                        variant="outline"
                        size="sm"
                        data-testid="ajouter-type-rdv"
                        onClick={() =>
                            setCopie((a) => {
                                const codes = a.filter((x) => (x.etablissement ?? null) === niveau).map((x) => x.code);
                                let n = codes.length + 1;
                                while (codes.includes(`type_${n}`)) n += 1;
                                return [...a, { code: `type_${n}`, etablissement: niveau, libelle: "", duree_min: 60, sujet: null, marge_avant_min: 0, marge_apres_min: 0, actif: true }];
                            })
                        }
                    >
                        <Plus className="mr-1 h-4 w-4" />
                        {t({ en: "Add a type", fr: "Ajouter un type" })}
                    </Button>
                    {fautes.length > 0 && (
                        <ul className="text-sm text-destructive" data-testid="fautes-types-rdv">
                            {fautes.map((f, i) => (
                                <li key={i}>{f}</li>
                            ))}
                        </ul>
                    )}
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => onFermer(null)}>
                        {t({ en: "Cancel", fr: "Annuler" })}
                    </Button>
                    <Button onClick={() => onFermer(copie)} disabled={fautes.length > 0} data-testid="appliquer-types-rdv">
                        {t({ en: "Apply", fr: "Appliquer" })}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

export const ThemeRendezVous = ({
    ouvert,
    onBasculer,
    signaler,
    baseRattachee,
    adresseConnue = null,
}: ProprietesThemeOrganisation & { baseRattachee: boolean | null; adresseConnue?: boolean | null }) => {
    const { t } = useLangue();
    const { user, loading: authLoading } = useAuth();
    const [enregistre, setEnregistre] = useState<Planificateur | null>(null);
    const [brouillon, setBrouillon] = useState<Planificateur | null>(null);
    const [etablissements, setEtablissements] = useState<Etablissement[]>([]);
    const [sujets, setSujets] = useState<Sujet[]>([]);
    const [niveau, setNiveau] = useState<string>(ORGANISATION);
    const [modale, setModale] = useState(false);
    const [erreur, setErreur] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);
    const dejaLu = useRef(false);

    useEffect(() => {
        if (authLoading || !user || !baseRattachee || dejaLu.current) return;
        dejaLu.current = true;
        void (async () => {
            const [p, sites, equipe] = await Promise.all([
                getPlanificateurApiV1OrganizationsPlanificateurGet(),
                getEtablissementsApiV1OrganizationsEtablissementsGet(),
                getEquipeApiV1OrganizationsEquipeGet(),
            ]);
            setEtablissements(sites?.data?.etablissements ?? []);
            setSujets(equipe?.data?.sujets ?? []);
            if (!p || p.error || !p.data) {
                setErreur(detailFromError(p?.error, "Planner unreadable"));
                return;
            }
            setEnregistre(p.data);
            setBrouillon(p.data);
        })();
    }, [authLoading, user, baseRattachee]);

    const modifie = useMemo(
        () => brouillon !== null && JSON.stringify(charge_utile_planificateur(brouillon)) !== JSON.stringify(charge_utile_planificateur(enregistre ?? {})),
        [brouillon, enregistre],
    );
    const defauts = brouillon?.defauts ?? {};
    const organisation = brouillon?.reglages ?? {};
    const courant: ReglagesPlanificateur = (niveau ? brouillon?.par_etablissement?.[niveau] : organisation) ?? {};
    /** F-8: what an empty field means at any level: the common default (an establishment inherits nothing). */
    const herite = (cle: Cle) => defauts[cle];
    const poser = (cle: Cle, valeur: unknown) =>
        setBrouillon((a) => {
            if (!a) return a;
            if (!niveau) return { ...a, reglages: { ...(a.reglages ?? {}), [cle]: valeur } };
            return { ...a, par_etablissement: { ...(a.par_etablissement ?? {}), [niveau]: { ...(a.par_etablissement?.[niveau] ?? {}), [cle]: valeur } } };
        });

    const erreurs: ErreurNommee[] = [];
    if (brouillon) {
        const niveaux: Array<[string, ReglagesPlanificateur]> = [[ORGANISATION, brouillon.reglages ?? {}], ...Object.entries(brouillon.par_etablissement ?? {})];
        for (const [n, r] of niveaux)
            for (const f of [...NOMBRES, ...NOMBRES_TRAJETS, FENETRE]) {
                const v = r[f.cle] as number | null | undefined;
                if (v !== null && v !== undefined && !(v >= f.min && v <= f.max))
                    erreurs.push({ cle: f.cle, libelle: t(f.libelle), message: t({ en: `between ${f.min} and ${f.max}`, fr: `entre ${f.min} et ${f.max}` }), afficher: () => setNiveau(n) });
            }
    }
    useSignaler("rendez-vous", modifie, erreurs.length > 0, signaler);
    /** A radius at any level: it measures from the business address, which the server needs to apply it. */
    const rayonRegle = [brouillon?.reglages, ...Object.values(brouillon?.par_etablissement ?? {})].some(
        (r) => r?.zone_rayon_km !== null && r?.zone_rayon_km !== undefined,
    );

    const enregistrer = async () => {
        if (!brouillon) return;
        setEnCours(true);
        setErreur(null);
        const r = await putPlanificateurApiV1OrganizationsPlanificateurPut({ body: charge_utile_planificateur(brouillon) });
        setEnCours(false);
        if (r.error || !r.data) {
            setErreur(detailFromError(r.error, "Planner not saved"));
            return;
        }
        setEnregistre(r.data);
        setBrouillon(r.data);
        toast.success(t({ en: "Appointment rules saved", fr: "Règles des rendez-vous enregistrées" }));
    };

    const typesIci = (brouillon?.types ?? []).filter((x) => (x.etablissement ?? "") === niveau);
    /** E8: the fairness window plays a role only when a level uses « In turn »; otherwise it stays
     *  shown and says so (nothing is hidden that could matter once an establishment picks the mode). */
    const modeIci = (courant.repartition ?? herite("repartition")) as string | null | undefined;
    const tourDeRoleUtile =
        modeIci === "tour_de_role" ||
        (!niveau && Object.values(brouillon?.par_etablissement ?? {}).some((r) => r?.repartition === "tour_de_role"));
    const sansEffet: Texte = {
        en: "No effect here: this level does not distribute in turn.",
        fr: "Sans effet ici : ce niveau ne répartit pas au tour de rôle.",
    };
    const nombre = (f: Nombre) => (
        <ChampReglage
            key={f.cle}
            cle={f.cle}
            idControle={`rdv-${f.cle}`}
            libelle={f.libelle}
            aides={[f.aide]}
            bornes={bornesDe(f.min, f.max)}
            note={f.cle === FENETRE.cle && !tourDeRoleUtile ? sansEffet : null}
        >
            <Input
                id={`rdv-${f.cle}`}
                type="number"
                min={f.min}
                max={f.max}
                step={f.pas ?? 1}
                placeholder={`${t({ en: "default", fr: "défaut" })} : ${texteValeur(herite(f.cle), t)}`}
                value={(courant[f.cle] as number | null | undefined) ?? ""}
                onChange={(e) => poser(f.cle, e.target.value === "" ? null : Number(e.target.value))}
            />
        </ChampReglage>
    );
    const ouiNon = (f: (typeof OUI_NON)[number]) => (
        <ChampReglage key={f.cle} cle={f.cle} idControle={`rdv-${f.cle}`} libelle={f.libelle} aides={[f.aide]}>
            <select
                id={`rdv-${f.cle}`}
                className="rounded border border-border bg-background px-2 py-1 text-sm"
                value={courant[f.cle] === null || courant[f.cle] === undefined ? "" : String(courant[f.cle])}
                onChange={(e) => poser(f.cle, e.target.value === "" ? null : e.target.value === "true")}
            >
                <option value="">{`${t({ en: "Default", fr: "Défaut" })} (${texteValeur(herite(f.cle), t)})`}</option>
                <option value="true">{t({ en: "Yes", fr: "Oui" })}</option>
                <option value="false">{t({ en: "No", fr: "Non" })}</option>
            </select>
        </ChampReglage>
    );
    const choix = (f: (typeof CHOIX)[number]) => (
        <ChampReglage key={f.cle} cle={f.cle} idControle={`rdv-${f.cle}`} libelle={f.libelle} aides={[f.aide]}>
            <select
                id={`rdv-${f.cle}`}
                className="rounded border border-border bg-background px-2 py-1 text-sm"
                value={(courant[f.cle] as string | null | undefined) ?? ""}
                onChange={(e) => poser(f.cle, e.target.value || null)}
            >
                <option value="">{`${t({ en: "Default", fr: "Défaut" })} (${t(f.options.find((o) => o.valeur === herite(f.cle))?.texte ?? { en: "—", fr: "—" })})`}</option>
                {f.options.map((o) => (
                    <option key={o.valeur} value={o.valeur}>
                        {t(o.texte)}
                    </option>
                ))}
            </select>
        </ChampReglage>
    );

    return (
        <Theme
            id="rendez-vous"
            icone={CalendarClock}
            titre={TITRE_RENDEZ_VOUS}
            description={{
                en: "The planner's rules: appointment types, ranges, zone, journeys, distribution and fallback, each establishment's own.",
                fr: "Les règles du planificateur : types de rendez-vous, plages, zone, trajets, répartition et repli, propres à chaque établissement.",
            }}
            resume={[
                baseRattachee === false
                    ? t({ en: "No database attached", fr: "Aucune base rattachée" })
                    : brouillon
                      ? t({ en: `${(brouillon.types ?? []).length} appointment type(s)`, fr: `${(brouillon.types ?? []).length} type(s) de rendez-vous` })
                      : null,
            ]}
            ouvert={ouvert}
            onBasculer={onBasculer}
            modifie={modifie}
            erreurs={erreurs}
            enregistrement={baseRattachee && brouillon ? { onEnregistrer: () => void enregistrer(), enCours } : undefined}
        >
            {!baseRattachee ? (
                <p className="text-sm text-muted-foreground" data-testid="rdv-sans-base">
                    {baseRattachee === null
                        ? t({ en: "Loading…", fr: "Chargement…" })
                        : t({
                              en: "The planner's rules live in the client's database: attach one in « Client data » first.",
                              fr: "Les règles du planificateur vivent dans la base du client : rattachez-en une dans « Données du client » d'abord.",
                          })}
                </p>
            ) : brouillon === null ? (
                <p className="text-sm text-muted-foreground">{erreur ?? t({ en: "Loading…", fr: "Chargement…" })}</p>
            ) : (
                <>
                    <Intertitre id="rdv-groupe-niveau" titre={{ en: "Level", fr: "Niveau" }}>
                        <ChampReglage
                            cle="niveau"
                            idControle="rdv-niveau-choix"
                            libelle={{ en: "Rules of", fr: "Règles de" }}
                            aides={[
                                {
                                    en: "Each establishment has its own complete rules: an empty field is the common default, nothing comes from elsewhere. The starting values are copied into a new establishment when it is created, and serve the calls that serve no establishment.",
                                    fr: "Chaque établissement a ses propres règles complètes : un champ vide est le défaut commun, rien ne vient d'ailleurs. Les valeurs de départ sont recopiées dans un nouvel établissement à sa création, et servent aux appels qui ne servent aucun établissement.",
                                },
                            ]}
                        >
                            <select id="rdv-niveau-choix" className="rounded border border-border bg-background px-2 py-1 text-sm" value={niveau} onChange={(e) => setNiveau(e.target.value)}>
                                <option value={ORGANISATION}>{t({ en: "Starting values of a new establishment", fr: "Valeurs de départ d'un nouvel établissement" })}</option>
                                {etablissements.map((e) => (
                                    <option key={e.id} value={e.id}>
                                        {e.nom}
                                    </option>
                                ))}
                            </select>
                        </ChampReglage>
                    </Intertitre>

                    <Intertitre id="rdv-groupe-types" titre={{ en: "Appointment types", fr: "Types de rendez-vous" }}>
                        <ChampReglage cle="types" libelle={{ en: "Types offered", fr: "Types proposés" }} aides={[{ en: "Code, name, length, who does it, margins before and after.", fr: "Code, libellé, durée, qui le fait, marges avant et après." }]}>
                            <div className="flex flex-wrap items-center gap-3">
                                <Button variant="outline" size="sm" onClick={() => setModale(true)} data-testid="ouvrir-types-rdv">
                                    {t({ en: "Edit the types…", fr: "Modifier les types…" })}
                                </Button>
                                <span className="text-xs text-muted-foreground">{typesIci.map((x) => `${x.libelle} (${x.duree_min} min)`).join(" · ") || t({ en: "None at this level", fr: "Aucun à ce niveau" })}</span>
                            </div>
                        </ChampReglage>
                    </Intertitre>

                    <Intertitre id="rdv-groupe-creneaux" titre={{ en: "Slots", fr: "Créneaux" }}>
                        {NOMBRES.map(nombre)}
                        <ChampReglage
                            cle="plages"
                            idControle="rdv-plages"
                            libelle={{ en: "Booking ranges", fr: "Plages de rendez-vous" }}
                            aides={[{ en: "Same format as the opening hours (one line per day). Empty: the establishment's opening hours.", fr: "Même format que les horaires d'ouverture (une ligne par jour). Vide : les horaires d'ouverture de l'établissement." }]}
                        >
                            <Textarea id="rdv-plages" rows={4} className="font-mono text-xs" placeholder={t({ en: "default: the opening hours", fr: "défaut : les horaires d'ouverture" })} value={courant.plages ?? ""} onChange={(e) => poser("plages", e.target.value || null)} />
                        </ChampReglage>
                        {choix(CHOIX[2])}
                    </Intertitre>

                    <Intertitre id="rdv-groupe-zone" titre={{ en: "Zone and journeys", fr: "Zone et trajets" }}>
                        {ouiNon(OUI_NON[0])}
                        {NOMBRES_TRAJETS.map(nombre)}
                        {adresseConnue === false && rayonRegle && (
                            <p className="text-xs text-destructive" data-testid="rdv-rayon-sans-adresse" role="note">
                                {t({
                                    en: "A radius is set, but no business address is saved (theme « Establishments »): the zone is not applied to a call whose establishment has no address of its own.",
                                    fr: "Un rayon est réglé, mais aucune adresse de l'entreprise n'est enregistrée (thème « Établissements ») : la zone n'est pas appliquée à un appel dont l'établissement n'a pas d'adresse propre.",
                                })}
                            </p>
                        )}
                        <ChampReglage
                            cle="zone_communes"
                            idControle="rdv-zone_communes"
                            libelle={{ en: "Zone served: communes (INSEE codes)", fr: "Zone desservie : communes (codes INSEE)" }}
                            aides={[{ en: "Separated by commas. Empty everywhere: no list.", fr: "Séparés par des virgules. Vide partout : pas de liste." }]}
                        >
                            <Input
                                id="rdv-zone_communes"
                                placeholder={`${t({ en: "default", fr: "défaut" })} : ${texteValeur(herite("zone_communes"), t)}`}
                                value={(courant.zone_communes ?? []).join(", ")}
                                onChange={(e) => {
                                    const codes = e.target.value.split(/[,\s]+/).map((c) => c.trim().toUpperCase()).filter(Boolean);
                                    poser("zone_communes", codes.length ? codes : null);
                                }}
                            />
                        </ChampReglage>
                    </Intertitre>

                    <Intertitre id="rdv-groupe-repartition" titre={{ en: "Distribution and fallback", fr: "Répartition et repli" }}>
                        {choix(CHOIX[0])}
                        {nombre(FENETRE)}
                        {ouiNon(OUI_NON[1])}
                        {choix(CHOIX[1])}
                    </Intertitre>

                    {erreur && (
                        <p className="text-sm text-destructive" role="alert">
                            {erreur}
                        </p>
                    )}
                    <ModaleTypes
                        ouverte={modale}
                        types={brouillon.types ?? []}
                        niveau={niveau || null}
                        sujets={sujets}
                        onFermer={(types) => {
                            setModale(false);
                            if (types) setBrouillon((a) => (a ? { ...a, types } : a));
                        }}
                    />
                </>
            )}
        </Theme>
    );
};
