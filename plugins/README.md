# Ironclaw Plugins

This directory contains Ironclaw plugins. Each plugin is a self-contained module in its own directory.

## Plugin Structure

```
plugins/
├── plugin_name/
│   ├── __init__.py
│   └── plugin.py  (must contain a class inheriting from IPlugin)
```

## Available Plugins

### 1. Calculator (`calculator`)
Safe mathematical expression evaluator with support for common functions (sin, cos, sqrt, etc.)

**Usage:**
```python
{
  "plugin_name": "calculator",
  "parameters": {
    "expression": "2 + 2 * 3",
    "precision": 10
  }
}
```

### 2. Web Search (`web_search`)
DuckDuckGo-powered web search with caching and rate limiting.

**Usage:**
```python
{
  "plugin_name": "web_search",
  "parameters": {
    "query": "Python FastAPI tutorial",
    "max_results": 5
  }
}
```

### 3. File Operations (`file_ops`)
Safe file read/write/search operations within workspace.

**Usage:**
```python
{
  "plugin_name": "file_ops",
  "parameters": {
    "operation": "write",  # read, write, list, search, delete
    "path": "example.txt",
    "content": "Hello, Ironclaw!"
  }
}
```

### 4. Weather (`weather`)
OpenWeatherMap API integration for weather data.

**Configuration:** Set `OPENWEATHER_API_KEY` in .env

**Usage:**
```python
{
  "plugin_name": "weather",
  "parameters": {
    "location": "London,UK",
    "units": "metric"
  }
}
```

### 5. News (`news`)
NewsAPI integration for latest news articles.

**Configuration:** Set `NEWSAPI_KEY` in .env

**Usage:**
```python
{
  "plugin_name": "news",
  "parameters": {
    "mode": "headlines",  # or "search"
    "category": "technology",
    "country": "us"
  }
}
```

## Creating a New Plugin

1. Create a new directory in `plugins/` with your plugin name
2. Create `__init__.py` and `plugin.py` in the directory
3. In `plugin.py`, create a class that inherits from `IPlugin`:

```python
from src.plugins.base import IPlugin, PluginMetadata, PluginResult, PluginStatus

class MyPlugin(IPlugin):
    def __init__(self):
        metadata = PluginMetadata(
            name="my_plugin",
            version="1.0.0",
            description="My awesome plugin",
            max_execution_time_seconds=10,
            max_memory_mb=256,
        )
        super().__init__(metadata)

    async def execute(self, **kwargs):
        # Your plugin logic here
        return PluginResult(
            status=PluginStatus.SUCCESS,
            data={"result": "ok"}
        )

    async def validate(self, **kwargs):
        # Validate input parameters
        return True
```

4. Restart Ironclaw or use hot reload: `POST /api/v1/plugins/reload-all`

## API Endpoints

- `GET /api/v1/plugins` - List all plugins
- `GET /api/v1/plugins/{name}` - Get plugin info
- `POST /api/v1/plugins/{name}/execute` - Execute plugin
- `PUT /api/v1/plugins/{name}/enable` - Enable/disable plugin
- `POST /api/v1/plugins/{name}/reload` - Hot reload plugin
- `POST /api/v1/plugins/reload-all` - Reload all plugins

## Plugin Features

- **Sandbox Isolation**: Each plugin runs in a separate process with resource limits
- **Hot Reload**: Plugins can be reloaded without restarting the server
- **Automatic Backups**: Previous versions are backed up before reload
- **Resource Limits**: Memory, CPU, and timeout limits enforced
- **Security**: Path traversal protection, network restrictions, permission system

## Testing

Run plugin tests:
```bash
pytest tests/integration/phase_2/test_plugins.py -v
```
