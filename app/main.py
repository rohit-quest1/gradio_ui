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
            label="Redis Migration Assessment",
            render=True,  # Enable rendering of components
            height=600
        )
        msg = gr.Textbox(
            label="Your Response",
            placeholder="Type your response here...",
            elem_id="inputTextBox"  # Add elem_id for JavaScript to target
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

# Function to reload JavaScript for button functionality
def reload_javascript():
    js = """
    <!-- Bootstrap CSS and JS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" integrity="sha384-9ndCyUaIbzAi2FUVXJi0CjmCapSmO7SnpJef0486qhLnuZ2cdeRhO02iuK6FUUVM" crossorigin="anonymous">
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js" integrity="sha384-geWF76RCwLtnZ8qwWowPQNguL3RmwHVBC9FhGdlKrxdiJJigb/j/68SIy3Te4Bkz" crossorigin="anonymous"></script>

    <!-- Custom CSS for buttons -->
    <style>
    .btn-chatbot {
        margin: 5px;
        padding: 8px 16px;
        border-radius: 20px;
        font-weight: 500;
        transition: all 0.3s ease;
    }
    .btn-primary.btn-chatbot {
        background-color: #2E75B6;
        border-color: #2E75B6;
    }
    .btn-primary.btn-chatbot:hover {
        background-color: #1A5DAB;
        border-color: #1A5DAB;
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    .btn-secondary.btn-chatbot {
        background-color: #6c757d;
        border-color: #6c757d;
    }
    .btn-secondary.btn-chatbot:hover {
        background-color: #5a6268;
        border-color: #5a6268;
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    .btn-success.btn-chatbot {
        background-color: #28a745;
        border-color: #28a745;
    }
    .btn-success.btn-chatbot:hover {
        background-color: #218838;
        border-color: #218838;
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    </style>

    <!-- JavaScript for button functionality -->
    <script>
    function registerMessageButtons() {
        const collection = document.querySelectorAll(".btn-chatbot");
        for (let i = 0; i < collection.length; i++) {
            collection[i].onclick = function() {
                const elem = document.getElementById("inputTextBox").getElementsByTagName('textarea')[0];
                elem.value = collection[i].getAttribute("value");
                elem.dispatchEvent(new Event('input', {
                    view: window,
                    bubbles: true,
                    cancelable: true
                }));
                
                // Trigger the Enter key press to submit the form
                elem.dispatchEvent(new KeyboardEvent('keydown', {
                    key: 'Enter',
                    code: 'Enter',
                    keyCode: 13,
                    which: 13,
                    bubbles: true,
                    cancelable: true
                }));
            };
        }
    }
    
    // Run registerMessageButtons periodically to catch new buttons
    var intervalId = window.setInterval(function(){
        registerMessageButtons();
    }, 1000);
    </script>
    """
    
    # Store the original TemplateResponse
    GradioTemplateResponseOriginal = gr.routes.templates.TemplateResponse
    
    # Override the TemplateResponse to inject our JavaScript
    def template_response(*args, **kwargs):
        res = GradioTemplateResponseOriginal(*args, **kwargs)
        res.body = res.body.replace(b'</html>', f'{js}</html>'.encode("utf8"))
        res.init_headers()
        return res
    
    gr.routes.templates.TemplateResponse = template_response

# Apply JavaScript injection
reload_javascript()

# Mount Gradio interface
app = gr.mount_gradio_app(app, create_gradio_interface(), path="/")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)