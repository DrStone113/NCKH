@echo off
cd /d "%~dp0"
title Setup Database
set PGPASSWORD=123
set PSQL="C:\Program Files\PostgreSQL\18\bin\psql.exe"
set INIT_SQL=%~dp0HealthApp\ai_backend\backend\db\init.sql

echo [1] Tao database va user...
%PSQL% -U postgres -c "CREATE DATABASE health_db;"
%PSQL% -U postgres -c "CREATE USER health WITH PASSWORD 'secret';"
%PSQL% -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE health_db TO health;"
%PSQL% -U postgres -d health_db -c "GRANT ALL ON SCHEMA public TO health;"
%PSQL% -U postgres -d health_db -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO health;"
%PSQL% -U postgres -d health_db -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO health;"

echo [2] Cai pgvector extension...
%PSQL% -U postgres -d health_db -c "CREATE EXTENSION IF NOT EXISTS vector;"

echo [3] Tao tables tu init.sql...
%PSQL% -U postgres -d health_db -f "%INIT_SQL%"

echo.
echo Done! Kiem tra:
%PSQL% -U postgres -d health_db -c "\dt"

pause
