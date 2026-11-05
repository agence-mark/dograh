"use client";

/**
 * [.mark] U3 sexies point 7 (E73) : Intégrations › Identifiants.
 *
 * Les types du fork : clé d'API, jeton, identifiant et mot de passe, en-tête libre. Pour chacun, les outils qui s'en
 * servent (« Utilisé par », calculé par le serveur) et le remplacement de la valeur : un champ d'écriture seule, la
 * valeur enregistrée n'est jamais lue ni affichée. Un identifiant de la bibliothèque de clés se gère dans « Clés ».
 */
import { KeyRound, Plus } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { notifier } from "@/components/mark/notifications";
import { ActionDePage } from "./action-de-page";

import {
    createCredentialApiV1CredentialsPost,
    deleteCredentialApiV1CredentialsCredentialUuidDelete,
    listCredentialsApiV1CredentialsGet,
    remplacerLaValeurApiV1CredentialsCredentialUuidValeurPut,
    utilisationDesIdentifiantsApiV1CredentialsUtilisationGet,
} from "@/client/sdk.gen";
import type { CredentialResponse, UtilisePar } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { echecAffiche } from "@/components/mark/notifications/echec-affiche";
import { ECHECS } from "@/components/mark/notifications/phrases-echec";
import { useAuth } from "@/lib/auth";

import { useLangue } from "../langue/langue";
import { EtatVide } from "../studio/etat-vide";
import { BlocChamp, Champs, FenetreOnglets, LigneChamp } from "../studio/fenetre-onglets";
import { SuppressionConfirmee } from "../studio/suppression-confirmee";
import { Liste } from "../studio/liste";
import { Info } from "../studio/marques";
import { Paginee } from "../studio/pagination";
import { Cellule, Ligne, Tableau } from "../studio/tableau";

type Sorte = "api_key" | "bearer_token" | "basic_auth" | "custom_header";

export function OngletIdentifiants() {
    const { t } = useLangue();
    const { user, loading } = useAuth();
    const [identifiants, setIdentifiants] = useState<CredentialResponse[] | null>(null);
    const [usage, setUsage] = useState<Record<string, UtilisePar[]>>({});
    const [erreur, setErreur] = useState<string | null>(null);
    const [ouvert, setOuvert] = useState<CredentialResponse | "nouveau" | null>(null);
    const dejaLu = useRef(false);

    const libelleSorte: Record<string, string> = {
        api_key: t({ en: "API key", fr: "Clé d'API" }),
        bearer_token: t({ en: "Token", fr: "Jeton" }),
        basic_auth: t({ en: "Login and password", fr: "Identifiant et mot de passe" }),
        custom_header: t({ en: "Free header", fr: "En-tête libre" }),
        none: "–",
    };

    const relire = useCallback(async () => {
        const [liste, utilises] = await Promise.all([listCredentialsApiV1CredentialsGet(), utilisationDesIdentifiantsApiV1CredentialsUtilisationGet()]);
        if (liste.error || !liste.data) return setErreur(echecAffiche(liste.error, ECHECS.identifiantsListe));
        setErreur(null);
        setIdentifiants(liste.data);
        setUsage(utilises.data ?? {});
    }, []);
    useEffect(() => {
        if (loading || !user || dejaLu.current) return;
        dejaLu.current = true;
        void relire();
    }, [loading, user, relire]);

    if (erreur) return <EtatVide cas="erreur" reessayer={() => void relire()} />;
    if (!identifiants) return <EtatVide cas="chargement" />;

    return (
        <div>
            <ActionDePage onglet="identifiants">
                <Button onClick={() => setOuvert("nouveau")}>
                    <Plus className="size-4" aria-hidden /> {t({ en: "New credential", fr: "Nouvel identifiant" })}
                </Button>
            </ActionDePage>
            {identifiants.length === 0 ? (
                <EtatVide cas="premier" icone={KeyRound} titre={t({ en: "No credential", fr: "Aucun identifiant" })} />
            ) : (
                <Paginee liste={identifiants}>
                    {(page) => (
                        <Tableau
                            colonnes={[
                                { titre: t({ en: "Name", fr: "Nom" }) },
                                { titre: t({ en: "Type", fr: "Type" }) },
                                { titre: t({ en: "Used by", fr: "Utilisé par" }) },
                            ]}
                        >
                            {page.map((c) => (
                                <Ligne key={c.uuid} onClick={() => setOuvert(c)}>
                                    <Cellule principale>{c.name}</Cellule>
                                    <Cellule>{libelleSorte[c.credential_type] ?? c.credential_type}</Cellule>
                                    <Cellule>{(usage[c.uuid] ?? []).map((o) => o.nom).join(", ") || "–"}</Cellule>
                                </Ligne>
                            ))}
                        </Tableau>
                    )}
                </Paginee>
            )}
            {ouvert === "nouveau" && <FenetreNouvelIdentifiant fermer={() => setOuvert(null)} apres={() => void relire()} libelleSorte={libelleSorte} />}
            {ouvert && ouvert !== "nouveau" && (
                <FenetreIdentifiant identifiant={ouvert} utilisePar={usage[ouvert.uuid] ?? []} libelleSorte={libelleSorte} fermer={() => setOuvert(null)} apres={() => void relire()} />
            )}
        </div>
    );
}

function FenetreIdentifiant({
    identifiant,
    utilisePar,
    libelleSorte,
    fermer,
    apres,
}: {
    identifiant: CredentialResponse;
    utilisePar: UtilisePar[];
    libelleSorte: Record<string, string>;
    fermer: () => void;
    apres: () => void;
}) {
    const { t } = useLangue();
    const [valeur, setValeur] = useState("");
    const [erreur, setErreur] = useState<string | null>(null);

    const remplacer = async () => {
        const r = await remplacerLaValeurApiV1CredentialsCredentialUuidValeurPut({ path: { credential_uuid: identifiant.uuid }, body: { valeur } });
        if (r.error) return setErreur(echecAffiche(r.error, ECHECS.identifiantRemplacer));
        setValeur("");
        setErreur(null);
        notifier.succes({ fr: "Valeur remplacée.", en: "Value replaced." });
        apres();
    };
    const supprimer = async () => {
        const r = await deleteCredentialApiV1CredentialsCredentialUuidDelete({ path: { credential_uuid: identifiant.uuid } });
        if (r.error) return setErreur(echecAffiche(r.error, ECHECS.identifiantSupprimer));
        notifier.succes({ fr: "Identifiant supprimé.", en: "Credential deleted." });
        apres();
        fermer();
    };
    return (
        <FenetreOnglets
            fermer={fermer}
            titre={identifiant.name}
            sous={libelleSorte[identifiant.credential_type] ?? identifiant.credential_type}
            valider={null}
            modifie={valeur !== ""}
            pied={erreur ? <span className="text-sm text-destructive">{erreur}</span> : undefined}
        >
            <Champs>
                <BlocChamp libelle={t({ en: "Used by", fr: "Utilisé par" })}>
                    {utilisePar.length === 0 ? (
                        <p className="text-sm text-muted-foreground">{t({ en: "No tool.", fr: "Aucun outil." })}</p>
                    ) : (
                        <ul className="text-sm">
                            {utilisePar.map((o) => (
                                <li key={o.tool_uuid} className="py-1 font-mono">
                                    {o.nom}
                                </li>
                            ))}
                        </ul>
                    )}
                </BlocChamp>
                <BlocChamp libelle={t({ en: "Replace the value", fr: "Remplacer la valeur" })} info={t({ en: "The stored value is never shown; type the new one.", fr: "La valeur enregistrée ne s'affiche jamais ; saisissez la nouvelle." })}>
                    <div className="flex items-center gap-2">
                        <Input
                            type="password"
                            autoComplete="new-password"
                            value={valeur}
                            onChange={(e) => setValeur(e.target.value)}
                            placeholder={t({ en: "New value", fr: "Nouvelle valeur" })}
                            aria-label={t({ en: "New value", fr: "Nouvelle valeur" })}
                        />
                        <Button variant="outline" disabled={!valeur.trim()} onClick={() => void remplacer()}>
                            {t({ en: "Replace", fr: "Remplacer" })}
                        </Button>
                    </div>
                </BlocChamp>
                <LigneChamp libelle={t({ en: "Delete the credential", fr: "Supprimer l'identifiant" })}>
                    <SuppressionConfirmee variant="outline" disabled={utilisePar.length > 0} onConfirmer={() => void supprimer()}>
                        {t({ en: "Delete", fr: "Supprimer" })}
                    </SuppressionConfirmee>
                </LigneChamp>
            </Champs>
        </FenetreOnglets>
    );
}

function FenetreNouvelIdentifiant({ fermer, apres, libelleSorte }: { fermer: () => void; apres: () => void; libelleSorte: Record<string, string> }) {
    const { t } = useLangue();
    const [sorte, setSorte] = useState<Sorte>("api_key");
    const [nom, setNom] = useState("");
    const [champ1, setChamp1] = useState(""); // nom d'en-tête ou nom d'utilisateur
    const [secret, setSecret] = useState("");
    const [erreur, setErreur] = useState<string | null>(null);

    const donnees = (): Record<string, string> =>
        sorte === "api_key"
            ? { header_name: champ1 || "X-API-Key", api_key: secret }
            : sorte === "bearer_token"
              ? { token: secret }
              : sorte === "basic_auth"
                ? { username: champ1, password: secret }
                : { header_name: champ1, header_value: secret };

    const creer = async () => {
        if (!nom.trim() || !secret) return setErreur(t({ en: "A name and a value are required.", fr: "Un nom et une valeur sont requis." }));
        if ((sorte === "basic_auth" || sorte === "custom_header") && !champ1.trim()) return setErreur(t({ en: "Fill the first field.", fr: "Remplissez le premier champ." }));
        const r = await createCredentialApiV1CredentialsPost({ body: { name: nom.trim(), credential_type: sorte, credential_data: donnees() } });
        if (r.error) return setErreur(echecAffiche(r.error, ECHECS.identifiantCreer));
        notifier.succes({ fr: "Identifiant créé.", en: "Credential created." });
        apres();
        fermer();
    };
    const premier =
        sorte === "basic_auth" ? t({ en: "Login", fr: "Identifiant" }) : sorte === "bearer_token" ? null : t({ en: "Header name", fr: "Nom de l'en-tête" });
    return (
        <FenetreOnglets
            fermer={fermer}
            titre={t({ en: "New credential", fr: "Nouvel identifiant" })}
            valider={t({ en: "Create", fr: "Créer" })}
            onValider={() => void creer()}
            modifie={nom !== "" || champ1 !== "" || secret !== ""}
            pied={erreur ? <span className="text-sm text-destructive">{erreur}</span> : undefined}
        >
            <Champs>
                <BlocChamp libelle={t({ en: "Name", fr: "Nom" })}>
                    <Input value={nom} onChange={(e) => setNom(e.target.value)} aria-label={t({ en: "Credential name", fr: "Nom de l'identifiant" })} />
                </BlocChamp>
                <LigneChamp libelle={t({ en: "Type", fr: "Type" })}>
                    <Liste
                        valeur={sorte}
                        changer={(v) => setSorte(v as Sorte)}
                        options={(["api_key", "bearer_token", "basic_auth", "custom_header"] as Sorte[]).map((s) => ({ valeur: s, libelle: libelleSorte[s] }))}
                        className="w-60"
                        taille="default"
                    />
                </LigneChamp>
                {premier && (
                    <BlocChamp libelle={premier}>
                        <Input value={champ1} onChange={(e) => setChamp1(e.target.value)} aria-label={premier} />
                    </BlocChamp>
                )}
                <BlocChamp libelle={t({ en: "Secret value", fr: "Valeur secrète" })}>
                    <Input type="password" autoComplete="new-password" value={secret} onChange={(e) => setSecret(e.target.value)} aria-label={t({ en: "Secret value", fr: "Valeur secrète" })} />
                </BlocChamp>
            </Champs>
        </FenetreOnglets>
    );
}
