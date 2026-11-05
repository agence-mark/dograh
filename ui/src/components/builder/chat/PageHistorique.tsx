"use client";

import { Plus } from "lucide-react";
import Link from "next/link";

import { ChatTousClients, useDansLeLabo } from "@/components/mark/equipe/VuesTousClients";
import { useLangue } from "@/components/mark/langue/langue";
import { OngletsPage } from "@/components/mark/studio/onglets-page";
import { PageStudio, TitrePage } from "@/components/mark/studio/shell-studio";
import { Button } from "@/components/ui/button";

import { useAdressesDuBuilder } from "./adresses";
import { ListeDesFils } from "./ListeDesFils";

/** Le Chat : l'historique des conversations du builder (maquette `app/labo/builder`). « Nouveau chat » mène à l'accueil du builder. */
export default function PageHistorique() {
    const { t } = useLangue();
    const adresses = useAdressesDuBuilder();
    const dansLeLabo = useDansLeLabo();
    return (
        <PageStudio>
            <TitrePage
                titre={t({ en: "Chat", fr: "Chat" })}
                info={t({
                    en: "Every chat is tied to an agent; state, cost, context, Stop and Resume are in the chat.",
                    fr: "Chaque chat est lié à un agent ; état, coût, contexte, Arrêter et Reprendre sont dans le chat.",
                })}
                action={
                    <Button asChild>
                        <Link href={adresses.client ? adresses.liste.replace(/\/chat$/, "/builder") : "/labo"}>
                            <Plus className="size-4" aria-hidden /> {t({ en: "New chat", fr: "Nouveau chat" })}
                        </Link>
                    </Button>
                }
            />
            {dansLeLabo ? (
                // Sous-lot 10 (E-3) : dans le Labo, les conversations du builder de tous les clients ouverts, en lecture seule.
                <OngletsPage
                    defaut="clients"
                    onglets={[
                        { id: "clients", titre: t({ en: "All clients", fr: "Tous les clients" }), contenu: <ChatTousClients /> },
                        { id: "labo", titre: "Labo", contenu: <ListeDesFils /> },
                    ]}
                />
            ) : (
                <div>
                    <ListeDesFils />
                </div>
            )}
        </PageStudio>
    );
}
