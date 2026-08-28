# 🎬 TomFlix App - FATEC

Projeto acadêmico de desenvolvimento web estruturado em contêineres Docker, simulando uma plataforma de streaming. O sistema evoluiu de uma arquitetura monolítica (Atividade 1) para uma arquitetura baseada em microsserviços com comunicação em rede interna (Atividade 2).

---

## 📌 Atividade 1: Estruturação Inicial e Banco de Dados

Nesta primeira etapa, o objetivo foi construir a interface principal da aplicação (Catálogo) e integrá-la a um banco de dados relacional (MariaDB) utilizando o FastAPI.

### Funcionalidades Implementadas
* Construção da interface com HTML/CSS (Jinja2).
* Modelagem do banco de dados (Tabelas: Usuários, Favoritos, Comentários).
* Integração com a API externa do TheMovieDB.
* Conteinerização do banco de dados e da aplicação principal via `docker-compose`.

### Evidências Visuais (Atividade 1)

**1. Tela de Login e Cadastro (Visual Dark Mode):**
![Tela de Login](assets/img/telaLogin.png)

**2. Catálogo de Filmes e Integração TMDB:**
![Tela do Catálogo](assets/img/catalogoTomflix.png)

**3. Tabela de Usuários no Banco de Dados:**
![Banco de Dados](assets/img/bancoDados.png)

---

## 🔒 Atividade 2: Microsserviços e Recuperação de Senha

Nesta segunda etapa, a arquitetura foi refatorada para isolar a responsabilidade de segurança. O acesso ao banco de dados para login e cadastro foi removido do Catálogo e transferido para um Microsserviço de Autenticação isolado.

### Funcionalidades Implementadas
* **Microsserviço de Autenticação:** Contêiner isolado rodando na porta interna 3000, invisível para a internet.
* **Comunicação Interna:** O Catálogo agora atua como proxy, enviando requisições HTTP (`requests`) para o microsserviço.
* **Recuperação de Senha Segura:** Geração de Tokens UUID únicos no banco de dados com limite de expiração ($\Delta t = 30 \text{ min}$).
* **Serviço de E-mail (SMTP):** Integração com o Mailtrap para disparo de links de redefinição de senha em ambiente de testes.
* **Sistema de Notificações (UX):** Redirecionamento inteligente com Flash Messages (Toasts) dinâmicas e coloridas na tela inicial.

### Evidências Visuais (Atividade 2)

**1. Recebimento do E-mail de Recuperação (Mailtrap):**
*Comprova a comunicação do microsserviço com o servidor SMTP através da porta 587.*
![E-mail no Mailtrap](assets/img/emailMailTrap.png)

**2. Tela de Redefinição de Senha:**
*Interface padronizada que injeta o token temporal oculto.*
![Nova Senha](assets/img/novaSenha.png)

**3. Validação de Segurança (Token Expirado/Inválido):**
*Comprova que o sistema recusa a reutilização de links, exibindo alerta vermelho dinâmico.*
![Erro de Token Inválido](assets/img/erroTokenInvalido.png)

**4. Notificação de Sucesso:**
*Comprova a sincronização do backend com a interface, exibindo alerta verde após a troca da senha.*
![Sucesso na Troca de Senha](assets/img/alteracaoSenha.png)

---
*Desenvolvido por Marcio Hernani - Estudante de Tecnologia em Sistemas Inteligentes*
---
*Disciplina: Computação em Nuvem - Professor Me. Allan L. R. Siriani* - (@siriani).
