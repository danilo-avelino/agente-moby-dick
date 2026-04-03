"""
Script de inicialização do banco de dados.
Execute UMA VEZ para criar tabelas e dados iniciais no Supabase.

Uso:
    python tools/db_setup.py
"""
import os
import sys
import psycopg
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────
# SQL DE SETUP
# ─────────────────────────────────────────────────────────

SQL = """
-- =====================================================
-- TABELAS DO BOT
-- (Não modifica nenhuma tabela existente)
-- =====================================================

-- Usuários autorizados
CREATE TABLE IF NOT EXISTS bot_users (
    id          BIGSERIAL PRIMARY KEY,
    phone       VARCHAR(20) UNIQUE NOT NULL,
    name        VARCHAR(100) NOT NULL,
    is_admin    BOOLEAN DEFAULT FALSE,
    created_by  VARCHAR(20),
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Lojas / Restaurantes
CREATE TABLE IF NOT EXISTS bot_stores (
    id          BIGSERIAL PRIMARY KEY,
    name        VARCHAR(100) UNIQUE NOT NULL,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Acesso usuário-loja
CREATE TABLE IF NOT EXISTS bot_user_store_access (
    id          BIGSERIAL PRIMARY KEY,
    user_phone  VARCHAR(20) REFERENCES bot_users(phone) ON DELETE CASCADE,
    store_id    BIGINT REFERENCES bot_stores(id) ON DELETE CASCADE,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_phone, store_id)
);

-- Setores
CREATE TABLE IF NOT EXISTS bot_sectors (
    id          BIGSERIAL PRIMARY KEY,
    store_id    BIGINT REFERENCES bot_stores(id) ON DELETE CASCADE,
    name        VARCHAR(100) NOT NULL,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(store_id, name)
);

-- Configurações de meta
CREATE TABLE IF NOT EXISTS bot_meta_configs (
    id            BIGSERIAL PRIMARY KEY,
    store_id      BIGINT REFERENCES bot_stores(id) ON DELETE CASCADE,
    name          VARCHAR(100) NOT NULL,
    display_name  VARCHAR(100) NOT NULL,
    target_value  INTEGER NOT NULL DEFAULT 2,
    comparison    VARCHAR(10) DEFAULT 'lte',
    table_name    VARCHAR(100) NOT NULL,
    created_by    VARCHAR(20),
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Setores por meta
CREATE TABLE IF NOT EXISTS bot_meta_sectors (
    id              BIGSERIAL PRIMARY KEY,
    meta_config_id  BIGINT REFERENCES bot_meta_configs(id) ON DELETE CASCADE,
    sector_id       BIGINT REFERENCES bot_sectors(id) ON DELETE CASCADE,
    UNIQUE(meta_config_id, sector_id)
);

-- =====================================================
-- FUNÇÃO: Cria tabela de registros dinamicamente
-- Usada pelo bot ao criar novas metas via WhatsApp
-- =====================================================

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
            created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    ', p_table_name);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =====================================================
-- TABELAS DE REGISTROS (metas iniciais da Moby Dick)
-- =====================================================

SELECT create_records_table('bot_records_limpeza');
SELECT create_records_table('bot_records_estoque');
SELECT create_records_table('bot_records_producao');

-- =====================================================
-- DADOS INICIAIS
-- =====================================================

-- Administradores
INSERT INTO bot_users (phone, name, is_admin) VALUES
    ('5586999731647', 'Danilo',  TRUE),
    ('5586999388667', 'Nariele', TRUE)
ON CONFLICT (phone) DO NOTHING;

-- Lojas
INSERT INTO bot_stores (name) VALUES
    ('Moby Dick Cloud Kitchen'),
    ('Terra Querida')
ON CONFLICT (name) DO NOTHING;

-- Seed de setores, metas e vínculos (executado em bloco para usar IDs dinâmicos)
DO $$
DECLARE
    moby_id        BIGINT;
    terra_id       BIGINT;

    nippon_dia_id  BIGINT;
    nippon_noi_id  BIGINT;
    tq_dia_id      BIGINT;
    tq_del_id      BIGINT;
    tq_dom_id      BIGINT;
    aglio_id       BIGINT;

    limpeza_id     BIGINT;
    estoque_id     BIGINT;
    producao_id    BIGINT;
BEGIN
    SELECT id INTO moby_id  FROM bot_stores WHERE name = 'Moby Dick Cloud Kitchen';
    SELECT id INTO terra_id FROM bot_stores WHERE name = 'Terra Querida';

    -- Acesso dos admins a todas as lojas
    INSERT INTO bot_user_store_access (user_phone, store_id) VALUES
        ('5586999731647', moby_id),
        ('5586999731647', terra_id),
        ('5586999388667', moby_id),
        ('5586999388667', terra_id)
    ON CONFLICT DO NOTHING;

    -- Setores da Moby Dick Cloud Kitchen
    INSERT INTO bot_sectors (store_id, name) VALUES
        (moby_id, 'Nippon - Dia'),
        (moby_id, 'Nippon - Noite'),
        (moby_id, 'Terra Querida - Dia'),
        (moby_id, 'Terra Querida Delivery'),
        (moby_id, 'Terra Querida - Dom Severino'),
        (moby_id, 'Aglio Nero')
    ON CONFLICT DO NOTHING;

    SELECT id INTO nippon_dia_id FROM bot_sectors WHERE store_id = moby_id AND name = 'Nippon - Dia';
    SELECT id INTO nippon_noi_id FROM bot_sectors WHERE store_id = moby_id AND name = 'Nippon - Noite';
    SELECT id INTO tq_dia_id     FROM bot_sectors WHERE store_id = moby_id AND name = 'Terra Querida - Dia';
    SELECT id INTO tq_del_id     FROM bot_sectors WHERE store_id = moby_id AND name = 'Terra Querida Delivery';
    SELECT id INTO tq_dom_id     FROM bot_sectors WHERE store_id = moby_id AND name = 'Terra Querida - Dom Severino';
    SELECT id INTO aglio_id      FROM bot_sectors WHERE store_id = moby_id AND name = 'Aglio Nero';

    -- Configurações de meta — Moby Dick
    INSERT INTO bot_meta_configs (store_id, name, display_name, target_value, table_name) VALUES
        (moby_id, 'limpeza',  'Limpeza',  2, 'bot_records_limpeza'),
        (moby_id, 'estoque',  'Estoque',  2, 'bot_records_estoque'),
        (moby_id, 'producao', 'Produção', 2, 'bot_records_producao')
    ON CONFLICT DO NOTHING;

    SELECT id INTO limpeza_id  FROM bot_meta_configs WHERE store_id = moby_id AND name = 'limpeza';
    SELECT id INTO estoque_id  FROM bot_meta_configs WHERE store_id = moby_id AND name = 'estoque';
    SELECT id INTO producao_id FROM bot_meta_configs WHERE store_id = moby_id AND name = 'producao';

    -- Limpeza → 6 setores (todos)
    INSERT INTO bot_meta_sectors (meta_config_id, sector_id) VALUES
        (limpeza_id, nippon_dia_id),
        (limpeza_id, nippon_noi_id),
        (limpeza_id, tq_dia_id),
        (limpeza_id, tq_del_id),
        (limpeza_id, tq_dom_id),
        (limpeza_id, aglio_id)
    ON CONFLICT DO NOTHING;

    -- Estoque → 5 setores (sem Dom Severino)
    INSERT INTO bot_meta_sectors (meta_config_id, sector_id) VALUES
        (estoque_id, nippon_dia_id),
        (estoque_id, nippon_noi_id),
        (estoque_id, tq_dia_id),
        (estoque_id, tq_del_id),
        (estoque_id, aglio_id)
    ON CONFLICT DO NOTHING;

    -- Produção → 6 setores (todos)
    INSERT INTO bot_meta_sectors (meta_config_id, sector_id) VALUES
        (producao_id, nippon_dia_id),
        (producao_id, nippon_noi_id),
        (producao_id, tq_dia_id),
        (producao_id, tq_del_id),
        (producao_id, tq_dom_id),
        (producao_id, aglio_id)
    ON CONFLICT DO NOTHING;

END $$;
"""


def setup_database() -> None:
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("❌ SUPABASE_DB_URL não encontrada no .env")
        sys.exit(1)

    print("🔧 Conectando ao banco de dados...")
    try:
        conn = psycopg.connect(db_url, autocommit=True)
        cursor = conn.cursor()

        print("📦 Criando tabelas e inserindo dados iniciais...")
        cursor.execute(SQL)

        cursor.close()
        conn.close()

        print("✅ Banco de dados configurado com sucesso!")
        print("\nDados inseridos:")
        print("  • Tabelas: bot_users, bot_stores, bot_user_store_access,")
        print("             bot_sectors, bot_meta_configs, bot_meta_sectors")
        print("  • Tabelas de registros: bot_records_limpeza, bot_records_estoque, bot_records_producao")
        print("  • Admins: Danilo (5586999731647), Nariele (5586999388667)")
        print("  • Lojas: Moby Dick Cloud Kitchen, Terra Querida")
        print("  • Metas Moby Dick: Limpeza (6 setores), Estoque (5 setores), Produção (6 setores)")

    except psycopg.Error as e:
        print(f"❌ Erro de banco de dados: {e}")
        sys.exit(1)


if __name__ == "__main__":
    setup_database()
