# Vireom

**Sistema biométrico facial embebido** para control de acceso en Raspberry Pi 5.  
100 % offline — sin deep learning, sin servicios en la nube.

---

## Problema que resuelve

Los sistemas de control de acceso biométrico comerciales dependen de servicios cloud, hardware propietario o modelos de deep learning pesados. **Vireom** demuestra que es viable construir un sistema funcional y medible usando únicamente algoritmos clásicos de visión por computadora sobre hardware de bajo coste.

## Características principales

- **Detección facial** con Haar Cascades (`haarcascade_frontalface_default.xml`)
- **Reconocimiento facial** con LBPH (`cv2.face.LBPHFaceRecognizer`)
- **API REST** + interfaz web operativa y panel de administración
- **Activación de hardware** (relé 12 V vía GPIO)
- **Base de datos local** SQLite — sin dependencias externas
- **Pipeline determinista**: Frame → Grayscale → Haar → ROI → Resize 200×200 → LBPH → Umbral → Decisión → Registro → GPIO
- Scripts de validación cruzada, análisis estadístico y calibración de umbral incluidos

## Tecnologías

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.9+ |
| Visión | OpenCV 4 (contrib) + Haar + LBPH |
| Backend | FastAPI + Uvicorn |
| Frontend | HTML / CSS / Vanilla JS (offline) |
| Base de datos | SQLite 3 (WAL mode) |
| Hardware | Raspberry Pi 5 · GPIO · Relé 12 V |
| Templates | Jinja2 |

## Arquitectura

```
┌──────────────────────────────────────────────────┐
│                   main.py                        │
│        (orquestador, hilos, lifespan)            │
├────────┬────────┬──────────┬─────────────────────┤
│ vision │  api   │ database │     hardware        │
│ camera │ routes │  db.py   │  gpio_control.py    │
│detector│        │schema.sql│                     │
│recognzr│        │          │                     │
│trainer │        │          │                     │
├────────┴────────┴──────────┴─────────────────────┤
│                  frontend/                       │
│        templates + static (CSS/JS/icons)         │
└──────────────────────────────────────────────────┘
```

## Estructura del proyecto

```
Vireom/
├── main.py                  # Punto de entrada, orquestador
├── config.py                # Configuración centralizada (dataclass)
├── init_db.py               # Inicialización de la base de datos
├── requirements.txt         # Dependencias Python
├── api/
│   └── routes.py            # Endpoints FastAPI
├── database/
│   ├── db.py                # Capa de acceso a SQLite
│   └── schema.sql           # Esquema DDL
├── vision/
│   ├── camera.py            # Captura de cámara (hilo dedicado)
│   ├── detector.py          # Detección Haar Cascade
│   ├── recognizer.py        # Reconocimiento LBPH
│   └── trainer.py           # Entrenamiento del modelo
├── hardware/
│   └── gpio_control.py      # Control de relé GPIO
├── frontend/
│   ├── templates/           # Jinja2 (index, login, admin)
│   └── static/              # CSS, JS, fuentes, iconos
├── models/                  # Modelo LBPH entrenado (.xml)
├── dataset/                 # Imágenes de entrenamiento
├── logs/                    # Logs de ejecución y reportes
├── scripts de validación    # cross_validation.py, statistical_analysis.py, etc.
├── .env.example             # Variables de entorno de referencia
└── LICENSE
```

## Requisitos previos

- Python 3.9 o superior
- Raspberry Pi 5 (recomendado) o cualquier sistema Linux/macOS con cámara
- Cámara USB o módulo CSI

## Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/Mukinma/Vireom.git
cd Vireom

# 2. Crear entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno (opcional pero recomendado)
cp .env.example .env
# Editar .env con tus valores

# 5. Inicializar base de datos
python init_db.py
```

## Ejecución

```bash
python main.py
```

La interfaz estará disponible en:

| Vista | URL |
|---|---|
| Operación (kiosco) | `http://<IP>:8000/` |
| Administración | `http://<IP>:8000/admin` |

## Modo escritorio sin navegador

Vireom también puede abrirse como **ventana nativa** en Windows, macOS y Linux sin escribir `localhost` en el navegador.

### Lanzamiento rápido

```bash
python desktop_launcher.py
```

Wrappers incluidos:

- Linux / Raspberry OS: `./run_desktop.sh`
- macOS: `./run_desktop.command`
- Windows: `run_desktop.bat`

La ventana abre por defecto el kiosco en `/`, inicia en **fullscreen** y, al cerrarla, también se detiene el servidor local.

### Requisitos de escritorio

Instala primero las dependencias Python:

```bash
pip install -r requirements.txt
```

En Linux / Raspberry OS, `pywebview` requiere además un backend gráfico compatible. Según tu entorno, instala GTK/WebKit2GTK o Qt. En Raspberry OS se recomienda verificar especialmente estos paquetes del sistema si el launcher no logra abrir la ventana.

### Acceso directo y autoarranque opcional en Raspberry OS / Linux

Puedes instalar el acceso directo de escritorio:

```bash
python install_linux_desktop_entry.py
```

Y si quieres habilitar autoarranque al iniciar sesión gráfica:

```bash
python install_linux_desktop_entry.py --autostart
```

Esto crea:

- acceso directo en `~/.local/share/applications/`
- autoarranque opcional en `~/.config/autostart/`

## Uso básico

1. Accede al panel de administración e inicia sesión.
2. Crea un usuario y captura muestras faciales desde la interfaz.
3. Entrena el modelo LBPH desde el panel.
4. El sistema está listo para reconocer — la pantalla de operación muestra el streaming y el resultado en tiempo real.

## Variables de entorno

| Variable | Descripción | Default |
|---|---|---|
| `CAMERAPI_SECRET` | Clave secreta para sesiones | `camerapi-local-secret` |
| `CAMERAPI_ADMIN_USER` | Usuario administrador | `admin` |
| `CAMERAPI_ADMIN_PASSWORD` | Contraseña administrador | `""` (debe definirse) |
| `CAMERAPI_SESSION_HTTPS_ONLY` | Marca la cookie de sesión como solo HTTPS | `false` |
| `CAMERAPI_SESSION_MAX_AGE_SECONDS` | Duración máxima de sesión | `28800` |
| `CAMERAPI_ENABLE_RESTART` | Habilita `/api/restart` solo en modo debug | `false` |
| `CAMERAPI_MAX_FPS` | FPS objetivo del stream de cámara | `30` |
| `CAMERAPI_STREAM_FPS` | FPS objetivo del video MJPEG servido al navegador | `15` |
| `CAMERAPI_PROCESS_INTERVAL_MS` | Intervalo del loop de detección/análisis | `200` |
| `CAMERAPI_CV_THREADS` | Hilos internos de OpenCV | `2` |
| `CAMERAPI_CAMERA_BUFFER_SIZE` | Buffer de captura de cámara | `1` |
| `CAMERAPI_CAMERA_JPEG_QUALITY` | Calidad JPEG del stream MJPEG | `80` |
| `CAMERAPI_CAMERA_FLIP_HORIZONTAL` | Corrige efecto espejo horizontal del stream | `true` |

> **Importante:** cambia estos valores antes de cualquier despliegue en producción.
> `CAMERAPI_ADMIN_PASSWORD` vacío deshabilita el login administrativo.
> Si tu cámara ya entrega una imagen no espejada, define `CAMERAPI_CAMERA_FLIP_HORIZONTAL=false`.

## Scripts de validación y análisis

| Script | Propósito |
|---|---|
| `cross_validation.py` | Validación cruzada Leave-One-Out |
| `session_validation.py` | Validación entre sesiones |
| `statistical_analysis.py` | Métricas FAR, FRR, EER |
| `calibrate_threshold.py` | Calibración del umbral de confianza |
| `bootstrap_dataset.py` | Carga inicial de imágenes al dataset |
| `generate_plots.py` | Generación de gráficas de resultados |
| `train_model.py` | Entrenamiento LBPH desde CLI |

## Seguridad

- Login administrativo local con sesión (`SessionMiddleware`)
- Endpoints administrativos protegidos con verificación de sesión y token CSRF
- Endpoints operativos que pueden accionar hardware requieren sesión de kiosco/admin y token CSRF
- Validación de entradas con Pydantic
- Sin dependencias de servicios externos ni transmisión de datos biométricos

## Validación local

```bash
./.venv/bin/pytest -q
npm test -- --run
PYTHONPYCACHEPREFIX=/tmp/vireom-pycache ./.venv/bin/python -m compileall -q .
./.venv/bin/python -m pip check
```

## Licencia

Este proyecto se distribuye bajo la licencia [MIT](LICENSE).

## Robustez de ejecución continua

- Reintento automático de cámara si falla apertura/lectura
- Watchdog interno para recuperación del hilo de captura
- Verificación de existencia/carga de modelo antes de reconocimiento
- Manejo robusto de errores en BD y GPIO
- Logging rotativo con `RotatingFileHandler` (5 archivos de 5MB)
- Registro de actividad y errores en `logs/system.log`
- Registro de tiempos por frame y errores críticos

## Health check

- Endpoint público mínimo: `GET /health`
- Endpoint detallado para administración: `GET /api/health/detail`
- El detalle valida cámara, modelo, BD, GPIO e incluye métricas como `avg_recognition_ms`, `fps` y `failed_attempts_consecutive`

## Prueba de estabilidad 2 horas

Ejecutar con el sistema en marcha:

```bash
python soak_test.py http://127.0.0.1:8000 7200 5
```

El script valida `/health` cada 5 segundos durante 2 horas.

## Prevalidación automática + soak 2h (con compuerta)

Flujo automatizado en `prevalidate_and_soak.py`:

1. Verifica dataset válido en BD/archivos.
2. Si falta modelo LBPH, entrena y guarda en `models/lbph_model.xml`.
3. Valida carga del modelo.
4. Ejecuta smoke test de `/health`.
5. Simula 5 accesos válidos + 5 inválidos.
6. Verifica registro en BD, activaciones GPIO y bloqueo por intentos.
7. Solo si todo pasa, ejecuta soak extendido de 2 horas.

Ejecución:

```bash
python prevalidate_and_soak.py
```

## Flujo por fases

### Fase 1 - Bootstrap dataset

```bash
python bootstrap_dataset.py
```

- Escanea `dataset/user_<id>/`
- Procesa rostro único con Haar y guarda en `dataset_processed/user_<id>/`
- Inserta `muestras` válidas en BD
- Exige mínimo 20 muestras válidas por usuario
- Genera `logs/bootstrap_report.json`

### Fase 2 - Entrenamiento LBPH

```bash
python train_model.py
```

- Usa solo usuarios con >=20 muestras válidas
- Guarda `models/lbph_model.xml`
- Verifica carga inmediata del modelo
- Genera `logs/train_metrics.json`

### Fase 3 - Calibración experimental

```bash
python calibrate_threshold.py
```

- Ejecuta predicciones genuinas/cruzadas
- Calcula FAR, FRR y umbral sugerido
- Actualiza `umbral_confianza` en BD
- Genera `logs/calibration_report.txt`

### Evaluación experimental extendida

```bash
python experimental_validation.py
python statistical_analysis.py
python generate_plots.py
python generate_academic_text.py
```

- `experimental_validation.py`: genera `logs/experimental_results.csv` con predicciones genuinas/impostor, confianza y latencia.
- `statistical_analysis.py`: calcula FAR, FRR, EER, Accuracy, Precision, Recall y umbral óptimo en `logs/statistical_report.txt`.
- `generate_plots.py`: guarda histogramas/curvas/distribución en `logs/plots/` y tabla APA en `logs/plots/apa_summary_table.csv`.
- `generate_academic_text.py`: redacta borradores para `logs/chapter3_metodologia.txt`, `logs/chapter4_resultados.txt` e `logs/ieee_draft.txt`.

### Validación cruzada robusta anti-sobreajuste

```bash
python cross_validation.py
```

- Aplica separación reproducible por usuario (70% entrenamiento / 30% prueba, seed fija).
- Ejecuta K-Fold estratificado por usuario con `k=5` sobre el subconjunto de entrenamiento.
- Reentrena LBPH en cada fold y evalúa únicamente muestras de prueba del fold.
- Calcula por fold: FAR, FRR, Accuracy, Precision, Recall, EER, medias/desviaciones de confianza.
- Detecta sobreajuste comparando `Accuracy_train` vs `Accuracy_test`.
- Genera: `logs/cross_validation_report.txt`, `logs/cross_validation_metrics.json`,
  `logs/chapter3_cross_validation.txt`, `logs/chapter4_cross_validation_results.txt`.

### Validación por sesión temporal

```bash
python session_validation.py
```

- Detecta sesiones automáticamente por timestamp/prefijo de captura.
- Si hay múltiples sesiones: entrena con sesión temprana y prueba con sesión tardía.
- Si hay una sola sesión: evalúa con conjunto de prueba aumentado (brillo, contraste, rotación ±5°, blur gaussiano).
- Calcula FAR, FRR, Accuracy, EER y estadísticas de confianza.
- Compara contra baseline de validación cruzada y reporta posibles cambios de robustez.
- Genera: `logs/session_validation_report.txt`, `logs/session_validation_metrics.json`,
  `logs/chapter3_session_validation.txt`, `logs/chapter4_session_validation_results.txt`.

### Validación estricta por sesión real (A/B)

```bash
python real_session_validation.py
```

- Requiere muestras etiquetadas por sesión real (`session_A` y `session_B`) en ruta o nombre de archivo.
- Ejecuta evaluación bidireccional estricta:
    - Entrenamiento con `session_A` y prueba con `session_B`.
    - Entrenamiento con `session_B` y prueba con `session_A`.
- Calcula FAR, FRR, Accuracy, EER y estadísticas de confianza por dirección y promedio.
- Compara contra baseline previo (`session_validation` o `cross_validation`).
- Genera: `logs/real_session_validation_report.txt`, `logs/real_session_validation_metrics.json`,
    `logs/chapter4_real_session_validation.txt`.

### Fase 4 y 5 - Prevalidación + soak 2h

```bash
python prevalidate_and_soak.py
```

- Ejecuta bootstrap -> entrenamiento (si falta modelo) -> calibración
- Verifica `/health`
- Simula 5 accesos válidos + 5 inválidos
- Si todo pasa, ejecuta soak de 2 horas
- Genera `logs/soak_2h_report.txt`

### Fase 6 - systemd (solo si soak 2h pasa)

```bash
python generate_systemd_artifacts.py
bash deploy/systemd/install_systemd.sh
```

`generate_systemd_artifacts.py` solo genera artefactos si `logs/soak_2h_report.txt` no reporta errores ni degradación.

## Ajustes dinámicos desde panel admin

- Umbral de confianza
- Tiempo de apertura de relé
- Máximo intentos
- Captura de 30 muestras por usuario
- Entrenamiento del modelo
- Reinicio del servicio

## Variables de entorno opcionales

- `CAMERAPI_ADMIN_USER`
- `CAMERAPI_ADMIN_PASSWORD`
- `CAMERAPI_SECRET`
