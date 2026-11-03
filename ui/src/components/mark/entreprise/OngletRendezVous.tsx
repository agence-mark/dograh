"use client";

/**
 * [.mark] K4 : « Rendez-vous » comme la maquette (`entreprise.tsx`, OngletRendezVous) : « Règles de » (un établissement
 * ou les valeurs de départ), le tableau des types (un clic ouvre la fenêtre du type, l'interrupteur « Proposé » agit
 * seul), puis trois sections en lignes (Créneaux, Zone et trajets, Répartition et repli) dont « Modifier » ouvre la
 * fenêtre. Mêmes règles, mêmes bornes et mêmes aides que l'ancien thème (`reglages-rendez-vous.ts`) ; chaque fenêtre
 * enregistre le planificateur entier avec sa part changée (la route remplace tout) et dit son résultat par `notifier`.
 */
import { CalendarClock, Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
    getEquipeApiV1OrganizationsEquipeGet,
    getEtablissementsApiV1OrganizationsEtablissementsGet,
    getPlanificateurApiV1OrganizationsPlanificateurGet,
    putPlanificateurApiV1OrganizationsPlanificateurPut,
} from "@/client/sdk.gen";
import type { Etablissement, Planificateur, ReglagesPlanificateur, Sujet, TypeRendezVous } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { detailFromError } from "@/lib/apiError";

import { type Texte, useLangue } from "../langue/langue";
import { notifier } from "../notifications";
import { BoutonAppliquerATous } from "../parametres-organisation/BoutonAppliquerATous";
import {
    CHOIX,
    FENETRE,
    type Nombre,
    NOMBRES,
    NOMBRES_TRAJETS,
    OUI_NON,
    texteValeur,
} from "../parametres-organisation/reglages-rendez-vous";
import { charge_utile_planificateur } from "../parametres-organisation/ThemeRendezVous";
import { EtatVide } from "../studio/etat-vide";
import { type Champ, FenetreChamps, type Valeurs } from "../studio/fenetre-champs";
import { Liste } from "../studio/liste";
import { Info } from "../studio/marques";
import { Cellule, Ligne, Tableau, TitreTableau } from "../studio/tableau";
import { SectionLue } from "./section-lue";

const DEPART = "";

export function OngletRendezVous({ baseRattachee }: { baseRattachee: boolean | null }) {
    const { t } = useLangue();
    const [plan, setPlan] = useState<Planificateur | null>(null);
    const [etablissements, setEtablissements] = useState<Etablissement[]>([]);
    const [sujets, setSujets] = useState<Sujet[]>([]);
    const [illisible, setIllisible] = useState(false);
    const [niveau, setNiveau] = useState(DEPART);
    const [type, setType] = useState<TypeRendezVous | "nouveau" | null>(null);

    const relire = useCallback(async () => {
        const [p, sites, equipe] = await Promise.all([
            getPlanificateurApiV1OrganizationsPlanificateurGet(),
            getEtablissementsApiV1OrganizationsEtablissementsGet(),
            getEquipeApiV1OrganizationsEquipeGet(),
        ]);
        setEtablissements(sites?.data?.etablissements ?? []);
        setSujets(equipe?.data?.sujets ?? []);
        setIllisible(Boolean(p?.error) || !p?.data);
        if (p?.data) setPlan(p.data);
    }, []);
    useEffect(() => {
        if (baseRattachee) void relire();
    }, [baseRattachee, relire]);

    if (baseRattachee === false) {
        return (
            <p className="pt-4 text-sm text-muted-foreground" data-testid="rdv-sans-base">
                {t({
                    en: "The planner's rules live in the client's database: attach one in Data and automations first.",
                    fr: "Les règles du planificateur vivent dans la base du client : rattachez-en une dans Base et automatisations d'abord.",
                })}
            </p>
        );
    }
    if (illisible) return <EtatVide cas="erreur" reessayer={() => void relire()} />;
    if (!plan) return <EtatVide cas="chargement" />;

    const defauts = plan.defauts ?? {};
    const courant: ReglagesPlanificateur = (niveau ? plan.par_etablissement?.[niveau] : plan.reglages) ?? {};
    const typesIci = (plan.types ?? []).filter((x) => (x.etablissement ?? "") === niveau);
    const nomNiveau = (id: string) => etablissements.find((e) => e.id === id)?.nom ?? id;
    const departLibelle = t({ en: "Starting values of a new establishment", fr: "Valeurs de départ d'un nouvel établissement" });
    const nomsNiveaux = [...etablissements.map((e) => e.nom), departLibelle];
    const idDeNom = (nom: string) => (nom === departLibelle ? DEPART : (etablissements.find((e) => e.nom === nom)?.id ?? DEPART));
    const sujetOuvert = (code: string | null | undefined) => sujets.find((s) => s.code === code)?.libelle;

    const ecrire = async (suivant: Planificateur, succes: Texte): Promise<boolean> => {
        const r = await putPlanificateurApiV1OrganizationsPlanificateurPut({ body: charge_utile_planificateur(suivant) });
        if (r.error || !r.data) {
            notifier.echec(
                { fr: "Les règles n'ont pas été enregistrées.", en: "The rules were not saved." },
                { erreur: detailFromError(r.error, "Planner not saved") },
            );
            return false;
        }
        notifier.succes(succes);
        setPlan(r.data);
        return true;
    };

    const posePart = (part: ReglagesPlanificateur): Planificateur =>
        niveau
            ? { ...plan, par_etablissement: { ...(plan.par_etablissement ?? {}), [niveau]: { ...(plan.par_etablissement?.[niveau] ?? {}), ...part } } }
            : { ...plan, reglages: { ...(plan.reglages ?? {}), ...part } };

    // ---- champs d'une section, tirés des définitions de l'ancien thème ----
    const champNombre = (f: Nombre): Champ => ({
        id: f.cle,
        t: "nombre",
        l: t(f.libelle),
        v: courant[f.cle] === null || courant[f.cle] === undefined ? "" : String(courant[f.cle]),
        min: f.min,
        max: f.max,
        info: `${t(f.aide)} ${t({ en: "Empty: the common default", fr: "Vide : le défaut commun" })} (${texteValeur(defauts[f.cle], t)}).`,
    });
    const defautChoix = (f: (typeof CHOIX)[number]) => t(f.options.find((o) => o.valeur === defauts[f.cle])?.texte ?? { en: "—", fr: "—" });
    const champChoix = (f: (typeof CHOIX)[number]): Champ => ({
        id: f.cle,
        t: "choix",
        l: t(f.libelle),
        o: [`${t({ en: "Default", fr: "Défaut" })} (${defautChoix(f)})`, ...f.options.map((o) => t(o.texte))],
        v: f.options.find((o) => o.valeur === courant[f.cle]) ? t(f.options.find((o) => o.valeur === courant[f.cle])!.texte) : `${t({ en: "Default", fr: "Défaut" })} (${defautChoix(f)})`,
        info: t(f.aide),
    });
    const libOuiNon = (f: (typeof OUI_NON)[number]) => {
        const oui = t({ en: "Yes", fr: "Oui" });
        const non = t({ en: "No", fr: "Non" });
        const dflt = `${t({ en: "Default", fr: "Défaut" })} (${defauts[f.cle] ? oui : non})`;
        return { oui, non, dflt };
    };
    const champOuiNon = (f: (typeof OUI_NON)[number]): Champ => {
        const { oui, non, dflt } = libOuiNon(f);
        const v = courant[f.cle];
        return { id: f.cle, t: "choix", l: t(f.libelle), o: [dflt, oui, non], v: v === true ? oui : v === false ? non : dflt, info: t(f.aide) };
    };
    const lireNombre = (valeurs: Valeurs, f: Nombre) => (String(valeurs[f.cle] ?? "").trim() === "" ? null : Number(valeurs[f.cle]));
    const lireChoix = (valeurs: Valeurs, f: (typeof CHOIX)[number]) => f.options.find((o) => t(o.texte) === valeurs[f.cle])?.valeur ?? null;
    const lireOuiNon = (valeurs: Valeurs, f: (typeof OUI_NON)[number]) => {
        const { oui, non } = libOuiNon(f);
        return valeurs[f.cle] === oui ? true : valeurs[f.cle] === non ? false : null;
    };
    const verifierNombres = (liste: Nombre[]) => (valeurs: Valeurs) => {
        const fautes: Record<string, string> = {};
        for (const f of liste) {
            const n = lireNombre(valeurs, f);
            if (n !== null && !(n >= f.min && n <= f.max)) fautes[f.cle] = t({ en: `Between ${f.min} and ${f.max}.`, fr: `Entre ${f.min} et ${f.max}.` });
        }
        return Object.keys(fautes).length ? fautes : null;
    };
    const texteOuiNon = (f: (typeof OUI_NON)[number]) => {
        const v = courant[f.cle];
        return v === null || v === undefined ? `${texteValeur(defauts[f.cle], t)} (${t({ en: "default", fr: "défaut" })})` : texteValeur(v, t);
    };
    const texteNombre = (f: Nombre, unite = "") => {
        const v = courant[f.cle];
        return v === null || v === undefined ? `${texteValeur(defauts[f.cle], t)}${unite} (${t({ en: "default", fr: "défaut" })})` : `${v}${unite}`;
    };
    const texteChoix = (f: (typeof CHOIX)[number]) => {
        const o = f.options.find((x) => x.valeur === courant[f.cle]);
        return o ? t(o.texte) : `${defautChoix(f)} (${t({ en: "default", fr: "défaut" })})`;
    };

    // ---- types ----
    const typeOuvert = type && type !== "nouveau" ? type : undefined;
    const enregistrerType = async (valeurs: Valeurs) => {
        const code = String(valeurs.code).trim();
        const ecrit: TypeRendezVous = {
            ...(typeOuvert ?? { actif: true }),
            code,
            etablissement: niveau || null,
            libelle: String(valeurs.libelle).trim(),
            duree_min: Number(valeurs.duree),
            sujet: sujets.find((s) => s.libelle === valeurs.sujet)?.code ?? null,
            marge_avant_min: Number(valeurs.avant),
            marge_apres_min: Number(valeurs.apres),
            actif: valeurs.actif === true,
        };
        const types = typeOuvert ? (plan.types ?? []).map((x) => (x === typeOuvert ? ecrit : x)) : [...(plan.types ?? []), ecrit];
        await ecrire({ ...plan, types }, { fr: "Type enregistré.", en: "Type saved." });
    };
    const verifierType = (valeurs: Valeurs) => {
        const fautes: Record<string, string> = {};
        const code = String(valeurs.code).trim();
        if (!/^[a-z0-9_]+$/.test(code)) fautes.code = t({ en: "Lower case, digits and underscores.", fr: "Minuscules, chiffres et tirets bas." });
        else if (typesIci.some((x) => x.code === code && x !== typeOuvert)) fautes.code = t({ en: "This code is already used.", fr: "Ce code est déjà pris." });
        if (!String(valeurs.libelle).trim()) fautes.libelle = t({ en: "A type needs a name.", fr: "Un type a besoin d'un libellé." });
        const d = Number(valeurs.duree);
        if (!(d >= 5 && d <= 1440)) fautes.duree = t({ en: "Between 5 and 1,440 minutes.", fr: "Entre 5 et 1 440 minutes." });
        return Object.keys(fautes).length ? fautes : null;
    };
    const basculerPropose = (x: TypeRendezVous, propose: boolean) =>
        void ecrire({ ...plan, types: (plan.types ?? []).map((y) => (y === x ? { ...y, actif: propose } : y)) }, propose ? { fr: "Type proposé.", en: "Type offered." } : { fr: "Type retiré de l'offre.", en: "Type no longer offered." });
    const retirerType = (x: TypeRendezVous) =>
        notifier.annulable(
            { fr: "Type retiré.", en: "Type removed." },
            { executer: () => ecrire({ ...plan, types: (plan.types ?? []).filter((y) => y !== x) }, { fr: "Type retiré.", en: "Type removed." }) },
        );

    const nombreChamps = (liste: Nombre[]) => liste.map(champNombre);
    const [rayon, ...autresTrajets] = [NOMBRES_TRAJETS[2], NOMBRES_TRAJETS[0], NOMBRES_TRAJETS[1]];
    const plagesChamp: Champ = {
        id: "plages",
        t: "zone",
        l: t({ en: "Booking ranges", fr: "Plages de rendez-vous" }),
        v: courant.plages ?? "",
        info: t({ en: "Same format as the opening hours (one line per day). Empty: the establishment's opening hours.", fr: "Même format que les horaires d'ouverture (une ligne par jour). Vide : les horaires d'ouverture de l'établissement." }),
    };

    return (
        <>
            <div className="flex items-center gap-3 pt-2 text-sm">
                <span className="flex items-center gap-1.5 text-muted-foreground">
                    {t({ en: "Rules of", fr: "Règles de" })}
                    <Info>
                        {t({
                            en: "Each establishment has its own complete rules: an empty field is the common default, nothing comes from elsewhere. The starting values are copied into a new establishment, and serve the calls that serve no establishment.",
                            fr: "Chaque établissement a ses propres règles complètes : un champ vide est le défaut commun, rien ne vient d'ailleurs. Les valeurs de départ sont recopiées dans un nouvel établissement, et servent aux appels qui ne servent aucun établissement.",
                        })}
                    </Info>
                </span>
                <Liste valeur={niveau ? nomNiveau(niveau) : departLibelle} changer={(nom) => setNiveau(idDeNom(nom))} options={nomsNiveaux} />
            </div>

            <TitreTableau
                titre={t({ en: "Appointment types", fr: "Types de rendez-vous" })}
                info={<Info>{t({ en: "This level's types: it offers these alone. The subject says who does it (« Team and routing »); empty: the whole team.", fr: "Les types de ce niveau : il propose ceux-là seuls. Le sujet dit qui le fait (« Équipe et routage ») ; vide : toute l'équipe." })}</Info>}
                action={
                    <Button variant="outline" size="sm" onClick={() => setType("nouveau")} data-testid="ajouter-type-rdv">
                        <Plus className="size-3.5" /> {t({ en: "Type", fr: "Type" })}
                    </Button>
                }
            />
            {typesIci.length === 0 ? (
                <EtatVide cas="premier" icone={CalendarClock} titre={t({ en: "No type at this level", fr: "Aucun type à ce niveau" })} />
            ) : (
                <Tableau
                    colonnes={[
                        { titre: t({ en: "Type", fr: "Type" }) },
                        { titre: t({ en: "Length", fr: "Durée" }), droite: true },
                        { titre: t({ en: "Margins", fr: "Marges" }), droite: true },
                        { titre: t({ en: "Done by", fr: "Fait par" }) },
                        { titre: t({ en: "Offered", fr: "Proposé" }), droite: true },
                    ]}
                >
                    {typesIci.map((x) => (
                        <Ligne key={x.code} onClick={() => setType(x)}>
                            <Cellule principale sous={<span className="font-mono">{x.code}</span>}>
                                {x.libelle}
                            </Cellule>
                            <Cellule droite>{x.duree_min} min</Cellule>
                            <Cellule droite>
                                {x.marge_avant_min ?? 0} / {x.marge_apres_min ?? 0} min
                            </Cellule>
                            <Cellule>{sujetOuvert(x.sujet) ?? t({ en: "the whole team", fr: "toute l'équipe" })}</Cellule>
                            <td className="text-right" onClick={(e) => e.stopPropagation()}>
                                <Switch checked={x.actif ?? true} onCheckedChange={(v) => basculerPropose(x, v)} aria-label={`${t({ en: "Offered", fr: "Proposé" })} : ${x.libelle}`} />
                            </td>
                        </Ligne>
                    ))}
                </Tableau>
            )}

            <SectionLue
                titre={t({ en: "Slots", fr: "Créneaux" })}
                lignes={[
                    [t({ en: "Booking ranges", fr: "Plages de rendez-vous" }), courant.plages?.trim() ? courant.plages.split("\n").join(" ; ") : `${t({ en: "the opening hours", fr: "les horaires d'ouverture" })} (${t({ en: "default", fr: "défaut" })})`],
                    ...NOMBRES.map((f): [string, string] => [t(f.libelle), texteNombre(f)]),
                ]}
                fenetre={{ titre: t({ en: "Slots", fr: "Créneaux" }), sections: [{ champs: [plagesChamp, ...nombreChamps(NOMBRES)] }] }}
                verifier={verifierNombres(NOMBRES)}
                onValider={(v) =>
                    void ecrire(posePart({ plages: String(v.plages).trim() || null, ...Object.fromEntries(NOMBRES.map((f) => [f.cle, lireNombre(v, f)])) }), { fr: "Créneaux enregistrés.", en: "Slots saved." })
                }
            />
            <SectionLue
                titre={t({ en: "Zone and journeys", fr: "Zone et trajets" })}
                lignes={[
                    [t(rayon.libelle), texteNombre(rayon, " km")],
                    [t({ en: "Zone served: communes", fr: "Zone desservie : communes" }), (courant.zone_communes ?? []).length ? (courant.zone_communes ?? []).join(", ") : t({ en: "no list", fr: "aucune liste" })],
                    [t(OUI_NON[0].libelle), texteOuiNon(OUI_NON[0])],
                    ...autresTrajets.map((f): [string, string] => [t(f.libelle), texteNombre(f)]),
                ]}
                fenetre={{
                    titre: t({ en: "Zone and journeys", fr: "Zone et trajets" }),
                    info: t({ en: "Where this level's people go, and how journeys are counted.", fr: "Où se rendent les personnes de ce niveau, et comment les trajets sont comptés." }),
                    sections: [
                        {
                            champs: [
                                champNombre(rayon),
                                { id: "zone_communes", t: "texte", l: t({ en: "Zone served: communes (INSEE codes)", fr: "Zone desservie : communes (codes INSEE)" }), v: (courant.zone_communes ?? []).join(", "), info: t({ en: "Separated by commas. Empty everywhere: no list.", fr: "Séparés par des virgules. Vide partout : pas de liste." }) },
                                champOuiNon(OUI_NON[0]),
                                ...nombreChamps(autresTrajets),
                            ],
                        },
                    ],
                }}
                verifier={verifierNombres([rayon, ...autresTrajets])}
                onValider={(v) => {
                    const codes = String(v.zone_communes).split(/[,\s]+/).map((c) => c.trim().toUpperCase()).filter(Boolean);
                    void ecrire(
                        posePart({
                            zone_rayon_km: lireNombre(v, rayon),
                            zone_communes: codes.length ? codes : null,
                            trajets_comptes: lireOuiNon(v, OUI_NON[0]),
                            ...Object.fromEntries(autresTrajets.map((f) => [f.cle, lireNombre(v, f)])),
                        }),
                        { fr: "Zone et trajets enregistrés.", en: "Zone and journeys saved." },
                    );
                }}
            />
            <SectionLue
                titre={t({ en: "Distribution and fallback", fr: "Répartition et repli" })}
                lignes={[
                    [t(CHOIX[0].libelle), texteChoix(CHOIX[0])],
                    [t(FENETRE.libelle), texteNombre(FENETRE)],
                    [t(CHOIX[1].libelle), texteChoix(CHOIX[1])],
                    [t(CHOIX[2].libelle), texteChoix(CHOIX[2])],
                    [t(OUI_NON[1].libelle), texteOuiNon(OUI_NON[1])],
                ]}
                fenetre={{ titre: t({ en: "Distribution and fallback", fr: "Répartition et repli" }), sections: [{ champs: [champChoix(CHOIX[0]), champNombre(FENETRE), champChoix(CHOIX[1]), champChoix(CHOIX[2]), champOuiNon(OUI_NON[1])] }] }}
                verifier={verifierNombres([FENETRE])}
                onValider={(v) =>
                    void ecrire(
                        posePart({
                            repartition: lireChoix(v, CHOIX[0]) as ReglagesPlanificateur["repartition"],
                            fenetre_equite_jours: lireNombre(v, FENETRE),
                            repli: lireChoix(v, CHOIX[1]) as ReglagesPlanificateur["repli"],
                            jours_feries: lireChoix(v, CHOIX[2]) as ReglagesPlanificateur["jours_feries"],
                            personne_visible: lireOuiNon(v, OUI_NON[1]),
                        }),
                        { fr: "Répartition enregistrée.", en: "Distribution saved." },
                    )
                }
            />

            <FenetreChamps
                ouverte={type !== null}
                fermer={() => setType(null)}
                titre={type === "nouveau" ? t({ en: "New appointment type", fr: "Nouveau type de rendez-vous" }) : (typeOuvert?.libelle ?? "")}
                valider={t({ en: "Save", fr: "Enregistrer" })}
                verifier={verifierType}
                onValider={(v) => void enregistrerType(v)}
                pied={
                    typeOuvert ? (
                        <span className="flex items-center gap-1">
                            <Button variant="ghost" size="sm" className="text-(--marque-danger-texte)" onClick={() => { const x = typeOuvert; setType(null); retirerType(x); }}>
                                <Trash2 className="size-3.5" /> {t({ en: "Remove", fr: "Retirer" })}
                            </Button>
                            {niveau && (
                                <BoutonAppliquerATous
                                    source={{ id: niveau, nom: nomNiveau(niveau) }}
                                    etablissements={etablissements.map((e) => ({ id: e.id, nom: e.nom }))}
                                    reglage="type"
                                    cle={typeOuvert.code}
                                    libelle={{ en: typeOuvert.libelle, fr: typeOuvert.libelle }}
                                    valeur={`${typeOuvert.libelle} (${typeOuvert.duree_min} min)`}
                                    onApplique={relire}
                                />
                            )}
                        </span>
                    ) : undefined
                }
                sections={[
                    {
                        champs: [
                            { id: "code", t: "texte", l: t({ en: "Code", fr: "Code" }), v: typeOuvert?.code ?? "", info: t({ en: "Lower case, digits and underscores: what the tools read.", fr: "Minuscules, chiffres et tirets bas : ce que lisent les outils." }) },
                            { id: "libelle", t: "texte", l: t({ en: "Name", fr: "Libellé" }), v: typeOuvert?.libelle ?? "", info: t({ en: "What the agent says.", fr: "Ce que dit l'agent." }) },
                            { id: "duree", t: "nombre", l: t({ en: "Length (min)", fr: "Durée (min)" }), v: String(typeOuvert?.duree_min ?? 60), min: 5, max: 1440, unite: "min" },
                            { id: "sujet", t: "choix", l: t({ en: "Subject", fr: "Sujet" }), o: [t({ en: "The whole team", fr: "Toute l'équipe" }), ...sujets.map((s) => s.libelle)], v: sujetOuvert(typeOuvert?.sujet) ?? t({ en: "The whole team", fr: "Toute l'équipe" }), info: t({ en: "Who does it (« Team and routing »).", fr: "Qui le fait (« Équipe et routage »)." }) },
                            { id: "avant", t: "nombre", l: t({ en: "Margin before (min)", fr: "Marge avant (min)" }), v: String(typeOuvert?.marge_avant_min ?? 0), min: 0, max: 480, unite: "min" },
                            { id: "apres", t: "nombre", l: t({ en: "Margin after (min)", fr: "Marge après (min)" }), v: String(typeOuvert?.marge_apres_min ?? 0), min: 0, max: 480, unite: "min" },
                            { id: "actif", t: "inter", l: t({ en: "Offered", fr: "Proposé" }), v: typeOuvert?.actif ?? true },
                        ],
                    },
                ]}
            />
        </>
    );
}
