README — Deploy e passos para colocar o agendamento em produção

Contexto
- Frontend (landing page) será hospedado em cPanel (HostGator) no domínio `cognitivatcc.com.br`.
- Backend (agendamento Google Calendar) deve ser hospedado onde Python, Postgres e Redis (opcional) sejam suportados (VPS HostGator, Render, Railway, DigitalOcean).

Arquivos adicionados neste repositório
- `Procfile` — arquivo para plataformas que usam Procfile (Render, Railway). Contém start command para `gunicorn`.
- Atualização em `requirements.txt` — adiciona `gunicorn`.
- `scripts/` — scripts auxiliares para empacotar frontend e aplicar migrations (ver abaixo).

Passos rápidos (resumido)
1. Publicar frontend no cPanel (zip/FTP) — ver seção "Frontend (cPanel)".
2. Provisionar backend em um host compatível (Render/HostGator VPS) — ver seção "Backend".
3. Configurar variáveis de ambiente no host do backend (veja lista em "Variáveis de ambiente").
4. Aplicar migrations Alembic e, se necessário, migrar tokens para encriptado.
5. Atualizar Google Cloud Console: Authorized redirect URI para `https://<BACKEND_DOMAIN>/calendar/callback`.

Frontend (cPanel) — passos detalhados
1. Localmente, gerar build do frontend:
   ```pwsh
   cd cognitiva_tcc
   npm install
   npm run build
   ```
   Isto criará a pasta `dist/` (Vite padrão).

2. Preparar `.htaccess` (roteamento SPA) — exemplo mínimo:
   ```apache
   <IfModule mod_rewrite.c>
     RewriteEngine On
     RewriteBase /
     RewriteCond %{REQUEST_FILENAME} !-f
     RewriteCond %{REQUEST_FILENAME} !-d
     RewriteRule ^ index.html [L,QSA]
   </IfModule>
   ```

3. Compactar `dist/` em ZIP e enviar via cPanel File Manager ou FTP para `public_html/`.
   - Se for subdomínio, envie para a pasta do subdomínio.

4. Ativar AutoSSL no cPanel e testar `https://cognitivatcc.com.br`.

Script auxiliar para Windows PowerShell (gera ZIP de `dist/`):
- `scripts/zip_dist.ps1` (fornecido neste repositório). Execute após `npm run build`.

Backend — recomendações e passos
1. Escolha do host: Render/Railway (fácil) ou VPS HostGator (mais controle). Shared cPanel NÃO é recomendado para o backend.
2. Criar instância/serviço e configurar variáveis de ambiente (não commitadas):
   - `DATABASE_URL` (Postgres recomendado)
   - `SECRET_KEY` (Flask secret)
   - `TOKEN_ENCRYPTION_KEY` (base64 urlsafe)
   - `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_AUTH_REDIRECT_URI` (ex.: `https://api.cognitivatcc.com.br/calendar/callback`)
   - `CORS_ORIGINS` (incluir `https://cognitivatcc.com.br`)
   - `REDIS_URL` (opcional)

3. Instalar dependências (no servidor):
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -U pip
   pip install -r requirements.txt
   ```

4. Aplicar migrations:
   ```bash
   export DATABASE_URL='postgresql://user:pass@host:5432/db'
   python3 migrations/run_alembic.py upgrade head
   ```

5. Migrar tokens legados (se houver):
   ```bash
   export TOKEN_ENCRYPTION_KEY='<sua-key-base64>'
   python3 migrations/migrate_tokens_to_encrypted.py
   ```

6. Iniciar app (exemplo com gunicorn/systemd):
   - `gunicorn main:app -w 4 -b 0.0.0.0:8000` (ou use o `Procfile` se for Render).

Variáveis de ambiente importantes (resumo)
- `DATABASE_URL`
- `SECRET_KEY`
- `TOKEN_ENCRYPTION_KEY`
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
- `GOOGLE_AUTH_REDIRECT_URI`
- `REDIS_URL` (opcional)
- `CORS_ORIGINS`

Scripts auxiliares incluídos
- `scripts/zip_dist.ps1` — PowerShell script para compactar a pasta `dist/` em `dist.zip`.
- `scripts/zip_dist.sh` — Bash equivalent.
- `scripts/run_migrations.sh` — helper para executar Alembic upgrade (Linux).
- `scripts/run_token_migration.sh` — helper para executar a migração de tokens (Linux).

Observações de segurança
- Nunca commit variáveis sensíveis.
- Rode backups completos antes de qualquer migration em produção.
- Guarde `TOKEN_ENCRYPTION_KEY` e `SECRET_KEY` em um cofre de segredos.

---
