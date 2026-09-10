#include <Arduino.h>
#include <WiFi.h>
#include "secrets.h"

void conectarWiFi() {
    Serial.println();
    Serial.println("========================");
    Serial.println("Conectando ao Wi-Fi...");
    Serial.println("========================");

    WiFi.mode(WIFI_STA);

    WiFi.begin(WIFI_NOME, WIFI_SENHA);

    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }

    Serial.println();
    Serial.println("Wi-Fi conectado!");

    Serial.print("Endereco IP: ");
    Serial.println(WiFi.localIP());

    Serial.print("Sinal Wi-Fi: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");
}

void setup() {
    Serial.begin(115200);

    delay(2000);

    Serial.println();
    Serial.println("Mini Fabrica Inteligente");
    Serial.println("Grupo 3 - ESP32-CAM");

    conectarWiFi();
}

void loop() {
    delay(1000);
}