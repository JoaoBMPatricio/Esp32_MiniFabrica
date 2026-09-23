# Servidor de leitura de QR Code

Recebe JPEG da ESP32-CAM, decodifica o QR Code com OpenCV, registra a leitura
em SQLite e retorna JSON. Flask define a API e Waitress atende as conexoes HTTP.
O servidor nao controla o motor, nao abre links e nao salva as imagens.

Para configurar Wi-Fi, gravar a placa e ligar o Arduino, siga o
[guia principal](../README).

## Iniciar

Execute na raiz do projeto, em PowerShell. Na primeira execucao:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r server/requirements.txt
```

Em cada sessao:

```powershell
.\.venv\Scripts\python.exe server/app.py
```

Mantenha o terminal aberto; `Ctrl+C` encerra o processo. O servidor escuta em
`0.0.0.0:5000`, acessivel pelas interfaces de rede do computador. Use somente
em rede local confiavel, pois esta API nao tem autenticacao.

Teste [localhost:5000/health](http://localhost:5000/health).
Para a ESP32, configure `http://IP-DO-COMPUTADOR:5000/api/qr` em
[include/qr_config.h](../include/qr_config.h) e grave novamente o firmware.
Nao existe pagina de interface na raiz deste servidor.

Para usar outra porta:

```powershell
$env:QR_PORT = '5001'
.\.venv\Scripts\python.exe server/app.py
```

Atualize tambem a porta na URL da ESP32. `QR_HOST` altera a interface de escuta;
`127.0.0.1` limita o acesso ao computador e impede a conexao da ESP32.

## API do servidor

| Metodo e rota | Resposta |
| --- | --- |
| `GET /health` | `{"ok":true}` quando o servidor esta ativo |
| `POST /api/qr` | Reconhece e registra o QR Code |
| `GET /api/leituras` | Historico das ultimas leituras |
| `GET /api/resumo` | Quantidade e ultima leitura por dado |

Envie os bytes JPEG diretamente no corpo de `POST /api/qr`, com
`Content-Type: image/jpeg`. Nao use multipart, base64 ou JSON no envio.
Limites: 2 MiB por requisicao, 4 megapixels por imagem e 256 caracteres no texto.
Imagens com mais de um QR detectado sao rejeitadas.

Sucesso, HTTP 200:

```json
{
  "ok": true,
  "conteudo": "AZUL",
  "registro": {
    "id": 1,
    "dado": "AZUL",
    "data_hora": "2026-09-22T15:20:00-03:00",
    "quantidade": 1
  }
}
```

Falha de leitura, HTTP 422:

```json
{"ok": false, "erro": "Nenhum QR Code legivel.", "conteudo": null}
```

| HTTP | Significado |
| --- | --- |
| 400 | Imagem vazia, invalida ou falha de decodificacao |
| 413 | Limite de bytes ou resolucao excedido |
| 415 | Content-Type diferente de image/jpeg |
| 422 | Sem QR legivel, multiplos QRs detectados ou texto longo demais |

O texto e preservado, incluindo maiusculas e espacos. Nao ha validacao de palavra
unica nem lista de categorias. As leituras bem-sucedidas aparecem no terminal e
sao gravadas em `server/leituras.db`. `quantidade` e o total acumulado daquele
mesmo dado no momento da leitura.

`GET /api/leituras?limite=50` retorna os registros mais recentes; o limite aceito
vai de 1 a 200. `GET /api/resumo` retorna uma linha por dado, adequada para a
integracao inicial com o dashboard da Equipe C.

Para armazenar o banco em outro local, defina `QR_DATABASE` antes de iniciar:

```powershell
$env:QR_DATABASE = 'C:\dados\mini-fabrica.db'
.\.venv\Scripts\python.exe server/app.py
```

## Rotas da ESP32-CAM

Estas rotas usam `http://IP-DA-ESP32` na porta 80, nao a porta do servidor Python.

| Metodo e rota | Funcao |
| --- | --- |
| `GET /` | Pagina com botoes de teste e resultado |
| `GET /capture` | Nova foto JPEG, sem decodificar QR |
| `POST /read` | Captura e envio ao servidor, como no disparo por GPIO |
| `GET /result` | Ultimo status e resposta em texto |

O resultado aparece na pagina e no monitor serial da ESP32. Falhas de rede
tambem sao exibidas; HTTP 502 indica falha de comunicacao HTTP.
`GET /result` retorna HTTP 200 para a consulta: o status da ultima leitura
esta no corpo. A ESP32 guarda apenas o ultimo resultado em memoria e o perde ao reiniciar.

## Testes

Com o servidor ativo, envie uma foto JPEG existente:

```powershell
curl.exe -H "Content-Type: image/jpeg" --data-binary "@foto.jpg" http://localhost:5000/api/qr
```

Execute a suite automatizada sem precisar iniciar o servidor:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s server -p "test_*.py" -v
```

Os testes cobrem texto, rotacao, multiplos QRs, ausencia de QR, imagens invalidas,
limites de entrada, gravacao no banco, historico e contagem. Usam imagens
sinteticas; foco, iluminacao, movimento e temporizacao precisam de teste na
camera e na esteira reais.

## Solucao de problemas

| Sintoma | Verificar |
| --- | --- |
| /health nao responde | Servidor iniciado, endereco e porta corretos |
| Porta ocupada | Use a instancia existente ou escolha outra porta com QR_PORT |
| ESP32 retorna falha HTTP | IP do computador, servidor ativo, rede acessivel e firewall |
| Funciona no computador, mas nao na ESP32 | Nao usar localhost na placa; conferir isolamento de clientes no Wi-Fi |
| HTTP 422 | Um unico QR inteiro na imagem, margem branca, foco e iluminacao |
| Foto borrada | Parada mecanica, tempo de estabilizacao e exposicao em src/main.cpp |
| GPIO nao dispara | GND comum, nivel de 3,3 V, liberacao de 50 ms e sequencia do guia principal |

Referencias: [OpenCV QRCodeDetector](https://docs.opencv.org/4.x/de/dc3/classcv_1_1QRCodeDetector.html)
e [Flask](https://flask.palletsprojects.com/en/stable/api/).
