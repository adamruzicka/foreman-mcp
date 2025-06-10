# foreman-mcp-py

# How to run

## Using uv locally

```shell
# uv run foreman-mcp \
    --foreman-url https://my-foreman-instance.something.somewhere \
    --foreman-username $FOREMAN_USERNAME \
    --foreman-password $FOREMAN_PASSWORD \
    --log-level debug \
    --host localhost \
    --port 8080
```

## Using vscode

Example vscode config

```
# settings.json
{
    "mcp": {
        "servers": {
            "foreman-mcp-py": {
                "type": "sse",
                "url": "http://localhost:8080/mcp/sse",

            }
        }
    },
}
```

## Using container

First, build the container:

```
podman build -t foreman-mcp .
```

Now run the container:

```
podman run -it -p 8080:8080 foreman-mcp --foreman-url https://my-foreman-instance.something.somewhere --foreman-username $FOREMAN_USERNAME --foreman-password $FOREMAN_PASSWORD --log-level debug --port 8080 --host localhost
```

# Using MCP Inspector

For use with mcp inspector
1) Start the inspector with `npx @modelcontextprotocol/inspector`
2) Open `http://localhost:6274` in your browser
3) Set `Type` to `Streamable HTTP` and `URL` to `http://localhost:8080/mcp`
  - or set `Type` to `SSE` and `URL` to `http://localhost:8080/sse`
4) Click connect
