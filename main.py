from fastapi import FastAPI, Request, Form, HTTPException, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import os
import requests # O Pulo do Gato: Biblioteca para fazer requisições HTTP internas
from database import get_db_connection
import uuid # Para gerar nomes únicos para as fotos
from datetime import timedelta # Para o tempo de expiração da URL
from minio import Minio
from minio.error import S3Error

# ==========================================
# CONFIGURAÇÃO DO MINIO (OBJECT STORAGE)
# ==========================================
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin_tomflix")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "SenhaForte123!")
MINIO_BUCKET_NAME = os.getenv("MINIO_BUCKET_NAME", "perfis-tomflix")

# Inicializa o cliente do MinIO
minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False # False porque estamos rodando local/Docker sem certificado SSL
)

# Garante que o bucket existe ao iniciar a aplicação
try:
    if not minio_client.bucket_exists(MINIO_BUCKET_NAME):
        minio_client.make_bucket(MINIO_BUCKET_NAME)
        print(f"Bucket '{MINIO_BUCKET_NAME}' criado com sucesso no MinIO.")
except S3Error as e:
    print(f"Erro ao conectar com o MinIO: {e}")

app = FastAPI(title="TomFlix App")

app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY"))
templates = Jinja2Templates(directory="templates")

# Endereço interno do microsserviço (definido no docker-compose.yml)
AUTH_URL = "http://auth-service:3000"
LOG_URL = os.getenv("LOG_URL", "http://log-service:4000") # <-- ADICIONE AQUI

# --- FUNÇÃO DE AUDITORIA ---
def disparar_log_auditoria(request: Request, usuario_id: int, acao: str):
    try:
        ip = request.client.host if request.client else "Desconhecido"
        payload = {"usuario_id": str(usuario_id), "acao": acao, "ip_origem": ip}
        requests.post(f"{LOG_URL}/log", json=payload, timeout=2)
    except Exception as e:
        print(f"Aviso: Falha ao enviar log para auditoria - {e}")

@app.get("/", response_class=HTMLResponse)
def tela_login(request: Request):
    if request.session.get("usuario_id"):
        return RedirectResponse(url="/catalogo", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html")

@app.post("/cadastrar")
def cadastrar_usuario(request: Request, nome: str = Form(...), email: str = Form(...), senha: str = Form(...)):
    try:
        resposta = requests.post(f"{AUTH_URL}/cadastrar", data={"nome": nome, "email": email, "senha": senha}, timeout=10)
        if resposta.status_code == 200:
            return RedirectResponse(url="/?msg=cadastro_sucesso", status_code=303)
        # O Pulo do Gato: Redireciona com mensagem de erro em vez de tela preta
        return RedirectResponse(url="/?msg=erro_cadastro", status_code=303)
    except requests.exceptions.RequestException:
        return RedirectResponse(url="/?msg=erro_offline", status_code=303)

@app.post("/login")
def realizar_login(request: Request, email: str = Form(...), senha: str = Form(...)):
    try:
        resposta = requests.post(f"{AUTH_URL}/login", data={"email": email, "senha": senha}, timeout=10)
        if resposta.status_code == 200:
            dados = resposta.json()
            request.session["usuario_id"] = dados["usuario_id"]
            request.session["role"] = dados["role"] 
            return RedirectResponse(url="/catalogo", status_code=303)
        # Redireciona em caso de credencial inválida
        return RedirectResponse(url="/?msg=erro_login", status_code=303)
    except requests.exceptions.RequestException:
        return RedirectResponse(url="/?msg=erro_offline", status_code=303)

@app.post("/esqueci-senha")
def esqueci_senha(request: Request, email: str = Form(...)):
    try:
        requests.post(f"{AUTH_URL}/esqueci-senha", data={"email": email}, timeout=10)
        return RedirectResponse(url="/?msg=email_enviado", status_code=303)
    except requests.exceptions.RequestException:
        return RedirectResponse(url="/?msg=erro_offline", status_code=303)
    
@app.get("/nova-senha", response_class=HTMLResponse)
def tela_nova_senha(request: Request, token: str):
    return templates.TemplateResponse(request=request, name="nova_senha.html", context={"token": token})

@app.post("/resetar-senha")
def resetar_senha(request: Request, token: str = Form(...), nova_senha: str = Form(...)):
    try:
        resposta = requests.post(f"{AUTH_URL}/resetar-senha", data={"token": token, "nova_senha": nova_senha}, timeout=10)
        if resposta.status_code == 200:
            return RedirectResponse(url="/?msg=senha_alterada", status_code=303)
        # Captura o token inválido/expirado e devolve para o início
        return RedirectResponse(url="/?msg=token_invalido", status_code=303)
    except requests.exceptions.RequestException:
        return RedirectResponse(url="/?msg=erro_offline", status_code=303)
            
@app.get("/logout")
def sair(request: Request):
    usuario_id = request.session.get("usuario_id")
    
    # --- NOVO: Dispara log de auditoria de Logout antes de limpar a sessão ---
    if usuario_id:
        disparar_log_auditoria(request, usuario_id, "logout")
        
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)

@app.post("/favoritar")
def favoritar_filme(
    request: Request,
    tmdb_movie_id: int = Form(...),
    titulo: str = Form(...),
    poster_path: str = Form(...)
):
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return RedirectResponse(url="/", status_code=303)

    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Usamos try/except para ignorar o erro caso ele clique duas vezes.
        query = """
            INSERT INTO favoritos (usuario_id, tmdb_movie_id, titulo, poster_path)
            VALUES (%s, %s, %s, %s)
        """
        cursor.execute(query, (usuario_id, tmdb_movie_id, titulo, poster_path))
        conn.commit()
        
        # --- NOVO: Dispara log de auditoria ---
        disparar_log_auditoria(request, usuario_id, f"favoritou_filme_{tmdb_movie_id}")
        
    except Exception:

        conn.rollback()
    finally:
        cursor.close()
        conn.close()

    return RedirectResponse(url="/catalogo", status_code=303)

@app.post("/comentar")
def comentar_filme(
    request: Request,
    tmdb_movie_id: int = Form(...),
    texto: str = Form(...)
):
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return RedirectResponse(url="/", status_code=303)

    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        query = "INSERT INTO comentarios (usuario_id, tmdb_movie_id, texto) VALUES (%s, %s, %s)"
        cursor.execute(query, (usuario_id, tmdb_movie_id, texto))
        conn.commit()
        
        # --- NOVO: Dispara log de auditoria ---
        disparar_log_auditoria(request, usuario_id, f"comentou_no_filme_{tmdb_movie_id}")
        
    finally:
        cursor.close()
        conn.close()

    return RedirectResponse(url="/catalogo", status_code=303)
@app.post("/apagar-comentario/{comentario_id}")
def apagar_comentario(request: Request, comentario_id: int):
    usuario_id = request.session.get("usuario_id")
    role = request.session.get("role")

    if not usuario_id:
        return RedirectResponse(url="/", status_code=303)

    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Busca quem é o dono original do comentário no banco
        cursor.execute("SELECT usuario_id FROM comentarios WHERE id = %s", (comentario_id,))
        resultado = cursor.fetchone()
        
        if not resultado:
            raise HTTPException(status_code=404, detail="Comentário não encontrado.")
            
        dono_id = resultado[0]

        # ==========================================
        # 2. ENFORCEMENT (RBAC de verdade)
        # ==========================================
        # Regra: Se o usuário NÃO for admin E NÃO for o dono do comentário -> Bloqueia com 403
        if role != "admin" and dono_id != usuario_id:
            # --- NOVO: Log de Segurança (Tentativa Negada) ---
            disparar_log_auditoria(request, usuario_id, f"tentativa_negada_403_apagar_comentario_{comentario_id}")
            
            raise HTTPException(
                status_code=403, 
                detail="Acesso negado: Apenas administradores podem apagar comentários de outros usuários."
            )

        # 3. Executa a ação caso passe pela barreira
        cursor.execute("DELETE FROM comentarios WHERE id = %s", (comentario_id,))
        conn.commit()
        
        # --- NOVO: Log de Sucesso ---
        disparar_log_auditoria(request, usuario_id, f"apagou_comentario_{comentario_id}")

        return RedirectResponse(url="/catalogo", status_code=303)
    
    finally:
        cursor.close()
        conn.close()

@app.get("/catalogo", response_class=HTMLResponse)
def exibir_catalogo(request: Request):
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return RedirectResponse(url="/", status_code=303)
    
    tmdb_key = os.getenv("TMDB_API_KEY")
    if not tmdb_key:
        raise HTTPException(status_code=500, detail="API Key do TMDB ausente no .env")

    # --- 1. CHAMADAS AO TMDB ---
    url_search = f"https://api.themoviedb.org/3/search/person?query=Tom+Hanks&api_key={tmdb_key}&language=pt-BR"
    resposta_search = requests.get(url_search).json()
    person_id = resposta_search["results"][0]["id"]
    
    url_movies = f"https://api.themoviedb.org/3/person/{person_id}/movie_credits?api_key={tmdb_key}&language=pt-BR"
    resposta_movies = requests.get(url_movies).json()
    
    filmes = [f for f in resposta_movies.get("cast", []) if f.get("poster_path")]

    # --- 2. BUSCA NO BANCO DE DADOS (SEGREGAÇÃO) ---
    conn = get_db_connection()
    cursor = conn.cursor()

    # -----------------------------------------------------
    # NOVO: Busca o nome do usuário logado para o cabeçalho
    # -----------------------------------------------------
    cursor.execute("SELECT nome FROM usuarios WHERE id = %s", (usuario_id,))
    resultado_usuario = cursor.fetchone()
    nome_usuario = resultado_usuario[0] if resultado_usuario else "Usuário"

    # Busca os favoritos do usuário logado
    cursor.execute("SELECT tmdb_movie_id FROM favoritos WHERE usuario_id = %s", (usuario_id,))
    favoritos_ids = [linha[0] for linha in cursor.fetchall()]

    # Busca TODOS os comentários (trazendo o ID do comentário e quem escreveu)
    cursor.execute("SELECT id, tmdb_movie_id, texto, usuario_id FROM comentarios ORDER BY criado_em DESC")
    comentarios_db = cursor.fetchall()
    
    cursor.close()
    conn.close()

    # Agrupa os comentários como dicionários para o HTML ter acesso aos IDs
    comentarios_por_filme = {}
    for cid, movie_id, texto, uid in comentarios_db:
        if movie_id not in comentarios_por_filme:
            comentarios_por_filme[movie_id] = []
        comentarios_por_filme[movie_id].append({
            "id": cid,
            "texto": texto,
            "usuario_id": uid
        })

    # --- 3. RENDERIZAÇÃO ---
    # Enviamos também a 'role' e o 'usuario_id' para o HTML saber quando desenhar o botão de apagar
    return templates.TemplateResponse(
        request, 
        "catalogo.html", 
        {
            "filmes": filmes,
            "favoritos": favoritos_ids,
            "comentarios": comentarios_por_filme,
            "role": request.session.get("role"),
            "usuario_logado_id": usuario_id,
            "nome_usuario": nome_usuario
        }
    )

@app.get("/auditoria", response_class=HTMLResponse)
def painel_auditoria(request: Request):
    usuario_id = request.session.get("usuario_id")
    role = request.session.get("role")

    # 1. Verifica se está logado
    if not usuario_id:
        return RedirectResponse(url="/", status_code=303)
        
    # ==========================================
    # 2. ENFORCEMENT (Obrigatório para o Requisito 5)
    # ==========================================
    if role != "admin":
        # Dispara um log rastreando a tentativa de invasão ao painel
        disparar_log_auditoria(request, usuario_id, "tentativa_acesso_painel_auditoria_403")
        raise HTTPException(
            status_code=403, 
            detail="Acesso negado: Rota exclusiva para administradores do sistema."
        )

    # 3. Consome os dados do microsserviço de log
    try:
        # Faz um GET na porta 4000 do contêiner log-service
        resposta = requests.get(f"{LOG_URL}/logs?limite=100", timeout=5)
        logs = resposta.json().get("logs", []) if resposta.status_code == 200 else []
    except Exception as e:
        print(f"Erro ao buscar logs: {e}")
        logs = []

    # 4. Busca os nomes dos usuários para a tabela ficar legível
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, nome FROM usuarios")
    usuarios_db = {str(u['id']): u['nome'] for u in cursor.fetchall()}
    cursor.close()
    conn.close()

    # Enriquece os logs com os nomes reais
    for log in logs:
        uid = log.get("usuario_id")
        log["nome_usuario"] = usuarios_db.get(uid, f"ID {uid}")

    return templates.TemplateResponse(
        request, 
        "auditoria.html", 
        {
            "logs": logs,
            "role": role,
            "nome_usuario": request.session.get("nome_usuario", "Admin")
        }
    )

@app.get("/perfil", response_class=HTMLResponse)
def pagina_perfil(request: Request):
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return RedirectResponse(url="/", status_code=303)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Busca os dados do usuário
    cursor.execute("SELECT nome, foto_perfil, bio FROM usuarios WHERE id = %s", (usuario_id,))
    usuario = cursor.fetchone()

    # Busca os filmes favoritos desse usuário
    cursor.execute("""
        SELECT f.id, f.titulo, f.ano 
        FROM favoritos fav
        JOIN filmes f ON fav.filme_id = f.id
        WHERE fav.usuario_id = %s
    """, (usuario_id,))
    favoritos = cursor.fetchall()
    cursor.close()
    conn.close()

    # REQUISITO 3: Geração da URL Pré-assinada
    foto_url = None
    if usuario and usuario.get("foto_perfil"):
        try:
            foto_url = minio_client.presigned_get_object(
                MINIO_BUCKET_NAME, 
                usuario["foto_perfil"],
                expires=timedelta(hours=1) # O link morre em 1 hora
            )
        except Exception as e:
            print(f"Erro ao gerar URL da foto: {e}")

    return templates.TemplateResponse(
        request, 
        "perfil.html", 
        {
            "usuario": usuario, 
            "favoritos": favoritos,
            "foto_url": foto_url,
            "nome_usuario": request.session.get("nome_usuario"),
            "role": request.session.get("role")
        }
    )

@app.post("/perfil/editar")
async def editar_perfil(
    request: Request,
    bio: str = Form(""),
    foto: UploadFile = File(None)
):
    # REQUISITO 4: Identidade verificada apenas pela sessão (não confia no frontend)
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        raise HTTPException(status_code=401, detail="Não autorizado")

    nome_arquivo = None

    # REQUISITO 2: Validação de Upload
    if foto and foto.filename:
        # Valida o tipo MIME (deve começar com 'image/')
        if not foto.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Apenas ficheiros de imagem (JPG, PNG, etc.) são permitidos.")
        
        # Valida o tamanho físico do arquivo (Máximo 2MB)
        foto.file.seek(0, 2) # Move o cursor para o final do ficheiro
        tamanho = foto.file.tell() # Pega o tamanho em bytes
        foto.file.seek(0) # Volta o cursor para o início para poder ler e salvar
        
        if tamanho > 2 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="A imagem deve ter no máximo 2MB.")

        # Gera um nome único no MinIO (ex: perfil_3_a1b2c3d4.jpg)
        extensao = foto.filename.split(".")[-1]
        nome_arquivo = f"perfil_{usuario_id}_{uuid.uuid4().hex}.{extensao}"

        try:
            # Envia o ficheiro binário para o MinIO
            minio_client.put_object(
                MINIO_BUCKET_NAME,
                nome_arquivo,
                foto.file,
                length=tamanho,
                content_type=foto.content_type
            )
        except S3Error as e:
            print(f"Erro no upload do MinIO: {e}")
            raise HTTPException(status_code=500, detail="Erro ao salvar a imagem no servidor.")

    # Atualiza a referência no MariaDB
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if nome_arquivo:
        # Atualiza bio e a foto
        cursor.execute(
            "UPDATE usuarios SET bio = %s, foto_perfil = %s WHERE id = %s", 
            (bio, nome_arquivo, usuario_id)
        )
    else:
        # Atualiza apenas a bio, mantendo a foto antiga intacta
        cursor.execute(
            "UPDATE usuarios SET bio = %s WHERE id = %s", 
            (bio, usuario_id)
        )
        
    conn.commit()
    cursor.close()
    conn.close()

    return RedirectResponse(url="/perfil", status_code=303)