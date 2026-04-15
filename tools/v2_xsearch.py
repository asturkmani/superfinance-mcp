"""X/Twitter search tool via xAI Grok API."""

import json
import os
from typing import Optional

import httpx


def register_xsearch_v2(server):
    """Register X search tool."""

    @server.tool()
    def x_search(
        query: str,
        handles: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> str:
        """
        Search X/Twitter posts via Grok.

        Returns a synthesized summary of relevant X posts matching the query.
        Useful for market sentiment, breaking news, analyst views, and tracking specific accounts.

        Args:
            query: What to search for (e.g. "AAPL earnings reaction", "Fed rate decision views")
            handles: Comma-separated X handles to filter (max 10, e.g. "unusual_whales,DeItaone,zaboratory"). Omit for broad search.
            from_date: Start date in YYYY-MM-DD format (e.g. "2026-04-01")
            to_date: End date in YYYY-MM-DD format (e.g. "2026-04-15")

        Examples:
            x_search(query="What are traders saying about NVDA earnings?")
            x_search(query="Latest market views", handles="unusual_whales,DeItaone", from_date="2026-04-10")
            x_search(query="Fed rate decision", from_date="2026-04-01", to_date="2026-04-15")
        """
        api_key = os.getenv("XAI_API_KEY")
        if not api_key:
            return json.dumps({
                "error": "XAI_API_KEY not configured",
                "message": "Set XAI_API_KEY environment variable to use X search",
            }, indent=2)

        # Build the x_search tool config
        tool_config = {"type": "x_search"}

        if handles:
            handle_list = [h.strip().lstrip("@") for h in handles.split(",") if h.strip()]
            if handle_list:
                tool_config["allowed_x_handles"] = handle_list[:10]

        if from_date:
            tool_config["from_date"] = from_date
        if to_date:
            tool_config["to_date"] = to_date

        payload = {
            "model": "grok-4-fast",
            "input": [
                {"role": "user", "content": query}
            ],
            "tools": [tool_config],
        }

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    "https://api.x.ai/v1/responses",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}",
                    },
                    json=payload,
                )

            if resp.status_code != 200:
                return json.dumps({
                    "error": f"xAI API returned {resp.status_code}",
                    "detail": resp.text[:500],
                }, indent=2)

            data = resp.json()

            # Extract the text response from the output
            text = None
            citations = []
            for item in data.get("output", []):
                if item.get("type") == "message":
                    for content in item.get("content", []):
                        if content.get("type") == "output_text":
                            text = content.get("text")
                            citations = content.get("annotations", [])

            if not text:
                return json.dumps({
                    "error": "No response from Grok",
                    "raw": data,
                }, indent=2)

            # Extract citation URLs
            sources = []
            for c in citations:
                if c.get("type") == "url_citation":
                    sources.append({
                        "title": c.get("title"),
                        "url": c.get("url"),
                    })

            result = {
                "success": True,
                "query": query,
                "summary": text,
            }
            if sources:
                result["sources"] = sources
            if handles:
                result["filtered_handles"] = tool_config.get("allowed_x_handles")
            if from_date or to_date:
                result["date_range"] = {
                    "from": from_date,
                    "to": to_date,
                }

            return json.dumps(result, indent=2)

        except httpx.TimeoutException:
            return json.dumps({"error": "Request to xAI API timed out"}, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
