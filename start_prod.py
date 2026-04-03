"""
Starter de produção — sem ngrok, apenas uvicorn.
Usado pelo systemd no servidor Oracle Cloud.
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
