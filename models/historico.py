import json
import sys
import os
import logging
import re
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
                        # Registrar o tamanho da string JSON para depuração
                        json_str_length = len(item['alteracoes']) if item['alteracoes'] else 0
                        logger.debug(f"Processando JSON de tamanho {json_str_length} para histórico do registro {registro_id}")
                        
                        # Sanitizar o JSON antes de processá-lo - usar modo agressivo para strings grandes
                        use_aggressive = json_str_length > 5000
                        sanitized_json = sanitize_json_string(item['alteracoes'], aggressive=use_aggressive)
                        
                        try:
                            alteracoes = json.loads(sanitized_json)
                            item['alteracoes_dict'] = alteracoes
                            # Contar quantos campos foram alterados
                            item['num_alteracoes'] = len(alteracoes)
                        except json.JSONDecodeError as je:
                            logger.error(f"Erro ao decodificar JSON no histórico do registro {registro_id}: {je}")
                            logger.error(f"Posição do erro: {je.pos}, linha: {je.lineno}, coluna: {je.colno}")
                            
                            # Registrar um trecho do JSON em torno da posição do erro
                            error_pos = je.pos
                            context_start = max(0, error_pos - 50)
                            context_end = min(len(sanitized_json), error_pos + 50)
                            error_context = sanitized_json[context_start:context_end]
                            logger.error(f"Contexto do erro: {error_context}")
                            
                            # Tentar sanitização mais agressiva
                            try:
                                sanitized_json = sanitize_json_string(item['alteracoes'], aggressive=True)
                                alteracoes = json.loads(sanitized_json)
                                item['alteracoes_dict'] = alteracoes
                                item['num_alteracoes'] = len(alteracoes)
                                logger.info(f"Sanitização agressiva bem-sucedida para o registro {registro_id}")
                            except json.JSONDecodeError as je2:
                                logger.error(f"Sanitização agressiva falhou para registro {registro_id}: {je2}")
                                logger.error(f"Posição do erro após sanitização agressiva: {je2.pos}, linha: {je2.lineno}, coluna: {je2.colno}")
                                
                                # Tentar uma abordagem ainda mais radical: remover todos os caracteres de escape
                                try:
                                    import re
                                    # Remover todas as barras invertidas
                                    sanitized_extreme = re.sub(r'\\', '', item['alteracoes'])
                                    # Substituir aspas simples por aspas duplas
                                    sanitized_extreme = sanitized_extreme.replace("'", '"')
                                    # Remover caracteres de controle
                                    sanitized_extreme = re.sub(r'[\x00-\x1F\x7F]', ' ', sanitized_extreme)
                                    
                                    try:
                                        alteracoes = json.loads(sanitized_extreme)
                                        item['alteracoes_dict'] = alteracoes
                                        item['num_alteracoes'] = len(alteracoes)
                                        logger.info(f"Sanitização extrema bem-sucedida para registro {registro_id}")
                                    except json.JSONDecodeError as je3:
                                        logger.error(f"Sanitização extrema falhou: {je3}")
                                        # Se falhar, usar um objeto vazio
                                        item['alteracoes_dict'] = {}
                                        item['num_alteracoes'] = 0
                                except Exception as e3:
                                    logger.error(f"Erro na sanitização extrema: {e3}")
                                    # Se falhar, usar um objeto vazio
                                    item['alteracoes_dict'] = {}
                                    item['num_alteracoes'] = 0
                            except Exception as e2:
                                logger.error(f"Sanitização agressiva falhou com erro não-JSON: {e2}")
                                # Se falhar, usar um objeto vazio
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
            alteracoes_json = sanitize_json_string(json.dumps(alteracoes, ensure_ascii=False))
            
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
                        # Registrar o tamanho da string JSON para depuração
                        hist_id = item.get('id', 'desconhecido')
                        json_str_length = len(item['alteracoes']) if item['alteracoes'] else 0
                        logger.debug(f"Processando JSON de tamanho {json_str_length} para histórico (id: {hist_id})")
                        
                        # Sanitizar o JSON antes de processá-lo - usar modo agressivo para strings grandes
                        use_aggressive = json_str_length > 5000
                        sanitized_json = sanitize_json_string(item['alteracoes'], aggressive=use_aggressive)
                        
                        try:
                            alteracoes = json.loads(sanitized_json)
                            item['alteracoes_dict'] = alteracoes
                            # Contar quantos campos foram alterados
                            item['num_alteracoes'] = len(alteracoes)
                        except json.JSONDecodeError as je:
                            logger.error(f"Erro ao decodificar JSON no histórico (id: {hist_id}): {je}")
                            logger.error(f"Posição do erro: {je.pos}, linha: {je.lineno}, coluna: {je.colno}")
                            
                            # Registrar um trecho do JSON em torno da posição do erro
                            error_pos = je.pos
                            context_start = max(0, error_pos - 50)
                            context_end = min(len(sanitized_json), error_pos + 50)
                            error_context = sanitized_json[context_start:context_end]
                            logger.error(f"Contexto do erro: {error_context}")
                            
                            # Tentar sanitização mais agressiva
                            try:
                                sanitized_json = sanitize_json_string(item['alteracoes'], aggressive=True)
                                alteracoes = json.loads(sanitized_json)
                                item['alteracoes_dict'] = alteracoes
                                item['num_alteracoes'] = len(alteracoes)
                                logger.info(f"Sanitização agressiva bem-sucedida para o histórico (id: {hist_id})")
                            except json.JSONDecodeError as je2:
                                logger.error(f"Sanitização agressiva falhou para histórico (id: {hist_id}): {je2}")
                                logger.error(f"Posição do erro após sanitização agressiva: {je2.pos}, linha: {je2.lineno}, coluna: {je2.colno}")
                                
                                # Tentar uma abordagem ainda mais radical: remover todos os caracteres de escape
                                try:
                                    # Remover todas as barras invertidas
                                    sanitized_extreme = re.sub(r'\\', '', item['alteracoes'])
                                    # Substituir aspas simples por aspas duplas
                                    sanitized_extreme = sanitized_extreme.replace("'", '"')
                                    # Remover caracteres de controle
                                    sanitized_extreme = re.sub(r'[\x00-\x1F\x7F]', ' ', sanitized_extreme)
                                    
                                    try:
                                        alteracoes = json.loads(sanitized_extreme)
                                        item['alteracoes_dict'] = alteracoes
                                        item['num_alteracoes'] = len(alteracoes)
                                        logger.info(f"Sanitização extrema bem-sucedida para histórico (id: {hist_id})")
                                    except json.JSONDecodeError as je3:
                                        logger.error(f"Sanitização extrema falhou: {je3}")
                                        # Se falhar, usar um objeto vazio
                                        item['alteracoes_dict'] = {}
                                        item['num_alteracoes'] = 0
                                except Exception as e3:
                                    logger.error(f"Erro na sanitização extrema: {e3}")
                                    # Se falhar, usar um objeto vazio
                                    item['alteracoes_dict'] = {}
                                    item['num_alteracoes'] = 0
                            except Exception as e2:
                                logger.error(f"Sanitização agressiva falhou com erro não-JSON: {e2}")
                                # Se falhar, usar um objeto vazio
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
            alteracoes_json = sanitize_json_string(json.dumps(alteracoes_dict, ensure_ascii=False))
            
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
