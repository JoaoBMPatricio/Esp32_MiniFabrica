import io
import logging
import os

import cv2
import numpy as np
from flask import Flask, jsonify, request
from PIL import Image, UnidentifiedImageError
from waitress import serve

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024


def falha(mensagem, status):
    return jsonify(ok=False, erro=mensagem, conteudo=None), status


@app.errorhandler(413)
def imagem_grande(_erro):
    return falha('Imagem excede o limite de 2 MB.', 413)


@app.get('/health')
def health():
    return jsonify(ok=True)


@app.post('/api/qr')
def ler_qr():
    if request.mimetype != 'image/jpeg':
        return falha('Envie JPEG no corpo com Content-Type: image/jpeg.', 415)
    dados = request.get_data()
    if not dados:
        return falha('Imagem vazia.', 400)
    try:
        with Image.open(io.BytesIO(dados)) as cabecalho:
            if cabecalho.format != 'JPEG':
                return falha('O arquivo nao e JPEG.', 400)
            if cabecalho.width * cabecalho.height > 4_000_000:
                return falha('Resolucao excede 4 megapixels.', 413)
            cabecalho.verify()
        imagem = cv2.imdecode(np.frombuffer(dados, np.uint8), cv2.IMREAD_GRAYSCALE)
        if imagem is None:
            return falha('JPEG invalido.', 400)
        detector = cv2.QRCodeDetector()
        encontrou, textos, pontos, _ = detector.detectAndDecodeMulti(imagem)
        if pontos is not None and len(pontos) > 1:
            return falha('Mais de um QR Code na imagem.', 422)
        texto = textos[0] if encontrou and textos else ''
        if not texto:
            texto, _, _ = detector.detectAndDecode(imagem)
    except (UnidentifiedImageError, OSError, ValueError, cv2.error, Image.DecompressionBombError):
        return falha('Imagem invalida ou QR Code indecodificavel.', 400)
    if not texto:
        return falha('Nenhum QR Code legivel.', 422)
    if len(texto) > 256:
        return falha('Conteudo excede 256 caracteres.', 422)
    # Texto opaco: nao abrir links, executar comandos ou alterar a palavra.
    app.logger.info('QR lido: %r', texto)
    return jsonify(ok=True, conteudo=texto)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    serve(app, host=os.getenv('QR_HOST', '0.0.0.0'),
          port=int(os.getenv('QR_PORT', '5000')), threads=2)
