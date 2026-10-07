"""FreeForge Workbench — branded vscode-class IDE shell + local AI agent bridge."""

from mainframe.workbench.accept import run_workbench_accept
from mainframe.workbench.status import model_fit_report, workbench_status

__all__ = [
    "run_workbench_accept",
    "workbench_status",
    "model_fit_report",
]
