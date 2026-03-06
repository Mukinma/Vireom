import json
import logging
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


LOGGER = logging.getLogger("camerapi.plots")


def setup_logging() -> None:
    Path("logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s level=%(levelname)s logger=%(name)s msg=%(message)s",
        handlers=[
            logging.FileHandler("logs/generate_plots.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def create_confidence_histogram(results_df: pd.DataFrame, out_dir: Path) -> None:
    genuine = results_df[results_df["scenario"] == "genuine"]["confianza"]
    impostor = results_df[results_df["scenario"] == "impostor"]["confianza"]

    plt.figure(figsize=(10, 6))
    plt.hist(genuine, bins=25, alpha=0.65, label="Genuine", color="#2563eb")
    plt.hist(impostor, bins=25, alpha=0.65, label="Impostor", color="#dc2626")
    plt.xlabel("Confianza LBPH (menor es mejor)")
    plt.ylabel("Frecuencia")
    plt.title("Histograma comparativo de confianzas")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "confidence_histogram.png", dpi=150)
    plt.close()


def create_far_frr_curve(curve_df: pd.DataFrame, out_dir: Path) -> None:
    plt.figure(figsize=(10, 6))
    plt.plot(curve_df["threshold"], curve_df["far"], label="FAR", color="#dc2626")
    plt.plot(curve_df["threshold"], curve_df["frr"], label="FRR", color="#2563eb")
    plt.xlabel("Umbral")
    plt.ylabel("Tasa")
    plt.title("Curva FAR vs FRR")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "far_frr_curve.png", dpi=150)
    plt.close()


def create_latency_distribution(results_df: pd.DataFrame, out_dir: Path) -> None:
    plt.figure(figsize=(10, 6))
    plt.hist(results_df["inferencia_ms"], bins=30, color="#16a34a", alpha=0.75)
    plt.xlabel("Latencia de inferencia (ms)")
    plt.ylabel("Frecuencia")
    plt.title("Distribución de latencia de inferencia")
    plt.tight_layout()
    plt.savefig(out_dir / "latency_distribution.png", dpi=150)
    plt.close()


def create_apa_table(metrics: dict, out_dir: Path) -> None:
    rows = [
        {"Métrica": "Media confianza genuina", "Valor": f"{metrics['mean_confidence_genuine']:.4f}"},
        {"Métrica": "Media confianza impostor", "Valor": f"{metrics['mean_confidence_impostor']:.4f}"},
        {"Métrica": "Desv. estándar genuina", "Valor": f"{metrics['std_confidence_genuine']:.4f}"},
        {"Métrica": "Desv. estándar impostor", "Valor": f"{metrics['std_confidence_impostor']:.4f}"},
        {"Métrica": "Latencia media (ms)", "Valor": f"{metrics['mean_latency_ms']:.4f}"},
        {"Métrica": "Umbral óptimo", "Valor": f"{metrics['optimal_threshold']:.4f}"},
        {"Métrica": "EER", "Valor": f"{((metrics['eer_far'] + metrics['eer_frr']) / 2):.4f}"},
        {"Métrica": "FAR", "Valor": f"{metrics['far']:.4f}"},
        {"Métrica": "FRR", "Valor": f"{metrics['frr']:.4f}"},
        {"Métrica": "Accuracy", "Valor": f"{metrics['accuracy']:.4f}"},
        {"Métrica": "Precision", "Valor": f"{metrics['precision']:.4f}"},
        {"Métrica": "Recall", "Valor": f"{metrics['recall']:.4f}"},
    ]
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "apa_summary_table.csv", index=False)
    md_lines = ["| Métrica | Valor |", "|---|---|"]
    for row in rows:
        md_lines.append(f"| {row['Métrica']} | {row['Valor']} |")
    (out_dir / "apa_summary_table.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")


def main() -> int:
    setup_logging()

    results_path = Path("logs/experimental_results.csv")
    curve_path = Path("logs/far_frr_curve.csv")
    metrics_path = Path("logs/statistical_metrics.json")

    if not results_path.exists() or not curve_path.exists() or not metrics_path.exists():
        raise RuntimeError("Faltan resultados previos. Ejecutar experimental_validation.py y statistical_analysis.py")

    results_df = pd.read_csv(results_path)
    curve_df = pd.read_csv(curve_path)
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))

    out_dir = Path("logs/plots")
    out_dir.mkdir(parents=True, exist_ok=True)

    create_confidence_histogram(results_df, out_dir)
    create_far_frr_curve(curve_df, out_dir)
    create_latency_distribution(results_df, out_dir)
    create_apa_table(metrics, out_dir)

    LOGGER.info("plots_generated dir=%s", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
