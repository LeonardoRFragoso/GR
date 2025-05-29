from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
import os
import pandas as pd
from werkzeug.utils import secure_filename
from functools import wraps
import logging
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import requests
from io import BytesIO

app = Flask(__name__)
app.secret_key = 'segredo-super-seguro'

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

logging.basicConfig(filename='access.log', level=logging.INFO, format='%(asctime)s - %(message)s')

DB_PATH = 'usuarios.db'

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS usuarios (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            username TEXT UNIQUE NOT NULL,
                            password_hash TEXT NOT NULL,
                            nivel TEXT DEFAULT 'comum',
                            email TEXT,
                            last_login TEXT,
                            created_at TEXT
                          )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS registros (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            usuario TEXT,
                            placa TEXT,
                            motorista TEXT,
                            cpf TEXT,
                            mot_loc TEXT,
                            carreta TEXT,
                            carreta_loc TEXT,
                            cliente TEXT,
                            loc_cliente TEXT,
                            arquivo TEXT,
                            data_registro TEXT,
                            numero_sm TEXT,
                            numero_ae TEXT,
                            container_1 TEXT,
                            container_2 TEXT,
                            data_sm TEXT,
                            data_ae TEXT,
                            sla_sm TEXT,
                            sla_ae TEXT,
                            status_sm TEXT,
                            tipo_carga TEXT,
                            status_container TEXT,
                            modalidade TEXT,
                            gerenciadora TEXT,
                            booking_di TEXT,
                            pedido_referencia TEXT,
                            lote_cs TEXT,
                            on_time_cliente TEXT,
                            horario_previsto TEXT,
                            observacao_operacional TEXT,
                            observacao_gr TEXT,
                            destino_intermediario TEXT,
                            destino_final TEXT,
                            anexar_nf TEXT,
                            anexar_os TEXT,
                            numero_nf TEXT,
                            serie TEXT,
                            quantidade INTEGER,
                            peso_bruto REAL,
                            valor_total_nota REAL
                          )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS historico (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            registro_id INTEGER,
                            alterado_por TEXT,
                            alteracoes TEXT,
                            data_alteracao TEXT
                          )''')
        conn.commit()

        # Verificar e criar usuários padrão (admin e gr) se não existirem
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Usuário admin (permissão total)
        cursor.execute("SELECT * FROM usuarios WHERE username = ?", ('admin',))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO usuarios (username, password_hash, nivel, created_at) VALUES (?, ?, ?, ?)",
                           ('admin', generate_password_hash('senha123'), 'admin', now))
        
        # Usuário GR (permissão intermediária - pode excluir registros de usuários comuns)
        cursor.execute("SELECT * FROM usuarios WHERE username = ?", ('gr',))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO usuarios (username, password_hash, nivel, created_at) VALUES (?, ?, ?, ?)",
                           ('gr', generate_password_hash('senha123'), 'gr', now))
            
        conn.commit()
        
        # Criar tabela de logs para registrar ações de usuários GR e admin
        cursor.execute('''CREATE TABLE IF NOT EXISTS logs_admin (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            usuario TEXT NOT NULL,
                            acao TEXT NOT NULL,
                            detalhes TEXT,
                            data_hora TEXT NOT NULL
                          )''')
        
        # Criar tabela para solicitações de redefinição de senha
        cursor.execute('''CREATE TABLE IF NOT EXISTS solicitacoes_senha (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            usuario_id INTEGER NOT NULL,
                            username TEXT NOT NULL,
                            data_solicitacao TEXT NOT NULL,
                            status TEXT DEFAULT 'pendente',
                            aprovado_por TEXT,
                            data_aprovacao TEXT,
                            FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
                          )''')

init_db()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get('nivel') != 'admin':
            flash("Acesso restrito a administradores.", "danger")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return wrapper

def admin_or_gr_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get('nivel') not in ['admin', 'gr']:
            flash("Acesso restrito a administradores e GR.", "danger")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return wrapper

def gr_or_admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get('nivel') not in ['gr', 'admin']:
            flash("Acesso restrito a usuários GR ou administradores.", "danger")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return wrapper

def log_admin_action(usuario, acao, detalhes=""):
    """Registra ações realizadas por administradores e GRs para auditoria"""
    # Implementa mecanismo de retry para lidar com banco de dados bloqueado
    max_attempts = 5
    attempt = 0
    while attempt < max_attempts:
        try:
            # Timeout de 5 segundos para operações de banco de dados
            with sqlite3.connect(DB_PATH, timeout=5.0) as conn:
                cursor = conn.cursor()
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("INSERT INTO admin_logs (usuario, acao, detalhes, data) VALUES (?, ?, ?, ?)",
                              (usuario, acao, detalhes, now))
                conn.commit()
            return  # Sucesso, sai da função
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_attempts - 1:
                # Espera um pouco antes de tentar novamente (com tempo crescente)
                import time
                wait_time = 0.1 * (2 ** attempt)  # 0.1s, 0.2s, 0.4s, 0.8s, 1.6s
                time.sleep(wait_time)
                attempt += 1
            else:
                # Se não for erro de bloqueio ou atingiu máximo de tentativas, propaga o erro
                print(f"Erro ao registrar log administrativo após {attempt+1} tentativas: {str(e)}")
                break

@app.route('/admin')
@login_required
@gr_or_admin_required
def admin_dashboard():
    """Painel administrativo para admin e redirecionamento para GR"""
    nivel_usuario = session.get('nivel')
    
    # Redireciona usuários GR para o ambiente GR
    if nivel_usuario == 'gr':
        return redirect(url_for('gr_ambiente'))
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # Estatísticas gerais
        cursor.execute("SELECT COUNT(*) FROM registros")
        total_registros = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT registro_id) FROM historico")
        registros_atualizados = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM usuarios WHERE nivel = 'comum'")
        total_usuarios_comuns = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM usuarios WHERE nivel = 'gr'")
        total_usuarios_gr = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM usuarios WHERE nivel = 'admin'")
        total_usuarios_admin = cursor.fetchone()[0]
        
        # Buscar os últimos logs administrativos
        cursor.execute("SELECT * FROM logs_admin ORDER BY id DESC LIMIT 10")
        logs_recentes = cursor.fetchall()
        colunas_logs = [desc[0] for desc in cursor.description]
        logs_formatados = [dict(zip(colunas_logs, log)) for log in logs_recentes]
        
    return render_template(
        'admin_dashboard.html', 
        usuario=session['user'], 
        nivel=session['nivel'],
        total_registros=total_registros,
        registros_atualizados=registros_atualizados,
        total_usuarios_comuns=total_usuarios_comuns,
        total_usuarios_gr=total_usuarios_gr,
        total_usuarios_admin=total_usuarios_admin,
        logs_recentes=logs_formatados
    )

@app.route('/gr_dashboard')
@login_required
def gr_dashboard():
    """Dashboard específico para usuários do grupo GR"""
    # Verificar se o usuário tem nível GR
    if session['nivel'] != 'gr':
        # Se não for GR, redirecionar para o dashboard apropriado
        if session['nivel'] == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('dashboard'))
            
    # Data atual para cálculos
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Consultas específicas para o dashboard GR
        # Total de registros
        cursor.execute("SELECT COUNT(*) FROM registros")
        total_registros = cursor.fetchone()[0]
        
        # 1. Quantidade de operações sem NF anexada
        cursor.execute("SELECT COUNT(*) FROM registros WHERE anexar_nf IS NULL OR anexar_nf = ''")
        operacoes_sem_nf = cursor.fetchone()[0]
        
        # 2. Quantidade de operações sem OS anexada
        cursor.execute("SELECT COUNT(*) FROM registros WHERE anexar_os IS NULL OR anexar_os = ''")
        operacoes_sem_os = cursor.fetchone()[0]
        
        # 3. Quantidade de operações sem Container 1 preenchido
        cursor.execute("SELECT COUNT(*) FROM registros WHERE container_1 IS NULL OR container_1 = ''")
        operacoes_sem_container1 = cursor.fetchone()[0]
        
        # 4. Quantidade de operações sem SM definida
        cursor.execute("SELECT COUNT(*) FROM registros WHERE numero_sm IS NULL OR numero_sm = ''")
        operacoes_sem_sm = cursor.fetchone()[0]
        
        # Buscar os registros mais recentes para exibição na tabela
        cursor.execute("""
            SELECT * FROM registros ORDER BY id DESC LIMIT 10
        """)
        registros_recentes = [dict(row) for row in cursor.fetchall()]
        
    return render_template(
        'gr_dashboard.html',
        usuario=session['user'],
        nivel=session['nivel'],
        total_registros=total_registros,
        operacoes_sem_nf=operacoes_sem_nf,
        operacoes_sem_os=operacoes_sem_os,
        operacoes_sem_container1=operacoes_sem_container1,
        operacoes_sem_sm=operacoes_sem_sm,
        registros=registros_recentes,
        now=now,
        today=today
    )

@app.route('/gr')
@login_required
@gr_or_admin_required
def gr_ambiente():
    """Ambiente específico para usuários do grupo GR"""
    # Data atual para cálculos
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 1. Registros com SM e AE definidos
        # Observação: Como não temos a coluna 'ultima_alteracao', vamos contar registros com SM e AE definidos
        cursor.execute("""
            SELECT COUNT(*) FROM registros 
            WHERE (numero_sm IS NOT NULL AND numero_sm != '')
            AND (numero_ae IS NOT NULL AND numero_ae != '')
        """)
        alteracoes_pos_sm_ae = cursor.fetchone()[0]
        
        # 2. Registros sem container definido
        cursor.execute("""
            SELECT COUNT(*) FROM registros 
            WHERE (container_1 IS NULL OR container_1 = '')
        """)
        sem_container = cursor.fetchone()[0]
        
        # 3. Registros sem SM definida
        cursor.execute("""
            SELECT COUNT(*) FROM registros 
            WHERE (numero_sm IS NULL OR numero_sm = '')
        """)
        sem_sm = cursor.fetchone()[0]
        
        # 4. Registros sem AE definida
        cursor.execute("""
            SELECT COUNT(*) FROM registros 
            WHERE (numero_ae IS NULL OR numero_ae = '')
        """)
        sem_ae = cursor.fetchone()[0]
        
        # Valores padrão para métricas de tempo caso ocorram erros ou não existam dados
        media_dias_ae = 2.5  # valor médio padrão para demonstração
        media_minutos_ae = media_dias_ae * 24 * 60  # conversão para minutos
        media_dias_sm = 1.8  # valor médio padrão para demonstração
        media_minutos_sm = media_dias_sm * 24 * 60  # conversão para minutos
        media_sla_ae = 0
        media_sla_sm = 0
        
        try:
            # Verificar se as colunas necessárias existem na tabela
            cursor.execute("PRAGMA table_info(registros)")
            colunas = [info[1] for info in cursor.fetchall()]
            
            # Usaremos SEMPRE os cálculos reais agora que sabemos que as colunas existem
            # e foram populadas com dados de exemplo
            usar_calculo_real = True
            
            if True:  # Sempre executar este bloco
                # 5 & 7. Dados AE (duração média)
                cursor.execute("""
                    SELECT AVG(JULIANDAY(data_ae) - JULIANDAY(data_registro)) as media_dias_ae
                    FROM registros
                    WHERE data_ae IS NOT NULL AND data_ae != '' AND data_registro IS NOT NULL
                """)
                result = cursor.fetchone()
                if result[0] is not None:
                    media_dias_ae = result[0]
                    media_minutos_ae = media_dias_ae * 24 * 60  # conversão para minutos
                
                # 6 & 8. Dados SM (duração média)
                cursor.execute("""
                    SELECT AVG(JULIANDAY(data_sm) - JULIANDAY(data_registro)) as media_dias_sm
                    FROM registros
                    WHERE data_sm IS NOT NULL AND data_sm != '' AND data_registro IS NOT NULL
                """)
                result = cursor.fetchone()
                if result[0] is not None:
                    media_dias_sm = result[0]
                    media_minutos_sm = media_dias_sm * 24 * 60  # conversão para minutos
                
                # Calculando as médias de SLA_AE e SLA_SM
                cursor.execute("""
                    SELECT 
                        AVG(CASE WHEN sla_ae IS NOT NULL AND sla_ae != '' THEN CAST(sla_ae AS REAL) ELSE NULL END) as media_sla_ae,
                        AVG(CASE WHEN sla_sm IS NOT NULL AND sla_sm != '' THEN CAST(sla_sm AS REAL) ELSE NULL END) as media_sla_sm
                    FROM registros
                """)
                result = cursor.fetchone()
                media_sla_ae = result[0] if result[0] is not None else 0
                media_sla_sm = result[1] if result[1] is not None else 0
        except Exception as e:
            # Se ocorrer algum erro, usamos os valores padrão e registramos o erro
            print(f"Erro ao calcular métricas: {e}")
        
        # Conversão para formato HH:MM:SS conforme solicitado
        # Converter dias para segundos
        segundos_ae = media_dias_ae * 24 * 60 * 60  # dias para segundos
        segundos_sm = media_dias_sm * 24 * 60 * 60  # dias para segundos
        
        # Calcular horas, minutos e segundos
        def segundos_para_hhmmss(segundos):
            horas = int(segundos // 3600)
            minutos = int((segundos % 3600) // 60)
            segs = int(segundos % 60)
            return f"{horas:02d}:{minutos:02d}:{segs:02d}"
        
        tempo_medio_ae = segundos_para_hhmmss(segundos_ae)
        tempo_medio_ae_minutos = int(media_minutos_ae)
        tempo_medio_sm = segundos_para_hhmmss(segundos_sm)
        tempo_medio_sm_minutos = int(media_minutos_sm)
        
        # Dados para a tabela de registros - simplificando a consulta para evitar JOINs que podem causar erro
        cursor.execute("""
            SELECT * 
            FROM registros
            ORDER BY id DESC
            LIMIT 20
        """)
        registros = [dict(row) for row in cursor.fetchall()]
    
    return render_template(
        'gr_ambiente.html',
        usuario=session['user'],
        nivel=session['nivel'],
        alteracoes_pos_sm_ae=alteracoes_pos_sm_ae,
        sem_container=sem_container,
        sem_sm=sem_sm,
        sem_ae=sem_ae,
        tempo_medio_ae=tempo_medio_ae,
        tempo_medio_ae_minutos=tempo_medio_ae_minutos,
        tempo_medio_sm=tempo_medio_sm,
        tempo_medio_sm_minutos=tempo_medio_sm_minutos,
        media_sla_ae=media_sla_ae,
        media_sla_sm=media_sla_sm,
        registros=registros,
        now=now,
        today=today
    )

@app.route('/admin/usuarios')
@login_required
@gr_or_admin_required
def admin_usuarios():
    # Buscar solicitações de redefinição de senha pendentes
    solicitacoes_pendentes = []
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, usuario_id, username, data_solicitacao FROM solicitacoes_senha WHERE status = 'pendente'")
        solicitacoes_pendentes = cursor.fetchall()
    """Gestão de usuários - somente para administradores"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios ORDER BY id")
        usuarios = cursor.fetchall()
        colunas = [desc[0] for desc in cursor.description]
        usuarios_formatados = [dict(zip(colunas, usuario)) for usuario in usuarios]

    return render_template('admin_usuarios.html', 
                          usuarios=usuarios_formatados, 
                          usuario=session['user'], 
                          nivel=session['nivel'],
                          solicitacoes=solicitacoes_pendentes)

@app.route('/admin/logs')
@login_required
@gr_or_admin_required
def admin_logs():
    # Verificar se há solicitações de redefinição de senha pendentes (apenas para admins)
    solicitacoes_pendentes = []
    if session.get('nivel') == 'admin':
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, data_solicitacao FROM solicitacoes_senha WHERE status = 'pendente'")
            solicitacoes_pendentes = cursor.fetchall()
            
            # Se houver solicitações pendentes, mostrar alerta
            if solicitacoes_pendentes:
                flash(f"Há {len(solicitacoes_pendentes)} solicitação(ões) de redefinição de senha pendente(s).", "warning")
    """Visualização de logs administrativos para GR e admin"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # Contar total de logs para paginação
        cursor.execute("SELECT COUNT(*) FROM logs_admin")
        total_logs = cursor.fetchone()[0]
        
        # Buscar logs com paginação
        cursor.execute("SELECT * FROM logs_admin ORDER BY id DESC LIMIT ? OFFSET ?", (per_page, offset))
        logs = cursor.fetchall()
        colunas = [desc[0] for desc in cursor.description]
        logs_formatados = [dict(zip(colunas, log)) for log in logs]
        
    total_pages = (total_logs + per_page - 1) // per_page
    return render_template(
        'admin_logs.html', 
        logs=logs_formatados,
        usuario=session['user'], 
        nivel=session['nivel'],
        page=page,
        total_pages=total_pages
    )

@app.route('/admin/usuarios/editar/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def editar_usuario(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # Buscar o usuário a ser editado
        cursor.execute("SELECT id, username, nivel FROM usuarios WHERE id = ?", (user_id,))
        usuario_db = cursor.fetchone()
        
        if not usuario_db:
            flash("Usuário não encontrado.", "danger")
            return redirect(url_for('admin_usuarios'))
        
        usuario_id, usuario_nome, nivel_atual = usuario_db
        
        if request.method == 'POST':
            nivel = request.form['nivel']
            # Validar o nível
            if nivel not in ['comum', 'gr', 'admin']:
                flash("Nível de usuário inválido.", "danger")
                return redirect(url_for('admin_usuarios'))
                
            cursor.execute("UPDATE usuarios SET nivel = ? WHERE id = ?", (nivel, user_id))
            conn.commit()
            
            # Registrar a alteração no log administrativo
            admin_usuario = session.get('user')
            log_admin_action(admin_usuario, "ALTERAÇÃO DE NÍVEL DE USUÁRIO", 
                          f"Usuário: {usuario_nome}, Nível anterior: {nivel_atual}, Novo nível: {nivel}")
            
            flash(f"Nível do usuário {usuario_nome} alterado para {nivel}.", "success")
            return redirect(url_for('admin_usuarios'))
        
        # Método GET com parâmetro na URL
        nivel = request.args.get('nivel')
        if nivel:
            # Validar o nível
            if nivel not in ['comum', 'gr', 'admin']:
                flash("Nível de usuário inválido.", "danger")
                return redirect(url_for('admin_usuarios'))
                
            # Não permitir que um admin remova seus próprios privilégios
            usuario_logado = session.get('user')
            if usuario_nome == usuario_logado and nivel != 'admin':
                flash("Você não pode remover seus próprios privilégios de administrador.", "danger")
                return redirect(url_for('admin_usuarios'))
                
            cursor.execute("UPDATE usuarios SET nivel = ? WHERE id = ?", (nivel, user_id))
            conn.commit()
            
            # Registrar a alteração no log administrativo
            admin_usuario = session.get('user')
            log_admin_action(admin_usuario, "ALTERAÇÃO DE NÍVEL DE USUÁRIO", 
                          f"Usuário: {usuario_nome}, Nível anterior: {nivel_atual}, Novo nível: {nivel}")
            
            flash(f"Nível do usuário {usuario_nome} alterado para {nivel}.", "success")
            return redirect(url_for('admin_usuarios'))
            
        # Se não tem parâmetro na URL, exibir a página de edição
        usuario = {
            'id': usuario_id,
            'username': usuario_nome,
            'nivel': nivel_atual
        }
        
    return render_template('admin_editar_usuario.html', usuario=usuario)

@app.route('/criar_usuario', methods=['POST'])
@admin_required
def criar_usuario():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        nivel = request.form.get('nivel')
        
        # Validações básicas
        if not username or not password or not nivel:
            flash("Todos os campos são obrigatórios.", "danger")
            return redirect(url_for('admin_usuarios'))
        
        # Verificar se o usuário já existe
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM usuarios WHERE username = ?", (username,))
            if cursor.fetchone():
                flash(f"Usuário '{username}' já existe!", "danger")
                return redirect(url_for('admin_usuarios'))
                
            # Criar novo usuário
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("INSERT INTO usuarios (username, password_hash, nivel, created_at) VALUES (?, ?, ?, ?)",
                           (username, generate_password_hash(password), nivel, now))
            conn.commit()
            
            # Registrar a ação no log
            log_admin_action(session['user'], "CRIAÇÃO DE USUÁRIO", 
                          f"Novo usuário: {username}, Nível: {nivel}")
            
            flash(f"Usuário '{username}' criado com sucesso!", "success")
            return redirect(url_for('admin_usuarios'))

@app.route('/alterar_senha', methods=['POST'])
@admin_required
def alterar_senha():
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        nova_senha = request.form.get('nova_senha')
        
        # Validações básicas
        if not user_id or not nova_senha:
            flash("Todos os campos são obrigatórios.", "danger")
            return redirect(url_for('admin_usuarios'))
        
        # Alterar a senha do usuário
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM usuarios WHERE id = ?", (user_id,))
            usuario_alvo = cursor.fetchone()
            
            if not usuario_alvo:
                flash("Usuário não encontrado.", "danger")
                return redirect(url_for('admin_usuarios'))
                
            # Atualizar a senha
            cursor.execute("UPDATE usuarios SET password_hash = ? WHERE id = ?", 
                          (generate_password_hash(nova_senha), user_id))
            conn.commit()
            
            # Registrar a ação no log
            log_admin_action(session['user'], "ALTERAÇÃO DE SENHA", 
                          f"Usuário: {usuario_alvo[0]}, ID: {user_id}")
            
            flash(f"Senha do usuário '{usuario_alvo[0]}' alterada com sucesso!", "success")
            return redirect(url_for('admin_usuarios'))

@app.route('/admin/usuarios/deletar/<int:user_id>')
@login_required
@admin_required
def deletar_usuario(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM usuarios WHERE id = ?", (user_id,))
        conn.commit()
    flash("Usuário removido com sucesso", "success")
    return redirect(url_for('admin_usuarios'))

# Esta rota foi removida pois duplicava a função admin_logs()

@app.route('/historico/<int:registro_id>')
@login_required
def historico_registro(registro_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Buscar os dados do registro
        cursor.execute("SELECT * FROM registros WHERE id = ?", (registro_id,))
        registro = cursor.fetchone()
        
        if not registro:
            flash("Registro não encontrado.", "danger")
            return redirect(url_for('dashboard'))
        
        # Buscar o histórico de alterações
        cursor.execute("""SELECT h.id, h.registro_id, h.alterado_por as usuario, 
                           h.alteracoes as descricao_alteracao, h.data_alteracao 
                        FROM historico h 
                        WHERE h.registro_id = ? 
                        ORDER BY h.id DESC""", (registro_id,))
        historico = [dict(row) for row in cursor.fetchall()]
        
        # Adicionar informações de criação ao registro
        registro = dict(registro)
        registro['usuario_criacao'] = registro.get('usuario', 'Desconhecido')
        registro['data_criacao'] = registro.get('data_registro', 'Data desconhecida')
        registro['status'] = registro.get('status', 'Pendente')
        
        # Para cada item do histórico, extrair os campos alterados
        for item in historico:
            alteracoes = item.get('descricao_alteracao', '')
            item['campos_alterados'] = ', '.join([campo.strip() for campo in alteracoes.split(',')]) if alteracoes else 'Dados não disponíveis'
        
        # Mapear os campos do banco para os nomes correspondentes no template
        campo_mapping = {
            # Campos originais
            'placa': 'CAVALO 1',
            'motorista': 'MOTORISTA',
            'cpf': 'CPF MOTORISTA',
            'mot_loc': 'UNIDADE',
            'carreta': 'CARRETA 1',
            'carreta_loc': 'Requisitante',
            'cliente': 'CLIENTE',
            'loc_cliente': 'ORIGEM',
            
            # Novos campos adicionados
            'carreta_2': 'CARRETA 2',
            'tipo_de_carga': 'TIPO DE CARGA',
            'lote_cs': 'LOTE CS',
            'container_1': 'CONTAINER 1',
            'container_2': 'CONTAINER 2',
            'status_container': 'STATUS CONTAINER',
            'modalidade': 'MODALIDADE',
            'horario_previsto': 'HORÁRIO PREVISTO DE INÍCIO',
            'on_time_cliente': 'ON TIME CLIENTE',
            'numero_sm': 'NÚMERO SM',
            'numero_ae': 'NÚMERO AE',
            'booking_di': 'BOOKING / DI',
            'gerenciadora': 'GERENCIADORA',
            'observacao_operacional': 'Observação Operacional',
            'observacao_gr': 'Observação de Gestão de Risco',
            
            # Dados do Cliente
            'pedido_referencia': 'PEDIDO/REFERÊNCIA',
            'destino_intermediario': 'DESTINO INTERMEDIÁRIO',
            'destino_final': 'DESTINO FINAL',
            
            # Documentos
            'numero_nf': 'Nº NF',
            'serie': 'SÉRIE',
            'quantidade': 'QUANTIDADE',
            'peso_bruto': 'PESO BRUTO',
            'valor_total_nota': 'VALOR TOTAL DA NOTA',
            'anexar_nf': 'ANEXAR NF',
            'anexar_os': 'ANEXAR OS'
        }
        
        # Criar uma cópia expandida do registro com nomes de campos completos
        registro_completo = {}
        # Primeiro vamos preencher todos os campos com seus valores originais
        for campo, valor in registro.items():
            registro_completo[campo] = valor
        
        # Agora mapeamos para os nomes usados no template
        for campo, valor in registro.items():
            if campo in campo_mapping:
                registro_completo[campo_mapping[campo]] = valor
                
        # Garantir explicitamente que o campo Requisitante esteja presente
        if 'carreta_loc' in registro:
            registro_completo['Requisitante'] = registro['carreta_loc']
    
    # Obter a data atual para comparações
    today = datetime.now().strftime("%Y-%m-%d")
    
    return render_template('historico_novo.html', 
                           historico=historico, 
                           registro=registro_completo, 
                           registro_id=registro_id,
                           campos=COMBOBOX_OPTIONS,
                           tipos=TIPOS_DE_DADOS,
                           container=CONTAINER_MAP,
                           nivel=session.get('nivel', 'comum'),
                           today=today)

@app.route('/solicitar_senha', methods=['GET', 'POST'])
def solicitar_senha():
    """Permite que usuários solicitem redefinição de senha"""
    if request.method == 'POST':
        username = request.form.get('username')
        
        if not username:
            flash("Por favor, informe seu nome de usuário.", "danger")
            return render_template('solicitar_senha.html')
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # Verificar se o usuário existe
            cursor.execute("SELECT id FROM usuarios WHERE username = ?", (username,))
            usuario = cursor.fetchone()
            
            if not usuario:
                flash(f"Usuário '{username}' não encontrado.", "danger")
                return render_template('solicitar_senha.html')
            
            usuario_id = usuario[0]
            
            # Verificar se já existe uma solicitação pendente para este usuário
            cursor.execute("SELECT id FROM solicitacoes_senha WHERE usuario_id = ? AND status = 'pendente'", (usuario_id,))
            if cursor.fetchone():
                flash("Você já possui uma solicitação de redefinição de senha pendente. Aguarde aprovação pelo administrador.", "warning")
                return render_template('solicitar_senha.html')
            
            # Criar nova solicitação
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("INSERT INTO solicitacoes_senha (usuario_id, username, data_solicitacao) VALUES (?, ?, ?)",
                          (usuario_id, username, now))
            conn.commit()
            
            flash("Sua solicitação de redefinição de senha foi enviada com sucesso! Um administrador irá avaliar seu pedido em breve.", "success")
            return redirect(url_for('login'))
    
    return render_template('solicitar_senha.html')

@app.route('/aprovar_senha/<int:solicitacao_id>', methods=['POST'])
@admin_required
def aprovar_senha(solicitacao_id):
    """Permite que administradores aprovem solicitações de redefinição de senha"""
    nova_senha = request.form.get('nova_senha')
    
    if not nova_senha:
        flash("Por favor, defina uma nova senha.", "danger")
        return redirect(url_for('admin_usuarios'))
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # Verificar se a solicitação existe e está pendente
        cursor.execute("SELECT usuario_id, username FROM solicitacoes_senha WHERE id = ? AND status = 'pendente'", (solicitacao_id,))
        solicitacao = cursor.fetchone()
        
        if not solicitacao:
            flash("Solicitação não encontrada ou já processada.", "danger")
            return redirect(url_for('admin_usuarios'))
        
        usuario_id, username = solicitacao
        
        # Atualizar a senha do usuário
        cursor.execute("UPDATE usuarios SET password_hash = ? WHERE id = ?",
                      (generate_password_hash(nova_senha), usuario_id))
        
        # Atualizar o status da solicitação
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE solicitacoes_senha SET status = 'aprovada', aprovado_por = ?, data_aprovacao = ? WHERE id = ?",
                      (session['user'], now, solicitacao_id))
        conn.commit()
        
        # Registrar a ação no log
        log_admin_action(session['user'], "APROVAÇÃO DE REDEFINIÇÃO DE SENHA", 
                      f"Usuário: {username}, ID: {usuario_id}")
        
        flash(f"Senha do usuário '{username}' redefinida com sucesso!", "success")
        return redirect(url_for('admin_usuarios'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO usuarios (username, password_hash) VALUES (?, ?)",
                               (username, generate_password_hash(password)))
                conn.commit()
                flash("Usuário registrado com sucesso!", "success")
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash("Nome de usuário já existe.", "danger")
    return render_template('register.html')

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        username = request.form['username']
        new_password = request.form['new_password']
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM usuarios WHERE username = ?", (username,))
            if cursor.fetchone():
                cursor.execute("UPDATE usuarios SET password_hash = ? WHERE username = ?",
                               (generate_password_hash(new_password), username))
                conn.commit()
                flash("Senha redefinida com sucesso.", "success")
                return redirect(url_for('login'))
            else:
                flash("Usuário não encontrado.", "danger")
    return render_template('reset_password.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        login_type = request.form.get('login_type', 'user')  # Tipo de login (user ou admin)
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT password_hash, nivel FROM usuarios WHERE username = ?", (username,))
            result = cursor.fetchone()
            
            if result and check_password_hash(result[0], password):
                nivel = result[1]
                session['user'] = username
                session['nivel'] = nivel
                
                # Registrar login no histórico
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("UPDATE usuarios SET last_login = ? WHERE username = ?", (now, username))
                conn.commit()
                
                logging.info(f'Login realizado: {username} (nivel: {nivel})')
                
                # Se o login foi na área administrativa e o usuário tem permissão (gr ou admin)
                if login_type == 'admin':
                    if nivel == 'admin':
                        # Registrar acesso administrativo no log
                        log_admin_action(username, "LOGIN ADMINISTRATIVO", "Acesso ao painel administrativo")
                        return redirect(url_for('admin_dashboard'))
                    elif nivel == 'gr':
                        # Registrar acesso administrativo no log
                        log_admin_action(username, "LOGIN GR", "Acesso ao ambiente GR")
                        return redirect(url_for('gr_ambiente'))
                    else:
                        # Usuário sem permissão tentando acessar área administrativa
                        flash('Você não tem permissão para acessar o painel administrativo', 'danger')
                        return redirect(url_for('login'))
                else:
                    # Redirecionamento baseado no nível do usuário
                    if nivel == 'gr':
                        return redirect(url_for('gr_ambiente'))
                    elif nivel == 'admin':
                        return redirect(url_for('admin_dashboard'))
                    else:
                        # Login de usuário comum - redireciona para o dashboard normal
                        return redirect(url_for('dashboard'))
            else:
                # Mensagem de erro genérica para não revelar quais usuários existem
                flash('Credenciais inválidas', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    user = session.pop('user', None)
    session.pop('nivel', None)
    if user:
        logging.info(f'Logout realizado: {user}')
    return redirect(url_for('login'))

ONEDRIVE_URL = "https://ictsi-my.sharepoint.com/:x:/p/leonardo_fragoso_itracker/EV8B0yiu9txKjo3I45WIYXkBK9u7ye7q9YF7bMb1E81fOA?download=1"

try:
    response = requests.get(ONEDRIVE_URL, timeout=10)
    response.raise_for_status()
    
    # Carregar as abas do Excel
    excel_file = pd.ExcelFile(BytesIO(response.content))
    
    # Listar todas as abas disponíveis (para debug)
    sheet_names = excel_file.sheet_names
    print(f"Abas disponíveis no Excel: {sheet_names}")
    
    # Carregar a aba principal
    df = excel_file.parse('Página1')
    df.columns = df.columns.astype(str).str.strip()
    
    # Carregar a aba PLACAS
    df_placas = None
    try:
        # Tentar diferentes possíveis nomes para a aba PLACAS
        if 'PLACAS' in sheet_names:
            df_placas = excel_file.parse('PLACAS')
        elif 'Placas' in sheet_names:
            df_placas = excel_file.parse('Placas')
        elif 'placas' in sheet_names:
            df_placas = excel_file.parse('placas')
        else:
            # Se não encontrar uma aba com nome exato, procurar por nomes similares
            for sheet in sheet_names:
                if 'placa' in sheet.lower():
                    df_placas = excel_file.parse(sheet)
                    break
        
        if df_placas is not None:
            df_placas.columns = df_placas.columns.astype(str).str.strip()
            print(f"Colunas na aba PLACAS: {df_placas.columns.tolist()}")
    except Exception as e:
        print(f"Erro ao carregar aba PLACAS: {e}")
        df_placas = None

    # Renomear coluna FOCAL para Requisitante se existir
    if 'FOCAL' in df.columns:
        df.rename(columns={'FOCAL': 'Requisitante'}, inplace=True)

    # Novos campos obrigatórios conforme solicitado
    CAMPOS_OBRIGATORIOS = {
        # Dados da unidade
        "UNIDADE",
        # Dados do cliente
        "CLIENTE", "MODALIDADE", "BOOKING / DI", "STATUS CONTAINER", "ORIGEM", "DESTINO FINAL",
        # Dados da operação
        "MOTORISTA", "CPF MOTORISTA", "CAVALO 1", "CARRETA 1", "TIPO DE CARGA", 
        "ON TIME (CLIENTE)", "HORÁRIO PREVISTO DE INÍCIO",
        # Dados de GR
        "GERENCIADORA"
    }

    TIPOS_DE_DADOS = {
        "UNIDADE": "STR", "Requisitante": "STR", "MOTORISTA": "STR", "CPF MOTORISTA": "STR",
        "CAVALO 1": "STR", "CARRETA 1": "STR", "CARRETA 2": "STR", "PEDIDO/REFERÊNCIA": "STR",
        "TIPO DE CARGA": "STR", "LOTE CS": "STR", "CONTAINER 1": "STR", "CONTAINER 2": "STR",
        "STATUS CONTAINER": "STR", "MODALIDADE": "STR", "CLIENTE": "STR", "ORIGEM": "STR",
        "DESTINO INTERMEDIÁRIO": "STR", "DESTINO FINAL": "STR", "HORÁRIO PREVISTO DE INÍCIO": "DT/HORA",
        "ON TIME (CLIENTE)": "STR", "Nº NF": "STR", "SÉRIE": "STR", "QUANTIDADE": "INT",
        "PESO BRUTO": "FLOAT", "VALOR TOTAL DA NOTA": "MOEDA", "ANEXAR NF": "FILE", "ANEXAR OS": "FILE",
        "NUMERO SM": "STR", "NÚMERO AE": "STR", "BOOKING / DI": "STR",
        "GERENCIADORA": "STR", "OBSERVACAO OPERACIONAL": "STR", "DATA": "DT/HORA", "STATUS SM": "STR",
        "DT CRIACAO SM": "DT/HORA", "DT CRIACAO AE": "DT/HORA",
        "OBSERVAÇÃO DE GR": "STR", "SLA SM": "DURAÇÃO", "SLA AE": "DURAÇÃO"
    }

    CONTAINER_MAP = {
        # Dados da unidade
        "UNIDADE": "dados da unidade", 
        "Requisitante": "dados da unidade", 
        # DATA removido do frontend conforme solicitado
        
        # Dados do cliente
        "CLIENTE": "dados do cliente",
        "MODALIDADE": "dados do cliente",
        "PEDIDO/REFERÊNCIA": "dados do cliente",
        "BOOKING / DI": "dados do cliente",
        "CONTAINER 1": "dados do cliente", 
        "CONTAINER 2": "dados do cliente", 
        "LOTE CS": "dados do cliente",
        "STATUS CONTAINER": "dados do cliente",
        "ORIGEM": "dados do cliente", 
        "DESTINO INTERMEDIÁRIO": "dados do cliente",
        "DESTINO FINAL": "dados do cliente",

        # Dados da operação
        "MOTORISTA": "dados da operação",
        "CPF MOTORISTA": "dados da operação", 
        "CAVALO 1": "dados da operação", 
        "CARRETA 1": "dados da operação",
        "CARRETA 2": "dados da operação", 
        "TIPO DE CARGA": "dados da operação",
        "ON TIME (CLIENTE)": "dados da operação", 
        "HORÁRIO PREVISTO DE INÍCIO": "dados da operação",
        "OBSERVACAO OPERACIONAL": "dados da operação",
        
        # Dados de GR
        "GERENCIADORA": "dados de gr",
        "NÚMERO AE": "dados de gr",
        "DT CRIACAO AE": "dados de gr",
        "NUMERO SM": "dados de gr", 
        "DT CRIACAO SM": "dados de gr",
        "STATUS SM": "dados de gr",
        "OBSERVAÇÃO DE GR": "dados de gr",
        "SLA SM": "dados de gr", 
        "SLA AE": "dados de gr",

        # Documentos (mantidos por completude, mesmo que não exibidos no formulário)
        "Nº NF": "documentos", "SÉRIE": "documentos", "QUANTIDADE": "documentos",
        "PESO BRUTO": "documentos", "VALOR TOTAL DA NOTA": "documentos",
        "ANEXAR NF": "documentos", "ANEXAR OS": "documentos"
    }

    CAMPOS_FORM = list(CONTAINER_MAP.keys())

    # Garantir que o campo Requisitante esteja nos campos do formulário
    if 'Requisitante' not in CAMPOS_FORM:
        CAMPOS_FORM.append('Requisitante')

    # Lista de campos que devem ser digitáveis (não dropdowns)
    CAMPOS_DIGITAVEIS = [
        "CLIENTE", "PEDIDO/REFERÊNCIA", "BOOKING / DI", "CONTAINER 1", "CONTAINER 2", 
        "LOTE CS", "ORIGEM", "DESTINO INTERMEDIÁRIO", "DESTINO FINAL", "ON TIME (CLIENTE)", 
        "HORÁRIO PREVISTO DE INÍCIO", "OBSERVACAO OPERACIONAL", "NÚMERO AE", 
        "DT CRIACAO AE", "NUMERO SM", "DT CRIACAO SM", "OBSERVAÇÃO DE GR"
    ]

    # Criar opções de dropdown para campos que não estão na lista de digitáveis
    COMBOBOX_OPTIONS = {}
    for campo in CAMPOS_FORM:
        if campo not in CAMPOS_DIGITAVEIS and campo in df.columns:
            COMBOBOX_OPTIONS[campo] = sorted(df[campo].dropna().astype(str).str.strip().unique().tolist())
        else:
            # Para campos digitáveis, definimos uma lista vazia para indicar que não são dropdowns
            COMBOBOX_OPTIONS[campo] = []
    
    # Adicionar manualmente o campo Requisitante nas opções se não estiver presente
    if 'Requisitante' not in COMBOBOX_OPTIONS:
        COMBOBOX_OPTIONS['Requisitante'] = []
        # Adicionar ou garantir que Requisitante está no CONTAINER_MAP
        if 'Requisitante' not in CONTAINER_MAP:
            CONTAINER_MAP['Requisitante'] = 'dados da unidade'
            
    # Adicionar CST à lista de MODALIDADE se não existir
    if 'MODALIDADE' in COMBOBOX_OPTIONS and 'CST' not in COMBOBOX_OPTIONS['MODALIDADE']:
        COMBOBOX_OPTIONS['MODALIDADE'].append('CST')
        COMBOBOX_OPTIONS['MODALIDADE'] = sorted(COMBOBOX_OPTIONS['MODALIDADE'])
        
    # Adicionar campo para Anexar Agendamento
    if 'Anexar Agendamento' not in COMBOBOX_OPTIONS:
        COMBOBOX_OPTIONS['Anexar Agendamento'] = []
    
    if 'Anexar Agendamento' not in CONTAINER_MAP:
        CONTAINER_MAP['Anexar Agendamento'] = 'documentos'
        
    if 'Anexar Agendamento' not in TIPOS_DE_DADOS:
        TIPOS_DE_DADOS['Anexar Agendamento'] = 'FILE'

    # Definir campos digitáveis (não são dropdowns)
    campos_digitaveis = ['CLIENTE', 'PEDIDO/REFERÊNCIA', 'BOOKING / DI', 'CONTAINER 1', 'CONTAINER 2', 
                      'LOTE CS', 'ORIGEM', 'DESTINO INTERMEDIÁRIO', 'DESTINO FINAL', 'ON TIME (CLIENTE)', 
                      'HORÁRIO PREVISTO DE INÍCIO', 'OBSERVACAO OPERACIONAL', 'NÚMERO AE', 
                      'DT CRIACAO AE', 'NUMERO SM', 'DT CRIACAO SM', 'OBSERVAÇÃO DE GR']
    
    # Remover esses campos do COMBOBOX_OPTIONS para que não sejam exibidos como dropdowns
    for campo in campos_digitaveis:
        if campo in COMBOBOX_OPTIONS:
            COMBOBOX_OPTIONS.pop(campo)
    
    # Atualizar os dropdowns de Motorista, Cavalo e Carretas usando a aba PLACAS se disponível
    if df_placas is not None:
        print("Usando dados da aba PLACAS para popular dropdowns")
        
        # Mapear as colunas necessárias da aba PLACAS
        placa_col = None
        motorista_col = None
        carreta_col = None
        cpf_col = None
        
        # Imprimir todas as colunas para debug
        print(f"Todas as colunas na aba PLACAS: {df_placas.columns.tolist()}")
        
        # Baseado na imagem da planilha, vamos usar os nomes exatos das colunas
        # A imagem mostra que temos colunas como "PLACA", "MOTORISTA", etc.
        placa_col = None
        motorista_col = None
        carreta_col = None
        cpf_col = None
        
        # Procurar as colunas pela correspondência exata ou parcial
        for col in df_placas.columns:
            if isinstance(col, str):
                col_upper = col.upper()
                # Procurar a coluna da placa (para Cavalo)
                if col_upper == 'PLACA':
                    placa_col = col
                    print(f"Coluna para CAVALO encontrada: {col}")
                # Procurar a coluna do motorista
                elif col_upper == 'MOTORISTA':
                    motorista_col = col
                    print(f"Coluna para MOTORISTA encontrada: {col}")
                # Procurar a coluna da carreta
                elif col_upper == 'CARRETA':
                    carreta_col = col
                    print(f"Coluna para CARRETA encontrada: {col}")
                # Procurar a coluna do CPF do motorista
                elif col_upper == 'CPF MOTORISTA' or col_upper == 'CPF':
                    cpf_col = col
                    print(f"Coluna para CPF MOTORISTA encontrada: {col}")
        
        # Verificar se todas as colunas foram encontradas
        colunas_necessarias = [placa_col, motorista_col, carreta_col]
        if None in colunas_necessarias:
            colunas_faltantes = []
            if placa_col is None: colunas_faltantes.append("PLACA")
            if motorista_col is None: colunas_faltantes.append("MOTORISTA")
            if carreta_col is None: colunas_faltantes.append("CARRETA")
            print(f"ATENÇÃO: As seguintes colunas não foram encontradas na aba PLACAS: {colunas_faltantes}")
            print("Tentando usar correspondência parcial para encontrar as colunas...")
            
            # Tentar encontrar colunas por correspondência parcial se não encontradas exatamente
            if placa_col is None:
                for col in df_placas.columns:
                    if isinstance(col, str) and 'PLACA' in col.upper():
                        placa_col = col
                        print(f"Coluna para CAVALO encontrada por correspondência parcial: {col}")
                        break
                        
            if motorista_col is None:
                for col in df_placas.columns:
                    if isinstance(col, str) and 'MOTORISTA' in col.upper():
                        motorista_col = col
                        print(f"Coluna para MOTORISTA encontrada por correspondência parcial: {col}")
                        break
                        
            if carreta_col is None:
                for col in df_placas.columns:
                    if isinstance(col, str) and 'CARRETA' in col.upper():
                        carreta_col = col
                        print(f"Coluna para CARRETA encontrada por correspondência parcial: {col}")
                        break
                        
            if cpf_col is None:
                for col in df_placas.columns:
                    if isinstance(col, str) and 'CPF' in col.upper():
                        cpf_col = col
                        print(f"Coluna para CPF MOTORISTA encontrada por correspondência parcial: {col}")
                        break
        
        # Usar coluna PLACA para o dropdown de Cavalo
        if placa_col is not None:
            cavalos = df_placas[placa_col].dropna().astype(str).str.strip().unique().tolist()
            COMBOBOX_OPTIONS['CAVALO 1'] = sorted(cavalos)
            print(f"Populado CAVALO 1 com {len(cavalos)} valores")
        
        # Usar coluna MOTORISTA para o dropdown de Motorista
        if motorista_col is not None:
            motoristas = df_placas[motorista_col].dropna().astype(str).str.strip().unique().tolist()
            COMBOBOX_OPTIONS['MOTORISTA'] = sorted(motoristas)
            print(f"Populado MOTORISTA com {len(motoristas)} valores")
        
        # Usar coluna CARRETA para os dropdowns de Carreta 1 e Carreta 2
        if carreta_col is not None:
            carretas = df_placas[carreta_col].dropna().astype(str).str.strip().unique().tolist()
            COMBOBOX_OPTIONS['CARRETA 1'] = sorted(carretas)
            COMBOBOX_OPTIONS['CARRETA 2'] = sorted(carretas)
            print(f"Populado CARRETA 1 e 2 com {len(carretas)} valores")
            
        # Criar mapeamento de MOTORISTA para CPF MOTORISTA da aba PLACAS
        if motorista_col is not None and cpf_col is not None:
            MOTORISTA_CPF_MAP = df_placas.set_index(motorista_col)[cpf_col].fillna('').to_dict()
            print(f"Criado mapeamento de MOTORISTA para CPF com {len(MOTORISTA_CPF_MAP)} entradas")
        else:
            MOTORISTA_CPF_MAP = {}
            print("Não foi possível criar mapeamento de MOTORISTA para CPF")
    else:
        # Garantir que CARRETA 1 e CARRETA 2 tenham os mesmos valores no dropdown usando a Página1
        if 'CARRETA 1' in COMBOBOX_OPTIONS and 'CARRETA 2' in COMBOBOX_OPTIONS:
            carretas_combinadas = set(COMBOBOX_OPTIONS['CARRETA 1']).union(set(COMBOBOX_OPTIONS['CARRETA 2']))
            COMBOBOX_OPTIONS['CARRETA 1'] = sorted(list(carretas_combinadas))
            COMBOBOX_OPTIONS['CARRETA 2'] = sorted(list(carretas_combinadas))
            
        # Mapeamento de MOTORISTA para CPF MOTORISTA da Página1
    # Fallback para Página1 se PLACAS não tiver as informações necessárias ou não existir
    if ((df_placas is None) or (len(MOTORISTA_CPF_MAP) == 0)) and ('MOTORISTA' in df.columns) and ('CPF MOTORISTA' in df.columns):
        print("Usando dados da Página1 para mapeamento CPF MOTORISTA")
        MOTORISTA_CPF_MAP = df.set_index('MOTORISTA')['CPF MOTORISTA'].fillna('').to_dict()

except Exception as e:
    print(f"Erro ao processar planilha do OneDrive: {e}")
    CAMPOS_FORM = []
    CAMPOS_OBRIGATORIOS = set()
    TIPOS_DE_DADOS = {}
    CONTAINER_MAP = {}
    COMBOBOX_OPTIONS = {}
    MOTORISTA_CPF_MAP = {}

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'docx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    # Verifica o nível do usuário e redireciona adequadamente
    nivel = session.get('nivel')
    if nivel == 'gr':
        # Usuários GR devem ser direcionados para a rota /gr
        return redirect(url_for('gr_ambiente'))
    elif nivel == 'admin':
        return redirect(url_for('admin_dashboard'))
    else:
        return redirect(url_for('dashboard'))

@app.route('/formulario', methods=['GET', 'POST'])
@login_required
def formulario():
    if request.method == 'POST':
        # Adicionar a data de criação automaticamente
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        dados = {}
        for campo in COMBOBOX_OPTIONS.keys():
            valor = request.form.get(campo)
            tipo = TIPOS_DE_DADOS.get(campo, 'STR')
            if tipo == 'INT':
                valor = int(valor or 0)
            elif tipo in ['FLOAT', 'MOEDA']:
                valor = float(str(valor).replace(',', '.').replace('R$', '').strip() or 0)
            elif tipo == 'DT/HORA':
                try:
                    valor = datetime.strptime(valor, "%Y-%m-%d %H:%M")
                except:
                    valor = None
            dados[campo] = valor

        # Validação de obrigatórios
        for campo in CAMPOS_OBRIGATORIOS:
            if campo not in dados or dados[campo] in [None, '']:
                flash(f"O campo '{campo}' é obrigatório.", "danger")
                return redirect(request.url)

        # Upload de arquivos
        arquivos_recebidos = {}
        for campo, tipo in TIPOS_DE_DADOS.items():
            if tipo == 'FILE':
                file_obj = request.files.get(campo)
                if file_obj and allowed_file(file_obj.filename):
                    filename = secure_filename(file_obj.filename)
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    if not os.path.exists(filepath):
                        file_obj.save(filepath)
                    arquivos_recebidos[campo] = filename
                elif campo in CAMPOS_OBRIGATORIOS:
                    flash(f"Arquivo obrigatório não enviado: {campo}", "danger")
                    return redirect(request.url)

        # Registro no banco
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # Adicionar manualmente o campo Requisitante nas opções se não estiver presente
            if 'Requisitante' not in dados or not dados['Requisitante']:
                dados['Requisitante'] = session['user']
                
            # Vinculação automática entre MOTORISTA e CPF MOTORISTA
            if 'MOTORISTA' in dados and dados['MOTORISTA'] and ('CPF MOTORISTA' not in dados or not dados['CPF MOTORISTA']):
                motorista = dados['MOTORISTA']
                # Verificar se o motorista existe no mapeamento e atualizar o CPF automaticamente
                if motorista in MOTORISTA_CPF_MAP:
                    dados['CPF MOTORISTA'] = MOTORISTA_CPF_MAP[motorista]
            
            # Definir STATUS SM automaticamente com base no valor de NUMERO SM
            if 'NUMERO SM' in dados and dados['NUMERO SM'] and str(dados['NUMERO SM']).strip():
                dados['STATUS SM'] = 'sim'
            else:
                dados['STATUS SM'] = 'não'
                
            # Se NUMERO SM foi preenchido, registrar a data de criação
            if 'NUMERO SM' in dados and dados['NUMERO SM'] and str(dados['NUMERO SM']).strip():
                dados['DT CRIACAO SM'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # Para registros novos, o SLA inicial é 0 porque a criação e o preenchimento ocorrem simultaneamente
                dados['SLA SM'] = 0
                
            # Se NÚMERO AE foi preenchido, registrar a data de criação
            if 'NÚMERO AE' in dados and dados['NÚMERO AE'] and str(dados['NÚMERO AE']).strip():
                dados['DT CRIACAO AE'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # Para registros novos, o SLA inicial é 0 porque a criação e o preenchimento ocorrem simultaneamente
                dados['SLA AE'] = 0
                
            valores_final = {
                **dados,
                **arquivos_recebidos,
                'usuario': session['user'],
                'data_registro': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            colunas_sql = ', '.join(valores_final.keys())
            placeholders = ', '.join(['?'] * len(valores_final))
            valores = list(valores_final.values())

            cursor.execute(f"INSERT INTO registros ({colunas_sql}) VALUES ({placeholders})", valores)
            conn.commit()

        logging.info(f"Registro criado por {session['user']}: {valores_final}")
        flash("Registro salvo com sucesso.", "success")
        return redirect(url_for('dashboard'))

    # Definir campos digitáveis (não são dropdowns) para o template
    campos_digitaveis = ['CLIENTE', 'PEDIDO/REFERÊNCIA', 'BOOKING / DI', 'CONTAINER 1', 'CONTAINER 2', 
                        'LOTE CS', 'ORIGEM', 'DESTINO INTERMEDIÁRIO', 'DESTINO FINAL', 'ON TIME (CLIENTE)', 
                        'HORÁRIO PREVISTO DE INÍCIO', 'OBSERVACAO OPERACIONAL', 'NÚMERO AE', 
                        'DT CRIACAO AE', 'NUMERO SM', 'DT CRIACAO SM', 'OBSERVAÇÃO DE GR']
    
    return render_template(
        'form.html',
        campos=COMBOBOX_OPTIONS,
        tipos=TIPOS_DE_DADOS,
        container=CONTAINER_MAP,
        usuario=session['user'],
        MOTORISTA_CPF_MAP=MOTORISTA_CPF_MAP,
        CAMPOS_OBRIGATORIOS=CAMPOS_OBRIGATORIOS,
        campos_digitaveis=campos_digitaveis
    )


@app.route('/dashboard')
@login_required
def dashboard():
    filtro = request.args.get('filtro', '')
    pagina = int(request.args.get('pagina', 1))
    por_pagina = 10
    offset = (pagina - 1) * por_pagina
    
    # Data atual para cálculos
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row  # Usar Row para acessar colunas por nome
        cursor = conn.cursor()
        
        # Calcular o total geral de registros para o indicador
        cursor.execute("SELECT COUNT(*) FROM registros")
        total_registros = cursor.fetchone()[0]
        
        # Novos KPIs para o dashboard
        # 1. Quantidade de operações sem NF anexada
        cursor.execute("SELECT COUNT(*) FROM registros WHERE anexar_nf IS NULL OR anexar_nf = ''")
        operacoes_sem_nf = cursor.fetchone()[0]
        
        # 2. Quantidade de operações sem OS anexada
        cursor.execute("SELECT COUNT(*) FROM registros WHERE anexar_os IS NULL OR anexar_os = ''")
        operacoes_sem_os = cursor.fetchone()[0]
        
        # 3. Quantidade de operações sem Container 1 preenchido
        cursor.execute("SELECT COUNT(*) FROM registros WHERE container_1 IS NULL OR container_1 = ''")
        operacoes_sem_container1 = cursor.fetchone()[0]
        
        # 4. Quantidade de operações sem SM definida
        cursor.execute("SELECT COUNT(*) FROM registros WHERE numero_sm IS NULL OR numero_sm = ''")
        operacoes_sem_sm = cursor.fetchone()[0]
        
        # Contagem de registros atualizados (com entradas no histórico)
        cursor.execute("""
            SELECT COUNT(DISTINCT registro_id) FROM historico
        """)
        registros_atualizados = cursor.fetchone()[0]
        
        # Contagem de registros criados no mês atual
        cursor.execute("""
            SELECT COUNT(*) FROM registros 
            WHERE data_registro LIKE ?
        """, (f'{now.strftime("%Y-%m")}%',))
        registros_mes_atual = cursor.fetchone()[0]
        
        # Contagem de registros criados hoje
        cursor.execute("""
            SELECT COUNT(*) FROM registros 
            WHERE data_registro LIKE ?
        """, (f'{today}%',))
        registros_hoje = cursor.fetchone()[0]
        
        # Busca dos registros com filtragem
        if filtro:
            cursor.execute("""
                SELECT * FROM registros
                WHERE placa LIKE ? OR motorista LIKE ? OR cliente LIKE ?
                ORDER BY id DESC
                LIMIT ? OFFSET ?
            """, (f'%{filtro}%', f'%{filtro}%', f'%{filtro}%', por_pagina, offset))
            registros = cursor.fetchall()
            cursor.execute("""
                SELECT COUNT(*) FROM registros
                WHERE placa LIKE ? OR motorista LIKE ? OR cliente LIKE ?
            """, (f'%{filtro}%', f'%{filtro}%', f'%{filtro}%'))
        else:
            cursor.execute("SELECT * FROM registros ORDER BY id DESC LIMIT ? OFFSET ?", (por_pagina, offset))
            registros = cursor.fetchall()
            cursor.execute("SELECT COUNT(*) FROM registros")

        total = cursor.fetchone()[0]
        total_paginas = (total + por_pagina - 1) // por_pagina
        paginas = list(range(1, total_paginas + 1))
        
        # Buscar os logs recentes de alterações (últimos 8) - Abordagem mais segura
        try:
            # Primeiro verificar quais colunas existem na tabela registros
            cursor.execute("PRAGMA table_info(registros)")
            colunas_registros = [info[1] for info in cursor.fetchall()]
            
            # Construir seleção dinâmica com base nas colunas existentes
            colunas_basicas = ['placa', 'motorista', 'cliente']
            colunas_existentes = [col for col in colunas_basicas if col in colunas_registros]
            colunas_sql = ', '.join([f'r.{col}' for col in colunas_existentes])
            
            query = f"""
                SELECT h.id, h.registro_id, h.alterado_por, h.alteracoes, h.data_alteracao,
                       {colunas_sql if colunas_existentes else ''}
                FROM historico h
                LEFT JOIN registros r ON h.registro_id = r.id
                ORDER BY h.id DESC
                LIMIT 8
            """
            
            cursor.execute(query)
            logs_recentes = [dict(row) for row in cursor.fetchall()]
            
            # Para cada log, extrair os campos alterados e formatar para exibição
            for log in logs_recentes:
                alteracoes = log.get('alteracoes', '')
                log['campos_alterados'] = [campo.strip() for campo in alteracoes.split(',')] if alteracoes else []
        except Exception as e:
            logging.error(f"Erro ao buscar logs recentes: {e}")
            logs_recentes = []

    return render_template(
        'dashboard.html',
        registros=registros,
        usuario=session['user'],
        nivel=session['nivel'],
        filtro=filtro,
        pagina=pagina,
        total_paginas=total_paginas,
        paginas=paginas,
        campos=COMBOBOX_OPTIONS,
        tipos=TIPOS_DE_DADOS,
        total=total_registros,
        # Novos KPIs
        operacoes_sem_nf=operacoes_sem_nf,
        operacoes_sem_os=operacoes_sem_os,
        operacoes_sem_container1=operacoes_sem_container1,
        operacoes_sem_sm=operacoes_sem_sm,
        logs_recentes=logs_recentes,
        now=now,
        today=today
    )

@app.route('/editar/<int:registro_id>', methods=['GET', 'POST'])
@login_required
def editar_registro(registro_id):
    nivel_usuario = session.get('nivel', 'comum')
    usuario = session.get('user')
    
    # Função auxiliar para executar operações de banco de dados com retry
    def executar_db_com_retry(operacao_func, max_retries=5, timeout=5.0):
        import time
        for tentativa in range(max_retries):
            try:
                with sqlite3.connect(DB_PATH, timeout=timeout) as conn:
                    return operacao_func(conn)
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and tentativa < max_retries - 1:
                    # Espera exponencial antes de tentar novamente
                    wait_time = 0.1 * (2 ** tentativa)  # 0.1s, 0.2s, 0.4s, 0.8s, 1.6s
                    print(f"Database locked, aguardando {wait_time}s antes de tentar novamente...")
                    time.sleep(wait_time)
                    continue
                else:
                    # Se não for erro de bloqueio ou atingiu máximo de tentativas, propaga o erro
                    raise
    
    # Buscar o registro original para comparação e logs
    def buscar_registro_original(conn):
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM registros WHERE id = ?", (registro_id,))
        registro = cursor.fetchone()
        if not registro:
            return None, None
        colunas = [desc[0] for desc in cursor.description]
        return registro, dict(zip(colunas, registro))
    
    try:
        registro_original, registro_dict_original = executar_db_com_retry(buscar_registro_original)
        if not registro_original:
            flash("Registro não encontrado.", "danger")
            return redirect(url_for('dashboard'))
        
        # Buscar o registro atual (pode ser o mesmo que o original mas isolamos a operação)
        def buscar_registro_atual(conn):
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM registros WHERE id = ?", (registro_id,))
            registro = cursor.fetchone()
            if not registro:
                return None, None
            colunas = [desc[0] for desc in cursor.description]
            return registro, dict(zip(colunas, registro))
        
        registro, registro_dict = executar_db_com_retry(buscar_registro_atual)
        if not registro:
            flash("Registro não encontrado.", "danger")
            return redirect(url_for('dashboard'))
        
        # Mapear os campos do banco para os nomes correspondentes no template
        campo_mapping = {
            # Campos originais
            'placa': 'CAVALO 1',
            'motorista': 'MOTORISTA',
            'cpf': 'CPF MOTORISTA',
            'mot_loc': 'UNIDADE',
            'carreta': 'CARRETA 1',
            'carreta_loc': 'CARRETA 2',
            'cliente': 'CLIENTE',
            'loc_cliente': 'ORIGEM',
            'numero_sm': 'NUMERO SM',
            'numero_ae': 'NÚMERO AE',
            'container_1': 'CONTAINER 1',
            'container_2': 'CONTAINER 2',
            'DT CRIACAO SM': 'DT CRIACAO SM',
            'DT CRIACAO AE': 'DT CRIACAO AE',
            'sla_sm': 'SLA SM',
            'sla_ae': 'SLA AE',
            'usuario': 'Requisitante',
            'destino_intermediario': 'DESTINO INTERMEDIÁRIO',
            'destino_final': 'DESTINO FINAL',
            'booking_di': 'BOOKING / DI',
            'pedido_referencia': 'PEDIDO/REFERÊNCIA',
            'lote_cs': 'LOTE CS',
            'on_time_cliente': 'ON TIME (CLIENTE)',
            'horario_previsto': 'HORÁRIO PREVISTO DE INÍCIO',
            'observacao_operacional': 'OBSERVACAO OPERACIONAL',
            'observacao_gr': 'OBSERVAÇÃO DE GR',
            'status_sm': 'STATUS SM',
            'tipo_carga': 'TIPO DE CARGA',
            'status_container': 'STATUS CONTAINER',
            'modalidade': 'MODALIDADE',
            'gerenciadora': 'GERENCIADORA',
            
            # Campos de arquivo
            'anexar_nf': 'ANEXAR NF',
            'anexar_os': 'ANEXAR OS',
            'numero_nf': 'Nº NF',
            'serie': 'SÉRIE',
            'quantidade': 'QUANTIDADE',
            'peso_bruto': 'PESO BRUTO',
            'valor_total_nota': 'VALOR TOTAL DA NOTA'
        }
        
        if request.method == 'POST':
            # Processar o formulário de edição
            dados_atualizados = {}
            campos_alterados = []
            
            # Definir o mapeamento entre os campos do formulário e as colunas do banco de dados
            # Isso garante que usamos os nomes corretos das colunas do banco
            form_to_db_map = {
                'UNIDADE': 'mot_loc',
                'Requisitante': 'usuario',
                'MOTORISTA': 'motorista',
                'CPF MOTORISTA': 'cpf',
                'CAVALO 1': 'placa',
                'CARRETA 1': 'carreta',
                'CARRETA 2': 'carreta_loc',
                'CLIENTE': 'cliente',
                'PEDIDO/REFERÊNCIA': 'pedido_referencia',
                'BOOKING / DI': 'booking_di',
                'CONTAINER 1': 'container_1',
                'CONTAINER 2': 'container_2',
                'LOTE CS': 'lote_cs',
                'ORIGEM': 'loc_cliente',
                'DESTINO INTERMEDIÁRIO': 'destino_intermediario',
                'DESTINO FINAL': 'destino_final',
                'ON TIME (CLIENTE)': 'on_time_cliente',
                'HORÁRIO PREVISTO DE INÍCIO': 'horario_previsto',
                'OBSERVACAO OPERACIONAL': 'observacao_operacional',
                'NÚMERO AE': 'numero_ae',
                'DT CRIACAO AE': 'data_ae',
                'NUMERO SM': 'numero_sm',
                'DT CRIACAO SM': 'data_sm',
                'OBSERVAÇÃO DE GR': 'observacao_gr',
                'STATUS CONTAINER': 'status_container',
                'TIPO DE CARGA': 'tipo_de_carga',
                'MODALIDADE': 'modalidade',
                'GERENCIADORA': 'gerenciadora'
            }
            
            # Capturar todos os campos do formulário
            for campo_form in request.form:
                # Skip campos vazios
                valor = request.form.get(campo_form, '').strip()
                if not valor:
                    continue
                    
                # Determinar o nome da coluna no banco
                campo_bd = form_to_db_map.get(campo_form, campo_form.lower().replace(' ', '_'))
                
                # Verificar se o campo existe no schema do banco
                if campo_bd in registro_dict_original:
                    # Converter para o tipo correto com base no tipo de dados
                    tipo = TIPOS_DE_DADOS.get(campo_form, 'STR')
                    
                    if tipo == 'INT':
                        try:
                            valor = int(valor or 0)
                        except ValueError:
                            valor = 0
                    elif tipo in ['FLOAT', 'MOEDA']:
                        try:
                            valor_str = str(valor).replace(',', '.').replace('R$', '').strip()
                            if valor_str.lower() == 'none' or valor_str == '':
                                valor = 0.0
                            else:
                                valor = float(valor_str)
                        except ValueError:
                            valor = 0.0
                    elif tipo == 'DT/HORA':
                        try:
                            valor = datetime.strptime(valor, "%Y-%m-%d %H:%M")
                        except:
                            valor = None
                    
                    # Verificar se o valor realmente mudou
                    if str(valor) != str(registro_dict_original.get(campo_bd, '')):
                        dados_atualizados[campo_bd] = valor
                        campos_alterados.append(campo_form)
                        print(f"Campo alterado: {campo_form} -> {campo_bd} = '{valor}'")
            
            # Tratar explicitamente o campo STATUS CONTAINER que pode ter causado problemas
            if 'STATUS CONTAINER' in request.form:
                status = request.form.get('STATUS CONTAINER')
                if status.strip():
                    dados_atualizados['status_container'] = status
                    if 'STATUS CONTAINER' not in campos_alterados:
                        campos_alterados.append('STATUS CONTAINER')
                    print(f"STATUS CONTAINER explicitamente atualizado para: '{status}'")
            
            # Capturar uploads de arquivos
            for campo, tipo in TIPOS_DE_DADOS.items():
                if tipo == 'FILE':
                    file_obj = request.files.get(campo)
                    if file_obj and file_obj.filename and allowed_file(file_obj.filename):
                        filename = secure_filename(file_obj.filename)
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        if not os.path.exists(filepath):
                            file_obj.save(filepath)
                        
                        campo_bd = form_to_db_map.get(campo, campo.lower().replace(' ', '_'))
                        dados_atualizados[campo_bd] = filename
                        campos_alterados.append(campo)
            
            # Adicionamos automaticamente o valor Requisitante como o nome do usuário logado
            if 'usuario' not in dados_atualizados:
                dados_atualizados['usuario'] = usuario
            
            # Vincular CPF MOTORISTA ao MOTORISTA selecionado automticamente
            if 'motorista' in dados_atualizados:
                motorista = dados_atualizados['motorista']
                if motorista in MOTORISTA_CPF_MAP and 'cpf' not in dados_atualizados:
                    dados_atualizados['cpf'] = MOTORISTA_CPF_MAP[motorista]
                    print(f"CPF atualizado automaticamente para o motorista: {motorista} -> {MOTORISTA_CPF_MAP[motorista]}")
            
            # Verificar campos obrigatórios
            for campo in CAMPOS_OBRIGATORIOS:
                campo_bd = form_to_db_map.get(campo, campo.lower().replace(' ', '_'))
                if campo_bd not in dados_atualizados and campo_bd not in registro_dict_original:
                    flash(f"O campo '{campo}' é obrigatório.", "danger")
                    return redirect(request.url)
            
            # Função auxiliar para calcular SLA
            def calcular_sla(data_reg_str):
                try:
                    dt_registro = datetime.strptime(data_reg_str, '%Y-%m-%d %H:%M:%S')
                    dt_atual = datetime.now()
                    return (dt_atual - dt_registro).total_seconds()
                except Exception as e:
                    print(f"Erro ao calcular SLA: {e}")
                    return None
            
            # Verificar novos preenchimentos de SM e AE para cálculo de SLA
            numero_sm_novo = request.form.get('NUMERO SM', '').strip()
            numero_ae_novo = request.form.get('NÚMERO AE', '').strip()
            
            # Recuperar SM e AE atuais do registro
            sm_atual = registro_dict_original.get('numero_sm', '')
            ae_atual = registro_dict_original.get('numero_ae', '')
            sm_atual = sm_atual if sm_atual else ''
            ae_atual = ae_atual if ae_atual else ''
            
            # Verificar se SM foi preenchido pela primeira vez
            if numero_sm_novo and not sm_atual:
                print(f"Novo preenchimento de SM: '{numero_sm_novo}'")
                dados_atualizados['data_sm'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                dados_atualizados['status_sm'] = 'sim'
                
                # Calcular SLA SM (tempo desde criação do registro até preenchimento)
                data_registro = registro_dict_original.get('data_registro')
                if data_registro:
                    try:
                        dt_registro = datetime.strptime(data_registro, '%Y-%m-%d %H:%M:%S')
                        dt_atual = datetime.now()
                        sla_segundos = (dt_atual - dt_registro).total_seconds()
                        dados_atualizados['sla_sm'] = sla_segundos
                        print(f"SLA SM calculado: {sla_segundos} segundos")
                    except Exception as e:
                        print(f"Erro ao calcular SLA SM: {e}")
            
            # Verificar se AE foi preenchido pela primeira vez
            if numero_ae_novo and not ae_atual:
                print(f"Novo preenchimento de AE: '{numero_ae_novo}'")
                dados_atualizados['data_ae'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # Calcular SLA AE (tempo desde criação do registro até preenchimento)
                data_registro = registro_dict_original.get('data_registro')
                if data_registro:
                    try:
                        dt_registro = datetime.strptime(data_registro, '%Y-%m-%d %H:%M:%S')
                        dt_atual = datetime.now()
                        sla_segundos = (dt_atual - dt_registro).total_seconds()
                        dados_atualizados['sla_ae'] = sla_segundos
                        print(f"SLA AE calculado: {sla_segundos} segundos")
                    except Exception as e:
                        print(f"Erro ao calcular SLA AE: {e}")
            
            # Construir a query de atualização
            if dados_atualizados:
                query_partes = []
                valores = []
                
                # Debug dos campos que serão atualizados
                print(f"Campos a serem atualizados: {list(dados_atualizados.keys())}")
                
                for campo, valor in dados_atualizados.items():
                    query_partes.append(f"{campo} = ?")
                    valores.append(valor)
                
                if query_partes:
                    # Preparar string de campos alterados para o log
                    if campos_alterados:
                        campos_alterados_str = ', '.join(campos_alterados)
                        
                        # Executar a query de atualização em uma operação isolada
                        def atualizar_registro_e_log(conn):
                            cursor = conn.cursor()
                            # Registrar as alterações no histórico
                            cursor.execute("INSERT INTO historico (registro_id, alterado_por, alteracoes, data_alteracao) VALUES (?, ?, ?, ?)",
                                          (registro_id, usuario, campos_alterados_str, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                            
                            # Executar a query de atualização
                            query = f"UPDATE registros SET {', '.join(query_partes)} WHERE id = ?"
                            valores.append(registro_id)
                            
                            print(f"Query de atualização: {query}")
                            print(f"Valores: {valores}")
                            
                            cursor.execute(query, valores)
                            return True
                        
                        # Executar a atualização com retry
                        executar_db_com_retry(atualizar_registro_e_log)
                        
                        # Se for usuário GR ou admin, registrar no log administrativo (em uma operação isolada)
                        if nivel_usuario in ['gr', 'admin']:
                            log_admin_action(usuario, "EDIÇÃO DE REGISTRO", 
                                          f"Registro ID: {registro_id}, Criado por: {registro_dict_original.get('usuario', 'Desconhecido')}, Campos alterados: {campos_alterados_str}")
                    flash("Registro atualizado com sucesso!", "success")
                    return redirect(url_for('dashboard'))
                else:
                    flash("Nenhuma alteração foi detectada no registro.", "info")
                    return redirect(url_for('dashboard'))
            else:
                flash("Nenhuma alteração foi detectada no registro.", "info")
                return redirect(url_for('dashboard'))
        # Já recuperamos o registro no início da função, então não é necessário buscar novamente
        if not registro_dict:
            flash("Registro não encontrado.", "danger")
            return redirect(url_for('dashboard'))
    except Exception as e:
        # Tratamento de erro global para a manipulação do registro
        print(f"Erro ao processar o registro ID {registro_id}: {str(e)}")
        flash(f"Ocorreu um erro ao processar o registro. Detalhes: {str(e)}", "danger")
        return redirect(url_for('dashboard'))
    
    # Debug: imprimir os valores do registro
    print(f"Valores do registro {registro_id} do banco: {registro_dict}")
    
    # Criar objeto de registro para o template (aqui vamos armazenar os dados mapeados para o formulário)
    registro_completo = {}
    
    # ESTRATÉGIA 1: Mapear diretamente as colunas do banco para o formulário
    # Mapear campos do banco de dados (coluna) para campos do formulário
    # Para maior clareza, esta é a estrutura: db_column_name -> form_field_name
    db_to_form_mapping = {
        'id': 'id',
        'usuario': 'Requisitante',
        'data_registro': 'DATA',
        'placa': 'CAVALO 1',
        'motorista': 'MOTORISTA',
        'cpf': 'CPF MOTORISTA',
        'mot_loc': 'UNIDADE',
        'carreta': 'CARRETA 1',
        'carreta_loc': 'CARRETA 2',
        'cliente': 'CLIENTE',
        'loc_cliente': 'ORIGEM',
        'container_1': 'CONTAINER 1',
        'container_2': 'CONTAINER 2',
        'lote_cs': 'LOTE CS',
        'destino_intermediario': 'DESTINO INTERMEDIÁRIO',
        'destino_final': 'DESTINO FINAL',
        'booking_di': 'BOOKING / DI',
        'pedido_referencia': 'PEDIDO/REFERÊNCIA',
        'on_time_cliente': 'ON TIME (CLIENTE)',
        'horario_previsto': 'HORÁRIO PREVISTO DE INÍCIO',
        'observacao_operacional': 'OBSERVACAO OPERACIONAL',
        'observacao_gr': 'OBSERVAÇÃO DE GR',
        'numero_sm': 'NUMERO SM',
        'dt_criacao_sm': 'DT CRIACAO SM',
        'sla_sm': 'SLA SM',
        'numero_ae': 'NÚMERO AE',
        'dt_criacao_ae': 'DT CRIACAO AE',
        'sla_ae': 'SLA AE',
        'status_sm': 'STATUS SM',
        'tipo_carga': 'TIPO DE CARGA',
        'status_container': 'STATUS CONTAINER',
        'modalidade': 'MODALIDADE',
        'gerenciadora': 'GERENCIADORA',
        'anexar_nf': 'ANEXAR NF',
        'anexar_os': 'ANEXAR OS',
        'anexar_agendamento': 'Anexar Agendamento'
    }
    
    # Percorrer todas as colunas do banco e mapear para o formulário
    for coluna_bd, valor in registro_dict.items():
        # Se a coluna do BD tem um mapeamento para o formulário
        if coluna_bd in db_to_form_mapping:
            campo_form = db_to_form_mapping[coluna_bd]
            registro_completo[campo_form] = valor
            print(f"Mapeado: BD '{coluna_bd}' -> Form '{campo_form}' = '{valor}'")
        else:
            # Para colunas que não têm mapeamento, usar o mesmo nome
            registro_completo[coluna_bd] = valor
            print(f"Sem mapeamento: '{coluna_bd}' = '{valor}'")
    
    # ESTRATÉGIA 2: Adicionar campos padrão do formulário que podem não estar no banco
    # Inicializar campos que devem estar presentes no formulário
    for campo in COMBOBOX_OPTIONS.keys():
        if campo not in registro_completo:
            registro_completo[campo] = ""
            
    # ESTRATÉGIA 3: Processar campos específicos
    # Determinar STATUS SM para o formulário se não estiver definido
    if 'STATUS SM' not in registro_completo or registro_completo['STATUS SM'] is None:
        if registro_dict.get('numero_sm') and str(registro_dict.get('numero_sm')).strip():
            registro_completo['STATUS SM'] = 'sim'
        else:
            registro_completo['STATUS SM'] = 'não'
            
    # Logging final dos campos mapeados
    print(f"Campos finais para o template: {registro_completo}")

    
    # Determinar STATUS SM para o formulário
    if registro_dict.get('numero_sm') and registro_dict.get('numero_sm').strip():
        registro_completo['STATUS SM'] = 'sim'
    else:
        registro_completo['STATUS SM'] = 'não'

    # Definir campos digitáveis (não são dropdowns) para o template
    campos_digitaveis = ['CLIENTE', 'PEDIDO/REFERÊNCIA', 'BOOKING / DI', 'CONTAINER 1', 'CONTAINER 2', 
                      'LOTE CS', 'ORIGEM', 'DESTINO INTERMEDIÁRIO', 'DESTINO FINAL', 'ON TIME (CLIENTE)', 
                      'HORÁRIO PREVISTO DE INÍCIO', 'OBSERVACAO OPERACIONAL', 'NÚMERO AE', 
                      'DT CRIACAO AE', 'NUMERO SM', 'DT CRIACAO SM', 'OBSERVAÇÃO DE GR']
    
    return render_template(
        'editar_novo.html',
        campos=COMBOBOX_OPTIONS,
        tipos=TIPOS_DE_DADOS,
        container=CONTAINER_MAP,
        usuario=session['user'],
        registro=registro_completo,
        CAMPOS_OBRIGATORIOS=CAMPOS_OBRIGATORIOS,
        MOTORISTA_CPF_MAP=MOTORISTA_CPF_MAP,
        campos_digitaveis=campos_digitaveis
    )

@app.route('/delete/<int:registro_id>')
@login_required
def delete(registro_id):
    nivel_usuario = session.get('nivel', 'comum')
    usuario = session.get('user')
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # Buscar o registro e seu criador
        cursor.execute("SELECT id, usuario FROM registros WHERE id = ?", (registro_id,))
        registro = cursor.fetchone()
        
        if not registro:
            flash("Registro não encontrado.", "danger")
            return redirect(url_for('dashboard'))
        
        registro_id, usuario_criador = registro
        
        # Verificar permissões conforme regras de negócio:
        # Admin - pode excluir qualquer registro
        # GR - pode excluir registros de usuários comuns
        # Comum - não pode excluir nenhum registro
        permitido = False
        motivo_log = ""
        
        if nivel_usuario == 'admin':
            permitido = True
            motivo_log = "Exclusão por administrador"
        elif nivel_usuario == 'gr':
            # Verificar se o usuário criador é um admin ou GR
            cursor.execute("SELECT nivel FROM usuarios WHERE username = ?", (usuario_criador,))
            nivel_criador = cursor.fetchone()
            nivel_criador = nivel_criador[0] if nivel_criador else 'comum'
            
            if nivel_criador == 'comum':
                permitido = True
                motivo_log = "Exclusão de registro de usuário comum por GR"
            else:
                permitido = False
                motivo_log = "Tentativa de exclusão de registro de usuário privilegiado (GR/admin) por GR - Bloqueado"
                
        if not permitido:
            # Registrar tentativa não autorizada no log
            if nivel_usuario in ['gr', 'admin']:
                log_admin_action(usuario, "TENTATIVA DE EXCLUSÃO NÃO AUTORIZADA", 
                               f"Registro ID: {registro_id}, Criado por: {usuario_criador}, Motivo: {motivo_log}")
                
            flash("Você não tem permissão para apagar este registro.", "danger")
            return redirect(url_for('dashboard'))
        
        # Exclusão autorizada
        cursor.execute("SELECT * FROM registros WHERE id = ?", (registro_id,))
        registro_completo = cursor.fetchone()
        
        # Executar a exclusão
        cursor.execute("DELETE FROM registros WHERE id = ?", (registro_id,))
        conn.commit()
        
        # Registrar a ação no log de administração (para GR e admin)
        if nivel_usuario in ['gr', 'admin']:
            log_admin_action(usuario, "EXCLUSÃO DE REGISTRO", 
                          f"Registro ID: {registro_id}, Criado por: {usuario_criador}, Motivo: {motivo_log}")

    # Também registrar no log geral
    logging.info(f"Registro ID {registro_id} apagado por {usuario} - Dados: {registro_completo}")
    flash("Registro apagado com sucesso.", "success")
    return redirect(url_for('dashboard'))

@app.route('/download/<filename>')
@login_required
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
