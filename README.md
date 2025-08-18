# Deep Research API

A powerful AI-driven research API that conducts comprehensive research using multi-agent workflows with Google's Gemini models or Ollama (local LLM). The system generates research questions, searches the web for answers, compiles detailed reports, and iteratively improves them through review cycles.

## 🚀 Features

- **Multi-Agent Workflow**: Specialized AI agents for question generation, research, reporting, and review
- **Real-time Updates**: WebSocket support for live progress tracking
- **Web Search Integration**: Powered by Google's Genai API with search capabilities
- **Session Management**: Track multiple research sessions with automatic cleanup
- **Production Ready**: Docker support, structured logging, health checks
- **Optimized Performance**: Agent pooling, error handling, timeout management

## 📋 Prerequisites

- **Python 3.11+** (for local development)
- **Docker & Docker Compose** (recommended)
- **LLM Provider**: Choose one:
  - **Google GenAI API Key** - Get one from [Google AI Studio](https://makersuite.google.com/app/apikey)
  - **Ollama** - Local LLM runtime for privacy-focused deployment

## 🛠️ Quick Start

### Option 1: Docker (Recommended)

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd deepsearch-api
   ```

2. **Set up environment**
   ```bash
   cp .env.example .env
   # Edit .env and configure your LLM provider (see Configuration section)
   ```

3. **Run with Docker**
   ```bash
   docker-compose up --build
   ```

4. **Access the API**
   - API: http://localhost:8000
   - Health Check: http://localhost:8000/health
   - API Docs: http://localhost:8000/docs

### Option 2: Local Development

1. **Clone and setup**
   ```bash
   git clone <repository-url>
   cd deepsearch-api
   cp .env.example .env
   # Edit .env with your LLM provider configuration
   ```

2. **Install dependencies**
   ```bash
   cd app
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   python main.py
   # Or: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

## 🔧 Configuration

### Environment Variables

Create a `.env` file in the project root. The system supports both Google GenAI and Ollama as LLM providers:

#### Option 1: Google GenAI (default)
```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_google_genai_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

#### Option 2: Ollama (local LLM)
```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gpt-oss:20b
OLLAMA_REQUEST_TIMEOUT=120.0
OLLAMA_CONTEXT_WINDOW=8000
```

**Note:** When using Ollama, ensure you have:
1. Ollama installed and running locally
2. The desired model pulled (e.g., `ollama pull gpt-oss:20b`)
3. The llama-index-llms-ollama package installed: `pip install llama-index-llms-ollama`

#### Additional Configuration (Optional)
```env
# Server Settings
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO
DEFAULT_TIMEOUT=300
DEFAULT_MAX_REVIEW_CYCLES=3
MAX_CONCURRENT_SESSIONS=10

# CORS Settings
CORS_ORIGINS=http://localhost:3000,http://localhost:8080
CORS_ALLOW_CREDENTIALS=true
```

## 📚 API Usage

### Start a Research Session

```bash
curl -X POST "http://localhost:8000/research/start" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Impact of artificial intelligence on modern education",
    "max_review_cycles": 3,
    "timeout": 300
  }'
```

**Response:**
```json
{
  "session_id": "uuid-here",
  "status": "started",
  "message": "Research session started for topic: Impact of artificial intelligence on modern education"
}
```

### Check Session Status

```bash
curl "http://localhost:8000/research/{session_id}/status"
```

### Get Research Result

```bash
curl "http://localhost:8000/research/{session_id}/result"
```

### Cancel Session

```bash
curl -X DELETE "http://localhost:8000/research/{session_id}"
```

### WebSocket for Real-time Updates

```javascript
const ws = new WebSocket(`ws://localhost:8000/research/${sessionId}/ws`);

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log('Progress:', data);
};
```

## 🐍 Python Client Example

```python
import asyncio
from client_example import ResearchAPIClient

async def main():
    client = ResearchAPIClient("http://localhost:8000")

    # Start research
    session_id = await client.start_research(
        topic="History of quantum computing",
        max_review_cycles=2
    )

    # Stream progress
    async def progress_callback(data):
        if data['type'] == 'completed':
            print("Research completed!")
            print(f"Result: {data['result']}")

    await client.stream_progress(session_id, progress_callback)

if __name__ == "__main__":
    asyncio.run(main())
```

## 🚀 Production Deployment

### Using Docker Compose

```bash
# Build and run production setup
docker-compose -f docker-compose.prod.yml up --build

# With Nginx reverse proxy
docker-compose -f docker-compose.prod.yml --profile production up
```

## 🔍 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/research/start` | Start new research session |
| `GET` | `/research/{session_id}/status` | Get session status |
| `GET` | `/research/{session_id}/result` | Get research result |
| `DELETE` | `/research/{session_id}` | Cancel session |
| `GET` | `/research/sessions` | List all sessions |
| `WS` | `/research/{session_id}/ws` | WebSocket for real-time updates |
| `GET` | `/health` | Health check endpoint |
| `GET` | `/docs` | Interactive API documentation |

## 🐛 Troubleshooting

### Common Issues

1. **"Invalid API key" error** (Google GenAI)
   - Verify your `GEMINI_API_KEY` in the `.env` file
   - Ensure the API key has proper permissions

2. **Ollama connection issues**
   - Ensure Ollama is running: `ollama serve`
   - Verify the model is available: `ollama list`
   - Check `OLLAMA_BASE_URL` matches your Ollama instance

3. **Port 8000 already in use**
   ```bash
   # Change port in .env file or use different port
   docker-compose up --build -p 8001:8000
   ```

4. **WebSocket connection fails**
   - Check firewall settings
   - Ensure WebSocket support in your client

5. **Research timeout**
   - Increase `DEFAULT_TIMEOUT` in `.env`
   - Check internet connection for web search
