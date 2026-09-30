from flask import Flask, request, jsonify
import sqlite3
from datetime import datetime
import cv2
import numpy as np

app = Flask(__name__)

DB_NAME = "reconhecimento.db"


def criar_banco():
    """Cria a tabela caso ela ainda não exista."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reconhecimento_qr (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hora TEXT NOT NULL,
            codigo_qr TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def salvar_qr(codigo_qr):
    """Salva o QR Code reconhecido no SQLite."""
    hora = datetime.now().strftime("%H:%M:%S")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO reconhecimento_qr (hora, codigo_qr)
        VALUES (?, ?)
    """, (hora, codigo_qr))

    conn.commit()
    id_registro = cursor.lastrowid
    conn.close()

    return id_registro, hora


def ler_qr_da_imagem(imagem):
    """Tenta ler um ou mais QR Codes usando OpenCV."""
    detector = cv2.QRCodeDetector()

    # Primeiro tenta detectar vários QR Codes.
    try:
        resultado, pontos, _ = detector.detectAndDecodeMulti(imagem)

        if resultado:
            codigos = [codigo for codigo in resultado if codigo]
            if codigos:
                return codigos
    except Exception:
        pass

    # Se não funcionar, tenta um único QR Code.
    codigo, _, _ = detector.detectAndDecode(imagem)

    if codigo:
        return [codigo]

    return []


@app.route("/", methods=["GET"])
def inicio():
    return jsonify({
        "status": "ok",
        "mensagem": "Servidor de reconhecimento de QR Code funcionando."
    })


@app.route("/scan", methods=["POST"])
def scan():
    """
    Recebe uma imagem JPEG/PNG e:
    1. lê o QR Code;
    2. salva o código no SQLite;
    3. retorna o resultado em JSON.

    Pode receber:
    - multipart/form-data com o campo 'image'
    - imagem diretamente no corpo da requisição
    """

    try:
        # Opção 1: ESP32 envia multipart/form-data
        if "image" in request.files:
            arquivo = request.files["image"]
            dados = arquivo.read()

        # Opção 2: ESP32 envia a imagem diretamente no body
        else:
            dados = request.get_data()

        if not dados:
            return jsonify({
                "sucesso": False,
                "erro": "Nenhuma imagem foi enviada."
            }), 400

        imagem_array = np.frombuffer(dados, dtype=np.uint8)
        imagem = cv2.imdecode(imagem_array, cv2.IMREAD_COLOR)

        if imagem is None:
            return jsonify({
                "sucesso": False,
                "erro": "A imagem enviada não pôde ser aberta."
            }), 400

        codigos = ler_qr_da_imagem(imagem)

        if not codigos:
            return jsonify({
                "sucesso": False,
                "mensagem": "Nenhum QR Code foi reconhecido."
            }), 200

        registros = []

        for codigo in codigos:
            id_registro, hora = salvar_qr(codigo)

            registros.append({
                "id": id_registro,
                "hora": hora,
                "codigo_qr": codigo
            })

        return jsonify({
            "sucesso": True,
            "quantidade": len(registros),
            "registros": registros
        }), 200

    except Exception as erro:
        return jsonify({
            "sucesso": False,
            "erro": str(erro)
        }), 500


if __name__ == "__main__":
    criar_banco()

    print("==============================================")
    print(" Mini Fábrica - Servidor de QR Code")
    print("==============================================")
    print("Banco: reconhecimento.db")
    print("Tabela: reconhecimento_qr")
    print("Endpoint: POST /scan")
    print("Servidor: http://0.0.0.0:5000")
    print("==============================================")

    app.run(host="0.0.0.0", port=5000, debug=False)
