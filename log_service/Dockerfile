# Usamos a imagem oficial do Python em sua versão "slim" para um contêiner mais leve e rápido
FROM python:3.10-slim

# Define a pasta de trabalho dentro do contêiner
WORKDIR /app

# Copia apenas o arquivo de dependências primeiro (otimiza o cache do Docker)
COPY requirements.txt .

# Instala as bibliotecas necessárias sem armazenar cache inútil
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante do código do serviço para dentro do contêiner
COPY . .

# Expõe a porta 4000 (a mesma que definimos no docker-compose.yml)
EXPOSE 4000

# Comando para iniciar o servidor web do FastAPI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "4000"]