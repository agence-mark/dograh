"use client";

/**
 * [.mark] Chantier fiabilite-orchestration, lot 4 (F20, F26, C5): the model guard and the fallback brain.
 *
 * - `delai_garde_modele_s`: past this delay without the model's first words, the code says its
 *   « the model is slow » sentence (theme Phrases) and tries again. Armed for EVERY agent, outage mode
 *   on or not. Empty: the outage setting if any, else 4 s.
 * - `cerveau_de_repli` (and `travail_llm_repli` for the background brain): where the second try goes.
 *   A TROUBLESHOOTING tool, never part of a standard setup (F26): none by default, presented as such.
 */
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { GreffierLlm, WorkflowConfigurations } from "@/types/workflow-configurations";

import { attributsDeBorne, texteHorsBornes } from "../bornes-reglages";
import { ChampReglage, texteBornes } from "../ecran/ChampReglage";
import { Intertitre } from "../ecran/Intertitre";
import { type Texte, useLangue } from "../langue/langue";
import { type BlocModele, ChampsFournisseurLlm } from "../modeles/ChampsFournisseurLlm";
import { type Enregistrer, RAPPEL_PUBLICATION_TEXTE } from "./enregistrement";

export const DELAI_DE_GARDE_PAR_DEFAUT_S = 4;

type CleDeRepli = "cerveau_de_repli" | "travail_llm_repli";

/** One fallback brain: a summary line, a dialog with the provider's generated form, a remove button. */
export function CerveauDeRepli({
    cle,
    idPrefixe,
    libelle,
    enregistre,
    enregistrer,
    desactive,
    bouton = { en: "Configure the fallback brain", fr: "Régler le cerveau de repli" },
}: {
    bouton?: Texte;
    cle: CleDeRepli;
    idPrefixe: string;
    libelle: Texte;
    enregistre: GreffierLlm | null;
    enregistrer: (patch: Partial<WorkflowConfigurations>, message: Texte) => Promise<void>;
    desactive: boolean;
}) {
    const { t } = useLangue();
    const [fenetre, setFenetre] = useState(false);
    const [bloc, setBloc] = useState<BlocModele>({});
    const relu = JSON.stringify(enregistre);
    useEffect(() => setBloc((JSON.parse(relu) ?? {}) as BlocModele), [relu]);
    const regle = enregistre !== null && typeof enregistre.model === "string" && enregistre.model !== "";
    return (
        <ChampReglage
            cle={cle}
            libelle={libelle}
            aides={[
                {
                    en: "A troubleshooting tool, never part of a standard setup: none by default. When the model is past its guard delay, the second try goes to this model, with the agent's tools and record (an OpenAI-compatible provider). To get a client out of trouble fast, without touching the code.",
                    fr: "Un outil de dépannage, jamais une obligation : aucun par défaut. Quand le modèle dépasse son délai de garde, la seconde tentative part chez ce modèle, avec les outils et la fiche de l'agent (fournisseur au protocole compatible OpenAI). Pour dépanner vite un client, sans toucher au code.",
                },
            ]}
            bornes={{ en: "Default: none", fr: "Par défaut : aucun" }}
        >
            <div className="flex flex-wrap items-center justify-between gap-3 rounded border p-3 text-sm">
                <span data-repli={regle ? "regle" : "aucun"}>
                    {regle
                        ? `${String(enregistre?.provider ?? "")} · ${String(enregistre?.model ?? "")}`
                        : t({ en: "No fallback brain", fr: "Aucun cerveau de repli" })}
                </span>
                <div className="flex gap-2">
                    {regle && (
                        <Button
                            variant="outline"
                            size="sm"
                            disabled={desactive}
                            onClick={() =>
                                void enregistrer(
                                    { [cle]: null },
                                    { en: "Fallback brain removed.", fr: "Cerveau de repli retiré." },
                                )
                            }
                        >
                            {t({ en: "Remove the fallback brain", fr: "Retirer le cerveau de repli" })}
                        </Button>
                    )}
                    <Button variant="outline" size="sm" onClick={() => setFenetre(true)}>
                        {t(bouton)}
                    </Button>
                </div>
            </div>
            <Dialog open={fenetre} onOpenChange={setFenetre}>
                <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle>{t(libelle)}</DialogTitle>
                        <DialogDescription>
                            {t({
                                en: "Troubleshooting only. The second try after a guard delay goes here; the agent's prompt, tools and record stay the same.",
                                fr: "Dépannage seulement. La seconde tentative après un délai de garde part ici ; le prompt, les outils et la fiche de l'agent restent les mêmes.",
                            })}
                        </DialogDescription>
                    </DialogHeader>
                    <ChampsFournisseurLlm bloc={bloc} onChange={setBloc} idPrefixe={idPrefixe} />
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setFenetre(false)}>
                            {t({ en: "Cancel", fr: "Annuler" })}
                        </Button>
                        <Button
                            disabled={desactive}
                            onClick={() =>
                                void enregistrer(
                                    { [cle]: Object.keys(bloc).length > 0 ? (bloc as GreffierLlm) : null },
                                    { en: "Fallback brain saved.", fr: "Cerveau de repli enregistré." },
                                ).then(() => setFenetre(false))
                            }
                        >
                            {t({ en: "Save the fallback brain", fr: "Enregistrer le cerveau de repli" })}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </ChampReglage>
    );
}

export const GardeDuModele = ({
    resolue,
    workflowName,
    onSave,
}: {
    resolue: WorkflowConfigurations;
    workflowName: string;
    onSave: Enregistrer;
}) => {
    const { t } = useLangue();
    const rappel = t(RAPPEL_PUBLICATION_TEXTE);
    const [enregistrement, setEnregistrement] = useState(false);
    const enregistrer = async (patch: Partial<WorkflowConfigurations>, message: Texte) => {
        setEnregistrement(true);
        try {
            await onSave({ ...resolue, ...patch }, workflowName);
            toast.success(`${t(message)} ${rappel}`);
        } finally {
            setEnregistrement(false);
        }
    };
    const delaiEnregistre = resolue.delai_garde_modele_s ?? null;
    const [delai, setDelai] = useState(delaiEnregistre === null ? "" : String(delaiEnregistre));
    useEffect(() => setDelai(delaiEnregistre === null ? "" : String(delaiEnregistre)), [delaiEnregistre]);
    const delaiNombre = delai.trim() === "" ? null : Number(delai.replace(",", "."));
    const erreur = delaiNombre === null ? null : texteHorsBornes("delai_garde_modele_s", delaiNombre);
    const repli = useMemo(() => (resolue.cerveau_de_repli ?? null) as GreffierLlm | null, [resolue.cerveau_de_repli]);

    return (
        <Intertitre
            id="briques-garde"
            titre={{ en: "Model guard", fr: "Garde du modèle" }}
            description={{
                en: "When the model is slow to answer: a sentence said by the code, then a second try. For every agent, outage mode on or not.",
                fr: "Quand le modèle tarde à répondre : une phrase dite par le code, puis une seconde tentative. Pour tous les agents, mode panne allumé ou non.",
            }}
        >
            <ChampReglage
                cle="delai_garde_modele_s"
                idControle="delai_garde_modele_s"
                libelle={{ en: "Guard delay (s)", fr: "Délai de garde (s)" }}
                bornes={texteBornes("delai_garde_modele_s")}
                erreur={erreur}
                aides={[
                    {
                        en: "Past this delay without the model's first words, the code says the sentence of « The model is slow to answer » (theme Phrases) and tries again; with outage mode on, the second time in a row hands the call over. Empty: the outage setting if any, else 4 s.",
                        fr: "Au-delà de ce délai sans les premiers mots du modèle, le code dit la phrase de « Le modèle tarde à répondre » (thème Phrases) et réessaie ; mode panne allumé, la deuxième fois d'affilée renvoie l'appel. Vide : le réglage du mode panne s'il y en a un, sinon 4 s.",
                    },
                ]}
            >
                <div className="flex items-center gap-2">
                    <Input
                        id="delai_garde_modele_s"
                        type="number"
                        inputMode="decimal"
                        className="max-w-32"
                        placeholder={String(DELAI_DE_GARDE_PAR_DEFAUT_S)}
                        {...attributsDeBorne("delai_garde_modele_s")}
                        value={delai}
                        onChange={(e) => setDelai(e.target.value)}
                    />
                    <Button
                        variant="outline"
                        size="sm"
                        disabled={enregistrement || erreur !== null || delaiNombre === delaiEnregistre}
                        onClick={() =>
                            void enregistrer(
                                { delai_garde_modele_s: delaiNombre },
                                { en: "Guard delay saved.", fr: "Délai de garde enregistré." },
                            )
                        }
                    >
                        {t({ en: "Save the guard delay", fr: "Enregistrer le délai de garde" })}
                    </Button>
                </div>
            </ChampReglage>
            <CerveauDeRepli
                cle="cerveau_de_repli"
                idPrefixe="repli"
                libelle={{ en: "Fallback brain (troubleshooting)", fr: "Cerveau de repli (dépannage)" }}
                enregistre={repli}
                enregistrer={enregistrer}
                desactive={enregistrement}
            />
        </Intertitre>
    );
};
