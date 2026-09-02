import os
import sys
import argparse
import webbrowser
import uvicorn

# from codegraph.dataclass.config import LLMConfig
# from codegraph.build_graph.builder import GraphBuilder
# from codegraph.build_graph.embedder import CodeEmbedder
# from codegraph.cli.commands import run_cli
# from codegraph.api.server import create_app


def print_help_guide():
    """Prints a structured mini-documentation cheatsheet for CodeGraph."""
    guide = """
================================================================================
                    🕸️  CODEGRAPH: CLI & USAGE MANUAL  🕸️
================================================================================

CodeGraph is a Graph-Augmented Code RAG and analysis tool that combines static 
AST parsing, SQLite graph relationships, and local vector embeddings.

--------------------------------------------------------------------------------
1. CONFIGURATION: Manage LLM Provider & Secrets
--------------------------------------------------------------------------------
Setup your LLM provider (OpenAI, Anthropic, Gemini, Ollama, Custom / LM Studio).
Configurations are securely stored in ~/.codegraph/config.json.

  codegraph config               Interactively select provider, model & API key
  codegraph config --show        Display active model, provider, and masked API key

--------------------------------------------------------------------------------
2. BUILD: Index & Vectorize a Codebase
--------------------------------------------------------------------------------
Parses source files, resolves cross-file dependencies, respects .gitignore,
and computes local vector embeddings.

  codegraph build <dir> [OPTIONS]

  Arguments:
    target_dir                   Path to the codebase directory to index

  Options:
    --db PATH                    SQLite DB output path (default: target_dir/codebase_graph.db)
    --model [fast|quality|strong|<hf_repo_id>]
                                 Embedding model choice (default: fast)
                                   • fast    : all-MiniLM-L6-v2 (384d, ultra-fast)
                                   • quality : BGE-small-en-v1.5 (384d, high accuracy)
                                   • strong  : BGE-base-en-v1.5 (768d, deep nuance)
                                   • custom  : Any valid HuggingFace repository ID

  Examples:
    codegraph build ./my_project
    codegraph build ./my_project --model quality --db my_project.db
    codegraph build ./my_project --model sentence-transformers/all-mpnet-base-v2

--------------------------------------------------------------------------------
3. QUERY: Inspect Code Graph & Ask Questions via CLI
--------------------------------------------------------------------------------
Run structural AST traversals, semantic vector searches, or ask LLM questions.

  codegraph query <command> "<target>" [OPTIONS]

  Commands:
    find       Show symbol metadata, docstrings, and location in source code
    callers    List functions/methods that call this symbol (Upstream)
    callees    List functions/methods called by this symbol (Downstream)
    trace      Trace downstream execution call tree up to N levels
    blast      Compute impact/blast radius if symbol is modified
    search     Perform semantic vector search using natural language
    chat       Ask architectural questions using GraphRAG + File Context

  Options:
    --db PATH                    Path to SQLite database (default: codebase_graph.db)
    --depth INT                  Max depth for trace and blast queries (default: 3)
    --top INT                    Number of semantic search results (default: 5)

  Examples:
    codegraph query find "create_app"
    codegraph query callers "GraphStorage"
    codegraph query blast "remove_stale_files" --depth 2
    codegraph query search "authentication token validation" --top 3
    codegraph query chat "How does the incremental builder handle deleted files?"

--------------------------------------------------------------------------------
4. UI: Launch Interactive Web Interface (CodeGraph Studio)
--------------------------------------------------------------------------------
Spins up the FastAPI server and opens the interactive Vis.js graph UI in your browser.

  codegraph ui [OPTIONS]

  Options:
    --db PATH                    Path to SQLite DB (default: codebase_graph.db)
    --host STR                   Host binding interface (default: 127.0.0.1)
    --port INT                   Port to bind web server (default: 8000)

  Examples:
    codegraph ui
    codegraph ui --db my_project.db --port 8080

--------------------------------------------------------------------------------
5. HELP: Show this Manual
--------------------------------------------------------------------------------
  codegraph help
================================================================================
"""
    print(guide)


def main():
    parser = argparse.ArgumentParser(
        prog="codegraph",
        description="CodeGraph: Graph-Augmented Code RAG & Analysis Engine",
        add_help=True
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    # Help / Docs Command
    subparsers.add_parser("help", help="Show comprehensive command documentation and examples")

    # Config Command
    config_parser = subparsers.add_parser("config", help="Manage LLM configuration")
    config_parser.add_argument("--show", action="store_true", help="Show current configuration")

    # Build Command
    build_parser = subparsers.add_parser("build", help="Index a codebase directory")
    build_parser.add_argument("target_dir", help="Path to codebase directory")
    build_parser.add_argument("--db", default="codebase_graph.db", help="Output SQLite DB path")
    build_parser.add_argument(
        "--model", 
        default="fast", 
        help="Embedding model choice: preset aliases ('fast', 'quality', 'strong') or any custom HuggingFace model ID"
    )

    # Query Command
    query_parser = subparsers.add_parser("query", help="Query the codebase graph")
    query_parser.add_argument(
        "command", 
        choices=["find", "callers", "callees", "trace", "blast", "search", "chat"],
        help="Query action to perform"
    )
    query_parser.add_argument("target", help="Exact symbol name or natural language question")
    query_parser.add_argument("--db", default="codebase_graph.db", help="Database file path")
    query_parser.add_argument("--depth", type=int, default=3, help="Max traversal depth")
    query_parser.add_argument("--top", type=int, default=5, help="Number of semantic results")

    # UI Command
    ui_parser = subparsers.add_parser("ui", help="Launch interactive browser UI")
    ui_parser.add_argument("--db", default="codebase_graph.db", help="Path to SQLite database")
    ui_parser.add_argument("--host", default="127.0.0.1", help="Host interface")
    ui_parser.add_argument("--port", type=int, default=8000, help="Port to bind server")

    # If no arguments provided, display the help guide
    if len(sys.argv) == 1:
        print_help_guide()
        sys.exit(0)

    args = parser.parse_args()

    if args.subcommand in ("help", None):
        print_help_guide()

    elif args.subcommand == "config":
        from codegraph.dataclass.config import LLMConfig
        if args.show:
            LLMConfig.show_current()
        else:
            LLMConfig.configure_interactive()

    elif args.subcommand == "build":
        from codegraph.build_graph.builder import GraphBuilder
        from codegraph.build_graph.embedder import CodeEmbedder

        target = os.path.abspath(args.target_dir)
        if not os.path.exists(target):
            print(f"Error: Directory '{target}' does not exist.")
            sys.exit(1)

        if args.db == "codebase_graph.db":
            db_path = os.path.join(target, "codebase_graph.db")
        else:
            db_path = os.path.abspath(args.db)

        print("\nPHASE 1: STRUCTURAL GRAPH GENERATION")
        builder = GraphBuilder(root_dir=target, db_path=db_path)
        builder.build()

        print("\nPHASE 2: AI VECTOR EMBEDDINGS")
        embedder = CodeEmbedder(db_path=db_path, model_choice=args.model)
        embedder.run()

        print("\nPIPELINE COMPLETE.")

    elif args.subcommand == "query":
        from codegraph.cli.commands import run_cli

        run_cli(args.db, args.command, args.target, args.depth, top_k=args.top)

    elif args.subcommand == "ui":
        from codegraph.api.server import create_app

        url = f"http://{args.host}:{args.port}"
        print(f"\nLaunching CodeGraph Studio at: {url}")
        print(f"Connected Database: {os.path.abspath(args.db)}")
        
        # Open default browser automatically
        webbrowser.open(url)

        # Start FastAPI app
        app = create_app(db_path=args.db)
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()