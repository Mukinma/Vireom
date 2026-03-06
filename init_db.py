from database.db import db


if __name__ == "__main__":
    db.init_db()
    print("Base de datos inicializada correctamente.")
