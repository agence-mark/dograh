"use client";

/**
 * [.mark] C6 (chantier correctifs-banc-34): the call-record fields a pathway
 * requires before the agent may take it.
 *
 * The check runs in the code, at the moment the model takes the pathway: until
 * the record holds every field chosen here (noted and sure, a name spelled
 * letter by letter), the agent stays on its step and is told what is missing.
 * Runs 882 and 884: the "name, number and address noted" pathway was taken with
 * the name never spelled, then with no town and no street.
 *
 * ⛔ Nothing is hard-coded: the fields are the agent's own record fields,
 * chosen per pathway. Empty = no check, the pathway behaves as before.
 * A long list is never shown in one block: the fields sit in a drop-down.
 */
import { ChevronDown } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

import { useLangue } from "./langue/langue";

interface ProprietesChampsRequis {
    /** What the pathway requires today (absent = nothing). */
    valeur: string[] | undefined;
    onChange: (valeur: string[] | undefined) => void;
    /** The names of the agent's record fields. */
    champs: string[];
    /** Is the call record switched on for this agent? */
    ficheAllumee: boolean;
    readOnly?: boolean;
}

export const ChampsRequisSortie = ({ valeur, onChange, champs, ficheAllumee, readOnly = false }: ProprietesChampsRequis) => {
    const { t } = useLangue();
    const choisis = valeur ?? [];
    // A field removed from the record since: the server ignores it, the screen says so.
    const disparus = choisis.filter((nom) => !champs.includes(nom));

    const basculer = (nom: string, coche: boolean) => {
        const suivants = coche ? [...choisis.filter((c) => c !== nom), nom] : choisis.filter((c) => c !== nom);
        onChange(suivants.length ? suivants : undefined);
    };

    return (
        <div className="grid gap-2" data-reglage="champs_requis">
            <Label htmlFor="champs_requis">{t({ en: "Required record fields", fr: "Champs requis de la fiche" })}</Label>
            <Label className="text-xs text-muted-foreground">
                {t({
                    en: "The agent can take this pathway only once the call record holds these fields, noted and sure (a name spelled letter by letter). Until then it stays on its step and asks for what is missing. Empty: no check.",
                    fr: "L'agent ne peut prendre cette sortie que quand la fiche de l'appel tient ces champs, notés et sûrs (un nom épelé lettre par lettre). D'ici là, il reste à son étape et demande ce qui manque. Vide : aucune vérification.",
                })}
            </Label>
            {!ficheAllumee ? (
                <p className="text-xs text-muted-foreground" data-note="fiche-eteinte">
                    {t({
                        en: "The call record is switched off for this agent: nothing is checked.",
                        fr: "La fiche de l'appel est éteinte pour cet agent : rien n'est vérifié.",
                    })}
                </p>
            ) : (
                <Popover>
                    <PopoverTrigger asChild>
                        <Button id="champs_requis" variant="outline" className="justify-between" disabled={readOnly}>
                            <span className="truncate">{choisis.length ? choisis.join(", ") : t({ en: "None", fr: "Aucun" })}</span>
                            <ChevronDown className="h-4 w-4 opacity-60" />
                        </Button>
                    </PopoverTrigger>
                    <PopoverContent className="max-h-72 w-72 overflow-y-auto p-2">
                        {champs.length === 0 && (
                            <p className="p-1 text-xs text-muted-foreground">
                                {t({ en: "The call record has no field yet.", fr: "La fiche de l'appel n'a encore aucun champ." })}
                            </p>
                        )}
                        {champs.map((nom) => (
                            <div key={nom} className="flex items-center gap-2 rounded p-1 hover:bg-muted/50">
                                <Checkbox
                                    id={`champ_requis_${nom}`}
                                    checked={choisis.includes(nom)}
                                    onCheckedChange={(coche) => basculer(nom, coche === true)}
                                />
                                <Label htmlFor={`champ_requis_${nom}`} className="text-xs font-normal">
                                    {nom}
                                </Label>
                            </div>
                        ))}
                    </PopoverContent>
                </Popover>
            )}
            {disparus.length > 0 && (
                <p className="text-xs text-destructive" data-note="champs-disparus">
                    {t({ en: "Not in the call record any more, ignored:", fr: "Plus dans la fiche de l'appel, ignorés :" })}{" "}
                    {disparus.join(", ")}.
                </p>
            )}
        </div>
    );
};
