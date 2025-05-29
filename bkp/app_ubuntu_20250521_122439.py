#!/usr/bin/env python3
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, jsonify, g, Blueprint
from werkzeug.exceptions import HTTPException, Unauthorized
import os
import logging
from datetime import datetime, timedelta

# Importações dos módulos criados - usamos config_ubuntu em vez de config
from config_ubuntu import (
    SECRET_KEY, DEBUG, HOST, PORT, UPLOAD_FOLDER,
    LOG_FILE, LOG_FORMAT, LOG_LEVEL
)
from models.database import init_db, get_db_connection
from models.registros import Registro
from models.historico import Historico
from auth.decorators import login_required, admin_required, admin_or_gr_required, gr_or_admin_required
from utils.file_utils import allowed_file, save_uploaded_file
from operations.excel import excel_processor
from operations.formularios import processar_formulario, validar_campos_obrigatorios
from operations.registros import processar_edicao_registro, exibir_formulario_edicao

# Importação dos blueprints
from auth.routes import auth_bp
from admin.routes import admin_bp
from blueprints.gr_routes import gr_bp

# Criação e configuração da aplicação Flask
app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Configurar logging para Ubuntu
logging.basicConfig(
    filename=LOG_FILE,
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT
)

# Garantir que o diretório de uploads existe
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Criar o blueprint 'main' para as rotas principais
main_bp = Blueprint('main', __name__, url_prefix='/main')

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
    app.logger.error(f"Erro não tratado: {str(e)}")
    
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
    
    # Para outros erros HTTP, retornar a página de erro com o código apropriado
    if isinstance(e, HTTPException):
        return render_template('error.html', error=str(e)), e.code
        
    # Retornar erro padrão para exceções genéricas
    return render_template('error.html', error=str(e)), 500

# Inicializar o banco de dados
init_db()

# Função auxiliar para redirecionar com base no nível do usuário
def redirecionar_por_nivel():
    """Função auxiliar para padronizar o redirecionamento por nível de usuário"""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    nivel = session.get('nivel')
    if nivel == 'admin':
        return redirect(url_for('admin.dashboard'))
    elif nivel == 'gr':
        return redirect(url_for('gr.ambiente'))
    else:
        return redirect(url_for('main.view_registros'))

# Rota principal no nível da aplicação
@app.route('/')
def root():
    if 'user' in session:
        return redirecionar_por_nivel()
    return redirect(url_for('auth.login'))

# Registrar todos os blueprints após definir todas as rotas
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(gr_bp)
app.register_blueprint(main_bp)

# Adicionamos as configurau00e7u00f5es especu00edficas para Ubuntu
# Isso garante uma melhor compatiblidade com o ambiente Linux
@app.before_first_request
def verificar_ambiente_ubuntu():
    import platform
    if 'Linux' in platform.system():
        app.logger.info(f"Servidor rodando em ambiente Linux: {platform.platform()}")
        # Verificar permissu00f5es de arquivos de uploads para Linux
        if os.path.exists(UPLOAD_FOLDER):
            try:
                test_file = os.path.join(UPLOAD_FOLDER, '.test_write')
                with open(test_file, 'w') as f:
                    f.write('test')
                os.remove(test_file)
                app.logger.info(f"Diretório de uploads {UPLOAD_FOLDER} tem permissu00f5es corretas")
            except Exception as e:
                app.logger.warning(f"Aviso: Problemas de permissu00e3o no diretório de uploads {UPLOAD_FOLDER}: {str(e)}")

# Para iniciar o servidor no Ubuntu - com tratamento especial para o ambiente Linux
if __name__ == '__main__':
    try:
        # Inicializar banco de dados
        init_db()
        
        # Relatar informau00e7u00f5es sobre o ambiente
        import platform
        print(f"\n=== Iniciando sistema de Atendimento GR ===")
        print(f"Sistema: {platform.system()} {platform.release()}")
        print(f"Python: {platform.python_version()}")
        print(f"Diretório de uploads: {UPLOAD_FOLDER}")
        print(f"Log file: {LOG_FILE}")
        print(f"\nServidor iniciado em http://{HOST}:{PORT}/")
        
        # Iniciar servidor
        app.run(debug=DEBUG, host=HOST, port=PORT)
    except Exception as e:
        print(f"Erro ao iniciar o servidor: {e}")
        logging.error(f"Erro ao iniciar o servidor: {e}")
