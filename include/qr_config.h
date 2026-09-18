#pragma once

// IP do computador na mesma rede da ESP32-CAM; nao usar localhost.
constexpr const char *QR_SERVER_URL = "http://192.168.0.189:5000/api/qr";
constexpr int QR_TRIGGER_PIN = 13;
constexpr int QR_BUSY_PIN = 14;
constexpr uint32_t QR_DEBOUNCE_MS = 50;
constexpr uint32_t QR_SETTLE_MS = 150;
constexpr uint16_t QR_HTTP_TIMEOUT_MS = 10000;
