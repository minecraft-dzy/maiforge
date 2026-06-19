"""
WebUI extension – mod management page.

Provides:
- /maiforge/mods  → mod list page
- /maiforge/install → API endpoint for install/uninstall
- /maiforge/mod/<id>/enable, disable, delete
- /maiforge/upload → upload a new mod ZIP
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger("maiforge.webui")

_MOD_PAGE_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>模组管理 - MaiForge</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:#f0f4f8;color:#2d3436}
.header{background:#fff;border-bottom:1px solid #dfe6e9;padding:16px 24px;display:flex;justify-content:space-between;align-items:center}
.header h1{font-size:20px}
.header .uninstall-btn{background:#d63031;color:#fff;border:none;padding:8px 16px;border-radius:6px;cursor:pointer;font-size:14px}
.header .uninstall-btn:hover{background:#c0392b}
.container{max-width:960px;margin:24px auto;padding:0 24px}
.mod-card{background:#fff;border-radius:10px;padding:20px;margin-bottom:12px;box-shadow:0 2px 8px rgba(0,0,0,.06);display:flex;justify-content:space-between;align-items:center}
.mod-info h3{font-size:16px;margin-bottom:4px}
.mod-info p{color:#636e72;font-size:13px}
.mod-info .desc{color:#2d3436;font-size:14px;margin-top:6px}
.mod-info .meta{color:#b2bec3;font-size:12px;margin-top:2px}
.mod-actions{display:flex;gap:8px}
.mod-actions button{padding:6px 14px;border:none;border-radius:6px;cursor:pointer;font-size:13px}
.btn-enable{background:#00b894;color:#fff}
.btn-disable{background:#fdcb6e;color:#2d3436}
.btn-delete{background:#d63031;color:#fff}
.upload-area{background:#fff;border-radius:10px;padding:20px;margin-bottom:16px;box-shadow:0 2px 8px rgba(0,0,0,.06)}
.upload-area h3{font-size:15px;margin-bottom:12px}
.upload-area input[type=file]{margin-right:12px}
.upload-area button{background:#6c5ce7;color:#fff;padding:8px 20px;border:none;border-radius:6px;cursor:pointer}
.empty{text-align:center;padding:48px;color:#b2bec3}
.toast{position:fixed;top:16px;right:16px;padding:12px 24px;border-radius:8px;color:#fff;font-size:14px;z-index:9999;display:none}
.toast.success{background:#00b894}
.toast.error{background:#d63031}
.state-badge{padding:2px 8px;border-radius:4px;font-size:11px;margin-left:8px}
.state-active{background:#00b89420;color:#00b894}
.state-disabled{background:#fdcb6e20;color:#e17055}
</style>
</head>
<body>
<div class="header">
<h1>📦 模组管理</h1>
<button class="uninstall-btn" onclick="uninstallForge()">卸载 MaiForge</button>
</div>
<div class="container">
<div class="upload-area">
<h3>安装新模组</h3>
<input type="file" id="modFile" accept=".zip">
<button onclick="uploadMod()">上传并安装</button>
</div>
<div id="modList"></div>
<div id="empty" class="empty" style="display:none">暂无已安装的模组</div>
</div>
<div class="toast" id="toast"></div>
<script>
const API = "/maiforge/api";

async function loadMods(){
    try{
        const r = await fetch(API+"/mods");
        const mods = await r.json();
        const list = document.getElementById("modList");
        const empty = document.getElementById("empty");
        if(mods.length===0){empty.style.display="block";list.innerHTML="";return}
        empty.style.display="none";
        list.innerHTML = mods.map(m=>`
        <div class="mod-card">
            <div class="mod-info">
                <h3>${esc(m.name)} <span class="state-badge state-${m.state==='active'?'active':'disabled'}">${m.state==='active'?'已启用':'已禁用'}</span></h3>
                <p>${esc(m.mod_id)} · v${esc(m.version)} · by ${esc(m.author)}</p>
                ${m.description?`<p class="desc">${esc(m.description)}</p>`:""}
            </div>
            <div class="mod-actions">
                ${m.state==='active'
                    ?`<button class="btn-disable" onclick="toggleMod('${esc(m.mod_id)}','disable')">禁用</button>`
                    :`<button class="btn-enable" onclick="toggleMod('${esc(m.mod_id)}','enable')">启用</button>`}
                <button class="btn-delete" onclick="deleteMod('${esc(m.mod_id)}')">删除</button>
            </div>
        </div>`).join("");
    }catch(e){toast("加载失败: "+e,"error")}
}

async function uploadMod(){
    const file = document.getElementById("modFile").files[0];
    if(!file) return toast("请选择文件","error");
    const fd = new FormData();
    fd.append("mod",file);
    try{
        const r = await fetch(API+"/upload",{method:"POST",body:fd});
        const d = await r.json();
        if(d.ok) toast(d.message,"success"),loadMods();
        else toast(d.message,"error");
    }catch(e){toast("上传失败","error")}
}

async function toggleMod(id,action){
    try{
        const r = await fetch(API+"/mod/"+id+"/"+action,{method:"POST"});
        const d = await r.json();
        toast(d.message,d.ok?"success":"error");
        loadMods();
    }catch(e){toast("操作失败","error")}
}

async function deleteMod(id){
    if(!confirm("确定删除此模组？此操作不可撤销。")) return;
    try{
        const r = await fetch(API+"/mod/"+id+"/delete",{method:"POST"});
        const d = await r.json();
        toast(d.message,d.ok?"success":"error");
        loadMods();
    }catch(e){toast("删除失败","error")}
}

async function uninstallForge(){
    if(!confirm("确定完全卸载 MaiForge？\n所有模组将被移除，主程序恢复正常。")) return;
    try{
        const r = await fetch(API+"/uninstall",{method:"POST"});
        const d = await r.json();
        toast(d.message,d.ok?"success":"error");
        if(d.ok) setTimeout(()=>location.reload(),2000);
    }catch(e){toast("卸载失败","error")}
}

function esc(s){return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}
function toast(msg,type){const t=document.getElementById("toast");t.textContent=msg;t.className="toast "+type;t.style.display="block";setTimeout(()=>t.style.display="none",3000)}
loadMods();
</script>
</body>
</html>"""


class ModWebUI:
    """Handles WebUI requests for mod management."""

    def __init__(self, forge):
        self.forge = forge  # MaiForge instance

    def serve_page(self) -> bytes:
        return _MOD_PAGE_HTML.encode("utf-8")

    # ---- API handlers ----

    def api_mods(self) -> bytes:
        mods = self.forge.get_all_mod_list()
        return json.dumps(mods).encode("utf-8")

    def api_upload(self, filedata: bytes, filename: str) -> bytes:
        if not filename.endswith(".zip"):
            return json.dumps({"ok": False, "message": "只支持 ZIP 格式的模组文件"}).encode()
        dest = self.forge.mods_dir / filename
        dest.write_bytes(filedata)
        try:
            self.forge.loader.load_mod(dest)
            mod = self.forge.loader.get_mod(filename[:-4])
            if mod:
                mod.enable(self.forge)
            return json.dumps({"ok": True, "message": f"模组 {filename} 已安装"}).encode()
        except Exception as exc:
            dest.unlink(missing_ok=True)
            return json.dumps({"ok": False, "message": f"加载失败: {exc}"}).encode()

    def api_toggle(self, mod_id: str, action: str) -> bytes:
        mod = self.forge.loader.get_mod(mod_id)
        if not mod:
            return json.dumps({"ok": False, "message": "模组未找到"}).encode()
        if action == "enable":
            try:
                mod.enable(self.forge)
                return json.dumps({"ok": True, "message": f"模组 {mod.info.name} 已启用"}).encode()
            except Exception as exc:
                return json.dumps({"ok": False, "message": str(exc)}).encode()
        elif action == "disable":
            mod.disable()
            return json.dumps({"ok": True, "message": f"模组 {mod.info.name} 已禁用"}).encode()
        return json.dumps({"ok": False, "message": "未知操作"}).encode()

    def api_delete(self, mod_id: str) -> bytes:
        mod = self.forge.loader.get_mod(mod_id)
        if not mod:
            return json.dumps({"ok": False, "message": "模组未找到"}).encode()
        mod.disable()
        self.forge.loader.unload_mod(mod_id)
        mod.zip_path.unlink(missing_ok=True)
        return json.dumps({"ok": True, "message": f"模组 {mod.info.name} 已删除"}).encode()

    def api_uninstall(self) -> bytes:
        try:
            self.forge.shutdown()
            self.forge.installer.uninstall()
            return json.dumps({"ok": True, "message": "MaiForge 已完全卸载。请重启主程序。"}).encode()
        except Exception as exc:
            return json.dumps({"ok": False, "message": str(exc)}).encode()
