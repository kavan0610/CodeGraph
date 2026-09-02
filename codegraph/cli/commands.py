def select_node(nodes: list, name: str) -> dict:
    """Helper to let the user pick a node if multiple have the same name."""
    if not nodes:
        print(f"Could not find anything named '{name}'.")
        return None
    if len(nodes) == 1:
        return nodes[0]
        
    print(f"Found {len(nodes)} matches for '{name}':")
    for i, n in enumerate(nodes):
        print(f"  [{i}] {n['kind'].upper()} in {n['file_path']} (Lines {n['start_line']}-{n['end_line']})")
    
    choice = int(input("Select number >> "))
    return nodes[choice]

def run_cli(db_path: str, command: str, target: str, depth: int = 3, top_k: int = 5):

    if command == "chat":
        import os
        import litellm
        from codegraph.retrieval.semantic import SemanticRetriever
        from codegraph.rag.context import GraphContextBuilder
        from codegraph.rag.llm import CodebaseAgent
        
        
        agent = CodebaseAgent()
        safe_base_url = agent.config.base_url if agent.config.base_url else None
        model_name = agent._get_formatted_model_string()

        # STEP 1: Intent Classification

        print("Step 1: Classifying query intent...")
        intent_prompt = f"""You are a query classifier for a codebase assistant.
User query: "{target}"
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

        # STEP 2: General Knowledge Bypass

        if "GENERAL" in intent:
            print("Intent: GENERAL (Bypassing codebase search)")
            combined_context = "No specific codebase context was relevant. Answer the user's question clearly using general programming knowledge."

        # STEP 3: Codebase Context Routing

        else:
            print("Intent: CODEBASE (Searching vector embeddings...)")
            retriever = SemanticRetriever(db_path)
            results = retriever.search(target, top_k=5)

            if not results:
                print("No matching code found in the database.")
                combined_context = "No matching code was found in the database."
            else:
                print(f"Step 2: AI evaluating {len(results)} candidate files/symbols...")
                candidates_text = ""
                valid_ids = {}
                for idx, (score, node) in enumerate(results):
                    node_id = str(node["id"])
                    valid_ids[node_id] = node
                    code_snippet = node.get("source_code") or node.get("docstring") or "No code available"
                    code_snippet = code_snippet[:500] + ("..." if len(code_snippet) > 500 else "")
                    candidates_text += f"ID: {node_id}\nName: {node['name']}\nType: {node['kind']}\nFile: {node['file_path']}\nSnippet:\n{code_snippet}\n\n"

                selection_prompt = f"""You are a codebase routing agent. The user is asking about this codebase: "{target}"
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

                print(f"Step 3: Building graph context for {len(selected_ids)} selected targets (Depth: {depth})...")
                context_builder = GraphContextBuilder(db_path)
                combined_context = ""

                for sid in selected_ids:
                    node = valid_ids[sid]
                    display_name = node["name"]
                    if node["kind"] == "module":
                        display_name = os.path.basename(node["file_path"])
                        if display_name.endswith(".py"):
                            display_name = display_name[:-3]
                    
                    base_context = context_builder.build_context(sid, depth=depth)
                    
                    if node["kind"] == "module" and os.path.exists(node["file_path"]):
                        try:
                            with open(node["file_path"], "r", encoding="utf-8") as f:
                                file_content = f.read()
                            base_context += f"\n\n--- RAW FILE CONTENT ({display_name}.py) ---\n{file_content[:15000]}"
                        except Exception as e:
                            base_context += f"\n\n[Warning: Could not read raw file from disk: {e}]"

                    combined_context += base_context + "\n\n"

        # STEP 4: Generate Answer

        print("Step 4: Generating AI response...\n")
        
        agent.chat(target, combined_context)
        
        print("\n")
        return

    elif command == "search":
        from codegraph.retrieval.semantic import SemanticRetriever
        
        print(f"\nSearching for concept: '{target}'")
        
        retriever = SemanticRetriever(db_path)
        results = retriever.search(target, top_k=top_k)
        
        for score, node in results:
            match_pct = f"{score * 100:.1f}%"
            print(f"[{match_pct}] {node['kind'].upper()}: {node['name']}")
            print(f"       File: {node['file_path']} (Lines {node['start_line']}-{node['end_line']})\n")
        return
    
    else:
        import os
        from codegraph.retrieval.structural import StructuralRetriever
        retriever = StructuralRetriever(db_path)
        
        nodes = retriever.find_nodes_by_name(target)
        
        if not nodes:
            target_file = target if target.endswith(".py") else f"{target}.py"
            query = """
                SELECT id, name, kind, file_path, start_line, end_line, docstring, source_code 
                FROM nodes 
                WHERE (file_path LIKE ? OR file_path LIKE ? OR file_path = ?)
                AND kind = 'module'
            """
            nodes = retriever.storage._fetch_all(query, (f"%/{target_file}", f"%\\{target_file}", target_file))

        if not nodes:
            print(f"Error: Symbol or file '{target}' not found.")
            return

        for n in nodes:
            if n["kind"] == "module":
                clean_name = os.path.basename(n["file_path"])
                if clean_name.endswith(".py"):
                    clean_name = clean_name[:-3]
                n["name"] = clean_name

        node = select_node(nodes, target)
        if not node:
            return

        print(f"\nTarget: {node['name']} ({node['id']})")
        print("-" * 50)

        # Execute the requested command
        if command == "find":
            print(f"File: {node['file_path']} | Lines: {node['start_line']}-{node['end_line']}")
            print(f"Docstring: {node['docstring'] or 'None'}")
            
        elif command == "callers":
            callers = retriever.get_callers(node['id'])
            for c in callers:
                print(f"[{c['kind']}] {c['name']} (File: {c['file_path']}:{c['line_number']})")
                
        elif command == "callees":
            callees = retriever.get_callees(node['id'])
            for c in callees:
                print(f"[{c['kind']}] {c['name']} (Line: {c['line_number']})")
                
        elif command == "blast":
            print(f"Blast Radius (Max Depth: {depth})")
            layers = retriever.blast_radius(node['id'], depth)
            for d, items in layers.items():
                if not items: continue
                print(f"\nLevel {d} Impact:")
                for item in items:
                    print(f"  - [{item['kind']}] {item['name']} (via {item['relation_type']})")
                    
        elif command == "trace":
            print(f"Execution Trace (Max Depth: {depth})")
            layers = retriever.trace(node['id'], depth)
            for d, items in layers.items():
                if not items: continue
                print(f"\nLevel {d} Calls:")
                for item in items:
                    print(f"  - [{item['kind']}] {item['name']} (via {item['relation_type']})")