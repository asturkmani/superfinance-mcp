"""Consolidated options tool."""

import json
import yfinance as yf


def register_options_v2(server):
    """Register consolidated options tool."""

    @server.tool()
    def options(
        action: str,
        ticker: str,
        expiration_date: str = None,
        option_type: str = "calls"
    ) -> str:
        """
        Get options data from Yahoo Finance.

        Actions:
        - chain: Get option chain for a specific expiration
        - analyze: Get options summary with all expirations and Greeks

        Args:
            action: Action to perform (chain|analyze)
            ticker: Ticker symbol (e.g., "AAPL")
            expiration_date: Expiration date for chain action (YYYY-MM-DD format)
            option_type: Type for chain action - calls or puts (default: calls)

        Returns:
            JSON with options data

        Examples:
            options(action="chain", ticker="AAPL", expiration_date="2024-06-21", option_type="calls")
            options(action="analyze", ticker="AAPL")

        Note: If expiration_date is not provided for chain action, returns available expiration dates.
        """
        try:
            ticker = ticker.strip().upper()
            company = yf.Ticker(ticker)

            if action == "chain":
                if not expiration_date:
                    return json.dumps({
                        "ticker": ticker,
                        "available_expirations": list(company.options),
                        "message": "Provide expiration_date parameter to get option chain"
                    }, indent=2)

                if expiration_date not in company.options:
                    return json.dumps({
                        "error": f"No options available for {expiration_date}",
                        "available_expirations": list(company.options)
                    }, indent=2)

                if option_type not in ["calls", "puts"]:
                    return json.dumps({
                        "error": "Invalid option_type. Use 'calls' or 'puts'."
                    }, indent=2)

                option_chain = company.option_chain(expiration_date)
                if option_type == "calls":
                    return option_chain.calls.to_json(orient="records", date_format="iso")
                else:
                    return option_chain.puts.to_json(orient="records", date_format="iso")

            elif action == "analyze":
                expirations = list(company.options)
                if not expirations:
                    return json.dumps({"ticker": ticker, "message": "No options data available"})

                info = company.info
                current_price = info.get("regularMarketPrice") or info.get("currentPrice")

                result = {
                    "ticker": ticker,
                    "current_price": current_price,
                    "expirations": expirations,
                    "chains": {}
                }

                # Get chains for first few expirations to keep response manageable
                for exp in expirations[:3]:
                    chain = company.option_chain(exp)
                    calls_summary = {
                        "count": len(chain.calls),
                        "data": json.loads(chain.calls.to_json(orient="records", date_format="iso"))
                    }
                    puts_summary = {
                        "count": len(chain.puts),
                        "data": json.loads(chain.puts.to_json(orient="records", date_format="iso"))
                    }
                    result["chains"][exp] = {"calls": calls_summary, "puts": puts_summary}

                return json.dumps(result, indent=2)

            else:
                return json.dumps({
                    "error": f"Invalid action: {action}",
                    "valid_actions": ["chain", "analyze"]
                }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
