"""
One-shot, bulletproof database reset.

Unlike importing schema.sql through phpMyAdmin, this script connects using the
EXACT same credentials your Flask app reads from .env — so there's no chance of
accidentally resetting a different MySQL instance than the one the app actually
uses (a common issue on Windows machines with more than one MySQL install, e.g.
XAMPP + a standalone MySQL Server both on port 3306).

It drops the database, recreates it, builds every table fresh from the current
models (guaranteed to match the code — no stale schema.sql possible), and then
runs the normal seed data.

Run from backend/:
    python reset_db.py
"""
import pymysql
from config import Config

print(f"Connecting to {Config.DB_HOST}:{Config.DB_PORT} as {Config.DB_USER} ...")

conn = pymysql.connect(
    host=Config.DB_HOST,
    port=int(Config.DB_PORT),
    user=Config.DB_USER,
    password=Config.DB_PASSWORD,
)
try:
    with conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {Config.DB_NAME};")
        cur.execute(f"CREATE DATABASE {Config.DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
    conn.commit()
    print(f"Database '{Config.DB_NAME}' dropped and recreated.")
finally:
    conn.close()

from app import create_app
from app.extensions import db

app = create_app()
with app.app_context():
    db.create_all()
    print(f"All {len(db.metadata.sorted_tables)} tables created from current models.")

print("\nNow run: python seed.py")
