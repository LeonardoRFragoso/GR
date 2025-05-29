import os
import sys

# Adiciona o diretório principal ao path para importações relativas
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import ALLOWED_EXTENSIONS, UPLOAD_FOLDER

def allowed_file(filename):
    """
    Verifica se o arquivo tem uma extensão permitida
    
    Args:
        filename: Nome do arquivo a ser verificado
        
    Returns:
        True se a extensão for permitida, False caso contrário
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def secure_filename(filename):
    """
    Retorna uma versão segura do nome do arquivo
    
    Args:
        filename: Nome do arquivo a ser limpo
        
    Returns:
        Nome seguro do arquivo
    """
    from werkzeug.utils import secure_filename as werkzeug_secure_filename
    return werkzeug_secure_filename(filename)

def save_uploaded_file(file, custom_filename=None):
    """
    Salva um arquivo enviado pelo usuário
    
    Args:
        file: Objeto de arquivo do Flask (request.files['file'])
        custom_filename: Nome personalizado para o arquivo (opcional)
        
    Returns:
        Nome do arquivo salvo ou None se falhar
    """
    if file and allowed_file(file.filename):
        # Usar o nome personalizado ou o nome original do arquivo
        filename = secure_filename(custom_filename if custom_filename else file.filename)
        
        # Criar o caminho completo do arquivo
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        
        try:
            # Salvar o arquivo
            file.save(filepath)
            return filename
        except Exception as e:
            print(f"Erro ao salvar arquivo: {e}")
            return None
    
    return None

def delete_file(filename):
    """
    Exclui um arquivo pelo nome
    
    Args:
        filename: Nome do arquivo a ser excluído
        
    Returns:
        True se o arquivo for excluído com sucesso, False caso contrário
    """
    try:
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False
    except Exception as e:
        print(f"Erro ao excluir arquivo: {e}")
        return False

def get_file_path(filename):
    """
    Retorna o caminho completo de um arquivo
    
    Args:
        filename: Nome do arquivo
        
    Returns:
        Caminho completo do arquivo
    """
    return os.path.join(UPLOAD_FOLDER, filename)
