-- Adicionar colunas verificado e data_verificacao à tabela historico
ALTER TABLE historico ADD COLUMN verificado INTEGER DEFAULT 0;
ALTER TABLE historico ADD COLUMN data_verificacao TEXT;
