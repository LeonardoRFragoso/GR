import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash
import sys
import os

# Adiciona o diretório principal ao path para importar config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH

def get_db_connection():
    """Estabelece e retorna uma conexão com o banco de dados"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Inicializa o banco de dados criando as tabelas necessárias"""
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

        # Verificar e criar usuários de teste se não existirem
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Usuário admin de teste
        cursor.execute("SELECT * FROM usuarios WHERE username = ?", ('teste_admin',))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO usuarios (username, password_hash, nivel, created_at) VALUES (?, ?, ?, ?)",
                           ('teste_admin', 'Teste@123', 'admin', now))
        
        # Usuário GR de teste
        cursor.execute("SELECT * FROM usuarios WHERE username = ?", ('teste_gr',))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO usuarios (username, password_hash, nivel, created_at) VALUES (?, ?, ?, ?)",
                           ('teste_gr', 'Teste@123', 'gr', now))
        
        # Usuário comum de teste
        cursor.execute("SELECT * FROM usuarios WHERE username = ?", ('teste_comum',))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO usuarios (username, password_hash, nivel, created_at) VALUES (?, ?, ?, ?)",
                           ('teste_comum', 'Teste@123', 'comum', now))
        
        # Adicionar também tabela para solicitações de senha se não existir
        cursor.execute('''CREATE TABLE IF NOT EXISTS solicitacoes_senha (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            username TEXT NOT NULL,
                            data_solicitacao TEXT,
                            status TEXT DEFAULT 'pendente',
                            aprovado_por TEXT,
                            data_aprovacao TEXT
                          )''')
        
        # Tabela para logs de ações administrativas
        cursor.execute('''CREATE TABLE IF NOT EXISTS admin_logs (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            usuario TEXT,
                            acao TEXT,
                            detalhes TEXT,
                            data TEXT
                          )''')
                          
        conn.commit()
