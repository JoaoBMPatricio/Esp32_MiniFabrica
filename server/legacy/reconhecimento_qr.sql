CREATE TABLE IF NOT EXISTS reconhecimento_qr (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hora TEXT NOT NULL,
    codigo_qr TEXT NOT NULL
);

SELECT *
FROM reconhecimento_qr
ORDER BY hora DESC;

SELECT strftime('%H', hora) AS hora, COUNT(*) AS quantidade
FROM reconhecimento_qr
GROUP BY strftime('%H', hora)
ORDER BY hora;
