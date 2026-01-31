Checklist de produção — calendar-api

Antes de executar qualquer migração em produção:

1. Backup completo do banco de dados
   - Faça um dump/export do banco (pg_dump para Postgres) e armazene em local seguro.

2. Verificar variáveis de ambiente
   - `DATABASE_URL` apontando para o banco Postgres de staging/produção.
   - `TOKEN_ENCRYPTION_KEY` definido (base64 urlsafe, 32 bytes antes da codificação).
   - `REDIS_URL` apontando para Redis para sessões (recomendado).
   - `SECRET_KEY` definido (flask secret para cookies).
   - `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET` definidos no ambiente.

3. Verificar dependências
   - Instalar pacotes do `requirements.txt` no ambiente virtual/contêiner.
     ```pwsh
     py -3 -m pip install -r requirements.txt
     ```

4. Aplicar migrações Alembic
   - Rodar as migrations apontando `DATABASE_URL` para Postgres:
     ```pwsh
     $env:DATABASE_URL = "postgresql://user:pass@host:5432/dbname"
     py -3 migrations/run_alembic.py upgrade head
     ```
   - Verifique que a revisão que adiciona a UniqueConstraint foi aplicada (revisões em `alembic/versions/`).

5. Migrar tokens para encriptados (se houver tokens antigos em texto claro)
   - Configure `TOKEN_ENCRYPTION_KEY` no ambiente com a chave segura.
   - O script cria um backup JSON antes de atualizar os registros.
     ```pwsh
     $env:TOKEN_ENCRYPTION_KEY = "<sua-key-base64>"
     py -3 migrations/migrate_tokens_to_encrypted.py
     ```
   - Verifique no banco que `token_encrypted` e `token_nonce` foram preenchidos.
   - Teste o fluxo de login/OAuth e a renovação de credenciais.

6. Testes pós-migração
   - Testar endpoints principais (/health, endpoints de agendamento) em staging.
   - Executar testes de concorrência se aplicável.

7. Limpeza pós-migração
   - Após validação, planejar remoção da coluna `token` (legacy) via Alembic revision separada.
   - Rotacionar quaisquer secrets que estiverem expostos e atualizar documentações.

8. Deploy
   - Assegurar HTTPS (TLS) ativo.
   - Setar variáveis de ambiente no ambiente de produção (não comitar).
   - Monitorar logs e métricas durante a janela de deploy.

Comandos úteis

- Gerar `TOKEN_ENCRYPTION_KEY` (exemplo Python):
  ```pwsh
  py -3 -c "import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
  ```

- Instalar dependências em user venv (Windows PowerShell):
  ```pwsh
  py -3 -m venv .venv
  . .venv/Scripts/Activate.ps1
  py -3 -m pip install -r requirements.txt
  ```

- Rodar migrações manualmente (alembic runner):
  ```pwsh
  $env:DATABASE_URL = "postgresql://user:pass@host:5432/dbname"
  py -3 migrations/run_alembic.py upgrade head
  ```

Observações

- Nunca execute o script de migração sem um backup completo.
- Teste tudo em um ambiente de staging antes de produção.
- Mantenha as chaves `TOKEN_ENCRYPTION_KEY` e `SECRET_KEY` em um cofre de segredos (Azure Key Vault, AWS Secrets Manager, HashiCorp Vault, etc.).
