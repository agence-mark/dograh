import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, expect, it, vi } from 'vitest';

import type { WorkflowVersionResponse } from '@/client/types.gen';

import RenderWorkflow from './RenderWorkflow';

const mocks = vi.hoisted(() => ({
    query: 'version=3&source=campaign',
    push: vi.fn(),
    versions: vi.fn(),
    save: vi.fn(),
    state: {
        rfInstance: { current: null },
        nodes: [], edges: [], workflowValidationErrors: [],
        workflowName: 'Agent', isDirty: false, templateContextVariables: {},
        setNodes: vi.fn(), setEdges: vi.fn(), setIsDirty: vi.fn(),
    },
}));
vi.mock('@xyflow/react/dist/style.css', () => ({}));
vi.mock('next/navigation', () => ({
    useRouter: () => ({ push: mocks.push }),
    useSearchParams: () => new URLSearchParams(mocks.query),
}));
vi.mock('@/client', () => ({
    getWorkflowVersionsApiV1WorkflowWorkflowIdVersionsGet: mocks.versions,
    createWorkflowDraftApiV1WorkflowWorkflowIdCreateDraftPost: vi.fn(),
    listDocumentsApiV1KnowledgeBaseDocumentsGet: async () => ({ data: { documents: [] } }),
    listToolsApiV1ToolsGet: async () => ({ data: [] }),
    listRecordingsApiV1WorkflowRecordingsGet: async () => ({ data: { recordings: [] } }),
}));
vi.mock('./hooks/useWorkflowState', () => ({ useWorkflowState: () => ({ ...mocks.state, saveWorkflow: mocks.save }) }));
vi.mock('@/components/flow/renderer', () => ({ useNodeSpecs: () => ({ specs: [] }) }));
vi.mock('@/context/OnboardingContext', () => ({ useOnboarding: () => ({ hasCompletedAction: () => true }) }));
vi.mock('@/components/mark/graphe/GroupeSurCanevas', () => ({ GroupeSurCanevas: () => null, FilGroupe: () => null }));
vi.mock('@/components/flow/edges/CustomEdge', () => ({ default: () => null }));
vi.mock('@/components/flow/nodes/GenericNode', () => ({ GenericNode: () => null }));
vi.mock('./components/PhoneCallDialog', () => ({ PhoneCallDialog: () => null }));
vi.mock('./components/WorkflowTesterPanel', () => ({
    WorkflowTesterPanel: ({ disabled }: { disabled: boolean }) => <div data-testid="tester" data-disabled={disabled} />,
}));
vi.mock('@xyflow/react', () => ({
    Background: () => null,
    BackgroundVariant: { Dots: 'dots' },
    MarkerType: { ArrowClosed: 'arrowclosed' },
    Panel: ({ children }: { children: ReactNode }) => children,
    ReactFlow: ({ nodesDraggable, children }: { nodesDraggable: boolean; children: ReactNode }) => <div data-testid="canvas" data-editable={nodesDraggable}>{children}</div>,
}));
vi.mock('./components/WorkflowEditorHeader', () => ({
    WorkflowEditorHeader: ({ versionNumber, onBackToDraft, saveWorkflow }: {
        versionNumber: number | null;
        onBackToDraft: () => void;
        saveWorkflow: () => void;
    }) => <div>
        <span data-testid="version-label">v{versionNumber}</span>
        <button onClick={onBackToDraft}>Back to draft</button>
        <button onClick={saveWorkflow}>Save</button>
    </div>,
}));

const version = (number: number, status: string): WorkflowVersionResponse => ({
    id: 100 + number, version_number: number, status,
    workflow_json: { nodes: [], edges: [] }, created_at: '2026-01-01T00:00:00Z',
});

beforeEach(() => {
    vi.clearAllMocks();
    mocks.query = 'version=3&source=campaign';
    mocks.versions.mockResolvedValue({ data: [version(21, 'draft'), version(20, 'published')] });
});

it.each(['archived', 'published'])('opens a linked %s version read-only before history loads', async status => {
    // `?essai=audio` : l'« Essayer » d'un autre onglet ouvre le panneau d'essai (fermé par défaut).
    mocks.query = 'version=3&source=campaign&essai=audio';
    render(<RenderWorkflow workflowId={12} initialWorkflowName="Agent" user={{ id: '1' }} initialSelectedVersion={version(3, status)} />);
    expect(screen.getByTestId('canvas').getAttribute('data-editable')).toBe('false');
    expect(screen.getByTestId('tester').getAttribute('data-disabled')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: 'Save', hidden: true }));
    expect(mocks.save).not.toHaveBeenCalled();
    expect(mocks.versions).not.toHaveBeenCalled();
    expect(screen.getByTestId('version-label').textContent).toContain('v3');
});

it('clears only the version from the address when returning to the draft (the page of an agent is /agents/<id>)', async () => {
    render(<RenderWorkflow workflowId={12} initialWorkflowName="Agent" user={{ id: '1' }} initialSelectedVersion={version(3, 'archived')} />);
    fireEvent.click(screen.getByRole('button', { name: 'Back to draft' }));
    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith('/agents/12?source=campaign', { scroll: false }));
});

it('draws the floating bar of the canvas, whose tools disappear on a past version', () => {
    const { unmount } = render(<RenderWorkflow workflowId={12} initialWorkflowName="Agent" user={{ id: '1' }} />);
    expect(screen.getByRole('button', { name: 'General prompt' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Node' })).toBeTruthy();
    unmount();
    render(<RenderWorkflow workflowId={12} initialWorkflowName="Agent" user={{ id: '1' }} initialSelectedVersion={version(3, 'archived')} />);
    expect(screen.queryByRole('button', { name: 'General prompt' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Fit the view' })).toBeTruthy();
});

it('opens the window of a node on Enter (keyboard), as the double-click does, and only on Enter', async () => {
    const { useOuvertureNoeud } = await import('@/components/mark/agent/ouverture-noeud');
    useOuvertureNoeud.setState({ demande: null });
    render(<RenderWorkflow workflowId={12} initialWorkflowName="Agent" user={{ id: '1' }} />);
    const noeud = document.createElement('div');
    noeud.className = 'react-flow__node';
    noeud.setAttribute('data-id', '7');
    noeud.tabIndex = 0;
    screen.getByTestId('canvas').appendChild(noeud);
    fireEvent.keyDown(noeud, { key: 'ArrowDown' });
    expect(useOuvertureNoeud.getState().demande).toBeNull();
    fireEvent.keyDown(noeud, { key: 'Enter' });
    expect(useOuvertureNoeud.getState().demande?.id).toBe('7');
});
