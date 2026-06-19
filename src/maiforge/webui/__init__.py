"""
WebUI integration – hooks into MaiBot's existing web server to add /maiforge routes.
"""
from .mod_page import ModWebUI


def register_routes(forge, app_or_router) -> None:
    """Register /maiforge routes on the host web framework."""
    webui = ModWebUI(forge)

    # We support Flask / FastAPI / aiohttp style routers
    # This is an adapter that tries to detect the framework

    def _add_route(path: str, handler, methods=None):
        """Try multiple frameworks."""
        if methods is None:
            methods = ["GET"]
        # FastAPI / Starlette
        if hasattr(app_or_router, "add_api_route"):
            app_or_router.add_api_route(path, handler, methods=methods)
            return
        # aiohttp
        if hasattr(app_or_router, "add_routes"):
            import aiohttp.web
            async def _aiohttp_handler(request):
                return aiohttp.web.Response(body=handler())
            for method in methods:
                app_or_router.add_routes([
                    aiohttp.web.route(method, path, _aiohttp_handler)
                ])
            return
        # Flask
        if hasattr(app_or_router, "add_url_rule"):
            app_or_router.add_url_rule(path, view_func=handler, methods=methods)
            return

    # Static page
    _add_route("/maiforge/mods", webui.serve_page, ["GET"])

    # API routes
    _add_route("/maiforge/api/mods", webui.api_mods, ["GET"])
    _add_route("/maiforge/api/uninstall", webui.api_uninstall, ["POST"])

    # Dynamic routes with path params – we use a catch-all + dispatch
    def _dispatch(path: str, request) -> bytes:
        parts = path.strip("/").split("/")
        # /maiforge/api/mod/<id>/<action>
        if len(parts) >= 3 and parts[0] == "maiforge" and parts[1] == "api" and parts[2] == "mod":
            if len(parts) >= 5:
                mod_id = parts[3]
                action = parts[4]
                if action == "enable" or action == "disable":
                    return webui.api_toggle(mod_id, action)
                if action == "delete":
                    return webui.api_delete(mod_id)
        # /maiforge/api/upload
        if path == "/maiforge/api/upload":
            # Handle multipart
            return webui.api_upload(
                request.get("file_data", b""),
                request.get("filename", "mod.zip"),
            )
        return b'{"ok":false,"message":"unknown route"}'


# Singleton adapter for MaiBot plugin system
def create_maiforge_plugin():
    """Factory for the MaiBot plugin that boots MaiForge."""
    from pathlib import Path
    import sys

    # Ensure maiforge src is on path
    forge_dir = Path(__file__).resolve().parent.parent
    if str(forge_dir) not in sys.path:
        sys.path.insert(0, str(forge_dir))

    from maiforge.core.forge import MaiForge

    class MaiForgePlugin:
        """MaiBot Plugin adapter for MaiForge."""

        def __init__(self):
            self.forge: MaiForge = None

        async def on_load(self, ctx):
            ctx.logger.info("[MaiForge] 正在初始化...")
            self.forge = MaiForge()
            self.forge.initialize()
            self.forge.load_mods()

            # Register WebUI routes
            register_routes(self.forge, ctx.web_app)
            ctx.logger.info(f"[MaiForge] 已加载 {len(self.forge.loader.mods)} 个模组")

        async def on_unload(self, ctx):
            if self.forge:
                self.forge.shutdown()
                ctx.logger.info("[MaiForge] 已关闭")

    return MaiForgePlugin()
