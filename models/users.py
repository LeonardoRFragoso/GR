import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import sys
import os

# Adiciona o diretório principal ao path para importações relativas
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.database import get_db_connection
from config import DB_PATH

class Usuario:
    @staticmethod
    def get_by_username(username):
        """Recupera um usuário pelo nome de usuário"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM usuarios WHERE username = ?", (username,))
                user = cursor.fetchone()
                if user:
                    user_dict = dict(user)
                    # Garantir que estamos usando 'nivel' como esperado pelo sistema
                    print(f"Colunas encontradas para o usuário {username}: {list(user_dict.keys())}")
                    return user_dict
                return None
        except Exception as e:
            print(f"Erro ao buscar usuário {username}: {e}")
            return None
    
    @staticmethod
    def get_by_id(user_id):
        """Recupera um usuário pelo ID"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,))
            user = cursor.fetchone()
            if user:
                user_dict = dict(user)
                # Mapear 'role' para 'nivel' para compatibilidade com o código existente
                if 'role' in user_dict and 'nivel' not in user_dict:
                    user_dict['nivel'] = user_dict['role']
                return user_dict
            return None
    
    @staticmethod
    def create(username, password, nivel='comum', email=None):
        """Cria um novo usuário"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO usuarios (username, password_hash, nivel, email, created_at, senha_temporaria, primeiro_login) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (username, generate_password_hash(password), nivel, email, now, 1, 1)
                )
                conn.commit()
                return cursor.lastrowid
        except sqlite3.IntegrityError as e:
            # Usuário já existe
            print(f"Erro ao criar usuário {username}: {e}")
            return None
        except Exception as e:
            print(f"Erro inesperado ao criar usuário {username}: {e}")
            return None

    @staticmethod
    def update(user_id, nivel=None, email=None):
        """Atualiza os dados de um usuário"""
        updates = []
        params = []
        
        if nivel is not None:
            updates.append("nivel = ?")
            params.append(nivel)
        if email is not None:
            updates.append("email = ?")
            params.append(email)
            
        if not updates:
            return False
        
        query = f"UPDATE usuarios SET {', '.join(updates)} WHERE id = ?"
        params.append(user_id)
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Erro ao atualizar usuário {user_id}: {e}")
            return False
    
    @staticmethod
    def change_password(user_id, new_password):
        """Altera a senha de um usuário"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE usuarios SET password_hash = ? WHERE id = ?",
                (generate_password_hash(new_password), user_id)
            )
            conn.commit()
            return cursor.rowcount > 0
    
    @staticmethod
    def verify_password(username, password):
        """Verifica se a senha está correta"""
        user = Usuario.get_by_username(username)
        if not user:
            return False
        return check_password_hash(user['password_hash'], password)
    
    @staticmethod
    def update_last_login(username):
        """Atualiza o último login do usuário"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE usuarios SET last_login = ? WHERE username = ?",
                (now, username)
            )
            conn.commit()
    
    @staticmethod
    def get_all():
        """Retorna todos os usuários"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM usuarios ORDER BY nivel, username")
                users = cursor.fetchall()
                result = []
                for user in users:
                    user_dict = dict(user)
                    result.append(user_dict)
                return result
        except Exception as e:
            print(f"Erro ao obter todos os usuários: {e}")
            return []
    
    @staticmethod
    def delete(user_id):
        """Remove um usuário pelo ID"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM usuarios WHERE id = ?", (user_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    @staticmethod
    def get_solicitacoes_pendentes():
        """Retorna todas as solicitações de redefinição de senha pendentes"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT s.*, u.nivel 
                    FROM solicitacoes_senha s
                    JOIN usuarios u ON s.username = u.username
                    WHERE s.status = 'pendente'
                    ORDER BY s.data_solicitacao DESC
                """)
                solicitacoes = cursor.fetchall()
                return [dict(solicitacao) for solicitacao in solicitacoes] if solicitacoes else []
        except Exception as e:
            print(f"Erro ao obter solicitações pendentes: {e}")
            return []
            
    @staticmethod
    def count_solicitacoes_senha_pendentes():
        """Conta o número de solicitações de redefinição de senha pendentes"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) FROM solicitacoes_senha 
                    WHERE status = 'pendente'
                """)
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            print(f"Erro ao contar solicitações de senha pendentes: {e}")
            return 0
