"""Feature flags for FreeForge workload runs + ablation / disable policy."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class FeatureFlags:
    retrieval: bool = True
    workflow_reuse: bool = True
    review: bool = True
    caching: bool = True

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)

    def label(self) -> str:
        parts = []
        if not self.retrieval:
            parts.append("no_retrieval")
        if not self.workflow_reuse:
            parts.append("no_workflow_reuse")
        if not self.review:
            parts.append("no_review")
        if not self.caching:
            parts.append("no_caching")
        return "full" if not parts else "+".join(parts)


ABLATIONS: dict[str, FeatureFlags] = {
    "full": FeatureFlags(),
    "no_retrieval": FeatureFlags(retrieval=False),
    "no_workflow_reuse": FeatureFlags(workflow_reuse=False),
    "no_review": FeatureFlags(review=False),
    "no_caching": FeatureFlags(caching=False),
}


# Workload-specific disables written after measured worsenings (updated by runner)
DEFAULT_DISABLE_POLICY: dict[str, dict[str, bool]] = {
    "repository_repair": {},
    "website_maintenance": {},
    "document_reporting": {},
}
