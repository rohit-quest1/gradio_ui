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

def create_gradio_interface():
    chat_ui = ChatUI()
    
    with gr.Blocks(theme=gr.themes.Default(font=[gr.themes.GoogleFont("Inconsolata"), "Arial", "sans-serif"])) as interface:
        gr.Markdown("# Quester - Redis Migration Assessment Tool")
        
        # Chat Tab - Now the only tab
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
    
    return interface

# Mount Gradio interface
app = gr.mount_gradio_app(app, create_gradio_interface(), path="/")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)