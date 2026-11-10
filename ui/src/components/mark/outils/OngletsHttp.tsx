"use client";

/**
 * [.mark] U3 sexies point 2 (E74) : les onglets Requête, Paramètres et Réponse d'un outil HTTP.
 *
 * Chaque ajout vit dans `definition.config` : emplacement, valeurs permises et défaut de chaque paramètre ; en-têtes
 * texte, variable ou secret ; chemins gardés de la réponse ; copies vers la fiche ; réponses simulées (essai et banc
 * seulement). Un secret est rangé dans un identifiant chiffré de l'organisation : sa valeur ne s'affiche JAMAIS
 * (champ d'écriture seule) et la définition de l'outil n'en garde que la référence.
 */
import { useState } from "react";

import { createCredentialApiV1CredentialsPost } from "@/client/sdk.gen";
import { CredentialSelector } from "@/components/http";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { notifier } from "@/components/mark/notifications";
import { ECHECS } from "@/components/mark/notifications/phrases-echec";
import { useLangue } from "../langue/langue";
import { BlocChamp, Champs, LigneChamp, Section } from "../studio/fenetre-onglets";
import { Liste } from "../studio/liste";
import { chargeEssais, type EssaisOutil, lireEssais } from "./essais-outil";
import { EssaisOutilHttp } from "./EssaisOutilHttp";
import { LignesEditables } from "./LignesEditables";
import { type Config, liste, nombre, texte } from "./modele";
import { BlocEntetesAnciens } from "./OngletsDeType";

type Pose = (modifs: Config) => void;

const METHODES = ["GET", "POST", "PUT", "PATCH", "DELETE"];

type Entete = { nom: string; sorte: "texte" | "variable" | "secret"; valeur?: string | null; identifiant_uuid?: string | null };
type Parametre = { name: string; type: string; description: string; required?: boolean; emplacement?: string | null; valeurs_permises?: string[] | null; defaut?: unknown };
type Copie = { chemin: string; cle: string };
type Simulee = { nom?: string; quand?: Record<string, string>; statut?: number; donnees?: unknown };

/** Les en-têtes libres (texte, variable, secret) : communs à la requête HTTP et aux serveurs MCP. */
export function BlocEntetes({ config, pose }: { config: Config; pose: Pose }) {
    const { t } = useLangue();
    const [erreur, setErreur] = useState<string | null>(null);
    // Le secret tapé reste ici, jamais dans la définition de l'outil, jusqu'à ce qu'il soit rangé.
    const [saisies, setSaisies] = useState<Record<number, string>>({});
    const entetes = liste<Entete>(config, "en_tetes_ext");

    // Un secret saisi devient un identifiant chiffré ; seule sa référence entre dans l'outil.
    const rangerLeSecret = async (i: number, nom: string, valeur: string) => {
        if (!nom.trim() || !valeur) return;
        const r = await createCredentialApiV1CredentialsPost({
            body: {
                name: `${nom} (${Date.now().toString(36)})`,
                credential_type: "custom_header",
                credential_data: { header_name: nom, header_value: valeur },
            },
        });
        if (r.error || !r.data) return notifier.echec(ECHECS.identifiantCreer, { erreur: r.error });
        setErreur(null);
        notifier.succes({ fr: "Secret rangé, il ne sera plus affiché.", en: "Secret stored, it will not be shown again." });
        setSaisies((v) => ({ ...v, [i]: "" }));
        pose({ en_tetes_ext: entetes.map((e, j) => (j === i ? { nom: e.nom, sorte: "secret", identifiant_uuid: r.data!.uuid } : e)) });
    };

    return (
        <BlocChamp
                libelle={t({ en: "Headers", fr: "En-têtes" })}
                info={t({
                    en: "Text as written; variable such as {{initial_context.x}}; secret: stored encrypted, never shown again.",
                    fr: "Texte tel quel ; variable comme {{initial_context.x}} ; secret : rangé chiffré, jamais réaffiché.",
                })}
            >
                <LignesEditables<Entete>
                    colonnes={[t({ en: "Name", fr: "Nom" }), t({ en: "Kind", fr: "Sorte" }), t({ en: "Value", fr: "Valeur" })]}
                    lignes={entetes}
                    changer={(l) => pose({ en_tetes_ext: l })}
                    vide={t({ en: "No header.", fr: "Aucun en-tête." })}
                    nouvelle={() => ({ nom: "", sorte: "texte", valeur: "" })}
                    ajouter={t({ en: "Add a header", fr: "Ajouter un en-tête" })}
                    rendu={(e, maj, i) => [
                        <Input key="n" className="h-8" value={e.nom} onChange={(x) => maj({ nom: x.target.value })} aria-label={t({ en: "Header name", fr: "Nom de l'en-tête" })} />,
                        <Liste
                            key="s"
                            valeur={e.sorte}
                            changer={(v) => maj({ sorte: v as Entete["sorte"], valeur: v === "secret" ? null : e.valeur ?? "", identifiant_uuid: null })}
                            options={[
                                { valeur: "texte", libelle: t({ en: "Text", fr: "Texte" }) },
                                { valeur: "variable", libelle: t({ en: "Variable", fr: "Variable" }) },
                                { valeur: "secret", libelle: t({ en: "Secret", fr: "Secret" }) },
                            ]}
                            className="w-32"
                        />,
                        e.sorte === "secret" ? (
                            e.identifiant_uuid ? (
                                <span key="v" className="text-muted-foreground">
                                    {t({ en: "Stored (hidden)", fr: "Rangé (masqué)" })}
                                </span>
                            ) : (
                                <Input
                                    key="v"
                                    className="h-8"
                                    type="password"
                                    autoComplete="new-password"
                                    value={saisies[i] ?? ""}
                                    onChange={(x) => setSaisies((v) => ({ ...v, [i]: x.target.value }))}
                                    onBlur={() => void rangerLeSecret(i, e.nom, saisies[i] ?? "")}
                                    placeholder={t({ en: "Type the secret", fr: "Saisir le secret" })}
                                    aria-label={t({ en: "Secret value", fr: "Valeur du secret" })}
                                />
                            )
                        ) : (
                            <Input key="v" className="h-8" value={e.valeur ?? ""} onChange={(x) => maj({ valeur: x.target.value })} aria-label={t({ en: "Header value", fr: "Valeur de l'en-tête" })} />
                        ),
                    ]}
                />
                {erreur && <p className="text-sm text-destructive">{erreur}</p>}
            </BlocChamp>
    );
}

export function OngletRequete({ config, pose }: { config: Config; pose: Pose }) {
    const { t } = useLangue();
    return (
        <Champs>
            <LigneChamp libelle={t({ en: "Method", fr: "Méthode" })}>
                <Liste valeur={texte(config, "method") || "POST"} changer={(v) => pose({ method: v })} options={METHODES} className="w-32" taille="default" />
            </LigneChamp>
            <BlocChamp libelle={t({ en: "Address", fr: "Adresse" })}>
                <Input value={texte(config, "url")} onChange={(e) => pose({ url: e.target.value })} placeholder="https://…/{{id}}" aria-label={t({ en: "Address", fr: "Adresse" })} />
            </BlocChamp>
            <BlocChamp libelle={t({ en: "Credential", fr: "Identifiant" })}>
                <CredentialSelector
                    value={texte(config, "credential_uuid")}
                    onChange={(v: string) => pose({ credential_uuid: v || undefined })}
                    showLabel={false}
                    placeholder={t({ en: "No authentication", fr: "Aucune authentification" })}
                    description=""
                />
            </BlocChamp>
            <LigneChamp libelle={t({ en: "Timeout (ms)", fr: "Délai (ms)" })}>
                <Input
                    className="h-8 w-28 text-right"
                    value={String(nombre(config, "timeout_ms", 5000))}
                    onChange={(e) => pose({ timeout_ms: Math.max(1, Number(e.target.value.replace(/\D/g, "")) || 1) })}
                    aria-label={t({ en: "Timeout", fr: "Délai" })}
                />
            </LigneChamp>
            <BlocEntetes config={config} pose={pose} />
            <BlocEntetesAnciens config={config} pose={pose} />
            {/* SE-22 : les essais, l'attente et « sans risque de doublon » d'une requête, repris de l'ancienne page d'un outil. */}
            <EssaisOutilHttp
                valeur={lireEssais(config)}
                onChange={(suivant: EssaisOutil) =>
                    // Les clés au défaut s'effacent (le défaut est le comportement d'avant) ; les autres s'écrivent.
                    pose({ essais: undefined, attente_entre_essais_s: undefined, sans_risque_de_doublon: undefined, ...chargeEssais(suivant) })
                }
                timeoutMs={nombre(config, "timeout_ms", 5000)}
            />
        </Champs>
    );
}

const EMPLACEMENTS = ["chemin", "requete", "corps", "en_tete"] as const;

export function OngletParametres({ config, pose }: { config: Config; pose: Pose }) {
    const { t } = useLangue();
    const etiquettes: Record<string, string> = {
        chemin: t({ en: "Path", fr: "Chemin" }),
        requete: t({ en: "Query", fr: "Requête" }),
        corps: t({ en: "Body", fr: "Corps" }),
        en_tete: t({ en: "Header", fr: "En-tête" }),
    };
    const parametres = liste<Parametre>(config, "parameters");
    return (
        <Champs>
            <BlocChamp
                libelle={t({ en: "Parameters the model gives", fr: "Paramètres donnés par le modèle" })}
                info={t({
                    en: "Where each value goes in the request, its allowed values (comma separated) and its default. Without a place, a POST sends it in the body and a GET in the query.",
                    fr: "Où part chaque valeur dans la requête, ses valeurs permises (séparées par des virgules) et son défaut. Sans emplacement, un POST l'envoie dans le corps et un GET dans la requête.",
                })}
            >
                <LignesEditables<Parametre>
                    colonnes={[
                        t({ en: "Name", fr: "Nom" }),
                        t({ en: "Place", fr: "Emplacement" }),
                        t({ en: "Allowed values", fr: "Valeurs permises" }),
                        t({ en: "Default", fr: "Défaut" }),
                        t({ en: "Description", fr: "Description" }),
                    ]}
                    lignes={parametres}
                    changer={(l) => pose({ parameters: l })}
                    vide={t({ en: "No parameter.", fr: "Aucun paramètre." })}
                    nouvelle={() => ({ name: "", type: "string", description: "", required: true })}
                    ajouter={t({ en: "Add a parameter", fr: "Ajouter un paramètre" })}
                    rendu={(p, maj) => [
                        <Input key="n" className="h-8" value={p.name} onChange={(e) => maj({ name: e.target.value })} aria-label={t({ en: "Parameter name", fr: "Nom du paramètre" })} />,
                        <Liste
                            key="e"
                            valeur={p.emplacement ?? ""}
                            changer={(v) => maj({ emplacement: v || null })}
                            vide={t({ en: "As before", fr: "Comme avant" })}
                            options={EMPLACEMENTS.map((x) => ({ valeur: x, libelle: etiquettes[x] }))}
                            className="w-32"
                        />,
                        <Input
                            key="v"
                            className="h-8"
                            value={(p.valeurs_permises ?? []).join(", ")}
                            onChange={(e) => {
                                const l = e.target.value.split(",").map((x) => x.trim()).filter(Boolean);
                                maj({ valeurs_permises: l.length ? l : null });
                            }}
                            aria-label={t({ en: "Allowed values", fr: "Valeurs permises" })}
                        />,
                        <Input
                            key="d"
                            className="h-8 w-24"
                            value={p.defaut == null ? "" : String(p.defaut)}
                            onChange={(e) => maj({ defaut: e.target.value === "" ? null : e.target.value })}
                            aria-label={t({ en: "Default value", fr: "Valeur par défaut" })}
                        />,
                        <Input key="x" className="h-8" value={p.description} onChange={(e) => maj({ description: e.target.value })} aria-label={t({ en: "Description", fr: "Description" })} />,
                    ]}
                />
            </BlocChamp>
        </Champs>
    );
}

const lireJson = (s: string): unknown => {
    if (!s.trim()) return {};
    try {
        return JSON.parse(s);
    } catch {
        return undefined;
    }
};

export function OngletReponse({ config, pose }: { config: Config; pose: Pose }) {
    const { t } = useLangue();
    const gardes = liste<string>(config, "chemins_gardes");
    const copies = liste<Copie>(config, "copies_dans_la_fiche");
    const simulees = liste<Simulee>(config, "reponses_simulees");
    return (
        <div>
            <Section
                titre={t({ en: "What the model reads", fr: "Ce que le modèle lit" })}
                info={t({
                    en: "Paths of the answer kept for the model, one per line (client.name, items.0.id). Empty: the whole answer.",
                    fr: "Chemins de la réponse gardés pour le modèle, un par ligne (client.nom, items.0.id). Vide : la réponse entière.",
                })}
            >
                <Textarea
                    rows={3}
                    value={gardes.join("\n")}
                    onChange={(e) => pose({ chemins_gardes: e.target.value.split("\n").map((x) => x.trim()).filter(Boolean) })}
                    aria-label={t({ en: "Kept paths", fr: "Chemins gardés" })}
                />
            </Section>
            <Section
                titre={t({ en: "Short answer for the voice", fr: "Réponse courte pour la voix" })}
                info={t({
                    en: "Off by default. On: the model only gets the first items of a list, long texts are cut and heavy fields removed. The call record keeps the whole answer.",
                    fr: "Éteint par défaut. Allumé : le modèle ne reçoit que les premiers éléments d'une liste, les textes longs sont coupés et les champs lourds retirés. La fiche de l'appel garde la réponse entière.",
                })}
            >
                <LigneChamp libelle={t({ en: "Shorten what the model reads", fr: "Raccourcir ce que le modèle lit" })}>
                    <Switch checked={config.resume_pour_la_voix === true} onCheckedChange={(v) => pose({ resume_pour_la_voix: v })} aria-label={t({ en: "Short answer for the voice", fr: "Réponse courte pour la voix" })} />
                </LigneChamp>
                {config.resume_pour_la_voix === true && (
                    <>
                        <LigneChamp libelle={t({ en: "Items kept from a list", fr: "Éléments gardés d'une liste" })}>
                            <Input
                                className="h-8 w-24 text-right"
                                value={String(nombre(config, "resume_max_elements", 3))}
                                onChange={(e) => pose({ resume_max_elements: Math.min(50, Math.max(1, Number(e.target.value.replace(/\D/g, "")) || 1)) })}
                                aria-label={t({ en: "Items kept", fr: "Éléments gardés" })}
                            />
                        </LigneChamp>
                        <LigneChamp libelle={t({ en: "Characters kept from a text", fr: "Caractères gardés d'un texte" })}>
                            <Input
                                className="h-8 w-24 text-right"
                                value={String(nombre(config, "resume_max_caracteres", 1200))}
                                onChange={(e) => pose({ resume_max_caracteres: Math.min(20000, Math.max(50, Number(e.target.value.replace(/\D/g, "")) || 50)) })}
                                aria-label={t({ en: "Characters kept", fr: "Caractères gardés" })}
                            />
                        </LigneChamp>
                        <BlocChamp libelle={t({ en: "Heavy fields removed", fr: "Champs lourds retirés" })} info={t({ en: "Field names, one per line.", fr: "Noms de champs, un par ligne." })}>
                            <Textarea
                                rows={2}
                                value={liste<string>(config, "resume_champs_retires").join("\n")}
                                onChange={(e) => pose({ resume_champs_retires: e.target.value.split("\n").map((x) => x.trim()).filter(Boolean) })}
                                aria-label={t({ en: "Heavy fields removed", fr: "Champs lourds retirés" })}
                            />
                        </BlocChamp>
                    </>
                )}
            </Section>
            <Section
                titre={t({ en: "Copied into the call record", fr: "Copié dans la fiche de l'appel" })}
                info={t({
                    en: "A value of the answer written in the record, read from the whole answer before any filtering.",
                    fr: "Une valeur de la réponse écrite dans la fiche, lue dans la réponse entière avant tout filtrage.",
                })}
            >
                <LignesEditables<Copie>
                    colonnes={[t({ en: "Path in the answer", fr: "Chemin dans la réponse" }), t({ en: "Record key", fr: "Clé de la fiche" })]}
                    lignes={copies}
                    changer={(l) => pose({ copies_dans_la_fiche: l })}
                    vide={t({ en: "Nothing copied.", fr: "Rien n'est copié." })}
                    nouvelle={() => ({ chemin: "", cle: "" })}
                    ajouter={t({ en: "Add a copy", fr: "Ajouter une copie" })}
                    rendu={(c, maj) => [
                        <Input key="c" className="h-8" value={c.chemin} onChange={(e) => maj({ chemin: e.target.value })} aria-label={t({ en: "Path", fr: "Chemin" })} />,
                        <Input key="k" className="h-8" value={c.cle} onChange={(e) => maj({ cle: e.target.value })} aria-label={t({ en: "Key", fr: "Clé" })} />,
                    ]}
                />
            </Section>
            <Section
                titre={t({ en: "Simulated answers", fr: "Réponses simulées" })}
                info={t({
                    en: "Served by the trial and the test bench only, never in a real call. « When »: parameter=value pairs, comma separated; empty: always.",
                    fr: "Servies par l'essai et le banc seulement, jamais en appel réel. « Quand » : des paires paramètre=valeur séparées par des virgules ; vide : toujours.",
                })}
            >
                <LignesEditables<Simulee>
                    colonnes={[t({ en: "Name", fr: "Nom" }), t({ en: "When", fr: "Quand" }), t({ en: "Code", fr: "Code" }), t({ en: "Body (JSON)", fr: "Corps (JSON)" })]}
                    lignes={simulees}
                    changer={(l) => pose({ reponses_simulees: l })}
                    vide={t({ en: "No simulated answer.", fr: "Aucune réponse simulée." })}
                    nouvelle={() => ({ nom: "", quand: {}, statut: 200, donnees: {} })}
                    ajouter={t({ en: "Add an answer", fr: "Ajouter une réponse" })}
                    rendu={(s, maj) => [
                        <Input key="n" className="h-8" value={s.nom ?? ""} onChange={(e) => maj({ nom: e.target.value })} aria-label={t({ en: "Answer name", fr: "Nom de la réponse" })} />,
                        <Input
                            key="q"
                            className="h-8"
                            defaultValue={Object.entries(s.quand ?? {}).map(([k, v]) => `${k}=${v}`).join(", ")}
                            onBlur={(e) =>
                                maj({
                                    quand: Object.fromEntries(
                                        e.target.value.split(",").map((x) => x.trim()).filter((x) => x.includes("=")).map((x) => [x.split("=")[0].trim(), x.slice(x.indexOf("=") + 1).trim()]),
                                    ),
                                })
                            }
                            aria-label={t({ en: "When", fr: "Quand" })}
                        />,
                        <Input key="c" className="h-8 w-20" value={String(s.statut ?? 200)} onChange={(e) => maj({ statut: Math.min(599, Math.max(100, Number(e.target.value.replace(/\D/g, "")) || 200)) })} aria-label={t({ en: "Status code", fr: "Code de statut" })} />,
                        <Textarea
                            key="d"
                            rows={2}
                            className="min-h-0 font-mono text-xs"
                            defaultValue={JSON.stringify(s.donnees ?? {})}
                            onBlur={(e) => {
                                const v = lireJson(e.target.value);
                                if (v !== undefined) maj({ donnees: v });
                            }}
                            aria-label={t({ en: "Body", fr: "Corps" })}
                        />,
                    ]}
                />
            </Section>
        </div>
    );
}

