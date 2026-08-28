from fastapi import FastAPI, Form, HTTPException
import mysql.connector
import bcrypt
import uuid
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
import os

app = FastAPI(title="Microsserviço de Autenticação")

def get_db_connection():
    """Cria a conexão isolada do microsserviço com o banco de dados."""
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )

@app.post("/cadastrar")
def cadastrar(nome: str = Form(...), email: str = Form(...), senha: str = Form(...)):
    """Recebe os dados do Catálogo, criptografa a senha e salva no banco."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    salt = bcrypt.gensalt()
    senha_hash = bcrypt.hashpw(senha.encode('utf-8'), salt).decode('utf-8')
    
    try:
        cursor.execute(
            "INSERT INTO usuarios (nome, email, senha_hash, role) VALUES (%s, %s, %s, %s)", 
            (nome, email, senha_hash, 'usuario')
        )
        conn.commit()
    except Exception:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")
    
    cursor.close()
    conn.close()
    return {"status": "sucesso"}

@app.post("/login")
def login(email: str = Form(...), senha: str = Form(...)):
    """Valida as credenciais e devolve o ID e o Papel (Role) do usuário."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT id, senha_hash, role FROM usuarios WHERE email = %s", (email,))
    user = cursor.fetchone()
    
    cursor.close()
    conn.close()

    if user and bcrypt.checkpw(senha.encode('utf-8'), user['senha_hash'].encode('utf-8')):
        return {"status": "sucesso", "usuario_id": user['id'], "role": user['role']}
    
    raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")

@app.post("/esqueci-senha")
def esqueci_senha(email: str = Form(...)):
    """Gera um token UUID único, salva no banco e dispara o e-mail."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT id FROM usuarios WHERE email = %s", (email,))
    user = cursor.fetchone()
    
    # Se o usuário não existir, retornamos sucesso mesmo assim (evita enumeração/ataques)
    if not user:
        cursor.close()
        conn.close()
        return {"status": "sucesso", "message": "Se o e-mail existir, um link foi enviado."}

    # Gera o token e define a expiração para 30 minutos no futuro
    token = str(uuid.uuid4())
    expira_em = datetime.now() + timedelta(minutes=30)
    
    cursor.execute(
        "INSERT INTO reset_tokens (token, usuario_id, expira_em) VALUES (%s, %s, %s)",
        (token, user['id'], expira_em)
    )
    conn.commit()
    cursor.close()
    conn.close()

    # Integração real com SMTP (Mailtrap)
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    
    # Este link será interceptado pelo Catálogo na próxima etapa
    link = f"http://localhost:8221/nova-senha?token={token}"
    
    msg = MIMEText(f"Acesse o link para redefinir sua senha:\n{link}\n\nEste link expira em 30 minutos.")
    msg['Subject'] = 'Redefinição de Senha - TomFlix'
    msg['From'] = 'suporte@tomflix.com'
    msg['To'] = email

    try:
        # Trocando a porta para 587 e adicionando um limite de 10 segundos
        with smtplib.SMTP("sandbox.smtp.mailtrap.io", 587, timeout=10) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(msg['From'], [msg['To']], msg.as_string())
    except Exception as e:
        raise HTTPException(status_code=500, detail="Erro ao conectar com o serviço de e-mail.")
    
    return {"status": "sucesso", "message": "E-mail de recuperação enviado."}

@app.post("/resetar-senha")
def resetar_senha(token: str = Form(...), nova_senha: str = Form(...)):
    """Valida o token temporal e aplica o Hash na nova senha."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Verifica 3 coisas simultaneamente: token existe? não foi usado?
    cursor.execute("SELECT * FROM reset_tokens WHERE token = %s AND usado = FALSE", (token,))
    registro = cursor.fetchone()
    
    if not registro:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=400, detail="Token inválido ou já utilizado.")
        
    # Verifica a expiração temporal
    if datetime.now() > registro['expira_em']:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=400, detail="Este link de recuperação expirou.")

    # Criptografa a nova senha
    salt = bcrypt.gensalt()
    senha_hash = bcrypt.hashpw(nova_senha.encode('utf-8'), salt).decode('utf-8')
    
    # Atualiza a senha na tabela principal e queima o token na tabela secundária
    cursor.execute("UPDATE usuarios SET senha_hash = %s WHERE id = %s", (senha_hash, registro['usuario_id']))
    cursor.execute("UPDATE reset_tokens SET usado = TRUE WHERE token = %s", (token,))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return {"status": "sucesso", "message": "Senha atualizada com êxito."}