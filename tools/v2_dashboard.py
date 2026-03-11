"""Consolidated dashboard management tool."""

import json
import os
from typing import Optional

from db import queries
from helpers.user_context import get_current_user_id


def get_base_url() -> str:
    """Get the base URL for dashboard links."""
    if os.getenv("FLY_APP_NAME"):
        return "https://joinvault.xyz"
    port = os.getenv("PORT")
    if port:
        return f"http://localhost:{port}"
    return "http://localhost:8080"


def register_dashboard_v2(server):
    """Register consolidated dashboard tool."""

    @server.tool()
    def dashboard(
        action: str,
        dashboard_id: str = None,
        widget_id: str = None,
        name: str = None,
        description: str = None,
        layout: str = "grid",
        widget_type: str = None,
        config: str = "{}",
        title: str = None,
        width: int = 1,
        height: int = 1
    ) -> str:
        """
        Manage custom dashboards with widgets.

        Actions:
        - create: Create a new dashboard
        - list: List all dashboards
        - get: Get dashboard URL
        - delete: Delete a dashboard
        - add_widget: Add a widget to a dashboard
        - update_widget: Update widget config/title/size
        - remove_widget: Remove a widget

        Args:
            action: Action to perform (create|list|get|delete|add_widget|update_widget|remove_widget)
            dashboard_id: Dashboard ID (for get/delete/add_widget)
            widget_id: Widget ID (for update_widget/remove_widget)
            name: Dashboard name (for create)
            description: Dashboard description (for create)
            layout: Dashboard layout - grid or stack (for create)
            widget_type: Widget type (for add_widget) - stock_chart, portfolio_pie, portfolio_treemap, analysis_table, correlation_heatmap, holdings_list, performance_chart
            config: Widget configuration JSON string (for add_widget/update_widget)
            title: Widget title (for add_widget/update_widget)
            width: Widget width in grid columns (for add_widget/update_widget)
            height: Widget height in grid rows (for add_widget/update_widget)

        Returns:
            JSON with dashboard/widget data or operation result

        Examples:
            dashboard(action="create", name="My Portfolio", description="Main dashboard")
            dashboard(action="list")
            dashboard(action="get", dashboard_id="dash_123")
            dashboard(action="add_widget", dashboard_id="dash_123", widget_type="portfolio_pie", config='{"group_by": "category"}')
            dashboard(action="update_widget", widget_id="wdg_123", title="New Title")
            dashboard(action="remove_widget", widget_id="wdg_123")
            dashboard(action="delete", dashboard_id="dash_123")
        """
        try:
            user_id = get_current_user_id()

            if action == "create":
                if not name:
                    return json.dumps({
                        "error": "name required for create action"
                    }, indent=2)

                dashboard_id = queries.create_dashboard(user_id, name, description, layout)
                url = f"{get_base_url()}/d/{dashboard_id}"
                
                return json.dumps({
                    "id": dashboard_id,
                    "name": name,
                    "url": url
                }, indent=2)

            elif action == "list":
                dashboards = queries.list_dashboards(user_id)
                return json.dumps(dashboards, indent=2)

            elif action == "get":
                if not dashboard_id:
                    return json.dumps({
                        "error": "dashboard_id required for get action"
                    }, indent=2)

                dashboard = queries.get_dashboard(dashboard_id)
                if not dashboard:
                    return json.dumps({"error": "Dashboard not found"}, indent=2)
                
                url = f"{get_base_url()}/d/{dashboard_id}"
                return json.dumps({
                    "id": dashboard_id,
                    "name": dashboard['name'],
                    "url": url
                }, indent=2)

            elif action == "delete":
                if not dashboard_id:
                    return json.dumps({
                        "error": "dashboard_id required for delete action"
                    }, indent=2)

                success = queries.delete_dashboard(dashboard_id)
                if success:
                    return json.dumps({
                        "success": True,
                        "message": "Dashboard deleted"
                    }, indent=2)
                else:
                    return json.dumps({
                        "success": False,
                        "error": "Dashboard not found"
                    }, indent=2)

            elif action == "add_widget":
                if not dashboard_id or not widget_type:
                    return json.dumps({
                        "error": "dashboard_id and widget_type required for add_widget action"
                    }, indent=2)

                # Validate JSON config
                try:
                    json.loads(config)
                except json.JSONDecodeError:
                    return json.dumps({"error": "Invalid JSON in config parameter"}, indent=2)
                
                # Validate widget type
                valid_types = [
                    'stock_chart', 'portfolio_pie', 'portfolio_treemap',
                    'analysis_table', 'correlation_heatmap', 'holdings_list',
                    'performance_chart'
                ]
                if widget_type not in valid_types:
                    return json.dumps({
                        "error": f"Invalid widget_type. Must be one of: {', '.join(valid_types)}"
                    }, indent=2)
                
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

            elif action == "update_widget":
                if not widget_id:
                    return json.dumps({
                        "error": "widget_id required for update_widget action"
                    }, indent=2)

                success = queries.update_widget(widget_id, title, config, None, width, height)
                if success:
                    widget = queries.get_widget(widget_id)
                    return json.dumps(widget, indent=2)
                else:
                    return json.dumps({
                        "error": "Widget not found or no changes"
                    }, indent=2)

            elif action == "remove_widget":
                if not widget_id:
                    return json.dumps({
                        "error": "widget_id required for remove_widget action"
                    }, indent=2)

                success = queries.delete_widget(widget_id)
                if success:
                    return json.dumps({
                        "success": True,
                        "message": "Widget removed"
                    }, indent=2)
                else:
                    return json.dumps({
                        "success": False,
                        "error": "Widget not found"
                    }, indent=2)

            else:
                return json.dumps({
                    "error": f"Invalid action: {action}",
                    "valid_actions": ["create", "list", "get", "delete", "add_widget", "update_widget", "remove_widget"]
                }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
