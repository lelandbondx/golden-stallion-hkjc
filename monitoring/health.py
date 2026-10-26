"""
Lightweight Health Recording & Monitoring Core for Silks.AI.
Writes per-event JSONL records to data/health/YYYYMMDD.jsonl and maintains
the latest state per component in data/pipeline_health.json.
"""
import os
import json
import time
import functools
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEALTH_DIR = os.path.join(BASE_DIR, "data", "health")
PIPELINE_HEALTH_FILE = os.path.join(BASE_DIR, "data", "pipeline_health.json")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record(component: str, status: str, metrics: dict = None, error: str = None) -> dict:
    """
    Records a health event for `component`.
    status: 'ok' | 'warn' | 'fail'
    metrics: optional dict (e.g. rows, expected_rows, meeting_date, source_url, duration_s)
    error: optional error message string
    """
    now_iso = _utc_now_iso()
    date_tag = datetime.now(timezone.utc).strftime("%Y%m%d")
    metrics = metrics or {}

    entry = {
        "component": component,
        "status": status,
        "timestamp": now_iso,
        "metrics": metrics,
        "error": str(error) if error else None,
    }

    try:
        os.makedirs(HEALTH_DIR, exist_ok=True)
        jsonl_path = os.path.join(HEALTH_DIR, f"{date_tag}.jsonl")
        with open(jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[HEALTH WARNING] Could not append to health log: {e}")

    # Update aggregate pipeline_health.json
    try:
        os.makedirs(os.path.dirname(PIPELINE_HEALTH_FILE), exist_ok=True)
        current = {}
        if os.path.exists(PIPELINE_HEALTH_FILE):
            try:
                with open(PIPELINE_HEALTH_FILE, "r", encoding="utf-8") as f:
                    current = json.load(f)
            except Exception as read_err:
                print(f"[HEALTH WARNING] Resetting corrupted pipeline_health.json: {read_err}")
                current = {}

        components = current.get("components", {})
        prev = components.get(component, {})
        last_success = now_iso if status == "ok" else prev.get("last_success_at")

        components[component] = {
            "status": status,
            "last_attempt_at": now_iso,
            "last_success_at": last_success,
            "metrics": metrics,
            "error": str(error) if error else None,
        }

        # Compute overall status
        statuses = [c.get("status") for c in components.values()]
        if "fail" in statuses:
            overall = "fail"
        elif "warn" in statuses:
            overall = "warn"
        else:
            overall = "ok"

        payload = {
            "overall_status": overall,
            "updated_at": now_iso,
            "components": components,
        }
        with open(PIPELINE_HEALTH_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[HEALTH WARNING] Could not update pipeline_health.json: {e}")

    return entry


def monitored(component: str):
    """
    Decorator for scraper and pipeline entrypoints.
    Records execution duration and status ('ok' or 'fail'), and re-raises uncaught exceptions.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            t0 = time.time()
            try:
                result = func(*args, **kwargs)
                duration = round(time.time() - t0, 3)
                metrics = {"duration_s": duration}
                if isinstance(result, dict):
                    if result.get("status") == "error":
                        record(component, "fail", metrics=metrics, error=result.get("reason", "Unknown error"))
                        return result
                    if "meetings" in result:
                        metrics["meetings_count"] = len(result.get("meetings") or [])
                elif hasattr(result, "__len__"):
                    metrics["rows"] = len(result)
                record(component, "ok", metrics=metrics)
                return result
            except Exception as exc:
                duration = round(time.time() - t0, 3)
                record(component, "fail", metrics={"duration_s": duration}, error=f"{type(exc).__name__}: {exc}")
                raise
        return wrapper
    return decorator


def get_pipeline_health() -> dict:
    """
    Returns the current pipeline health dictionary from data/pipeline_health.json.
    """
    if os.path.exists(PIPELINE_HEALTH_FILE):
        try:
            with open(PIPELINE_HEALTH_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            return {"overall_status": "fail", "error": f"Corrupted health file: {e}", "components": {}}
    return {"overall_status": "warn", "components": {}}
