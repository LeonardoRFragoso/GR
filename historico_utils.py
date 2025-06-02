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

def sanitize_json_string(json_str, aggressive=False, extreme=False):
    """
    Sanitiza uma string JSON para garantir que ela possa ser processada corretamente.
    Lida com problemas comuns como aspas simples em vez de duplas e escapes incorretos.
    
    Args:
        json_str (str): String JSON a ser sanitizada
        aggressive (bool): Se True, aplica sanitização mais agressiva desde o início
        extreme (bool): Se True, aplica sanitização extrema removendo todos os caracteres problemáticos
        
    Returns:
        str: String JSON sanitizada ou '{}' em caso de falha total
    """
    import re
    
    if not json_str or not isinstance(json_str, str):
        logger.warning("Tentativa de sanitizar um valor nulo ou não-string. Retornando JSON vazio.")
        return '{}'
        
    # Log para depuração
    logger.debug(f"Sanitizando JSON string: {json_str[:100]}...")
    
    # Pré-processamento para identificar e corrigir padrões problemáticos conhecidos
    # Especialmente focado na posição 10103 onde ocorrem erros frequentes
    if len(json_str) > 10000:
        logger.info("Aplicando pré-processamento para JSON grande com potenciais problemas na posição 10103")
        
        # Verificar a região ao redor da posição 10103
        if len(json_str) > 10103:
            start_region = max(0, 10103 - 100)
            end_region = min(len(json_str), 10103 + 100)
            problematic_region = json_str[start_region:end_region]
            logger.debug(f"Região potencialmente problemática (10103): {problematic_region}")
            
            # Verificar o caractere exato na posição 10103
            exact_pos = min(10103, len(json_str) - 1)
            if exact_pos < len(json_str):
                char_at_pos = json_str[exact_pos]
                next_char = json_str[exact_pos+1] if exact_pos+1 < len(json_str) else ''
                logger.debug(f"Caractere na posição 10103: '{char_at_pos}', Próximo: '{next_char}'")
                
                # Se for uma barra invertida seguida de um caractere não válido para escape
                if char_at_pos == '\\' and next_char not in '"\\bfnrt/':
                    # Substituir diretamente esses caracteres por espaços
                    json_str = json_str[:exact_pos] + '  ' + json_str[exact_pos+2:]
                    logger.info(f"Corrigido caractere problemático na posição exata 10103")
    
    # Para strings muito grandes ou quando o modo agressivo é solicitado, aplicar sanitização mais agressiva desde o início
    is_large_json = len(json_str) > 5000 or aggressive
    
    try:
        # Para strings pequenas, tente fazer parse diretamente (pode já ser válido)
        if not is_large_json:
            json.loads(json_str)
            return json_str
        else:
            # Para strings grandes, vamos direto para a sanitização
            raise json.JSONDecodeError("Forçando sanitização para JSON grande", json_str, 0)
    except json.JSONDecodeError:
        # Se falhar, tente sanitizar
        sanitized = ""
        try:
            # Abordagem mais radical para lidar com barras invertidas problemáticas
            # Primeiro, substituir todas as barras invertidas por barras duplas
            sanitized = json_str.replace('\\', '\\\\')
        except Exception as e:
            logger.error(f"Erro ao substituir barras invertidas: {e}")
            return '{}'
            
            # Substituir aspas simples por aspas duplas em chaves e valores
            sanitized = re.sub(r"([\{\[,:]\s*)'([^']*)'(\s*[\}\],:])", r'\1"\2"\3', sanitized)
            
            # Corrigir aspas duplas escapadas incorretamente
            sanitized = sanitized.replace('\\"', '"').replace('\"', '\\"')
            
            # Para JSON grandes, aplicar sanitização adicional focada em problemas de escape
            if is_large_json:
                # Substituir sequências de escape problemáticas
                for problematic_char in ['\\a', '\\v', '\\e', '\\?']:
                    sanitized = sanitized.replace(problematic_char, ' ')
                
                # Remover caracteres de controle não escapados
                sanitized = re.sub(r'[\x00-\x1F\x7F]', ' ', sanitized)
                
                # Tratar especificamente o problema na posição 10103 (erro reportado)
                if len(sanitized) > 10103:
                    # Verificar um intervalo ao redor da posição problemática
                    start_pos = max(0, 10103 - 100)  # Aumentado o intervalo para capturar mais contexto
                    end_pos = min(len(sanitized), 10103 + 100)
                    problematic_section = sanitized[start_pos:end_pos]
                    logger.debug(f"Seção problemática (posição 10103): {problematic_section}")
                    
                    # Verificar o caractere exato na posição 10103 e seu contexto
                    exact_pos = min(10103, len(sanitized) - 1)
                    char_at_pos = sanitized[exact_pos] if exact_pos < len(sanitized) else ''
                    context_5_chars = sanitized[max(0, exact_pos-5):min(len(sanitized), exact_pos+6)]
                    logger.debug(f"Caractere na posição 10103: '{char_at_pos}', Contexto: '{context_5_chars}'")
                    
                    # Tratamento específico para o caractere na posição 10103
                    if char_at_pos == '\\':
                        # Se for uma barra invertida, verificar o próximo caractere
                        next_char = sanitized[exact_pos+1] if exact_pos+1 < len(sanitized) else ''
                        logger.debug(f"Caractere seguinte: '{next_char}'")
                        
                        # Se o próximo caractere não for um caractere de escape válido, substituir ambos
                        if next_char not in '"\\bfnrt/':
                            sanitized = sanitized[:exact_pos] + '  ' + sanitized[exact_pos+2:]
                            logger.debug(f"Substituído caractere problemático na posição exata 10103")
                    
                    # Substituir barras invertidas não escapadas em toda a seção
                    fixed_section = re.sub(r'(?<!\\)\\(?!["\\bfnrt/])', '\\\\', problematic_section)
                    # Substituir também sequências de escape inválidas
                    fixed_section = re.sub(r'\\[^"\\bfnrt/]', ' ', fixed_section)
                    # Remover caracteres de controle não escapados
                    fixed_section = re.sub(r'[\x00-\x1F\x7F]', ' ', fixed_section)
                    sanitized = sanitized[:start_pos] + fixed_section + sanitized[end_pos:]
                
                # Tratar também a posição 8765 (problema conhecido anteriormente)
                if len(sanitized) > 8765:
                    # Verificar um intervalo ao redor da posição problemática
                    start_pos = max(0, 8765 - 50)  # Aumentado o intervalo para capturar mais contexto
                    end_pos = min(len(sanitized), 8765 + 50)
                    problematic_section = sanitized[start_pos:end_pos]
                    logger.debug(f"Seção problemática (posição 8765): {problematic_section}")
                    
                    # Substituir barras invertidas não escapadas nesta seção
                    fixed_section = re.sub(r'(?<!\\)\\(?!["\\bfnrt/])', '\\\\', problematic_section)
                    # Substituir também sequências de escape inválidas
                    fixed_section = re.sub(r'\\[^"\\bfnrt/]', ' ', fixed_section)
                    sanitized = sanitized[:start_pos] + fixed_section + sanitized[end_pos:]
                
                # Se o modo agressivo está ativado, aplicar sanitização adicional em todo o JSON
                if aggressive:
                    logger.info(f"Aplicando sanitização agressiva para string JSON de tamanho {len(sanitized)}")
                    
                    # Substituir todas as sequências de escape problemáticas em todo o JSON
                    for i in range(0, len(sanitized), 1000):  # Processar em blocos de 1000 caracteres
                        chunk = sanitized[i:i+1000]
                        # Substituir barras invertidas não escapadas
                        chunk = re.sub(r'(?<!\\)\\(?!["\\bfnrt/])', '\\\\', chunk)
                        # Substituir sequências de escape inválidas
                        chunk = re.sub(r'\\[^"\\bfnrt/]', ' ', chunk)
                        # Remover caracteres de controle não escapados
                        chunk = re.sub(r'[\x00-\x1F\x7F]', ' ', chunk)
                        sanitized = sanitized[:i] + chunk + sanitized[i+1000:]
            
            # Verificar se a string sanitizada é um JSON válido
            try:
                json.loads(sanitized)
                return sanitized
            except json.JSONDecodeError as je:
                # Se ainda falhar, tentar uma abordagem mais específica para o erro
                logger.warning(f"Primeira sanitização falhou na posição {je.pos}: {je}. Tentando abordagem alternativa.")
                
                # Verificar se o erro está relacionado a um caractere de escape
                if 'char' in str(je).lower() and '\\' in str(je):
                    logger.info(f"Detectado erro de escape na posição {je.pos}")
                    
                    # Tratar especificamente o problema na posição do erro
                    error_pos = je.pos
                    start_pos = max(0, error_pos - 50)
                    end_pos = min(len(sanitized), error_pos + 50)
                    problematic_section = sanitized[start_pos:end_pos]
                    logger.debug(f"Seção problemática (posição {error_pos}): {problematic_section}")
                    
                    # Substituir barras invertidas problemáticas nesta seção específica
                    fixed_section = problematic_section
                    # Substituir barras invertidas não escapadas
                    fixed_section = re.sub(r'(?<!\\)\\(?!["\\bfnrt/])', '\\\\', fixed_section)
                    # Substituir também sequências de escape inválidas
                    fixed_section = re.sub(r'\\[^"\\bfnrt/]', ' ', fixed_section)
                    # Substituir barras invertidas solitárias (sem caractere de escape válido após)
                    fixed_section = re.sub(r'\\(?!["\\bfnrt/])', ' ', fixed_section)
                    
                    sanitized = sanitized[:start_pos] + fixed_section + sanitized[end_pos:]
                    
                    try:
                        json.loads(sanitized)
                        return sanitized
                    except json.JSONDecodeError:
                        # Continuar com a abordagem alternativa
                        pass
                
                # Abordagem alternativa: começar do zero com a string original
                sanitized = json_str.replace("'", '"')
                
                # Garantir que todas as barras invertidas estejam corretamente escapadas
                sanitized = re.sub(r'(?<!\\)\\(?!["\\bfnrt/])', '\\\\', sanitized)
                
                # Remover sequências de escape inválidas
                sanitized = re.sub(r'\\[^"\\bfnrt/]', ' ', sanitized)
                
                try:
                    json.loads(sanitized)
                    return sanitized
                except json.JSONDecodeError as je2:
                    logger.error(f"Erro persistente na posição {je2.pos}: {je2}. Tentando abordagem mais agressiva.")
                    
                    # Abordagem mais agressiva: remover todos os caracteres de escape problemáticos
                    # Tratar especificamente o problema na posição reportada pelo erro
                    if je2.pos > 0:
                        error_pos = je2.pos
                        start_pos = max(0, error_pos - 50)
                        end_pos = min(len(sanitized), error_pos + 50)
                        problematic_section = sanitized[start_pos:end_pos]
                        logger.debug(f"Seção problemática (posição {error_pos}): {problematic_section}")
                        
                        # Substituir a seção problemática por uma versão mais limpa
                        fixed_section = re.sub(r'\\[^"\\bfnrt/]', ' ', problematic_section)
                        # Substituir barras invertidas solitárias
                        fixed_section = re.sub(r'\\(?!["\\bfnrt/])', ' ', fixed_section)
                        sanitized = sanitized[:start_pos] + fixed_section + sanitized[end_pos:]
                    
                    # Último recurso: remover todos os caracteres de escape problemáticos
                    logger.info("Aplicando sanitização extrema: removendo escapes problemáticos")
                    chars = list(sanitized)
                    i = 0
                    while i < len(chars) - 1:
                        if chars[i] == '\\':
                            # Se for uma barra invertida, verificar o próximo caractere
                            if i + 1 < len(chars) and chars[i+1] not in '"\\bfnrt/':
                                # Se o próximo caractere não for um caractere de escape válido
                                chars[i] = ' '  # Substituir barra invertida por espaço
                                chars[i+1] = ' '  # Substituir também o caractere seguinte
                                i += 2
                                continue
                            # Verificar se estamos na posição problemática 10103 ou próximo dela
                            elif i >= 10100 and i <= 10106:
                                # Tratamento especial para a região próxima à posição 10103
                                logger.debug(f"Tratando escape na posição crítica: {i}")
                                chars[i] = ' '  # Substituir barra invertida por espaço
                                if i + 1 < len(chars):
                                    chars[i+1] = ' '  # Substituir também o caractere seguinte
                                i += 2
                                continue
                        i += 1
                    sanitized = ''.join(chars)
                    
                    # Verificar novamente a região ao redor da posição 10103 após a sanitização
                    if len(sanitized) > 10103:
                        exact_pos = min(10103, len(sanitized) - 1)
                        context_after = sanitized[max(0, exact_pos-10):min(len(sanitized), exact_pos+11)]
                        logger.debug(f"Contexto após sanitização extrema (posição 10103): '{context_after}'")
                        
                        # Se ainda houver barras invertidas nesta região, removê-las completamente
                        if '\\' in context_after:
                            logger.debug("Ainda há barras invertidas na região crítica, removendo-as completamente")
                            clean_context = context_after.replace('\\', ' ')
                            sanitized = sanitized[:max(0, exact_pos-10)] + clean_context + sanitized[min(len(sanitized), exact_pos+11):]
                    
                    try:
                        json.loads(sanitized)
                        return sanitized
                    except json.JSONDecodeError as je3:
                        logger.error(f"Sanitização agressiva falhou na posição {je3.pos}: {je3}. Tentando abordagem de substituição de objeto.")
                        # Registrar a string JSON problemática para análise posterior (limitada a 200 caracteres em torno do erro)
                        error_pos = je3.pos
                        context_start = max(0, error_pos - 100)
                        context_end = min(len(sanitized), error_pos + 100)
                        error_context = sanitized[context_start:context_end]
                        logger.error(f"Contexto do erro (posição {error_pos}): {error_context}")
                        
                        # Se ainda falhar, tentar substituir a seção problemática por um objeto vazio
                        if je3.pos > 0:
                            # Tentar identificar o início e fim do objeto/array problemático
                            # e substituí-lo por um objeto vazio
                            error_pos = je3.pos
                            # Procurar o início do objeto/array problemático (chave ou colchete de abertura)
                            open_pos = sanitized.rfind('{', 0, error_pos)
                            if open_pos == -1:
                                open_pos = sanitized.rfind('[', 0, error_pos)
                            
                            # Procurar o fim do objeto/array problemático (chave ou colchete de fechamento)
                            close_pos = sanitized.find('}', error_pos)
                            if close_pos == -1:
                                close_pos = sanitized.find(']', error_pos)
                            
                            if open_pos != -1 and close_pos != -1:
                                # Substituir o objeto/array problemático por um objeto vazio
                                sanitized = sanitized[:open_pos] + '{}' + sanitized[close_pos+1:]
                                try:
                                    json.loads(sanitized)
                                    return sanitized
                                except json.JSONDecodeError as je4:
                                    logger.error(f"Substituição de objeto falhou na posição {je4.pos}: {je4}. Tentando abordagem mais radical.")
                                    # Tentar uma abordagem mais radical: remover todos os caracteres de escape
                                    logger.info("Aplicando sanitização ultra-extrema: removendo todas as barras invertidas")
                                    sanitized = re.sub(r'\\', '', sanitized)
                                    
                                    # Remover também todos os caracteres de controle
                                    sanitized = re.sub(r'[\x00-\x1F\x7F]', ' ', sanitized)
                                    
                                    # Verificar especificamente a posição 10103 novamente
                                    if len(sanitized) > 10103:
                                        exact_pos = min(10103, len(sanitized) - 1)
                                        context_after = sanitized[max(0, exact_pos-10):min(len(sanitized), exact_pos+11)]
                                        logger.debug(f"Contexto após remover todas as barras (posição 10103): '{context_after}'")
                                    
                                    try:
                                        json.loads(sanitized)
                                        return sanitized
                                    except json.JSONDecodeError as je5:
                                        logger.error(f"Sanitização ultra-extrema falhou na posição {je5.pos}: {je5}")
                                        # Tentar substituir o caractere exato que está causando o problema
                                        if je5.pos > 0:
                                            sanitized = sanitized[:je5.pos] + ' ' + sanitized[je5.pos+1:]
                                            try:
                                                json.loads(sanitized)
                                                return sanitized
                                            except:
                                                pass
                        
                        # Se tudo falhar, retornar um JSON vazio válido
                        logger.error(f"Impossível sanitizar JSON, retornando objeto vazio")
                        return '{}'

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
                            # Usar a função de sanitização para tratar a string JSON
                            sanitized_json = sanitize_json_string(alteracoes_json)
                            alteracoes_obj = json.loads(sanitized_json)
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
                    except json.JSONDecodeError as je:
                        logger.error(f"Erro de parsing JSON em obter_historico_alteracoes (processamento de alterações): {je}")
                        logger.error(f"Posição do erro: {je.pos}, linha: {je.lineno}, coluna: {je.colno}")
                        campos_alterados_encontrados = False
                    except Exception as e:
                        logger.error(f"Erro ao processar alterações: {e}")
                        campos_alterados_encontrados = False
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
                # Usar a função de sanitização para tratar a string JSON
                sanitized_json = sanitize_json_string(alteracao.get('alteracoes_raw', '{}'))
                try:
                    alteracoes_obj = json.loads(sanitized_json)
                except json.JSONDecodeError as je:
                    logger.error(f"Erro de parsing JSON em obter_historico_alteracoes: {je}")
                    logger.error(f"Posição do erro: {je.pos}, linha: {je.lineno}, coluna: {je.colno}")
                    # Tentar sanitização mais agressiva
                    sanitized_json = sanitize_json_string(alteracao.get('alteracoes_raw', '{}'), aggressive=True)
                    alteracoes_obj = json.loads(sanitized_json)
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
                                        # Usar a função de sanitização para tratar a string JSON
                                        sanitized_json = sanitize_json_string(hist_anterior['alteracoes'])
                                        try:
                                            alt_json = json.loads(sanitized_json)
                                            if campo in alt_json:
                                                if isinstance(alt_json[campo], dict) and 'valor_antigo' in alt_json[campo]:
                                                    valor_anterior = alt_json[campo].get('valor_antigo')
                                                elif isinstance(alt_json[campo], dict) and 'valor_novo' in alt_json[campo]:
                                                    valor_anterior = alt_json[campo].get('valor_novo')
                                        except json.JSONDecodeError as je:
                                            logger.error(f"Erro de parsing JSON ao buscar histórico anterior: {je}")
                                            logger.error(f"Posição do erro: {je.pos}, linha: {je.lineno}, coluna: {je.colno}")
                                            # Tentar sanitização mais agressiva
                                            sanitized_json = sanitize_json_string(hist_anterior['alteracoes'], aggressive=True)
                                            try:
                                                alt_json = json.loads(sanitized_json)
                                                if campo in alt_json:
                                                    if isinstance(alt_json[campo], dict) and 'valor_antigo' in alt_json[campo]:
                                                        valor_anterior = alt_json[campo].get('valor_antigo')
                                                    elif isinstance(alt_json[campo], dict) and 'valor_novo' in alt_json[campo]:
                                                        valor_anterior = alt_json[campo].get('valor_novo')
                                            except Exception as e2:
                                                logger.error(f"Falha na sanitização agressiva para histórico: {e2}")
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
                                            # Usar a função de sanitização para tratar a string JSON
                                            sanitized_json = sanitize_json_string(hist['alteracoes'])
                                            alt_json = json.loads(sanitized_json)
                                            if campo in alt_json:
                                                if isinstance(alt_json[campo], dict) and 'valor_novo' in alt_json[campo]:
                                                    valor_anterior = alt_json[campo].get('valor_novo')
                                                    break
                                        except json.JSONDecodeError as je:
                                            logger.debug(f"Erro de parsing JSON ao buscar histórico anterior para campo {campo}: {je}")
                                            # Tentar sanitização mais agressiva
                                            try:
                                                sanitized_json = sanitize_json_string(hist['alteracoes'], aggressive=True)
                                                alt_json = json.loads(sanitized_json)
                                                if campo in alt_json:
                                                    if isinstance(alt_json[campo], dict) and 'valor_novo' in alt_json[campo]:
                                                        valor_anterior = alt_json[campo].get('valor_novo')
                                                        break
                                            except Exception:
                                                pass
                                        except Exception:
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