import json
import sys
import os
import logging
from datetime import datetime

# Adiciona o diretÃ³rio principal ao path para importaÃ§Ãµes relativas
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.database import get_db_connection
from historico_utils import sanitize_json_string

logger = logging.getLogger(__name__)

class Historico:
    @staticmethod
    def get_by_registro(registro_id):
        """
        Recupera o histÃ³rico de alteraÃ§Ãµes de um registro
        
        Args:
            registro_id: ID do registro
            
        Returns:
            Lista de alteraÃ§Ãµes com detalhes formatados
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM historico WHERE registro_id = ? ORDER BY data_alteracao DESC",
                    (registro_id,)
                )
                historico = cursor.fetchall()
                
                # Formatar o histÃ³rico
                historico_formatado = []
                for h in historico:
                    item = dict(h)
                    try:
                        # Parse das alteraÃ§Ãµes que estÃ£o em formato JSON
                        alteracoes = json.loads(item['alteracoes'])
                        item['alteracoes_dict'] = alteracoes
                        # Contar quantos campos foram alterados
                        item['num_alteracoes'] = len(alteracoes)
                    except:
                        item['alteracoes_dict'] = {}
                        item['num_alteracoes'] = 0
                    
                    historico_formatado.append(item)
                
                return historico_formatado
                
        except Exception as e:
            print(f"Erro ao recuperar histÃ³rico: {e}")
            return []
    
    @staticmethod
    def add(registro_id, usuario, alteracoes):
        """
        Adiciona uma entrada no histÃ³rico de alteraÃ§Ãµes
        
        Args:
            registro_id: ID do registro alterado
            usuario: UsuÃ¡rio que fez a alteraÃ§Ã£o
            alteracoes: DicionÃ¡rio com as alteraÃ§Ãµes (campo: {anterior, novo})
            
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
            print(f"Erro ao adicionar histÃ³rico: {e}")
            return None
    
    @staticmethod
    def get_all(limit=100, offset=0):
        """
        Recupera todo o histÃ³rico com paginaÃ§Ã£o
        
        Args:
            limit: Quantidade mÃ¡xima de entradas a serem retornadas
            offset: PosiÃ§Ã£o inicial para paginaÃ§Ã£o
            
        Returns:
            Lista de entradas do histÃ³rico
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
                
                # Formatar o histÃ³rico
                historico_formatado = []
                for h in historico:
                    item = dict(h)
                    try:
                        # Parse das alteraÃ§Ãµes que estÃ£o em formato JSON
                        alteracoes = json.loads(item['alteracoes'])
                        item['alteracoes_dict'] = alteracoes
                        # Contar quantos campos foram alterados
                        item['num_alteracoes'] = len(alteracoes)
                    except:
                        item['alteracoes_dict'] = {}
                        item['num_alteracoes'] = 0
                    
                    historico_formatado.append(item)
                
                return historico_formatado
                
        except Exception as e:
            print(f"Erro ao recuperar histÃ³rico: {e}")
            return []
    
    @staticmethod
    def count():
        """
        Conta o nÃºmero total de entradas no histÃ³rico
        
        Returns:
            NÃºmero total de entradas
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM historico")
                count = cursor.fetchone()[0]
                return count
                
        except Exception as e:
            print(f"Erro ao contar histÃ³rico: {e}")
            return 0
    
    @staticmethod
    def registrar_acao(usuario, acao, tabela, registro_id, detalhes=None):
        """
        Registra uma aÃ§Ã£o no histÃ³rico (criaÃ§Ã£o, alteraÃ§Ã£o, exclusÃ£o)
        
        Args:
            usuario: UsuÃ¡rio que realizou a aÃ§Ã£o
            acao: Tipo de aÃ§Ã£o (criaÃ§Ã£o, alteraÃ§Ã£o, exclusÃ£o)
            tabela: Nome da tabela afetada
            registro_id: ID do registro afetado
            detalhes: Detalhes adicionais da aÃ§Ã£o (opcional)
            
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
            print(f"Erro ao registrar aÃ§Ã£o no histÃ³rico: {e}")
            return None
