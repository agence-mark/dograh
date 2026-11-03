"use client";

/**
 * [.mark] U3 sexies point 1 (E73) : « Connecteurs » devient « Intégrations », trois onglets : Logiciels, Serveurs MCP,
 * Identifiants. L'adresse `/labo/connecteurs` reste valable. Une intégration est le branchement d'un logiciel une fois
 * pour l'organisation ; elle met des actions à disposition, que les Outils utilisent. K5 : cadre de page (`PageStudio`).
 */
import { useState } from "react";

import { useConnecteurs } from "../connecteurs/useConnecteurs";
import { useLangue } from "../langue/langue";
import { OngletsPage, useOngletDeLAdresse } from "../studio/onglets-page";
import { PageStudio } from "../studio/shell-studio";
import { TitrePage } from "../studio/titre-page";
import { ContexteAction } from "./action-de-page";
import { OngletIdentifiants } from "./OngletIdentifiants";
import { OngletLogiciels } from "./OngletLogiciels";
import { OngletServeursMcp } from "./OngletServeursMcp";
import { usePropositions } from "./usePropositions";

export function PageIntegrations() {
    const { t } = useLangue();
    const connecteurs = useConnecteurs();
    const propositions = usePropositions();
    // K7 : l'action de l'onglet actif s'affiche à droite du titre (comme la maquette) ; la page lit l'onglet actif et prête l'emplacement.
    const { actif, choisir } = useOngletDeLAdresse(["logiciels", "mcp", "identifiants"], "logiciels");
    const [emplacement, setEmplacement] = useState<HTMLElement | null>(null);
    return (
        <ContexteAction.Provider value={{ emplacement, actif }}>
        <PageStudio>
                <TitrePage
                    titre={t({ en: "Integrations", fr: "Intégrations" })}
                    info={t({
                        en: "What is connected once for the organization: the client's software, the MCP servers and the credentials (keys, tokens, passwords) of the HTTP requests, the MCP servers and the software connected by a key. The tools rely on them. The model providers' keys are in Models and keys.",
                        fr: "Ce qui est branché une fois pour l'organisation : les logiciels du client, les serveurs MCP et les identifiants (clés, jetons, mots de passe) des requêtes HTTP, des serveurs MCP et des logiciels branchés par clé. Les outils s'appuient dessus. Les clés des fournisseurs de modèles sont dans Modèles et clés.",
                    })}
                    action={<div ref={setEmplacement} className="contents" />}
                />
                <OngletsPage
                    controle={{ actif, choisir }}
                    onglets={[
                        { id: "logiciels", titre: t({ en: "Software", fr: "Logiciels" }), contenu: <OngletLogiciels connecteurs={connecteurs} propositions={propositions} /> },
                        { id: "mcp", titre: t({ en: "MCP servers", fr: "Serveurs MCP" }), contenu: <OngletServeursMcp /> },
                        { id: "identifiants", titre: t({ en: "Credentials", fr: "Identifiants" }), contenu: <OngletIdentifiants /> },
                    ]}
                />
        </PageStudio>
        </ContexteAction.Provider>
    );
}
