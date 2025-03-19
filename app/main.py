import json
import asyncio
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import gradio as gr
from app.ui.chat_ui import ChatUI
from app.services.memcached_service import validate_memcached_connection, profile_memcached
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import matplotlib.pyplot as plt
import os

# Initialize FastAPI app and logger
app = FastAPI()
app.mount("/charts", StaticFiles(directory="./app/output/charts", html=True), name="charts")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_visualizations():
    """Load the visualization data for the visualization tab"""
    # Load data from JSON files
    with open("./app/output/data_profiler_stats.json") as f:
        data_profiler = json.load(f)
    with open("./app/output/usage_profiler_stats.json") as f:
        usage_profiler = json.load(f)
    
    # 1. Reads vs Writes
    read_percent = usage_profiler['read_write_ratio']['read_percent']
    write_percent = usage_profiler['read_write_ratio']['write_percent']
    reads_vs_writes = px.pie(
        values=[read_percent, write_percent], 
        names=['Reads', 'Writes'],
        title='Reads vs Writes',
        color_discrete_sequence=px.colors.sequential.Blues_r
    )
    
    # 2. Key Size Distribution
    key_size_distribution = data_profiler['key_value_stats']['key_stats']['key_size_distribution']['buckets']
    key_sizes = [bucket['bytes_range']['max'] for bucket in key_size_distribution]
    key_counts = [bucket['count'] for bucket in key_size_distribution]
    key_size_df = {'Key Size (bytes)': key_sizes, 'Count': key_counts}
    key_dist = px.bar(
        key_size_df, 
        x='Key Size (bytes)', 
        y='Count',
        title='Key Size Distribution',
        color='Count',
        color_continuous_scale=px.colors.sequential.Blues
    )
    
    # 3. Value Size Distribution
    value_size_distribution = data_profiler['key_value_stats']['value_analysis']['value_size_distribution']['buckets']
    value_sizes = [bucket['bytes_range']['max'] for bucket in value_size_distribution]
    value_counts = [bucket['count'] for bucket in value_size_distribution]
    value_size_df = {'Value Size (bytes)': value_sizes, 'Count': value_counts}
    value_dist = px.bar(
        value_size_df, 
        x='Value Size (bytes)', 
        y='Count',
        title='Value Size Distribution',
        color='Count',
        color_continuous_scale=px.colors.sequential.Blues
    )
    
    # 4. TTL Distribution
    ttl_distribution = data_profiler['ttl_stats']['ttl_distribution']['histogram']
    ttl_ranges = [f"{bucket['seconds_range']['min']} - {bucket['seconds_range']['max']}" for bucket in ttl_distribution]
    ttl_counts = [bucket['count'] for bucket in ttl_distribution]
    ttl_df = {'TTL Range (seconds)': ttl_ranges, 'Count': ttl_counts}
    ttl_dist = px.bar(
        ttl_df,
        x='TTL Range (seconds)',
        y='Count',
        title='TTL Distribution',
        color='Count',
        color_continuous_scale=px.colors.sequential.Blues
    )
    
    # 5. Memory per Shard
    memory_per_shard = data_profiler['operational_metrics']['client_connections']['average_per_shard']
    memory_gauge = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = memory_per_shard,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': "Memory per Shard"},
        gauge = {
            'axis': {'range': [None, 100]},
            'bar': {'color': "#2E75B6"},
            'steps': [
                {'range': [0, 30], 'color': "#D6EAF8"},
                {'range': [30, 70], 'color': "#AED6F1"},
                {'range': [70, 100], 'color': "#3498DB"}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': 80
            }
        }
    ))
    
    return reads_vs_writes, key_dist, value_dist, ttl_dist, memory_gauge

def create_gradio_interface():
    chat_ui = ChatUI()
    
    with gr.Blocks(theme=gr.themes.Default(font=[gr.themes.GoogleFont("Inconsolata"), "Arial", "sans-serif"])) as interface:
        gr.Markdown("# Quester - Redis Migration Assessment Tool")
        
        with gr.Tabs():
            # Chat Tab
            with gr.TabItem("Assessment Chat"):
                chatbot = gr.Chatbot(
                    label="Redis Migration Assessment"
                )
                msg = gr.Textbox(
                    label="Your Response",
                    placeholder="Type your response here..."
                )
                clear = gr.Button("Start Over")
                
                async def respond(message, chat_history):
                    return await chat_ui.handle_response(message, chat_history)
                
                msg.submit(
                    respond,
                    [msg, chatbot],
                    [chatbot, msg]
                )
                
                clear.click(
                    chat_ui.reset,
                    outputs=[chatbot]
                )
                
                interface.load(
                    lambda: [(None, chat_ui.welcome_message)],
                    outputs=[chatbot]
                )
            
            
            with gr.TabItem("Interactive Visualizations"):
                gr.Markdown("## Interactive Redis Migration Visualizations")
                
                # Create a function to refresh visualizations
                def refresh_visualizations():
                    # Check if visualization files exist
                    if not os.path.exists("./app/output/charts"):
                        return "Visualizations not yet generated. Please complete the assessment first."
                    
                    html_content = ""
                    
                    # Add HTML iframe elements for each chart
                    chart_files = [
                        "reads_vs_writes.html",
                        "key_size_distribution.html",
                        "value_size_distribution.html",
                        "ttl_distribution.html",
                        "memory_per_shard.html"
                    ]
                    
                    for chart in chart_files:
                        if os.path.exists(f"./app/output/charts/{chart}"):
                            chart_name = chart.replace(".html", "").replace("_", " ").title()
                            html_content += f"<h3>{chart_name}</h3>"
                            html_content += f"<iframe src='/charts/{chart}' width='100%' height='400px' style='border:none;'></iframe>"
                        
                    if not html_content:
                        return "Visualization files not found. Please complete the assessment first."
                    
                    return html_content
                
                # Display button to refresh visualizations
                refresh_btn = gr.Button("Refresh Visualizations")
                viz_html = gr.HTML(refresh_visualizations())
                
                refresh_btn.click(refresh_visualizations, outputs=viz_html)
    
    return interface

# Mount Gradio interface
app = gr.mount_gradio_app(app, create_gradio_interface(), path="/")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)