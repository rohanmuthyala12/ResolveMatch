"""Verify the real HTTP MCP transport and tool discovery without a model call."""

import asyncio

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from backend import config


async def main():
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {config.MCP_TOKEN}"}
    ) as client:
        async with streamable_http_client(config.MCP_URL, http_client=client) as (
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                assert {t.name for t in listed.tools} == {
                    "get_ticket",
                    "search_historical_tickets",
                    "get_engineer_history",
                    "get_engineer_workload",
                    "rank_engineers",
                    "assign_ticket",
                }
                result = await session.call_tool(
                    "search_historical_tickets",
                    {
                        "ticket_description": "Databricks ETL CUSTOMER_ID schema type mismatch"
                    },
                )
                assert not result.isError
                print(
                    "PASS: authenticated Streamable HTTP MCP, six tools discovered, incident search returned successfully."
                )


if __name__ == "__main__":
    asyncio.run(main())
