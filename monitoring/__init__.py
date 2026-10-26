"""
Silks.AI Fail-Loud Monitoring, Health & Calibration Contracts Package.
"""
from .health import record, monitored, get_pipeline_health
from .hkjc_guard import HKJCDateMismatch, HKJCFetchError, validate_hkjc_html, fetch_hkjc
from .contracts import (
    compute_sha_tin_calibrations,
    validate_racecard_contract,
    validate_odds_contract,
    validate_incident_contract,
    validate_features_contract,
)

__all__ = [
    "record",
    "monitored",
    "get_pipeline_health",
    "HKJCDateMismatch",
    "HKJCFetchError",
    "validate_hkjc_html",
    "fetch_hkjc",
    "compute_sha_tin_calibrations",
    "validate_racecard_contract",
    "validate_odds_contract",
    "validate_incident_contract",
    "validate_features_contract",
]
