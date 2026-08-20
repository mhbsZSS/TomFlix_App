import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

# O Pulo do Gato: load_dotenv() puxa as variáveis do arquivo .env para a memória
load_dotenv()

def get_db_connection():
    """Cria e retorna uma conexão segura com o banco de dados."""
    try:
        connection = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME")
        )
        if connection.is_connected():
            return connection
    except Error as e:
        print(f"Erro crítico ao conectar ao MySQL: {e}")
        return None