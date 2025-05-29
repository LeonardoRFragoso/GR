#!/usr/bin/env python3
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, jsonify, g, Blueprint
from flask_wtf.csrf import CSRFProtect
from werkzeug.exceptions import HTTPException, Unauthorized
import os
import logging
import time
from datetime import datetime, timedelta

# Importações dos módulos criados - usamos config_ubuntu em vez de config
from config_ubuntu import (
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

# Importação dos blueprints
from auth.routes import auth_bp, solicitacoes_bp
from routes import comum_bp, main_bp
from admin_routes import admin_bp  # Importando do arquivo admin_routes.py na raiz

# Importar o novo blueprint GR do arquivo gr_routes.py
from gr_routes import gr_blueprint as gr_bp_new

# Configurar logging para Ubuntu
logging.basicConfig(
    filename=LOG_FILE,
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT
)

# Criação e configuração da aplicação Flask
app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Configurar CSRF protection
csrf = CSRFProtect(app)

# Verificar se a tabela de sessões existe e criá-la se necessário
create_sessions_table()

# Função para limpar sessões inativas
@app.before_request
def cleanup_sessions():
    # Executar a limpeza a cada 5 minutos (aproximadamente)
    if not hasattr(g, 'last_session_cleanup') or time.time() - g.last_session_cleanup > 300:
        cleanup_inactive_sessions()
        g.last_session_cleanup = time.time()

# Registrar todos os blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(gr_bp_new)  # Novo blueprint GR do arquivo gr_routes.py
app.register_blueprint(comum_bp)
app.register_blueprint(main_bp)
app.register_blueprint(solicitacoes_bp)

# Definir uma rota raiz que redireciona baseado no nível do usuário
@app.route('/')
def root():
    if 'user' in session:
        nivel = session.get('nivel')
        if nivel == 'admin':
            return redirect(url_for('admin.admin_dashboard'))
        elif nivel == 'gr':
            return redirect(url_for('gr.ambiente'))
        return redirect(url_for('main.view_registros'))
    return redirect(url_for('auth.login'))

# Para iniciar o servidor no Ubuntu
if __name__ == '__main__':
    try:
        # Inicializar banco de dados
        init_db()
        
        # Iniciar servidor
        print(f"Servidor iniciado em http://{HOST}:{PORT}/")
        app.run(debug=DEBUG, host=HOST, port=PORT)
    except Exception as e:
        print(f"Erro ao iniciar o servidor: {e}")
        logging.error(f"Erro ao iniciar o servidor: {e}")
