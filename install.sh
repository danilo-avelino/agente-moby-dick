#!/usr/bin/env bash
# Instalação de dependências — compatível com Python 3.14
# Execute: bash install.sh

PYTHON=/c/Users/danil/AppData/Local/Python/bin/python3

echo "📦 Instalando dependências principais..."
$PYTHON -m pip install fastapi "uvicorn[standard]" httpx python-dotenv pyngrok "psycopg[binary]"

echo "📦 Instalando supabase (sem pyiceberg)..."
$PYTHON -m pip install supabase postgrest gotrue realtime supafunc --no-deps
$PYTHON -m pip install "storage3==0.12.2" --no-deps --force-reinstall
$PYTHON -m pip install PyJWT websockets deprecation python-dateutil

echo "✅ Instalação concluída!"
$PYTHON -c "from supabase import create_client; import fastapi, uvicorn, httpx, psycopg; print('Todos os imports OK')"
