from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, abort, g
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import sqlite3
import logging
from datetime import datetime, timedelta
import os
import sys
from auth.session_manager import init_session, end_session, validate_session

# Adiciona o diretório principal ao path para importações relativas
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.database import get_db_connection
from models.users import Usuario

# Criar o blueprint de autenticação
auth_bp = Blueprint('auth', __name__)

# ========================
# DECORADORES DE AUTENTICAÇÃO
# ========================

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user' not in session:
            flash('Por favor, faça login para acessar esta página.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user' not in session or session.get('nivel') != 'admin':
            flash('Acesso restrito a administradores.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return wrapper

def gr_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        print(f"GR_REQUIRED - Session: user={session.get('user', 'None')}, nivel={session.get('nivel', 'None')}")
        if 'user' not in session or session.get('nivel') not in ['gr', 'admin']:
            print("GR_REQUIRED - Acesso negado: usuário não tem perfil GR ou admin")
            flash('Acesso restrito à Gestão de Relacionamento.', 'danger')
            return redirect(url_for('auth.login'))
        print("GR_REQUIRED - Acesso permitido")
        return f(*args, **kwargs)
    return wrapper

def admin_or_gr_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user' not in session or session.get('nivel') not in ['admin', 'gr']:
            flash('Acesso restrito a administradores e GR.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return wrapper

# ========================
# FUNÇÕES AUXILIARES
# ========================

def log_action(usuario, acao, detalhes):
    """Registra ações de autenticação no log"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO logs_admin (usuario, acao, detalhes, data_log)
                VALUES (?, ?, ?, ?)
            """, (usuario, acao, detalhes, datetime.now()))
            conn.commit()
    except Exception as e:
        logging.error(f"Erro ao registrar log: {e}")

def redirecionar_por_nivel():
    """Redireciona o usuário com base em seu nível de acesso"""
    try:
        logging.info(f"Conteúdo completo da sessão em redirecionar_por_nivel: {session}")
        
        if 'user' in session:
            username = session.get('user')
            nivel = session.get('nivel')
            
            logging.info(f"Redirecionando usuário {username} com nível {nivel}")
            
            # Verificar se é um usuário administrador (por nível ou nome de usuário)
            if nivel == 'admin' or username in ['admin', 'teste_admin']:
                logging.info(f"Detectado usuário administrativo: {username}, tentando redirecionar para dashboard administrativo")
                # Tente redirecionar para o dashboard admin, se falhar, use uma rota alternativa
                try:
                    logging.info("Tentando redirecionar para /admin/dashboard diretamente")
                    return redirect('/admin/dashboard')
                except Exception as e:
                    logging.error(f"Erro ao redirecionar para /admin/dashboard: {e}")
                    # Tente usar url_for como alternativa
                    try:
                        logging.info("Tentando url_for('admin.admin_dashboard') como alternativa")
                        url = url_for('admin.admin_dashboard')
                        logging.info(f"URL gerada: {url}")
                        return redirect(url)
                    except Exception as e2:
                        logging.error(f"Erro ao gerar URL com url_for: {e2}")
                        # Última tentativa - redirecionar para a raiz
                        return redirect('/')
            
            # Verificar se é um usuário de gestão de risco
            elif nivel == 'gr':
                logging.info(f"Detectado usuário GR: {username}, redirecionando para gr.ambiente")
                try:
                    return redirect(url_for('gr.ambiente'))
                except Exception as e:
                    logging.error(f"Erro ao redirecionar para gr.ambiente: {e}")
                    return redirect('/gr/ambiente')
            
            # Caso contrário, é um usuário comum
            else:
                logging.info(f"Detectado usuário comum: {username}, redirecionando para comum.dashboard_comum")
                try:
                    return redirect(url_for('comum.dashboard_comum'))
                except Exception as e:
                    logging.error(f"Erro ao redirecionar para comum.dashboard_comum: {e}")
                    return redirect('/comum/dashboard')
        
        logging.warning("Usuário não está na sessão, redirecionando para login")
        return redirect(url_for('auth.login'))
    
    except Exception as e:
        logging.error(f"Erro no redirecionamento por nível: {e}")
        # Em caso de erro, redirecione para a página de login
        return redirect(url_for('auth.login'))

def _validar_tipo_login(nivel, login_type):
    """Valida se o tipo de login é compatível com o nível do usuário"""
    # Se login_type for 'user', apenas usuários comuns podem acessar
    # Se login_type for 'admin', apenas usuários admin ou gr podem acessar
    
    # Adicionar logs para depuração
    logging.info(f"Validando tipo de login: nivel={nivel}, login_type={login_type}")
    
    # Permitir que usuários administradores façam login independentemente do tipo de login
    if nivel == 'admin' or nivel == 'gr':
        return True
    
    # Para usuários comuns, verificar se estão usando a aba correta
    if login_type == 'user':
        return nivel == 'comum'
    elif login_type == 'admin':
        return nivel in ['admin', 'gr']
    
    return False

def verificar_primeiro_login(username):
    """Verifica se é o primeiro login do usuário ou se a senha é temporária"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT primeiro_login, senha_temporaria FROM usuarios WHERE username = ?", (username,))
            resultado = cursor.fetchone()
            
            if resultado:
                # Retorna True se qualquer um dos flags estiver ativado (1)
                return resultado['primeiro_login'] == 1 or resultado['senha_temporaria'] == 1
            return False
    except Exception as e:
        logging.error(f"Erro ao verificar primeiro login: {e}")
        return False

# ========================
# ROTAS DE AUTENTICAÇÃO
# ========================

@auth_bp.route('/')
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Rota de login principal"""
    # Limpar mensagens flash antigas
    if '_flashes' in session:
        session.pop('_flashes', None)
    
    # Se o usuário já está logado, redirecionar para a página apropriada
    if 'user' in session:
        return redirecionar_por_nivel()
    
    if request.method == 'POST':
        username = request.form.get('usuario')
        password = request.form.get('senha')
        login_type = request.form.get('login_type', 'user')  # Obtém o tipo de login (user ou admin)
        
        logging.info(f"Tentativa de login - Usuário: {username}, Tipo de Login: {login_type}")
        
        if not username or not password:
            flash('Por favor, preencha todos os campos.', 'warning')
            return render_template('login.html')
        
        # Usuários de teste para desenvolvimento
        test_users = {
            'teste_admin': {'password': 'Teste@123', 'nivel': 'admin'},
            'teste_gr': {'password': 'Teste@123', 'nivel': 'gr'},
            'teste_comum': {'password': 'Teste@123', 'nivel': 'comum'}
        }
        
        # Verificar se é um usuário de teste
        if username in test_users and password == test_users[username]['password']:
            nivel = test_users[username]['nivel']
            logging.info(f"Tentativa de login com usuário de teste: {username}, senha: {'*' * len(password)}, nível esperado: {nivel}")
            
            # Para usuários de teste admin e gr, sempre permitir o login independentemente da aba
            if nivel in ['admin', 'gr']:
                logging.info(f"Permitindo login para usuário administrativo de teste: {username}")
                # Inicializar a sessão
                session_id = init_session(username, nivel)
                logging.info(f"Sessão inicializada para usuário de teste: {username} com nível {nivel}, session_id={session_id}")
                logging.info(f"Conteúdo da sessão após login: {session}")
                
                try:
                    logging.info(f"Tentando redirecionar usuário admin/gr {username}")
                    return redirecionar_por_nivel()
                except Exception as e:
                    logging.error(f"Erro ao redirecionar usuário de teste: {e}")
                    flash(f"Erro ao redirecionar: {e}", "danger")
                    return render_template('login.html')
            
            # Para usuários comuns, verificar se estão usando a aba correta
            if not _validar_tipo_login(nivel, login_type):
                flash('Você deve usar a aba correta para seu tipo de usuário.', 'danger')
                return render_template('login.html')
            
            # Inicializar a sessão
            session_id = init_session(username, nivel)
            logging.info(f"Sessão inicializada para usuário de teste: {username} com nível {nivel}, session_id={session_id}")
            logging.info(f"Conteúdo da sessão após login: {session}")
            
            try:
                logging.info(f"Tentando redirecionar usuário {username} com nível {nivel}")
                return redirecionar_por_nivel()
            except Exception as e:
                logging.error(f"Erro ao redirecionar usuário de teste: {e}")
                flash(f"Erro ao redirecionar: {e}", "danger")
                return render_template('login.html')
        
        # Verificar usuário no banco de dados
        try:
            user = Usuario.get_by_username(username)
            logging.info(f"Resultado da busca por usuário {username}: {user is not None}")
            
            if not user:
                logging.warning(f"Usuário não encontrado: {username}")
                flash('Usuário não encontrado.', 'danger')
                return render_template('login.html')
            
            # Verificar senha
            senha_valida = Usuario.verify_password(username, password)
            logging.info(f"Senha válida para {username}: {senha_valida}")
            
            if not senha_valida:
                logging.warning(f"Senha incorreta para usuário: {username}")
                flash('Senha incorreta.', 'danger')
                return render_template('login.html')
            
            # Login bem-sucedido
            nivel = user['nivel']
            logging.info(f"Login bem-sucedido para {username} com nível {nivel}")
            
            # Verificar se o tipo de login é compatível com o nível do usuário
            tipo_login_valido = _validar_tipo_login(nivel, login_type)
            logging.info(f"Tipo de login válido para {username}: {tipo_login_valido} (nivel={nivel}, login_type={login_type})")
            
            if not tipo_login_valido:
                logging.warning(f"Tipo de login inválido para {username}: nivel={nivel}, login_type={login_type}")
                flash('Você deve usar a aba correta para seu tipo de usuário.', 'danger')
                return render_template('login.html')
            
            # Inicializar sessão com o novo sistema de gerenciamento
            session_id = init_session(username, nivel)
            logging.info(f"Login de usuário do banco: {username} com nível {nivel}, session_id={session_id}")
            Usuario.update_last_login(username)
            
            # Verificar se é o primeiro login
            primeiro_login = verificar_primeiro_login(username)
            logging.info(f"Primeiro login para {username}: {primeiro_login}")
            
            if primeiro_login:
                logging.info(f"Redirecionando {username} para troca de senha no primeiro login")
                return redirect(url_for('auth.troca_senha_primeiro_login'))
            
            try:
                logging.info(f"Tentando redirecionar {username} por nível após login bem-sucedido")
                return redirecionar_por_nivel()
            except Exception as e:
                logging.error(f"Erro ao redirecionar usuário do banco: {e}")
                flash(f"Erro ao redirecionar: {e}", "danger")
                return render_template('login.html')
            
        except Exception as e:
            logging.error(f"Erro no login: {e}")
            flash('Ocorreu um erro durante o login. Por favor, tente novamente.', 'danger')
            return render_template('login.html')
    
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    """Rota para logout"""
    username = session.get('user', 'Usuário desconhecido')
    logging.info(f"Logout de usuário: {username}")
    # Usar o sistema de gerenciamento de sessões para encerrar a sessão
    end_session()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Rota para registro de novos usuários (solicitação de acesso)"""
    if request.method == 'POST':
        nome = request.form.get('nome')
        username = request.form.get('username')
        email = request.form.get('email')
        setor = request.form.get('setor')
        justificativa = request.form.get('justificativa')
        
        # Validar campos
        if not all([nome, username, email, setor, justificativa]):
            flash('Por favor, preencha todos os campos obrigatórios.', 'warning')
            return render_template('pre_registro.html')
        
        # Verificar se o usuário já existe
        user = Usuario.get_by_username(username)
        if user:
            flash('Este nome de usuário já está em uso. Por favor, escolha outro.', 'warning')
            return render_template('pre_registro.html')
        
        # Registrar a solicitação no banco de dados
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO solicitacoes_registro 
                    (nome, username, email, setor, justificativa, status, data_solicitacao) 
                    VALUES (?, ?, ?, ?, ?, 'pendente', ?)
                """, (nome, username, email, setor, justificativa, datetime.now()))
                conn.commit()
                
                flash('Sua solicitação de acesso foi enviada com sucesso! Um administrador irá analisá-la em breve.', 'success')
                return render_template('registro_confirmacao.html', nome=nome, username=username)
        except sqlite3.IntegrityError as e:
            logging.error(f"Erro de integridade ao registrar solicitação: {e}")
            if 'UNIQUE constraint failed' in str(e):
                flash('Este nome de usuário ou email já está em uso. Por favor, escolha outro.', 'danger')
            else:
                flash(f'Erro de integridade no banco de dados: {str(e)}', 'danger')
        except Exception as e:
            logging.error(f"Erro ao registrar solicitação: {e}")
            flash(f'Ocorreu um erro ao processar sua solicitação: {str(e)}. Por favor, tente novamente.', 'danger')
    
    return render_template('pre_registro.html')

@auth_bp.route('/solicitar_senha', methods=['GET', 'POST'])
def solicitar_senha():
    """Rota para solicitar redefinição de senha"""
    if request.method == 'POST':
        username = request.form.get('username')
        
        if not username:
            flash('Por favor, informe seu nome de usuário.', 'warning')
            return render_template('solicitar_senha.html')
        
        # Verificar se o usuário existe
        user = Usuario.get_by_username(username)
        if not user:
            flash('Usuário não encontrado.', 'danger')
            return render_template('solicitar_senha.html')
        
        # Registrar a solicitação no banco de dados
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Verificar se já existe uma solicitação pendente
                cursor.execute("SELECT * FROM solicitacoes_senha WHERE username = ? AND status = 'pendente'", (username,))
                if cursor.fetchone():
                    flash('Você já possui uma solicitação de redefinição de senha pendente.', 'info')
                    return render_template('solicitar_senha.html')
                
                # Registrar nova solicitação
                cursor.execute("""
                    INSERT INTO solicitacoes_senha 
                    (username, status, data_solicitacao) 
                    VALUES (?, 'pendente', ?)
                """, (username, datetime.now()))
                conn.commit()
                
                flash('Sua solicitação de redefinição de senha foi enviada com sucesso! Um administrador irá processá-la em breve.', 'success')
                return render_template('sucesso.html', mensagem='Solicitação de Redefinição de Senha Enviada', 
                                      submensagem='Um administrador irá analisar sua solicitação em breve.',
                                      redirect_url=url_for('auth.login'))
        except Exception as e:
            logging.error(f"Erro ao solicitar redefinição de senha: {e}")
            flash('Ocorreu um erro ao processar sua solicitação. Por favor, tente novamente.', 'danger')
    
    return render_template('solicitar_senha.html')

@auth_bp.route('/troca_senha_primeiro_login', methods=['GET', 'POST'])
@login_required
def troca_senha_primeiro_login():
    """Rota para troca de senha no primeiro login"""
    username = session.get('user')
    
    # Verificar se é realmente o primeiro login ou senha temporária
    is_primeiro_login = verificar_primeiro_login(username)
    
    if request.method == 'POST':
        senha_nova = request.form.get('senha_nova')
        senha_confirmacao = request.form.get('senha_confirmacao')
        
        if not senha_nova or not senha_confirmacao:
            flash('Por favor, preencha todos os campos.', 'warning')
            return render_template('troca_senha_primeiro_login.html', primeiro_login=is_primeiro_login)
        
        if senha_nova != senha_confirmacao:
            flash('As senhas não coincidem.', 'warning')
            return render_template('troca_senha_primeiro_login.html', primeiro_login=is_primeiro_login)
        
        # Validar complexidade da senha
        if len(senha_nova) < 8:
            flash('A senha deve ter pelo menos 8 caracteres.', 'warning')
            return render_template('troca_senha_primeiro_login.html', primeiro_login=is_primeiro_login)
        
        # Atualizar a senha e marcar como não sendo mais o primeiro login
        try:
            user = Usuario.get_by_username(username)
            if not user:
                flash('Usuário não encontrado.', 'danger')
                return redirect(url_for('auth.logout'))
            
            # Atualizar a senha
            logging.info(f"Atualizando senha para o usuário {username} (ID: {user['id']})")
            resultado = Usuario.change_password(user['id'], senha_nova)
            logging.info(f"Resultado da atualização de senha: {resultado}")
            
            # Marcar como não sendo mais o primeiro login e não tendo mais senha temporária
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE usuarios SET primeiro_login = 0, senha_temporaria = 0 WHERE id = ?", (user['id'],))
                    conn.commit()
                    logging.info(f"Flags de primeiro_login e senha_temporaria atualizados para o usuário {username}")
            except Exception as e:
                logging.error(f"Erro ao atualizar flags de primeiro_login e senha_temporaria: {e}")
            
            # Adicionar mensagem de sucesso
            flash('Senha alterada com sucesso! Você será redirecionado para a página inicial em 2 segundos.', 'success')
            logging.info(f"Exibindo mensagem de sucesso para o usuário {username} antes do redirecionamento")
            
            # Determinar a URL de redirecionamento com base no nível do usuário
            nivel = session.get('nivel')
            redirect_url = '/'
            
            try:
                if nivel == 'admin' or username in ['admin', 'teste_admin']:
                    logging.info(f"URL de redirecionamento para admin {username}: dashboard administrativo")
                    redirect_url = '/admin/dashboard'  # URL direta em vez de url_for
                elif nivel == 'gr':
                    logging.info(f"URL de redirecionamento para usuário GR {username}: ambiente GR")
                    redirect_url = '/gr/ambiente'  # URL direta em vez de url_for
                else:
                    logging.info(f"URL de redirecionamento para usuário comum {username}: dashboard comum")
                    redirect_url = '/comum/dashboard'  # URL direta em vez de url_for
            except Exception as e:
                logging.error(f"Erro ao determinar URL de redirecionamento: {e}")
                redirect_url = '/'
            
            logging.info(f"URL de redirecionamento final para {username}: {redirect_url}")
            
            # Passar a URL de redirecionamento para o template
            logging.info(f"Renderizando template com senha_alterada=True e URL de redirecionamento={redirect_url}")
            return render_template('troca_senha_primeiro_login.html', 
                                  primeiro_login=is_primeiro_login, 
                                  redirect_url=redirect_url,
                                  redirect_delay=2000,  # 2 segundos em milissegundos
                                  senha_alterada=True)  # Flag para indicar que a senha foi alterada
        except Exception as e:
            logging.error(f"Erro ao trocar senha no primeiro login: {e}")
            flash('Ocorreu um erro ao alterar sua senha. Por favor, tente novamente.', 'danger')
            return render_template('troca_senha_primeiro_login.html', primeiro_login=is_primeiro_login)
    
    # Para requisições GET, apenas renderizar o template
    return render_template('troca_senha_primeiro_login.html', primeiro_login=is_primeiro_login)

# ========================
# BLUEPRINT DE SOLICITAÇÕES
# ========================

# Criar o blueprint de solicitações
solicitacoes_bp = Blueprint('solicitacoes', __name__, url_prefix='/solicitacoes')

@solicitacoes_bp.route('/')
@admin_required
def solicitacoes_view():
    """Rota para visualizar solicitações (acesso e senha)"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Obter solicitações de acesso pendentes
            cursor.execute("""
                SELECT * FROM solicitacoes_registro 
                WHERE status = 'pendente' 
                ORDER BY data_solicitacao DESC
            """)
            solicitacoes_acesso_pendentes = [dict(row) for row in cursor.fetchall()]
            
            # Obter solicitações de acesso processadas
            cursor.execute("""
                SELECT * FROM solicitacoes_registro 
                WHERE status != 'pendente' 
                ORDER BY data_processamento DESC
            """)
            solicitacoes_acesso_processadas = [dict(row) for row in cursor.fetchall()]
            
            # Obter solicitações de senha pendentes
            cursor.execute("""
                SELECT s.*, u.nivel 
                FROM solicitacoes_senha s
                JOIN usuarios u ON s.username = u.username
                WHERE s.status = 'pendente'
                ORDER BY s.data_solicitacao DESC
            """)
            solicitacoes_senha_pendentes = [dict(row) for row in cursor.fetchall()]
            
            # Obter solicitações de senha processadas
            cursor.execute("""
                SELECT s.*, u.nivel 
                FROM solicitacoes_senha s
                JOIN usuarios u ON s.username = u.username
                WHERE s.status != 'pendente'
                ORDER BY s.data_processamento DESC
            """)
            solicitacoes_senha_processadas = [dict(row) for row in cursor.fetchall()]
            
            # Contar totais
            total_pendentes = len(solicitacoes_acesso_pendentes) + len(solicitacoes_senha_pendentes)
            
            return render_template('admin_solicitacoes.html',
                                  solicitacoes_pendentes=solicitacoes_acesso_pendentes,
                                  solicitacoes_processadas=solicitacoes_acesso_processadas,
                                  solicitacoes_senha_pendentes=solicitacoes_senha_pendentes,
                                  solicitacoes_senha_processadas=solicitacoes_senha_processadas,
                                  total_pendentes=total_pendentes,
                                  usuario=session.get('user'))
    except Exception as e:
        logging.error(f"Erro ao visualizar solicitações: {e}")
        flash('Ocorreu um erro ao carregar as solicitações.', 'danger')
        return redirect(url_for('admin.admin_dashboard'))

@solicitacoes_bp.route('/aprovar_acesso/<int:solicitacao_id>', methods=['POST'])
@admin_required
def aprovar_acesso(solicitacao_id):
    """Aprovar solicitação de acesso"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Obter dados da solicitação
            cursor.execute("SELECT * FROM solicitacoes_registro WHERE id = ?", (solicitacao_id,))
            solicitacao = cursor.fetchone()
            
            if not solicitacao:
                flash('Solicitação não encontrada.', 'danger')
                return redirect(url_for('solicitacoes.solicitacoes_view'))
            
            solicitacao = dict(solicitacao)
            
            # Verificar se o usuário já existe
            cursor.execute("SELECT * FROM usuarios WHERE username = ?", (solicitacao['username'],))
            if cursor.fetchone():
                flash(f"Usuário '{solicitacao['username']}' já existe no sistema.", 'danger')
                return redirect(url_for('solicitacoes.solicitacoes_view'))
            
            # Gerar senha temporária
            import random
            import string
            temp_password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            
            # Criar o usuário
            nivel = request.form.get('nivel', 'comum')
            Usuario.create(solicitacao['username'], temp_password, nivel, solicitacao['email'])
            
            # Marcar como primeiro login
            cursor.execute("""
                UPDATE usuarios SET primeiro_login = 1 
                WHERE username = ?
            """, (solicitacao['username'],))
            
            # Atualizar status da solicitação
            cursor.execute("""
                UPDATE solicitacoes_registro 
                SET status = 'aprovada', 
                    data_processamento = ?, 
                    processado_por = ?,
                    observacao = ?
                WHERE id = ?
            """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), session.get('user'), f"Aprovado com nível: {nivel}", solicitacao_id))
            
            conn.commit()
            
            # Registrar no log
            log_action(
                session.get('user'),
                "APROVAÇÃO DE SOLICITAÇÃO DE ACESSO",
                f"Solicitação ID: {solicitacao_id}, Usuário: {solicitacao['username']}, Nível: {nivel}"
            )
            
            flash(f"Solicitação de acesso para '{solicitacao['username']}' aprovada com sucesso! Uma senha temporária foi gerada.", 'success')
            return redirect(url_for('solicitacoes.solicitacoes_view'))
    except Exception as e:
        logging.error(f"Erro ao aprovar solicitação de acesso: {e}")
        flash('Ocorreu um erro ao processar a solicitação.', 'danger')
        return redirect(url_for('solicitacoes.solicitacoes_view'))

@solicitacoes_bp.route('/rejeitar_acesso/<int:solicitacao_id>', methods=['POST'])
@admin_required
def rejeitar_acesso(solicitacao_id):
    """Rejeitar solicitação de acesso"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Obter dados da solicitação
            cursor.execute("SELECT * FROM solicitacoes_registro WHERE id = ?", (solicitacao_id,))
            solicitacao = cursor.fetchone()
            
            if not solicitacao:
                flash('Solicitação não encontrada.', 'danger')
                return redirect(url_for('solicitacoes.solicitacoes_view'))
            
            solicitacao = dict(solicitacao)
            motivo = request.form.get('motivo', 'Não especificado')
            
            # Atualizar status da solicitação
            cursor.execute("""
                UPDATE solicitacoes_registro 
                SET status = 'rejeitada', 
                    data_processamento = ?, 
                    processado_por = ?,
                    observacao = ?
                WHERE id = ?
            """, (datetime.now(), session.get('user'), f"Motivo: {motivo}", solicitacao_id))
            
            conn.commit()
            
            # Registrar no log
            log_action(
                session.get('user'),
                "REJEIÇÃO DE SOLICITAÇÃO DE ACESSO",
                f"Solicitação ID: {solicitacao_id}, Usuário: {solicitacao['username']}, Motivo: {motivo}"
            )
            
            flash(f"Solicitação de acesso para '{solicitacao['username']}' foi rejeitada.", 'success')
            return redirect(url_for('solicitacoes.solicitacoes_view'))
    except Exception as e:
        logging.error(f"Erro ao rejeitar solicitação de acesso: {e}")
        flash('Ocorreu um erro ao processar a solicitação.', 'danger')
        return redirect(url_for('solicitacoes.solicitacoes_view'))

@solicitacoes_bp.route('/aprovar_senha/<int:solicitacao_id>', methods=['POST'])
@admin_required
def aprovar_senha(solicitacao_id):
    """Aprovar solicitação de redefinição de senha"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Obter dados da solicitação
            cursor.execute("SELECT * FROM solicitacoes_senha WHERE id = ?", (solicitacao_id,))
            solicitacao = cursor.fetchone()
            
            if not solicitacao:
                flash('Solicitação não encontrada.', 'danger')
                return redirect(url_for('solicitacoes.solicitacoes_view'))
            
            solicitacao = dict(solicitacao)
            
            # Verificar se o usuário existe
            user = Usuario.get_by_username(solicitacao['username'])
            if not user:
                flash(f"Usuário '{solicitacao['username']}' não existe no sistema.", 'danger')
                return redirect(url_for('solicitacoes.solicitacoes_view'))
            
            # Gerar senha temporária
            import random
            import string
            temp_password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            
            # Atualizar a senha do usuário
            Usuario.change_password(user['id'], temp_password)
            
            # Marcar como primeiro login
            cursor.execute("""
                UPDATE usuarios SET primeiro_login = 1 
                WHERE username = ?
            """, (solicitacao['username'],))
            
            # Atualizar status da solicitação
            cursor.execute("""
                UPDATE solicitacoes_senha 
                SET status = 'aprovada', 
                    data_processamento = ?, 
                    processado_por = ?,
                    observacao = ?
                WHERE id = ?
            """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), session.get('user'), "Senha temporária gerada", solicitacao_id))
            
            conn.commit()
            
            # Registrar no log
            log_action(
                session.get('user'),
                "APROVAÇÃO DE SOLICITAÇÃO DE REDEFINIÇÃO DE SENHA",
                f"Solicitação ID: {solicitacao_id}, Usuário: {solicitacao['username']}"
            )
            
            flash(f"Solicitação de redefinição de senha para '{solicitacao['username']}' aprovada com sucesso! Uma senha temporária foi gerada.", 'success')
            return redirect(url_for('solicitacoes.solicitacoes_view'))
    except Exception as e:
        logging.error(f"Erro ao aprovar solicitação de redefinição de senha: {e}")
        flash('Ocorreu um erro ao processar a solicitação.', 'danger')
        return redirect(url_for('solicitacoes.solicitacoes_view'))

@solicitacoes_bp.route('/rejeitar_senha/<int:solicitacao_id>', methods=['POST'])
@admin_required
def rejeitar_senha(solicitacao_id):
    """Rejeitar solicitação de redefinição de senha"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Obter dados da solicitação
            cursor.execute("SELECT * FROM solicitacoes_senha WHERE id = ?", (solicitacao_id,))
            solicitacao = cursor.fetchone()
            
            if not solicitacao:
                flash('Solicitação não encontrada.', 'danger')
                return redirect(url_for('solicitacoes.solicitacoes_view'))
            
            solicitacao = dict(solicitacao)
            motivo = request.form.get('motivo', 'Não especificado')
            
            # Atualizar status da solicitação
            cursor.execute("""
                UPDATE solicitacoes_senha 
                SET status = 'rejeitada', 
                    data_processamento = ?, 
                    processado_por = ?,
                    observacao = ?
                WHERE id = ?
            """, (datetime.now(), session.get('user'), f"Motivo: {motivo}", solicitacao_id))
            
            conn.commit()
            
            # Registrar no log
            log_action(
                session.get('user'),
                "REJEIÇÃO DE SOLICITAÇÃO DE REDEFINIÇÃO DE SENHA",
                f"Solicitação ID: {solicitacao_id}, Usuário: {solicitacao['username']}, Motivo: {motivo}"
            )
            
            flash(f"Solicitação de redefinição de senha para '{solicitacao['username']}' foi rejeitada.", 'success')
            return redirect(url_for('solicitacoes.solicitacoes_view'))
    except Exception as e:
        logging.error(f"Erro ao rejeitar solicitação de redefinição de senha: {e}")
        flash('Ocorreu um erro ao processar a solicitação.', 'danger')
        return redirect(url_for('solicitacoes.solicitacoes_view'))