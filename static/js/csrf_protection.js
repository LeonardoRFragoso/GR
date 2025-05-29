/**
 * CSRF Protection - Garante que todas as requisições AJAX incluam o token CSRF
 * 
 * Este script deve ser incluído em todas as páginas que fazem requisições AJAX
 * para garantir que o token CSRF seja incluído em todas as requisições POST.
 */

document.addEventListener('DOMContentLoaded', function() {
    // Função para obter o token CSRF da meta tag
    function getCSRFToken() {
        const metaTag = document.querySelector('meta[name="csrf-token"]');
        return metaTag ? metaTag.getAttribute('content') : null;
    }

    // Função para obter o token CSRF de um input hidden
    function getCSRFTokenFromForm() {
        const csrfInput = document.querySelector('input[name="csrf_token"]');
        return csrfInput ? csrfInput.value : null;
    }

    // Função para verificar se todos os formulários têm o token CSRF
    function checkAllForms() {
        const forms = document.querySelectorAll('form[method="post"]');
        const csrfToken = getCSRFToken() || getCSRFTokenFromForm();
        
        if (!csrfToken) {
            console.warn('CSRF token não encontrado na página. Isso pode causar erros 400 Bad Request.');
            return;
        }
        
        forms.forEach(form => {
            let hasCSRFToken = false;
            
            // Verificar se o formulário já tem um input com o token CSRF
            const inputs = form.querySelectorAll('input');
            inputs.forEach(input => {
                if (input.name === 'csrf_token') {
                    hasCSRFToken = true;
                    // Garantir que o valor do token está atualizado
                    input.value = csrfToken;
                }
            });
            
            // Se não tiver, adicionar o token CSRF
            if (!hasCSRFToken) {
                const csrfInput = document.createElement('input');
                csrfInput.type = 'hidden';
                csrfInput.name = 'csrf_token';
                csrfInput.value = csrfToken;
                form.appendChild(csrfInput);
                console.log('Token CSRF adicionado ao formulário:', form.action);
            }
            
            // Adicionar evento submit para garantir que o token CSRF está presente
            form.addEventListener('submit', function(e) {
                const csrfInput = this.querySelector('input[name="csrf_token"]');
                if (!csrfInput || !csrfInput.value) {
                    e.preventDefault();
                    console.error('Erro: Token CSRF ausente no formulário');
                    alert('Erro de segurança: Token CSRF ausente. Por favor, recarregue a página e tente novamente.');
                    return false;
                }
            });
        });
    }

    // Configurar AJAX para incluir o token CSRF em todas as requisições
    const csrfToken = getCSRFToken() || getCSRFTokenFromForm();
    if (csrfToken) {
        // Se o jQuery estiver disponível, configurar o AJAX do jQuery
        if (typeof $ !== 'undefined' && $.ajaxSetup) {
            $.ajaxSetup({
                beforeSend: function(xhr, settings) {
                    if (!/^(GET|HEAD|OPTIONS|TRACE)$/i.test(settings.type) && !this.crossDomain) {
                        xhr.setRequestHeader('X-CSRFToken', csrfToken);
                    }
                }
            });
            console.log('CSRF token configurado para requisições AJAX do jQuery');
        }

        // Configurar o Fetch API para incluir o token CSRF
        const originalFetch = window.fetch;
        window.fetch = function(url, options = {}) {
            // Se não for GET, HEAD, OPTIONS ou TRACE, adicionar o token CSRF
            if (options.method && !/^(GET|HEAD|OPTIONS|TRACE)$/i.test(options.method)) {
                options.headers = options.headers || {};
                options.headers['X-CSRFToken'] = csrfToken;
            }
            return originalFetch(url, options);
        };
        console.log('CSRF token configurado para requisições Fetch API');

        // Configurar o XMLHttpRequest para incluir o token CSRF
        const originalOpen = XMLHttpRequest.prototype.open;
        XMLHttpRequest.prototype.open = function(method, url) {
            const xhr = this;
            originalOpen.apply(xhr, arguments);
            
            if (!/^(GET|HEAD|OPTIONS|TRACE)$/i.test(method)) {
                xhr.addEventListener('readystatechange', function() {
                    if (xhr.readyState === 1) { // OPENED
                        xhr.setRequestHeader('X-CSRFToken', csrfToken);
                    }
                });
            }
        };
        console.log('CSRF token configurado para requisições XMLHttpRequest');
    } else {
        console.warn('CSRF token não encontrado. Requisições AJAX podem falhar com erro 400 Bad Request.');
    }

    // Verificar todos os formulários na página
    checkAllForms();

    // Observar mudanças no DOM para verificar novos formulários
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.addedNodes && mutation.addedNodes.length > 0) {
                // Verificar se algum dos nós adicionados é um formulário ou contém um formulário
                for (let i = 0; i < mutation.addedNodes.length; i++) {
                    const node = mutation.addedNodes[i];
                    if (node.nodeType === 1) { // ELEMENT_NODE
                        if (node.tagName === 'FORM' && node.getAttribute('method') === 'post') {
                            checkAllForms();
                            break;
                        } else if (node.querySelectorAll) {
                            const forms = node.querySelectorAll('form[method="post"]');
                            if (forms.length > 0) {
                                checkAllForms();
                                break;
                            }
                        }
                    }
                }
            }
        });
    });

    // Configurar o observer para observar todo o documento
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
});
