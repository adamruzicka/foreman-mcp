import contextlib
import logging
from collections.abc import AsyncIterator

import anyio
import apypie
import json
import click
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Mount, Route
from starlette.types import Receive, Scope, Send

from pydantic import AnyUrl
import httpx

logger = logging.getLogger(__name__)


@click.command()
@click.option("--port", default=3000, help="Port to listen on for HTTP")
@click.option(
    "--log-level",
    default="INFO",
    help="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
)
@click.option(
    "--json-response",
    is_flag=True,
    default=False,
    help="Enable JSON responses instead of SSE streams",
)
@click.option(
    "--foreman-url",
    help="Foreman URL to connect to",
)
@click.option(
    "--foreman-username",
    default="admin",
    help="Username for Foreman API authentication",
)
@click.option(
    "--foreman-password",
    default="changeme",
    help="Password for Foreman API authentication",
)
def main(
    port: int,
    log_level: str,
    json_response: bool,
    foreman_url: str,
    foreman_username: str,
    foreman_password: str,
) -> int:
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    app = Server("mcp-streamable-http-stateless-demo")
    foreman = apypie.ForemanApi(
        uri=foreman_url,
        username=foreman_username,
        password=foreman_password,
        verify_ssl=False
    )


    @app.call_tool()
    async def call_tool(
        name: str, arguments: dict
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        if name == 'list-all-report-templates':
            templates = foreman.resource_action('report_templates', 'index', {})
            lines = [f"Name: {t['name']}\nDescription: {t['description']}" for t in templates['results']]
            return [types.TextContent(type="text", text="\n\n".join(lines))]
        elif name == 'get-report-template':
            template_name = arguments.get("name")
            if not template_name:
                raise ValueError("Missing 'name' argument for get-report-template")

            # Find the template by name
            templates = foreman.resource_action('report_templates', 'index', {'search': f'name="{template_name}"'})
            results = templates.get('results', [])
            if not results:
                raise ValueError(f"Report template '{template_name}' not found")

            template_id = results[0]['id']
            template = foreman.resource_action('report_templates', 'show', {'id': template_id})

            return [
                types.TextContent(
                    type="text",
                    text=f"Name: {template['name']}\nDescription: {template.get('description', '')}\nTemplate:\n{template.get('template', '')}"
                )
            ]
        elif name == 'create-report-template':
            raise ValueError(f"Not implemented: {name}")
        elif name == 'get-report-templates-documentation':
            url = f"{foreman_url.rstrip('/')}/templates_doc/v1/reports.en.html"
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.get(url, auth=(foreman_username, foreman_password))
                response.raise_for_status()
            return [
                types.TextContent(
                    type="text",
                    text=response.text,
                )
            ]

    @app.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="render-report-template",
                description=("Renders a report template in Foreman and returns the result"),
                inputSchema={
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name of the report template to render"
                        }
                    }
                }
            ),
            types.Tool(
                name="create-report-template",
                description=("Creates a report template in Foreman"),
                inputSchema={
                    "type": "object",
                    "required": ["name", "template"],
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name of the report template to create"
                        },
                        "template": {
                            "type": "string",
                            "description": "Body of the report template to create"
                        },
                        "description": {
                            "type": "string",
                            "description": "Description of the report template to create"
                        },
                    }
                }
            ),
            types.Tool(
                name="get-report-template",
                description="Retrieves a specific report template by name from Foreman",
                inputSchema={
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name of the report template to retrieve"
                        }
                    }
                }
            ),
            types.Tool(
                name='list-all-report-templates',
                description="Retrieves the list of all available report templates in Foreman",
                inputSchema={
                    "type": "object"
                }
            ),
            types.Tool(
                name="get-report-templates-documentation",
                description="Retrieves the documentation for report templates from Foreman in HTML format",
                inputSchema={
                    "type": "object",
                }
            ),
        ]

    # Create the session manager with true stateless mode
    session_manager = StreamableHTTPSessionManager(
        app=app,
        event_store=None,
        json_response=json_response,
        stateless=True,
    )

    async def handle_streamable_http(
        scope: Scope, receive: Receive, send: Send
    ) -> None:
        await session_manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        """Context manager for session manager."""
        async with session_manager.run():
            logger.info("Application started with StreamableHTTP session manager!")
            try:
                yield
            finally:
                logger.info("Application shutting down...")

    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await app.run(
                streams[0], streams[1], app.create_initialization_options()
            )
        return Response()

    # Create an ASGI application using the transport
    starlette_app = Starlette(
        debug=True,
        routes=[
            Mount("/mcp", app=handle_streamable_http),
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message)
        ],
        lifespan=lifespan,
    )

    import uvicorn

    uvicorn.run(starlette_app, host="127.0.0.1", port=port)

    return 0
