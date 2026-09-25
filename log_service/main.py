import os
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import redis

app = FastAPI(title="TomFlix - Log de Auditoria")

# --- CONEXÃO COM O REDIS ---
# O host é o nome do container ("redis") que definimos no docker-compose.yml
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# decode_responses=True garante que os dados voltem como strings limpas (e não bytes)
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

STREAM_NAME = "tomflix_audit_stream"

# --- MODELO DE DADOS ---
class LogEvent(BaseModel):
    usuario_id: str
    acao: str
    ip_origem: str | None = "Desconhecido"

# --- ROTA DE GRAVAÇÃO (Usada pelos outros microsserviços) ---
@app.post("/log")
async def registrar_log(evento: LogEvent):
    try:
        # Monta o dicionário que será salvo no banco em memória
        log_data = {
            "usuario_id": evento.usuario_id,
            "acao": evento.acao,
            "ip_origem": evento.ip_origem,
            "timestamp": datetime.now().isoformat()
        }
        
        # O comando XADD adiciona o evento ao Stream. 
        # O '*' diz para o próprio Redis gerar o ID único baseado no tempo.
        redis_client.xadd(STREAM_NAME, log_data)
        
        return {"status": "sucesso", "mensagem": "Log registrado no Redis."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- ROTA DE LEITURA (Usada pelo Admin) ---
@app.get("/logs")
async def consultar_logs(limite: int = 50):
    try:
        # O comando XREVRANGE busca os dados do fim para o começo (do mais novo pro mais velho)
        # max='+' (id mais alto) e min='-' (id mais baixo)
        eventos_brutos = redis_client.xrevrange(STREAM_NAME, max='+', min='-', count=limite)
        
        logs_formatados = []
        for redis_id, dados in eventos_brutos:
            # Anexa o ID real do Redis ao retorno para referência
            dados["redis_id"] = redis_id
            logs_formatados.append(dados)
            
        return {"logs": logs_formatados}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))