import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import cv2
import numpy as np

import app as modulo_app
from app import QRInvalido, app, conectar_banco, parse_qr_payload


def jpeg(imagem):
    ok, dados = cv2.imencode('.jpg', imagem)
    assert ok
    return dados.tobytes()


def qr(texto):
    imagem = cv2.QRCodeEncoder_create().encode(texto)
    imagem = cv2.copyMakeBorder(
        imagem, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255
    )
    return cv2.resize(
        imagem, None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST
    )


class ParserIndustrialTest(unittest.TestCase):
    def test_aceita_exemplos_industriais(self):
        casos = [
            ('PECA;ENGRENAGEM;L-001;ACO;APROVADA', 'APROVADA'),
            ('PECA;TAMPA;L-002;PLASTICO;APROVADA', 'APROVADA'),
            ('PECA;EIXO;L-003;ALUMINIO;INSPECAO', 'INSPECAO'),
            ('PECA;ENGRENAGEM;L-004;AÇO;INSPEÇÃO', 'INSPECAO'),
        ]
        for texto, status in casos:
            with self.subTest(texto=texto):
                campos = parse_qr_payload(texto)
                self.assertEqual(campos['tipo'], 'PECA')
                self.assertEqual(campos['status'], status)

    def test_remove_espacos_dos_campos(self):
        campos = parse_qr_payload(
            ' PECA ; ENGRENAGEM ; L-001 ; AÇO ; APROVADA '
        )
        self.assertEqual(campos['nome_peca'], 'ENGRENAGEM')
        self.assertEqual(campos['material'], 'AÇO')

    def test_rejeita_payloads_invalidos(self):
        casos = [
            'texto comum',
            'PECA;TAMPA',
            'PECA;;L-001;ACO;APROVADA',
            'PECA;TAMPA;L-002;PLASTICO;APROVADA;EXTRA',
            ';ENGRENAGEM;L-001;ACO;APROVADA',
            'OUTRO;ENGRENAGEM;L-001;ACO;APROVADA',
            'PECA;ENGRENAGEM;L-001;ACO;DESCONHECIDA',
            f'PECA;{"X" * 81};L-001;ACO;APROVADA',
            'X' * 257,
        ]
        for texto in casos:
            with self.subTest(texto=texto):
                with self.assertRaises(QRInvalido):
                    parse_qr_payload(texto)


class LeituraQrApiTest(unittest.TestCase):
    def setUp(self):
        self.pasta_temporaria = tempfile.TemporaryDirectory()
        self.logger_desabilitado = app.logger.disabled
        app.logger.disabled = True
        app.config.update(
            TESTING=True,
            DATABASE=os.path.join(self.pasta_temporaria.name, 'teste.db'),
            DATABASE_TIMEOUT_SECONDS=0.1,
        )
        self.client = app.test_client()
        self.contador_operacao = 0

    def tearDown(self):
        app.logger.disabled = self.logger_desabilitado
        self.pasta_temporaria.cleanup()

    def enviar(self, dados, tipo='image/jpeg', operation_id=None):
        if operation_id is None:
            self.contador_operacao += 1
            operation_id = f'teste-{self.contador_operacao}'
        cabecalhos = {'X-Operation-Id': operation_id} if operation_id else {}
        return self.client.post(
            '/api/qr', data=dados, content_type=tipo, headers=cabecalhos
        )

    def enviar_qr(self, texto, operation_id=None):
        return self.enviar(jpeg(qr(texto)), operation_id=operation_id)

    def test_leitura_valida_salva_campos(self):
        texto = 'PECA;ENGRENAGEM;L-001;ACO;APROVADA'
        resposta = self.enviar_qr(texto, 'operacao-valida')
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json['id'], 1)
        self.assertEqual(resposta.json['operation_id'], 'operacao-valida')
        self.assertEqual(resposta.json['dado'], texto)
        self.assertEqual(resposta.json['nome_peca'], 'ENGRENAGEM')
        self.assertEqual(resposta.json['lote'], 'L-001')
        self.assertEqual(resposta.json['material'], 'ACO')
        self.assertEqual(resposta.json['status'], 'APROVADA')
        self.assertEqual(resposta.json['quantidade'], 1)
        self.assertFalse(resposta.json['duplicate'])
        self.assertIn('data_hora', resposta.json)

    def test_unicode_e_texto_original(self):
        texto = 'PECA;ENGRENAGEM;L-004;AÇO;INSPEÇÃO'
        resposta = self.enviar_qr(texto)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json['dado'], texto)
        self.assertEqual(resposta.json['material'], 'AÇO')
        self.assertEqual(resposta.json['status'], 'INSPECAO')

    def test_operation_id_ausente(self):
        resposta = self.client.post(
            '/api/qr', data=jpeg(qr('PECA;TAMPA;L-1;ACO;APROVADA')),
            content_type='image/jpeg',
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(resposta.json['erro'], 'operation_id_ausente')

    def test_operation_id_invalido(self):
        resposta = self.enviar_qr(
            'PECA;TAMPA;L-1;ACO;APROVADA', 'id com espaços'
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(resposta.json['erro'], 'operation_id_invalido')

    def test_retentativa_nao_duplica(self):
        texto = 'PECA;TAMPA;L-002;PLASTICO;APROVADA'
        primeira = self.enviar_qr(texto, 'mesma-operacao')
        segunda = self.enviar_qr(texto, 'mesma-operacao')
        self.assertEqual(primeira.status_code, 200)
        self.assertEqual(segunda.status_code, 200)
        self.assertEqual(primeira.json['id'], segunda.json['id'])
        self.assertFalse(primeira.json['duplicate'])
        self.assertTrue(segunda.json['duplicate'])
        self.assertEqual(self.client.get('/api/leituras').json['total'], 1)

    def test_quantidade_e_um_em_cada_evento(self):
        texto = 'PECA;TAMPA;L-002;PLASTICO;APROVADA'
        for operation_id in ('peca-1', 'peca-2', 'peca-3'):
            resposta = self.enviar_qr(texto, operation_id)
            self.assertEqual(resposta.json['quantidade'], 1)
        leituras = self.client.get('/api/leituras').json['leituras']
        self.assertEqual(sum(item['quantidade'] for item in leituras), 3)

    def test_qr_industrial_invalido_nao_e_salvo(self):
        for texto in (
            'texto comum', 'PECA;TAMPA', 'PECA;;L-1;ACO;APROVADA',
            'PECA;TAMPA;L-1;ACO;APROVADA;EXTRA',
        ):
            with self.subTest(texto=texto):
                resposta = self.enviar_qr(texto)
                self.assertEqual(resposta.status_code, 422)
                self.assertEqual(resposta.json['erro'], 'qr_invalido')
        self.assertEqual(self.client.get('/api/leituras').json['total'], 0)

    def test_sem_qr(self):
        imagem = np.full((480, 640), 255, np.uint8)
        resposta = self.enviar(jpeg(imagem))
        self.assertEqual(resposta.status_code, 422)
        self.assertEqual(resposta.json['erro'], 'qr_nao_encontrado')

    def test_multiplos_qrs(self):
        imagem = np.concatenate([
            qr('PECA;TAMPA;L-1;ACO;APROVADA'),
            qr('PECA;EIXO;L-2;ACO;APROVADA'),
        ], axis=1)
        resposta = self.enviar(jpeg(imagem))
        self.assertEqual(resposta.status_code, 422)
        self.assertEqual(resposta.json['erro'], 'multiplos_qrs')

    def test_imagem_vazia_e_bytes_invalidos(self):
        vazia = self.enviar(b'')
        invalida = self.enviar(b'nao e imagem')
        self.assertEqual(vazia.status_code, 400)
        self.assertEqual(vazia.json['erro'], 'imagem_vazia')
        self.assertEqual(invalida.status_code, 400)
        self.assertEqual(invalida.json['erro'], 'imagem_invalida')

    def test_tipo_incorreto(self):
        resposta = self.enviar(b'abc', 'text/plain')
        self.assertEqual(resposta.status_code, 415)
        self.assertEqual(resposta.json['erro'], 'tipo_de_midia_invalido')

    def test_limites_da_imagem(self):
        grande = self.client.post(
            '/api/qr', data=b'x' * (2 * 1024 * 1024 + 1),
            content_type='image/jpeg', headers={'X-Operation-Id': 'grande'},
        )
        resolucao = np.full((2100, 2100), 255, np.uint8)
        alta = self.enviar(jpeg(resolucao))
        self.assertEqual(grande.status_code, 413)
        self.assertEqual(alta.status_code, 413)

    def test_health_verifica_banco(self):
        resposta = self.client.get('/health')
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json['status'], 'ready')
        self.assertEqual(resposta.json['banco'], 'ready')

    def test_erros_de_rota_e_metodo_sao_json(self):
        inexistente = self.client.get('/api/inexistente')
        metodo = self.client.get('/api/qr')
        self.assertEqual(inexistente.status_code, 404)
        self.assertTrue(inexistente.is_json)
        self.assertEqual(metodo.status_code, 405)
        self.assertTrue(metodo.is_json)

    def test_limite_do_historico(self):
        self.assertEqual(
            self.client.get('/api/leituras?limite=0').status_code, 400
        )
        self.assertEqual(
            self.client.get('/api/leituras?limite=abc').status_code, 400
        )

    def test_resumo_agrega_peca_status_e_lote(self):
        self.enviar_qr('PECA;TAMPA;L-1;ACO;APROVADA', 'a-1')
        self.enviar_qr('PECA;TAMPA;L-1;ACO;REPROVADA', 'a-2')
        self.enviar_qr('PECA;EIXO;L-2;ACO;APROVADA', 'a-3')
        resumo = self.client.get('/api/resumo').json
        self.assertEqual(resumo['total_pecas'], 3)
        self.assertEqual(resumo['por_peca'][0], {
            'nome_peca': 'TAMPA', 'quantidade': 2,
        })
        self.assertEqual(resumo['por_status'][0], {
            'status': 'APROVADA', 'quantidade': 2,
        })
        self.assertEqual(resumo['por_lote'][0], {
            'lote': 'L-1', 'quantidade': 2,
        })
        self.assertEqual(len(resumo['leituras_recentes']), 3)

    def test_erro_de_banco_retorna_json_503(self):
        with patch.object(
            modulo_app, 'buscar_operacao',
            side_effect=sqlite3.OperationalError('database is locked'),
        ):
            resposta = self.enviar_qr(
                'PECA;TAMPA;L-1;ACO;APROVADA', 'banco-falha'
            )
        self.assertEqual(resposta.status_code, 503)
        self.assertTrue(resposta.is_json)
        self.assertEqual(resposta.json['erro'], 'banco_indisponivel')

    def test_falha_ao_abrir_banco_afeta_health_e_consultas(self):
        arquivo = os.path.join(self.pasta_temporaria.name, 'arquivo')
        with open(arquivo, 'w', encoding='utf-8') as destino:
            destino.write('não é uma pasta')
        app.config['DATABASE'] = os.path.join(arquivo, 'banco.db')
        for rota in ('/health', '/api/leituras', '/api/resumo'):
            with self.subTest(rota=rota):
                resposta = self.client.get(rota)
                self.assertEqual(resposta.status_code, 503)
                self.assertTrue(resposta.is_json)
                self.assertEqual(
                    resposta.json['erro'], 'banco_indisponivel'
                )

    def test_banco_bloqueado_na_gravacao(self):
        banco = conectar_banco()
        banco.execute('BEGIN IMMEDIATE')
        try:
            resposta = self.enviar_qr(
                'PECA;TAMPA;L-1;ACO;APROVADA', 'banco-bloqueado'
            )
        finally:
            banco.rollback()
            banco.close()
        self.assertEqual(resposta.status_code, 503)
        self.assertEqual(resposta.json['erro'], 'banco_indisponivel')


class BancoMigracaoConcorrenciaTest(unittest.TestCase):
    def setUp(self):
        self.pasta_temporaria = tempfile.TemporaryDirectory()
        self.caminho = os.path.join(self.pasta_temporaria.name, 'teste.db')
        app.config.update(
            TESTING=True,
            DATABASE=self.caminho,
            DATABASE_TIMEOUT_SECONDS=2.0,
        )

    def tearDown(self):
        self.pasta_temporaria.cleanup()

    def test_migra_banco_anterior_sem_perder_registros(self):
        banco = sqlite3.connect(self.caminho)
        banco.execute('''
            CREATE TABLE leituras_qr (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dado TEXT NOT NULL,
                data_hora TEXT NOT NULL,
                quantidade INTEGER NOT NULL
            )
        ''')
        banco.execute('''
            INSERT INTO leituras_qr (dado, data_hora, quantidade)
            VALUES (?, ?, 3)
        ''', ('PECA;EIXO;L-3;ALUMINIO;INSPECAO', '2026-09-30T08:00:00-03:00'))
        banco.commit()
        banco.close()

        migrado = conectar_banco()
        try:
            colunas = {
                linha['name']
                for linha in migrado.execute('PRAGMA table_info(leituras_qr)')
            }
            registro = migrado.execute(
                'SELECT * FROM leituras_qr'
            ).fetchone()
        finally:
            migrado.close()

        self.assertTrue({
            'operation_id', 'tipo', 'nome_peca', 'lote', 'material',
            'status', 'quantidade',
        }.issubset(colunas))
        self.assertEqual(registro['operation_id'], 'legacy-1')
        self.assertEqual(registro['nome_peca'], 'EIXO')
        self.assertEqual(registro['status'], 'INSPECAO')
        self.assertEqual(registro['quantidade'], 1)

    def test_gravacoes_concorrentes_nao_perdem_leituras(self):
        conectar_banco().close()

        def gravar(numero):
            texto = 'PECA;ENGRENAGEM;L-1;ACO;APROVADA'
            return modulo_app.registrar_leitura(
                f'concorrente-{numero}', texto, parse_qr_payload(texto)
            )

        with ThreadPoolExecutor(max_workers=4) as executor:
            registros = list(executor.map(gravar, range(20)))
        self.assertEqual(len({registro['id'] for registro in registros}), 20)
        self.assertEqual(
            len({registro['operation_id'] for registro in registros}), 20
        )
        self.assertTrue(all(registro['quantidade'] == 1 for registro in registros))
        banco = conectar_banco()
        try:
            total = banco.execute(
                'SELECT COUNT(*) FROM leituras_qr'
            ).fetchone()[0]
        finally:
            banco.close()
        self.assertEqual(total, 20)


if __name__ == '__main__':
    unittest.main()
