"""Windows-target environment doctor — measure host PC, never invent performance."""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import ROOT, ensure_state
from mainframe.freeforge import probe_playwright

# Approximate public weight sizes (GiB on disk) for optional local CPU models.
# These are catalog estimates for fit math only — doctor never downloads them.
MODEL_CATALOG: list[dict[str, Any]] = [
    {
        "id": "tinyllama-1.1b-q4",
        "weights_gib": 0.7,
        "params_b": 1.1,
        "default_ctx": 2048,
        "notes": "Small CPU-friendly estimate; verify after local pull.",
    },
    {
        "id": "qwen2.5-3b-instruct-q4",
        "weights_gib": 2.0,
        "params_b": 3.0,
        "default_ctx": 4096,
        "notes": "Small/mid CPU estimate; verify after local pull.",
    },
    {
        "id": "llama3.2-3b-instruct-q4",
        "weights_gib": 2.0,
        "params_b": 3.0,
        "default_ctx": 8192,
        "notes": "Longer default ctx increases KV estimate.",
    },
    {
        "id": "qwen2.5-7b-instruct-q4",
        "weights_gib": 4.5,
        "params_b": 7.0,
        "default_ctx": 8192,
        "notes": "Often tight on ≤16 GiB systems with browser+IDE.",
    },
    {
        "id": "llama3.1-8b-instruct-q4",
        "weights_gib": 4.7,
        "params_b": 8.0,
        "default_ctx": 8192,
        "notes": "Often exceeds safe budget on 16 GiB laptops with Chrome.",
    },
]

# Rough KV cache GiB ≈ params_b * (ctx/1000) * k
# Calibrated as an order-of-magnitude stand-in for fp16 K/V with GQA-ish models
# (e.g. ~1 GiB KV for ~7B @ 8k). Not a profiler substitute; labeled estimate_only.
KV_GIB_PER_BPARAM_PER_1K_CTX = 0.02
RUNTIME_OVERHEAD_GIB = 1.5  # interpreter + allocator + fragmentation reserve
SAFETY_MARGIN_GIB = 2.0  # leave headroom for OS + IDE


@dataclass
class Finding:
    severity: str  # info | warn | action
    code: str
    message: str
    action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(cmd: list[str], timeout: float = 20.0) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError:
        return 127, "", "not found"
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def _ps(script: str, timeout: float = 25.0) -> tuple[int, str, str]:
    return _run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        timeout=timeout,
    )


def _scrub_secrets(text: str) -> str:
    """Redact token-like substrings from any doctor output strings."""
    patterns = [
        (r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[=:]\s*\S+", r"\1=***REDACTED***"),
        (r"(?i)\b(sk-[a-zA-Z0-9]{10,})\b", "***REDACTED***"),
        (r"(?i)\b(ghp_[a-zA-Z0-9]{20,})\b", "***REDACTED***"),
        (r"(?i)\b(xox[baprs]-[a-zA-Z0-9-]{10,})\b", "***REDACTED***"),
    ]
    out = text
    for pat, repl in patterns:
        out = re.sub(pat, repl, out)
    return out


def detect_host_context() -> dict[str, Any]:
    """
    Distinguish user Windows PC from remote/dev-container environments.
    Hardware numbers from a container must not be presented as the user's PC.
    """
    indicators: list[str] = []
    env_flags = {
        "REMOTE_CONTAINERS": os.environ.get("REMOTE_CONTAINERS"),
        "CODESPACES": os.environ.get("CODESPACES"),
        "DEVCONTAINER": os.environ.get("DEVCONTAINER"),
        "CURSOR_AGENT": os.environ.get("CURSOR_AGENT"),
        "VSCODE_INJECTION": os.environ.get("VSCODE_INJECTION"),
        "DOCKER_CONTAINER": "1" if Path("/.dockerenv").exists() else None,
    }
    for k, v in env_flags.items():
        if v:
            indicators.append(f"env:{k}={_scrub_secrets(str(v))[:40]}")

    # WSL vs native Windows
    is_wsl = False
    if sys.platform.startswith("linux"):
        try:
            is_wsl = "microsoft" in Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            is_wsl = False
        if is_wsl:
            indicators.append("wsl")

    # CURSOR_AGENT alone means an agent is driving this session on the host —
    # it is NOT proof of a remote container. Only container/codespace markers
    # revoke trust_hardware_as_user_pc.
    in_container = bool(
        env_flags.get("REMOTE_CONTAINERS")
        or env_flags.get("CODESPACES")
        or env_flags.get("DEVCONTAINER")
        or env_flags.get("DOCKER_CONTAINER")
        or Path("/.dockerenv").exists()
    )

    if sys.platform == "win32" and not in_container:
        kind = "native_windows"
        trust_hardware_as_user_pc = True
    elif is_wsl and not in_container:
        kind = "wsl"
        trust_hardware_as_user_pc = False  # numbers are VM slice, not full PC claim
    elif in_container:
        kind = "container_or_remote_dev"
        trust_hardware_as_user_pc = False
    else:
        kind = f"other:{sys.platform}"
        trust_hardware_as_user_pc = False

    return {
        "kind": kind,
        "trust_hardware_as_user_pc": trust_hardware_as_user_pc,
        "indicators": indicators,
        "note": (
            "Hardware measurements apply to this process's host view. "
            "When trust_hardware_as_user_pc is false, do not treat RAM/CPU/disk as the user's physical PC."
        ),
    }


def measure_memory() -> dict[str, Any]:
    if sys.platform == "win32":
        code, out, err = _ps(
            "(Get-CimInstance Win32_OperatingSystem | "
            "Select-Object TotalVisibleMemorySize,FreePhysicalMemory | ConvertTo-Json -Compress)"
        )
        if code == 0 and out.strip():
            try:
                data = json.loads(out.strip())
                # Values are KiB
                total_kib = float(data["TotalVisibleMemorySize"])
                free_kib = float(data["FreePhysicalMemory"])
                return {
                    "source": "Win32_OperatingSystem",
                    "total_gib": round(total_kib / (1024 * 1024), 2),
                    "available_gib": round(free_kib / (1024 * 1024), 2),
                    "measured": True,
                }
            except (KeyError, ValueError, TypeError, json.JSONDecodeError):
                pass
        return {"source": "powershell_failed", "measured": False, "detail": _scrub_secrets(err or out)[:200]}

    # Non-Windows fallback — still measured locally, but flagged by host context
    try:
        # Linux
        meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
        total_kb = free_kb = avail_kb = None
        for line in meminfo.splitlines():
            if line.startswith("MemTotal:"):
                total_kb = int(line.split()[1])
            elif line.startswith("MemAvailable:"):
                avail_kb = int(line.split()[1])
            elif line.startswith("MemFree:"):
                free_kb = int(line.split()[1])
        avail = avail_kb if avail_kb is not None else free_kb
        if total_kb and avail is not None:
            return {
                "source": "/proc/meminfo",
                "total_gib": round(total_kb / (1024 * 1024), 2),
                "available_gib": round(avail / (1024 * 1024), 2),
                "measured": True,
            }
    except OSError:
        pass
    return {"source": "unavailable", "measured": False}


def measure_cpu() -> dict[str, Any]:
    logical = os.cpu_count() or 1
    result: dict[str, Any] = {
        "logical_cpus": logical,
        "platform_processor": platform.processor() or None,
        "machine": platform.machine(),
        "measured": True,
    }
    if sys.platform == "win32":
        code, out, _ = _ps(
            "(Get-CimInstance Win32_Processor | "
            "Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed,Architecture | "
            "ConvertTo-Json -Compress)"
        )
        if code == 0 and out.strip():
            try:
                data = json.loads(out.strip())
                if isinstance(data, list):
                    data = data[0]
                result.update(
                    {
                        "source": "Win32_Processor",
                        "name": data.get("Name"),
                        "physical_cores": data.get("NumberOfCores"),
                        "logical_cpus": data.get("NumberOfLogicalProcessors") or logical,
                        "max_clock_mhz": data.get("MaxClockSpeed"),
                        "architecture_cim": data.get("Architecture"),
                    }
                )
            except (json.JSONDecodeError, TypeError, AttributeError):
                result["source"] = "platform_only"
        # Feature flags via registry / CIM is heavy; report presence of AVX via a light check if possible
        code2, out2, _ = _ps(
            "try { "
            "$f = [System.Runtime.Intrinsics.X86.Avx]::IsSupported; "
            "$f2 = [System.Runtime.Intrinsics.X86.Avx2]::IsSupported; "
            "@{avx=[bool]$f; avx2=[bool]$f2} | ConvertTo-Json -Compress "
            "} catch { @{avx=$null; avx2=$null; error='unavailable'} | ConvertTo-Json -Compress }"
        )
        if code2 == 0 and out2.strip():
            try:
                feats = json.loads(out2.strip())
                result["features"] = {
                    "avx": feats.get("avx"),
                    "avx2": feats.get("avx2"),
                    "note": "From .NET System.Runtime.Intrinsics (process ISA view).",
                }
            except json.JSONDecodeError:
                result["features"] = {"note": "unmeasured"}
    return result


def measure_disk() -> dict[str, Any]:
    usage = shutil.disk_usage(str(ROOT))
    return {
        "path": str(ROOT),
        "total_gib": round(usage.total / (1024**3), 2),
        "free_gib": round(usage.free / (1024**3), 2),
        "used_gib": round(usage.used / (1024**3), 2),
        "measured": True,
        "source": "shutil.disk_usage",
    }


def _tool_version(exe: str, args: list[str]) -> dict[str, Any]:
    path = shutil.which(exe)
    if not path:
        return {"present": False, "path": None, "version": None}
    code, out, err = _run([path, *args], timeout=15.0)
    ver = (out or err).strip().splitlines()[0] if (out or err).strip() else None
    return {
        "present": True,
        "path": path,
        "version": _scrub_secrets(ver) if ver else None,
        "exit_code": code,
    }


def measure_runtimes() -> dict[str, Any]:
    return {
        "python": {
            "present": True,
            "version": sys.version.split()[0],
            "executable": sys.executable,
            "implementation": platform.python_implementation(),
        },
        "node": _tool_version("node", ["--version"]),
        "git": _tool_version("git", ["--version"]),
        "ripgrep": _tool_version("rg", ["--version"]),
        "openclaw": _tool_version("openclaw", ["--version"]),
        "opencode": _tool_version("opencode", ["--version"]),
        "docker": {
            **_tool_version("docker", ["--version"]),
            "required_for_core": False,
            "note": "Docker Desktop is not required for MAINFRAME/FreeForge core.",
        },
    }


def measure_shell() -> dict[str, Any]:
    comspec = os.environ.get("COMSPEC")
    ps_code, ps_out, _ = _ps("$PSVersionTable.PSVersion.ToString()")
    # Behavior: does PowerShell accept -Command and return JSON?
    behavior_code, behavior_out, behavior_err = _ps("'ok'")
    return {
        "comspec": comspec,
        "powershell_version": ps_out.strip() if ps_code == 0 else None,
        "powershell_command_ok": behavior_code == 0 and "ok" in behavior_out,
        "shell_flags": {
            "supports_noninteractive": True,
            "measured_ok_probe": behavior_code == 0,
            "stderr_sample_scrubbed": _scrub_secrets((behavior_err or "")[:120]) or None,
        },
        "note": "Doctor uses non-interactive PowerShell; does not change shell profile or startup tasks.",
    }


def measure_browsers() -> dict[str, Any]:
    playwright = probe_playwright()
    edge = shutil.which("msedge") or _windows_app_path(
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    )
    chrome = shutil.which("chrome") or _windows_app_path(
        r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    )
    return {
        "playwright": playwright,
        "msedge_path": edge,
        "chrome_path": chrome,
        "system_browser_present": bool(edge or chrome),
    }


def _windows_app_path(path: str) -> str | None:
    p = Path(path)
    return str(p) if p.is_file() else None


def derive_resource_limits(mem: dict[str, Any], cpu: dict[str, Any], disk: dict[str, Any]) -> dict[str, Any]:
    """Conservative limits from measured resources — not performance claims."""
    avail = float(mem.get("available_gib") or 0)
    total = float(mem.get("total_gib") or 0)
    logical = int(cpu.get("logical_cpus") or 1)
    free_disk = float(disk.get("free_gib") or 0)

    # Indexing: keep light on low RAM
    if avail >= 8:
        index_workers = min(4, max(1, logical // 2))
        index_ram_gib = 1.5
    elif avail >= 4:
        index_workers = min(2, logical)
        index_ram_gib = 0.75
    else:
        index_workers = 1
        index_ram_gib = 0.35

    if avail >= 8:
        browser_workers = 2
        browser_ram_gib = 1.0
    elif avail >= 4:
        browser_workers = 1
        browser_ram_gib = 0.75
    else:
        browser_workers = 0
        browser_ram_gib = 0.0

    test_workers = min(4, max(1, logical // 2)) if avail >= 4 else 1

    # Optional CPU inference budget = available - safety - browser - index reserve
    inference_budget = max(0.0, avail - SAFETY_MARGIN_GIB - browser_ram_gib - index_ram_gib)
    if free_disk < 5:
        inference_budget = 0.0

    return {
        "basis": {
            "available_gib_measured": avail,
            "total_gib_measured": total,
            "logical_cpus_measured": logical,
            "free_disk_gib_measured": free_disk,
        },
        "indexing": {
            "max_workers": index_workers,
            "ram_reserve_gib": index_ram_gib,
        },
        "browser_workers": {
            "max_workers": browser_workers,
            "ram_reserve_gib": browser_ram_gib,
            "engine": "playwright",
        },
        "tests": {
            "max_workers": test_workers,
        },
        "optional_cpu_inference": {
            "ram_budget_gib": round(inference_budget, 2),
            "required": False,
            "note": "Budget for optional local models only; zero is valid.",
        },
        "docker_desktop": {
            "required_for_core": False,
        },
    }


def estimate_model_fit(mem: dict[str, Any], limits: dict[str, Any]) -> dict[str, Any]:
    budget = float(limits["optional_cpu_inference"]["ram_budget_gib"])
    avail = float(mem.get("available_gib") or 0)
    rows: list[dict[str, Any]] = []
    for model in MODEL_CATALOG:
        weights = float(model["weights_gib"])
        ctx = int(model["default_ctx"])
        params_b = float(model["params_b"])
        kv = params_b * (ctx / 1000.0) * KV_GIB_PER_BPARAM_PER_1K_CTX
        total_est = weights + kv + RUNTIME_OVERHEAD_GIB
        # Verify against measurement: need estimate + margin under *current* available
        # and under derived inference budget.
        fits_available = (total_est + SAFETY_MARGIN_GIB) <= avail
        fits_budget = total_est <= budget
        verified_fit = bool(mem.get("measured")) and fits_available and fits_budget and budget > 0
        rows.append(
            {
                "id": model["id"],
                "estimate_only": {
                    "weights_gib": weights,
                    "kv_cache_gib_est": round(kv, 3),
                    "runtime_overhead_gib": RUNTIME_OVERHEAD_GIB,
                    "total_gib_est": round(total_est, 2),
                    "ctx_tokens": ctx,
                    "formula_note": (
                        "total ≈ weights + (params_b * ctx/1000 * "
                        f"{KV_GIB_PER_BPARAM_PER_1K_CTX}) + overhead; order-of-magnitude."
                    ),
                },
                "measurement_check": {
                    "available_gib": avail,
                    "inference_budget_gib": budget,
                    "safety_margin_gib": SAFETY_MARGIN_GIB,
                    "fits_available_with_margin": fits_available,
                    "fits_inference_budget": fits_budget,
                    "verified_fit": verified_fit,
                },
                "recommendation": (
                    "eligible_to_consider"
                    if verified_fit
                    else "do_not_recommend_until_more_ram_or_smaller_ctx"
                ),
                "notes": model["notes"],
                "tokens_per_sec": "unmeasured",
                "downloaded": False,
            }
        )

    recommended = [r["id"] for r in rows if r["recommendation"] == "eligible_to_consider"]
    return {
        "catalog_policy": "No model files downloaded by doctor.",
        "kv_and_overhead_are_estimates": True,
        "performance_claims": "none — throughput unmeasured",
        "models": rows,
        "recommended_ids": recommended,
        "recommendation_rule": (
            "Recommend only when measured available RAM and inference budget both cover "
            "estimated weights+KV+overhead with safety margin."
        ),
    }


def background_job_limitations(host: dict[str, Any]) -> dict[str, Any]:
    return {
        "startup": {
            "doctor_enables_startup_tasks": False,
            "limitation": (
                "Windows logon/startup task registration is not performed by doctor. "
                "OpenClaw Gateway scheduling requires an explicitly running Gateway process."
            ),
            "action": "Start Gateway manually when needed; do not assume auto-start.",
        },
        "sleep": {
            "limitation": (
                "Sleep/hibernate suspends user processes; cron/automations inside a local Gateway "
                "will not fire while the PC is asleep."
            ),
            "action": "Keep the machine awake for scheduled local jobs, or accept missed windows.",
        },
        "offline": {
            "limitation": (
                "Offline: deterministic MAINFRAME automation and local FreeForge SQLite work. "
                "Hosted models and channel delivery need network. "
                "public-apis discovery uses the local pinned snapshot (no endpoint fan-out)."
            ),
            "action": (
                "Use `python -m mainframe run|scorecard|accept|discovery search` offline; "
                "pause AI if unreachable."
            ),
        },
        "host_context": host["kind"],
        "docker_desktop_required": False,
    }


def build_findings(
    host: dict[str, Any],
    mem: dict[str, Any],
    disk: dict[str, Any],
    runtimes: dict[str, Any],
    browsers: dict[str, Any],
    limits: dict[str, Any],
    fit: dict[str, Any],
) -> list[Finding]:
    findings: list[Finding] = []
    if not host["trust_hardware_as_user_pc"]:
        findings.append(
            Finding(
                "warn",
                "host_context_untrusted",
                f"Host context is {host['kind']}; measured hardware must not be treated as the user's physical PC.",
                "Re-run doctor on the target Windows desktop session (not a remote container).",
            )
        )
    else:
        findings.append(
            Finding(
                "info",
                "host_context_native_windows",
                "Measurements taken in a native Windows process context.",
                None,
            )
        )

    if not mem.get("measured"):
        findings.append(
            Finding("action", "ram_unmeasured", "RAM could not be measured.", "Allow PowerShell CIM queries and re-run doctor.")
        )
    elif float(mem.get("available_gib") or 0) < 2:
        findings.append(
            Finding(
                "action",
                "ram_low",
                f"Only {mem.get('available_gib')} GiB available.",
                "Close browsers/IDEs before optional local inference; keep inference budget at 0 if needed.",
            )
        )

    if float(disk.get("free_gib") or 0) < 5:
        findings.append(
            Finding(
                "action",
                "disk_low",
                f"Free disk on workspace volume is {disk.get('free_gib')} GiB.",
                "Free at least 5 GiB before pulling any local model weights.",
            )
        )

    if not runtimes["git"]["present"]:
        findings.append(
            Finding("action", "git_missing", "Git not found on PATH.", "Install Git for Windows (free) if repo workflows need it.")
        )
    if not runtimes["ripgrep"]["present"]:
        findings.append(
            Finding(
                "warn",
                "rg_missing",
                "ripgrep (rg) not found on PATH.",
                "Optional: install ripgrep for faster search; MAINFRAME core does not require it.",
            )
        )

    pw = browsers.get("playwright") or {}
    if pw.get("status") != "available":
        findings.append(
            Finding(
                "warn",
                "playwright_paused",
                f"Playwright browser probe: {pw.get('status')} — {pw.get('detail')}",
                "Install Playwright browsers locally if FreeForge browser checks are needed; no cloud browser required.",
            )
        )
    else:
        findings.append(
            Finding("info", "playwright_ok", "Playwright Chromium launched successfully (about:blank).", None)
        )

    if runtimes["docker"]["present"]:
        findings.append(
            Finding(
                "info",
                "docker_present_not_required",
                "Docker found on PATH but is not required for MAINFRAME/FreeForge core.",
                "Do not treat Docker Desktop license/state as a core dependency.",
            )
        )

    if not fit["recommended_ids"]:
        findings.append(
            Finding(
                "info",
                "no_model_recommended",
                "No catalog model passed measured fit checks; optional CPU inference stays paused/unused.",
                "Do not download large models based on doctor output alone.",
            )
        )
    else:
        findings.append(
            Finding(
                "info",
                "models_eligible_estimate",
                "Eligible to consider (fit estimate verified against measured RAM/budget): "
                + ", ".join(fit["recommended_ids"]),
                "Throughput still unmeasured; pull only if you choose, outside doctor.",
            )
        )

    findings.append(
        Finding(
            "info",
            "resource_limits_set",
            (
                f"Limits: index_workers={limits['indexing']['max_workers']}, "
                f"browser_workers={limits['browser_workers']['max_workers']}, "
                f"test_workers={limits['tests']['max_workers']}, "
                f"inference_budget_gib={limits['optional_cpu_inference']['ram_budget_gib']}"
            ),
            None,
        )
    )
    findings.append(
        Finding(
            "info",
            "no_startup_mutation",
            "Doctor did not enable startup tasks, install services, or download models.",
            None,
        )
    )
    return findings


def run_doctor() -> dict[str, Any]:
    ensure_state()
    started = time.perf_counter()
    host = detect_host_context()
    mem = measure_memory()
    cpu = measure_cpu()
    disk = measure_disk()
    runtimes = measure_runtimes()
    shell = measure_shell()
    browsers = measure_browsers()
    limits = derive_resource_limits(mem, cpu, disk)
    fit = estimate_model_fit(mem, limits)
    # If host context is untrusted, strip recommendations that imply user's PC capacity.
    if not host["trust_hardware_as_user_pc"]:
        fit = {
            **fit,
            "recommended_ids": [],
            "models": [
                {**m, "recommendation": "withheld_host_context_untrusted", "measurement_check": {
                    **m["measurement_check"],
                    "verified_fit": False,
                }}
                for m in fit["models"]
            ],
            "recommendation_rule": (
                "Recommendations withheld because hardware may be a container/VM slice, not the user PC."
            ),
        }
        limits = {
            **limits,
            "note": "Limits computed from this environment's view; re-run on native Windows before trusting them.",
        }

    bg = background_job_limitations(host)
    findings = build_findings(host, mem, disk, runtimes, browsers, limits, fit)
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    report = {
        "suite": "mainframe-doctor",
        "generated_at": _utc(),
        "duration_ms": elapsed_ms,
        "target": "windows_user_pc",
        "host_context": host,
        "memory": mem,
        "cpu": cpu,
        "disk": disk,
        "runtimes": runtimes,
        "shell": shell,
        "browsers": browsers,
        "resource_limits": limits,
        "model_fit": fit,
        "background_jobs": bg,
        "findings": [f.to_dict() for f in findings],
        "secrets_exposed": False,
        "models_downloaded": False,
        "startup_tasks_enabled": False,
        "performance_benchmarks_claimed": False,
        "ok": True,
    }
    # Persist under .mainframe/runs without secrets
    runs = ROOT / ".mainframe" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = runs / f"doctor-{stamp}.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    report["report_path"] = str(path.relative_to(ROOT)).replace("\\", "/")
    return report
