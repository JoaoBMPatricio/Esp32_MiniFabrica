#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include "esp_camera.h"
#include "secrets.h"
#include "qr_config.h"

#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0

#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5

#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22
#define FLASH_GPIO_NUM    4

WebServer server(80);
bool cameraPronta = false;
bool gatilhoArmado = false;
int nivelGatilho = HIGH;
uint32_t mudancaGatilho = 0;
String ultimoResultado = "Nenhuma leitura realizada.";
int ultimoStatus = 0;

camera_fb_t *obterFotoAtual() {
    if (!cameraPronta) {
        return nullptr;
    }

    delay(QR_SETTLE_MS);
    // Um unico buffer: eliminar o quadro pendente e o seguinte.
    for (int i = 0; i < 2; ++i) {
        camera_fb_t *antigo = esp_camera_fb_get();
        if (!antigo) {
            return nullptr;
        }
        esp_camera_fb_return(antigo);
    }
    return esp_camera_fb_get();
}

void lerQrCode() {
    digitalWrite(QR_BUSY_PIN, HIGH);
    ultimoStatus = 503;
    ultimoResultado = "Camera ou Wi-Fi indisponivel.";

    if (cameraPronta && WiFi.status() == WL_CONNECTED) {
        if (QR_SERVER_URL[0] == '\0') {
            ultimoResultado = "Configure QR_SERVER_URL em include/qr_config.h.";
        } else {
            camera_fb_t *foto = obterFotoAtual();
            if (!foto) {
                ultimoStatus = 500;
                ultimoResultado = "Falha ao capturar imagem.";
            } else {
                WiFiClient cliente;
                HTTPClient http;
                http.setConnectTimeout(3000);
                http.setTimeout(QR_HTTP_TIMEOUT_MS);
                if (http.begin(cliente, QR_SERVER_URL)) {
                    http.addHeader("Content-Type", "image/jpeg");
                    int codigo = http.POST(foto->buf, foto->len);
                    esp_camera_fb_return(foto);
                    if (codigo > 0) {
                        ultimoStatus = codigo;
                        ultimoResultado = http.getString();
                    } else {
                        ultimoStatus = 502;
                        ultimoResultado = "Falha HTTP: " + HTTPClient::errorToString(codigo);
                    }
                    http.end();
                } else {
                    esp_camera_fb_return(foto);
                    ultimoStatus = 502;
                    ultimoResultado = "URL do servidor invalida.";
                }
            }
        }
    }

    Serial.printf("Leitura QR - HTTP %d: ", ultimoStatus);
    Serial.println(ultimoResultado);
    digitalWrite(QR_BUSY_PIN, LOW);
    // Exigir nova liberacao estavel apos cada operacao.
    gatilhoArmado = false;
    nivelGatilho = digitalRead(QR_TRIGGER_PIN);
    mudancaGatilho = millis();
}

void verificarGatilho() {
    int nivel = digitalRead(QR_TRIGGER_PIN);
    if (nivel != nivelGatilho) {
        nivelGatilho = nivel;
        mudancaGatilho = millis();
    }
    if (millis() - mudancaGatilho < QR_DEBOUNCE_MS) {
        return;
    }
    if (nivel == HIGH) {
        gatilhoArmado = true;
    } else if (gatilhoArmado) {
        lerQrCode();
    }
}

void desligarFlash() {

    pinMode(FLASH_GPIO_NUM, OUTPUT);

    digitalWrite(
        FLASH_GPIO_NUM,
        LOW
    );
}

void configurarSensorCamera() {

    sensor_t *sensor = esp_camera_sensor_get();

    if (!sensor) {

        Serial.println(
            "Nao foi possivel configurar o sensor."
        );

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

    Serial.println(
        "Sensor configurado para leitura de QR Code."
    );
}

void conectarWiFi() {

    Serial.println();
    Serial.println("========================");
    Serial.println("Conectando ao Wi-Fi...");
    Serial.println("========================");

    WiFi.mode(WIFI_STA);

    WiFi.begin(
        WIFI_NOME,
        WIFI_SENHA
    );

    while (WiFi.status() != WL_CONNECTED) {

        delay(500);
        Serial.print(".");
    }

    Serial.println();
    Serial.println("Wi-Fi conectado!");

    Serial.print("Endereco IP: ");
    Serial.println(WiFi.localIP());
    Serial.print("IP da ESP32: ");
    Serial.println(WiFi.localIP());

    Serial.print("Gateway: ");
    Serial.println(WiFi.gatewayIP());
}

bool iniciarCamera() {

    Serial.println();
    Serial.println("========================");
    Serial.println("Inicializando camera...");
    Serial.println("========================");

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

    esp_err_t resultado =
        esp_camera_init(&config);

    if (resultado != ESP_OK) {

        Serial.print(
            "Erro ao inicializar camera: 0x"
        );

        Serial.println(
            resultado,
            HEX
        );

        return false;
    }

    Serial.println(
        "Camera inicializada com sucesso!"
    );

    configurarSensorCamera();

    return true;
}

void paginaInicial() {

    String pagina = R"rawliteral(
<!DOCTYPE html>
<html>

<head>
    <meta charset="UTF-8">
    <title>Mini Fabrica Inteligente</title>
</head>

<body>

    <h1>Mini Fabrica Inteligente</h1>

    <h2>Grupo 3 - ESP32-CAM</h2>

    <p>
        Clique no botão abaixo para capturar uma imagem.
    </p>

    <button onclick="capturar()">
        Capturar imagem
    </button>
    <button id="ler" onclick="lerQr()">Ler QR Code</button>
    <pre id="resultado" aria-live="polite"></pre>

    <br><br>

    <img
        id="imagem"
        style="max-width: 640px;"
    >

    <script>

        async function atualizarResultado() {
            try {
                const resposta = await fetch('/result', {cache: 'no-store'});
                document.getElementById('resultado').textContent = await resposta.text();
            } catch (erro) {
                document.getElementById('resultado').textContent = 'ESP32-CAM indisponivel.';
            }
        }

        async function lerQr() {
            const botao = document.getElementById('ler');
            botao.disabled = true;
            document.getElementById('resultado').textContent = 'Processando...';
            try {
                const resposta = await fetch('/read', {method: 'POST'});
                document.getElementById('resultado').textContent = await resposta.text();
            } catch (erro) {
                document.getElementById('resultado').textContent = 'Falha de conexao.';
            } finally {
                botao.disabled = false;
            }
        }

        async function acompanhar() {
            if (!document.getElementById('ler').disabled) await atualizarResultado();
            setTimeout(acompanhar, 2000);
        }
        acompanhar();

        function capturar() {

            const imagem =
                document.getElementById("imagem");

            imagem.src =
                "/capture?t=" + new Date().getTime();
        }

    </script>

</body>

</html>
)rawliteral";

    server.send(
        200,
        "text/html",
        pagina
    );
}

void capturarImagem() {

    Serial.println();
    Serial.println("Solicitacao de captura recebida.");

    digitalWrite(QR_BUSY_PIN, HIGH);
    camera_fb_t *foto = obterFotoAtual();

    if (!foto) {

        Serial.println("Erro ao capturar imagem.");

        server.send(
            500,
            "text/plain",
            "Erro ao capturar imagem"
        );

        digitalWrite(QR_BUSY_PIN, LOW);
        return;
    }

    Serial.print("Nova imagem capturada: ");
    Serial.print(foto->len);
    Serial.println(" bytes");

    server.setContentLength(foto->len);

    server.send(
        200,
        "image/jpeg",
        ""
    );

    WiFiClient cliente = server.client();

    cliente.write(
        foto->buf,
        foto->len
    );

    esp_camera_fb_return(foto);
    digitalWrite(QR_BUSY_PIN, LOW);

    Serial.println(
        "Imagem atual enviada ao navegador."
    );
}

void setup() {

    Serial.begin(115200);

    pinMode(QR_TRIGGER_PIN, INPUT_PULLUP);
    digitalWrite(QR_BUSY_PIN, HIGH);
    pinMode(QR_BUSY_PIN, OUTPUT);

    desligarFlash();

    delay(2000);

    Serial.println();
    Serial.println(
        "=============================="
    );

    Serial.println(
        "Mini Fabrica Inteligente"
    );

    Serial.println(
        "Grupo 3 - ESP32-CAM"
    );

    Serial.println(
        "=============================="
    );


    conectarWiFi();


    cameraPronta = iniciarCamera();
    if (!cameraPronta) {

        Serial.println(
            "Falha critica na camera."
        );

        return;
    }

    server.on(
        "/",
        HTTP_GET,
        paginaInicial
    );

    server.on(
        "/capture",
        HTTP_GET,
        capturarImagem
    );

    server.on("/read", HTTP_POST, []() {
        lerQrCode();
        server.sendHeader("Cache-Control", "no-store");
        server.send(ultimoStatus, "text/plain; charset=utf-8", ultimoResultado);
    });
    server.on("/result", HTTP_GET, []() {
        server.sendHeader("Cache-Control", "no-store");
        server.send(200, "text/plain; charset=utf-8",
            String("HTTP ") + ultimoStatus + "\n" + ultimoResultado);
    });


    server.begin();
    digitalWrite(QR_BUSY_PIN, LOW);
    nivelGatilho = digitalRead(QR_TRIGGER_PIN);
    mudancaGatilho = millis();


    Serial.println();
    Serial.println(
        "Servidor iniciado!"
    );

    Serial.print(
        "Abra no navegador: http://"
    );

    Serial.println(
        WiFi.localIP()
    );
}

void loop() {

    server.handleClient();
    if (cameraPronta) {
        verificarGatilho();
    }

}
