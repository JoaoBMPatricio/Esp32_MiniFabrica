# Servidor oficial de QR Code

`app.py` é a única implementação oficial. Ele recebe JPEG da ESP32-CAM,
reconhece exatamente um QR Code industrial, valida seus campos e registra a
leitura no SQLite. Os programas em `legacy/` são apenas referência histórica.

## Instalação e execução

Execute na raiz do repositório:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r server/requirements.txt
.\.venv\Scripts\python.exe server/app.py
```

O Waitress escuta por padrão em `0.0.0.0:5000`. O SQLite padrão fica em
`server/leituras.db`. As variáveis opcionais são `QR_HOST`, `QR_PORT` e
`QR_DATABASE`.

## Contrato do QR

```text
PECA;NOME_PECA;LOTE;MATERIAL;STATUS
```

São aceitos `APROVADA`, `REPROVADA`, `INSPECAO` e `INSPEÇÃO`. O conteúdo
original permanece em `dado`; os cinco campos também são armazenados
separadamente. Uma leitura representa uma peça e sempre recebe `quantidade = 1`.

## API

### GET /health

Verifica processo, OpenCV, banco e tabela. Retorna HTTP 200 somente quando o
serviço está pronto:

```json
{"ok": true, "status": "ready", "banco": "ready", "opencv": "4.x"}
```

### POST /api/qr

Cabeçalhos obrigatórios:

```text
Content-Type: image/jpeg
X-Operation-Id: identificador-unico-da-operacao
```

O corpo contém os bytes JPEG, sem multipart, Base64 ou JSON. O identificador
aceita de 1 a 128 letras, números, `.`, `_`, `-` e `:`. Repetir o mesmo
identificador devolve o registro existente com `duplicate: true`.

Limites: 2 MiB por requisição, 4 megapixels por imagem, 256 caracteres no texto
total e limites específicos por campo. Uma captura com mais de um QR legível é
rejeitada.

Exemplo manual com um arquivo:

```powershell
curl.exe -H "Content-Type: image/jpeg" `
  -H "X-Operation-Id: teste-manual-001" `
  --data-binary "@foto.jpg" `
  http://localhost:5000/api/qr
```

### GET /api/leituras

`/api/leituras?limite=50` retorna o total existente e os registros mais
recentes. O limite aceito fica entre 1 e 200.

### GET /api/resumo

Retorna:

- `total_pecas`;
- `por_peca`;
- `por_status`;
- `por_lote`;
- dez `leituras_recentes`.

Esses dados formam o contrato inicial para a Equipe C.

## Erros

Erros esperados são sempre JSON com `ok`, `erro` e `mensagem`.

| HTTP | Exemplos |
| --- | --- |
| 400 | imagem vazia/inválida ou operation_id inválido |
| 404 | rota inexistente |
| 405 | método incorreto |
| 413 | bytes ou resolução acima do limite |
| 415 | Content-Type diferente de `image/jpeg` |
| 422 | QR ausente, múltiplo ou industrialmente inválido |
| 503 | banco indisponível ou bloqueado |

## Banco e migração

O esquema de referência está em `schema.sql`. A inicialização de `app.py` usa
`PRAGMA table_info` e adiciona as colunas ausentes sem apagar linhas. Registros
anteriores recebem `operation_id` no formato `legacy-ID`, quantidade 1 e campos
industriais quando o texto antigo puder ser validado.

Uma linha antiga cujo conteúdo não seja industrial é preservada com campos
industriais nulos. Bancos com esquema desconhecido fora da tabela oficial não
são fundidos automaticamente. Faça backup do `.db` antes de migrações importantes.

## Testes

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s server -p "test_*.py" -v
```

Os testes não iniciam o servidor de rede e não usam o banco de produção; cada
caso cria um banco temporário.
