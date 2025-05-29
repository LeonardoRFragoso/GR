from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import sqlite3
import logging
import os

app = Flask(__name__)
app.secret_key = 'chave_secreta_para_teste_gr'

# Configurar logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Função para conectar ao banco de dados
def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# Rota principal - página de login
@app.route('/')
def index():
    return render_template('teste_login_gr.html')

# Rota de login
@app.route('/login', methods=['POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        logger.info(f"Tentativa de login: {username}")
        
        # Login direto para teste_gr
        if username == 'teste_gr' and password == 'Teste@123':
            logger.info("Login bem-sucedido para teste_gr")
            session.clear()
            session['user'] = username
            session['nivel'] = 'gr'
            session['user_id'] = 11  # ID fixo para teste_gr
            
            logger.info(f"Sessão definida: {session}")
            return redirect(url_for('ambiente'))
        
        # Verificar no banco de dados para outros usuários
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM usuarios WHERE username = ?", (username,))
                user = cursor.fetchone()
                
                if user:
                    # Verificar senha
                    cursor.execute("SELECT password FROM usuarios WHERE username = ?", (username,))
                    stored_password_row = cursor.fetchone()
                    
                    if stored_password_row:
                        stored_password = stored_password_row[0]
                        is_valid = False
                        
                        # Para senhas hashed com pbkdf2:sha256
                        if stored_password.startswith('pbkdf2:sha256:'):
                            from werkzeug.security import check_password_hash
                            is_valid = check_password_hash(stored_password, password)
                        # Fallback para comparação direta
                        else:
                            is_valid = (stored_password == password)
                        
                        if is_valid:
                            # Login bem-sucedido
                            session.clear()
                            session['user'] = username
                            session['nivel'] = user['nivel']
                            session['user_id'] = user['id']
                            logger.info(f"Usuário autenticado: {username} com nível {user['nivel']}")
                            
                            if user['nivel'] == 'gr':
                                return redirect(url_for('ambiente'))
                            else:
                                return redirect(url_for('index'))
        except Exception as e:
            logger.error(f"Erro ao verificar usuário: {e}")
        
        flash('Usuário ou senha inválidos', 'danger')
        return redirect(url_for('index'))

# Rota do ambiente GR
@app.route('/ambiente')
def ambiente():
    logger.info(f"Acessando ambiente - Sessão: {session}")
    
    if 'user' not in session:
        logger.warning("Usuário não está na sessão")
        flash('Por favor, faça login para acessar esta página', 'warning')
        return redirect(url_for('index'))
    
    nivel = session.get('nivel')
    logger.info(f"Nível do usuário: {nivel}")
    
    if nivel != 'gr':
        logger.warning(f"Acesso negado: nível {nivel} não tem permissão")
        flash('Acesso restrito à Gestão de Relacionamento', 'danger')
        return redirect(url_for('index'))
    
    # Obter algumas métricas básicas para exibição
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Registros pendentes (sem SM)
            cursor.execute("""
                SELECT COUNT(*) 
                FROM registros 
                WHERE DT_CRIACAO_SM IS NULL AND excluido = 0
            """)
            registros_pendentes = cursor.fetchone()[0]
            
            # Registros em andamento (com SM, sem AE)
            cursor.execute("""
                SELECT COUNT(*) 
                FROM registros 
                WHERE DT_CRIACAO_SM IS NOT NULL AND DT_CRIACAO_AE IS NULL AND excluido = 0
            """)
            registros_andamento = cursor.fetchone()[0]
            
            # Registros concluídos (com AE)
            cursor.execute("""
                SELECT COUNT(*) 
                FROM registros 
                WHERE DT_CRIACAO_AE IS NOT NULL AND excluido = 0
            """)
            registros_concluidos = cursor.fetchone()[0]
    except Exception as e:
        logger.error(f"Erro ao obter métricas: {e}")
        registros_pendentes = 0
        registros_andamento = 0
        registros_concluidos = 0
    
    return render_template('teste_ambiente_gr.html', 
                          usuario=session.get('user'),
                          nivel=session.get('nivel'),
                          user_id=session.get('user_id'),
                          session_data=dict(session),
                          registros_pendentes=registros_pendentes,
                          registros_andamento=registros_andamento,
                          registros_concluidos=registros_concluidos)

# Rota para verificar o status da sessão
@app.route('/session_status')
def session_status():
    return jsonify({
        'logged_in': 'user' in session,
        'user': session.get('user', None),
        'nivel': session.get('nivel', None),
        'user_id': session.get('user_id', None)
    })

# Rota de logout
@app.route('/logout')
def logout():
    session.clear()
    flash('Você foi desconectado', 'info')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5002)
