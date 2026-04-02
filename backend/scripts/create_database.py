import argparse
import sys
from pathlib import Path
from typing import Optional

import psycopg
from psycopg import OperationalError, sql
from psycopg.rows import tuple_row

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.auth_service import ensure_bootstrap_super_admin


def create_database_if_missing(db_name: str) -> None:
    """Create PostgreSQL database if it doesn't exist."""
    try:
        with psycopg.connect(settings.psycopg_admin_uri, autocommit=True) as conn:
            with conn.cursor(row_factory=tuple_row) as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
                exists = cur.fetchone()
                if exists:
                    print(f"✅ Database '{db_name}' already exists.")
                    return

                query = sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name))
                cur.execute(query)
                print(f"✅ Created database '{db_name}'.")
    except OperationalError as e:
        print(f"❌ Failed to create database: {e}")
        raise


def apply_sql_file(path: Path) -> None:
    """Apply SQL file to the database - execute as single script."""
    if not path.exists():
        raise FileNotFoundError(f"SQL file not found: {path}")

    # Read with utf-8-sig to automatically strip BOM if present
    sql_text = path.read_text(encoding="utf-8-sig").strip()

    if not sql_text:
        print(f"⚠️  Skipping empty file: {path}")
        return

    try:
        with psycopg.connect(settings.psycopg_database_uri, autocommit=True) as conn:
            with conn.cursor() as cur:
                # 🔥 FIX: Execute entire file as one script
                # PostgreSQL can handle multiple statements in one execute()
                # This preserves dollar-quoted blocks and transaction boundaries
                cur.execute(sql_text)

        print(f"✅ Applied: {path.name}")
    except Exception as e:
        print(f"❌ Failed to apply {path.name}:")
        print(f"   Error: {e}")
        raise


def bootstrap_admin_if_configured() -> None:
    """Create bootstrap admin user if configured in .env."""
    username = (settings.bootstrap_admin_username or "").strip()
    password = settings.bootstrap_admin_password or ""

    if not username or not password:
        print(
            "⚠️  No bootstrap admin configured (set BOOTSTRAP_ADMIN_USERNAME and BOOTSTRAP_ADMIN_PASSWORD)"
        )
        return

    db = SessionLocal()
    try:
        ensure_bootstrap_super_admin(db, username=username, password=password)
        print(f"✅ Bootstrap super admin ensured for username '{username}'.")
    except Exception as e:
        print(f"❌ Failed to create bootstrap admin: {e}")
        raise
    finally:
        db.close()


def main() -> None:
    """Main entry point for database creation script."""
    parser = argparse.ArgumentParser(
        description="Create and initialize QC-BKP modern database"
    )
    parser.add_argument(
        "--skip-seed",
        action="store_true",
        help="Create schema only and skip seed data",
    )
    args = parser.parse_args()

    schema_path = REPO_ROOT / "db" / "schema.sql"
    seed_path = REPO_ROOT / "db" / "seed.sql"

    print("=" * 60)
    print("🚀 Starting Database Bootstrap")
    print("=" * 60)
    print(f"Database: {settings.pg_database}")
    print(f"Host: {settings.pg_host}:{settings.pg_port}")
    print(f"User: {settings.pg_user}")
    print("=" * 60)

    try:
        # Step 1: Create database
        print("\n📦 Step 1: Creating database...")
        create_database_if_missing(settings.pg_database)

        # Step 2: Apply schema
        print("\n📋 Step 2: Applying schema...")
        apply_sql_file(schema_path)

        # Step 3: Apply seed data (unless skipped)
        if not args.skip_seed:
            print("\n🌱 Step 3: Applying seed data...")
            apply_sql_file(seed_path)
        else:
            print("\n⏭️  Step 3: Skipped seed data (--skip-seed)")

        # Step 4: Bootstrap admin
        print("\n👤 Step 4: Bootstrap admin user...")
        bootstrap_admin_if_configured()

        print("\n" + "=" * 60)
        print("✅ Database bootstrap completed successfully!")
        print("=" * 60)

    except FileNotFoundError as exc:
        print(f"\n❌ File Error: {exc}")
        raise SystemExit(1) from exc

    except OperationalError as exc:
        print("\n" + "=" * 60)
        print("❌ DATABASE CONNECTION FAILED")
        print("=" * 60)
        print("Could not connect to PostgreSQL.")
        print("\n🔧 Troubleshooting:")
        print("  1. Ensure PostgreSQL is running:")
        print("     sudo systemctl status postgresql")
        print("  2. Verify .env credentials:")
        print(f"     Host: {settings.pg_host}")
        print(f"     Port: {settings.pg_port}")
        print(f"     User: {settings.pg_user}")
        print(f"     Database: {settings.pg_database}")
        print("  3. Test connection:")
        print(
            f"     psql -h {settings.pg_host} -p {settings.pg_port} -U {settings.pg_user} -d postgres"
        )
        print("=" * 60)
        raise SystemExit(1) from exc

    except Exception as exc:
        print(f"\n❌ Unexpected Error: {exc}")
        import traceback

        traceback.print_exc()
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
