/*---------------------------------------------------------------------------------------------
 *  FreeForge streaming chat panel — UI shell; brain is MAINFRAME Python via bridge.
 *--------------------------------------------------------------------------------------------*/

import { FreeForgeAiStatus } from './freeforge.contribution.js';

export interface ChatMessage {
	readonly role: 'user' | 'assistant' | 'system';
	readonly content: string;
	readonly streaming?: boolean;
}

export interface ChatPanelState {
	readonly sessionId: string | null;
	readonly messages: ChatMessage[];
	readonly ai: FreeForgeAiStatus;
	readonly cancelled: boolean;
}

export function initialChatState(ai: FreeForgeAiStatus): ChatPanelState {
	return {
		sessionId: null,
		messages: [],
		ai,
		cancelled: false,
	};
}

/** Append a streamed chunk to the last assistant message (or create one). */
export function appendStreamChunk(state: ChatPanelState, chunk: string): ChatPanelState {
	const messages = state.messages.slice();
	const last = messages[messages.length - 1];
	if (last && last.role === 'assistant' && last.streaming) {
		messages[messages.length - 1] = {
			role: 'assistant',
			content: last.content + chunk,
			streaming: true,
		};
	} else {
		messages.push({ role: 'assistant', content: chunk, streaming: true });
	}
	return { ...state, messages };
}

export function finalizeAssistant(state: ChatPanelState): ChatPanelState {
	const messages = state.messages.map((m, i) =>
		i === state.messages.length - 1 && m.role === 'assistant'
			? { role: 'assistant' as const, content: m.content, streaming: false }
			: m
	);
	return { ...state, messages };
}

export function pausedBanner(ai: FreeForgeAiStatus): string | null {
	if (ai.state === 'available') {
		return null;
	}
	return ai.detail || 'Local AI paused. Deterministic editing continues.';
}
