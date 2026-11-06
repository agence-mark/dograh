/**
 * [.mark] SA-V : un enregistrement du graphe dit son résultat (règle de l'écran « retour d'action »), succès comme échec.
 * Avant : aucun message au succès, et un échec réseau ou serveur n'allait que dans le journal.
 */
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
    put: vi.fn(),
    succes: vi.fn(),
    echec: vi.fn(),
    avertissement: vi.fn(),
    specs: { specs: [] as never[], bySpecName: new Map(), loading: false },
}));

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('@/client', () => ({
    createWorkflowRunApiV1WorkflowWorkflowIdRunsPost: vi.fn(),
    updateWorkflowApiV1WorkflowWorkflowIdPut: mocks.put,
    getDefaultConfigurationsApiV1UserConfigurationsDefaultsGet: async () => ({ error: 'x' }),
    validateWorkflowApiV1WorkflowWorkflowIdValidatePost: async () => ({ data: { is_valid: true, errors: [] } }),
}));
vi.mock('@/components/flow/renderer', () => ({ useNodeSpecs: () => mocks.specs }));
vi.mock('@/components/mark/notifications', () => ({
    notifier: { succes: mocks.succes, echec: mocks.echec, avertissement: mocks.avertissement },
}));

import { useWorkflowState } from './useWorkflowState';

const FLUX = { nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } };
const UTILISATEUR = { id: 'u1' };
const monter = () => {
    const rendu = renderHook(() => useWorkflowState({ initialWorkflowName: 'Agent', workflowId: 7, initialFlow: FLUX, user: UTILISATEUR }));
    rendu.result.current.rfInstance.current = { getViewport: () => ({ x: 0, y: 0, zoom: 1 }) } as never;
    return rendu;
};

describe('enregistrement du graphe', () => {
    beforeEach(() => vi.clearAllMocks());

    it('dit « Brouillon enregistré » quand le serveur accepte', async () => {
        mocks.put.mockResolvedValue({ data: { workflow_definition: { nodes: [], edges: [] }, version_number: 2, version_status: 'draft' } });
        const { result } = monter();
        await act(async () => { await result.current.saveWorkflow(); });
        expect(mocks.succes).toHaveBeenCalledTimes(1);
        expect(mocks.succes.mock.calls[0][0]).toEqual({ fr: 'Brouillon enregistré.', en: 'Draft saved.' });
        expect(mocks.echec).not.toHaveBeenCalled();
    });

    it('dit l’échec quand le serveur refuse, sans texte brut', async () => {
        mocks.put.mockResolvedValue({ error: { detail: 'Traceback (most recent call last)' } });
        const { result } = monter();
        await act(async () => { await result.current.saveWorkflow(); });
        expect(mocks.echec).toHaveBeenCalledTimes(1);
        expect(mocks.echec.mock.calls[0][0]).toEqual({ fr: 'Brouillon non enregistré. Réessayez.', en: 'Draft not saved. Try again.' });
        expect(mocks.succes).not.toHaveBeenCalled();
    });

    it('dit l’échec quand le réseau tombe', async () => {
        mocks.put.mockRejectedValue(new Error('network'));
        const { result } = monter();
        await act(async () => { await result.current.saveWorkflow(); });
        expect(mocks.echec).toHaveBeenCalledTimes(1);
        expect(mocks.succes).not.toHaveBeenCalled();
    });
});
