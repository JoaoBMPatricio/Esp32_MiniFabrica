# Mini Fábrica Inteligente com ESP32-CAM

Projeto do Grupo 3, Equipe B, para reconhecimento de QR Codes industriais. A
ESP32-CAM fotografa uma etiqueta, envia o JPEG pela rede e o servidor Python
interpreta e registra a peça no SQLite.

## Arquitetura oficial

```text
ESP32-CAM
  -> captura JPEG
  -> POST /api/qr com X-Operation-Id
  -> server/app.py
  -> OpenCV QRCodeDetector
  -> validação do QR industrial
  -> SQLite
  -> resposta JSON para ESP32 e navegador
```

O único servidor oficial é `server/app.py`, na porta 5000. Protótipos antigos
foram preservados em `server/legacy/` e não devem ser executados.

## QR industrial

Cada etiqueta deve possuir exatamente este formato:

```text
PECA;NOME_PECA;LOTE;MATERIAL;STATUS
```

Exemplo:

```text
PECA;ENGRENAGEM;L-001;ACO;APROVADA
```

O servidor aceita os status `APROVADA`, `REPROVADA`, `INSPECAO` e `INSPEÇÃO`.
`INSPEÇÃO` é armazenado como `INSPECAO`. Nome da peça, lote e material não usam
listas fixas. Campos vazios, extras, ausentes ou excessivamente grandes são
rejeitados e não chegam ao banco.

Cada leitura válida registra:

- ID gerado pelo SQLite;
- Dado, preservando o texto original do QR;
- Data/Hora do computador que executa o servidor, incluindo o fuso;
- Quantidade igual a 1 por peça;
- Tipo, peça, lote, material e status em campos separados;
- `operation_id` gerado pela ESP32 para impedir duplicação em retentativas.

## Requisitos

- ESP32-CAM AI Thinker com PSRAM e programador USB compatível;
- computador com Python e PlatformIO;
- ESP32 e computador acessíveis pela mesma rede Wi-Fi de 2,4 GHz;
- QR Code visível, foco ajustado e iluminação externa;

## Configuração

### Wi-Fi

Copie o exemplo e preencha os dados locais:

```powershell
Copy-Item include/secrets.example.h include/secrets.h
```

Edite `include/secrets.h`:

```cpp
const char* WIFI_NOME = "NOME_DA_REDE";
const char* WIFI_SENHA = "SENHA_DA_REDE";
```

### Endereço do servidor

Copie a configuração de exemplo:

```powershell
Copy-Item include/qr_config.example.h include/qr_config.h
```

Descubra o IPv4 do computador com `ipconfig` e edite `QR_SERVER_URL`:

```cpp
constexpr const char *QR_SERVER_URL =
    "http://192.168.0.10:5000/api/qr";
```

Não use `localhost`: na ESP32 isso significaria a própria placa. Os arquivos
`secrets.h` e `qr_config.h` são locais e ignorados pelo Git.

## Executar o servidor

Na raiz do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r server/requirements.txt
.\.venv\Scripts\python.exe server/app.py
```

O processo escuta em `0.0.0.0:5000`. Se necessário, permita TCP 5000 no
firewall da rede privada. É possível mudar o banco, a porta ou a interface:

```powershell
$env:QR_DATABASE = 'C:\dados\mini-fabrica.db'
$env:QR_PORT = '5001'
$env:QR_HOST = '0.0.0.0'
.\.venv\Scripts\python.exe server/app.py
```

Ao mudar a porta, atualize também `QR_SERVER_URL` e grave o firmware novamente.

## API e integração com a Equipe C

| Método e URL | Função |
| --- | --- |
| `GET /health` | Verifica OpenCV, acesso ao SQLite e tabela oficial |
| `POST /api/qr` | Recebe JPEG e `X-Operation-Id`, reconhece e registra |
| `GET /api/leituras?limite=50` | Retorna até 200 leituras recentes |
| `GET /api/resumo` | Totais por peça, status e lote, mais leituras recentes |

Exemplo de sucesso:

```json
{
  "ok": true,
  "id": 15,
  "operation_id": "AABBCCDDEEFF-0012ABCD-89ABCDEF",
  "dado": "PECA;ENGRENAGEM;L-001;ACO;APROVADA",
  "tipo": "PECA",
  "nome_peca": "ENGRENAGEM",
  "lote": "L-001",
  "material": "ACO",
  "status": "APROVADA",
  "data_hora": "2026-09-30T08:30:00-03:00",
  "quantidade": 1,
  "duplicate": false
}
```

Se a mesma operação for recebida outra vez, o servidor devolve o registro
original com `duplicate: true`. Nenhuma segunda linha é criada. A Equipe C pode
usar `total_pecas`, `por_peca`, `por_status`, `por_lote` e
`leituras_recentes` retornados por `/api/resumo`; o dashboard não faz parte
deste repositório.

O banco padrão é `server/leituras.db`. Na primeira inicialização, o servidor
adiciona colunas ausentes da versão anterior, cria `operation_id` para linhas
antigas e ajusta `quantidade` para 1 sem apagar registros. Conteúdo antigo que
não segue o QR industrial é preservado, mas seus campos industriais permanecem
nulos. Faça backup do arquivo antes de uma apresentação importante.

## Interface da ESP32

Após o Serial informar o IP, abra:

```text
http://IP_DA_ESP32/
```

- **Capturar imagem** mostra uma prévia sem alterar o sinal BUSY.
- **Ler QR Code** inicia um ciclo completo e registra uma peça.
- `/result` mostra o último status e a resposta do servidor Python.