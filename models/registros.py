import sqlite3
from datetime import datetime
import json
import sys
import os

# Adiciona o diretório principal ao path para importações relativas
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.database import get_db_connection

class Registro:
    @staticmethod
    def create(usuario, dados):
        """
        Cria um novo registro de atendimento
        
        Args:
            usuario: Nome do usuário que está criando o registro
            dados: Dicionário com os dados do registro
            
        Returns:
            ID do registro criado ou None se falhar
        """
        try:
            # Garantir que dados tem a data atual
            if 'data_registro' not in dados:
                dados['data_registro'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Garantir que o usuário está no registro
            dados['usuario'] = usuario
            
            # Construir a query dinamicamente com base nos campos presentes
            campos = list(dados.keys())
            placeholders = ['?'] * len(campos)
            values = [dados[campo] for campo in campos]
            
            query = f"""
                INSERT INTO registros ({', '.join(campos)})
                VALUES ({', '.join(placeholders)})
            """
            
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, values)
                conn.commit()
                return cursor.lastrowid
                
        except Exception as e:
            print(f"Erro ao criar registro: {e}")
            return None
    
    @staticmethod
    def get_by_id(registro_id):
        """
        Recupera um registro pelo ID
        
        Args:
            registro_id: ID do registro
            
        Returns:
            Dicionário com os dados do registro ou None se não encontrado
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM registros WHERE id = ? AND excluido = 0", (registro_id,))
                registro = cursor.fetchone()
                return dict(registro) if registro else None
        except Exception as e:
            print(f"Erro ao recuperar registro: {e}")
            return None
    
    @staticmethod
    def update(registro_id, dados, usuario_alteracao):
        """
        Atualiza um registro existente e registra as alterações no histórico
        
        Args:
            registro_id: ID do registro a ser atualizado
            dados: Dicionário com os novos dados
            usuario_alteracao: Nome do usuário que está fazendo a alteração
            
        Returns:
            True se a atualização for bem-sucedida, False caso contrário
        """
        try:
            # Recuperar o registro original para comparação
            registro_original = Registro.get_by_id(registro_id)
            if not registro_original:
                return False
            
            # Remover campos que não são colunas da tabela
            dados_filtrados = {k: v for k, v in dados.items() if k in registro_original}
            
            # Identificar campos alterados
            alteracoes = {}
            for campo, novo_valor in dados_filtrados.items():
                if campo in registro_original and registro_original[campo] != novo_valor:
                    alteracoes[campo] = {
                        'anterior': registro_original[campo],
                        'novo': novo_valor
                    }
            
            if not alteracoes:
                # Não há alterações a fazer
                return True
            
            # Construir a query de atualização
            campos_update = [f"{campo} = ?" for campo in dados_filtrados.keys()]
            values = list(dados_filtrados.values())
            values.append(registro_id)  # Para o WHERE
            
            query = f"""
                UPDATE registros 
                SET {', '.join(campos_update)}
                WHERE id = ?
            """
            
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, values)
                
                # Registrar as alterações no histórico
                data_alteracao = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                alteracoes_json = json.dumps(alteracoes, ensure_ascii=False)
                
                cursor.execute("""
                    INSERT INTO historico_alteracoes 
                    (registro_id, usuario, data_alteracao, alteracoes) 
                    VALUES (?, ?, ?, ?)
                """, (
                    registro_id, 
                    usuario_alteracao,
                    data_alteracao,
                    alteracoes_json
                ))
                
                conn.commit()
                return True
                
        except Exception as e:
            print(f"Erro ao atualizar registro: {e}")
            return False
    
    @staticmethod
    def delete(registro_id, usuario):
        """
        Marca um registro como excluído (exclusão lógica)
        
        Args:
            registro_id: ID do registro a ser marcado como excluído
            usuario: Nome do usuário que está executando a exclusão
            
        Returns:
            True se a exclusão lógica for bem-sucedida, False caso contrário
        """
        try:
            # Verificar se o registro existe e não está já excluído
            registro = Registro.get_by_id(registro_id)
            if not registro:
                return False
                
            data_exclusao = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE registros SET excluido = 1, data_exclusao = ?, excluido_por = ? WHERE id = ?", 
                             (data_exclusao, usuario, registro_id))
                conn.commit()
                return True
        except Exception as e:
            print(f"Erro ao realizar exclusão lógica do registro: {e}")
            return False
    
    @staticmethod
    def get_all(limit=100, offset=0, filters=None):
        """
        Recupera todos os registros com paginação e filtros opcionais
        
        Args:
            limit: Quantidade máxima de registros a serem retornados
            offset: Posição inicial para paginação
            filters: Dicionário com filtros a serem aplicados
            
        Returns:
            Lista de registros
        """
        try:
            filters = filters or {}
            base_query = "SELECT * FROM registros WHERE excluido = 0"
            params = []
            
            # Aplicar filtros se existirem
            if filters:
                filter_conditions = []
                for campo, valor in filters.items():
                    # Filtros especiais dos cards
                    if campo == 'sem_nf' and valor:
                        filter_conditions.append("(anexar_nf IS NULL OR anexar_nf = '')")
                    elif campo == 'sem_os' and valor:
                        filter_conditions.append("(anexar_os IS NULL OR anexar_os = '')")
                    elif campo == 'sem_container' and valor:
                        filter_conditions.append("(container_1 IS NULL OR container_1 = '')")
                    elif campo == 'sem_sm' and valor:
                        filter_conditions.append("(numero_sm IS NULL OR numero_sm = '')")
                    elif campo == 'sem_ae' and valor:
                        filter_conditions.append("(numero_ae IS NULL OR numero_ae = '')")
                    elif campo == 'alteracoes_pos_smae' and valor:
                        filter_conditions.append("data_modificacao > data_registro AND (numero_sm IS NOT NULL OR numero_ae IS NOT NULL)")
                    elif campo == 'status_sm' and valor == 'Pendente':
                        filter_conditions.append("(status_sm = 'Pendente' OR status_sm IS NULL OR status_sm = '')")
                    # Filtros regulares
                    elif valor and campo != 'alteracoes_pos_smae':  # Evitar adicionar o parâmetro para filtros especiais
                        filter_conditions.append(f"{campo} = ?")
                        params.append(valor)
            
                if filter_conditions:
                    base_query += " AND " + " AND ".join(filter_conditions)
        
            # Ordenar primeiro por registros com horário previsto futuro mais próximo
            # Depois por registros com horário previsto passado ou sem horário
            query = f"{base_query} ORDER BY "
            query += "CASE WHEN horario_previsto IS NULL OR horario_previsto = '' THEN 1 "
            query += "WHEN horario_previsto < datetime('now') THEN 2 "
            query += "ELSE 0 END ASC, "
            query += "CASE WHEN horario_previsto IS NULL OR horario_previsto = '' THEN data_registro "
            query += "WHEN horario_previsto < datetime('now') THEN data_registro "
            query += "ELSE horario_previsto END ASC "
            query += "LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                registros = cursor.fetchall()
                return [dict(reg) for reg in registros]
                
        except Exception as e:
            print(f"Erro ao recuperar registros: {e}")
            return []
    
    @staticmethod
    def count(filters=None):
        """
        Conta o número total de registros com filtros opcionais
        
        Args:
            filters: Dicionário com filtros a serem aplicados
            
        Returns:
            Número total de registros
        """
        try:
            base_query = "SELECT COUNT(*) FROM registros WHERE excluido = 0"
            params = []
            
            # Aplicar filtros se existirem
            if filters:
                filter_conditions = []
                for campo, valor in filters.items():
                    # Filtros especiais dos cards
                    if campo == 'sem_nf' and valor:
                        filter_conditions.append("(arquivo IS NULL OR arquivo = '')")
                    elif campo == 'sem_os' and valor:
                        filter_conditions.append("(numero_ae IS NULL OR numero_ae = '')")
                    elif campo == 'sem_container' and valor:
                        filter_conditions.append("(container_1 IS NULL OR container_1 = '')")
                    elif campo == 'sem_sm' and valor:
                        filter_conditions.append("(numero_sm IS NULL OR numero_sm = '')")
                    elif campo == 'sem_ae' and valor:
                        filter_conditions.append("(numero_ae IS NULL OR numero_ae = '')")
                    elif campo == 'alteracoes_pos_smae' and valor:
                        filter_conditions.append("data_modificacao > data_registro AND (numero_sm IS NOT NULL OR numero_ae IS NOT NULL)")
                    elif campo == 'status_sm' and valor == 'Pendente':
                        filter_conditions.append("(status_sm = 'Pendente' OR status_sm IS NULL OR status_sm = '')")
                    # Filtros regulares
                    elif valor and campo != 'alteracoes_pos_smae':  # Evitar adicionar o parâmetro para filtros especiais
                        filter_conditions.append(f"{campo} = ?")
                        params.append(valor)
                
                if filter_conditions:
                    base_query += " AND " + " AND ".join(filter_conditions)
            
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(base_query, params)
                count = cursor.fetchone()[0]
                return count
                
        except Exception as e:
            print(f"Erro ao contar registros: {e}")
            return 0
