"""
Quick installation test script for Ironclaw
Run this to verify your installation is working correctly
"""
import sys
import importlib.util


def check_import(module_name: str) -> bool:
    """Check if a module can be imported."""
    spec = importlib.util.find_spec(module_name)
    return spec is not None


def main():
    print("=" * 60)
    print("Ironclaw Installation Test")
    print("=" * 60)
    print()
    
    # Check Python version
    print("1. Checking Python version...")
    version = sys.version_info
    if version.major == 3 and version.minor >= 11:
        print(f"   ✅ Python {version.major}.{version.minor}.{version.micro}")
    else:
        print(f"   ❌ Python {version.major}.{version.minor}.{version.micro}")
        print("   ERROR: Python 3.11+ required")
        return False
    
    # Check core dependencies
    print("\n2. Checking core dependencies...")
    dependencies = {
        "fastapi": "FastAPI web framework",
        "uvicorn": "ASGI server",
        "pydantic": "Data validation",
        "sqlalchemy": "Database ORM",
        "redis": "Cache client",
        "openai": "OpenAI SDK",
        "groq": "Groq SDK",
        "loguru": "Logging",
        "prometheus_client": "Metrics",
        "httpx": "HTTP client",
    }
    
    all_ok = True
    for module, description in dependencies.items():
        if check_import(module):
            print(f"   ✅ {module:20} ({description})")
        else:
            print(f"   ❌ {module:20} ({description})")
            all_ok = False
    
    if not all_ok:
        print("\n   ERROR: Missing dependencies. Run: pip install -e .")
        return False
    
    # Check project structure
    print("\n3. Checking project structure...")
    from pathlib import Path
    
    required_paths = [
        "src/api/main.py",
        "src/config.py",
        "src/database/connection.py",
        "src/cognitive/llm/router.py",
        "docker-compose.yml",
        ".env.example",
        "pyproject.toml",
    ]
    
    for path_str in required_paths:
        path = Path(path_str)
        if path.exists():
            print(f"   ✅ {path_str}")
        else:
            print(f"   ❌ {path_str}")
            all_ok = False
    
    if not all_ok:
        print("\n   ERROR: Project structure incomplete")
        return False
    
    # Check configuration
    print("\n4. Checking configuration...")
    env_file = Path(".env")
    if env_file.exists():
        print("   ✅ .env file exists")
        
        # Try to load config
        try:
            from src.config import settings
            print(f"   ✅ Configuration loaded")
            print(f"   - Environment: {settings.environment}")
            print(f"   - Available providers: {settings.available_ai_providers}")
            
            if not settings.available_ai_providers:
                print("   ⚠️  No AI providers configured (add API keys to .env)")
        except Exception as e:
            print(f"   ❌ Error loading config: {e}")
            all_ok = False
    else:
        print("   ⚠️  .env file not found (copy from .env.example)")
    
    # Summary
    print("\n" + "=" * 60)
    if all_ok:
        print("✅ Installation test PASSED")
        print()
        print("Next steps:")
        print("1. Edit .env and add your API keys")
        print("2. Start Docker: docker-compose up -d")
        print("3. Run server: python -m src.api.main")
        print("4. Visit: http://localhost:8000/docs")
    else:
        print("❌ Installation test FAILED")
        print()
        print("Please fix the errors above and try again.")
    print("=" * 60)
    
    return all_ok


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
