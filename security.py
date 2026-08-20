from passlib.context import CryptContext

# Define o algoritmo de hash seguro (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def gerar_hash_senha(senha: str):
    """Transforma a senha em um código embaralhado."""
    return pwd_context.hash(senha)

def verificar_senha(senha_pura: str, senha_hash: str):
    """Compara a senha digitada com o hash salvo no banco."""
    return pwd_context.verify(senha_pura, senha_hash)