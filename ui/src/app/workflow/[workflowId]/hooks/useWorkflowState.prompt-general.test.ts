/**
 * [.mark] Clôture SA-5 (É68, Evan 09/11) : le texte de départ d'un Prompt général NEUF vient de la bibliothèque (en français), jamais d'un
 * texte écrit en dur ; le texte d'amont ne reste que si la bibliothèque est vide ou illisible. Un prompt déjà écrit n'est jamais touché
 * (seul l'ajout d'un nœud global neuf lit la graine).
 */
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const AMONT = 'You are a helpful assistant whose mode of interaction with the user is voice.';

const mocks = vi.hoisted(() => ({
    graine: vi.fn(),
    specs: { specs: [] as never[], bySpecName: new Map(), loading: false },
}));

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('@/client', () => ({
    createWorkflowRunApiV1WorkflowWorkflowIdRunsPost: vi.fn(),
    updateWorkflowApiV1WorkflowWorkflowIdPut: vi.fn(),
    getDefaultConfigurationsApiV1UserConfigurationsDefaultsGet: async () => ({ error: 'x' }),
    validateWorkflowApiV1WorkflowWorkflowIdValidatePost: async () => ({ data: { is_valid: true, errors: [] } }),
    lireLaGraineDuPromptGeneralApiV1BuilderAgentsWorkflowIdPromptGeneralDeDepartGet: mocks.graine,
}));
vi.mock('@/components/flow/renderer', () => ({ useNodeSpecs: () => mocks.specs }));
vi.mock('@/components/mark/notifications', () => ({ notifier: { succes: vi.fn(), echec: vi.fn(), avertissement: vi.fn() } }));

import { useWorkflowState } from './useWorkflowState';

const UTILISATEUR = { id: 'u1' };
const FLUX = { nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } };

const spec = (name: string, prompt?: string) => ({
    name,
    properties: [{ name: 'name', default: name }, ...(prompt ? [{ name: 'prompt', default: prompt }] : [])],
});

function monter() {
    mocks.specs.bySpecName = new Map([
        ['globalNode', spec('globalNode', AMONT)],
        ['agentNode', spec('agentNode', 'Prompt de l\'étape')],
    ]) as never;
    const rendu = renderHook(() => useWorkflowState({ initialWorkflowName: 'Agent', workflowId: 7, initialFlow: FLUX, user: UTILISATEUR }));
    const ajoutes: Array<{ type: string; data: Record<string, unknown> }> = [];
    rendu.result.current.rfInstance.current = {
        screenToFlowPosition: () => ({ x: 0, y: 0 }),
        getNodes: () => [],
        setNodes: () => undefined,
        addNodes: (n: never[]) => ajoutes.push(...n),
    } as never;
    return { ...rendu, ajoutes };
}

describe('graine du Prompt général neuf', () => {
    beforeEach(() => vi.clearAllMocks());

    it('un nœud global neuf reçoit le texte de la bibliothèque', async () => {
        mocks.graine.mockResolvedValue({ data: { texte: 'Tu es la voix de l\'entreprise.', source: 'recette', slug: 'mon-prompt' } });
        const { result, ajoutes } = monter();
        await act(async () => { await result.current.handleNodeSelect('globalNode'); });
        expect(mocks.graine).toHaveBeenCalledWith({ path: { workflow_id: 7 } });
        expect(ajoutes).toHaveLength(1);
        expect(ajoutes[0].data.prompt).toBe('Tu es la voix de l\'entreprise.');
    });

    it('bibliothèque vide : le texte d\'amont reste', async () => {
        mocks.graine.mockResolvedValue({ data: { texte: null, source: 'amont', slug: null } });
        const { result, ajoutes } = monter();
        await act(async () => { await result.current.handleNodeSelect('globalNode'); });
        expect(ajoutes[0].data.prompt).toBe(AMONT);
    });

    it('lecture en échec : le nœud est ajouté quand même, avec le texte d\'amont', async () => {
        mocks.graine.mockRejectedValue(new Error('réseau'));
        const { result, ajoutes } = monter();
        await act(async () => { await result.current.handleNodeSelect('globalNode'); });
        expect(ajoutes).toHaveLength(1);
        expect(ajoutes[0].data.prompt).toBe(AMONT);
    });

    it('un autre nœud ne lit pas la graine', async () => {
        const { result, ajoutes } = monter();
        await act(async () => { await result.current.handleNodeSelect('agentNode'); });
        expect(mocks.graine).not.toHaveBeenCalled();
        expect(ajoutes[0].data.prompt).toBe('Prompt de l\'étape');
    });
});
