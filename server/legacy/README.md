# Implementações antigas

Esta pasta preserva protótipos produzidos durante o desenvolvimento. Eles não
fazem parte da arquitetura oficial e não devem ser iniciados junto com o projeto.

O servidor oficial é `../app.py`, escuta por padrão na porta 5000 e recebe as
imagens em `POST /api/qr`.

- `server_qr_banco.py` usa a rota antiga `/scan` e outro esquema SQLite.
- `integração BDD` é um protótipo Flask-SQLAlchemy com dependência e esquema
  próprios.
- `reconhecimento_qr.sql` pertence ao esquema do servidor antigo `/scan`.

Os arquivos foram mantidos apenas como histórico e possível referência para os
integrantes que os criaram. Alterações úteis devem ser incorporadas ao servidor
oficial com testes, sem executar estas versões em paralelo.
