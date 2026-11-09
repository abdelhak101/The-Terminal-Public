import os
import time
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def get_connection(dbname="postgres", max_retries=10, delay=2):
    """Establishes a connection to the database with retries."""
    host = os.getenv("POSTGRES_HOST", "localhost")
    user = os.getenv("POSTGRES_USER", "admin")
    password = os.getenv("POSTGRES_PASSWORD", "admin_password")
    port = os.getenv("POSTGRES_PORT", "25432")

    for i in range(max_retries):
        try:
            conn = psycopg2.connect(
                host=host,
                user=user,
                password=password,
                port=port,
                dbname=dbname
            )
            logger.info(f"Successfully connected to database: {dbname}")
            return conn
        except psycopg2.OperationalError as e:
            if i < max_retries - 1:
                logger.warning(f"Database connection failed. Retrying in {delay}s... ({i+1}/{max_retries})")
                time.sleep(delay)
            else:
                logger.error(f"Could not connect to database after {max_retries} attempts.")
                raise e

def create_database(db_name):
    """Creates a database if it doesn't exist."""
    conn = get_connection("postgres")
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        exists = cur.fetchone()
        if not exists:
            logger.info(f"Creating database: {db_name}")
            cur.execute(f"CREATE DATABASE {db_name}")
        else:
            logger.info(f"Database already exists: {db_name}")
    
    conn.close()

def apply_sql_file(file_path, db_name):
    """Applies an SQL file to a specific database."""
    logger.info(f"Applying {file_path} to {db_name}...")
    conn = get_connection(db_name)
    
    try:
        with conn.cursor() as cur:
            with open(file_path, 'r') as f:
                lines = f.readlines()
                # Strip psql commands like \c
                sql = "".join([line for line in lines if not line.strip().startswith('\\')])
                if sql.strip():
                    cur.execute(sql)
        conn.commit()
        logger.info(f"Successfully applied {file_path}")
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to apply {file_path}: {e}")
        raise e
    finally:
        conn.close()

def main():
    # 1. Ensure databases exist
    required_dbs = ["metadata", "dagster"]
    for db in required_dbs:
        create_database(db)
    
    # 2. Apply schemas to 'metadata' database
    init_dir = "infrastructure/docker/storage/init"
    sql_files = [
        "02-metadata-schema.sql",
        "03-feature-registry.sql",
        "04-clickhouse-migration.sql"
    ]
    
    for sql_file in sql_files:
        file_path = os.path.join(init_dir, sql_file)
        if os.path.exists(file_path):
            apply_sql_file(file_path, "metadata")
        else:
            logger.warning(f"SQL file not found: {file_path}")

    logger.info("✨ Database setup complete!")

if __name__ == "__main__":
    main()
