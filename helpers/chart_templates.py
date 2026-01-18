"""HTML template generators for chart tools."""

import json as json_module
from typing import Optional


def generate_tradingview_chart_html(
    tickers: list[str],
    interval: str = "D",
    theme: str = "dark",
    show_details: bool = True,
) -> str:
    """
    Generate HTML page with TradingView Advanced Chart widget.

    Args:
        tickers: List of ticker symbols to display
        interval: Chart interval (1, 5, 15, 30, 60, D, W, M)
        theme: "dark" or "light"
        show_details: Whether to show volume and info panel

    Returns:
        Complete HTML page string
    """
    # TradingView uses different symbol format
    symbols_json = ", ".join([f'"{ticker}"' for ticker in tickers])

    # Build comparison symbols for multi-ticker
    comparison_symbols = ""
    if len(tickers) > 1:
        comparison_symbols = ", ".join([f'"{ticker}"' for ticker in tickers[1:]])

    # Primary symbol (first one)
    primary_symbol = tickers[0] if tickers else "AAPL"

    # Widget configuration
    hide_volume = "false" if show_details else "true"
    hide_side_toolbar = "false" if show_details else "true"

    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stock Chart - {", ".join(tickers)}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        html, body {{
            width: 100%;
            height: 100%;
            background: {"#1e1e1e" if theme == "dark" else "#ffffff"};
        }}
        .tradingview-widget-container {{
            width: 100%;
            height: 100%;
        }}
    </style>
</head>
<body>
    <div class="tradingview-widget-container">
        <div id="tradingview_chart" style="width: 100%; height: 100%;"></div>
    </div>
    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
    <script type="text/javascript">
        new TradingView.widget({{
            "autosize": true,
            "symbol": "{primary_symbol}",
            "interval": "{interval}",
            "timezone": "exchange",
            "theme": "{theme}",
            "style": "1",
            "locale": "en",
            "enable_publishing": false,
            "hide_top_toolbar": false,
            "hide_legend": false,
            "save_image": true,
            "hide_volume": {hide_volume},
            "hide_side_toolbar": {hide_side_toolbar},
            "allow_symbol_change": true,
            "container_id": "tradingview_chart",
            "studies": ["Volume@tv-basicstudies"],
            {"'compare_symbols': [" + ", ".join([f'{{"symbol": "{t}", "position": "SameScale"}}' for t in tickers[1:]]) + "]," if len(tickers) > 1 else ""}
            "show_popup_button": true,
            "popup_width": "1000",
            "popup_height": "650"
        }});
    </script>
</body>
</html>'''

    return html


def generate_chartjs_pie_html(
    data: list[dict],
    title: str,
    chart_type: str = "doughnut",
    theme: str = "dark",
) -> str:
    """
    Generate HTML page with Apache ECharts pie/donut chart.

    Args:
        data: List of dicts with label, value, and optional color keys
        title: Chart title
        chart_type: "pie" or "doughnut"
        theme: "dark" or "light"

    Returns:
        Complete HTML page string
    """
    import json

    # Beautiful color palette with gradients
    default_colors = [
        "#5470c6",  # Royal Blue
        "#91cc75",  # Fresh Green
        "#fac858",  # Golden Yellow
        "#ee6666",  # Coral Red
        "#73c0de",  # Sky Blue
        "#3ba272",  # Emerald
        "#fc8452",  # Tangerine
        "#9a60b4",  # Purple
        "#ea7ccc",  # Pink
        "#48b8d0",  # Teal
        "#c4b5fd",  # Lavender
        "#6ee7b7",  # Mint
        "#fbbf24",  # Amber
        "#f87171",  # Light Red
        "#60a5fa",  # Light Blue
    ]

    # Prepare data for ECharts
    chart_data = []
    total = sum(item.get("value", 0) for item in data)

    for i, item in enumerate(data):
        chart_data.append({
            "name": item.get("label", f"Item {i+1}"),
            "value": round(item.get("value", 0), 2)
        })

    chart_data_json = json.dumps(chart_data)
    colors_json = json.dumps(default_colors[:len(data)])

    # Theme colors
    bg_color = "#0d1117" if theme == "dark" else "#ffffff"
    text_color = "#e6edf3" if theme == "dark" else "#1f2937"
    subtitle_color = "#8b949e" if theme == "dark" else "#6b7280"

    # Radius settings for pie vs donut
    radius = "['45%', '75%']" if chart_type == "doughnut" else "['0%', '75%']"

    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>{title}</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        html, body {{
            width: 100%;
            height: 100%;
            background: {bg_color};
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
            overflow: hidden;
        }}
        #chart {{
            width: 100%;
            height: 100%;
        }}
    </style>
</head>
<body>
    <div id="chart"></div>
    <script>
        const chart = echarts.init(document.getElementById('chart'), '{theme}');
        const total = {total};
        const isMobile = window.innerWidth < 768;

        const option = {{
            backgroundColor: '{bg_color}',
            title: {{
                text: '{title}',
                subtext: 'Total: $' + total.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}}),
                left: 'center',
                top: 20,
                textStyle: {{
                    color: '{text_color}',
                    fontSize: 22,
                    fontWeight: 600,
                    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
                }},
                subtextStyle: {{
                    color: '{subtitle_color}',
                    fontSize: 14,
                    fontWeight: 400
                }}
            }},
            tooltip: {{
                trigger: 'item',
                backgroundColor: '{"rgba(30, 41, 59, 0.95)" if theme == "dark" else "rgba(255, 255, 255, 0.95)"}',
                borderColor: '{"#334155" if theme == "dark" else "#e2e8f0"}',
                borderWidth: 1,
                borderRadius: 8,
                padding: [12, 16],
                textStyle: {{
                    color: '{text_color}',
                    fontSize: 13
                }},
                formatter: function(params) {{
                    const pct = ((params.value / total) * 100).toFixed(1);
                    return '<div style="font-weight: 600; margin-bottom: 4px;">' + params.name + '</div>' +
                           '<div style="color: {"#94a3b8" if theme == "dark" else "#64748b"}; font-size: 12px;">Value: <span style="color: {text_color}; font-weight: 500;">$' + params.value.toLocaleString(undefined, {{minimumFractionDigits: 2}}) + '</span></div>' +
                           '<div style="color: {"#94a3b8" if theme == "dark" else "#64748b"}; font-size: 12px;">Share: <span style="color: {text_color}; font-weight: 500;">' + pct + '%</span></div>';
                }}
            }},
            legend: {{
                type: 'scroll',
                orient: isMobile ? 'horizontal' : 'vertical',
                right: isMobile ? 'center' : 30,
                left: isMobile ? 'center' : 'auto',
                top: isMobile ? 'auto' : 'middle',
                bottom: isMobile ? 15 : 'auto',
                itemWidth: 12,
                itemHeight: 12,
                itemGap: isMobile ? 8 : 12,
                textStyle: {{
                    color: '{text_color}',
                    fontSize: isMobile ? 11 : 13,
                    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
                }},
                formatter: function(name) {{
                    const item = {chart_data_json}.find(d => d.name === name);
                    if (item) {{
                        const pct = ((item.value / total) * 100).toFixed(1);
                        return isMobile ? name : name + '  ' + pct + '%';
                    }}
                    return name;
                }},
                pageTextStyle: {{
                    color: '{subtitle_color}'
                }}
            }},
            color: {colors_json},
            series: [
                {{
                    name: 'Holdings',
                    type: 'pie',
                    radius: isMobile ? ['35%', '65%'] : {radius},
                    center: isMobile ? ['50%', '45%'] : ['40%', '55%'],
                    avoidLabelOverlap: true,
                    itemStyle: {{
                        borderRadius: 6,
                        borderColor: '{bg_color}',
                        borderWidth: 3,
                        shadowBlur: 10,
                        shadowColor: 'rgba(0, 0, 0, 0.2)'
                    }},
                    label: {{
                        show: true,
                        position: 'inside',
                        color: '#ffffff',
                        fontSize: 13,
                        fontWeight: 600,
                        formatter: function(params) {{
                            if (params.percent < 6) return '';
                            return params.percent.toFixed(1) + '%';
                        }},
                        textShadowColor: 'rgba(0, 0, 0, 0.5)',
                        textShadowBlur: 4
                    }},
                    labelLine: {{
                        show: false
                    }},
                    emphasis: {{
                        scale: true,
                        scaleSize: 8,
                        itemStyle: {{
                            shadowBlur: 20,
                            shadowColor: 'rgba(0, 0, 0, 0.3)'
                        }},
                        label: {{
                            show: true,
                            fontSize: 15,
                            fontWeight: 700,
                            formatter: function(params) {{
                                return params.name + '\\n' + params.percent.toFixed(1) + '%';
                            }}
                        }}
                    }},
                    data: {chart_data_json},
                    animationType: 'scale',
                    animationEasing: 'elasticOut',
                    animationDuration: 1000,
                    animationDelay: function(idx) {{
                        return idx * 50;
                    }}
                }}
            ]
        }};

        chart.setOption(option);

        // Responsive resize
        window.addEventListener('resize', function() {{
            chart.resize();
        }});
    </script>
</body>
</html>'''

    return html


def generate_treemap_html(
    data: list[dict],
    title: str,
    theme: str = "dark",
) -> str:
    """
    Generate HTML page with Apache ECharts treemap (heatmap-style).

    Args:
        data: List of dicts with label, value keys
        title: Chart title
        theme: "dark" or "light"

    Returns:
        Complete HTML page string
    """
    # Beautiful color palette
    default_colors = [
        "#5470c6", "#91cc75", "#fac858", "#ee6666", "#73c0de",
        "#3ba272", "#fc8452", "#9a60b4", "#ea7ccc", "#48b8d0",
        "#c4b5fd", "#6ee7b7", "#fbbf24", "#f87171", "#60a5fa",
    ]

    # Prepare data for ECharts treemap
    total = sum(item.get("value", 0) for item in data)
    treemap_data = []

    for i, item in enumerate(data):
        value = item.get("value", 0)
        pct = (value / total * 100) if total > 0 else 0
        treemap_data.append({
            "name": item.get("label", f"Item {i+1}"),
            "value": round(value, 2),
            "pct": round(pct, 1),
            "itemStyle": {"color": default_colors[i % len(default_colors)]}
        })

    treemap_data_json = json_module.dumps(treemap_data)

    # Theme colors
    bg_color = "#0d1117" if theme == "dark" else "#ffffff"
    text_color = "#e6edf3" if theme == "dark" else "#1f2937"
    subtitle_color = "#8b949e" if theme == "dark" else "#6b7280"
    border_color = "#1e293b" if theme == "dark" else "#e2e8f0"

    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>{title}</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        html, body {{
            width: 100%;
            height: 100%;
            background: {bg_color};
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
            overflow: hidden;
        }}
        #chart {{
            width: 100%;
            height: 100%;
        }}
    </style>
</head>
<body>
    <div id="chart"></div>
    <script>
        const chart = echarts.init(document.getElementById('chart'), '{theme}');
        const total = {total};
        const isMobile = window.innerWidth < 768;

        const option = {{
            backgroundColor: '{bg_color}',
            title: {{
                text: '{title}',
                subtext: 'Total: $' + total.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}}),
                left: 'center',
                top: 15,
                textStyle: {{
                    color: '{text_color}',
                    fontSize: isMobile ? 18 : 22,
                    fontWeight: 600
                }},
                subtextStyle: {{
                    color: '{subtitle_color}',
                    fontSize: isMobile ? 12 : 14
                }}
            }},
            tooltip: {{
                trigger: 'item',
                backgroundColor: '{"rgba(30, 41, 59, 0.95)" if theme == "dark" else "rgba(255, 255, 255, 0.95)"}',
                borderColor: '{"#334155" if theme == "dark" else "#e2e8f0"}',
                borderWidth: 1,
                borderRadius: 8,
                padding: [12, 16],
                textStyle: {{
                    color: '{text_color}',
                    fontSize: 13
                }},
                formatter: function(params) {{
                    const pct = params.data.pct;
                    return '<div style="font-weight: 600; margin-bottom: 4px;">' + params.name + '</div>' +
                           '<div style="color: {"#94a3b8" if theme == "dark" else "#64748b"}; font-size: 12px;">Value: <span style="color: {text_color}; font-weight: 500;">$' + params.value.toLocaleString(undefined, {{minimumFractionDigits: 2}}) + '</span></div>' +
                           '<div style="color: {"#94a3b8" if theme == "dark" else "#64748b"}; font-size: 12px;">Share: <span style="color: {text_color}; font-weight: 500;">' + pct + '%</span></div>';
                }}
            }},
            series: [
                {{
                    type: 'treemap',
                    top: isMobile ? 70 : 80,
                    left: 10,
                    right: 10,
                    bottom: 10,
                    roam: false,
                    nodeClick: false,
                    breadcrumb: {{
                        show: false
                    }},
                    label: {{
                        show: true,
                        formatter: function(params) {{
                            const pct = params.data.pct;
                            if (pct < 3) return '';
                            return params.name + '\\n' + pct + '%';
                        }},
                        color: '#ffffff',
                        fontSize: isMobile ? 11 : 13,
                        fontWeight: 600,
                        textShadowColor: 'rgba(0, 0, 0, 0.5)',
                        textShadowBlur: 4,
                        lineHeight: isMobile ? 16 : 20
                    }},
                    itemStyle: {{
                        borderColor: '{border_color}',
                        borderWidth: 2,
                        gapWidth: 2,
                        borderRadius: 4
                    }},
                    emphasis: {{
                        itemStyle: {{
                            shadowBlur: 20,
                            shadowColor: 'rgba(0, 0, 0, 0.3)'
                        }},
                        label: {{
                            fontSize: isMobile ? 13 : 15
                        }}
                    }},
                    data: {treemap_data_json},
                    animationDuration: 1000,
                    animationEasing: 'cubicOut'
                }}
            ]
        }};

        chart.setOption(option);

        window.addEventListener('resize', function() {{
            chart.resize();
        }});
    </script>
</body>
</html>'''

    return html


def generate_portfolio_page_html(
    holdings: list[dict],
    grouped_data: dict,
    total_value: float,
    currency: str,
    theme: str = "light",
) -> str:
    """
    Generate an interactive portfolio dashboard page with toggleable views.

    Args:
        holdings: List of holding dicts with symbol, name, category, brokerage, value
        grouped_data: Pre-computed groupings {ticker: [...], name: [...], category: [...], brokerage: [...]}
        total_value: Total portfolio value
        currency: Currency code for display
        theme: "dark" or "light"

    Returns:
        Complete HTML page string
    """
    # Beautiful color palette
    default_colors = [
        "#5470c6", "#91cc75", "#fac858", "#ee6666", "#73c0de",
        "#3ba272", "#fc8452", "#9a60b4", "#ea7ccc", "#48b8d0",
        "#c4b5fd", "#6ee7b7", "#fbbf24", "#f87171", "#60a5fa",
        "#a78bfa", "#34d399", "#fcd34d", "#fb7185", "#38bdf8",
    ]

    # Theme colors
    bg_color = "#0d1117" if theme == "dark" else "#ffffff"
    card_bg = "#161b22" if theme == "dark" else "#f6f8fa"
    text_color = "#e6edf3" if theme == "dark" else "#1f2937"
    subtitle_color = "#8b949e" if theme == "dark" else "#6b7280"
    border_color = "#30363d" if theme == "dark" else "#d1d5db"
    active_bg = "#238636" if theme == "dark" else "#1f883d"
    active_text = "#ffffff"
    button_hover = "#30363d" if theme == "dark" else "#e5e7eb"

    # JSON encode the data
    grouped_json = json_module.dumps(grouped_data)
    colors_json = json_module.dumps(default_colors)
    holdings_json = json_module.dumps(holdings)

    # Format total value for display
    formatted_total = f"{total_value:,.2f}"

    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Portfolio Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        html, body {{
            width: 100%;
            height: 100%;
            background: {bg_color};
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
            color: {text_color};
            overflow-x: hidden;
        }}
        .container {{
            display: flex;
            flex-direction: column;
            height: 100%;
            padding: 16px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            flex-wrap: wrap;
            gap: 8px;
        }}
        .title {{
            font-size: 24px;
            font-weight: 600;
        }}
        .total {{
            font-size: 18px;
            color: {subtitle_color};
        }}
        .total-value {{
            color: {text_color};
            font-weight: 600;
        }}
        .controls {{
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            margin-bottom: 16px;
        }}
        .control-group {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .control-label {{
            font-size: 13px;
            color: {subtitle_color};
            font-weight: 500;
        }}
        .toggle-group {{
            display: flex;
            background: {card_bg};
            border-radius: 8px;
            padding: 4px;
            border: 1px solid {border_color};
        }}
        .toggle-btn {{
            padding: 8px 16px;
            border: none;
            background: transparent;
            color: {text_color};
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            border-radius: 6px;
            transition: all 0.2s ease;
            white-space: nowrap;
        }}
        .toggle-btn:hover {{
            background: {button_hover};
        }}
        .toggle-btn.active {{
            background: {active_bg};
            color: {active_text};
        }}
        #chart {{
            flex: 1;
            min-height: 400px;
        }}
        @media (max-width: 768px) {{
            .container {{
                padding: 12px;
            }}
            .header {{
                flex-direction: column;
                align-items: flex-start;
            }}
            .title {{
                font-size: 20px;
            }}
            .total {{
                font-size: 14px;
            }}
            .controls {{
                flex-direction: column;
                width: 100%;
            }}
            .control-group {{
                width: 100%;
                justify-content: space-between;
            }}
            .toggle-group {{
                flex: 1;
            }}
            .toggle-btn {{
                flex: 1;
                padding: 10px 8px;
                font-size: 12px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="title">Portfolio Dashboard</div>
            <div class="total">Total: <span class="total-value">${formatted_total} {currency}</span></div>
        </div>

        <div class="controls">
            <div class="control-group">
                <span class="control-label">Chart:</span>
                <div class="toggle-group" id="chartTypeToggle">
                    <button class="toggle-btn active" data-type="pie">Pie</button>
                    <button class="toggle-btn" data-type="treemap">Treemap</button>
                </div>
            </div>

            <div class="control-group">
                <span class="control-label">Group by:</span>
                <div class="toggle-group" id="groupByToggle">
                    <button class="toggle-btn active" data-group="ticker">Ticker</button>
                    <button class="toggle-btn" data-group="name">Name</button>
                    <button class="toggle-btn" data-group="category">Category</button>
                    <button class="toggle-btn" data-group="brokerage">Brokerage</button>
                </div>
            </div>
        </div>

        <div id="chart"></div>
    </div>

    <script>
        // Embedded data
        const groupedData = {grouped_json};
        const colors = {colors_json};
        const holdings = {holdings_json};
        const total = {total_value};

        // State
        let currentChartType = 'pie';
        let currentGroupBy = 'ticker';

        // Initialize chart
        const chart = echarts.init(document.getElementById('chart'), '{theme}');
        const isMobile = window.innerWidth < 768;

        function formatNumber(num) {{
            return num.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
        }}

        function getChartOption(chartType, data) {{
            const chartData = data.map((item, i) => ({{
                name: item.label,
                value: item.value,
                pct: ((item.value / total) * 100).toFixed(1),
                itemStyle: {{ color: colors[i % colors.length] }}
            }}));

            // Get tickers that belong to a group
            function getTickersForGroup(groupBy, groupName) {{
                if (groupBy === 'ticker') return [];
                const fieldMap = {{
                    'name': 'consolidated_name',
                    'category': 'category',
                    'brokerage': 'brokerage'
                }};
                const field = fieldMap[groupBy];
                if (!field) return [];
                return holdings
                    .filter(h => h[field] === groupName)
                    .map(h => h.symbol)
                    .sort();
            }}

            const commonTooltip = {{
                trigger: 'item',
                backgroundColor: '{"rgba(30, 41, 59, 0.95)" if theme == "dark" else "rgba(255, 255, 255, 0.95)"}',
                borderColor: '{"#334155" if theme == "dark" else "#e2e8f0"}',
                borderWidth: 1,
                borderRadius: 8,
                padding: [12, 16],
                textStyle: {{
                    color: '{text_color}',
                    fontSize: 13
                }},
                formatter: function(params) {{
                    const pct = params.data.pct;
                    let html = '<div style="font-weight: 600; margin-bottom: 4px;">' + params.name + '</div>' +
                           '<div style="color: {"#94a3b8" if theme == "dark" else "#64748b"}; font-size: 12px;">Value: <span style="color: {text_color}; font-weight: 500;">$' + formatNumber(params.value) + '</span></div>' +
                           '<div style="color: {"#94a3b8" if theme == "dark" else "#64748b"}; font-size: 12px;">Share: <span style="color: {text_color}; font-weight: 500;">' + pct + '%</span></div>';

                    // Add ticker breakdown for grouped views
                    const tickers = getTickersForGroup(currentGroupBy, params.name);
                    if (tickers.length > 0) {{
                        html += '<div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid {"#334155" if theme == "dark" else "#e2e8f0"}; color: {"#94a3b8" if theme == "dark" else "#64748b"}; font-size: 11px;">Tickers: <span style="color: {text_color};">' + tickers.join(', ') + '</span></div>';
                    }}

                    return html;
                }}
            }};

            if (chartType === 'pie') {{
                return {{
                    backgroundColor: '{bg_color}',
                    tooltip: commonTooltip,
                    legend: {{
                        type: 'scroll',
                        orient: isMobile ? 'horizontal' : 'vertical',
                        right: isMobile ? 'center' : 20,
                        left: isMobile ? 'center' : 'auto',
                        top: isMobile ? 'auto' : 'middle',
                        bottom: isMobile ? 10 : 'auto',
                        itemWidth: 12,
                        itemHeight: 12,
                        itemGap: isMobile ? 8 : 10,
                        textStyle: {{
                            color: '{text_color}',
                            fontSize: isMobile ? 11 : 12
                        }},
                        formatter: function(name) {{
                            const item = chartData.find(d => d.name === name);
                            if (item) {{
                                return isMobile ? name : name + '  ' + item.pct + '%';
                            }}
                            return name;
                        }},
                        pageTextStyle: {{ color: '{subtitle_color}' }}
                    }},
                    series: [{{
                        type: 'pie',
                        radius: isMobile ? ['30%', '60%'] : ['40%', '70%'],
                        center: isMobile ? ['50%', '45%'] : ['35%', '50%'],
                        avoidLabelOverlap: true,
                        itemStyle: {{
                            borderRadius: 6,
                            borderColor: '{bg_color}',
                            borderWidth: 3,
                            shadowBlur: 10,
                            shadowColor: 'rgba(0, 0, 0, 0.2)'
                        }},
                        label: {{
                            show: true,
                            position: 'inside',
                            color: '#ffffff',
                            fontSize: 12,
                            fontWeight: 600,
                            formatter: function(params) {{
                                if (parseFloat(params.data.pct) < 5) return '';
                                return params.data.pct + '%';
                            }},
                            textShadowColor: 'rgba(0, 0, 0, 0.5)',
                            textShadowBlur: 4
                        }},
                        labelLine: {{ show: false }},
                        emphasis: {{
                            scale: true,
                            scaleSize: 8,
                            itemStyle: {{
                                shadowBlur: 20,
                                shadowColor: 'rgba(0, 0, 0, 0.3)'
                            }},
                            label: {{
                                show: true,
                                fontSize: 14,
                                fontWeight: 700,
                                formatter: function(params) {{
                                    return params.name + '\\n' + params.data.pct + '%';
                                }}
                            }}
                        }},
                        data: chartData,
                        animationType: 'scale',
                        animationEasing: 'elasticOut',
                        animationDuration: 800
                    }}]
                }};
            }} else {{
                // Treemap
                return {{
                    backgroundColor: '{bg_color}',
                    tooltip: commonTooltip,
                    series: [{{
                        type: 'treemap',
                        top: 10,
                        left: 10,
                        right: 10,
                        bottom: 10,
                        roam: false,
                        nodeClick: false,
                        breadcrumb: {{ show: false }},
                        label: {{
                            show: true,
                            formatter: function(params) {{
                                const pct = parseFloat(params.data.pct);
                                if (pct < 3) return '';
                                return params.name + '\\n' + params.data.pct + '%';
                            }},
                            color: '#ffffff',
                            fontSize: isMobile ? 11 : 13,
                            fontWeight: 600,
                            textShadowColor: 'rgba(0, 0, 0, 0.5)',
                            textShadowBlur: 4,
                            lineHeight: isMobile ? 16 : 20
                        }},
                        itemStyle: {{
                            borderColor: '{"#1e293b" if theme == "dark" else "#e2e8f0"}',
                            borderWidth: 2,
                            gapWidth: 2,
                            borderRadius: 4
                        }},
                        emphasis: {{
                            itemStyle: {{
                                shadowBlur: 20,
                                shadowColor: 'rgba(0, 0, 0, 0.3)'
                            }},
                            label: {{ fontSize: isMobile ? 13 : 15 }}
                        }},
                        data: chartData,
                        animationDuration: 800,
                        animationEasing: 'cubicOut'
                    }}]
                }};
            }}
        }}

        function updateChart() {{
            const data = groupedData[currentGroupBy] || [];
            const option = getChartOption(currentChartType, data);
            chart.setOption(option, true);
        }}

        // Event handlers for toggles
        document.getElementById('chartTypeToggle').addEventListener('click', function(e) {{
            if (e.target.classList.contains('toggle-btn')) {{
                this.querySelectorAll('.toggle-btn').forEach(btn => btn.classList.remove('active'));
                e.target.classList.add('active');
                currentChartType = e.target.dataset.type;
                updateChart();
            }}
        }});

        document.getElementById('groupByToggle').addEventListener('click', function(e) {{
            if (e.target.classList.contains('toggle-btn')) {{
                this.querySelectorAll('.toggle-btn').forEach(btn => btn.classList.remove('active'));
                e.target.classList.add('active');
                currentGroupBy = e.target.dataset.group;
                updateChart();
            }}
        }});

        // Initial render
        updateChart();

        // Responsive resize
        window.addEventListener('resize', function() {{
            chart.resize();
        }});
    </script>
</body>
</html>'''

    return html
