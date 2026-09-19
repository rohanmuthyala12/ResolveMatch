"""Register the project connector and preserve existing agent instructions."""

import argparse
import asyncio

from . import config
from .trueforge import request


async def setup(model=None):
    agents = (await request("GET", "/agents"))["data"]
    existing = next((a for a in agents if a["name"] == config.AGENT_NAME), None)
    models = (await request("GET", "/models"))["data"]
    if not models:
        raise SystemExit("Configure a model provider in TrueForge first.")
    selected = model or (
        existing["manifest"]["model"]["name"] if existing else models[0]["name"]
    )
    if selected not in {m["name"] for m in models}:
        raise SystemExit("Selected model is not configured in TrueForge.")
    await request(
        "PUT",
        "/settings/mcp-servers",
        {
            "manifest": {
                "name": "resolvematch",
                "type": "remote",
                "description": "ResolveMatch incident evidence, routing, and approved assignments",
                "url": config.MCP_URL,
                "auth": {
                    "type": "header",
                    "headers": {"Authorization": f"Bearer {config.MCP_TOKEN}"},
                },
            }
        },
    )
    instructions = (config.ROOT / "agent-instructions.md").read_text()
    manifest = dict(existing["manifest"]) if existing else {"model": {"name": selected}}
    old = manifest.get("instructions", "")
    marker = "\n\n--- ResolveMatch integration contract ---\n"
    if existing:
        manifest["instructions"] = old.split(marker)[0] + marker + instructions
    else:
        manifest["instructions"] = instructions
    manifest["mcp_servers"] = [
        {
            "name": "resolvematch",
            "enable_tools": [
                "get_ticket",
                "search_historical_tickets",
                "get_engineer_history",
                "get_engineer_workload",
                "rank_engineers",
                "assign_ticket",
            ],
            "require_approval_for_tools": ["assign_ticket"],
            "preload": True,
        }
    ]
    manifest["config"] = {
        "sandbox": {"enabled": False},
        "dynamic_sub_agents": {"enabled": False},
        "generative_ui": {"enabled": False},
        "ask_user_questions": {"enabled": False},
        "iteration_limit": 12,
    }
    if existing:
        await request(
            "PUT",
            "/agents/" + existing["id"],
            {
                "manifest": manifest,
                "description": existing.get(
                    "description", "ResolveMatch incident routing"
                ),
            },
        )
    else:
        await request(
            "POST",
            "/agents",
            {
                "name": config.AGENT_NAME,
                "description": "Evidence-backed incident routing with human-approved assignment",
                "manifest": manifest,
            },
        )
    print(
        f"Connected {config.AGENT_NAME} to ResolveMatch. Assignment approval is explicitly enabled."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        help="Configured TrueForge model name; defaults to existing agent or first configured model",
    )
    args = parser.parse_args()
    asyncio.run(setup(args.model))
