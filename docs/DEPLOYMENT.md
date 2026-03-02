# Deployment Guide — GPU Server

Step-by-step instructions for deploying Metabase on the GPU server (`pockskllm01`).

---

## Prerequisites

Verify these are running on the server:

```bash
# Check Ollama is running with sqlcoder loaded
docker ps | grep ollama
docker exec -it ollama ollama list    # should show sqlcoder:latest

# Check rag-net network exists
docker network ls | grep rag-net
```

If `rag-net` doesn't exist:
```bash
docker network create rag-net
```

If Ollama isn't on `rag-net`:
```bash
docker network connect rag-net ollama
```

---

## Step 1: Stop the Old Application

```bash
docker stop sql-rag-api
docker rm sql-rag-api
```

Verify it's gone:
```bash
docker ps | grep sql-rag-api    # should return nothing
```

---

## Step 2: Transfer Code to Server

From your local machine:
```bash
# Option A: Git clone (if repo is pushed)
ssh root@pockskllm01
cd ~
git clone <your-repo-url> metabase
cd metabase

# Option B: SCP the project
scp -r /path/to/metabase root@pockskllm01:~/metabase
ssh root@pockskllm01
cd ~/metabase
```

---

## Step 3: Environment Configuration

No `.env` file is needed for Docker deployment. All config is in `docker-compose.yml`:

```yaml
environment:
  - LLM_BASE_URL=http://ollama:11434/v1   # Ollama container on rag-net
  - LLM_API_KEY=ollama                      # Ollama doesn't need a real key
  - LLM_MODEL=sqlcoder                      # Model name as shown in `ollama list`
```

**If you want to change the model**, edit `docker-compose.yml`:
```yaml
  - LLM_MODEL=devstral:24b    # Switch to larger model
```

**If Ollama is on a different port** (check `docker ps`):
```yaml
  - LLM_BASE_URL=http://ollama:11434/v1    # Default Ollama port inside container is always 11434
```

Note: Even if Ollama maps to port 11439 on the host, inside the Docker network it's always `11434`.

---

## Step 4: Build and Start

```bash
cd ~/metabase
docker compose up -d --build
```

This will:
1. Build the Docker image (~30 seconds)
2. Start the container on port 7999
3. Connect to the `rag-net` network
4. Volume mount `./app` for hot-reload

---

## Step 5: Verify Deployment

```bash
# Check container is running
docker ps | grep sql-rag-api

# Check health endpoint
curl http://localhost:7999/health
# Expected: {"status":"ok"}

# Test a query
curl -X POST http://localhost:7999/sqlgen \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "How many registrations in Dharwad?",
    "role_id": 1,
    "username": "LIDharwad@6"
  }'
```

Expected response:
```json
{
  "query": "How many registrations in Dharwad?",
  "type": "sql",
  "response": "SELECT COUNT(*) AS registration_count FROM dbo.registration_details_ksk_v2 WHERE district = 'DHARWAD' AND labour_inspector = N'LIDharwad@6'",
  "role": "Labour Inspector"
}
```

---

## Step 6: Check Logs

```bash
# Follow logs in real-time
docker compose logs -f sql-rag-api

# Last 50 lines
docker logs --tail 50 sql-rag-api
```

Healthy log output looks like:
```
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:7999
INFO:     sqlgen request | role=Labour Inspector user=LIDharwad@6
```

If you see `LLM request failed` or `Connection error`, Ollama is not reachable — check Step 7.

---

## Step 7: Troubleshooting

### LLM Connection Failed

```bash
# Verify Ollama is on rag-net
docker network inspect rag-net | grep -A5 ollama

# Test connectivity from inside the container
docker exec -it sql-rag-api curl http://ollama:11434/v1/models
```

If the curl fails, connect Ollama to the network:
```bash
docker network connect rag-net ollama
docker compose restart
```

### Container Won't Start

```bash
docker compose logs sql-rag-api    # Check for Python errors
docker compose down
docker compose up -d --build       # Force rebuild
```

### Model Not Found

```bash
# Check which models are loaded in Ollama
docker exec -it ollama ollama list

# Pull sqlcoder if missing
docker exec -it ollama ollama pull sqlcoder
```

### Port 7999 Already in Use

```bash
# Find what's using the port
lsof -i :7999

# Kill the old process or change port in docker-compose.yml
```

---

## Updating the Application

### Code changes (no rebuild needed)

Because of the volume mount (`./app:/app/app`), changes to any file in `app/` take effect immediately:

```bash
# Edit a file
vim app/prompt.py

# The running container picks up changes automatically
# (uvicorn hot-reload is not enabled in production, so restart the container)
docker compose restart
```

### Dependency changes (rebuild needed)

If you add packages to `requirements.txt`:

```bash
docker compose up -d --build
```

### Switch to a different LLM model

Edit `docker-compose.yml`:
```yaml
environment:
  - LLM_MODEL=devstral:24b    # or any model in `ollama list`
```

Then:
```bash
docker compose restart
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Start | `docker compose up -d` |
| Stop | `docker compose down` |
| Rebuild | `docker compose up -d --build` |
| Restart | `docker compose restart` |
| Logs | `docker compose logs -f sql-rag-api` |
| Health check | `curl http://localhost:7999/health` |
| Shell into container | `docker exec -it sql-rag-api bash` |
