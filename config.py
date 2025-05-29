import os

# Configurações da aplicação
SECRET_KEY = 'segredo-super-seguro'
DEBUG = True
HOST = '127.0.0.1'
PORT = 5000

# Configurações de pasta
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Configurações de banco de dados
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'usuarios.db')

# Configurações de log
LOG_FILE = 'access.log'
LOG_FORMAT = '%(asctime)s - %(message)s'
LOG_LEVEL = 'INFO'

# Configuração do OneDrive
ONEDRIVE_URL = "https://ictsi-my.sharepoint.com/:x:/p/leonardo_fragoso_itracker/EV8B0yiu9txKjo3I45WIYXkBG6MEojBRiSfm38PFvP5ZQg?e=EBHGvm"

# Configuração de extensões de arquivo permitidas
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'docx'}
