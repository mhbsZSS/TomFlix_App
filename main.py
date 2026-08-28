from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import os
import requests # O Pulo do Gato: Biblioteca para fazer requisições HTTP internas
from database import get_db_connection

app = FastAPI(title="TomFlix App")

app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY"))
templates = Jinja2Templates(directory="templates")

# Endereço interno do microsserviço (definido no docker-compose.yml)
AUTH_URL = "http://auth-service:3000"

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
