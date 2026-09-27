import { Loader2 } from 'lucide-react';

interface ConnectionStatusProps {
    connectionStatus: 'idle' | 'connecting' | 'connected' | 'failed';
}

export const ConnectionStatus = ({ connectionStatus }: ConnectionStatusProps) => {
    if (connectionStatus === 'idle') return null;

    if (connectionStatus === 'connecting') {
        return (
            <div className="flex items-center justify-center space-x-2 text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin" />
                <span className="text-sm font-medium">Establishing Connection...</span>
            </div>
        );
    }

    if (connectionStatus === 'connected') {
        return (
            <div className="flex items-center justify-center space-x-2 text-foreground">
                <div className="h-2 w-2 bg-(--signal-ok) rounded-full animate-pulse" />
                <span className="text-sm font-medium">Connected</span>
            </div>
        );
    }

    if (connectionStatus === 'failed') {
        return (
            <div className="flex items-center justify-center space-x-2 text-destructive">
                <div className="h-2 w-2 bg-destructive rounded-full" />
                <span className="text-sm font-medium">Connection Failed</span>
            </div>
        );
    }

    return null;
};
