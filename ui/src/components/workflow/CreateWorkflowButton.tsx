'use client';

import { PlusIcon } from 'lucide-react';
import { useState } from 'react';

import { FenetreCreationAgent } from '@/components/mark/agent/FenetreCreationAgent';
import { useLangue } from '@/components/mark/langue/langue';
import { Button } from "@/components/ui/button";

/**
 * [.mark] Partie 3, sous-lot 9 : le bouton de création d'amont ouvre la fenêtre de création UNIQUE (structure, recette, cerveau,
 * point de départ). L'ancienne fenêtre à deux cartes (`ModaleCreationAgent`) et sa page blanche en anglais sont retirées : « Vide »
 * pose le gabarit neutre de .mark.
 */
export function CreateWorkflowButton() {
    const { t } = useLangue();
    const [ouverte, setOuverte] = useState(false);
    return (
        <>
            <Button className="cursor-pointer" onClick={() => setOuverte(true)}>
                <PlusIcon className="w-4 h-4" />
                {t({ en: "New agent", fr: "Nouvel agent" })}
            </Button>
            <FenetreCreationAgent ouvert={ouverte} fermer={() => setOuverte(false)} />
        </>
    );
}
