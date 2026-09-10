#include <Arduino.h>
#include "esp_camera.h"

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


bool iniciarCamera() {

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

    config.frame_size = FRAMESIZE_VGA;

    config.jpeg_quality = 10;

    config.fb_count = 1;

    esp_err_t resultado =
        esp_camera_init(&config);

    if (resultado != ESP_OK) {

        Serial.printf(
            "Erro ao iniciar camera: 0x%x\n",
            resultado
        );

        return false;
    }

    Serial.println("Camera inicializada!");

    return true;
}

void capturarFoto() {

    Serial.println("Capturando...");

    camera_fb_t *foto =
        esp_camera_fb_get();

    if (!foto) {

        Serial.println(
            "Erro na captura!"
        );

        return;
    }

    Serial.print("Imagem capturada: ");

    Serial.print(foto->len);

    Serial.println(" bytes");

    esp_camera_fb_return(foto);
}


void setup() {

    Serial.begin(115200);

    delay(2000);

    Serial.println();
    Serial.println("Mini Fabrica - Grupo 3");

    if (!iniciarCamera()) {

        Serial.println("Falha na camera.");

        return;
    }

    Serial.println("OV2640 funcionando!");

    delay(2000);

    capturarFoto();
}


void loop() {

}