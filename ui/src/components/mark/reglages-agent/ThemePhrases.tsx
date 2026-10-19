"use client";

/**
 * [.mark] Theme « Phrases » (chantier fiabilite-orchestration, lot 4 bis: F15, F17, F18, F23 to F25).
 *
 * Every sentence the CODE says by itself, without the model, comes from a cause the code can detect
 * (`phrases/catalogue-des-phrases.json`, the copy of `api/services/phrases/catalogue.py`, kept equal by
 * `test_phrases_ecran.py`). A rule = a cause + a place (the whole group, set on the main agent; this
 * agent; one step of this agent) + one to three sentences + a delay when the cause has one + on/off.
 * The call takes the step's rule, else the agent's, else the main agent's group rule, else the default.
 *
 * Taken over (F17): the bridge phrase (`attente.phrase_pont`, its delay) and the sentence before a call
 * transfer (`transfert_humain.phrase_mise_en_relation`), set before this theme existed, show here as group
 * rules; the first save of the theme writes them as rules and removes the old keys (values kept).
 */
import { MessageSquareText, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import type { ReglePhrase, WorkflowConfigurations } from "@/types/workflow-configurations";

import { ChampReglage } from "../ecran/ChampReglage";
import { Intertitre } from "../ecran/Intertitre";
import { Theme } from "../ecran/Theme";
import { useGroupe } from "../groupe/contexte-groupe";
import { DELAI_PHRASE_PONT_DEFAUT_S } from "../groupe/reglages-groupe";
import { type Texte, useLangue } from "../langue/langue";
import { useEnregistrementTheme } from "./enregistrement";
import CATALOGUE from "./phrases/catalogue-des-phrases.json";
import { differe, nommerErreurs, type ProprietesThemeAgent, useBrouillon, useEtatTheme, useRevelation } from "./theme-commun";

export const ID_THEME_PHRASES = "phrases";
export const TITRE_PHRASES = { en: "Phrases", fr: "Phrases" };

export interface MotifDePhrase {
    id: string;
    famille: "attente" | "annonce";
    libelle: Texte;
    quand: Texte;
    a_un_delai: boolean;
    variantes_defaut: string[];
    delai_defaut_s: number | null;
    actif_par_defaut: boolean;
    eteinte: Texte;
    silence_de_l_appelant: boolean;
}

export const MOTIFS_DE_PHRASES = CATALOGUE.motifs as MotifDePhrase[];
export const BORNES_PHRASES = CATALOGUE.bornes;

const MOTIF_PASSATION = "passation_tarde";
const MOTIF_MISE_EN_RELATION = "mise_en_relation";

/** One rule as the screen edits it: the place is one value (« groupe », « agent », « etape:<name> »). */
interface RegleEcran {
    motif: string;
    endroit: string;
    variantes: string[];
    delai: string;
    active: boolean;
}

const endroitDe = (r: ReglePhrase) => (r.portee === "etape" ? `etape:${r.etape ?? ""}` : (r.portee ?? "agent"));

const versEcran = (r: ReglePhrase): RegleEcran => ({
    motif: r.motif,
    endroit: endroitDe(r),
    variantes: [...(r.variantes ?? [])],
    delai: r.delai_s === null || r.delai_s === undefined ? "" : String(r.delai_s),
    active: r.active ?? true,
});

/** The rules of the configuration, plus the old sentences taken over as group rules (F17). */
export const extrairePhrases = (c: Partial<WorkflowConfigurations>) => {
    const regles = (c.phrases_regles ?? []).map(versEcran);
    const aUneRegleDeGroupe = (motif: string) => regles.some((r) => r.motif === motif && r.endroit === "groupe");
    const pont = c.attente?.phrase_pont?.trim() ?? "";
    if (pont !== "" && !aUneRegleDeGroupe(MOTIF_PASSATION)) {
        regles.push({
            motif: MOTIF_PASSATION,
            endroit: "groupe",
            variantes: [pont],
            delai: String(c.attente?.delai_phrase_pont_s ?? DELAI_PHRASE_PONT_DEFAUT_S),
            active: true,
        });
    }
    const relation = c.transfert_humain?.phrase_mise_en_relation?.trim() ?? "";
    if (relation !== "" && !aUneRegleDeGroupe(MOTIF_MISE_EN_RELATION)) {
        regles.push({ motif: MOTIF_MISE_EN_RELATION, endroit: "groupe", variantes: [relation], delai: "", active: true });
    }
    return { regles };
};

const motifDe = (id: string) => MOTIFS_DE_PHRASES.find((m) => m.id === id);

const nombre = (texte: string): number | null => {
    if (texte.trim() === "") return null;
    const n = Number(texte.replace(",", "."));
    return Number.isFinite(n) ? n : NaN;
};

/** What is saved: the rules, cleaned, in the server's shape. */
export const chargePhrases = (regles: RegleEcran[]): ReglePhrase[] =>
    regles.map((r) => {
        const motif = motifDe(r.motif);
        const variantes = r.variantes.map((v) => v.trim().replace(/\s+/g, " ")).filter((v) => v !== "");
        const etape = r.endroit.startsWith("etape:") ? r.endroit.slice("etape:".length) : null;
        const delai = motif?.a_un_delai ? nombre(r.delai) : null;
        return {
            motif: r.motif,
            portee: etape !== null ? "etape" : (r.endroit as "groupe" | "agent"),
            etape,
            variantes: [...new Set(variantes)],
            delai_s: delai,
            active: r.active,
        };
    });

/** The named errors of the rules (F23: two rules of the same cause at the same place are refused). */
export const erreursDesPhrases = (regles: RegleEcran[]): Array<{ cle: string; libelle: Texte; message: Texte }> => {
    const erreurs: Array<{ cle: string; libelle: Texte; message: Texte }> = [];
    const vues = new Set<string>();
    if (regles.length > BORNES_PHRASES.regles_max) {
        erreurs.push({
            cle: "phrases_regles",
            libelle: TITRE_PHRASES,
            message: { en: `At most ${BORNES_PHRASES.regles_max} rules.`, fr: `Au plus ${BORNES_PHRASES.regles_max} règles.` },
        });
    }
    chargePhrases(regles).forEach((regle, i) => {
        const motif = motifDe(regle.motif);
        const libelle = motif?.libelle ?? { en: regle.motif, fr: regle.motif };
        const cle = `phrases_regles.${i}`;
        const endroit = `${regle.motif}|${regle.portee}|${regle.etape ?? ""}`;
        if (vues.has(endroit)) {
            erreurs.push({ cle, libelle, message: { en: "Two rules of this cause at the same place.", fr: "Deux règles de ce motif au même endroit." } });
        }
        vues.add(endroit);
        if (regle.portee === "etape" && !regle.etape) {
            erreurs.push({ cle, libelle, message: { en: "Choose the step.", fr: "Choisissez l'étape." } });
        }
        if (regle.active && regle.variantes.length === 0) {
            erreurs.push({ cle, libelle, message: { en: "An active rule needs a sentence.", fr: "Une règle activée demande une phrase." } });
        }
        if (regle.variantes.some((v) => v.length > BORNES_PHRASES.longueur_max)) {
            erreurs.push({
                cle,
                libelle,
                message: { en: `At most ${BORNES_PHRASES.longueur_max} characters.`, fr: `Au plus ${BORNES_PHRASES.longueur_max} caractères.` },
            });
        }
        const d = regle.delai_s;
        if (d !== null && d !== undefined && (Number.isNaN(d) || d < BORNES_PHRASES.delai_min_s || d > BORNES_PHRASES.delai_max_s)) {
            erreurs.push({
                cle,
                libelle,
                message: {
                    en: `Delay between ${BORNES_PHRASES.delai_min_s} and ${BORNES_PHRASES.delai_max_s} s.`,
                    fr: `Délai entre ${BORNES_PHRASES.delai_min_s} et ${BORNES_PHRASES.delai_max_s} s.`,
                },
            });
        }
    });
    return erreurs;
};

const TEXTES = {
    description: {
        en: "The sentences the code says by itself, without the model, when it detects a wait or a problem.",
        fr: "Les phrases que le code dit lui-même, sans le modèle, quand il détecte une attente ou un problème.",
    },
    attentes: { en: "Waits", fr: "Attentes" },
    attentesAide: {
        en: "One at a time, then 3 s of rest; never while the caller speaks. Their delay only runs while the system works, never while the caller thinks.",
        fr: "Une seule à la fois, puis 3 s de repos ; jamais pendant que l'appelant parle. Leur délai ne court que pendant que le système travaille, jamais pendant que l'appelant réfléchit.",
    },
    annonces: { en: "Announcements", fr: "Annonces" },
    annoncesAide: {
        en: "Always said, after the sentence in progress. The caller can cut any sentence of the code: it stops there.",
        fr: "Toujours dites, à la suite de la phrase en cours. L'appelant peut couper toute phrase du code : elle s'arrête net.",
    },
    defaut: { en: "Default", fr: "Par défaut" },
    allumee: { en: "on", fr: "allumée" },
    eteinteParDefaut: { en: "off", fr: "éteinte" },
    quandEteinte: { en: "When off", fr: "Éteinte" },
    ajouter: { en: "Add a rule", fr: "Ajouter une règle" },
    retirer: { en: "Remove the rule", fr: "Retirer la règle" },
    endroit: { en: "Where", fr: "Où" },
    groupe: { en: "The whole group", fr: "Tout le groupe" },
    agent: { en: "This agent", fr: "Cet agent" },
    etape: { en: "Step", fr: "Étape" },
    phrase: { en: "Sentence", fr: "Phrase" },
    delai: { en: "Delay (s)", fr: "Délai (s)" },
    delaiGarde: {
        en: "Its delay is the model guard's (theme Services, « Model guard »).",
        fr: "Son délai est celui de la garde du modèle (thème Briques, « Garde du modèle »).",
    },
    active: { en: "On", fr: "Activée" },
    reprise: {
        en: "Taken over from the former setting: saved as a rule at the next save of this theme.",
        fr: "Repris de l'ancien réglage : enregistré comme règle au prochain enregistrement de ce thème.",
    },
} satisfies Record<string, Texte>;

export const ThemePhrases = ({
    resolue,
    workflowName,
    onSave,
    ouvert,
    onBasculer,
    ouvrir,
    etapes,
}: ProprietesThemeAgent & { etapes: string[] }) => {
    const { t } = useLangue();
    const groupe = useGroupe();
    const { enregistre, brouillon, setBrouillon, resynchroniser } = useBrouillon(resolue, extrairePhrases);
    const { afficher } = useRevelation(ouvrir);
    const regles = brouillon.regles;
    const setRegles = (maj: (avant: RegleEcran[]) => RegleEcran[]) => setBrouillon((avant) => ({ regles: maj(avant.regles) }));

    const modifie = differe(brouillon, enregistre);
    const erreurs = erreursDesPhrases(regles);
    useEtatTheme(ID_THEME_PHRASES, modifie, erreurs.length > 0);

    // The group's rules live on the main agent only (a lone agent has « this agent »).
    const peutRegleDeGroupe = groupe.specialiseDe === null && Array.isArray(resolue.agents_specialises);
    const ancienPont = (resolue.attente?.phrase_pont ?? "").trim() !== "" || resolue.attente?.delai_phrase_pont_s != null;
    const ancienneRelation = (resolue.transfert_humain?.phrase_mise_en_relation ?? "").trim() !== "";

    const { enCours, enregistrer } = useEnregistrementTheme({
        titre: TITRE_PHRASES,
        resolue,
        workflowName,
        onSave,
        parties: [
            {
                nom: { en: "Phrases", fr: "Phrases" },
                modifie,
                config: () => {
                    const charge: Partial<WorkflowConfigurations> = { phrases_regles: chargePhrases(regles) };
                    // F17: the old keys are removed once their value is a rule (kept by the theme).
                    if (ancienPont) {
                        const { phrase_pont: _p, delai_phrase_pont_s: _d, ...reste } = resolue.attente ?? {};
                        charge.attente = reste;
                    }
                    if (ancienneRelation) {
                        const { phrase_mise_en_relation: _r, ...reste } = resolue.transfert_humain ?? {};
                        charge.transfert_humain = reste;
                    }
                    return charge;
                },
                apres: resynchroniser,
            },
        ],
    });

    const ajouter = (motif: MotifDePhrase) =>
        setRegles((avant) => [
            ...avant,
            {
                motif: motif.id,
                endroit: peutRegleDeGroupe && !avant.some((r) => r.motif === motif.id && r.endroit === "groupe") ? "groupe" : "agent",
                variantes: [...motif.variantes_defaut],
                delai: motif.a_un_delai && motif.delai_defaut_s !== null ? String(motif.delai_defaut_s) : "",
                active: true,
            },
        ]);
    const changer = (index: number, patch: Partial<RegleEcran>) =>
        setRegles((avant) => avant.map((r, i) => (i === index ? { ...r, ...patch } : r)));
    const retirer = (index: number) => setRegles((avant) => avant.filter((_, i) => i !== index));

    const reprise = (r: RegleEcran) =>
        r.endroit === "groupe" &&
        !(resolue.phrases_regles ?? []).some((x) => x.motif === r.motif && (x.portee ?? "agent") === "groupe") &&
        ((r.motif === MOTIF_PASSATION && ancienPont) || (r.motif === MOTIF_MISE_EN_RELATION && ancienneRelation));

    const famille = (id: "attente" | "annonce", titre: Texte, aide: Texte) => (
        <Intertitre id={`phrases-${id}`} titre={titre} description={aide}>
            {MOTIFS_DE_PHRASES.filter((m) => m.famille === id).map((motif) => (
                <div key={motif.id} data-motif={motif.id} className="space-y-3 rounded border p-3">
                    <div className="space-y-1 text-sm">
                        <div className="font-medium">{t(motif.libelle)}</div>
                        <div className="text-muted-foreground">{t(motif.quand)}</div>
                        <div className="text-xs text-muted-foreground">
                            {t(TEXTES.defaut)} : {motif.actif_par_defaut ? t(TEXTES.allumee) : t(TEXTES.eteinteParDefaut)}
                            {" · « "}
                            {motif.variantes_defaut.join(" » / « ")}
                            {" »"}
                            {motif.a_un_delai && motif.delai_defaut_s !== null ? ` · ${motif.delai_defaut_s} s` : ""}
                        </div>
                        <div className="text-xs text-muted-foreground">
                            {t(TEXTES.quandEteinte)} : {t(motif.eteinte)}
                        </div>
                        {!motif.a_un_delai && motif.id === "modele_tarde" && (
                            <div className="text-xs text-muted-foreground">{t(TEXTES.delaiGarde)}</div>
                        )}
                    </div>
                    {regles.map((regle, index) =>
                        regle.motif !== motif.id ? null : (
                            <div key={index} data-regle={`${motif.id}-${index}`} className="space-y-2 rounded bg-muted/40 p-2">
                                {reprise(regle) && (
                                    <p className="text-xs text-muted-foreground" data-note="phrase-reprise">
                                        {t(TEXTES.reprise)}
                                    </p>
                                )}
                                <div className="flex flex-wrap items-end gap-3">
                                    <div className="space-y-1">
                                        <label className="text-xs" htmlFor={`phrase_${index}_endroit`}>
                                            {t(TEXTES.endroit)}
                                        </label>
                                        <Select value={regle.endroit} onValueChange={(v: string) => changer(index, { endroit: v })}>
                                            <SelectTrigger id={`phrase_${index}_endroit`} className="w-56">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {(peutRegleDeGroupe || regle.endroit === "groupe") && (
                                                    <SelectItem value="groupe">{t(TEXTES.groupe)}</SelectItem>
                                                )}
                                                <SelectItem value="agent">{t(TEXTES.agent)}</SelectItem>
                                                {etapes.map((nom) => (
                                                    <SelectItem key={nom} value={`etape:${nom}`}>
                                                        {`${t(TEXTES.etape)} : ${nom}`}
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    {motif.a_un_delai && (
                                        <div className="space-y-1">
                                            <label className="text-xs" htmlFor={`phrase_${index}_delai`}>
                                                {t(TEXTES.delai)}
                                            </label>
                                            <Input
                                                id={`phrase_${index}_delai`}
                                                type="number"
                                                inputMode="decimal"
                                                className="w-28"
                                                min={BORNES_PHRASES.delai_min_s}
                                                max={BORNES_PHRASES.delai_max_s}
                                                step="0.5"
                                                placeholder={motif.delai_defaut_s !== null ? String(motif.delai_defaut_s) : ""}
                                                value={regle.delai}
                                                onChange={(e) => changer(index, { delai: e.target.value })}
                                            />
                                        </div>
                                    )}
                                    <div className="flex items-center gap-2 pb-2">
                                        <Switch
                                            id={`phrase_${index}_active`}
                                            aria-label={t(TEXTES.active)}
                                            checked={regle.active}
                                            onCheckedChange={(coche) => changer(index, { active: coche })}
                                        />
                                        <label className="text-xs" htmlFor={`phrase_${index}_active`}>
                                            {t(TEXTES.active)}
                                        </label>
                                    </div>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        aria-label={`${t(TEXTES.retirer)} : ${t(motif.libelle)}`}
                                        onClick={() => retirer(index)}
                                    >
                                        <Trash2 className="h-4 w-4" />
                                    </Button>
                                </div>
                                {Array.from({ length: BORNES_PHRASES.variantes_max }, (_, v) => (
                                    <Input
                                        key={v}
                                        id={`phrase_${index}_variante_${v}`}
                                        aria-label={`${t(TEXTES.phrase)} ${v + 1}`}
                                        maxLength={BORNES_PHRASES.longueur_max}
                                        placeholder={v === 0 ? (motif.variantes_defaut[0] ?? "") : ""}
                                        value={regle.variantes[v] ?? ""}
                                        onChange={(e) => {
                                            const variantes = [...regle.variantes];
                                            while (variantes.length <= v) variantes.push("");
                                            variantes[v] = e.target.value;
                                            changer(index, { variantes });
                                        }}
                                    />
                                ))}
                            </div>
                        ),
                    )}
                    <Button variant="outline" size="sm" aria-label={`${t(TEXTES.ajouter)} : ${t(motif.libelle)}`} onClick={() => ajouter(motif)}>
                        <Plus className="mr-1 h-4 w-4" />
                        {t(TEXTES.ajouter)}
                    </Button>
                </div>
            ))}
        </Intertitre>
    );

    const allumees = MOTIFS_DE_PHRASES.filter((m) => {
        const propre = regles.find((r) => r.motif === m.id && r.endroit !== "groupe" && !r.endroit.startsWith("etape:"))
            ?? regles.find((r) => r.motif === m.id && r.endroit === "groupe");
        return propre ? propre.active : m.actif_par_defaut;
    }).length;

    return (
        <Theme
            id={ID_THEME_PHRASES}
            icone={MessageSquareText}
            titre={TITRE_PHRASES}
            description={TEXTES.description}
            resume={[
                `${allumees}/${MOTIFS_DE_PHRASES.length} ${t({ en: "on", fr: "allumées" })}`,
                `${regles.length} ${t({ en: "rule(s)", fr: "règle(s)" })}`,
            ]}
            ouvert={ouvert}
            onBasculer={onBasculer}
            modifie={modifie}
            erreurs={nommerErreurs(erreurs, t, afficher)}
            enregistrement={{ onEnregistrer: enregistrer, enCours }}
        >
            <ChampReglage
                cle="phrases_regles"
                libelle={{ en: "Rules of the sentences said by the code", fr: "Règles des phrases dites par le code" }}
                aides={[
                    {
                        en: "For each cause: the step's rule, else this agent's, else the main agent's group rule, else the default. A specialised agent takes the main agent's sentence until it sets its own.",
                        fr: "Pour chaque motif : la règle de l'étape, sinon celle de cet agent, sinon la règle de groupe du principal, sinon le défaut. Un spécialisé reprend la phrase du principal tant qu'il n'a pas la sienne.",
                    },
                ]}
            >
                <div className="space-y-6">
                    {famille("attente", TEXTES.attentes, TEXTES.attentesAide)}
                    {famille("annonce", TEXTES.annonces, TEXTES.annoncesAide)}
                </div>
            </ChampReglage>
        </Theme>
    );
};
