"use client";

import { useLangue } from "@/components/mark/langue/langue";
import {
    conversationItemsFromLiveFeedback,
    conversationItemsFromRealtimeFeedbackEvents,
} from "./adapters/fromRealtimeFeedback";
import { ConversationContainer } from "./ConversationContainer";
import { ConversationTimeline } from "./ConversationTimeline";
import type {
    ConversationStatus,
    RealtimeFeedbackMessage,
    WorkflowRunLogs,
} from "./types";
import { countConversationMessages } from "./utils";

interface LiveModeProps {
    mode: "live";
    messages: RealtimeFeedbackMessage[];
    isCallActive: boolean;
    isCallCompleted: boolean;
}

interface HistoricalModeProps {
    mode: "historical";
    logs: WorkflowRunLogs | null;
}

type RealtimeFeedbackProps = LiveModeProps | HistoricalModeProps;

export function RealtimeFeedback(props: RealtimeFeedbackProps) {
    const { t } = useLangue();
    let items;
    let status: ConversationStatus;
    let title: string;
    let emptyState: { title: string; subtitle: string };
    let autoScroll = false;

    if (props.mode === "historical") {
        items = props.logs?.realtime_feedback_events
            ? conversationItemsFromRealtimeFeedbackEvents(props.logs.realtime_feedback_events)
            : [];
        status = "ended";
        title = t({ en: "Call Transcript", fr: "Transcription de l'appel" });
        emptyState = {
            title: t({ en: "No conversation recorded", fr: "Aucune conversation enregistrée" }),
            subtitle: t({ en: "Real-time feedback events were not captured for this call", fr: "Les échanges en direct n'ont pas été captés pour cet appel" }),
        };
    } else {
        items = conversationItemsFromLiveFeedback(props.messages);
        status = props.isCallActive ? "live" : props.isCallCompleted ? "ended" : "ready";
        title = t({ en: "Live Transcript", fr: "Transcription en direct" });
        emptyState = {
            title: t({ en: "No messages yet", fr: "Aucun message pour l'instant" }),
            subtitle: props.isCallActive
                ? t({ en: "Start speaking to see the transcript", fr: "Parlez pour voir la transcription" })
                : t({ en: "Start the call to begin the conversation", fr: "Lancez l'appel pour démarrer la conversation" }),
        };
        autoScroll = true;
    }

    return (
        <ConversationContainer
            title={title}
            status={status}
            messageCount={countConversationMessages(items) || undefined}
        >
            <ConversationTimeline
                items={items}
                autoScroll={autoScroll}
                emptyState={emptyState}
            />
        </ConversationContainer>
    );
}
