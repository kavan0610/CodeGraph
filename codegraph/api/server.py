import os
import json
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from codegraph.dataclass.config import LLMConfig, CONFIG_FILE
from codegraph.database.sqlite import GraphStorage
from codegraph.retrieval.structural import StructuralRetriever
from codegraph.retrieval.semantic import SemanticRetriever
from codegraph.rag.context import GraphContextBuilder
from codegraph.rag.llm import CodebaseAgent

def create_app(db_path: str = "codebase_graph.db") -> FastAPI:
    app = FastAPI(title="CodeGraph Studio")

    # ------------------ Request Schemas ------------------
    class ChatRequest(BaseModel):
        question: str
        depth: int = 2
        history: list = []

    class ConfigRequest(BaseModel):
        provider: str
        model: str
        base_url: Optional[str] = None
        api_key: Optional[str] = None

    class StructuralRequest(BaseModel):
        command: str
        target: str
        depth: int = 3
        node_id: Optional[str] = None 

    # ------------------ API Endpoints ------------------
    @app.get("/api/graph")
    def get_graph_data(): 
        if not os.path.exists(db_path):
            raise HTTPException(status_code=404, detail="Database file not found.")

        # CLEAN: Delegated to GraphStorage DAO instead of raw SQL in controller
        storage = GraphStorage(db_path)
        graph_data = storage.get_full_graph_data()
        nodes_rows = graph_data["nodes"]
        edges_rows = graph_data["edges"]

        kind_colors = {
            "module": "#64748b", "class": "#8b5cf6", "function": "#3b82f6",
            "method": "#06b6d4", "variable": "#f59e0b", "external": "#ef4444"
        }

        vis_nodes = []
        for n in nodes_rows:
            color = kind_colors.get(n["kind"], "#94a3b8")
            
            if n["kind"] == "module":
                display_name = os.path.basename(n["file_path"])
                if display_name.endswith('.py'):
                    display_name = display_name[:-3] 
                label = display_name
            else:
                filename = os.path.basename(n["file_path"])
                label = f"{filename}.{n['name']}"
                display_name = n["name"]
            
            vis_nodes.append({
                "id": n["id"],
                "label": label,
                "raw_name": display_name, 
                "title": f"{n['file_path']}:L{n['start_line']}-{n['end_line']}",
                "color": {"background": color, "border": "#ffffff"},
                "shape": "dot",
                "kind": n["kind"],
                "file": n["file_path"],
                "docstring": n["docstring"] or "No docstring",
                "code": n["source_code"],
                "lines": f"{n['start_line']}-{n['end_line']}"
            })

        edge_styles = {
            "CALLS": {"color": "#38bdf8", "opacity": 0.9},
            "DEFINES": {"color": "#64748b", "opacity": 0.3},
            "IMPORTS": {"color": "#10b981", "opacity": 0.7}
        }

        vis_edges = []
        for e in edges_rows:
            style = edge_styles.get(e["relation_type"], {"color": "#cbd5e1", "opacity": 0.5})
            vis_edges.append({
                "from": e["source_id"], "to": e["target_id"], "label": e["relation_type"],
                "color": style, "arrows": "to",
                "font": {"size": 9, "color": "#cbd5e1", "align": "middle"}
            })

        return {"nodes": vis_nodes, "edges": vis_edges}

    @app.post("/api/query/structural")
    def run_structural_query(req: StructuralRequest):
        retriever = StructuralRetriever(db_path)
        
        if req.node_id:
            query = "SELECT id, name, kind, file_path, start_line, end_line, docstring, source_code FROM nodes WHERE id = ?"
            nodes = retriever.storage._fetch_all(query, (req.node_id,))
            if not nodes:
                return {"status": "error", "message": "Specific node ID not found in database."}
        else:
            query = "SELECT id, name, kind, file_path, start_line, end_line, docstring, source_code FROM nodes WHERE name = ?"
            nodes = retriever.storage._fetch_all(query, (req.target,))
            
            if not nodes:
                target_file = req.target if req.target.endswith(".py") else f"{req.target}.py"
                query = """
                    SELECT id, name, kind, file_path, start_line, end_line, docstring, source_code 
                    FROM nodes 
                    WHERE (file_path LIKE ? OR file_path LIKE ? OR file_path = ?)
                    AND kind = 'module'
                """
                nodes = retriever.storage._fetch_all(query, (f"%/{target_file}", f"%\\{target_file}", target_file))

            if not nodes:
                return {"status": "error", "message": f"Symbol or file '{req.target}' not found."}
                
        for n in nodes:
            if n["kind"] == "module":
                clean_name = os.path.basename(n["file_path"])
                if clean_name.endswith(".py"):
                    clean_name = clean_name[:-3]
                n["name"] = clean_name

        if len(nodes) > 1 and not req.node_id:
            return {"status": "multiple_matches", "data": nodes}

        target_node = nodes[0]
        node_id = target_node["id"]

        if req.command == "find": return {"status": "success", "data": target_node}
        elif req.command == "callers": return {"status": "success", "data": retriever.get_callers(node_id)}
        elif req.command == "callees": return {"status": "success", "data": retriever.get_callees(node_id)}
        elif req.command == "blast": return {"status": "success", "data": retriever.blast_radius(node_id, req.depth)}
        elif req.command == "trace": return {"status": "success", "data": retriever.trace(node_id, req.depth)}
        else: raise HTTPException(status_code=400, detail="Invalid command")

    @app.get("/api/query/semantic")
    def run_semantic_search(q: str, top_k: int = 5):
        try:
            retriever = SemanticRetriever(db_path)
            results = retriever.search(q, top_k=top_k)
            
            formatted_results = []
            for score, node in results:
                display_name = node["name"]
                if node["kind"] == "module":
                    display_name = os.path.basename(node["file_path"])
                    if display_name.endswith(".py"):
                        display_name = display_name[:-3]
                
                formatted_results.append({
                    "score": round(float(score) * 100, 1),
                    "id": node["id"],
                    "name": display_name,
                    "kind": node["kind"],
                    "file_path": node["file_path"],
                    "start_line": node["start_line"],
                    "end_line": node["end_line"]
                })
                
            return {"status": "success", "results": formatted_results}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @app.post("/api/query/chat")
    def run_chat(req: ChatRequest):
        import litellm
        agent = CodebaseAgent()
        safe_base_url = agent.config.base_url if agent.config.base_url else None
        model_name = agent._get_formatted_model_string()

        intent_prompt = f"""You are a query classifier for a codebase assistant.
User query: "{req.question}"

Classify this query into one of two categories:
1. "CODEBASE": The user is asking about this specific project, its functions, files, classes, architecture, workflows, or internal logic.
2. "GENERAL": The user is asking a general programming, syntax, algorithmic, conceptual, or external library question that does not require internal project context.

Respond with ONLY one word: either CODEBASE or GENERAL."""

        try:
            intent_res = litellm.completion(
                model=model_name,
                messages=[{"role": "user", "content": intent_prompt}],
                api_base=safe_base_url,
                temperature=0.0
            )
            intent = intent_res.choices[0].message.content.strip().upper()
        except Exception:
            intent = "CODEBASE"

        if "GENERAL" in intent:
            matched_names = ["No context used (General Knowledge)"]
            combined_context = "No specific codebase context was relevant. Answer the user's question clearly using general programming knowledge."
        else:
            retriever = SemanticRetriever(db_path)
            results = retriever.search(req.question, top_k=5)
            
            if not results:
                matched_names = ["No context found"]
                combined_context = "No matching code was found in the database."
                selected_ids = []
            else:
                candidates_text = ""
                valid_ids = {}
                for idx, (score, node) in enumerate(results):
                    node_id = str(node["id"])
                    valid_ids[node_id] = node
                    
                    code_snippet = node.get("source_code") or node.get("docstring") or "No code available"
                    code_snippet = code_snippet[:500] + ("..." if len(code_snippet) > 500 else "")
                    candidates_text += f"ID: {node_id}\nName: {node['name']}\nType: {node['kind']}\nFile: {node['file_path']}\nSnippet:\n{code_snippet}\n\n"

                selection_prompt = f"""You are a codebase routing agent. The user is asking about this codebase: "{req.question}"
Below are {len(results)} candidate nodes retrieved from the project.
{candidates_text}
Select the most relevant ID(s) (maximum 3) needed to build context for answering the question.
Respond ONLY with a comma-separated list of the selected ID(s). Do not include formatting, markdown, or extra text."""

                try:
                    selection_response = litellm.completion(
                        model=model_name,
                        messages=[{"role": "user", "content": selection_prompt}],
                        api_base=safe_base_url,
                        temperature=0.0
                    )
                    llm_selected_text = selection_response.choices[0].message.content.strip()
                except Exception:
                    llm_selected_text = str(results[0][1]["id"])

                selected_ids = []
                for raw_id in llm_selected_text.replace('`', '').replace('"', '').replace('\n', ',').split(','):
                    clean_id = raw_id.strip()
                    if clean_id in valid_ids and clean_id not in selected_ids:
                        selected_ids.append(clean_id)
                
                if not selected_ids:
                    selected_ids = [str(results[0][1]["id"])]

                selected_ids = selected_ids[:3]

                context_builder = GraphContextBuilder(db_path)
                combined_context = ""
                matched_names = []

                for sid in selected_ids:
                    node = valid_ids[sid]
                    display_name = node["name"]
                    if node["kind"] == "module":
                        display_name = os.path.basename(node["file_path"])
                        if display_name.endswith(".py"):
                            display_name = display_name[:-3]
                    matched_names.append(display_name)

                    base_context = context_builder.build_context(sid, depth=req.depth)
                    
                    if node["kind"] == "module" and os.path.exists(node["file_path"]):
                        try:
                            with open(node["file_path"], "r", encoding="utf-8") as f:
                                file_content = f.read()
                            base_context += f"\n\n--- RAW FILE CONTENT ({display_name}.py) ---\n{file_content[:15000]}"
                        except Exception as e:
                            base_context += f"\n\n[Warning: Could not read raw file from disk: {e}]"

                    combined_context += base_context + "\n\n"

        msg = [{"role": "system", "content": "You are a senior engineer answering questions strictly using the provided GraphRAG context and file contents. If answering general programming questions, explain clearly and concisely."}]
        
        for h in req.history[-6:]:
            msg.append({"role": h["role"], "content": h["content"]})
            
        msg.append({"role": "user", "content": f"CONTEXT:\n{combined_context}\n\nQUESTION:\n{req.question}"})
        
        final_response = litellm.completion(
            model=model_name, 
            messages=msg, 
            api_base=safe_base_url, 
            temperature=0.2
        )
        
        return {
            "status": "success", 
            "matched_symbol": ", ".join(matched_names), 
            "answer": final_response.choices[0].message.content
        }
    
    @app.get("/api/config")
    def get_config():
        c = LLMConfig.load()
        return {"configured": True, "provider": c.provider, "model": c.model, "base_url": c.base_url or "", "api_key": "***"} if c else {"configured": False}

    @app.post("/api/config")
    def save_config(req: ConfigRequest):
        import dataclasses
        config_obj = LLMConfig(provider=req.provider, model=req.model, api_key=req.api_key or "dummy", base_url=req.base_url or None)
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f: json.dump(dataclasses.asdict(config_obj), f, indent=2)
        return {"status": "success"}

    # ------------------ Serve Vite Frontend ------------------
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    dist_path = os.path.abspath(os.path.join(current_dir, "..", "ui", "dist"))

    if os.path.exists(dist_path):
        assets_path = os.path.join(dist_path, "assets")
        if os.path.exists(assets_path):
            app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

        @app.get("/")
        async def serve_ui():
            return FileResponse(os.path.join(dist_path, "index.html"))
    else:
        @app.get("/")
        async def ui_not_found():
            return {"error": f"UI build not found at {dist_path}. Please navigate to the 'ui' directory and run 'npx vite build'."}

    return app