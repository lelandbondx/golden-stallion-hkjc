"""
Model Training Entrypoint & Metadata Recorder for Silks.AI.
Replaces the broken `scratch_train.py` reference in `.github/workflows/auto_update_data.yml`.
Trains the XGBoost model via `model.train_and_save_model()`, records `data/model_meta.json`,
and updates `data/pipeline_health.json`.
"""
import os
import json
import hashlib
from datetime import datetime, timezone
import model
from monitoring.health import record as record_health


def _compute_feature_hash(features_list: list) -> str:
    joined = "|".join(str(f) for f in features_list)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def main():
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    feat_hash = _compute_feature_hash(model.ALL_FEATURES)
    trained_model = model.train_and_save_model()

    train_rows = 0
    if os.path.exists("data/train_horse_features.csv"):
        try:
            with open("data/train_horse_features.csv", "r", encoding="utf-8", errors="ignore") as f:
                train_rows = max(0, sum(1 for _ in f) - 1)
        except Exception:
            train_rows = 0

    meta = {
        "trained_at": now_iso,
        "model_path": model.MODEL_PATH,
        "feature_count": len(model.ALL_FEATURES),
        "feature_list_hash": feat_hash,
        "features": model.ALL_FEATURES,
        "train_rows": train_rows,
        "model_exists": os.path.exists(model.MODEL_PATH),
    }

    os.makedirs("data", exist_ok=True)
    with open("data/model_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    if trained_model is not None or os.path.exists(model.MODEL_PATH):
        record_health(
            "model_training",
            "ok",
            metrics={
                "trained_at": now_iso,
                "feature_list_hash": feat_hash,
                "train_rows": train_rows,
            },
        )
        print(f"[TRAIN] Model verified and metadata written to data/model_meta.json (hash={feat_hash}, rows={train_rows}).")
    else:
        record_health(
            "model_training",
            "fail",
            metrics={"feature_list_hash": feat_hash},
            error="model.joblib missing and training returned None",
        )
        raise RuntimeError("Model training failed and model.joblib is missing.")


if __name__ == "__main__":
    main()
