# Development Guide - Agent Gateway

Guide for developers working on Phase 3 and beyond.

## Project Structure

```
gateway/
├── main.py                 # FastAPI app entry point
├── config.py              # Configuration loader
├── db.py                  # SQLAlchemy ORM & session management
├── models.py              # SQLAlchemy model definitions
├── schemas.py             # Pydantic request/response schemas
├── auth.py                # Authentication utilities (passwords, JWT)
├── logging_config.py      # Logging infrastructure
├── classifier.py          # Data classification (RED/YELLOW/GREEN)
├── queue.py               # Request queue (single-at-a-time)
├── audit.py               # Audit logging to SQLite
│
├── middleware_auth.py     # JWT middleware for protected routes
├── routes_auth.py         # Authentication endpoints
├── routes_chat.py         # Chat/inference endpoints
├── routes_audit.py        # Audit log query endpoints
│
├── providers/
│   ├── __init__.py        # Provider base class
│   ├── ollama.py          # Ollama provider (local Qwen)
│   └── claude.py          # Claude provider stub
│
├── scripts/
│   ├── wait-for-ollama.sh # Legacy Ollama health wait helper
│   └── check-phase3-runtime.sh # Host Ollama preflight
│
├── tests/
│   └── test_core.py       # Core unit tests
│
├── Dockerfile             # Docker image definition
├── docker-compose.yml     # Docker Compose orchestration
├── requirements.txt       # Python dependencies
├── config.yaml            # Configuration file (optional)
├── .env.example           # Environment template
├── README.md              # User-facing documentation
└── pyproject.toml         # Python project metadata
```

## Development Setup

### 1. Clone and Setup

```bash
cd gateway/
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment Variables

```bash
cp .env.example .env

# Edit .env with your settings
export $(cat .env | xargs)
```

### 3. Run Locally (without Docker)

```bash
# First, ensure Ollama is running:
# ollama serve

# In another terminal:
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Run Tests

```bash
pytest tests/ -v
# or with coverage:
pytest tests/ -v --cov=. --cov-report=html
```

## Key Modules

### auth.py
- `PasswordManager`: Argon2 password hashing and verification
- `TokenManager`: JWT token creation and verification
- Functions: `get_password_manager()`, `get_token_manager()`

### classifier.py
- `DataClassifier`: Pattern-based data classification
- `classify_data(text)`: Classify text as RED/YELLOW/GREEN
- Patterns loaded from `config.yaml`

### queue.py
- `InferenceQueue`: Manages single-at-a-time inference lock
- `acquire_inference_queue(request_id)`: Acquire queue slot
- `get_queue_depth()`, `get_current_request_id()`: Monitoring

### providers/
- `Provider` (base class): Abstract interface
- `OllamaProvider`: Async HTTP calls to Ollama
- `ClaudeProvider`: Stub for Phase 7+ Claude integration

## Common Tasks

### Adding a New Endpoint

1. Create route handler in `routes_*.py`:
   ```python
   @router.post("/new-endpoint")
   async def new_endpoint(
       user_id: int = Depends(get_current_user),
       db: Session = Depends(get_db),
   ):
       # Handler logic
       pass
   ```

2. Add schema to `schemas.py`:
   ```python
   class NewEndpointRequest(BaseModel):
       field1: str
   ```

3. Include router in `main.py`:
   ```python
   from routes_new import router as new_router
   app.include_router(new_router)
   ```

### Running Queries

```python
from db import SessionLocal
from models import User

db = SessionLocal()
users = db.query(User).filter(User.is_active == True).all()
db.close()
```

### Logging

```python
import logging

logger = logging.getLogger(__name__)
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")

# Audit logging:
from logging_config import audit_logger

await audit_logger.log_action(
    user_id=1,
    request_id="uuid",
    action="chat",
    result="success",
)
```

## Testing

### Unit Tests

Tests are in `tests/test_*.py`. Run with:

```bash
pytest tests/ -v
```

For the measured coverage gate:

```bash
pytest tests/ -q --cov=. --cov-report=term-missing
```

The 2026-08-30 verification run collected 101 tests with 88% application-only
coverage. `.coveragerc` excludes test code from that measurement; the focused
authentication modules measured 95%.

### Integration Tests

HTTP flow tests use FastAPI's test client and mock only system boundaries such
as Ollama and Claude. Provider resilience tests cover timeouts, refused
connections, retry limits, and model-specific timeouts. A live Ollama smoke
test remains part of host sign-off because it depends on the Phase 2 service.

### Manual Testing with curl

```bash
# Create user
curl -X POST http://localhost:8000/admin/setup/user \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "TestPassword123!"}'

# Login
TOKEN=$(curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "TestPassword123!"}' \
  | jq -r '.access_token')

# Chat
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello, what is your name?"}'
```

### Archiving expired audit events

The archive command uses `audit_logging.retention_days` and
`audit_logging.archive_path` from `config.yaml` unless overridden by the
corresponding environment settings:

```bash
python -m audit_archive
```

Schedule that command with cron/systemd for unattended retention. Each run
writes a timestamped `.jsonl.gz` archive atomically before deleting the archived
rows from SQLite.

## Database

### Schema

- `users`: User accounts
- `refresh_tokens`: Refresh tokens (7-day TTL)
- `audit_logs`: Action audit trail
- `model_config`: Model configuration and metadata

### Resetting Database

```python
from db import reset_db
reset_db()
```

## Docker Development

### Build Image

```bash
docker build -t agent-gateway:latest .
```

### Run Container

```bash
docker run --network host \
  -e GATEWAY_JWT_SECRET="your-secret-key-min-32-chars" \
  -v /data/ai-platform:/data/ai-platform \
  agent-gateway:latest
```

### Docker Compose

```bash
# Confirm host Ollama, port 8000, JWT secret, and Compose config
./scripts/check-phase3-runtime.sh

# Start the Gateway container
docker compose up --build -d gateway

# Check logs
docker compose logs -f gateway

# Stop services
docker compose down
```

## Debugging

### Enable Debug Logging

```bash
export GATEWAY_LOG_LEVEL=DEBUG
uvicorn main:app --reload
```

### Database Inspection

```bash
sqlite3 /data/ai-platform/gateway.db
> SELECT * FROM audit_logs LIMIT 10;
> .quit
```

### Trace Requests

Each request has a `request_id` (UUID). Search logs for this ID to trace end-to-end:

```bash
docker logs gateway | grep "req-uuid-12345"
```

## Performance Profiling

TODO: Add profiling with Pylance (Phase 3.5+)

```python
# Usage:
# from pylance_profiling import profile
# @profile
# async def my_handler(): ...
```

## Contributing

### Code Style

- Follow PEP 8
- Use type hints
- Write docstrings
- Keep functions under 50 lines

### Before Committing

1. Run tests: `pytest tests/ -v`
2. Format code: `black *.py`
3. Check imports: `isort --check-only *.py`
4. Lint: `flake8 --max-line-length=100 *.py`

```bash
# Auto-format all:
black *.py
isort *.py
```

### Git Workflow

1. Create feature branch: `git checkout -b feature/my-feature`
2. Make changes and commit
3. Push: `git push origin feature/my-feature`
4. Create PR (Phase 4+)

## Known Issues & TODOs

### Phase 3 (Current)

- [ ] Logout endpoint: Needs Phase 4 request context integration
- [ ] Approval cache: Currently in-memory (no persistence)
- [x] Retry logic: transient Ollama failures use bounded backoff
- [x] Error responses: stable envelopes include request IDs and retry guidance
- [x] Automated suite: 101 tests, 88% application-only coverage (2026-08-30)
- [ ] Live-host Ollama smoke and performance sign-off
- [x] Isolated HTTP/provider integration flows

### Phase 4+

- [ ] Web UI for login and chat
- [ ] Rate limiting and quotas
- [ ] Admin dashboard
- [ ] Permission scopes
- [ ] Two-factor authentication
- [ ] Multi-user workspace support

## Resources

- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [SQLAlchemy Docs](https://docs.sqlalchemy.org/)
- [PyJWT Docs](https://pyjwt.readthedocs.io/)
- [Argon2 Docs](https://argon2-cffi.readthedocs.io/)
- [Ollama API Docs](https://github.com/ollama/ollama/blob/main/docs/api.md)

## Getting Help

- Check existing issues in the repo
- Search logs for error messages and request IDs
- Review similar endpoints for patterns
- Consult [CONTEXT.md](../../CONTEXT.md) for architecture decisions

---

**Last Updated**: 2026-08-29  
**Phase**: 3  
**Version**: 3.0.0-dev
