import json
import sys
import os
import logging
from datetime import datetime

# Adiciona o diretório principal ao path para importações relativas
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.database import get_db_connection
from historico_utils import sanitize_json_string

logger = logging.getLogger(__name__)

class Historico:
    @staticmethod
    def get_by_registro(registro_id):
        """
        Recupera o histórico de alterações de um registro
        
        Args:
            registro_id: ID do registro
            
        Returns:
            Lista de alterações com detalhes formatados
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM historico WHERE registro_id = ? ORDER BY data_alteracao DESC",
                    (registro_id,)
                )
                historico = cursor.fetchall()
                
                # Formatar o histórico
                historico_formatado = []
                for h in historico:
                    item = dict(h)
                    try:
                        # Sanitizar e fazer parse das alterações que estão em formato JSON
                        sanitized_json = sanitize_json_string(item['alteracoes'])
                        alteracoes = json.loads(sanitized_json)
                        item['alteracoes_dict'] = alteracoes
                        # Contar quantos campos foram alterados
                        item['num_alteracoes'] = len(alteracoes)
                    except json.JSONDecodeError as je:
                        logger.error(f"Erro ao decodificar JSON no histórico do registro {registro_id}: {je}")
                        item['alteracoes_dict'] = {}
                        item['num_alteracoes'] = 0
                    except Exception as e:
                        logger.error(f"Erro inesperado ao processar histórico do registro {registro_id}: {e}")
                        item['alteracoes_dict'] = {}
                        item['num_alteracoes'] = 0
                    
                    historico_formatado.append(item)
                
                return historico_formatado
                
        except Exception as e:
            logger.error(f"Erro ao recuperar histórico: {e}")
            return []
    
    @staticmethod
    def add(registro_id, usuario, alteracoes):
        """
        Adiciona uma entrada no histórico de alterações
        
        Args:
            registro_id: ID do registro alterado
            usuario: Usuário que fez a alteração
            alteracoes: Dicionário com as alterações (campo: {anterior, novo})
            
        Returns:
            ID da entrada criada ou None se falhar
        """
        from datetime import datetime
        
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            alteracoes_json = json.dumps(alteracoes, ensure_ascii=False)
            
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO historico (registro_id, alterado_por, alteracoes, data_alteracao) VALUES (?, ?, ?, ?)",
                    (registro_id, usuario, alteracoes_json, now)
                )
                conn.commit()
                return cursor.lastrowid
                
        except Exception as e:
            logger.error(f"Erro ao adicionar histórico: {e}")
            return None
    
    @staticmethod
    def get_all(limit=100, offset=0):
        """
        Recupera todo o histórico com paginação
        
        Args:
            limit: Quantidade máxima de entradas a serem retornadas
            offset: Posição inicial para paginação
            
        Returns:
            Lista de entradas do histórico
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT h.*, r.usuario as registro_usuario
                    FROM historico h
                    LEFT JOIN registros r ON h.registro_id = r.id
                    ORDER BY h.data_alteracao DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset)
                )
                historico = cursor.fetchall()
                
                # Formatar o histórico
                historico_formatado = []
                for h in historico:
                    item = dict(h)
                    try:
                        # Sanitizar e fazer parse das alterações que estão em formato JSON
                        sanitized_json = sanitize_json_string(item['alteracoes'])
                        alteracoes = json.loads(sanitized_json)
                        item['alteracoes_dict'] = alteracoes
                        # Contar quantos campos foram alterados
                        item['num_alteracoes'] = len(alteracoes)
                    except json.JSONDecodeError as je:
                        logger.error(f"Erro ao decodificar JSON no histórico (id: {item.get('id', 'desconhecido')}): {je}")
                        item['alteracoes_dict'] = {}
                        item['num_alteracoes'] = 0
                    except Exception as e:
                        logger.error(f"Erro inesperado ao processar histórico (id: {item.get('id', 'desconhecido')}): {e}")
                        item['alteracoes_dict'] = {}
                        item['num_alteracoes'] = 0
                    
                    historico_formatado.append(item)
                
                return historico_formatado
                
        except Exception as e:
            logger.error(f"Erro ao recuperar histórico: {e}")
            return []
    
    @staticmethod
    def count():
        """
        Conta o número total de entradas no histórico
        
        Returns:
            Número total de entradas
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM historico")
                count = cursor.fetchone()[0]
                return count
                
        except Exception as e:
            logger.error(f"Erro ao contar histórico: {e}")
            return 0
    
    @staticmethod
    def registrar_acao(usuario, acao, tabela, registro_id, detalhes=None):
        """
        Registra uma ação no histórico (criação, alteração, exclusão)
        
        Args:
            usuario: Usuário que realizou a ação
            acao: Tipo de ação (criação, alteração, exclusão)
            tabela: Nome da tabela afetada
            registro_id: ID do registro afetado
            detalhes: Detalhes adicionais da ação (opcional)
            
        Returns:
            ID da entrada criada ou None se falhar
        """
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            alteracoes_dict = {
                "acao": acao,
                "tabela": tabela,
                "detalhes": detalhes or ""
            }
            alteracoes_json = json.dumps(alteracoes_dict, ensure_ascii=False)
            
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO historico (registro_id, alterado_por, alteracoes, data_alteracao) VALUES (?, ?, ?, ?)",
                    (registro_id, usuario, alteracoes_json, now)
                )
                conn.commit()
                return cursor.lastrowid
                
        except Exception as e:
            logger.error(f"Erro ao registrar ação no histórico: {e}")
            return None
