#include <Arduino.h>
#include <WiFi.h>
#include "esp_camera.h"
#include "secrets.h"

// ==============================
// PINAGEM ESP32-CAM AI THINKER
// ==============================

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


// ==============================
// WIFI
// ==============================

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
}


// ==============================
// CAMERA
// ==============================

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

    // 640x480
    config.frame_size = FRAMESIZE_VGA;

    // Quanto menor, melhor a qualidade
    config.jpeg_quality = 10;

    config.fb_count = 1;

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

    return true;
}


// ==============================
// CAPTURA
// ==============================

void capturarFoto() {

    Serial.println();
    Serial.println("Capturando imagem...");

    camera_fb_t *foto =
        esp_camera_fb_get();

    if (!foto) {

        Serial.println(
            "ERRO: nao foi possivel capturar."
        );

        return;
    }

    Serial.println(
        "Imagem capturada!"
    );

    Serial.print(
        "Tamanho do JPEG: "
    );

    Serial.print(
        foto->len
    );

    Serial.println(
        " bytes"
    );

    esp_camera_fb_return(foto);

    Serial.println(
        "Memoria da imagem liberada."
    );
}


// ==============================
// SETUP
// ==============================

void setup() {

    Serial.begin(115200);

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


    if (!iniciarCamera()) {

        Serial.println(
            "Falha critica na camera."
        );

        return;
    }


    delay(2000);

    capturarFoto();
}


// ==============================
// LOOP
// ==============================

void loop() {

    delay(1000);
}