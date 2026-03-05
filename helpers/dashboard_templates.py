"""Dashboard HTML rendering with mobile-first responsive design."""

import json
from typing import Dict, List


def generate_dashboard_html(dashboard: dict, widgets: list, widget_data: dict = None) -> str:
    """
    Generate a self-contained HTML page for a dashboard.
    
    Mobile-first CSS grid:
    - Mobile (<768px): single column, widgets stack vertically
    - Tablet (768-1024px): 2 columns
    - Desktop (>1024px): 4 columns
    
    Args:
        dashboard: Dashboard dict from queries
        widgets: List of widget dicts from queries
        widget_data: Optional dict mapping widget_id -> data dict
        
    Returns:
        Complete HTML page as string
    """
    dashboard_name = dashboard.get('name', 'Dashboard')
    dashboard_desc = dashboard.get('description', '')
    
    # Render all widgets
    widget_cards = []
    for widget in widgets:
        widget_id = widget.get('id')
        data = widget_data.get(widget_id) if widget_data else None
        widget_html = _render_widget_card(widget, data)
        widget_cards.append(widget_html)
    
    widgets_html = '\n'.join(widget_cards)
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{dashboard_name} - SuperFinance</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <script src="https://unpkg.com/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: #0f0f23;
            color: #e2e8f0;
            line-height: 1.6;
        }}
        
        .header {{
            background: #1a1a2e;
            padding: 20px;
            border-bottom: 1px solid #2a2a4a;
        }}
        
        .header h1 {{
            font-size: 24px;
            font-weight: 600;
            margin-bottom: 4px;
        }}
        
        .header p {{
            color: #94a3b8;
            font-size: 14px;
        }}
        
        .dashboard-grid {{
            display: grid;
            gap: 16px;
            padding: 16px;
            grid-template-columns: 1fr;
        }}
        
        @media (min-width: 768px) {{
            .dashboard-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}
        }}
        
        @media (min-width: 1024px) {{
            .dashboard-grid {{
                grid-template-columns: repeat(4, 1fr);
            }}
        }}
        
        .widget-card {{
            background: #1a1a2e;
            border-radius: 12px;
            border: 1px solid #2a2a4a;
            overflow: hidden;
            min-height: 300px;
            display: flex;
            flex-direction: column;
        }}
        
        .widget-card.w-2 {{ grid-column: span 2; }}
        .widget-card.w-3 {{ grid-column: span 3; }}
        .widget-card.w-4 {{ grid-column: span 4; }}
        
        @media (max-width: 767px) {{
            .widget-card.w-2, .widget-card.w-3, .widget-card.w-4 {{
                grid-column: span 1;
            }}
        }}
        
        .widget-header {{
            padding: 16px;
            border-bottom: 1px solid #2a2a4a;
        }}
        
        .widget-title {{
            font-size: 16px;
            font-weight: 600;
            color: #e2e8f0;
        }}
        
        .widget-content {{
            padding: 16px;
            flex: 1;
            overflow: auto;
        }}
        
        .chart-container {{
            width: 100%;
            height: 100%;
            min-height: 250px;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #2a2a4a;
        }}
        
        th {{
            color: #94a3b8;
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
        }}
        
        .positive {{
            color: #4ade80;
        }}
        
        .negative {{
            color: #f87171;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{dashboard_name}</h1>
        {f'<p>{dashboard_desc}</p>' if dashboard_desc else ''}
    </div>
    
    <div class="dashboard-grid">
        {widgets_html}
    </div>
</body>
</html>"""
    
    return html


def _render_widget_card(widget: dict, data: dict = None) -> str:
    """Render a single widget card."""
    widget_type = widget['widget_type']
    widget_id = widget.get('id', '')
    title = widget.get('title') or _default_title(widget_type)
    width = widget.get('width', 1)
    config_str = widget.get('config', '{}')
    
    try:
        config = json.loads(config_str)
    except:
        config = {}
    
    # Render widget content based on type
    content = _render_widget_content(widget_type, widget_id, config, data)
    
    width_class = f' w-{width}' if width > 1 else ''
    
    return f"""
    <div class="widget-card{width_class}">
        <div class="widget-header">
            <div class="widget-title">{title}</div>
        </div>
        <div class="widget-content">
            {content}
        </div>
    </div>"""


def _default_title(widget_type: str) -> str:
    """Get default title for widget type."""
    titles = {
        'stock_chart': 'Stock Chart',
        'portfolio_pie': 'Portfolio Allocation',
        'portfolio_treemap': 'Portfolio Treemap',
        'analysis_table': 'Analysis',
        'correlation_heatmap': 'Correlation Matrix',
        'holdings_list': 'Holdings',
        'performance_chart': 'Performance'
    }
    return titles.get(widget_type, widget_type.replace('_', ' ').title())


def _render_widget_content(widget_type: str, widget_id: str, config: dict, data: dict = None) -> str:
    """Route to specific widget renderer."""
    renderers = {
        'stock_chart': render_stock_chart_widget,
        'portfolio_pie': render_portfolio_pie_widget,
        'portfolio_treemap': render_portfolio_treemap_widget,
        'analysis_table': render_analysis_table_widget,
        'correlation_heatmap': render_correlation_heatmap_widget,
        'holdings_list': render_holdings_list_widget,
        'performance_chart': render_performance_chart_widget
    }
    
    renderer = renderers.get(widget_type)
    if renderer:
        return renderer(widget_id, config, data)
    
    return f'<p>Unknown widget type: {widget_type}</p>'


def render_stock_chart_widget(widget_id: str, config: dict, data: dict = None) -> str:
    """TradingView lightweight chart embed."""
    tickers = config.get('tickers', 'AAPL')
    period = config.get('period', '1y')
    chart_type = config.get('chart_type', 'candlestick')
    
    # Use real data if available
    chart_id = f"chart-{widget_id}"
    
    if data and "charts" in data:
        charts = data["charts"]
        # Use first ticker's data
        chart_data = list(charts.values())[0] if charts else []
    else:
        # Fallback sample data
        chart_data = [
            {"time": "2024-01-01", "open": 150, "high": 155, "low": 148, "close": 153},
            {"time": "2024-01-02", "open": 153, "high": 158, "low": 152, "close": 157},
            {"time": "2024-01-03", "open": 157, "high": 160, "low": 155, "close": 156},
        ]
    
    return f"""
    <div id="{chart_id}" class="chart-container"></div>
    <script>
        (function() {{
            const chart = LightweightCharts.createChart(
                document.getElementById('{chart_id}'),
                {{
                    layout: {{
                        background: {{ color: '#1a1a2e' }},
                        textColor: '#e2e8f0',
                    }},
                    grid: {{
                        vertLines: {{ color: '#2a2a4a' }},
                        horzLines: {{ color: '#2a2a4a' }},
                    }},
                    width: document.getElementById('chart-{id(config)}').clientWidth,
                    height: 250,
                }}
            );
            
            const series = chart.addCandlestickSeries({{
                upColor: '#4ade80',
                downColor: '#f87171',
                borderVisible: false,
                wickUpColor: '#4ade80',
                wickDownColor: '#f87171',
            }});
            
            const data = {json.dumps(chart_data)};
            
            series.setData(data);
            chart.timeScale().fitContent();
        }})();
    </script>
    <p style="margin-top: 12px; color: #94a3b8; font-size: 14px;">
        Tickers: {tickers} | Period: {period}
    </p>
    """


def render_portfolio_pie_widget(widget_id: str, config: dict, data: dict = None) -> str:
    """Plotly pie/donut chart of portfolio allocation."""
    group_by = config.get('group_by', 'ticker')
    
    # Use real data if available
    if data and "labels" in data and "values" in data:
        labels = data["labels"]
        values = data["values"]
    else:
        # Fallback sample data
        labels = ['AAPL', 'MSFT', 'GOOG', 'AMZN']
        values = [30, 25, 25, 20]
    
    chart_id = f"pie-{widget_id}"
    
    return f"""
    <div id="{chart_id}" class="chart-container"></div>
    <script>
        (function() {{
            const data = [{{
                labels: {json.dumps(labels)},
                values: {json.dumps(values)},
                type: 'pie',
                hole: 0.4,
                marker: {{
                    colors: ['#4ade80', '#60a5fa', '#a78bfa', '#f87171']
                }},
                textfont: {{ color: '#e2e8f0' }}
            }}];
            
            const layout = {{
                paper_bgcolor: '#1a1a2e',
                plot_bgcolor: '#1a1a2e',
                font: {{ color: '#e2e8f0' }},
                showlegend: true,
                legend: {{
                    font: {{ color: '#e2e8f0' }}
                }},
                margin: {{ t: 0, b: 0, l: 0, r: 0 }}
            }};
            
            Plotly.newPlot('{chart_id}', data, layout, {{
                responsive: true,
                displayModeBar: false
            }});
        }})();
    </script>
    """


def render_portfolio_treemap_widget(widget_id: str, config: dict, data: dict = None) -> str:
    """Plotly treemap of portfolio."""
    group_by = config.get('group_by', 'ticker')
    
    # Use real data if available
    if data and "labels" in data and "parents" in data and "values" in data:
        labels = data["labels"]
        parents = data["parents"]
        values = data["values"]
    else:
        # Fallback sample data
        labels = ['Portfolio', 'Tech', 'Finance', 'AAPL', 'MSFT', 'JPM', 'GS']
        parents = ['', 'Portfolio', 'Portfolio', 'Tech', 'Tech', 'Finance', 'Finance']
        values = [0, 0, 0, 30, 25, 25, 20]
    
    chart_id = f"treemap-{widget_id}"
    
    return f"""
    <div id="{chart_id}" class="chart-container"></div>
    <script>
        (function() {{
            const data = [{{
                type: 'treemap',
                labels: {json.dumps(labels)},
                parents: {json.dumps(parents)},
                values: {json.dumps(values)},
                textfont: {{ color: '#e2e8f0' }},
                marker: {{
                    colors: ['#1a1a2e', '#4ade80', '#60a5fa', '#4ade80', '#4ade80', '#60a5fa', '#60a5fa']
                }}
            }}];
            
            const layout = {{
                paper_bgcolor: '#1a1a2e',
                plot_bgcolor: '#1a1a2e',
                margin: {{ t: 0, b: 0, l: 0, r: 0 }}
            }};
            
            Plotly.newPlot('{chart_id}', data, layout, {{
                responsive: true,
                displayModeBar: false
            }});
        }})();
    </script>
    """


def render_analysis_table_widget(widget_id: str, config: dict, data: dict = None) -> str:
    """Table of analytics data (risk, ratios, technicals)."""
    tickers = config.get('tickers', 'AAPL,MSFT')
    metrics = config.get('metrics', 'risk')
    
    # Sample data
    return """
    <table>
        <thead>
            <tr>
                <th>Ticker</th>
                <th>Price</th>
                <th>Change</th>
                <th>Volume</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>AAPL</td>
                <td>$173.50</td>
                <td class="positive">+2.3%</td>
                <td>45.2M</td>
            </tr>
            <tr>
                <td>MSFT</td>
                <td>$405.20</td>
                <td class="negative">-0.8%</td>
                <td>23.1M</td>
            </tr>
        </tbody>
    </table>
    """


def render_correlation_heatmap_widget(widget_id: str, config: dict, data: dict = None) -> str:
    """Plotly heatmap of correlation matrix."""
    period = config.get('period', '1y')
    
    # Use real data if available
    if data and "tickers" in data and "z" in data and data["tickers"]:
        tickers = data["tickers"]
        z = data["z"]
    else:
        # Fallback sample data
        tickers = ['AAPL', 'MSFT', 'GOOG', 'AMZN']
        z = [
            [1.0, 0.8, 0.7, 0.6],
            [0.8, 1.0, 0.75, 0.65],
            [0.7, 0.75, 1.0, 0.8],
            [0.6, 0.65, 0.8, 1.0]
        ]
    
    chart_id = f"heatmap-{widget_id}"
    
    return f"""
    <div id="{chart_id}" class="chart-container"></div>
    <script>
        (function() {{
            const data = [{{
                z: {json.dumps(z)},
                x: {json.dumps(tickers)},
                y: {json.dumps(tickers)},
                type: 'heatmap',
                colorscale: [
                    [0, '#f87171'],
                    [0.5, '#fbbf24'],
                    [1, '#4ade80']
                ],
                showscale: true
            }}];
            
            const layout = {{
                paper_bgcolor: '#1a1a2e',
                plot_bgcolor: '#1a1a2e',
                font: {{ color: '#e2e8f0' }},
                xaxis: {{ color: '#e2e8f0' }},
                yaxis: {{ color: '#e2e8f0' }},
                margin: {{ t: 20, b: 40, l: 40, r: 0 }}
            }};
            
            Plotly.newPlot('{chart_id}', data, layout, {{
                responsive: true,
                displayModeBar: false
            }});
        }})();
    </script>
    """


def render_holdings_list_widget(widget_id: str, config: dict, data: dict = None) -> str:
    """Table of current holdings with prices."""
    if data and "holdings" in data:
        holdings = data["holdings"]
    else:
        # Fallback sample data
        holdings = [
            {
                "symbol": "AAPL",
                "quantity": 100,
                "current_price": 173.50,
                "market_value": 17350,
                "return_pct": 12.5
            },
            {
                "symbol": "MSFT",
                "quantity": 50,
                "current_price": 405.20,
                "market_value": 20260,
                "return_pct": 8.3
            },
            {
                "symbol": "GOOG",
                "quantity": 25,
                "current_price": 142.80,
                "market_value": 3570,
                "return_pct": -3.2
            }
        ]
    
    rows_html = ""
    for h in holdings:
        return_cls = "positive" if (h.get("return_pct") or 0) >= 0 else "negative"
        return_str = f"{h['return_pct']:+.1f}%" if h.get("return_pct") is not None else "—"
        price_str = f"${h['current_price']:,.2f}" if h.get("current_price") else "—"
        value_str = f"${h['market_value']:,.2f}" if h.get("market_value") else "—"
        qty_str = f"{h['quantity']:,.2f}" if h.get("quantity") else "—"
        
        rows_html += f"""
            <tr>
                <td><strong>{h['symbol']}</strong></td>
                <td>{qty_str}</td>
                <td>{price_str}</td>
                <td>{value_str}</td>
                <td class="{return_cls}">{return_str}</td>
            </tr>"""
    
    return f"""
    <table>
        <thead>
            <tr>
                <th>Symbol</th>
                <th>Shares</th>
                <th>Price</th>
                <th>Value</th>
                <th>Return</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
    """


def render_performance_chart_widget(widget_id: str, config: dict, data: dict = None) -> str:
    """Line chart of historical performance."""
    tickers = config.get('tickers', 'AAPL,SPY')
    period = config.get('period', '1y')
    
    # Use real data if available
    if data and "series" in data and data["series"]:
        # Use first series
        series_data = list(data["series"].values())[0]
        dates = [p["date"] for p in series_data]
        values = [p["value"] * 100 for p in series_data]  # Convert to percentage
    else:
        # Fallback sample data
        dates = ['2024-01-01', '2024-02-01', '2024-03-01', '2024-04-01']
        values = [0, 5, 10, 15]
    
    chart_id = f"perf-{widget_id}"
    
    return f"""
    <div id="{chart_id}" class="chart-container"></div>
    <script>
        (function() {{
            const trace = {{
                x: {json.dumps(dates)},
                y: {json.dumps(values)},
                type: 'scatter',
                mode: 'lines',
                line: {{ color: '#4ade80', width: 2 }},
                fill: 'tozeroy',
                fillcolor: 'rgba(74, 222, 128, 0.1)'
            }};
            
            const layout = {{
                paper_bgcolor: '#1a1a2e',
                plot_bgcolor: '#1a1a2e',
                font: {{ color: '#e2e8f0' }},
                xaxis: {{
                    color: '#e2e8f0',
                    gridcolor: '#2a2a4a'
                }},
                yaxis: {{
                    color: '#e2e8f0',
                    gridcolor: '#2a2a4a',
                    tickformat: '.1%'
                }},
                margin: {{ t: 20, b: 40, l: 50, r: 20 }},
                showlegend: false
            }};
            
            Plotly.newPlot('{chart_id}', [trace], layout, {{
                responsive: true,
                displayModeBar: false
            }});
        }})();
    </script>
    <p style="margin-top: 12px; color: #94a3b8; font-size: 14px;">
        Tickers: {tickers} | Period: {period}
    </p>
    """
