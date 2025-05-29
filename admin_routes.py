from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app
from functools import wraps
from datetime import datetime, timedelta
import sqlite3
import os
import logging
import hashlib
import secrets
import json
import traceback
from werkzeug.security import generate_password_hash
from flask import session, render_template, redirect, url_for, flash, Blueprint, request
from routes import login_required

# Importar a função de processamento de edição de registros
from operations.registros import processar_edicao_registro

# Importar funções de debug
try:
    from admin_debug import logger as debug_logger, log_db_query, log_db_result, log_db_schema, log_db_tables
    DEBUG_ENABLED = True
except ImportError:
    DEBUG_ENABLED = False
    # Criar um logger dummy para não quebrar o código
    class DummyLogger:
        def debug(self, *args, **kwargs): pass
        def info(self, *args, **kwargs): pass
        def warning(self, *args, **kwargs): pass
        def error(self, *args, **kwargs): pass
        def exception(self, *args, **kwargs): pass
    debug_logger = DummyLogger()
    def log_db_query(*args, **kwargs): pass
    def log_db_result(*args, **kwargs): pass
    def log_db_schema(*args, **kwargs): pass
    def log_db_tables(*args, **kwargs): pass

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('admin_routes')

# Criar o Blueprint para as rotas de administração
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Função para obter conexão com o banco de dados
def get_db_connection():
    conn = sqlite3.connect('usuarios.db')
    conn.row_factory = sqlite3.Row
    return conn

# Decorator para verificar se o usuário está autenticado e é administrador
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        logger.info(f"Verificando acesso administrativo para: {session.get('user', 'Usuário desconhecido')}")
        logger.info(f"Conteúdo da sessão em admin_required: {session}")
        
        if 'user' not in session:
            logger.warning("Tentativa de acesso sem usuário na sessão")
            flash('Você precisa fazer login para acessar esta página', 'danger')
            return redirect(url_for('auth.login'))
        
        # Verificar se o usuário é administrador
        nivel = session.get('nivel')
        username = session.get('user')
        
        logger.info(f"Usuário: {username}, Nível: {nivel}")
        
        # Permitir acesso se o nível for 'admin' ou se for um dos usuários de teste administrativos
        if nivel == 'admin' or username in ['admin', 'teste_admin']:
            logger.info(f"Acesso administrativo concedido para: {username}")
            return f(*args, **kwargs)
        
        # Se não for administrador, redirecionar para a página apropriada
        logger.warning(f"Tentativa de acesso administrativo por usuário não autorizado: {username}")
        flash('Você não tem permissão para acessar esta página', 'danger')
        
        # Redirecionar para uma rota que certamente existe
        if nivel == 'gr':
            logger.info("Redirecionando para gr.ambiente")
            return redirect(url_for('gr.ambiente'))
        else:
            logger.info("Redirecionando para comum.dashboard_comum")
            return redirect(url_for('comum.dashboard_comum'))
    return decorated_function

# Função para registrar ações administrativas nos logs
def log_admin_action(usuario, acao, detalhes):
    try:
        # Tentar importar a função centralizada de logs
        try:
            from models.log_manager import registrar_log
            # Usar a função centralizada
            registrar_log(usuario, 'admin', acao, detalhes)
            return
        except ImportError:
            logger.warning("Módulo de log centralizado não encontrado, usando método legado")
        
        # Método legado (fallback)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Verificar se a tabela log_atividades existe
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='log_atividades'")
            if cursor.fetchone():
                # Usar a tabela unificada
                data_hora = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                cursor.execute("""
                    INSERT INTO log_atividades (data_hora, usuario, nivel, acao, descricao)
                    VALUES (?, ?, ?, ?, ?)
                """, (data_hora, usuario, 'admin', acao, detalhes))
            else:
                # Fallback para a tabela antiga
                cursor.execute("""
                    INSERT INTO logs_admin (usuario, acao, detalhes, data_log)
                    VALUES (?, ?, ?, ?)
                """, (usuario, acao, detalhes, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            
            conn.commit()
    except Exception as e:
        logger.error(f"Erro ao registrar log administrativo: {e}")

# Função para gerar hash de senha
def hash_password(password):
    # Usar o generate_password_hash do Werkzeug para compatibilidade com check_password_hash
    # Retorna apenas o hash da senha para simplificar o uso
    return generate_password_hash(password)

#----------------------------------------------
# Rota para edição de registros
#----------------------------------------------

@admin_bp.route('/editar_registro/<int:registro_id>', methods=['GET', 'POST'])
@admin_required
def editar_registro(registro_id):
    """Rota para edição de registros para administradores"""
    return processar_edicao_registro(registro_id)

#----------------------------------------------
# Rotas para o Dashboard Administrativo
#----------------------------------------------

@admin_bp.route('/dashboard')
@admin_required
def admin_dashboard():
    """Rota para o dashboard administrativo"""
    try:
        debug_logger.info("Iniciando carregamento do dashboard administrativo")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Registrar tabelas disponíveis para debug
            if DEBUG_ENABLED:
                log_db_tables(conn)
            
            # Obter estatísticas de usuários
            query = "SELECT COUNT(*) FROM usuarios"
            log_db_query(query)
            try:
                cursor.execute(query)
                total_usuarios = cursor.fetchone()[0]
                debug_logger.debug(f"Total de usuários: {total_usuarios}")
            except Exception as e:
                debug_logger.exception(f"Erro ao contar usuários: {e}")
                total_usuarios = 0
            
            # Usar 'nivel' conforme a estrutura correta do banco de dados
            query = "SELECT COUNT(*) FROM usuarios WHERE nivel = 'admin'"
            log_db_query(query)
            try:
                cursor.execute(query)
                total_admins = cursor.fetchone()[0]
                debug_logger.debug(f"Total de admins: {total_admins}")
            except Exception as e:
                debug_logger.exception(f"Erro ao contar admins: {e}")
                total_admins = 0
            
            query = "SELECT COUNT(*) FROM usuarios WHERE nivel = 'comum'"
            log_db_query(query)
            try:
                cursor.execute(query)
                total_comuns = cursor.fetchone()[0]
                debug_logger.debug(f"Total de usuários comuns: {total_comuns}")
            except Exception as e:
                debug_logger.exception(f"Erro ao contar usuários comuns: {e}")
                total_comuns = 0
            
            query = "SELECT COUNT(*) FROM usuarios WHERE nivel = 'gr'"
            log_db_query(query)
            try:
                cursor.execute(query)
                total_gr = cursor.fetchone()[0]
                debug_logger.debug(f"Total de usuários GR: {total_gr}")
            except Exception as e:
                debug_logger.exception(f"Erro ao contar usuários GR: {e}")
                total_gr = 0
            
            # Verificar se a tabela solicitacoes_senha existe
            query = "SELECT name FROM sqlite_master WHERE type='table' AND name='solicitacoes_senha'"
            log_db_query(query)
            cursor.execute(query)
            if cursor.fetchone():
                # Obter solicitações pendentes
                query = "SELECT COUNT(*) FROM solicitacoes_senha WHERE status = 'pendente'"
                log_db_query(query)
                try:
                    cursor.execute(query)
                    solicitacoes_senha = cursor.fetchone()[0]
                    debug_logger.debug(f"Solicitações de senha pendentes: {solicitacoes_senha}")
                except Exception as e:
                    debug_logger.exception(f"Erro ao contar solicitações de senha: {e}")
                    solicitacoes_senha = 0
            else:
                debug_logger.warning("Tabela solicitacoes_senha não existe")
                solicitacoes_senha = 0
            
            # Verificar se a tabela solicitacoes_registro existe
            query = "SELECT name FROM sqlite_master WHERE type='table' AND name='solicitacoes_registro'"
            log_db_query(query)
            cursor.execute(query)
            if cursor.fetchone():
                query = "SELECT COUNT(*) FROM solicitacoes_registro WHERE status = 'pendente'"
                log_db_query(query)
                try:
                    cursor.execute(query)
                    solicitacoes_registro = cursor.fetchone()[0]
                    debug_logger.debug(f"Solicitações de registro pendentes: {solicitacoes_registro}")
                except Exception as e:
                    debug_logger.exception(f"Erro ao contar solicitações de registro: {e}")
                    solicitacoes_registro = 0
            else:
                debug_logger.warning("Tabela solicitacoes_registro não existe")
                solicitacoes_registro = 0
            
            # Verificar se a tabela logs existe
            query = "SELECT name FROM sqlite_master WHERE type='table' AND name='logs'"
            log_db_query(query)
            cursor.execute(query)
            if cursor.fetchone():
                # Verificar as colunas disponíveis na tabela logs
                if DEBUG_ENABLED:
                    log_db_schema(conn, 'logs')
                
                # Verificar se a tabela usuarios existe para o JOIN
                query = "SELECT name FROM sqlite_master WHERE type='table' AND name='usuarios'"
                log_db_query(query)
                cursor.execute(query)
                if cursor.fetchone():
                    # Obter atividade recente (logs)
                    try:
                        query = """
                            SELECT l.*, u.username
                            FROM logs l
                            LEFT JOIN usuarios u ON l.usuario = u.username
                            ORDER BY l.data DESC
                            LIMIT 10
                        """
                        log_db_query(query)
                        cursor.execute(query)
                        logs_recentes = cursor.fetchall()
                        debug_logger.debug(f"Logs recentes: {len(logs_recentes)} registros")
                    except Exception as e:
                        debug_logger.exception(f"Erro ao buscar logs recentes: {e}")
                        logs_recentes = []
                else:
                    debug_logger.warning("Tabela usuarios não existe para JOIN com logs")
                    # Obter logs sem o JOIN
                    try:
                        query = "SELECT * FROM logs ORDER BY data DESC LIMIT 10"
                        log_db_query(query)
                        cursor.execute(query)
                        logs_recentes = cursor.fetchall()
                        debug_logger.debug(f"Logs recentes (sem JOIN): {len(logs_recentes)} registros")
                    except Exception as e:
                        debug_logger.exception(f"Erro ao buscar logs recentes sem JOIN: {e}")
                        logs_recentes = []
            else:
                debug_logger.warning("Tabela logs não existe")
                logs_recentes = []
            
            # Verificar se a tabela registros existe
            query = "SELECT name FROM sqlite_master WHERE type='table' AND name='registros'"
            log_db_query(query)
            cursor.execute(query)
            if cursor.fetchone():
                # Verificar as colunas disponíveis na tabela registros
                if DEBUG_ENABLED:
                    colunas_registros = log_db_schema(conn, 'registros')
                    debug_logger.debug(f"Colunas na tabela registros: {colunas_registros}")
                
                # Obter estatísticas de registros
                try:
                    query = "SELECT COUNT(*) FROM registros WHERE excluido = 0"
                    log_db_query(query)
                    cursor.execute(query)
                    total_registros = cursor.fetchone()[0]
                    debug_logger.debug(f"Total de registros: {total_registros}")
                except Exception as e:
                    debug_logger.exception(f"Erro ao contar registros: {e}")
                    total_registros = 0
                
                try:
                    query = "SELECT COUNT(*) FROM registros WHERE data_registro >= date('now', '-7 days') AND excluido = 0"
                    log_db_query(query)
                    cursor.execute(query)
                    registros_ultima_semana = cursor.fetchone()[0]
                    debug_logger.debug(f"Registros da última semana: {registros_ultima_semana}")
                except Exception as e:
                    debug_logger.exception(f"Erro ao contar registros da última semana: {e}")
                    registros_ultima_semana = 0
                
                # Verificar se a coluna data_modificacao existe
                query = "PRAGMA table_info(registros)"
                log_db_query(query)
                cursor.execute(query)
                colunas = cursor.fetchall()
                tem_data_modificacao = any(col[1] == 'data_modificacao' for col in colunas)
                
                if tem_data_modificacao:
                    try:
                        query = "SELECT COUNT(*) FROM registros WHERE data_modificacao >= datetime('now', '-7 days') AND excluido = 0"
                        log_db_query(query)
                        cursor.execute(query)
                        registros_atualizados = cursor.fetchone()[0]
                        debug_logger.debug(f"Registros atualizados na última semana: {registros_atualizados}")
                    except Exception as e:
                        debug_logger.exception(f"Erro ao contar registros atualizados: {e}")
                        registros_atualizados = registros_ultima_semana  # Fallback para registros da última semana
                else:
                    debug_logger.warning("Coluna data_modificacao não existe na tabela registros")
                    registros_atualizados = registros_ultima_semana  # Usar registros da última semana como aproximação
                
                # Verificar se a coluna alteracoes_verificadas existe
                tem_alteracoes_verificadas = any(col[1] == 'alteracoes_verificadas' for col in colunas)
                
                if tem_alteracoes_verificadas:
                    try:
                        query = "SELECT COUNT(*) as total FROM registros WHERE alteracoes_verificadas = 1 AND excluido = 0"
                        log_db_query(query)
                        cursor.execute(query)
                        total_alteracoes_verificadas = cursor.fetchone()[0]
                        debug_logger.debug(f"Total de alterações verificadas: {total_alteracoes_verificadas}")
                    except Exception as e:
                        debug_logger.exception(f"Erro ao contar alterações verificadas: {e}")
                        total_alteracoes_verificadas = 0
                else:
                    debug_logger.warning("Coluna alteracoes_verificadas não existe na tabela registros")
                    total_alteracoes_verificadas = 0
            else:
                debug_logger.warning("Tabela registros não existe")
                total_registros = 0
                registros_ultima_semana = 0
                registros_atualizados = 0
                total_alteracoes_verificadas = 0
            
            # Criar uma lista de campos mais alterados (ainda fictícia, mas com dados reais)
            campos_mais_alterados = [
                {'campo': 'Status SM/AE', 'total': total_alteracoes_verificadas, 'percentual': 100 if total_alteracoes_verificadas > 0 else 0}
            ]
            
            # Obter atividade por usuário com base nos logs reais
            atividade_por_usuario = []
            if logs_recentes:  # Só tenta buscar atividade se houver logs
                try:
                    query = """
                        SELECT usuario, COUNT(*) as total_acoes
                        FROM logs
                        GROUP BY usuario
                        ORDER BY total_acoes DESC
                        LIMIT 5
                    """
                    log_db_query(query)
                    cursor.execute(query)
                    atividade_por_usuario = []
                    for row in cursor.fetchall():
                        atividade_por_usuario.append(dict(row))
                    debug_logger.debug(f"Atividade por usuário: {len(atividade_por_usuario)} registros")
                except Exception as e:
                    debug_logger.exception(f"Erro ao buscar atividade por usuário: {e}")
            
            # Formatar logs para exibição no template
            logs_formatados = []
            for log in logs_recentes:
                try:
                    # Verificar se as chaves existem antes de acessá-las
                    log_formatado = {
                        'id': log['id'] if 'id' in log else 'N/A',
                        'usuario': (log['username'] if 'username' in log and log['username'] else 
                                   log['usuario'] if 'usuario' in log else 'Sistema'),
                        'acao': log['acao'] if 'acao' in log else 'N/A',
                        'detalhes': log['detalhes'] if 'detalhes' in log else 'N/A',
                        'data': log['data'] if 'data' in log else 'N/A'
                    }
                    logs_formatados.append(log_formatado)
                except Exception as e:
                    debug_logger.exception(f"Erro ao formatar log: {e}")
                    # Continuar com o próximo log
            
            debug_logger.info("Dashboard administrativo carregado com sucesso")
            # Obter o usuário e nível da sessão
            usuario = session.get('user', 'Desconhecido')
            nivel = session.get('nivel', 'comum')
            
            # Adicionar variáveis de paginação para compatibilidade com outros templates
            page = 1
            total_pages = 1
            
            return render_template('admin_dashboard.html',
                                   usuario=usuario,
                                   nivel=nivel,
                                   total_usuarios=total_usuarios,
                                   total_usuarios_admin=total_admins,  # Renomeado para corresponder ao que o template espera
                                   total_usuarios_comuns=total_comuns,  # Renomeado para corresponder ao que o template espera
                                   total_usuarios_gr=total_gr,  # Renomeado para corresponder ao que o template espera
                                   solicitacoes_senha=solicitacoes_senha,
                                   solicitacoes_registro=solicitacoes_registro,
                                   logs_recentes=logs_recentes,
                                   logs_formatados=logs_formatados,
                                   total_registros=total_registros,
                                   registros_ultima_semana=registros_ultima_semana,
                                   registros_atualizados=registros_atualizados,
                                   campos_mais_alterados=campos_mais_alterados,
                                   atividade_por_usuario=atividade_por_usuario,
                                   page=page,
                                   total_pages=total_pages)
    
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Erro ao carregar dashboard administrativo: {e}")
        debug_logger.exception(f"Erro detalhado ao carregar dashboard administrativo: {error_details}")
        flash(f"Erro ao carregar dashboard: {e}", "danger")
        # Redirecionar para a rota de login em vez de 'index' que não existe
        return redirect(url_for('auth.login'))

#----------------------------------------------
# Rotas para Gerenciamento de Usuários
#----------------------------------------------

@admin_bp.route('/usuarios')
@admin_required
def usuarios():
    """Rota para listar todos os usuários"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Obter todos os usuários
            cursor.execute("""
                SELECT id, username, email, nivel, last_login, created_at, senha_temporaria, ultima_alteracao_senha
                FROM usuarios
                ORDER BY username
            """)
            usuarios = cursor.fetchall()
            
            # Contar total de solicitações pendentes para a sidebar
            total_pendentes = 0
            
            # Verificar se a tabela de solicitações de registro existe
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='solicitacoes_registro'")
            if cursor.fetchone():
                cursor.execute("SELECT COUNT(*) FROM solicitacoes_registro WHERE status = 'pendente'")
                solicitacoes_registro = cursor.fetchone()[0]
                total_pendentes += solicitacoes_registro
            
            # Verificar se a tabela de solicitações de senha existe
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='solicitacoes_senha'")
            if cursor.fetchone():
                cursor.execute("SELECT COUNT(*) FROM solicitacoes_senha WHERE status = 'pendente'")
                solicitacoes_senha = cursor.fetchone()[0]
                total_pendentes += solicitacoes_senha
            
            # Obter o usuário e nível da sessão
            usuario = session.get('user', 'Desconhecido')
            nivel = session.get('nivel', 'comum')
            
            # Adicionar variáveis de paginação para compatibilidade com outros templates
            page = 1
            total_pages = 1
            
            return render_template('admin_usuarios.html', 
                                  usuarios=usuarios, 
                                  total_pendentes=total_pendentes,
                                  usuario=usuario,
                                  nivel=nivel,
                                  page=page,
                                  total_pages=total_pages)
    
    except Exception as e:
        logger.error(f"Erro ao listar usuários: {e}")
        flash(f"Erro ao listar usuários: {e}", "danger")
        return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/usuarios/novo', methods=['GET', 'POST'])
@admin_required
def novo_usuario():
    """Rota para criar um novo usuário"""
    # Contar total de solicitações pendentes para a sidebar
    total_pendentes = 0
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Verificar se a tabela de solicitações de registro existe
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='solicitacoes_registro'")
            if cursor.fetchone():
                cursor.execute("SELECT COUNT(*) FROM solicitacoes_registro WHERE status = 'pendente'")
                solicitacoes_registro = cursor.fetchone()[0]
                total_pendentes += solicitacoes_registro
            
            # Verificar se a tabela de solicitações de senha existe
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='solicitacoes_senha'")
            if cursor.fetchone():
                cursor.execute("SELECT COUNT(*) FROM solicitacoes_senha WHERE status = 'pendente'")
                solicitacoes_senha = cursor.fetchone()[0]
                total_pendentes += solicitacoes_senha
    except Exception as e:
        logger.error(f"Erro ao contar solicitações pendentes: {e}")
        total_pendentes = 0
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        senha = request.form.get('senha')
        nivel = request.form.get('nivel')
        
        # Validação básica
        if not username or not email or not senha or not nivel:
            flash("Todos os campos são obrigatórios", "danger")
            return render_template('admin_usuarios_novo.html', total_pendentes=total_pendentes)
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Verificar se o username já existe
                cursor.execute("SELECT id FROM usuarios WHERE username = ?", (username,))
                if cursor.fetchone():
                    flash("Nome de usuário já existe", "danger")
                    return render_template('admin_usuarios_novo.html', total_pendentes=total_pendentes)
                
                # Gerar hash da senha usando a função do Werkzeug
                password_hash = generate_password_hash(senha)
                
                # Inserir novo usuário
                cursor.execute("""
                    INSERT INTO usuarios (username, password_hash, nivel, email, created_at, senha_temporaria)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (username, password_hash, nivel, email, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 0))
                
                # Registrar a ação nos logs administrativos
                log_admin_action(
                    session.get('user'),
                    "CRIAÇÃO DE USUÁRIO",
                    f"Novo usuário criado: {username} (Nível: {nivel})"
                )
                
                conn.commit()
                
                flash(f"Usuário {username} criado com sucesso", "success")
                return redirect(url_for('admin.usuarios'))
        
        except Exception as e:
            logger.error(f"Erro ao criar usuário: {e}")
            flash(f"Erro ao criar usuário: {e}", "danger")
            return render_template('admin_usuarios_novo.html', total_pendentes=total_pendentes)
    
    # Método GET
    return render_template('admin_usuarios_novo.html', total_pendentes=total_pendentes)

#----------------------------------------------
# Rotas para Gerenciamento de Solicitações
#----------------------------------------------

@admin_bp.route('/solicitacoes')
@admin_required
def solicitacoes():
    """Rota para listar todas as solicitações de acesso"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Obter solicitações de registro pendentes
            cursor.execute("""
                SELECT id, nome, username, email, setor, justificativa, data_solicitacao, status, 'registro' as tipo
                FROM solicitacoes_registro
                WHERE status = 'pendente'
                ORDER BY data_solicitacao DESC
            """)
            solicitacoes_pendentes = cursor.fetchall()
            
            # Obter solicitações de senha pendentes
            try:
                cursor.execute("""
                    SELECT id, username, '' as email, '' as nome, '' as setor, 
                           'Redefinição de senha solicitada' as justificativa, 
                           data_solicitacao, status, 'senha' as tipo
                    FROM solicitacoes_senha
                    WHERE status = 'pendente'
                    ORDER BY data_solicitacao DESC
                """)
                solicitacoes_senha_pendentes = cursor.fetchall()
                
                # Adicionar as solicitações de senha às pendentes
                solicitacoes_pendentes = list(solicitacoes_pendentes) + list(solicitacoes_senha_pendentes)
                logger.info(f"Total de solicitações de senha pendentes: {len(solicitacoes_senha_pendentes)}")
            except Exception as e:
                logger.error(f"Erro ao buscar solicitações de senha: {e}")
                solicitacoes_senha_pendentes = []
            
            # Obter solicitações processadas
            cursor.execute("""
                SELECT id, nome, username, email, setor, status, motivo_rejeicao, data_solicitacao, data_processamento, processado_por
                FROM solicitacoes_registro
                WHERE status != 'pendente'
                ORDER BY data_processamento DESC
                LIMIT 50
            """)
            solicitacoes_processadas = cursor.fetchall()
            
            # Contar total de pendentes (registro + senha)
            cursor.execute("SELECT COUNT(*) FROM solicitacoes_registro WHERE status = 'pendente'")
            total_pendentes_registro = cursor.fetchone()[0]
            
            try:
                cursor.execute("SELECT COUNT(*) FROM solicitacoes_senha WHERE status = 'pendente'")
                total_pendentes_senha = cursor.fetchone()[0]
            except Exception as e:
                logger.error(f"Erro ao contar solicitações de senha pendentes: {e}")
                total_pendentes_senha = 0
                
            total_pendentes = total_pendentes_registro + total_pendentes_senha
            
            # Adicionar variáveis de paginação para compatibilidade com outros templates
            page = 1
            total_pages = 1
            
            return render_template('admin_solicitacoes.html', 
                                  solicitacoes_pendentes=solicitacoes_pendentes,
                                  solicitacoes_processadas=solicitacoes_processadas,
                                  total_pendentes=total_pendentes,
                                  page=page,
                                  total_pages=total_pages)
    
    except Exception as e:
        logger.error(f"Erro ao listar solicitações: {e}")
        flash(f"Erro ao listar solicitações: {e}", "danger")
        return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/solicitacoes/aprovar/<int:solicitacao_id>', methods=['POST'])
@admin_required
def aprovar_solicitacao_registro(solicitacao_id):
    """Aprovar uma solicitação de registro e criar o usuário"""
    try:
        nivel = request.form.get('nivel')
        senha = request.form.get('senha')
        senha_temporaria = 'senha_temporaria' in request.form
        
        if not nivel or not senha:
            flash("Nível de acesso e senha são obrigatórios", "danger")
            return redirect(url_for('admin.solicitacoes'))
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Obter dados da solicitação
            cursor.execute("SELECT nome, username, email, setor FROM solicitacoes_registro WHERE id = ?", (solicitacao_id,))
            solicitacao = cursor.fetchone()
            
            if not solicitacao:
                flash("Solicitação não encontrada", "danger")
                return redirect(url_for('admin.solicitacoes'))
            
            # Verificar se o username já existe
            cursor.execute("SELECT id FROM usuarios WHERE username = ?", (solicitacao['username'],))
            if cursor.fetchone():
                flash(f"Nome de usuário {solicitacao['username']} já existe", "danger")
                return redirect(url_for('admin.solicitacoes'))
            
            # Gerar hash da senha
            password_hash = hash_password(senha)
            
            # Inserir novo usuário
            cursor.execute("""
                INSERT INTO usuarios (username, email, password_hash, nivel, created_at, senha_temporaria, primeiro_login)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (solicitacao['username'], solicitacao['email'], 
                  password_hash, nivel, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
                  1 if senha_temporaria else 0, 1))
            
            # Atualizar status da solicitação
            cursor.execute("""
                UPDATE solicitacoes_registro 
                SET status = 'aprovado', data_processamento = ?, processado_por = ?
                WHERE id = ?
            """, (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), session.get('user'), solicitacao_id))
            
            # Registrar a ação nos logs administrativos
            log_admin_action(
                session.get('user'),
                "APROVAÇÃO DE SOLICITAÇÃO",
                f"Solicitação de registro aprovada para: {solicitacao['username']} (Nível: {nivel})"
            )
            
            conn.commit()
            
            flash(f"Solicitação aprovada e usuário {solicitacao['username']} criado com sucesso", "success")
            return redirect(url_for('admin.solicitacoes'))
    
    except Exception as e:
        logger.error(f"Erro ao aprovar solicitação: {e}")
        flash(f"Erro ao aprovar solicitação: {e}", "danger")
        return redirect(url_for('admin.solicitacoes'))

@admin_bp.route('/solicitacoes/rejeitar/<int:solicitacao_id>', methods=['POST'])
@admin_required
def rejeitar_solicitacao_registro(solicitacao_id):
    """Rejeitar uma solicitação de registro"""
    try:
        motivo = request.form.get('motivo')
        
        if not motivo:
            flash("Motivo da rejeição é obrigatório", "danger")
            return redirect(url_for('admin.solicitacoes'))
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Obter dados da solicitação
            cursor.execute("SELECT username FROM solicitacoes_registro WHERE id = ?", (solicitacao_id,))
            solicitacao = cursor.fetchone()
            
            if not solicitacao:
                flash("Solicitação não encontrada", "danger")
                return redirect(url_for('admin.solicitacoes'))
            
            # Atualizar status da solicitação
            cursor.execute("""
                UPDATE solicitacoes_registro 
                SET status = 'rejeitado', motivo_rejeicao = ?, data_processamento = ?, processado_por = ?
                WHERE id = ?
            """, (motivo, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), session.get('user'), solicitacao_id))
            
            # Registrar a ação nos logs administrativos
            log_admin_action(
                session.get('user'),
                "REJEIÇÃO DE SOLICITAÇÃO",
                f"Solicitação de registro rejeitada para: {solicitacao['username']} (Motivo: {motivo})"
            )
            
            conn.commit()
            
            flash(f"Solicitação de {solicitacao['username']} rejeitada com sucesso", "success")
            return redirect(url_for('admin.solicitacoes'))
    
    except Exception as e:
        logger.error(f"Erro ao rejeitar solicitação: {e}")
        flash(f"Erro ao rejeitar solicitação: {e}", "danger")
        return redirect(url_for('admin.solicitacoes'))

@admin_bp.route('/usuarios/editar/<int:usuario_id>', methods=['GET', 'POST'])
@admin_required
def editar_usuario(usuario_id):
    """Rota para editar um usuário existente"""
    # Contar total de solicitações pendentes para a sidebar
    total_pendentes = 0
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Verificar se a tabela de solicitações de registro existe
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='solicitacoes_registro'")
            if cursor.fetchone():
                cursor.execute("SELECT COUNT(*) FROM solicitacoes_registro WHERE status = 'pendente'")
                solicitacoes_registro = cursor.fetchone()[0]
                total_pendentes += solicitacoes_registro
            
            # Verificar se a tabela de solicitações de senha existe
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='solicitacoes_senha'")
            if cursor.fetchone():
                cursor.execute("SELECT COUNT(*) FROM solicitacoes_senha WHERE status = 'pendente'")
                solicitacoes_senha = cursor.fetchone()[0]
                total_pendentes += solicitacoes_senha
            
            # Obter dados do usuário
            cursor.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
            usuario = cursor.fetchone()
            
            if not usuario:
                flash("Usuário não encontrado", "danger")
                return redirect(url_for('admin.usuarios'))
            
            if request.method == 'POST':
                email = request.form.get('email')
                nivel = request.form.get('nivel')
                senha_temporaria = 1 if request.form.get('ativo') == 'on' else 0
                nova_senha = request.form.get('nova_senha')
                
                # Validação básica
                if not email or not nivel:
                    flash("Email e nível são obrigatórios", "danger")
                    return render_template('admin_editar_usuario.html', usuario=usuario, total_pendentes=total_pendentes)
                
                # Atualizar dados do usuário
                if nova_senha:
                    # Gerar novo hash de senha usando diretamente o Werkzeug
                    password_hash = generate_password_hash(nova_senha)
                    
                    cursor.execute("""
                        UPDATE usuarios
                        SET email = ?, nivel = ?, senha_temporaria = ?, password_hash = ?
                        WHERE id = ?
                    """, (email, nivel, senha_temporaria, password_hash, usuario_id))
                else:
                    cursor.execute("""
                        UPDATE usuarios
                        SET email = ?, nivel = ?, senha_temporaria = ?
                        WHERE id = ?
                    """, (email, nivel, senha_temporaria, usuario_id))
                
                # Registrar a ação nos logs administrativos
                log_admin_action(
                    session.get('user'),
                    "EDIÇÃO DE USUÁRIO",
                    f"Usuário editado: {usuario['username']} (ID: {usuario_id}), Nível alterado para: {nivel}"
                )
                
                conn.commit()
                
                flash("Usuário atualizado com sucesso", "success")
                return redirect(url_for('admin.usuarios'))
            
            # Método GET
            return render_template('admin_editar_usuario.html', usuario=usuario, total_pendentes=total_pendentes)
    
    except Exception as e:
        logger.error(f"Erro ao editar usuário: {e}")
        flash(f"Erro ao editar usuário: {e}", "danger")
        return redirect(url_for('admin.usuarios'))

@admin_bp.route('/usuarios/excluir/<int:usuario_id>', methods=['POST'])
@admin_required
def excluir_usuario(usuario_id):
    """Rota para excluir um usuário"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Verificar se o usuário existe
            cursor.execute("SELECT username FROM usuarios WHERE id = ?", (usuario_id,))
            usuario = cursor.fetchone()
            
            if not usuario:
                flash("Usuário não encontrado", "danger")
                return redirect(url_for('admin.usuarios'))
            
            # Impedir a exclusão do próprio usuário
            if usuario['username'] == session.get('user'):
                flash("Você não pode excluir seu próprio usuário", "danger")
                return redirect(url_for('admin.usuarios'))
            
            # Excluir o usuário
            cursor.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
            
            # Registrar a ação nos logs administrativos
            log_admin_action(
                session.get('user'),
                "EXCLUSÃO DE USUÁRIO",
                f"Usuário excluído: {usuario['username']} (ID: {usuario_id})"
            )
            
            conn.commit()
            
            flash("Usuário excluído com sucesso", "success")
            return redirect(url_for('admin.usuarios'))
    
    except Exception as e:
        logger.error(f"Erro ao excluir usuário: {e}")
        flash(f"Erro ao excluir usuário: {e}", "danger")
        return redirect(url_for('admin.usuarios'))

#----------------------------------------------
# Rotas para Gerenciamento de Solicitações
#----------------------------------------------

@admin_bp.route('/solicitacoes_senha')
@admin_required
def solicitacoes_senha():
    """Rota para listar todas as solicitações de senha pendentes"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Obter solicitações de senha pendentes
            cursor.execute("""
                SELECT s.*, u.nome
                FROM solicitacoes_senha s
                LEFT JOIN usuarios u ON s.usuario_id = u.id
                WHERE s.status = 'pendente'
                ORDER BY s.data_solicitacao DESC
            """)
            solicitacoes_senha = cursor.fetchall()
            
            # Obter solicitações de registro pendentes
            cursor.execute("""
                SELECT *
                FROM solicitacoes_registro
                WHERE status = 'pendente'
                ORDER BY data_solicitacao DESC
            """)
            solicitacoes_registro = cursor.fetchall()
            
            return render_template('admin_solicitacoes.html',
                                  solicitacoes_senha=solicitacoes_senha,
                                  solicitacoes_registro=solicitacoes_registro)
    
    except Exception as e:
        logger.error(f"Erro ao listar solicitações: {e}")
        flash(f"Erro ao listar solicitações: {e}", "danger")
        return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/solicitacoes/aprovar/senha/<int:solicitacao_id>', methods=['POST'])
@admin_required
def aprovar_solicitacao_senha(solicitacao_id):
    """Rota para aprovar uma solicitação de redefinição de senha"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Verificar se a solicitação existe e está pendente
            cursor.execute("""
                SELECT *
                FROM solicitacoes_senha
                WHERE id = ? AND status = 'pendente'
            """, (solicitacao_id,))
            solicitacao = cursor.fetchone()
            
            if not solicitacao:
                flash("Solicitação não encontrada ou já processada", "danger")
                return redirect(url_for('admin.solicitacoes'))
            
            # Obter informações do usuário
            cursor.execute("""
                SELECT id, username
                FROM usuarios
                WHERE username = ?
            """, (solicitacao['username'],))
            usuario = cursor.fetchone()
            
            if not usuario:
                flash(f"Usuário {solicitacao['username']} não encontrado", "danger")
                return redirect(url_for('admin.solicitacoes'))
            
            # Obter a nova senha do formulário
            nova_senha = request.form.get('senha')
            if not nova_senha:
                nova_senha = secrets.token_urlsafe(8)  # Senha de 8 caracteres
            
            # Gerar hash da nova senha
            password_hash = hash_password(nova_senha)
            
            # Definir se a senha é temporária
            senha_temporaria = 1 if request.form.get('senha_temporaria') else 0
            
            # Atualizar senha do usuário
            cursor.execute("""
                UPDATE usuarios
                SET password_hash = ?, senha_temporaria = ?, ultima_alteracao_senha = ?
                WHERE id = ?
            """, (password_hash, senha_temporaria, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), usuario['id']))
            
            # Atualizar status da solicitação
            cursor.execute("""
                UPDATE solicitacoes_senha
                SET status = 'aprovada', aprovado_por = ?, data_aprovacao = ?
                WHERE id = ?
            """, (session.get('user'), datetime.now().strftime('%Y-%m-%d %H:%M:%S'), solicitacao_id))
            
            # Registrar a ação nos logs administrativos
            log_admin_action(
                session.get('user'),
                "APROVAÇÃO DE REDEFINIÇÃO DE SENHA",
                f"Solicitação de redefinição de senha aprovada para: {solicitacao['username']}"
            )
            
            conn.commit()
            
            flash(f"Solicitação aprovada. Nova senha para {solicitacao['username']}: {nova_senha}", "success")
            return redirect(url_for('admin.solicitacoes'))
    
    except Exception as e:
        logger.error(f"Erro ao aprovar solicitação de senha: {e}")
        flash(f"Erro ao aprovar solicitação: {e}", "danger")
        return redirect(url_for('admin.solicitacoes'))

@admin_bp.route('/solicitacoes/rejeitar/senha/<int:solicitacao_id>', methods=['POST'])
@admin_required
def rejeitar_solicitacao_senha(solicitacao_id):
    """Rota para rejeitar uma solicitação de redefinição de senha"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Verificar se a solicitação existe e está pendente
            cursor.execute("""
                SELECT *
                FROM solicitacoes_senha
                WHERE id = ? AND status = 'pendente'
            """, (solicitacao_id,))
            solicitacao = cursor.fetchone()
            
            if not solicitacao:
                flash("Solicitação não encontrada ou já processada", "danger")
                return redirect(url_for('admin.solicitacoes'))
            
            # Obter motivo da rejeição do formulário
            motivo = request.form.get('motivo', '')
            
            # Atualizar status da solicitação
            cursor.execute("""
                UPDATE solicitacoes_senha
                SET status = 'rejeitada', aprovado_por = ?, data_aprovacao = ?
                WHERE id = ?
            """, (session.get('user'), datetime.now().strftime('%Y-%m-%d %H:%M:%S'), solicitacao_id))
            
            # Registrar a ação nos logs administrativos
            log_admin_action(
                session.get('user'),
                "REJEIÇÃO DE REDEFINIÇÃO DE SENHA",
                f"Solicitação de redefinição de senha rejeitada para: {solicitacao['username']}. Motivo: {motivo}"
            )
            
            conn.commit()
            
            flash("Solicitação rejeitada com sucesso", "success")
            return redirect(url_for('admin.solicitacoes'))
    
    except Exception as e:
        logger.error(f"Erro ao rejeitar solicitação de senha: {e}")
        flash(f"Erro ao rejeitar solicitação: {e}", "danger")
        return redirect(url_for('admin.solicitacoes'))

@admin_bp.route('/solicitacoes/aprovar/registro/<int:solicitacao_id>', methods=['POST'])
@admin_required
def aprovar_solicitacao_registro_completo(solicitacao_id):
    """Rota para aprovar uma solicitação de registro de usuário"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Verificar se a solicitação existe e está pendente
            cursor.execute("""
                SELECT *
                FROM solicitacoes_registro
                WHERE id = ? AND status = 'pendente'
            """, (solicitacao_id,))
            solicitacao = cursor.fetchone()
            
            if not solicitacao:
                flash("Solicitação não encontrada ou já processada", "danger")
                return redirect(url_for('admin.solicitacoes'))
            
            # Verificar se o username já existe
            cursor.execute("SELECT id FROM usuarios WHERE username = ?", (solicitacao['username'],))
            if cursor.fetchone():
                flash(f"Nome de usuário {solicitacao['username']} já existe", "danger")
                return redirect(url_for('admin.solicitacoes'))
            
            # Gerar senha aleatória
            senha = secrets.token_urlsafe(8)  # Senha de 8 caracteres
            
            # Gerar hash da senha
            password_hash = hash_password(senha)
            
            # Criar novo usuário
            cursor.execute("""
                INSERT INTO usuarios (username, nome, email, password_hash, nivel, created_at, senha_temporaria)
                VALUES (?, ?, ?, ?, 'comum', ?, 1)
            """, (solicitacao['username'], solicitacao['nome'], solicitacao['email'], 
                  password_hash, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            
            # Atualizar status da solicitação
            cursor.execute("""
                UPDATE solicitacoes_registro
                SET status = 'aprovada', processado_por = ?, data_processamento = ?
                WHERE id = ?
            """, (session.get('user'), datetime.now().strftime('%Y-%m-%d %H:%M:%S'), solicitacao_id))
            
            # Registrar a ação nos logs administrativos
            log_admin_action(
                session.get('user'),
                "APROVAÇÃO DE REGISTRO DE USUÁRIO",
                f"Solicitação de registro aprovada para: {solicitacao['username']} (Nome: {solicitacao['nome']})"
            )
            
            conn.commit()
            
            flash(f"Solicitação aprovada. Usuário {solicitacao['username']} criado com senha: {senha}", "success")
            return redirect(url_for('admin.solicitacoes'))
    
    except Exception as e:
        logger.error(f"Erro ao aprovar solicitação de registro: {e}")
        flash(f"Erro ao aprovar solicitação: {e}", "danger")
        return redirect(url_for('admin.solicitacoes'))

@admin_bp.route('/solicitacoes/rejeitar/registro/<int:solicitacao_id>', methods=['POST'])
@admin_required
def rejeitar_solicitacao_registro_completo(solicitacao_id):
    """Rota para rejeitar uma solicitação de registro de usuário"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Verificar se a solicitação existe e está pendente
            cursor.execute("""
                SELECT *
                FROM solicitacoes_registro
                WHERE id = ? AND status = 'pendente'
            """, (solicitacao_id,))
            solicitacao = cursor.fetchone()
            
            if not solicitacao:
                flash("Solicitação não encontrada ou já processada", "danger")
                return redirect(url_for('admin.solicitacoes'))
            
            # Atualizar status da solicitação
            cursor.execute("""
                UPDATE solicitacoes_registro
                SET status = 'rejeitada', processado_por = ?, data_processamento = ?
                WHERE id = ?
            """, (session.get('user'), datetime.now().strftime('%Y-%m-%d %H:%M:%S'), solicitacao_id))
            
            # Registrar a ação nos logs administrativos
            log_admin_action(
                session.get('user'),
                "REJEIÇÃO DE REGISTRO DE USUÁRIO",
                f"Solicitação de registro rejeitada para: {solicitacao['username']} (Nome: {solicitacao['nome']})"
            )
            
            conn.commit()
            
            flash("Solicitação rejeitada com sucesso", "success")
            return redirect(url_for('admin.solicitacoes'))
    
    except Exception as e:
        logger.error(f"Erro ao rejeitar solicitação de registro: {e}")
        flash(f"Erro ao rejeitar solicitação: {e}", "danger")
        return redirect(url_for('admin.solicitacoes'))

#----------------------------------------------
# Rotas para Visualização de Logs
#----------------------------------------------

@admin_bp.route('/logs', methods=['GET', 'POST'])
@login_required
def logs():
    try:
        if session.get('nivel') != 'admin':
            return redirect(url_for('index'))
        
        # Obter parâmetros básicos
        tipo_log = request.args.get('tipo_log', '')
        usuario_filtro = request.args.get('usuario', '')
        acao_filtro = request.args.get('acao', '')
        data_inicio = request.args.get('data_inicio', '')
        data_fim = request.args.get('data_fim', '')
        nivel_filtro = request.args.get('nivel', '')
        page = request.args.get('page', 1, type=int)
        per_page = 20  # Número de logs por página
        
        # Conectar ao banco de dados
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Verificar se a tabela logs_unificados existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='logs_unificados'")
        usar_tabela_unificada = cursor.fetchone() is not None
        
        # Definir a tabela a ser usada
        tabela_logs = "logs_unificados" if usar_tabela_unificada else "log_atividades"
        logger.info(f"Usando tabela de logs: {tabela_logs}")
        
        # Construir a consulta base
        query_base = f"FROM {tabela_logs} WHERE 1=1"
        params = []
        
        # Adicionar filtros se fornecidos
        if usuario_filtro:
            query_base += " AND usuario LIKE ?"
            params.append(f"%{usuario_filtro}%")
            
        if acao_filtro:
            query_base += " AND acao LIKE ?"
            params.append(f"%{acao_filtro}%")
            
        if nivel_filtro:
            query_base += " AND nivel = ?"
            params.append(nivel_filtro)
            
        if data_inicio:
            query_base += " AND data_hora >= ?"
            params.append(f"{data_inicio} 00:00:00")
            
        if data_fim:
            query_base += " AND data_hora <= ?"
            params.append(f"{data_fim} 23:59:59")
            
        if tipo_log:
            if tipo_log == 'sistema':
                query_base += " AND nivel = 'sistema'"
            elif tipo_log == 'usuarios':
                query_base += " AND nivel = 'admin'"
            elif tipo_log == 'registros':
                query_base += " AND nivel NOT IN ('sistema', 'admin')"
        
        # Contar total de registros para paginação
        count_query = f"SELECT COUNT(*) {query_base}"
        cursor.execute(count_query, params)
        total_logs = cursor.fetchone()[0]
        
        # Calcular total de páginas
        total_pages = (total_logs + per_page - 1) // per_page
        if total_pages < 1:
            total_pages = 1
        
        # Ajustar página atual se estiver fora dos limites
        if page < 1:
            page = 1
        if page > total_pages:
            page = total_pages
        
        # Calcular offset para paginação
        offset = (page - 1) * per_page
        
        # Consulta final com paginação
        query = f"""
            SELECT id, usuario, nivel, acao, descricao, 
            data_hora as data, 
            CASE 
                WHEN nivel = 'sistema' THEN 'sistema'
                WHEN nivel = 'admin' THEN 'usuarios'
                ELSE 'registros'
            END as tipo_log,
            registro_id
            {query_base}
            ORDER BY data_hora DESC
            LIMIT ? OFFSET ?
        """
        
        # Adicionar parâmetros de paginação
        params.append(per_page)
        params.append(offset)
        
        # Executar a consulta
        cursor.execute(query, params)
        logs = cursor.fetchall()
        
        # Garantir que logs seja uma lista, mesmo que vazia
        if logs is None:
            logs = []
        
        # Obter listas para filtros
        cursor.execute(f"SELECT DISTINCT usuario FROM {tabela_logs} ORDER BY usuario")
        usuarios = [row[0] for row in cursor.fetchall() if row[0]]
        
        cursor.execute(f"SELECT DISTINCT acao FROM {tabela_logs} ORDER BY acao")
        acoes = [row[0] for row in cursor.fetchall() if row[0]]
        
        cursor.execute(f"SELECT DISTINCT nivel FROM {tabela_logs} ORDER BY nivel")
        niveis = [row[0] for row in cursor.fetchall() if row[0]]
        
        # Contar total de solicitações pendentes para a sidebar
        total_pendentes = 0
        
        # Verificar se a tabela de solicitações de registro existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='solicitacoes_registro'")
        if cursor.fetchone():
            cursor.execute("SELECT COUNT(*) as total FROM solicitacoes_registro WHERE status = 'pendente'")
            result = cursor.fetchone()
            if result:
                total_pendentes += result[0]  # Usar índice em vez de nome da coluna
        
        # Verificar se a tabela de solicitações de senha existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='solicitacoes_senha'")
        if cursor.fetchone():
            cursor.execute("SELECT COUNT(*) as total FROM solicitacoes_senha WHERE status = 'pendente'")
            result = cursor.fetchone()
            if result:
                total_pendentes += result[0]  # Usar índice em vez de nome da coluna
        
        conn.close()
        
        # Renderizar o template com os dados
        return render_template('admin_logs.html', 
                           logs=logs, 
                           usuarios=usuarios, 
                           acoes=acoes,
                           niveis=niveis,
                           tipo_log=tipo_log,
                           usuario_filtro=usuario_filtro,
                           acao_filtro=acao_filtro,
                           nivel_filtro=nivel_filtro,
                           data_inicio=data_inicio,
                           data_fim=data_fim,
                           total_pendentes=total_pendentes,
                           usuario=session.get('user'),
                           nivel=session.get('nivel'),
                           page=page,
                           total_pages=total_pages,
                           total_logs=total_logs)
    
    except Exception as e:
        logger.error(f"Erro ao listar logs: {e}")
        flash(f"Erro ao listar logs: {e}", "danger")
        return redirect(url_for('admin.admin_dashboard'))

#----------------------------------------------
# Rotas para Backup e Manutenção
#----------------------------------------------

@admin_bp.route('/backup')
@admin_required
def backup():
    """Rota para realizar backup do banco de dados"""
    try:
        # Obter data e hora atual para o nome do arquivo
        data_hora = datetime.now().strftime('%Y%m%d_%H%M%S')
        nome_arquivo = f"backup_usuarios_{data_hora}.db"
        diretorio_backup = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backups')
        
        # Criar diretório de backup se não existir
        if not os.path.exists(diretorio_backup):
            os.makedirs(diretorio_backup)
        
        caminho_backup = os.path.join(diretorio_backup, nome_arquivo)
        
        # Realizar backup do banco de dados
        with get_db_connection() as conn:
            # Criar uma cópia do banco de dados
            with open(caminho_backup, 'wb') as f_backup:
                for linha in conn.iterdump():
                    f_backup.write(f"{linha}\n".encode('utf-8'))
            
            # Registrar a ação nos logs administrativos
            log_admin_action(
                session.get('user'),
                "BACKUP DO BANCO DE DADOS",
                f"Backup realizado: {nome_arquivo} em {diretorio_backup}"
            )
        
        flash(f"Backup realizado com sucesso: {nome_arquivo}", "success")
        return redirect(url_for('admin.admin_dashboard'))
    
    except Exception as e:
        logger.error(f"Erro ao realizar backup: {e}")
        flash(f"Erro ao realizar backup: {e}", "danger")
        return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/limpar-logs', methods=['POST'])
@admin_required
def limpar_logs():
    """Rota para limpar logs antigos"""
    try:
        dias = int(request.form.get('dias', 90))
        
        if dias < 30:
            flash("Por razões de segurança, não é possível excluir logs com menos de 30 dias", "danger")
            return redirect(url_for('admin.logs'))
        
        data_limite = (datetime.now() - timedelta(days=dias)).strftime('%Y-%m-%d')
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Contar quantos logs serão excluídos
            cursor.execute("SELECT COUNT(*) FROM logs WHERE data < ?", (data_limite,))
            total_excluidos = cursor.fetchone()[0]
            
            # Excluir logs antigos
            cursor.execute("DELETE FROM logs WHERE data < ?", (data_limite,))
            
            # Registrar a ação nos logs administrativos
            log_admin_action(
                session.get('user'),
                "LIMPEZA DE LOGS",
                f"Removidos {total_excluidos} logs anteriores a {data_limite}"
            )
            
            conn.commit()
        
        flash(f"{total_excluidos} logs anteriores a {data_limite} foram removidos com sucesso", "success")
        return redirect(url_for('admin.logs'))
    
    except Exception as e:
        logger.error(f"Erro ao limpar logs: {e}")
        flash(f"Erro ao limpar logs: {e}", "danger")
        return redirect(url_for('admin.logs'))

#----------------------------------------------
# Rotas para Estatísticas e Relatórios
#----------------------------------------------

@admin_bp.route('/estatisticas')
@admin_required
def estatisticas():
    """Rota para visualizar estatísticas detalhadas do sistema"""
    try:
        periodo = request.args.get('periodo', '30')  # Padrão: 30 dias
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Estatísticas de usuários
            cursor.execute("SELECT nivel, COUNT(*) FROM usuarios GROUP BY nivel")
            usuarios_por_nivel = cursor.fetchall()
            
            cursor.execute("SELECT COUNT(*) FROM usuarios WHERE ultimo_acesso >= date('now', '-30 days')")
            usuarios_ativos_30d = cursor.fetchone()[0]
            
            # Estatísticas de registros
            cursor.execute("SELECT status_sm, COUNT(*) FROM registros WHERE excluido = 0 GROUP BY status_sm")
            registros_por_status = cursor.fetchall()
            
            cursor.execute(f"SELECT COUNT(*) FROM registros WHERE data_registro >= date('now', '-{periodo} days') AND excluido = 0")
            registros_periodo = cursor.fetchone()[0]
            
            # Estatísticas de solicitações
            cursor.execute("SELECT status, COUNT(*) FROM solicitacoes_senha GROUP BY status")
            solicitacoes_senha_por_status = cursor.fetchall()
            
            cursor.execute("SELECT status, COUNT(*) FROM solicitacoes_registro GROUP BY status")
            solicitacoes_registro_por_status = cursor.fetchall()
            
            # Estatísticas de logs
            cursor.execute("SELECT date(data), COUNT(*) FROM logs GROUP BY date(data) ORDER BY date(data) DESC LIMIT 30")
            logs_por_dia = cursor.fetchall()
            
            cursor.execute("SELECT usuario, COUNT(*) FROM logs GROUP BY usuario ORDER BY COUNT(*) DESC LIMIT 10")
            logs_por_usuario = cursor.fetchall()
            
            # Dados para gráficos
            labels_usuarios = [row[0] for row in usuarios_por_nivel]
            dados_usuarios = [row[1] for row in usuarios_por_nivel]
            
            labels_registros = [row[0] if row[0] else 'Sem status' for row in registros_por_status]
            dados_registros = [row[1] for row in registros_por_status]
            
            labels_logs = [row[0] for row in logs_por_dia]
            dados_logs = [row[1] for row in logs_por_dia]
            
            return render_template('admin_estatisticas.html',
                                  periodo=periodo,
                                  usuarios_por_nivel=usuarios_por_nivel,
                                  usuarios_ativos_30d=usuarios_ativos_30d,
                                  registros_por_status=registros_por_status,
                                  registros_periodo=registros_periodo,
                                  solicitacoes_senha_por_status=solicitacoes_senha_por_status,
                                  solicitacoes_registro_por_status=solicitacoes_registro_por_status,
                                  logs_por_dia=logs_por_dia,
                                  logs_por_usuario=logs_por_usuario,
                                  labels_usuarios=labels_usuarios,
                                  dados_usuarios=dados_usuarios,
                                  labels_registros=labels_registros,
                                  dados_registros=dados_registros,
                                  labels_logs=labels_logs,
                                  dados_logs=dados_logs)
    
    except Exception as e:
        logger.error(f"Erro ao carregar estatísticas: {e}")
        flash(f"Erro ao carregar estatísticas: {e}", "danger")
        return redirect(url_for('admin.admin_dashboard'))



#----------------------------------------------
# Rotas para Configurações do Sistema
#----------------------------------------------

@admin_bp.route('/configuracoes', methods=['GET', 'POST'])
@admin_required
def configuracoes():
    """Rota para gerenciar configurações do sistema"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Verificar se a tabela de configurações existe
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='configuracoes'")
            if not cursor.fetchone():
                # Criar tabela de configurações se não existir
                cursor.execute("""
                    CREATE TABLE configuracoes (
                        chave TEXT PRIMARY KEY,
                        valor TEXT,
                        descricao TEXT,
                        tipo TEXT,
                        data_modificacao TIMESTAMP
                    )
                """)
                
                # Inserir configurações padrão
                configuracoes_padrao = [
                    ('titulo_sistema', 'Atendimento GR', 'Título do sistema', 'texto', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                    ('max_tentativas_login', '3', 'Número máximo de tentativas de login', 'numero', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                    ('tempo_bloqueio_login', '30', 'Tempo de bloqueio após exceder tentativas (minutos)', 'numero', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                    ('tempo_sessao', '60', 'Tempo de sessão (minutos)', 'numero', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                    ('permitir_registro', 'true', 'Permitir solicitações de registro', 'booleano', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                    ('permitir_redefinicao_senha', 'true', 'Permitir solicitações de redefinição de senha', 'booleano', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                    ('email_notificacoes', '', 'Email para notificações', 'texto', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                ]
                
                cursor.executemany("""
                    INSERT INTO configuracoes (chave, valor, descricao, tipo, data_modificacao)
                    VALUES (?, ?, ?, ?, ?)
                """, configuracoes_padrao)
                
                conn.commit()
            
            if request.method == 'POST':
                # Atualizar configurações
                for chave in request.form:
                    if chave != 'csrf_token':
                        valor = request.form.get(chave)
                        
                        cursor.execute("""
                            UPDATE configuracoes
                            SET valor = ?, data_modificacao = ?
                            WHERE chave = ?
                        """, (valor, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), chave))
                
                # Registrar a ação nos logs administrativos
                log_admin_action(
                    session.get('user'),
                    "ATUALIZAÇÃO DE CONFIGURAÇÕES",
                    f"Configurações do sistema atualizadas"
                )
                
                conn.commit()
                
                flash("Configurações atualizadas com sucesso", "success")
                return redirect(url_for('admin.configuracoes'))
            
            # Obter configurações atuais
            cursor.execute("SELECT * FROM configuracoes ORDER BY chave")
            configuracoes = cursor.fetchall()
            
            return render_template('admin_configuracoes.html', configuracoes=configuracoes)
    
    except Exception as e:
        logger.error(f"Erro ao gerenciar configurações: {e}")
        flash(f"Erro ao gerenciar configurações: {e}", "danger")
        return redirect(url_for('admin.admin_dashboard'))
