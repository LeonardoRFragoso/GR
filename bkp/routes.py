from flask import Blueprint, render_template, request, redirect, url_for, flash, session
import sys
import os
import sqlite3
import time
import logging
import json
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, jsonify, current_app, send_from_directory

# Adiciona o diretório principal ao path para importações relativas
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth.decorators import login_required, admin_required, admin_or_gr_required
from models.database import get_db_connection
from models.users import Usuario
from models.registros import Registro
from models.historico import Historico
from admin.logs import log_admin_action, get_admin_logs, count_admin_logs
from admin.routes_solicitacoes import (solicitacoes_view, aprovar_solicitacao_registro, 
    rejeitar_solicitacao_registro, get_solicitacoes_pendentes, get_solicitacoes_processadas, count_solicitacoes_pendentes)

# Criação do blueprint para administração
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Rota simples para teste de acesso
@admin_bp.route('/teste')
@admin_required
def teste_admin():
    return render_template('admin_dashboard.html', 
                           usuario=session.get('user'),
                           nivel=session.get('nivel'),
                           total_solicitacoes_pendentes=0,
                           total_solicitacoes_senha_pendentes=0,
                           total_usuarios_comuns=0,
                           total_usuarios_gr=0,
                           total_usuarios_admin=0,
                           total_registros=0,
                           registros_por_status=[],
                           logs_formatados=[],
                           atividade_por_usuario=[],
                           tempo=int(time.time()))

@admin_bp.route('/dashboard')
@login_required
def dashboard():
    """Painel administrativo para admin e redirecionamento para GR"""
    usuario = session.get('user')
    nivel = session.get('nivel')
    
    # Se o usuário for GR, redireciona para o dashboard de GR
    if nivel == 'gr':
        return redirect(url_for('gr.dashboard'))
    
    # Verificar se o usuário é admin
    if nivel != 'admin':
        flash('Acesso restrito a administradores.', 'danger')
        return redirect(url_for('auth.login'))
    
    # Resumo de estatísticas para o admin
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Contar solicitações de registro pendentes
            cursor.execute("SELECT COUNT(*) FROM solicitacoes_registro WHERE status = 'pendente'")
            total_solicitacoes_pendentes = cursor.fetchone()[0]
            
            # Contar solicitações de redefinição de senha pendentes
            cursor.execute("SELECT COUNT(*) FROM solicitacoes_senha WHERE status = 'pendente'")
            total_solicitacoes_senha_pendentes = cursor.fetchone()[0]
            
            # Total de usuários por nível
            cursor.execute("SELECT nivel, COUNT(*) as total FROM usuarios GROUP BY nivel")
            usuarios_por_nivel = cursor.fetchall()
            
            # Inicializar contadores de usuários por tipo
            total_usuarios_comuns = 0
            total_usuarios_gr = 0
            total_usuarios_admin = 0
            
            # Extrair contadores específicos por nível
            for nivel_item in usuarios_por_nivel:
                if nivel_item['nivel'] == 'comum':
                    total_usuarios_comuns = nivel_item['total']
                elif nivel_item['nivel'] == 'gr':
                    total_usuarios_gr = nivel_item['total']
                elif nivel_item['nivel'] == 'admin':
                    total_usuarios_admin = nivel_item['total']
            
            # Total de registros
            cursor.execute("SELECT COUNT(*) FROM registros")
            total_registros = cursor.fetchone()[0]
            
            # Registros por status
            cursor.execute("""
                SELECT status_sm, COUNT(*) as total 
                FROM registros 
                WHERE status_sm IS NOT NULL AND status_sm != '' 
                GROUP BY status_sm
                ORDER BY total DESC
            """)
            registros_por_status = cursor.fetchall()
            
            # Atividade recente (últimas ações administrativas) com melhor formatação
            cursor.execute("""
                SELECT * FROM admin_logs
                ORDER BY data DESC
                LIMIT 10
            """)
            atividade_recente_raw = cursor.fetchall()
            atividade_recente = []
            
            # Formatar os logs para melhor visualização
            for log in atividade_recente_raw:
                log_formatado = dict(log)
                
                # Extrair detalhes mais relevantes
                detalhes = log_formatado['detalhes']
                if 'Registro ID:' in detalhes and 'Campos:' in detalhes:
                    try:
                        registro_id = detalhes.split('Registro ID:')[1].split(',')[0].strip()
                        log_formatado['registro_id'] = registro_id
                        
                        # Extrair apenas alguns campos relevantes se houver muitos
                        if '=>' in detalhes:
                            campos_alterados = [campo.strip() for campo in detalhes.split('Campos:')[1].split(', ') 
                                              if '=>' in campo]
                            num_campos = len(campos_alterados)
                            
                            if num_campos > 2:
                                log_formatado['detalhes'] = f"Alterados {num_campos} campos no registro {registro_id}"
                            elif num_campos > 0:
                                log_formatado['detalhes'] = f"Alterado(s) {', '.join([c.split(':')[0].strip() for c in campos_alterados])} no registro {registro_id}"
                    except Exception as e:
                        print(f"Erro ao formatar log: {e}")
                
                atividade_recente.append(log_formatado)
                
            # Estatísticas sobre as atividades dos usuários
            cursor.execute("""
                SELECT usuario, acao, COUNT(*) as total 
                FROM admin_logs 
                GROUP BY usuario, acao 
                ORDER BY total DESC, usuario
                LIMIT 20
            """)
            atividade_por_usuario = cursor.fetchall()
            
            # Campos mais frequentemente alterados
            cursor.execute("""
                SELECT * FROM admin_logs
                WHERE acao LIKE '%EDIÇÃO%'
                ORDER BY data DESC
                LIMIT 100
            """)
            logs_edicao = cursor.fetchall()
            
            campos_alterados = {}
            for log in logs_edicao:
                detalhes = log['detalhes']
                if 'Campos:' in detalhes:
                    try:
                        campos_parte = detalhes.split('Campos:')[1]
                        for parte in campos_parte.split(', '):
                            if ':' in parte and '=>' in parte:
                                campo_nome = parte.split(':')[0].strip()
                                if campo_nome in campos_alterados:
                                    campos_alterados[campo_nome] += 1
                                else:
                                    campos_alterados[campo_nome] = 1
                    except Exception as e:
                        print(f"Erro ao analisar campos alterados: {e}")
            
            # Converter para lista ordenada
            campos_mais_alterados = sorted(
                [{'campo': campo, 'total': total} for campo, total in campos_alterados.items()],
                key=lambda x: x['total'], 
                reverse=True
            )[:5]  # Top 5 campos mais alterados
            
            # Solicitações de senha pendentes
            cursor.execute("""
                SELECT s.*, u.nivel 
                FROM solicitacoes_senha s
                JOIN usuarios u ON s.username = u.username
                WHERE s.status = 'pendente'
                ORDER BY s.data_solicitacao DESC
            """)
            solicitacoes_pendentes = cursor.fetchall()
            
    except Exception as e:
        flash(f"Erro ao carregar o dashboard: {e}", "danger")
        usuarios_por_nivel = []
        total_usuarios_comuns = 0
        total_usuarios_gr = 0
        total_usuarios_admin = 0
        total_registros = 0
        registros_por_status = []
        atividade_recente = []
        atividade_por_usuario = []
        campos_mais_alterados = []
        solicitacoes_pendentes = []
    
    return render_template(
        'admin_dashboard.html',
        usuario=usuario,
        nivel=nivel,
        usuarios_por_nivel=usuarios_por_nivel,
        total_usuarios_comuns=total_usuarios_comuns,
        total_usuarios_gr=total_usuarios_gr,
        total_usuarios_admin=total_usuarios_admin,
        total_registros=total_registros,
        registros_por_status=registros_por_status,
        atividade_recente=atividade_recente,
        atividade_por_usuario=atividade_por_usuario,
        campos_mais_alterados=campos_mais_alterados,
        logs_formatados=atividade_recente,
        total_solicitacoes_pendentes=total_solicitacoes_pendentes,
        total_solicitacoes_senha_pendentes=total_solicitacoes_senha_pendentes
    )

# Nova rota de diagnóstico ultra simplificada
@admin_bp.route('/usuarios_teste')
@login_required
def usuarios_teste():
    # Rota ultra simplificada só para diagnóstico
    return f"<html><body><h1>Página de Gestão de Usuários - Diagnóstico</h1><p>Se você consegue ver esta página, a rota está funcionando. Usuário: {session.get('user')}</p></body></html>"

# Rota original restaurada para gestão de usuários
@admin_bp.route('/usuarios')
@login_required
def usuarios():
    """Gerenciamento de usuários - restrito a administradores com tratamento de erro robusto"""
    try:
        nivel = session.get('nivel')
        usuario = session.get('user')
        
        # Se não for administrador, redirecionar para o dashboard
        if nivel != 'admin':
            flash('Acesso restrito a administradores.', 'danger')
            return redirect(url_for('auth.login'))
        
        # Inicializar variáveis com valores padrão
        usuarios = []
        solicitacoes = []
        total_solicitacoes_reg_pendentes = 0
        total_solicitacoes_senha_pendentes = 0
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Obter listagem de usuários
            try:
                cursor.execute("SELECT * FROM usuarios ORDER BY nivel, username")
                usuarios = [dict(u) for u in cursor.fetchall()]
            except Exception as e:
                logging.error(f"Erro ao consultar usuários: {str(e)}")
                flash("Erro ao carregar lista de usuários", "warning")
            
            # 2. Tentar obter solicitações de senha (tratando caso a tabela não exista)
            try:
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='solicitacoes_senha'
                """)
                if cursor.fetchone():
                    cursor.execute("""
                        SELECT s.*, u.nivel 
                        FROM solicitacoes_senha s
                        LEFT JOIN usuarios u ON s.username = u.username
                        WHERE s.status = 'pendente'
                        ORDER BY s.data_solicitacao DESC
                    """)
                    solicitacoes = [dict(s) for s in cursor.fetchall()]
                    
                    # Contar solicitações pendentes
                    cursor.execute("""
                        SELECT COUNT(*) FROM solicitacoes_senha 
                        WHERE status = 'pendente'
                    """)
                    total_solicitacoes_senha_pendentes = cursor.fetchone()[0] or 0
            except Exception as e:
                logging.warning(f"Tabela de solicitações de senha não encontrada ou erro ao acessá-la: {str(e)}")
                solicitacoes = []
                total_solicitacoes_senha_pendentes = 0
            
            # 3. Tentar obter contagem de solicitações de registro (se a tabela existir)
            try:
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='solicitacoes_registro'
                """)
                if cursor.fetchone():
                    cursor.execute("""
                        SELECT COUNT(*) as count 
                        FROM solicitacoes_registro 
                        WHERE status = 'pendente'
                    """)
                    result = cursor.fetchone()
                    total_solicitacoes_reg_pendentes = result[0] if result else 0
            except Exception as e:
                logging.warning(f"Tabela de solicitações de registro não encontrada ou erro ao acessá-la: {str(e)}")
                total_solicitacoes_reg_pendentes = 0
        
        return render_template(
            'admin_usuarios.html',
            usuarios=usuarios,
            solicitacoes=solicitacoes,
            usuario=usuario,
            nivel=nivel,
            total_solicitacoes_reg_pendentes=total_solicitacoes_reg_pendentes,
            total_solicitacoes_senha_pendentes=total_solicitacoes_senha_pendentes,
            usuario_edit=None
        )
        
    except Exception as e:
        logging.error(f"Erro inesperado em usuarios(): {str(e)}")
        flash("Ocorreu um erro inesperado. Por favor, tente novamente.", "danger")
        return redirect(url_for('admin.dashboard'))


@admin_bp.route('/editar_usuario/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def editar_usuario(user_id):
    """Edição de usuários"""
    admin_username = session.get('user')
    
    # Obter o usuário pelo ID
    usuario = Usuario.get_by_id(user_id)
    if not usuario:
        flash("Usuário não encontrado.", "danger")
        return redirect(url_for('admin.usuarios'))
    
    if request.method == 'POST':
        # Obter os dados do formulário
        nivel = request.form.get('nivel')
        
        # Atualizar o usuário
        if Usuario.update(user_id, nivel=nivel):
            flash("Usuário atualizado com sucesso.", "success")
            
            # Registrar a ação no log administrativo
            detalhes = f"Usuário: {usuario['username']}, Nível: {nivel}"
                
            log_admin_action(
                admin_username,
                "EDIÇÃO DE USUÁRIO",
                detalhes
            )
            
            return redirect(url_for('admin.usuarios'))
        else:
            flash("Erro ao atualizar usuário.", "danger")
    
    # Obter a lista de usuários e solicitações para o template unificado
    usuarios = Usuario.get_all()
    solicitacoes = Usuario.get_solicitacoes_pendentes()
    
    return render_template(
        'admin_usuarios.html',
        usuario_edit=usuario,
        usuarios=usuarios,
        solicitacoes=solicitacoes,
        usuario=admin_username,
        nivel=session.get('nivel')
    )

@admin_bp.route('/criar_usuario', methods=['POST'])
@admin_required
def criar_usuario():
    """Criação de novos usuários"""
    admin_username = session.get('user')
    
    if request.method == 'POST':
        # Obter os dados do formulário
        username = request.form.get('username')
        password = request.form.get('password')
        nivel = request.form.get('nivel')
        
        # Validações básicas
        if not username or not password:
            flash("Nome de usuário e senha são obrigatórios.", "danger")
            return redirect(url_for('admin.usuarios'))
        
        # Criar o usuário
        user_id = Usuario.create(username, password, nivel)
        if user_id:
            flash("Usuário criado com sucesso.", "success")
            
            # Registrar a ação no log administrativo
            log_admin_action(
                admin_username,
                "CRIAÇÃO DE USUÁRIO",
                f"Usuário: {username}, Nível: {nivel}"
            )
        else:
            flash("Erro ao criar usuário. O nome de usuário pode já estar em uso.", "danger")
    
    return redirect(url_for('admin.usuarios'))

@admin_bp.route('/logs')
@admin_or_gr_required
def logs():
    """Visualização de logs administrativos"""
    # Paginação
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page
    
    try:
        # Obter os logs com paginação
        logs = get_admin_logs(per_page, offset)
        
        # Contar total de logs para paginação
        total = count_admin_logs()
        total_pages = (total + per_page - 1) // per_page  # Arredondar para cima
        
        # Obtemos também solicitações de senha para administradores
        nivel_usuario = session.get('nivel')
        solicitacoes_pendentes = []
        
        if nivel_usuario == 'admin':
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT s.*, u.nivel 
                    FROM solicitacoes_senha s
                    JOIN usuarios u ON s.username = u.username
                    WHERE s.status = 'pendente'
                    ORDER BY s.data_solicitacao DESC
                """)
                solicitacoes_pendentes = cursor.fetchall()
        
        return render_template(
            'admin_logs.html',
            logs=logs,
            page=page,
            total_pages=total_pages,
            usuario=session.get('user'),
            nivel=nivel_usuario,
            solicitacoes_pendentes=solicitacoes_pendentes
        )
    except Exception as e:
        flash(f"Erro ao carregar logs: {e}", "danger")
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/alterar_senha_usuario', methods=['POST'])
@admin_required
def alterar_senha_usuario():
    """Alteração de senha de usuário pelo administrador"""
    admin_username = session.get('user')
    
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        nova_senha = request.form.get('nova_senha')
        
        if not user_id or not nova_senha:
            flash("ID de usuário e nova senha são obrigatórios.", "danger")
            return redirect(url_for('admin.usuarios'))
        
        try:
            # Converter para inteiro com tratamento de erro
            user_id = int(user_id)
            
            # Obter o usuário
            usuario = Usuario.get_by_id(user_id)
            if not usuario:
                flash("Usuário não encontrado.", "danger")
                return redirect(url_for('admin.usuarios'))
            
            # Alterar a senha
            if Usuario.change_password(user_id, nova_senha):
                flash("Senha alterada com sucesso.", "success")
                
                # Registrar a ação no log administrativo
                log_admin_action(
                    admin_username,
                    "ALTERAÇÃO DE SENHA",
                    f"Usuário: {usuario['username']}, Nova senha definida pelo administrador"
                )
            else:
                flash("Erro ao alterar a senha.", "danger")
        except ValueError:
            flash("ID de usuário inválido.", "danger")
    
    return redirect(url_for('admin.usuarios'))

@admin_bp.route('/aprovar_solicitacao/<solicitacao_id>', methods=['POST'])
@admin_required
def aprovar_solicitacao(solicitacao_id):
    """Aprovação de solicitação de redefinição de senha"""
    admin_username = session.get('user')
    
    try:
        # Converter para inteiro com tratamento de erro
        solicitacao_id = int(solicitacao_id) if solicitacao_id else 0
    except ValueError:
        flash("ID de solicitação inválido.", "danger")
        return redirect(url_for('admin.usuarios'))
    
    if request.method == 'POST':
        nova_senha = request.form.get('nova_senha')
        
        if not nova_senha:
            flash("Nova senha é obrigatória.", "danger")
            return redirect(url_for('admin.usuarios'))
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Obter a solicitação
                cursor.execute("SELECT * FROM solicitacoes_senha WHERE id = ?", (solicitacao_id,))
                solicitacao = cursor.fetchone()
                
                if not solicitacao:
                    flash("Solicitação não encontrada.", "danger")
                    return redirect(url_for('admin.usuarios'))
                
                # Obter o usuário
                cursor.execute("SELECT * FROM usuarios WHERE username = ?", (solicitacao['username'],))
                usuario = cursor.fetchone()
                
                if not usuario:
                    flash("Usuário não encontrado.", "danger")
                    return redirect(url_for('admin.usuarios'))
                
                # Atualizar a senha
                from werkzeug.security import generate_password_hash
                senha_hash = generate_password_hash(nova_senha)
                cursor.execute("UPDATE usuarios SET password_hash = ? WHERE id = ?", (senha_hash, usuario['id']))
                
                # Atualizar o status da solicitação
                cursor.execute("UPDATE solicitacoes_senha SET status = 'aprovada' WHERE id = ?", (solicitacao_id,))
                
                conn.commit()
                
                flash("Solicitação aprovada e senha redefinida com sucesso.", "success")
                
                # Registrar a ação no log administrativo
                log_admin_action(
                    admin_username,
                    "APROVAÇÃO DE REDEFINIÇÃO DE SENHA",
                    f"Usuário: {usuario['username']}, Solicitação ID: {solicitacao_id}"
                )
                
                return redirect(url_for('admin.usuarios'))
                
        except Exception as e:
            flash(f"Erro ao aprovar solicitação: {e}", "danger")
            return redirect(url_for('admin.usuarios'))
    
    return redirect(url_for('admin.usuarios'))

@admin_bp.route('/rejeitar_solicitacao/<solicitacao_id>')
@admin_required
def rejeitar_solicitacao(solicitacao_id):
    """Rejeição de solicitação de redefinição de senha"""
    try:
        # Converter para inteiro com tratamento de erro
        solicitacao_id = int(solicitacao_id) if solicitacao_id else 0
    except ValueError:
        flash("ID de solicitação inválido.", "danger")
        return redirect(url_for('admin.usuarios'))
    admin_username = session.get('user')
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Obter a solicitação
            cursor.execute("SELECT * FROM solicitacoes_senha WHERE id = ?", (solicitacao_id,))
            solicitacao = cursor.fetchone()
            
            if not solicitacao:
                flash("Solicitação não encontrada.", "danger")
                return redirect(url_for('admin.usuarios'))
            
            # Atualizar o status da solicitação
            cursor.execute("UPDATE solicitacoes_senha SET status = 'rejeitada' WHERE id = ?", (solicitacao_id,))
            
            conn.commit()
            
            flash("Solicitação rejeitada com sucesso.", "success")
            
            # Registrar a ação no log administrativo
            log_admin_action(
                admin_username,
                "REJEIÇÃO DE REDEFINIÇÃO DE SENHA",
                f"Usuário: {solicitacao['username']}, Solicitação ID: {solicitacao_id}"
            )
            
    except Exception as e:
        flash(f"Erro ao rejeitar solicitação: {e}", "danger")
    
    return redirect(url_for('admin.usuarios'))

@admin_bp.route('/excluir_usuario/<user_id>')
@admin_required
def excluir_usuario(user_id):
    """Exclusão de usuários"""
    try:
        # Converter para inteiro com tratamento de erro
        user_id = int(user_id) if user_id else 0
    except ValueError:
        flash("ID de usuário inválido.", "danger")
        return redirect(url_for('admin.usuarios'))
    admin_username = session.get('user')
    
    # Não permitir que o admin exclua a si mesmo
    usuario = Usuario.get_by_id(user_id)
    if not usuario:
        flash("Usuário não encontrado.", "danger")
        return redirect(url_for('admin.usuarios'))
    
    if usuario['username'] == admin_username:
        flash("Você não pode excluir seu próprio usuário.", "danger")
        return redirect(url_for('admin.usuarios'))
    
    # Excluir o usuário
    if Usuario.delete(user_id):
        flash("Usuário excluído com sucesso.", "success")
        
        # Registrar a ação no log administrativo
        log_admin_action(
            admin_username,
            "EXCLUSÃO DE USUÁRIO",
            f"Usuário: {usuario['username']}, Nível: {usuario['nivel']}"
        )
    else:
        flash("Erro ao excluir usuário.", "danger")
    
    return redirect(url_for('admin.usuarios'))

@admin_bp.route('/historico/<int:registro_id>')
@login_required
def historico_registro(registro_id):
    """Visualização do histórico de alterações de um registro"""
    usuario = session.get('user')
    nivel = session.get('nivel')
    
    try:
        # Obter o registro
        registro = Registro.get_by_id(registro_id)
        if not registro:
            flash("Registro não encontrado.", "danger")
            return redirect(url_for('root'))
        
        # Formatar a data de criação do registro
        if 'data_registro' in registro:
            data_criacao = registro['data_registro']
            if isinstance(data_criacao, str):
                registro['data_criacao'] = data_criacao
            else:
                registro['data_criacao'] = data_criacao.strftime('%H:%M:%S %d-%m-%Y') if data_criacao else 'Data desconhecida'
        else:
            registro['data_criacao'] = 'Data desconhecida'
        
        # Adicionar informações de criação ao registro
        registro['usuario_criacao'] = registro.get('usuario', 'Desconhecido')
        
        # Garantir que todos os campos estão no formato esperado
        registro['on_time_cliente'] = registro.get('ON TIME (CLIENTE)', '')
        registro['horario_previsto'] = registro.get('HORÁRIO PREVISTO DE INÍCIO', '')
        
        # Obter o histórico de alterações
        historico = Historico.get_by_registro(registro_id)
        
        # Para cada item do histórico, extrair os campos alterados
        for item in historico:
            alteracoes = item.get('alteracoes', '')
            if isinstance(alteracoes, str):
                item['campos_alterados'] = alteracoes
            else:
                item['campos_alterados'] = ', '.join(alteracoes.keys()) if alteracoes else 'Dados não disponíveis'
            
            # Garantir que a data de alteração está formatada corretamente
            if 'data_alteracao' in item and isinstance(item['data_alteracao'], datetime):
                item['data_alteracao'] = item['data_alteracao'].strftime('%H:%M:%S %d-%m-%Y')
        
        # Preparar as estruturas necessárias para o template
        from operations.excel import excel_processor
        
        # Acessar diretamente os atributos do objeto excel_processor
        COMBOBOX_OPTIONS = excel_processor.COMBOBOX_OPTIONS
        TIPOS_DE_DADOS = excel_processor.TIPOS_DE_DADOS
        CONTAINER_MAP = excel_processor.CONTAINER_MAP
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        return render_template(
            'historico_novo.html',
            registro=registro,
            historico=historico,
            usuario=usuario,
            nivel=nivel,
            campos=COMBOBOX_OPTIONS,
            tipos=TIPOS_DE_DADOS,
            container=CONTAINER_MAP,
            today=today
        )
    except Exception as e:
        import traceback
        print(f"Erro ao carregar histórico: {e}")
        print(traceback.format_exc())
        flash(f"Erro ao carregar histórico: {e}", "danger")
        return redirect(url_for('root'))


@admin_bp.route('/solicitacoes')
@admin_required
def solicitacoes():
    """Página de gerenciamento de solicitações de registro"""
    usuario = session.get('user')
    nivel = session.get('nivel')
    
    # Verificar se o usuário é admin
    if nivel != 'admin':
        flash('Acesso restrito a administradores.', 'danger')
        return redirect(url_for('auth.login'))
    
    # Buscar solicitações pendentes e processadas
    solicitacoes_pendentes = get_solicitacoes_pendentes()
    solicitacoes_processadas = get_solicitacoes_processadas()
    total_pendentes = count_solicitacoes_pendentes()
    
    return render_template(
        'admin_solicitacoes.html',
        usuario=usuario,
        nivel=nivel,
        solicitacoes_pendentes=solicitacoes_pendentes,
        solicitacoes_processadas=solicitacoes_processadas,
        total_pendentes=total_pendentes
    )


@admin_bp.route('/aprovar_solicitacao_registro_route/<int:solicitacao_id>', methods=['POST'])
@admin_required
def aprovar_solicitacao_registro_route(solicitacao_id):
    # Obter dados do formulário
    nivel = request.form.get('nivel')
    senha = request.form.get('senha')
    senha_temporaria = 'senha_temporaria' in request.form
    
    admin_username = session.get('user')
    solicitacao = None
    username = ""
    
    if not nivel or not senha:
        flash('Preencha todos os campos obrigatórios.', 'danger')
        return redirect(url_for('admin.solicitacoes'))
    
    try:
        # Usar conexões separadas para evitar problemas de cache do SQLite
        # Primeira conexão: obter os dados da solicitação
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM solicitacoes_registro WHERE id = ?", (solicitacao_id,))
            solicitacao = cursor.fetchone()
            
            if not solicitacao:
                flash('Solicitação não encontrada.', 'danger')
                return redirect(url_for('admin.solicitacoes'))
            
            username = solicitacao['username']
            email = solicitacao['email']
            
            # Verificar se a solicitação ainda está pendente
            if solicitacao['status'] != 'pendente':
                flash(f"Esta solicitação já foi processada anteriormente com status: {solicitacao['status']}", "warning")
                return redirect(url_for('admin.solicitacoes'))
        
        # Segunda conexão: criar o usuário e atualizar o status
        with get_db_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Importar o método para hash de senha
            from werkzeug.security import generate_password_hash
            
            # Verificar se o usuário já existe
            cursor.execute("SELECT * FROM usuarios WHERE username = ?", (username,))
            usuario_existente = cursor.fetchone()
            if usuario_existente:
                flash(f"Usuário '{username}' já existe no sistema!", "warning")
                return redirect(url_for('admin.solicitacoes'))
            
            # Inserir o usuário
            cursor.execute("""
                INSERT INTO usuarios (username, password_hash, nivel, email, created_at, senha_temporaria)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                username, 
                generate_password_hash(senha), 
                nivel,
                email,
                now,
                1 if senha_temporaria else 0
            ))
            
            # Atualizar a solicitação como aprovada
            cursor.execute("""
                UPDATE solicitacoes_registro 
                SET status = 'aprovada', processado_por = ?, data_processamento = ?
                WHERE id = ? AND status = 'pendente'
            """, (admin_username, now, solicitacao_id))
            
            # Verificar se algum registro foi atualizado
            if cursor.rowcount == 0:
                conn.rollback()
                flash("Não foi possível aprovar a solicitação. Ela pode já ter sido processada por outro administrador.", "warning")
                return redirect(url_for('admin.solicitacoes'))
            
            # Commit da transação
            conn.commit()
        
        # Registrar a ação no log
        log_admin_action(admin_username, "APROVAÇÃO DE USUÁRIO", 
                      f"Usuário '{username}' aprovado com nível '{nivel}' "
                      f"e senha temporária {'ativada' if senha_temporaria else 'desativada'}")
        
        # Limpar cache da sessão
        if 'total_solicitacoes_pendentes' in session:
            session.pop('total_solicitacoes_pendentes')
        
        # Usar o sistema de flash message para mostrar mensagem de sucesso na página redirecionada
        flash(f"Usuário '{username}' aprovado com sucesso!", "success")
        
        # Forçar a atualização completa da página
        response = redirect(url_for('admin.solicitacoes', _refresh=int(time.time())))
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
            
    except Exception as e:
        flash(f"Erro ao aprovar solicitação: {str(e)}", 'danger')
        logging.error(f"Erro ao aprovar solicitação: {e}")
        
    return redirect(url_for('admin.solicitacoes'))

@admin_bp.route('/aprovar_solicitacao_registro/<int:solicitacao_id>', methods=['POST'])
@admin_required
def aprovar_solicitacao_registro(solicitacao_id):
    """Aprovação de solicitação de registro"""
    return aprovar_solicitacao_registro_route(solicitacao_id)


@admin_bp.route('/rejeitar_solicitacao_registro/<int:solicitacao_id>', methods=['POST'])
@admin_required
def rejeitar_solicitacao_registro_route(solicitacao_id):
    """Rejeição de solicitação de registro"""
    return rejeitar_solicitacao_registro(solicitacao_id)
