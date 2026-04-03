"""
Migration: adiciona photo_file_id em todas as tabelas bot_records_*,
           telegram_chat_id em bot_users,
           e atualiza a função create_records_table.

Execute UMA VEZ após o db_setup.py inicial:
    python tools/migration_add_photo.py
"""
import os
import sys
import psycopg
from dotenv import load_dotenv

load_dotenv()

SQL = """
-- 1. Adicionar photo_file_id em TODAS as tabelas bot_records_* existentes (idempotente)
DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOR tbl IN
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name LIKE 'bot_records_%'
        ORDER BY table_name
    LOOP
        EXECUTE format(
            'ALTER TABLE %I ADD COLUMN IF NOT EXISTS photo_file_id VARCHAR(200)',
            tbl
        );
        RAISE NOTICE 'photo_file_id adicionado em: %', tbl;
    END LOOP;
END $$;

-- 2. Adicionar telegram_chat_id em bot_users (para envio do relatório mensal)
ALTER TABLE bot_users ADD COLUMN IF NOT EXISTS telegram_chat_id BIGINT;

-- 3. Atualizar create_records_table para incluir photo_file_id em tabelas futuras
CREATE OR REPLACE FUNCTION create_records_table(p_table_name TEXT)
RETURNS VOID AS $$
BEGIN
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I (
            id              BIGSERIAL PRIMARY KEY,
            meta_config_id  BIGINT REFERENCES bot_meta_configs(id),
            sector_id       BIGINT REFERENCES bot_sectors(id),
            reported_by     VARCHAR(20),
            occurrence_date DATE DEFAULT CURRENT_DATE,
            notes           TEXT,
            photo_file_id   VARCHAR(200),
            created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    ', p_table_name);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
"""


def run_migration() -> None:
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("SUPABASE_DB_URL nao encontrada no .env")
        sys.exit(1)

    print("Conectando ao banco...")
    try:
        conn = psycopg.connect(db_url, autocommit=True)
        cursor = conn.cursor()
        print("Executando migration...")
        cursor.execute(SQL)
        cursor.close()
        conn.close()
        print("Migration concluida!")
        print("  + photo_file_id em todas as tabelas bot_records_*")
        print("  + telegram_chat_id em bot_users")
        print("  + create_records_table atualizada")
    except psycopg.Error as e:
        print(f"Erro: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_migration()
