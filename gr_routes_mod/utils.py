# utils.py

import re
import logging
from datetime import datetime
from functools import wraps
from flask import session, flash, redirect, url_for

logger = logging.getLogger(__name__)

def formatar_data_br(valor):
    if not valor:
        return ""
    valor = valor.replace('T', ' ')
    if ' ' in valor:
        data_parte, hora_parte = valor.split(' ', 1)
    else:
        data_parte, hora_parte = valor, ''
    if re.match(r'\d{4}-\d{2}-\d{2}', data_parte):
        ano, mes, dia = data_parte.split('-')
        data_formatada = f"{dia}-{mes}-{ano}"
    else:
        data_formatada = data_parte
    if hora_parte:
        if re.match(r'\d{2}:\d{2}:\d{2}', hora_parte):
            hora_formatada = hora_parte
        elif re.match(r'\d{2}:\d{2}', hora_parte):
            hora_formatada = f"{hora_parte}:00"
        else:
            hora_formatada = hora_parte
        return f"{hora_formatada} {data_formatada}"
    else:
        return data_formatada

def formatar_dados_exibicao(valor, tipo='texto'):
    if valor is None:
        return ""
    try:
        if tipo == 'data':
            if isinstance(valor, str) and re.match(r'\d{4}-\d{2}-\d{2}', valor):
                partes = valor.split(' ', 1)
                data = partes[0]
                hora = partes[1] if len(partes) > 1 else ''
                ano, mes, dia = data.split('-')
                data_formatada = f"{dia}/{mes}/{ano}"
                return f"{data_formatada} {hora}" if hora else data_formatada
            return valor
        elif tipo == 'numero':
            numero = float(valor)
            return f"{numero:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        elif tipo == 'moeda':
            valor_num = float(valor)
            return f"R$ {valor_num:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        else:
            return str(valor).strip()
    except Exception as e:
        logger.error(f"Erro ao formatar valor '{valor}' como {tipo}: {e}")
        return str(valor)

def validar_dados(dados, regras):
    erros = {}
    for campo, regra in regras.items():
        valor = dados.get(campo)
        if regra.get('obrigatorio', False) and (valor is None or valor == ''):
            erros[campo] = f"O campo {campo} é obrigatório."
            continue
        if valor is None or valor == '':
            continue
        tipo = regra.get('tipo', 'texto')
        if tipo == 'numero':
            try:
                valor_num = float(valor)
                if 'min' in regra and valor_num < regra['min']:
                    erros[campo] = f"O valor mínimo para {campo} é {regra['min']}."
                if 'max' in regra and valor_num > regra['max']:
                    erros[campo] = f"O valor máximo para {campo} é {regra['max']}."
            except ValueError:
                erros[campo] = f"O campo {campo} deve ser um número válido."
        elif tipo == 'data':
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', valor):
                erros[campo] = f"O campo {campo} deve estar no formato YYYY-MM-DD."
            else:
                try:
                    ano, mes, dia = map(int, valor.split('-'))
                    data_valor = datetime(ano, mes, dia)
                    if 'min' in regra:
                        data_min = datetime.strptime(regra['min'], '%Y-%m-%d')
                        if data_valor < data_min:
                            erros[campo] = f"A data mínima para {campo} é {regra['min']}."
                    if 'max' in regra:
                        data_max = datetime.strptime(regra['max'], '%Y-%m-%d')
                        if data_valor > data_max:
                            erros[campo] = f"A data máxima para {campo} é {regra['max']}."
                except ValueError:
                    erros[campo] = f"O campo {campo} contém uma data inválida."
        elif tipo == 'texto':
            if 'min' in regra and len(valor) < regra['min']:
                erros[campo] = f"O campo {campo} deve ter pelo menos {regra['min']} caracteres."
            if 'max' in regra and len(valor) > regra['max']:
                erros[campo] = f"O campo {campo} deve ter no máximo {regra['max']} caracteres."
    return len(erros) == 0, erros

def gr_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash('Por favor, faça login para acessar esta página.', 'warning')
            return redirect(url_for('auth.login'))
        nivel = session.get('nivel')
        if nivel not in ['gr', 'admin']:
            flash('Acesso restrito à Gestão de Relacionamento.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function
