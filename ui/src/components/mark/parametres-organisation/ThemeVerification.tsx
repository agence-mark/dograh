"use client";

/**
 * [.mark] Theme « Caller verification » (chantier l-agent-collegue, L6, V2 to V7; new theme decided
 * by Evan in the plan, 07/10).
 *
 * What the code checks before an agent may read a caller's record: the factors accepted, the
 * fields of the control question, and for each kind of data the level required and the fields
 * the agent may read; where the records are read (the client database, or a software that holds
 * them through its translator). Stored in Dograh (``organization_configurations``), one « Save »
 * (E6). Nothing runs until an agent switches « Caller verification » on (theme « Call data » of
 * the agent, V7). The SMS code is wired but never tried for real (V5): said here.
 */
import { ListeDeroulante } from "@/components/mark/studio/liste-deroulante";
import { ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { notifier } from "@/components/mark/notifications";

import {
    getLogicielsDossierApiV1OrganizationsVerificationAppelantLogicielsGet,
    getVerificationAppelantApiV1OrganizationsVerificationAppelantGet,
    putVerificationAppelantApiV1OrganizationsVerificationAppelantPut,
} from "@/client/sdk.gen";
import type { LogicielDossier, ReglagesVerification } from "@/client/types.gen";
import { Switch } from "@/components/ui/switch";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

import { bornesDe, ChampReglage } from "../ecran/ChampReglage";
import { useFormeMaquette } from "../ecran/forme-maquette";
import { Intertitre } from "../ecran/Intertitre";
import { type ErreurNommee, Theme } from "../ecran/Theme";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { type Texte, useLangue } from "../langue/langue";
import { Liste } from "../studio/liste";
import { Puces } from "../studio/puces";
import { type ProprietesThemeOrganisation, useSignaler } from "./ThemesOrganisation";

export const TITRE_VERIFICATION: Texte = { en: "Caller verification", fr: "Vérification de l'appelant" };

export const FACTEURS: Array<{ cle: "numero" | "question" | "code_sms"; libelle: Texte; aide: Texte }> = [
    {
        cle: "numero",
        libelle: { en: "Number calling", fr: "Numéro appelant" },
        aide: { en: "Passes when the number calling is one of the record's (read from the call, never from the agent). Default: on.", fr: "Réussi quand le numéro appelant est l'un de ceux du dossier (lu dans l'appel, jamais donné par l'agent). Par défaut : allumé." },
    },
    {
        cle: "question",
        libelle: { en: "Control question", fr: "Question de contrôle" },
        aide: { en: "Passes when every field chosen below matches the record, compared by the code. Default: on.", fr: "Réussie quand chaque champ choisi ci-dessous correspond au dossier, comparé par le code. Par défaut : allumée." },
    },
    {
        cle: "code_sms",
        libelle: { en: "Code by SMS", fr: "Code par SMS" },
        aide: { en: "A one-time code sent during the call to the record's mobile, through the client's Twilio (« Telephony »). Wired, never tried for real: switch it on only with a client who asks for it. Default: off.", fr: "Un code à usage unique envoyé pendant l'appel au mobile du dossier, par le Twilio du client (« Téléphonie »). Branché, jamais essayé en réel : à allumer seulement avec un client qui le demande. Par défaut : éteint." },
    },
];

export const CHAMPS_CONTROLE: Array<{ cle: string; libelle: Texte }> = [
    { cle: "reference", libelle: { en: "A request's number", fr: "Numéro d'une demande" } },
    { cle: "nom", libelle: { en: "Last name", fr: "Nom" } },
    { cle: "code_postal", libelle: { en: "Postcode", fr: "Code postal" } },
    { cle: "commune", libelle: { en: "Town", fr: "Commune" } },
    { cle: "mail", libelle: { en: "E-mail", fr: "E-mail" } },
];

export const TYPES_LISIBLES: Array<{ cle: "demandes" | "rendez_vous"; libelle: Texte; champs: Array<{ cle: string; libelle: Texte }> }> = [
    {
        cle: "demandes",
        libelle: { en: "His requests and where they stand", fr: "Ses demandes et où elles en sont" },
        champs: [
            { cle: "reference", libelle: { en: "Number", fr: "Numéro" } },
            { cle: "type", libelle: { en: "Type", fr: "Type" } },
            { cle: "statut", libelle: { en: "Status", fr: "Statut" } },
            { cle: "creee_le", libelle: { en: "Date", fr: "Date" } },
            { cle: "resume", libelle: { en: "Summary", fr: "Résumé" } },
        ],
    },
    {
        cle: "rendez_vous",
        libelle: { en: "His coming appointments", fr: "Ses prochains rendez-vous" },
        champs: [
            { cle: "debut", libelle: { en: "Start", fr: "Début" } },
            { cle: "fin", libelle: { en: "End", fr: "Fin" } },
            { cle: "libelle", libelle: { en: "Kind", fr: "Nature" } },
            { cle: "statut", libelle: { en: "Status", fr: "Statut" } },
        ],
    },
];

/** What « Save » sends: the whole settings, as the server holds them. */
export const charge_utile_verification = (r: ReglagesVerification): ReglagesVerification => ({
    numero: r.numero ?? true,
    question: r.question ?? true,
    code_sms: r.code_sms ?? false,
    champs_controle: r.champs_controle ?? [],
    lisibles: r.lisibles ?? {},
    logiciel: r.logiciel || null,
});

const basculer = (liste: string[], cle: string, present: boolean) =>
    present ? [...liste.filter((x) => x !== cle), cle] : liste.filter((x) => x !== cle);

export const ThemeVerification = ({ ouvert, onBasculer, signaler, plat, sansTitre }: ProprietesThemeOrganisation) => {
    const { t } = useLangue();
    const maquette = useFormeMaquette();
    const { user, loading: authLoading } = useAuth();
    const [enregistre, setEnregistre] = useState<ReglagesVerification | null>(null);
    const [brouillon, setBrouillon] = useState<ReglagesVerification | null>(null);
    const [logiciels, setLogiciels] = useState<LogicielDossier[]>([]);
    const [erreur, setErreur] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);
    const dejaLu = useRef(false);

    useEffect(() => {
        if (authLoading || !user || dejaLu.current) return;
        dejaLu.current = true;
        void (async () => {
            const [r, l] = await Promise.all([
                getVerificationAppelantApiV1OrganizationsVerificationAppelantGet(),
                getLogicielsDossierApiV1OrganizationsVerificationAppelantLogicielsGet(),
            ]);
            setLogiciels(l?.data ?? []);
            if (!r || r.error || !r.data) {
                setErreur(detailFromError(r?.error, "Caller verification unreadable"));
                return;
            }
            setEnregistre(r.data);
            setBrouillon(r.data);
        })();
    }, [authLoading, user]);

    const modifie = useMemo(
        () => brouillon !== null && enregistre !== null && JSON.stringify(charge_utile_verification(brouillon)) !== JSON.stringify(charge_utile_verification(enregistre)),
        [brouillon, enregistre],
    );
    const actifs = brouillon ? FACTEURS.filter((f) => brouillon[f.cle]).length : 0;
    const erreurs: ErreurNommee[] = [];
    if (brouillon?.question && !(brouillon.champs_controle ?? []).length)
        erreurs.push({ cle: "champs_controle", libelle: t({ en: "Fields of the question", fr: "Champs de la question" }), message: t({ en: "choose at least one", fr: "choisissez-en au moins un" }), afficher: () => undefined });
    for (const type of TYPES_LISIBLES) {
        const niveau = brouillon?.lisibles?.[type.cle];
        if (brouillon && niveau && (niveau.champs ?? []).length && (niveau.facteurs_requis ?? 2) > actifs)
            erreurs.push({ cle: `lisibles.${type.cle}`, libelle: t(type.libelle), message: t({ en: "more factors required than switched on", fr: "plus de facteurs exigés qu'allumés" }), afficher: () => undefined });
    }
    useSignaler("verification", modifie, erreurs.length > 0, signaler);

    const poser = (champ: Partial<ReglagesVerification>) => setBrouillon((a) => (a ? { ...a, ...champ } : a));
    const poserNiveau = (type: string, champ: { facteurs_requis?: number; champs?: string[] }) =>
        setBrouillon((a) => {
            if (!a) return a;
            const actuel = a.lisibles?.[type] ?? { facteurs_requis: 2, champs: [] };
            return { ...a, lisibles: { ...(a.lisibles ?? {}), [type]: { ...actuel, ...champ } } };
        });

    const enregistrer = async () => {
        if (!brouillon) return;
        setEnCours(true);
        setErreur(null);
        const r = await putVerificationAppelantApiV1OrganizationsVerificationAppelantPut({ body: charge_utile_verification(brouillon) });
        setEnCours(false);
        if (r.error || !r.data) {
            setErreur(detailFromError(r.error, "Caller verification not saved"));
            return;
        }
        setEnregistre(r.data);
        setBrouillon(r.data);
        notifier.succes({ fr: "Vérification enregistrée.", en: "Verification saved." });
    };

    return (
        <Theme
            id="verification"
            plat={plat}
            sansTitre={sansTitre}
            icone={ShieldCheck}
            titre={TITRE_VERIFICATION}
            description={{
                en: "What the code checks before an agent may read a caller's record: factors, control question, level and readable fields by kind of data. Runs only for an agent that switches it on.",
                fr: "Ce que le code vérifie avant qu'un agent puisse lire le dossier d'un appelant : facteurs, question de contrôle, niveau et champs lisibles par type de donnée. Ne tourne que pour un agent qui l'allume.",
            }}
            resume={[brouillon ? t({ en: `${actifs} factor(s)`, fr: `${actifs} facteur(s)` }) : null]}
            ouvert={ouvert}
            onBasculer={onBasculer}
            modifie={modifie}
            erreurs={erreurs}
            enregistrement={brouillon && !maquette ? { onEnregistrer: () => void enregistrer(), enCours } : undefined}
        >
            {brouillon === null ? (
                <p className="text-sm text-muted-foreground">{erreur ?? t({ en: "Loading…", fr: "Chargement…" })}</p>
            ) : (
                <>
                    <Intertitre
                        id="verif-groupe-facteurs"
                        titre={{ en: "Factors", fr: "Facteurs" }}
                        description={maquette ? { en: "What the code checks before an agent may read a caller's record. Runs only for an agent that switches it on. Two failed attempts: nothing is read, a colleague calls back. The answers are never kept.", fr: "Ce que le code vérifie avant qu'un agent puisse lire le dossier d'un appelant. Ne tourne que pour un agent qui l'allume. Deux tentatives échouées : rien n'est lu, un collègue rappelle. Les réponses ne sont jamais gardées." } : undefined}
                        action={
                            maquette ? (
                                <Button size="sm" disabled={enCours || !modifie || erreurs.length > 0} data-testid="enregistrer-verification" onClick={() => void enregistrer()}>
                                    {t({ en: "Save", fr: "Enregistrer" })}
                                </Button>
                            ) : undefined
                        }
                    >
                        {FACTEURS.map((f) => (
                            <ChampReglage key={f.cle} cle={f.cle} idControle={`verif-${f.cle}`} libelle={f.libelle} aides={[f.aide]} disposition="ligne">
                                <Switch id={`verif-${f.cle}`} checked={Boolean(brouillon[f.cle])} onCheckedChange={(v) => poser({ [f.cle]: v })} />
                            </ChampReglage>
                        ))}
                        <ChampReglage
                            cle="champs_controle"
                            libelle={{ en: "Fields of the question", fr: "Champs de la question" }}
                            aides={[
                                { en: "The caller must give every field ticked. A wrong answer is a failed attempt; two failed attempts: nothing is read, a colleague calls back. The answers are never kept.", fr: "L'appelant doit donner chaque champ coché. Une mauvaise réponse est une tentative échouée ; deux tentatives échouées : rien n'est lu, un collègue rappelle. Les réponses ne sont jamais gardées." },
                                { en: "Shown only with the control question on.", fr: "Affiché seulement quand la question de contrôle est allumée." },
                            ]}
                            bornes={{ en: "Default: last name and postcode", fr: "Par défaut : nom et code postal" }}
                        >
                            {brouillon.question ? (
                                maquette ? (
                                    <div data-testid="verif-champs-controle">
                                        <Puces
                                            choix={CHAMPS_CONTROLE.map((c) => ({ cle: c.cle, libelle: t(c.libelle) }))}
                                            valeur={brouillon.champs_controle ?? []}
                                            changer={(v) => poser({ champs_controle: v })}
                                        />
                                        {!(brouillon.champs_controle ?? []).length && (
                                            <p className="pt-2 text-xs text-destructive">{t({ en: "Choose at least one.", fr: "Choisissez-en au moins un." })}</p>
                                        )}
                                    </div>
                                ) : (
<div className="flex flex-wrap gap-3" data-testid="verif-champs-controle">
                                    {CHAMPS_CONTROLE.map((c) => (
                                        <label key={c.cle} className="flex items-center gap-1 text-sm">
                                            <input
                                                type="checkbox"
                                                checked={(brouillon.champs_controle ?? []).includes(c.cle)}
                                                onChange={(e) => poser({ champs_controle: basculer(brouillon.champs_controle ?? [], c.cle, e.target.checked) })}
                                            />
                                            {t(c.libelle)}
                                        </label>
                                    ))}
                                </div>
                            
                                )
) : (
                                <span className="text-xs text-muted-foreground">{t({ en: "Control question off.", fr: "Question de contrôle éteinte." })}</span>
                            )}
                        </ChampReglage>
                    </Intertitre>

                    <Intertitre
                        id="verif-groupe-lecture"
                        titre={{ en: "What may be read", fr: "Ce qui peut être lu" }}
                        description={maquette ? { en: "How many distinct factors must have passed, and the fields the agent may read. No field ticked: never read.", fr: "Combien de facteurs distincts doivent avoir réussi, et les champs que l'agent peut lire. Aucun champ coché : jamais lu." } : undefined}
                    >
                        {TYPES_LISIBLES.map((type) => {
                            const niveau = brouillon.lisibles?.[type.cle] ?? { facteurs_requis: 2, champs: [] };
                            return (
                                <ChampReglage
                                    key={type.cle}
                                    cle={`lisibles.${type.cle}`}
                                    idControle={`verif-niveau-${type.cle}`}
                                    libelle={type.libelle}
                                    aides={[{ en: "How many distinct factors must have passed, and the fields the agent may read. No field ticked: never read.", fr: "Combien de facteurs distincts doivent avoir réussi, et les champs que l'agent peut lire. Aucun champ coché : jamais lu." }]}
                                    bornes={bornesDe(1, 3)}
                                >
                                    {maquette ? (
                                        <div className="space-y-3">
                                            <div className="flex items-center gap-3">
                                                <span className="text-sm text-muted-foreground">{t({ en: "Factors required", fr: "Facteurs exigés" })}</span>
                                                <Input
                                                    id={`verif-niveau-${type.cle}`}
                                                    type="number"
                                                    min={1}
                                                    max={3}
                                                    aria-label={t({ en: "Factors required", fr: "Facteurs exigés" })}
                                                    value={niveau.facteurs_requis ?? 2}
                                                    className={`w-20 text-right ${(niveau.facteurs_requis ?? 2) > actifs ? "border-(--pastille-urgente)" : ""}`}
                                                    onChange={(e) => poserNiveau(type.cle, { facteurs_requis: Math.min(3, Math.max(1, Number(e.target.value) || 1)) })}
                                                />
                                            </div>
                                            {(niveau.facteurs_requis ?? 2) > actifs && (
                                                <p className="text-xs text-destructive" data-testid={`verif-inaccessible-${type.cle}`}>
                                                    {t({ en: "More factors required than switched on: never read.", fr: "Plus de facteurs exigés qu'allumés : jamais lu." })}
                                                </p>
                                            )}
                                            <Puces
                                                choix={type.champs.map((c) => ({ cle: c.cle, libelle: t(c.libelle) }))}
                                                valeur={niveau.champs ?? []}
                                                changer={(v) => poserNiveau(type.cle, { champs: v })}
                                                testid={(c) => `verif-lisible-${type.cle}-${c}`}
                                            />
                                        </div>
                                    ) : (
                                    <div className="space-y-1">
                                        <ListeDeroulante
                                            id={`verif-niveau-${type.cle}`}
                                            aria-label={t({ en: "Factors required", fr: "Facteurs exigés" })}
                                            className="rounded border border-border bg-background px-2 py-1 text-sm"
                                            value={niveau.facteurs_requis ?? 2}
                                            onChange={(e) => poserNiveau(type.cle, { facteurs_requis: Number(e.target.value) })}
                                        >
                                            {[1, 2, 3].map((n) => (
                                                <option key={n} value={n}>
                                                    {t({ en: `${n} factor(s)`, fr: `${n} facteur(s)` })}
                                                </option>
                                            ))}
                                        </ListeDeroulante>
                                        {(niveau.facteurs_requis ?? 2) > actifs && (
                                            <p className="text-xs text-destructive" data-testid={`verif-inaccessible-${type.cle}`}>
                                                {t({ en: "More factors required than switched on: never read.", fr: "Plus de facteurs exigés qu'allumés : jamais lu." })}
                                            </p>
                                        )}
                                        <div className="flex flex-wrap gap-3">
                                            {type.champs.map((c) => (
                                                <label key={c.cle} className="flex items-center gap-1 text-sm">
                                                    <input
                                                        type="checkbox"
                                                        data-testid={`verif-lisible-${type.cle}-${c.cle}`}
                                                        checked={(niveau.champs ?? []).includes(c.cle)}
                                                        onChange={(e) => poserNiveau(type.cle, { champs: basculer(niveau.champs ?? [], c.cle, e.target.checked) })}
                                                    />
                                                    {t(c.libelle)}
                                                </label>
                                            ))}
                                        </div>
                                    </div>
                                    )}
                                </ChampReglage>
                            );
                        })}
                    </Intertitre>

                    <Intertitre
                        id="verif-groupe-source"
                        titre={{ en: "Where the records are", fr: "Où sont les dossiers" }}
                        description={maquette ? { en: "A software that holds the records appears here once its translator exists and it is connected (« Integrations »).", fr: "Un logiciel qui tient les dossiers apparaît ici dès que son traducteur existe et qu'il est connecté (« Intégrations »)." } : undefined}
                    >
                        <ChampReglage
                            cle="logiciel"
                            idControle="verif-logiciel"
                            libelle={{ en: "Records read in", fr: "Dossiers lus dans" }}
                            aides={[{ en: "The client database by default. A software that holds the records appears here once its translator exists (and is connected in « Integrations »).", fr: "La base du client par défaut. Un logiciel qui tient les dossiers apparaît ici dès que son traducteur existe (et qu'il est connecté dans « Intégrations »)." }]}
                            bornes={{ en: "Default: the client database", fr: "Par défaut : la base du client" }}
                        >
                            {maquette ? (
                                <Liste
                                    valeur={brouillon.logiciel ?? ""}
                                    changer={(v) => poser({ logiciel: v || null })}
                                    vide={t({ en: "The client database", fr: "La base du client" })}
                                    options={logiciels.map((l) => ({ valeur: l.systeme, libelle: l.libelle }))}
                                    className="w-56"
                                />
                            ) : (
                            <ListeDeroulante
                                id="verif-logiciel"
                                className="rounded border border-border bg-background px-2 py-1 text-sm"
                                value={brouillon.logiciel ?? ""}
                                onChange={(e) => poser({ logiciel: e.target.value || null })}
                            >
                                <option value="">{t({ en: "The client database", fr: "La base du client" })}</option>
                                {logiciels.map((l) => (
                                    <option key={l.systeme} value={l.systeme}>
                                        {l.libelle}
                                    </option>
                                ))}
                            </ListeDeroulante>
                            )}
                        </ChampReglage>
                    </Intertitre>
                    {erreur && (
                        <p className="text-sm text-destructive" role="alert">
                            {erreur}
                        </p>
                    )}
                </>
            )}
        </Theme>
    );
};
