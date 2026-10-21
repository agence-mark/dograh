"use client";

/**
 * [.mark] correctifs-apres-banc-v4, lot 5 (plan 4.2, 4.3, 4.7) : la MODALE d'une règle de phrase, ouverte par sa
 * carte ou par « Ajouter une phrase » (étape 2). La phrase se lit de haut en bas ; une case que le motif ne permet
 * pas DISPARAÎT, remplacée par une ligne grise qui dit pourquoi. L'apercu déroule ce que vit l'appelant, seconde par
 * seconde, avec les incohérences en orange (sans bloquer) ; les erreurs qui bloquent sont nommées au-dessus du pied.
 *
 * Elle travaille sur une COPIE de la règle : « Enregistrer » la rend à l'appelant (le thème l'inscrit dans son
 * brouillon, la fenêtre d'une étape l'enregistre tout de suite), « Annuler » la jette.
 */
import { Plus, Timer, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import type { ReglePhrase } from "@/types/workflow-configurations";

import { type Texte, useLangue } from "../../langue/langue";
import { CadreModale, Gris, L } from "./cadre";
import type { MembreDeLEquipe,OutilDeLAgent } from "./donnees";
import {
    type Action,
    apercuDeLaRegle,
    appliquerEndroit,
    BORNES_PHRASES,
    type ContextePhrases,
    erreursDeLaRegle,
    type EtapeGraphe,
    MOTIF_SILENCE,
    MOTIF_TRAVAIL_DURE,
    motifDe,
    nomDeLAction,
    normaliserRegle,
    valeurEndroit,
} from "./modele";

export interface ChampDeFiche {
    nom: string;
    valeurs?: string[] | null;
}

export interface EnvironnementPhrases {
    etapes: EtapeGraphe[];
    outils: OutilDeLAgent[];
    champsFiche: ChampDeFiche[];
    equipe: MembreDeLEquipe[];
    /** Le principal d'un groupe peut poser une règle pour tout le groupe ; un agent seul, non. */
    peutGroupe: boolean;
    contexte: ContextePhrases;
}

const TEXTES = {
    dans: { en: "In", fr: "Dans" },
    quand: { en: "When", fr: "Quand" },
    outil: { en: "For the tool", fr: "Pour l'outil" },
    dit: { en: "The code says", fr: "Le code dit" },
    texte: { en: "Text", fr: "Texte" },
    auBoutDe: { en: "After", fr: "Au bout de" },
    redite: { en: "Repeat", fr: "Redite" },
    ensuite: { en: "Then", fr: "Ensuite" },
    groupe: { en: "The whole group", fr: "Tout le groupe" },
    agent: { en: "This agent", fr: "Cet agent" },
    etape: { en: "Step", fr: "Étape" },
    etapeSupprimee: { en: "Deleted step", fr: "Étape supprimée" },
    tousLesOutils: { en: "All the tools", fr: "Tous les outils" },
    placeholderPhrase: { en: "Write the sentence the voice says", fr: "Écrivez la phrase dite par la voix" },
    ajouterPhrase: { en: "add a sentence", fr: "ajouter une phrase" },
    ordre: { en: "Order", fr: "Ordre" },
    tournees: { en: "Rotated", fr: "Tournées" },
    dansLOrdre: { en: "In order", fr: "Dans l'ordre" },
    lesPhrases: { en: "The sentences above", fr: "Les phrases ci-dessus" },
    cellEcritePar: { en: "The one the agent writes, else the sentences above", fr: "Celle que l'agent écrit, sinon les phrases ci-dessus" },
    secondes: { en: "s", fr: "s" },
    tousLes: { en: "every", fr: "toutes les" },
    auPlus: { en: "at most", fr: "au plus" },
    foisParAttente: { en: "times per wait (the first included)", fr: "fois par attente (la première comprise)" },
    foisRelances: { en: "prompts", fr: "relances" },
    et: { en: "and", fr: "et" },
    dansLAppel: { en: "in the call", fr: "dans l'appel" },
    sansLimite: { en: "no limit", fr: "sans limite" },
    jamais: { en: "never", fr: "jamais" },
    dire: { en: "say", fr: "dire" },
    noter: { en: "note", fr: "noter" },
    puis: { en: "then", fr: "puis" },
    egal: { en: "=", fr: "=" },
    activee: { en: "On", fr: "Activée" },
    eteinte: { en: "Off", fr: "Éteinte" },
    supprimer: { en: "Delete", fr: "Supprimer" },
    annuler: { en: "Cancel", fr: "Annuler" },
    enregistrer: { en: "Save", fr: "Enregistrer" },
    ajouter: { en: "Add", fr: "Ajouter" },
    changerMotif: { en: "← Change the cause", fr: "← Changer de motif" },
    apercu: { en: "Preview: what the caller hears", fr: "Aperçu : ce qu'entend l'appelant" },
    siEteinte: { en: "If off:", fr: "Si éteinte :" },
    aCorriger: { en: "To fix before saving:", fr: "À corriger avant d'enregistrer :" },
    aucune: { en: "—", fr: "—" },
    destination: { en: "Transfer to", fr: "Transférer à" },
    cleDeLEquipe: { en: "Team member key", fr: "Clé de la personne de l'équipe" },
} satisfies Record<string, Texte>;

const lire = (texte: string): number | null => {
    if (texte.trim() === "") return null;
    const n = Number(texte.replace(",", "."));
    return Number.isFinite(n) ? n : Number.NaN;
};
const enTexte = (n: number | null | undefined) => (n === null || n === undefined ? "" : String(n));

/** Une à trois phrases, chacune dans sa case. */
const ListeDePhrases = ({
    valeurs,
    onChange,
    idPrefixe,
    libelleCase,
    avecOrdre,
    ordre,
    onOrdre,
    placeholder,
    obligatoire = false,
}: {
    valeurs: string[];
    onChange: (suivantes: string[]) => void;
    idPrefixe: string;
    libelleCase: string;
    avecOrdre?: boolean;
    ordre?: "tournees" | "dans_l_ordre";
    onOrdre?: (o: "tournees" | "dans_l_ordre") => void;
    placeholder?: string;
    obligatoire?: boolean;
}) => {
    const { t } = useLangue();
    const lignes = valeurs.length > 0 ? valeurs : obligatoire ? [""] : [];
    return (
        <div className="w-full space-y-1.5">
            {lignes.map((v, i) => (
                <div key={i} className="flex items-center gap-2">
                    <span className="w-4 text-xs text-muted-foreground">{i + 1}</span>
                    <Input
                        id={`${idPrefixe}_${i}`}
                        aria-label={`${libelleCase} ${i + 1}`}
                        maxLength={BORNES_PHRASES.longueur_max}
                        placeholder={placeholder}
                        value={v}
                        onChange={(e) => {
                            const copie = [...lignes];
                            copie[i] = e.target.value;
                            onChange(copie);
                        }}
                    />
                    {!obligatoire || lignes.length > 1 ? (
                        <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`${t({ en: "Remove", fr: "Retirer" })} ${libelleCase} ${i + 1}`}
                            onClick={() => onChange(lignes.filter((_, j) => j !== i))}
                        >
                            <Trash2 className="h-4 w-4" />
                        </Button>
                    ) : null}
                </div>
            ))}
            {lignes.length < BORNES_PHRASES.variantes_max && (
                <Button variant="ghost" size="sm" className="ml-4" onClick={() => onChange([...lignes, ""])} aria-label={`${t(TEXTES.ajouterPhrase)} (${libelleCase})`}>
                    <Plus className="h-3.5 w-3.5" /> {t(TEXTES.ajouterPhrase)}
                </Button>
            )}
            {avecOrdre && lignes.length > 1 && onOrdre && (
                <div className="ml-6 flex items-center gap-2 pt-1">
                    <span className="text-xs text-muted-foreground">{t(TEXTES.ordre)}</span>
                    <Select value={ordre ?? "tournees"} onValueChange={(v: string) => onOrdre(v as "tournees" | "dans_l_ordre")}>
                        <SelectTrigger id={`${idPrefixe}_ordre`} className="w-40" aria-label={t(TEXTES.ordre)}>
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="tournees">{t(TEXTES.tournees)}</SelectItem>
                            <SelectItem value="dans_l_ordre">{t(TEXTES.dansLOrdre)}</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
            )}
        </div>
    );
};

const Nombre = ({ id, valeur, onChange, unite, largeur = "w-20", etiquette }: { id: string; valeur: string; onChange: (v: string) => void; unite?: string; largeur?: string; etiquette: string }) => (
    <span className="flex items-center gap-1">
        <Input id={id} aria-label={etiquette} type="number" inputMode="decimal" step="0.5" className={`h-9 ${largeur}`} value={valeur} onChange={(e) => onChange(e.target.value)} />
        {unite && <span className="text-sm text-muted-foreground">{unite}</span>}
    </span>
);

export const FormulaireRegle = ({
    regle,
    onChange,
    env,
    existeUneRegleDuGroupe,
}: {
    regle: ReglePhrase;
    onChange: (r: ReglePhrase) => void;
    env: EnvironnementPhrases;
    existeUneRegleDuGroupe?: boolean;
}) => {
    const { t } = useLangue();
    const motif = motifDe(regle.motif);
    const [saisies, setSaisies] = useState({
        delai: enTexte(regle.delai_s),
        redite: enTexte(regle.redite_s),
        parAttente: enTexte(regle.max_par_attente),
        parAppel: enTexte(regle.max_par_appel),
    });
    const apercu = useMemo(() => apercuDeLaRegle(regle, env.contexte, { existeUneRegleDuGroupe }), [regle, env.contexte, existeUneRegleDuGroupe]);
    if (!motif) return null;
    const maj = (patch: Partial<ReglePhrase>) => onChange({ ...regle, ...patch });
    const majSortie = (patch: NonNullable<ReglePhrase["ensuite"]>) => maj({ ensuite: { ...(regle.ensuite ?? {}), ...patch } });
    const saisir = (cle: keyof typeof saisies, texte: string, champ: "delai_s" | "redite_s" | "max_par_attente" | "max_par_appel") => {
        setSaisies((avant) => ({ ...avant, [cle]: texte }));
        const valeur = lire(texte);
        // Une annonce écrite par l'agent est dite dès le lancement : un délai non nul la retire.
        if (champ === "delai_s" && valeur !== 0 && regle.texte_de_l_agent) maj({ delai_s: valeur, texte_de_l_agent: false });
        else maj({ [champ]: valeur } as Partial<ReglePhrase>);
    };
    const estSilence = motif.id === MOTIF_SILENCE;
    const probleme = motif.moment === "probleme";
    const sortieAction = (regle.ensuite?.action ?? "") as Action | "";
    const fin = motif.fin_d_attente.fr || motif.fin_d_attente.en;
    const valeurDuEndroit = valeurEndroit(regle, env.etapes);
    const etapeInconnue = regle.portee === "etape" && !env.etapes.some((e) => `etape:${e.id}` === valeurDuEndroit);
    const champChoisi = env.champsFiche.find((c) => c.nom === regle.ensuite?.noter?.champ);
    const sortiesPermises = motif.sorties_permises;
    const sansSortie = motif.id === "mise_en_relation" || (!motif.a_un_delai && motif.moment === "attente");
    const outilsDeLAgent = env.outils.map((o) => o.nom);

    return (
        <div className="space-y-3" data-formulaire-phrase={motif.id}>
            <L label={t(TEXTES.dans)} nom="dans">
                <Select value={valeurDuEndroit} onValueChange={(v: string) => onChange(appliquerEndroit(regle, v, env.etapes))}>
                    <SelectTrigger id="phrase_endroit" aria-label={t(TEXTES.dans)} className="w-72">
                        <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                        {(env.peutGroupe || regle.portee === "groupe") && <SelectItem value="groupe">{t(TEXTES.groupe)}</SelectItem>}
                        <SelectItem value="agent">{t(TEXTES.agent)}</SelectItem>
                        {env.etapes.map((e) => (
                            <SelectItem key={e.id} value={`etape:${e.id}`}>
                                {`${t(TEXTES.etape)} : ${e.nom}`}
                            </SelectItem>
                        ))}
                        {etapeInconnue && <SelectItem value={valeurDuEndroit}>{`${t(TEXTES.etapeSupprimee)} : ${regle.etape ?? regle.etape_id ?? ""}`}</SelectItem>}
                    </SelectContent>
                </Select>
            </L>
            <L label={t(TEXTES.quand)} aide={t(motif.quand)} nom="quand">
                <span className="rounded-md border bg-muted/40 px-3 py-2 text-sm font-medium" data-motif-choisi>
                    {t(motif.libelle)}
                </span>
            </L>
            <L label={t(TEXTES.outil)} nom="outil">
                {motif.filtre_outil ? (
                    outilsDeLAgent.length === 0 ? (
                        <Gris>{t({ en: "All the tools of this agent (no tool read on its steps).", fr: "Tous les outils de cet agent (aucun outil lu sur ses étapes)." })}</Gris>
                    ) : (
                        <div className="w-full space-y-1">
                            <p className="text-xs text-muted-foreground">
                                {(regle.outils ?? []).length === 0 ? t(TEXTES.tousLesOutils) : (regle.outils ?? []).join(", ")}
                            </p>
                            <div className="flex flex-wrap gap-x-4 gap-y-1">
                                {outilsDeLAgent.map((nom) => {
                                    const coche = (regle.outils ?? []).includes(nom);
                                    return (
                                        <label key={nom} className="flex items-center gap-1.5 text-sm">
                                            <Checkbox
                                                aria-label={`${t(TEXTES.outil)} : ${nom}`}
                                                checked={coche}
                                                onCheckedChange={(c) => maj({ outils: c === true ? [...(regle.outils ?? []), nom] : (regle.outils ?? []).filter((x) => x !== nom) })}
                                            />
                                            <code className="text-xs">{nom}</code>
                                        </label>
                                    );
                                })}
                            </div>
                        </div>
                    )
                ) : (
                    <Gris>
                        {motif.id === MOTIF_TRAVAIL_DURE
                            ? t({ en: "Does not apply to this cause: the sentence holds for any job handed over here.", fr: "Ne s'applique pas à ce motif : la phrase vaut pour tout travail confié à cet endroit." })
                            : t({ en: "Does not apply to this cause.", fr: "Ne s'applique pas à ce motif." })}
                    </Gris>
                )}
            </L>
            <L label={t(TEXTES.dit)} nom="variantes">
                <ListeDePhrases
                    valeurs={regle.variantes ?? []}
                    onChange={(variantes) => maj({ variantes })}
                    idPrefixe="phrase_variante"
                    libelleCase={t({ en: "Sentence", fr: "Phrase" })}
                    avecOrdre
                    ordre={regle.ordre}
                    onOrdre={(ordre) => maj({ ordre })}
                    placeholder={t(TEXTES.placeholderPhrase)}
                    obligatoire
                />
            </L>
            {motif.texte_de_l_agent && (
                <L
                    label={t(TEXTES.texte)}
                    nom="texte-de-l-agent"
                    aide={t({
                        en: "Only for this cause, from the very launch (After = 0 s). The tool « hand over the job » then asks the agent for its announcement. Measured before being switched on (29/30).",
                        fr: "Seulement pour ce motif, dès le lancement (Au bout de = 0 s). L'outil qui confie le travail demande alors son annonce à l'agent. Mesuré avant d'être allumé (29/30).",
                    })}
                >
                    {regle.delai_s === 0 ? (
                        <Select value={regle.texte_de_l_agent ? "agent" : "phrases"} onValueChange={(v: string) => maj({ texte_de_l_agent: v === "agent" })}>
                            <SelectTrigger id="phrase_texte_de_l_agent" aria-label={t(TEXTES.texte)} className="w-96">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="phrases">{t(TEXTES.lesPhrases)}</SelectItem>
                                <SelectItem value="agent">{t(TEXTES.cellEcritePar)}</SelectItem>
                            </SelectContent>
                        </Select>
                    ) : (
                        <Gris>{t({ en: "Available only with After = 0 s.", fr: "Disponible seulement avec Au bout de = 0 s." })}</Gris>
                    )}
                </L>
            )}
            <L
                label={t(TEXTES.auBoutDe)}
                nom="delai"
                aide={
                    motif.a_un_delai
                        ? regle.delai_s === 0
                            ? t({ en: "0 s = at once, as soon as the wait starts.", fr: "0 s = dès le début de l'attente." })
                            : estSilence
                              ? t({ en: "Counted in seconds of silence of the caller.", fr: "Compté en secondes de silence de l'appelant." })
                              : probleme
                                ? undefined
                                : t({ en: "Counted from the start of the wait.", fr: "Compté depuis le début de l'attente." })
                        : undefined
                }
            >
                {motif.a_un_delai ? (
                    <Nombre
                        id="phrase_delai"
                        etiquette={t({ en: "Delay (s)", fr: "Délai (s)" })}
                        valeur={saisies.delai}
                        onChange={(v) => saisir("delai", v, "delai_s")}
                        unite={estSilence ? t({ en: "s of silence", fr: "s de silence" }) : t(TEXTES.secondes)}
                    />
                ) : probleme || motif.id === "mise_en_relation" ? (
                    <Gris>
                        {probleme
                            ? t({
                                  en: "No delay or repeat: triggered by a fact (the failure), not by a wait. The waiting time is the tool's (deadline and retries, set on the tool).",
                                  fr: "Pas de délai ni de redite : déclenché par un fait (l'échec), pas par une attente. Le temps d'attente est celui de l'outil (délai et essais, écran de l'outil).",
                              })
                            : t({ en: "No delay: said right before the action.", fr: "Pas de délai : dite juste avant l'action." })}
                    </Gris>
                ) : (
                    <Gris>
                        {t({
                            en: "The delay is the model guard's, set in Models → Guard (Services theme).",
                            fr: "Le délai est celui de la garde du modèle, réglé dans Modèles → Garde (thème Briques).",
                        })}
                    </Gris>
                )}
            </L>
            {motif.moment === "attente" && (
                <L
                    label={t(TEXTES.redite)}
                    nom="redite"
                    aide={motif.peut_redire ? t({ en: "Counted from the end of the previous sentence.", fr: "Compté depuis la fin de la phrase précédente." }) : undefined}
                >
                    {motif.peut_redire ? (
                        <>
                            <span className="text-sm">{t(TEXTES.tousLes)}</span>
                            <Nombre id="phrase_redite" etiquette={t({ en: "Repeat every (s)", fr: "Redite toutes les (s)" })} valeur={saisies.redite} onChange={(v) => saisir("redite", v, "redite_s")} unite={t(TEXTES.secondes)} />
                            <span className="text-xs text-muted-foreground">({t({ en: `empty = ${estSilence ? "as the delay" : "never"}`, fr: `vide = ${estSilence ? "comme le délai" : "jamais"}` })})</span>
                            <span className="text-sm">{t(TEXTES.auPlus)}</span>
                            <Nombre
                                id="phrase_par_attente"
                                etiquette={t({ en: "At most, per wait", fr: "Au plus, par attente" })}
                                valeur={saisies.parAttente}
                                onChange={(v) => saisir("parAttente", v, "max_par_attente")}
                                unite={estSilence ? t(TEXTES.foisRelances) : t(TEXTES.foisParAttente)}
                            />
                            {estSilence && <span className="text-xs text-muted-foreground">({t({ en: "empty = the Call pacing setting", fr: "vide = le réglage de Rythme" })})</span>}
                            {!estSilence && (
                                <>
                                    <span className="text-sm">{t(TEXTES.et)}</span>
                                    <Nombre
                                        id="phrase_par_appel"
                                        etiquette={t({ en: "At most, in the call", fr: "Au plus, dans l'appel" })}
                                        valeur={saisies.parAppel}
                                        onChange={(v) => saisir("parAppel", v, "max_par_appel")}
                                        unite={`${t(TEXTES.dansLAppel)} (${t({ en: "empty", fr: "vide" })} = ${t(TEXTES.sansLimite)})`}
                                        largeur="w-16"
                                    />
                                </>
                            )}
                        </>
                    ) : (
                        <Gris>{t({ en: "Once: the second try goes right away.", fr: "Une seule fois : la seconde tentative part aussitôt." })}</Gris>
                    )}
                </L>
            )}
            {probleme && (
                <>
                    <L label={t({ en: "Before the cap", fr: "Avant le plafond" })} nom="avant-plafond">
                        <Gris>
                            {t({ en: "After the sentence:", fr: "Après la phrase :" })} {t(nomDeLAction(motif.sortie_defaut)).toLowerCase()}
                        </Gris>
                    </L>
                    <L
                        label={t({ en: "At most", fr: "Au plus" })}
                        nom="plafond"
                        aide={t({ en: "Failures counted in the call, then the exit below. Empty: the exit goes at every failure.", fr: "Échecs comptés dans l'appel, puis la sortie ci-dessous. Vide : la sortie part à chaque échec." })}
                    >
                        <Nombre
                            id="phrase_par_appel"
                            etiquette={t({ en: "At most, in the call", fr: "Au plus, dans l'appel" })}
                            valeur={saisies.parAppel}
                            onChange={(v) => saisir("parAppel", v, "max_par_appel")}
                            unite={t({ en: "failures in the call, then:", fr: "échecs dans l'appel, puis :" })}
                            largeur="w-16"
                        />
                    </L>
                </>
            )}
            {sansSortie ? (
                <L label={t(TEXTES.ensuite)} nom="ensuite">
                    <Gris>
                        {motif.id === "mise_en_relation"
                            ? t({ en: "Nothing after: the transfer starts.", fr: "Rien ensuite : le transfert part." })
                            : t({ en: "Nothing after: the second try, then the outage mode.", fr: "Rien ensuite : la seconde tentative, puis le mode panne." })}
                    </Gris>
                </L>
            ) : (
                <L label={t(TEXTES.ensuite)} nom="ensuite" aide={estSilence ? t({ en: "At the silence that follows the last prompt.", fr: "Au silence qui suit la dernière relance." }) : undefined}>
                    <div className="w-full space-y-2">
                        <div className="flex flex-wrap items-start gap-2">
                            <span className="pt-2 text-sm">{t(TEXTES.dire)}</span>
                            <div className="min-w-[16rem] flex-1">
                                <ListeDePhrases valeurs={regle.ensuite?.phrases ?? []} onChange={(phrases) => majSortie({ phrases })} idPrefixe="phrase_sortie" libelleCase={t({ en: "Exit sentence", fr: "Phrase de sortie" })} />
                            </div>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm">{t(TEXTES.noter)}</span>
                            {env.champsFiche.length > 0 ? (
                                <Select
                                    value={regle.ensuite?.noter?.champ || "_aucun"}
                                    onValueChange={(v: string) => majSortie({ noter: v === "_aucun" ? null : { champ: v, valeur: "" } })}
                                >
                                    <SelectTrigger id="phrase_noter_champ" aria-label={t({ en: "Record field", fr: "Champ de la fiche" })} className="w-44">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="_aucun">{t(TEXTES.aucune)}</SelectItem>
                                        {env.champsFiche.map((c) => (
                                            <SelectItem key={c.nom} value={c.nom}>
                                                {c.nom}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            ) : (
                                <Input
                                    id="phrase_noter_champ"
                                    aria-label={t({ en: "Record field", fr: "Champ de la fiche" })}
                                    className="w-44"
                                    value={regle.ensuite?.noter?.champ ?? ""}
                                    onChange={(e) => majSortie({ noter: e.target.value || regle.ensuite?.noter?.valeur ? { champ: e.target.value, valeur: regle.ensuite?.noter?.valeur ?? "" } : null })}
                                />
                            )}
                            {regle.ensuite?.noter && (
                                <>
                                    <span className="text-sm">{t(TEXTES.egal)}</span>
                                    {champChoisi?.valeurs && champChoisi.valeurs.length > 0 ? (
                                        <Select value={regle.ensuite.noter.valeur || "_aucune"} onValueChange={(v: string) => majSortie({ noter: { champ: regle.ensuite!.noter!.champ, valeur: v === "_aucune" ? "" : v } })}>
                                            <SelectTrigger id="phrase_noter_valeur" aria-label={t({ en: "Value", fr: "Valeur" })} className="w-44">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="_aucune">{t(TEXTES.aucune)}</SelectItem>
                                                {champChoisi.valeurs.map((v) => (
                                                    <SelectItem key={v} value={v}>
                                                        {v}
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    ) : (
                                        <Input
                                            id="phrase_noter_valeur"
                                            aria-label={t({ en: "Value", fr: "Valeur" })}
                                            className="w-44"
                                            value={regle.ensuite.noter.valeur}
                                            onChange={(e) => majSortie({ noter: { champ: regle.ensuite!.noter!.champ, valeur: e.target.value } })}
                                        />
                                    )}
                                </>
                            )}
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm">{t(TEXTES.puis)}</span>
                            <Select value={sortieAction || "_defaut"} onValueChange={(v: string) => majSortie({ action: v === "_defaut" ? null : (v as Action), destination: v === "transferer" ? regle.ensuite?.destination : null })}>
                                <SelectTrigger id="phrase_sortie_action" aria-label={t(TEXTES.puis)} className="w-56">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="_defaut">{`${t({ en: "As before", fr: "Comme avant" })} (${t(nomDeLAction(motif.sortie_defaut)).toLowerCase()})`}</SelectItem>
                                    {sortiesPermises.map((a) => (
                                        <SelectItem key={a} value={a}>
                                            {t(nomDeLAction(a))}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                            {sortieAction === "transferer" &&
                                (env.equipe.length > 0 ? (
                                    <Select value={regle.ensuite?.destination || "_aucune"} onValueChange={(v: string) => majSortie({ destination: v === "_aucune" ? null : v })}>
                                        <SelectTrigger id="phrase_sortie_destination" aria-label={t(TEXTES.destination)} className="w-48">
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="_aucune">{t(TEXTES.aucune)}</SelectItem>
                                            {env.equipe.map((p) => (
                                                <SelectItem key={p.cle} value={p.cle}>
                                                    {p.nom || p.cle}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                ) : (
                                    <Input
                                        id="phrase_sortie_destination"
                                        aria-label={t(TEXTES.destination)}
                                        placeholder={t(TEXTES.cleDeLEquipe)}
                                        className="w-48"
                                        value={regle.ensuite?.destination ?? ""}
                                        onChange={(e) => majSortie({ destination: e.target.value })}
                                    />
                                ))}
                        </div>
                    </div>
                </L>
            )}
            {fin && (
                <L label="" nom="fin-d-attente">
                    <Gris>
                        {t({ en: "End of the wait:", fr: "Fin de l'attente :" })} {t(motif.fin_d_attente)}
                    </Gris>
                </L>
            )}
            <div className="rounded-md border bg-muted/30 p-3" data-apercu-phrase>
                <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
                    <Timer className="h-4 w-4" /> {t(TEXTES.apercu)}
                </div>
                <ol className="space-y-1.5">
                    {apercu.lignes.map((ligne, i) => (
                        <li key={i} className="grid grid-cols-[72px_1fr] gap-2 text-sm" data-ligne-apercu>
                            <span className="pt-0.5 font-mono text-xs text-muted-foreground">{ligne.quand}</span>
                            <span className={ligne.sortie || ligne.jamais ? "text-muted-foreground" : ""} style={ligne.jamais ? { textDecoration: "line-through" } : undefined}>
                                {ligne.texte}
                            </span>
                        </li>
                    ))}
                </ol>
                {apercu.alertes.map((a) => (
                    <p key={a} className="mt-2 rounded border border-(--signal-warn) bg-(--signal-warn)/10 px-2 py-1 text-xs" data-alerte-phrase>
                        ⚠ {a}
                    </p>
                ))}
                <p className="mt-2 text-xs text-muted-foreground">
                    {t(TEXTES.siEteinte)} {apercu.eteinte}.
                </p>
            </div>
        </div>
    );
};

export const ModaleRegle = ({
    regle: initiale,
    env,
    nouvelle = false,
    peutSupprimer = false,
    existeUneRegleDuGroupe,
    onEnregistrer,
    onSupprimer,
    onFermer,
    onRetour,
}: {
    regle: ReglePhrase;
    env: EnvironnementPhrases;
    nouvelle?: boolean;
    peutSupprimer?: boolean;
    existeUneRegleDuGroupe?: boolean;
    onEnregistrer: (r: ReglePhrase) => void;
    onSupprimer?: () => void;
    onFermer: () => void;
    onRetour?: () => void;
}) => {
    const { t } = useLangue();
    const [regle, setRegle] = useState<ReglePhrase>(() => normaliserRegle(initiale));
    const motif = motifDe(regle.motif);
    const erreurs = erreursDeLaRegle(regle, env.etapes);
    const nom = motif ? t(motif.libelle).toLowerCase() : regle.motif;
    return (
        <CadreModale
            identifiant={nouvelle ? "ajout" : "modifier"}
            titre={`${nouvelle ? t({ en: "New sentence", fr: "Nouvelle phrase" }) : t({ en: "Edit the sentence", fr: "Modifier la phrase" })} : ${nom}`}
            description={
                nouvelle
                    ? t({
                          en: "Step 2 of 2: the values offered are the catalogue's, adapt them. A box that does not apply to the cause is replaced by a grey line.",
                          fr: "Étape 2 sur 2 : les valeurs proposées sont celles du catalogue, adaptez-les. Une case qui ne s'applique pas au motif est remplacée par une ligne grise.",
                      })
                    : t({
                          en: "The sentence reads from top to bottom; a box that does not apply to the cause is replaced by a grey line.",
                          fr: "La phrase se lit de haut en bas ; une case qui ne s'applique pas au motif est remplacée par une ligne grise.",
                      })
            }
            onFermer={onFermer}
            pied={
                <>
                    <div className="flex flex-col gap-2">
                        {erreurs.length > 0 && (
                            <div className="text-xs text-destructive" role="alert" data-erreurs-phrase>
                                <span className="font-medium">{t(TEXTES.aCorriger)}</span>
                                <ul className="list-disc pl-4">
                                    {erreurs.map((e, i) => (
                                        <li key={i}>{t(e)}</li>
                                    ))}
                                </ul>
                            </div>
                        )}
                        <div className="flex items-center gap-4">
                            <label className="flex items-center gap-2 text-sm">
                                <Switch id="phrase_active" aria-label={t(TEXTES.activee)} checked={regle.active !== false} onCheckedChange={(active) => setRegle({ ...regle, active })} />
                                {regle.active !== false ? t(TEXTES.activee) : t(TEXTES.eteinte)}
                            </label>
                            {nouvelle && onRetour && (
                                <Button variant="ghost" size="sm" onClick={onRetour}>
                                    {t(TEXTES.changerMotif)}
                                </Button>
                            )}
                        </div>
                    </div>
                    <div className="flex gap-2">
                        {peutSupprimer && onSupprimer && (
                            <Button variant="ghost" className="text-destructive" onClick={onSupprimer}>
                                {t(TEXTES.supprimer)}
                            </Button>
                        )}
                        <Button variant="outline" onClick={onFermer}>
                            {t(TEXTES.annuler)}
                        </Button>
                        <Button disabled={erreurs.length > 0} onClick={() => onEnregistrer(regle)}>
                            {nouvelle ? t(TEXTES.ajouter) : t(TEXTES.enregistrer)}
                        </Button>
                    </div>
                </>
            }
        >
            <FormulaireRegle regle={regle} onChange={setRegle} env={env} existeUneRegleDuGroupe={existeUneRegleDuGroupe} />
        </CadreModale>
    );
};

