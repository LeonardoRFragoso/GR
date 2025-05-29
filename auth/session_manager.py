import uuid
import time
from datetime import datetime
from flask import session, request
import logging
import sqlite3
from models.database import get_db_connection

# Tempo em segundos para considerar uma sessão inativa
SESSION_TIMEOUT = 300  # 5 minutos

def generate_device_id():
    """Gera um ID único para o dispositivo baseado em informações do navegador"""
    user_agent = request.headers.get('User-Agent', '')
    ip = request.remote_addr
    # Combinar informações para criar um identificador de dispositivo
    device_info = f"{user_agent}|{ip}"
    return device_info

def init_session(username, nivel):
    """Inicializa uma nova sessão para o usuário"""
    # Limpar qualquer sessão anterior
    session.clear()
    
    # Gerar um ID único para esta sessão
    session_id = str(uuid.uuid4())
    device_id = generate_device_id()
    current_time = int(time.time())
    
    # Armazenar informações na sessão
    session['user'] = username
    session['nivel'] = nivel
    # Não usar 'role' pois a tabela usuarios não tem essa coluna
    session['session_id'] = session_id
    session['device_id'] = device_id
    session['last_activity'] = current_time
    
    # Registrar a sessão no banco de dados
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sessoes_ativas (session_id, username, device_id, nivel, last_activity, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
            """, (session_id, username, device_id, nivel, current_time))
            conn.commit()
            logging.info(f"Nova sessão iniciada: {username} em {device_id}")
    except Exception as e:
        logging.error(f"Erro ao registrar sessão: {e}")
    
    return session_id

def validate_session():
    """Valida se a sessão atual é válida"""
    if 'user' not in session or 'session_id' not in session:
        return False
    
    username = session.get('user')
    session_id = session.get('session_id')
    device_id = session.get('device_id')
    current_device_id = generate_device_id()
    
    # Verificar se o dispositivo atual é o mesmo que iniciou a sessão
    if device_id != current_device_id:
        logging.warning(f"Tentativa de acesso com dispositivo diferente: {username}")
        return False
    
    # Verificar se a sessão existe no banco de dados
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM sessoes_ativas 
                WHERE session_id = ? AND username = ?
            """, (session_id, username))
            session_record = cursor.fetchone()
            
            if not session_record:
                logging.warning(f"Sessão não encontrada no banco: {username}")
                return False
            
            # Verificar se a sessão não expirou
            last_activity = session.get('last_activity', 0)
            current_time = int(time.time())
            
            if current_time - last_activity > SESSION_TIMEOUT:
                logging.info(f"Sessão expirada por inatividade: {username}")
                end_session()
                return False
            
            # Atualizar o timestamp de última atividade
            update_activity()
            return True
            
    except Exception as e:
        logging.error(f"Erro ao validar sessão: {e}")
        return False

def update_activity():
    """Atualiza o timestamp de última atividade da sessão"""
    if 'user' not in session or 'session_id' not in session:
        return
    
    current_time = int(time.time())
    session['last_activity'] = current_time
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE sessoes_ativas 
                SET last_activity = ? 
                WHERE session_id = ?
            """, (current_time, session.get('session_id')))
            conn.commit()
    except Exception as e:
        logging.error(f"Erro ao atualizar atividade da sessão: {e}")

def end_session():
    """Encerra a sessão atual"""
    if 'session_id' in session:
        session_id = session.get('session_id')
        username = session.get('user')
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM sessoes_ativas 
                    WHERE session_id = ?
                """, (session_id,))
                conn.commit()
                logging.info(f"Sessão encerrada: {username}")
        except Exception as e:
            logging.error(f"Erro ao encerrar sessão no banco: {e}")
    
    session.clear()

def cleanup_inactive_sessions():
    """Remove sessões inativas do banco de dados"""
    current_time = int(time.time())
    cutoff_time = current_time - SESSION_TIMEOUT
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM sessoes_ativas 
                WHERE last_activity < ?
            """, (cutoff_time,))
            
            if cursor.rowcount > 0:
                logging.info(f"Removidas {cursor.rowcount} sessões inativas")
            
            conn.commit()
    except Exception as e:
        logging.error(f"Erro ao limpar sessões inativas: {e}")

def create_sessions_table():
    """Cria a tabela de sessões ativas se não existir"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessoes_ativas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE NOT NULL,
                    username TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    nivel TEXT NOT NULL,
                    last_activity INTEGER NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
            """)
            conn.commit()
            logging.info("Tabela de sessões ativas verificada/criada")
    except Exception as e:
        logging.error(f"Erro ao criar tabela de sessões: {e}")
