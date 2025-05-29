import sys
import os
from datetime import datetime

# Adiciona o diretório principal ao path para importações relativas
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.database import get_db_connection

def log_admin_action(usuario, acao, detalhes=""):
    """
    Registra ações realizadas por administradores e GRs para auditoria
    
    Args:
        usuario: Nome do usuário que realizou a ação
        acao: Descrição da ação realizada
        detalhes: Detalhes adicionais sobre a ação
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Registramos na tabela de admin_logs
            cursor.execute(
                "INSERT INTO admin_logs (usuario, acao, detalhes, data) VALUES (?, ?, ?, ?)",
                (usuario, acao, detalhes, now)
            )
            conn.commit()
            
            # Retornamos o ID do log criado
            return cursor.lastrowid
            
    except Exception as e:
        print(f"Erro ao registrar ação administrativa: {e}")
        return None

def get_admin_logs(limit=100, offset=0):
    """
    Recupera os logs de ações administrativas
    
    Args:
        limit: Quantidade máxima de logs a serem retornados
        offset: Posição inicial para paginação
        
    Returns:
        Lista de logs administrativos
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM admin_logs ORDER BY data DESC LIMIT ? OFFSET ?", 
                (limit, offset)
            )
            logs = cursor.fetchall()
            return [dict(log) for log in logs]
    except Exception as e:
        print(f"Erro ao recuperar logs administrativos: {e}")
        return []
        
def count_admin_logs():
    """
    Conta o número total de logs administrativos para paginação
    
    Returns:
        Número total de logs
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM admin_logs")
            count = cursor.fetchone()[0]
            return count
    except Exception as e:
        print(f"Erro ao contar logs administrativos: {e}")
        return 0
