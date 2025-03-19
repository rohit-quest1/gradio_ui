from app.services.memcached_service import validate_memcached_connection, profile_memcached
import logging
import json
import matplotlib.pyplot as plt
import seaborn as sns
import os
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import gradio as gr

import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_RETRIES = 3


with open("./app/questionnaire.json") as f:
    QUESTIONNAIRE = json.load(f)


class ChatUI:
    def __init__(self):
        self.current_section = 0
        self.current_subsection = 0
        self.responses = {}
        self.memcached_url = None
        self.profiling_results = None
        self.is_url_validated = False
        self.welcome_message = """
# Welcome to Quester - Redis Migration Assessment Tool

I'm your AI assistant specializing in Memcached to Redis migrations. I'll help you assess your migration initiative through a series of questions and technical analysis.

To begin, please provide your Memcached URL for analysis, or type "skip" to proceed with the questionnaire."""

    def reset(self):
        self.current_section = 0
        self.current_subsection = 0
        self.responses = {}
        self.memcached_url = None
        self.profiling_results = None
        self.is_url_validated = False
        return [(None, self.welcome_message)]

    async def handle_url_input(self, url: str) -> str:
        if url.lower() == "skip":
            # Allow skipping and proceed to questionnaire
            self.is_url_validated = True  # Set this to true even though we're skipping
            return "Skipping Memcached connection. Proceeding with the questionnaire."
        
        is_valid = await validate_memcached_connection(url)
        if is_valid:
            self.memcached_url = url
            self.is_url_validated = True
            # Start profiling asynchronously
            asyncio.create_task(self.start_profiling())
            return "Successfully connected to Memcached. Starting profiling in background. Let's proceed with the assessment questions."
        else:
            # Reset state to initial and return to welcome
            self.reset()
            return f"Failed to connect to Memcached after {MAX_RETRIES} attempts. Please try again with a valid URL or type 'skip' to proceed without connection analysis."

    async def start_profiling(self):
        if self.memcached_url:
            self.profiling_results = await profile_memcached(self.memcached_url)
            logger.info("Profiling completed")

    def get_current_question(self):
        if self.current_section >= len(QUESTIONNAIRE["sections"]):
            return None, None
        section = QUESTIONNAIRE["sections"][self.current_section]
        subsection = section["subSections"][self.current_subsection]
        return section, subsection

    def render_question(self, section, subsection):
        if "isMultiSelect" in subsection and subsection["isMultiSelect"]:
            # Create buttons for multi-select options with different styling
            buttons_html = ""
            for i, opt in enumerate(subsection["options"]):
                # Use the actual option text as the value
                buttons_html += f'<a class="btn btn-primary btn-chatbot text-white" value="{opt}">{opt}</a> '
            
            return f"""### {section['name']}
#### {subsection['name']}
Select all that apply (click on your choices):

{buttons_html}"""
        else:
            # Create buttons for single-select options
            buttons_html = ""
            for i, opt in enumerate(subsection["options"]):
                # Use the actual option text as the value
                buttons_html += f'<a class="btn btn-primary btn-chatbot text-white" value="{opt}">{opt}</a> '
            
            return f"""### {section['name']}
#### {subsection['name']}
Select one option (click on your choice):

{buttons_html}"""

    def generate_charts(self):
        # Create charts directory if it doesn't exist
        os.makedirs("./app/output/charts", exist_ok=True)
        
        # Load data from JSON files
        with open("./app/output/data_profiler_stats.json") as f:
            data_profiler = json.load(f)
        with open("./app/output/usage_profiler_stats.json") as f:
            usage_profiler = json.load(f)

        # 1. Reads vs Writes Pie Chart
        read_percent = usage_profiler['read_write_ratio']['read_percent']
        write_percent = usage_profiler['read_write_ratio']['write_percent']
        reads_vs_writes = px.pie(
            values=[read_percent, write_percent], 
            names=['Reads', 'Writes'],
            title='Reads vs Writes',
            color_discrete_sequence=px.colors.sequential.Blues_r
        )
        reads_vs_writes.update_traces(textinfo='percent+label')
        reads_vs_writes.update_layout(height=400, width=600)
        # Save as full HTML with Plotly.js included
        pio.write_html(reads_vs_writes, './app/output/charts/reads_vs_writes.html', full_html=True, include_plotlyjs='cdn')
        # Also save as image for the chat tab
        reads_vs_writes.write_image('./app/output/charts/reads_vs_writes.png')

        # 2. Key Size Distribution Histogram
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
        key_dist.update_layout(bargap=0.1, height=400, width=800)
        pio.write_html(key_dist, './app/output/charts/key_size_distribution.html', full_html=True, include_plotlyjs='cdn')
        key_dist.write_image('./app/output/charts/key_size_distribution.png')

        # 3. Value Size Distribution Histogram
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
        value_dist.update_layout(bargap=0.1, height=400, width=800)
        pio.write_html(value_dist, './app/output/charts/value_size_distribution.html', full_html=True, include_plotlyjs='cdn')
        value_dist.write_image('./app/output/charts/value_size_distribution.png')

        # 4. TTL Distribution Histogram
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
        ttl_dist.update_layout(xaxis_tickangle=-45, height=400, width=800)
        pio.write_html(ttl_dist, './app/output/charts/ttl_distribution.html', full_html=True, include_plotlyjs='cdn')
        ttl_dist.write_image('./app/output/charts/ttl_distribution.png')

        # 5. Memory per Shard Radial Chart
        memory_per_shard = data_profiler['operational_metrics']['client_connections']['average_per_shard']
        total_memory = data_profiler['memory_analysis']['total_memory_used_bytes']
        
        # Create an interesting gauge chart for memory per shard
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
        memory_gauge.update_layout(height=400, width=600)
        pio.write_html(memory_gauge, './app/output/charts/memory_per_shard.html', full_html=True, include_plotlyjs='cdn')
        memory_gauge.write_image('./app/output/charts/memory_per_shard.png')
        
        # Return the plotly figures for inline display
        return reads_vs_writes, key_dist, value_dist, ttl_dist, memory_gauge

    async def handle_response(self, response, chat_history):
        # Handle initial URL input
        print(f"Chat history length: {len(chat_history)}")
        print(f"Response received: {response}")
        
        if len(chat_history) == 1 and chat_history[0][0] is None:  # Only welcome message present
            print("Processing URL input")
            result = await self.handle_url_input(response)
            chat_history.append((response, result))
            if not self.is_url_validated:
                return chat_history, ""  # Early return if URL is not validated
            section, subsection = self.get_current_question()
            if section and subsection:
                question = self.render_question(section, subsection)
                chat_history.append((None, question))
            return chat_history, ""
        
        # Handle questionnaire responses
        section, subsection = self.get_current_question()
        if section and subsection:
            key = f"{section['name']}_{subsection['name']}"
            
            # Process button selections (which now contain the actual option text)
            try:
                if "isMultiSelect" in subsection and subsection["isMultiSelect"]:
                    # For multi-select, process comma-separated values
                    selected_options = [opt.strip() for opt in response.split(',')]
                    # Validate that all options exist in the available options
                    valid_options = [opt for opt in selected_options if opt in subsection["options"]]
                    self.responses[key] = valid_options
                    # Format the response to show what was selected
                    formatted_response = f"Selected: {', '.join(valid_options)}"
                else:
                    # For single-select, the response is the option text
                    if response in subsection["options"]:
                        selected_option = response
                        self.responses[key] = selected_option
                        # Format the response to show what was selected
                        formatted_response = f"Selected: {selected_option}"
                    else:
                        formatted_response = f"Invalid selection. Please select one of the provided options."
                        chat_history.append((response, formatted_response))
                        return chat_history, ""
            except Exception as e:
                formatted_response = f"Error processing selection: {str(e)}"
                chat_history.append((response, formatted_response))
                return chat_history, ""
            
            # Move to next question
            if self.current_subsection + 1 < len(section["subSections"]):
                self.current_subsection += 1
            else:
                self.current_section += 1
                self.current_subsection = 0
            
            chat_history.append((response, formatted_response))
            
            # Check if questionnaire is complete
            new_section, new_subsection = self.get_current_question()
            if new_section and new_subsection:
                question = self.render_question(new_section, new_subsection)
                chat_history.append((None, question))
            else:
                # Generate final report
                report = "# Migration Assessment Report\n\n"
                if self.profiling_results:
                    report += "## Memcached Profile\n"
                    for key, value in self.profiling_results.items():
                        report += f"- {key}: {value}\n"
                
                # Generate charts and get the plotly figures
                reads_vs_writes, key_dist, value_dist, ttl_dist, memory_gauge = self.generate_charts()
                
                report += "\n## Assessment Summary\n"
                report += "Based on your responses, here are the key recommendations:\n"
                report += "\n1. Implementation will be logged here in future updates"
                report += "\n\n## Visualizations\n"
                report += "Here are interactive visualizations of your Memcached data:\n\n"
                
                # Add the report text to chat history
                chat_history.append((None, report))
                
                # Add each chart as a separate message with a Gradio plot component
                chat_history.append((None, gr.Plot(reads_vs_writes, label="Reads vs Writes")))
                chat_history.append((None, gr.Plot(key_dist, label="Key Size Distribution")))
                chat_history.append((None, gr.Plot(value_dist, label="Value Size Distribution")))
                chat_history.append((None, gr.Plot(ttl_dist, label="TTL Distribution")))
                chat_history.append((None, gr.Plot(memory_gauge, label="Memory per Shard")))
            
            return chat_history, ""
        return chat_history, ""