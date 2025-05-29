import pandas as pd
import requests
from io import BytesIO
import sys
import os

# Adiciona o diretório principal ao path para importações relativas
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import ONEDRIVE_URL

class ExcelProcessor:
    """Classe simplificada para processar dados da planilha do OneDrive"""
    
    def __init__(self):
        # Inicializar variáveis
        self.df = None  # DataFrame principal
        self.df_placas = None  # DataFrame de placas
        self.CAMPOS_OBRIGATORIOS = []  # Lista de campos obrigatórios simplificada
        self.COMBOBOX_OPTIONS = {}  # Opções para os dropdowns
        self.MOTORISTA_CPF_MAP = {}  # Mapeamento de motoristas para CPFs
        self.COLUNAS_PLACAS = {}  # Mapeamento de colunas na aba PLACAS
        self.CONTAINER_MAP = {}  # Mapeamento de campos para categorias (adicionado para compatibilidade)
        
        # Inicializar TIPOS_DE_DADOS com valores padrão
        self.TIPOS_DE_DADOS = {
            'UNIDADE': 'text',
            'CLIENTE': 'text',
            'MOTORISTA': 'text',
            'CPF MOTORISTA': 'cpf',
            'CAVALO': 'text',
            'CARRETA 1': 'text',
            'CARRETA 2': 'text',
            'TIPO DE CARGA': 'text',
            'PEDIDO/REFERÊNCIA': 'text',
            'BOOKING / DI': 'text',
            'CONTAINER 1': 'text',
            'CONTAINER 2': 'text',
            'LOTE CS': 'text',
            'MODALIDADE': 'text',
            'STATUS CONTAINER': 'text',
            'ORIGEM': 'text',
            'DESTINO INTERMEDIÁRIO': 'text',
            'DESTINO FINAL': 'text',
            'ON TIME (CLIENTE)': 'datetime',
            'HORÁRIO PREVISTO DE INÍCIO': 'datetime',
            'OBSERVACAO OPERACIONAL': 'text',
            'NÚMERO AE': 'text',
            'DT CRIACAO AE': 'date',
            'NUMERO SM': 'text',
            'DT CRIACAO SM': 'date',
            'OBSERVAÇÃO DE GR': 'text',
            'ANEXAR NF': 'file',
            'ANEXAR OS': 'file',
            'ANEXAR AGENDAMENTO': 'file'
        }
        
        # Inicializar CAMPOS_FORM
        self.CAMPOS_FORM = list(self.TIPOS_DE_DADOS.keys())
        
        # Carregar os dados do OneDrive
        self.load_data()
    
    def load_data(self):
        """Carrega os dados da planilha do OneDrive (versão simplificada)"""
        try:
            # Adicionar parâmetro para download direto
            url = ONEDRIVE_URL
            if '?download=1' not in url and 'download=1' not in url:
                # Adicionar parâmetro de download se não estiver presente
                if '?' in url:
                    url += '&download=1'
                else:
                    url += '?download=1'
            
            print(f"Tentando acessar URL: {url}")
            response = requests.get(url, timeout=15)  # Aumentar timeout para 15 segundos
            response.raise_for_status()
            
            # Carregar as abas do Excel usando openpyxl
            print("Tentando carregar o arquivo Excel com openpyxl...")
            excel_file = pd.ExcelFile(BytesIO(response.content), engine='openpyxl')
            
            print(f"Abas disponíveis no Excel: {excel_file.sheet_names}")
            
            # Carregar a aba principal (assumindo que é a primeira aba)
            self.df = excel_file.parse(0)
            # Limpeza básica dos dados
            for col in self.df.columns:
                self.df[col] = self.df[col].fillna('').astype(str).str.strip()
            print(f"Carregada primeira aba com {len(self.df)} linhas e {len(self.df.columns)} colunas")
            print(f"Colunas na primeira aba: {self.df.columns.tolist()}")
            
            # Carregar a aba PLACAS se existir
            if "PLACAS" in excel_file.sheet_names:
                self.df_placas = excel_file.parse("PLACAS")
                # Limpeza básica dos dados
                for col in self.df_placas.columns:
                    self.df_placas[col] = self.df_placas[col].fillna('').astype(str).str.strip()
                print(f"Carregada aba PLACAS com {len(self.df_placas)} linhas e {len(self.df_placas.columns)} colunas")
                print(f"Colunas na aba PLACAS: {self.df_placas.columns.tolist()}")
            
            # Processar os dados de forma simplificada
            self._process_data_simple()
            
            return True
            
        except Exception as e:
            print(f"Erro ao processar planilha do OneDrive: {e}")
            # Definir valores padrão em caso de falha
            self.CAMPOS_OBRIGATORIOS = []
            self.COMBOBOX_OPTIONS = {}
            self.MOTORISTA_CPF_MAP = {}
            # Não precisamos definir TIPOS_DE_DADOS aqui, pois já foi inicializado no __init__
            return False
    
    def _process_column(self, df, column_name):
        """Processa uma coluna do DataFrame para obter valores únicos e formatados."""
        if column_name not in df.columns:
            print(f"Coluna {column_name} não encontrada no DataFrame")
            return []
            
        # Obter valores únicos e remover NaN
        values = df[column_name].dropna().unique().tolist()
        
        # Converter para string e remover espaços em branco
        values = [str(v).strip() for v in values if str(v).strip()]
        
        # Ordenar valores
        values.sort()
        
        return values
    
    def _process_data_simple(self):
        """Processa os dados da planilha de forma simplificada"""
        print("Usando dados da aba PLACAS para popular dropdowns")
        
        # Definir campos obrigatórios simplificados
        self.CAMPOS_OBRIGATORIOS = [
            'UNIDADE', 'CLIENTE', 'MOTORISTA', 'CPF MOTORISTA', 'CAVALO'
        ]
        
        # Processar dados da aba PLACAS se estiver disponível
        if self.df_placas is not None:
            print(f"Colunas disponíveis na aba PLACAS: {self.df_placas.columns.tolist()}")
            
            # Mapear colunas da aba PLACAS
            self.COLUNAS_PLACAS = {
                'PLACA': 'PLACA',  # Coluna PLACA -> Campo CAVALO
                'MOTORISTA': 'MOTORISTA',  # Coluna MOTORISTA -> Campo MOTORISTA
                'CPF': 'CPF',  # Coluna CPF -> Campo CPF MOTORISTA
                'CARRETA': 'CARRETA'  # Coluna CARRETA -> Campos CARRETA 1 e CARRETA 2
            }
            
            # Processar coluna PLACA (para o campo CAVALO)
            placa_col = self.COLUNAS_PLACAS.get('PLACA')
            if placa_col and placa_col in self.df_placas.columns:
                placas = self.df_placas[placa_col].dropna().unique().tolist()
                placas = [p for p in placas if p and p.strip()]
                print(f"Processada coluna PLACA: {len(placas)} valores únicos")
                print(f"Exemplos de placas: {placas[:5]}")
                self.COMBOBOX_OPTIONS['CAVALO'] = placas
            
            # Processar coluna CARRETA (para os campos CARRETA 1 e CARRETA 2)
            carreta_col = self.COLUNAS_PLACAS.get('CARRETA')
            if carreta_col and carreta_col in self.df_placas.columns:
                carretas = self.df_placas[carreta_col].dropna().unique().tolist()
                carretas = [c for c in carretas if c and c.strip()]
                print(f"Processada coluna CARRETA: {len(carretas)} valores únicos")
                print(f"Exemplos de carretas: {carretas[:5]}")
                # Usar a mesma lista para ambos os campos
                self.COMBOBOX_OPTIONS['CARRETA 1'] = carretas
                self.COMBOBOX_OPTIONS['CARRETA 2'] = carretas
                self.COMBOBOX_OPTIONS['CARRETAS'] = carretas
            
            # Processar coluna MOTORISTA
            motorista_col = self.COLUNAS_PLACAS.get('MOTORISTA')
            if motorista_col and motorista_col in self.df_placas.columns:
                motoristas = self.df_placas[motorista_col].dropna().unique().tolist()
                motoristas = [m for m in motoristas if m and m.strip()]
                print(f"Processada coluna MOTORISTA: {len(motoristas)} valores únicos")
                print(f"Exemplos de motoristas: {motoristas[:5]}")
                self.COMBOBOX_OPTIONS['MOTORISTA'] = motoristas
                
                # Criar mapeamento MOTORISTA -> CPF simplificado
                cpf_col = self.COLUNAS_PLACAS.get('CPF')
                if cpf_col and cpf_col in self.df_placas.columns:
                    # Criar mapeamento simplificado
                    motorista_cpf_map = {}
                    for _, row in self.df_placas.iterrows():
                        motorista = str(row[motorista_col]).strip()
                        cpf = str(row[cpf_col]).strip()
                        
                        # Remover pontos, traços e espaços do CPF
                        cpf = cpf.replace('.', '').replace('-', '').replace(' ', '')
                        
                        if motorista and cpf:
                            motorista_cpf_map[motorista] = cpf
                    
                    self.MOTORISTA_CPF_MAP = motorista_cpf_map
                    print(f"Mapeamento MOTORISTA -> CPF criado com {len(motorista_cpf_map)} entradas")
                    print(f"Exemplos de mapeamento (motorista -> CPF): {list(motorista_cpf_map.items())[:5]}")
        
        # Definir valores para os comboboxes
        self.COMBOBOX_OPTIONS['UNIDADE'] = ['Rio de Janeiro', 'Floriano', 'Suzano']
        self.COMBOBOX_OPTIONS['MODALIDADE'] = ['IMPORTAÇÃO', 'EXPORTAÇÃO', 'CABOTAGEM', 'CST']
        self.COMBOBOX_OPTIONS['STATUS CONTAINER'] = ['CHEIO', 'VAZIO']
        
        # Processar TIPO DE CARGA da aba principal
        if 'TIPO DE CARGA' in self.df.columns:
            tipos_carga = self.df['TIPO DE CARGA'].dropna().unique().tolist()
            tipos_carga = [t for t in tipos_carga if t and t.strip()]
            if tipos_carga:
                self.COMBOBOX_OPTIONS['TIPO DE CARGA'] = tipos_carga
                print(f"Tipos de carga carregados da planilha: {tipos_carga}")
            else:
                # Para campos digitáveis, definimos uma lista vazia para indicar que não são dropdowns
                self.COMBOBOX_OPTIONS['TIPO DE CARGA'] = []
        
        # Adicionar manualmente o campo Requisitante nas opções se não estiver presente
        if 'Requisitante' not in self.COMBOBOX_OPTIONS:
            self.COMBOBOX_OPTIONS['Requisitante'] = []
            
        # Inicializar CONTAINER_MAP com categorias básicas para compatibilidade
        self.CONTAINER_MAP = {
            'UNIDADE': 'dados da unidade',
            'Requisitante': 'dados da unidade',
            'ANEXAR NF': 'documentos',
            'ANEXAR OS': 'documentos',
            'ANEXAR AGENDAMENTO': 'documentos'
        }
                
        # Definir campos digitáveis (não são dropdowns)
        campos_digitaveis = [
            'CLIENTE', 'PEDIDO/REFERÊNCIA', 'BOOKING / DI', 'CONTAINER 1', 'CONTAINER 2', 
            'LOTE CS', 'ORIGEM', 'DESTINO INTERMEDIÁRIO', 'DESTINO FINAL', 'ON TIME (CLIENTE)', 
            'HORÁRIO PREVISTO DE INÍCIO', 'OBSERVACAO OPERACIONAL', 'NÚMERO AE', 
            'DT CRIACAO AE', 'NUMERO SM', 'DT CRIACAO SM', 'OBSERVAÇÃO DE GR'
        ]
        
        # Remover esses campos do COMBOBOX_OPTIONS para que não sejam exibidos como dropdowns
        for campo in campos_digitaveis:
            if campo in self.COMBOBOX_OPTIONS:
                self.COMBOBOX_OPTIONS.pop(campo)
        
        # Definir tipos de dados para cada campo
        self.TIPOS_DE_DADOS = {
            'UNIDADE': 'text',
            'CLIENTE': 'text',
            'MOTORISTA': 'text',
            'CPF MOTORISTA': 'cpf',
            'CAVALO': 'text',
            'CARRETA 1': 'text',
            'CARRETA 2': 'text',
            'TIPO DE CARGA': 'text',
            'PEDIDO/REFERÊNCIA': 'text',
            'BOOKING / DI': 'text',
            'CONTAINER 1': 'text',
            'CONTAINER 2': 'text',
            'LOTE CS': 'text',
            'MODALIDADE': 'text',
            'STATUS CONTAINER': 'text',
            'ORIGEM': 'text',
            'DESTINO INTERMEDIÁRIO': 'text',
            'DESTINO FINAL': 'text',
            'ON TIME (CLIENTE)': 'datetime',
            'HORÁRIO PREVISTO DE INÍCIO': 'datetime',
            'OBSERVACAO OPERACIONAL': 'text',
            'NÚMERO AE': 'text',
            'DT CRIACAO AE': 'date',
            'NUMERO SM': 'text',
            'DT CRIACAO SM': 'date',
            'OBSERVAÇÃO DE GR': 'text',
            'ANEXAR NF': 'file',
            'ANEXAR OS': 'file',
            'ANEXAR AGENDAMENTO': 'file'
        }
        
        # Definir a lista de campos do formulário (CAMPOS_FORM)
        # Esta lista é usada em várias partes do código para iterar sobre todos os campos
        self.CAMPOS_FORM = list(self.TIPOS_DE_DADOS.keys())
    
    def convert_to_db_format(self, data):
        """Converte os dados do formulário para o formato do banco de dados"""
        db_data = {}
        
        # Mapeamento de campos do formulário para colunas do banco de dados
        field_mapping = {
            'UNIDADE': 'UNIDADE',
            'MOTORISTA': 'MOTORISTA',
            'CPF MOTORISTA': 'CPF MOTORISTA',
            'CAVALO': 'CAVALO 1',
            'CARRETA 1': 'CARRETA 1',
            'CARRETA 2': 'CARRETA 2',
            'TIPO DE CARGA': 'TIPO DE CARGA',
            'CLIENTE': 'CLIENTE',
            'PEDIDO/REFERÊNCIA': 'PEDIDO/REFERÊNCIA',
            'BOOKING / DI': 'BOOKING / DI',
            'CONTAINER 1': 'CONTAINER 1',
            'CONTAINER 2': 'CONTAINER 2',
            'LOTE CS': 'LOTE CS',
            'MODALIDADE': 'MODALIDADE',
            'STATUS CONTAINER': 'STATUS CONTAINER',
            'ORIGEM': 'ORIGEM',
            'DESTINO INTERMEDIÁRIO': 'DESTINO INTERMEDIÁRIO',
            'DESTINO FINAL': 'DESTINO FINAL',
            'ON TIME (CLIENTE)': 'ON TIME (CLIENTE)',
            'HORÁRIO PREVISTO DE INÍCIO': 'HORÁRIO PREVISTO DE INÍCIO',
            'OBSERVACAO OPERACIONAL': 'OBSERVACAO OPERACIONAL ',
            'NÚMERO AE': 'NÚMERO AE',
            'DT CRIACAO AE': 'DT CRIACAO AE',
            'NUMERO SM': 'NUMERO SM',
            'DT CRIACAO SM': 'DT CRIACAO SM',
            'OBSERVAÇÃO DE GR': 'OBSERVAÇÃO DE GR',
            'ANEXAR NF': 'ANEXAR NF',
            'ANEXAR OS': 'ANEXAR OS',
            'ANEXAR AGENDAMENTO': 'ANEXAR AGENDAMENTO'
        }
        
        # Mapear campos do formulário para o banco de dados
        for form_field, db_field in field_mapping.items():
            if form_field in data:
                db_data[db_field] = data[form_field]
        
        return db_data

# Criar uma instância da classe ExcelProcessor para ser importada por outros módulos
excel_processor = ExcelProcessor()
