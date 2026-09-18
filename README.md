# Mini Fábrica Inteligente: leitura de QR Code

A ESP32-CAM com câmera OV3660 fotografa o QR Code da peça parada na esteira.
Um servidor Python/OpenCV no computador decodifica a imagem e devolve o texto,
por exemplo, `AZUL`. Projeto do Grupo 3.

```text
Arduino detecta a peça e para a esteira
  -> dispara a ESP32-CAM
  -> ESP32 captura JPEG e envia pela rede
  -> servidor lê o QR Code
  -> resultado na página da ESP32 e no monitor serial
```

Este repositório contém o firmware da ESP32-CAM e o servidor. O programa do
Arduino que controla sensor/motor, o retorno da palavra ao Arduino e a retomada
automática da esteira ainda não estão implementados aqui.

## Requisitos

- ESP32-CAM AI Thinker com PSRAM e módulo OV3660 compatível com a placa.
- Alimentação adequada e programador USB compatível, como ESP32-CAM-MB.
- Computador com Python e PlatformIO (extensão do VS Code ou CLI).
- Wi-Fi de 2,4 GHz para a ESP32 e computador acessível pela rede local.
  O computador pode estar conectado por Ethernet.
- QR Code visível, foco ajustado e iluminação externa. O flash está desligado.
- Para disparo automático: Arduino da esteira e ligação descrita abaixo.
  O teste pelo navegador dispensa o Arduino.

## Executar pela primeira vez

Os comandos usam PowerShell aberto na raiz deste projeto.

### 1. Iniciar o servidor

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r server/requirements.txt
.\.venv\Scripts\python.exe server/app.py
```

Mantenha o terminal aberto. Acesse [localhost:5000/health](http://localhost:5000/health):
a resposta deve ser `{"ok":true}`. O servidor Python é uma API; a página de testes
fica na ESP32. Para encerrar o processo iniciado nesse terminal, use `Ctrl+C`.

### 2. Configurar a rede

Em outro terminal, execute `ipconfig` e identifique o IPv4 da interface de rede
local do computador, não o endereço de uma VPN.

Crie `include/secrets.h` usando [secrets.example.h](include/secrets.example.h)
como modelo, caso ainda não exista. Preencha `WIFI_NOME` e `WIFI_SENHA`.
Esse arquivo é ignorado pelo Git; não publique suas credenciais.

Em [include/qr_config.h](include/qr_config.h), ajuste o endereço do servidor:

```cpp
constexpr const char *QR_SERVER_URL = "http://192.168.0.189:5000/api/qr";
```

Substitua o IP pelo do seu computador. Não use `localhost`, que na ESP32 aponta
para a própria placa. Se necessário, permita TCP 5000 no firewall da rede privada.
Se o IP ou a porta mudar, atualize a configuração e envie o firmware novamente.

### 3. Compilar e gravar a ESP32-CAM

Conecte a placa pelo programador USB. No PlatformIO do VS Code, use **Build**,
**Upload** e **Serial Monitor**, no ambiente `esp32cam`. Pelo terminal:

```powershell
pio run
pio run --target upload
pio device monitor --baud 115200
```

Se `pio` não estiver no PATH, use o terminal do PlatformIO. Na instalação padrão
do Windows, também é possível substituir `pio` por
`& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe"`.
Se houver várias portas, informe a correta com `--upload-port COMx` no upload
e `--port COMx` no monitor.

Se o programador não fizer o boot automaticamente, use GPIO 0 em GND durante
o reset para gravar; depois remova essa ligação e reinicie para executar.
Aguarde o monitor serial mostrar o IP da ESP32-CAM.

### 4. Testar a leitura

1. Abra `http://IP-DA-ESP32/` no navegador.
2. Posicione um único QR Code diante da câmera.
3. Use **Capturar imagem** para conferir enquadramento e foco.
4. Use **Ler QR Code** para capturar, enviar ao servidor e exibir o conteúdo.

Uma leitura válida retorna, por exemplo, `{"ok":true,"conteudo":"AZUL"}`.
O texto é preservado: não precisa ser link nem pertencer a uma lista de palavras.
Uma falha exibe um erro e substitui o resultado anterior.

## Disparo pela esteira

Interligue os GNDs. Os GPIOs abaixo são compartilhados com microSD;
não use cartão SD nessa configuração.

| Sinal | Pino da ESP32-CAM | Comportamento |
| --- | --- | --- |
| Disparo | GPIO 13, entrada com pull-up | LOW estável por 50 ms dispara uma leitura |
| Ocupada | GPIO 14, saída de 3,3 V | HIGH na inicialização/captura/envio; LOW quando livre |

**Não aplique 5 V aos GPIOs da ESP32.** Use conversão de nível ou, para o disparo,
uma saída que apenas puxe para GND (`OUTPUT LOW`) e libere a linha (`INPUT` sem
pull-up). Nunca aplique `OUTPUT HIGH` ou `INPUT_PULLUP` de 5 V nessa linha.
Confira se a entrada do Arduino reconhece os 3,3 V do sinal Ocupada.

O programa do Arduino deve seguir esta sequência:

1. Liberar Disparo por pelo menos 50 ms, inclusive após a inicialização.
2. Detectar a peça, parar a esteira e aguardar Ocupada = LOW.
3. Manter Disparo em LOW até observar Ocupada = HIGH.
4. Liberar Disparo e manter a esteira parada até Ocupada voltar a LOW.

Um LOW mantido não repete a leitura. Antes do próximo ciclo, deixe Disparo
liberado por pelo menos 50 ms após o fim da operação. Pulsos durante uma operação
não são enfileirados. Preveja timeout no Arduino, mantendo a peça parada em caso de falha.

**Ocupada = LOW indica o fim da tentativa, não sucesso no QR Code.**
A palavra fica disponível no HTTP/Serial da ESP32, mas ainda não é enviada ao
Arduino. Não use esse sinal sozinho para confirmar a classificação da peça.

## Configurações e arquivos

| Arquivo | Responsabilidade |
| --- | --- |
| [src/main.cpp](src/main.cpp) | Câmera, disparo, envio HTTP e página de testes |
| [include/qr_config.h](include/qr_config.h) | URL, pinos e tempos |
| `include/secrets.h` | Credenciais Wi-Fi locais |
| [platformio.ini](platformio.ini) | Placa, framework e gravação |
| [server/app.py](server/app.py) | API de leitura com OpenCV |
| [server/README.md](server/README.md) | API, testes e solução de erros |

A captura usa JPEG SVGA (800 × 600), um buffer em PSRAM, inversão vertical e
descarte de dois quadros antes da foto. `QR_SETTLE_MS` adiciona 150 ms de espera;
ajuste-o à parada mecânica real, pois o firmware não confirma que o motor parou.
Brilho, ganho e exposição são configurados em `configurarSensorCamera()`.

Para usar novamente, inicie o servidor e ligue a ESP32. Não é necessário
reinstalar dependências ou gravar o firmware se as configurações não mudaram.
O computador precisa permanecer ligado e acessível durante as leituras.
