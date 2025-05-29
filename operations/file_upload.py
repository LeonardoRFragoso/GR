"""
Módulo para gerenciar uploads de arquivos no sistema de Atendimento GR.
"""
import os
import logging
from werkzeug.utils import secure_filename

# Configurações de upload
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'uploads')
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png', 'xls', 'xlsx', 'txt'}

# Garantir que o diretório de uploads existe
if not os.path.exists(UPLOAD_FOLDER):
    try:
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        logging.info(f"Diretório de uploads criado: {UPLOAD_FOLDER}")
    except Exception as e:
        logging.error(f"Erro ao criar diretório de uploads: {e}")

def allowed_file(filename):
    """
    Verifica se o arquivo tem uma extensão permitida.
    
    Args:
        filename: Nome do arquivo a ser verificado
        
    Returns:
        True se a extensão for permitida, False caso contrário
    """
    if not filename:
        return False
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_uploaded_file(file, tipo='arquivo'):
    """
    Salva um arquivo enviado pelo usuário no sistema.
    
    Args:
        file: Objeto de arquivo do Flask (request.files)
        tipo: Tipo de arquivo (para nomear o arquivo)
        
    Returns:
        Tuple com o caminho relativo do arquivo salvo e o nome original do arquivo,
        ou (None, None) em caso de erro
    """
    if file and file.filename and allowed_file(file.filename):
        try:
            # Criar nome de arquivo seguro
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            filename = secure_filename(f"{tipo}_{timestamp}_{file.filename}")
            
            # Caminho relativo para o banco de dados
            relative_path = os.path.join('uploads', filename)
            
            # Caminho absoluto para salvar o arquivo
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            
            # Salvar o arquivo
            file.save(filepath)
            logging.info(f"Arquivo salvo com sucesso: {filepath}")
            
            return relative_path, file.filename
        except Exception as e:
            logging.error(f"Erro ao salvar arquivo: {e}")
            return None, None
    
    return None, None
