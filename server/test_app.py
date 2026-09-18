import unittest

import cv2
import numpy as np

from app import app


def jpeg(imagem):
    ok, dados = cv2.imencode('.jpg', imagem)
    assert ok
    return dados.tobytes()


def qr(texto):
    imagem = cv2.QRCodeEncoder_create().encode(texto)
    imagem = cv2.copyMakeBorder(imagem, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
    return cv2.resize(imagem, None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST)


class LeituraQrTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def enviar(self, dados, tipo='image/jpeg'):
        return self.client.post('/api/qr', data=dados, content_type=tipo)

    def test_palavra(self):
        resposta = self.enviar(jpeg(qr('AZUL')))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json, {'ok': True, 'conteudo': 'AZUL'})

    def test_texto_preservado(self):
        texto = 'https://example.com/peca'
        self.assertEqual(self.enviar(jpeg(qr(texto))).json['conteudo'], texto)

    def test_rotacao(self):
        imagem = cv2.rotate(qr('VERDE'), cv2.ROTATE_90_CLOCKWISE)
        self.assertEqual(self.enviar(jpeg(imagem)).json['conteudo'], 'VERDE')

    def test_sem_qr(self):
        resposta = self.enviar(jpeg(np.full((480, 640), 255, np.uint8)))
        self.assertEqual(resposta.status_code, 422)
        self.assertFalse(resposta.json['ok'])
        self.assertIsNone(resposta.json['conteudo'])

    def test_dois_qrs(self):
        imagem = np.concatenate([qr('AZUL'), qr('VERDE')], axis=1)
        self.assertEqual(self.enviar(jpeg(imagem)).status_code, 422)

    def test_invalido(self):
        for dados in (b'', b'nao e imagem'):
            self.assertEqual(self.enviar(dados).status_code, 400)

    def test_tipo_incorreto(self):
        self.assertEqual(self.enviar(b'abc', 'text/plain').status_code, 415)

    def test_limite_bytes(self):
        self.assertEqual(self.enviar(b'x' * (2 * 1024 * 1024 + 1)).status_code, 413)

    def test_limite_resolucao(self):
        imagem = np.full((2100, 2100), 255, np.uint8)
        self.assertEqual(self.enviar(jpeg(imagem)).status_code, 413)

    def test_health(self):
        self.assertEqual(self.client.get('/health').json, {'ok': True})


if __name__ == '__main__':
    unittest.main()
