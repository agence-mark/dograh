"use client";

/**
 * [.mark] Chantier voix-soniox, lot 7 (D11, D21, D26) : les BALISES D'EXPRESSION PERMISES de l'agent
 * (`tts_balises_permises`), au theme « Voix », en CARTE cliquable qui ouvre une MODALE centree (le design des
 * phrases du code ; jamais un panneau lateral).
 *
 * Trois etats, que la carte nomme et que la modale propose :
 * - **par defaut** (`null`, ou cle absente) : la voix Soniox laisse passer `warm`, `calm`, `slowly`, `pause` ;
 *   toute autre voix envoie son texte tel qu'ecrit (un agent qui n'a rien allume ne change pas) ;
 * - **liste de l'agent** : seules ces balises passent, tout autre crochet est retire avant la voix ;
 * - **aucune** (`[]`) : tous les crochets sont retires.
 *
 * ⛔ La carte dit ce que fait la liste, sans rien promettre de plus : le modele ne peut pas ecrire de balise (ses
 * crochets sont retires avant la voix, D-25), seules les phrases fixes du code peuvent en porter. Aucune balise
 * n'est ecrite par le code.
 *
 * La modale travaille sur une COPIE (Annuler / Appliquer, comme les issues, E4) ; le bouton du theme enregistre.
 */
import { ChevronRight, Info, Tags } from "lucide-react";
import { useState } from "react";

import { ChampEtiquettes } from "@/components/mark/ChampEtiquettes";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";

import { type Texte, useLangue } from "../langue/langue";
import { CadreModale } from "./phrases/cadre";

/**
 * La liste par defaut de la voix Soniox (D11), sans crochets. Meme liste que `BALISES_PAR_DEFAUT`
 * (`api/services/pipecat/balises_expression.py`) : un test les compare.
 */
export const BALISES_PAR_DEFAUT: readonly string[] = ["warm", "calm", "slowly", "pause"];

/** Le maximum que le serveur accepte (`max_length` de `tts_balises_permises`). */
export const BALISES_MAX = 30;

/** Ce que le champ garde : `null` ou absent = defaut de la voix, liste vide = aucune, sinon la liste. */
export type ValeurBalises = string[] | null | undefined;

type Mode = "defaut" | "liste" | "aucune";

export const modeDesBalises = (valeur: ValeurBalises): Mode =>
    valeur === null || valeur === undefined ? "defaut" : valeur.length === 0 ? "aucune" : "liste";

/** Sans crochets, minuscules, sans doublon : la forme sous laquelle le serveur compare. */
const nommer = (valeurs: string[]): string[] => {
    const vues = new Set<string>();
    for (const brut of valeurs) {
        let nom = brut.trim();
        if (nom.startsWith("[") && nom.endsWith("]")) nom = nom.slice(1, -1);
        nom = nom.trim().toLowerCase();
        if (nom) vues.add(nom);
    }
    return [...vues];
};

const TITRE: Texte = { en: "Allowed expression tags", fr: "Balises d'expression permises" };

const LIBELLES_MODE: Record<Mode, Texte> = {
    defaut: { en: "The voice's default", fr: "Défaut de la voix" },
    liste: { en: "The agent's list", fr: "Liste de l'agent" },
    aucune: { en: "None", fr: "Aucune" },
};

const Balises = ({ noms }: { noms: readonly string[] }) => (
    <div className="flex flex-wrap gap-1.5">
        {noms.map((nom) => (
            <span key={nom} data-balise={nom} className="rounded-md bg-muted px-2 py-1 font-mono text-[13px]">
                [{nom}]
            </span>
        ))}
    </div>
);

const ModaleBalises = ({
    valeur,
    onAppliquer,
    onFermer,
}: {
    valeur: ValeurBalises;
    onAppliquer: (mode: Mode, liste: string[]) => void;
    onFermer: () => void;
}) => {
    const { t } = useLangue();
    const [mode, setMode] = useState<Mode>(modeDesBalises(valeur));
    const [liste, setListe] = useState<string[]>(Array.isArray(valeur) ? valeur : []);

    return (
        <CadreModale
            identifiant="balises"
            titre={t(TITRE)}
            description={t({
                en: "Which passages between square brackets may reach the voice. Any other is removed before it.",
                fr: "Quels passages entre crochets peuvent arriver à la voix. Tout autre est retiré avant elle.",
            })}
            onFermer={onFermer}
            pied={
                <>
                    <code className="text-[11px] text-muted-foreground">tts_balises_permises</code>
                    <div className="flex gap-2">
                        <Button type="button" variant="outline" onClick={onFermer}>
                            {t({ en: "Cancel", fr: "Annuler" })}
                        </Button>
                        <Button
                            type="button"
                            onClick={() => {
                                onAppliquer(mode, nommer(liste));
                                onFermer();
                            }}
                        >
                            {t({ en: "Apply", fr: "Appliquer" })}
                        </Button>
                    </div>
                </>
            }
        >
            <div className="space-y-5">
                <div className="flex items-start gap-2 rounded-lg border bg-muted/30 p-3 text-xs text-muted-foreground" data-notice-balises>
                    <Info className="mt-0.5 h-4 w-4 shrink-0" />
                    <div className="space-y-1">
                        <p>
                            {t({
                                en: "An expression tag is a word between square brackets, in English, that some voices read as a direction (a warm tone, a pause). A voice does not know an unknown tag and can read it aloud: that is why only the tags listed here are kept.",
                                fr: "Une balise d'expression est un mot en anglais entre crochets que certaines voix lisent comme une indication (un ton chaleureux, une pause). Une voix qui ne connaît pas une balise peut la lire à voix haute : c'est pourquoi seules les balises de la liste sont gardées.",
                            })}
                        </p>
                        <p>
                            {t({
                                en: "Under the Soniox voice the model itself may write a tag of this list; any other bracket it writes is removed before the voice, as before. The fixed sentences of the code can carry one too. Sentence by sentence only. The conversation history keeps the tags (the voice reports what it said); the transcript, the kept verbatim and the call record never show the brackets.",
                                fr: "Sous la voix Soniox, le modèle peut lui-même écrire une balise de cette liste ; tout autre crochet qu'il écrit est retiré avant la voix, comme avant. Les phrases fixes du code peuvent aussi en porter. Phrase par phrase seulement. L'historique garde les balises (la voix rapporte ce qu'elle a dit) ; la transcription, le verbatim conservé et la fiche d'appel ne montrent jamais les crochets.",
                            })}
                        </p>
                    </div>
                </div>

                <RadioGroup value={mode} onValueChange={(v) => setMode(v as Mode)} className="gap-4" aria-label={t(TITRE)}>
                    <div className="flex items-start gap-3">
                        <RadioGroupItem value="defaut" id="balises-mode-defaut" className="mt-1" />
                        <div className="space-y-1.5">
                            <Label htmlFor="balises-mode-defaut" className="text-sm font-medium">
                                {t(LIBELLES_MODE.defaut)}
                            </Label>
                            <p className="text-xs text-muted-foreground">
                                {t({
                                    en: "The Soniox voice keeps the tags below. Any other voice sends its text as written: nothing changes for an agent that set nothing.",
                                    fr: "La voix Soniox garde les balises ci-dessous. Toute autre voix envoie son texte tel qu'écrit : rien ne change pour un agent qui n'a rien réglé.",
                                })}
                            </p>
                            <Balises noms={BALISES_PAR_DEFAUT} />
                        </div>
                    </div>
                    <div className="flex items-start gap-3">
                        <RadioGroupItem value="liste" id="balises-mode-liste" className="mt-1" />
                        <div className="min-w-0 flex-1 space-y-1.5">
                            <Label htmlFor="balises-mode-liste" className="text-sm font-medium">
                                {t(LIBELLES_MODE.liste)}
                            </Label>
                            <p className="text-xs text-muted-foreground">
                                {t({
                                    en: "Only these tags pass, on any voice. Written without brackets; capitals and spaces do not matter.",
                                    fr: "Seules ces balises passent, sur toute voix. Écrites sans crochets ; majuscules et espaces sans importance.",
                                })}
                            </p>
                            <ChampEtiquettes
                                id="tts_balises_permises"
                                valeurs={liste}
                                maxElements={BALISES_MAX}
                                placeholder={t({ en: "Add a tag", fr: "Ajouter une balise" })}
                                onChange={(nouvelles) => {
                                    setListe(nommer(nouvelles));
                                    setMode("liste");
                                }}
                            />
                        </div>
                    </div>
                    <div className="flex items-start gap-3">
                        <RadioGroupItem value="aucune" id="balises-mode-aucune" className="mt-1" />
                        <div className="space-y-1.5">
                            <Label htmlFor="balises-mode-aucune" className="text-sm font-medium">
                                {t(LIBELLES_MODE.aucune)}
                            </Label>
                            <p className="text-xs text-muted-foreground">
                                {t({
                                    en: "Every bracket is removed before the voice, whatever it says.",
                                    fr: "Tous les crochets sont retirés avant la voix, quoi qu'ils disent.",
                                })}
                            </p>
                        </div>
                    </div>
                </RadioGroup>
            </div>
        </CadreModale>
    );
};

export const CarteBalises = ({
    valeur,
    onChange,
    retourAuDefaut,
    sansEffet,
}: {
    valeur: ValeurBalises;
    onChange: (valeur: ValeurBalises) => void;
    /**
     * Ce que « defaut » ecrit : `undefined` quand la cle n'etait pas enregistree (rien a envoyer, aucun
     * changement), `null` sinon.
     */
    retourAuDefaut: null | undefined;
    /** Le texte part mot a mot : la transformation n'est pas posee. */
    sansEffet?: boolean;
}) => {
    const { t } = useLangue();
    const [ouverte, setOuverte] = useState(false);
    const mode = modeDesBalises(valeur);
    const noms = mode === "liste" ? (valeur as string[]) : mode === "defaut" ? BALISES_PAR_DEFAUT : [];
    const ouvrir = () => setOuverte(true);
    return (
        <>
            <div
                role="button"
                tabIndex={0}
                aria-label={`${t(TITRE)} : ${t(LIBELLES_MODE[mode])}`}
                onClick={ouvrir}
                onKeyDown={(e) => e.key === "Enter" && ouvrir()}
                id="reglage-tts_balises_permises"
                data-reglage="tts_balises_permises"
                data-carte-balises={mode}
                className="group flex cursor-pointer items-stretch gap-4 rounded-lg border bg-card p-4 transition hover:border-foreground/30 hover:shadow-sm"
            >
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-(--acc-soft) text-(--acc-text)">
                    <Tags className="h-4 w-4" />
                </span>
                <div className="min-w-0 flex-1 space-y-2">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span className="text-sm font-semibold">{t(TITRE)}</span>
                        <code className="text-[11px] text-muted-foreground/80">tts_balises_permises</code>
                        <Badge variant="outline" className="text-[11px] font-normal">
                            {t(LIBELLES_MODE[mode])}
                        </Badge>
                    </div>
                    {noms.length > 0 ? (
                        <Balises noms={noms} />
                    ) : (
                        <p className="text-xs text-muted-foreground">{t({ en: "No tag: every bracket is removed.", fr: "Aucune balise : tous les crochets sont retirés." })}</p>
                    )}
                    <p className="text-xs text-muted-foreground">
                        {mode === "defaut"
                            ? t({
                                  en: "Soniox voice: these tags pass, any other bracket is removed. Any other voice: the text is sent as written.",
                                  fr: "Voix Soniox : ces balises passent, tout autre crochet est retiré. Autre voix : le texte part tel qu'écrit.",
                              })
                            : t({
                                  en: "Any other bracket is removed before the voice, on any voice.",
                                  fr: "Tout autre crochet est retiré avant la voix, sur toute voix.",
                              })}
                    </p>
                    {sansEffet && (
                        <p className="text-xs text-destructive" data-note="balises-sans-effet">
                            {t({
                                en: "⚠ No effect right now: the text goes to the voice word by word, and a tag would arrive in pieces. Switch back to « Sentence by sentence ».",
                                fr: "⚠️ Sans effet en ce moment : le texte part vers la voix mot par mot, et une balise arriverait en morceaux. Repassez sur « Phrase par phrase ».",
                            })}
                        </p>
                    )}
                </div>
                <div className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
                    {t({ en: "Edit", fr: "Modifier" })}
                    <ChevronRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
                </div>
            </div>
            {ouverte && (
                <ModaleBalises
                    valeur={valeur}
                    onFermer={() => setOuverte(false)}
                    onAppliquer={(modeChoisi, liste) =>
                        onChange(modeChoisi === "defaut" ? retourAuDefaut : modeChoisi === "aucune" ? [] : liste)
                    }
                />
            )}
        </>
    );
};
