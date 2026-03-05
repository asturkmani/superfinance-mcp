"""Dashboard management tools."""

import json
import os
from typing import Optional

from db import queries
from helpers.user_context import get_current_user_id


def get_base_url() -> str:
    """Get the base URL for dashboard links."""
    # In production (Fly.io), use the app URL
    if os.getenv("FLY_APP_NAME"):
        return "https://joinvault.xyz"
    
    # In HTTP mode, use localhost with PORT
    port = os.getenv("PORT")
    if port:
        return f"http://localhost:{port}"
    
    # Fallback for local dev
    return "http://localhost:8080"


def register_dashboard_tools(server):
    """Register dashboard tools with the server."""

    @server.tool()
    def create_dashboard(name: str, description: str = None, layout: str = "grid") -> str:
        """
        Create a new dashboard.
        
        Args:
            name: Dashboard name
            description: Optional description
            layout: Layout type ('grid' or 'stack'), default 'grid'
        
        Returns:
            JSON with dashboard ID, name, and URL
        """
        try:
            user_id = get_current_user_id()
            return _create_dashboard_impl(user_id, name, description, layout)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @server.tool()
    def list_dashboards() -> str:
        """
        List all dashboards for the current user.
        
        Returns:
            JSON array of dashboards with id, name, description, layout, created_at
        """
        try:
            user_id = get_current_user_id()
            return _list_dashboards_impl(user_id)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @server.tool()
    def add_widget(
        dashboard_id: str,
        widget_type: str,
        config: str = "{}",
        title: str = None,
        width: int = 1,
        height: int = 1
    ) -> str:
        """
        Add a widget to a dashboard.
        
        Widget types:
        - stock_chart: Price chart. Config: {"tickers": "AAPL", "period": "1y", "chart_type": "candlestick"}
        - portfolio_pie: Portfolio allocation pie chart. Config: {"group_by": "category"}
        - portfolio_treemap: Portfolio treemap. Config: {"group_by": "ticker"}
        - analysis_table: Analytics data table. Config: {"tickers": "AAPL,MSFT", "metrics": "risk"}
        - correlation_heatmap: Correlation matrix. Config: {"period": "1y"}
        - holdings_list: Current holdings table. Config: {"account_id": null}
        - performance_chart: Historical performance. Config: {"tickers": "AAPL,SPY", "period": "1y"}
        
        Args:
            dashboard_id: Dashboard ID
            widget_type: Type of widget (see above)
            config: JSON string with widget configuration
            title: Optional widget title
            width: Grid width (1-4 columns, default 1)
            height: Grid height (default 1)
        
        Returns:
            JSON with widget details
        """
        try:
            return _add_widget_impl(dashboard_id, widget_type, config, title, width, height)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @server.tool()
    def remove_widget(widget_id: str) -> str:
        """
        Remove a widget from a dashboard.
        
        Args:
            widget_id: Widget ID
        
        Returns:
            JSON with success status
        """
        try:
            success = queries.delete_widget(widget_id)
            if success:
                return json.dumps({"success": True, "message": "Widget removed"}, indent=2)
            else:
                return json.dumps({"success": False, "error": "Widget not found"}, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @server.tool()
    def update_widget(
        widget_id: str, 
        title: str = None, 
        config: str = None, 
        width: int = None, 
        height: int = None
    ) -> str:
        """
        Update a widget's config, title, or size.
        
        Args:
            widget_id: Widget ID
            title: New title (optional)
            config: New JSON config (optional)
            width: New width (optional)
            height: New height (optional)
        
        Returns:
            JSON with updated widget details
        """
        try:
            success = queries.update_widget(widget_id, title, config, None, width, height)
            if success:
                widget = queries.get_widget(widget_id)
                return json.dumps(widget, indent=2)
            else:
                return json.dumps({"error": "Widget not found or no changes"}, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @server.tool()
    def delete_dashboard(dashboard_id: str) -> str:
        """
        Delete a dashboard and all its widgets.
        
        Args:
            dashboard_id: Dashboard ID
        
        Returns:
            JSON with success status
        """
        try:
            success = queries.delete_dashboard(dashboard_id)
            if success:
                return json.dumps({"success": True, "message": "Dashboard deleted"}, indent=2)
            else:
                return json.dumps({"success": False, "error": "Dashboard not found"}, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @server.tool()
    def get_dashboard_url(dashboard_id: str) -> str:
        """
        Get the URL for a dashboard.
        
        Args:
            dashboard_id: Dashboard ID
        
        Returns:
            JSON with dashboard URL
        """
        try:
            dashboard = queries.get_dashboard(dashboard_id)
            if not dashboard:
                return json.dumps({"error": "Dashboard not found"}, indent=2)
            
            url = f"{get_base_url()}/d/{dashboard_id}"
            return json.dumps({
                "id": dashboard_id,
                "name": dashboard['name'],
                "url": url
            }, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)


# Implementation functions (for testing)
def _create_dashboard_impl(user_id: str, name: str, description: Optional[str], layout: str) -> str:
    """Implementation of create_dashboard (exported for testing)."""
    dashboard_id = queries.create_dashboard(user_id, name, description, layout)
    url = f"{get_base_url()}/d/{dashboard_id}"
    
    return json.dumps({
        "id": dashboard_id,
        "name": name,
        "url": url
    }, indent=2)


def _list_dashboards_impl(user_id: str) -> str:
    """Implementation of list_dashboards (exported for testing)."""
    dashboards = queries.list_dashboards(user_id)
    return json.dumps(dashboards, indent=2)


def _add_widget_impl(
    dashboard_id: str,
    widget_type: str,
    config: str,
    title: Optional[str],
    width: int,
    height: int
) -> str:
    """Implementation of add_widget (exported for testing)."""
    # Validate JSON config
    try:
        json.loads(config)
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON in config parameter")
    
    # Validate widget type
    valid_types = [
        'stock_chart', 'portfolio_pie', 'portfolio_treemap',
        'analysis_table', 'correlation_heatmap', 'holdings_list',
        'performance_chart'
    ]
    if widget_type not in valid_types:
        raise ValueError(f"Invalid widget_type. Must be one of: {', '.join(valid_types)}")
    
    # Add widget
    widget_id = queries.add_widget(
        dashboard_id=dashboard_id,
        widget_type=widget_type,
        config=config,
        title=title,
        width=width,
        height=height
    )
    
    # Return created widget
    widget = queries.get_widget(widget_id)
    return json.dumps(widget, indent=2)
