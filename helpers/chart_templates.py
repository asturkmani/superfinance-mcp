"""HTML template generators for chart tools."""

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
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
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
                orient: 'vertical',
                right: 30,
                top: 'middle',
                itemWidth: 14,
                itemHeight: 14,
                itemGap: 12,
                textStyle: {{
                    color: '{text_color}',
                    fontSize: 13,
                    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
                }},
                formatter: function(name) {{
                    const item = {chart_data_json}.find(d => d.name === name);
                    if (item) {{
                        const pct = ((item.value / total) * 100).toFixed(1);
                        return name + '  ' + pct + '%';
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
                    radius: {radius},
                    center: ['40%', '55%'],
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
                        position: 'outside',
                        color: '{text_color}',
                        fontSize: 12,
                        fontWeight: 500,
                        formatter: function(params) {{
                            if (params.percent < 5) return '';
                            return params.name;
                        }},
                        distanceToLabelLine: 5
                    }},
                    labelLine: {{
                        show: true,
                        length: 15,
                        length2: 10,
                        smooth: true,
                        lineStyle: {{
                            color: '{subtitle_color}',
                            width: 1
                        }}
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
                            fontSize: 14,
                            fontWeight: 600
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
