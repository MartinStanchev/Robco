"""Tests for the MCP tool server, display tools, and camera tools (Phase 4)."""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path

import pytest

from src.hardware.stubs import StubCameraInput, StubDisplayOutput
from src.tools.camera import create_camera_tools
from src.tools.display import create_display_tools
from src.tools.server import ToolDefinition, ToolParam, ToolServer

FIXTURES = Path(__file__).parent / "fixtures"
TEST_IMAGE = FIXTURES / "test_image.jpg"


# ---------------------------------------------------------------------------
# ToolParam and ToolDefinition
# ---------------------------------------------------------------------------


class TestToolDefinition:
    def test_tool_param_frozen(self) -> None:
        param = ToolParam(type="string", description="test")
        assert param.type == "string"
        assert param.required is True

    def test_tool_param_optional(self) -> None:
        param = ToolParam(type="integer", description="count", required=False)
        assert not param.required

    def test_tool_definition_defaults(self) -> None:
        tool = ToolDefinition(name="test", description="A test tool")
        assert tool.parameters == {}
        assert tool.handler() == {}

    def test_tool_definition_with_params(self) -> None:
        tool = ToolDefinition(
            name="greet",
            description="Say hello",
            parameters={"name": ToolParam(type="string", description="Name")},
            handler=lambda name: {"greeting": f"Hello {name}"},
        )
        assert "name" in tool.parameters
        result = tool.handler(name="World")
        assert result == {"greeting": "Hello World"}


# ---------------------------------------------------------------------------
# ToolServer — registration and execution
# ---------------------------------------------------------------------------


class TestToolServerRegistration:
    def test_empty_server(self) -> None:
        server = ToolServer()
        assert server.registered_tools == []

    def test_register_tool(self) -> None:
        server = ToolServer()
        tool = ToolDefinition(name="test", description="Test tool")
        server.register_tool(tool)
        assert "test" in server.registered_tools

    def test_register_multiple_tools(self) -> None:
        server = ToolServer()
        server.register_tool(ToolDefinition(name="a", description="Tool A"))
        server.register_tool(ToolDefinition(name="b", description="Tool B"))
        assert sorted(server.registered_tools) == ["a", "b"]

    def test_register_overwrites_duplicate(self) -> None:
        server = ToolServer()
        server.register_tool(
            ToolDefinition(name="test", description="V1", handler=lambda: {"v": 1})
        )
        server.register_tool(
            ToolDefinition(name="test", description="V2", handler=lambda: {"v": 2})
        )
        assert len(server.registered_tools) == 1


class TestToolServerExecution:
    async def test_execute_sync_tool(self) -> None:
        server = ToolServer()
        server.register_tool(
            ToolDefinition(
                name="add",
                description="Add numbers",
                parameters={
                    "a": ToolParam(type="integer", description="First"),
                    "b": ToolParam(type="integer", description="Second"),
                },
                handler=lambda a, b: {"sum": a + b},
            )
        )
        result = await server.execute_tool("add", {"a": 3, "b": 4})
        assert result == {"sum": 7}

    async def test_execute_async_tool(self) -> None:
        async def async_handler(text: str) -> dict:
            return {"echoed": text}

        server = ToolServer()
        server.register_tool(
            ToolDefinition(
                name="echo",
                description="Echo text",
                parameters={"text": ToolParam(type="string", description="Input")},
                handler=async_handler,
            )
        )
        result = await server.execute_tool("echo", {"text": "hello"})
        assert result == {"echoed": "hello"}

    async def test_execute_unknown_tool(self) -> None:
        server = ToolServer()
        result = await server.execute_tool("nonexistent", {})
        assert "error" in result
        assert "Unknown tool" in result["error"]

    async def test_execute_tool_with_error(self) -> None:
        def bad_handler() -> dict:
            raise ValueError("something went wrong")

        server = ToolServer()
        server.register_tool(
            ToolDefinition(name="bad", description="Breaks", handler=bad_handler)
        )
        result = await server.execute_tool("bad", {})
        assert "error" in result
        assert "something went wrong" in result["error"]

    async def test_execute_tool_non_dict_result(self) -> None:
        server = ToolServer()
        server.register_tool(
            ToolDefinition(
                name="stringify",
                description="Returns a string",
                handler=lambda: "just a string",
            )
        )
        result = await server.execute_tool("stringify", {})
        assert result == {"result": "just a string"}


# ---------------------------------------------------------------------------
# ToolServer — declarations
# ---------------------------------------------------------------------------


class TestToolServerDeclarations:
    def test_no_tools_returns_none(self) -> None:
        server = ToolServer()
        assert server.get_tool_declarations() is None

    def test_tool_with_params(self) -> None:
        server = ToolServer()
        server.register_tool(
            ToolDefinition(
                name="greet",
                description="Say hello",
                parameters={
                    "name": ToolParam(type="string", description="Person name"),
                },
                handler=lambda name: {},
            )
        )
        decls = server.get_tool_declarations()
        assert decls is not None
        assert len(decls) == 1
        assert "function_declarations" in decls[0]

        func_decls = decls[0]["function_declarations"]
        assert len(func_decls) == 1
        assert func_decls[0]["name"] == "greet"
        assert func_decls[0]["description"] == "Say hello"
        assert "parameters" in func_decls[0]

        params = func_decls[0]["parameters"]
        assert params["type"] == "OBJECT"
        assert "name" in params["properties"]
        assert params["properties"]["name"]["type"] == "STRING"
        assert "name" in params["required"]

    def test_tool_without_params(self) -> None:
        server = ToolServer()
        server.register_tool(
            ToolDefinition(name="ping", description="Ping", handler=lambda: {})
        )
        decls = server.get_tool_declarations()
        func_decls = decls[0]["function_declarations"]
        assert "parameters" not in func_decls[0]

    def test_multiple_tools_in_one_declaration(self) -> None:
        server = ToolServer()
        server.register_tool(ToolDefinition(name="a", description="A"))
        server.register_tool(ToolDefinition(name="b", description="B"))
        decls = server.get_tool_declarations()
        func_decls = decls[0]["function_declarations"]
        assert len(func_decls) == 2
        names = {d["name"] for d in func_decls}
        assert names == {"a", "b"}

    def test_optional_param_not_in_required(self) -> None:
        server = ToolServer()
        server.register_tool(
            ToolDefinition(
                name="test",
                description="Test",
                parameters={
                    "required_p": ToolParam(
                        type="string", description="R", required=True
                    ),
                    "optional_p": ToolParam(
                        type="string", description="O", required=False
                    ),
                },
                handler=lambda **kw: {},
            )
        )
        decls = server.get_tool_declarations()
        params = decls[0]["function_declarations"][0]["parameters"]
        assert "required_p" in params["required"]
        assert "optional_p" not in params["required"]


# ---------------------------------------------------------------------------
# ToolServer — builtin tools
# ---------------------------------------------------------------------------


class TestToolServerBuiltins:
    def test_register_no_hardware(self) -> None:
        server = ToolServer()
        server.register_builtin_tools()
        assert server.registered_tools == []

    def test_register_display_tools(self) -> None:
        server = ToolServer()
        display = StubDisplayOutput()
        server.register_builtin_tools(display=display)
        assert "display_text" in server.registered_tools
        assert "display_status" in server.registered_tools
        assert "clear_display" in server.registered_tools

    def test_register_camera_tools(self) -> None:
        server = ToolServer()
        camera = StubCameraInput()
        server.register_builtin_tools(camera=camera)
        assert "capture_camera_frame" in server.registered_tools

    def test_register_all_hardware(self) -> None:
        server = ToolServer()
        server.register_builtin_tools(
            display=StubDisplayOutput(), camera=StubCameraInput()
        )
        assert len(server.registered_tools) == 4


# ---------------------------------------------------------------------------
# ToolServer — user tool discovery
# ---------------------------------------------------------------------------


class TestToolServerDiscovery:
    def test_missing_directory(self) -> None:
        server = ToolServer()
        server.discover_user_tools("/nonexistent/path")
        assert server.registered_tools == []

    def test_empty_directory(self, tmp_path: Path) -> None:
        server = ToolServer()
        server.discover_user_tools(str(tmp_path))
        assert server.registered_tools == []

    def test_discover_valid_tool(self, tmp_path: Path) -> None:
        tool_file = tmp_path / "my_tool.py"
        tool_file.write_text(
            "from src.tools.server import ToolDefinition\n"
            "TOOLS = [\n"
            "    ToolDefinition(name='my_tool', description='Custom tool',\n"
            "                   handler=lambda: {'custom': True}),\n"
            "]\n"
        )
        server = ToolServer()
        server.discover_user_tools(str(tmp_path))
        assert "my_tool" in server.registered_tools

    def test_skip_underscore_files(self, tmp_path: Path) -> None:
        (tmp_path / "__init__.py").write_text("")
        (tmp_path / "_private.py").write_text(
            "from src.tools.server import ToolDefinition\n"
            "TOOLS = [ToolDefinition(name='private', description='X')]\n"
        )
        server = ToolServer()
        server.discover_user_tools(str(tmp_path))
        assert server.registered_tools == []

    def test_skip_broken_modules(self, tmp_path: Path) -> None:
        (tmp_path / "broken.py").write_text("raise RuntimeError('bad')\n")
        server = ToolServer()
        server.discover_user_tools(str(tmp_path))
        assert server.registered_tools == []

    def test_skip_non_tool_items(self, tmp_path: Path) -> None:
        (tmp_path / "misc.py").write_text("TOOLS = ['not_a_tool', 42]\n")
        server = ToolServer()
        server.discover_user_tools(str(tmp_path))
        assert server.registered_tools == []


# ---------------------------------------------------------------------------
# Display tools
# ---------------------------------------------------------------------------


class TestDisplayTools:
    def test_creates_three_tools(self) -> None:
        display = StubDisplayOutput()
        tools = create_display_tools(display)
        assert len(tools) == 3
        names = {t.name for t in tools}
        assert names == {"display_text", "display_status", "clear_display"}

    def test_display_text_handler(self) -> None:
        display = StubDisplayOutput()
        tools = {t.name: t for t in create_display_tools(display)}
        result = tools["display_text"].handler(text="Hello!")
        assert result == {"status": "ok", "text": "Hello!"}
        assert display.last_text == "Hello!"

    def test_display_status_handler(self) -> None:
        display = StubDisplayOutput()
        tools = {t.name: t for t in create_display_tools(display)}
        result = tools["display_status"].handler(status="thinking")
        assert result == {"status": "ok", "status_shown": "thinking"}
        assert display.last_status == "thinking"

    def test_clear_display_handler(self) -> None:
        display = StubDisplayOutput()
        display.show_text("something")
        tools = {t.name: t for t in create_display_tools(display)}
        result = tools["clear_display"].handler()
        assert result == {"status": "ok"}
        assert display.last_text == ""

    def test_display_text_params(self) -> None:
        display = StubDisplayOutput()
        tools = {t.name: t for t in create_display_tools(display)}
        assert "text" in tools["display_text"].parameters
        assert tools["display_text"].parameters["text"].type == "string"

    async def test_display_tool_via_server(self) -> None:
        display = StubDisplayOutput()
        server = ToolServer()
        server.register_builtin_tools(display=display)
        result = await server.execute_tool("display_text", {"text": "via server"})
        assert result["status"] == "ok"
        assert display.last_text == "via server"


# ---------------------------------------------------------------------------
# Camera tools
# ---------------------------------------------------------------------------


class TestCameraTools:
    def test_creates_one_tool(self) -> None:
        camera = StubCameraInput()
        tools = create_camera_tools(camera)
        assert len(tools) == 1
        assert tools[0].name == "capture_camera_frame"

    def test_capture_returns_base64(self) -> None:
        camera = StubCameraInput()
        tools = create_camera_tools(camera)
        result = tools[0].handler()
        assert "image" in result
        assert result["mime_type"] == "image/jpeg"
        # Verify base64 is decodable
        decoded = base64.b64decode(result["image"])
        assert len(decoded) > 0

    def test_capture_with_test_image(self) -> None:
        camera = StubCameraInput(TEST_IMAGE)
        tools = create_camera_tools(camera)
        result = tools[0].handler()
        decoded = base64.b64decode(result["image"])
        assert decoded == TEST_IMAGE.read_bytes()
        assert result["size_bytes"] == len(TEST_IMAGE.read_bytes())

    def test_capture_stub_minimal_jpeg(self) -> None:
        camera = StubCameraInput()  # No image path → minimal JPEG
        tools = create_camera_tools(camera)
        result = tools[0].handler()
        decoded = base64.b64decode(result["image"])
        # StubCameraInput returns SOI+EOI markers
        assert decoded == b"\xff\xd8\xff\xd9"
        assert result["size_bytes"] == 4

    def test_capture_has_no_params(self) -> None:
        camera = StubCameraInput()
        tools = create_camera_tools(camera)
        assert tools[0].parameters == {}

    async def test_camera_tool_via_server(self) -> None:
        camera = StubCameraInput()
        server = ToolServer()
        server.register_builtin_tools(camera=camera)
        result = await server.execute_tool("capture_camera_frame", {})
        assert result["mime_type"] == "image/jpeg"
        assert "image" in result
