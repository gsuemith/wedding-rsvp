"""
Migration script to add email, phone_number, and password_hash columns
to the mailing_addresses table.
"""
import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable is not set")
    sys.exit(1)

def run_migration():
    """Add missing columns to mailing_addresses table."""
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        # Check if columns exist and add them if they don't
        migrations = [
            """
            DO $$ 
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'mailing_addresses' 
                    AND column_name = 'email'
                ) THEN
                    ALTER TABLE mailing_addresses ADD COLUMN email VARCHAR;
                END IF;
            END $$;
            """,
            """
            DO $$ 
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'mailing_addresses' 
                    AND column_name = 'phone_number'
                ) THEN
                    ALTER TABLE mailing_addresses ADD COLUMN phone_number VARCHAR;
                END IF;
            END $$;
            """,
            """
            DO $$ 
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'mailing_addresses' 
                    AND column_name = 'password_hash'
                ) THEN
                    ALTER TABLE mailing_addresses ADD COLUMN password_hash VARCHAR;
                END IF;
            END $$;
            """
        ]
        
        for migration in migrations:
            try:
                conn.execute(text(migration))
                conn.commit()
                print("✓ Migration applied successfully")
            except Exception as e:
                print(f"✗ Error applying migration: {e}")
                conn.rollback()
                raise
    
    print("\nMigration completed!")

if __name__ == "__main__":
    run_migration()

