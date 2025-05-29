from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory, send_file, abort, Response
import os
import sys
import time
import json
import sqlite3
import logging
import re
from datetime import datetime
from werkzeug.utils import secure_filename
import werkzeug.wrappers
from models.database import get_db_connection
from models.historico import Historico
from models.registros import Registro
from operations.excel import excel_processor
from operations.registros import processar_edicao_registro

# Importar decoradores de autenticação do novo arquivo auth.routes.py
from auth.routes import login_required, admin_required, gr_required, admin_or_gr_required

# ========================
# BLUEPRINTS
# ========================

# Os blueprints auth_bp, solicitacoes_bp e admin_bp foram movidos para seus respectivos arquivos
# Importar admin_bp de admin_routes.py quando necessário
gr_bp = Blueprint('gr', __name__, url_prefix='/gr')
comum_bp = Blueprint('comum', __name__, url_prefix='/comum')
main_bp = Blueprint('main', __name__, url_prefix='/main')

# ========================
# FUNÇÕES AUXILIARES INTERNAS
# ========================

# Função para formatar datas no padrão brasileiro DD-MM-AAAA HH:MM:SS
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

# Função para converter formato de data para o banco de dados
def converter_formato_data(valor):
    if not valor:
        return ""
    
    # Se o valor já está no formato HH:MM:SS DD-MM-AAAA, retorná-lo sem alterações
    if re.match(r'\d{2}:\d{2}:\d{2} \d{2}-\d{2}-\d{4}', valor):
        return valor
    
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
comum_bp.add_app_template_filter(formatar_data_br, 'formatar_data_br')

def log_admin_action(usuario, acao, detalhes):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO logs_admin (usuario, acao, detalhes, data_log)
                VALUES (?, ?, ?, ?)
            """, (usuario, acao, detalhes, datetime.now()))
            conn.commit()
    except Exception as e:
        logging.error(f"Erro ao registrar log: {e}")

def paginate_list(lista, page, per_page):
    total = len(lista)
    start = (page - 1) * per_page
    end = start + per_page
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    page = max(1, min(page, total_pages))
    return lista[start:end], total, total_pages, page

def fetchone_dict(cursor):
    row = cursor.fetchone()
    if row is None:
        return None
    # row is sqlite3.Row or tuple - convert accordingly
    if isinstance(row, dict):
        return row
    if hasattr(cursor, 'description'):
        return {cursor.description[i][0]: value for i, value in enumerate(row)}
    return row

# ========================
# ROTAS - USUÁRIO COMUM (comum_bp)
# ========================

# ========================
# ROTAS - USUÁRIO COMUM (comum_bp)
# ========================

@comum_bp.route('/dashboard')
@login_required
def dashboard_comum():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 20
        filtro = request.args.get('filtro')
        filtro_unidade = request.args.get('filtro_unidade', 'todas')
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Importar funções de controle de acesso
            from access_control import get_campos_permitidos
            
            # Obter nível do usuário
            nivel = session.get('nivel', 'comum')
            
            # Buscar todas as unidades disponíveis no banco de dados
            try:
                # Verificar se a coluna existe na tabela
                cursor.execute("PRAGMA table_info(registros)")
                colunas = [col[1] for col in cursor.fetchall()]
                print(f"Colunas da tabela registros: {colunas}")
                
                if 'unidade' in colunas:
                    cursor.execute("SELECT DISTINCT unidade FROM registros WHERE unidade IS NOT NULL AND unidade != '' ORDER BY unidade")
                    resultados = cursor.fetchall()
                    unidades_disponiveis = [row[0] for row in resultados]
                    print(f"Resultados da consulta: {resultados}")
                else:
                    print("Coluna 'unidade' não encontrada na tabela registros")
                    unidades_disponiveis = []
                
                # Garantir que as unidades padrão estejam sempre disponíveis
                unidades_padrao = ['RIO DE JANEIRO', 'FLORIANO', 'SUZANO']
                
                # Converter todas as unidades existentes para maiúsculas
                unidades_disponiveis = [unidade.upper() for unidade in unidades_disponiveis]
                
                # Adicionar unidades padrão que não estão na lista de unidades disponíveis
                for unidade in unidades_padrao:
                    if unidade not in unidades_disponiveis:
                        unidades_disponiveis.append(unidade)
                
                # Ordenar as unidades
                unidades_disponiveis.sort()
                
                print(f"Unidades disponíveis: {unidades_disponiveis}")
            except Exception as e:
                print(f"Erro ao buscar unidades: {e}")
                unidades_disponiveis = ['Rio de Janeiro', 'Floriano', 'SUZANO']
            
            # Restrições de acesso por nível
            restricoes_nivel = ""
            if nivel == 'comum':
                # Remover restrições complexas para usuários comuns
                # Permitir que vejam todos os registros no sistema
                restricoes_nivel = """
                    AND 1=1
                """
            elif nivel == 'gr':
                # GRs podem ver registros de usuários comuns e GRs, mas não de admins
                restricoes_nivel = """
                    AND (usuario IN (SELECT username FROM usuarios WHERE nivel IN ('comum', 'gr')))
                """
            # Admins podem ver todos os registros (sem restrição adicional)
            
            base_query = """
                SELECT 
                    id, 
                    unidade,
                    data_registro, 
                    usuario, 
                    placa as cavalo, 
                    motorista, 
                    cpf,
                    container_1, 
                    container_2, 
                    cliente, 
                    numero_nf as nf,
                    anexar_os as os,
                    numero_sm as sm,
                    numero_ae as ae,
                    on_time_cliente, 
                    horario_previsto,
                    tipo_carga,
                    modalidade,
                    status_container,
                    booking_di,
                    lote_cs,
                    destino_intermediario,
                    destino_final,
                    observacao_operacional,
                    observacao_gr,
                    data_modificacao,
                    alteracoes_verificadas
                FROM registros 
                WHERE excluido = 0
                {}
            """.format(restricoes_nivel)
            
            if filtro == 'sem_nf':
                base_query = base_query + " AND (anexar_nf IS NULL OR anexar_nf = '')"
            elif filtro == 'sem_os':
                base_query = base_query + " AND (anexar_os IS NULL OR anexar_os = '')"
            elif filtro == 'sem_container':
                base_query = base_query + " AND (container_1 IS NULL OR container_1 = '')"
            elif filtro == 'sem_ae':
                base_query = base_query + " AND (numero_ae IS NULL OR numero_ae = '')"
            elif filtro == 'sem_sm':
                base_query = base_query + " AND (numero_sm IS NULL OR numero_sm = '')"
            # Filtro de alterações pós SM/AE removido - exclusivo para usuários GR
            
            # Aplicar filtro de unidade se não for 'todas'
            if filtro_unidade != 'todas':
                # Usar LIKE para corresponder parcialmente
                base_query = base_query + f" AND unidade LIKE '%{filtro_unidade}%'"
                print(f"Aplicando filtro de unidade: {filtro_unidade}")
            # Ordenar por horario_previsto (saída prevista) mais próximo do horário atual
            base_query += " ORDER BY CASE WHEN horario_previsto IS NULL THEN 1 ELSE 0 END, horario_previsto ASC"
            print(f"Executando query: {base_query}")
            cursor.execute(base_query)
            rows = cursor.fetchall()
            print(f"Registros encontrados: {len(rows)}")
            # Converter os resultados para dicionários
            registros = [dict((cursor.description[i][0], value) for i, value in enumerate(row)) for row in rows]
            
            # Processar as datas para garantir o formato correto
            for registro in registros:
                # Processar on_time_cliente
                if registro.get('on_time_cliente'):
                    # Verificar se a data já está no formato HH:MM:SS DD-MM-AAAA
                    data_str = registro['on_time_cliente']
                    if ' ' in data_str:
                        partes = data_str.split(' ')
                        if len(partes) >= 2:
                            # Se a primeira parte tem ':' e a segunda tem '-', está no formato correto
                            if ':' in partes[0] and '-' in partes[1]:
                                pass  # Já está no formato correto
                            # Se a primeira parte tem '-' e a segunda tem ':', inverter a ordem
                            elif '-' in partes[0] and ':' in partes[1]:
                                registro['on_time_cliente'] = f"{partes[1]} {partes[0]}"
                
                # Processar horario_previsto
                if registro.get('horario_previsto'):
                    # Verificar se a data já está no formato HH:MM:SS DD-MM-AAAA
                    data_str = registro['horario_previsto']
                    if ' ' in data_str:
                        partes = data_str.split(' ')
                        if len(partes) >= 2:
                            # Se a primeira parte tem ':' e a segunda tem '-', está no formato correto
                            if ':' in partes[0] and '-' in partes[1]:
                                pass  # Já está no formato correto
                            # Se a primeira parte tem '-' e a segunda tem ':', inverter a ordem
                            elif '-' in partes[0] and ':' in partes[1]:
                                registro['horario_previsto'] = f"{partes[1]} {partes[0]}"
            if registros:
                print(f"Primeiro registro: {registros[0]}")
            else:
                print("Nenhum registro encontrado na consulta.")

            # Contagem por condição
            def count_condicao(cond_sql):
                cursor.execute(f"SELECT COUNT(*) as total FROM registros WHERE excluido = 0 AND ({cond_sql})")
                res = cursor.fetchone()
                return res[0] if res else 0

            operacoes_sem_nf = count_condicao("anexar_nf IS NULL OR anexar_nf = ''")
            operacoes_sem_os = count_condicao("anexar_os IS NULL OR anexar_os = ''")
            operacoes_sem_container = count_condicao("container_1 IS NULL OR container_1 = ''")
            operacoes_sem_sm = count_condicao("numero_sm IS NULL OR numero_sm = ''")
            operacoes_sem_ae = count_condicao("numero_ae IS NULL OR numero_ae = ''")
            
            # Contagem de alterações pós SM/AE
            alteracoes_pos_smae = count_condicao("((numero_sm IS NOT NULL AND numero_sm != '' AND numero_sm != '0') OR \
                                               (numero_ae IS NOT NULL AND numero_ae != '' AND numero_ae != '0')) AND \
                                               data_modificacao IS NOT NULL AND \
                                               alteracoes_verificadas = 0")

            total_registros = len(registros)
            registros_pagina, total, total_pages, page = paginate_list(registros, page, per_page)

            # Importar funções e constantes do módulo de controle de acesso
            from access_control import campo_visivel, get_campos_permitidos
            
            # Mapear colunas da tabela para campos do formulário
            colunas_tabela = {
                'id': 'ID',
                'data_registro': 'Data de Registro',
                'usuario': 'Usuário',
                'cavalo': 'CAVALO 1',
                'motorista': 'MOTORISTA',
                'cpf': 'CPF MOTORISTA',
                'container_1': 'CONTAINER 1',
                'container_2': 'CONTAINER 2',
                'cliente': 'CLIENTE',
                'nf': 'Nº NF',
                'os': 'ANEXAR OS',
                'sm': 'NUMERO SM',
                'ae': 'NÚMERO AE',
                'on_time_cliente': 'ON TIME (CLIENTE)',
                'horario_previsto': 'HORÁRIO PREVISTO DE INÍCIO',
                'tipo_carga': 'TIPO DE CARGA',
                'modalidade': 'MODALIDADE',
                'status_container': 'STATUS CONTAINER',
                'booking_di': 'BOOKING / DI',
                'lote_cs': 'LOTE CS'
            }
            
            # Obter campos permitidos para o nível do usuário
            campos_permitidos = get_campos_permitidos(nivel)
            
            # Filtrar colunas visíveis com base nos campos permitidos
            colunas_visiveis = {}
            for coluna_db, campo_form in colunas_tabela.items():
                if campo_form in campos_permitidos or coluna_db in ['id', 'data_registro', 'usuario']:
                    colunas_visiveis[coluna_db] = campo_form
            
            return render_template('dashboard.html',
                                   registros=registros_pagina,
                                   operacoes_sem_nf=operacoes_sem_nf,
                                   operacoes_sem_os=operacoes_sem_os,
                                   operacoes_sem_container=operacoes_sem_container,
                                   operacoes_sem_sm=operacoes_sem_sm,
                                   operacoes_sem_ae=operacoes_sem_ae,
                                   alteracoes_pos_smae=alteracoes_pos_smae,
                                   usuario=session.get('user'),
                                   nivel=session.get('nivel'),
                                   page=page,
                                   total_pages=total_pages,
                                   total_registros=total_registros,
                                   colunas_visiveis=colunas_visiveis)
    except Exception as e:
        import traceback
        logging.error(f"Erro ao carregar dashboard: {e}")
        logging.error(traceback.format_exc())
        flash('Erro ao carregar os registros.', 'danger')
        
        nivel = session.get('nivel', 'comum')
        
        # Mapear colunas da tabela para campos do formulário
        colunas_tabela = {
            'id': 'ID',
            'data_registro': 'Data de Registro',
            'usuario': 'Usuário',
            'cavalo': 'CAVALO 1',
            'motorista': 'MOTORISTA',
            'cpf': 'CPF MOTORISTA',
            'container_1': 'CONTAINER 1',
            'container_2': 'CONTAINER 2',
            'cliente': 'CLIENTE',
            'nf': 'Nº NF',
            'os': 'ANEXAR OS',
            'sm': 'NUMERO SM',
            'ae': 'NÚMERO AE',
            'on_time_cliente': 'ON TIME (CLIENTE)',
            'horario_previsto': 'HORÁRIO PREVISTO DE INÍCIO',
            'tipo_carga': 'TIPO DE CARGA',
            'modalidade': 'MODALIDADE',
            'status_container': 'STATUS CONTAINER',
            'booking_di': 'BOOKING / DI',
            'lote_cs': 'LOTE CS'
        }
        
        # Obter campos permitidos para o nível do usuário
        from access_control import get_campos_permitidos
        campos_permitidos = get_campos_permitidos(nivel)
        
        # Filtrar colunas visíveis com base nos campos permitidos
        colunas_visiveis = {}
        for coluna_db, campo_form in colunas_tabela.items():
            if campo_form in campos_permitidos or coluna_db in ['id', 'data_registro', 'usuario']:
                colunas_visiveis[coluna_db] = campo_form
        
        # Definir valores padrão para evitar erros
        registros_pagina = []
        page = 1
        total_pages = 1
        total_registros = 0
        operacoes_sem_nf = 0
        operacoes_sem_os = 0
        operacoes_sem_container = 0
        operacoes_sem_sm = 0
        operacoes_sem_ae = 0
        
        return render_template('dashboard.html',
                               registros=registros_pagina,
                               operacoes_sem_nf=operacoes_sem_nf,
                               operacoes_sem_os=operacoes_sem_os,
                               operacoes_sem_container=operacoes_sem_container,
                               operacoes_sem_sm=operacoes_sem_sm,
                               operacoes_sem_ae=operacoes_sem_ae,
                               usuario=session.get('user'),
                               nivel=session.get('nivel'),
                               page=page,
                               total_pages=total_pages,
                               total_registros=total_registros,
                               colunas_visiveis=colunas_visiveis,
                               unidades_disponiveis=unidades_disponiveis)

@comum_bp.route('/view_registros')
@login_required
def view_registros():
    filtro = request.args.get('filtro')
    try:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            base_query = """
                SELECT 
                    id,
                    unidade,
                    data_registro,
                    usuario,
                    placa as cavalo,
                    motorista,
                    cpf,
                    container_1,
                    container_2,
                    cliente,
                    numero_nf as nf,
                    anexar_os as os,
                    numero_sm as sm,
                    on_time_cliente,
                    horario_previsto,
                    tipo_carga,
                    modalidade,
                    status_container,
                    booking_di,
                    lote_cs,
                    destino_intermediario,
                    destino_final,
                    observacao_operacional,
                    observacao_gr
                FROM registros
                WHERE excluido = 0
            """

            if filtro == 'sem_nf':
                base_query = base_query.replace('WHERE excluido = 0', 'WHERE excluido = 0 AND (numero_nf IS NULL OR numero_nf = "")')
            elif filtro == 'sem_os':
                base_query = base_query.replace('WHERE excluido = 0', 'WHERE excluido = 0 AND (anexar_os IS NULL OR anexar_os = "")')
            elif filtro == 'sem_container':
                base_query = base_query.replace('WHERE excluido = 0', 'WHERE excluido = 0 AND (container_1 IS NULL OR container_1 = "")')
            elif filtro == 'sem_sm':
                base_query = base_query.replace('WHERE excluido = 0', 'WHERE excluido = 0 AND (numero_sm IS NULL OR numero_sm = "")')

            # Ordenar por horario_previsto (saída prevista) mais próximo do horário atual
            base_query += " ORDER BY CASE WHEN horario_previsto IS NULL THEN 1 ELSE 0 END, horario_previsto ASC"
            cursor.execute(base_query)
            registros = [dict(row) for row in cursor.fetchall()]

            return render_template('historico_novo.html', registros=registros, filtro=filtro)

    except Exception as e:
        logging.error(f"Erro ao buscar registros: {e}")
        flash('Erro ao carregar os registros.', 'danger')
        return redirect(url_for('comum.dashboard_comum'))

@comum_bp.route('/download_anexo/<int:registro_id>/<tipo>', methods=['GET'])
@login_required
def download_anexo(registro_id, tipo):
    print(f"Iniciando download_anexo para registro_id={registro_id}, tipo={tipo}")
    # Usar a função centralizada para download (as_attachment=True)
    return handle_anexo(registro_id, tipo, download=True)


# Nova rota alternativa para download de anexos
@comum_bp.route('/download_anexo_alt/<int:registro_id>/<tipo>', methods=['GET'])
@login_required
def download_anexo_alt(registro_id, tipo):
    print(f"Iniciando download_anexo_alt para registro_id={registro_id}, tipo={tipo}")
    try:
        # Verificar se o tipo é válido
        if tipo not in ['nf', 'os', 'agendamento']:
            flash('Tipo de anexo inválido.', 'danger')
            return redirect(url_for('comum.dashboard_comum'))

        # Mapear o tipo para o nome da coluna no banco de dados
        tipo_map = {
            'nf': 'anexar_nf',
            'os': 'anexar_os',
            'agendamento': 'anexar_agendamento'
        }
        
        coluna_arquivo = tipo_map[tipo]
        
        # Buscar o registro no banco de dados
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Buscar o caminho do arquivo
            query = f"SELECT {coluna_arquivo} FROM registros WHERE id = ? AND excluido = 0"
            cursor.execute(query, (registro_id,))
            resultado = cursor.fetchone()
            
            if not resultado or not resultado[0]:
                return jsonify({'error': 'Arquivo não encontrado'}), 404
            
            # Obter o caminho relativo do arquivo
            caminho_relativo = resultado[0]
            
            # Construir a URL estática
            caminho_url = caminho_relativo.replace("\\", "/")
            url_estatica = url_for('static', filename=caminho_url)
            
            # Retornar a URL como JSON
            return jsonify({'url': url_estatica})
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@comum_bp.route('/novo_registro', methods=['GET', 'POST'])
@login_required
def novo_registro():
    # Se estiver visualizando um registro existente, redirecionar para a rota de visualizau00e7u00e3o
    registro_id = request.args.get('registro_id')
    if registro_id and request.method == 'GET':
        return redirect(url_for('comum.visualizar_registro', registro_id=registro_id))
    
    # Verificar se o usuu00e1rio u00e9 do tipo GR e estu00e1 tentando criar um novo registro
    if session.get('nivel') == 'gr' and request.method == 'GET':
        flash('Usuu00e1rios GR nu00e3o podem criar novos registros.', 'danger')
        return redirect(url_for('gr.ambiente'))
    
    # Verificar se o usuu00e1rio u00e9 do tipo GR e estu00e1 tentando enviar um formulu00e1rio
    if session.get('nivel') == 'gr' and request.method == 'POST':
        flash('Usuu00e1rios GR nu00e3o podem criar ou editar registros por esta rota.', 'danger')
        return redirect(url_for('gr.ambiente'))
    if request.method == 'POST':
        try:
            print("======= INICIANDO PROCESSAMENTO DO FORMULÁRIO =======")
            
            # Obter dados do formulário
            form_data = request.form.to_dict()
            print(f"Dados do formulário recebidos: {len(form_data)} campos")
            
            # Processar arquivos enviados (simplificado)
            arquivos = {}
            for campo in ['ANEXAR NF', 'ANEXAR OS', 'ANEXAR AGENDAMENTO']:
                if campo in request.files and request.files[campo].filename:
                    arquivo = request.files[campo]
                    
                    # Criar diretório de uploads se não existir
                    upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
                    if not os.path.exists(upload_dir):
                        os.makedirs(upload_dir)
                    
                    # Gerar um nome único para o arquivo
                    nome_arquivo = secure_filename(f"{campo.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{arquivo.filename}")
                    
                    # Salvar o arquivo
                    caminho_arquivo = os.path.join(upload_dir, nome_arquivo)
                    arquivo.save(caminho_arquivo)
                    
                    # Armazenar o caminho relativo para o banco de dados
                    arquivos[campo] = f"uploads/{nome_arquivo}"
            
            # Adicionar caminhos dos arquivos aos dados do formulário
            form_data.update(arquivos)
            
            # Função para converter datas para o formato HH:MM:SS DD-MM-AAAA
            def converter_formato_data(data_str):
                if not data_str:
                    return ''
                
                try:
                    # Substituir 'T' por espaço para formato padrão
                    data_str = data_str.replace('T', ' ')
                    
                    # Verificar se a string tem formato válido
                    if ' ' in data_str:  # Tem data e hora
                        data_parte, hora_parte = data_str.split(' ', 1)
                    else:  # Só tem data
                        data_parte, hora_parte = data_str, '00:00:00'
                    
                    # Validar e formatar a parte da data
                    if '-' in data_parte:  # Formato YYYY-MM-DD
                        partes_data = data_parte.split('-')
                        if len(partes_data) == 3:
                            ano, mes, dia = partes_data
                            # Verificar se o ano tem formato válido (4 dígitos)
                            if not (1900 <= int(ano) <= 2100):
                                ano = datetime.now().year
                            # Garantir que mês e dia tenham 2 dígitos
                            mes = mes.zfill(2)
                            dia = dia.zfill(2)
                            data_formatada = f"{dia}-{mes}-{ano}"
                        else:
                            # Formato inválido, usar data atual
                            hoje = datetime.now()
                            data_formatada = hoje.strftime("%d-%m-%Y")
                    else:  # Formato desconhecido, usar data atual
                        hoje = datetime.now()
                        data_formatada = hoje.strftime("%d-%m-%Y")
                    
                    # Validar e formatar a parte da hora
                    if ':' in hora_parte:  # Formato HH:MM ou HH:MM:SS
                        partes_hora = hora_parte.split(':')
                        if len(partes_hora) >= 2:
                            hora, minuto = partes_hora[0:2]
                            # Garantir que hora e minuto tenham 2 dígitos
                            hora = hora.zfill(2)
                            minuto = minuto.zfill(2)
                            # Se não tiver segundos, adicionar :00
                            if len(partes_hora) < 3:
                                segundo = "00"
                            else:
                                segundo = partes_hora[2].zfill(2)
                            hora_formatada = f"{hora}:{minuto}:{segundo}"
                        else:
                            # Formato inválido, usar hora atual
                            agora = datetime.now()
                            hora_formatada = agora.strftime("%H:%M:%S")
                    else:  # Formato desconhecido, usar hora atual
                        agora = datetime.now()
                        hora_formatada = agora.strftime("%H:%M:%S")
                    
                    # Retornar no formato HH:MM:SS DD-MM-AAAA
                    return f"{hora_formatada} {data_formatada}"
                
                except Exception as e:
                    print(f"Erro ao converter formato de data: {e}")
                    # Em caso de erro, retornar a data/hora atual formatada
                    agora = datetime.now()
                    return agora.strftime("%H:%M:%S %d-%m-%Y")
            
            # Importar funções de mapeamento do módulo de controle de acesso
            from access_control import mapear_campo_para_db, get_campos_permitidos
            
            # Obter nível do usuário
            nivel = session.get('nivel', 'comum')
            
            # Obter campos permitidos para o nível do usuário
            campos_permitidos = get_campos_permitidos(nivel)
            
            # Preparar dados para o banco de dados usando o mapeamento do módulo de controle de acesso
            db_data = {}
            
            # Mapear cada campo do formulário para a coluna correspondente no banco de dados
            print("\n==== PROCESSANDO CAMPOS DO FORMULÁRIO ====\n")
            for campo_form, valor in form_data.items():
                # Verificar se o campo está na lista de campos permitidos
                if campo_form in campos_permitidos:
                    campo_db = mapear_campo_para_db(campo_form)
                    print(f"Tentando mapear campo '{campo_form}' -> '{campo_db}'")
                    
                    # Verificar se o campo existe na tabela
                    if campo_db:
                        # Tratar campos de data/hora
                        if campo_form in ['HORÁRIO PREVISTO DE INÍCIO', 'ON TIME (CLIENTE)', 'DATA SM', 'DATA AE']:
                            db_data[campo_db] = converter_formato_data(valor)
                            print(f"Campo de data/hora '{campo_form}' convertido para: {db_data[campo_db]}")
                        else:
                            # Verificar se é uma string vazia e o campo não deve aceitar string vazia
                            if valor == "" and campo_db in ['numero_sm', 'numero_ae', 'tipo_carga']:
                                db_data[campo_db] = None
                                print(f"Campo '{campo_form}' com valor vazio convertido para NULL")
                            else:
                                db_data[campo_db] = valor
                        print(f"Mapeado campo '{campo_form}' para '{campo_db}' com valor: {valor}")
                    else:
                        print(f"AVISO: Campo '{campo_form}' não tem mapeamento para o banco de dados")
                else:
                    print(f"AVISO: Campo '{campo_form}' não está na lista de campos permitidos para o nível {nivel}")
            
            # Verificar e corrigir campos específicos que podem estar com problemas
            print("\n==== VERIFICANDO CAMPOS CRÍTICOS ====\n")
            
            # Verificar campo CAVALO -> placa
            if 'CAVALO' in form_data and form_data['CAVALO']:
                db_data['placa'] = form_data['CAVALO']
                print(f"Campo CAVALO definido explicitamente: {form_data['CAVALO']} -> placa")
            
            # Verificar campo MOTORISTA
            if 'MOTORISTA' in form_data and form_data['MOTORISTA']:
                db_data['motorista'] = form_data['MOTORISTA']
                print(f"Campo MOTORISTA definido explicitamente: {form_data['MOTORISTA']}")
            
            # Verificar campo CPF MOTORISTA
            if 'CPF MOTORISTA' in form_data and form_data['CPF MOTORISTA']:
                # Remover pontos, traços e espaços do CPF
                cpf_limpo = form_data['CPF MOTORISTA'].replace('.', '').replace('-', '').replace(' ', '')
                db_data['cpf'] = cpf_limpo
                print(f"Campo CPF MOTORISTA definido explicitamente: {form_data['CPF MOTORISTA']} -> {cpf_limpo} (cpf)")
                print(f"CPF formatado removendo pontos, traços e espaços")
            
            # Verificar campos CARRETA 1 e CARRETA 2
            if 'CARRETA 1' in form_data and form_data['CARRETA 1']:
                db_data['carreta1'] = form_data['CARRETA 1']
                print(f"Campo CARRETA 1 definido explicitamente: {form_data['CARRETA 1']} -> carreta1")
            
            if 'CARRETA 2' in form_data and form_data['CARRETA 2']:
                db_data['carreta2'] = form_data['CARRETA 2']
                print(f"Campo CARRETA 2 definido explicitamente: {form_data['CARRETA 2']} -> carreta2")
            
            # Verificar campo TIPO DE CARGA
            if 'TIPO DE CARGA' in form_data and form_data['TIPO DE CARGA']:
                db_data['tipo_carga'] = form_data['TIPO DE CARGA']
                print(f"Campo TIPO DE CARGA definido explicitamente: {form_data['TIPO DE CARGA']} -> tipo_carga")
            
            # Adicionar caminhos dos arquivos aos dados do banco
            for campo_form, caminho in arquivos.items():
                campo_db = mapear_campo_para_db(campo_form)
                if campo_db:
                    db_data[campo_db] = caminho
                    
                    # Adicionar também o nome original do arquivo
                    if campo_form == 'ANEXAR NF':
                        db_data['arquivo_nf_nome'] = request.files[campo_form].filename
                    elif campo_form == 'ANEXAR OS':
                        db_data['arquivo_os_nome'] = request.files[campo_form].filename
                    elif campo_form == 'ANEXAR AGENDAMENTO':
                        db_data['arquivo_agendamento_nome'] = request.files[campo_form].filename
            
            # Garantir que campos importantes estão presentes
            # Adicionar campos de observação
            db_data['observacao_operacional'] = form_data.get('OBSERVACAO OPERACIONAL', '')
            db_data['observacao_gr'] = form_data.get('OBSERVAÇÃO DE GR', '')
            
            # Garantir que o campo unidade está presente
            if 'UNIDADE' in form_data and form_data['UNIDADE']:
                db_data['unidade'] = form_data['UNIDADE']
                print(f"Adicionado campo 'unidade' com valor: {form_data['UNIDADE']}")
            
            # Verificar se há campos importantes faltando
            campos_importantes = ['unidade', 'cliente', 'placa', 'container_1']
            for campo in campos_importantes:
                if campo not in db_data or not db_data[campo]:
                    print(f"AVISO: Campo importante '{campo}' está faltando ou vazio")
            
            # Verificar campos de data e hora para garantir formato correto
            # Não precisamos converter novamente aqui, pois já foram convertidos anteriormente
            campos_data_hora = ['horario_previsto', 'on_time_cliente', 'data_sm', 'data_ae']
            for campo in campos_data_hora:
                if campo in db_data and db_data[campo]:
                    # Apenas registrar os valores para debug
                    print(f"Valor de '{campo}' já convertido: {db_data[campo]}")
                    
                    # Garantir que o formato está correto (apenas verificar, não converter)
                    if not re.match(r'\d{2}:\d{2}:\d{2} \d{2}-\d{2}-\d{4}', db_data[campo]):
                        print(f"AVISO: Formato de data/hora para '{campo}' pode estar incorreto: {db_data[campo]}")

                        
            # Armazenar os valores originais de horario_previsto e on_time_cliente
            horario_previsto_original = db_data.get('horario_previsto')
            on_time_cliente_original = db_data.get('on_time_cliente')
            
            # Garantir que campos de string vazios sejam NULL para campos que não aceitam string vazia
            campos_nao_vazios = ['numero_sm', 'numero_ae', 'tipo_carga', 'status_container', 'modalidade']
            for campo in campos_nao_vazios:
                if campo in db_data and db_data[campo] == "":
                    db_data[campo] = None
                    print(f"Campo '{campo}' com valor vazio convertido para NULL")
            
            # Adicionar campos de controle
            db_data['data_registro'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            db_data['usuario'] = session.get('user', 'sistema')
            db_data['excluido'] = 0
            
            # Restaurar os valores originais de horario_previsto e on_time_cliente
            # para garantir que não sejam sobrescritos
            if horario_previsto_original:
                db_data['horario_previsto'] = horario_previsto_original
                print(f"Valor final de horario_previsto restaurado: {db_data['horario_previsto']}")
                
            if on_time_cliente_original:
                db_data['on_time_cliente'] = on_time_cliente_original
                print(f"Valor final de on_time_cliente restaurado: {db_data['on_time_cliente']}")
            
            # Inserir no banco de dados
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Verificar se a tabela registros existe
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='registros'")
                    if not cursor.fetchone():
                        print("ERRO: Tabela 'registros' não existe no banco de dados!")
                        raise Exception("Tabela 'registros' não existe no banco de dados")
                    
                    # Obter estrutura da tabela para verificar colunas
                    cursor.execute("PRAGMA table_info(registros)")
                    colunas_tabela = [info[1] for info in cursor.fetchall()]
                    print(f"Colunas na tabela registros: {colunas_tabela}")
                    
                    # Remover campos vazios e campos que não existem na tabela
                    campos_filtrados = {}
                    for campo, valor in db_data.items():
                        if valor is not None and campo in colunas_tabela:
                            campos_filtrados[campo] = valor
                        elif campo not in colunas_tabela:
                            print(f"AVISO: Campo '{campo}' não existe na tabela registros e será ignorado")
                    
                    print(f"Campos filtrados para inserção: {campos_filtrados}")
                    
                    # Construir a query de inserção
                    campos = list(campos_filtrados.keys())
                    placeholders = ', '.join(['?' for _ in campos])
                    valores = list(campos_filtrados.values())
                    
                    if not campos:
                        raise Exception("Nenhum campo válido para inserir no banco de dados")
                    
                    query = f"INSERT INTO registros ({', '.join(campos)}) VALUES ({placeholders})"
                    print(f"Query de inserção: {query}")
                    print(f"Valores para inserção: {valores}")
                    
                    cursor.execute(query, valores)
                    registro_id = cursor.lastrowid
                    conn.commit()
                    print(f"Registro inserido com sucesso! ID: {registro_id}")
                    
                    # Verificar se o registro foi realmente inserido
                    cursor.execute("SELECT * FROM registros WHERE id = ?", (registro_id,))
                    if cursor.fetchone():
                        print(f"Confirmação: Registro {registro_id} encontrado após inserção")
                    else:
                        print(f"ERRO: Registro {registro_id} NÃO encontrado após inserção!")
                        raise Exception("Falha na confirmação do registro inserido")
            except Exception as e:
                print(f"ERRO durante a inserção no banco: {e}")
                import traceback
                print(traceback.format_exc())
                raise e
            
            # Redirecionar para a página de sucesso antes do dashboard
            return render_template('registro_sucesso.html', 
                                  registro_id=registro_id, 
                                  usuario=session.get('user'),
                                  nivel=session.get('nivel'))
        
        except Exception as e:
            print(f"ERRO AO SALVAR REGISTRO: {e}")
            import traceback
            print(traceback.format_exc())
            flash(f'Erro ao salvar registro: {str(e)}', 'danger')
            return redirect(url_for('comum.dashboard_comum'))

    registro_id = request.args.get('registro_id')
    registro = None
    if registro_id:
        try:
            print(f"Buscando registro com ID: {registro_id}")
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM registros WHERE id = ? AND excluido = 0", (registro_id,))
                row = cursor.fetchone()
                print(f"Resultado da consulta para ID {registro_id}: {'Encontrado' if row else 'Não encontrado'}")
                if row:
                    print(f"Colunas disponíveis: {[desc[0] for desc in cursor.description]}")
                if row:
                    registro = dict((cursor.description[i][0], value) for i, value in enumerate(row))
                    
                    # Mapear campos do banco de dados para os nomes dos campos no formulu00e1rio
                    # Isso garante que os campos sejam preenchidos corretamente no formulu00e1rio
                    form_registro = {}
                    
                    # Mapeamento de campos do banco para campos do formulu00e1rio
                    campo_mapping = {
                        'unidade': 'UNIDADE',
                        'cliente': 'CLIENTE',
                        'motorista': 'MOTORISTA',
                        'cpf': 'CPF MOTORISTA',
                        'placa': 'CAVALO',
                        'carreta1': 'CARRETA 1',
                        'carreta2': 'CARRETA 2',
                        'container_1': 'CONTAINER 1',
                        'container_2': 'CONTAINER 2',
                        'tipo_carga': 'TIPO DE CARGA',
                        'status_container': 'STATUS CONTAINER',
                        'modalidade': 'MODALIDADE',
                        'destino_intermediario': 'DESTINO INTERMEDIÁRIO',
                        'destino_final': 'DESTINO FINAL',
                        'horario_previsto': 'HORÁRIO PREVISTO DE INÍCIO',
                        'on_time_cliente': 'ON TIME (CLIENTE)',
                        'pedido_referencia': 'PEDIDO/REFERÊNCIA',
                        'booking_di': 'BOOKING / DI',
                        'lote_cs': 'LOTE CS',
                        'numero_nf': 'Nº NF',
                        'anexar_nf': 'anexar_nf',
                        'anexar_os': 'anexar_os',
                        'anexar_agendamento': 'anexar_agendamento',
                        'arquivo_nf_nome': 'arquivo_nf_nome',
                        'arquivo_os_nome': 'arquivo_os_nome',
                        'arquivo_agendamento_nome': 'arquivo_agendamento_nome',
                        'observacao_operacional': 'OBSERVACAO OPERACIONAL',
                        'observacao_gr': 'OBSERVAÇÃO DE GR'
                    }
                    
                    # Preencher o dicionário form_registro com os valores do banco
                    print(f"Valores originais do registro: {registro}")
                    for db_campo, form_campo in campo_mapping.items():
                        if db_campo in registro and registro[db_campo] is not None:
                            form_registro[form_campo] = registro[db_campo]
                            print(f"Mapeado: {db_campo} -> {form_campo} = {registro[db_campo]}")
                        else:
                            print(f"Campo não encontrado ou nulo: {db_campo}")
                    
                    # Substituir o registro original pelo mapeado para o formulário
                    registro = form_registro
                    
                    # Adicionar o ID do registro para referência
                    registro['id'] = row['id']
                    
                    # Registrar no log para debug
                    print(f"Registro carregado para edição/visualização: {registro}")
        except Exception as e:
            logging.error(f"Erro ao buscar registro: {e}")
            flash('Erro ao carregar o registro para edição.', 'danger')

    # Recarregar dados do Excel para garantir que estão atualizados
    try:
        excel_processor.load_data()
    except Exception as e:
        logging.error(f"Erro ao carregar dados do Excel: {e}")
        flash('Erro ao carregar dados do Excel. Alguns campos podem não estar disponíveis.', 'warning')

    # Campos obrigatórios
    campos_obrigatorios = ['UNIDADE', 'CLIENTE', 'MOTORISTA', 'CPF MOTORISTA', 'CAVALO', 'CONTAINER 1']

    # Tipos de campos
    tipos = {}
    for field_name, field_type in excel_processor.TIPOS_DE_DADOS.items():
        tipos[field_name] = field_type

    # Valores para os dropdowns
    campos = {
        'UNIDADE': ['Rio de Janeiro', 'Floriano', 'Suzano'],
        'MODALIDADE': ['IMPORTAÇÃO', 'EXPORTAÇÃO', 'CABOTAGEM', 'CST'],
        'STATUS CONTAINER': ['CHEIO', 'VAZIO'],
        'GERENCIADORA': ['GR1', 'GR2', 'GR3']
    }
    
    # Adicionar TIPO DE CARGA da aba principal (Página1) da planilha
    if 'TIPO DE CARGA' in excel_processor.df.columns:
        tipos_carga = excel_processor.df['TIPO DE CARGA'].dropna().unique().tolist()
        if tipos_carga:
            campos['TIPO DE CARGA'] = tipos_carga
            print(f"Tipos de carga carregados da planilha: {tipos_carga}")
        else:
            campos['TIPO DE CARGA'] = ['GERAL', 'PERIGOSA', 'REFRIGERADA']  # Valores padrão caso não encontre na planilha

    # Adicionar dados do Excel para os dropdowns
    if excel_processor.df_placas is not None:
        # Motoristas - usado para o campo MOTORISTA
        motorista_col = excel_processor.COLUNAS_PLACAS.get('MOTORISTA')
        if motorista_col:
            motoristas = excel_processor.df_placas[motorista_col].dropna().unique().tolist()
            campos['MOTORISTA'] = motoristas
            
        # Cavalos (placas) - usado para o campo CAVALO
        placa_col = excel_processor.COLUNAS_PLACAS.get('PLACA')
        if placa_col:
            placas = excel_processor.df_placas[placa_col].dropna().unique().tolist()
            campos['CAVALO'] = placas
            
        # Carretas - usado para os campos CARRETA 1 e CARRETA 2
        carreta_col = excel_processor.COLUNAS_PLACAS.get('CARRETA')
        if carreta_col:
            carretas = excel_processor.df_placas[carreta_col].dropna().unique().tolist()
            # Usar a mesma lista de carretas para ambos os campos
            campos['CARRETAS'] = carretas

    # Determinar se estamos no modo de visualizau00e7u00e3o (quando registro_id estu00e1 presente)
    modo_visualizacao = True if request.args.get('registro_id') else False
    
    return render_template('form_new.html',
                           usuario=session.get('user'),
                           nivel=session.get('nivel'),
                           registro=registro,
                           CAMPOS_OBRIGATORIOS=campos_obrigatorios,
                           tipos=tipos,
                           campos=campos,
                           COMBOBOX_OPTIONS=campos,
                           MOTORISTA_CPF_MAP=excel_processor.MOTORISTA_CPF_MAP,
                           modo_visualizacao=modo_visualizacao)

@comum_bp.route('/visualizar_registro/<int:registro_id>', methods=['GET', 'POST'])
@login_required
def visualizar_registro(registro_id):
    try:
        logging.info(f"Visualizando registro com ID: {registro_id}")
        print(f"DEBUG: Iniciando visualização do registro {registro_id}")
        
        # Se for uma requisição POST, redirecionar para a rota de edição
        if request.method == 'POST':
            return redirect(url_for('comum.editar_registro_comum', registro_id=registro_id))
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Obter dados do registro
            cursor.execute("SELECT * FROM registros WHERE id = ? AND excluido = 0", (registro_id,))
            row = cursor.fetchone()
            
            if not row:
                flash("Registro não encontrado.", "danger")
                if session.get('nivel') == 'gr':
                    return redirect(url_for('gr.ambiente'))
                else:
                    return redirect(url_for('comum.dashboard_comum'))
            
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
            nivel = session.get('nivel', 'comum')
            
            # Para visualização, mostrar todas as seções disponíveis
            todas_secoes = ['unidade', 'cliente', 'transporte', 'cargas', 'observacoes', 'notas', 'documentos', 'gr']
            
            # Obter histórico de alterações do registro
            try:
                print(f"DEBUG: Consultando histórico para o registro {registro_id}")
                cursor.execute("""
                    SELECT id, registro_id, alterado_por, alteracoes, data_alteracao
                    FROM historico
                    WHERE registro_id = ?
                    ORDER BY data_alteracao DESC
                """, (registro_id,))
                
                # Verificar se a tabela historico existe
                historico_rows = cursor.fetchall()
                print(f"DEBUG: Encontradas {len(historico_rows)} entradas no histórico")
                
                # Processar os resultados com segurança
                historico = []
                for hist_row in historico_rows:
                    hist_dict = {}
                    for i, value in enumerate(hist_row):
                        column_name = cursor.description[i][0]
                        hist_dict[column_name] = value
                    # Mapear os nomes das colunas para os nomes esperados pelo template
                    hist_dict['usuario'] = hist_dict.get('alterado_por', 'N/A')
                    hist_dict['nivel'] = session.get('nivel', 'comum')  # Usar nível do usuário atual
                    hist_dict['acao'] = 'Alteração'
                    hist_dict['detalhes'] = hist_dict.get('alteracoes', 'N/A')
                    historico.append(hist_dict)
            except Exception as hist_error:
                print(f"DEBUG: Erro ao processar histórico: {hist_error}")
                historico = []  # Usar uma lista vazia em caso de erro
            
            # Preparar dados para renderização do template
            print(f"DEBUG: Preparando dados para renderização do template")
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
                'campo_visivel': lambda campo, nivel: True,  # Mostrar todos os campos
                'campo_editavel': campo_editavel,
                'tem_anexos': tem_anexos,
                'historico': historico
            }
            
            print(f"DEBUG: Renderizando template visualizar_registro.html")
            return render_template('visualizar_registro.html', **template_data)
    
    except Exception as e:
        logging.error(f"Erro ao visualizar registro: {e}")
        flash(f"Erro ao visualizar registro: {str(e)}", "danger")
        if session.get('nivel') == 'gr':
            return redirect(url_for('gr.ambiente'))
        else:
            return redirect(url_for('comum.dashboard_comum'))

@comum_bp.route('/delete_registro/<int:registro_id>', methods=['POST'])
@login_required
def delete_registro(registro_id):
    try:
        usuario_atual = session.get('user', '')
        nivel_atual = session.get('nivel', '')
        
        # Verificar se o usuário tem permissão para excluir registros
        if nivel_atual == 'gr':
            flash('Usuários GR não têm permissão para excluir registros.', 'danger')
            return redirect(url_for('gr.ambiente'))
        
        # Verificar se o registro existe
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, usuario FROM registros WHERE id = ? AND excluido = 0", (registro_id,))
            registro = cursor.fetchone()
            
            if not registro:
                flash('Registro não encontrado.', 'danger')
                return redirect(url_for('comum.dashboard_comum'))
            
            # Verificar se o usuário comum só pode excluir seus próprios registros
            if nivel_atual == 'comum' and usuario_atual != registro['usuario']:
                flash('Você só pode excluir seus próprios registros.', 'danger')
                return redirect(url_for('comum.dashboard_comum'))
            
            # Implementar exclusão lógica (marcar como excluído)
            cursor.execute("""
                UPDATE registros 
                SET excluido = 1, 
                    data_exclusao = ?, 
                    excluido_por = ?
                WHERE id = ?
            """, (
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                usuario_atual,
                registro_id
            ))
            conn.commit()
            
            # Tentativa de registrar no histórico (simplificado)
            try:
                cursor.execute("""
                    INSERT INTO historico 
                    (registro_id, alterado_por, alteracoes, data_alteracao) 
                    VALUES (?, ?, ?, ?)
                """, (
                    registro_id, 
                    usuario_atual, 
                    '{"acao": "exclusao", "detalhes": "Registro excluido"}',
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                ))
                conn.commit()
            except Exception as hist_error:
                # Ignorar erros de histórico, apenas registrar
                logging.error(f"Erro ao registrar histórico (não crítico): {hist_error}")
                # Continuar com a exclusão mesmo se o histórico falhar
                pass
            
            flash('Registro excluído com sucesso!', 'success')
            return redirect(url_for('comum.dashboard_comum'))
            
    except Exception as e:
        logging.error(f"Erro ao excluir registro: {e}")
        flash(f'Erro ao excluir registro: {str(e)}', 'danger')
        return redirect(url_for('comum.dashboard_comum'))

# ========================
# ROTAS - GR (gr_bp)
# ========================

# Rota /ambiente implementada abaixo

# ========================
# ROTAS - ADMIN (admin_bp)
# ========================

# Todas as rotas administrativas foram movidas para o arquivo admin_routes.py

# Esta rota foi movida para auth.routes.py

# Esta rota foi movida para auth.routes.py

# Esta rota foi movida para auth.routes.py

# ========================
# ROTAS DO BLUEPRINT MAIN
# ========================

# Esta função foi movida para auth.routes.py
from auth.routes import redirecionar_por_nivel

# Nova rota específica para visualização de registros
from models.busca_global import busca_global, contar_busca_global

@main_bp.route('/view_registros')
@login_required
def view_registros():
    try:
        usuario = session.get('user')
        nivel = session.get('nivel')
        
        # Verificar se o usuário tem permissão adequada
        # Se for admin ou GR, eles têm suas próprias páginas específicas, mas podem acessar esta também
        if nivel not in ['admin', 'gr', 'comum']:
            logging.warning(f"Usuário {usuario} com nível desconhecido ({nivel}) tentou acessar view_registros")
            flash("Você não tem permissão para acessar esta página.", "danger")
            return redirect(url_for('auth.login'))
            
        logging.info(f"Usuário {usuario} (nível {nivel}) acessando view_registros")
    
        # Paginação
        page = request.args.get('page', 1, type=int)
        per_page = 15
        offset = (page - 1) * per_page
        
        # Filtros
        placa = request.args.get('placa', '')
        motorista = request.args.get('motorista', '')
        tipo_filtro = request.args.get('filtro', '')
        termo_busca = request.args.get('termo_busca', '')
        
        registros = []
        total = 0
        
        # Verificar se estamos fazendo uma busca global
        if termo_busca and termo_busca.strip() != '':
            # Usar nossa nova função de busca global
            registros = busca_global(termo_busca, per_page, offset)
            total = contar_busca_global(termo_busca)
            logging.info(f"Busca global por '{termo_busca}' encontrou {total} registros")
        else:
            # Construir as condições de filtro padrão
            filtros = {}
            
            # Filtros específicos
            if placa:
                filtros['placa'] = placa
            if motorista:
                filtros['motorista'] = motorista
                
            # Processar filtros específicos dos cards
            if tipo_filtro == 'sem_nf':
                filtros['sem_nf'] = True
            elif tipo_filtro == 'sem_os':
                filtros['sem_os'] = True
            elif tipo_filtro == 'sem_container':
                filtros['sem_container'] = True
            elif tipo_filtro == 'sem_sm':
                filtros['sem_sm'] = True
            elif tipo_filtro == 'sem_ae':
                filtros['sem_ae'] = True
                
            # Usar o método get_all original para filtros padrão
            registros = Registro.get_all(per_page, offset, filtros)
            total = Registro.count(filtros)
    except Exception as e:
        logging.error(f"Erro ao carregar registros: {str(e)}")
        flash(f"Ocorreu um erro ao carregar os registros. Por favor, tente novamente.", "danger")
        return redirecionar_por_nivel()
    
    try:
        # Usuários comuns também podem ver e atualizar todos os registros
        # A única restrição é que não podem apagar registros que não criaram
        
        # Formatar as datas para o formato solicitado
        for registro in registros:
            # Formatar "On Time" no formato "HH:MM:SS DD-MM-AAAA"
            if registro.get('on_time_cliente'):
                try:
                    data_on_time = datetime.strptime(registro['on_time_cliente'], '%Y-%m-%d %H:%M:%S')
                    registro['on_time_cliente'] = data_on_time.strftime('%H:%M:%S %d-%m-%Y')
                except (ValueError, TypeError):
                    pass  # Mantém o valor original se não conseguir converter
                    
            # Formatar "Horário Previsto" (agora "Saída Prevista") no formato "HH:MM:SS DD-MM-AAAA"
            if registro.get('horario_previsto'):
                try:
                    data_prevista = datetime.strptime(registro['horario_previsto'], '%Y-%m-%d %H:%M:%S')
                    registro['horario_previsto'] = data_prevista.strftime('%H:%M:%S %d-%m-%Y')
                except (ValueError, TypeError):
                    pass  # Mantém o valor original se não conseguir converter
        
        # Calcular total de páginas para paginação
        total_pages = (total + per_page - 1) // per_page  # Arredondar para cima
        
        # Obter lista de placas e motoristas para filtros
        placas = []
        motoristas = []
        
        # KPIs - Contadores para estatísticas
        operacoes_sem_nf = 0
        operacoes_sem_os = 0
        operacoes_sem_container1 = 0
        operacoes_sem_sm = 0
        operacoes_sem_ae = 0
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Placas disponíveis para o usuário
                cursor.execute(
                    "SELECT DISTINCT placa FROM registros WHERE placa IS NOT NULL AND placa != '' AND excluido = 0 ORDER BY placa"
                )
                placas = [row[0] for row in cursor.fetchall() if row[0]]
                
                # Motoristas disponíveis para o usuário
                cursor.execute(
                    "SELECT DISTINCT motorista FROM registros WHERE motorista IS NOT NULL AND motorista != '' AND excluido = 0 ORDER BY motorista"
                )
                motoristas = [row[0] for row in cursor.fetchall() if row[0]]
                
                # Cálculo dos KPIs
                # 1. Operações sem NF anexada
                cursor.execute(
                    "SELECT COUNT(*) FROM registros WHERE (anexar_nf IS NULL OR anexar_nf = 0 OR anexar_nf = '') AND excluido = 0"
                )
                operacoes_sem_nf = cursor.fetchone()[0]
                
                # 2. Operações sem OS anexada
                cursor.execute(
                    "SELECT COUNT(*) FROM registros WHERE (anexar_nf IS NULL OR anexar_nf = '') AND excluido = 0"
                )
                operacoes_sem_nf = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM registros WHERE (anexar_os IS NULL OR anexar_os = '') AND excluido = 0")
                operacoes_sem_os = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM registros WHERE (container_1 IS NULL OR container_1 = '') AND excluido = 0")
                operacoes_sem_container1 = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM registros WHERE (numero_sm IS NULL OR numero_sm = '') AND excluido = 0")
                operacoes_sem_sm = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM registros WHERE (numero_ae IS NULL OR numero_ae = '') AND excluido = 0")
                operacoes_sem_ae = cursor.fetchone()[0]
                
        except Exception as e:
            logging.error(f"Erro ao carregar filtros e estatísticas: {e}")
            flash(f"Erro ao carregar filtros e estatísticas: {e}", "warning")
            # Continua a execução para mostrar os registros mesmo sem os filtros
        
        return render_template(
            'gr_ambiente.html',
            usuario=usuario,
            nivel=nivel,
            registros=registros,
            page=page,
            total_pages=total_pages,
            placas=placas,
            motoristas=motoristas,
            placa_filtro=placa,
            motorista_filtro=motorista,
            # Adiciona os KPIs para o template
            operacoes_sem_nf=operacoes_sem_nf,
            operacoes_sem_os=operacoes_sem_os,
            operacoes_sem_container1=operacoes_sem_container1,
            operacoes_sem_sm=operacoes_sem_sm,
            operacoes_sem_ae=operacoes_sem_ae
        )
    except Exception as e:
        logging.error(f"Erro ao processar registros: {str(e)}")
        flash(f"Ocorreu um erro ao processar os dados. Por favor, tente novamente.", "danger")
        return redirecionar_por_nivel()

# Rota para gerenciamento de registros (mantida para compatibilidade com links existentes)
@main_bp.route('/gerenciar_registros')
@login_required
def gerenciar_registros():
    # Esta rota é mantida para compatibilidade com links existentes
    # Redireciona para a nova rota de visualização de registros que possui
    # todas as funcionalidades necessárias para gerenciamento
    return redirect(url_for('main.view_registros'))

# Rota para edição de registro
@main_bp.route('/editar/<int:registro_id>', methods=['GET', 'POST'])
@login_required
def editar_registro(registro_id):
    return processar_edicao_registro(registro_id)


# Rota para edição de registros para usuários comuns
@comum_bp.route('/editar_registro/<int:registro_id>', methods=['GET', 'POST'])
@login_required
def editar_registro_comum(registro_id):
    """Rota para edição de registros para usuários comuns"""
    # Adicionar log detalhado para depuração
    print(f"\n===== ROTA editar_registro_comum CHAMADA PARA ID {registro_id} =====\n")
    print(f"Método da requisição: {request.method}")
    
    # Verificar se há dados no formulário
    if request.method == 'POST':
        print("\n=== DADOS DO FORMULÁRIO RECEBIDOS ===\n")
        print(f"Form data: {request.form.to_dict()}")
        print(f"Files: {list(request.files.keys())}")
        
        # Para cada arquivo, verificar se há conteúdo
        for file_key in request.files:
            file = request.files[file_key]
            if file and file.filename:
                print(f"Arquivo '{file_key}': {file.filename} ({len(file.read())} bytes)")
                # Importante: resetar o cursor do arquivo após a leitura
                file.seek(0)
            else:
                print(f"Arquivo '{file_key}': Nenhum arquivo ou nome vazio")
        
        # Usar a função de processamento direto consolidada para garantir que os dados sejam salvos
        try:
            # Importar a função de processamento direto consolidada
            from operations.registros_direto_final import processar_edicao_registro_direto
            
            # Processar a edição diretamente com a função consolidada
            resultado = processar_edicao_registro_direto(registro_id)
            
            if resultado is True:
                print("Edição direta bem-sucedida - Redirecionando para dashboard")
                flash("Registro atualizado com sucesso!", "success")
                return redirect(url_for('comum.dashboard_comum'))
            else:
                print("Edição direta falhou - Redirecionando para dashboard com mensagem de erro")
                flash("Erro ao atualizar o registro. Por favor, tente novamente.", "error")
                return redirect(url_for('comum.dashboard_comum'))
        except Exception as e:
            import traceback
            print(f"\n=== ERRO AO PROCESSAR EDIÇÃO DIRETA ===\n")
            print(f"Erro: {str(e)}")
            print(traceback.format_exc())
            flash(f"Erro ao processar a edição: {str(e)}", "error")
            return redirect(url_for('comum.dashboard_comum'))
    
    # Se for GET, usar a função original para exibir o formulário
    try:
        from operations.registros import exibir_formulario_edicao
        return exibir_formulario_edicao(registro_id)
    except Exception as e:
        import traceback
        print(f"\n=== ERRO AO EXIBIR FORMULÁRIO DE EDIÇÃO ===\n")
        print(f"Erro: {str(e)}")
        print(traceback.format_exc())
        flash(f"Erro ao exibir formulário de edição: {str(e)}", "error")
        return redirect(url_for('comum.dashboard_comum'))

# Rota para exclusão lógica de registro
@main_bp.route('/delete/<int:registro_id>')
@login_required
def delete(registro_id):
    nivel_usuario = session.get('nivel', 'comum')
    usuario = session.get('user')
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Buscar o registro e seu criador
        cursor.execute("SELECT id, usuario FROM registros WHERE id = ? AND excluido = 0", (registro_id,))
        registro = cursor.fetchone()
        
        if not registro:
            flash("Registro não encontrado.", "danger")
            return redirect(url_for('main.view_registros'))
        
        registro_id, usuario_criador = registro
        
        # Verificar permissões conforme as novas regras de negócio:
        # Admin - pode excluir qualquer registro
        # GR - NÃO PODE EXCLUIR NENHUM REGISTRO
        # Comum - pode excluir qualquer registro de usuário comum
        permitido = False
        motivo_log = ""
        
        if nivel_usuario == 'admin':
            permitido = True
            motivo_log = "Exclusão por administrador"
        elif nivel_usuario == 'gr':
            # Usuários GR NÃO PODEM EXCLUIR REGISTROS
            permitido = False
            motivo_log = "Usuários GR não têm permissão para excluir registros"
        elif nivel_usuario == 'comum':
            # Verificar se o usuário criador é um usuário comum
            cursor.execute("SELECT nivel FROM usuarios WHERE username = ?", (usuario_criador,))
            nivel_criador_record = cursor.fetchone()
            
            if nivel_criador_record is None:
                # Se não encontrar o usuário no banco, registrar no log e permitir a exclusão (comum por padrão)
                logging.warning(f"Usuário criador '{usuario_criador}' não encontrado no banco de dados")
                nivel_criador = 'comum'  # Assume nível comum por segurança
            else:
                nivel_criador = nivel_criador_record[0]
            
            if nivel_criador == 'comum':
                permitido = True
                motivo_log = f"Exclusão de registro de usuário comum por outro usuário comum ({usuario})"
            else:
                permitido = False
                motivo_log = "Usuários comuns não podem excluir registros de administradores ou GRs"
                
        if not permitido:
            # Registrar tentativa não autorizada no log
            if nivel_usuario in ['gr', 'admin']:
                from models.admin.logs import log_admin_action
                log_admin_action(usuario, "TENTATIVA DE EXCLUSÃO NÃO AUTORIZADA", 
                               f"Registro ID: {registro_id}, Criado por: {usuario_criador}, Motivo: {motivo_log}")
                
            flash("Você não tem permissão para apagar este registro.", "danger")
            return redirect(url_for('main.view_registros'))
        
        # Exclusão lógica autorizada
        cursor.execute("SELECT * FROM registros WHERE id = ?", (registro_id,))
        registro_completo = cursor.fetchone()
        
        # Data atual para registrar quando o registro foi excluído
        data_exclusao = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Executar a exclusão lógica (marcar como excluído em vez de remover)
        cursor.execute("UPDATE registros SET excluido = 1, data_exclusao = ?, excluido_por = ? WHERE id = ?", 
                    (data_exclusao, usuario, registro_id))
        conn.commit()
        
        # Registrar a ação no log de administração (para GR e admin)
        if nivel_usuario in ['gr', 'admin']:
            from models.admin.logs import log_admin_action
            log_admin_action(usuario, "EXCLUSÃO LÓGICA DE REGISTRO", 
                          f"Registro ID: {registro_id}, Criado por: {usuario_criador}, Motivo: {motivo_log}")

    # Também registrar no log geral
    logging.info(f"Registro ID {registro_id} marcado como excluído por {usuario} em {data_exclusao}")
    flash("Registro excluído com sucesso.", "success")
    return redirect(url_for('main.view_registros'))

# Função auxiliar para manipulação de anexos
def handle_anexo(registro_id, tipo, download=False):
    """Função centralizada para manipular anexos, seja para download ou visualização"""
    print(f"Iniciando {'download' if download else 'visualizar'}_anexo para registro_id={registro_id}, tipo={tipo}")
    try:
        # Mapear o tipo para a coluna correta no banco de dados
        mapeamento_colunas = {
            'nf': 'anexar_nf',
            'os': 'anexar_os',
            'agendamento': 'anexar_agendamento'
        }
        
        if tipo not in mapeamento_colunas:
            flash('Tipo de anexo inválido.', 'danger')
            return redirect(url_for('comum.dashboard_comum'))
        
        coluna_arquivo = mapeamento_colunas[tipo]
        
        # Conectar ao banco de dados
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Verificar se a coluna de nome do arquivo existe para este tipo
            coluna_nome = None
            if tipo == 'nf':
                coluna_nome = 'arquivo_nf_nome'
            
            # Obter todas as colunas para debug
            cursor.execute("PRAGMA table_info(registros)")
            colunas = [info[1] for info in cursor.fetchall()]
            print(f"Colunas na tabela registros: {colunas}")
            
            # Se tiver coluna de nome, buscar também
            if coluna_nome and coluna_nome in colunas:
                query = f"SELECT {coluna_arquivo}, {coluna_nome} FROM registros WHERE id = ? AND excluido = 0"
            else:
                query = f"SELECT {coluna_arquivo} FROM registros WHERE id = ? AND excluido = 0"
            
            print(f"Executando query: {query}")
            cursor.execute(query, (registro_id,))
            resultado = cursor.fetchone()
            print(f"Resultado da query: {resultado}")
            
            if not resultado:
                flash('Dados do registro não encontrados.', 'danger')
                return redirect(url_for('comum.visualizar_registro', registro_id=registro_id))
            
            # Verificar se o caminho do arquivo existe
            caminho_relativo = resultado[0] if resultado[0] else None  # Caminho relativo do arquivo
            
            if not caminho_relativo:
                flash(f'Arquivo não encontrado.', 'danger')
                return redirect(url_for('comum.visualizar_registro', registro_id=registro_id))
            
            # Obter o nome do arquivo ou criar um nome padrão
            nome_arquivo = None
            if len(resultado) > 1 and resultado[1]:
                nome_arquivo = resultado[1]
            
            # Se o nome não estiver disponível, extrair do caminho ou usar um nome padrão
            if not nome_arquivo:
                # Tentar extrair o nome do arquivo do caminho
                if caminho_relativo:
                    nome_arquivo = os.path.basename(caminho_relativo)
                else:
                    nome_arquivo = f"anexo_{tipo}_{registro_id}.pdf"
            
            print(f"Caminho relativo: {caminho_relativo}")
            print(f"Nome do arquivo: {nome_arquivo}")
            
            # Normalizar o caminho relativo
            caminho_relativo = caminho_relativo.replace('\\', '/')
            
            # Remover 'static/' do início do caminho se estiver presente
            if caminho_relativo.startswith('static/'):
                caminho_relativo = caminho_relativo[7:]
            
            # Verificar se o caminho é uma URL ou um caminho local
            if caminho_relativo.startswith('http://') or caminho_relativo.startswith('https://'):
                # Se for uma URL, redirecionar para ela
                if download:
                    return redirect(caminho_relativo)
                else:
                    # Para visualização, podemos mostrar em um iframe
                    return render_template('visualizar_url.html', url=caminho_relativo, titulo=f"Visualizar {tipo.upper()}")
            
            # Verificar se o caminho relativo é um caminho completo ou apenas um nome de arquivo
            if '/' in caminho_relativo or '\\' in caminho_relativo:
                # Caminho absoluto para o arquivo
                caminho_absoluto = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', caminho_relativo)
            else:
                # Se for apenas um nome de arquivo, procurar na pasta uploads
                caminho_absoluto = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', caminho_relativo)
            
            # Verificar se o caminho existe, se não, tentar alternativas
            if not os.path.exists(caminho_absoluto):
                # Lista de possíveis locais para buscar o arquivo
                possiveis_caminhos = [
                    # Caminho alternativo (direto do diretório raiz)
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), caminho_relativo),
                    # Caminho completo
                    caminho_relativo,
                    # Apenas o nome do arquivo na pasta uploads
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', os.path.basename(caminho_relativo)),
                    # Apenas o nome do arquivo na pasta raiz
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.path.basename(caminho_relativo)),
                    # Nome do arquivo com prefixo padrão na pasta uploads
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', f"{tipo}_{registro_id}_{os.path.basename(caminho_relativo)}"),
                    # Nome do arquivo com prefixo padrão na pasta raiz
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{tipo}_{registro_id}_{os.path.basename(caminho_relativo)}"),
                    # Verificar na pasta uploads sem static
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads', os.path.basename(caminho_relativo)),
                    # Verificar na pasta uploads com o ID do registro
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads', f"{tipo}_{registro_id}.{caminho_relativo.split('.')[-1]}"),
                    # Verificar na pasta static/uploads com o ID do registro
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', f"{tipo}_{registro_id}.{caminho_relativo.split('.')[-1]}"),
                    # Verificar na pasta uploads com o nome original
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads', nome_arquivo),
                    # Verificar na pasta static/uploads com o nome original
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', nome_arquivo),
                    # Verificar com o prefixo 'anexar_'
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', f"anexar_{tipo}_{registro_id}_{os.path.basename(caminho_relativo)}"),
                    # Verificar com o prefixo 'anexar_' e timestamp genérico
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', f"anexar_{tipo}_*_{os.path.basename(caminho_relativo)}"),
                    # Verificar na pasta static
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', f"{tipo}_{registro_id}_{os.path.basename(caminho_relativo)}"),
                    # Verificar na pasta static com nome do arquivo
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', nome_arquivo),
                    # Verificar na pasta static com o nome do arquivo original
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', os.path.basename(caminho_relativo)),
                ]
                
                # Tentar cada um dos caminhos possíveis
                arquivo_encontrado = False
                for caminho_possivel in possiveis_caminhos:
                    print(f"Tentando caminho: {caminho_possivel}")
                    # Verificar se o caminho contém um padrão glob (asterisco)
                    if '*' in caminho_possivel:
                        # Usar glob para encontrar arquivos que correspondam ao padrão
                        import glob
                        arquivos_correspondentes = glob.glob(caminho_possivel)
                        print(f"Arquivos correspondentes ao padrão {caminho_possivel}: {arquivos_correspondentes}")
                        if arquivos_correspondentes:
                            # Usar o primeiro arquivo encontrado
                            caminho_absoluto = arquivos_correspondentes[0]
                            print(f"Arquivo encontrado com padrão glob: {caminho_absoluto}")
                            arquivo_encontrado = True
                            break
                    elif os.path.exists(caminho_possivel):
                        caminho_absoluto = caminho_possivel
                        print(f"Arquivo encontrado em: {caminho_absoluto}")
                        arquivo_encontrado = True
                        break
                
                # Se não encontrou o arquivo, tentar buscar qualquer arquivo com o tipo e ID do registro
                if not arquivo_encontrado:
                    print(f"Tentando encontrar qualquer arquivo para {tipo}_{registro_id}")
                    import glob
                    padroes_genericos = [
                        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', f"{tipo}_{registro_id}*"),
                        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', f"anexar_{tipo}_{registro_id}*"),
                        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', f"{tipo}_{registro_id}*"),
                    ]
                    
                    for padrao in padroes_genericos:
                        arquivos = glob.glob(padrao)
                        print(f"Arquivos encontrados com padrão {padrao}: {arquivos}")
                        if arquivos:
                            caminho_absoluto = arquivos[0]
                            print(f"Arquivo encontrado com padrão genérico: {caminho_absoluto}")
                            arquivo_encontrado = True
                            break
            print(f"Caminho absoluto do arquivo: {caminho_absoluto}")
            
            # Verificar se o arquivo existe no sistema de arquivos
            if not os.path.exists(caminho_absoluto):
                print(f"Arquivo não encontrado no caminho: {caminho_absoluto}")
                flash('Arquivo não encontrado no sistema.', 'danger')
                # Redirecionar de volta para a página de visualização do registro, não para o dashboard
                return redirect(url_for('comum.visualizar_registro', registro_id=registro_id))
            
            # Determinar o tipo MIME
            extensao = nome_arquivo.split('.')[-1].lower() if '.' in nome_arquivo else 'pdf'
            mime_types = {
                'pdf': 'application/pdf',
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'png': 'image/png',
                'doc': 'application/msword',
                'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            }
            mime_type = mime_types.get(extensao, 'application/octet-stream')
            
            if download:
                print(f"Enviando arquivo para download: {nome_arquivo}, tipo MIME: {mime_type}")
                # Verificar se o arquivo realmente existe antes de enviar
                if not os.path.exists(caminho_absoluto):
                    flash(f"Arquivo não encontrado: {nome_arquivo}", "danger")
                    return redirect(url_for('comum.visualizar_registro', registro_id=registro_id))
                    
                try:
                    # Forçar o download definindo as_attachment como True
                    # Usar nome_arquivo como download_name para garantir que o arquivo baixado tenha o nome correto
                    response = send_file(
                        caminho_absoluto,
                        as_attachment=True,
                        download_name=nome_arquivo,
                        mimetype=mime_type
                    )
                    # Adicionar headers para forçar o download
                    response.headers["Content-Disposition"] = f"attachment; filename={nome_arquivo}"
                    response.headers["X-Content-Type-Options"] = "nosniff"
                    return response
                except Exception as e:
                    print(f"Erro ao enviar arquivo para download: {e}")
                    flash(f"Erro ao baixar arquivo: {str(e)}", "danger")
                    return redirect(url_for('comum.visualizar_registro', registro_id=registro_id))
            else:
                print(f"Enviando arquivo para visualização: {nome_arquivo}, tipo MIME: {mime_type}")
                
                # Verificar se é um documento Office (docx, xlsx, pptx) ou PDF
                office_extensions = ['docx', 'xlsx', 'pptx', 'doc', 'xls', 'ppt']
                viewable_extensions = ['pdf', 'jpg', 'jpeg', 'png', 'gif']
                
                # Se for um documento Office, retornar o arquivo para download mas sem redirecionar
                # Isso permite que o JavaScript no frontend decida como exibir o arquivo
                if extensao in office_extensions:
                    tipo_nome = {
                        'nf': 'Nota Fiscal',
                        'os': 'Ordem de Serviço',
                        'agendamento': 'Agendamento'
                    }.get(tipo, tipo.upper())
                    
                    # Definir um header especial para informar o frontend que este é um documento Office
                    response = send_file(
                        caminho_absoluto,
                        as_attachment=False,  # Importante: False para que o frontend decida
                        download_name=nome_arquivo,
                        mimetype=mime_type
                    )
                    response.headers["X-Document-Type"] = "office"
                    return response
                
                # Se for um tipo visualizável (PDF ou imagem), mostrar no navegador
                # Para todos os outros tipos de arquivos, tentar visualização direta no navegador
                return send_file(
                    caminho_absoluto,
                    as_attachment=False,  # Importante: False para visualizar no navegador
                    download_name=nome_arquivo,
                    mimetype=mime_type
                )
            
    except Exception as e:
        import traceback
        acao = "baixar" if download else "visualizar"
        print(f"ERRO AO {acao.upper()} ANEXO: {e}")
        print(traceback.format_exc())
        flash(f'Erro ao {acao} anexo: {str(e)}', 'danger')
        return redirect(url_for('comum.dashboard_comum'))

# Rota para editar anexos
@comum_bp.route('/editar_anexo/<int:registro_id>/<tipo>', methods=['GET', 'POST'])
@login_required
def editar_anexo(registro_id, tipo):
    try:
        # Importar funções de controle de acesso
        from access_control import campo_editavel
        
        # Verificar permissões para editar anexos
        nivel_usuario = session.get('nivel')
        
        # Mapear o tipo para o nome do campo no formulário
        campo_form_map = {
            'nf': 'ANEXAR NF',
            'os': 'ANEXAR OS',
            'agendamento': 'ANEXAR AGENDAMENTO'
        }
        
        # Verificar se o usuário tem permissão para editar este tipo de anexo
        if not campo_editavel(campo_form_map[tipo], nivel_usuario):
            flash('Você não tem permissão para editar este tipo de anexo.', 'danger')
            return redirect(url_for('comum.visualizar_registro', registro_id=registro_id))
            
        # Verificar se o tipo é válido
        if tipo not in ['nf', 'os', 'agendamento']:
            flash('Tipo de anexo inválido.', 'danger')
            return redirect(url_for('comum.dashboard_comum'))
            
        # Mapear o tipo para o nome da coluna no banco de dados
        tipo_map = {
            'nf': 'anexar_nf',
            'os': 'anexar_os',
            'agendamento': 'anexar_agendamento'
        }
        
        nome_map = {
            'nf': 'arquivo_nf_nome',
            'os': 'arquivo_os_nome',
            'agendamento': 'arquivo_agendamento_nome'
        }
        
        coluna_arquivo = tipo_map[tipo]
        coluna_nome = nome_map[tipo]
        
        # Verificar se o registro existe
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM registros WHERE id = ? AND excluido = 0", (registro_id,))
            if not cursor.fetchone():
                flash('Registro não encontrado.', 'danger')
                return redirect(url_for('comum.dashboard_comum'))
        
        # Se for um POST, processar o upload do novo arquivo
        if request.method == 'POST':
            if 'arquivo' not in request.files:
                flash('Nenhum arquivo enviado.', 'danger')
                return redirect(request.url)
                
            arquivo = request.files['arquivo']
            
            if arquivo.filename == '':
                flash('Nenhum arquivo selecionado.', 'danger')
                return redirect(request.url)
                
            if arquivo:
                # Obter extensão do arquivo
                _, extensao = os.path.splitext(arquivo.filename)
                extensao = extensao.lower()
                
                # Verificar se a extensão é permitida
                extensoes_permitidas = ['.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png', '.xls', '.xlsx', '.txt']
                if extensao not in extensoes_permitidas:
                    flash(f'Tipo de arquivo não permitido. Extensões permitidas: {", ".join(extensoes_permitidas)}', 'danger')
                    return redirect(request.url)
                
                # Verificar tamanho do arquivo (limite de 10MB)
                if len(arquivo.read()) > 10 * 1024 * 1024:  # 10MB em bytes
                    arquivo.seek(0)  # Resetar o ponteiro do arquivo
                    flash('O arquivo excede o tamanho máximo permitido de 10MB.', 'danger')
                    return redirect(request.url)
                
                arquivo.seek(0)  # Resetar o ponteiro do arquivo após a leitura
                
                # Criar nome de arquivo único com timestamp
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                nome_arquivo = f"anexar_{tipo}_{timestamp}_{secure_filename(arquivo.filename)}"
                
                # Caminho para salvar o arquivo
                caminho_relativo = os.path.join('uploads', nome_arquivo)
                
                # Caminho absoluto para o diretório static
                static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
                
                # Caminho absoluto para o diretório uploads dentro de static
                uploads_dir = os.path.join(static_dir, 'uploads')
                
                # Caminho absoluto completo para o arquivo
                caminho_absoluto = os.path.join(static_dir, caminho_relativo)
                
                # Garantir que o diretório de uploads existe
                print(f"Criando diretório de uploads: {uploads_dir}")
                try:
                    if not os.path.exists(uploads_dir):
                        os.makedirs(uploads_dir, exist_ok=True)
                    print(f"Diretório de uploads criado/verificado com sucesso: {uploads_dir}")
                except Exception as e:
                    print(f"Erro ao criar diretório de uploads: {e}")
                    flash(f"Erro ao criar diretório para upload: {str(e)}", "danger")
                    return redirect(request.url)
                
                # Salvar o arquivo com tratamento de erros
                try:
                    print(f"Tentando salvar arquivo em: {caminho_absoluto}")
                    arquivo.save(caminho_absoluto)
                    print(f"Arquivo salvo com sucesso em: {caminho_absoluto}")
                except Exception as e:
                    print(f"Erro ao salvar arquivo: {e}")
                    flash(f"Erro ao salvar arquivo: {str(e)}", "danger")
                    return redirect(request.url)
                
                # Atualizar o registro no banco de dados
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Primeiro, obter o caminho do arquivo antigo para excluí-lo depois
                    cursor.execute(f"SELECT {coluna_arquivo} FROM registros WHERE id = ?", (registro_id,))
                    resultado = cursor.fetchone()
                    caminho_antigo = resultado[0] if resultado else None
                    
                    # Atualizar o registro com o novo caminho e nome do arquivo
                    cursor.execute(f"UPDATE registros SET {coluna_arquivo} = ?, {coluna_nome} = ? WHERE id = ?", 
                                 (caminho_relativo, arquivo.filename, registro_id))
                    
                    # Registrar a atividade no log
                    data_hora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    usuario = session.get('user')
                    nivel = session.get('nivel')
                    tipo_nome = {
                        'nf': 'Nota Fiscal',
                        'os': 'Ordem de Serviço',
                        'agendamento': 'Agendamento'
                    }[tipo]
                    descricao = f"Anexo de {tipo_nome} atualizado"
                    
                    try:
                        cursor.execute(
                            "INSERT INTO log_atividades (data_hora, usuario, nivel, acao, registro_id, descricao) VALUES (?, ?, ?, ?, ?, ?)",
                            (data_hora, usuario, nivel, 'editar_anexo', registro_id, descricao)
                        )
                    except sqlite3.OperationalError:
                        # Se a tabela não existir, criá-la
                        cursor.execute("""
                            CREATE TABLE IF NOT EXISTS log_atividades (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                data_hora TEXT,
                                usuario TEXT,
                                nivel TEXT,
                                acao TEXT,
                                registro_id INTEGER,
                                descricao TEXT
                            )
                        """)
                        # Tentar novamente a inserção
                        cursor.execute(
                            "INSERT INTO log_atividades (data_hora, usuario, nivel, acao, registro_id, descricao) VALUES (?, ?, ?, ?, ?, ?)",
                            (data_hora, usuario, nivel, 'editar_anexo', registro_id, descricao)
                        )
                    
                    conn.commit()
                    
                    # Excluir o arquivo antigo se existir
                    if caminho_antigo:
                        caminho_antigo_absoluto = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', caminho_antigo)
                        try:
                            if os.path.exists(caminho_antigo_absoluto):
                                os.remove(caminho_antigo_absoluto)
                                print(f"Arquivo antigo excluído: {caminho_antigo_absoluto}")
                        except Exception as e:
                            print(f"Erro ao excluir arquivo antigo: {e}")
                
                flash(f'Anexo atualizado com sucesso.', 'success')
                return redirect(url_for('comum.visualizar_registro', registro_id=registro_id))
        
        # Obter informações sobre o arquivo atual
        arquivo_atual = None
        nome_arquivo_atual = None
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            try:
                # Buscar informações do arquivo atual
                cursor.execute(f"SELECT {coluna_arquivo}, {coluna_nome} FROM registros WHERE id = ?", (registro_id,))
                resultado = cursor.fetchone()
                if resultado and resultado[0]:
                    arquivo_atual = resultado[0]
                    nome_arquivo_atual = resultado[1] if resultado[1] else os.path.basename(arquivo_atual)
            except Exception as e:
                print(f"Erro ao buscar informações do arquivo atual: {e}")
        
        # Renderizar o template para edição de anexo
        return render_template('editar_anexo.html', 
                              registro_id=registro_id, 
                              tipo=tipo,
                              tipo_nome={
                                  'nf': 'Nota Fiscal',
                                  'os': 'Ordem de Serviço',
                                  'agendamento': 'Agendamento'
                              }[tipo],
                              arquivo_atual=arquivo_atual,
                              nome_arquivo_atual=nome_arquivo_atual,
                              usuario=session.get('user'),
                              nivel=session.get('nivel'))
                              
    except Exception as e:
        import traceback
        print(f"ERRO AO EDITAR ANEXO: {e}")
        print(traceback.format_exc())
        flash(f'Erro ao editar anexo: {str(e)}', 'danger')
        return redirect(url_for('comum.visualizar_registro', registro_id=registro_id))

# Rota para download de arquivos
@main_bp.route('/download/<filename>')
@login_required
def download_file(filename):
    from flask import current_app
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

# Rota para visualizar anexos sem baixá-los
@comum_bp.route('/visualizar_anexo/<int:registro_id>/<tipo>', methods=['GET'])
@login_required
def visualizar_anexo(registro_id, tipo):
    print(f"Iniciando visualizar_anexo para registro_id={registro_id}, tipo={tipo}")
    # Usar a função centralizada para visualização (as_attachment=False)
    return handle_anexo(registro_id, tipo, download=False)

# API para obter contadores atualizados
@comum_bp.route('/api/contadores')
@login_required
def api_contadores_comum():
    """API para obter contadores atualizados sem recarregar a página"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Função para contar registros com uma condição específica
            def count_condicao(cond_sql):
                cursor.execute(f"SELECT COUNT(*) as total FROM registros WHERE excluido = 0 AND ({cond_sql})")
                res = cursor.fetchone()
                return res[0] if res else 0
            
            # Obter nível do usuário
            nivel = session.get('nivel', 'comum')
            
            # Restrições de acesso por nível
            restricoes_nivel = ""
            if nivel == 'comum':
                # Usuários comuns só podem ver registros criados por usuários comuns
                restricoes_nivel = "AND (usuario IN (SELECT username FROM usuarios WHERE nivel = 'comum'))"
            elif nivel == 'gr':
                # GRs podem ver registros de usuários comuns e GRs, mas não de admins
                restricoes_nivel = "AND (usuario IN (SELECT username FROM usuarios WHERE nivel IN ('comum', 'gr')))"
            
            # Contadores para os cards
            contadores = {
                'operacoes_sem_nf': count_condicao(f"(anexar_nf IS NULL OR anexar_nf = '') {restricoes_nivel}"),
                'operacoes_sem_os': count_condicao(f"(anexar_os IS NULL OR anexar_os = '') {restricoes_nivel}"),
                'operacoes_sem_container': count_condicao(f"(container_1 IS NULL OR container_1 = '') {restricoes_nivel}"),
                'operacoes_sem_sm': count_condicao(f"(numero_sm IS NULL OR numero_sm = '') {restricoes_nivel}"),
                'operacoes_sem_ae': count_condicao(f"(numero_ae IS NULL OR numero_ae = '') {restricoes_nivel}")
            }
            
            return jsonify(contadores)
            
    except Exception as e:
        logging.error(f"Erro ao obter contadores: {e}")
        return jsonify({'error': str(e)}), 500

# Rota para excluir anexos
@comum_bp.route('/excluir_anexo/<int:registro_id>/<tipo>', methods=['GET'])
@login_required
def excluir_anexo(registro_id, tipo):
    try:
        # Mapear o tipo para as colunas correspondentes no banco de dados
        mapeamento_colunas = {
            'nf': ('anexar_nf', 'arquivo_nf_nome'),
            'os': ('anexar_os', 'arquivo_os_nome'),
            'agendamento': ('anexar_agendamento', 'arquivo_agendamento_nome')
        }
        
        if tipo not in mapeamento_colunas:
            flash(f'Tipo de anexo inválido: {tipo}', 'danger')
            return redirect(url_for('comum.visualizar_registro', registro_id=registro_id))
        
        coluna_arquivo, coluna_nome = mapeamento_colunas[tipo]
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Obter o caminho do arquivo atual
            cursor.execute(f"SELECT {coluna_arquivo} FROM registros WHERE id = ?", (registro_id,))
            resultado = cursor.fetchone()
            
            if not resultado or not resultado[0]:
                flash('Nenhum anexo encontrado para exclusão.', 'warning')
                return redirect(url_for('comum.visualizar_registro', registro_id=registro_id))
            
            caminho_arquivo = resultado[0]
            
            # Atualizar o registro para remover a referência ao arquivo
            cursor.execute(f"UPDATE registros SET {coluna_arquivo} = NULL, {coluna_nome} = NULL WHERE id = ?", (registro_id,))
            
            # Registrar a ação no log
            usuario = session.get('user')
            nivel = session.get('nivel')
            data_hora = datetime.now()
            descricao = f"Exclusão de anexo do tipo {tipo}"
            
            cursor.execute(
                "INSERT INTO log_atividades (data_hora, usuario, nivel, acao, registro_id, descricao) VALUES (?, ?, ?, ?, ?, ?)",
                (data_hora, usuario, nivel, 'excluir_anexo', registro_id, descricao)
            )
            
            conn.commit()
            
            # Excluir o arquivo físico
            try:
                caminho_completo = os.path.join(os.path.dirname(os.path.abspath(__file__)), caminho_arquivo)
                if os.path.exists(caminho_completo):
                    os.remove(caminho_completo)
                    print(f"Arquivo excluído: {caminho_completo}")
            except Exception as e:
                print(f"Erro ao excluir arquivo físico: {e}")
                # Continuar mesmo se não conseguir excluir o arquivo físico
        
        flash('Anexo excluído com sucesso.', 'success')
        # Redirecionamento para a página de edição de registro
        return redirect(url_for('comum.editar_registro', registro_id=registro_id))
        
    except Exception as e:
        import traceback
        print(f"ERRO AO EXCLUIR ANEXO: {e}")
        print(traceback.format_exc())
        flash(f'Erro ao excluir anexo: {str(e)}', 'danger')
        return redirect(url_for('comum.visualizar_registro', registro_id=registro_id))
