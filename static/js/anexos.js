// Função para confirmar exclusão de anexos
function confirmarExclusao(registroId, tipo) {
  // Mapear o tipo para um nome mais amigável
  const tipoNome = {
    'nf': 'Nota Fiscal',
    'os': 'Ordem de Serviço',
    'agendamento': 'Agendamento'
  }[tipo] || tipo;
  
  // Mensagem de confirmação mais detalhada
  const mensagem = `Tem certeza que deseja excluir este anexo de ${tipoNome}?\n\nEsta ação não pode ser desfeita.`;
  
  if (confirm(mensagem)) {
    // Mostrar indicador visual de carregamento
    const anexoElement = document.querySelector(`.anexo-existente[data-tipo="${tipo}"]`);
    if (anexoElement) {
      // Adicionar classe de carregamento e desabilitar botões
      anexoElement.classList.add('excluindo');
      const botoes = anexoElement.querySelectorAll('button, a');
      botoes.forEach(btn => btn.disabled = true);
      
      // Adicionar spinner
      const conteudo = anexoElement.querySelector('.d-flex');
      if (conteudo) {
        const spinner = document.createElement('div');
        spinner.className = 'spinner-border spinner-border-sm text-primary ms-2';
        spinner.setAttribute('role', 'status');
        spinner.innerHTML = '<span class="visually-hidden">Excluindo...</span>';
        conteudo.appendChild(spinner);
      }
    }
    
    // Usar o caminho absoluto para evitar problemas com a rota
    const url = `/comum/excluir_anexo/${registroId}/${tipo}`;
    console.log('Excluindo anexo:', url);
    
    // Criar um formulário para fazer uma requisição GET
    const form = document.createElement('form');
    form.method = 'GET';
    form.action = url;
    document.body.appendChild(form);
    form.submit();
  }
}

// Configurar drag and drop para todos os campos de upload
function setupDragAndDrop() {
  console.log('Inicializando setupDragAndDrop');
  
  // Definir os tipos de anexos que queremos configurar
  const tiposAnexos = [
    { id: 'nf', titulo: 'Nota Fiscal' },
    { id: 'os', titulo: 'Ordem de Serviço' },
    { id: 'agendamento', titulo: 'Agendamento' }
  ];
  
  // Selecionar todas as áreas de drag and drop
  const dragAreas = tiposAnexos.map(tipo => {
    const areaId = `drag-area-${tipo.id}`;
    const fileSelectId = `selected-file-${tipo.id}`;
    const area = document.getElementById(areaId);
    const fileSelect = document.getElementById(fileSelectId);
    
    if (area) {
      console.log(`Área de ${tipo.titulo} encontrada: ${areaId}`);
    } else {
      console.log(`Área de ${tipo.titulo} NÃO encontrada: ${areaId}`);
    }
    
    return { 
      tipo: tipo.id, 
      titulo: tipo.titulo,
      area, 
      fileSelect 
    };
  });
  
  // Configurar cada área
  dragAreas.forEach(function(item) {
    if (item.area) {
      if (item.fileSelect) {
        console.log(`Configurando área de ${item.titulo} com seletor de arquivo:`, item.area.id);
        initDragArea(item.area, item.fileSelect);
      } else {
        console.log(`Configurando área de ${item.titulo} (sem fileSelect):`, item.area.id);
        // Tentar encontrar o elemento selected-file dentro da área
        const fileSelect = item.area.querySelector('.selected-file');
        if (fileSelect) {
          initDragArea(item.area, fileSelect);
        } else {
          console.log(`Elemento selected-file não encontrado para ${item.titulo}`, item.area.id);
        }
      }
    } else {
      console.log(`Elemento drag-area não encontrado para ${item.titulo}`);
    }
  });
}

// Configurar uma área específica de drag and drop
function initDragArea(dragArea, selectedFile) {
  console.log('Inicializando área de drag and drop:', dragArea.id);
  
  // Encontrar o input de arquivo e o botão de navegação
  const fileInput = dragArea.querySelector('input[type="file"]');
  const browseBtn = dragArea.querySelector('.browse-btn');
  
  if (!fileInput) {
    console.error('Input de arquivo não encontrado para', dragArea.id);
    return;
  }
  
  console.log('Input de arquivo:', fileInput.name);
  console.log('Botão de navegação:', browseBtn ? 'encontrado' : 'não encontrado');
  
  // Eventos para drag and drop
  ['dragover', 'dragleave', 'drop'].forEach(eventName => {
    dragArea.addEventListener(eventName, function(e) {
      e.preventDefault();
      e.stopPropagation();
    });
  });
  
  // Adicionar classe quando arquivo é arrastado sobre a área
  dragArea.addEventListener('dragover', function() {
    console.log('Arquivo arrastado sobre a área:', dragArea.id);
    this.classList.add('active');
  });
  
  // Remover classe quando arquivo sai da área
  dragArea.addEventListener('dragleave', function() {
    console.log('Arquivo saiu da área:', dragArea.id);
    this.classList.remove('active');
  });
  
  // Processar quando arquivo é solto na área
  dragArea.addEventListener('drop', function(e) {
    console.log('Arquivo solto na área:', dragArea.id);
    this.classList.remove('active');
    if (e.dataTransfer.files.length) {
      fileInput.files = e.dataTransfer.files;
      updateFileDetails(dragArea, selectedFile, e.dataTransfer.files[0]);
    }
  });
  
  // Abrir seletor de arquivo ao clicar no botão
  if (browseBtn) {
    browseBtn.addEventListener('click', function(e) {
      console.log('Botão de navegação clicado em:', dragArea.id);
      e.preventDefault();
      e.stopPropagation();
      fileInput.click();
    });
  }
  
  // Abrir seletor de arquivo ao clicar na área (exceto no botão ou no input)
  dragArea.addEventListener('click', function(e) {
    // Verificar se o clique não foi no input, no botão ou em um elemento filho do botão
    if (e.target !== fileInput && !e.target.closest('.browse-btn')) {
      console.log('Área de drag and drop clicada:', dragArea.id);
      fileInput.click();
    }
  });
  
  // Lidar com a seleção de arquivo via input
  fileInput.addEventListener('change', function() {
    if (this.files && this.files.length) {
      console.log('Arquivo selecionado via input:', this.files[0].name);
      updateFileDetails(dragArea, selectedFile, this.files[0]);
    }
  });
}

// Atualizar detalhes do arquivo selecionado
function updateFileDetails(dragArea, selectedFile, file) {
  if (!file) {
    console.error('Nenhum arquivo fornecido para updateFileDetails');
    return;
  }
  
  console.log('Atualizando detalhes do arquivo:', file.name);
  
  // Verificar extensão de arquivo
  const allowedExtensions = ['pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx'];
  const fileExtension = file.name.split('.').pop().toLowerCase();
  const isValidExtension = allowedExtensions.includes(fileExtension);
  
  // Limpar classes anteriores
  dragArea.classList.remove('file-uploaded');
  dragArea.classList.remove('file-error');
  dragArea.classList.remove('active');
  
  // Adicionar a classe apropriada
  if (isValidExtension) {
    dragArea.classList.add('file-uploaded');
  } else {
    dragArea.classList.add('file-error');
  }
  
  // Atualizar a exibição do arquivo selecionado
  if (selectedFile) {
    // Limpar conteúdo anterior
    selectedFile.innerHTML = '';
    
    if (isValidExtension) {
      // Criar um elemento para exibir o arquivo selecionado
      const fileInfo = document.createElement('div');
      fileInfo.className = 'alert alert-success p-2 mb-0';
      fileInfo.innerHTML = `
        <div class="d-flex align-items-center">
          <i class="fas fa-check-circle me-2"></i>
          <span class="flex-grow-1 text-truncate">${file.name}</span>
          <button type="button" class="btn-close btn-sm ms-2" aria-label="Remover" onclick="clearFileSelection(this)"></button>
        </div>
      `;
      selectedFile.appendChild(fileInfo);
    } else {
      // Exibir mensagem de erro
      const errorInfo = document.createElement('div');
      errorInfo.className = 'alert alert-danger p-2 mb-0';
      errorInfo.innerHTML = `
        <div class="d-flex align-items-center">
          <i class="fas fa-exclamation-triangle me-2"></i>
          <span>Formato não suportado: ${fileExtension}</span>
          <button type="button" class="btn-close btn-sm ms-2" aria-label="Remover" onclick="clearFileSelection(this)"></button>
        </div>
      `;
      selectedFile.appendChild(errorInfo);
    }
  }
  
  console.log(`Arquivo ${isValidExtension ? 'válido' : 'inválido'}: ${file.name}`);
}

// Função para limpar a seleção de arquivo
function clearFileSelection(button) {
  const selectedFileElement = button.closest('.selected-file');
  const dragArea = selectedFileElement.closest('.drag-area');
  const fileInput = dragArea.querySelector('input[type="file"]');
  
  // Limpar o input de arquivo
  if (fileInput) {
    fileInput.value = '';
  }
  
  // Limpar a exibição
  selectedFileElement.innerHTML = '';
  
  // Remover classes
  dragArea.classList.remove('file-uploaded');
  dragArea.classList.remove('file-error');
  
  console.log('Seleção de arquivo limpa');
}

// Inicializar quando o documento estiver pronto
document.addEventListener('DOMContentLoaded', function() {
  console.log('DOM carregado, inicializando funções de anexos');
  setupDragAndDrop();
  
  // Verificar se há formulário e adicionar evento de submit
  const form = document.querySelector('form');
  if (form) {
    form.addEventListener('submit', function(e) {
      // Verificar se há arquivos selecionados
      const fileInputs = form.querySelectorAll('input[type="file"]');
      let hasFiles = false;
      
      fileInputs.forEach(function(input) {
        if (input.files && input.files.length > 0) {
          hasFiles = true;
          console.log('Arquivo para envio:', input.name, input.files[0].name);
        }
      });
      
      if (hasFiles) {
        console.log('Formulário sendo enviado com arquivos');
      } else {
        console.log('Formulário sendo enviado sem arquivos');
      }
    });
  }
});
