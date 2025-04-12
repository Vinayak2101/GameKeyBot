## Deployment
1. **Local Testing (Windows)**:
   - Install Python 3.9+ and PostgreSQL.
   - Create database: `createdb botdb`.
   - Set `.env` (see example).
   - Run: `python main.py`.
2. **Heroku**:
   - Push to Heroku: `git push heroku main`.
   - Set `.env` vars: `heroku config:set KEY=VALUE`.
   - Add Heroku Postgres: `heroku addons:create heroku-postgresql`.
   - Set webhook: Update `main.py` to call `setWebhook`.
3. **AWS/VPS**:
   - Install Python, PostgreSQL, Nginx.
   - Configure HTTPS with Let’s Encrypt.
   - Run as service with `gunicorn` or `uvicorn`.
