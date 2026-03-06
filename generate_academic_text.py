import json
import logging
from pathlib import Path


LOGGER = logging.getLogger("camerapi.academic")


def setup_logging() -> None:
    Path("logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s level=%(levelname)s logger=%(name)s msg=%(message)s",
        handlers=[
            logging.FileHandler("logs/generate_academic_text.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def load_metrics() -> dict:
    metrics_path = Path("logs/statistical_metrics.json")
    if not metrics_path.exists():
        raise RuntimeError("No existe logs/statistical_metrics.json")
    return json.loads(metrics_path.read_text(encoding="utf-8"))


def load_bootstrap_summary() -> dict:
    bootstrap_path = Path("logs/bootstrap_report.json")
    if not bootstrap_path.exists():
        return {}
    return json.loads(bootstrap_path.read_text(encoding="utf-8"))


def build_methodology_text(metrics: dict, bootstrap: dict) -> str:
    users = bootstrap.get("total_users_detected", "N/D")
    samples = bootstrap.get("total_valid_samples", "N/D")
    return f"""
Capítulo 3 – Metodología

Se diseñó una validación experimental para un sistema biométrico facial embebido basado en técnicas clásicas de visión por computadora. Se empleó detección de rostro mediante Haar Cascade y reconocimiento de identidad mediante LBPH, manteniéndose una operación local sin servicios en la nube y sin modelos de aprendizaje profundo.

El dataset fue organizado por usuario en carpetas con estructura `dataset/user_<id>/`. Durante el preprocesamiento, se verificó la existencia física de cada imagen, se realizó conversión a escala de grises, se detectó un único rostro por imagen y se generó una región de interés normalizada a 200x200 píxeles. Las muestras válidas fueron registradas en base de datos SQLite y almacenadas en un repositorio procesado. Para garantizar consistencia experimental, se estableció un mínimo de muestras válidas por usuario antes del entrenamiento del modelo.

La fase experimental se estructuró con ensayos genuinos e impostores. Para cada usuario, fueron ejecutadas 30 predicciones genuinas y 30 predicciones cruzadas. En cada inferencia se registraron identidad real, identidad predicha, nivel de confianza LBPH y tiempo de inferencia en milisegundos. Posteriormente, se estimaron métricas biométricas y de clasificación (FAR, FRR, Accuracy, Precision y Recall), así como el punto EER y un umbral óptimo determinado por minimización conjunta de FAR/FRR.

El protocolo de validación fue alineado con el objetivo general del proyecto Protocolo_PI_4E_2026, orientado al diseño de un mecanismo de control de acceso facial robusto, reproducible y trazable para despliegue embebido.

Resumen de dataset experimental utilizado: usuarios detectados={users}, muestras válidas={samples}.
""".strip() + "\n"


def build_results_text(metrics: dict) -> str:
    eer = (metrics["eer_far"] + metrics["eer_frr"]) / 2.0
    return f"""
Capítulo 4 – Resultados

La evaluación experimental fue ejecutada sobre el modelo LBPH entrenado con muestras faciales preprocesadas. Se observó una media de confianza en condiciones genuinas de {metrics['mean_confidence_genuine']:.4f}, mientras que para escenarios impostores se obtuvo una media de {metrics['mean_confidence_impostor']:.4f}. Las dispersiones asociadas fueron {metrics['std_confidence_genuine']:.4f} y {metrics['std_confidence_impostor']:.4f}, respectivamente.

El umbral óptimo fue estimado en {metrics['optimal_threshold']:.4f}. Bajo dicho umbral se registraron FAR={metrics['far']:.4f} y FRR={metrics['frr']:.4f}. Se identificó un punto de equilibrio de error (EER) aproximado de {eer:.4f}, con umbral de equilibrio en {metrics['eer_threshold']:.4f}.

En términos de desempeño de clasificación, fueron obtenidos Accuracy={metrics['accuracy']:.4f}, Precision={metrics['precision']:.4f} y Recall={metrics['recall']:.4f}. La latencia promedio de inferencia fue {metrics['mean_latency_ms']:.4f} ms, lo cual evidencia viabilidad de ejecución local en plataforma embebida, sujeta a verificación final en hardware objetivo.

Los resultados obtenidos sustentan el objetivo general del proyecto Protocolo_PI_4E_2026, al demostrar que un enfoque clásico Haar+LBPH puede ser evaluado con trazabilidad estadística y criterios biométricos formales en un entorno local sin dependencia de deep learning.
""".strip() + "\n"


def build_ieee_text(metrics: dict) -> str:
    return f"""
IEEE-Style Results Paragraph

An embedded, fully local facial biometric pipeline based on Haar Cascade detection and LBPH recognition was experimentally evaluated under genuine and impostor conditions. Confidence and inference latency were recorded for each prediction. The optimal threshold was experimentally estimated at {metrics['optimal_threshold']:.4f}, yielding FAR={metrics['far']:.4f}, FRR={metrics['frr']:.4f}, and EER≈{((metrics['eer_far'] + metrics['eer_frr']) / 2.0):.4f}. Classification performance reached Accuracy={metrics['accuracy']:.4f}, Precision={metrics['precision']:.4f}, and Recall={metrics['recall']:.4f}. The measured average inference latency was {metrics['mean_latency_ms']:.4f} ms, supporting the feasibility of classical computer-vision biometrics for resource-constrained offline access control aligned with Protocolo_PI_4E_2026.
""".strip() + "\n"


def main() -> int:
    setup_logging()
    metrics = load_metrics()
    bootstrap = load_bootstrap_summary()

    chapter3 = build_methodology_text(metrics, bootstrap)
    chapter4 = build_results_text(metrics)
    ieee = build_ieee_text(metrics)

    Path("logs/chapter3_metodologia.txt").write_text(chapter3, encoding="utf-8")
    Path("logs/chapter4_resultados.txt").write_text(chapter4, encoding="utf-8")
    Path("logs/ieee_draft.txt").write_text(ieee, encoding="utf-8")

    LOGGER.info("academic_text_generated files=chapter3_metodologia.txt,chapter4_resultados.txt,ieee_draft.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
