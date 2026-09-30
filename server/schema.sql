-- Esquema de referência do servidor oficial server/app.py.
-- Migrações de bancos existentes são executadas pelo próprio aplicativo.
CREATE TABLE IF NOT EXISTS leituras_qr (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id TEXT NOT NULL UNIQUE,
    dado TEXT NOT NULL,
    tipo TEXT NOT NULL,
    nome_peca TEXT NOT NULL,
    lote TEXT NOT NULL,
    material TEXT NOT NULL,
    status TEXT NOT NULL,
    data_hora TEXT NOT NULL,
    quantidade INTEGER NOT NULL DEFAULT 1 CHECK (quantidade = 1)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_leituras_operation_id
ON leituras_qr (operation_id);

CREATE INDEX IF NOT EXISTS idx_leituras_nome_peca
ON leituras_qr (nome_peca);

CREATE INDEX IF NOT EXISTS idx_leituras_lote
ON leituras_qr (lote);

-- Quantidade total de peças.
SELECT COALESCE(SUM(quantidade), 0) AS total_pecas
FROM leituras_qr;

-- Quantidade por peça.
SELECT nome_peca, SUM(quantidade) AS quantidade
FROM leituras_qr
GROUP BY nome_peca
ORDER BY quantidade DESC, nome_peca;

-- Quantidade por status.
SELECT status, SUM(quantidade) AS quantidade
FROM leituras_qr
GROUP BY status
ORDER BY quantidade DESC, status;

-- Quantidade por lote.
SELECT lote, SUM(quantidade) AS quantidade
FROM leituras_qr
GROUP BY lote
ORDER BY quantidade DESC, lote;
