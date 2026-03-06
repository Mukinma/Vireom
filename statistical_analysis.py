import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd


LOGGER = logging.getLogger("camerapi.stats")


def setup_logging() -> None:
    Path("logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s level=%(levelname)s logger=%(name)s msg=%(message)s",
        handlers=[
            logging.FileHandler("logs/statistical_analysis.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def evaluate_threshold(df: pd.DataFrame, threshold: float) -> dict:
    genuine = df[df["scenario"] == "genuine"].copy()
    impostor = df[df["scenario"] == "impostor"].copy()

    genuine["accepted"] = (genuine["user_predicho"] == genuine["claimed_user"]) & (genuine["confianza"] <= threshold)
    impostor["accepted"] = (impostor["user_predicho"] == impostor["claimed_user"]) & (impostor["confianza"] <= threshold)

    tp = int(genuine["accepted"].sum())
    fn = int((~genuine["accepted"]).sum())
    fp = int(impostor["accepted"].sum())
    tn = int((~impostor["accepted"]).sum())

    far = fp / max(1, len(impostor))
    frr = fn / max(1, len(genuine))
    accuracy = (tp + tn) / max(1, tp + tn + fp + fn)
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)

    return {
        "threshold": float(threshold),
        "far": float(far),
        "frr": float(frr),
        "accuracy": float(accuracy),
        "precision": float(precision),
        "recall": float(recall),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
    }


def compute_metrics(df: pd.DataFrame) -> dict:
    genuine = df[df["scenario"] == "genuine"]
    impostor = df[df["scenario"] == "impostor"]

    if genuine.empty or impostor.empty:
        raise RuntimeError("El CSV experimental debe contener escenarios genuine e impostor")

    confidence_values = df["confianza"].to_numpy(dtype=float)
    min_conf, max_conf = float(np.min(confidence_values)), float(np.max(confidence_values))
    thresholds = np.linspace(min_conf, max_conf, 400)

    curve = [evaluate_threshold(df, float(th)) for th in thresholds]
    curve_df = pd.DataFrame(curve)

    curve_df["eer_gap"] = (curve_df["far"] - curve_df["frr"]).abs()
    eer_row = curve_df.sort_values(["eer_gap", "threshold"]).iloc[0]

    curve_df["cost"] = curve_df["far"] + curve_df["frr"] + (curve_df["far"] - curve_df["frr"]).abs() * 0.5
    best_row = curve_df.sort_values(["cost", "threshold"]).iloc[0]

    metrics = {
        "mean_confidence_genuine": float(genuine["confianza"].mean()),
        "mean_confidence_impostor": float(impostor["confianza"].mean()),
        "std_confidence_genuine": float(genuine["confianza"].std(ddof=0)),
        "std_confidence_impostor": float(impostor["confianza"].std(ddof=0)),
        "mean_latency_ms": float(df["inferencia_ms"].mean()),
        "std_latency_ms": float(df["inferencia_ms"].std(ddof=0)),
        "n_genuine": int(len(genuine)),
        "n_impostor": int(len(impostor)),
        "eer_threshold": float(eer_row["threshold"]),
        "eer_far": float(eer_row["far"]),
        "eer_frr": float(eer_row["frr"]),
        "optimal_threshold": float(best_row["threshold"]),
        "far": float(best_row["far"]),
        "frr": float(best_row["frr"]),
        "accuracy": float(best_row["accuracy"]),
        "precision": float(best_row["precision"]),
        "recall": float(best_row["recall"]),
        "tp": int(best_row["tp"]),
        "tn": int(best_row["tn"]),
        "fp": int(best_row["fp"]),
        "fn": int(best_row["fn"]),
    }

    return {"metrics": metrics, "curve_df": curve_df}


def write_report(metrics: dict, report_path: Path) -> None:
    lines = [
        "=== REPORTE ESTADÍSTICO EXPERIMENTAL LBPH ===",
        f"n_genuine={metrics['n_genuine']}",
        f"n_impostor={metrics['n_impostor']}",
        f"media_confianza_genuine={metrics['mean_confidence_genuine']:.6f}",
        f"media_confianza_impostor={metrics['mean_confidence_impostor']:.6f}",
        f"desv_confianza_genuine={metrics['std_confidence_genuine']:.6f}",
        f"desv_confianza_impostor={metrics['std_confidence_impostor']:.6f}",
        f"media_latencia_ms={metrics['mean_latency_ms']:.6f}",
        f"desv_latencia_ms={metrics['std_latency_ms']:.6f}",
        f"EER_threshold={metrics['eer_threshold']:.6f}",
        f"EER_FAR={metrics['eer_far']:.6f}",
        f"EER_FRR={metrics['eer_frr']:.6f}",
        f"threshold_optimo={metrics['optimal_threshold']:.6f}",
        f"FAR={metrics['far']:.6f}",
        f"FRR={metrics['frr']:.6f}",
        f"Accuracy={metrics['accuracy']:.6f}",
        f"Precision={metrics['precision']:.6f}",
        f"Recall={metrics['recall']:.6f}",
        f"TP={metrics['tp']}",
        f"TN={metrics['tn']}",
        f"FP={metrics['fp']}",
        f"FN={metrics['fn']}",
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    setup_logging()

    csv_path = Path("logs/experimental_results.csv")
    if not csv_path.exists():
        raise RuntimeError("No existe logs/experimental_results.csv")

    df = pd.read_csv(csv_path)
    required_columns = {"scenario", "claimed_user", "user_real", "user_predicho", "confianza", "inferencia_ms"}
    if not required_columns.issubset(set(df.columns)):
        missing = required_columns - set(df.columns)
        raise RuntimeError(f"CSV experimental incompleto. Faltan columnas: {sorted(missing)}")

    results = compute_metrics(df)
    metrics = results["metrics"]
    curve_df = results["curve_df"]

    report_path = Path("logs/statistical_report.txt")
    write_report(metrics, report_path)

    curve_path = Path("logs/far_frr_curve.csv")
    curve_df.to_csv(curve_path, index=False)

    metrics_path = Path("logs/statistical_metrics.json")
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")

    LOGGER.info("statistical_report_written path=%s", report_path)
    LOGGER.info("curve_written path=%s rows=%s", curve_path, len(curve_df))
    LOGGER.info("metrics_written path=%s", metrics_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
