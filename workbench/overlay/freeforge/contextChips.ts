/*---------------------------------------------------------------------------------------------
 *  Context chips — selection, active file, diagnostics (from host LSP).
 *--------------------------------------------------------------------------------------------*/

export interface ContextChip {
	readonly kind: 'selection' | 'active_file' | 'diagnostic';
	readonly path: string;
	readonly startLine?: number;
	readonly endLine?: number;
	readonly label: string;
}

export function selectionChip(
	path: string,
	startLine: number,
	endLine: number
): ContextChip {
	return {
		kind: 'selection',
		path,
		startLine,
		endLine,
		label: `${path}:${startLine}-${endLine}`,
	};
}

export function activeFileChip(path: string): ContextChip {
	return { kind: 'active_file', path, label: path };
}

export function diagnosticChip(
	path: string,
	line: number,
	message: string
): ContextChip {
	const short = message.length > 48 ? message.slice(0, 45) + '…' : message;
	return {
		kind: 'diagnostic',
		path,
		startLine: line,
		endLine: line,
		label: `${path}:${line} ${short}`,
	};
}

export function chipsToBridgePayload(chips: ContextChip[]): {
	path: string;
	text: string;
	start_line?: number;
	end_line?: number;
}[] {
	return chips
		.filter((c) => c.kind === 'selection')
		.map((c) => ({
			path: c.path,
			text: c.label,
			start_line: c.startLine,
			end_line: c.endLine,
		}));
}
