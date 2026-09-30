#include <Arduino.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <WiFi.h>
#include "esp_camera.h"
#include "esp_system.h"
#include "qr_config.h"
#include "secrets.h"

#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22
#define FLASH_GPIO_NUM 4

WebServer server(80);
bool cameraPronta = false;
bool reconhecimentoEmAndamento = false;
bool leituraSolicitada = false;
bool wifiEstavaConectado = false;
uint32_t proximaTentativaWiFi = 0;
uint32_t ultimoGatilhoAceitoUs = 0;
volatile bool gatilhoPendente = false;
volatile uint32_t instanteGatilhoUs = 0;
String ultimoResultado = "Nenhuma leitura realizada.";
int ultimoStatus = 0;

void IRAM_ATTR registrarGatilho() {
    instanteGatilhoUs = micros();
    gatilhoPendente = true;
}

void desligarFlash() {
    pinMode(FLASH_GPIO_NUM, OUTPUT);
    digitalWrite(FLASH_GPIO_NUM, LOW);
}

void mostrarRedeConectada(const char *mensagem) {
    Serial.println(mensagem);
    Serial.print("IP da ESP32: ");
    Serial.println(WiFi.localIP());
    Serial.print("Gateway: ");
    Serial.println(WiFi.gatewayIP());
}

void iniciarWiFi() {
    Serial.println("Conectando ao Wi-Fi...");
    WiFi.persistent(false);
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.begin(WIFI_NOME, WIFI_SENHA);

    uint32_t inicio = millis();
    while (WiFi.status() != WL_CONNECTED &&
           millis() - inicio < QR_WIFI_CONNECT_TIMEOUT_MS) {
        delay(250);
        Serial.print(".");
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
        wifiEstavaConectado = true;
        mostrarRedeConectada("Wi-Fi conectado.");
    } else {
        wifiEstavaConectado = false;
        proximaTentativaWiFi = millis() + QR_WIFI_RETRY_INTERVAL_MS;
        Serial.println(
            "Wi-Fi indisponivel. O firmware continuara tentando."
        );
    }
}

void gerenciarWiFi() {
    bool conectado = WiFi.status() == WL_CONNECTED;
    if (conectado) {
        if (!wifiEstavaConectado) {
            mostrarRedeConectada("Wi-Fi reconectado.");
        }
        wifiEstavaConectado = true;
        return;
    }

    if (wifiEstavaConectado) {
        Serial.println("Wi-Fi desconectado.");
    }
    wifiEstavaConectado = false;

    if ((int32_t)(millis() - proximaTentativaWiFi) >= 0) {
        Serial.println("Tentando reconectar ao Wi-Fi...");
        WiFi.begin(WIFI_NOME, WIFI_SENHA);
        proximaTentativaWiFi = millis() + QR_WIFI_RETRY_INTERVAL_MS;
    }
}

void configurarSensorCamera() {
    sensor_t *sensor = esp_camera_sensor_get();
    if (!sensor) {
        Serial.println("Nao foi possivel configurar o sensor.");
        return;
    }

    sensor->set_vflip(sensor, 1);
    sensor->set_brightness(sensor, 1);
    sensor->set_contrast(sensor, 2);
    sensor->set_saturation(sensor, -2);
    sensor->set_sharpness(sensor, 2);
    sensor->set_denoise(sensor, 1);
    sensor->set_whitebal(sensor, 1);
    sensor->set_awb_gain(sensor, 1);
    sensor->set_gain_ctrl(sensor, 1);
    sensor->set_exposure_ctrl(sensor, 1);
    sensor->set_aec2(sensor, 1);
    sensor->set_ae_level(sensor, 1);
    sensor->set_gainceiling(sensor, GAINCEILING_4X);
    sensor->set_bpc(sensor, 1);
    sensor->set_wpc(sensor, 1);
    sensor->set_lenc(sensor, 1);
    sensor->set_raw_gma(sensor, 1);
    Serial.println("Sensor configurado para leitura de QR Code.");
}

bool iniciarCamera() {
    Serial.println("Inicializando camera...");
    Serial.println(
        psramFound() ? "PSRAM detectada." : "PSRAM nao detectada."
    );

    camera_config_t config = {};
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = Y2_GPIO_NUM;
    config.pin_d1 = Y3_GPIO_NUM;
    config.pin_d2 = Y4_GPIO_NUM;
    config.pin_d3 = Y5_GPIO_NUM;
    config.pin_d4 = Y6_GPIO_NUM;
    config.pin_d5 = Y7_GPIO_NUM;
    config.pin_d6 = Y8_GPIO_NUM;
    config.pin_d7 = Y9_GPIO_NUM;
    config.pin_xclk = XCLK_GPIO_NUM;
    config.pin_pclk = PCLK_GPIO_NUM;
    config.pin_vsync = VSYNC_GPIO_NUM;
    config.pin_href = HREF_GPIO_NUM;
    config.pin_sccb_sda = SIOD_GPIO_NUM;
    config.pin_sccb_scl = SIOC_GPIO_NUM;
    config.pin_pwdn = PWDN_GPIO_NUM;
    config.pin_reset = RESET_GPIO_NUM;
    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;
    config.frame_size = FRAMESIZE_SVGA;
    config.jpeg_quality = 10;
    config.fb_count = 1;
    config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
    config.fb_location = CAMERA_FB_IN_PSRAM;

    esp_err_t resultado = esp_camera_init(&config);
    if (resultado != ESP_OK) {
        Serial.printf("Erro ao inicializar camera: 0x%X\n", resultado);
        return false;
    }
    configurarSensorCamera();
    Serial.println("Camera inicializada com sucesso.");
    return true;
}

camera_fb_t *obterFotoAtual() {
    if (!cameraPronta) {
        return nullptr;
    }
    delay(QR_SETTLE_MS);
    for (int i = 0; i < 2; ++i) {
        camera_fb_t *antigo = esp_camera_fb_get();
        if (!antigo) {
            return nullptr;
        }
        esp_camera_fb_return(antigo);
    }
    return esp_camera_fb_get();
}

String gerarOperationId() {
    uint64_t chip = ESP.getEfuseMac();
    char id[64];
    snprintf(
        id,
        sizeof(id),
        "%04lX%08lX-%08lX-%08lX",
        (unsigned long)(chip >> 32),
        (unsigned long)(chip & 0xFFFFFFFFULL),
        (unsigned long)millis(),
        (unsigned long)esp_random()
    );
    return String(id);
}

int enviarFotoAoServidor(
    camera_fb_t *foto,
    const String &operationId,
    String &resposta
) {
    int ultimoCodigo = -1;
    String ultimoErro = "falha desconhecida";

    for (uint8_t tentativa = 0;
         tentativa <= QR_HTTP_MAX_RETRIES;
         ++tentativa) {
        if (WiFi.status() != WL_CONNECTED) {
            resposta = "Servidor de reconhecimento indisponivel: sem Wi-Fi.";
            return 503;
        }

        if (tentativa > 0) {
            Serial.println("Repetindo o envio com o mesmo operation_id...");
            delay(QR_HTTP_RETRY_DELAY_MS);
        }

        WiFiClient cliente;
        HTTPClient http;
        http.setConnectTimeout(QR_HTTP_CONNECT_TIMEOUT_MS);
        http.setTimeout(QR_HTTP_TIMEOUT_MS);
        http.setReuse(false);

        if (!http.begin(cliente, QR_SERVER_URL)) {
            ultimoCodigo = -1;
            ultimoErro = "URL do servidor invalida";
        } else {
            http.addHeader("Content-Type", "image/jpeg");
            http.addHeader("X-Operation-Id", operationId);
            ultimoCodigo = http.POST(foto->buf, foto->len);
            if (ultimoCodigo > 0) {
                resposta = http.getString();
            } else {
                ultimoErro = HTTPClient::errorToString(ultimoCodigo);
            }
            http.end();
        }

        if (ultimoCodigo > 0 && ultimoCodigo < 500) {
            return ultimoCodigo;
        }
    }

    if (ultimoCodigo > 0) {
        return ultimoCodigo;
    }
    resposta = "Servidor de reconhecimento indisponivel. Detalhe: " +
               ultimoErro;
    return 502;
}

bool lerQrCode() {
    if (reconhecimentoEmAndamento) {
        return false;
    }

    reconhecimentoEmAndamento = true;
    digitalWrite(QR_BUSY_PIN, HIGH);
    ultimoStatus = 503;
    ultimoResultado = "Camera, Wi-Fi ou servidor indisponivel.";

    if (!cameraPronta) {
        ultimoStatus = 500;
        ultimoResultado = "Camera indisponivel.";
    } else if (WiFi.status() != WL_CONNECTED) {
        ultimoResultado = "Servidor de reconhecimento indisponivel: sem Wi-Fi.";
    } else if (QR_SERVER_URL[0] == '\0') {
        ultimoResultado = "Configure QR_SERVER_URL em include/qr_config.h.";
    } else {
        camera_fb_t *foto = obterFotoAtual();
        if (!foto) {
            ultimoStatus = 500;
            ultimoResultado = "Falha ao capturar imagem.";
        } else {
            String operationId = gerarOperationId();
            Serial.print("operation_id: ");
            Serial.println(operationId);
            ultimoStatus = enviarFotoAoServidor(
                foto, operationId, ultimoResultado
            );
            esp_camera_fb_return(foto);
        }
    }

    Serial.printf("Leitura QR - HTTP %d: ", ultimoStatus);
    Serial.println(ultimoResultado);
    digitalWrite(QR_BUSY_PIN, LOW);
    reconhecimentoEmAndamento = false;
    return true;
}

void processarGatilho() {
    bool pendente = false;
    uint32_t instante = 0;
    noInterrupts();
    if (gatilhoPendente) {
        pendente = true;
        instante = instanteGatilhoUs;
        gatilhoPendente = false;
    }
    interrupts();

    if (pendente &&
        instante - ultimoGatilhoAceitoUs >= QR_DEBOUNCE_MS * 1000UL) {
        ultimoGatilhoAceitoUs = instante;
        leituraSolicitada = true;
    }

    if (leituraSolicitada && !reconhecimentoEmAndamento) {
        leituraSolicitada = false;
        lerQrCode();
    }
}

void paginaInicial() {
    String pagina = R"rawliteral(
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Mini Fabrica Inteligente</title>
</head>
<body>
    <h1>Mini Fabrica Inteligente</h1>
    <h2>Grupo 3 - ESP32-CAM</h2>
    <p>Use a previa para ajustar a camera e Ler QR Code para registrar a peca.</p>
    <button onclick="capturar()">Capturar imagem</button>
    <button id="ler" onclick="lerQr()">Ler QR Code</button>
    <pre id="resultado" aria-live="polite"></pre>
    <img id="imagem" alt="Previa da camera" style="max-width: 100%;">
    <script>
        async function atualizarResultado() {
            try {
                const resposta = await fetch('/result', {cache: 'no-store'});
                document.getElementById('resultado').textContent =
                    await resposta.text();
            } catch (_) {
                document.getElementById('resultado').textContent =
                    'ESP32-CAM indisponivel.';
            }
        }
        async function lerQr() {
            const botao = document.getElementById('ler');
            botao.disabled = true;
            document.getElementById('resultado').textContent = 'Processando...';
            try {
                const resposta = await fetch('/read', {method: 'POST'});
                document.getElementById('resultado').textContent =
                    await resposta.text();
            } catch (_) {
                document.getElementById('resultado').textContent =
                    'Falha de conexao.';
            } finally {
                botao.disabled = false;
            }
        }
        function capturar() {
            document.getElementById('imagem').src =
                '/capture?t=' + Date.now();
        }
        async function acompanhar() {
            if (!document.getElementById('ler').disabled) {
                await atualizarResultado();
            }
            setTimeout(acompanhar, 2000);
        }
        acompanhar();
    </script>
</body>
</html>
)rawliteral";
    server.send(200, "text/html; charset=utf-8", pagina);
}

void capturarImagem() {
    if (reconhecimentoEmAndamento) {
        server.send(
            409,
            "application/json; charset=utf-8",
            "{\"ok\":false,\"erro\":\"sistema_ocupado\","
            "\"mensagem\":\"Reconhecimento ja esta em andamento.\"}"
        );
        return;
    }

    camera_fb_t *foto = obterFotoAtual();
    if (!foto) {
        server.send(
            500,
            "application/json; charset=utf-8",
            "{\"ok\":false,\"erro\":\"captura_falhou\"}"
        );
        return;
    }

    size_t esperado = foto->len;
    server.sendHeader("Cache-Control", "no-store");
    server.sendHeader("Connection", "close");
    server.setContentLength(esperado);
    server.send(200, "image/jpeg", "");

    WiFiClient cliente = server.client();
    size_t enviado = 0;
    uint8_t falhas = 0;
    while (enviado < esperado && cliente.connected() && falhas < 3) {
        size_t restante = esperado - enviado;
        size_t bytes = cliente.write(foto->buf + enviado, restante);
        if (bytes == 0) {
            ++falhas;
            delay(10);
        } else {
            enviado += bytes;
            falhas = 0;
        }
    }
    esp_camera_fb_return(foto);

    Serial.printf(
        "Previa JPEG: esperado=%u, enviado=%u bytes.\n",
        (unsigned int)esperado,
        (unsigned int)enviado
    );
    if (enviado != esperado) {
        Serial.println("Falha: envio parcial da previa ao navegador.");
    } else {
        Serial.println("Previa enviada por completo.");
    }
}

void configurarServidor() {
    server.on("/", HTTP_GET, paginaInicial);
    server.on("/capture", HTTP_GET, capturarImagem);
    server.on("/read", HTTP_POST, []() {
        if (reconhecimentoEmAndamento) {
            server.send(
                409,
                "application/json; charset=utf-8",
                "{\"ok\":false,\"erro\":\"sistema_ocupado\","
                "\"mensagem\":\"Reconhecimento ja esta em andamento.\"}"
            );
            return;
        }
        lerQrCode();
        server.sendHeader("Cache-Control", "no-store");
        server.send(ultimoStatus, "application/json; charset=utf-8", ultimoResultado);
    });
    server.on("/result", HTTP_GET, []() {
        server.sendHeader("Cache-Control", "no-store");
        server.send(
            200,
            "text/plain; charset=utf-8",
            String("HTTP ") + ultimoStatus + "\n" + ultimoResultado
        );
    });
    server.onNotFound([]() {
        server.send(
            404,
            "application/json; charset=utf-8",
            "{\"ok\":false,\"erro\":\"rota_inexistente\"}"
        );
    });
    server.begin();
    Serial.println("Servidor HTTP da ESP32 iniciado na porta 80.");
}

void setup() {
    Serial.begin(115200);
    pinMode(QR_TRIGGER_PIN, INPUT_PULLUP);
    pinMode(QR_BUSY_PIN, OUTPUT);
    digitalWrite(QR_BUSY_PIN, LOW);
    desligarFlash();
    delay(2000);

    Serial.println("==============================");
    Serial.println("Mini Fabrica Inteligente");
    Serial.println("Grupo 3 - ESP32-CAM");
    Serial.println("==============================");

    iniciarWiFi();
    cameraPronta = iniciarCamera();
    if (!cameraPronta) {
        Serial.println(
            "Camera indisponivel. Interface iniciada para diagnostico."
        );
    }
    configurarServidor();
    attachInterrupt(
        digitalPinToInterrupt(QR_TRIGGER_PIN), registrarGatilho, FALLING
    );
    digitalWrite(QR_BUSY_PIN, LOW);
}

void loop() {
    gerenciarWiFi();
    processarGatilho();
    server.handleClient();
    delay(1);
}
