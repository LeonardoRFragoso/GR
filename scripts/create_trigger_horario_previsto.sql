-- Trigger para validar que horario_previsto é posterior à data_registro
CREATE TRIGGER IF NOT EXISTS check_horario_previsto
BEFORE INSERT ON registros
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.horario_previsto IS NOT NULL AND NEW.horario_previsto <= NEW.data_registro THEN
            RAISE(ABORT, 'O horário previsto deve ser posterior à data de registro')
    END;
END;

-- Trigger para validar que horario_previsto é posterior à data_registro durante atualizações
CREATE TRIGGER IF NOT EXISTS check_horario_previsto_update
BEFORE UPDATE ON registros
FOR EACH ROW
WHEN NEW.horario_previsto IS NOT NULL AND OLD.horario_previsto IS NOT NEW.horario_previsto
BEGIN
    SELECT CASE
        WHEN NEW.horario_previsto <= NEW.data_registro THEN
            RAISE(ABORT, 'O horário previsto deve ser posterior à data de registro')
    END;
END;
