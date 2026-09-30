#ifndef QR_CONFIG_H
#define QR_CONFIG_H

// Copie este arquivo para qr_config.h e informe o IP do computador.
// A ESP32-CAM e o computador devem estar na mesma rede.
constexpr const char *QR_SERVER_URL =
    "http://IP_DO_SERVIDOR:5000/api/qr";
constexpr int QR_TRIGGER_PIN = 13;
constexpr int QR_BUSY_PIN = 14;
constexpr uint32_t QR_DEBOUNCE_MS = 50;
constexpr uint32_t QR_SETTLE_MS = 150;
constexpr uint32_t QR_WIFI_CONNECT_TIMEOUT_MS = 20000;
constexpr uint32_t QR_WIFI_RETRY_INTERVAL_MS = 10000;
constexpr uint16_t QR_HTTP_CONNECT_TIMEOUT_MS = 3000;
constexpr uint16_t QR_HTTP_TIMEOUT_MS = 10000;
constexpr uint16_t QR_HTTP_RETRY_DELAY_MS = 500;
constexpr uint8_t QR_HTTP_MAX_RETRIES = 1;

#endif
