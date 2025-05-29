import os

# Configurações da aplicação para ambiente Ubuntu
SECRET_KEY = 'segredo-super-seguro'
DEBUG = False  # Desativado para ambiente de produção
HOST = '0.0.0.0'  # Permite conexões de qualquer IP
PORT = 8520  # Porta personalizada conforme solicitado

# Configurações de pasta com caminhos Linux
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Configurações de banco de dados
DB_PATH = os.path.join(BASE_DIR, 'usuarios.db')

# Configurações de log
LOG_FILE = os.path.join(BASE_DIR, 'access.log')
LOG_FORMAT = '%(asctime)s - %(message)s'
LOG_LEVEL = 'INFO'

# Configuração do OneDrive
ONEDRIVE_URL = "https://ictsi-my.sharepoint.com/:x:/p/leonardo_fragoso_itracker/EV8B0yiu9txKjo3I45WIYXkBK9u7ye7q9YF7bMb1E81fOA?download=1"

# Configuração de extensões de arquivo permitidas
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'docx'}
