"use client";

/**
 * [.mark] The establishments of the organization (chantier l-agent-travaille, L1, E1 to E4).
 *
 * A list to edit, so a modal (E4) working on a copy: « Cancel » / « Save ». It saves itself
 * (its own PUT), so it is not part of the theme's draft. Each establishment: its name, the
 * Telephony numbers that lead to it (E3, none = « to attach »), its second number and its
 * transfer number, then its values (E2's inheritance, with its greyed value and « Customize », is
 * gone since F-8, below).
 *
 * What the call reads is resolved by the server, never here: this screen only shows where a
 * value comes from.
 *
 * Lot 11 (agents-specialises, lot 4 of the fiche plan): the fiche is COMPLETE and inherits nothing
 * (M2, C3). No more numbers here (C4: a number belongs to the agent, the fiche to the place; the
 * numbers already stored are kept as they are). Added: the immediate closing of the fiche (C5), its
 * appointments and its zone (written with it, in the client's database), and « Create by copy »
 * (F2). The copy is written at once by the server, so it is offered only when nothing is waiting
 * to be saved here.
 *
 * cloture-code, F-8 (Evan, 22/10): an establishment has its own complete values and inherits
 * NOTHING, whichever way a call finds it. No more « inherited » value nor « Customize »: each field
 * is the fiche's own, an empty one is empty. A NEW establishment starts from the starting values
 * (the organization's address, announcements and sentences, its appointment rules and types), shown
 * filled in its fields; then it lives its own life. The server prefills the same way (route and
 * client's database), so a fiche created elsewhere starts alike.
 */
import { Copy, Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
    getEtablissementsApiV1OrganizationsEtablissementsGet,
    getPhrasesApiV1OrganizationsPhrasesGet,
    getPlanificateurApiV1OrganizationsPlanificateurGet,
    putPlanificateurApiV1OrganizationsPlanificateurPut,
    saveEtablissementsApiV1OrganizationsEtablissementsPut,
} from "@/client/sdk.gen";
import type {
    AdresseEtablissement,
    Etablissement,
    Phrase,
    Planificateur,
    ReglagesAnnonceOuverture,
    ResultatCopieEtablissement,
} from "@/client/types.gen";
import { notifier } from "@/components/mark/notifications";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

import { ChampAdresseEtablissement } from "../ChampAdresseEtablissement";
import { DerniereModificationFiche, useDernieresModifications } from "../entreprise/derniere-modification";
import { type Texte, useLangue } from "../langue/langue";
import { ETATS } from "../SectionAnnonceOuverture";
import { EXEMPLE_HORAIRES } from "../SectionHorairesOuverture";
import { Liste } from "../studio/liste";
import { Info } from "../studio/marques";
import { BoutonAppliquerATous, type ReglageAppliquable } from "./BoutonAppliquerATous";
import { FicheRendezVous } from "./FicheRendezVous";
import { ModaleCopieFiche } from "./ModaleCopieFiche";
import { libelleReglage, texteValeur } from "./reglages-rendez-vous";
import { charge_utile_planificateur } from "./charge-utile-planificateur";

export const ETABLISSEMENTS_ENREGISTRES: Texte = { en: "Establishments saved", fr: "Établissements enregistrés" };

/** « Magasin du centre » -> « magasin-du-centre », unique in the list. */
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

/** F-8: what a NEW establishment starts from (the common values), then it lives its own life. */
export interface ValeursDeDepart {
    adresse: AdresseEtablissement | null;
    annonce: ReglagesAnnonceOuverture;
    phrases: Phrase[];
}

const nouveau = (pris: string[], t: (x: Texte) => string, depart: ValeursDeDepart): Etablissement => {
    const nom = t({ en: "New establishment", fr: "Nouvel établissement" });
    const plein = (v: string | null | undefined) => (v && v.trim() ? v.trim() : null);
    return {
        id: identifiantPour(nom, pris),
        nom,
        numeros: [],
        adresse: depart.adresse ?? null,
        annonce_fermeture: plein(depart.annonce.annonce_fermeture),
        annonce_pause: plein(depart.annonce.annonce_pause),
        phrases: Object.fromEntries(
            depart.phrases.filter((p) => p.niveau === "etablissement" && plein(p.contenu)).map((p) => [p.variable, (p.contenu ?? "").trim()]),
        ),
    };
};

/** F-8: the planner of a NEW establishment: a copy of the starting rules and types, under its identifier. */
export const planificateurAvecNouveau = (p: Planificateur, id: string): Planificateur => ({
    ...p,
    par_etablissement: { ...(p.par_etablissement ?? {}), [id]: { ...(p.reglages ?? {}) } },
    types: [
        ...(p.types ?? []).filter((x) => (x.etablissement ?? null) !== id),
        ...(p.types ?? []).filter((x) => !x.etablissement).map((x) => ({ ...x, etablissement: id })),
    ],
});

/** The PUT body: empty strings are null (« nothing », F-8), as the server reads them. */
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
        // Lot 11 (C5): the immediate closing of the fiche. Sent only when the server (or the screen) set it,
        // so a fiche read without it is saved without it; a date means nothing without a state.
        ...(e.etat_force !== undefined || e.etat_force_jusqu_a !== undefined
            ? { etat_force: e.etat_force ?? null, etat_force_jusqu_a: e.etat_force ? (e.etat_force_jusqu_a ?? null) : null }
            : {}),
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
    /**
     * [.mark] K4 : la fenêtre d'UNE fiche (comme la maquette) : l'identifiant de la fiche à ouvrir, ou « nouveau ».
     * Absent : l'ancienne fenêtre à liste (les établissements d'un coup).
     */
    fiche?: string | "nouveau";
}

/**
 * F-8: the fiche's OWN field. [.mark] K4 (maquette) : le libellé et son « ! » (l'aide et ce que veut dire « vide »),
 * le champ, les gestes ; plus de clé technique ni de phrase d'explication visible. Le sens de « vide » reste lisible
 * par un lecteur d'écran (`sr-only`).
 */
const ChampPropre = ({
    id,
    libelle,
    aide,
    vide,
    onVider,
    action,
    children,
}: {
    id: string;
    libelle: Texte;
    aide: Texte;
    vide?: Texte;
    onVider?: () => void;
    /** D152: « Apply to all establishments », next to the field. */
    action?: React.ReactNode;
    children: React.ReactNode;
}) => {
    const { t } = useLangue();
    return (
        <div className="space-y-2 py-3.5" data-testid={`champ-${id}`}>
            <p className="flex items-center gap-1.5 text-sm font-medium">
                {t(libelle)}
                <Info>
                    {t(aide)}
                    {vide ? ` ${t(vide)}` : ""}
                </Info>
            </p>
            {children}
            {(onVider || action) && (
                <div className="flex flex-wrap items-center gap-2">
                    {onVider && (
                        <Button variant="ghost" size="sm" onClick={onVider} data-testid={`vider-${id}`}>
                            {t({ en: "Empty this field", fr: "Vider ce champ" })}
                        </Button>
                    )}
                    {action}
                </div>
            )}
            {vide && (
                <span className="sr-only" data-testid={`vide-${id}`}>
                    {t(vide)}
                </span>
            )}
        </div>
    );
};

/** [.mark] K4 : une section de la fenêtre d'une fiche : titre en gras, champs séparés par un trait. */
const SectionFiche = ({ titre, info, children }: { titre: Texte; info?: Texte; children: React.ReactNode }) => {
    const { t } = useLangue();
    return (
        <section>
            <p className="flex items-center gap-1.5 pb-1 text-sm font-semibold">
                {t(titre)}
                {info && <Info>{t(info)}</Info>}
            </p>
            <div className="divide-y">{children}</div>
        </section>
    );
};

const VIDE_RIEN: Texte = {
    en: "Empty: nothing for this establishment (nothing is taken from the organization).",
    fr: "Vide : rien pour cet établissement (rien n'est pris à l'organisation).",
};

export function ModaleEtablissements({ ouverte, onFermer, adresseOrganisation, annonceOrganisation, fiche }: ProprietesModale) {
    const { t } = useLangue();
    const modifications = useDernieresModifications(ouverte);
    const [liste, setListe] = useState<Etablissement[] | null>(null);
    const [phrasesEtablissement, setPhrasesEtablissement] = useState<Phrase[]>([]);
    // The terms as typed: a line being written is kept until it is left.
    const [termesSaisis, setTermesSaisis] = useState<Record<string, string>>({});
    const [choisi, setChoisi] = useState(0);
    const [erreur, setErreur] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);
    const [adresseIncomplete, setAdresseIncomplete] = useState(false);
    // F-8: « Empty this field » on the address remounts its inputs (they keep what was typed otherwise).
    const [adresseVidee, setAdresseVidee] = useState(0);
    // All the sentences (the starting contents of those placed at the establishment's level prefill a new fiche).
    const [phrasesCatalogue, setPhrasesCatalogue] = useState<Phrase[]>([]);
    // The identifiers already saved never change (a call, a stamp, a future base row refer to
    // them); a NEW establishment's identifier follows its name until it is saved.
    const [idsEnregistres, setIdsEnregistres] = useState<string[]>([]);
    // What was read, to know whether something waits to be saved (the copy is offered only when nothing does).
    const [lue, setLue] = useState<string>("");
    // The planner, written in the client's database: the fiche's appointments and zone live in it (lot 11).
    const [planificateur, setPlanificateur] = useState<Planificateur | null>(null);
    const [planificateurLu, setPlanificateurLu] = useState<Planificateur | null>(null);
    const [planificateurIndisponible, setPlanificateurIndisponible] = useState<string | null>(null);
    const [fenetreCopie, setFenetreCopie] = useState(false);
    const [resultatCopie, setResultatCopie] = useState<{ nom: string; resultat: ResultatCopieEtablissement } | null>(null);
    // A copy was made while the window was open: the caller must read the list again, saved or not.
    const aCopie = useRef(false);
    // [.mark] K4 : une fiche « nouveau » est ajoutée une seule fois, dès que la liste est lue.
    const ajoutee = useRef(false);

    const charger = useCallback(async (choix?: string) => {
        const [catalogue, phrases, lecturePlanif] = await Promise.all([
            getEtablissementsApiV1OrganizationsEtablissementsGet(),
            getPhrasesApiV1OrganizationsPhrasesGet(),
            getPlanificateurApiV1OrganizationsPlanificateurGet(),
        ]);
        setPhrasesEtablissement((phrases.data?.phrases ?? []).filter((p) => p.niveau === "etablissement"));
        setPhrasesCatalogue(phrases.data?.phrases ?? []);
        if (lecturePlanif.error || !lecturePlanif.data) {
            // No client database (or unreachable): the fiche is edited and saved all the same, its
            // appointments and zone are said to live elsewhere. Never a reason to lose the fiche.
            setPlanificateur(null);
            setPlanificateurLu(null);
            setPlanificateurIndisponible(detailFromError(lecturePlanif.error, "Planner unreadable"));
        } else {
            setPlanificateur(lecturePlanif.data);
            setPlanificateurLu(lecturePlanif.data);
            setPlanificateurIndisponible(null);
        }
        if (catalogue.error || !catalogue.data) {
            // ⛔ Unreadable: nothing to edit, or the save would replace what is there.
            setErreur(detailFromError(catalogue.error, "Establishments unreadable"));
            return;
        }
        const lus = catalogue.data.etablissements ?? [];
        setListe(lus);
        setLue(JSON.stringify(charge_utile_etablissements(lus)));
        setIdsEnregistres(lus.map((e) => e.id));
        if (choix !== undefined) setChoisi(Math.max(0, lus.findIndex((e) => e.id === choix)));
    }, []);

    useEffect(() => {
        if (!ouverte) return;
        setListe(null);
        setErreur(null);
        setChoisi(0);
        setResultatCopie(null);
        aCopie.current = false;
        ajoutee.current = false;
        void charger(fiche && fiche !== "nouveau" ? fiche : undefined);
    }, [ouverte, charger, fiche]);

    const courant = liste && liste.length > 0 ? liste[Math.min(choisi, liste.length - 1)] : null;
    const modifier = (champ: Partial<Etablissement>) =>
        setListe((avant) => (avant ? avant.map((e, i) => (i === Math.min(choisi, avant.length - 1) ? { ...e, ...champ } : e)) : avant));

    const ajouter = () => {
        const fiche = nouveau(
            (liste ?? []).map((e) => e.id),
            t,
            { adresse: adresseOrganisation, annonce: annonceOrganisation, phrases: phrasesCatalogue },
        );
        setListe((avant) => {
            const suite = [...(avant ?? []), fiche];
            setChoisi(suite.length - 1);
            return suite;
        });
        // F-8: its appointment rules and types start from the starting ones (written with the fiche).
        setPlanificateur((p) => (p ? planificateurAvecNouveau(p, fiche.id) : p));
    };
    const retirer = (rang: number) => {
        setListe((avant) => (avant ? avant.filter((_e, i) => i !== rang) : avant));
        setChoisi(0);
    };
    /** The fiche's planner level follows its identifier while a NEW fiche is still named (the id follows the name). */
    const suivreIdentifiant = (ancien: string, nouveau: string) => {
        if (ancien === nouveau) return;
        setPlanificateur((p) => {
            if (!p) return p;
            // F-8: its own types follow it too (copied from the starting ones when it was added).
            const types = (p.types ?? []).map((x) => (x.etablissement === ancien ? { ...x, etablissement: nouveau } : x));
            const propre = p.par_etablissement?.[ancien];
            if (propre === undefined) return { ...p, types };
            const reste = { ...(p.par_etablissement ?? {}) };
            delete reste[ancien];
            return { ...p, types, par_etablissement: { ...reste, [nouveau]: propre } };
        });
    };
    const poserRendezVous = (id: string, cle: string, valeur: unknown) =>
        setPlanificateur((p) =>
            p ? { ...p, par_etablissement: { ...(p.par_etablissement ?? {}), [id]: { ...(p.par_etablissement?.[id] ?? {}), [cle]: valeur } } } : p,
        );

    const viderAdresse = () => {
        modifier({ adresse: null });
        setAdresseIncomplete(false);
        setAdresseVidee((n) => n + 1);
    };

    const fautes: string[] = [];
    (liste ?? []).forEach((e) => {
        if (!e.nom.trim()) fautes.push(t({ en: "An establishment has no name.", fr: "Un établissement n'a pas de nom." }));
    });
    if (adresseIncomplete)
        fautes.push(t({ en: "Choose the town for this postal code before saving.", fr: "Choisissez la commune de ce code postal avant d'enregistrer." }));

    /** The planner as it will be written: only the levels of fiches that exist once the list is saved. */
    const planificateurAEcrire = (): Planificateur | null => {
        if (!planificateur || !liste) return null;
        const ids = new Set(liste.map((e) => e.id));
        return {
            ...planificateur,
            par_etablissement: Object.fromEntries(Object.entries(planificateur.par_etablissement ?? {}).filter(([id]) => ids.has(id))),
            // F-8: the types of a new fiche removed before saving go with it (those read are left as they are).
            types: (planificateur.types ?? []).filter(
                (x) => !x.etablissement || ids.has(x.etablissement) || (planificateurLu?.types ?? []).some((y) => y.etablissement === x.etablissement),
            ),
        };
    };
    const planificateurModifie = (() => {
        const a = planificateurAEcrire();
        return a !== null && planificateurLu !== null && JSON.stringify(charge_utile_planificateur(a)) !== JSON.stringify(charge_utile_planificateur(planificateurLu));
    })();
    const listeModifiee = liste !== null && JSON.stringify(charge_utile_etablissements(liste)) !== lue;
    const rienNAttend = !listeModifiee && !planificateurModifie;

    // D152: « Apply to all establishments ». The server copies the SAVED value of this fiche into the others,
    // so the button is off while something waits to be saved, and drawn only for a fiche that exists.
    const lieux = (liste ?? []).filter((e) => idsEnregistres.includes(e.id)).map((e) => ({ id: e.id, nom: e.nom }));
    const apresApplication = async () => {
        // The others were written: the caller must read the list again, and so do we.
        aCopie.current = true;
        await charger(courant?.id);
    };
    const appliquer = (reglage: ReglageAppliquable, cle: string, libelle: Texte, valeur?: string | null) =>
        courant && idsEnregistres.includes(courant.id) ? (
            <BoutonAppliquerATous
                source={{ id: courant.id, nom: courant.nom }}
                etablissements={lieux}
                reglage={reglage}
                cle={cle}
                libelle={libelle}
                valeur={valeur}
                enAttente={!rienNAttend}
                onApplique={apresApplication}
            />
        ) : null;

    const enregistrer = async () => {
        if (!liste) return;
        setEnCours(true);
        setErreur(null);
        const reponse = await saveEtablissementsApiV1OrganizationsEtablissementsPut({ body: charge_utile_etablissements(liste) });
        if (reponse.error) {
            setEnCours(false);
            setErreur(detailFromError(reponse.error, "Establishments not saved"));
            return;
        }
        // The fiches exist now (the client's database knows them): the planner's levels can be written.
        const ecrire = planificateurAEcrire();
        if (ecrire && planificateurModifie) {
            const suite = await putPlanificateurApiV1OrganizationsPlanificateurPut({ body: charge_utile_planificateur(ecrire) });
            if (suite.error || !suite.data) {
                setEnCours(false);
                // The fiches ARE saved: the window stays open on what is left, and the caller reads again on close.
                aCopie.current = true;
                setLue(JSON.stringify(charge_utile_etablissements(liste)));
                setIdsEnregistres(liste.map((e) => e.id));
                setErreur(
                    `${t({ en: "Establishments saved, but the appointments and zone were not:", fr: "Établissements enregistrés, mais pas les rendez-vous et la zone :" })} ${detailFromError(suite.error, "Planner not saved")}`,
                );
                return;
            }
        }
        setEnCours(false);
        notifier.succes({ fr: "Établissements enregistrés.", en: "Establishments saved." });
        onFermer(true);
    };

    /** « Create by copy » answered: read everything again (the server wrote the new fiche) and open it. */
    const copieFaite = async (resultat: ResultatCopieEtablissement | null) => {
        setFenetreCopie(false);
        if (!resultat) return;
        aCopie.current = true;
        setResultatCopie({ nom: resultat.etablissement.nom, resultat });
        await charger(resultat.etablissement.id);
    };

    // [.mark] K4 : en mode « fiche », la fiche « nouveau » est ajoutée une fois la liste lue.
    useEffect(() => {
        if (!ouverte || fiche !== "nouveau" || liste === null || ajoutee.current) return;
        ajoutee.current = true;
        ajouter();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [ouverte, fiche, liste]);
    const [retraitDemande, setRetraitDemande] = useState(false);
    const modeFiche = fiche !== undefined;
    const titreFenetre = modeFiche
        ? fiche === "nouveau"
            ? t({ en: "New establishment", fr: "Nouvel établissement" })
            : (courant?.nom ?? "")
        : t({ en: "Establishments", fr: "Établissements" });
    const retirerEtEnregistrer = () => {
        if (!courant || !liste) return;
        const reste = liste.filter((e) => e !== courant);
        void (async () => {
            setEnCours(true);
            const reponse = await saveEtablissementsApiV1OrganizationsEtablissementsPut({ body: charge_utile_etablissements(reste) });
            setEnCours(false);
            if (reponse.error) {
                setErreur(detailFromError(reponse.error, "Establishments not saved"));
                return;
            }
            notifier.succes({ fr: "Établissement retiré.", en: "Establishment removed." });
            onFermer(true);
        })();
    };
    const fenetreEtat = (
        <div className="space-y-2 py-3.5" data-testid="champ-etat-force">
            <p className="flex items-center gap-1.5 text-sm font-medium">
                {t({ en: "State of this establishment", fr: "État de cet établissement" })}
                <Info>{t({ en: "Default: computed from the hours.", fr: "Défaut : calculé depuis les horaires." })}</Info>
            </p>
            {courant && (
                <Liste
                    valeur={courant.etat_force ?? ""}
                    vide={t({ en: "Computed from the opening hours", fr: "Calculé depuis les horaires" })}
                    options={ETATS.map((etat) => ({ valeur: etat.valeur, libelle: `${t({ en: "Forced:", fr: "Forcé :" })} ${t(etat.libelle)}` }))}
                    taille="default"
                    className="w-full"
                    changer={(v) => modifier(v === "" ? { etat_force: null, etat_force_jusqu_a: null } : { etat_force: v as Etablissement["etat_force"] })}
                />
            )}
        </div>
    );

    return (
        <Dialog open={ouverte} onOpenChange={(o) => (o ? null : onFermer(aCopie.current))}>
            <DialogContent
                className={`flex max-h-[86vh] flex-col gap-0 overflow-hidden p-0 ${modeFiche ? "sm:max-w-xl" : "sm:max-w-5xl"}`}
                data-testid="modale-etablissements"
                onOpenAutoFocus={(e) => e.preventDefault()}
            >
                <div className="shrink-0 border-b px-6 pt-5 pr-12 pb-4">
                    <DialogTitle className="flex items-center gap-2 text-lg">
                        {titreFenetre}
                        <Info>
                            {fiche === "nouveau"
                                ? t({
                                      en: "A new establishment starts from the starting values, then lives its own life. An empty announcement or sentence says nothing.",
                                      fr: "Un nouvel établissement part des valeurs de départ, puis vit sa vie. Une annonce ou une phrase vide ne dit rien.",
                                  })
                                : t({
                                      en: "Every call that serves this fiche (the agent that chooses it in its theme « Business », or the number called) reads its hours, address, announcements, sentences, appointments, closing and transfer number alone, nothing is inherited. An empty announcement or sentence says nothing.",
                                      fr: "Tout appel qui sert cette fiche (l'agent qui la choisit dans son thème « Établissement », ou le numéro appelé) en lit seuls les horaires, l'adresse, les annonces, les phrases, les rendez-vous, la fermeture et le numéro de transfert, rien n'est hérité. Une annonce ou une phrase vide ne dit rien.",
                                  })}
                        </Info>
                    </DialogTitle>
                    <DialogDescription className="sr-only">{titreFenetre}</DialogDescription>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto bg-background px-6 py-5">
                    {erreur && (
                        <p className="pb-3 text-sm text-destructive" role="alert" data-testid="erreur-etablissements">
                            {erreur}
                        </p>
                    )}
                    {liste === null ? (
                        !erreur && <p className="text-sm text-muted-foreground">{t({ en: "Loading…", fr: "Chargement…" })}</p>
                    ) : (
                        <div className={modeFiche ? "" : "grid gap-4 md:grid-cols-[14rem_1fr]"}>
                            {!modeFiche && (
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
                            {/* Lot 11 (F2): the copy is written at once by the server: offered when nothing waits to be saved. */}
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => setFenetreCopie(true)}
                                disabled={liste.length === 0 || !rienNAttend}
                                data-testid="creer-par-copie"
                            >
                                <Copy className="mr-1 h-4 w-4" />
                                {t({ en: "Create by copy", fr: "Créer par copie" })}
                            </Button>
                            {!rienNAttend && liste.length > 0 && (
                                <p className="text-xs text-muted-foreground" data-testid="copie-apres-enregistrement">
                                    {t({
                                        en: "Save the changes first: the copy is written at once.",
                                        fr: "Enregistrez d'abord les changements : la copie est écrite tout de suite.",
                                    })}
                                </p>
                            )}
                        </div>
                            )}
                            {courant && (
                                <div className="min-w-0 space-y-8" data-testid="fiche-etablissement">
                                {resultatCopie && (
                                    <p className="rounded border border-border bg-muted/40 p-2 text-sm" role="status" data-testid="resultat-copie">
                                        {t({ en: "Created from a copy:", fr: "Créée par copie :" })} <span className="font-medium">{resultatCopie.nom}</span>.{" "}
                                        {t({
                                            en: "Not copied, to fill on this fiche: the second number, the transfer number and the immediate closing.",
                                            fr: "Non copiés, à renseigner sur cette fiche : le second numéro, le numéro de transfert et la fermeture immédiate.",
                                        })}{" "}
                                        {resultatCopie.resultat.reglages_rendez_vous_copies || (resultatCopie.resultat.types_rendez_vous_copies ?? 0) > 0
                                            ? t({
                                                  en: `Appointment settings copied (${resultatCopie.resultat.types_rendez_vous_copies ?? 0} type(s)).`,
                                                  fr: `Réglages de rendez-vous copiés (${resultatCopie.resultat.types_rendez_vous_copies ?? 0} type(s)).`,
                                              })
                                            : (resultatCopie.resultat.non_copie ?? []).includes("reglages_rendez_vous")
                                              ? t({ en: "The appointment settings could not be copied.", fr: "Les réglages de rendez-vous n'ont pas pu être copiés." })
                                              : t({ en: "No appointment settings to copy.", fr: "Aucun réglage de rendez-vous à copier." })}
                                    </p>
                                )}
                                <SectionFiche
                                    titre={{ en: "Fiche", fr: "Fiche" }}
                                >
                                    <div className="space-y-2 py-3.5">
                                        <div className="flex items-center gap-1.5 text-sm font-medium">
<label htmlFor="etablissement-nom">{t({ en: "Name", fr: "Nom" })}</label>
<Info>{t({ en: "Given to the agents as {{etablissement}}.", fr: "Donné aux agents comme {{etablissement}}." })}</Info>
</div>
                                        <DerniereModificationFiche modification={modifications.parFiche[courant.id]} />
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
                                                const id = identifiantPour(nom, autres);
                                                suivreIdentifiant(courant.id, id);
                                                modifier({ nom, id });
                                            }}
                                        />
                                    </div>
                                    <div className="space-y-2 py-3.5">
                                        <div className="flex items-center gap-1.5 text-sm font-medium">
<label htmlFor="etablissement-second-numero">{t({ en: "Second number", fr: "Second numéro" })}</label>
<Info>{t({ en: "Reached when the agent cannot answer.", fr: "Joint quand l'agent ne peut pas répondre." })}</Info>
</div>
                                        <Input id="etablissement-second-numero" value={courant.second_numero ?? ""} placeholder="+33344000000" onChange={(e) => modifier({ second_numero: e.target.value })} />
                                    </div>
                                    <div className="space-y-2 py-3.5">
                                        <div className="flex items-center gap-1.5 text-sm font-medium">
<label htmlFor="etablissement-numero-transfert">{t({ en: "Transfer number", fr: "Numéro de transfert" })}</label>
<Info>
                                                {t({
                                                    en: "Given to the agents as {{numero_transfert}}: write it in the transfer tool's destination.",
                                                    fr: "Donné aux agents comme {{numero_transfert}} : à écrire dans la destination de l'outil de transfert.",
                                                })}
                                            </Info>
</div>
                                        <Input id="etablissement-numero-transfert" value={courant.numero_transfert ?? ""} placeholder="+33344000000" onChange={(e) => modifier({ numero_transfert: e.target.value })} />
                                    </div>
                                <ChampPropre
                                    id="adresse"
                                    libelle={{ en: "Address", fr: "Adresse" }}
                                    aide={{
                                        en: "Given to the agents as {{adresse_etablissement}}; helps recognise the towns callers name.",
                                        fr: "Donnée aux agents comme {{adresse_etablissement}} ; aide à reconnaître les communes citées.",
                                    }}
                                    vide={{
                                        en: "Empty: no address for this establishment (never the organization's).",
                                        fr: "Vide : aucune adresse pour cet établissement (jamais celle de l'organisation).",
                                    }}
                                    onVider={courant.adresse ? viderAdresse : undefined}
                                    action={appliquer(
                                        "fiche",
                                        "adresse",
                                        { en: "Address", fr: "Adresse" },
                                        courant.adresse ? [courant.adresse.voie, courant.adresse.code_postal, courant.adresse.commune].filter(Boolean).join(" ") : "",
                                    )}
                                >
                                    <ChampAdresseEtablissement
                                        key={`${courant.id}-${adresseVidee}`}
                                        id={`etablissement-adresse-${courant.id}`}
                                        enregistree={courant.adresse ?? null}
                                        onChange={(valeur, incomplete) => {
                                            setAdresseIncomplete(incomplete);
                                            if (!incomplete) modifier({ adresse: valeur });
                                        }}
                                    />
                                </ChampPropre>


                                </SectionFiche>
                                <SectionFiche
                                    titre={{ en: "Opening hours and closures", fr: "Horaires d'ouverture et fermetures" }}
                                    info={{ en: "Same format as an agent's hours; a closure is a dated line (« 24/12/2026 : fermé »). They win over the hours of the agents that serve this establishment.", fr: "Même format que les horaires d'un agent ; une fermeture est une ligne datée (« 24/12/2026 : fermé »). Ils l'emportent sur les horaires des agents qui servent cet établissement." }}
                                >
                                <ChampPropre
                                    id="horaires_ouverture"
                                    libelle={{ en: "Hours", fr: "Horaires" }}
                                    aide={{
                                        en: "Same format as an agent's hours; a closure is a dated line (« 24/12/2026 : fermé »). They win over the hours of the agents that serve this establishment.",
                                        fr: "Même format que les horaires d'un agent ; une fermeture est une ligne datée (« 24/12/2026 : fermé »). Ils l'emportent sur les horaires des agents qui servent cet établissement.",
                                    }}
                                    vide={{
                                        en: "Empty: no hours for this establishment (never an agent's own).",
                                        fr: "Vide : aucun horaire pour cet établissement (jamais ceux d'un agent).",
                                    }}
                                    action={appliquer(
                                        "fiche",
                                        "horaires_ouverture",
                                        { en: "Opening hours and closures", fr: "Horaires d'ouverture et fermetures" },
                                        courant.horaires_ouverture,
                                    )}
                                >
                                    <Textarea
                                        id="etablissement-horaires"
                                        rows={8}
                                        className="font-mono text-xs"
                                        placeholder={EXEMPLE_HORAIRES}
                                        value={courant.horaires_ouverture ?? ""}
                                        onChange={(e) => modifier({ horaires_ouverture: e.target.value })}
                                    />
                                </ChampPropre>


                                </SectionFiche>
                                <SectionFiche
                                    titre={{ en: "Announcements", fr: "Annonces" }}
                                >
                                {(["annonce_fermeture", "annonce_pause"] as const).map((cle) => (
                                    <ChampPropre
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
                                        vide={{
                                            en: "Empty: nothing is announced for this establishment (never the organization's sentence).",
                                            fr: "Vide : rien n'est annoncé pour cet établissement (jamais la phrase de l'organisation).",
                                        }}
                                        action={appliquer(
                                            "fiche",
                                            cle,
                                            cle === "annonce_fermeture" ? { en: "Closing sentence", fr: "Phrase de fermeture" } : { en: "Break sentence", fr: "Phrase de pause" },
                                            courant[cle],
                                        )}
                                    >
                                        <Textarea
                                            id={`etablissement-${cle}`}
                                            rows={2}
                                            maxLength={300}
                                            value={courant[cle] ?? ""}
                                            onChange={(e) => modifier({ [cle]: e.target.value })}
                                        />
                                    </ChampPropre>
                                ))}

                                {phrasesEtablissement.map((p) => {
                                    const cle = `phrase:${p.variable}`;
                                    const propre = (courant.phrases ?? {})[p.variable];
                                    return (
                                        <ChampPropre
                                            key={cle}
                                            id={p.variable}
                                            libelle={{ en: p.description || p.variable, fr: p.description || p.variable }}
                                            aide={{
                                                en: `A sentence of the catalogue placed at the establishment's level, given to the agents as {{${p.variable}}}.`,
                                                fr: `Une phrase du catalogue placée au niveau de l'établissement, donnée aux agents comme {{${p.variable}}}.`,
                                            }}
                                            vide={VIDE_RIEN}
                                            action={appliquer("phrase", p.variable, { en: p.description || p.variable, fr: p.description || p.variable }, propre)}
                                        >
                                            <Textarea
                                                id={`etablissement-phrase-${p.variable}`}
                                                rows={2}
                                                maxLength={1000}
                                                value={propre ?? ""}
                                                onChange={(e) => modifier({ phrases: { ...(courant.phrases ?? {}), [p.variable]: e.target.value } })}
                                            />
                                        </ChampPropre>
                                    );
                                })}


                                </SectionFiche>
                                <SectionFiche
                                    titre={{ en: "Immediate closing", fr: "Fermeture immédiate" }}
                                    info={{ en: "Closes THIS fiche's agents now, whatever the hours say, and lifts itself at the date. The organization's « Close everything » closes the fiches that have no closing of their own.", fr: "Ferme maintenant les agents de CETTE fiche, quoi que disent les horaires, et se lève à la date. Le « Tout fermer » de l'organisation ferme les fiches qui n'ont pas la leur." }}
                                >
                                    {fenetreEtat}
                                    {courant.etat_force && (
                                        <ChampPropre
                                            id="etat_force_jusqu_a"
                                            libelle={{ en: "Until (Paris time)", fr: "Jusqu'au (heure de Paris)" }}
                                            aide={{
                                                en: "This moment lifts the forced state by itself. Left empty, it holds until someone comes back here, and no reopening is announced.",
                                                fr: "Ce moment lève l'état forcé tout seul. Vide, il tient jusqu'à ce que quelqu'un revienne ici, et aucune réouverture n'est annoncée.",
                                            }}
                                        >
                                            <Input
                                                id="fiche-etat-force-jusqua"
                                                type="datetime-local"
                                                value={courant.etat_force_jusqu_a ? courant.etat_force_jusqu_a.slice(0, 16) : ""}
                                                onChange={(e) => modifier({ etat_force_jusqu_a: e.target.value || null })}
                                            />
                                        </ChampPropre>
                                    )}

                                </SectionFiche>
                                <SectionFiche
                                    titre={{ en: "Terms added to the trade vocabulary", fr: "Termes ajoutés au lexique métier" }}
                                >
                                    <ChampPropre
                                        id="termes_lexique"
                                        libelle={{ en: "One brand or name per line", fr: "Une marque ou un nom par ligne" }}
                                        aide={{
                                            en: "Recognised like the organization's names on this establishment's calls; a spelling already in the organization's vocabulary is ignored.",
                                            fr: "Reconnus comme les noms de l'organisation sur les appels de cet établissement ; une orthographe déjà dans le lexique de l'organisation est ignorée.",
                                        }}
                                    >
                                        <Textarea
                                            id="etablissement-termes"
                                            rows={3}
                                            value={termesSaisis[courant.id] ?? (courant.termes_lexique ?? []).map((x) => x.terme).join("\n")}
                                            onChange={(e) => {
                                                const texte = e.target.value;
                                                setTermesSaisis((a) => ({ ...a, [courant.id]: texte }));
                                                modifier({ termes_lexique: termesDepuisTexte(texte, courant.termes_lexique) });
                                            }}
                                        />
                                    </ChampPropre>

                                </SectionFiche>
                                {planificateur ? (
                                    <FicheRendezVous
                                        id={courant.id}
                                        reglages={planificateur.par_etablissement?.[courant.id] ?? {}}
                                        defauts={planificateur.defauts ?? {}}
                                        onPoser={(cle, valeur) => poserRendezVous(courant.id, cle, valeur)}
                                        boutonPour={(cle) =>
                                            appliquer("planificateur", cle, libelleReglage(cle), texteValeur(planificateur.par_etablissement?.[courant.id]?.[cle], t))
                                        }
                                    />
                                ) : (
                                    <SectionFiche titre={{ en: "Appointments and zone", fr: "Rendez-vous et zone" }}>
                                        <p className="text-sm text-muted-foreground" data-testid="fiche-rdv-sans-base">
                                            {t({
                                                en: "The appointment rules and the zone live in the client's database: attach one in « Client data » first.",
                                                fr: "Les règles de rendez-vous et la zone vivent dans la base du client : rattachez-en une dans « Données du client » d'abord.",
                                            })}
                                            {planificateurIndisponible ? ` (${planificateurIndisponible})` : ""}
                                        </p>
                                    </SectionFiche>
                                )}
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
                </div>
                <ModaleCopieFiche
                    ouverte={fenetreCopie}
                    fiches={liste ?? []}
                    sourceInitiale={courant?.id ?? ""}
                    onFermer={(resultat) => void copieFaite(resultat)}
                />
                <div className="flex shrink-0 items-center justify-end gap-2 border-t px-6 py-3">
                    {modeFiche && fiche !== "nouveau" && courant && (
                        <Button
                            variant="ghost"
                            size="sm"
                            className="mr-auto text-(--marque-danger-texte)"
                            onClick={() => (retraitDemande ? retirerEtEnregistrer() : setRetraitDemande(true))}
                            disabled={enCours}
                            data-testid="retirer-etablissement"
                        >
                            <Trash2 className="size-3.5" />
                            {retraitDemande ? t({ en: "Confirm: remove it", fr: "Confirmer le retrait" }) : t({ en: "Remove this establishment", fr: "Retirer cet établissement" })}
                        </Button>
                    )}
                    <Button variant="outline" onClick={() => onFermer(aCopie.current)}>
                        {t({ en: "Cancel", fr: "Annuler" })}
                    </Button>
                    <Button onClick={() => void enregistrer()} disabled={enCours || liste === null || fautes.length > 0} data-testid="enregistrer-etablissements">
                        {t({ en: "Save", fr: "Enregistrer" })}
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}
