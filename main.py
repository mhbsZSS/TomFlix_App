from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import os
import requests
from database import get_db_connection
from security import gerar_hash_senha, verificar_senha

app = FastAPI(title="TomFlix App")

# Ativa as sessões usando a chave secreta do seu .env
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY"))

# Aponta para a pasta onde criaremos nossos arquivos de tela (HTML)
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
def tela_login(request: Request):
    """Rota inicial: Mostra o login ou redireciona se já estiver logado."""
    if request.session.get("usuario_id"):
        return RedirectResponse(url="/catalogo", status_code=303)
    
    # Parâmetros declarados explicitamente resolvem o bug do dict!
    return templates.TemplateResponse(request=request, name="login.html")

@app.post("/cadastrar")
def cadastrar_usuario(request: Request, nome: str = Form(...), email: str = Form(...), senha: str = Form(...)):
    """Recebe os dados, aplica o hash na senha e salva no MariaDB/MySQL."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Erro de banco de dados")
    
    cursor = conn.cursor()
    senha_segura = gerar_hash_senha(senha) # segurança
    
    try:
        query = "INSERT INTO usuarios (nome, email, senha_hash) VALUES (%s, %s, %s)"
        cursor.execute(query, (nome, email, senha_segura))
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail="Erro ao cadastrar. E-mail pode já estar em uso.")
    
    cursor.close()
    conn.close()
    
    # Redireciona de volta para a tela inicial para o usuário fazer login
    return RedirectResponse(url="/", status_code=303)

@app.post("/login")
def realizar_login(request: Request, email: str = Form(...), senha: str = Form(...)):
    """Verifica credenciais e inicia a sessão do usuário."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, senha_hash FROM usuarios WHERE email = %s", (email,))
    usuario = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if usuario and verificar_senha(senha, usuario[1]):
        # Segregação: gravamos o ID na sessão!
        request.session["usuario_id"] = usuario[0]
        return RedirectResponse(url="/catalogo", status_code=303)
    
    raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")

@app.get("/logout")
def sair(request: Request):
    """Limpa a sessão, essencial para testar múltiplas contas."""
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
    finally:
        cursor.close()
        conn.close()

    return RedirectResponse(url="/catalogo", status_code=303)

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
    
    # Busca os favoritos do usuário logado
    cursor.execute("SELECT tmdb_movie_id FROM favoritos WHERE usuario_id = %s", (usuario_id,))
    favoritos_ids = [linha[0] for linha in cursor.fetchall()]

    # Busca os comentários do usuário logado
    cursor.execute("SELECT tmdb_movie_id, texto FROM comentarios WHERE usuario_id = %s ORDER BY criado_em DESC", (usuario_id,))
    comentarios_db = cursor.fetchall()
    
    cursor.close()
    conn.close()

    # Agrupa os comentários por ID do filme para facilitar no HTML
    comentarios_por_filme = {}
    for movie_id, texto in comentarios_db:
        if movie_id not in comentarios_por_filme:
            comentarios_por_filme[movie_id] = []
        comentarios_por_filme[movie_id].append(texto)

    # --- 3. RENDERIZAÇÃO ---
    return templates.TemplateResponse(
        request, 
        "catalogo.html", 
        {
            "filmes": filmes,
            "favoritos": favoritos_ids,
            "comentarios": comentarios_por_filme
        }
    
    )
