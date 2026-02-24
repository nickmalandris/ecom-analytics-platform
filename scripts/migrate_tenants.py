"""
Migration script: Add access token columns to tenants table.
"""

import os
import psycopg2
from dotenv import load_dotenv

def get_db_url():
    """Get database URL from environment."""
    load_dotenv()
    return os.getenv("DATABASE_URL")

def main():
    db_url = get_db_url()
    if not db_url:
        print("DATABASE_URL not set")
        return

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            print("Checking for existing columns...")
            
            # Check if columns exist
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='tenants' AND column_name='shopify_access_token'
            """)
            if cur.fetchone():
                print("Columns already exist. Skipping.")
                return

            print("Adding new columns...")
            cur.execute("""
                ALTER TABLE public.tenants
                ADD COLUMN shopify_access_token TEXT,
                ADD COLUMN meta_access_token TEXT,
                ADD COLUMN meta_token_expires_at TIMESTAMPTZ;
            """)
        conn.commit()
        print("Migration complete.")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
