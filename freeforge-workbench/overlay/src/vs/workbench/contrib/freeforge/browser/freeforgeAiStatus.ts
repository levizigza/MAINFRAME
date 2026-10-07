/*---------------------------------------------------------------------------------------------
 *  FreeForge AI status — available vs paused (Mode B). Never invents availability.
 *--------------------------------------------------------------------------------------------*/

import { Disposable } from '../../../../base/common/lifecycle.js';
import { IStatusbarService, StatusbarAlignment } from '../../../services/statusbar/browser/statusbar.js';
import { ICommandService } from '../../../../platform/commands/common/commands.js';
import { localize } from '../../../../nls.js';
import { IWorkbenchContribution } from '../../../common/contributions.js';

/**
 * Status bar entry reflecting MAINFRAME `ai probe` via Extension Host / CLI bridge.
 * Until the bridge reports available, UI must show paused.
 */
export class FreeforgeAiStatusContribution extends Disposable implements IWorkbenchContribution {
	static readonly ID = 'workbench.contrib.freeforge.aiStatus';

	private _available = false;

	constructor(
		@IStatusbarService private readonly statusbarService: IStatusbarService,
		@ICommandService private readonly commandService: ICommandService
	) {
		super();
		const entry = this.statusbarService.addEntry(
			{
				name: localize('freeforge.aiStatus', 'FreeForge AI'),
				text: '$(debug-pause) FreeForge AI: paused',
				ariaLabel: localize('freeforge.aiPaused', 'FreeForge AI paused — local Ollama unavailable'),
				command: 'freeforge.showAiStatus',
				tooltip: localize(
					'freeforge.aiTooltip',
					'Mode B optional. Deterministic editing still works. Run: python -m mainframe workbench fitness'
				),
			},
			'status.freeforge.ai',
			StatusbarAlignment.RIGHT,
			100
		);
		this._register(entry);

		// Poll bridge command when registered by FreeForge extension host glue
		const tick = async () => {
			try {
				const result = (await this.commandService.executeCommand(
					'freeforge.aiProbe'
				)) as { status?: string } | undefined;
				const avail = result?.status === 'available';
				if (avail !== this._available) {
					this._available = avail;
					entry.update({
						name: localize('freeforge.aiStatus', 'FreeForge AI'),
						text: avail
							? '$(check) FreeForge AI: available'
							: '$(debug-pause) FreeForge AI: paused',
						ariaLabel: avail
							? localize('freeforge.aiAvail', 'FreeForge AI available')
							: localize('freeforge.aiPaused', 'FreeForge AI paused — local Ollama unavailable'),
						command: 'freeforge.showAiStatus',
						tooltip: avail
							? localize('freeforge.aiOn', 'Local Ollama eligible at loopback')
							: localize(
									'freeforge.aiTooltip',
									'Mode B optional. Deterministic editing still works. Run: python -m mainframe workbench fitness'
								),
					});
				}
			} catch {
				// Bridge not ready — remain paused
			}
		};
		void tick();
		const handle = setInterval(() => void tick(), 15000);
		this._register({ dispose: () => clearInterval(handle) });
	}
}
