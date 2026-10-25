"""
Post-deployment verification script.

Polls the deep diagnostics endpoint (/health/deep) of the deployed Container App
to verify that all subsystems (Fabric SQL, VoiceLive Auth, Analytics Agent)
are live, responding, and healthy.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request


def write_github_summary(report: dict, target_url: str) -> None:
    summary_file = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_file:
        return

    status = report.get("status", "unknown").upper()
    badge = "🟢" if status == "HEALTHY" else "🔴"
    timestamp = report.get("timestamp", "")
    components = report.get("components", {})

    lines = [
        f"## {badge} Post-Deployment Component Verification: {status}",
        f"**Target URL:** `{target_url}`",
        f"**Verification Timestamp:** `{timestamp}`",
        "",
        "| Subsystem | Status | Latency | Details |",
        "| :--- | :---: | :---: | :--- |",
    ]

    for name, comp in components.items():
        comp_status = comp.get("status", "unknown").upper()
        comp_badge = "✅" if comp_status == "OK" else "❌"
        latency = f"{comp.get('latency_ms', 0)} ms"
        msg = comp.get("message", "")
        lines.append(f"| **{name.replace('_', ' ').title()}** | {comp_badge} `{comp_status}` | {latency} | {msg} |")

    lines.append("")

    try:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception as e:
        print(f"Failed to write GITHUB_STEP_SUMMARY: {e}", file=sys.stderr)


def print_cli_summary(report: dict, target_url: str) -> None:
    status = report.get("status", "unknown").upper()
    components = report.get("components", {})

    print("\n" + "=" * 70)
    print(f"POST-DEPLOYMENT COMPONENT VERIFICATION: {status}")
    print(f"Target: {target_url}")
    print("-" * 70)
    print(f"{'Component':<20} {'Status':<10} {'Latency':<12} {'Details'}")
    print("-" * 70)
    for name, comp in components.items():
        comp_name = name.replace("_", " ").title()
        comp_status = comp.get("status", "unknown").upper()
        latency = f"{comp.get('latency_ms', 0)} ms"
        msg = comp.get("message", "")
        print(f"{comp_name:<20} {comp_status:<10} {latency:<12} {msg}")
    print("=" * 70 + "\n")


def poll_health_endpoint(target_url: str, timeout_seconds: int = 180, interval_seconds: int = 10) -> bool:
    endpoint = target_url.rstrip("/") + "/health/deep"
    print(f"Polling {endpoint} (timeout: {timeout_seconds}s, interval: {interval_seconds}s)...")

    start_time = time.time()
    last_report = None

    while time.time() - start_time < timeout_seconds:
        elapsed = int(time.time() - start_time)
        try:
            req = urllib.request.Request(
                endpoint,
                headers={"User-Agent": "GitHub-Actions-Deployment-Verifier/1.0"},
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                status_code = response.getcode()
                raw_body = response.read().decode("utf-8")
                try:
                    last_report = json.loads(raw_body)
                except json.JSONDecodeError:
                    last_report = {"status": "unhealthy", "message": raw_body}

                if status_code == 200 and last_report.get("status") == "healthy":
                    print(f"✓ Health check succeeded after {elapsed}s.")
                    print_cli_summary(last_report, endpoint)
                    write_github_summary(last_report, endpoint)
                    return True
                else:
                    print(f"[{elapsed}s] Server returned HTTP {status_code} - not healthy yet...")

        except urllib.error.HTTPError as e:
            try:
                raw_body = e.read().decode("utf-8")
                last_report = json.loads(raw_body)
            except Exception:
                last_report = {"status": "error", "message": str(e)}
            print(f"[{elapsed}s] HTTP {e.code}: {e.reason}")

        except Exception as e:
            print(f"[{elapsed}s] Connection attempt failed: {e}")

        time.sleep(interval_seconds)

    print(f"\n❌ Verification timed out after {timeout_seconds}s!")
    if last_report:
        print_cli_summary(last_report, endpoint)
        write_github_summary(last_report, endpoint)
    return False


def main():
    target = None
    if len(sys.argv) > 1 and sys.argv[1].strip():
        target = sys.argv[1].strip()
    else:
        target = os.getenv("APPLICATION_URL") or os.getenv("APP_URL")

    if not target:
        print("Usage: python scripts/verify_deployment.py <APPLICATION_URL>", file=sys.stderr)
        sys.exit(1)

    if not target.startswith("http://") and not target.startswith("https://"):
        target = f"https://{target}"

    success = poll_health_endpoint(target)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
