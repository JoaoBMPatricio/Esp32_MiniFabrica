import io
import logging
import os
import sqlite3
from contextlib import closing
from datetime import datetime

import cv2
import numpy as np
from flask import Flask, jsonify, request
from PIL import Image, UnidentifiedImageError
from waitress import serve

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024
app.config['DATABASE'] = os.getenv(
    'QR_DATABASE', os.path.join(os.path.dirname(__file__), 'leituras.db')
)


def conectar_banco():
    caminho = app.config['DATABASE']
    pasta = os.path.dirname(os.path.abspath(caminho))
    os.makedirs(pasta, exist_ok=True)
    banco = sqlite3.connect(caminho, timeout=5)
    banco.row_factory = sqlite3.Row
    banco.execute('PRAGMA journal_mode = WAL')
    banco.execute('''
        CREATE TABLE IF NOT EXISTS leituras_qr (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dado TEXT NOT NULL,
            data_hora TEXT NOT NULL,
            quantidade INTEGER NOT NULL CHECK (quantidade > 0)
        )
    ''')
    banco.execute(
        'CREATE INDEX IF NOT EXISTS idx_leituras_qr_dado '
        'ON leituras_qr (dado)'
    )
    return banco


def registrar_leitura(dado):
    data_hora = datetime.now().astimezone().isoformat(timespec='seconds')
    with closing(conectar_banco()) as banco:
        with banco:
            banco.execute('BEGIN IMMEDIATE')
            linha = banco.execute(
                'SELECT COALESCE(MAX(quantidade), 0) + 1 AS proxima '
                'FROM leituras_qr WHERE dado = ?',
                (dado,),
            ).fetchone()
            quantidade = linha['proxima']
            cursor = banco.execute(
                'INSERT INTO leituras_qr (dado, data_hora, quantidade) '
                'VALUES (?, ?, ?)',
                (dado, data_hora, quantidade),
            )
    return {
        'id': cursor.lastrowid,
        'dado': dado,
        'data_hora': data_hora,
        'quantidade': quantidade,
    }


def falha(mensagem, status):
    return jsonify(ok=False, erro=mensagem, conteudo=None), status


@app.errorhandler(413)
def imagem_grande(_erro):
    return falha('Imagem excede o limite de 2 MB.', 413)


@app.get('/health')
def health():
    return jsonify(ok=True)


@app.get('/api/leituras')
def listar_leituras():
    try:
        limite = int(request.args.get('limite', '50'))
    except ValueError:
        return falha('O limite deve ser um numero inteiro.', 400)
    if not 1 <= limite <= 200:
        return falha('O limite deve estar entre 1 e 200.', 400)
    with closing(conectar_banco()) as banco:
        linhas = banco.execute(
            'SELECT id, dado, data_hora, quantidade FROM leituras_qr '
            'ORDER BY id DESC LIMIT ?',
            (limite,),
        ).fetchall()
    leituras = [dict(linha) for linha in linhas]
    return jsonify(ok=True, total=len(leituras), leituras=leituras)


@app.get('/api/resumo')
def resumo():
    with closing(conectar_banco()) as banco:
        linhas = banco.execute('''
            SELECT dado, MAX(quantidade) AS quantidade,
                   MAX(data_hora) AS ultima_leitura
            FROM leituras_qr
            GROUP BY dado
            ORDER BY quantidade DESC, dado ASC
        ''').fetchall()
    return jsonify(ok=True, itens=[dict(linha) for linha in linhas])


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
    try:
        registro = registrar_leitura(texto)
    except sqlite3.Error:
        app.logger.exception('Falha ao registrar QR no banco de dados.')
        return falha('QR reconhecido, mas nao foi possivel salva-lo.', 503)
    app.logger.info('QR lido e salvo: %r (id=%d)', texto, registro['id'])
    return jsonify(ok=True, conteudo=texto, registro=registro)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    with closing(conectar_banco()):
        pass
    serve(app, host=os.getenv('QR_HOST', '0.0.0.0'),
          port=int(os.getenv('QR_PORT', '5000')), threads=2)
