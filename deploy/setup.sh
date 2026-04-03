#!/bin/bash
# =============================================================
# setup.sh — Configuração inicial do servidor Oracle Cloud
# Execute uma única vez como usuário ubuntu:
#   bash setup.sh
# =============================================================
set -e

APP_DIR="/opt/agente-metas"
REPO_URL="https://github.com/SEU_USUARIO/SEU_REPO.git"   # <-- ajuste
PYTHON_BIN="python3"

echo "=== [1/7] Atualizando pacotes ==="
sudo apt-get update -y
sudo apt-get upgrade -y
sudo apt-get install -y git python3 python3-pip python3-venv nginx certbot python3-certbot-nginx curl

echo "=== [2/7] Criando diretório da aplicação ==="
sudo mkdir -p "$APP_DIR"
sudo chown ubuntu:ubuntu "$APP_DIR"

echo "=== [3/7] Clonando repositório ==="
# Se o diretório já existe com código, apenas atualiza
if [ -d "$APP_DIR/.git" ]; then
    git -C "$APP_DIR" pull
else
    git clone "$REPO_URL" "$APP_DIR"
fi

echo "=== [4/7] Criando ambiente virtual e instalando dependências ==="
cd "$APP_DIR"
$PYTHON_BIN -m venv .venv
source .venv/bin/activate

# supabase precisa de instalação especial (sem pyiceberg)
pip install --upgrade pip
pip install fastapi uvicorn[standard] python-dotenv apscheduler httpx
pip install psycopg[binary]
pip install supabase --no-deps
pip install "storage3==0.12.2" PyJWT websockets deprecation python-dateutil

deactivate

echo "=== [5/7] Configurando arquivo .env ==="
if [ ! -f "$APP_DIR/.env" ]; then
    cat > "$APP_DIR/.env" <<'ENVEOF'
TELEGRAM_BOT_TOKEN=
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
SUPABASE_DB_URL=
ENVEOF
    echo ""
    echo ">>> ATENÇÃO: preencha $APP_DIR/.env com suas credenciais antes de iniciar o serviço!"
fi

echo "=== [6/7] Instalando serviço systemd ==="
sudo cp "$APP_DIR/deploy/agente-metas.service" /etc/systemd/system/agente-metas.service
sudo systemctl daemon-reload
sudo systemctl enable agente-metas

echo "=== [7/7] Liberando portas no firewall do Oracle ==="
# Regras iptables (Oracle bloqueia por padrão portas 80/443 mesmo com Security List aberta)
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 8000 -j ACCEPT
# Tornar regras persistentes
sudo apt-get install -y iptables-persistent
sudo netfilter-persistent save

echo ""
echo "======================================================"
echo " Setup concluído!"
echo " Próximos passos:"
echo "   1. Edite $APP_DIR/.env com suas credenciais"
echo "   2. Execute: bash deploy/setup_https.sh (SSL)"
echo "   3. sudo systemctl start agente-metas"
echo "   4. Atualize o webhook do Telegram para https://SEU_DOMINIO/webhook"
echo "======================================================"
