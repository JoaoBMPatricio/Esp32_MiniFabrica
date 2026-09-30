import io
import logging
import os
import re
import sqlite3
from contextlib import contextmanager
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
app.config['DATABASE_TIMEOUT_SECONDS'] = 5.0

TAMANHO_MAXIMO_PAYLOAD = 256
LIMITES_CAMPOS = {
    'tipo': 16,
    'nome_peca': 80,
    'lote': 64,
    'material': 64,
    'status': 16,
}
STATUS_ACEITOS = {'APROVADA', 'REPROVADA', 'INSPECAO', 'INSPEÇÃO'}
OPERATION_ID_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$')
COLUNAS_MIGRACAO = {
    'operation_id': 'TEXT',
    'tipo': 'TEXT',
    'nome_peca': 'TEXT',
    'lote': 'TEXT',
    'material': 'TEXT',
    'status': 'TEXT',
    'quantidade': 'INTEGER NOT NULL DEFAULT 1',
}


class QRInvalido(ValueError):
    pass


def parse_qr_payload(texto):
    if not isinstance(texto, str) or not texto:
        raise QRInvalido('O QR Code está vazio.')
    if len(texto) > TAMANHO_MAXIMO_PAYLOAD:
        raise QRInvalido(
            f'O conteúdo excede {TAMANHO_MAXIMO_PAYLOAD} caracteres.'
        )
    if any(ord(caractere) < 32 for caractere in texto):
        raise QRInvalido('O QR Code contém caracteres de controle.')

    campos = [campo.strip() for campo in texto.split(';')]
    if len(campos) != 5:
        raise QRInvalido(
            'Use exatamente cinco campos: '
            'PECA;NOME_PECA;LOTE;MATERIAL;STATUS.'
        )
    if any(not campo for campo in campos):
        raise QRInvalido('Nenhum campo do QR Code pode ficar vazio.')

    tipo, nome_peca, lote, material, status = campos
    tipo = tipo.upper()
    status = status.upper()
    if tipo != 'PECA':
        raise QRInvalido('O primeiro campo deve ser PECA.')
    if status not in STATUS_ACEITOS:
        raise QRInvalido(
            'Status aceitos: APROVADA, REPROVADA ou INSPECAO.'
        )
    if status == 'INSPEÇÃO':
        status = 'INSPECAO'

    valores = {
        'tipo': tipo,
        'nome_peca': nome_peca,
        'lote': lote,
        'material': material,
        'status': status,
    }
    for nome, valor in valores.items():
        if len(valor) > LIMITES_CAMPOS[nome]:
            raise QRInvalido(
                f'O campo {nome} excede {LIMITES_CAMPOS[nome]} caracteres.'
            )
    return valores


def _agora():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def _preparar_banco(banco):
    espera_ms = int(float(app.config['DATABASE_TIMEOUT_SECONDS']) * 1000)
    banco.execute(f'PRAGMA busy_timeout = {espera_ms}')
    banco.execute('PRAGMA journal_mode = WAL')
    with banco:
        banco.execute('''
            CREATE TABLE IF NOT EXISTS leituras_qr (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_id TEXT NOT NULL UNIQUE,
                dado TEXT NOT NULL,
                tipo TEXT NOT NULL,
                nome_peca TEXT NOT NULL,
                lote TEXT NOT NULL,
                material TEXT NOT NULL,
                status TEXT NOT NULL,
                data_hora TEXT NOT NULL,
                quantidade INTEGER NOT NULL DEFAULT 1
                    CHECK (quantidade = 1)
            )
        ''')
        colunas = {
            linha['name']
            for linha in banco.execute('PRAGMA table_info(leituras_qr)')
        }
        precisa_migrar = (
            banco.execute('PRAGMA user_version').fetchone()[0] < 1
            or any(nome not in colunas for nome in COLUNAS_MIGRACAO)
        )
        for nome, definicao in COLUNAS_MIGRACAO.items():
            if nome not in colunas:
                banco.execute(
                    f'ALTER TABLE leituras_qr ADD COLUMN {nome} {definicao}'
                )

        if precisa_migrar:
            banco.execute('UPDATE leituras_qr SET quantidade = 1')
            banco.execute('''
                UPDATE leituras_qr
                SET operation_id = 'legacy-' || id
                WHERE operation_id IS NULL OR TRIM(operation_id) = ''
            ''')

            linhas = banco.execute('''
                SELECT id, dado FROM leituras_qr
                WHERE tipo IS NULL OR nome_peca IS NULL OR lote IS NULL
                   OR material IS NULL OR status IS NULL
            ''').fetchall()
            for linha in linhas:
                try:
                    campos = parse_qr_payload(linha['dado'])
                except QRInvalido:
                    continue
                banco.execute('''
                    UPDATE leituras_qr
                    SET tipo = ?, nome_peca = ?, lote = ?, material = ?,
                        status = ?
                    WHERE id = ?
                ''', (
                    campos['tipo'], campos['nome_peca'], campos['lote'],
                    campos['material'], campos['status'], linha['id'],
                ))

        indices = {
            linha['name']
            for linha in banco.execute("""
                SELECT name FROM sqlite_master
                WHERE type = 'index' AND tbl_name = 'leituras_qr'
            """)
        }
        if 'uq_leituras_operation_id' not in indices:
            banco.execute('''
                CREATE UNIQUE INDEX uq_leituras_operation_id
                ON leituras_qr (operation_id)
            ''')
        if 'idx_leituras_nome_peca' not in indices:
            banco.execute('''
                CREATE INDEX idx_leituras_nome_peca
                ON leituras_qr (nome_peca)
            ''')
        if 'idx_leituras_lote' not in indices:
            banco.execute('''
                CREATE INDEX idx_leituras_lote
                ON leituras_qr (lote)
            ''')
        if precisa_migrar:
            banco.execute('PRAGMA user_version = 1')


def conectar_banco():
    banco = None
    try:
        caminho = app.config['DATABASE']
        pasta = os.path.dirname(os.path.abspath(caminho))
        os.makedirs(pasta, exist_ok=True)
        banco = sqlite3.connect(
            caminho,
            timeout=float(app.config['DATABASE_TIMEOUT_SECONDS']),
        )
        banco.row_factory = sqlite3.Row
        _preparar_banco(banco)
        return banco
    except (OSError, sqlite3.Error):
        if banco is not None:
            banco.close()
        raise


@contextmanager
def conexao_banco():
    banco = conectar_banco()
    try:
        yield banco
    finally:
        banco.close()


def _registro_dict(linha, duplicate=False):
    registro = dict(linha)
    registro['duplicate'] = duplicate
    return registro


def buscar_operacao(operation_id):
    with conexao_banco() as banco:
        linha = banco.execute('''
            SELECT id, operation_id, dado, tipo, nome_peca, lote, material,
                   status, data_hora, quantidade
            FROM leituras_qr WHERE operation_id = ?
        ''', (operation_id,)).fetchone()
    return _registro_dict(linha, duplicate=True) if linha else None


def registrar_leitura(operation_id, dado, campos):
    with conexao_banco() as banco:
        with banco:
            banco.execute('BEGIN IMMEDIATE')
            existente = banco.execute('''
                SELECT id, operation_id, dado, tipo, nome_peca, lote, material,
                       status, data_hora, quantidade
                FROM leituras_qr WHERE operation_id = ?
            ''', (operation_id,)).fetchone()
            if existente:
                return _registro_dict(existente, duplicate=True)

            data_hora = _agora()
            cursor = banco.execute('''
                INSERT INTO leituras_qr (
                    operation_id, dado, tipo, nome_peca, lote, material,
                    status, data_hora, quantidade
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            ''', (
                operation_id, dado, campos['tipo'], campos['nome_peca'],
                campos['lote'], campos['material'], campos['status'], data_hora,
            ))
            linha = banco.execute('''
                SELECT id, operation_id, dado, tipo, nome_peca, lote, material,
                       status, data_hora, quantidade
                FROM leituras_qr WHERE id = ?
            ''', (cursor.lastrowid,)).fetchone()
    return _registro_dict(linha, duplicate=False)


def falha(erro, mensagem, http_status, **detalhes):
    resposta = {'ok': False, 'erro': erro, 'mensagem': mensagem}
    resposta.update(detalhes)
    return jsonify(resposta), http_status


def _operation_id():
    valor = request.headers.get('X-Operation-Id', '')
    if not valor:
        return None, falha(
            'operation_id_ausente',
            'Envie o identificador no cabeçalho X-Operation-Id.',
            400,
        )
    if not OPERATION_ID_RE.fullmatch(valor):
        return None, falha(
            'operation_id_invalido',
            'Use de 1 a 128 caracteres: letras, números, ponto, hífen, '
            'sublinhado ou dois-pontos.',
            400,
        )
    return valor, None


def _decodificar_qr(imagem):
    detector = cv2.QRCodeDetector()
    encontrou, textos, _pontos, _retificados = detector.detectAndDecodeMulti(
        imagem
    )
    legiveis = [texto for texto in textos if texto] if encontrou else []
    if len(legiveis) > 1:
        return None, 'multiplos_qrs'
    if len(legiveis) == 1:
        return legiveis[0], None
    texto, _pontos, _retificado = detector.detectAndDecode(imagem)
    return (texto, None) if texto else (None, 'qr_nao_encontrado')


@app.errorhandler(413)
def imagem_grande(_erro):
    return falha(
        'imagem_muito_grande', 'A imagem excede o limite de 2 MB.', 413
    )


@app.errorhandler(404)
def rota_inexistente(_erro):
    return falha('rota_inexistente', 'A rota solicitada não existe.', 404)


@app.errorhandler(405)
def metodo_invalido(_erro):
    return falha(
        'metodo_invalido', 'O método HTTP não é aceito nesta rota.', 405
    )


@app.errorhandler(Exception)
def erro_inesperado(erro):
    app.logger.exception('Erro inesperado na API.', exc_info=erro)
    return falha(
        'erro_interno', 'O servidor encontrou um erro inesperado.', 500
    )


@app.get('/health')
def health():
    try:
        with conexao_banco() as banco:
            banco.execute('SELECT 1 FROM leituras_qr LIMIT 1').fetchone()
    except (OSError, sqlite3.Error):
        app.logger.exception('Banco indisponível no health check.')
        return falha(
            'banco_indisponivel',
            'O processo está ativo, mas o banco SQLite não está acessível.',
            503,
            status='not_ready',
        )
    return jsonify(
        ok=True, status='ready', opencv=cv2.__version__, banco='ready'
    )


@app.get('/api/leituras')
def listar_leituras():
    try:
        limite = int(request.args.get('limite', '50'))
    except ValueError:
        return falha(
            'limite_invalido', 'O limite deve ser um número inteiro.', 400
        )
    if not 1 <= limite <= 200:
        return falha(
            'limite_invalido', 'O limite deve estar entre 1 e 200.', 400
        )
    try:
        with conexao_banco() as banco:
            total = banco.execute(
                'SELECT COUNT(*) FROM leituras_qr'
            ).fetchone()[0]
            linhas = banco.execute('''
                SELECT id, operation_id, dado, tipo, nome_peca, lote, material,
                       status, data_hora, quantidade
                FROM leituras_qr ORDER BY id DESC LIMIT ?
            ''', (limite,)).fetchall()
    except (OSError, sqlite3.Error):
        app.logger.exception('Falha ao consultar leituras.')
        return falha(
            'banco_indisponivel',
            'Não foi possível consultar as leituras.',
            503,
        )
    leituras = [dict(linha) for linha in linhas]
    return jsonify(
        ok=True, total=total, quantidade_retornada=len(leituras),
        leituras=leituras,
    )


@app.get('/api/resumo')
def resumo():
    try:
        with conexao_banco() as banco:
            total = banco.execute(
                'SELECT COALESCE(SUM(quantidade), 0) FROM leituras_qr'
            ).fetchone()[0]

            def agrupar(campo):
                linhas = banco.execute(f'''
                    SELECT {campo}, SUM(quantidade) AS quantidade
                    FROM leituras_qr
                    WHERE {campo} IS NOT NULL
                    GROUP BY {campo}
                    ORDER BY quantidade DESC, {campo} ASC
                ''').fetchall()
                return [dict(linha) for linha in linhas]

            recentes = banco.execute('''
                SELECT id, operation_id, dado, tipo, nome_peca, lote, material,
                       status, data_hora, quantidade
                FROM leituras_qr ORDER BY id DESC LIMIT 10
            ''').fetchall()
            por_peca = agrupar('nome_peca')
            por_status = agrupar('status')
            por_lote = agrupar('lote')
    except (OSError, sqlite3.Error):
        app.logger.exception('Falha ao gerar resumo.')
        return falha(
            'banco_indisponivel', 'Não foi possível gerar o resumo.', 503
        )
    return jsonify(
        ok=True,
        total_pecas=total,
        por_peca=por_peca,
        por_status=por_status,
        por_lote=por_lote,
        leituras_recentes=[dict(linha) for linha in recentes],
    )


@app.post('/api/qr')
def ler_qr():
    operation_id, erro_operation_id = _operation_id()
    if erro_operation_id:
        return erro_operation_id
    if request.mimetype != 'image/jpeg':
        return falha(
            'tipo_de_midia_invalido',
            'Envie JPEG no corpo com Content-Type: image/jpeg.',
            415,
        )

    try:
        existente = buscar_operacao(operation_id)
    except (OSError, sqlite3.Error):
        app.logger.exception('Falha ao consultar operation_id.')
        return falha(
            'banco_indisponivel', 'Não foi possível consultar o banco.', 503
        )
    if existente:
        return jsonify(ok=True, **existente)

    dados = request.get_data()
    if not dados:
        return falha('imagem_vazia', 'A requisição não contém uma imagem.', 400)
    try:
        with Image.open(io.BytesIO(dados)) as cabecalho:
            if cabecalho.format != 'JPEG':
                return falha(
                    'imagem_invalida', 'O conteúdo enviado não é JPEG.', 400
                )
            if cabecalho.width * cabecalho.height > 4_000_000:
                return falha(
                    'imagem_muito_grande',
                    'A resolução excede 4 megapixels.',
                    413,
                )
            cabecalho.verify()
        imagem = cv2.imdecode(
            np.frombuffer(dados, np.uint8), cv2.IMREAD_GRAYSCALE
        )
        if imagem is None:
            return falha(
                'imagem_invalida',
                'Não foi possível decodificar a imagem.',
                400,
            )
        texto, erro_qr = _decodificar_qr(imagem)
    except (
        UnidentifiedImageError, OSError, ValueError, cv2.error,
        Image.DecompressionBombError,
    ):
        return falha(
            'imagem_invalida', 'Não foi possível decodificar a imagem.', 400
        )

    if erro_qr == 'multiplos_qrs':
        return falha(
            'multiplos_qrs',
            'Posicione apenas uma peça com QR Code por captura.',
            422,
        )
    if erro_qr:
        return falha(
            'qr_nao_encontrado', 'Nenhum QR Code foi encontrado.', 422
        )

    try:
        campos = parse_qr_payload(texto)
    except QRInvalido as erro:
        return falha('qr_invalido', str(erro), 422)

    try:
        registro = registrar_leitura(operation_id, texto, campos)
    except (OSError, sqlite3.Error):
        app.logger.exception('Falha ao registrar QR no banco de dados.')
        return falha(
            'banco_indisponivel', 'Não foi possível salvar a leitura.', 503
        )
    app.logger.info(
        'QR salvo: %r (id=%d, operation_id=%s, duplicate=%s)',
        texto, registro['id'], operation_id, registro['duplicate'],
    )
    return jsonify(ok=True, **registro)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    try:
        with conexao_banco():
            pass
    except (OSError, sqlite3.Error) as erro:
        raise SystemExit(f'Não foi possível inicializar o banco: {erro}')
    serve(
        app,
        host=os.getenv('QR_HOST', '0.0.0.0'),
        port=int(os.getenv('QR_PORT', '5000')),
        threads=4,
    )
