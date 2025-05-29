from flask import render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime
import time
import logging
import sqlite3
import os
import sys
import json
from werkzeug.utils import secure_filename

# Adiciona o diretório principal ao path para importações relativas
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.database import get_db_connection
from models.registros import Registro
from operations.excel import excel_processor
from access_control import (
    CAMPOS_POR_NIVEL, SECOES_VISIVEIS, CAMPOS_SOMENTE_LEITURA, CAMPOS_OCULTOS,
    CAMPO_MAPPING, ICONES_SECOES, TITULOS_SECOES, CAMPOS_SECAO,
    campo_visivel, campo_editavel, mapear_db_para_campo, mapear_campo_para_db,
    get_secoes_visiveis, get_campos_permitidos
)
from models.historico import Historico
from models.admin.logs import log_admin_action
from utils.file_utils import save_uploaded_file, allowed_file
from operations.excel import excel_processor

def processar_edicao_registro(registro_id):
    """
    Processa a edição de um registro
    
    Args:
        registro_id: ID do registro a ser editado
        
    Returns:
        Redirecionamento para a página apropriada após o processamento
    """
    print(f"\n\n=== DEPURAÇÃO: Iniciando processamento de edição para registro {registro_id} ===")
    print(f"Método da requisição: {request.method}")
    
    # Verificar se o token CSRF está presente
    if 'csrf_token' in request.form:
        print(f"Token CSRF encontrado no formulário: {request.form['csrf_token'][:15]}...")
    else:
        print("ALERTA: Token CSRF não encontrado no formulário!")
        
    if request.method != 'POST':
        # Se não for POST, apenas exibe o formulário
        return exibir_formulario_edicao(registro_id)
    
    # Obter o usuário e nível de acesso da sessão
    usuario = session.get('user')
    nivel = session.get('nivel')
    
    # Define uma função para executar operações no banco de dados com retry
    def executar_db_com_retry(operacao_func, max_retries=5, timeout=5.0):
        """
        Executa uma operação no banco de dados com retry em caso de falha
        
        Args:
            operacao_func: Função que realiza a operação no banco de dados
            max_retries: Número máximo de tentativas
            timeout: Tempo de espera entre tentativas
            
        Returns:
            Resultado da operação ou None se falhar
        """
        for i in range(max_retries):
            try:
                with get_db_connection() as conn:
                    return operacao_func(conn)
            except sqlite3.Error as e:
                print(f"Tentativa {i+1}/{max_retries} falhou: {e}")
                if i < max_retries - 1:
                    time.sleep(timeout)
        return None
    
    # Buscar o registro original para comparação
    def buscar_registro_original(conn):
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM registros WHERE id = ?", (registro_id,))
        registro = cursor.fetchone()
        return dict(registro) if registro else None
    
    registro_original = executar_db_com_retry(buscar_registro_original)
    
    if not registro_original:
        flash("Registro não encontrado.", "danger")
        return redirect(url_for('main.view_registros'))
    
    # Verificar permissões para edição
    if nivel == 'comum':
        # Verificar se o usuário criador é um usuário comum
        with get_db_connection() as conn_verif:
            cursor_verif = conn_verif.cursor()
            cursor_verif.execute("SELECT nivel FROM usuarios WHERE username = ?", (registro_original['usuario'],))
            nivel_criador_record = cursor_verif.fetchone()
            
            if nivel_criador_record is None:
                # Se não encontrar o usuário no banco, registrar no log e permitir a edição (comum por padrão)
                logging.warning(f"Usuário criador '{registro_original['usuario']}' não encontrado no banco de dados")
                nivel_criador = 'comum'
            else:
                nivel_criador = nivel_criador_record[0]
            
            if nivel_criador != 'comum':
                flash("Você não tem permissão para editar registros de administradores ou GRs.", "danger")
                return redirect(url_for('main.view_registros'))
    # Usuários GR e admin podem editar conforme suas permissões
    
    # Buscar o registro atual para ter os dados mais recentes
    def buscar_registro_atual(conn):
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM registros WHERE id = ?", (registro_id,))
        registro = cursor.fetchone()
        return dict(registro) if registro else None
    
    registro_atual = executar_db_com_retry(buscar_registro_atual)
    
    # Obter dados do formulário
    dados_form = {}
    form_data = request.form.to_dict()
    
    # Importar funções e constantes de mapeamento do módulo de controle de acesso
    from access_control import mapear_campo_para_db, CAMPO_MAPPING
    
    # Log de todos os campos do formulário para depuração
    print(f"Todos os campos do formulário: {form_data}")
    
    # Processar todos os campos do formulário, independentemente de maiúsculas/minúsculas
    print("\n===== PROCESSAMENTO DE TODOS OS CAMPOS DO FORMULÁRIO =====\n")
    
    # Obter todos os campos do mapeamento inverso (nomes dos campos no banco de dados)
    from access_control import CAMPO_MAPPING_INVERSO
    
    # Lista de campos válidos no banco de dados (colunas reais da tabela)
    campos_validos_db = [
        'id', 'usuario', 'placa', 'motorista', 'cpf', 'mot_loc', 'carreta', 'carreta1', 'carreta2',
        'carreta_loc', 'cliente', 'loc_cliente', 'arquivo', 'data_registro', 'numero_sm', 'numero_ae',
        'container_1', 'container_2', 'data_sm', 'data_ae', 'sla_sm', 'sla_ae', 'status_sm', 'tipo_carga',
        'status_container', 'modalidade', 'gerenciadora', 'booking_di', 'pedido_referencia', 'lote_cs',
        'on_time_cliente', 'horario_previsto', 'observacao_operacional', 'observacao_gr', 'destino_intermediario',
        'destino_final', 'anexar_nf', 'anexar_os', 'anexar_agendamento', 'numero_nf', 'serie', 'quantidade',
        'peso_bruto', 'valor_total_nota', 'excluido', 'data_exclusao', 'excluido_por', 'data_modificacao',
        'unidade', 'arquivo_nf_nome', 'arquivo_os_nome', 'arquivo_agendamento_nome', 'alteracoes_verificadas',
        'origem'
    ]
    
    # Processar campos diretamente, independentemente de maiúsculas/minúsculas
    for campo_banco in CAMPO_MAPPING_INVERSO.values():
        # Verificar se o campo existe no formulário em maiúsculas
        campo_form_maiusculo = CAMPO_MAPPING_INVERSO.get(campo_banco, '').upper()
        if campo_form_maiusculo and campo_form_maiusculo in form_data:
            dados_form[campo_banco] = form_data[campo_form_maiusculo]
            print(f"Campo {campo_form_maiusculo} adicionado como {campo_banco}: {form_data[campo_form_maiusculo]}")
        
        # Verificar se o campo existe no formulário em minúsculas
        campo_form_minusculo = CAMPO_MAPPING_INVERSO.get(campo_banco, '').lower()
        if campo_form_minusculo and campo_form_minusculo in form_data:
            dados_form[campo_banco] = form_data[campo_form_minusculo]
            print(f"Campo {campo_form_minusculo} adicionado como {campo_banco}: {form_data[campo_form_minusculo]}")
    
    # Processar explicitamente os campos da seção "Dados da Operação"
    campos_operacao = {
        'MOTORISTA': 'motorista',
        'CPF MOTORISTA': 'cpf',
        'CAVALO': 'placa',
        'CARRETA 1': 'carreta1',
        'CARRETA 2': 'carreta2',
        'TIPO DE CARGA': 'tipo_carga',
        'HORÁRIO PREVISTO DE INÍCIO': 'horario_previsto',
        'ON TIME (CLIENTE)': 'on_time_cliente'
    }
    
    for campo_form, campo_banco in campos_operacao.items():
        if campo_form in form_data and form_data[campo_form].strip():
            valor = form_data[campo_form]
            
            # Remover pontos, traços e espaços do CPF do motorista
            if campo_form == 'CPF MOTORISTA':
                valor = valor.replace('.', '').replace('-', '').replace(' ', '')
                print(f"CPF do motorista formatado: {form_data[campo_form]} -> {valor}")
                
            dados_form[campo_banco] = valor
            print(f"Campo da seção 'Dados da Operação' processado: {campo_form} -> {campo_banco}: {valor}")
    
    # Agora processar usando o mapeamento normal para garantir que não perdemos nenhum campo
    for campo_form, valor in form_data.items():
        campo_db = mapear_campo_para_db(campo_form)
        if campo_db and campo_db not in dados_form and campo_db in campos_validos_db:  # Garantir que o campo existe no banco
            dados_form[campo_db] = valor
            print(f"Mapeado campo '{campo_form}' para '{campo_db}' com valor: {valor}")
        elif not campo_db and campo_form not in ['csrf_token']:
            print(f"Campo '{campo_form}' não tem mapeamento para o banco de dados")
    
    # Log final de todos os campos que serão atualizados
    print("\n===== CAMPOS QUE SERÃO ATUALIZADOS NO BANCO DE DADOS =====\n")
    for campo, valor in dados_form.items():
        print(f"Campo '{campo}' será atualizado para: '{valor}'")
    print("\n===== FIM DO PROCESSAMENTO DE CAMPOS =====\n")
    
    # Verificar campos específicos para garantir que foram incluídos
    campos_importantes = ['unidade_nome', 'placa', 'status_container', 'motorista', 'cpf', 'carreta1', 'carreta2', 'tipo_carga', 'horario_previsto', 'on_time_cliente']
    for campo in campos_importantes:
        if campo not in dados_form:
            # Tentar obter o valor diretamente do formulário
            campo_form = next((k for k, v in CAMPO_MAPPING.items() if v == campo), None)
            if campo_form and campo_form in form_data:
                dados_form[campo] = form_data[campo_form]
                print(f"Adicionado campo importante '{campo}' com valor: {form_data[campo_form]}")
            else:
                print(f"Campo importante '{campo}' não encontrado no formulário")
    
    # Log dos dados que serão enviados para o banco
    print(f"Dados preparados para o banco: {dados_form}")
    
    # Função para converter datas do formato ISO com T para formato YYYY-MM-DD HH:MM:SS
    def converter_formato_data(data_str):
        if not data_str:
            return ''
        # Substituir 'T' por espaço para formato padrão do banco
        data_str = data_str.replace('T', ' ')
        # Se não tiver segundos, adicionar :00
        if data_str and ' ' in data_str and len(data_str.split(' ')[1].split(':')) == 2:
            data_str = f"{data_str}:00"
        return data_str
    
    # Processar os demais campos normalmente, exceto os já processados
    campos_ja_processados = ['UNIDADE', 'CAVALO 1', 'STATUS CONTAINER']
    
    # Obter a lista de campos do formulário
    try:
        # Tentar usar CAMPOS_FORM do excel_processor
        campos_form = excel_processor.CAMPOS_FORM
        print(f"Usando excel_processor.CAMPOS_FORM com {len(campos_form)} campos")
    except AttributeError:
        # Fallback: usar os campos do formulário enviado
        print("CAMPOS_FORM não encontrado no excel_processor, usando campos do formulário enviado")
        campos_form = list(request.form.keys())
        print(f"Usando campos do formulário: {len(campos_form)} campos")
    
    # Processar todos os campos do formulário
    for campo in campos_form:
        if campo not in campos_ja_processados:  # Pular esses campos que já tratamos
            campo_db = mapear_campo_para_db(campo)
            if campo_db:
                valor = request.form.get(campo, '')
                
                # Converter campos de data/hora para o formato correto
                if campo_db in ['on_time_cliente', 'horario_previsto'] and valor:
                    valor = converter_formato_data(valor)
                    print(f"Convertendo formato de data para {campo_db}: '{valor}'")
                
                dados_form[campo_db] = valor
                print(f"Campo {campo} -> {campo_db} = '{valor}'")
            else:
                print(f"Aviso: Campo {campo} não tem mapeamento para o banco de dados")
    
    # Debug - Imprimir todos os campos para verificar
    print(f"Todos os campos recebidos no formulário: {dict(request.form)}")
    print(f"Arquivos recebidos: {list(request.files.keys())}")
    print(f"Nível do usuário: {nivel}")
    
    # Para usuários comuns, não permitir alteração nos campos de GR
    if nivel == 'comum':
        # Preservar os valores originais dos campos de GR
        campos_gr = ['numero_sm', 'data_sm', 'status_sm', 'numero_ae', 'data_ae', 'observacao_gr', 'sla_sm', 'sla_ae', 'gerenciadora']
        valores_gr = {}
        
        # Guardar os valores originais dos campos de GR
        for campo in campos_gr:
            # Importante: preservar mesmo que seja NULL ou vazio
            if campo in registro_original:
                valores_gr[campo] = registro_original[campo]
                print(f"Preservando campo GR: {campo} = '{valores_gr[campo]}'")
        
        # Limpar dados_form para conter apenas os campos que o usuário comum pode editar
        dados_form_original = dados_form.copy()
        dados_form = {}  # Reset para evitar que usuário comum edite campos de GR
        
        # Processar campos do usuário comum
        for campo, valor in dados_form_original.items():
            # Não incluir campos de GR na edição por usuário comum
            if campo not in campos_gr:
                dados_form[campo] = valor
                print(f"Mantendo campo comum: {campo} = '{valor}'")
        
        # Adicionar os valores preservados dos campos de GR
        dados_form.update(valores_gr)
        print(f"Valores de GR preservados: {valores_gr}")
        
        # Verificar se o registro tem SM ou AE e se houve alterações em campos importantes
        tem_sm = registro_original.get('numero_sm') and str(registro_original.get('numero_sm')).strip()
        tem_ae = registro_original.get('numero_ae') and str(registro_original.get('numero_ae')).strip()
        
        if tem_sm or tem_ae:
            print(f"Registro já possui SM ({tem_sm}) ou AE ({tem_ae}). Marcando para detecção de alterações.")
            # Registrar data de modificação e usuário que modificou
            data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            dados_form['data_modificacao'] = data_atual
            dados_form['alteracoes_verificadas'] = 0  # Marcar como não verificado
            dados_form['modificado_por'] = usuario
    
    elif nivel == 'gr':
        # Para usuários GR, somente permitir alteração nos campos específicos de GR
        dados_form_original = dados_form.copy()
        dados_form = {}  # Reset para evitar que GR edite campos de usuários comuns
        
        # Processar explicitamente APENAS os campos de GR do formulário
        campos_gr_form = [
            'NUMERO SM', 'DT CRIACAO SM', 'STATUS SM', 'NÚMERO AE', 'DT CRIACAO AE', 
            'OBSERVAÇÃO DE GR', 'SLA SM', 'SLA AE', 'GERENCIADORA'
        ]
        
        # Processar campos de GR
        for campo in campos_gr_form:
            valor = request.form.get(campo, '')
            if campo in request.form:  # Se o campo existe no formulário
                # Converter nome do campo para o formato do banco de dados
                campo_db = mapear_campo_para_db(campo)
                if campo_db:
                    # Verificar se é um campo SM ou AE e se o valor foi alterado
                    valor_original = registro_original.get(campo_db, '')
                    if valor and valor != valor_original:
                        # Registrar a data atual quando SM ou AE é adicionado/alterado
                        if campo_db == 'numero_sm' and valor.strip():
                            data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            dados_form['data_sm'] = data_atual
                            print(f"Registrando data_sm = {data_atual} para SM = {valor}")
                        elif campo_db == 'numero_ae' and valor.strip():
                            data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            dados_form['data_ae'] = data_atual
                            print(f"Registrando data_ae = {data_atual} para AE = {valor}")
                    
                    dados_form[campo_db] = valor
                    print(f"Campo GR definido: {campo} -> {campo_db} = '{valor}'")
        
        # Manter os campos de upload que o GR pode alterar
        for campo in ['anexar_nf', 'anexar_os', 'anexar_agendamento']:
            if campo in dados_form_original:
                dados_form[campo] = dados_form_original[campo]
                print(f"Mantendo campo de upload: {campo} = '{dados_form[campo]}'")
    
    elif nivel == 'admin':
        # Processar explicitamente os campos de GR do formulário para admin (que pode editar tudo)
        campos_gr_form = [
            'NUMERO SM', 'DATA SM', 'STATUS SM', 'NUMERO AE', 'DATA AE', 
            'OBSERVAÇÃO DE GR', 'SLA SM', 'SLA AE'
        ]
        for campo in campos_gr_form:
            valor = request.form.get(campo, '')
            if valor.strip():
                # Converter nome do campo para o formato do banco de dados
                campo_db = mapear_campo_para_db(campo)
                if campo_db:
                    dados_form[campo_db] = valor
                    print(f"Campo GR definido: {campo} -> {campo_db} = '{valor}'")
    
    # Mapear nomes dos campos de upload para colunas no banco de dados
    # Ajustado para corresponder às colunas reais na tabela 'registros'
    campos_upload = {
        'ANEXAR NF': 'anexar_nf',
        'anexar_nf': 'anexar_nf',
        'ANEXAR OS': 'anexar_os',
        'anexar_os': 'anexar_os',
        'ANEXAR AGENDAMENTO': 'anexar_agendamento',
        'anexar_agendamento': 'anexar_agendamento',
        'Anexar Agendamento': 'anexar_agendamento'  # Variante com inicial maiúscula
    }
    
    # Debug: Mostrar todos os campos em request.files
    print("\n===== ARQUIVOS RECEBIDOS NO REQUEST =====\n")
    for key in request.files.keys():
        file = request.files[key]
        print(f"Arquivo encontrado: {key} -> {file.filename if file and file.filename else 'Sem nome'}")
    print("\n===== FIM DOS ARQUIVOS RECEBIDOS =====\n")
    
    # Processar anexo de agendamento de forma simplificada
    if 'anexar_agendamento' in request.files:
        file = request.files['anexar_agendamento']
        print(f"Processando anexo de agendamento: {file.filename if file and file.filename else 'Sem arquivo'}")
        
        if file and file.filename and file.filename.strip() != '':
            try:
                # Salvar o arquivo
                arquivo_salvo = save_uploaded_file(file)
                if arquivo_salvo:
                    print(f"Arquivo salvo com sucesso: {arquivo_salvo}")
                    
                    # Atualizar as colunas no banco de dados
                    dados_form['anexar_agendamento'] = arquivo_salvo
                    dados_form['arquivo_agendamento_nome'] = file.filename
                    
                    print(f"Colunas atualizadas: anexar_agendamento = {arquivo_salvo}, arquivo_agendamento_nome = {file.filename}")
                else:
                    print(f"Falha ao salvar arquivo - não retornou nome de arquivo")
            except Exception as e:
                print(f"Exceção ao salvar arquivo: {str(e)}")
        else:
            print("Nenhum arquivo selecionado para upload ou arquivo inválido")
    else:
        print("Campo 'anexar_agendamento' não encontrado no formulário")
        
    # Verificar se há anexos sendo atualizados
    anexos_campos = [campo for campo in dados_form.keys() if 'anexar_' in campo or 'arquivo_' in campo]
    if anexos_campos:
        print("\n=== ANEXOS SENDO ATUALIZADOS ===\n")
        for campo in anexos_campos:
            print(f"Anexo '{campo}': {dados_form[campo]}")
    else:
        print("\nNenhum anexo sendo atualizado")

    
    # Para compatibilidade, se houver um campo genérico 'arquivo'
    if 'arquivo' in request.files:
        file = request.files['arquivo']
        if file and file.filename and allowed_file(file.filename):
            arquivo = save_uploaded_file(file)
            if arquivo:
                dados_form['arquivo'] = arquivo
    
    # Para campos de GR, verificar permissões
    campos_gr = ['numero_sm', 'data_sm', 'status_sm', 'numero_ae', 'data_ae', 'observacao_gr']
    
    if nivel not in ['admin', 'gr']:
        # Usuário comum não pode alterar campos de GR
        for campo in campos_gr:
            if campo in dados_form:
                dados_form.pop(campo)
    
    # Se o usuário é GR ou admin, calcular SLA se necessário
    if nivel in ['admin', 'gr']:
        # Calcular SLA SM se temos data_sm
        if 'data_sm' in dados_form and dados_form['data_sm']:
            # Função para calcular SLA em horas entre duas datas
            def calcular_sla(data_reg_str):
                try:
                    data_reg = datetime.strptime(data_reg_str, "%Y-%m-%d %H:%M:%S")
                    data_sm = datetime.strptime(dados_form['data_sm'], "%Y-%m-%d %H:%M:%S")
                    delta = data_sm - data_reg
                    horas = delta.total_seconds() / 3600
                    return round(horas, 2)
                except Exception as e:
                    print(f"Erro ao calcular SLA: {e}")
                    return 0
            
            # Usar a data de registro original
            sla_sm = calcular_sla(registro_original['data_registro'])
            dados_form['sla_sm'] = str(sla_sm)
        
        # Calcular SLA AE se temos data_ae e data_sm
        if 'data_ae' in dados_form and dados_form['data_ae'] and 'data_sm' in dados_form and dados_form['data_sm']:
            try:
                data_sm = datetime.strptime(dados_form['data_sm'], "%Y-%m-%d %H:%M:%S")
                data_ae = datetime.strptime(dados_form['data_ae'], "%Y-%m-%d %H:%M:%S")
                delta = data_ae - data_sm
                horas = delta.total_seconds() / 3600
                dados_form['sla_ae'] = str(round(horas, 2))
            except Exception as e:
                print(f"Erro ao calcular SLA AE: {e}")
        valores = list(dados_form.values())
        valores.append(registro_id)  # Para o WHERE
    else:
        # Para usuários comuns, também precisamos preparar a lista de valores
        valores = list(dados_form.values())
        valores.append(registro_id)  # Para o WHERE
    
    # A query de atualização será preparada mais tarde, depois de processar todos os campos
    
    print(f"\n===== DADOS PARA ATUALIZAÇÃO =====")
    print(f"Total de campos a atualizar: {len(dados_form)}")
    print(f"Campos: {list(dados_form.keys())}")
    print(f"Valores: {valores}")
    print("====================================\n")
    
    # Inicializar o dicionário de alterações
    alteracoes = {}
    
    # Estabelecer conexão com o banco de dados e executar a atualização
    conn = None
    try:
        print("Tentando estabelecer conexão com o banco de dados...")
        conn = get_db_connection()
        print("Conexão estabelecida com sucesso.")
        
        cursor = conn.cursor()
        
        # Lista de campos importantes que, quando alterados, devem marcar o registro como modificado
        campos_importantes = [
            'cliente', 'container_1', 'container_2', 'lote_cs', 'status_container',
            'destino_intermediario', 'destino_final', 'motorista', 'cpf',
            'placa', 'carreta1', 'carreta2', 'horario_previsto', 'on_time_cliente',
            'anexar_nf', 'anexar_os', 'anexar_agendamento', 'tipo_carga', 'origem'
        ]
        
        # Verificar se algum campo importante foi alterado
        campos_alterados = False
        for campo in campos_importantes:
            if campo in dados_form and campo in registro_original:
                valor_novo = str(dados_form[campo]) if dados_form[campo] is not None else ''
                valor_antigo = str(registro_original[campo]) if registro_original[campo] is not None else ''
                if valor_novo != valor_antigo:
                    print(f"Campo importante alterado: {campo} - de '{valor_antigo}' para '{valor_novo}'")
                    campos_alterados = True
                    alteracoes[campo] = {
                        'valor_antigo': valor_antigo,
                        'valor_novo': valor_novo
                    }
        
        # Verificar explicitamente os campos da seção "Dados da Operação"
        campos_operacao_db = ['motorista', 'cpf', 'placa', 'carreta1', 'carreta2', 'tipo_carga', 'horario_previsto', 'on_time_cliente']
        for campo in campos_operacao_db:
            if campo in dados_form and campo in registro_original:
                valor_novo = str(dados_form[campo]) if dados_form[campo] is not None else ''
                valor_antigo = str(registro_original[campo]) if registro_original[campo] is not None else ''
                if valor_novo != valor_antigo:
                    print(f"Campo da seção 'Dados da Operação' alterado: {campo} - de '{valor_antigo}' para '{valor_novo}'")
                    campos_alterados = True
                    alteracoes[campo] = {
                        'valor_antigo': valor_antigo,
                        'valor_novo': valor_novo
                    }
        
        # Se campos importantes foram alterados por um usuário comum, atualizar data_modificacao, alteracoes_verificadas e modificado_por
        if campos_alterados and nivel == 'comum':
            print("Campos importantes foram alterados por usuário comum. Atualizando data_modificacao, alteracoes_verificadas e modificado_por.")
            data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            dados_form['data_modificacao'] = data_atual
            dados_form['alteracoes_verificadas'] = 0
            dados_form['modificado_por'] = usuario  # Definir quem fez a modificação
            
            # Verificar se o registro tem SM ou AE
            tem_sm = registro_original.get('numero_sm') and str(registro_original.get('numero_sm')).strip()
            tem_ae = registro_original.get('numero_ae') and str(registro_original.get('numero_ae')).strip()
            
            if tem_sm or tem_ae:
                print(f"Registro já possui SM ({tem_sm}) ou AE ({tem_ae}). Garantindo que modificado_por seja '{usuario}' para detecção de alterações.")
                # Forçar a atualização do campo modificado_por mesmo que já tenha sido definido anteriormente
                dados_form['modificado_por'] = usuario
        
        # Preparar a query de atualização com os campos do formulário
        campos_update = [f"{campo} = ?" for campo in dados_form.keys()]
        query = f"UPDATE registros SET {', '.join(campos_update)} WHERE id = ?"
        valores = list(dados_form.values()) + [registro_id]
        
        print(f"\n=== QUERY SQL FINAL ===\n")
        print(f"Query: {query}")
        print(f"Valores: {valores}")
        print(f"Total de campos a atualizar: {len(campos_update)}")
        
        print("\n=== DETALHES DA QUERY DE ATUALIZAÇÃO ===\n")
        print(f"Query SQL: {query}")
        print(f"Valores: {valores}")
        print(f"ID do registro a ser atualizado: {registro_id}")
        print(f"Total de campos a serem atualizados: {len(dados_form)}")
        
        # Verificar anexos sendo atualizados
        anexos = [campo for campo in dados_form.keys() if 'anexar_' in campo or 'arquivo_' in campo]
        if anexos:
            print("\n=== ANEXOS SENDO ATUALIZADOS ===\n")
            for anexo in anexos:
                print(f"Anexo '{anexo}': {dados_form[anexo]}")
        
        # Executar a query com try/except detalhado
        try:
            print("\n=== EXECUTANDO QUERY SQL ===\n")
            cursor.execute(query, valores)
            atualizados = cursor.rowcount
            print(f"Linhas atualizadas: {atualizados}")
            
            # IMPORTANTE: Realizar o commit IMEDIATAMENTE para salvar as alterações
            print("\n=== REALIZANDO COMMIT DAS ALTERAÇÕES ===\n")
            conn.commit()
            print("Commit realizado com sucesso!")
            
            # Verificar imediatamente se as alterações foram salvas
            print("\n=== VERIFICANDO SE AS ALTERAÇÕES FORAM SALVAS ===\n")
            
            # Verificar anexos
            if 'arquivo_agendamento_nome' in dados_form:
                cursor.execute("SELECT arquivo_agendamento_nome FROM registros WHERE id = ?", (registro_id,))
                resultado = cursor.fetchone()
                if resultado and resultado[0] == dados_form['arquivo_agendamento_nome']:
                    print(f"Anexo confirmado no banco: {resultado[0]}")
                else:
                    print(f"ALERTA: Anexo não encontrado ou diferente no banco: {resultado[0] if resultado else 'Nenhum'}")
            
            print("Alterações verificadas e confirmadas no banco de dados.")
            
            # Verificar se a atualização foi bem-sucedida
            cursor.execute(f"SELECT * FROM registros WHERE id = ?", (registro_id,))
            registro_atualizado = cursor.fetchone()
            if registro_atualizado:
                print(f"\nRegistro atualizado com sucesso. ID: {registro_id}")
                
                # Verificar especificamente os anexos
                if 'anexar_agendamento' in dados_form or 'arquivo_agendamento_nome' in dados_form:
                    cursor.execute("SELECT arquivo_agendamento_nome FROM registros WHERE id = ?", (registro_id,))
                    anexo_atual = cursor.fetchone()
                    if anexo_atual and anexo_atual[0]:
                        print(f"Anexo salvo com sucesso: {anexo_atual[0]}")
                    else:
                        print("Nenhum anexo encontrado após a atualização.")
            else:
                print(f"\nERRO: Não foi possível encontrar o registro após a atualização!")
                return "Erro: Registro não encontrado após atualização"
                
        except Exception as e:
            print(f"Erro ao executar a query: {e}")
            if conn:
                conn.rollback()
            flash("Erro ao atualizar o registro. Por favor, tente novamente.", "error")
            return False
    except Exception as e:
        print(f"Erro na execução da query: {e}")
        if conn:
            conn.rollback()
        return False
    
    # Continuar com a mesma conexão para registrar no histórico se houver alterações
    if alteracoes:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        alteracoes_json = json.dumps(alteracoes, ensure_ascii=False)
        
        print(f"Registrando alterações no histórico: {len(alteracoes)} campos modificados")
        
        try:
            # Inserir no histórico
            cursor.execute(
                "INSERT INTO historico (registro_id, alterado_por, alteracoes, data_alteracao) VALUES (?, ?, ?, ?)",
                (registro_id, usuario, alteracoes_json, now)
            )
            print("Histórico atualizado com sucesso.")
            
            # Registrar no log administrativo se for admin ou GR
            if nivel in ['admin', 'gr']:
                acao = "EDIÇÃO DE REGISTRO"
                if nivel == 'gr':
                    acao = "EDIÇÃO DE REGISTRO (GR)"
                
                # Preparar detalhes das alterações no formato 'de/para'
                detalhes_alteracoes = []
                for campo, valores in alteracoes.items():
                    valor_anterior = valores['anterior'] if valores['anterior'] else '(vazio)'
                    valor_novo = valores['novo'] if valores['novo'] else '(vazio)'
                    detalhes_alteracoes.append(f"{campo}: {valor_anterior} => {valor_novo}")
                
                detalhes_log = f"Registro ID: {registro_id}, Campos: {', '.join(detalhes_alteracoes)}"
                
                # Inserir no log administrativo
                cursor.execute(
                    "INSERT INTO admin_logs (usuario, acao, detalhes, data) VALUES (?, ?, ?, ?)",
                    (usuario, acao, detalhes_log, now)
                )
                print("Log administrativo atualizado com detalhes de/para.")
            
            # Commit das alterações
            print("Tentando realizar commit das alterações...")
            conn.commit()
            print("Commit realizado com sucesso.")
            
            # Verificar se as alterações foram realmente salvas
            print("Verificando se as alterações foram salvas...")
            cursor.execute("SELECT * FROM registros WHERE id = ?", (registro_id,))
            registro_atualizado = cursor.fetchone()
            if registro_atualizado:
                print("Registro encontrado após atualização.")
                registro_dict = dict((cursor.description[i][0], value) for i, value in enumerate(registro_atualizado))
                for campo, valor in dados_form.items():
                    if campo in registro_dict:
                        print(f"Campo {campo}: valor esperado = '{valor}', valor salvo = '{registro_dict[campo]}'")
                    else:
                        print(f"Campo {campo} não encontrado no registro após atualização!")
            else:
                print("ERRO: Registro não encontrado após atualização!")
            
        except Exception as e:
            print(f"Erro ao registrar histórico ou realizar commit: {e}")
            print(f"Tipo de erro: {type(e).__name__}")
            print(f"Detalhes do erro: {str(e)}")
            if conn:
                print("Tentando realizar rollback...")
                try:
                    conn.rollback()
                    print("Rollback realizado com sucesso.")
                except Exception as rollback_error:
                    print(f"Erro ao realizar rollback: {rollback_error}")
            flash("Erro ao salvar as alterações. Por favor, tente novamente.", "error")
            return redirect(url_for('comum.dashboard_comum'))
    else:
        print("Nenhuma alteração detectada para registro no histórico.")
        # Commit mesmo sem alterações para o histórico
        try:
            print("Tentando realizar commit sem alterações para o histórico...")
            conn.commit()
            print("Commit realizado com sucesso.")
        except Exception as e:
            print(f"Erro ao realizar commit: {e}")
            print(f"Tipo de erro: {type(e).__name__}")
            print(f"Detalhes do erro: {str(e)}")
            if conn:
                print("Tentando realizar rollback...")
                try:
                    conn.rollback()
                    print("Rollback realizado com sucesso.")
                except Exception as rollback_error:
                    print(f"Erro ao realizar rollback: {rollback_error}")
            flash("Erro ao salvar as alterações. Por favor, tente novamente.", "error")
            return redirect(url_for('comum.dashboard_comum'))
            
    # Verificar se a atualização foi bem-sucedida
    # Se chegamos até aqui sem retornar False, a atualização foi bem-sucedida
    print("\n===== Atualização concluída com sucesso =====\n")
    flash("Registro atualizado com sucesso!", "success")
    # Garantir que o redirecionamento seja para o dashboard
    print("Redirecionando para o dashboard...")
    return True  # Retornar True para que a função editar_registro_comum em routes.py faça o redirecionamento

def exibir_formulario_edicao(registro_id):
    """
    Exibe o formulário de edição para um registro
    
    Args:
        registro_id: ID do registro a ser editado
        
    Returns:
        Renderização do template de edição
    """
    print(f"\n\n=== DEPURAÇÃO: Iniciando exibir_formulario_edicao para registro {registro_id} ===")
    usuario = session.get('user')
    nivel = session.get('nivel')
    
    # Buscar dados do registro no banco
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM registros WHERE id = ?", (registro_id,))
        registro_row = cursor.fetchone()
        
        # Verificar todas as colunas da tabela registros
        cursor.execute("PRAGMA table_info(registros)")
        colunas = cursor.fetchall()
        print("\nColunas na tabela registros:")
        for col in colunas:
            print(f"  - {col[1]} ({col[2]})")
        
        # Converter o objeto sqlite3.Row para um dicionário
        if registro_row:
            registro = dict(registro_row)
            print("\nDados do registro:")
            for campo, valor in registro.items():
                print(f"  - {campo}: {valor}")
        else:
            registro = None
        
    if not registro:
        flash("Registro não encontrado.", "danger")
        return redirect(url_for('main.view_registros'))
    
    # Verificar permissões para visualização
    if nivel == 'comum':
        # Verificar se o usuário criador é um usuário comum
        with get_db_connection() as conn_verif:
            cursor_verif = conn_verif.cursor()
            cursor_verif.execute("SELECT nivel FROM usuarios WHERE username = ?", (registro['usuario'],))
            nivel_criador_record = cursor_verif.fetchone()
            
            if nivel_criador_record is None:
                # Se não encontrar o usuário no banco, registrar no log e permitir a visualização (comum por padrão)
                logging.warning(f"Usuário criador '{registro['usuario']}' não encontrado no banco de dados")
                nivel_criador = 'comum'
            else:
                nivel_criador = nivel_criador_record[0]
            
            if nivel_criador != 'comum':
                flash("Você não tem permissão para visualizar registros de administradores ou GRs.", "danger")
                return redirect(url_for('main.view_registros'))
    # Usuários GR e admin podem visualizar conforme suas permissões
    
    # Mapear os dados do banco para os campos do formulário
    registro_completo = {'id': registro_id}
    
    # Importar funções e constantes do módulo de controle de acesso
    from access_control import mapear_db_para_campo, get_campos_permitidos, campo_visivel, campo_editavel, CAMPOS_POR_NIVEL
    
    # Obter a lista de campos permitidos para o nível do usuário
    campos_permitidos = get_campos_permitidos(nivel)
    
    # Importar o dicionário de mapeamento para debug
    from access_control import CAMPO_MAPPING
    print("\nMapeamento de campos:")
    for db_campo, form_campo in CAMPO_MAPPING.items():
        print(f"  - {db_campo} -> {form_campo}")
    
    # Verificar campos específicos que estamos procurando
    campos_problematicos = ['origem', 'status_container', 'modalidade', 'horario_previsto', 'on_time_cliente']
    print("\nVerificando campos problemáticos no registro:")
    for campo in campos_problematicos:
        print(f"  - {campo}: {registro.get(campo, 'NÃO ENCONTRADO')}")
    
    # Campos problemáticos que precisamos garantir que sejam carregados corretamente
    campos_problematicos = {
        # Dados da Carga
        'origem': 'ORIGEM',
        'status_container': 'STATUS CONTAINER',
        'modalidade': 'MODALIDADE',
        'container_1': 'CONTAINER 1',
        'container_2': 'CONTAINER 2',
        'destino_intermediario': 'DESTINO INTERMEDIÁRIO',
        'destino_final': 'DESTINO FINAL',
        'lote_cs': 'LOTE CS',
        # Dados da Operação
        'motorista': 'MOTORISTA',
        'cpf': 'CPF MOTORISTA',
        'placa': 'CAVALO',
        'carreta1': 'CARRETA 1',
        'carreta2': 'CARRETA 2',
        'tipo_carga': 'TIPO DE CARGA',
        'horario_previsto': 'HORÁRIO PREVISTO DE INÍCIO',
        'on_time_cliente': 'ON TIME (CLIENTE)',
        'data_registro': 'DATA',
        # Anexos - NF
        'anexar_nf': 'ANEXAR NF',
        'arquivo_nf_nome': 'arquivo_nf_nome',
        # Anexos - OS
        'anexar_os': 'ANEXAR OS',
        'arquivo_os_nome': 'arquivo_os_nome',
        # Anexos - Agendamento
        'anexar_agendamento': 'ANEXAR AGENDAMENTO',
        'arquivo_agendamento_nome': 'arquivo_agendamento_nome'
    }
    
    # Mapear campos do banco para o formulário, considerando apenas os permitidos
    print("\nMapeando campos do banco para o formulário:")
    for campo_db, valor in registro.items():
        campo_form = mapear_db_para_campo(campo_db)
        print(f"  - {campo_db} -> {campo_form}: {valor}")
        
        # Se o campo não estiver na lista de permitidos, pular
        if not campo_visivel(campo_form, nivel):
            print(f"    - Campo {campo_form} não é visível para o nível {nivel}")
            continue
        
        # Pular processamento de campos de data e hora aqui, pois serão processados mais tarde
        # Isso evita conflitos de formato
        if campo_db in ['horario_previsto', 'on_time_cliente', 'data_registro'] and valor:
            # Se for um dos campos que serão processados posteriormente, pular
            if campo_form in ['HORÁRIO PREVISTO DE INÍCIO', 'ON TIME (CLIENTE)']:
                print(f"    - Pulando processamento inicial do campo {campo_form}, será processado posteriormente")
                continue
            
            # Para outros campos de data/hora, garantir que o valor seja uma string
            if not isinstance(valor, str):
                valor = str(valor)
            
            # Remover milissegundos se existirem
            if '.' in valor:
                valor = valor.split('.')[0]
            
            # Garantir o formato YYYY-MM-DD HH:MM:SS
            if 'T' in valor:
                valor = valor.replace('T', ' ')
            
            print(f"    - Processando campo de data/hora {campo_db}: {valor}")
            
        registro_completo[campo_form] = valor
        print(f"    - Adicionado ao registro_completo: {campo_form} = {valor}")
    
    # Garantir que os campos problemáticos sejam carregados corretamente
    for campo_db, campo_form in campos_problematicos.items():
        if campo_db in registro and registro[campo_db] and campo_form not in registro_completo:
            valor = registro[campo_db]
            print(f"  - Adicionando campo problemático: {campo_db} -> {campo_form}: {valor}")
            
            # Garantir que os campos de data e hora sejam exibidos corretamente
            if campo_db in ['horario_previsto', 'on_time_cliente']:
                # Usar diretamente o valor do banco de dados, sem tentar converter
                # Isso garante que o valor original seja exibido no formulário
                print(f"    - Usando valor original para o campo {campo_form}: {valor}")
                
                # Se o valor estiver vazio, usar um valor padrão para evitar campos em branco
                if not valor:
                    agora = datetime.now()
                    valor = agora.strftime('%H:%M:%S %d-%m-%Y')
                    print(f"    - Usando valor padrão: {valor}")
            
            registro_completo[campo_form] = valor
    
    # Verificar anexos
    print("\nVerificando anexos:")
    anexos = {
        'nf': registro.get('anexar_nf'),
        'os': registro.get('anexar_os'),
        'agendamento': registro.get('anexar_agendamento')
    }
    for tipo, valor in anexos.items():
        print(f"  - Anexo {tipo}: {valor}")
    
    # Verificar campos no registro_completo
    print("\nCampos no registro_completo:")
    for campo, valor in registro_completo.items():
        print(f"  - {campo}: {valor}")
    
    # Garantir que os campos da seção "Dados da Operação" estejam no registro_completo
    campos_operacao = {
        'motorista': 'MOTORISTA',
        'cpf': 'CPF MOTORISTA',
        'placa': 'CAVALO',
        'carreta1': 'CARRETA 1',
        'carreta2': 'CARRETA 2',
        'tipo_carga': 'TIPO DE CARGA',
        'horario_previsto': 'HORÁRIO PREVISTO DE INÍCIO',
        'on_time_cliente': 'ON TIME (CLIENTE)'
    }
    
    # Adicionar explicitamente os campos da seção "Dados da Operação"
    for campo_db, campo_form in campos_operacao.items():
        if campo_db in registro:
            valor = registro[campo_db]
            print(f"Adicionando campo da seção 'Dados da Operação': {campo_db} -> {campo_form}: {valor}")
            
            # Garantir que os campos de data e hora sejam exibidos corretamente
            if campo_db in ['horario_previsto', 'on_time_cliente']:
                # Usar diretamente o valor do banco de dados, sem tentar converter
                # Isso garante que o valor original seja exibido no formulário
                print(f"    - Usando valor original para o campo {campo_form}: {valor}")
                
                # Se o valor estiver vazio, usar um valor padrão para evitar campos em branco
                if not valor:
                    agora = datetime.now()
                    valor = agora.strftime('%H:%M:%S %d-%m-%Y')
                    print(f"    - Usando valor padrão: {valor}")
            
            # Forçar a adição do campo ao registro_completo, mesmo que já exista
            registro_completo[campo_form] = valor
            
            # Adicionar também o valor com a chave original do banco de dados
            # Isso garante que o template possa acessar os valores tanto com as chaves
            # originais quanto com as chaves mapeadas
            registro_completo[campo_db] = valor
    
    # Garantir que os campos de data e hora estejam no registro_completo
    # Verificar e adicionar diretamente os valores dos campos de data e hora
    if 'horario_previsto' in registro:
        horario_previsto = registro['horario_previsto']
        # Adicionar explicitamente o valor ao registro_completo
        registro_completo['HORÁRIO PREVISTO DE INÍCIO'] = horario_previsto
        registro_completo['horario_previsto'] = horario_previsto
        registro_completo['horario_previsto_valor'] = horario_previsto  # Chave adicional para garantir
        print(f"Adicionado explicitamente: HORÁRIO PREVISTO DE INÍCIO = {horario_previsto}")
    
    if 'on_time_cliente' in registro:
        on_time = registro['on_time_cliente']
        # Adicionar explicitamente o valor ao registro_completo
        registro_completo['ON TIME (CLIENTE)'] = on_time
        registro_completo['on_time_cliente'] = on_time
        registro_completo['on_time_valor'] = on_time  # Chave adicional para garantir
        print(f"Adicionado explicitamente: ON TIME (CLIENTE) = {on_time}")
            
    # Verificar se os campos de data e hora foram adicionados corretamente
    if 'HORÁRIO PREVISTO DE INÍCIO' in registro_completo:
        print(f"Campo HORÁRIO PREVISTO DE INÍCIO adicionado com valor: {registro_completo['HORÁRIO PREVISTO DE INÍCIO']}")
    else:
        print("ERRO: Campo HORÁRIO PREVISTO DE INÍCIO não foi adicionado ao registro_completo")
        
    if 'ON TIME (CLIENTE)' in registro_completo:
        print(f"Campo ON TIME (CLIENTE) adicionado com valor: {registro_completo['ON TIME (CLIENTE)']}")
    else:
        print("ERRO: Campo ON TIME (CLIENTE) não foi adicionado ao registro_completo")
    
    # Definir se o usuário é o criador do registro (para permissões adicionais)
    is_criador = registro['usuario'] == usuario
    
    # Definir se deve mostrar os campos de GR (apenas para admin e gr)
    mostrar_campos_gr = nivel in ['admin', 'gr']
    
    # Obter as listas para os dropdowns
    placas = excel_processor.COMBOBOX_OPTIONS.get('CAVALO', [])
    carretas = excel_processor.COMBOBOX_OPTIONS.get('CARRETA 1', [])
    tipos_carga = excel_processor.COMBOBOX_OPTIONS.get('TIPO DE CARGA', [])
    
    # Garantir que os campos de data e hora estejam no registro_completo
    # Verificar e adicionar diretamente os valores dos campos de data e hora
    print(f"\n=== DEPURAÇÃO DETALHADA DOS CAMPOS DE DATA/HORA ===")
    print(f"horario_previsto (do banco): {registro.get('horario_previsto')}")
    print(f"on_time_cliente (do banco): {registro.get('on_time_cliente')}")
    
    # Adicionar explicitamente os campos ao registro_completo usando todas as variações possíveis
    # para garantir que o template encontre os valores
    
    # 1. Usando os nomes dos campos do formulário (com acentos e espaços)
    registro_completo['HORÁRIO PREVISTO DE INÍCIO'] = registro.get('horario_previsto', '')
    registro_completo['ON TIME (CLIENTE)'] = registro.get('on_time_cliente', '')
    
    # 2. Usando os nomes originais das colunas do banco
    registro_completo['horario_previsto'] = registro.get('horario_previsto', '')
    registro_completo['on_time_cliente'] = registro.get('on_time_cliente', '')
    
    # 3. Usando variações adicionais que podem ser usadas pelo template
    registro_completo['horario_previsto_valor'] = registro.get('horario_previsto', '')
    registro_completo['on_time_valor'] = registro.get('on_time_cliente', '')
    
    # Imprimir o registro_completo para verificar se os valores foram adicionados corretamente
    print("\nValores no registro_completo:")
    print(f"HORÁRIO PREVISTO DE INÍCIO: {registro_completo.get('HORÁRIO PREVISTO DE INÍCIO')}")
    print(f"ON TIME (CLIENTE): {registro_completo.get('ON TIME (CLIENTE)')}")
    print(f"horario_previsto: {registro_completo.get('horario_previsto')}")
    print(f"on_time_cliente: {registro_completo.get('on_time_cliente')}")
    print(f"horario_previsto_valor: {registro_completo.get('horario_previsto_valor')}")
    print(f"on_time_valor: {registro_completo.get('on_time_valor')}")
    print("=== FIM DA DEPURAÇÃO DETALHADA ===")
    
    # Obter as seções visíveis e garantir que 'transporte' esteja incluído
    secoes_visiveis = get_secoes_visiveis(nivel)
    if 'transporte' not in secoes_visiveis:
        secoes_visiveis.append('transporte')  # Garantir que a seção 'transporte' esteja visível
    
    # Verificar anexos existentes para passar ao template
    tem_anexos = {
        'nf': registro.get('anexar_nf') is not None and registro.get('anexar_nf') != '',
        'os': registro.get('anexar_os') is not None and registro.get('anexar_os') != '',
        'agendamento': registro.get('anexar_agendamento') is not None and registro.get('anexar_agendamento') != ''
    }
    
    # Usar template diferente com base no nível do usuário
    if nivel == 'comum':
        # Para usuários comuns, usar o template form_new.html
        # Mapear campos do banco para os nomes esperados pelo template form_new.html
        form_registro = {}
        
        # Mapeamento específico para o template form_new.html
        campo_mapping_form_new = {
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
            'anexar_nf': 'ANEXAR NF',
            'anexar_os': 'ANEXAR OS',
            'anexar_agendamento': 'ANEXAR AGENDAMENTO',
            'observacao_operacional': 'OBSERVACAO OPERACIONAL',
            'observacao_gr': 'OBSERVAÇÃO DE GR',
            'origem': 'ORIGEM'
        }
        
        # Preencher o dicionário form_registro com os valores do banco
        print("\nMapeando campos para form_new.html:")
        for db_campo, valor in registro.items():
            if db_campo in campo_mapping_form_new and valor is not None:
                form_campo = campo_mapping_form_new[db_campo]
                
                # Converter datas para o formato esperado pelo input datetime-local
                if db_campo in ['horario_previsto', 'on_time_cliente'] and valor:
                    try:
                        # Verificar se o valor está no formato 'HH:MM:SS DD-MM-YYYY'
                        if isinstance(valor, str) and ' ' in valor:
                            # Extrair partes da data
                            hora_parte = valor.split(' ')[0]  # HH:MM:SS
                            data_parte = valor.split(' ')[1]  # DD-MM-YYYY
                            
                            # Separar componentes
                            hora, minuto, segundo = hora_parte.split(':') if ':' in hora_parte else (hora_parte, '00', '00')
                            dia, mes, ano = data_parte.split('-') if '-' in data_parte else ('01', '01', '2025')
                            
                            # Formatar para YYYY-MM-DDTHH:MM (formato aceito pelo input datetime-local)
                            valor_formatado = f"{ano}-{mes.zfill(2)}-{dia.zfill(2)}T{hora.zfill(2)}:{minuto.zfill(2)}"
                            form_registro[form_campo] = valor_formatado
                            
                            # Armazenar o valor original para referência
                            form_registro[f"{form_campo}_original"] = valor
                            
                            print(f"  - {db_campo} -> {form_campo}: {valor} (formatado para {valor_formatado})")
                        else:
                            form_registro[form_campo] = valor
                            form_registro[f"{form_campo}_original"] = valor
                            print(f"  - {db_campo} -> {form_campo}: {valor} (formato não reconhecido)")
                    except Exception as e:
                        print(f"Erro ao formatar data {valor}: {str(e)}")
                        form_registro[form_campo] = valor
                        form_registro[f"{form_campo}_original"] = valor
                else:
                    # Para outros campos, usar o valor como está
                    form_registro[form_campo] = valor
                    print(f"  - {db_campo} -> {form_campo}: {valor}")
        
        # Adicionar o ID do registro para referência
        form_registro['id'] = registro_id
        
        # Adicionar campos vazios para os campos que não estão no registro
        # Isso é importante para garantir que o template não tente acessar campos que não existem
        for form_campo in set(campo_mapping_form_new.values()) - set(form_registro.keys()):
            form_registro[form_campo] = ''
        
        # Adicionar informações de anexos
        if registro.get('anexar_nf'):
            form_registro['anexar_nf'] = registro.get('anexar_nf')
            form_registro['arquivo_nf_nome'] = registro.get('arquivo_nf_nome', 'arquivo.pdf')
        
        if registro.get('anexar_os'):
            form_registro['anexar_os'] = registro.get('anexar_os')
            form_registro['arquivo_os_nome'] = registro.get('arquivo_os_nome', 'arquivo.pdf')
        
        if registro.get('anexar_agendamento'):
            form_registro['anexar_agendamento'] = registro.get('anexar_agendamento')
            form_registro['arquivo_agendamento_nome'] = registro.get('arquivo_agendamento_nome', 'arquivo.pdf')
        
        print("\nRegistro completo para o template:")
        for campo, valor in form_registro.items():
            print(f"  - {campo}: {valor}")
        
        return render_template(
            'form_edit.html',
            usuario=usuario,
            nivel=nivel,
            registro=form_registro,  # Usar o dicionário mapeado para o template
            CAMPOS_OBRIGATORIOS=excel_processor.CAMPOS_OBRIGATORIOS,
            tipos=excel_processor.TIPOS_DE_DADOS,
            campos=excel_processor.COMBOBOX_OPTIONS,
            COMBOBOX_OPTIONS=excel_processor.COMBOBOX_OPTIONS,
            MOTORISTA_CPF_MAP=excel_processor.MOTORISTA_CPF_MAP,
            modo_visualizacao=False,
            tem_anexos=tem_anexos  # Adicionar a variável tem_anexos ao contexto
        )
    else:
        # Para usuários GR e admin, usar o template editar_registro_gr.html
        return render_template(
            'editar_registro_gr.html',
            campos=excel_processor.COMBOBOX_OPTIONS,
            tipos=excel_processor.TIPOS_DE_DADOS,
            container=excel_processor.CONTAINER_MAP,
            usuario=usuario,
            nivel=nivel,
            registro=registro_completo,
            CAMPOS_OBRIGATORIOS=excel_processor.CAMPOS_OBRIGATORIOS,
            MOTORISTA_CPF_MAP=excel_processor.MOTORISTA_CPF_MAP,
            PLACAS=placas,
            CARRETAS=carretas,
            TIPOS_CARGA=tipos_carga,
            campos_digitaveis=get_campos_permitidos(nivel),
            secoes_visiveis=secoes_visiveis,
            campos_somente_leitura=CAMPOS_SOMENTE_LEITURA.get(nivel, []),
            campos_ocultos=CAMPOS_OCULTOS.get(nivel, []),
            is_criador=is_criador,
            mostrar_campos_gr=mostrar_campos_gr,
            CAMPO_MAPPING=CAMPO_MAPPING,
            ICONES_SECOES=ICONES_SECOES,
            TITULOS_SECOES=TITULOS_SECOES,
            CAMPOS_SECAO=CAMPOS_SECAO,
            campo_visivel=campo_visivel,
            campo_editavel=campo_editavel,
            CAMPOS_POR_NIVEL=CAMPOS_POR_NIVEL,
            tem_anexos=tem_anexos
        )

# Usar as funções do módulo de controle de acesso
def mapear_campo_para_db(campo_form):
    """
    Mapeia um nome de campo do formulário para o nome da coluna no banco de dados
    
    Args:
        campo_form: Nome do campo no formulário
        
    Returns:
        Nome da coluna no banco de dados ou None se não houver mapeamento
    """
    from access_control import mapear_campo_para_db as mapear
    return mapear(campo_form)

def mapear_db_para_campo(coluna_db):
    """
    Mapeia um nome de coluna do banco para o nome do campo no formulário
    
    Args:
        coluna_db: Nome da coluna no banco de dados
        
    Returns:
        Nome do campo no formulário ou None se não houver mapeamento
    """
    from access_control import mapear_db_para_campo as mapear
    return mapear(coluna_db)
