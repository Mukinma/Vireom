PRAGMA foreign_keys = ON;

-- =========================
-- 1. Tabla administradores
-- =========================

CREATE TABLE IF NOT EXISTS administradores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    rol TEXT NOT NULL CHECK(rol IN ('CEO','ENCARGADO','OPERADOR')),
    activo INTEGER NOT NULL DEFAULT 1 CHECK(activo IN (0,1)),
    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_admin_rol ON administradores(rol);
CREATE INDEX IF NOT EXISTS idx_admin_activo ON administradores(activo);

-- =========================
-- 2. Agregar campo en usuarios
-- =========================

ALTER TABLE usuarios ADD COLUMN creado_por_admin_id INTEGER NULL;

-- Nota:
-- SQLite no permite agregar FK con ALTER directamente.
-- Pero sí podemos documentar la relación a nivel conceptual.
-- Alternativamente se valida en lógica de aplicación.

-- =========================   
-- 3. Crear relación lógica por consistencia
-- =========================

-- Esta vista ayuda a auditoría administrativa

CREATE VIEW IF NOT EXISTS vista_usuarios_con_admin AS
SELECT 
    u.id,
    u.nombre,
    u.activo,
    u.fecha_registro,
    a.username AS creado_por
FROM usuarios u
LEFT JOIN administradores a 
    ON u.creado_por_admin_id = a.id;