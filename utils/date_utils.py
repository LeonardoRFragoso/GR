from datetime import datetime

# Formato padrão do projeto para datas
DEFAULT_DATE_FORMAT = '%d-%m-%Y %H:%M:%S'  # DD-MM-YYYY HH:MM:SS

def get_current_datetime_str():
    """
    Retorna a data e hora atual no formato padrão do projeto (DD-MM-YYYY HH:MM:SS)
    
    Returns:
        str: Data e hora atual formatada
    """
    return datetime.now().strftime(DEFAULT_DATE_FORMAT)

def format_date(date_obj, format_str=None):
    """
    Formata um objeto datetime para o formato padrão ou especificado
    
    Args:
        date_obj (datetime): Objeto datetime a ser formatado
        format_str (str, optional): Formato específico. Se None, usa o formato padrão.
    
    Returns:
        str: Data formatada
    """
    if format_str is None:
        format_str = DEFAULT_DATE_FORMAT
    return date_obj.strftime(format_str)

def parse_date(date_str, try_formats=None):
    """
    Tenta converter uma string de data para um objeto datetime
    
    Args:
        date_str (str): String contendo a data
        try_formats (list, optional): Lista de formatos a serem tentados.
            Se None, tenta formatos comuns incluindo o padrão do projeto.
    
    Returns:
        datetime: Objeto datetime ou None se não conseguir converter
    """
    if not date_str:
        return None
        
    if try_formats is None:
        try_formats = [
            DEFAULT_DATE_FORMAT,  # DD-MM-YYYY HH:MM:SS (padrão do projeto)
            '%Y-%m-%d %H:%M:%S',  # YYYY-MM-DD HH:MM:SS (formato ISO)
            '%d/%m/%Y %H:%M:%S',  # DD/MM/YYYY HH:MM:SS
            '%d-%m-%Y',           # DD-MM-YYYY (sem hora)
            '%Y-%m-%d',           # YYYY-MM-DD (sem hora)
            '%d/%m/%Y'            # DD/MM/YYYY (sem hora)
        ]
    
    for fmt in try_formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    return None

def ensure_date_format(date_str):
    """
    Garante que uma string de data esteja no formato padrão do projeto
    
    Args:
        date_str (str): String contendo a data em qualquer formato
    
    Returns:
        str: Data no formato padrão do projeto ou a string original se não conseguir converter
    """
    dt = parse_date(date_str)
    if dt:
        return format_date(dt)
    return date_str
