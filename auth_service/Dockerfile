# Imagem base
FROM python:3.11-slim

# Diretório de trabalho do microsserviço
WORKDIR /app

# Instala as dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da autenticação
COPY . .

# Expõe a porta 3000 para uso interno na rede Docker
EXPOSE 3000

# Comando para iniciar o servidor de autenticação
CMD ["uvicorn", "auth:app", "--host", "0.0.0.0", "--port", "3000"]