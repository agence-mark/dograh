"use client";

/**
 * [.mark] The tool type « Integration » (chantier l-agent-travaille, L5; plan connecteurs-agent
 * steps 2 and 3): an action of a connector of the catalogue, done during the call in the client's
 * software through the installation's Nango.
 *
 * - ``ChoixAction``: the connector and the action (creation dialog and tool page);
 * - ``ConfigOutilIntegration``: the whole tool (the client's rules, deadline, phrases, anticipation);
 * - ``BlocConnexions``: this organization's connections, and the authorization link to send the
 *   client (tool page and theme « Integrations » of the Platform Settings).
 *
 * The organization is never chosen here: the server takes the signed-in user's (D6).
 */
import { Copy, Link2, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { BuiltinToolConfig } from "@/app/tools/[toolUuid]/components";
import type { ConnecteurVue } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

import { ChampReglage } from "../ecran/ChampReglage";
import { useLangue } from "../langue/langue";
import { type ConfigIntegration, configParDefaut, type Connecteurs, DELAI_DEFAUT_MS, useConnecteurs } from "./useConnecteurs";

const actionDe = (catalogue: ConnecteurVue[], config: ConfigIntegration) =>
    catalogue.find((c) => c.nom === config.connecteur)?.actions.find((a) => a.nom === config.action);

export function ChoixAction({
    catalogue,
    valeur,
    onChange,
}: {
    catalogue: ConnecteurVue[];
    valeur: ConfigIntegration;
    onChange: (valeur: ConfigIntegration) => void;
}) {
    const { t } = useLangue();
    const connecteur = catalogue.find((c) => c.nom === valeur.connecteur);
    const action = actionDe(catalogue, valeur);
    return (
        <div className="grid gap-3 sm:grid-cols-2">
            <label className="grid gap-1 text-sm">
                <span>{t({ en: "Software", fr: "Logiciel" })}</span>
                <Select
                    value={valeur.connecteur}
                    onValueChange={(nom) => {
                        const nouveau = configParDefaut(catalogue, nom);
                        if (nouveau) onChange(nouveau);
                    }}
                >
                    <SelectTrigger id="integration-connecteur">
                        <SelectValue placeholder={t({ en: "Choose the software", fr: "Choisir le logiciel" })} />
                    </SelectTrigger>
                    <SelectContent>
                        {catalogue.map((c) => (
                            <SelectItem key={c.nom} value={c.nom}>
                                {c.libelle}
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
            </label>
            <label className="grid gap-1 text-sm">
                <span>{t({ en: "Action", fr: "Action" })}</span>
                <Select
                    value={valeur.action}
                    onValueChange={(nom) => {
                        const nouveau = configParDefaut(catalogue, valeur.connecteur, nom);
                        if (nouveau) onChange({ ...nouveau, delai_ms: valeur.delai_ms, phrase_attente: valeur.phrase_attente, phrase_repli: valeur.phrase_repli });
                    }}
                >
                    <SelectTrigger id="integration-action">
                        <SelectValue placeholder={t({ en: "Choose the action", fr: "Choisir l'action" })} />
                    </SelectTrigger>
                    <SelectContent>
                        {(connecteur?.actions ?? []).map((a) => (
                            <SelectItem key={a.nom} value={a.nom}>
                                {a.nom}
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
            </label>
            {action && (
                <p className="text-xs text-muted-foreground sm:col-span-2">
                    {action.description}{" "}
                    {action.ecrit
                        ? t({ en: "It writes in the software: never anticipated, put aside for after the call if it fails.", fr: "Elle écrit dans le logiciel : jamais anticipée, mise de côté pour l'après-appel si elle échoue." })
                        : t({ en: "It only reads.", fr: "Elle ne fait que lire." })}
                </p>
            )}
        </div>
    );
}

/** The client's rules as JSON text; null when it is not an object. */
export const lireReglages = (texte: string): Record<string, unknown> | null => {
    if (texte.trim() === "") return {};
    try {
        const v = JSON.parse(texte);
        return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
    } catch {
        return null;
    }
};

export function ConfigOutilIntegration({
    connecteurs,
    valeur,
    onChange,
    onValide,
}: {
    connecteurs: Connecteurs;
    valeur: ConfigIntegration;
    onChange: (valeur: ConfigIntegration) => void;
    /** False while the rules typed are not valid JSON: the page keeps « Save » asleep. */
    onValide: (valide: boolean) => void;
}) {
    const { t } = useLangue();
    const catalogue = connecteurs.catalogue ?? [];
    const action = actionDe(catalogue, valeur);
    const [texteReglages, setTexteReglages] = useState(JSON.stringify(valeur.reglages ?? {}, null, 2));
    const cleAction = `${valeur.connecteur}/${valeur.action}`;
    useEffect(() => {
        setTexteReglages(JSON.stringify(valeur.reglages ?? {}, null, 2));
        // Only when the action changes: the text typed stays while it is being typed.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [cleAction]);
    const reglagesLus = lireReglages(texteReglages);
    useEffect(() => onValide(reglagesLus !== null), [reglagesLus, onValide]);

    const poser = (partiel: Partial<ConfigIntegration>) => onChange({ ...valeur, ...partiel });
    const declencheurs = valeur.declencheurs ?? {};

    if (connecteurs.erreur) return <p className="text-sm text-destructive">{connecteurs.erreur}</p>;
    if (!connecteurs.catalogue) return <p className="text-sm text-muted-foreground">{t({ en: "Loading…", fr: "Chargement…" })}</p>;

    return (
        <div className="space-y-5">
            <ChoixAction catalogue={catalogue} valeur={valeur} onChange={onChange} />

            <ChampReglage
                cle="config.reglages"
                idControle="integration-reglages"
                libelle={{ en: "The client's rules", fr: "Les règles du client" }}
                aides={[
                    {
                        en: "From the audit, as JSON: for the slots, the duration by reason (keys are words of the reason separated by « | », in minutes), the opening hours by weekday (0 is Monday), the notice in hours, the number of slots proposed, the calendar.",
                        fr: "Issues de l'audit, en JSON : pour les créneaux, la durée par motif (clés = mots du motif séparés par « | », en minutes), les horaires par jour (0 = lundi), le délai minimal en heures, le nombre de créneaux proposés, l'agenda.",
                    },
                ]}
            >
                <Textarea
                    id="integration-reglages"
                    className="font-mono text-xs"
                    rows={8}
                    value={texteReglages}
                    onChange={(e) => {
                        setTexteReglages(e.target.value);
                        const lus = lireReglages(e.target.value);
                        if (lus) poser({ reglages: lus });
                    }}
                />
                {reglagesLus === null && (
                    <p className="text-xs text-destructive">{t({ en: "Not valid JSON: the tool cannot be saved.", fr: "JSON invalide : l'outil ne peut pas être enregistré." })}</p>
                )}
            </ChampReglage>

            <ChampReglage
                cle="config.delai_ms"
                idControle="integration-delai"
                libelle={{ en: "Deadline during the call", fr: "Délai pendant l'appel" }}
                aides={[{ en: "Past it, the fallback phrase is said and the call goes on.", fr: "Au-delà, la phrase de repli est dite et l'appel continue." }]}
                bornes={{ en: "500 to 15,000 ms · default 5,000", fr: "500 à 15 000 ms · défaut 5 000" }}
            >
                <Input
                    id="integration-delai"
                    type="number"
                    min={500}
                    max={15000}
                    step={100}
                    value={valeur.delai_ms ?? DELAI_DEFAUT_MS}
                    onChange={(e) => poser({ delai_ms: Number(e.target.value) || DELAI_DEFAUT_MS })}
                />
            </ChampReglage>

            <ChampReglage
                cle="config.phrase_attente"
                idControle="integration-phrase-attente"
                libelle={{ en: "Waiting phrase", fr: "Phrase d'attente" }}
                aides={[{ en: "Said while the action runs. Empty: nothing is said.", fr: "Dite pendant que l'action tourne. Vide : rien n'est dit." }]}
            >
                <Input
                    id="integration-phrase-attente"
                    value={valeur.phrase_attente ?? ""}
                    placeholder={t({ en: "One moment, I am looking at the calendar.", fr: "Un instant, je regarde l'agenda." })}
                    onChange={(e) => poser({ phrase_attente: e.target.value.trim() === "" ? null : e.target.value })}
                />
            </ChampReglage>

            <ChampReglage
                cle="config.phrase_repli"
                idControle="integration-phrase-repli"
                libelle={{ en: "Fallback phrase", fr: "Phrase de repli" }}
                aides={[
                    {
                        en: "Said when the deadline passes or the software fails, never a blank. Empty: « I am passing your request on, you will be called back very soon. »",
                        fr: "Dite quand le délai passe ou que le logiciel échoue, jamais un blanc. Vide : « Je transmets votre demande, on vous rappelle très vite. »",
                    },
                ]}
            >
                <Input
                    id="integration-phrase-repli"
                    value={valeur.phrase_repli ?? ""}
                    placeholder={t({ en: "I am passing your request on, you will be called back very soon.", fr: "Je transmets votre demande, on vous rappelle très vite." })}
                    onChange={(e) => poser({ phrase_repli: e.target.value.trim() === "" ? null : e.target.value })}
                />
            </ChampReglage>

            <ChampReglage
                cle="config.anticipable"
                idControle="integration-anticipable"
                libelle={{ en: "Anticipate", fr: "Anticiper" }}
                aides={[
                    {
                        en: "Launched as soon as its fields are in the record, before the model asks: no wait. Read-only actions only; the result is thrown away if the model asks with other values.",
                        fr: "Lancée dès que ses champs sont dans la fiche, avant que le modèle la demande : aucune attente. Actions de lecture seulement ; le résultat est jeté si le modèle demande d'autres valeurs.",
                    },
                ]}
                bornes={{ en: "Default: off", fr: "Par défaut : éteint" }}
                disposition="ligne"
            >
                <Switch
                    id="integration-anticipable"
                    disabled={!action?.anticipable_permis}
                    checked={Boolean(valeur.anticipable) && Boolean(action?.anticipable_permis)}
                    onCheckedChange={(anticipable) => poser({ anticipable, declencheurs: anticipable ? declencheurs : {} })}
                />
            </ChampReglage>
            {valeur.anticipable && action?.anticipable_permis && (
                <ChampReglage
                    cle="config.declencheurs"
                    libelle={{ en: "Record field of each parameter", fr: "Champ de la fiche de chaque paramètre" }}
                    aides={[{ en: "Empty: the parameter is not read from the record. The action starts once every field filled here is known.", fr: "Vide : le paramètre n'est pas lu dans la fiche. L'action part dès que tous les champs remplis ici sont connus." }]}
                >
                    <div className="grid gap-2 sm:grid-cols-2">
                        {action.parametres.map((p) => (
                            <label key={p.nom} className="space-y-0.5 text-xs text-muted-foreground">
                                <code>{p.nom}</code>
                                <Input
                                    id={`integration-declencheur-${p.nom}`}
                                    value={declencheurs[p.nom] ?? ""}
                                    placeholder={p.nom}
                                    onChange={(e) => {
                                        const suivant = { ...declencheurs };
                                        if (e.target.value.trim() === "") delete suivant[p.nom];
                                        else suivant[p.nom] = e.target.value.trim();
                                        poser({ declencheurs: suivant });
                                    }}
                                />
                            </label>
                        ))}
                    </div>
                </ChampReglage>
            )}

            <BlocConnexions connecteurs={connecteurs} seulement={valeur.connecteur} />
        </div>
    );
}

export function BlocConnexions({ connecteurs, seulement }: { connecteurs: Connecteurs; seulement?: string }) {
    const { t } = useLangue();
    const [lien, setLien] = useState<{ connecteur: string; url: string } | null>(null);
    const [enCours, setEnCours] = useState<string | null>(null);
    const catalogue = (connecteurs.catalogue ?? []).filter((c) => !seulement || c.nom === seulement);
    const etat = connecteurs.etat;

    if (!etat) return null;
    if (!etat.nango_configure)
        return (
            <p className="text-sm text-muted-foreground" id="connexions-nango-absent">
                {t({
                    en: "No Nango on this installation (NANGO_URL, NANGO_SECRET_KEY): the integration tools fall back to their phrase.",
                    fr: "Pas de Nango sur cette installation (NANGO_URL, NANGO_SECRET_KEY) : les outils d'intégration disent leur phrase de repli.",
                })}
            </p>
        );

    const generer = async (nom: string) => {
        setEnCours(nom);
        try {
            const r = await connecteurs.demanderLien([nom]);
            if (r.lien) setLien({ connecteur: nom, url: r.lien });
        } catch (e) {
            toast.error(e instanceof Error ? e.message : t({ en: "No authorization link", fr: "Pas de lien d'autorisation" }));
        } finally {
            setEnCours(null);
        }
    };

    return (
        <div className="space-y-2" id="connexions-organisation">
            {etat.erreur && <p className="text-sm text-destructive">{etat.erreur}</p>}
            {catalogue.map((c) => {
                const connexion = (etat.connexions ?? []).find((x) => x.integration === c.integration);
                return (
                    <div key={c.nom} className="flex flex-wrap items-center gap-3 rounded-md border bg-(--surface) p-3 text-sm">
                        <span className="font-medium">{c.libelle}</span>
                        {connexion ? (
                            <span className="text-(--signal-ok)">
                                {t({ en: "Connected", fr: "Connecté" })}
                                {connexion.erreurs ? ` · ${connexion.erreurs} ${t({ en: "error(s)", fr: "erreur(s)" })}` : ""}
                            </span>
                        ) : (
                            <span className="text-(--signal-warn)">{t({ en: "Not connected", fr: "Non connecté" })}</span>
                        )}
                        <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="ml-auto"
                            disabled={enCours === c.nom}
                            onClick={() => void generer(c.nom)}
                        >
                            <Link2 className="mr-2 h-3.5 w-3.5" />
                            {connexion
                                ? t({ en: "New authorization link", fr: "Nouveau lien d'autorisation" })
                                : t({ en: "Authorization link for the client", fr: "Lien d'autorisation pour le client" })}
                        </Button>
                        {lien?.connecteur === c.nom && (
                            <div className="flex w-full items-center gap-2">
                                <Input readOnly value={lien.url} id={`lien-autorisation-${c.nom}`} className="font-mono text-xs" />
                                <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    aria-label={t({ en: "Copy the link", fr: "Copier le lien" })}
                                    onClick={() => {
                                        void navigator.clipboard?.writeText(lien.url);
                                        toast.success(t({ en: "Link copied", fr: "Lien copié" }));
                                    }}
                                >
                                    <Copy className="h-3.5 w-3.5" />
                                </Button>
                            </div>
                        )}
                    </div>
                );
            })}
            <Button type="button" variant="ghost" size="sm" onClick={() => void connecteurs.relire()}>
                <RefreshCw className="mr-2 h-3.5 w-3.5" />
                {t({ en: "Check the connections again", fr: "Revérifier les connexions" })}
            </Button>
        </div>
    );
}

/** The creation dialog of « Tools »: the software and the action; the rest on the tool page. */
export function ChampsCreationIntegration({ onChange }: { onChange: (valeur: ConfigIntegration | null) => void }) {
    const { t } = useLangue();
    const connecteurs = useConnecteurs();
    const [valeur, setValeur] = useState<ConfigIntegration | null>(null);
    useEffect(() => {
        if (connecteurs.catalogue && valeur === null) {
            const premier = configParDefaut(connecteurs.catalogue);
            setValeur(premier);
            onChange(premier);
        }
    }, [connecteurs.catalogue, valeur, onChange]);
    if (connecteurs.erreur) return <p className="text-sm text-destructive">{connecteurs.erreur}</p>;
    if (!connecteurs.catalogue || !valeur) return <p className="text-sm text-muted-foreground">{t({ en: "Loading…", fr: "Chargement…" })}</p>;
    return (
        <ChoixAction
            catalogue={connecteurs.catalogue}
            valeur={valeur}
            onChange={(v) => {
                setValeur(v);
                onChange(v);
            }}
        />
    );
}

/** The name and description card of the tool page, its texts in two languages. */
export function EnteteOutilIntegration(props: {
    name: string;
    onNameChange: (v: string) => void;
    description: string;
    onDescriptionChange: (v: string) => void;
}) {
    const { t } = useLangue();
    return (
        <BuiltinToolConfig
            {...props}
            title={t({ en: "Integration Configuration", fr: "Configuration de l'intégration" })}
            subtitle={t({
                en: "An action in the client's software, done during the call. Empty description: the action's own.",
                fr: "Une action dans le logiciel du client, faite pendant l'appel. Description vide : celle de l'action.",
            })}
        />
    );
}
