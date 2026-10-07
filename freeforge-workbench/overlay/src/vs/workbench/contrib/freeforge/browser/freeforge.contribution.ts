/*---------------------------------------------------------------------------------------------
 *  FreeForge Workbench overlay — thin contrib on pinned microsoft/vscode.
 *  Does not vendor Void workbench services.
 *--------------------------------------------------------------------------------------------*/

import { Disposable } from '../../../../base/common/lifecycle.js';
import { Registry } from '../../../../platform/registry/common/platform.js';
import {
	Extensions as ViewContainerExtensions,
	IViewContainersRegistry,
	ViewContainerLocation,
	IViewsRegistry,
} from '../../../common/views.js';
import { SyncDescriptor } from '../../../../platform/instantiation/common/descriptors.js';
import { ViewPaneContainer } from '../../../browser/parts/views/viewPaneContainer.js';
import { localize2 } from '../../../../nls.js';
import { Codicon } from '../../../../base/common/codicons.js';
import { registerIcon } from '../../../../platform/theme/common/iconRegistry.js';
import { FreeforgeChatViewPane } from './freeforgeChatViewPane.js';
import { FreeforgeAiStatusContribution } from './freeforgeAiStatus.js';
import { registerWorkbenchContribution2, WorkbenchPhase } from '../../../common/contributions.js';

export const FREEFORGE_VIEW_CONTAINER_ID = 'workbench.view.freeforge';
export const FREEFORGE_CHAT_VIEW_ID = 'freeforge.chat';

const freeforgeIcon = registerIcon(
	'freeforge-view-icon',
	Codicon.robot,
	'FreeForge Workbench view icon'
);

const viewContainer = Registry.as<IViewContainersRegistry>(
	ViewContainerExtensions.ViewContainersRegistry
).registerViewContainer(
	{
		id: FREEFORGE_VIEW_CONTAINER_ID,
		title: localize2('freeforge', 'FreeForge'),
		icon: freeforgeIcon,
		order: 6,
		ctorDescriptor: new SyncDescriptor(ViewPaneContainer, [
			FREEFORGE_VIEW_CONTAINER_ID,
			{ mergeViewWithContainerWhenSingleView: true },
		]),
		storageId: FREEFORGE_VIEW_CONTAINER_ID,
		hideIfEmpty: false,
	},
	ViewContainerLocation.Sidebar,
	{ isDefault: false }
);

Registry.as<IViewsRegistry>(ViewContainerExtensions.ViewsRegistry).registerViews(
	[
		{
			id: FREEFORGE_CHAT_VIEW_ID,
			name: localize2('freeforge.chat', 'Chat'),
			containerIcon: freeforgeIcon,
			ctorDescriptor: new SyncDescriptor(FreeforgeChatViewPane),
			canToggleVisibility: true,
			canMoveView: true,
			order: 1,
		},
	],
	viewContainer
);

registerWorkbenchContribution2(
	FreeforgeAiStatusContribution.ID,
	FreeforgeAiStatusContribution,
	WorkbenchPhase.AfterRestored
);

export class FreeforgeWorkbenchBootstrap extends Disposable {
	static readonly ID = 'workbench.contrib.freeforge.bootstrap';
}
