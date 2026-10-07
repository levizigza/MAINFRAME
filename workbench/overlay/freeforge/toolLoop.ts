/*---------------------------------------------------------------------------------------------
 *  Agent tool loop descriptors — executed by MAINFRAME Python, not reimplemented in TS.
 *--------------------------------------------------------------------------------------------*/

export type ToolName = 'read' | 'search' | 'propose_patch' | 'run_tests' | 'verify';

export interface ToolCall {
	readonly name: ToolName;
	readonly args: Record<string, unknown>;
}

export interface ToolLoopState {
	readonly calls: ToolCall[];
	readonly cancelled: boolean;
}

export function emptyToolLoop(): ToolLoopState {
	return { calls: [], cancelled: false };
}

export function enqueueTool(state: ToolLoopState, call: ToolCall): ToolLoopState {
	if (state.cancelled) {
		return state;
	}
	return { ...state, calls: state.calls.concat([call]) };
}

export function cancelToolLoop(state: ToolLoopState): ToolLoopState {
	return { ...state, cancelled: true };
}

/** Map UI tool names to `python -m mainframe …` argv prefixes (documentation for bridge). */
export const TOOL_CLI: Record<ToolName, string[]> = {
	read: ['retrieve'],
	search: ['retrieve'],
	propose_patch: ['workbench', 'turn'],
	run_tests: ['verify', 'run'],
	verify: ['verify', 'run'],
};
