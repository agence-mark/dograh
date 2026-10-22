"use client";

/**
 * [.mark] Chantier voix-soniox, lot 7 (D2, D26) : le choix de la voix Soniox, en CARTE cliquable qui ouvre une MODALE
 * centree (le design des phrases du code, jamais un panneau lateral).
 *
 * La carte montre la voix retenue ; la modale propose les voix que le produit connait (filtre « francais », recherche,
 * description, accent, genre) et une SAISIE LIBRE pour une voix absente de la liste ou une voix clonee du projet.
 *
 * ⛔ Honnetete sur la liste : le produit ne connait que les voix relevees chez Soniox (les 11 francaises, le 21/10/2026),
 * pas les quelque 200 du catalogue. La modale le dit, avec la date du releve, et renvoie a la saisie libre. Aucun
 * « 200 voix » n'est promis a l'ecran.
 *
 * La modale travaille sur une COPIE (Annuler / Choisir) : rien n'est ecrit dans le formulaire avant « Choisir ».
 * La liste vient du schema (`mark_voix`, `mark_voix_releve`) : aucune voix n'est ecrite ici.
 */
import { ChevronRight, Info, Search, Volume2 } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

import { useLangue } from "../langue/langue";
import { CadreModale } from "../reglages-agent/phrases/cadre";

/** Une voix connue du produit, telle que le schema la declare (`null` = non releve, jamais invente). */
export interface VoixConnue {
    id: string;
    francais?: boolean;
    accent?: string | null;
    genre?: string | null;
    description?: string | null;
}

const normaliser = (texte: string) =>
    texte
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "")
        .toLowerCase();

const Pastilles = ({ voix }: { voix: VoixConnue }) => {
    const { t } = useLangue();
    return (
        <>
            {voix.francais && (
                <Badge variant="outline" className="text-[11px] font-normal">
                    {t({ en: "French", fr: "Français" })}
                </Badge>
            )}
            {voix.accent && (
                <Badge variant="outline" className="text-[11px] font-normal">
                    {voix.accent}
                </Badge>
            )}
            {voix.genre && (
                <Badge variant="outline" className="text-[11px] font-normal">
                    {voix.genre}
                </Badge>
            )}
        </>
    );
};

const ModaleDesVoix = ({
    idChamp,
    valeur,
    voix,
    releve,
    onChoisir,
    onFermer,
}: {
    idChamp: string;
    valeur: string;
    voix: VoixConnue[];
    releve?: string;
    onChoisir: (id: string) => void;
    onFermer: () => void;
}) => {
    const { t } = useLangue();
    const [copie, setCopie] = useState(valeur);
    const [recherche, setRecherche] = useState("");
    const [seulementFrancais, setSeulementFrancais] = useState(true);

    const visibles = useMemo(() => {
        const motif = normaliser(recherche.trim());
        return voix.filter((v) => {
            if (seulementFrancais && !v.francais) return false;
            if (!motif) return true;
            return normaliser([v.id, v.accent, v.genre, v.description].filter(Boolean).join(" ")).includes(motif);
        });
    }, [voix, recherche, seulementFrancais]);

    const dansLaListe = voix.some((v) => v.id === copie);
    const choix = copie.trim();

    return (
        <CadreModale
            identifiant="voix"
            titre={t({ en: "Choose the voice", fr: "Choisir la voix" })}
            description={t({
                en: "The voices the product knows. Any other voice, or a voice cloned in your Soniox project, is typed at the bottom.",
                fr: "Les voix que le produit connaît. Une autre voix, ou une voix clonée dans votre projet Soniox, se saisit en bas.",
            })}
            onFermer={onFermer}
            pied={
                <>
                    <span className="text-xs text-muted-foreground" data-voix-choisie>
                        {choix ? (
                            <>
                                {t({ en: "Chosen:", fr: "Choisie :" })} <code className="text-[11px]">{choix}</code>
                            </>
                        ) : (
                            t({ en: "No voice chosen.", fr: "Aucune voix choisie." })
                        )}
                    </span>
                    <div className="flex gap-2">
                        <Button type="button" variant="outline" onClick={onFermer}>
                            {t({ en: "Cancel", fr: "Annuler" })}
                        </Button>
                        <Button
                            type="button"
                            disabled={!choix}
                            onClick={() => {
                                onChoisir(choix);
                                onFermer();
                            }}
                        >
                            {t({ en: "Use this voice", fr: "Prendre cette voix" })}
                        </Button>
                    </div>
                </>
            }
        >
            <div className="space-y-4">
                <div className="flex items-start gap-2 rounded-lg border bg-muted/30 p-3 text-xs text-muted-foreground" data-notice-voix>
                    <Info className="mt-0.5 h-4 w-4 shrink-0" />
                    <p>
                        {t({
                            en: `This list holds ${voix.length} voices, the French ones taken from Soniox${releve ? ` on ${releve}` : ""}. Soniox offers about 200 in all: for another one, type its identifier below.`,
                            fr: `Cette liste compte ${voix.length} voix, les françaises, relevées chez Soniox${releve ? ` le ${releve}` : ""}. Soniox en propose environ 200 : pour une autre, saisissez son identifiant en bas.`,
                        })}
                    </p>
                </div>

                <div className="flex flex-wrap items-center gap-3">
                    <div className="relative min-w-48 flex-1">
                        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                        <Input
                            id={`${idChamp}-recherche`}
                            className="pl-9"
                            value={recherche}
                            onChange={(e) => setRecherche(e.target.value)}
                            placeholder={t({ en: "Search a voice", fr: "Rechercher une voix" })}
                            aria-label={t({ en: "Search a voice", fr: "Rechercher une voix" })}
                        />
                    </div>
                    <label className="flex items-center gap-2 text-sm" htmlFor={`${idChamp}-francais`}>
                        <Switch id={`${idChamp}-francais`} checked={seulementFrancais} onCheckedChange={setSeulementFrancais} />
                        {t({ en: "French only", fr: "Français seulement" })}
                    </label>
                </div>

                <div role="listbox" aria-label={t({ en: "Known voices", fr: "Voix connues" })} className="space-y-2" data-liste-voix>
                    {visibles.length === 0 && (
                        <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                            {t({ en: "No known voice matches. Type its identifier below.", fr: "Aucune voix connue ne correspond. Saisissez son identifiant en bas." })}
                        </p>
                    )}
                    {visibles.map((v) => {
                        const choisie = v.id === copie;
                        return (
                            <div
                                key={v.id}
                                role="option"
                                aria-selected={choisie}
                                tabIndex={0}
                                data-voix={v.id}
                                onClick={() => setCopie(v.id)}
                                onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), setCopie(v.id))}
                                className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition hover:border-foreground/30 ${
                                    choisie ? "border-(--acc-fill) bg-(--acc-soft)" : "bg-card"
                                }`}
                            >
                                <div className="min-w-0 flex-1 space-y-1">
                                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                                        <span className="text-sm font-semibold">{v.id}</span>
                                        <Pastilles voix={v} />
                                    </div>
                                    {v.description && <p className="text-xs text-muted-foreground">{v.description}</p>}
                                </div>
                                {choisie && <span className="text-xs font-medium">{t({ en: "Chosen", fr: "Choisie" })}</span>}
                            </div>
                        );
                    })}
                </div>

                <div className="space-y-2 border-t pt-4">
                    <label htmlFor={`${idChamp}-saisie-libre`} className="text-sm font-medium">
                        {t({ en: "Voice not in the list, or cloned voice", fr: "Voix absente de la liste, ou voix clonée" })}
                    </label>
                    <Input
                        id={`${idChamp}-saisie-libre`}
                        value={dansLaListe ? "" : copie}
                        onChange={(e) => setCopie(e.target.value)}
                        placeholder={t({ en: "Voice identifier", fr: "Identifiant de la voix" })}
                    />
                    <p className="text-xs text-muted-foreground">
                        {t({
                            en: "The identifier as Soniox gives it (the name of a catalogue voice, or the identifier of a voice cloned in the project that owns the key). It is not checked here: a wrong one fails when the call starts.",
                            fr: "L'identifiant tel que Soniox le donne (le nom d'une voix du catalogue, ou l'identifiant d'une voix clonée dans le projet qui détient la clé). Il n'est pas vérifié ici : un identifiant faux échoue au début de l'appel.",
                        })}
                    </p>
                </div>
            </div>
        </CadreModale>
    );
};

export const CarteDesVoix = ({
    idChamp,
    valeur,
    voix,
    releve,
    onChoisir,
}: {
    /** `${service}_${champ}` : l'identifiant du champ du formulaire. */
    idChamp: string;
    valeur: string;
    voix: VoixConnue[];
    releve?: string;
    onChoisir: (id: string) => void;
}) => {
    const { t } = useLangue();
    const [ouverte, setOuverte] = useState(false);
    const connue = voix.find((v) => v.id === valeur);
    const ouvrir = () => setOuverte(true);
    return (
        <>
            <div
                role="button"
                tabIndex={0}
                id={idChamp}
                aria-label={t({ en: `Voice: ${valeur || "none"}. Change it`, fr: `Voix : ${valeur || "aucune"}. La changer` })}
                onClick={ouvrir}
                onKeyDown={(e) => e.key === "Enter" && ouvrir()}
                data-carte-voix={idChamp}
                className="group flex cursor-pointer items-stretch gap-4 rounded-lg border bg-card p-4 transition hover:border-foreground/30 hover:shadow-sm"
            >
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-(--acc-soft) text-(--acc-text)">
                    <Volume2 className="h-4 w-4" />
                </span>
                <div className="min-w-0 flex-1 space-y-1.5">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span className="text-sm font-semibold" data-voix-retenue>
                            {valeur || t({ en: "No voice chosen", fr: "Aucune voix choisie" })}
                        </span>
                        {connue ? (
                            <Pastilles voix={connue} />
                        ) : (
                            valeur && (
                                <Badge variant="outline" className="text-[11px] font-normal">
                                    {t({ en: "Typed by hand", fr: "Saisie à la main" })}
                                </Badge>
                            )
                        )}
                    </div>
                    <p className="text-xs text-muted-foreground">
                        {connue?.description ??
                            (valeur
                                ? t({ en: "Not in the list of the product: a voice typed by hand, or cloned.", fr: "Absente de la liste du produit : une voix saisie à la main, ou clonée." })
                                : t({ en: "Open the list to choose one.", fr: "Ouvrez la liste pour en choisir une." }))}
                    </p>
                </div>
                <div className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
                    {t({ en: "Change", fr: "Changer" })}
                    <ChevronRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
                </div>
            </div>
            {ouverte && (
                <ModaleDesVoix idChamp={idChamp} valeur={valeur} voix={voix} releve={releve} onChoisir={onChoisir} onFermer={() => setOuverte(false)} />
            )}
        </>
    );
};
