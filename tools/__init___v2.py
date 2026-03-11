"""Tool modules for SuperFinance MCP server - V2 Consolidated."""

from tools.v2_cache import register_cache_v2
from tools.v2_token import register_token_v2
from tools.v2_discover import register_discover_v2
from tools.v2_classify import register_classify_v2
from tools.v2_liability import register_liability_v2
from tools.v2_account import register_account_v2
from tools.v2_holding import register_holding_v2
from tools.v2_transaction import register_transaction_v2
from tools.v2_dashboard import register_dashboard_v2
from tools.v2_market import register_market_v2
from tools.v2_options import register_options_v2
from tools.v2_analyze import register_analyze_v2
from tools.v2_portfolio import register_portfolio_v2
from tools.v2_sync import register_sync_v2

# Keep these from original (chart and calculate are standalone)
from tools.visualization import register_visualization_tools
from tools.yahoo_finance import register_yahoo_finance_tools  # For calculate tool


def register_all_tools_v2(server):
    """Register all consolidated V2 tools with the FastMCP server."""
    # Consolidated tools
    register_cache_v2(server)
    register_token_v2(server)
    register_discover_v2(server)
    register_classify_v2(server)
    register_liability_v2(server)
    register_account_v2(server)
    register_holding_v2(server)
    register_transaction_v2(server)
    register_dashboard_v2(server)
    register_market_v2(server)
    register_options_v2(server)
    register_analyze_v2(server)
    register_portfolio_v2(server)
    register_sync_v2(server)
    
    # Keep standalone tools (chart is already good)
    register_visualization_tools(server)
    
    # Register calculate tool from yahoo_finance (it's standalone)
    from tools.yahoo_finance import register_yahoo_finance_tools
    # We need just the calculate tool, but the function registers all
    # Let's extract it
    @server.tool()
    def calculate(expression: str) -> str:
        """
        Execute Python code for calculations and data analysis.

        Useful for:
        - Mathematical calculations
        - Financial analysis with stock data
        - Data manipulation with pandas/numpy
        - Statistical computations

        Available libraries: math, numpy (as np), pandas (as pd), json

        Args:
            expression: Python code to execute. Can include multiple lines.
                       The last expression will be returned.
                       Use print() for intermediate output.

        Returns:
            String containing the result and any printed output
        """
        import math
        import sys
        from io import StringIO
        import numpy as np
        import pandas as pd
        import json
        
        try:
            safe_globals = {
                '__builtins__': {
                    'abs': abs, 'round': round, 'min': min, 'max': max,
                    'sum': sum, 'len': len, 'range': range, 'enumerate': enumerate,
                    'zip': zip, 'map': map, 'filter': filter, 'sorted': sorted,
                    'list': list, 'dict': dict, 'set': set, 'tuple': tuple,
                    'str': str, 'int': int, 'float': float, 'bool': bool,
                    'print': print, 'True': True, 'False': False, 'None': None,
                },
                'math': math,
                'np': np,
                'pd': pd,
                'json': json,
            }

            old_stdout = sys.stdout
            sys.stdout = StringIO()

            local_vars = {}
            exec(expression, safe_globals, local_vars)

            output = sys.stdout.getvalue()
            sys.stdout = old_stdout

            lines = expression.strip().split('\n')
            last_line = lines[-1].strip() if lines else ''

            result_parts = []
            if output:
                result_parts.append(f"Output:\n{output}")

            if last_line and '=' not in last_line and not last_line.startswith(('import', 'from', 'def', 'class', 'if', 'for', 'while')):
                try:
                    result_value = eval(last_line, safe_globals, local_vars)
                    if result_value is not None:
                        result_parts.append(f"Result:\n{result_value}")
                except:
                    pass

            return '\n\n'.join(result_parts) if result_parts else "Code executed successfully (no output)"

        except Exception as e:
            return f"Error executing code: {type(e).__name__}: {str(e)}"


__all__ = ["register_all_tools_v2"]
