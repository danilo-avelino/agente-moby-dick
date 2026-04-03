"""
Inicializa o Agente das Metas com ngrok + servidor FastAPI (Telegram).

Uso:
    python start.py
"""
import os
import sys
import subprocess
import time
from dotenv import load_dotenv

load_dotenv()


def start() -> None:
    try:
        from pyngrok import ngrok
    except ImportError:
        print("pyngrok nao instalado. Execute: bash install.sh")
        sys.exit(1)

    auth_token = os.getenv("NGROK_AUTH_TOKEN")
    if auth_token:
        ngrok.set_auth_token(auth_token)

    # Encerra qualquer processo ngrok ativo
    subprocess.run(["taskkill", "/F", "/IM", "ngrok.exe"], capture_output=True)

    # Libera a porta 8000 se estiver ocupada
    result = subprocess.run(
        ["netstat", "-ano"],
        capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        if ":8000 " in line and "LISTENING" in line:
            parts = line.split()
            pid = parts[-1]
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)

    time.sleep(2)

    tunnel = ngrok.connect(8000)
    public_url = tunnel.public_url
    webhook_url = f"{public_url}/webhook"

    # Configura webhook no Telegram
    from tools.telegram_client import set_webhook
    result = set_webhook(webhook_url)
    webhook_ok = result.get("ok", False)

    print("\n" + "=" * 62)
    print("AGENTE DAS METAS (Telegram) — INICIANDO")
    print("=" * 62)
    print(f"\nURL publica (ngrok): {public_url}")
    print(f"Webhook URL:         {webhook_url}")
    webhook_status = "OK" if webhook_ok else f"ERRO — {result.get('description', '')}"
    print(f"Webhook Telegram:    {webhook_status}")
    print("\n" + "=" * 62)
    print("Servidor iniciando na porta 8000...")
    print("Ctrl+C para encerrar")
    print("=" * 62 + "\n")

    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    start()
