import json
import logging
import sqlite3
from datetime import datetime
from flask import jsonify
from models.database import get_db_connection

# Constantes para nomes de tabelas
TABLE_REGISTROS = 'registros'
TABLE_HISTORICO = 'historico'

# Constantes para nomes de colunas frequentemente usadas
COL_ID = 'id'
COL_EXCLUIDO = 'excluido'

# Configurar logger
logger = logging.getLogger(__name__)

def obter_historico_alteracoes(registro_id):
    """Obter o histórico de alterações de um registro.
    
    Args:
        registro_id (int): ID do registro
        
    Returns:
        dict: Dicionário com informações do registro e alterações
    """
    # Importar json no início da função para evitar problemas de escopo
    import json
    import re
    
    logger.info(f"Obtendo histórico de alterações para o registro {registro_id}")
    
    # Inicializar conexão com o banco de dados
    conn = None
    
    try:
        # Abrir conexão com o banco de dados
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verificar se o registro existe
        cursor.execute(f"SELECT * FROM {TABLE_REGISTROS} WHERE {COL_ID} = ? AND {COL_EXCLUIDO} = 0", (registro_id,))
        registro = cursor.fetchone()
        if not registro:
            logger.error(f"Registro ID {registro_id} não encontrado")
            return jsonify({"error": "Registro não encontrado", "success": False}), 404
        
        # Inicializar o dicionário de informações do registro
        registro_info = {}
        
        # Obter a data de modificação mais recente
        data_modificacao = None
        
        # Verificar se a tabela historico existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='historico'")
        tabela_existe = cursor.fetchone()
        
        if tabela_existe:
            # Buscar a alteração mais recente para este registro
            cursor.execute(
                """SELECT data_alteracao FROM historico 
                WHERE registro_id = ? 
                ORDER BY data_alteracao DESC LIMIT 1""", 
                (registro_id,)
            )
            ultima_alteracao = cursor.fetchone()
            
            if ultima_alteracao:
                data_modificacao = ultima_alteracao['data_alteracao']
        
        # Processar campos do registro
        for campo in registro.keys():
            valor = registro[campo]
            
            # Se for o campo data_modificacao e temos uma data mais recente do histórico
            if campo == 'data_modificacao' and data_modificacao:
                valor = data_modificacao
            
            # Tratar valores nulos
            if valor is None:
                valor = 'Não informado'
                
            # Formatar datas se necessário
            if campo in ['data_registro', 'data_modificacao', 'data_sm', 'data_ae', 'on_time_cliente', 'horario_previsto'] and valor and valor != 'Não informado':
                try:
                    # Verificar o formato da data
                    if isinstance(valor, str):
                        # Tentar diferentes formatos de data
                        try:
                            # Formato ISO: YYYY-MM-DD HH:MM:SS
                            data_obj = datetime.strptime(valor, '%Y-%m-%d %H:%M:%S')
                            valor = data_obj.strftime('%d/%m/%Y %H:%M:%S')
                        except ValueError:
                            try:
                                # Formato alternativo: HH:MM:SS DD-MM-YYYY
                                data_obj = datetime.strptime(valor, '%H:%M:%S %d-%m-%Y')
                                valor = data_obj.strftime('%d/%m/%Y %H:%M:%S')
                            except ValueError:
                                # Manter o formato original se não conseguir converter
                                logger.warning(f"Formato de data não reconhecido para {campo}: {valor}")
                except Exception as e:
                    logger.error(f"Erro ao formatar data {campo}: {e}")
                    # Não interromper o processamento, apenas logar o erro
            
            # Adicionar o campo ao dicionário de informações
            registro_info[campo] = valor
        
        # Buscar o histórico de alterações para este registro
        alteracoes = []
        
        # Verificar se a tabela histórico existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='historico'")
        if cursor.fetchone():
            # Buscar todos os registros do histórico para este registro
            cursor.execute("""
                SELECT id, registro_id, alterado_por, alteracoes, data_alteracao
                FROM historico
                WHERE registro_id = ?
                ORDER BY data_alteracao DESC
            """, (registro_id,))
            
            registros_historico = cursor.fetchall()
            logger.info(f"Encontrados {len(registros_historico)} registros no histórico para o registro {registro_id}")
            
            # Processar cada registro do histórico
            for registro_hist in registros_historico:
                try:
                    alteracao = {
                        'id': registro_hist['id'],
                        'registro_id': registro_hist['registro_id'],
                        'usuario': registro_hist['alterado_por'],
                        'data_hora': registro_hist['data_alteracao'],
                        'alteracoes_raw': registro_hist['alteracoes']
                    }
                    
                    # Tentar processar as alterações como JSON
                    try:
                        alteracoes_json = registro_hist['alteracoes']
                        if isinstance(alteracoes_json, str):
                            alteracoes_obj = json.loads(alteracoes_json.replace("'", '"'))
                        else:
                            alteracoes_obj = alteracoes_json
                        
                        # Log para depuração
                        logger.info(f"Processando alteração: {alteracoes_obj}")
                        
                        # Verificar se é uma alteração do tipo 'Edição GR'
                        if isinstance(alteracoes_obj, dict) and 'tipo' in alteracoes_obj and alteracoes_obj['tipo'] == 'Edição GR':
                            alteracao['tipo'] = 'Edição GR'
                            alteracao['campos'] = alteracoes_obj.get('campos', [])
                        # Verificar se é uma alteração do tipo 'Verificação de Alterações'
                        elif isinstance(alteracoes_obj, dict) and 'tipo' in alteracoes_obj and alteracoes_obj['tipo'] == 'Verificação de Alterações':
                            alteracao['tipo'] = 'Verificação de Alterações'
                            alteracao['campos'] = alteracoes_obj.get('campos', [])
                        else:
                            # Processar alterações normais (campo a campo)
                            campos_alterados = []
                            for campo, valores in alteracoes_obj.items():
                                if isinstance(valores, dict) and 'valor_antigo' in valores and 'valor_novo' in valores:
                                    campos_alterados.append({
                                        'campo': campo,
                                        'valor_antigo': valores['valor_antigo'],
                                        'valor_novo': valores['valor_novo']
                                    })
                            alteracao['campos_alterados'] = campos_alterados
                    except Exception as e:
                        logger.error(f"Erro ao processar alterações JSON: {e}")
                        alteracao['erro'] = str(e)
                    
                    alteracoes.append(alteracao)
                except Exception as e:
                    logger.error(f"Erro ao processar registro do histórico: {e}")
        
        # Transformar o formato dos dados para ser compatível com o JavaScript
        alteracoes_formatadas = []
        
        # Verificar se há campos alterados
        campos_alterados_encontrados = False
        
        # Obter a data de inclusão de SM/AE
        data_sm_ae = None
        for alteracao in alteracoes:
            try:
                alteracoes_obj = json.loads(alteracao.get('alteracoes_raw', '{}').replace("'", '"'))
                # Verificar se é uma alteração que inclui SM ou AE
                if ('numero_sm' in alteracoes_obj or 'numero_ae' in alteracoes_obj) and alteracao.get('usuario', '').lower() in ['gr', 'admin']:
                    data_sm_ae = alteracao.get('data_hora', '')
                    break
            except Exception as e:
                logger.error(f"Erro ao processar data de SM/AE: {e}")
        
        for alteracao in alteracoes:
            # Processar todas as alterações, independentemente do usuário ou do momento
            usuario = alteracao.get('usuario', '').lower()
            
            # Processar cada campo alterado dentro da alteração
            for campo_alterado in alteracao.get('campos_alterados', []):
                campo = campo_alterado.get('campo', '')
                # Não ignorar nenhum campo, para garantir que todas as alterações sejam exibidas
                
                campos_alterados_encontrados = True
                
                # Garantir que os valores não sejam None
                valor_antigo = campo_alterado.get('valor_antigo', '')
                if valor_antigo is None or valor_antigo == '':
                    valor_antigo = 'Vazio'
                
                valor_novo = campo_alterado.get('valor_novo', '')
                if valor_novo is None or valor_novo == '':
                    valor_novo = 'Vazio'
                
                # Adicionar a alteração formatada
                alteracoes_formatadas.append({
                    'campo': campo,
                    'valor_antigo': valor_antigo,
                    'valor_novo': valor_novo,
                    'data_alteracao': alteracao.get('data_hora', ''),
                    'usuario': alteracao.get('usuario', 'Sistema')
                })
        
        # Se não encontrou campos alterados, criar alterações para os campos do tipo 'Edição GR'
        if not campos_alterados_encontrados:
            for alteracao in alteracoes:
                # Verificar se é uma alteração do tipo 'Edição GR' ou 'Verificação de Alterações'
                if 'tipo' in alteracao:
                    if alteracao['tipo'] == 'Edição GR' or alteracao['tipo'] == 'Verificação de Alterações':
                        for campo in alteracao.get('campos', []):
                            # Obter o valor atual do campo do registro
                            valor_atual = registro[campo] if campo in registro.keys() else 'Não disponível'
                            if valor_atual is None:
                                valor_atual = 'Não informado'
                            
                            # Tentar obter o valor anterior buscando no histórico
                            valor_anterior = None
                            
                            # Estratégia 1: Buscar o valor anterior em alterações anteriores deste campo
                            try:
                                # Buscar alterações anteriores para este campo
                                cursor.execute("""
                                    SELECT alteracoes FROM historico 
                                    WHERE registro_id = ? AND alteracoes LIKE ? AND data_alteracao < ?
                                    ORDER BY data_alteracao DESC LIMIT 1
                                """, (registro_id, f'%"{campo}"%', alteracao.get('data_hora', '')))
                                
                                hist_anterior = cursor.fetchone()
                                if hist_anterior:
                                    try:
                                        alt_json = json.loads(hist_anterior['alteracoes'].replace("'", '"'))
                                        if campo in alt_json:
                                            if isinstance(alt_json[campo], dict) and 'valor_antigo' in alt_json[campo]:
                                                valor_anterior = alt_json[campo].get('valor_antigo')
                                            elif isinstance(alt_json[campo], dict) and 'valor_novo' in alt_json[campo]:
                                                valor_anterior = alt_json[campo].get('valor_novo')
                                    except Exception as e:
                                        logger.error(f"Erro ao processar histórico anterior (estratégia 1): {e}")
                            except Exception as e:
                                logger.error(f"Erro ao buscar histórico anterior (estratégia 1): {e}")
                            
                            # Estratégia 2: Se não encontrou, buscar o valor em qualquer alteração anterior
                            if valor_anterior is None:
                                try:
                                    cursor.execute("""
                                        SELECT alteracoes FROM historico 
                                        WHERE registro_id = ? AND data_alteracao < ?
                                        ORDER BY data_alteracao DESC
                                    """, (registro_id, alteracao.get('data_hora', '')))
                                    
                                    historicos = cursor.fetchall()
                                    for hist in historicos:
                                        try:
                                            alt_json = json.loads(hist['alteracoes'].replace("'", '"'))
                                            if campo in alt_json:
                                                if isinstance(alt_json[campo], dict) and 'valor_novo' in alt_json[campo]:
                                                    valor_anterior = alt_json[campo].get('valor_novo')
                                                    break
                                        except:
                                            continue
                                except Exception as e:
                                    logger.error(f"Erro ao buscar histórico anterior (estratégia 2): {e}")
                            
                            # Se ainda não encontrou, usar mensagem padrão
                            if valor_anterior is None:
                                valor_anterior = 'Valor anterior não disponível'
                            
                            # Se o campo for numero_sm ou numero_ae e o valor atual for vazio, usar 'N/A'
                            if campo in ['numero_sm', 'numero_ae'] and (valor_atual == '' or valor_atual is None):
                                valor_atual = 'N/A'
                            
                            # Se o campo for observacao_gr e o valor atual for vazio, usar 'Vazio'
                            if campo == 'observacao_gr' and (valor_atual == '' or valor_atual is None):
                                valor_atual = 'Vazio'
                            
                            alteracoes_formatadas.append({
                                'campo': campo,
                                'valor_antigo': str(valor_anterior),
                                'valor_novo': str(valor_atual),
                                'data_alteracao': alteracao.get('data_hora', ''),
                                'usuario': alteracao.get('usuario', 'Sistema')
                            })
        
        # Se ainda não tiver alterações, criar uma entrada para cada alteração
        if not alteracoes_formatadas:
            for alteracao in alteracoes:
                alteracoes_formatadas.append({
                    'campo': 'Registro',
                    'valor_antigo': 'Não disponível',
                    'valor_novo': 'Alteração registrada',
                    'data_alteracao': alteracao.get('data_hora', ''),
                    'usuario': alteracao.get('usuario', 'Sistema')
                })
        
        # Ordenar alterações por data (mais recente primeiro)
        alteracoes_formatadas.sort(key=lambda x: x.get('data_alteracao', ''), reverse=True)
        
        # Fechar a conexão com o banco de dados
        if conn:
            conn.close()
        
        logger.info(f"Retornando {len(alteracoes_formatadas)} alterações formatadas para o registro {registro_id}")
        
        return jsonify({
            "registro_info": registro_info,
            "alteracoes": alteracoes_formatadas,
            "success": True
        })
    
    except Exception as e:
        # Fechar a conexão com o banco de dados em caso de erro
        if conn:
            conn.close()
        
        logger.error(f"Erro ao obter histórico de alterações: {e}")
        return jsonify({"error": str(e), "success": False}), 500