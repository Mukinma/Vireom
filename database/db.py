import sqlite3
import time
import logging
import re
from pathlib import Path
from typing import Any, Optional, Iterable

from config import config


logger = logging.getLogger("camerapi.db")
ACCESS_RESULTS_ALLOWED = {
    "AUTORIZADO",
    "DENEGADO",
    "DESCONOCIDO",
    "ERROR",
    "MANUAL",
    "DENEGADO_BLOQUEO",
}


class Database:
    def __init__(self, db_path: str = config.db_path, schema_path: str = "database/schema.sql"):
        self.db_path = str(db_path)
        self.schema_path = str(schema_path)
        self.max_retries = 3
        self.retry_delay_sec = 0.2

        db_file = Path(self.db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

    def _apply_pragmas(self, conn: sqlite3.Connection) -> None:
        conn.row_factory = sqlite3.Row

        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")

        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA temp_store = MEMORY;")
        conn.execute("PRAGMA cache_size = -20000;")

        conn.execute("PRAGMA trusted_schema = OFF;")
        conn.execute("PRAGMA recursive_triggers = ON;")

    def connect(self) -> sqlite3.Connection:
        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                conn = sqlite3.connect(
                    self.db_path,
                    check_same_thread=False,
                    timeout=10,
                )
                self._apply_pragmas(conn)
                return conn
            except sqlite3.Error as exc:
                last_error = exc
                logger.error("db_connect_failed attempt=%s error=%s", attempt, exc)
                time.sleep(self.retry_delay_sec)
        raise RuntimeError(f"No se pudo conectar a SQLite: {last_error}")

    def init_db(self, schema_path: Optional[str] = None) -> None:
        schema_path = schema_path or self.schema_path

        schema_file = Path(schema_path).resolve()
        if not schema_file.is_file():
            raise FileNotFoundError(f"Schema no encontrado: {schema_file}")

        try:
            sql = schema_file.read_text(encoding="utf-8")
        except Exception as exc:
            raise RuntimeError(f"No se pudo leer schema: {schema_file}") from exc

        try:
            with self.connect() as conn:
                sql_to_execute = sql

                usuarios_cols = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(usuarios);").fetchall()
                }
                if "creado_por_admin_id" in usuarios_cols:
                    sql_to_execute = re.sub(
                        r"ALTER\s+TABLE\s+usuarios\s+ADD\s+COLUMN\s+creado_por_admin_id\s+INTEGER\s+NULL\s*;",
                        "",
                        sql_to_execute,
                        flags=re.IGNORECASE,
                    )

                muestras_cols_before = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(muestras);").fetchall()
                }
                has_pose_type_before = "pose_type" in muestras_cols_before
                if not has_pose_type_before:
                    sql_to_execute = re.sub(
                        r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+idx_muestras_pose\s+ON\s+muestras\s*\(\s*pose_type\s*\)\s*;",
                        "",
                        sql_to_execute,
                        flags=re.IGNORECASE,
                    )

                conn.executescript(sql_to_execute)

                # ── Migration: add pose_type column to muestras ──
                muestras_cols = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(muestras);").fetchall()
                }
                if "pose_type" not in muestras_cols:
                    conn.execute(
                        "ALTER TABLE muestras ADD COLUMN pose_type TEXT DEFAULT 'frontal';"
                    )
                    logger.info("migration_applied added_column=pose_type table=muestras")

                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_muestras_pose ON muestras(pose_type);"
                )
        except Exception:
            logger.exception("db_init_failed schema_path=%s", schema_file)
            raise

    def fetch_one(self, query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        try:
            with self.connect() as conn:
                return conn.execute(query, params).fetchone()
        except Exception:
            logger.exception("db_fetch_one_failed query=%s", query)
            raise

    def fetch_all(self, query: str, params: tuple = ()) -> list[sqlite3.Row]:
        try:
            with self.connect() as conn:
                return conn.execute(query, params).fetchall()
        except Exception:
            logger.exception("db_fetch_all_failed query=%s", query)
            raise

    def execute(self, query: str, params: tuple = ()) -> int:
        try:
            with self.connect() as conn:
                cur = conn.execute(query, params)
                return cur.lastrowid
        except Exception:
            logger.exception("db_execute_failed query=%s", query)
            raise

    def execute_many(self, query: str, params: Iterable[tuple]) -> int:
        params_list = list(params)
        if not params_list:
            return 0
        try:
            with self.connect() as conn:
                conn.executemany(query, params_list)
            return len(params_list)
        except Exception:
            logger.exception("db_execute_many_failed query=%s", query)
            raise

    def health_check(self) -> bool:
        try:
            row = self.fetch_one("SELECT 1 AS ok")
            return bool(row and row["ok"] == 1)
        except Exception:
            logger.exception("db_health_failed")
            return False

    def get_config(self) -> dict[str, Any]:
        row = self.fetch_one(
            "SELECT umbral_confianza, tiempo_apertura_seg, max_intentos FROM configuracion WHERE id=1"
        )
        if not row:
            return {
                "umbral_confianza": float(config.default_confidence_threshold),
                "tiempo_apertura_seg": int(config.default_open_seconds),
                "max_intentos": int(config.default_max_attempts),
            }
        return dict(row)

    def update_config(self, umbral_confianza: float, tiempo_apertura_seg: int, max_intentos: int) -> None:
        if not (1.0 <= float(umbral_confianza) <= 200.0):
            raise ValueError("umbral_confianza fuera de rango 1..200")
        if not (1 <= int(tiempo_apertura_seg) <= 30):
            raise ValueError("tiempo_apertura_seg fuera de rango 1..30")
        if not (1 <= int(max_intentos) <= 10):
            raise ValueError("max_intentos fuera de rango 1..10")

        self.execute(
            "UPDATE configuracion SET umbral_confianza=?, tiempo_apertura_seg=?, max_intentos=? WHERE id=1",
            (float(umbral_confianza), int(tiempo_apertura_seg), int(max_intentos)),
        )

    def create_user(self, nombre: str, activo: bool = True) -> int:
        nombre_norm = (nombre or "").strip()
        if not nombre_norm:
            raise ValueError("nombre vacío")
        return self.execute(
            "INSERT INTO usuarios (nombre, activo) VALUES (?, ?)",
            (nombre_norm, 1 if activo else 0),
        )

    def set_user_status(self, user_id: int, active: bool) -> None:
        if int(user_id) <= 0:
            raise ValueError("user_id inválido")
        self.execute("UPDATE usuarios SET activo=? WHERE id=?", (1 if active else 0, int(user_id)))

    def delete_user(self, user_id: int) -> bool:
        if int(user_id) <= 0:
            raise ValueError("user_id inválido")
        user = self.get_user(user_id)
        if not user:
            return False
        try:
            with self.connect() as conn:
                conn.execute("DELETE FROM muestras WHERE usuario_id=?", (int(user_id),))
                conn.execute("UPDATE accesos SET usuario_id=NULL WHERE usuario_id=?", (int(user_id),))
                conn.execute("DELETE FROM usuarios WHERE id=?", (int(user_id),))
            return True
        except Exception:
            logger.exception("db_delete_user_failed user_id=%s", user_id)
            raise

    def list_users(self) -> list[dict[str, Any]]:
        rows = self.fetch_all(
            """
            SELECT
                u.id,
                u.nombre,
                u.activo,
                u.fecha_registro,
                COUNT(m.id) AS samples_count,
                MAX(m.fecha_captura) AS last_sample_at,
                (
                    SELECT a.fecha
                    FROM accesos a
                    WHERE a.usuario_id = u.id
                    ORDER BY a.id DESC
                    LIMIT 1
                ) AS last_access_at,
                (
                    SELECT a.resultado
                    FROM accesos a
                    WHERE a.usuario_id = u.id
                    ORDER BY a.id DESC
                    LIMIT 1
                ) AS last_access_result,
                (
                    SELECT mm.trained_at
                    FROM model_meta mm
                    WHERE mm.id = 1
                ) AS model_trained_at
            FROM usuarios u
            LEFT JOIN muestras m ON m.usuario_id = u.id
            GROUP BY u.id
            ORDER BY u.id DESC
            """
        )

        users: list[dict[str, Any]] = []
        for row in rows:
            user = dict(row)
            samples_count = int(user.get("samples_count") or 0)
            last_sample_at = user.get("last_sample_at")
            model_trained_at = user.pop("model_trained_at", None)
            user["samples_count"] = samples_count
            user["needs_training"] = (
                samples_count <= 0
                or not model_trained_at
                or (bool(last_sample_at) and str(last_sample_at) > str(model_trained_at))
            )
            user["thumbnail_url"] = f"/api/users/{user['id']}/thumbnail" if samples_count > 0 else None
            users.append(user)
        return users

    def get_user(self, user_id: int) -> Optional[dict[str, Any]]:
        if int(user_id) <= 0:
            raise ValueError("user_id inválido")
        row = self.fetch_one("SELECT id, nombre, activo FROM usuarios WHERE id=?", (int(user_id),))
        return dict(row) if row else None

    def get_user_thumbnail_path(self, user_id: int) -> Optional[str]:
        if int(user_id) <= 0:
            raise ValueError("user_id inválido")
        row = self.fetch_one(
            """
            SELECT imagen_ref
            FROM muestras
            WHERE usuario_id=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (int(user_id),),
        )
        return str(row["imagen_ref"]) if row else None

    def _normalize_imagen_ref(self, imagen_ref: str) -> str:
        ref = (imagen_ref or "").strip()
        if not ref:
            raise ValueError("imagen_ref vacío")

        p = Path(ref)
        if p.is_absolute() or ".." in p.parts:
            raise ValueError("imagen_ref inválido, no se permiten rutas absolutas ni traversal")

        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-/")
        if any(ch not in allowed for ch in ref):
            raise ValueError("imagen_ref contiene caracteres no permitidos")

        return ref

    def insert_sample_with_pose(self, user_id: int, imagen_ref: str, pose_type: str) -> int:
        if int(user_id) <= 0:
            raise ValueError("user_id inválido")
        imagen_ref_norm = self._normalize_imagen_ref(imagen_ref)
        valid_poses = {"frontal", "tilt_left", "tilt_right", "look_up", "look_down", "turn_left", "turn_right", "center"}
        pose = pose_type.strip().lower() if pose_type else "frontal"
        if pose not in valid_poses:
            pose = "frontal"
        return self.execute(
            "INSERT INTO muestras (usuario_id, imagen_ref, pose_type) VALUES (?, ?, ?)",
            (int(user_id), imagen_ref_norm, pose),
        )

    def insert_samples_with_pose(self, user_id: int, samples: Iterable[tuple[str, str]]) -> int:
        if int(user_id) <= 0:
            raise ValueError("user_id inválido")
        valid_poses = {"frontal", "tilt_left", "tilt_right", "look_up", "look_down", "turn_left", "turn_right", "center"}
        rows = []
        for imagen_ref, pose_type in samples:
            imagen_ref_norm = self._normalize_imagen_ref(imagen_ref)
            pose = pose_type.strip().lower() if pose_type else "frontal"
            if pose not in valid_poses:
                pose = "frontal"
            rows.append((int(user_id), imagen_ref_norm, pose))
        return self.execute_many(
            "INSERT INTO muestras (usuario_id, imagen_ref, pose_type) VALUES (?, ?, ?)",
            rows,
        )

    def insert_sample(self, user_id: int, imagen_ref: str) -> int:
        if int(user_id) <= 0:
            raise ValueError("user_id inválido")
        imagen_ref_norm = self._normalize_imagen_ref(imagen_ref)
        return self.execute(
            "INSERT INTO muestras (usuario_id, imagen_ref) VALUES (?, ?)",
            (int(user_id), imagen_ref_norm),
        )

    def list_samples(self, user_id: Optional[int] = None) -> list[dict[str, Any]]:
        if user_id is None:
            rows = self.fetch_all("SELECT id, usuario_id, imagen_ref, fecha_captura FROM muestras ORDER BY id DESC")
        else:
            if int(user_id) <= 0:
                raise ValueError("user_id inválido")
            rows = self.fetch_all(
                "SELECT id, usuario_id, imagen_ref, fecha_captura FROM muestras WHERE usuario_id=? ORDER BY id DESC",
                (int(user_id),),
            )
        return [dict(row) for row in rows]

    def insert_access(
        self,
        user_id: Optional[int],
        confianza: Optional[float],
        resultado: str,
        motivo: Optional[str] = None,
    ) -> int:
        resultado_norm = (resultado or "").strip().upper()
        if resultado_norm not in ACCESS_RESULTS_ALLOWED:
            raise ValueError("resultado inválido")

        conf = None if confianza is None else float(confianza)
        if conf is not None and not (0.0 <= conf <= 100.0):
            raise ValueError("confianza fuera de rango 0..100")

        uid = None if user_id is None else int(user_id)
        if uid is not None and uid <= 0:
            raise ValueError("user_id inválido")

        motivo_norm = None
        if motivo is not None:
            motivo_norm = motivo.strip()
            if motivo_norm == "":
                motivo_norm = None
            if motivo_norm is not None and len(motivo_norm) > 300:
                motivo_norm = motivo_norm[:300]

        return self.execute(
            "INSERT INTO accesos (usuario_id, confianza, resultado, motivo) VALUES (?, ?, ?, ?)",
            (uid, conf, resultado_norm, motivo_norm),
        )

    def list_user_access_logs(self, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
        if int(user_id) <= 0:
            raise ValueError("user_id inválido")
        lim = max(1, min(500, int(limit)))
        rows = self.fetch_all(
            """
            SELECT a.id, a.fecha, a.confianza, a.resultado, a.motivo
            FROM accesos a
            WHERE a.usuario_id = ?
            ORDER BY a.id DESC
            LIMIT ?
            """,
            (int(user_id), lim),
        )
        return [dict(row) for row in rows]

    def count_user_samples(self, user_id: int) -> int:
        if int(user_id) <= 0:
            raise ValueError("user_id inválido")
        row = self.fetch_one(
            "SELECT COUNT(*) AS total FROM muestras WHERE usuario_id=?",
            (int(user_id),),
        )
        return row["total"] if row else 0

    def list_access_logs(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        lim = int(limit)
        if lim <= 0:
            lim = 1
        if lim > 1000:
            lim = 1000
        off = max(0, int(offset))

        rows = self.fetch_all(
            """
            SELECT a.id, a.usuario_id, a.fecha, a.confianza, a.resultado, a.motivo, u.nombre
            FROM accesos a
            LEFT JOIN usuarios u ON a.usuario_id = u.id
            ORDER BY a.id DESC
            LIMIT ? OFFSET ?
            """,
            (lim, off),
        )
        return [dict(row) for row in rows]

    # ── model_meta helpers ──────────────────────────────────────────

    def get_model_meta(self) -> Optional[dict[str, Any]]:
        row = self.fetch_one("SELECT trained_at, samples, unique_users FROM model_meta WHERE id=1")
        return dict(row) if row else None

    def save_model_meta(self, samples: int, unique_users: int) -> None:
        self.execute(
            """
            INSERT INTO model_meta (id, trained_at, samples, unique_users)
            VALUES (1, CURRENT_TIMESTAMP, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                trained_at = CURRENT_TIMESTAMP,
                samples = excluded.samples,
                unique_users = excluded.unique_users
            """,
            (int(samples), int(unique_users)),
        )

    # ── administradores helpers ─────────────────────────────────────

    def get_admin_by_username(self, username: str) -> Optional[dict[str, Any]]:
        row = self.fetch_one(
            "SELECT id, username, password_hash, rol, activo FROM administradores WHERE username=? AND activo=1",
            (username,),
        )
        return dict(row) if row else None

    def upsert_admin_password(self, username: str, password_hash: str) -> None:
        self.execute(
            """
            INSERT INTO administradores (username, password_hash, rol, activo)
            VALUES (?, ?, 'CEO', 1)
            ON CONFLICT(username) DO UPDATE SET
                password_hash = excluded.password_hash,
                activo = 1
            """,
            (username, password_hash),
        )


db = Database()
