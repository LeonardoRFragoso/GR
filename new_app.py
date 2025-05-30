from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, jsonify, g, Blueprint, make_response
from flask_wtf.csrf import CSRFProtect
from werkzeug.exceptions import HTTPException, Unauthorized
import os
import logging
from datetime import datetime, timedelta
import time

# Importações dos módulos criados
from config import (
    SECRET_KEY, DEBUG, HOST, PORT, UPLOAD_FOLDER,
    LOG_FILE, LOG_FORMAT, LOG_LEVEL
)
from models.database import init_db, get_db_connection
from models.registros import Registro
from models.historico import Historico
from auth.routes import login_required, admin_required, gr_required, admin_or_gr_required
from utils.file_utils import allowed_file, save_uploaded_file
from operations.excel import excel_processor
from operations.formularios import processar_formulario, validar_campos_obrigatorios
from operations.registros import processar_edicao_registro, exibir_formulario_edicao
from auth.session_manager import validate_session, cleanup_inactive_sessions, create_sessions_table, end_session


# Importar os blueprints
from auth.routes import auth_bp, solicitacoes_bp
from routes import comum_bp, main_bp
from admin_routes import admin_bp  # Importando do arquivo admin_routes.py

# Importar o novo blueprint GR do arquivo gr_routes.py
from gr_routes import gr_blueprint as gr_bp_new

# Criação e configuração da aplicação Flask
app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Configurações de sessão para segurança
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)  # Sessão expira em 30 minutos (mantido para compatibilidade)
app.config['SESSION_USE_SIGNER'] = True  # Assinar cookies de sessão
app.config['SESSION_COOKIE_SECURE'] = False  # Mudar para True em produção com HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevenir acesso via JavaScript
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Restringir cookies a mesmo site

# Configurar proteção CSRF
csrf = CSRFProtect()
csrf.init_app(app)

# Configurar logging
logging.basicConfig(filename=LOG_FILE, level=getattr(logging, LOG_LEVEL), format=LOG_FORMAT)

# Garantir que o diretório de uploads existe
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Inicializar o sistema de gerenciamento de sessões
create_sessions_table()

# Configurar hook para validar sessões em cada requisição
@app.before_request
def before_request():
    # Ignorar validação para rotas públicas e arquivos estáticos
    if request.endpoint and (
        request.endpoint.startswith('static') or 
        request.endpoint == 'auth.login' or
        request.endpoint == 'auth.logout' or
        request.path.startswith('/static')
    ):
        return
    
    # Se o usuário está logado, validar a sessão
    if 'user' in session:
        if not validate_session():
            # Sessão inválida, redirecionar para login
            end_session()
            flash('Sua sessão expirou ou foi encerrada. Por favor, faça login novamente.', 'warning')
            return redirect(url_for('auth.login'))

# Configurar rota para heartbeat para manter a sessão ativa
@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    if 'user' in session:
        # Atualizar a atividade da sessão
        validate_session()
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"}), 401

# Limpar sessões inativas periodicamente
@app.before_request
def cleanup_sessions():
    # Executar a limpeza a cada 5 minutos (aproximadamente)
    if not hasattr(g, 'last_session_cleanup') or time.time() - g.last_session_cleanup > 300:
        cleanup_inactive_sessions()
        g.last_session_cleanup = time.time()

# Registrar os blueprints na aplicação
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
# app.register_blueprint(gr_bp)  # Comentado para usar o novo blueprint GR
app.register_blueprint(gr_bp_new)  # Novo blueprint GR do arquivo gr_routes.py
app.register_blueprint(comum_bp)
app.register_blueprint(main_bp)
app.register_blueprint(solicitacoes_bp)

# Adicionar funções globais ao contexto do template
app.jinja_env.globals.update(max=max, min=min)

# A função de redirecionamento por nível foi movida para auth.routes.py

# Configurar tratamento de erro para sessão expirada
@app.before_request
def clear_session_on_auth_pages():
    # Se a rota atual é relacionada a autenticação e há algum problema na sessão
    if request.path == '/login' or request.path == '/' or request.path == '/auth/login':
        # Limpar completamente a sessão e mensagens flash para garantir que não haja erros
        if '_flashes' in session:
            session.pop('_flashes', None)

# Handler para limpar mensagens flash em rotas de autenticação
@app.before_request
def clear_messages_on_auth_pages():
    # Se a rota atual é relacionada a autenticação
    if request.path == '/login' or request.path == '/auth/login':
        # Limpar mensagens flash sem afetar o restante da sessão
        if '_flashes' in session:
            session.pop('_flashes', None)

# Função auxiliar para limpar a sessão (sem rota associada)
def clear_session_completely():
    # Limpar completamente a sessão e todas as mensagens flash
    session.clear()
    if '_flashes' in session:
        session.pop('_flashes', None)

# Tratamento global de erros para evitar mensagens de erro no login
@app.errorhandler(Exception)
def handle_exception(e):
    # Log detalhado do erro
    error_context = {
        'error_type': type(e).__name__,
        'error_message': str(e),
        'path': request.path,
        'method': request.method,
        'user': session.get('user'),
        'nivel': session.get('nivel')
    }
    
    # Tratar erros 404 (Not Found) de forma silenciosa para rotas específicas
    if isinstance(e, HTTPException) and e.code == 404:
        # Verificar se é uma solicitação do Chrome DevTools ou outra solicitação automática
        if request.path.startswith('/.well-known/') or 'chrome.devtools' in request.path:
            # Retornar 404 sem log de erro
            return 'Not Found', 404
        
        # Para outros erros 404, registrar um log informativo e retornar 404
        app.logger.info(f"Rota não encontrada: {request.path}")
        return render_template('error.html', error="A página solicitada não foi encontrada."), 404
    
    # Para outros erros, continuar com o log detalhado
    app.logger.error(
        f"Erro não tratado: {type(e).__name__}",
        extra={'error_context': error_context},
        exc_info=True
    )
    
    # Tratar erros de autenticação
    if isinstance(e, Unauthorized) or (isinstance(e, HTTPException) and e.code == 401):
        # Limpar a sessão para evitar problemas de autenticação persistentes
        session.clear()
        flash("Sua sessão expirou ou você não tem permissão para acessar esta página. Por favor, faça login novamente.", "warning")
        return redirect(url_for('auth.login'))
    
    # Se o erro ocorrer durante uma solicitação de login, apenas limpar a sessão
    if request.path == '/login' or request.path == '/' or request.path == '/auth/login':
        session.clear()
        # Não exibe flash message para não confundir o usuário na tela de login
        return redirect(url_for('auth.login'))
    
    # Log adicional para erros de permissão
    if isinstance(e, HTTPException) and e.code in [403, 401]:
        app.logger.warning(f"Erro de permissão: {str(e)} - Usuário: {session.get('user')}, Nível: {session.get('nivel')}, Rota: {request.path}")
        
    # Para outros erros HTTP, retornar o código de erro apropriado
    if isinstance(e, HTTPException):
        return render_template('error.html', error=str(e)), e.code
        
    # Para erros não-HTTP, retornar 500
    return render_template('error.html', error=str(e)), 500



# Importar a função de redirecionamento por nível
from auth.routes import redirecionar_por_nivel

# Rota para servir o favicon.ico
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static', 'assets'),
                              'favicon.ico', mimetype='image/x-icon')

# Rota principal (index) para redirecionamento
@app.route('/')
def index():
    # Se o usuário está logado, redirecionar para a página apropriada
    if 'user' in session:
        return redirecionar_por_nivel()
    # Caso contrário, redirecionar para a página de login
    return redirect(url_for('auth.login'))

# Inicialização do banco de dados
init_db()

# Executar a aplicação
if __name__ == '__main__':
    app.run(debug=DEBUG, host=HOST, port=PORT)