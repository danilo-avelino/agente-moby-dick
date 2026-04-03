#!/bin/bash
# =============================================================
# setup_https.sh — Configura DuckDNS + SSL (Let's Encrypt)
# Execute após setup.sh:
#   bash deploy/setup_https.sh
# =============================================================
set -e

# ─── EDITE ESTAS VARIÁVEIS ───────────────────────────────────
DUCKDNS_SUBDOMAIN="meu-agente"          # só o subdomínio, sem .duckdns.org
DUCKDNS_TOKEN="seu-token-duckdns-aqui"
EMAIL="seu@email.com"                   # para notificações do Let's Encrypt
# ─────────────────────────────────────────────────────────────

DOMAIN="${DUCKDNS_SUBDOMAIN}.duckdns.org"

echo "=== [1/4] Atualizando IP no DuckDNS ==="
curl -s "https://www.duckdns.org/update?domains=${DUCKDNS_SUBDOMAIN}&token=${DUCKDNS_TOKEN}&ip=" | grep -q "OK" && echo "IP atualizado!" || echo "Falha ao atualizar DuckDNS — verifique token e subdomínio"

echo "=== [2/4] Configurando nginx ==="
# Substitui placeholder pelo domínio real
sudo sed -i "s/SEU_DOMINIO.duckdns.org/${DOMAIN}/" /opt/agente-metas/deploy/nginx.conf
sudo cp /opt/agente-metas/deploy/nginx.conf /etc/nginx/sites-available/agente-metas
sudo ln -sf /etc/nginx/sites-available/agente-metas /etc/nginx/sites-enabled/agente-metas
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx

echo "=== [3/4] Obtendo certificado SSL com certbot ==="
sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email "$EMAIL" --redirect

echo "=== [4/4] Renovação automática (já ativa via systemd timer) ==="
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer

echo ""
echo "======================================================"
echo " HTTPS configurado com sucesso!"
echo " Domínio: https://${DOMAIN}"
echo ""
echo " Agora configure o webhook do Telegram:"
echo "   curl -X POST https://api.telegram.org/bot\$TELEGRAM_BOT_TOKEN/setWebhook \\"
echo "        -d url=https://${DOMAIN}/webhook"
echo ""
echo " E inicie o serviço:"
echo "   sudo systemctl start agente-metas"
echo "   sudo systemctl status agente-metas"
echo "======================================================"
