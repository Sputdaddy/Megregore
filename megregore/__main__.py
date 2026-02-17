"""
Entry point for Megregore.

Usage:
    python -m megregore              # Run MCP server (used by Claude Code)
    python -m megregore web          # Run web UI server (open localhost:3000)
    python -m megregore backfill     # Embed all existing memories into ChromaDB
"""
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="[megregore] %(asctime)s %(levelname)s: %(message)s",
    stream=sys.stderr,
)


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "mcp"

    if command == "web":
        from .web import main as web_main
        web_main()
    elif command == "mcp":
        from .mcp_server import main as mcp_main
        mcp_main()
    elif command == "backfill":
        _run_backfill()
    else:
        print(f"Unknown command: {command}")
        print("Usage: python -m megregore [mcp|web|backfill]")
        sys.exit(1)


def _run_backfill():
    """Run the embedding backfill process."""
    import asyncio

    async def _do_backfill():
        from .embeddings import backfill_all

        print()
        print("  Megregore — Embedding Backfill")
        print("  " + "=" * 40)
        print("  Loading embedding model (first run downloads ~80MB)...")
        print()

        result = await backfill_all()

        if result["status"] == "error":
            print(f"  ERROR: {result['message']}")
            sys.exit(1)

        print(f"  Processed: {result['total']} memories")
        print(f"  Succeeded: {result['succeeded']}")
        print(f"  Failed:    {result['failed']}")
        print("  " + "=" * 40)
        print("  Backfill complete. Semantic search is now active.")
        print()

    asyncio.run(_do_backfill())


main()
