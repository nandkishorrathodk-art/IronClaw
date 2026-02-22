# Ironclaw Quick Start Guide ⚡

Get Ironclaw running in **5 minutes**!

---

## 🚀 Fast Setup (Windows)

### Step 1: Run Setup Script

```bash
# Double-click setup.bat or run in terminal:
setup.bat
```

This will:
- ✅ Create Python virtual environment
- ✅ Install all dependencies  
- ✅ Create `.env` file from template
- ✅ Start Docker services (PostgreSQL, Redis, Qdrant)

### Step 2: Add API Key

Open `.env` file and add **at least one** API key:

```bash
# Recommended: Groq (FREE, ultra-fast)
GROQ_API_KEY=gsk_your_key_here

# OR OpenAI (best quality)
OPENAI_API_KEY=sk-your_key_here
```

Get keys:
- **Groq** (FREE): https://console.groq.com/keys
- **OpenAI**: https://platform.openai.com/api-keys

### Step 3: Start Ironclaw

```bash
# Activate virtual environment
venv\Scripts\activate

# Start server
python -m src.api.main
```

Server starts at: **http://localhost:8000**

### Step 4: Test It!

Open browser to: **http://localhost:8000/docs**

Or test with curl:

```bash
curl -X POST http://localhost:8000/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -d "{\"messages\": [{\"role\": \"user\", \"content\": \"Hello!\"}]}"
```

---

## 🎯 Quick Examples

### 1. Simple Chat

```bash
curl -X POST http://localhost:8000/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "What is Python?"}],
    "task_type": "conversation"
  }'
```

### 2. Code Generation

```bash
curl -X POST http://localhost:8000/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Write a quicksort in Python"}],
    "task_type": "code_generation"
  }'
```

### 3. Stream Response

```bash
curl -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Tell me a story"}],
    "stream": true
  }'
```

### 4. Check Health

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/chat/providers/health
```

---

## 📊 Monitor Performance

- **API Docs**: http://localhost:8000/docs
- **Prometheus Metrics**: http://localhost:8000/metrics
- **Health Check**: http://localhost:8000/health

---

## 🔥 Pro Tips

### 1. Use Groq for Speed

Groq is **5-10x faster** than other providers and has a FREE tier:

```json
{
  "provider": "groq",
  "messages": [{"role": "user", "content": "Fast response!"}]
}
```

### 2. Let Router Decide

Don't specify provider - let the router choose based on task:

```json
{
  "task_type": "conversation",  // Router uses Groq (fast)
  "messages": [...]
}
```

```json
{
  "task_type": "code_generation",  // Router uses OpenAI (best)
  "messages": [...]
}
```

### 3. Control Costs

Set daily limits in `.env`:

```bash
ROUTER_MAX_COST_PER_DAY_USD=5.0
```

### 4. Optimize Performance

```bash
# For production
MAX_CONCURRENT_REQUESTS=100
API_WORKERS=4
DATABASE_POOL_SIZE=20
```

---

## ⚠️ Troubleshooting

### "No AI providers configured"

**Solution**: Add API key to `.env` file

### "Port 8000 already in use"

**Solution**: Change port in `.env`:
```bash
API_PORT=8001
```

### "Docker services not starting"

**Solution**: Check Docker Desktop is running:
```bash
docker-compose ps
docker-compose logs
```

### "Import errors"

**Solution**: Reinstall dependencies:
```bash
venv\Scripts\activate
pip install -e . --force-reinstall
```

---

## 📚 Next Steps

- **Full Documentation**: See [README.md](README.md)
- **API Reference**: http://localhost:8000/docs
- **Architecture**: See [docs/architecture.md](docs/architecture.md)
- **Contributing**: See [CONTRIBUTING.md](CONTRIBUTING.md)

---

## 🆘 Need Help?

- **GitHub Issues**: https://github.com/your-repo/ironclaw/issues
- **Documentation**: [README.md](README.md)

---

**Happy Building! 🚀**
