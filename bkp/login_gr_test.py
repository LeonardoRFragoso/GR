from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
import os
import logging

app = Flask(__name__)
app.secret_key = 'chave_secreta_para_teste'

# Configurar logging
logging.basicConfig(level=logging.DEBUG)

# Função para conectar ao banco de dados
def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# Rota principal
@app.route('/')
def index():
    return render_template('login_gr_test.html')

# Rota de login
@app.route('/login', methods=['POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        app.logger.info(f"Tentativa de login: {username}")
        
        # Login direto para teste_gr
        if username == 'teste_gr' and password == 'Teste@123':
            app.logger.info("Login bem-sucedido para teste_gr")
            session.clear()
            session['user'] = username
            session['nivel'] = 'gr'
            session['user_id'] = 11  # ID fixo para teste_gr
            
            app.logger.info(f"Sessão definida: {session}")
            return redirect('/ambiente')
        
        flash('Usuário ou senha inválidos', 'danger')
        return redirect('/')

# Rota do ambiente GR
@app.route('/ambiente')
def ambiente():
    app.logger.info(f"Acessando ambiente - Sessão: {session}")
    
    if 'user' not in session:
        app.logger.warning("Usuário não está na sessão")
        flash('Por favor, faça login para acessar esta página', 'warning')
        return redirect('/')
    
    nivel = session.get('nivel')
    app.logger.info(f"Nível do usuário: {nivel}")
    
    if nivel != 'gr':
        app.logger.warning(f"Acesso negado: nível {nivel} não tem permissão")
        flash('Acesso restrito à Gestão de Relacionamento', 'danger')
        return redirect('/')
    
    return render_template('ambiente_gr_test.html', 
                          usuario=session.get('user'),
                          nivel=session.get('nivel'))

# Rota de logout
@app.route('/logout')
def logout():
    session.clear()
    flash('Você foi desconectado', 'info')
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True, port=5001)
