# Run from the repository root. This creates genuine staged commits from the supplied files.
git init
git add requirements.txt .gitignore .env.example app/config.py app/state.py
git commit -m "chore: scaffold project and settings"
git add app/github_client.py
git commit -m "feat: implement GitHub PR client"
git add app/sandbox.py
git commit -m "feat: add sandbox lint tool"
git add app/refactor.py
git commit -m "feat: implement LLM refactor service"
git add app/graph.py
git commit -m "feat: build LangGraph state machine"
git add app/main.py app/schemas.py main.py
git commit -m "feat: expose FastAPI endpoints and HITL gate"
git add tests
git commit -m "test: add graph and sandbox tests"
git add README.md openapi.json Dockerfile docker-compose.yml
git commit -m "docs: add OpenAPI and Docker support"
