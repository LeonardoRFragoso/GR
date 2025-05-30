from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
import sqlite3
import logging
import os
import re
import json
from datetime import datetime, timedelta
from functools import wraps

# Configurar logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Constantes para nomes de tabelas
TABLE_REGISTROS = 'registros'
TABLE_HISTORICO = 'historico'
TABLE_USUARIOS = 'usuarios'

# Constantes para nomes de colunas frequentemente usadas
COL_ID = 'id'
COL_EXCLUIDO = 'excluido'
COL_NUMERO_SM = 'numero_sm'
COL_NUMERO_AE = 'numero_ae'
COL_DATA_SM = 'data_sm'
COL_DATA_AE = 'data_ae'
COL_DATA_REGISTRO = 'data_registro'
COL_DATA_MODIFICACAO = 'data_modificacao'
COL_ALTERACOES_VERIFICADAS = 'alteracoes_verificadas'
COL_MODIFICADO_POR = 'modificado_por'
COL_OBSERVACAO_GR = 'observacao_gr'
COL_CONTAINER_1 = 'container_1'

# Constantes para status
STATUS_PENDENTE = 'Pendente'
STATUS_EM_ANDAMENTO = 'Em andamento'
STATUS_CONCLUIDO = 'Concluído'

# Constantes para níveis de usuário
NIVEL_GR = 'gr'
NIVEL_ADMIN = 'admin'

# Constantes para tipos de alteração
ALTERACAO_EDICAO_GR = 'Edição GR'
ALTERACAO_VERIFICACAO = 'Verificação de Alterações'

# Constantes para mensagens de erro/aviso comuns
MSG_REGISTRO_NAO_ENCONTRADO = 'Registro não encontrado.'
MSG_TABELA_HISTORICO_NAO_ENCONTRADA = 'Tabela de histórico não encontrada, não é possível verificar alterações por campo'
MSG_NENHUM_CAMPO_MONITORADO = 'Nenhum campo monitorado encontrado na tabela registros'

# Criar blueprint para rotas GR
gr_blueprint = Blueprint('gr', __name__, url_prefix='/gr')  # Nome 'gr' para manter compatibilidade com o new_app.py

# Função para formatar data no padrão brasileiro
def formatar_data_br(valor):
    if not valor:
        return ""
    
    # Substituir 'T' por espaço para formato ISO
    valor = valor.replace('T', ' ')
    
    # Verificar se é uma data completa com hora
    if ' ' in valor:
        data_parte, hora_parte = valor.split(' ', 1)
    else:
        data_parte, hora_parte = valor, ''
    
    # Verificar se a data está no formato yyyy-mm-dd
    if re.match(r'\d{4}-\d{2}-\d{2}', data_parte):
        # Converter de yyyy-mm-dd para dd-mm-yyyy
        ano, mes, dia = data_parte.split('-')
        data_formatada = f"{dia}-{mes}-{ano}"
    else:
        data_formatada = data_parte
    
    # Formatar a hora para garantir que tenha segundos (HH:MM:SS)
    if hora_parte:
        # Se a hora já tem o formato completo HH:MM:SS, use-a diretamente
        if re.match(r'\d{2}:\d{2}:\d{2}', hora_parte):
            hora_formatada = hora_parte
        # Se a hora tem apenas HH:MM, adicione os segundos
        elif re.match(r'\d{2}:\d{2}', hora_parte):
            hora_formatada = f"{hora_parte}:00"
        else:
            hora_formatada = hora_parte
        
        # Manter o formato HH:MM:SS DD-MM-AAAA
        return f"{hora_formatada} {data_formatada}"
    else:
        return data_formatada

# Registrar o filtro para uso nos templates
gr_blueprint.add_app_template_filter(formatar_data_br, 'formatar_data_br')

# Classe para gerenciar conexão com o banco de dados usando contexto
class DatabaseConnection:
    """Classe para gerenciar conexão com o banco de dados usando o padrão de contexto.
    
    Exemplo de uso:
        with DatabaseConnection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tabela")
    """
    def __init__(self, database='usuarios.db'):
        """Inicializa o gerenciador de conexão.
        
        Args:
            database (str, optional): Nome do arquivo do banco de dados. Padrão é 'usuarios.db'.
        """
        self.database = database
        self.conn = None
    
    def __enter__(self):
        """Estabelece a conexão ao entrar no contexto.
        
        Returns:
            sqlite3.Connection: Objeto de conexão com o banco de dados.
            
        Raises:
            sqlite3.Error: Se ocorrer um erro ao conectar ao banco de dados.
        """
        try:
            self.conn = sqlite3.connect(self.database)
            self.conn.row_factory = sqlite3.Row
            return self.conn
        except sqlite3.Error as e:
            logger.error(f"Erro ao conectar ao banco de dados {self.database}: {e}")
            raise
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Fecha a conexão ao sair do contexto.
        
        Args:
            exc_type: Tipo da exceção, se ocorrer.
            exc_val: Valor da exceção, se ocorrer.
            exc_tb: Traceback da exceção, se ocorrer.
        """
        if self.conn:
            if exc_type is not None:
                # Se ocorreu uma exceção, fazer rollback
                self.conn.rollback()
                logger.error(f"Transação revertida devido a erro: {exc_val}")
            else:
                # Se não ocorreu exceção, fazer commit
                try:
                    self.conn.commit()
                except Exception as e:
                    self.conn.rollback()
                    logger.error(f"Erro ao fazer commit: {e}")
            self.conn.close()

# Função para conectar ao banco de dados (mantida para compatibilidade)
def get_db_connection(database='usuarios.db'):
    """Estabelece uma conexão com o banco de dados SQLite.
    
    Args:
        database (str, optional): Nome do arquivo do banco de dados. Padrão é 'usuarios.db'.
        
    Returns:
        sqlite3.Connection: Objeto de conexão com o banco de dados.
        
    Raises:
        sqlite3.Error: Se ocorrer um erro ao conectar ao banco de dados.
    """
    try:
        conn = sqlite3.connect(database)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.error(f"Erro ao conectar ao banco de dados {database}: {e}")
        raise

# Funu00e7u00e3o auxiliar para converter resultados de consulta em dicionu00e1rios
def fetchone_dict(cursor):
    row = cursor.fetchone()
    if row is None:
        return None
    return dict((cursor.description[i][0], value) for i, value in enumerate(row))

# Função auxiliar para obter registros com alterações pós SM/AE
def get_registros_com_alteracoes_pos_smae(cursor, colunas):
    """Função auxiliar para obter registros com alterações pós SM/AE
    
    Args:
        cursor: Cursor do banco de dados
        colunas: Lista de colunas da tabela registros
        
    Returns:
        tuple: (registros_alterados, alteracoes_pos_smae)
    """
    registros_alterados = []
    alteracoes_pos_smae = 0
    
    # Lista de campos a serem monitorados após inclusão de SM/AE
    campos_monitorados = [
        'usuario', 'placa', 'motorista', 'cpf', 'mot_loc', 'carreta', 'carreta1', 'carreta2',
        'carreta_loc', 'cliente', 'loc_cliente', 'arquivo', 'container_1', 'container_2',
        'status_sm', 'tipo_carga', 'status_container', 'modalidade', 'gerenciadora',
        'booking_di', 'pedido_referencia', 'lote_cs', 'on_time_cliente', 'horario_previsto',
        'observacao_operacional', 'observacao_gr', 'destino_intermediario', 'destino_final',
        'anexar_nf', 'anexar_os', 'anexar_agendamento', 'numero_nf', 'serie', 'quantidade',
        'peso_bruto', 'valor_total_nota', 'unidade', 'arquivo_nf_nome', 'arquivo_os_nome',
        'arquivo_agendamento_nome', 'origem'
    ]
    
    # Verificar quais desses campos existem na tabela
    campos_existentes = [campo for campo in campos_monitorados if campo in colunas]
    
    if not campos_existentes:
        logger.warning("Nenhum campo monitorado encontrado na tabela registros")
        return registros_alterados, alteracoes_pos_smae
    
    try:
        # Verificar se a tabela histórico existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='historico'")
        tabela_historico_existe = cursor.fetchone() is not None
        
        # Verificar se a coluna alteracoes_verificadas existe
        coluna_alteracoes_verificadas_existe = 'alteracoes_verificadas' in colunas
        
        if tabela_historico_existe:
            # Construir consulta para verificar alterações nos campos monitorados
            campos_clausula = " OR ".join([f"h.alteracoes LIKE '%{campo}%'" for campo in campos_existentes])
            
            # Consulta para obter registros com alterações pós SM/AE usando histórico
            # Modificada para excluir alterações feitas pelo usuário GR (inclusão de SM/AE)
            cursor.execute(f"""
                SELECT DISTINCT r.* 
                FROM registros r
                JOIN historico h ON r.id = h.registro_id
                WHERE ((r.numero_sm IS NOT NULL AND r.numero_sm != '' AND r.numero_sm != '0') 
                   OR (r.numero_ae IS NOT NULL AND r.numero_ae != '' AND r.numero_ae != '0'))
                AND r.excluido = 0
                AND {'r.alteracoes_verificadas = 0' if coluna_alteracoes_verificadas_existe else '1=1'}
                AND h.data_alteracao > 
                    CASE 
                        WHEN r.data_sm IS NOT NULL AND r.data_sm > r.data_ae THEN r.data_sm
                        WHEN r.data_ae IS NOT NULL THEN r.data_ae
                        ELSE r.data_sm
                    END
                AND ({campos_clausula})
                AND h.alterado_por NOT IN (SELECT username FROM usuarios WHERE nivel = 'gr')
                AND h.alteracoes NOT LIKE '%"tipo": "Edição GR"%'
                AND h.alteracoes NOT LIKE '%numero_sm%'
                AND h.alteracoes NOT LIKE '%numero_ae%'
            """)
            registros_alterados = [dict(row) for row in cursor.fetchall()]
        elif coluna_alteracoes_verificadas_existe:
            # Fallback: usar apenas a coluna alteracoes_verificadas se não houver tabela histórico
            # Neste caso, não temos como filtrar por quem fez a alteração, então usamos apenas o flag
            cursor.execute("""
                SELECT * FROM registros 
                WHERE ((numero_sm IS NOT NULL AND numero_sm != '' AND numero_sm != '0') 
                    OR (numero_ae IS NOT NULL AND numero_ae != '' AND numero_ae != '0'))
                AND excluido = 0 
                AND alteracoes_verificadas = 0
            """)
            registros_alterados = [dict(row) for row in cursor.fetchall()]
        else:
            logger.warning("Nem tabela histórico nem coluna alteracoes_verificadas encontradas")
        
        alteracoes_pos_smae = len(registros_alterados)
        logger.info(f"Obtidos {alteracoes_pos_smae} registros com alterações pós SM/AE")
        logger.debug(f"Filtro alteracoes_pos_smae: {bool(registros_alterados)}")
        logger.debug(f"Total de registros obtidos: {len(registros_alterados)}")
        logger.debug(f"Total de registros alterados: {alteracoes_pos_smae}")
    except Exception as e:
        logger.error(f"Erro ao obter registros com alterações pós SM/AE: {e}")
    
    return registros_alterados, alteracoes_pos_smae

# Função auxiliar para obter contagens básicas de registros
def get_contagens_basicas(cursor):
    """Função auxiliar para obter contagens básicas de registros
    
    Args:
        cursor: Cursor do banco de dados
        
    Returns:
        dict: Dicionário com as contagens básicas
    """
    contagens = {}
    
    # Contagens por status_sm
    cursor.execute("SELECT COUNT(*) FROM registros WHERE status_sm = 'Pendente' AND excluido = 0")
    contagens['registros_pendentes'] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM registros WHERE status_sm = 'Em andamento' AND excluido = 0")
    contagens['registros_andamento'] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM registros WHERE status_sm = 'Concluído' AND excluido = 0")
    contagens['registros_concluidos'] = cursor.fetchone()[0]
    
    # Contagem de registros sem container
    cursor.execute("SELECT COUNT(*) FROM registros WHERE (container_1 IS NULL OR container_1 = '') AND excluido = 0")
    contagens['sem_container'] = cursor.fetchone()[0]
    
    # Contagem de registros sem SM
    cursor.execute("""
        SELECT COUNT(*) 
        FROM registros 
        WHERE (numero_sm IS NULL OR numero_sm = '') 
        AND excluido = 0
    """)
    contagens['sem_sm'] = cursor.fetchone()[0]
    
    # Contagem de registros sem AE
    cursor.execute("""
        SELECT COUNT(*) 
        FROM registros 
        WHERE (numero_ae IS NULL OR numero_ae = '') 
        AND excluido = 0
    """)
    contagens['sem_ae'] = cursor.fetchone()[0]
    
    # Contagem de registros sem NF anexada
    cursor.execute("""
        SELECT COUNT(*) 
        FROM registros 
        WHERE (anexar_nf IS NULL OR anexar_nf = 0 OR anexar_nf = '') 
        AND excluido = 0
    """)
    contagens['sem_nf'] = cursor.fetchone()[0]
    
    # Contagem de registros sem OS anexada
    cursor.execute("""
        SELECT COUNT(*) 
        FROM registros 
        WHERE (anexar_os IS NULL OR anexar_os = 0 OR anexar_os = '') 
        AND excluido = 0
    """)
    contagens['sem_os'] = cursor.fetchone()[0]
    
    return contagens

# Função auxiliar para calcular tempos médios
def calcular_tempos_medios(cursor):
    """Função auxiliar para calcular tempos médios entre etapas
    
    Args:
        cursor: Cursor do banco de dados
        
    Returns:
        dict: Dicionário com os tempos médios formatados
    """
    tempos = {}
    
    # Calcular tempo médio entre data_registro e horario_previsto (se disponível)
    cursor.execute("""
        SELECT AVG(julianday(horario_previsto) - julianday(data_registro)) 
        FROM registros 
        WHERE horario_previsto IS NOT NULL AND data_registro IS NOT NULL AND excluido = 0
    """)
    tempo_medio_inicio_dias = cursor.fetchone()[0]
    if tempo_medio_inicio_dias is not None:
        tempos['tempo_medio_inicio'] = f"{tempo_medio_inicio_dias:.1f} dias"
    else:
        tempos['tempo_medio_inicio'] = "N/A"
    
    # Calcular tempo médio entre horario_previsto e on_time_cliente (se disponível)
    cursor.execute("""
        SELECT AVG(julianday(on_time_cliente) - julianday(horario_previsto)) 
        FROM registros 
        WHERE on_time_cliente IS NOT NULL AND horario_previsto IS NOT NULL AND excluido = 0
    """)
    tempo_medio_conclusao_dias = cursor.fetchone()[0]
    if tempo_medio_conclusao_dias is not None:
        tempos['tempo_medio_conclusao'] = f"{tempo_medio_conclusao_dias:.1f} dias"
    else:
        tempos['tempo_medio_conclusao'] = "N/A"
    
    return tempos

# Função auxiliar para verificar e criar colunas necessárias
def verificar_criar_colunas(conn, cursor):
    """Função auxiliar para verificar e criar colunas necessárias na tabela registros
    
    Args:
        conn: Conexão com o banco de dados
        cursor: Cursor do banco de dados
        
    Returns:
        list: Lista atualizada de colunas da tabela registros
    """
    # Obter informações sobre as colunas da tabela registros
    cursor.execute(f"PRAGMA table_info({TABLE_REGISTROS})")
    colunas = [col[1] for col in cursor.fetchall()]
    
    # Verificar se a coluna 'alteracoes_verificadas' existe, se não, criar
    if COL_ALTERACOES_VERIFICADAS not in colunas:
        try:
            cursor.execute(f"ALTER TABLE {TABLE_REGISTROS} ADD COLUMN {COL_ALTERACOES_VERIFICADAS} INTEGER DEFAULT 0")
            conn.commit()
            logger.info(f"Coluna '{COL_ALTERACOES_VERIFICADAS}' adicionada à tabela {TABLE_REGISTROS}")
            # Atualizar a lista de colunas após adicionar a nova coluna
            cursor.execute(f"PRAGMA table_info({TABLE_REGISTROS})")
            colunas = [col[1] for col in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Erro ao adicionar coluna '{COL_ALTERACOES_VERIFICADAS}': {e}")
    
    # Verificar se a coluna 'modificado_por' existe, se não, criar
    if COL_MODIFICADO_POR not in colunas:
        try:
            cursor.execute(f"ALTER TABLE {TABLE_REGISTROS} ADD COLUMN {COL_MODIFICADO_POR} TEXT")
            conn.commit()
            logger.info(f"Coluna '{COL_MODIFICADO_POR}' adicionada à tabela {TABLE_REGISTROS}")
            # Atualizar a lista de colunas após adicionar a nova coluna
            cursor.execute(f"PRAGMA table_info({TABLE_REGISTROS})")
            colunas = [col[1] for col in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Erro ao adicionar coluna '{COL_MODIFICADO_POR}': {e}")
    
    return colunas

# Função auxiliar para formatar dados para exibição
def formatar_dados_exibicao(valor, tipo='texto'):
    """Formata dados para exibição na interface
    
    Args:
        valor: Valor a ser formatado
        tipo: Tipo de formatação ('texto', 'data', 'numero', 'moeda')
        
    Returns:
        str: Valor formatado para exibição
    """
    if valor is None:
        return ""
    
    try:
        if tipo == 'data':
            # Verificar se a data está no formato ISO
            if isinstance(valor, str) and re.match(r'\d{4}-\d{2}-\d{2}', valor):
                # Converter para o formato brasileiro
                partes = valor.split(' ', 1)
                data = partes[0]
                hora = partes[1] if len(partes) > 1 else ''
                
                ano, mes, dia = data.split('-')
                data_formatada = f"{dia}/{mes}/{ano}"
                
                if hora:
                    return f"{data_formatada} {hora}"
                return data_formatada
            return valor
        
        elif tipo == 'numero':
            # Formatar número com separador de milhares
            try:
                numero = float(valor)
                return f"{numero:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            except (ValueError, TypeError):
                return valor
        
        elif tipo == 'moeda':
            # Formatar valor monetário
            try:
                valor_num = float(valor)
                return f"R$ {valor_num:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            except (ValueError, TypeError):
                return valor
        
        else:  # tipo == 'texto' ou qualquer outro
            # Converter para string e remover espaços em branco extras
            return str(valor).strip()
    
    except Exception as e:
        logger.error(f"Erro ao formatar valor '{valor}' como {tipo}: {e}")
        return str(valor)

# Função auxiliar para registrar alterações no histórico
def registrar_historico(cursor, registro_id, tipo_alteracao, campos, valores=None, usuario=None, conn=None):
    """Função auxiliar para registrar alterações no histórico
    
    Args:
        cursor: Cursor do banco de dados
        registro_id: ID do registro alterado
        tipo_alteracao: Tipo de alteração (ex: 'Edição GR', 'Verificação de Alterações')
        campos: Lista de campos alterados
        valores: Dicionário com os valores alterados (opcional)
        usuario: Nome do usuário que fez a alteração (opcional, usa session['user'] se None)
        conn: Conexão com o banco de dados (opcional, se fornecido, fará commit das alterações)
        
    Returns:
        bool: True se o registro foi feito com sucesso, False caso contrário
    """
    try:
        # Verificar se a tabela histórico existe
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{TABLE_HISTORICO}'")
        if not cursor.fetchone():
            logger.warning(MSG_TABELA_HISTORICO_NAO_ENCONTRADA)
            return False
        
        # Usar o usuário da sessão se não for fornecido
        if usuario is None:
            usuario = session.get('user', 'Sistema')
        
        # Preparar o objeto de alterações
        alteracoes = {
            "tipo": tipo_alteracao,
            "campos": campos,
            "usuario": usuario
        }
        
        # Adicionar valores se fornecidos
        if valores:
            alteracoes["valores"] = valores
        
        # Registrar no histórico
        cursor.execute(f"""
            INSERT INTO {TABLE_HISTORICO} (registro_id, alterado_por, alteracoes, data_alteracao)
            VALUES (?, ?, ?, ?)
        """, (registro_id, usuario, json.dumps(alteracoes), datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        
        # Commit das alterações se a conexão foi fornecida
        if conn:
            conn.commit()
        
        return True
    except Exception as e:
        logger.error(f"Erro ao registrar histórico: {e}")
        return False

# Função auxiliar para validar dados de entrada
def validar_dados(dados, regras):
    """Valida dados de entrada de acordo com regras especificadas
    
    Args:
        dados: Dicionário com os dados a serem validados
        regras: Dicionário com as regras de validação no formato:
               {'campo': {'tipo': 'texto|data|numero', 'obrigatorio': True|False, 'min': valor, 'max': valor}}
    
    Returns:
        tuple: (valido, erros) onde valido é um booleano e erros é um dicionário de mensagens de erro
    """
    erros = {}
    
    for campo, regra in regras.items():
        valor = dados.get(campo)
        
        # Verificar se é obrigatório
        if regra.get('obrigatorio', False) and (valor is None or valor == ''):
            erros[campo] = f"O campo {campo} é obrigatório."
            continue
        
        # Se o campo não é obrigatório e está vazio, pular outras validações
        if valor is None or valor == '':
            continue
        
        # Validar tipo
        tipo = regra.get('tipo', 'texto')
        if tipo == 'numero':
            try:
                valor_num = float(valor)
                
                # Verificar valor mínimo
                if 'min' in regra and valor_num < regra['min']:
                    erros[campo] = f"O valor mínimo para {campo} é {regra['min']}."
                
                # Verificar valor máximo
                if 'max' in regra and valor_num > regra['max']:
                    erros[campo] = f"O valor máximo para {campo} é {regra['max']}."
            except ValueError:
                erros[campo] = f"O campo {campo} deve ser um número válido."
        
        elif tipo == 'data':
            # Verificar formato da data (YYYY-MM-DD)
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', valor):
                erros[campo] = f"O campo {campo} deve estar no formato YYYY-MM-DD."
            else:
                try:
                    # Verificar se é uma data válida
                    ano, mes, dia = map(int, valor.split('-'))
                    datetime(ano, mes, dia)
                    
                    # Verificar data mínima
                    if 'min' in regra:
                        data_min = datetime.strptime(regra['min'], '%Y-%m-%d')
                        data_valor = datetime.strptime(valor, '%Y-%m-%d')
                        if data_valor < data_min:
                            erros[campo] = f"A data mínima para {campo} é {regra['min']}."
                    
                    # Verificar data máxima
                    if 'max' in regra:
                        data_max = datetime.strptime(regra['max'], '%Y-%m-%d')
                        data_valor = datetime.strptime(valor, '%Y-%m-%d')
                        if data_valor > data_max:
                            erros[campo] = f"A data máxima para {campo} é {regra['max']}."
                except ValueError:
                    erros[campo] = f"O campo {campo} contém uma data inválida."
        
        elif tipo == 'texto':
            # Verificar comprimento mínimo
            if 'min' in regra and len(valor) < regra['min']:
                erros[campo] = f"O campo {campo} deve ter pelo menos {regra['min']} caracteres."
            
            # Verificar comprimento máximo
            if 'max' in regra and len(valor) > regra['max']:
                erros[campo] = f"O campo {campo} deve ter no máximo {regra['max']} caracteres."
    
    return len(erros) == 0, erros

# Decorador para verificar se o usuu00e1rio estu00e1 logado como GR ou admin
def gr_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        logger.info(f"Verificando acesso GR - Session: {session}")
        if 'user' not in session:
            logger.warning("Usuu00e1rio nu00e3o estu00e1 na sessu00e3o")
            flash('Por favor, fau00e7a login para acessar esta pu00e1gina.', 'warning')
            return redirect(url_for('auth.login'))
        
        nivel = session.get('nivel')
        logger.info(f"Nu00edvel do usuu00e1rio: {nivel}")
        
        if nivel not in ['gr', 'admin']:
            logger.warning(f"Acesso negado: nu00edvel {nivel} nu00e3o tem permissu00e3o")
            flash('Acesso restrito u00e0 Gestu00e3o de Relacionamento.', 'danger')
            return redirect(url_for('auth.login'))
        
        return f(*args, **kwargs)
    return decorated_function

# Rota principal - Ambiente GR
@gr_blueprint.route('/')
@gr_blueprint.route('/ambiente')
@gr_required
def ambiente():
    logger.info(f"Acessando ambiente GR - Session: {session}")
    
    # Inicializar variáveis com valores padrão
    registros = []
    registros_alterados = []
    total_registros = 0
    total_paginas = 1
    pagina_atual = 1
    alteracoes_pos_smae = 0
    sem_container = 0
    registros_pendentes = 0
    sem_ae_total = 0
    sem_nf_total = 0
    sem_os_total = 0
    tempo_medio_inicio = "N/A"
    tempo_medio_conclusao = "N/A"
    alteracoes_pos_smae_verificado = 0
    registros_andamento = 0
    registros_concluidos = 0
    filtro_sem_sm = False
    filtro_sem_ae = False
    filtro_sem_container = False
    filtro_sem_nf = False
    filtro_sem_os = False
    filtro_alteracoes_pos_smae = False
    page = 1
    
    # Função auxiliar para gerar URLs de paginação
    def gerar_url_paginacao(pagina):
        args = request.args.copy()
        args['page'] = pagina
        return url_for('gr.ambiente', **args)
    
    try:
        # Obter parâmetros de filtragem da URL
        page = request.args.get('page', 1, type=int)
        
        # Obter parâmetros de filtro dos checkboxes
        filtro_sem_sm = request.args.get('sem_sm', 'false') == 'true'
        filtro_sem_ae = request.args.get('sem_ae', 'false') == 'true'
        filtro_sem_container = request.args.get('sem_container', 'false') == 'true'
        filtro_sem_nf = request.args.get('sem_nf', 'false') == 'true'
        filtro_sem_os = request.args.get('sem_os', 'false') == 'true'
        
        # Obter parâmetros de filtro dos indicadores
        filtro_alteracoes_pos_smae = request.args.get('alteracoes_pos_smae', 'false') == 'true'
        
        # Conectar ao banco de dados
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Verificar e criar colunas necessárias usando a função auxiliar
            colunas = verificar_criar_colunas(conn, cursor)
            
            # Construir a consulta SQL base
            query = "SELECT * FROM registros WHERE excluido = 0"
            params = []
            
            # Aplicar filtros
            if filtro_sem_sm:
                query += " AND (numero_sm IS NULL OR numero_sm = '')"
            
            if filtro_sem_ae:
                query += " AND (numero_ae IS NULL OR numero_ae = '')"
            
            if filtro_sem_container:
                # Usar a coluna container_1
                query += " AND (container_1 IS NULL OR container_1 = '')"
                
            if filtro_sem_nf:
                query += " AND (anexar_nf IS NULL OR anexar_nf = '')"
                
            if filtro_sem_os:
                query += " AND (anexar_os IS NULL OR anexar_os = '')"
                
            if filtro_alteracoes_pos_smae:
                # Obter registros com alterações pós SM/AE usando a função auxiliar
                registros_alterados_filtro, _ = get_registros_com_alteracoes_pos_smae(cursor, colunas)
                
                if registros_alterados_filtro:
                    # Usar os IDs na consulta principal
                    registro_ids = [str(registro['id']) for registro in registros_alterados_filtro]
                    ids_str = ",".join(registro_ids)
                    query = f"SELECT * FROM registros WHERE id IN ({ids_str}) AND excluido = 0 ORDER BY id DESC"
                    params = []
                    logger.info(f"Filtro alterações pós SM/AE: Encontrados {len(registro_ids)} registros")
                else:
                    # Se não houver registros, usar uma condição que não retorne nada
                    query = "SELECT * FROM registros WHERE 1=0"
                    params = []
                    logger.info("Filtro alterações pós SM/AE: Nenhum registro encontrado")
                    
                # Verificar se a tabela histórico existe
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='historico'")
                if not cursor.fetchone():
                    # Fallback se a tabela histórico não existir
                    if 'alteracoes_verificadas' in colunas:
                        query += " AND ((numero_sm IS NOT NULL AND numero_sm != '' AND numero_sm != '0') OR (numero_ae IS NOT NULL AND numero_ae != '' AND numero_ae != '0')) AND alteracoes_verificadas = 0"
                    else:
                        query += " AND ((numero_sm IS NOT NULL AND numero_sm != '' AND numero_sm != '0') OR (numero_ae IS NOT NULL AND numero_ae != '' AND numero_ae != '0'))"
            
            # Adicionar ordenação se não for uma consulta personalizada
            if not query.strip().endswith("DESC"):
                query += " ORDER BY id DESC"
            
            # Contar total de registros para paginação
            count_query = query.replace("SELECT *", "SELECT COUNT(*)")
            cursor.execute(count_query, params)
            total_registros = cursor.fetchone()[0]
            
            # Calcular paginação
            itens_por_pagina = 20  # Aumentado de 10 para 20 registros por página
            total_paginas = (total_registros + itens_por_pagina - 1) // itens_por_pagina
            pagina_atual = min(page, total_paginas) if total_paginas > 0 else 1
            offset = (pagina_atual - 1) * itens_por_pagina
            
            # Adicionar limite e offset para paginação
            query += " LIMIT ? OFFSET ?"
            params.extend([itens_por_pagina, offset])
            
            # Executar a consulta final
            cursor.execute(query, params)
            registros = [dict(row) for row in cursor.fetchall()]
            
            # Obter registros com alterações pós SM/AE para destacar na tabela
            registros_alterados, alteracoes_pos_smae = get_registros_com_alteracoes_pos_smae(cursor, colunas)
            
            # Extrair os IDs dos registros alterados para facilitar a comparação no template
            registros_alterados_ids = [str(r['id']) for r in registros_alterados] if registros_alterados else []
            
            # Marcar os registros que estão na página atual e também na lista de alterados
            for registro in registros:
                registro['tem_alteracoes_pos_smae'] = str(registro['id']) in registros_alterados_ids
            
            # Registrar informações para debug
            logger.debug(f"Filtro alteracoes_pos_smae: {filtro_alteracoes_pos_smae}")
            logger.debug(f"Total de registros obtidos: {len(registros)}")
            logger.debug(f"Total de registros alterados: {alteracoes_pos_smae}")
            logger.debug(f"IDs de registros alterados: {registros_alterados_ids}")
            
            # Obter contagens básicas usando a função auxiliar
            contagens = get_contagens_basicas(cursor)
            registros_pendentes = contagens['registros_pendentes']
            registros_andamento = contagens['registros_andamento']
            registros_concluidos = contagens['registros_concluidos']
            sem_container = contagens['sem_container']
            sem_ae_total = contagens['sem_ae']
            sem_nf_total = contagens['sem_nf']
            sem_os_total = contagens['sem_os']
            
            # Calcular tempos médios usando a função auxiliar
            tempos = calcular_tempos_medios(cursor)
            tempo_medio_inicio = tempos['tempo_medio_inicio']
            tempo_medio_conclusao = tempos['tempo_medio_conclusao']
            
            # Usar a função auxiliar para obter a contagem de alterações nos campos específicos após inclusão de SM/AE
            _, alteracoes_pos_smae = get_registros_com_alteracoes_pos_smae(cursor, colunas)
                
            logger.info(f"Total de registros com alterações pós SM/AE: {alteracoes_pos_smae}")
            
            # Obter registros com alterações para exibir quando o filtro está ativo
            if filtro_alteracoes_pos_smae:
                # Usar a função auxiliar para obter os registros com alterações pós SM/AE
                registros_alterados, _ = get_registros_com_alteracoes_pos_smae(cursor, colunas)
                
                # Se não houver registros alterados e a tabela histórico não existir, usar fallback
                if not registros_alterados:
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='historico'")
                    if not cursor.fetchone():
                        # Fallback usando apenas a tabela registros
                        cursor.execute("""
                            SELECT * FROM registros 
                            WHERE ((numero_sm IS NOT NULL AND numero_sm != '' AND numero_sm != '0') 
                                  OR (numero_ae IS NOT NULL AND numero_ae != '' AND numero_ae != '0')) 
                            AND data_modificacao IS NOT NULL 
                            AND alteracoes_verificadas = 0
                            AND excluido = 0
                            ORDER BY data_modificacao DESC
                        """)
                        registros_alterados = [dict(row) for row in cursor.fetchall()]
                
                logger.info(f"Obtidos {len(registros_alterados)} registros com alterações pós SM/AE")
            
            # Verificar novamente as alterações nos campos SM/AE para garantir que o valor esteja correto
            # Usamos o valor já calculado, não precisamos recalcular
            alteracoes_pos_smae_verificado = alteracoes_pos_smae
        
        # Renderizar o template com todos os dados
        return render_template('gr_ambiente.html', 
                           usuario=session.get('user', 'Usuário'),
                           nivel=session.get('nivel', 'N/A'),
                           tempo_medio_conclusao=tempo_medio_conclusao,
                           tempo_medio_inicio=tempo_medio_inicio,
                           registros_pendentes=registros_pendentes,
                           registros_andamento=registros_andamento,
                            registros_concluidos=registros_concluidos,
                            sem_container=sem_container,
                            sem_sm=registros_pendentes,
                            sem_ae=sem_ae_total,
                            sem_nf=sem_nf_total,
                            sem_os=sem_os_total,
                            alteracoes_pos_smae=alteracoes_pos_smae_verificado,
                            registros=registros,
                            registros_alterados=registros_alterados,
                            registros_alterados_ids=registros_alterados_ids,  # Adicionado para facilitar comparação no template
                            page=page,
                            pagina_atual=pagina_atual,
                            total_paginas=total_paginas,
                            total_registros=total_registros,
                            filtro_sem_sm=filtro_sem_sm,
                            filtro_sem_ae=filtro_sem_ae,
                            filtro_sem_container=filtro_sem_container,
                            filtro_sem_nf=filtro_sem_nf,
                            filtro_sem_os=filtro_sem_os,
                            gerar_url_paginacao=gerar_url_paginacao)
                           
    except Exception as e:
        logger.error(f"Erro ao renderizar ambiente GR: {e}")
        flash(f"Erro ao carregar o ambiente: {str(e)}", "danger")
        return redirect(url_for('auth.login'))

# Rota para o dashboard GR
@gr_blueprint.route('/dashboard')
@gr_required
def dashboard():
    logger.info(f"Acessando dashboard GR - Session: {session}")
    
    try:
        # Obter parâmetros de filtro de data
        data_inicio = request.args.get('data_inicio', None)
        data_fim = request.args.get('data_fim', None)
        
        # Se não houver filtro de data, usar a semana atual como padrão
        if not data_inicio or not data_fim:
            from datetime import datetime, timedelta
            hoje = datetime.now()
            inicio_semana = hoje - timedelta(days=hoje.weekday())
            fim_semana = inicio_semana + timedelta(days=6)
            
            data_inicio = inicio_semana.strftime('%Y-%m-%d')
            data_fim = fim_semana.strftime('%Y-%m-%d')
        
        # Conectar ao banco de dados
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Obter as colunas disponíveis na tabela registros
            cursor.execute("PRAGMA table_info(registros)")
            colunas = [info[1] for info in cursor.fetchall()]
            logger.info(f"Colunas disponíveis na tabela registros: {colunas}")
            
            # 1. Tempo Médio AE (data de criação AE - data da criação registro ou ultima modificação)
            # Modificado para considerar apenas valores positivos
            cursor.execute("""
                SELECT AVG(tempo) as tempo_medio_ae
                FROM (
                    SELECT julianday(data_ae) - 
                        CASE 
                            WHEN data_modificacao IS NOT NULL AND data_modificacao > data_registro 
                            THEN julianday(data_modificacao) 
                            ELSE julianday(data_registro) 
                        END as tempo
                    FROM registros
                    WHERE data_ae IS NOT NULL 
                    AND data_registro IS NOT NULL
                    AND excluido = 0
                    AND (data_registro BETWEEN ? AND ? OR data_modificacao BETWEEN ? AND ?)
                    -- Filtrar apenas tempos positivos
                    AND julianday(data_ae) > 
                        CASE 
                            WHEN data_modificacao IS NOT NULL AND data_modificacao > data_registro 
                            THEN julianday(data_modificacao) 
                            ELSE julianday(data_registro) 
                        END
                )
            """, (data_inicio, data_fim, data_inicio, data_fim))
            
            tempo_medio_ae_dias = cursor.fetchone()[0]
            if tempo_medio_ae_dias is not None and tempo_medio_ae_dias > 0:
                # Converter dias para horas e minutos
                tempo_medio_ae_horas = tempo_medio_ae_dias * 24
                horas = int(tempo_medio_ae_horas)
                minutos = int((tempo_medio_ae_horas - horas) * 60)
                tempo_medio_ae = f"{horas}h {minutos}min"
            else:
                tempo_medio_ae = "N/A"
            
            # 2. Tempo Médio SM (data de criação SM - data da criação registro ou ultima modificação)
            # Modificado para considerar apenas valores positivos
            cursor.execute("""
                SELECT AVG(tempo) as tempo_medio_sm
                FROM (
                    SELECT julianday(data_sm) - 
                        CASE 
                            WHEN data_modificacao IS NOT NULL AND data_modificacao > data_registro 
                            THEN julianday(data_modificacao) 
                            ELSE julianday(data_registro) 
                        END as tempo
                    FROM registros
                    WHERE data_sm IS NOT NULL 
                    AND data_registro IS NOT NULL
                    AND excluido = 0
                    AND (data_registro BETWEEN ? AND ? OR data_modificacao BETWEEN ? AND ?)
                    -- Filtrar apenas tempos positivos
                    AND julianday(data_sm) > 
                        CASE 
                            WHEN data_modificacao IS NOT NULL AND data_modificacao > data_registro 
                            THEN julianday(data_modificacao) 
                            ELSE julianday(data_registro) 
                        END
                )
            """, (data_inicio, data_fim, data_inicio, data_fim))
            
            tempo_medio_sm_dias = cursor.fetchone()[0]
            if tempo_medio_sm_dias is not None and tempo_medio_sm_dias > 0:
                # Converter dias para horas e minutos
                tempo_medio_sm_horas = tempo_medio_sm_dias * 24
                horas = int(tempo_medio_sm_horas)
                minutos = int((tempo_medio_sm_horas - horas) * 60)
                tempo_medio_sm = f"{horas}h {minutos}min"
            else:
                tempo_medio_sm = "N/A"
            
            # 3. Tempo médio Hábil para criação da SM (horario_previsto - data_registro ou data_modificacao)
            cursor.execute("""
                SELECT AVG(julianday(horario_previsto) - 
                    CASE 
                        WHEN data_modificacao IS NOT NULL AND data_modificacao > data_registro 
                        THEN julianday(data_modificacao) 
                        ELSE julianday(data_registro) 
                    END) as tempo_medio_habil
                FROM registros
                WHERE horario_previsto IS NOT NULL 
                AND data_registro IS NOT NULL
                AND excluido = 0
                AND (data_registro BETWEEN ? AND ? OR data_modificacao BETWEEN ? AND ?)
            """, (data_inicio, data_fim, data_inicio, data_fim))
            
            tempo_medio_habil_dias = cursor.fetchone()[0]
            if tempo_medio_habil_dias is not None and tempo_medio_habil_dias > 0:
                # Converter dias para horas e minutos
                tempo_medio_habil_horas = tempo_medio_habil_dias * 24
                horas = int(tempo_medio_habil_horas)
                minutos = int((tempo_medio_habil_horas - horas) * 60)
                tempo_medio_habil = f"{horas}h {minutos}min"
            else:
                tempo_medio_habil = "N/A"
            
            # 4. Gráfico de barras: total de registros por dia da semana atual
            from datetime import datetime, timedelta
            hoje = datetime.now()
            inicio_semana_atual = hoje - timedelta(days=hoje.weekday())
            
            # Dias da semana em português
            dias_semana_nomes = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
            
            # Inicializar arrays para os dados do gráfico
            dias = []
            dados_registros_total = []
            dados_registros_com_sm_ae = []
            
            # Registrar informações para debug
            logger.info(f"Data atual: {hoje}, Início da semana atual: {inicio_semana_atual}")
            
            # Determinar o dia atual da semana (0 = segunda, 6 = domingo)
            dia_atual_semana = hoje.weekday()
            
            # Iterar pelos dias da semana atual até o dia atual
            for i in range(dia_atual_semana + 1):  # +1 para incluir o dia atual
                data_dia = inicio_semana_atual + timedelta(days=i)
                
                # Formatar o nome do dia para exibição
                nome_dia = dias_semana_nomes[i]
                dias.append(nome_dia)
                
                # Registrar as datas para debug
                logger.info(f"Dia {i+1} da semana: {nome_dia} ({data_dia.strftime('%Y-%m-%d')})")
                
                # Total de registros no dia
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM registros 
                    WHERE date(data_registro) = date(?)
                    AND excluido = 0
                """, (data_dia.strftime('%Y-%m-%d'),))
                total_registros = cursor.fetchone()[0]
                dados_registros_total.append(total_registros)
                
                # Registrar contagem para debug
                logger.info(f"Total de registros no dia {nome_dia}: {total_registros}")
                
                # Total de registros com SM ou AE no dia
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM registros 
                    WHERE date(data_registro) = date(?)
                    AND excluido = 0
                    AND ((numero_sm IS NOT NULL AND numero_sm != '') OR (numero_ae IS NOT NULL AND numero_ae != ''))
                """, (data_dia.strftime('%Y-%m-%d'),))
                total_com_sm_ae = cursor.fetchone()[0]
                dados_registros_com_sm_ae.append(total_com_sm_ae)
                
                # Registrar contagem para debug
                logger.info(f"Total de registros com SM/AE no dia {nome_dia}: {total_com_sm_ae}")
                
            # Se não houver dados para a semana atual (por exemplo, se for segunda-feira),
            # adicionar pelo menos um dia para evitar gráfico vazio
            if len(dias) == 0:
                dias = ['Segunda']
                dados_registros_total = [0]
                dados_registros_com_sm_ae = [0]
                logger.info("Nenhum dia da semana atual para mostrar, adicionando dia padrão")
            
            # 5. Mapa de calor: Horário de cada dia que temos mais registros criados
            # Obter contagem de registros por hora do dia (0-23) e dia da semana (0-6, onde 0 é segunda)
            cursor.execute("""
                SELECT 
                    strftime('%w', data_registro) as dia_semana,
                    strftime('%H', data_registro) as hora,
                    COUNT(*) as total
                FROM registros
                WHERE data_registro IS NOT NULL
                AND excluido = 0
                AND date(data_registro) BETWEEN date(?) AND date(?)
                GROUP BY dia_semana, hora
                ORDER BY dia_semana, hora
            """, (data_inicio, data_fim))
            
            # Inicializar matriz de mapa de calor (7 dias x 24 horas)
            mapa_calor_registros = [[0 for _ in range(24)] for _ in range(7)]
            
            # Preencher a matriz com os dados
            resultados_heatmap = cursor.fetchall()
            logger.info(f"Dados para mapa de calor: {len(resultados_heatmap)} registros encontrados")
            
            for row in resultados_heatmap:
                dia = int(row[0])
                # Converter de 0=domingo para 0=segunda
                dia = (dia - 1) % 7
                hora = int(row[1])
                total = row[2]
                mapa_calor_registros[dia][hora] = total
                
                # Log para depuração
                if total > 0:
                    logger.info(f"Mapa de calor: Dia {dia} (0=seg, 6=dom), Hora {hora}h: {total} registros")
            
            # 6. Mapa de calor: Registros criados no mesmo dia da saída prevista entre 6-8h
            cursor.execute("""
                SELECT 
                    strftime('%w', data_registro) as dia_semana,
                    COUNT(*) as total
                FROM registros
                WHERE data_registro IS NOT NULL
                AND horario_previsto IS NOT NULL
                AND date(data_registro) = date(horario_previsto)
                AND strftime('%H', data_registro) IN ('06', '07', '08')
                AND excluido = 0
                AND date(data_registro) BETWEEN date(?) AND date(?)
                GROUP BY dia_semana
                ORDER BY dia_semana
            """, (data_inicio, data_fim))
            
            # Inicializar array para o mapa de calor (7 dias)
            mapa_calor_mesmo_dia = [0 for _ in range(7)]
            
            # Preencher o array com os dados
            resultados_tardios = cursor.fetchall()
            logger.info(f"Dados para mapa de registros tardios: {len(resultados_tardios)} registros encontrados")
            
            for row in resultados_tardios:
                dia = int(row[0])
                # Converter de 0=domingo para 0=segunda
                dia = (dia - 1) % 7
                total = row[1]
                mapa_calor_mesmo_dia[dia] = total
                
                # Log para depuração
                logger.info(f"Registros tardios: Dia {dia} (0=seg, 6=dom): {total} registros")
        
        # Preparar dados para o template
        dados_grafico = {
            'dias': dias,
            'registros_total': dados_registros_total,
            'registros_com_sm_ae': dados_registros_com_sm_ae
        }
        
        # Nomes dos dias da semana para o mapa de calor
        dias_semana = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
        
        return render_template('gr_dashboard.html',
                               usuario=session.get('user', 'Usuário'),
                               nivel=session.get('nivel', 'N/A'),
                               tempo_medio_ae=tempo_medio_ae,
                               tempo_medio_sm=tempo_medio_sm,
                               tempo_medio_habil=tempo_medio_habil,
                               dados_grafico=dados_grafico,
                               mapa_calor_registros=mapa_calor_registros,
                               mapa_calor_mesmo_dia=mapa_calor_mesmo_dia,
                               dias_semana=dias_semana,
                               data_inicio=data_inicio,
                               data_fim=data_fim)
    
    except Exception as e:
        logger.error(f"Erro ao renderizar dashboard GR: {e}")
        flash(f"Erro ao carregar o dashboard: {str(e)}", "danger")
        return redirect(url_for('gr.ambiente'))

# Rota para obter histórico de alterações de um registro
@gr_blueprint.route('/historico_alteracoes/<int:registro_id>', methods=['GET'])
@gr_required
def obter_historico_alteracoes(registro_id):
    # Importar a função de utilidade que implementamos separadamente
    from historico_utils import obter_historico_alteracoes as get_historico
    
    # Chamar a função de utilidade para obter o histórico
    return get_historico(registro_id)

# Rota para obter detalhes das alterações pós SM/AE (rota legada, redireciona para historico_alteracoes)
@gr_blueprint.route('/alteracoes/<int:registro_id>', methods=['GET'])
@gr_required
def obter_alteracoes(registro_id):
    logger.info(f"Redirecionando de /alteracoes/{registro_id} para /historico_alteracoes/{registro_id}")
    return redirect(url_for('gr.obter_historico_alteracoes', registro_id=registro_id))

# Rota para confirmar verificação de alterações
@gr_blueprint.route('/confirmar_verificacao/<int:registro_id>', methods=['POST'])
@gr_required
def confirmar_verificacao(registro_id):
    logger.info(f"Confirmando verificação de alterações do registro {registro_id} - Session: {session}")
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Verificar se o registro existe
            cursor.execute("SELECT * FROM registros WHERE id = ? AND excluido = 0", (registro_id,))
            registro = cursor.fetchone()
            
            if not registro:
                flash("Registro não encontrado", "danger")
                return redirect(url_for('gr.ambiente'))
            
            # Marcar o registro como verificado
            cursor.execute("""
                UPDATE registros
                SET alteracoes_verificadas = 1
                WHERE id = ?
            """, (registro_id,))
            
            conn.commit()
            
            flash("Alterações verificadas com sucesso", "success")
            return redirect(url_for('gr.ambiente', alteracoes_pos_smae='true'))
    
    except Exception as e:
        logger.error(f"Erro ao confirmar verificação de alterações: {e}")
        flash(f"Erro ao confirmar verificação: {str(e)}", "danger")
        return redirect(url_for('gr.ambiente'))

# Rota para visualizar histu00f3rico de um registro
@gr_blueprint.route('/historico/<int:registro_id>')
@gr_required
def historico_registro(registro_id):
    logger.info(f"Acessando histórico do registro {registro_id} - Session: {session}")
    
    try:
        # Usar a classe DatabaseConnection para gerenciar a conexão
        with DatabaseConnection() as conn:
            cursor = conn.cursor()
            
            # Obter dados do registro
            cursor.execute(
                "SELECT * FROM registros WHERE id = ?", 
                (registro_id,)
            )
            registro = cursor.fetchone()
            
            if not registro:
                return jsonify({
                    "success": False,
                    "message": "Registro não encontrado"
                })
            
            # Converter para dicionário para facilitar o acesso
            registro = dict(registro)
            
            # Obter as colunas da tabela registros
            cursor.execute("PRAGMA table_info(registros)")
            campos_existentes = [col[1] for col in cursor.fetchall()]
            
            # Preparar informações do registro para exibição
            # Garantir que todos os campos tenham valores válidos
            cliente = registro.get('cliente', '')
            numero_sm = registro.get('numero_sm', '')
            numero_ae = registro.get('numero_ae', '')
            data_registro = registro.get('data_inclusao', '')
            data_modificacao = registro.get('data_modificacao', '')
            
            # Verificar se os valores são None e substituir por string vazia
            cliente = cliente if cliente is not None else ''
            numero_sm = numero_sm if numero_sm is not None else ''
            numero_ae = numero_ae if numero_ae is not None else ''
            data_registro = data_registro if data_registro is not None else ''
            data_modificacao = data_modificacao if data_modificacao is not None else ''
            
            # Formatar as datas se estiverem presentes
            if data_registro:
                try:
                    data_registro_dt = datetime.strptime(data_registro, '%Y-%m-%d %H:%M:%S')
                    data_registro = data_registro_dt.strftime('%Y-%m-%d %H:%M:%S')
                except (ValueError, TypeError):
                    logger.warning(f"Formato de data inválido para data_registro: {data_registro}")
            
            if data_modificacao:
                try:
                    data_modificacao_dt = datetime.strptime(data_modificacao, '%Y-%m-%d %H:%M:%S')
                    data_modificacao = data_modificacao_dt.strftime('%Y-%m-%d %H:%M:%S')
                except (ValueError, TypeError):
                    logger.warning(f"Formato de data inválido para data_modificacao: {data_modificacao}")
            
            # Criar objeto de informações do registro
            registro_info = {
                "id": registro_id,
                "cliente": cliente or 'Não informado',
                "numero_sm": numero_sm or 'Não informado',
                "numero_ae": numero_ae or 'Não informado',
                "data_registro": data_registro or 'Não informado',
                "data_modificacao": data_modificacao or 'Não informado'
            }
            
            # Buscar o histórico de alterações para este registro
            alteracoes = []
            
            try:
                # Verificar se a tabela histórico existe
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='historico'")
                if cursor.fetchone():
                    # Buscar todos os registros do histórico que contenham alterações em formato JSON
                    cursor.execute("""
                        SELECT h.alteracoes, h.data_alteracao, h.alterado_por, u.nivel
                        FROM historico h
                        LEFT JOIN usuarios u ON h.alterado_por = u.username
                        WHERE h.registro_id = ? 
                        ORDER BY h.data_alteracao DESC
                    """, (registro_id,))
                    
                    registros_historico = cursor.fetchall()
                    
                    for registro_hist in registros_historico:
                        if registro_hist[0]:  # Se temos alterações em JSON
                            try:
                                alteracoes_json = json.loads(registro_hist[0])
                                data_alteracao = registro_hist[1]
                                usuario = registro_hist[2]
                                nivel_usuario = registro_hist[3]
                                
                                # Processar cada campo alterado
                                for campo, valores in alteracoes_json.items():
                                    # Verificar se é um campo monitorado
                                    if campo.lower() in [c.lower() for c in campos_existentes]:
                                        # Verificar se a alteração ocorreu após a inclusão de SM/AE
                                        data_sm = registro['data_sm'] if 'data_sm' in registro.keys() else None
                                        data_ae = registro['data_ae'] if 'data_ae' in registro.keys() else None
                                        
                                        # Garantir que a data de alteração está no formato correto
                                        try:
                                            data_alteracao_dt = datetime.strptime(data_alteracao, '%Y-%m-%d %H:%M:%S')
                                        except (ValueError, TypeError):
                                            # Se houver erro no formato da data, usar a data atual
                                            logger.warning(f"Formato de data inválido: {data_alteracao}. Usando data atual.")
                                            data_alteracao_dt = datetime.now()
                                            data_alteracao = data_alteracao_dt.strftime('%Y-%m-%d %H:%M:%S')
                                        
                                        # Determinar a data mais recente entre SM e AE
                                        data_referencia = None
                                        if data_sm and data_ae:
                                            try:
                                                data_sm_dt = datetime.strptime(data_sm, '%Y-%m-%d %H:%M:%S')
                                                data_ae_dt = datetime.strptime(data_ae, '%Y-%m-%d %H:%M:%S')
                                                data_referencia = max(data_sm_dt, data_ae_dt)
                                            except (ValueError, TypeError):
                                                # Se houver erro no formato da data, usar a data de alteração
                                                data_referencia = None
                                        elif data_sm:
                                            try:
                                                data_referencia = datetime.strptime(data_sm, '%Y-%m-%d %H:%M:%S')
                                            except (ValueError, TypeError):
                                                data_referencia = None
                                        elif data_ae:
                                            try:
                                                data_referencia = datetime.strptime(data_ae, '%Y-%m-%d %H:%M:%S')
                                            except (ValueError, TypeError):
                                                data_referencia = None
                                        
                                        # Garantir que os valores anterior e novo não sejam nulos
                                        valor_anterior = valores.get('valor_antigo', '')
                                        if valor_anterior is None:
                                            valor_anterior = ''
                                        
                                        valor_novo = valores.get('valor_novo', '')
                                        if valor_novo is None:
                                            valor_novo = ''
                                        
                                        # Só adicionar a alteração se ocorreu após a inclusão de SM/AE
                                        if not data_referencia or data_alteracao_dt > data_referencia:
                                            alteracoes.append({
                                                'data_hora': data_alteracao,
                                                'usuario': usuario if usuario else 'Sistema',
                                                'campo': campo,
                                                'valor_anterior': valor_anterior,
                                                'valor_novo': valor_novo
                                            })
                            except json.JSONDecodeError:
                                logger.warning(f"Formato JSON inválido no histórico: {registro_hist[0]}")
            except Exception as e:
                logger.error(f"Erro ao processar histórico: {e}")
        
        # Se não houver alterações reais ou mesmo se houver, adicionar uma entrada fixa para garantir a exibição correta
        if not alteracoes:
            # Usar a data atual formatada
            data_atual = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
            
            # Adicionar uma entrada fixa
            alteracoes.append({
                'data_hora': data_atual,
                'usuario': 'Sistema',
                'campo': 'Registro SM/AE',
                'valor_anterior': 'Sem valor anterior',
                'valor_novo': f"SM: {numero_sm} | AE: {numero_ae}"
            })
            
            # Log para depuração
            logger.info(f"Criada entrada fixa para o registro {registro_id} com data: {data_atual}")
        
        # Registrar informações para diagnóstico
        logger.info(f"Retornando {len(alteracoes)} alterações para o registro {registro_id}")
        if alteracoes:
            logger.info(f"Exemplo de alteração: {alteracoes[0]}")
        
        # Retornar os dados em formato JSON
        return jsonify({
            "success": True,
            "registro_id": registro_id,
            "registro_info": registro_info,
            "alteracoes": alteracoes
        })
    
    except Exception as e:
        logger.error(f"Erro ao renderizar histórico do registro {registro_id}: {e}")
        return jsonify({
            "success": False,
            "message": f"Erro ao carregar o histórico: {str(e)}"
        }), 500
        
# Rota para editar um registro como GR
@gr_blueprint.route('/editar_registro/<int:registro_id>', methods=['GET', 'POST'])
@gr_required
def editar_registro(registro_id):
    logger.info(f"Acessando edição do registro {registro_id} - Session: {session}")
    
    try:
        # Usar a classe DatabaseConnection para gerenciar a conexão
        with DatabaseConnection() as conn:
            cursor = conn.cursor()
            
            # Obter dados do registro usando constantes
            cursor.execute(f"SELECT * FROM {TABLE_REGISTROS} WHERE {COL_ID} = ? AND {COL_EXCLUIDO} = 0", (registro_id,))
            row = cursor.fetchone()
            
            if not row:
                flash(MSG_REGISTRO_NAO_ENCONTRADO, "danger")
                return redirect(url_for('gr.ambiente'))
                
            # Converter para dicionário
            registro_db = dict((cursor.description[i][0], value) for i, value in enumerate(row))
            
            # Verificar se existem anexos para este registro
            tem_anexos = {
                'nf': bool(registro_db.get('anexar_nf')),
                'os': bool(registro_db.get('anexar_os')),
                'agendamento': bool(registro_db.get('anexar_agendamento'))
            }
            
            # Importar funções e constantes do módulo de controle de acesso
            from access_control import (
                CAMPO_MAPPING, ICONES_SECOES, TITULOS_SECOES, CAMPOS_SECAO,
                campo_visivel, campo_editavel, mapear_db_para_campo,
                get_campos_permitidos, get_secoes_visiveis
            )
            
            # Mapear campos do banco de dados para os nomes dos campos no formulário
            form_registro = {'id': registro_id}
            
            # Preencher o dicionário form_registro com os valores do banco
            for db_campo, valor in registro_db.items():
                form_campo = mapear_db_para_campo(db_campo)
                if form_campo and valor is not None:
                    form_registro[form_campo] = valor
                else:
                    # Se não houver mapeamento, usar o nome original do campo
                    form_registro[db_campo] = valor
            
            if request.method == 'POST':
                # Obter dados do formulário
                dados_form = {
                    COL_NUMERO_SM: request.form.get('numero_sm', ''),
                    COL_DATA_SM: request.form.get('data_sm', ''),
                    COL_NUMERO_AE: request.form.get('numero_ae', ''),
                    COL_DATA_AE: request.form.get('data_ae', ''),
                    COL_OBSERVACAO_GR: request.form.get('observacao_gr', '')
                }
                
                # Definir regras de validação
                regras_validacao = {
                    COL_DATA_SM: {'tipo': 'data', 'obrigatorio': False},
                    COL_DATA_AE: {'tipo': 'data', 'obrigatorio': False},
                    COL_NUMERO_SM: {'tipo': 'texto', 'max': 50},
                    COL_NUMERO_AE: {'tipo': 'texto', 'max': 50},
                    COL_OBSERVACAO_GR: {'tipo': 'texto', 'max': 1000}
                }
                
                # Validar dados
                valido, erros = validar_dados(dados_form, regras_validacao)
                
                if not valido:
                    # Se houver erros de validação, mostrar mensagens e retornar ao formulário
                    for campo, mensagem in erros.items():
                        flash(mensagem, 'danger')
                    return render_template('editar_registro_gr.html', registro=form_registro)
                
                try:
                    # Verificar e criar colunas necessárias
                    colunas = verificar_criar_colunas(conn, cursor)
                    
                    # Verificar se houve alteração nos campos SM ou AE
                    sm_atual = registro_db.get(COL_NUMERO_SM, '')
                    ae_atual = registro_db.get(COL_NUMERO_AE, '')
                    
                    # Registrar a data e hora atual
                    data_hora_atual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    
                    # Verificar se houve alteração no SM
                    sm_alterado = dados_form[COL_NUMERO_SM] != sm_atual
                    
                    # Verificar se houve alteração no AE
                    ae_alterado = dados_form[COL_NUMERO_AE] != ae_atual
                    
                    # Definir as datas de criação/modificação dos campos
                    if COL_DATA_SM in registro_db:
                        dados_form[COL_DATA_SM] = data_hora_atual if dados_form[COL_NUMERO_SM] and (not registro_db.get(COL_DATA_SM) or sm_alterado) else registro_db.get(COL_DATA_SM)
                    else:
                        dados_form[COL_DATA_SM] = data_hora_atual if dados_form[COL_NUMERO_SM] else None
                    
                    if COL_DATA_AE in registro_db:
                        dados_form[COL_DATA_AE] = data_hora_atual if dados_form[COL_NUMERO_AE] and (not registro_db.get(COL_DATA_AE) or ae_alterado) else registro_db.get(COL_DATA_AE)
                    else:
                        dados_form[COL_DATA_AE] = data_hora_atual if dados_form[COL_NUMERO_AE] else None
                    
                    # Atualizar o registro com os novos dados
                    if COL_ALTERACOES_VERIFICADAS in colunas and COL_MODIFICADO_POR in colunas:
                        update_query = f"""
                            UPDATE {TABLE_REGISTROS}
                            SET {COL_NUMERO_SM} = ?,
                                {COL_DATA_SM} = ?,
                                {COL_NUMERO_AE} = ?,
                                {COL_DATA_AE} = ?,
                                {COL_OBSERVACAO_GR} = ?,
                                {COL_MODIFICADO_POR} = ?,
                                {COL_ALTERACOES_VERIFICADAS} = 1
                            WHERE {COL_ID} = ?
                        """
                        cursor.execute(update_query, (
                            dados_form[COL_NUMERO_SM], 
                            dados_form[COL_DATA_SM], 
                            dados_form[COL_NUMERO_AE], 
                            dados_form[COL_DATA_AE], 
                            dados_form[COL_OBSERVACAO_GR], 
                            NIVEL_GR, 
                            registro_id
                        ))
                    else:
                        update_query = f"""
                            UPDATE {TABLE_REGISTROS}
                            SET {COL_NUMERO_SM} = ?,
                                {COL_DATA_SM} = ?,
                                {COL_NUMERO_AE} = ?,
                                {COL_DATA_AE} = ?,
                                {COL_OBSERVACAO_GR} = ?
                            WHERE {COL_ID} = ?
                        """
                        cursor.execute(update_query, (
                            dados_form[COL_NUMERO_SM], 
                            dados_form[COL_DATA_SM], 
                            dados_form[COL_NUMERO_AE], 
                            dados_form[COL_DATA_AE], 
                            dados_form[COL_OBSERVACAO_GR], 
                            registro_id
                        ))
                    
                    # Registrar no histórico usando a função auxiliar
                    registrar_historico(
                        cursor,
                        registro_id,
                        ALTERACAO_EDICAO_GR,
                        [COL_NUMERO_SM, COL_NUMERO_AE, COL_OBSERVACAO_GR],
                        {
                            COL_NUMERO_SM: dados_form[COL_NUMERO_SM],
                            COL_NUMERO_AE: dados_form[COL_NUMERO_AE],
                            COL_OBSERVACAO_GR: dados_form[COL_OBSERVACAO_GR]
                        },
                        conn=conn
                    )
                    
                    # Commit das alterações no banco de dados
                    conn.commit()
                    
                    flash("Registro atualizado com sucesso!", "success")
                    return redirect(url_for('gr.ambiente'))
                except Exception as e:
                    logger.error(f"Erro ao atualizar registro {registro_id}: {e}")
                    flash(f"Erro ao atualizar registro: {e}", "danger")
            
            # Preparar dados para renderização do template
            return render_template('editar_registro_gr.html', registro=form_registro, tem_anexos=tem_anexos)
    
    except Exception as e:
        logger.error(f"Erro ao acessar edição do registro {registro_id}: {e}")
        flash(f"Erro ao acessar edição do registro: {e}", "danger")
        return redirect(url_for('gr.ambiente'))

# Rota para visualizar um registro (somente leitura)
@gr_blueprint.route('/visualizar_registro/<int:registro_id>')
@gr_required
def visualizar_registro(registro_id):
    logger.info(f"Visualizando registro {registro_id} - Session: {session}")
    
    try:
        with DatabaseConnection() as conn:
            cursor = conn.cursor()
            
            # Obter dados do registro
            cursor.execute(f"SELECT * FROM {TABLE_REGISTROS} WHERE {COL_ID} = ? AND {COL_EXCLUIDO} = 0", (registro_id,))
            row = cursor.fetchone()
            
            if not row:
                flash(MSG_REGISTRO_NAO_ENCONTRADO, "danger")
                return redirect(url_for('gr.ambiente'))
            
            # Converter para dicionário
            registro_db = dict((cursor.description[i][0], value) for i, value in enumerate(row))
            
            # Verificar se existem anexos para este registro
            tem_anexos = {
                'nf': bool(registro_db.get('anexar_nf')),
                'os': bool(registro_db.get('anexar_os')),
                'agendamento': bool(registro_db.get('anexar_agendamento'))
            }
            
            # Importar funções e constantes do módulo de controle de acesso
            from access_control import (
                CAMPO_MAPPING, ICONES_SECOES, TITULOS_SECOES, CAMPOS_SECAO,
                campo_visivel, campo_editavel, mapear_db_para_campo,
                get_campos_permitidos, get_secoes_visiveis
            )
            
            # Mapear campos do banco de dados para os nomes dos campos no formulário
            form_registro = {'id': registro_id}
            
            # Preencher o dicionário form_registro com os valores do banco
            for db_campo, valor in registro_db.items():
                form_campo = mapear_db_para_campo(db_campo)
                if form_campo and valor is not None:
                    form_registro[form_campo] = valor
            
            # Nível do usuário atual
            nivel = session.get('nivel', 'gr')
            
            # Para visualização, mostrar todas as seções disponíveis
            todas_secoes = ['unidade', 'cliente', 'transporte', 'cargas', 'observacoes', 'notas', 'documentos', 'gr']
            
            # Obter histórico de alterações do registro
            try:
                logger.debug(f"Consultando histórico para o registro {registro_id}")
                cursor.execute(f"""
                    SELECT id, registro_id, alterado_por, alteracoes, data_alteracao
                    FROM {TABLE_HISTORICO}
                    WHERE registro_id = ?
                    ORDER BY data_alteracao DESC
                """, (registro_id,))
                
                # Verificar se a tabela historico existe
                historico_rows = cursor.fetchall()
                logger.debug(f"Encontradas {len(historico_rows)} entradas no histórico")
                
                # Processar os resultados com segurança
                historico = []
                for hist_row in historico_rows:
                    hist_dict = {}
                    for i, value in enumerate(hist_row):
                        column_name = cursor.description[i][0]
                        hist_dict[column_name] = value
                    # Mapear os nomes das colunas para os nomes esperados pelo template
                    hist_dict['usuario'] = hist_dict.get('alterado_por', 'N/A')
                    hist_dict['nivel'] = session.get('nivel', 'gr')  # Usar nível do usuário atual
                    hist_dict['acao'] = 'Alteração'
                    hist_dict['detalhes'] = hist_dict.get('alteracoes', 'N/A')
                    historico.append(hist_dict)
            except Exception as hist_error:
                logger.error(f"Erro ao processar histórico: {hist_error}")
                historico = []  # Usar uma lista vazia em caso de erro
            
            # Preparar dados para renderização do template
            logger.debug(f"Preparando dados para renderização do template")
            template_data = {
                'usuario': session.get('user'),
                'nivel': nivel,
                'registro': form_registro,
                'campos_permitidos': get_campos_permitidos('admin'),  # Usar campos do admin para mostrar tudo
                'secoes_visiveis': todas_secoes,  # Mostrar todas as seções
                'CAMPO_MAPPING': CAMPO_MAPPING,
                'ICONES_SECOES': ICONES_SECOES,
                'TITULOS_SECOES': TITULOS_SECOES,
                'CAMPOS_SECAO': CAMPOS_SECAO,
                'campo_visivel': campo_visivel,
                'campo_editavel': campo_editavel,
                'tem_anexos': tem_anexos,
                'historico': historico,
                'modo_visualizacao': True  # Indica que é modo somente leitura
            }
            
            logger.debug(f"Renderizando template visualizar_registro.html")
            return render_template('visualizar_registro.html', **template_data)
    
    except Exception as e:
        logger.error(f"Erro ao visualizar registro {registro_id}: {e}")
        flash(f"Erro ao visualizar o registro: {str(e)}", "danger")
        return redirect(url_for('gr.ambiente'))

# Rota para exibir modal de confirmação para marcar alterações como verificadas
@gr_blueprint.route('/exibir_confirmacao/<int:registro_id>')
@gr_required
def exibir_confirmacao_verificacao(registro_id):
    logger.info(f"Exibindo confirmação para marcar alterações como verificadas - Registro {registro_id}")
    
    try:
        with DatabaseConnection() as conn:
            cursor = conn.cursor()
            
            # Obter dados do registro
            cursor.execute(f"SELECT * FROM {TABLE_REGISTROS} WHERE {COL_ID} = ? AND {COL_EXCLUIDO} = 0", (registro_id,))
            registro = fetchone_dict(cursor)
            
            if not registro:
                flash(MSG_REGISTRO_NAO_ENCONTRADO, "danger")
                return redirect(url_for('gr.ambiente', alteracoes_pos_smae='true'))
            
            # Obter histórico de alterações
            cursor.execute(f"""
                SELECT h.*, u.username as usuario_nome
                FROM {TABLE_HISTORICO} h
                LEFT JOIN {TABLE_USUARIOS} u ON h.alterado_por = u.username
                WHERE h.registro_id = ?
                ORDER BY h.data_alteracao DESC
                LIMIT 10
            """, (registro_id,))
            historico = [dict(row) for row in cursor.fetchall()]
        
        # Renderizar o template de confirmação
        return render_template('confirmar_verificacao.html',
                            registro=registro,
                            historico=historico,
                            usuario=session.get('user', 'Usuário'),
                            nivel=session.get('nivel', 'N/A'))
    
    except Exception as e:
        logger.error(f"Erro ao exibir confirmação: {e}")
        flash(f"Erro ao exibir confirmação: {str(e)}", "danger")
        return redirect(url_for('gr.ambiente', alteracoes_pos_smae='true'))

# Rota para marcar alterações como verificadas
@gr_blueprint.route('/marcar_alteracoes_verificadas/<int:registro_id>', methods=['POST'])
@gr_required
def marcar_alteracoes_verificadas(registro_id):
    logger.info(f"Marcando alterações como verificadas para registro {registro_id}")
    
    try:
        with DatabaseConnection() as conn:
            cursor = conn.cursor()
            
            # Verificar se o registro existe
            cursor.execute(f"SELECT {COL_ID}, {COL_NUMERO_SM}, {COL_NUMERO_AE} FROM {TABLE_REGISTROS} WHERE {COL_ID} = ? AND {COL_EXCLUIDO} = 0", (registro_id,))
            registro = cursor.fetchone()
            if not registro:
                logger.error(f"Registro ID {registro_id} não encontrado")
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({"error": "Registro não encontrado", "success": False}), 404
                else:
                    flash(MSG_REGISTRO_NAO_ENCONTRADO, "danger")
                    return redirect(url_for('gr.ambiente', alteracoes_pos_smae='true'))
            
            # Marcar as alterações como verificadas
            cursor.execute(f"UPDATE {TABLE_REGISTROS} SET {COL_ALTERACOES_VERIFICADAS} = 1 WHERE {COL_ID} = ?", (registro_id,))
            
            # Verificar se a atualização foi bem-sucedida
            if cursor.rowcount == 0:
                logger.error(f"Falha ao atualizar o registro {registro_id}")
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({"error": "Falha ao atualizar o registro", "success": False}), 500
                else:
                    flash("Falha ao marcar alterações como verificadas.", "danger")
                    return redirect(url_for('gr.ambiente', alteracoes_pos_smae='true'))
            
            # Registrar no histórico que as alterações foram verificadas usando a função auxiliar
            registrar_historico(
                cursor, 
                registro_id, 
                ALTERACAO_VERIFICACAO, 
                [COL_ALTERACOES_VERIFICADAS]
            )
            
            # Log de sucesso
            logger.info(f"Alterações marcadas como verificadas com sucesso para o registro {registro_id}")
            
            # Responder de acordo com o tipo de requisição
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    "success": True, 
                    "message": "Alterações verificadas com sucesso",
                    "registro_id": registro_id
                })
            else:
                flash("Alterações marcadas como verificadas com sucesso.", "success")
                return redirect(url_for('gr.ambiente', alteracoes_pos_smae='true'))
    
    except Exception as e:
        logger.error(f"Erro ao marcar alterações como verificadas: {e}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"error": str(e), "success": False}), 500
        else:
            flash(f"Erro ao marcar alterações como verificadas: {str(e)}", "danger")
            return redirect(url_for('gr.ambiente', alteracoes_pos_smae='true'))

# Esta função foi removida por estar duplicada. A versão atualizada é obter_historico_alteracoes

# Rota para a página de sucesso com redirecionamento automático
@gr_blueprint.route('/sucesso')
@gr_required
def sucesso():
    mensagem = request.args.get('mensagem', 'Operação concluída com sucesso')
    redirect_page = request.args.get('redirect', 'gr.ambiente')
    submensagem = request.args.get('submensagem', 'Você será redirecionado automaticamente')
    
    # Construir a URL de redirecionamento
    redirect_url = url_for(redirect_page)
    
    return render_template('sucesso.html',
                          mensagem=mensagem,
                          submensagem=submensagem,
                          redirect_url=redirect_url)

# Fim das rotas do blueprint GR

# Rota API para obter contadores atualizados
@gr_blueprint.route('/api/contadores')
@gr_required
def api_contadores():
    """API para obter contadores atualizados sem recarregar a página"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Obter informações sobre as colunas da tabela registros
            cursor.execute("PRAGMA table_info(registros)")
            colunas = [col[1] for col in cursor.fetchall()]
            
            # Obter contagens básicas usando a função auxiliar
            contadores = get_contagens_basicas(cursor)
            
            # Renomear a chave 'sem_nf' para 'operacoes_sem_nf' para manter compatibilidade
            contadores['operacoes_sem_nf'] = contadores.pop('sem_nf')
            
            # Inicializar a chave 'alteracoes_pos_smae' se não existir
            if 'alteracoes_pos_smae' not in contadores:
                contadores['alteracoes_pos_smae'] = 0
            
            # Usar a função auxiliar para obter a contagem de alterações nos campos específicos após inclusão de SM/AE
            _, alteracoes_pos_smae = get_registros_com_alteracoes_pos_smae(cursor, colunas)
            contadores['alteracoes_pos_smae'] = alteracoes_pos_smae
            
            return jsonify(contadores)
            
    except Exception as e:
        logger.error(f"Erro ao obter contadores: {e}")
        return jsonify({'error': str(e)}), 500

